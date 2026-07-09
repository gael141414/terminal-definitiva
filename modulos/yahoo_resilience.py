from __future__ import annotations

import contextlib
import io
import logging
from typing import Any

import pandas as pd

YAHOO_LOGGER = logging.getLogger("valuequant.yahoo")

YAHOO_RATE_LIMIT_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "query2.finance.yahoo",
    "quotesummary",
)


def is_yahoo_rate_limit_error(exc: BaseException | str) -> bool:
    """Detecta rate limits de Yahoo/yfinance sin depender del tipo exacto."""

    text = f"{type(exc).__name__}: {exc}".lower() if isinstance(exc, BaseException) else str(exc).lower()
    return any(marker in text for marker in YAHOO_RATE_LIMIT_MARKERS)


def _captured_provider_output(stdout: io.StringIO, stderr: io.StringIO) -> str:
    return "\n".join(part for part in (stdout.getvalue(), stderr.getvalue()) if part)


def _normalize_dataframe(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value
    if isinstance(value, pd.Series):
        return value.to_frame()
    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


def safe_yfinance_download(yf_module: Any, *args: Any, context: str = "yfinance", **kwargs: Any) -> pd.DataFrame:
    """Ejecuta yf.download con fallback estable ante errores temporales.

    Captura stdout/stderr porque yfinance puede imprimir mensajes 429 aunque no lance
    una excepción estructurada. Ante rate limit devuelve DataFrame vacío.
    """

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            data = yf_module.download(*args, **kwargs)
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo rate limit en %s; se devuelve DataFrame vacío.", context)
            return pd.DataFrame()
        YAHOO_LOGGER.warning("Yahoo download no disponible en %s: %s: %s", context, type(exc).__name__, exc)
        return pd.DataFrame()

    captured = _captured_provider_output(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        YAHOO_LOGGER.warning("Yahoo rate limit capturado en %s; se devuelve DataFrame vacío.", context)
        return pd.DataFrame()

    return _normalize_dataframe(data)


def safe_yfinance_info(yf_module: Any, ticker: str, *, context: str = "yfinance_info") -> dict[str, Any]:
    """Obtiene yf.Ticker(ticker).info con fallback estable ante quoteSummary/429."""

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            info = yf_module.Ticker(str(ticker).strip()).info
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo info rate limit para %s en %s; se devuelve dict vacío.", ticker, context)
            return {}
        YAHOO_LOGGER.warning("Yahoo info no disponible para %s en %s: %s: %s", ticker, context, type(exc).__name__, exc)
        return {}

    captured = _captured_provider_output(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        YAHOO_LOGGER.warning("Yahoo info rate limit capturado para %s en %s; se devuelve dict vacío.", ticker, context)
        return {}

    return info if isinstance(info, dict) else {}
