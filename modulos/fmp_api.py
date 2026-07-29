from __future__ import annotations

import logging
import re
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st

from modulos.config import CONFIG
from modulos.data_provider_errors import (
    PROVIDER_ERROR,
    RATE_LIMITED,
    RESTRICTED,
    TIMEOUT,
    DataProviderError,
    DataTimeoutError,
    InsufficientCoverageError,
    InvalidTickerError,
    NoDataError,
    ProviderError,
    RateLimitedError,
    RestrictedError,
)
from modulos.data_quality import INSUFFICIENT_ROWS, validate_dataframe


FMP_API_KEY = CONFIG.fmp_api_key
BASE_URL = "https://financialmodelingprep.com/api/v3"
STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT = 15
FMP_MAX_LIMIT_CURRENT_PLAN = 5

logger = logging.getLogger("valuequant.fmp")

# Estados posibles de una llamada FMP clasificada por fetch_fmp_json_classified().
# Distinguen causas que requieren manejo/mensajes distintos en la UI: una clave
# inválida (401) no es lo mismo que un endpoint fuera de plan (402/403), un
# rate limit temporal (429) o un fallo transitorio del proveedor (timeout/5xx).
FMP_STATUS_OK = "ok"
FMP_STATUS_DISABLED = "disabled"
FMP_STATUS_UNAUTHORIZED = "unauthorized"
FMP_STATUS_RESTRICTED_PLAN = "restricted_plan"
FMP_STATUS_RATE_LIMITED = "rate_limited"
FMP_STATUS_PROVIDER_ERROR = "provider_error"
FMP_STATUS_NO_DATA = "no_data"

FMP_STATUS_MESSAGES = {
    FMP_STATUS_DISABLED: "Noticias desactivadas por configuración (FMP_NEWS_ENABLED=false).",
    FMP_STATUS_UNAUTHORIZED: "Clave de API de FMP inválida o ausente.",
    FMP_STATUS_RESTRICTED_PLAN: "Noticias no disponibles con el plan actual de FMP.",
    FMP_STATUS_RATE_LIMITED: "Límite de peticiones de FMP alcanzado temporalmente. Inténtalo de nuevo en unos minutos.",
    FMP_STATUS_PROVIDER_ERROR: "FMP no está disponible temporalmente (error del proveedor). Inténtalo más tarde.",
    FMP_STATUS_NO_DATA: "FMP no devolvió datos para esta consulta.",
}


def classify_fmp_status_code(status_code: int | None) -> str:
    """Clasifica un status HTTP de FMP en una causa accionable.

    401 -> credenciales; 402/403 -> endpoint fuera del plan contratado (no es
    un problema de clave ni de conexión); 429 -> rate limit temporal;
    5xx -> fallo transitorio del proveedor.
    """
    if status_code is None:
        return FMP_STATUS_PROVIDER_ERROR
    if status_code == 401:
        return FMP_STATUS_UNAUTHORIZED
    if status_code in (402, 403):
        return FMP_STATUS_RESTRICTED_PLAN
    if status_code == 429:
        return FMP_STATUS_RATE_LIMITED
    if status_code >= 500:
        return FMP_STATUS_PROVIDER_ERROR
    if status_code == 200:
        return FMP_STATUS_OK
    return FMP_STATUS_PROVIDER_ERROR


