"""任务状态、作品、下载、申诉（PRD §4、§5.6）。"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (ConceptImage, DesignSession, DesignSpec, Entitlement, GenerationTask, ManufacturingCheck,
                      ModelVersion, RequirementClaim, SliceReport, User, now)
from ..security import current_user, sign_url
from ..services import jobs, quota
from ..services.materials import MATERIALS

router = APIRouter(prefix="/api/v1", tags=["models"])

STAGES_CREATIVE = [("CONCEPT", "效果图确认"), ("RUNNING", "图生 3D"), ("PROCESSING_ASSET", "处理文件"),
                   ("MANUFACTURING_VALIDATION", "修复 · 预检"), ("SLICE_CHECK", "切片"), ("VERIFIED_DELIVERABLE", "合格交付")]
STAGES_CAD = [("RUNNING", "本地建模"), ("MANUFACTURING_VALIDATION", "内核实测"), ("SLICE_CHECK", "切片"),
              ("VERIFIED_DELIVERABLE", "合格交付")]
STAGES_AI_CAD = [("RUNNING", "AI 设计与构建模型"), ("MANUFACTURING_VALIDATION", "检查尺寸与设计要求"),
                 ("SLICE_CHECK", "打印前检查"), ("VERIFIED_DELIVERABLE", "文件交付")]


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=now().tzinfo)


@router.get("/generations/{tid}")
def get_generation(tid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(GenerationTask, tid)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    # Querying a known task is safe. Never recover an uncertain creation by
    # submitting again; throttle recovery so UI polling cannot flood the queue.
    cutoff = now() - timedelta(seconds=30)
    if t.state == "RUNNING" and t.provider_task_id and t.error and _aware(t.updated_at) < cutoff:
        changed = db.execute(update(GenerationTask).where(
            GenerationTask.id == t.id, GenerationTask.user_id == user.id,
            GenerationTask.state == "RUNNING", GenerationTask.provider_task_id.is_not(None),
            GenerationTask.error != "", GenerationTask.updated_at < cutoff
        ).values(updated_at=now()).execution_options(synchronize_session=False)).rowcount
        db.commit()
        db.refresh(t)
        if changed:
            jobs.enqueue(t.id)
    stages = STAGES_CREATIVE if t.engine == "creative" else STAGES_AI_CAD if t.params.get("cadMode") == "ai" else STAGES_CAD
    return {"id": t.id, "engine": t.engine, "state": t.state, "stageLog": t.stage_log, "error": t.error,
            "modelVersionId": t.model_version_id, "conceptVersion": t.concept_version, "sessionId": t.session_id,
            "stages": [{"key": k, "label": v} for k, v in stages], "providerTaskId": t.provider_task_id}


def model_out(db: Session, mv: ModelVersion, user: User) -> dict:
    chk = db.scalar(select(ManufacturingCheck).where(ManufacturingCheck.model_version_id == mv.id).order_by(ManufacturingCheck.id.desc()))
    sl = db.scalar(select(SliceReport).where(SliceReport.model_version_id == mv.id).order_by(SliceReport.id.desc()))
    task = db.get(GenerationTask, mv.task_id)
    spec = db.get(DesignSpec, task.design_spec_id) if task else None
    concept_url, turns = None, None
    if task and task.session_id:
        c = db.scalar(select(ConceptImage).where(ConceptImage.session_id == task.session_id, ConceptImage.version == task.concept_version))
        s = db.get(DesignSession, task.session_id)
        concept_url = sign_url(c.file_path, user.id, 120) if c else None
        turns = {"used": s.turns_used, "limit": s.turns_limit, "sessionId": s.id} if s else None
    verified = _aware(mv.verified_at)
    appeal_open = bool(verified and now() - verified < timedelta(hours=settings.appeal_window_hours)
                       and not mv.production_downloaded_at)
    claim = db.scalar(select(RequirementClaim).where(RequirementClaim.model_version_id == mv.id))
    mat = MATERIALS[mv.material_id]
    return {
        "id": mv.id, "title": mv.title, "engine": mv.engine, "dimensionMm": mv.dimension_mm,
        "material": {"id": mat["id"], "name": mat["name"]}, "materialProfileVersion": mv.material_profile_version,
        "validationState": mv.validation_state, "fileHash": mv.file_hash,
        "verifiedAt": verified.isoformat() if verified else None, "createdAt": _aware(mv.created_at).isoformat(),
        "files": {k: sign_url(v, user.id, 60) for k, v in mv.files.items()},
        "report": chk.report if chk else None, "slice": sl.report if sl else None,
        "checklist": spec.hard_checklist if spec else [], "conceptVersion": task.concept_version if task else None,
        "conceptUrl": concept_url, "turns": turns, "taskId": mv.task_id,
        "appeal": {"open": appeal_open, "windowHours": settings.appeal_window_hours,
                   "claim": {"decision": claim.decision, "autoResult": claim.auto_result} if claim else None},
        "cad": {**spec.spec, "planId": spec.id} if spec and spec.engine == "cad" else None,
    }


@router.get("/models")
def list_models(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ModelVersion).where(ModelVersion.user_id == user.id, ModelVersion.deleted.is_(False))
                      .order_by(ModelVersion.created_at.desc()).limit(100)).all()
    out = []
    for mv in rows:
        task = db.get(GenerationTask, mv.task_id)
        thumb = None
        if task and task.session_id:
            c = db.scalar(select(ConceptImage).where(ConceptImage.session_id == task.session_id, ConceptImage.version == task.concept_version))
            thumb = sign_url(c.file_path, user.id, 120) if c else None
        out.append({"id": mv.id, "title": mv.title, "engine": mv.engine, "dimensionMm": mv.dimension_mm,
                    "material": MATERIALS[mv.material_id]["name"], "createdAt": _aware(mv.created_at).isoformat(),
                    "thumb": thumb, "glb": sign_url(mv.files["glb"], user.id, 60)})
    tasks = db.scalars(select(GenerationTask).where(GenerationTask.user_id == user.id,
                                                    GenerationTask.state.notin_(("VERIFIED_DELIVERABLE",)))
                       .order_by(GenerationTask.created_at.desc()).limit(20)).all()
    return {"models": out, "tasks": [{"id": t.id, "engine": t.engine, "state": t.state, "error": t.error,
                                      "createdAt": _aware(t.created_at).isoformat()} for t in tasks]}


@router.get("/models/{mid}")
def get_model(mid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mv = db.get(ModelVersion, mid)
    if not mv or mv.user_id != user.id or mv.deleted:
        raise HTTPException(404, "作品不存在")
    return model_out(db, mv, user)


@router.post("/models/{mid}/downloaded")
def mark_downloaded(mid: str, fmt: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mv = db.get(ModelVersion, mid)
    if not mv or mv.user_id != user.id:
        raise HTTPException(404, "作品不存在")
    if fmt in ("stl", "3mf", "step") and not mv.production_downloaded_at:
        mv.production_downloaded_at = now()
        db.commit()
    return {"ok": True}


@router.delete("/models/{mid}")
def delete_model(mid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mv = db.get(ModelVersion, mid)
    if not mv or mv.user_id != user.id:
        raise HTTPException(404, "作品不存在")
    mv.deleted = True  # 账本与审计记录依法保留
    db.commit()
    return {"ok": True}


class ClaimIn(BaseModel):
    items: list[str] = Field(min_length=1)
    note: str = Field(default="", max_length=500)


@router.post("/models/{mid}/appeal")
def appeal(mid: str, body: ClaimIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mv = db.get(ModelVersion, mid)
    if not mv or mv.user_id != user.id:
        raise HTTPException(404, "作品不存在")
    data = model_out(db, mv, user)
    if not data["appeal"]["open"]:
        raise HTTPException(409, "已超过 24 小时或已下载正式生产文件，不能再申诉。")
    if db.scalar(select(RequirementClaim).where(RequirementClaim.model_version_id == mv.id)):
        raise HTTPException(409, "该作品已提交过申诉")
    keys = {i["key"] for i in data["checklist"]} | {"concept_mismatch"}
    valid = [i for i in body.items if i in keys]
    claim = RequirementClaim(model_version_id=mv.id, user_id=user.id, checklist_items=valid, note=body.note)
    # 自动判定：仅清单项/与效果图不符可成立；纯审美意见不属平台责任
    if not valid:
        claim.auto_result, claim.decision = "subjective", "user"
    elif "size" in valid:
        dims = mv.dimension_mm
        target = db.get(DesignSpec, db.get(GenerationTask, mv.task_id).design_spec_id).size_mm
        ok = abs(max(dims) - target) <= 2 or abs(dims[2] - target) <= 2
        claim.auto_result, claim.decision = ("size_ok", "pending") if ok else ("size_mismatch", "platform")
    else:
        claim.auto_result, claim.decision = "manual_review", "pending"
    claim.decided_at = now() if claim.decision != "pending" else None
    if claim.decision == "platform":
        task = db.get(GenerationTask, mv.task_id)
        ent = db.get(Entitlement, task.entitlement_id) if task.entitlement_id else None
        if ent:
            quota.restore_after_settled(db, ent, f"appeal:{claim.id}")
    db.add(claim)
    db.commit()
    msg = {"platform": "判定为平台责任，已恢复本次额度，可免费重新生成。",
           "user": "清单之外的审美意见不属于平台责任，可在对话设计中继续调整（按计次规则）。",
           "pending": "已提交人工复核，48 小时内答复。"}[claim.decision]
    return {"decision": claim.decision, "message": msg}
