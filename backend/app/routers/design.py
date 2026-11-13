"""创意路线：效果图对话设计（PRD §2.4、GEN-A13～A17、FR-15/16/36）。"""
from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from PIL import Image

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import ConceptImage, DesignSession, DesignSpec, Entitlement, GenerationTask, User, now
from ..providers import image as image_provider
from ..providers import aholo_client
from ..security import current_user, sign_url
from ..services import cost_governor, jobs, preflight, prompt_compiler, quota, storage
from ..services.materials import get_material

router = APIRouter(prefix="/api/v1/design-sessions", tags=["design"])


class OpenIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=400)
    materialId: str = "mono_resin"
    sizeMm: float = 60
    purpose: str = "桌面摆件"
    idempotencyKey: str | None = Field(default=None, max_length=64)


class TurnIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=200)
    baseVersion: int | None = None


class ConfirmIn(BaseModel):
    version: int
    idempotencyKey: str | None = Field(default=None, max_length=64)


def _concept_out(c: ConceptImage, user_id: str) -> dict:
    return {"version": c.version, "parentVersion": c.parent_version, "instruction": c.instruction,
            "dimension": c.dimension, "summary": prompt_compiler.summary(c.attributes),
            "imageUrl": sign_url(c.file_path, user_id, 120), "qc": c.qc_result, "createdAt": c.created_at.isoformat()}


def session_out(db: Session, s: DesignSession) -> dict:
    spec = db.get(DesignSpec, s.design_spec_id)
    concepts = db.scalars(select(ConceptImage).where(ConceptImage.session_id == s.id).order_by(ConceptImage.version)).all()
    task = db.scalar(select(GenerationTask).where(GenerationTask.session_id == s.id).order_by(GenerationTask.created_at.desc()))
    mat = get_material(spec.material_id)
    return {
        "id": s.id, "title": s.title, "state": s.state, "turnsUsed": s.turns_used, "turnsLimit": s.turns_limit,
        "turnsRemaining": s.turns_limit - s.turns_used, "currentVersion": s.current_version,
        "confirmedVersion": s.confirmed_version, "expiresAt": s.expires_at.isoformat(),
        "material": {"id": mat["id"], "name": mat["name"], "color": mat["color"], "note": mat["note"]},
        "sizeMm": spec.size_mm, "purpose": spec.spec.get("purpose"), "checklist": spec.hard_checklist,
        "messages": s.messages, "concepts": [_concept_out(c, s.user_id) for c in concepts],
        "taskId": task.id if task else None, "taskState": task.state if task else None,
    }


def _qc(spec: dict, png: bytes) -> dict:
    """Image integrity and requested design rules; no visual composition inference."""
    valid = False
    dimensions = None
    try:
        with Image.open(BytesIO(png)) as image:
            dimensions = list(image.size)
            valid = image.format == "PNG" and min(image.size) >= 256 and max(image.size) <= 8192
            image.verify()
        with Image.open(BytesIO(png)) as image:
            image.load()
    except Exception:
        valid = False
    integrated = bool(spec.get("connectedBase") or spec.get("hangHole"))
    return {"singleSubject": None, "integratedBase": integrated, "noFloating": None,
            "cleanBackground": None, "imageIntegrity": valid, "dimensions": dimensions,
            "method": "image-integrity-and-design-rules", "estimated": True,
            "passed": valid and integrated}


