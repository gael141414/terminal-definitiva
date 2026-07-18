"""Jerarquía común de errores de proveedores de datos externos (FMP, Yahoo/yfinance).

Cada código distingue una causa accionable distinta: un ticker inválido no se
arregla reintentando, un rate limit sí; "no hay datos en absoluto" no es lo
mismo que "hay datos pero insuficientes para el análisis". fmp_api.py y
yahoo_resilience.py capturan estas excepciones internamente — no se propagan
hacia la UI/Streamlit, que sigue recibiendo exactamente los mismos contratos
de retorno de siempre (None, DataFrame vacío, tuplas ``(valor, status)``) —
el único cambio es que ahora se registra con contexto (endpoint/ticker/código)
en vez de silenciarse con ``except Exception: return None``.
"""

from __future__ import annotations

NO_DATA = "no_data"
INVALID_TICKER = "invalid_ticker"
RATE_LIMITED = "rate_limited"
RESTRICTED = "restricted"
TIMEOUT = "timeout"
PROVIDER_ERROR = "provider_error"
INSUFFICIENT_COVERAGE = "insufficient_coverage"

ALL_CODES = {
    NO_DATA,
    INVALID_TICKER,
    RATE_LIMITED,
    RESTRICTED,
    TIMEOUT,
    PROVIDER_ERROR,
    INSUFFICIENT_COVERAGE,
}


class DataProviderError(Exception):
    """Base de la jerarquía. ``code`` es uno de los valores de ``ALL_CODES``."""

    code = PROVIDER_ERROR

    def __init__(self, message: str, *, context: str, code: str | None = None):
        super().__init__(message)
        self.context = context
        self.code = code or self.code

    def __str__(self) -> str:  # pragma: no cover - solo formatea logging
        return f"[{self.code}] {self.context}: {super().__str__()}"


class NoDataError(DataProviderError):
    """El proveedor respondió correctamente pero sin datos utilizables."""

    code = NO_DATA


class InvalidTickerError(DataProviderError):
    """El proveedor indica explícitamente que el símbolo no existe/es inválido."""

    code = INVALID_TICKER


class RateLimitedError(DataProviderError):
    """Límite de peticiones alcanzado (causa transitoria, reintentable)."""

    code = RATE_LIMITED


class RestrictedError(DataProviderError):
    """Acceso denegado por plan/credenciales (causa permanente hasta cambiar config)."""

    code = RESTRICTED


class DataTimeoutError(DataProviderError):
    """La petición no respondió dentro del timeout configurado."""

    code = TIMEOUT


class ProviderError(DataProviderError):
    """Fallo transitorio genérico del proveedor (5xx, red, JSON inválido, etc.)."""

    code = PROVIDER_ERROR


class InsufficientCoverageError(DataProviderError):
    """Hay datos, pero no cubren lo mínimo necesario (filas/columnas/años)."""

    code = INSUFFICIENT_COVERAGE
