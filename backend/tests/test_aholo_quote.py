from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.config import settings
from app.providers import aholo_client, image


@pytest.fixture
def quoted(monkeypatch):
    monkeypatch.setattr(settings, 'aholo_quote_enabled', True, raising=False)
    monkeypatch.setattr(settings, 'aholo_max_call_credits', 64, raising=False)
    original = httpx.Client
    def transport(handler):
        monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return transport


def rpc(data, sse=False):
    result = {'jsonrpc': '2.0', 'id': 1, 'result': {'structuredContent': {'c': '0', 'm': 'success', 'd': data}, 'isError': False}}
    if sse:
        return httpx.Response(200, text='event: message\ndata: '+json.dumps(result)+'\n\n', headers={'content-type': 'text/event-stream'})
    return httpx.Response(200, json=result)


def handler_for(quote_credits=12, balance=100, expired=False, sse=False):
    seen = []
    def handler(req):
        seen.append(req.url.path)
        if req.url.path == '/lux3d-mcp/mcp':
            args = json.loads(req.content)['params']
            assert req.headers['Authorization'] == 'test-key'
            if args['name'] == 'getlux3daccountbalance':
                assert args['arguments'] == {'source': 100, 'agentName': 'ZaowuEngine'}
                return rpc({'availableCredits': balance, 'trialCountMap': {'meshgen': 5}, 'uniqueId': 'ctx_test'}, sse)
            assert args['name'] == 'post_quotelux3dopenapirequests'
            body = args['arguments']['body']
            assert body['source'] == 100 and body['agentName'] == 'ZaowuEngine' and body['uniqueId'] == 'ctx_test'
            item = body['items']['1']
            assert item['endpoint'] == {'method': 'POST', 'path': '/lux3d/v1/generate/multimodal-to-image/task/create'}
            assert json.loads(item['parameters']['body']) == {'prompt': 'bear'}
            assert item['parameters']['pathParameters'] == '{}' and item['parameters']['queryParameters'] == '{}'
            expires = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 5)
            return rpc({'uniqueId': 'ctx_test', 'quoteId': 'quote_test', 'source': 100, 'estimatedCreditsTotal': quote_credits, 'details': {'1': quote_credits}, 'expiresAt': expires.isoformat()}, sse)
        assert req.url.path.endswith('/multimodal-to-image/task/create')
        return httpx.Response(200, json={'c': '0', 'd': 123})
    return seen, handler


@pytest.mark.parametrize('sse', [False, True])
def test_create_quotes_exact_payload_before_paid_submission(quoted, sse):
    seen, handler = handler_for(sse=sse)
    quoted(handler)
    with httpx.Client() as client:
        assert aholo_client.create(client, 'https://api.aholo3d.cn', 'test-key', 'multimodal-to-image', {'prompt': 'bear'}) == '123'
    assert seen == ['/lux3d-mcp/mcp', '/lux3d-mcp/mcp', '/lux3d/v1/generate/multimodal-to-image/task/create']


@pytest.mark.parametrize('kwargs', [{'quote_credits': 65}, {'balance': 11}, {'expired': True}, {'quote_credits': None}])
def test_quote_rejection_never_creates_generation(quoted, kwargs):
    seen, handler = handler_for(**kwargs)
    quoted(handler)
    with httpx.Client() as client:
        with pytest.raises(aholo_client.AholoError):
            aholo_client.create(client, 'https://api.aholo3d.cn', 'test-key', 'multimodal-to-image', {'prompt': 'bear'})
    assert all(not path.endswith('/create') for path in seen)


def test_quote_transport_failure_is_definite_precreate_rejection(quoted):
    def handler(req):
        raise httpx.ReadTimeout('offline', request=req)
    quoted(handler)
    from app.providers.aholo_quote import AholoQuoteRejected
    with httpx.Client() as client:
        with pytest.raises(AholoQuoteRejected):
            aholo_client.create(client, 'https://api.aholo3d.cn', 'test-key', 'multimodal-to-image', {'prompt': 'bear'})


def test_image_callback_persists_task_before_polling(quoted, monkeypatch):
    monkeypatch.setattr(settings, 'image_provider', 'aholo')
    monkeypatch.setattr(settings, 'image_api_base', 'https://api.aholo3d.cn')
    monkeypatch.setattr(settings, 'image_api_key', 'test-key')
    seen, handler = handler_for()
    persisted = []
    def fail_after_create(req):
        if req.url.path.endswith('/get'):
            assert persisted == ['123']
            return httpx.Response(200, json={'c': '0', 'd': {'status': 4}})
        return handler(req)
    quoted(fail_after_create)
    with pytest.raises(aholo_client.AholoError):
        image.generate('bear', {}, on_task_created=persisted.append)
    assert persisted == ['123']