def _generate_concept(db: Session, user: User, s: DesignSession, spec: dict, version: int, parent: int | None,
                      instruction: str, dimension: str, free_tier: bool) -> ConceptImage:
    remaining = s.budget_fen - s.spent_fen - settings.cost_lux3d_fen  # 始终为转 3D 预留
    try:
        cost_governor.approve(remaining, settings.cost_concept_image_fen)
    except cost_governor.BudgetExceeded as e:
        raise cost_governor.http_budget_error(e)
    # Persist the in-flight state together with each cost reservation. Other requests
    # cannot edit, confirm, expire, or abandon this session during a network call.
    s.state = "generating"
    if settings.deepseek_api_key:
        from ..providers import deepseek
        try:
            cost_governor.approve(remaining - settings.cost_concept_image_fen, settings.cost_semantic_fen)
        except cost_governor.BudgetExceeded as e:
            raise cost_governor.http_budget_error(e)
        semantic = cost_governor.open_call(db, user_id=user.id, ref_type="session", ref_id=s.id,
                                          provider="deepseek", endpoint="design-spec",
                                          estimate_fen=settings.cost_semantic_fen, free_tier=free_tier)
        try:
            spec = deepseek.refine(spec, instruction if parent is not None else None)
        except Exception:
            _concept_failure(db, s, semantic, parent)
            raise HTTPException(502, "语义服务暂不可用，请稍后重试")
        cost_governor.close_call(semantic, "success")
        s.spent_fen += settings.cost_semantic_fen
        db.commit()
    prompt = prompt_compiler.concept_prompt(spec)
    call = cost_governor.open_call(db, user_id=user.id, ref_type="session", ref_id=s.id,
                                   provider="image-mock" if settings.image_mock else settings.image_provider,
                                   endpoint="concept" if parent is None else "concept-edit",
                                   estimate_fen=settings.cost_concept_image_fen, free_tier=free_tier)
    ref = None
    if parent is not None:
        prev = db.scalar(select(ConceptImage).where(ConceptImage.session_id == s.id, ConceptImage.version == parent))
        ref = storage.path_for(prev.file_path).read_bytes()
    try:
        if settings.image_mock:
            res = image_provider.generate(prompt, spec, ref)
        else:
            def remember_task(provider_task_id):
                call.provider_task_id = provider_task_id
                db.commit()
            res = image_provider.generate(prompt, spec, ref, on_task_created=remember_task)
    except Exception as exc:
        definite_rejection = (isinstance(exc, aholo_client.AholoError)
                              and not isinstance(exc, aholo_client.AholoCreateUncertain)
                              and not call.provider_task_id)
        _concept_failure(db, s, call, parent, actual_fen=0 if definite_rejection else None)
        raise HTTPException(502, "图像服务暂不可用，请稍后重试")
    actual = res.cost_fen if settings.image_mock or getattr(res, "actual_cost_known", False) else None
    cost_governor.close_call(call, "success", actual, getattr(res, "task_id", None))
    s.spent_fen += res.cost_fen
    db.commit()
    rel = storage.save_bytes(f"concepts/{s.id}/v{version}.png", res.png)
    c = ConceptImage(session_id=s.id, version=version, parent_version=parent, instruction=instruction, dimension=dimension,
                     prompt=prompt, prompt_template_version=prompt_compiler.CONCEPT_TEMPLATE_VERSION, attributes=spec,
                     provider=res.provider, cost_fen=res.cost_fen, qc_result=_qc(spec, res.png), file_path=rel,
                     file_hash=storage.sha256_bytes(res.png))
    db.add(c)
    s.current_version = version
    return c


def _concept_failure(db, s, call, parent, actual_fen=None):
    cost_governor.close_call(call, "failed", actual_fen)
    expense = actual_fen if actual_fen is not None else call.cost_estimated_fen
    s.spent_fen += expense
    if parent is None:
        ent = db.get(Entitlement, s.entitlement_id)
        quota.release(db, ent, f"first_image_failed:{s.id}")
        s.state = "abandoned"
    else:
        s.turns_used = max(0, s.turns_used - 1)
        s.state = "adjusting"
    quota.record_failure(db, s.user_id, expense, counts_attempt=False)
    db.commit()


def _owned(db: Session, sid: str, user: User) -> DesignSession:
    quota.lock_write(db, user.id)
    s = db.get(DesignSession, sid)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "设计会话不存在")
    if s.state in ("opened", "concept_ready", "adjusting") and s.expires_at.replace(tzinfo=s.expires_at.tzinfo or now().tzinfo) < now():
        _abandon(db, s, "expired")
        db.commit()
    return s


def _abandon(db: Session, s: DesignSession, state: str) -> None:
    active = db.scalar(select(GenerationTask.id).where(GenerationTask.session_id == s.id, GenerationTask.state.notin_(jobs.TERMINAL)))
    if active:
        return
    ent = db.get(Entitlement, s.entitlement_id) if s.entitlement_id else None
    if ent:
        quota.release(db, ent, f"session_{state}:{s.id}")
    quota.record_failure(db, s.user_id, s.spent_fen, counts_attempt=False)
    quota.ledger(db, s.user_id).abandoned_sessions += 1
    s.state = state


