from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # Credenciales Exchange / Broker
    API_KEY: str
    API_SECRET: str
    USE_SANDBOX: bool = True
    
    # Telegram Configuration
    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: int
    TELEGRAM_API_ID: int  # Para Telethon (Scraper)
    TELEGRAM_API_HASH: str # Para Telethon (Scraper)
    TARGET_SIGNAL_CHANNELS: List[str] = []
    
    # Risk Management & Protection
    MAX_DRAWDOWN_LIMIT: float = 0.15      # Bloqueo total si la cuenta pierde un 15%
    PDT_PROTECTION: bool = True           # Regla de Pattern Day Trader (Max 3 intraday)
    GLOBAL_STOP_LOSS_PCT: float = 0.02    # Riesgo máximo de pérdida por operación (2%)
    MAX_RISK_PER_TRADE: float = 0.01      # Fracción del portfolio arriesgado por operación
    
    # Infrastructure Mitigation
    MAX_RPM_FINNHUB: int = 55
    GITHUB_ACTIONS_DRIFT_TOLERANCE_MIN: int = 5
    ORACLE_CPU_THRESHOLD_BURN: bool = True
    
    # Webhook
    WEBHOOK_SECRET_TOKEN: str = "default_secure_token"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()