import json

import httpx
import pytest

from app.config import settings
from app.providers import cad_ai


PLAN = {
    "ready": True, "summary": "带排水孔的肥皂托盘", "questions": [],
    "assumptions": ["按普通香皂大小制作，长12厘米、宽8厘米"],
    "requirements": ["底部排水孔", "四周挡边"], "dimensionsMm": [120, 80, 20],
    "expectedBodies": 1,
    "designBrief": "120×80×20毫米肥皂托盘，底板厚3毫米，四周挡边厚3毫米，底部五个直径5毫米排水孔。",
}
SCRIPT = 'import cadquery as cq\nresult = cq.Workplane("XY").box(120, 80, 20)'


def transport(monkeypatch, payload, *, status=200, finish="stop", raw_content=None):
    monkeypatch.setattr(settings, "deepseek_api_key", "private-test-key")
    requests = []
    original = httpx.Client

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(status, json={"choices": [{"finish_reason": finish,
            "message": {"content": json.dumps(payload, ensure_ascii=False) if raw_content is None else raw_content}}]})

    monkeypatch.setattr(cad_ai.httpx, "Client", lambda **kwargs: original(
        transport=httpx.MockTransport(respond), timeout=kwargs.get("timeout")))
    return requests


def test_interpret_retains_new_object_and_followup_context(monkeypatch):
    requests = transport(monkeypatch, PLAN)
    result = cad_ai.interpret("改成12厘米，底部加排水孔", {"previousPlan": {"summary": "肥皂托盘"}})
    assert result == PLAN
    submitted = json.loads(requests[0]["messages"][1]["content"])
    assert submitted["text"] == "改成12厘米，底部加排水孔"
    assert submitted["context"]["previousPlan"]["summary"] == "肥皂托盘"
    assert requests[0]["response_format"] == {"type": "json_object"}


def test_ambiguous_input_returns_everyday_question(monkeypatch):
    payload = {**PLAN, "ready": False, "summary": "需要了解要做的东西", "questions": ["这个东西是用来做什么的？"]}
    transport(monkeypatch, payload)
    result = cad_ai.interpret("做那个东西")
    assert not result["ready"]
    assert result["questions"] == ["这个东西是用来做什么的？"]


@pytest.mark.parametrize("changes", [
    {"dimensionsMm": [100, 0, 20]}, {"dimensionsMm": [1, 2]},
    {"dimensionsMm": [100, 80, float("nan")]}, {"expectedBodies": 5},
    {"expectedBodies": True}, {"ready": "yes"}, {"requirements": "drain holes"},
    {"designBrief": ""}, {"questions": ["多大？"]},
    {"ready": False, "questions": []},
])
def test_malformed_plan_is_not_treated_as_ready(monkeypatch, changes):
    transport(monkeypatch, {**PLAN, **changes})
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.interpret("做个肥皂托盘")


def test_generate_returns_real_script_and_carries_repair_feedback(monkeypatch):
    requests = transport(monkeypatch, {"script": SCRIPT})
    assert cad_ai.generate_script(PLAN, "shape invalid", "broken script") == SCRIPT
    submitted = json.loads(requests[0]["messages"][1]["content"])
    assert submitted["plan"] == PLAN
    assert submitted["error"] == "shape invalid"
    assert submitted["previous_script"] == "broken script"


def test_generate_retains_server_material_rules(monkeypatch):
    requests = transport(monkeypatch, {"script": SCRIPT})
    rules = {"min_wall_mm": 2.0, "min_hole_mm": 3.0, "min_feature_mm": 2.0, "max_size_mm": 300}
    cad_ai.generate_script({**PLAN, "materialRules": rules, "apiKey": "do-not-copy-extra-fields"})
    submitted = json.loads(requests[0]["messages"][1]["content"])
    assert submitted["plan"]["materialRules"] == rules
    assert "apiKey" not in submitted["plan"]


def test_invalid_material_rules_stop_before_paid_request(monkeypatch):
    requests = transport(monkeypatch, {"script": SCRIPT})
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.generate_script({**PLAN, "materialRules": {"min_wall_mm": -2}})
    assert requests == []


def test_script_generation_uses_dedicated_model(monkeypatch):
    requests = transport(monkeypatch, {"script": SCRIPT})
    monkeypatch.setattr(settings, "deepseek_model", "planning-fast")
    monkeypatch.setattr(settings, "deepseek_cad_model", "cad-accurate")
    cad_ai.generate_script(PLAN)
    assert requests[0]["model"] == "cad-accurate"
    assert requests[0]["max_tokens"] == 12000
    assert requests[0]["thinking"] == {"type": "enabled"}
    assert requests[0]["reasoning_effort"] == "low"


def test_planning_keeps_fast_model(monkeypatch):
    requests = transport(monkeypatch, PLAN)
    monkeypatch.setattr(settings, "deepseek_model", "planning-fast")
    monkeypatch.setattr(settings, "deepseek_cad_model", "cad-accurate")
    cad_ai.interpret("托盘")
    assert requests[0]["model"] == "planning-fast"


