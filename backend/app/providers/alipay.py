"""支付宝 Vibe Pay 适配器（PRD §5.2、§8.4）。

规则：金额以服务端为准；异步通知验签后再主动查单；同一通知/订单只入账一次。
MOCK 模式：返回平台内的模拟收银台地址，由 /pay/mock/confirm 触发与真实通知相同的入账逻辑。
"""
from __future__ import annotations

import base64
import urllib.parse
from datetime import datetime

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from ..config import settings


def _sign(params: dict) -> str:
    content = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v not in (None, "") and k != "sign")
    key = serialization.load_pem_private_key(settings.alipay_private_key.encode(), password=None)
    return base64.b64encode(key.sign(content.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()


def create_payment(out_trade_no: str, amount_fen: int, subject: str) -> str:
    """返回用户跳转/扫码的支付地址。"""
    if settings.alipay_mock:
        return f"{settings.frontend_origin}/pay/mock?trade={out_trade_no}"
    # TODO(接入)：按 Vibe Pay / 网页支付文档确认 method 与 biz_content 字段
    params = {
        "app_id": settings.alipay_app_id, "method": "alipay.trade.page.pay", "charset": "utf-8",
        "sign_type": "RSA2", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "version": "1.0",
        "notify_url": settings.alipay_notify_url,
        "return_url": f"{settings.frontend_origin}/pay/return",
        "biz_content": (
            '{"out_trade_no":"%s","total_amount":"%.2f","subject":"%s","product_code":"FAST_INSTANT_TRADE_PAY"}'
            % (out_trade_no, amount_fen / 100, subject)
        ),
    }
    params["sign"] = _sign(params)
    return f"{settings.alipay_gateway}?{urllib.parse.urlencode(params)}"


def verify_notify(params: dict) -> bool:
    if settings.alipay_mock:
        return params.get("mock") == "1"
    sign = params.get("sign", "")
    content = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k not in ("sign", "sign_type") and v != "")
    try:
        pub = serialization.load_pem_public_key(settings.alipay_public_key.encode())
        pub.verify(base64.b64decode(sign), content.encode(), padding.PKCS1v15(), hashes.SHA256())
        return True
    except Exception:
        return False


def query_paid(out_trade_no: str) -> tuple[bool, str | None, int | None]:
    """主动查单：返回 (是否已支付, 支付宝交易号, 实付金额分)。"""
    if settings.alipay_mock:
        return True, f"MOCK{out_trade_no[-10:]}", None
    # TODO(接入)：alipay.trade.query
    params = {
        "app_id": settings.alipay_app_id, "method": "alipay.trade.query", "charset": "utf-8", "sign_type": "RSA2",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "version": "1.0",
        "biz_content": '{"out_trade_no":"%s"}' % out_trade_no,
    }
    params["sign"] = _sign(params)
    with httpx.Client(timeout=15) as c:
        j = c.get(settings.alipay_gateway, params=params).json().get("alipay_trade_query_response", {})
    paid = j.get("trade_status") in ("TRADE_SUCCESS", "TRADE_FINISHED")
    amount = int(round(float(j.get("total_amount", 0)) * 100)) if j.get("total_amount") else None
    return paid, j.get("trade_no"), amount


def refund(out_trade_no: str, amount_fen: int, reason: str) -> bool:
    if settings.alipay_mock:
        return True
    # TODO(接入)：alipay.trade.refund，使用 out_request_no 保证幂等
    return False
