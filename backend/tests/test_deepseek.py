import json

import httpx
import pytest

from app.config import settings
from app.providers import deepseek


def test_refine_preserves_manufacturing_rules(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "test-private-key")
    def respond(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert "json" in body["messages"][0]["content"].lower()
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "subject": "A chubby cat", "style": "soft clay", "color": "pink",
            "shapeNotes": ["short sturdy ears"], "hardConstraints": [], "sizeHeightMm": 999,
        })}}]})
    original = httpx.Client
    monkeypatch.setattr(deepseek.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(respond)))
    spec = {"subject": "猫", "sizeHeightMm": 60, "hardConstraints": ["min wall 2 mm"], "connectedBase": True}
    result = deepseek.refine(spec)
    assert result["subject"] == "A chubby cat"
    assert result["sizeHeightMm"] == 60
    assert result["hardConstraints"] == ["min wall 2 mm"]
    assert result["connectedBase"] is True


def test_refine_bad_response_never_exposes_key(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "test-private-key")
    original = httpx.Client
    monkeypatch.setattr(deepseek.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(
        lambda _: httpx.Response(401, json={"error": "test-private-key"}))))
    with pytest.raises(deepseek.SemanticError) as error:
        deepseek.refine({"subject": "cat"})
    assert "test-private-key" not in str(error.value)


def test_refine_disabled_is_local(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    spec = {"subject": "cat"}
    assert deepseek.refine(spec) == spec
