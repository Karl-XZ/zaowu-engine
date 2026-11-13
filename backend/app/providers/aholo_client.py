"""Aholo REST contract: https://labs.aholo.ai/api-docs/openapi.yaml.

Creation is deliberately never retried: the public API has no documented
idempotency guarantee. A lost response must be reconciled with the provider.
"""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urlsplit

import httpx

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_MODEL_BYTES = 200 * 1024 * 1024


class AholoError(Exception):
    pass


class AholoCreateUncertain(AholoError):
    pass


class AholoTaskTimeout(AholoError):
    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f'Aholo task {task_id} timed out; resume this task, do not create another')


def https_url(value: str) -> str:
    if not isinstance(value, str):
        raise AholoError('Aholo returned a missing URL')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise AholoError('Aholo returned an invalid HTTPS URL')
    return value


def response_data(response: httpx.Response):
    if response.is_error:
        raise AholoError(f'Aholo HTTP {response.status_code}')
    try:
        body = response.json()
    except ValueError as exc:
        raise AholoError('Aholo returned invalid JSON') from exc
    if not isinstance(body, dict) or str(body.get('c')) != '0':
        code = body.get('c', 'invalid-envelope') if isinstance(body, dict) else 'invalid-envelope'
        raise AholoError(f'Aholo rejected request ({code})')
    return body.get('d')


def create(client: httpx.Client, base: str, key: str, operation: str, payload: dict, idempotency_key: str | None = None) -> str:
    from ..config import settings
    path = f'/lux3d/v1/generate/{operation}/task/create'
    if getattr(settings, 'aholo_quote_enabled', False):
        from .aholo_quote import approve
        approve(client, base, key, path, payload, getattr(settings, 'aholo_max_call_credits', 64))
    headers = {'Authorization': key}
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    try:
        response = client.post(base.rstrip('/') + path, headers=headers, json=payload)
    except httpx.TransportError as exc:
        raise AholoCreateUncertain('Aholo create outcome uncertain; reconcile task history before retrying') from exc
    if response.status_code >= 500:
        raise AholoCreateUncertain('Aholo create returned a server error; outcome uncertain, reconcile before retrying')
    if not response.is_error:
        try:
            envelope = response.json()
        except ValueError as exc:
            raise AholoCreateUncertain('Aholo create returned invalid JSON; outcome uncertain, reconcile before retrying') from exc
        if not isinstance(envelope, dict) or 'c' not in envelope or envelope['c'] is None:
            raise AholoCreateUncertain('Aholo create returned an invalid envelope; outcome uncertain, reconcile before retrying')
    data = response_data(response)
    if isinstance(data, bool) or not isinstance(data, (str, int)) or not str(data).isdigit() or int(data) <= 0:
        raise AholoCreateUncertain('Aholo create returned no usable task ID; outcome uncertain, do not retry')
    return str(data)


def wait_for(client: httpx.Client, base: str, key: str, task_id: str, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            data = response_data(client.get(base.rstrip('/') + '/lux3d/v1/generate/task/get', headers={'Authorization': key}, params={'taskid': task_id}, timeout=min(30, max(.01, deadline-time.monotonic()))))
        except httpx.TransportError:
            data = None  # Querying an existing task is safe to retry.
        if data is not None:
            if not isinstance(data, dict) or str(data.get('status')) not in {'0', '1', '3', '4', '6'}:
                raise AholoError(f'Aholo task {task_id} returned an invalid status')
            if str(data['status']) in {'3', '4', '6'}:
                return data
        time.sleep(min(3, max(0, deadline-time.monotonic())))
    raise AholoTaskTimeout(task_id)


def output_urls(data: dict) -> list[str]:
    outputs = data.get('outputs') or []
    if not isinstance(outputs, list):
        raise AholoError('Aholo returned invalid outputs')
    return [https_url(item['content']) for item in outputs if isinstance(item, dict) and isinstance(item.get('content'), str) and item['content'].startswith('https://')]


def download_bytes(client: httpx.Client, url: str, max_bytes: int) -> bytes:
    # No API credentials are attached to third-party asset downloads.
    with client.stream('GET', https_url(url), timeout=120, follow_redirects=False) as response:
        if response.status_code != 200:
            raise AholoError(f'Aholo asset HTTP {response.status_code}')
        try:
            declared = int(response.headers.get('content-length', '0'))
        except ValueError as exc:
            raise AholoError('Aholo asset has invalid size') from exc
        if declared > max_bytes:
            raise AholoError('Aholo asset exceeds size limit')
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise AholoError('Aholo asset exceeds size limit')
            chunks.append(chunk)
    return b''.join(chunks)


def upload_image(client: httpx.Client, base: str, key: str, image: bytes) -> str:
    try:
        return _upload_image(client, base, key, image)
    except httpx.HTTPError as exc:
        raise AholoError('Aholo reference upload failed before generation was submitted') from exc


def _upload_image(client: httpx.Client, base: str, key: str, image: bytes) -> str:
    if not image or len(image) > MAX_IMAGE_BYTES:
        raise AholoError('Reference image is empty or exceeds 20 MB')
    response = client.get(base.rstrip('/') + '/asset/v1/token', headers={'Authorization': key})
    if response.is_error:
        raise AholoError(f'Aholo upload token HTTP {response.status_code}')
    try:
        token = response.json()
        domain = https_url(token['globalDomain']).rstrip('/')
        headers = {'ous-token-v2': token['ousToken']}
        block_size = int(token['blockSize'])
        if block_size <= 0 or not token['ousToken']:
            raise ValueError()
    except (ValueError, KeyError, TypeError) as exc:
        raise AholoError('Aholo returned invalid upload credentials') from exc
    digest = hashlib.md5(image).hexdigest()  # Required by the upload protocol, not cryptographic authentication.
    if len(image) <= block_size:
        response_data(client.post(domain + '/ous/api/v2/single/upload', headers=headers, data={'md5': digest}, files={'file': ('concept.png', image, 'image/png')}))
    else:
        blocks = (len(image) + block_size - 1) // block_size
        init = response_data(client.post(domain + '/ous/api/v2/block/upload/init', headers=headers, params={'md5': digest, 'blocks': blocks, 'size': len(image), 'name': 'concept.png'}))
        if not isinstance(init, dict):
            raise AholoError('Aholo returned invalid upload initialization')
        if not init.get('deduplicated'):
            for index in range(blocks):
                part = image[index*block_size:(index+1)*block_size]
                response_data(client.post(domain + '/ous/api/v2/block/upload/part', headers=headers, data={'block': str(index+1)}, files={'file': ('concept.png', part, 'application/octet-stream')}))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        data = response_data(client.get(domain + '/ous/api/v2/upload/status', headers=headers))
        if not isinstance(data, dict):
            raise AholoError('Aholo returned invalid upload status')
        if str(data.get('status')) == '5':
            return https_url(data.get('url'))
        if str(data.get('status')) in {'6', '8'}:
            raise AholoError('Aholo reference upload failed')
        time.sleep(.25)
    raise AholoError('Aholo reference upload timed out before generation')
