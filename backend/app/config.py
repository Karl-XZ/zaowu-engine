"""全局配置。所有第三方密钥留空时，对应能力自动进入模拟模式（MOCK），流程可完整跑通。"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    # ---- 基础 ----
    app_name: str = "造物引擎"
    secret_key: str = "change-me-in-production"
    database_url: str = f"sqlite:///{ROOT / 'backend' / 'data' / 'zaowu.db'}"
    storage_dir: str = str(ROOT / "backend" / "data" / "files")
    public_base_url: str = "http://localhost:8010"
    frontend_origin: str = "http://localhost:5173"
    generation_workers: int = 2
    timezone: str = "Asia/Shanghai"

    # ---- 计次与价格（PRD §5）----
    daily_free_quota: int = 3
    paid_price_fen: int = 500
    design_turns_limit: int = 10
    daily_failed_attempts_limit: int = 5
    daily_failed_cost_limit_fen: int = 200
    consecutive_failure_limit: int = 3
    daily_abandoned_sessions_limit: int = 3
    session_expire_hours: int = 24
    daily_cad_rebuild_limit: int = 30
    appeal_window_hours: int = 24
    supplier_rejection_window_days: int = 30
    platform_daily_free_budget_fen: int = 20000  # 平台每日免费总预算（熔断）

    # ---- 成本估算（未知时不得视为 0；以下为占位估计，接入真实账单后修改）----
    cost_concept_image_fen: int = 10
    cost_lux3d_fen: int = 100
    session_budget_fen: int = 350  # 首图 + 10 次调整 + 1 次转 3D + 修复预留

    # ---- 效果图生成（供应商待定）----
    image_provider: str = ""          # 例如 aholo / openai / custom，留空 = MOCK
    image_api_base: str = ""
    image_api_key: str = ""

    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    deepseek_cad_model: str = "deepseek-flash"
    cost_semantic_fen: int = 2
    cost_cad_ai_fen: int = 5
    cad_ai_job_budget_fen: int = 30
    cad_ai_max_attempts: int = 3
    daily_cad_ai_plan_limit: int = 50
    cad_script_timeout_s: int = 60

    # ---- Aholo Lux3D（中国区/国际区 Key 不互通）----
    aholo_region: str = "cn"
    aholo_api_base: str = ""
    aholo_api_key: str = ""
    aholo_model_version: str = "G1"
    aholo_quote_enabled: bool = False
    aholo_max_call_credits: int = 64

    # ---- 支付宝 Vibe Pay ----
    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""
    alipay_gateway: str = ""
    alipay_notify_url: str = ""

    # ---- 嘉立创 ----
    jlc_api_base: str = ""
    jlc_app_key: str = ""
    jlc_app_secret: str = ""
    jlc_upload_url: str = "https://www.jlc-3dp.cn/"

    # ---- 切片器（OrcaSlicer / PrusaSlicer CLI 路径）----
    slicer_cli_path: str = ""

    # ---- 管理员 ----
    admin_emails: str = "admin@zaowu.local"

    @property
    def image_mock(self) -> bool:
        return not (self.image_provider and self.image_api_key)

    @property
    def aholo_mock(self) -> bool:
        return not (self.aholo_api_base and self.aholo_api_key)

    @property
    def alipay_mock(self) -> bool:
        return not (self.alipay_app_id and self.alipay_private_key)

    @property
    def jlc_mock(self) -> bool:
        return not (self.jlc_api_base and self.jlc_app_key)


settings = Settings()
Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True) if settings.database_url.startswith("sqlite") else None
