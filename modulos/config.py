from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - python-dotenv puede no estar instalado en algunos entornos
    load_dotenv = None

try:
    import streamlit as st
except Exception:  # pragma: no cover - permite importar fuera de Streamlit
    st = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = PROJECT_ROOT / ".env"

if load_dotenv is not None:
    # override=False mantiene prioridad para variables ya exportadas por el sistema/hosting.
    load_dotenv(DOTENV_PATH, override=False)


PLACEHOLDER_VALUES = {
    "",
    "your_fmp_api_key_here",
    "your_gemini_api_key_here",
    "your_google_api_key_here",
    "your_telegram_bot_token_here",
    "your_telegram_chat_id_here",
    "changeme",
    "change_me",
    "none",
    "null",
}


def _is_missing_secret(value: Any) -> bool:
    """Detecta valores vacíos o placeholders de archivos example/secrets."""
    if value is None:
        return True
    normalized = str(value).strip()
    if normalized.lower() in PLACEHOLDER_VALUES:
        return True
    if normalized.lower().startswith("your_"):
        return True
    return False


def get_secret(name: str, default: Any = None) -> Any:
    """Lee configuración desde Streamlit secrets, variables de entorno o .env local.

    Orden de prioridad efectivo:
    1. st.secrets[name], cuando Streamlit está disponible y no contiene un placeholder.
    2. os.environ[name]. Aquí también entran variables cargadas desde .env.
    3. default.
    """
    if st is not None:
        try:
            value = st.secrets.get(name)  # type: ignore[union-attr]
            if not _is_missing_secret(value):
                return value
        except Exception:
            pass

    value = os.getenv(name)
    if not _is_missing_secret(value):
        return value
    return default


def get_bool_secret(name: str, default: bool = False) -> bool:
    value = str(get_secret(name, str(default))).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    fmp_api_key: str
    gemini_api_key: str
    google_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    debug: bool = False


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig(
        app_env=str(get_secret("APP_ENV", "local")),
        fmp_api_key=str(get_secret("FMP_API_KEY", "")),
        gemini_api_key=str(get_secret("GEMINI_API_KEY", "")),
        google_api_key=str(get_secret("GOOGLE_API_KEY", "")),
        telegram_bot_token=str(get_secret("TELEGRAM_BOT_TOKEN", "")),
        telegram_chat_id=str(get_secret("TELEGRAM_CHAT_ID", "")),
        debug=get_bool_secret("VALUEQUANT_DEBUG", get_bool_secret("DEBUG", False)),
    )


CONFIG = get_config()
