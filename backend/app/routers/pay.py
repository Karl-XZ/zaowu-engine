"""支付（PRD §5.2、§5.3）：订单 → 支付宝 → 异步通知验签 + 主动查单 → 发放一次付费权益（幂等）。"""
from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Entitlement, PaymentOrder, User, now
from ..providers import alipay
from ..security import current_user
from ..services import quota

router = APIRouter(prefix="/api/v1/pay", tags=["pay"])


def _order_out(o: PaymentOrder) -> dict:
    return {"id": o.id, "outTradeNo": o.out_trade_no, "amountFen": o.amount_fen, "state": o.state,
            "paidAt": o.paid_at.isoformat() if o.paid_at else None, "mock": settings.alipay_mock}


@router.post("/orders")
def create_order(user: User = Depends(current_user), db: Session = Depends(get_db)):
    # 金额只由服务端决定；单账户未使用权益上限 3 次（PRD §5.2 合规边界）
    if quota.paid_credits(db, user.id) >= 3:
        raise HTTPException(409, "你还有未使用的付费次数，先用完再购买。")
    o = PaymentOrder(user_id=user.id, amount_fen=settings.paid_price_fen,
                     out_trade_no=f"Z{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(4).upper()}")
    db.add(o)
    db.commit()
    url = alipay.create_payment(o.out_trade_no, o.amount_fen, f"{settings.app_name} · 3D 模型生成 1 次")
    return {**_order_out(o), "payUrl": url}


@router.get("/orders/{oid}")
def get_order(oid: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(PaymentOrder, oid)
    if not o or o.user_id != user.id:
        raise HTTPException(404, "订单不存在")
    if o.state == "WAITING_PAY":  # 前端轮询时主动查单补偿（网络超时场景）
        _try_complete(db, o, source="poll")
    return _order_out(o)


def _try_complete(db: Session, o: PaymentOrder, source: str, notify: dict | None = None) -> None:
    if o.state != "WAITING_PAY":
        return  # 幂等：重复通知不重复入账
    if source == "poll" and settings.alipay_mock:
        return  # 模拟模式下需在模拟收银台点击支付
    paid, trade_no, amount = alipay.query_paid(o.out_trade_no)
    o.notify_log = [*o.notify_log, {"source": source, "at": now().isoformat(), "paid": paid, "raw": notify or {}}]
    if not paid:
        db.commit()
        return
    if amount is not None and amount != o.amount_fen:
        o.state = "AMOUNT_MISMATCH"
        db.commit()
        return
    o.state, o.paid_at, o.external_trade_no = "PAID", now(), trade_no
    quota.grant_paid(db, o)
    db.commit()


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    form = dict(await request.form())
    if not alipay.verify_notify(form):
        raise HTTPException(400, "签名校验失败")
    o = db.scalar(select(PaymentOrder).where(PaymentOrder.out_trade_no == form.get("out_trade_no")).with_for_update())
    if not o:
        raise HTTPException(404, "订单不存在")
    _try_complete(db, o, "notify", {k: form.get(k) for k in ("trade_no", "trade_status", "total_amount")})
    return PlainTextResponse("success")


class MockIn(BaseModel):
    outTradeNo: str


@router.post("/mock/confirm")
def mock_confirm(body: MockIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not settings.alipay_mock:
        raise HTTPException(404, "Not found")
    o = db.scalar(select(PaymentOrder).where(PaymentOrder.out_trade_no == body.outTradeNo))
    if not o or o.user_id != user.id:
        raise HTTPException(404, "订单不存在")
    _try_complete(db, o, "notify", {"mock": "1"})
    return _order_out(o)


@router.post("/refund-unused")
def refund_unused(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """对未使用的付费权益原路退款（失败恢复的权益同样适用）。"""
    ents = db.scalars(select(Entitlement).where(Entitlement.user_id == user.id, Entitlement.kind == "paid",
                                                Entitlement.state == "available", Entitlement.payment_order_id.isnot(None))).all()
    done = 0
    for e in ents:
        o = db.get(PaymentOrder, e.payment_order_id)
        if o and o.state in ("ENTITLEMENT_GRANTED", "PAID") and alipay.refund(o.out_trade_no, o.amount_fen, "未使用权益退款"):
            o.state, o.refunded_at = "REFUNDED", now()
            e.state = "refunded"
            done += 1
    db.commit()
    return {"refunded": done}
