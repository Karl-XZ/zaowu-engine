import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services import jobs


@pytest.fixture
def client_and_headers(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "test-only")
    monkeypatch.setattr(jobs, "enqueue", lambda _: None)
    with TestClient(app) as client:
        def register():
            r = client.post('/api/v1/auth/register', json={
                'email': uuid.uuid4().hex + '@cad-test.local', 'password': 'local-test-123', 'privacyConsent': True})
            assert r.status_code == 200
            return {'Authorization': 'Bearer ' + r.json()['token']}
        yield client, register(), register()


def plan_result(ready=True):
    return {'ready': ready, 'summary': '手机放在桌上，底部留出充电线位置',
            'questions': [] if ready else ['你想把手机竖放还是横放？'],
            'assumptions': ['按普通大屏手机估计大小'], 'requirements': ['手机支撑', '充电线通道'],
            'dimensionsMm': [90, 70, 100], 'expectedBodies': 1, 'designBrief': 'An angled phone stand with cable opening'}


def test_plain_language_plan_confirm_and_idempotency(client_and_headers, monkeypatch):
    from app.providers import cad_ai
    monkeypatch.setattr(cad_ai, 'interpret', lambda text, context=None: plan_result())
    client, headers, _ = client_and_headers
    body = {'text': '做个放手机的架子，放桌上能边看视频边充电，不要容易倒'}
    r = client.post('/api/v1/cad/ai/plan', headers=headers, json=body)
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan['ready'] and plan['planId']
    assert client.get('/api/v1/quota', headers=headers).json()['freeReserved'] == 0
    request = {'planId': plan['planId'], 'confirmAssumptions': True, 'idempotencyKey': uuid.uuid4().hex}
    first = client.post('/api/v1/cad/ai/generate', headers=headers, json=request)
    second = client.post('/api/v1/cad/ai/generate', headers=headers, json=request)
    assert first.status_code == second.status_code == 200
    assert first.json()['taskId'] == second.json()['taskId']
    assert client.get('/api/v1/quota', headers=headers).json()['freeReserved'] == 1


def test_clarification_and_ownership(client_and_headers, monkeypatch):
    from app.providers import cad_ai
    monkeypatch.setattr(cad_ai, 'interpret', lambda text, context=None: plan_result(False))
    client, headers, other = client_and_headers
    plan = client.post('/api/v1/cad/ai/plan', headers=headers, json={'text': '做个架子'}).json()
    r = client.post('/api/v1/cad/ai/generate', headers=headers,
                    json={'planId': plan['planId'], 'confirmAssumptions': True})
    assert r.status_code == 409
    r = client.post('/api/v1/cad/ai/plan', headers=other,
                    json={'text': '竖着放手机', 'previousPlanId': plan['planId']})
    assert r.status_code == 404
    r = client.post('/api/v1/cad/ai/generate', headers=headers, json={'planId': plan['planId']})
    assert r.status_code == 422


def test_ai_script_kernel_delivery_and_local_repair(client_and_headers, monkeypatch):
    from app.providers import cad_ai
    monkeypatch.setattr(cad_ai, 'interpret', lambda text, context=None: plan_result())
    scripts = []
    def generate(plan, error=None, previous_script=None):
        scripts.append(error)
        if not error:
            return "import os\nresult = os.environ"
        return ('import cadquery as cq\n'
                'base = cq.Workplane("XY").box(90, 70, 5, centered=(True, True, False))\n'
                'back = cq.Workplane("XY").box(90, 5, 100, centered=(True, True, False)).translate((0, 30, 0))\n'
                'result = base.union(back)\n')
    monkeypatch.setattr(cad_ai, 'generate_script', generate)
    monkeypatch.setattr(cad_ai, 'review_script', lambda *args: {'meetsRequirements': True, 'missingFeatures': [], 'notes': []}, raising=False)
    client, headers, _ = client_and_headers
    plan = client.post('/api/v1/cad/ai/plan', headers=headers, json={'text': '放手机的桌面架子'}).json()
    task = client.post('/api/v1/cad/ai/generate', headers=headers,
                       json={'planId': plan['planId'], 'confirmAssumptions': True}).json()
    jobs._run_safe(task['taskId'])
    state = client.get('/api/v1/generations/' + task['taskId'], headers=headers).json()
    assert state['state'] == 'VERIFIED_DELIVERABLE', state
    assert len(scripts) == 2 and scripts[1]
    model = client.get('/api/v1/models/' + state['modelVersionId'], headers=headers).json()
    assert model['report']['cad']['valid'] is True
    assert 'step' in model['files']
    step = client.get(model['files']['step'])
    assert step.status_code == 200 and b'ISO-10303-21' in step.content
    quota = client.get('/api/v1/quota', headers=headers).json()
    assert quota['freeUsed'] == 1 and quota['freeReserved'] == 0


def test_missing_required_features_never_delivers_box(client_and_headers, monkeypatch):
    from app.providers import cad_ai
    monkeypatch.setattr(cad_ai, 'interpret', lambda *args, **kwargs: plan_result())
    monkeypatch.setattr(cad_ai, 'generate_script', lambda *args, **kwargs:
        'import cadquery as cq\nresult = cq.Workplane("XY").box(90,70,100)')
    monkeypatch.setattr(cad_ai, 'review_script', lambda *args: {
        'meetsRequirements': False, 'missingFeatures': ['没有手机放置空间和充电开口'], 'notes': []}, raising=False)
    client, headers, _ = client_and_headers
    plan = client.post('/api/v1/cad/ai/plan', headers=headers, json={'text': '手机支架，底下留充电线位置'}).json()
    task = client.post('/api/v1/cad/ai/generate', headers=headers,
                       json={'planId': plan['planId'], 'confirmAssumptions': True}).json()
    jobs._run_safe(task['taskId'])
    state = client.get('/api/v1/generations/' + task['taskId'], headers=headers).json()
    assert state['state'] == 'FAILED_REFUND' and not state['modelVersionId']
    quota = client.get('/api/v1/quota', headers=headers).json()
    assert quota['freeUsed'] == quota['freeReserved'] == 0