@router.post("/preflight")
def preflight_only(body: OpenIn, user: User = Depends(current_user)):
    try:
        mat = get_material(body.materialId)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return preflight.check_text(body.prompt, mat, body.sizeMm).to_dict()


@router.post("")
def open_session(body: OpenIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quota.lock_write(db, user.id)
    if body.idempotencyKey:
        old = db.scalar(select(DesignSession).where(DesignSession.idempotency_key == body.idempotencyKey))
        if old:
            if old.user_id != user.id:
                raise HTTPException(409, "幂等键已被使用")
            return session_out(db, old)
    try:
        mat = get_material(body.materialId)
    except ValueError as e:
        raise HTTPException(400, str(e))
    pf = preflight.check_text(body.prompt, mat, body.sizeMm)
    if not pf.ok:
        raise HTTPException(422, {"preflight": pf.to_dict()})
    lg = quota.ledger(db, user.id)
    if lg.abandoned_sessions >= settings.daily_abandoned_sessions_limit:
        raise HTTPException(429, f"今天已放弃 {lg.abandoned_sessions} 个设计会话，请先完成已有设计或明天再来。")
    free_left = settings.daily_free_quota - lg.free_used - lg.free_reserved
    quota.ensure_paid_engine_allowed(db, user, free_tier=free_left > 0)
    spec = prompt_compiler.build_spec(body.prompt, mat, body.sizeMm, body.purpose)
    ds = DesignSpec(user_id=user.id, engine="creative", category=spec["category"], material_id=mat["id"],
                    material_profile_version=mat["profile_version"], size_mm=body.sizeMm, spec=spec,
                    hard_checklist=prompt_compiler.hard_checklist(spec, mat),
                    risk_flags=[i.code for i in pf.issues], template_version=prompt_compiler.CONCEPT_TEMPLATE_VERSION)
    db.add(ds)
    db.flush()
    s = DesignSession(user_id=user.id, design_spec_id=ds.id, title=body.prompt.strip()[:24],
                      turns_limit=settings.design_turns_limit, budget_fen=settings.session_budget_fen,
                      idempotency_key=body.idempotencyKey,
                      expires_at=now() + timedelta(hours=settings.session_expire_hours))
    db.add(s)
    db.flush()
    ent = quota.reserve(db, user, "session", s.id)
    s.entitlement_id = ent.id
    note = "" if mat["color"] else "（单色材料：颜色只体现在效果图上，打印件为材料本色）"
    _generate_concept(db, user, s, spec, 0, None, body.prompt, "", ent.kind == "free")
    s.state = "concept_ready"
    s.messages = [
        {"role": "user", "text": body.prompt, "at": now().isoformat()},
        {"role": "ai", "version": 0, "at": now().isoformat(),
         "text": "第一张效果图好了。我按打印要求做成了一体结构"
                 + ("，并加了稳固的底座" if spec["connectedBase"] else "") + "。" + note
                 + "".join(f" 提示：{i.message}{i.suggestion}" for i in pf.issues if i.level == "warn")},
    ]
    db.commit()
    return session_out(db, s)


@router.get("")
def list_sessions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(DesignSession).where(DesignSession.user_id == user.id).order_by(DesignSession.created_at.desc()).limit(50)).all()
    return [{"id": s.id, "title": s.title, "state": s.state, "turnsUsed": s.turns_used, "createdAt": s.created_at.isoformat()} for s in rows]


