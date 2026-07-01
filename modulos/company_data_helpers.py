from __future__ import annotations

import math
from typing import Any

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from modulos.data_quality import is_valid_value, validate_dataframe, validate_mapping


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convierte valores Yahoo a float finito sin propagar NaN/inf."""

    try:
        if not is_valid_value(value):
            return default
        numeric = float(value)
    except Exception:
        return default
    if not math.isfinite(numeric):
        return default
    return numeric


def _safe_percent(value: Any) -> float | None:
    """Convierte ratios 0-1 de Yahoo a porcentaje 0-100 si son válidos."""

    if not is_valid_value(value):
        return None
    numeric = _safe_float(value, default=float("nan"))
    if not math.isfinite(numeric):
        return None
    return numeric * 100


def obtener_transacciones_insiders(ticker):
    """Descarga las últimas compras/ventas de los directivos (Form 4)."""

    try:
        ticker_yf = yf.Ticker(ticker)
        transacciones = ticker_yf.insider_transactions

        quality = validate_dataframe(transacciones, source="yahoo_insider_transactions", min_rows=1)
        if quality.blocking:
            return None

        cols_deseadas = ["Start Date", "Insider", "Position", "Transaction", "Value", "Shares"]
        cols_presentes = [c for c in cols_deseadas if c in transacciones.columns]
        if not cols_presentes:
            return None

        df_limpio = transacciones[cols_presentes].copy()

        if "Start Date" in df_limpio.columns:
            df_limpio["Start Date"] = pd.to_datetime(df_limpio["Start Date"], errors="coerce").dt.strftime("%Y-%m-%d")

        df_limpio = df_limpio.dropna(how="all")
        if df_limpio.empty:
            return None

        return df_limpio.head(15)
    except Exception:
        return None


@st.cache_data(ttl=86400 * 7)
def obtener_tickers_filtrados():
    """Descarga la lista de la SEC y filtra ETFs, SPACS y empresas extranjeras."""

    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"User-Agent": "ValueQuant Terminal (contacto@valuequant.com)"}
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        datos = r.json()

        quality = validate_mapping(datos, source="sec_company_tickers", min_coverage=0.01)
        if quality.blocking:
            return ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]

        filtros_basura = [
            " ADR", " LTD", " LIMITED", " PLC", " S.A.", " N.V.",
            " FUND", " TRUST", " ETF", " ACQUISITION", " SPAC",
            " BLANK CHECK", " BANCORP",
        ]

        lista_formateada = []
        for v in datos.values():
            if not isinstance(v, dict):
                continue

            ticker = str(v.get("ticker") or "").strip()
            title = str(v.get("title") or "").strip()
            if not ticker or not title:
                continue

            nombre_mayus = title.upper()
            if not any(basura in nombre_mayus for basura in filtros_basura):
                lista_formateada.append(f"{ticker} - {title.title()}")

        return sorted(lista_formateada) or ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]
    except Exception:
        return ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]


def obtener_valoracion_sectorial(ticker):
    """Aplica la regla de valoración relativa según el sector."""

    try:
        info = yf.Ticker(ticker).info
        if not isinstance(info, dict) or not info:
            return None, None, 0, "No se pudieron validar los datos de Yahoo Finance.", {}, 0

        quality = validate_mapping(info, source="yahoo_info", min_coverage=0.01)
        if quality.blocking:
            return None, None, 0, "No se pudieron validar los datos de Yahoo Finance.", {}, 0

        sector = str(info.get("sector") or "Desconocido")

        multiplos = {
            "P/E (Price/Earnings)": _safe_float(info.get("trailingPE")),
            "P/B (Price/Book)": _safe_float(info.get("priceToBook")),
            "EV / EBITDA": _safe_float(info.get("enterpriseToEbitda")),
            "EV / Ventas": _safe_float(info.get("enterpriseToRevenue")),
        }

        metrica_clave = "P/E (Price/Earnings)"
        racionalidad = "Para empresas maduras, las ganancias netas estables son el mejor indicador de valor."
        umbral_barato = 15.0

        if sector in ["Technology", "Communication Services"]:
            metrica_clave = "EV / Ventas"
            racionalidad = "En tecnología y software, se valora el crecimiento y la captura de mercado (Top-Line). Muchas reinvierten todo y no tienen beneficio neto hoy."
            umbral_barato = 5.0

        elif sector in ["Financial Services", "Real Estate"]:
            metrica_clave = "P/B (Price/Book)"
            racionalidad = "En bancos y aseguradoras, los activos financieros son un proxy directo del valor. Un ratio menor a 1 indica que compras sus activos con descuento."
            umbral_barato = 1.2

        elif sector in ["Industrials", "Basic Materials", "Energy", "Utilities"]:
            metrica_clave = "EV / EBITDA"
            racionalidad = "En industria pesada, elimina el ruido de las agresivas políticas de amortización de maquinaria y diferencias impositivas."
            umbral_barato = 10.0

        elif sector in ["Consumer Defensive", "Healthcare"]:
            metrica_clave = "P/E (Price/Earnings)"
            racionalidad = "Sectores estables y predecibles. El mercado paga por la seguridad del beneficio neto constante."
            umbral_barato = 15.0

        valor_metrica = multiplos.get(metrica_clave, 0)

        return sector, metrica_clave, valor_metrica, racionalidad, multiplos, umbral_barato

    except Exception as e:
        return None, None, 0, str(e), {}, 0


@st.cache_data(show_spinner=False)
def obtener_datos_directiva(ticker):
    """Extrae qué porcentaje de la empresa tienen los directivos y fondos."""

    try:
        info = yf.Ticker(ticker).info
        quality = validate_mapping(
            info,
            ["heldPercentInsiders", "heldPercentInstitutions", "shortRatio"],
            source="yahoo_ownership",
            min_coverage=0.34,
        )
        if quality.blocking:
            return None, None, None

        insiders = _safe_percent(info.get("heldPercentInsiders"))
        instituciones = _safe_percent(info.get("heldPercentInstitutions"))
        short_ratio = _safe_float(info.get("shortRatio"), default=0.0)

        return insiders, instituciones, short_ratio
    except Exception:
        return None, None, None
