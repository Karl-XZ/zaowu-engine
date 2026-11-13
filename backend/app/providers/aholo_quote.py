"""Read-only regional MCP account/quote gate before REST task creation.

Quotes are account-benefit-free credit estimates, never RMB or billed charges.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import urlsplit

import httpx

from .aholo_client import AholoError


class AholoQuoteRejected(AholoError):
    """No generation was submitted; account/quote approval failed."""


def _call(client: httpx.Client, url: str, key: str, name: str, arguments: dict) -> dict:
    response = client.post(url, headers={'Authorization': key, 'Accept': 'application/json, text/event-stream'}, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}, timeout=30)
    if response.status_code != 200:
        raise AholoQuoteRejected(f'Aholo quote service HTTP {response.status_code}; generation was not submitted')
    if 'text/event-stream' in response.headers.get('content-type', ''):
        messages = []
        for event in response.text.replace('\r\n', '\n').split('\n\n'):
            data = '\n'.join(line[5:].lstrip() for line in event.splitlines() if line.startswith('data:'))
            if data:
                messages.append(json.loads(data))
        envelope = next((item for item in reversed(messages) if 'result' in item or 'error' in item), {})
    else:
        envelope = response.json()
    result = envelope.get('result')
    if not isinstance(result, dict) or result.get('isError') or envelope.get('error'):
        raise AholoQuoteRejected('Aholo quote service rejected request; generation was not submitted')
    body = result.get('structuredContent')
    if not isinstance(body, dict):
        body = next((json.loads(item['text']) for item in result.get('content', []) if item.get('type') == 'text'), {})
    if not isinstance(body, dict) or str(body.get('c')) != '0' or not isinstance(body.get('d'), dict):
        raise AholoQuoteRejected('Aholo account/quote unavailable; generation was not submitted')
    return body['d']


def approve(client: httpx.Client, base: str, key: str, path: str, payload: dict, max_credits: int) -> dict:
    host = urlsplit(base).hostname
    if host not in {'api.aholo3d.cn', 'api.aholo.ai'}:
        raise AholoQuoteRejected('Quote gate requires an official regional Aholo API host')
    url = f'https://{host}/lux3d-mcp/mcp'
    identity = {'source': 100, 'agentName': 'ZaowuEngine'}
    try:
        account = _call(client, url, key, 'getlux3daccountbalance', identity)
        available = account.get('availableCredits')
        context = account.get('uniqueId')
        if type(available) is not int or available < 0 or not isinstance(context, str) or not context:
            raise AholoQuoteRejected('Aholo account balance/context missing; generation was not submitted')
        quote = _call(client, url, key, 'post_quotelux3dopenapirequests', {'body': {**identity, 'uniqueId': context, 'items': {'1': {
            'endpoint': {'method': 'POST', 'path': path},
            'parameters': {'pathParameters': '{}', 'queryParameters': '{}', 'body': json.dumps(payload, ensure_ascii=False)},
        }}}})
        credits = quote.get('estimatedCreditsTotal')
        expires = datetime.fromisoformat(quote['expiresAt'].replace('Z', '+00:00'))
        if (type(credits) is not int or credits < 0 or type(max_credits) is not int or max_credits < 0
                or credits > max_credits or credits > available):
            raise AholoQuoteRejected('Aholo credit quote exceeds the call cap or available balance; generation was not submitted')
        if (quote.get('uniqueId') != context or quote.get('source') != 100 or not quote.get('quoteId')
                or quote.get('details') != {'1': credits} or expires <= datetime.now(timezone.utc)):
            raise AholoQuoteRejected('Aholo quote is expired or inconsistent; generation was not submitted')
        # Trial counters do not waive the conservative credit balance requirement.
        return quote
    except AholoQuoteRejected:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise AholoQuoteRejected('Aholo account/quote check failed; generation was not submitted') from exc