def fetch_fmp_json_classified(
    url: str,
    params: dict[str, Any],
    *,
    context: str,
    retries: int = 1,
    backoff_seconds: float = 1.5,
) -> tuple[list[dict] | None, str]:
    """GET a FMP con clasificación de errores y sin exponer nunca la API key.

    Devuelve ``(payload, status)``. Reintenta una única vez, y solo ante
    ``rate_limited``/``provider_error`` (causas transitorias) — un 401/402/403
    es una causa permanente hasta que cambie la configuración o el plan, así
    que reintentarlo en el momento no serviría de nada y solo generaría más
    tráfico contra un endpoint ya restringido.

    Importante: nunca se registra ``url``, ``params`` ni el texto de la
    excepción de requests (``str(exc)`` incluye la URL completa, incl. la
    apikey, para errores HTTP) — solo ``context`` y el status HTTP/nombre de
    clase de la excepción.
    """
    attempt = 0
    while True:
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.Timeout:
            if attempt < retries:
                time.sleep(backoff_seconds)
                attempt += 1
                continue
            logger.warning("FMP timeout en %s tras %s intento(s).", context, attempt + 1)
            return None, FMP_STATUS_PROVIDER_ERROR
        except requests.exceptions.RequestException as exc:
            logger.warning("FMP error de red en %s: %s", context, type(exc).__name__)
            return None, FMP_STATUS_PROVIDER_ERROR

        status = classify_fmp_status_code(response.status_code)

        if status in (FMP_STATUS_RATE_LIMITED, FMP_STATUS_PROVIDER_ERROR) and attempt < retries:
            time.sleep(backoff_seconds)
            attempt += 1
            continue

        if status != FMP_STATUS_OK:
            logger.warning("FMP status=%s (http %s) en %s.", status, response.status_code, context)
            return None, status

        try:
            payload = response.json()
        except ValueError:
            logger.warning("FMP devolvió JSON inválido en %s.", context)
            return None, FMP_STATUS_NO_DATA

        if not isinstance(payload, list) or not payload:
            return None, FMP_STATUS_NO_DATA

        return payload, FMP_STATUS_OK


def _normalizar_ticker(ticker: str) -> str:
    return str(ticker or "").upper().strip()


def _fmp_api_disponible() -> bool:
    return bool(str(FMP_API_KEY or "").strip())


def _variantes_ticker_fmp(ticker: str) -> list[str]:
    ticker_limpio = _normalizar_ticker(ticker)
    variantes = [
        ticker_limpio,
        ticker_limpio.replace(".", "-"),
        ticker_limpio.replace("-", "."),
    ]
    return list(dict.fromkeys([variant for variant in variantes if variant]))


def _endpoint_context(url: str) -> str:
    """Identificador de log seguro derivado de ``url`` (sin query string).

    La apikey viaja siempre en ``params``, nunca en ``url``, en todos los
    endpoints que construye este módulo — pero se recorta cualquier posible
    query string igualmente, por la misma cautela que ``_error_sin_secretos``:
    nunca depender de que ningún llamador futuro rompa esa invariante.
    """
    base = url.split("?", 1)[0]
    return base.replace(BASE_URL, "legacy").replace(STABLE_BASE_URL, "stable")


def _fetch_fmp_payload(url: str, params: dict[str, str | int] | None) -> list[dict]:
    """Como ``_descargar_json`` pero lanzando la excepción tipada correspondiente
    en vez de devolver ``None`` silenciosamente; ``_descargar_json`` la atrapa y
    la traduce al contrato de retorno existente (nadie más debe llamar a esta
    función directamente)."""
    context = _endpoint_context(url)

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout as exc:
        raise DataTimeoutError("Timeout en la petición.", context=context) from exc
    except requests.exceptions.RequestException as exc:
        raise ProviderError(f"Error de red ({type(exc).__name__}).", context=context) from exc

    if response.status_code != 200:
        status = classify_fmp_status_code(response.status_code)
        if status == FMP_STATUS_RATE_LIMITED:
            raise RateLimitedError(f"HTTP {response.status_code}.", context=context, code=RATE_LIMITED)
        if status in (FMP_STATUS_UNAUTHORIZED, FMP_STATUS_RESTRICTED_PLAN):
            # 401 (credenciales) y 402/403 (plan) son causas distintas para el
            # diagnóstico detallado (fetch_fmp_json_classified las separa), pero
            # para esta jerarquía ambas son "acceso denegado, no reintentable".
            raise RestrictedError(f"HTTP {response.status_code}.", context=context, code=RESTRICTED)
        raise ProviderError(f"HTTP {response.status_code}.", context=context)

    try:
        payload = response.json()
    except ValueError as exc:
        raise NoDataError("JSON inválido en la respuesta.", context=context) from exc

    if not isinstance(payload, list) or not payload:
        raise NoDataError("Payload vacío o con forma inesperada.", context=context)

    if isinstance(payload[0], dict) and payload[0].get("Error Message"):
        mensaje = str(payload[0]["Error Message"])
        # Heurística best-effort: FMP no tiene un código de error dedicado para
        # "símbolo inválido", así que se infiere del texto del mensaje.
        if re.search(r"symbol|ticker", mensaje, re.IGNORECASE):
            raise InvalidTickerError(mensaje, context=context)
        raise ProviderError(mensaje, context=context)

    return payload


