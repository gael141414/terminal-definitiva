from __future__ import annotations

import contextlib
import io
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

YAHOO_RATE_LIMIT_MARKERS = (
    "429",
    "too many requests",
    "edge: too many requests",
    "query2.finance.yahoo",
    "finance.yahoo.com",
)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, BaseException):
        parts = [type(value).__name__, str(value)]
        cause = getattr(value, "__cause__", None)
        context = getattr(value, "__context__", None)
        if cause is not None:
            parts.append(str(cause))
        if context is not None:
            parts.append(str(context))
        return " ".join(parts)
    return str(value)


def is_yahoo_rate_limit_error(value: Any) -> bool:
    """Detecta errores temporales de rate limit emitidos por Yahoo/yfinance."""

    text = _as_text(value).lower()
    return any(marker in text for marker in YAHOO_RATE_LIMIT_MARKERS)


def _captured_text(stdout: io.StringIO, stderr: io.StringIO) -> str:
    return "\n".join(part for part in (stdout.getvalue(), stderr.getvalue()) if part)


def _empty_dataframe() -> pd.DataFrame:
    return pd.DataFrame()


def _normalize_download_result(value: Any) -> pd.DataFrame:
    if value is None:
        return _empty_dataframe()
    if isinstance(value, pd.Series):
        return value.to_frame()
    if isinstance(value, pd.DataFrame):
        return value
    return _empty_dataframe()


def safe_yfinance_download(yf_module: Any, *args: Any, context: str = "", **kwargs: Any) -> pd.DataFrame:
    """Ejecuta yf.download capturando ruido y convirtiendo 429 en DataFrame vacío.

    yfinance puede escribir errores HTTP en stdout/stderr sin lanzar una excepción clara.
    Este wrapper evita que un rate limit temporal rompa o ensucie los checks locales.
    """

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = yf_module.download(*args, **kwargs)
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo Finance rate limit%s; devolviendo DataFrame vacío.", f" en {context}" if context else "")
            return _empty_dataframe()
        logger.warning("Yahoo Finance download falló%s: %s", f" en {context}" if context else "", exc)
        return _empty_dataframe()

    captured = _captured_text(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        logger.warning("Yahoo Finance rate limit%s; devolviendo DataFrame vacío.", f" en {context}" if context else "")
        return _empty_dataframe()

    return _normalize_download_result(result)


def safe_yfinance_info(yf_module: Any, ticker: str, *, context: str = "") -> dict[str, Any]:
    """Obtiene yf.Ticker(ticker).info y convierte rate limits en dict vacío."""

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            info = yf_module.Ticker(ticker).info
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo Finance rate limit para %s%s; devolviendo info vacía.", ticker, f" en {context}" if context else "")
            return {}
        logger.warning("Yahoo Finance info falló para %s%s: %s", ticker, f" en {context}" if context else "", exc)
        return {}

    captured = _captured_text(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        logger.warning("Yahoo Finance rate limit para %s%s; devolviendo info vacía.", ticker, f" en {context}" if context else "")
        return {}

    return info if isinstance(info, dict) else {}
