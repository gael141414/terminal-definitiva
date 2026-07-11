from __future__ import annotations

import contextlib
import io
import logging
import time
from typing import Any, Callable, TypeVar

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

# Estados posibles de una llamada a Yahoo/yfinance protegida por safe_yfinance_fetch.
STATUS_OK = "ok"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_NO_DATA = "no_data"
STATUS_ERROR = "error"

T = TypeVar("T")


def is_yahoo_rate_limit_error(exc: BaseException | str) -> bool:
    """Detecta errores temporales de Yahoo/yfinance sin depender del tipo exacto."""

    message = str(exc).lower()
    return any(marker in message for marker in YAHOO_RATE_LIMIT_MARKERS)


def _captured_provider_output(stdout: io.StringIO, stderr: io.StringIO) -> str:
    return "\n".join(part for part in (stdout.getvalue(), stderr.getvalue()) if part)


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return bool(value.empty)
    if isinstance(value, (dict, list, tuple, str)):
        return len(value) == 0
    return False


def safe_yfinance_fetch(
    getter: Callable[[], T],
    *,
    empty_value: T,
    context: str = "yfinance",
    retries: int = 1,
    backoff_seconds: float = 1.5,
) -> tuple[T, str]:
    """Ejecuta ``getter()`` (cualquier acceso a yfinance: ``.info``, ``.history()``,
    ``.fast_info``, ``.financials``, ``.dividends``, ``.news``, ``.option_chain()``,
    ``.insider_transactions``, etc.) con captura de ruido de stdout/stderr y
    clasificación explícita del resultado.

    Devuelve ``(valor, status)`` donde ``status`` es uno de:
    ``"ok"``, ``"rate_limited"``, ``"no_data"``, ``"error"``.

    Si el primer intento se clasifica como rate limit, reintenta hasta ``retries``
    veces con un backoff corto (``backoff_seconds``) antes de rendirse — hoy no
    existía ningún reintento en la capa de resiliencia, lo que convertía un 429
    puntual en un fallo definitivo para todo el rerun de Streamlit.
    """

    attempt = 0
    while True:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                value = getter()
        except Exception as exc:
            rate_limited = is_yahoo_rate_limit_error(exc)
            if rate_limited and attempt < retries:
                logger.warning(
                    "Yahoo rate limit en %s (intento %s/%s); reintentando en %.1fs.",
                    context, attempt + 1, retries, backoff_seconds,
                )
                time.sleep(backoff_seconds)
                attempt += 1
                continue
            status = STATUS_RATE_LIMITED if rate_limited else STATUS_ERROR
            logger.warning("Yahoo no disponible en %s (%s): %s", context, status, exc)
            return empty_value, status

        captured = _captured_provider_output(stdout, stderr)
        if is_yahoo_rate_limit_error(captured):
            if attempt < retries:
                logger.warning(
                    "Yahoo rate limit capturado en salida de %s (intento %s/%s); reintentando en %.1fs.",
                    context, attempt + 1, retries, backoff_seconds,
                )
                time.sleep(backoff_seconds)
                attempt += 1
                continue
            logger.warning("Yahoo rate limit capturado en salida de %s; se agota reintento.", context)
            return empty_value, STATUS_RATE_LIMITED

        if _is_empty_value(value):
            return empty_value, STATUS_NO_DATA

        return value, STATUS_OK


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
