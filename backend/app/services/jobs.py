"""异步生成任务（PRD §9.2 状态机）。进程内线程池执行；重启后自动恢复未完成任务（幂等：已有 provider_task_id 时只查询不重建）。

生产环境可替换为 Celery / RQ，任务函数保持不变。
"""
from __future__ import annotations

import logging
import os
import traceback
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from ..config import settings
from ..db import SessionLocal
from ..models import (ConceptImage, DesignSession, DesignSpec, Entitlement, GenerationTask, ManufacturingCheck,
                      ModelVersion, ProviderCostLedger, SliceReport, now)
from ..providers import aholo, aholo_client
from . import cad_templates, cost_governor, mesh_pipeline, quota, storage
from .materials import MATERIALS

log = logging.getLogger("zaowu.jobs")
_pool = ThreadPoolExecutor(max_workers=max(1, min(2, settings.generation_workers)), thread_name_prefix="gen")
TERMINAL = {"VERIFIED_DELIVERABLE", "FAILED_REFUND"}


def enqueue(task_id: str) -> None:
    _pool.submit(_run_safe, task_id)


def resume_pending() -> None:
    with SessionLocal() as db:
        ids = db.scalars(select(GenerationTask.id).where(GenerationTask.state.notin_(TERMINAL))).all()
    for i in ids:
        enqueue(i)


def _stage(db, task: GenerationTask, state: str, note: str = "") -> None:
    task.state = state
    task.stage_log = [*task.stage_log, {"state": state, "at": now().isoformat(), "note": note}]
    db.commit()


@contextmanager
def _task_lock(task_id):
    # OS locks survive threads/processes and are released automatically on crash.
    # All workers must share the same local storage (as they share SQLite).
    with storage.path_for(f"locks/{task_id}.lock").open("a+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            handle.write(b"0")
            handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                yield False
                return
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
        try:
            yield True
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _run_safe(task_id: str) -> None:
    with _task_lock(task_id) as acquired:
        if acquired:
            _run_locked(task_id)


def _run_locked(task_id: str) -> None:
    try:
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id)
            if not task or task.state in TERMINAL:
                return
            (_run_cad if task.engine == "cad" else _run_creative)(db, task)
    except Exception as e:  # 任何异常：失败并恢复权益
        log.error("task %s crashed: %s", task_id, traceback.format_exc())
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id)
            if task and task.state not in TERMINAL:
                _fail(db, task, "系统处理异常，请稍后重试", count_attempt=False)


def _fail(db, task: GenerationTask, reason: str, count_attempt: bool = True) -> None:
    ent = db.get(Entitlement, task.entitlement_id) if task.entitlement_id else None
    if ent:
        quota.release(db, ent, f"task_failed:{task.id}")
    quota.record_failure(db, task.user_id, task.cost_actual_fen, counts_attempt=count_attempt and task.engine == "creative")
    task.error = reason
    _stage(db, task, "FAILED_REFUND", reason)


def _deliver(db, task: GenerationTask, spec: DesignSpec, result: dict, title: str) -> None:
    material = MATERIALS[spec.material_id]
    mv = ModelVersion(user_id=task.user_id, task_id=task.id, title=title, engine=task.engine,
                      files=result["files"], dimension_mm=result["report"]["check"]["dimensionMm"],
                      material_id=spec.material_id, material_profile_version=material["profile_version"],
                      validation_state="passed", file_hash=result["hash"], verified_at=now())
    db.add(mv)
    db.flush()
    db.add(ManufacturingCheck(model_version_id=mv.id, material_profile_version=material["profile_version"],
                              report=result["report"], validation_state="passed"))
    sl = result["report"]["slice"]
    db.add(SliceReport(model_version_id=mv.id, slicer=sl.get("slicer", "estimate"),
                       profile_version=material["profile_version"], report=sl, result=sl.get("result", "")))
    task.model_version_id = mv.id
    ent = db.get(Entitlement, task.entitlement_id) if task.entitlement_id else None
    if ent:
        quota.settle(db, ent, f"verified:{mv.id}")
    _stage(db, task, "VERIFIED_DELIVERABLE", "合格交付，已核销 1 次")


