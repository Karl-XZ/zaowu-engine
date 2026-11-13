"""核心数据实体（PRD §9.1）。流水类表只追加不修改。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(64), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    privacy_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QuotaLedger(Base):
    """每用户每业务日一行；所有增减在事务中完成。"""
    __tablename__ = "quota_ledgers"
    __table_args__ = (UniqueConstraint("user_id", "biz_date"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    biz_date: Mapped[str] = mapped_column(String(10))
    free_used: Mapped[int] = mapped_column(Integer, default=0)
    free_reserved: Mapped[int] = mapped_column(Integer, default=0)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    failed_cost_fen: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    abandoned_sessions: Mapped[int] = mapped_column(Integer, default=0)
    cad_rebuilds: Mapped[int] = mapped_column(Integer, default=0)


class Entitlement(Base):
    """一次生成权益：免费额度预留或 5 元付费权益。"""
    __tablename__ = "entitlements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # free | paid
    biz_date: Mapped[str] = mapped_column(String(10))
    state: Mapped[str] = mapped_column(String(16), default="available")  # available|reserved|settled|released|refunded
    payment_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class EntitlementEvent(Base):
    __tablename__ = "entitlement_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    entitlement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    type: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DesignSpec(Base):
    __tablename__ = "design_specs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    engine: Mapped[str] = mapped_column(String(8))  # creative | cad
    category: Mapped[str] = mapped_column(String(32))
    material_id: Mapped[str] = mapped_column(String(32))
    material_profile_version: Mapped[str] = mapped_column(String(32))
    size_mm: Mapped[float] = mapped_column()
    spec: Mapped[dict] = mapped_column(JSON, default=dict)
    hard_checklist: Mapped[list] = mapped_column(JSON, default=list)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list)
    template_version: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DesignSession(Base):
    __tablename__ = "design_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    design_spec_id: Mapped[str] = mapped_column(ForeignKey("design_specs.id"))
    title: Mapped[str] = mapped_column(String(128), default="")
    turns_used: Mapped[int] = mapped_column(Integer, default=0)
    turns_limit: Mapped[int] = mapped_column(Integer, default=10)
    state: Mapped[str] = mapped_column(String(16), default="opened")  # opened|concept_ready|adjusting|confirmed|abandoned|expired
    entitlement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=-1)
    confirmed_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_fen: Mapped[int] = mapped_column(Integer, default=0)
    spent_fen: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[list] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConceptImage(Base):
    __tablename__ = "concept_images"
    __table_args__ = (UniqueConstraint("session_id", "version"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("design_sessions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instruction: Mapped[str] = mapped_column(Text, default="")
    dimension: Mapped[str] = mapped_column(String(32), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_template_version: Mapped[str] = mapped_column(String(32), default="")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    cost_fen: Mapped[int] = mapped_column(Integer, default=0)
    qc_result: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    file_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GenerationTask(Base):
    __tablename__ = "generation_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    engine: Mapped[str] = mapped_column(String(8))  # creative | cad
    design_spec_id: Mapped[str] = mapped_column(String(32))
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    concept_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entitlement_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="")
    provider_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="CREATED")
    stage_log: Mapped[list] = mapped_column(JSON, default=list)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_actual_fen: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    model_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    task_id: Mapped[str] = mapped_column(String(32))
    parent_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    engine: Mapped[str] = mapped_column(String(8))
    files: Mapped[dict] = mapped_column(JSON, default=dict)  # fmt -> relative path
    dimension_mm: Mapped[list] = mapped_column(JSON, default=list)
    material_id: Mapped[str] = mapped_column(String(32))
    material_profile_version: Mapped[str] = mapped_column(String(32))
    validation_state: Mapped[str] = mapped_column(String(16), default="pending")  # pending|passed|failed
    file_hash: Mapped[str] = mapped_column(String(64), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    production_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ManufacturingCheck(Base):
    __tablename__ = "manufacturing_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[str] = mapped_column(String(32), index=True)
    material_profile_version: Mapped[str] = mapped_column(String(32))
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_state: Mapped[str] = mapped_column(String(16))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SliceReport(Base):
    __tablename__ = "slice_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[str] = mapped_column(String(32), index=True)
    slicer: Mapped[str] = mapped_column(String(32))
    profile_version: Mapped[str] = mapped_column(String(32))
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    out_trade_no: Mapped[str] = mapped_column(String(64), unique=True)
    external_trade_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_fen: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(32), default="generation")
    state: Mapped[str] = mapped_column(String(24), default="WAITING_PAY")
    notify_log: Mapped[list] = mapped_column(JSON, default=list)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProviderCostLedger(Base):
    """每笔真实（或估计）供应商支出。不能被退款或额度释放冲销。"""
    __tablename__ = "provider_cost_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    ref_type: Mapped[str] = mapped_column(String(16))
    ref_id: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(String(64))
    provider_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_estimated_fen: Mapped[int] = mapped_column(Integer, default=0)
    cost_actual_fen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_free_tier: Mapped[bool] = mapped_column(Boolean, default=True)
    outcome: Mapped[str] = mapped_column(String(16), default="pending")  # pending|success|failed
    bill_status: Mapped[str] = mapped_column(String(16), default="estimated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RequirementClaim(Base):
    __tablename__ = "requirement_claims"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    model_version_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(32))
    checklist_items: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    auto_result: Mapped[str] = mapped_column(String(32), default="")
    decision: Mapped[str] = mapped_column(String(32), default="pending")  # pending|platform|user
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PrintOrder(Base):
    __tablename__ = "print_orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    model_version_id: Mapped[str] = mapped_column(String(32))
    file_hash: Mapped[str] = mapped_column(String(64))
    material_id: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    mode: Mapped[str] = mapped_column(String(8), default="B")  # A=API, B=手动跳转
    external_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    quote: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
