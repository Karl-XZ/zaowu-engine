"""额度、材料、配置、文件下载、嘉立创导出、管理后台。"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (DesignSession, GenerationTask, ModelVersion, PaymentOrder, PrintOrder, ProviderCostLedger,
                      RequirementClaim, User, now)
from ..providers import jlc
from ..security import admin_user, current_user, verify_signed
from ..services import quota, storage
from ..services.materials import MATERIALS, public_materials

router = APIRouter(prefix="/api/v1", tags=["misc"])


@router.get("/config")
def config():
    return {"appName": settings.app_name, "priceFen": settings.paid_price_fen, "dailyFree": settings.daily_free_quota,
            "turnsLimit": settings.design_turns_limit, "appealHours": settings.appeal_window_hours,
            "mock": {"image": settings.image_mock, "aholo": settings.aholo_mock, "alipay": settings.alipay_mock,
                     "jlc": settings.jlc_mock, "slicer": not bool(settings.slicer_cli_path)},
            "jlcMode": jlc.mode()}


@router.get("/materials")
def materials():
    return public_materials()


@router.get("/quota")
def get_quota(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return quota.status(db, user)


@router.get("/files/{path:path}")
def file(path: str, u: str, e: int, s: str):
    if not verify_signed(path, u, e, s):
        raise HTTPException(403, "链接无效或已过期")
    p = storage.path_for(path)
    if not p.exists():
        raise HTTPException(404, "文件不存在")
    media = {".png": "image/png", ".glb": "model/gltf-binary", ".stl": "model/stl", ".3mf": "model/3mf", ".step": "application/step",
             ".json": "application/json"}.get(p.suffix, "application/octet-stream")
    return FileResponse(p, media_type=media, filename=p.name if p.suffix in (".stl", ".3mf", ".step", ".json") else None)


@router.post("/print/{mid}/package")
def print_package(mid: str, quantity: int = 1, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """锁定生产文件哈希，生成嘉立创下单包（模式 B），API 获批后走模式 A 报价。"""
    mv = db.get(ModelVersion, mid)
    if not mv or mv.user_id != user.id or mv.validation_state != "passed":
        raise HTTPException(404, "仅合格交付的模型可以下单")
    if "stl" not in mv.files:
        raise HTTPException(409, "缺少生产文件")
    if storage.sha256_file(mv.files["stl"]) != mv.file_hash:
        raise HTTPException(409, "生产文件哈希与验收时不一致，已阻断")
    quote = None
    if jlc.mode() == "A":
        quote = jlc.quote(storage.path_for(mv.files["stl"]).read_bytes(), "model.stl", mv.material_id, quantity)
    po = PrintOrder(user_id=user.id, model_version_id=mv.id, file_hash=mv.file_hash, material_id=mv.material_id,
                    quantity=quantity, mode=jlc.mode(), status="QUOTED" if quote else "DRAFT", quote=quote or {})
    db.add(po)
    if not mv.production_downloaded_at:
        mv.production_downloaded_at = now()
    db.commit()
    return {"printOrderId": po.id, "mode": po.mode, "quote": quote, "uploadUrl": jlc.manual_upload_url(),
            "material": MATERIALS[mv.material_id]["name"], "fileHash": mv.file_hash,
            "packageUrl": f"/api/v1/print/{po.id}/zip"}


@router.get("/print/{pid}/zip")
def print_zip(pid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    po = db.get(PrintOrder, pid)
    if not po or po.user_id != user.id:
        raise HTTPException(404, "订单不存在")
    mv = db.get(ModelVersion, po.model_version_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k in ("stl", "3mf", "report"):
            if k in mv.files:
                z.write(storage.path_for(mv.files[k]), arcname=f"{mv.title or 'model'}.{ 'json' if k == 'report' else k}")
        z.writestr("README.txt", f"造物引擎 生产文件包\n材料：{MATERIALS[mv.material_id]['name']}\n数量：{po.quantity}\n"
                                 f"尺寸(mm)：{' x '.join(str(x) for x in mv.dimension_mm)}\nSHA-256：{mv.file_hash}\n"
                                 f"请在嘉立创 3D 打印下单页上传 STL/3MF，并选择上述材料。\n")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename=zaowu_{mv.id[:8]}.zip"})


@router.get("/admin/overview")
def admin_overview(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    start = datetime.now(quota.TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    cost = lambda *conds: db.scalar(select(func.coalesce(func.sum(ProviderCostLedger.cost_estimated_fen), 0)).where(*conds)) or 0
    states = dict(db.execute(select(GenerationTask.state, func.count()).group_by(GenerationTask.state)).all())
    delivered = states.get("VERIFIED_DELIVERABLE", 0)
    total_cost = cost()
    revenue = db.scalar(select(func.coalesce(func.sum(PaymentOrder.amount_fen), 0)).where(
        PaymentOrder.state.in_(("PAID", "ENTITLEMENT_GRANTED", "USED")))) or 0
    recent_fail = db.scalars(select(GenerationTask).where(GenerationTask.state == "FAILED_REFUND")
                             .order_by(GenerationTask.created_at.desc()).limit(10)).all()
    ledger = db.scalars(select(ProviderCostLedger).order_by(ProviderCostLedger.id.desc()).limit(30)).all()
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "sessions": db.scalar(select(func.count()).select_from(DesignSession)),
        "taskStates": states, "delivered": delivered,
        "costTodayFen": cost(ProviderCostLedger.created_at >= start),
        "freeCostTodayFen": cost(ProviderCostLedger.created_at >= start, ProviderCostLedger.is_free_tier.is_(True)),
        "platformFreeBudgetFen": settings.platform_daily_free_budget_fen,
        "costTotalFen": total_cost, "revenueFen": revenue,
        "costPerDeliveredFen": round(total_cost / delivered) if delivered else None,
        "claimsPending": db.scalar(select(func.count()).select_from(RequirementClaim).where(RequirementClaim.decision == "pending")),
        "recentFailures": [{"id": t.id, "engine": t.engine, "error": t.error, "cost": t.cost_actual_fen,
                            "at": t.created_at.isoformat()} for t in recent_fail],
        "ledger": [{"id": r.id, "provider": r.provider, "endpoint": r.endpoint, "estimated": r.cost_estimated_fen,
                    "actual": r.cost_actual_fen, "free": r.is_free_tier, "outcome": r.outcome, "at": r.created_at.isoformat()}
                   for r in ledger],
        "mock": config()["mock"],
    }
