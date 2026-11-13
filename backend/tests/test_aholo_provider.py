import io
import json
import struct
import zipfile

import httpx
import pytest
from PIL import Image

from app.config import settings
from app.providers import aholo, image


@pytest.fixture
def real(monkeypatch):
    monkeypatch.setattr(settings, 'aholo_quote_enabled', False, raising=False)
    monkeypatch.setattr(settings, 'aholo_api_base', 'https://api.aholo3d.cn')
    monkeypatch.setattr(settings, 'aholo_api_key', 'test-key')
    monkeypatch.setattr(settings, 'image_provider', 'aholo')
    monkeypatch.setattr(settings, 'image_api_base', 'https://api.aholo3d.cn')
    monkeypatch.setattr(settings, 'image_api_key', 'image-key')
    client = httpx.Client
    def install(handler):
        monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    return install


def envelope(data, code='0'):
    return httpx.Response(200, json={'f': None, 'c': code, 'm': '', 'd': data})


def test_submit_uploads_reference_and_uses_official_json_contract(real):
    paths = []
    def handler(req):
        paths.append(req.url.path)
        if req.url.path == '/asset/v1/token':
            assert req.headers['Authorization'] == 'test-key'
            return httpx.Response(200, json={'ousToken': 'upload-token', 'globalDomain': 'https://ous.example.com', 'blockSize': 100})
        if req.url.path == '/ous/api/v2/single/upload':
            assert 'Authorization' not in req.headers
            assert req.headers['ous-token-v2'] == 'upload-token'
            assert b'reference-png' in req.content
            return envelope({'taskId': 'upload-1'})
        if req.url.path == '/ous/api/v2/upload/status':
            return envelope({'status': 5, 'url': 'https://cdn.example.com/input.png'})
        assert req.url.path == '/lux3d/v1/generate/img-to-3d/task/create'
        assert json.loads(req.content) == {'img': 'https://cdn.example.com/input.png', 'version': 'G1', 'outputFormat': ['glb'], 'enablePbr': False, 'aiPredictSize': False}
        return envelope(1256173)
    real(handler)
    assert aholo.submit(b'reference-png', None, 'stable-id', {}) == '1256173'
    assert len(paths) == 4


def test_poll_unwraps_success_and_prefers_glb(real):
    def handler(req):
        assert req.url.path == '/lux3d/v1/generate/task/get'
        assert req.url.params['taskid'] == '123'
        return envelope({'taskId': 123, 'status': 3, 'outputs': [{'content': 'https://cdn.example.com/out.zip'}, {'content': 'https://cdn.example.com/out.glb'}, {'content': 'NOT_REQUESTED'}]})
    real(handler)
    result = aholo.poll('123', 1)
    assert result['status'] == 'succeeded'
    assert result['resultUrl'] == 'https://cdn.example.com/out.glb'
    assert result['costFen'] == settings.cost_lux3d_fen


@pytest.mark.parametrize('status', [4, 6])
def test_terminal_failure_never_downloads_mock(real, status):
    real(lambda req: envelope({'taskId': 123, 'status': status}))
    result = aholo.poll('123', 1)
    assert result['status'] == 'failed'
    with pytest.raises(aholo.Lux3DError):
        aholo.download(result, {})


def test_rejected_create_is_not_retried_or_mocked(real):
    calls = []
    def handler(req):
        calls.append(req)
        return envelope(None, 'INSUFFICIENT_CREDITS')
    real(handler)
    with pytest.raises(Exception, match='INSUFFICIENT_CREDITS'):
        image.generate('a bear', {})
    assert len(calls) == 1


def test_ambiguous_create_timeout_is_not_retried(real):
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout('timeout', request=req)
    real(handler)
    with pytest.raises(Exception, match='uncertain|未知|不确定'):
        image.generate('a bear', {})
    assert len(calls) == 1


def test_image_async_result_is_normalized_to_png(real):
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buf, 'JPEG')
    def handler(req):
        if req.url.path.endswith('/create'):
            assert req.headers['Authorization'] == 'image-key'
            assert json.loads(req.content) == {'prompt': 'a bear'}
            return envelope(123)
        if req.url.path.endswith('/get'):
            return envelope({'taskId': 123, 'status': 3, 'outputs': [{'content': 'https://cdn.example.com/image.jpg'}]})
        assert 'Authorization' not in req.headers
        return httpx.Response(200, content=buf.getvalue())
    real(handler)
    result = image.generate('a bear', {})
    assert result.png.startswith(b'\x89PNG')
    assert result.provider == 'aholo'


def glb():
    data = b'{"asset":{"version":"2.0"}}  '
    return b'glTF' + struct.pack('<II', 2, 20 + len(data)) + struct.pack('<II', len(data), 0x4E4F534A) + data