def _descargar_json(url: str, params: dict[str, str | int] | None = None) -> list[dict] | None:
    if not _fmp_api_disponible():
        return None
    try:
        return _fetch_fmp_payload(url, params)
    except DataProviderError as exc:
        logger.warning("FMP %s", exc)
        return None
    except Exception as exc:
        logger.error("FMP error inesperado en %s: %s", _endpoint_context(url), type(exc).__name__)
        return None


def _params_sin_secretos(params: dict[str, str | int] | None) -> dict[str, str | int]:
    if not params:
        return {}
    safe_params = dict(params)
    if "apikey" in safe_params:
        safe_params["apikey"] = "***"
    return safe_params


_APIKEY_QUERY_PATTERN = re.compile(r"apikey=[^&\s]+", re.IGNORECASE)


def _error_sin_secretos(exc: BaseException) -> str:
    """Representación de un error de requests sin la apikey.

    ``repr()``/``str()`` de ``requests.exceptions.HTTPError`` incluye la URL
    completa reconstruida (base + query string), que contiene la apikey real
    aunque los ``params`` de entrada ya estuvieran redactados — por eso no
    basta con redactar ``params``, hay que redactar también el texto del
    propio error antes de mostrarlo en la UI (``st.json`` en el panel de
    diagnóstico) o registrarlo en logs.
    """
    text = repr(exc)
    text = _APIKEY_QUERY_PATTERN.sub("apikey=***", text)
    if FMP_API_KEY:
        text = text.replace(FMP_API_KEY, "***")
    return text


def _probar_endpoint(
    url: str,
    params: dict[str, str | int] | None,
) -> dict[str, object]:
    resultado: dict[str, object] = {
        "url": url,
        "params": _params_sin_secretos(params),
        "ok": False,
        "status_code": None,
        "code": None,
        "rows": 0,
        "has_date": False,
        "error": None,
        "sample": None,
    }

    if not _fmp_api_disponible():
        resultado["error"] = "FMP_API_KEY no configurada. Define la clave en st.secrets o variable de entorno."
        return resultado

    # Herramienta de diagnóstico interactivo: a propósito atrapa cualquier
    # excepción (no solo las tipadas) para mostrarla siempre al usuario en vez
    # de dejar que una causa inesperada tumbe el panel de diagnóstico.
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resultado["status_code"] = response.status_code
        resultado["sample"] = response.text[:500]
        resultado["code"] = classify_fmp_status_code(response.status_code)
        response.raise_for_status()

        payload = response.json()
        if isinstance(payload, list):
            resultado["rows"] = len(payload)
            resultado["has_date"] = bool(payload and isinstance(payload[0], dict) and "date" in payload[0])
            resultado["ok"] = bool(payload and resultado["has_date"])
            if not resultado["ok"] and resultado["code"] == FMP_STATUS_OK:
                resultado["code"] = FMP_STATUS_NO_DATA
        elif isinstance(payload, dict):
            resultado["error"] = payload.get("Error Message") or payload.get("message") or "Respuesta JSON no list"
            resultado["code"] = FMP_STATUS_NO_DATA
        else:
            resultado["error"] = f"Respuesta JSON inesperada: {type(payload).__name__}"
            resultado["code"] = FMP_STATUS_NO_DATA
    except requests.exceptions.Timeout as exc:
        resultado["error"] = _error_sin_secretos(exc)
        resultado["code"] = TIMEOUT
    except Exception as exc:
        resultado["error"] = _error_sin_secretos(exc)
        if resultado["code"] is None:
            resultado["code"] = PROVIDER_ERROR

    return resultado


