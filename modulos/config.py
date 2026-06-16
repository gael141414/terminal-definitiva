from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

try:
    import streamlit as st
except Exception:  # pragma: no cover - permite importar fuera de Streamlit
    st = None


def get_secret(name: str, default: Any = None) -> Any:
    """Lee configuración desde Streamlit secrets o variables de entorno.

    Orden de prioridad:
    1. st.secrets[name], cuando Streamlit está disponible.
    2. os.environ[name].
    3. default.
    """
    if st is not None:
        try:
            value = st.secrets.get(name)  # type: ignore[union-attr]
            if value not in (None, ""):
                return value
        except Exception:
            pass

    value = os.getenv(name)
    if value not in (None, ""):
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
        debug=get_bool_secret("DEBUG", False),
    )


CONFIG = get_config()