@pytest.mark.parametrize('name', ['model.glb', 'folder/model.glb'])
def test_download_extracts_glb_zip_in_memory(real, name):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr(name, glb())
    real(lambda req: httpx.Response(200, content=buf.getvalue()))
    assert aholo.download({'status': 'succeeded', 'resultUrl': 'https://cdn.example.com/out.zip'}, {}) == glb()


def test_download_rejects_unsafe_or_missing_real_result(real):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('../model.glb', glb())
    real(lambda req: httpx.Response(200, content=buf.getvalue()))
    with pytest.raises(aholo.Lux3DError):
        aholo.download({'status': 'succeeded', 'resultUrl': 'https://cdn.example.com/out.zip'}, {})
    with pytest.raises(aholo.Lux3DError):
        aholo.download({'status': 'succeeded', 'resultUrl': None}, {})

def test_large_reference_uses_multipart_blocks(real):
    parts = []
    def handler(req):
        if req.url.path == '/asset/v1/token':
            return httpx.Response(200, json={'ousToken': 'upload-token', 'globalDomain': 'https://ous.example.com', 'blockSize': 3})
        assert 'Authorization' not in req.headers
        if req.url.path.endswith('/init'):
            assert req.url.params['blocks'] == '3'
            assert req.url.params['size'] == '8'
            return envelope({'taskId': 22, 'lackBlocks': None, 'progress': None, 'deduplicated': False})
        if req.url.path.endswith('/part'):
            parts.append(req.content)
            return envelope(None)
        return envelope({'status': 5, 'url': 'https://cdn.example.com/input.png'})
    real(handler)
    from app.providers import aholo_client
    with httpx.Client() as client:
        assert aholo_client.upload_image(client, settings.aholo_api_base, 'test-key', b'abcdefgh') == 'https://cdn.example.com/input.png'
    assert len(parts) == 3
    assert b'abc' in parts[0] and b'def' in parts[1] and b'gh' in parts[2]


def test_poll_timeout_preserves_provider_task_id(real, monkeypatch):
    from app.providers import aholo_client
    real(lambda req: envelope({'taskId': 123, 'status': 1}))
    ticks = iter([0, 0, 0, 0, 2, 2])
    monkeypatch.setattr(aholo_client.time, 'monotonic', lambda: next(ticks, 2))
    monkeypatch.setattr(aholo_client.time, 'sleep', lambda seconds: None)
    with pytest.raises(aholo_client.AholoTaskTimeout) as error:
        aholo.poll('123', 1)
    assert error.value.task_id == '123'


def test_download_rejects_oversized_assets_before_reading(real):
    real(lambda req: httpx.Response(200, headers={'content-length': str(201*1024*1024)}, content=b''))
    with pytest.raises(aholo.Lux3DError, match='size limit'):
        aholo.download({'status': 'succeeded', 'resultUrl': 'https://cdn.example.com/a.glb'}, {})


@pytest.mark.parametrize('body', [{'c': '0', 'd': {'status': 9}}, {'c': '0', 'd': []}, {'c': '-1', 'd': None}])
def test_poll_rejects_malformed_or_error_envelope(real, body):
    real(lambda req: httpx.Response(200, json=body))
    with pytest.raises(aholo.Lux3DError):
        aholo.poll('123', 1)

@pytest.mark.parametrize('response', [httpx.Response(503), httpx.Response(200, text='<html>upstream failed</html>'), httpx.Response(200, json={'unexpected': 'shape'})])
def test_ambiguous_create_response_is_not_a_definite_rejection(real, response):
    from app.providers import aholo_client
    real(lambda req: response)
    with httpx.Client() as client:
        with pytest.raises(aholo_client.AholoCreateUncertain):
            aholo_client.create(client, settings.aholo_api_base, 'test-key', 'multimodal-to-image', {'prompt': 'bear'})


def test_color_3d_keeps_pbr_materials(real):
    real(lambda req: envelope(123))
    from app.providers import aholo_client
    from unittest.mock import patch
    with patch.object(aholo_client, 'upload_image', return_value='https://cdn.example.com/input.png'):
        def handler(req):
            assert json.loads(req.content)['enablePbr'] is True
            return envelope(123)
        real(handler)
        assert aholo.submit(b'reference-png', None, 'id', {'colorMode': 'color'}) == '123'

def test_upload_timeout_is_definitely_before_generation(real):
    from app.providers import aholo_client
    calls = []
    def handler(req):
        calls.append(req.url.path)
        raise httpx.ReadTimeout('offline', request=req)
    real(handler)
    with pytest.raises(aholo_client.AholoError) as error:
        aholo.submit(b'reference-png', None, 'id', {})
    assert not isinstance(error.value, aholo_client.AholoCreateUncertain)
    assert calls == ['/asset/v1/token']
