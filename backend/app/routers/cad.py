"""精确 CAD（PRD §3.2）。模板命中 → 本地建模，外部 API 0 次；同一作品纯参数重建不计次。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import DesignSpec, GenerationTask, ModelVersion, User, now
from ..security import current_user
from ..services import cad_templates, jobs, preflight, quota
from ..services.materials import get_material

router = APIRouter(prefix="/api/v1/cad", tags=["cad"])


class ParseIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    materialId: str = "mono_resin"


class GenIn(BaseModel):
    template: str
    params: dict
    materialId: str = "mono_resin"
    label: str = Field(default="", max_length=32)
    parentModelId: str | None = None
    idempotencyKey: str | None = Field(default=None, max_length=64)


@router.get("/templates")
def templates():
    return cad_templates.TEMPLATES


@router.post("/parse")
def parse(body: ParseIn, user: User = Depends(current_user)):
    mat = get_material(body.materialId)
    pf = preflight.check_text(body.text, mat, engine="cad")
    kind, params, missing = cad_templates.parse_text(body.text)
    return {"template": kind, "templateName": cad_templates.TEMPLATES[kind]["name"],
            "templateVersion": cad_templates.TEMPLATES[kind]["version"], "params": params, "missing": missing,
            "errors": cad_templates.validate(kind, params, mat), "preflight": pf.to_dict()}


@router.post("/validate")
def validate(body: GenIn, user: User = Depends(current_user)):
    mat = get_material(body.materialId)
    return {"errors": cad_templates.validate(body.template, body.params, mat)}


@router.post("/generate")
def generate(body: GenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quota.lock_write(db, user.id)
    if body.template not in cad_templates.TEMPLATES:
        raise HTTPException(400, "未知模板")
    try:
        mat = get_material(body.materialId)
    except ValueError as e:
        raise HTTPException(400, str(e))
    params = {k: float(body.params.get(k, v)) for k, v in cad_templates.TEMPLATES[body.template]["params"].items()}
    errs = cad_templates.validate(body.template, params, mat)
    if errs:
        raise HTTPException(422, {"errors": errs})
    if body.idempotencyKey:
        from sqlalchemy import select
        t = db.scalar(select(GenerationTask).where(GenerationTask.idempotency_key == body.idempotencyKey))
        if t:
            if t.user_id != user.id or t.engine != "cad":
                raise HTTPException(409, "幂等键已被使用")
            return {"taskId": t.id, "free": t.entitlement_id is None}
    rebuild = False
    if body.parentModelId:
        parent = db.get(ModelVersion, body.parentModelId)
        if parent and parent.user_id == user.id and parent.engine == "cad":
            pspec = db.get(DesignSpec, db.get(GenerationTask, parent.task_id).design_spec_id)
            rebuild = pspec.spec.get("template") == body.template and pspec.material_id == mat["id"]
    lg = quota.ledger(db, user.id)
    if rebuild and lg.cad_rebuilds >= settings.daily_cad_rebuild_limit:
        raise HTTPException(429, f"今日免费参数重建已达 {settings.daily_cad_rebuild_limit} 次，明天恢复。")
    spec = DesignSpec(user_id=user.id, engine="cad", category=body.template, material_id=mat["id"],
                      material_profile_version=mat["profile_version"],
                      size_mm=max(v for k, v in params.items() if k in ("length", "diameter", "height")),
                      spec={"template": body.template, "params": params, "label": body.label},
                      hard_checklist=[{"key": k, "label": k, "value": f"{v:g} mm"} for k, v in params.items()],
                      template_version=cad_templates.TEMPLATES[body.template]["version"])
    db.add(spec)
    db.flush()
    task = GenerationTask(user_id=user.id, engine="cad", design_spec_id=spec.id, idempotency_key=body.idempotencyKey,
                          params={"rebuildOf": body.parentModelId} if rebuild else {},
                          stage_log=[{"state": "CREATED", "at": now().isoformat(), "note": "参数已确认"}])
    db.add(task)
    db.flush()
    if rebuild:
        lg.cad_rebuilds += 1
    else:
        task.entitlement_id = quota.reserve(db, user, "task", task.id).id
    db.commit()
    jobs.enqueue(task.id)
    return {"taskId": task.id, "free": rebuild}
