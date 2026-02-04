"""Configuration management using Pydantic"""
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class AppMode(str, Enum):
    """Application execution mode"""
    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderType(str, Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SLM = "SL-M"


class TransactionType(str, Enum):
    """Transaction types"""
    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    """Product types"""
    MIS = "MIS"  # Intraday
    CNC = "CNC"  # Delivery
    NRML = "NRML"  # Normal (for F&O)


class Settings(BaseSettings):
    """Application settings from environment"""

    # Kite Connect
    kite_api_key: str = Field(alias="KITE_API_KEY")
    kite_api_secret: str = Field(alias="KITE_API_SECRET")
    kite_access_token: str = Field(alias="KITE_ACCESS_TOKEN")
    kite_user_id: str = Field(alias="KITE_USER_ID")

    # Application
    app_mode: AppMode = Field(default=AppMode.PAPER, alias="APP_MODE")
    app_timezone: str = Field(default="Asia/Kolkata", alias="APP_TIMEZONE")

    # SEBI/NSE Compliance (Feb 2025)
    compliance_sebi_2025: bool = Field(default=False, alias="COMPLIANCE_SEBI_2025")
    exchange_algo_id: Optional[str] = Field(default=None, alias="EXCHANGE_ALGO_ID")
    whitelisted_clients: str = Field(default="", alias="WHITELISTED_CLIENTS")  # Comma-separated client IDs
    oauth_required: bool = Field(default=True, alias="OAUTH_REQUIRED")
    two_fa_required: bool = Field(default=True, alias="TWO_FA_REQUIRED")
    require_static_ip: bool = Field(default=False, alias="REQUIRE_STATIC_IP")
    expected_egress_ip: Optional[str] = Field(default=None, alias="EXPECTED_EGRESS_IP")
    force_daily_logout_iso: str = Field(default="03:30", alias="FORCE_DAILY_LOGOUT_ISO")  # IST time
    audit_retention_years: int = Field(default=5, alias="AUDIT_RETENTION_YEARS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database
    database_url: str = Field(alias="DATABASE_URL")
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")

    # Redis
    redis_url: str = Field(alias="REDIS_URL")
    redis_max_connections: int = Field(default=50, alias="REDIS_MAX_CONNECTIONS")

    # API Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_workers: int = Field(default=4, alias="API_WORKERS")
    api_secret_key: str = Field(alias="API_SECRET_KEY")
    cors_origins: List[str] = Field(default=["*"], alias="CORS_ORIGINS")

    # WebSocket
    ws_ping_interval: int = Field(default=30, alias="WS_PING_INTERVAL")
    ws_reconnect_delay: int = Field(default=5, alias="WS_RECONNECT_DELAY")
    ws_max_reconnect_attempts: int = Field(default=10, alias="WS_MAX_RECONNECT_ATTEMPTS")

    # Risk Management
    risk_per_trade_pct: float = Field(default=0.5, alias="RISK_PER_TRADE_PCT")
    risk_max_portfolio_heat_pct: float = Field(default=2.0, alias="RISK_MAX_PORTFOLIO_HEAT_PCT")
    risk_daily_loss_stop_pct: float = Field(default=2.5, alias="RISK_DAILY_LOSS_STOP_PCT")

    # Market Hours
    market_open_time: str = Field(default="09:15", alias="MARKET_OPEN_TIME")
    market_close_time: str = Field(default="15:30", alias="MARKET_CLOSE_TIME")
    eod_squareoff_time: str = Field(default="15:25", alias="EOD_SQUAREOFF_TIME")

    # NSE Holidays
    nse_holiday_segment: str = Field(default="FO", alias="NSE_HOLIDAY_SEGMENT")
    nse_holiday_cache_path: str = Field(default="packages/core/data/nse_holidays_trading.json", alias="NSE_HOLIDAY_CACHE_PATH")
    nse_holiday_refresh_days: int = Field(default=30, alias="NSE_HOLIDAY_REFRESH_DAYS")
    nse_holiday_allow_network: bool = Field(default=True, alias="NSE_HOLIDAY_ALLOW_NETWORK")

    # Alerts
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    slack_webhook_url: Optional[str] = Field(default=None, alias="SLACK_WEBHOOK_URL")

    # Monitoring
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, alias="METRICS_PORT")

    # Development
    debug: bool = Field(default=False, alias="DEBUG")
    reload: bool = Field(default=False, alias="RELOAD")

    # TOPS Compliance (from env)
    tops_cap_per_sec: int = Field(default=8, alias="TOPS_CAP_PER_SEC")

    class Config:
        env_file = ".env"
        case_sensitive = False


class RiskConfig:
    """Risk management configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.per_trade_risk_pct = config.get("per_trade_risk_pct", 0.5)
        self.max_portfolio_heat_pct = config.get("max_portfolio_heat_pct", 2.0)
        self.daily_loss_stop_pct = config.get("daily_loss_stop_pct", 2.5)
        self.slippage_bps = config.get("slippage_bps", 5)
        self.fees_per_order = config.get("fees_per_order", 20)
        self.fees_per_option_leg = config.get("fees_per_option_leg", 2)
        self.max_position_size_multiplier = config.get("max_position_size_multiplier", 3)


class UniverseConfig:
    """Universe configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.indices = config.get("indices", ["NIFTY", "BANKNIFTY"])
        self.fo_stocks_liquidity_rank_top_n = config.get("fo_stocks_liquidity_rank_top_n", 50)
        self.exclude_fo_ban = config.get("exclude_fo_ban", True)
        self.exclude_illiquid_threshold_turnover = config.get("exclude_illiquid_threshold_turnover", 10000000)
        self.sync_time = config.get("sync_time", "08:30")


class OptionsFiltersConfig:
    """Options filtering configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.max_spread_mid_pct = config.get("max_spread_mid_pct", 0.5)
        self.min_oi = config.get("min_oi", 20000)
        self.min_last_traded_volume = config.get("min_last_traded_volume", 100)
        self.strikes_from_atm = config.get("strikes_from_atm", 5)
        self.prefer_weekly = config.get("prefer_weekly", True)
        self.max_dte = config.get("max_dte", 7)
        self.iv_percentile_min = config.get("iv_percentile_min", 20)
        self.iv_percentile_max = config.get("iv_percentile_max", 80)


class StrategyConfig:
    """Individual strategy configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.name = config["name"]
        self.enabled = config.get("enabled", True)
        self.priority = config.get("priority", 1)
        self.params = config.get("params", {})


class RankingConfig:
    """Ranking engine configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.weights = config.get("weights", {
            "momentum": 0.25,
            "trend": 0.25,
            "liquidity": 0.20,
            "regime": 0.15,
            "rr": 0.15
        })
        self.penalties = config.get("penalties", {
            "illiquid_mult": 0.5,
            "news_event_mult": 0.7,
            "far_from_vwap_mult": 0.8
        })
        self.top_n = config.get("top_n", 5)


class ExitsConfig:
    """Exit management configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.hard_stop_atr_mult = config.get("hard_stop_atr_mult", 2.0)
        self.trail_enabled = config.get("trail_enabled", True)
        self.trail_atr_mult = config.get("trail_atr_mult", 1.2)
        self.trail_step_pct = config.get("trail_step_pct", 0.5)
        self.tp1_rr = config.get("tp1_rr", 1.2)
        self.tp1_partial_pct = config.get("tp1_partial_pct", 50)
        self.tp2_rr = config.get("tp2_rr", 2.0)
        self.tp2_partial_pct = config.get("tp2_partial_pct", 100)
        self.move_to_be_after_tp1 = config.get("move_to_be_after_tp1", True)
        self.time_stop_enabled = config.get("time_stop_enabled", True)
        self.time_stop_min = config.get("time_stop_min", 20)
        self.vol_stop_enabled = config.get("vol_stop_enabled", True)
        self.vol_spike_mult = config.get("vol_spike_mult", 2.0)
        self.mae_stop_enabled = config.get("mae_stop_enabled", True)
        self.mae_stop_pct = config.get("mae_stop_pct", 1.5)


class MarketConfig:
    """Market hours and EOD configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.open_time = config.get("open_time", "09:15")
        self.close_time = config.get("close_time", "15:30")
        self.eod_squareoff_time = config.get("eod_squareoff_time", "15:25")
        self.eod_squareoff_enabled = config.get("eod_squareoff_enabled", True)
        self.premarket_sync_time = config.get("premarket_sync_time", "08:30")
        self.event_aware = config.get("event_aware", True)
        self.event_stop_mult = config.get("event_stop_mult", 1.5)


class ExecutionConfig:
    """Order execution configuration"""
    def __init__(self, config: Dict[str, Any]):
        self.default_order_type = config.get("default_order_type", "LIMIT")
        self.limit_chase_ticks = config.get("limit_chase_ticks", 2)
        self.limit_timeout_sec = config.get("limit_timeout_sec", 5)
        self.ioc_for_exits = config.get("ioc_for_exits", True)
        self.max_order_retries = config.get("max_order_retries", 3)
        self.retry_backoff_ms = config.get("retry_backoff_ms", 500)
        self.exchange_algo_id = config.get("exchange_algo_id", None)
        self.tops_cap_per_sec = config.get("tops_cap_per_sec", 8)


class AppConfig:
    """Main application configuration loaded from YAML"""

    def __init__(self, config_path: str = "configs/app.yaml"):
        self.config_path = Path(config_path)
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        self.mode = AppMode(config.get("mode", "PAPER"))
        self.timezone = config.get("timezone", "Asia/Kolkata")

        self.risk = RiskConfig(config.get("risk", {}))
        self.universe = UniverseConfig(config.get("universe", {}))
        self.options_filters = OptionsFiltersConfig(config.get("options_filters", {}))

        self.strategies = [
            StrategyConfig(s) for s in config.get("strategies", [])
        ]

        self.ranking = RankingConfig(config.get("ranking", {}))
        self.exits = ExitsConfig(config.get("exits", {}))
        self.market = MarketConfig(config.get("market", {}))
        self.execution = ExecutionConfig(config.get("execution", {}))

        self.alerts = config.get("alerts", {})
        self.websocket = config.get("websocket", {})
        self.logging = config.get("logging", {})
        self.monitoring = config.get("monitoring", {})

    def get_strategy_by_name(self, name: str) -> Optional[StrategyConfig]:
        """Get strategy configuration by name"""
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None

    def get_enabled_strategies(self) -> List[StrategyConfig]:
        """Get all enabled strategies"""
        return [s for s in self.strategies if s.enabled]

    def reload(self):
        """Reload configuration from file"""
        self._load_config()


# Global configuration instances
settings = Settings()
app_config = AppConfig()