def _endpoint_a_dataframe(
    endpoints: list[tuple[str, dict[str, str | int] | None]],
) -> pd.DataFrame | None:
    payload = None
    context = "sin_endpoints_candidatos"
    for url, params in endpoints:
        context = _endpoint_context(url)
        payload = _descargar_json(url, params)
        if payload:
            break

    if not payload:
        # _descargar_json ya registró la causa concreta de cada intento fallido;
        # aquí no hay nada nuevo que loguear, solo agotar los candidatos.
        return None

    try:
        df = pd.DataFrame(payload)
        quality = validate_dataframe(df, ["date"], source="fmp_endpoint", min_rows=1)
        if quality.blocking:
            if quality.status == INSUFFICIENT_ROWS:
                logger.warning(
                    "FMP %s",
                    InsufficientCoverageError(quality.message or "cobertura insuficiente.", context=context),
                )
            else:
                logger.warning(
                    "FMP %s",
                    NoDataError(quality.message or f"validación de calidad bloqueante ({quality.status}).", context=context),
                )
            return None

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index(ascending=True)

        if df.empty:
            logger.warning("FMP %s", NoDataError("todas las fechas del payload eran inválidas.", context=context))
            return None

        metadata_columns = {
            "symbol", "reportedCurrency", "cik", "fillingDate", "acceptedDate",
            "calendarYear", "period", "link", "finalLink",
        }
        for column in df.columns:
            if column not in metadata_columns:
                converted = pd.to_numeric(df[column], errors="coerce")
                if converted.notna().any():
                    df[column] = converted

        return df
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("FMP %s", ProviderError(f"fallo construyendo DataFrame ({type(exc).__name__}).", context=context))
        return None
    except Exception as exc:
        logger.error("FMP error inesperado construyendo DataFrame en %s: %s", context, type(exc).__name__)
        return None


def _construir_endpoints_fundamentales(
    ticker: str,
    limite_anios: int,
) -> dict[str, list[tuple[str, dict[str, str | int] | None]]]:
    ticker_limpio = _normalizar_ticker(ticker)
    limite = min(max(int(limite_anios), 1), FMP_MAX_LIMIT_CURRENT_PLAN)
    variantes_ticker = _variantes_ticker_fmp(ticker_limpio)
    endpoints: dict[str, list[tuple[str, dict[str, str | int] | None]]] = {
        "income_statement": [],
        "balance_sheet": [],
        "cash_flow": [],
        "key_metrics": [],
    }

    if not _fmp_api_disponible():
        return endpoints

    for symbol in variantes_ticker:
        stable_params = {
            "symbol": symbol,
            "period": "annual",
            "limit": limite,
            "apikey": FMP_API_KEY,
        }
        legacy_params = {"limit": limite, "apikey": FMP_API_KEY}
        endpoints["income_statement"].extend([
            (f"{BASE_URL}/income-statement/{symbol}", legacy_params),
            (f"{STABLE_BASE_URL}/income-statement", stable_params),
        ])
        endpoints["balance_sheet"].extend([
            (f"{BASE_URL}/balance-sheet-statement/{symbol}", legacy_params),
            (f"{STABLE_BASE_URL}/balance-sheet-statement", stable_params),
        ])
        endpoints["cash_flow"].extend([
            (f"{BASE_URL}/cash-flow-statement/{symbol}", legacy_params),
            (f"{STABLE_BASE_URL}/cash-flow-statement", stable_params),
        ])
        endpoints["key_metrics"].extend([
            (f"{BASE_URL}/key-metrics/{symbol}", legacy_params),
            (f"{STABLE_BASE_URL}/key-metrics", stable_params),
        ])

    return endpoints