def test_review_reports_missing_geometry_from_independent_inputs(monkeypatch):
    requests = transport(monkeypatch, {"meetsRequirements": False,
        "missingFeatures": ["缺少底部排水孔"], "notes": ["包围盒符合尺寸，但脚本只建立实心方块"]})
    metrics = {"boundsMm": [120, 80, 20], "volumeMm3": 192000}
    result = cad_ai.review_script(PLAN, SCRIPT, metrics)
    assert result["missingFeatures"] == ["缺少底部排水孔"]
    assert result["meetsRequirements"] is False
    submitted = json.loads(requests[0]["messages"][1]["content"])
    assert submitted["script"] == SCRIPT
    assert submitted["metrics"] == metrics
    assert submitted["plan"]["requirements"] == ["底部排水孔", "四周挡边"]
    assert requests[0]["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("payload", [
    {"meetsRequirements": "yes", "missingFeatures": [], "notes": []},
    {"meetsRequirements": True, "missingFeatures": ["排水孔"], "notes": []},
    {"meetsRequirements": False, "missingFeatures": [], "notes": []},
    {"meetsRequirements": True, "missingFeatures": [], "notes": "solid valid"},
    {"valid": True},
])
def test_invalid_review_is_never_treated_as_acceptance(monkeypatch, payload):
    transport(monkeypatch, payload)
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.review_script(PLAN, SCRIPT, {"volumeMm3": 192000})


def test_review_acceptance_is_explicit(monkeypatch):
    transport(monkeypatch, {"meetsRequirements": True, "missingFeatures": [], "notes": ["此为AI审查，几何有效性以内核为准"]})
    result = cad_ai.review_script(PLAN, SCRIPT, {"volumeMm3": 192000})
    assert result["meetsRequirements"] is True


def test_review_request_defines_operation_order_and_required_feature_scope(monkeypatch):
    # This verifies the checker request contract, not the correctness of AI geometry analysis.
    requests = transport(monkeypatch, {"meetsRequirements": True, "missingFeatures": [], "notes": []})
    source = "两个连在一起的笔筒，一高一矮，底部各有一个排水孔"
    cad_ai.review_script({**PLAN, "sourceText": source}, SCRIPT, {"volumeMm3": 1000})
    system = requests[0]["messages"][0]["content"]
    submitted = json.loads(requests[0]["messages"][1]["content"])
    assert submitted["plan"]["sourceText"] == source
    assert "按语句顺序" in system
    assert "最终result" in system
    assert "装饰" in system
    assert "requirements" in system


def test_checker_contract_supplies_authoritative_plane_and_overlap_facts(monkeypatch):
    # Contract assertions ensure facts reach the model; they do not certify its judgment.
    requests = transport(monkeypatch, {"meetsRequirements": True, "missingFeatures": [], "notes": []})
    cad_ai.review_script(PLAN, SCRIPT, {"volumeMm3": 1000})
    system = requests[0]["messages"][0]["content"]
    assert "YZ: local (u,v) = global (Y,Z); extrusion normal = +X." in system
    assert "XZ: local (u,v) = global (X,Z); extrusion normal = -Y." in system
    assert "centered=False" in system
    assert "[tx,tx+width]" in system
    assert "18-6=12" in system
    assert "实际区间交集" in system


@pytest.mark.parametrize("payload", [{"script": ""}, {"script": 123}, {"metrics": {"valid": True}}])
def test_generate_rejects_metadata_in_place_of_script(monkeypatch, payload):
    transport(monkeypatch, payload)
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.generate_script(PLAN)


def test_generate_rejects_unconfirmed_ambiguous_plan(monkeypatch):
    requests = transport(monkeypatch, {"script": SCRIPT})
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.generate_script({**PLAN, "ready": False, "questions": ["用来做什么？"]})
    assert requests == []


@pytest.mark.parametrize("status,finish", [(401, "stop"), (429, "stop"), (200, "length")])
def test_provider_failures_never_fallback_or_expose_secret(monkeypatch, status, finish):
    transport(monkeypatch, {"error": "private-test-key"}, status=status, finish=finish)
    with pytest.raises(cad_ai.CadAIError) as error:
        cad_ai.interpret("手机支架")
    assert "private-test-key" not in str(error.value)


def test_missing_credentials_never_returns_mock(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.interpret("手机支架")


@pytest.mark.parametrize("content", ["", "  "])
def test_blank_json_mode_content_has_safe_specific_error(monkeypatch, content):
    transport(monkeypatch, {}, raw_content=content)
    with pytest.raises(cad_ai.CadAIError, match="空内容"):
        cad_ai.generate_script(PLAN)


@pytest.mark.parametrize("text", ["", "  ", "x" * 8001])
def test_invalid_user_text_stops_before_paid_request(monkeypatch, text):
    requests = transport(monkeypatch, PLAN)
    with pytest.raises(cad_ai.CadAIError):
        cad_ai.interpret(text)
    assert requests == []
