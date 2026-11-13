"""Everyday language CAD plans and user-confirmed construction tasks."""
from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import DesignSpec, GenerationTask, ProviderCostLedger, User, now
from ..security import current_user
from ..services import cost_governor, jobs, preflight, quota
from ..services.materials import get_material

router = APIRouter(prefix="/api/v1/cad/ai", tags=["natural-language-cad"])


class PlanIn(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    previousPlanId: str | None = Field(default=None, max_length=32)
    materialId: str = "mono_resin"


class GenerateIn(BaseModel):
    planId: str = Field(min_length=1, max_length=32)
    confirmAssumptions: bool = False
    idempotencyKey: str | None = Field(default=None, max_length=64)


def _owned_plan(db, plan_id, user):
    plan = db.get(DesignSpec, plan_id)
    if not plan or plan.user_id != user.id or plan.spec.get("mode") != "ai":
        raise HTTPException(404, "设计方案不存在")
    return plan


@router.post("/plan")
def plan(body: PlanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..providers import cad_ai
    if not settings.deepseek_api_key:
        raise HTTPException(503, "自然语言建模服务尚未配置")
    quota.lock_write(db, user.id)
    material = get_material(body.materialId)
    # The brief may contain multiple sentences; manufacturing constraints are
    # checked by the independent kernel/mesh pipeline rather than keyword jargon.
    pf = preflight.check_text(body.text[:400], material, engine="cad")
    blocks = [i for i in pf.issues if i.level == "block" and i.code in ("forbidden", "ip_risk")]
    if blocks:
        raise HTTPException(422, blocks[0].message)
    previous = _owned_plan(db, body.previousPlanId, user) if body.previousPlanId else None
    if previous and previous.material_id != material["id"]:
        raise HTTPException(409, "修改方案时请保持材料一致，或开启新方案")
    start = datetime.now(quota.TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(select(func.count()).select_from(ProviderCostLedger).where(
        ProviderCostLedger.user_id == user.id, ProviderCostLedger.endpoint == "cad-plan",
        ProviderCostLedger.created_at >= start)) or 0
    if count >= settings.daily_cad_ai_plan_limit:
        raise HTTPException(429, f"今日方案理解已达 {settings.daily_cad_ai_plan_limit} 次，明天恢复")
    quota.ensure_paid_engine_allowed(db, user, free_tier=True)
    call = cost_governor.open_call(db, user_id=user.id, ref_type="cad-plan", ref_id=uuid.uuid4().hex,
        provider="deepseek", endpoint="cad-plan", estimate_fen=settings.cost_cad_ai_fen, free_tier=True)
    try:
        context = {**(previous.spec if previous else {}), "materialId": material["id"],
                   "materialRules": {k: material[k] for k in ("min_wall_mm", "min_hole_mm", "min_feature_mm", "max_size_mm")}}
        parsed = cad_ai.interpret(body.text, context=context)
    except Exception:
        cost_governor.close_call(call, "failed")
        db.commit()
        raise HTTPException(502, "暂时没有理解成功，请稍后再试；尚未扣除模型生成次数") from None
    cost_governor.close_call(call, "success")
    data = {**parsed, "mode": "ai", "sourceText": body.text,
            "previousPlanId": body.previousPlanId,
            "materialRules": {k: material[k] for k in ("min_wall_mm", "min_hole_mm", "min_feature_mm", "max_size_mm")}}
    dims = data.get("dimensionsMm") or [60, 60, 60]
    spec = DesignSpec(user_id=user.id, engine="cad", category="ai", material_id=material["id"],
        material_profile_version=material["profile_version"], size_mm=max(dims), spec=data,
        hard_checklist=[{"key": f"requirement_{i}", "label": "设计要求", "value": text}
                        for i, text in enumerate(data.get("requirements", []))], template_version="cad_ai_v1")
    db.add(spec)
    db.commit()
    return {"planId": spec.id, **data}


@router.post("/generate")
def generate(body: GenerateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not body.confirmAssumptions:
        raise HTTPException(422, "请先确认设计方案和建议尺寸")
    if not settings.deepseek_api_key:
        raise HTTPException(503, "自然语言建模服务尚未配置")
    quota.lock_write(db, user.id)
    spec = _owned_plan(db, body.planId, user)
    if not spec.spec.get("ready"):
        raise HTTPException(409, "请先回答方案中的问题，再开始建模")
    if body.idempotencyKey:
        task = db.scalar(select(GenerationTask).where(GenerationTask.idempotency_key == body.idempotencyKey))
        if task:
            if task.user_id != user.id or task.design_spec_id != spec.id:
                raise HTTPException(409, "提交编号已被使用")
            return {"taskId": task.id}
    existing = db.scalar(select(GenerationTask).where(GenerationTask.design_spec_id == spec.id,
        GenerationTask.state != "FAILED_REFUND"))
    if existing:
        return {"taskId": existing.id}
    material = get_material(spec.material_id)
    if max(spec.spec["dimensionsMm"]) > material["max_size_mm"]:
        raise HTTPException(422, "方案尺寸超过当前材料支持范围，请用日常语言提出缩小尺寸或调整设计")
    lg = quota.ledger(db, user.id)
    quota.ensure_paid_engine_allowed(db, user, free_tier=lg.free_used + lg.free_reserved < settings.daily_free_quota)
    task = GenerationTask(user_id=user.id, engine="cad", design_spec_id=spec.id,
        idempotency_key=body.idempotencyKey, provider="deepseek-cadquery",
        params={"cadMode": "ai", "budgetFen": settings.cad_ai_job_budget_fen},
        stage_log=[{"state": "CREATED", "at": now().isoformat(), "note": "已确认口语设计方案"}])
    db.add(task)
    db.flush()
    task.entitlement_id = quota.reserve(db, user, "task", task.id).id
    db.commit()
    jobs.enqueue(task.id)
    return {"taskId": task.id}
