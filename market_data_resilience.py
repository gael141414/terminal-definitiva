from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

YAHOO_RATE_LIMIT_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "query2.finance.yahoo",
    "quotesummary",
)


def is_yahoo_rate_limit_error(exc: BaseException | str) -> bool:
    """Detecta errores temporales de Yahoo/yfinance sin depender del tipo exacto."""

    message = str(exc).lower()
    return any(marker in message for marker in YAHOO_RATE_LIMIT_MARKERS)


def safe_yfinance_download(*args: Any, _download_func: Callable[..., pd.DataFrame] | None = None, **kwargs: Any) -> pd.DataFrame:
    """Ejecuta yf.download con fallback estable ante rate limits o errores temporales.

    Devuelve un DataFrame vacío en lugar de propagar excepciones de proveedor externo.
    Esto permite que pantallas, backtests y smoke tests degraden de forma controlada.
    """

    download_func = _download_func or yf.download
    try:
        data = download_func(*args, **kwargs)
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo Finance rate limit detectado; se devuelve DataFrame vacío: %s", exc)
        else:
            logger.warning("Yahoo Finance no disponible; se devuelve DataFrame vacío: %s", exc)
        return pd.DataFrame()

    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.Series):
        return data.to_frame()
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def safe_yfinance_info(ticker: str, *, _ticker_factory: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Obtiene yf.Ticker(...).info con fallback estable ante 429/quoteSummary."""

    ticker_factory = _ticker_factory or yf.Ticker
    try:
        info = ticker_factory(ticker).info
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo Finance info rate limit para %s; se devuelve dict vacío: %s", ticker, exc)
        else:
            logger.warning("Yahoo Finance info no disponible para %s; se devuelve dict vacío: %s", ticker, exc)
        return {}

    return info if isinstance(info, dict) else {}
