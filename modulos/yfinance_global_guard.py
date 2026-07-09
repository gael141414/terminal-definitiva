from __future__ import annotations

import contextlib
import functools
import io
import logging
from typing import Any

import pandas as pd

from modulos.yahoo_resilience import is_yahoo_rate_limit_error

logger = logging.getLogger(__name__)


def _normalize_download_result(value: Any) -> Any:
    if value is None:
        return pd.DataFrame()
    return value


def install_yfinance_guard(yf_module: Any | None = None) -> bool:
    """Instala un guard idempotente sobre yfinance.download.

    Protege llamadas legacy, especialmente las de charts.py, frente a errores temporales
    de Yahoo Finance que pueden escribirse en stdout/stderr o lanzarse como excepción.
    """

    if yf_module is None:
        import yfinance as yf_module  # type: ignore[no-redef]

    current_download = getattr(yf_module, "download", None)
    if current_download is None:
        return False
    if getattr(current_download, "_valuequant_guarded", False):
        return False

    original_download = current_download

    @functools.wraps(original_download)
    def guarded_download(*args: Any, **kwargs: Any) -> Any:
        stdout = io.StringIO()
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = original_download(*args, **kwargs)
        except Exception as exc:
            if is_yahoo_rate_limit_error(exc):
                logger.warning("Yahoo Finance rate limit interceptado por guard global; devolviendo DataFrame vacío.")
                return pd.DataFrame()
            raise

        captured = "\n".join(part for part in (stdout.getvalue(), stderr.getvalue()) if part)
        if is_yahoo_rate_limit_error(captured):
            logger.warning("Yahoo Finance rate limit detectado en salida capturada; devolviendo DataFrame vacío.")
            return pd.DataFrame()

        return _normalize_download_result(result)

    setattr(guarded_download, "_valuequant_guarded", True)
    setattr(guarded_download, "_valuequant_original_download", original_download)
    yf_module.download = guarded_download
    return True