def _run_creative(db, task: GenerationTask) -> None:
    spec = db.get(DesignSpec, task.design_spec_id)
    session = db.get(DesignSession, task.session_id)
    concept = db.scalar(select(ConceptImage).where(ConceptImage.session_id == session.id,
                                                   ConceptImage.version == task.concept_version))
    material = MATERIALS[spec.material_id]
    ent = db.get(Entitlement, task.entitlement_id)
    free_tier = bool(ent and ent.kind == "free")
    image_png = storage.path_for(concept.file_path).read_bytes()
    spec_dict = {**spec.spec, **concept.attributes}

    attempts = task.retry_count
    while True:
        attempts += 1
        remaining = session.budget_fen - session.spent_fen
        if not task.provider_task_id:
            unresolved = db.scalar(select(ProviderCostLedger).where(
                ProviderCostLedger.ref_type == "task", ProviderCostLedger.ref_id == task.id,
                ProviderCostLedger.outcome == "pending"))
            if unresolved:
                task.error = "供应商创建结果待核对，已暂停自动重试以避免重复扣费"
                db.commit()
                return
            try:
                cost_governor.approve(remaining, settings.cost_lux3d_fen)
            except cost_governor.BudgetExceeded as e:
                return _fail(db, task, f"成本预算不足，未调用 Lux3D：{e}")
            _stage(db, task, "QUEUED", "已通过成本审核")
            call = cost_governor.open_call(db, user_id=task.user_id, ref_type="task", ref_id=task.id,
                                           provider="aholo" if not settings.aholo_mock else "aholo-mock",
                                           endpoint="image-to-3d", estimate_fen=settings.cost_lux3d_fen, free_tier=free_tier)
            from . import prompt_compiler
            prompt = prompt_compiler.lux3d_prompt(spec_dict) if task.params.get("useTextConstraint") else None
            try:
                task.provider_task_id = aholo.submit(image_png, prompt, f"{task.id}-{attempts}", spec_dict)
            except aholo_client.AholoCreateUncertain:
                task.error = "供应商创建结果待核对，已暂停自动重试以避免重复扣费"
                db.commit()
                return
            except aholo_client.AholoError:
                cost_governor.close_call(call, "failed", 0)
                db.commit()
                return _fail(db, task, "供应商拒绝创建任务，已恢复生成额度")
            except Exception:
                task.error = "供应商创建结果待核对，已暂停自动重试以避免重复扣费"
                db.commit()
                return
            task.provider = "aholo"
            call.provider_task_id = task.provider_task_id
            db.commit()
        else:
            call = db.scalar(select(ProviderCostLedger).where(
                ProviderCostLedger.ref_type == "task", ProviderCostLedger.ref_id == task.id,
                ProviderCostLedger.provider_task_id == task.provider_task_id).order_by(ProviderCostLedger.id.desc()))
        _stage(db, task, "RUNNING", f"Lux3D 图生 3D · {task.provider_task_id}")
        try:
            res = aholo.poll(task.provider_task_id)
        except Exception:
            task.error = "供应商任务查询暂未完成，可继续查询现有任务"
            db.commit()
            return
        if res.get("status") not in ("succeeded", "failed"):
            return
        if call is None or call.outcome == "pending":
            cost = int(res.get("costFen") if res.get("costFen") is not None else settings.cost_lux3d_fen)
            task.cost_actual_fen += cost
            session.spent_fen += cost
            if call:
                actual = cost if res.get("costFen") is not None and (settings.aholo_mock or res.get("actualCostKnown")) else None
                cost_governor.close_call(call, "success" if res["status"] == "succeeded" else "failed", actual, task.provider_task_id)
        task.error = ""
        db.commit()
        if res["status"] != "succeeded":
            return _fail(db, task, "Lux3D 生成失败")
        _stage(db, task, "PROCESSING_ASSET", "转存模型、统一坐标与单位")
        glb = aholo.download(res, spec_dict)
        storage.save_bytes(f"models/{task.id}/source_{attempts}.glb", glb)
        mesh = mesh_pipeline.load_glb(glb)
        _stage(db, task, "MANUFACTURING_VALIDATION", "修复 · 水密 · 壁厚 · 尺寸")
        result = mesh_pipeline.process(mesh, material, spec.size_mm, f"models/{task.id}")
        if result["passed"]:
            _stage(db, task, "SLICE_CHECK", f"切片：{result['report']['slice'].get('printTimeMin', '?')} 分钟")
            session.state = "confirmed"
            return _deliver(db, task, spec, result, session.title or "我的作品")
        # 本地修复失败：仅当剩余预算足够且未重试过时，再付费重生成一次
        task.retry_count += 1
        if attempts >= 2 or session.budget_fen - session.spent_fen < settings.cost_lux3d_fen:
            failed = [i["label"] for i in result["report"]["check"]["items"] if not i["ok"]]
            return _fail(db, task, "制造预检未通过：" + "、".join(failed or ["切片失败"]))
        task.provider_task_id = None
        _stage(db, task, "REPAIRING", "本地修复未达标，预算内重新生成一次")


def _run_cad(db, task: GenerationTask) -> None:
    spec = db.get(DesignSpec, task.design_spec_id)
    if spec.spec.get("mode") == "ai":
        from . import cad_ai_jobs
        return cad_ai_jobs.run(db, task, spec)
    material = MATERIALS[spec.material_id]
    kind, params = spec.spec["template"], spec.spec["params"]
    _stage(db, task, "RUNNING", f"本地 CAD 模板 {cad_templates.TEMPLATES[kind]['version']} · 外部 API 0 次")
    mesh = cad_templates.build(kind, params)
    _stage(db, task, "MANUFACTURING_VALIDATION", "CAD 内核实测")
    result = mesh_pipeline.process(mesh, material, None, f"models/{task.id}", expected_bodies=2 if kind == "box" else 1)
    if not result["passed"]:
        failed = [i["label"] for i in result["report"]["check"]["items"] if not i["ok"]]
        return _fail(db, task, "CAD 校验未通过：" + "、".join(failed or ["切片失败"]))
    _stage(db, task, "SLICE_CHECK", "切片检查通过")
    _deliver(db, task, spec, result, f"{cad_templates.TEMPLATES[kind]['name']} {spec.spec.get('label', '')}".strip())
