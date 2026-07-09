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
    "rate limit",
    "ratelimit",
    "query2.finance.yahoo",
    "quotesummary",
)


def is_yahoo_rate_limit_error(exc: BaseException | str) -> bool:
    """Detecta errores temporales de Yahoo/yfinance sin depender del tipo exacto."""

    message = str(exc).lower()
    return any(marker in message for marker in YAHOO_RATE_LIMIT_MARKERS)


def _captured_provider_output(stdout: io.StringIO, stderr: io.StringIO) -> str:
    return "\n".join(part for part in (stdout.getvalue(), stderr.getvalue()) if part)


def safe_yfinance_download(yf_module: Any, *args: Any, context: str = "yfinance", **kwargs: Any) -> pd.DataFrame:
    """Ejecuta yf.download con fallback estable ante rate limits o errores temporales.

    Devuelve un DataFrame vacío en lugar de propagar excepciones del proveedor externo.
    Captura stdout/stderr porque yfinance puede imprimir errores 429 sin lanzarlos de
    forma uniforme.
    """

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            data = yf_module.download(*args, **kwargs)
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo rate limit en %s; se devuelve DataFrame vacío.", context)
        else:
            logger.warning("Yahoo no disponible en %s; se devuelve DataFrame vacío: %s", context, exc)
        return pd.DataFrame()

    captured = _captured_provider_output(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        logger.warning("Yahoo rate limit capturado en salida de %s; se devuelve DataFrame vacío.", context)
        return pd.DataFrame()

    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.Series):
        return data.to_frame()
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def safe_yfinance_info(yf_module: Any, ticker: str, *, context: str = "yfinance_info") -> dict[str, Any]:
    """Obtiene yf.Ticker(...).info con fallback estable ante 429/quoteSummary."""

    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            info = yf_module.Ticker(ticker).info
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            logger.warning("Yahoo info rate limit para %s en %s; se devuelve dict vacío.", ticker, context)
        else:
            logger.warning("Yahoo info no disponible para %s en %s; se devuelve dict vacío: %s", ticker, context, exc)
        return {}

    captured = _captured_provider_output(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        logger.warning("Yahoo info rate limit capturado para %s en %s; se devuelve dict vacío.", ticker, context)
        return {}

    return info if isinstance(info, dict) else {}
