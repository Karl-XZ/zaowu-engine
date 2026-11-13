"""嘉立创适配器（PRD §6）。

模式 A：API 获批后，后台报价、经用户确认后下单、查询进度物流（仅真实联调通过后显示“一键下单”）。
模式 B（默认）：导出标准生产文件，跳转嘉立创官网上传下单。
"""
from __future__ import annotations

import httpx

from ..config import settings


def mode() -> str:
    return "B" if settings.jlc_mock else "A"


def quote(file_bytes: bytes, filename: str, material_id: str, qty: int) -> dict | None:
    if settings.jlc_mock:
        return None
    # TODO(接入)：按开放平台开发指南实现签名与报价接口；HTTP 200 之外须校验业务结果码
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{settings.jlc_api_base.rstrip('/')}/3dp/quote",
                   headers={"X-App-Key": settings.jlc_app_key},
                   data={"material": material_id, "quantity": qty},
                   files={"file": (filename, file_bytes)})
        r.raise_for_status()
        return r.json()


def create_order(quote_id: str, recipient: dict) -> str | None:
    if settings.jlc_mock:
        return None
    # TODO(接入)：创建/关联订单，仅在用户确认报价、收件信息单独授权后调用
    return None


def manual_upload_url() -> str:
    return settings.jlc_upload_url
