from __future__ import annotations

import contextlib
import io
import logging
from typing import Any, Callable

import pandas as pd
import yfinance as yf

YAHOO_LOGGER = logging.getLogger("valuequant.yahoo")

YAHOO_RATE_LIMIT_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "ratelimit",
    "query2.finance.yahoo",
    "quotesummary",
    "edge: too many requests",
)


def is_yahoo_rate_limit_error(value: BaseException | str | None) -> bool:
    """Detecta rate limits de Yahoo/yfinance sin depender del tipo exacto."""

    if value is None:
        return False
    text = f"{type(value).__name__}: {value}".lower() if isinstance(value, BaseException) else str(value).lower()
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


def safe_yfinance_download(
    yf_module: Any | None = None,
    *args: Any,
    _download_func: Callable[..., Any] | None = None,
    context: str = "yfinance",
    **kwargs: Any,
) -> pd.DataFrame:
    """Ejecuta yf.download con fallback estable ante errores temporales.

    Soporta dos formas:
    - safe_yfinance_download(yf, tickers="AAPL", ...)
    - safe_yfinance_download("AAPL", period="1y", ...)
    """

    if yf_module is None:
        module = yf
        call_args = args
    elif hasattr(yf_module, "download"):
        module = yf_module
        call_args = args
    else:
        module = yf
        call_args = (yf_module, *args)

    download_func = _download_func or module.download
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            data = download_func(*call_args, **kwargs)
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


def safe_yfinance_info(
    yf_module: Any | None,
    ticker: str | None = None,
    *,
    _ticker_factory: Callable[[str], Any] | None = None,
    context: str = "yfinance_info",
) -> dict[str, Any]:
    """Obtiene yf.Ticker(ticker).info con fallback estable ante quoteSummary/429."""

    if ticker is None:
        symbol = str(yf_module).strip()
        module = yf
    else:
        symbol = str(ticker).strip()
        module = yf if yf_module is None else yf_module

    ticker_factory = _ticker_factory or getattr(module, "Ticker", yf.Ticker)
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            info = ticker_factory(symbol).info
    except Exception as exc:
        if is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo info rate limit para %s en %s; se devuelve dict vacío.", symbol, context)
            return {}
        YAHOO_LOGGER.warning("Yahoo info no disponible para %s en %s: %s: %s", symbol, context, type(exc).__name__, exc)
        return {}

    captured = _captured_provider_output(stdout, stderr)
    if is_yahoo_rate_limit_error(captured):
        YAHOO_LOGGER.warning("Yahoo info rate limit capturado para %s en %s; se devuelve dict vacío.", symbol, context)
        return {}

    return info if isinstance(info, dict) else {}