def diagnosticar_conexion_fmp(ticker: str, limite_anios: int = 2) -> dict[str, object]:
    """Devuelve diagnóstico detallado de conectividad FMP sin cachear."""
    ticker_limpio = _normalizar_ticker(ticker)
    endpoints = _construir_endpoints_fundamentales(ticker_limpio, limite_anios)
    diagnostico: dict[str, object] = {
        "ticker": ticker_limpio,
        "api_key_configurada": _fmp_api_disponible(),
        "variantes_probadas": _variantes_ticker_fmp(ticker_limpio),
        "base_url_legacy": BASE_URL,
        "base_url_stable": STABLE_BASE_URL,
        "attempts": {},
    }

    attempts: dict[str, list[dict[str, object]]] = {}
    for nombre, endpoint_list in endpoints.items():
        attempts[nombre] = [
            _probar_endpoint(url, params)
            for url, params in endpoint_list[:4]
        ]
    diagnostico["attempts"] = attempts
    return diagnostico


@st.cache_data(ttl=86400, show_spinner=False)
def extraer_datos_fundamentales_fmp(
    ticker: str,
    limite_anios: int = 10,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Descarga estados financieros y métricas institucionales desde FMP."""
    ticker_limpio = _normalizar_ticker(ticker)
    try:
        if not _fmp_api_disponible():
            return None, None, None, None

        limite = min(max(int(limite_anios), 1), FMP_MAX_LIMIT_CURRENT_PLAN)
        if not ticker_limpio:
            return None, None, None, None

        endpoints = _construir_endpoints_fundamentales(ticker_limpio, limite)

        df_is = _endpoint_a_dataframe(endpoints["income_statement"])
        df_bs = _endpoint_a_dataframe(endpoints["balance_sheet"])
        df_cf = _endpoint_a_dataframe(endpoints["cash_flow"])
        df_metrics = _endpoint_a_dataframe(endpoints["key_metrics"])

        if all(df is None for df in (df_is, df_bs, df_cf, df_metrics)):
            # Cada _endpoint_a_dataframe ya registró su causa concreta; aquí solo
            # se deja constancia de que los 4 estados fallaron para este ticker.
            logger.warning("FMP %s", NoDataError("ningún estado financiero disponible.", context=f"fundamentales:{ticker_limpio}"))
            return None, None, None, None

        return df_is, df_bs, df_cf, df_metrics
    except Exception as exc:
        logger.error("FMP error inesperado obteniendo fundamentales de %s: %s", ticker_limpio or ticker, type(exc).__name__)
        return None, None, None, None


@st.cache_data(ttl=3600, show_spinner=False)
def obtener_cotizacion_fmp(ticker: str) -> float:
    """Obtiene la cotización actual de FMP."""
    ticker_limpio = _normalizar_ticker(ticker)
    try:
        if not _fmp_api_disponible():
            return 0.0

        if not ticker_limpio:
            return 0.0

        endpoints = []
        for symbol in _variantes_ticker_fmp(ticker_limpio):
            endpoints.extend([
                (f"{BASE_URL}/quote-short/{symbol}", {"apikey": FMP_API_KEY}),
                (f"{STABLE_BASE_URL}/quote-short", {"symbol": symbol, "apikey": FMP_API_KEY}),
            ])

        payload = None
        for url, params in endpoints:
            payload = _descargar_json(url, params)
            if payload:
                break

        if not payload:
            logger.warning("FMP %s", NoDataError("no hay cotización disponible.", context=f"cotizacion:{ticker_limpio}"))
            return 0.0

        price = payload[0].get("price", 0.0)
        return float(price) if price is not None else 0.0
    except (TypeError, ValueError) as exc:
        logger.warning(
            "FMP %s",
            ProviderError(f"precio con forma inesperada ({type(exc).__name__}).", context=f"cotizacion:{ticker_limpio}"),
        )
        return 0.0
    except Exception as exc:
        logger.error("FMP error inesperado obteniendo cotización de %s: %s", ticker_limpio or ticker, type(exc).__name__)
        return 0.0
