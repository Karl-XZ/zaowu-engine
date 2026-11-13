"""Cost Governor（PRD §3.6）：所有可能扣费的调用先经批准、预留、记账。成本未知时不得视为 0。"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import ProviderCostLedger


class BudgetExceeded(Exception):
    pass


def approve(remaining_budget_fen: int, estimate_fen: int | None) -> None:
    if estimate_fen is None:
        raise BudgetExceeded("供应商单价未知，禁止调用")
    if estimate_fen > remaining_budget_fen:
        raise BudgetExceeded(f"预计 {estimate_fen} 分超出剩余预算 {remaining_budget_fen} 分")


def open_call(db: Session, *, user_id: str, ref_type: str, ref_id: str, provider: str, endpoint: str,
              estimate_fen: int, free_tier: bool) -> ProviderCostLedger:
    row = ProviderCostLedger(user_id=user_id, ref_type=ref_type, ref_id=ref_id, provider=provider, endpoint=endpoint,
                             cost_estimated_fen=estimate_fen, is_free_tier=free_tier)
    db.add(row)
    db.flush()
    # A supplier may accept the request even if our process dies or its reply is lost.
    # Persist the reservation BEFORE crossing that network boundary.
    db.commit()
    return row


def close_call(row: ProviderCostLedger, outcome: str, actual_fen: int | None = None, provider_task_id: str | None = None) -> None:
    row.outcome = outcome
    if actual_fen is not None:
        row.cost_actual_fen = actual_fen
        row.bill_status = "actual"
    if provider_task_id:
        row.provider_task_id = provider_task_id


def http_budget_error(e: BudgetExceeded) -> HTTPException:
    return HTTPException(409, f"本次请求超出成本上限，未发起付费调用：{e}")