@router.get("/{sid}")
def get_session(sid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return session_out(db, _owned(db, sid, user))


@router.post("/{sid}/turns")
def add_turn(sid: str, body: TurnIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quota.lock_write(db, user.id)
    db.expire_all()
    s = _owned(db, sid, user)
    if s.state not in ("concept_ready", "adjusting"):
        raise HTTPException(409, "该设计会话已结束")
    spec_row = db.get(DesignSpec, s.design_spec_id)
    mat = get_material(spec_row.material_id)
    msgs = [*s.messages, {"role": "user", "text": body.instruction, "at": now().isoformat()}]
    pf = preflight.check_text(body.instruction, mat)
    if not pf.ok:  # 预检拦截：不调用付费接口、不消耗次数
        blk = next(i for i in pf.issues if i.level == "block")
        msgs.append({"role": "block", "text": blk.message, "suggestion": blk.suggestion, "at": now().isoformat()})
        s.messages = msgs
        db.commit()
        return session_out(db, s)
    if s.turns_used >= s.turns_limit:
        raise HTTPException(409, f"本次设计的 {s.turns_limit} 次调整已用完：可以选择任一版本转 3D，或新开一个设计。")
    base_v = body.baseVersion if body.baseVersion is not None else s.current_version
    base = db.scalar(select(ConceptImage).where(ConceptImage.session_id == s.id, ConceptImage.version == base_v))
    if not base:
        raise HTTPException(400, "参考版本不存在")
    new_spec, dim = prompt_compiler.apply_instruction(base.attributes, body.instruction)
    ent = db.get(Entitlement, s.entitlement_id)
    # 次数原子扣减：先占位再生成，失败回滚
    s.turns_used += 1
    version = db.scalar(select(ConceptImage.version).where(ConceptImage.session_id == s.id).order_by(ConceptImage.version.desc())) + 1
    try:
        _generate_concept(db, user, s, new_spec, version, base_v, body.instruction, dim, bool(ent and ent.kind == "free"))
    except Exception:
        db.rollback()
        raise
    s.state = "adjusting"
    tip = ""
    if "颜色" in dim and not mat["color"]:
        tip = f" 提示：{mat['note']}"
    msgs.append({"role": "ai", "version": version, "dimension": dim, "turn": s.turns_used, "at": now().isoformat(),
                 "text": f"已按「{body.instruction}」调整为 v{version}。{tip}"})
    s.messages = msgs
    db.commit()
    return session_out(db, s)


@router.post("/{sid}/confirm")
def confirm(sid: str, body: ConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quota.lock_write(db, user.id)
    db.expire_all()
    s = _owned(db, sid, user)
    if s.state == "generating":
        raise HTTPException(409, "效果图正在生成，请稍后确认")
    if body.idempotencyKey:
        t = db.scalar(select(GenerationTask).where(GenerationTask.idempotency_key == body.idempotencyKey))
        if t:
            if t.user_id != user.id or t.session_id != s.id or t.engine != "creative":
                raise HTTPException(409, "幂等键已被使用")
            return {"taskId": t.id}
    existing = db.scalar(select(GenerationTask).where(GenerationTask.session_id == s.id,
                                                      GenerationTask.state.notin_(("FAILED_REFUND",))))
    if existing and existing.state != "VERIFIED_DELIVERABLE":
        return {"taskId": existing.id}
    c = db.scalar(select(ConceptImage).where(ConceptImage.session_id == s.id, ConceptImage.version == body.version))
    if not c:
        raise HTTPException(400, "版本不存在")
    if not c.qc_result.get("passed"):
        raise HTTPException(422, "这张效果图不适合转 3D（构图质检未通过），请再调整一次。")
    ent = db.get(Entitlement, s.entitlement_id) if s.entitlement_id else None
    if existing and existing.state == "VERIFIED_DELIVERABLE" or not ent or ent.state != "reserved":
        # 已交付后改选其他版本 / 原权益已失效：重新预留 1 次
        ent = quota.reserve(db, user, "session", s.id)
        s.entitlement_id = ent.id
        s.budget_fen = s.spent_fen + settings.cost_lux3d_fen * 2
    quota.ensure_paid_engine_allowed(db, user, free_tier=ent.kind == "free")
    task = GenerationTask(user_id=user.id, engine="creative", design_spec_id=s.design_spec_id, session_id=s.id,
                          concept_version=c.version, entitlement_id=ent.id, idempotency_key=body.idempotencyKey,
                          stage_log=[{"state": "CREATED", "at": now().isoformat(), "note": f"确认效果图 v{c.version}"}])
    db.add(task)
    s.state = "confirmed"
    s.confirmed_version = c.version
    s.messages = [*s.messages, {"role": "system", "text": f"已确认 v{c.version}，开始转成 3D。", "at": now().isoformat()}]
    db.commit()
    jobs.enqueue(task.id)
    return {"taskId": task.id}


@router.post("/{sid}/abandon")
def abandon(sid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    quota.lock_write(db, user.id)
    db.expire_all()
    s = _owned(db, sid, user)
    if s.state in ("concept_ready", "adjusting", "opened"):
        _abandon(db, s, "abandoned")
        db.commit()
    return session_out(db, s)
