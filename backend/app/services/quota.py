"""额度与权益账本（PRD §5）。

- 每日 3 次免费按北京时间自然日计；创意与 CAD 共用。
- 任务开始先预留权益；只有 VERIFIED_DELIVERABLE 才核销；失败释放。
- 失败尝试次数 / 失败成本 / 连续失败 / 放弃会话 上限，防止“刷失败不扣次”。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Entitlement, EntitlementEvent, PaymentOrder, ProviderCostLedger, QuotaLedger, User, now

TZ = ZoneInfo(settings.timezone)


def lock_write(db: Session, user_id: str | None = None) -> None:
    """SQLite has no row locks: acquire its writer lock before reading balances."""
    connection = db.connection()
    if connection.dialect.name == "sqlite":
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    elif user_id:
        db.execute(select(User.id).where(User.id == user_id).with_for_update())


def biz_date(dt: datetime | None = None) -> str:
    return (dt or datetime.now(TZ)).astimezone(TZ).strftime("%Y-%m-%d")


def next_reset() -> datetime:
    n = datetime.now(TZ)
    return (n + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def ledger(db: Session, user_id: str, date: str | None = None) -> QuotaLedger:
    lock_write(db, user_id)
    db.flush()
    date = date or biz_date()
    row = db.execute(
        select(QuotaLedger).where(QuotaLedger.user_id == user_id, QuotaLedger.biz_date == date)
        .with_for_update().execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if row is None:
        row = QuotaLedger(user_id=user_id, biz_date=date)
        db.add(row)
        db.flush()
    return row


def _event(db: Session, user_id: str, ent_id: str | None, type_: str, reason: str = "") -> None:
    db.add(EntitlementEvent(user_id=user_id, entitlement_id=ent_id, type=type_, reason=reason))


def paid_credits(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(Entitlement).where(
            Entitlement.user_id == user_id, Entitlement.kind == "paid", Entitlement.state == "available"
        )
    ) or 0


def platform_free_spend_today(db: Session) -> int:
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(
        select(func.coalesce(func.sum(ProviderCostLedger.cost_estimated_fen), 0)).where(
            ProviderCostLedger.is_free_tier.is_(True), ProviderCostLedger.created_at >= start
        )
    ) or 0


def status(db: Session, user: User) -> dict:
    lg = ledger(db, user.id)
    db.commit()
    free_left = max(0, settings.daily_free_quota - lg.free_used - lg.free_reserved)
    return {
        "bizDate": lg.biz_date,
        "freeTotal": settings.daily_free_quota,
        "freeUsed": lg.free_used,
        "freeReserved": lg.free_reserved,
        "freeRemaining": free_left,
        "paidCredits": paid_credits(db, user.id),
        "priceFen": settings.paid_price_fen,
        "resetAt": next_reset().isoformat(),
        "failedAttempts": lg.failed_attempts,
        "failedAttemptsLimit": settings.daily_failed_attempts_limit,
        "failedCostFen": lg.failed_cost_fen,
        "failedCostLimitFen": settings.daily_failed_cost_limit_fen,
        "consecutiveFailures": lg.consecutive_failures,
        "abandonedSessions": lg.abandoned_sessions,
        "abandonedSessionsLimit": settings.daily_abandoned_sessions_limit,
        "cadRebuilds": lg.cad_rebuilds,
        "cadRebuildLimit": settings.daily_cad_rebuild_limit,
        "paidEngineBlocked": paid_engine_block_reason(lg) is not None,
        "blockReason": paid_engine_block_reason(lg),
    }


def paid_engine_block_reason(lg: QuotaLedger) -> str | None:
    if lg.failed_attempts >= settings.daily_failed_attempts_limit:
        return f"今日未交付的生成尝试已达 {settings.daily_failed_attempts_limit} 次，付费引擎明天 00:00 恢复；精确 CAD 模板仍可使用。"
    if lg.failed_cost_fen >= settings.daily_failed_cost_limit_fen:
        return "今日失败生成的成本已达上限，付费引擎明天 00:00 恢复；精确 CAD 模板仍可使用。"
    if lg.consecutive_failures >= settings.consecutive_failure_limit:
        return f"已连续 {lg.consecutive_failures} 次未能交付，请调整描述或改用推荐模板后再试。"
    return None


def ensure_paid_engine_allowed(db: Session, user: User, free_tier: bool) -> None:
    lg = ledger(db, user.id)
    reason = paid_engine_block_reason(lg)
    if reason:
        raise HTTPException(429, reason)
    if free_tier and platform_free_spend_today(db) >= settings.platform_daily_free_budget_fen:
        raise HTTPException(503, "今日免费生成名额已用完（平台预算熔断），明天 00:00 恢复；可使用付费生成或 CAD 模板。")


def reserve(db: Session, user: User, ref_type: str, ref_id: str) -> Entitlement:
    """原子预留一次权益：优先免费额度，其次已付权益；都没有则 402。"""
    lg = ledger(db, user.id)
    if lg.free_used + lg.free_reserved < settings.daily_free_quota:
        lg.free_reserved += 1
        ent = Entitlement(user_id=user.id, kind="free", biz_date=lg.biz_date, state="reserved", ref_type=ref_type, ref_id=ref_id)
        db.add(ent)
        db.flush()
        _event(db, user.id, ent.id, "free_reserved", f"{ref_type}:{ref_id}")
        return ent
    ent = db.execute(
        select(Entitlement).where(
            Entitlement.user_id == user.id, Entitlement.kind == "paid", Entitlement.state == "available"
        ).order_by(Entitlement.created_at).limit(1).with_for_update()
    ).scalar_one_or_none()
    if ent is None:
        raise HTTPException(402, "今日免费额度已用完，支付 ¥5 后可继续生成")
    ent.state, ent.ref_type, ent.ref_id = "reserved", ref_type, ref_id
    _event(db, user.id, ent.id, "paid_frozen", f"{ref_type}:{ref_id}")
    return ent


def settle(db: Session, ent: Entitlement, reason: str = "verified_deliverable") -> None:
    lock_write(db, ent.user_id)
    changed = db.execute(update(Entitlement).where(Entitlement.id == ent.id, Entitlement.state == "reserved")
                         .values(state="settled").execution_options(synchronize_session=False)).rowcount
    if not changed:
        return
    if ent.kind == "free":
        lg = ledger(db, ent.user_id, ent.biz_date)
        lg.free_reserved = max(0, lg.free_reserved - 1)
        lg.free_used += 1
    else:
        order = db.get(PaymentOrder, ent.payment_order_id) if ent.payment_order_id else None
        if order:
            order.state = "USED"
    ent.state = "settled"
    _event(db, ent.user_id, ent.id, "settled", reason)
    lg_today = ledger(db, ent.user_id)
    lg_today.consecutive_failures = 0


def release(db: Session, ent: Entitlement, reason: str) -> None:
    """失败或放弃：免费额度退回；付费权益恢复为可用（用户可申请原路退款）。"""
    lock_write(db, ent.user_id)
    changed = db.execute(update(Entitlement).where(Entitlement.id == ent.id, Entitlement.state == "reserved")
                         .values(state="released" if ent.kind == "free" else "available")
                         .execution_options(synchronize_session=False)).rowcount
    if not changed:
        return
    if ent.kind == "free":
        lg = ledger(db, ent.user_id, ent.biz_date)
        lg.free_reserved = max(0, lg.free_reserved - 1)
        ent.state = "released"
    else:
        ent.state = "available"
        ent.ref_type = ent.ref_id = None
    _event(db, ent.user_id, ent.id, "released", reason)


def restore_after_settled(db: Session, ent: Entitlement, reason: str) -> None:
    """已核销后因平台责任（申诉成立/供应商拒收）需补偿：免费额度若已跨日，补 1 次付费权益（不可提现）。"""
    lock_write(db, ent.user_id)
    changed = db.execute(update(Entitlement).where(Entitlement.id == ent.id, Entitlement.state == "settled")
                         .values(state="released" if ent.kind == "free" else "available")
                         .execution_options(synchronize_session=False)).rowcount
    if not changed:
        return
    if ent.kind == "free":
        if ent.biz_date == biz_date():
            lg = ledger(db, ent.user_id)
            lg.free_used = max(0, lg.free_used - 1)
            ent.state = "released"
        else:
            ent.state = "released"
            db.add(Entitlement(user_id=ent.user_id, kind="paid", biz_date=biz_date(), state="available"))
    else:
        ent.state = "available"
    _event(db, ent.user_id, ent.id, "restored", reason)


def record_failure(db: Session, user_id: str, cost_fen: int, counts_attempt: bool = True) -> None:
    lg = ledger(db, user_id)
    if counts_attempt:
        lg.failed_attempts += 1
        lg.consecutive_failures += 1
    lg.failed_cost_fen += cost_fen


def grant_paid(db: Session, order: PaymentOrder) -> Entitlement:
    ent = Entitlement(user_id=order.user_id, kind="paid", biz_date=biz_date(), state="available", payment_order_id=order.id)
    db.add(ent)
    db.flush()
    _event(db, order.user_id, ent.id, "paid_granted", order.out_trade_no)
    order.state = "ENTITLEMENT_GRANTED"
    return ent
