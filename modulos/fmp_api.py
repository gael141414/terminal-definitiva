from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

from modulos.config import CONFIG


FMP_API_KEY = CONFIG.fmp_api_key
BASE_URL = "https://financialmodelingprep.com/api/v3"
STABLE_BASE_URL = "https://financialmodelingprep.com/stable"
REQUEST_TIMEOUT = 15
FMP_MAX_LIMIT_CURRENT_PLAN = 5


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


def _descargar_json(url: str, params: dict[str, str | int] | None = None) -> list[dict] | None:
    try:
        if not _fmp_api_disponible():
            return None
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            return None
        if isinstance(payload[0], dict) and payload[0].get("Error Message"):
            return None
        return payload
    except Exception:
        return None


def _params_sin_secretos(params: dict[str, str | int] | None) -> dict[str, str | int]:
    if not params:
        return {}
    safe_params = dict(params)
    if "apikey" in safe_params:
        safe_params["apikey"] = "***"
    return safe_params


def _probar_endpoint(
    url: str,
    params: dict[str, str | int] | None,
) -> dict[str, object]:
    resultado: dict[str, object] = {
        "url": url,
        "params": _params_sin_secretos(params),
        "ok": False,
        "status_code": None,
        "rows": 0,
        "has_date": False,
        "error": None,
        "sample": None,
    }

    if not _fmp_api_disponible():
        resultado["error"] = "FMP_API_KEY no configurada. Define la clave en st.secrets o variable de entorno."
        return resultado

    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resultado["status_code"] = response.status_code
        resultado["sample"] = response.text[:500]
        response.raise_for_status()

        payload = response.json()
        if isinstance(payload, list):
            resultado["rows"] = len(payload)
            resultado["has_date"] = bool(payload and isinstance(payload[0], dict) and "date" in payload[0])
            resultado["ok"] = bool(payload and resultado["has_date"])
        elif isinstance(payload, dict):
            resultado["error"] = payload.get("Error Message") or payload.get("message") or "Respuesta JSON no list"
        else:
            resultado["error"] = f"Respuesta JSON inesperada: {type(payload).__name__}"
    except Exception as exc:
        resultado["error"] = repr(exc)

    return resultado


def _endpoint_a_dataframe(
    endpoints: list[tuple[str, dict[str, str | int] | None]],
) -> pd.DataFrame | None:
    try:
        payload = None
        for url, params in endpoints:
            payload = _descargar_json(url, params)
            if payload:
                break

        if not payload:
            return None

        df = pd.DataFrame(payload)
        if df.empty or "date" not in df.columns:
            return None

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).set_index("date").sort_index(ascending=True)

        if df.empty:
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
    except Exception:
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
    try:
        if not _fmp_api_disponible():
            return None, None, None, None

        ticker_limpio = _normalizar_ticker(ticker)
        limite = min(max(int(limite_anios), 1), FMP_MAX_LIMIT_CURRENT_PLAN)
        if not ticker_limpio:
            return None, None, None, None

        endpoints = _construir_endpoints_fundamentales(ticker_limpio, limite)

        df_is = _endpoint_a_dataframe(endpoints["income_statement"])
        df_bs = _endpoint_a_dataframe(endpoints["balance_sheet"])
        df_cf = _endpoint_a_dataframe(endpoints["cash_flow"])
        df_metrics = _endpoint_a_dataframe(endpoints["key_metrics"])

        if all(df is None for df in (df_is, df_bs, df_cf, df_metrics)):
            return None, None, None, None

        return df_is, df_bs, df_cf, df_metrics
    except Exception:
        return None, None, None, None


@st.cache_data(ttl=3600, show_spinner=False)
def obtener_cotizacion_fmp(ticker: str) -> float:
    """Obtiene la cotización actual de FMP."""
    try:
        if not _fmp_api_disponible():
            return 0.0

        ticker_limpio = _normalizar_ticker(ticker)
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
            return 0.0

        price = payload[0].get("price", 0.0)
        return float(price) if price is not None else 0.0
    except Exception:
        return 0.0
