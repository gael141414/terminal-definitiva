from __future__ import annotations

from math import isfinite

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from modulos.fmp_api import extraer_datos_fundamentales_fmp, obtener_cotizacion_fmp
from modulos.utils import analizar_sentimiento_noticias


def _numero(valor: object, default: float = np.nan) -> float:
    try:
        numero = float(valor)
        return numero if isfinite(numero) else default
    except Exception:
        return default


def _ultimo(df: pd.DataFrame | None, columnas: tuple[str, ...], default: float = np.nan) -> float:
    if df is None or df.empty:
        return default
    for columna in columnas:
        if columna in df.columns:
            serie = pd.to_numeric(df[columna], errors="coerce").dropna()
            if not serie.empty:
                return _numero(serie.iloc[-1], default)
    return default


def _cagr(serie: pd.Series) -> float:
    valores = pd.to_numeric(serie, errors="coerce").dropna()
    if len(valores) < 2:
        return np.nan
    inicial = float(valores.iloc[0])
    final = float(valores.iloc[-1])
    periodos = len(valores) - 1
    if inicial <= 0 or final <= 0 or periodos <= 0:
        return np.nan
    return (final / inicial) ** (1 / periodos) - 1


def _precio_actual(ticker: str) -> float:
    precio = obtener_cotizacion_fmp(ticker)
    if precio > 0:
        return precio

    try:
        yf_ticker = yf.Ticker(ticker)
        fast_info = getattr(yf_ticker, "fast_info", {}) or {}
        precio = _numero(fast_info.get("last_price") or fast_info.get("lastPrice"))
        if isfinite(precio) and precio > 0:
            return precio
        info = yf_ticker.info or {}
        return _numero(info.get("currentPrice") or info.get("previousClose"), 0.0)
    except Exception:
        return 0.0


def _volatilidad_anual(ticker: str) -> float:
    try:
        hist = yf.download(ticker, period="1y", auto_adjust=True, progress=False, threads=False)
        close = hist["Close"] if "Close" in hist else hist
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        returns = pd.to_numeric(close, errors="coerce").pct_change().dropna()
        if returns.empty:
            return 0.30
        return float(returns.std() * np.sqrt(252))
    except Exception:
        return 0.30


def _info_yfinance(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) else {}
    except Exception:
        return {}


def _construir_modelo(ticker: str, precio_actual: float) -> dict[str, object]:
    df_is, df_bs, df_cf, df_metrics = extraer_datos_fundamentales_fmp(ticker, 5)
    info = _info_yfinance(ticker)
    noticias, sentimiento = analizar_sentimiento_noticias(ticker)

    revenue_cagr = _cagr(df_is["revenue"]) if df_is is not None and "revenue" in df_is.columns else np.nan
    revenue_growth = _ultimo(df_metrics, ("revenueGrowth",), revenue_cagr)
    fcf = _ultimo(df_cf, ("freeCashFlow",))
    revenue = _ultimo(df_is, ("revenue",))
    fcf_margin = fcf / revenue if isfinite(fcf) and isfinite(revenue) and revenue else np.nan
    roic = _ultimo(df_metrics, ("roic", "returnOnInvestedCapital", "roicTTM"))
    pe = _ultimo(df_metrics, ("peRatio", "priceEarningsRatio", "peRatioTTM"))
    debt_equity = _ultimo(df_metrics, ("debtToEquity", "debtToEquityRatio"))
    net_debt = _ultimo(df_bs, ("netDebt",))
    cash = _ultimo(df_bs, ("cashAndCashEquivalents", "cashAndShortTermInvestments"))
    volatilidad = _volatilidad_anual(ticker)

    crecimiento_ref = revenue_growth if isfinite(revenue_growth) else revenue_cagr
    crecimiento_ref = crecimiento_ref if isfinite(crecimiento_ref) else 0.03
    roic_ref = roic if isfinite(roic) else 0.08
    fcf_margin_ref = fcf_margin if isfinite(fcf_margin) else 0.0

    quality_score = 50.0
    quality_score += np.clip(crecimiento_ref, -0.15, 0.35) * 70
    quality_score += np.clip(roic_ref, -0.05, 0.30) * 55
    quality_score += np.clip(fcf_margin_ref, -0.20, 0.30) * 45
    if isfinite(debt_equity):
        quality_score -= max(debt_equity - 1.0, 0) * 8
    if isfinite(pe) and pe > 45:
        quality_score -= min((pe - 45) * 0.35, 12)
    quality_score = float(np.clip(quality_score, 5, 95))

    base_return = 0.04
    base_return += np.clip(crecimiento_ref, -0.20, 0.40) * 0.45
    base_return += np.clip(roic_ref, -0.10, 0.35) * 0.25
    base_return += np.clip(fcf_margin_ref, -0.25, 0.35) * 0.20
    base_return += np.clip(sentimiento, -1, 1) * 0.08
    if isfinite(pe) and pe > 60:
        base_return -= 0.06

    base_return = float(np.clip(base_return, -0.18, 0.35))
    dispersion = float(np.clip(volatilidad * 0.55, 0.16, 0.42))
    p_base = precio_actual * (1 + base_return)
    p_toro = precio_actual * (1 + min(base_return + dispersion, 0.85))
    p_oso = precio_actual * (1 + max(base_return - dispersion * 1.25, -0.60))
    prob_alcista = float(np.clip(48 + sentimiento * 14 + (quality_score - 50) * 0.35, 15, 85))

    catalizadores = []
    riesgos = []

    if crecimiento_ref > 0.15:
        catalizadores.append("Crecimiento de ventas superior al 15%, compatible con expansion de multiplos.")
    if fcf_margin_ref > 0.05:
        catalizadores.append("Generacion de caja positiva, reduce riesgo de financiacion externa.")
    if roic_ref > 0.12:
        catalizadores.append("ROIC por encima del coste de capital estimado.")
    if sentimiento > 0.12:
        catalizadores.append("Flujo reciente de titulares con sesgo alcista.")
    if not catalizadores:
        catalizadores.append("Catalizador principal: normalizacion de expectativas y mejora operativa.")

    if fcf_margin_ref < 0:
        riesgos.append("Free cash flow negativo: vigilar runway de caja y posible dilucion.")
    if isfinite(debt_equity) and debt_equity > 1.5:
        riesgos.append("Apalancamiento elevado frente al perfil de crecimiento.")
    if isfinite(pe) and pe > 60:
        riesgos.append("Multiplo exigente: sensible a revisiones de beneficios.")
    if sentimiento < -0.12:
        riesgos.append("Titulares recientes con sesgo bajista.")
    if not riesgos:
        riesgos.append("Riesgo principal: ejecucion y revision de expectativas del mercado.")

    titulares = [n["Titular"] for n in (noticias or [])[:4]]
    sector = info.get("sector") or "N/D"

    return {
        "sector": sector,
        "sentimiento": sentimiento,
        "quality_score": quality_score,
        "probabilidad_alcista_pct": prob_alcista,
        "precio_toro": p_toro,
        "precio_base": p_base,
        "precio_oso": p_oso,
        "retorno_base": base_return,
        "volatilidad": volatilidad,
        "crecimiento": crecimiento_ref,
        "fcf_margin": fcf_margin_ref,
        "roic": roic_ref,
        "pe": pe,
        "cash": cash,
        "net_debt": net_debt,
        "catalizadores": catalizadores,
        "riesgos": riesgos,
        "titulares": titulares,
    }


def _pct(valor: float) -> str:
    return "N/D" if not isfinite(valor) else f"{valor * 100:+.1f}%"


def ejecutar_proyeccion(ticker_input):
    """Modelo probabilistico de 3 escenarios y catalizadores sin dependencia obligatoria de IA externa."""

    st.markdown(f"### 🔮 Proyección Cuantitativa y Catalizadores: {ticker_input}")
    st.markdown("Modelo probabilístico: combina fundamentales FMP, volatilidad, sentimiento de noticias y calidad financiera para trazar 3 escenarios de precio a 12 meses.")

    with st.spinner("Calculando escenarios y catalizadores..."):
        try:
            precio_actual = _precio_actual(ticker_input)
            if precio_actual <= 0:
                st.error("No se pudo obtener precio actual suficiente para construir la proyección.")
                return

            modelo = _construir_modelo(ticker_input, precio_actual)
            p_toro = float(modelo["precio_toro"])
            p_base = float(modelo["precio_base"])
            p_oso = float(modelo["precio_oso"])
            prob_alcista = float(modelo["probabilidad_alcista_pct"])

            ret_toro = ((p_toro / precio_actual) - 1) * 100
            ret_base = ((p_base / precio_actual) - 1) * 100
            ret_oso = ((p_oso / precio_actual) - 1) * 100

            st.markdown("---")
            st.markdown(f"### 🎯 Precio Objetivo a 12 Meses (Probabilidad Alcista: {prob_alcista:.0f}%)")
            c1, c2, c3 = st.columns(3)
            c1.metric("🟢 Caso Toro", f"${p_toro:,.2f}", f"{ret_toro:+.2f}%")
            c2.metric("🟡 Caso Base", f"${p_base:,.2f}", f"{ret_base:+.2f}%")
            c3.metric("🔴 Caso Oso", f"${p_oso:,.2f}", f"{ret_oso:+.2f}%")

            fecha_hoy = pd.Timestamp.today().normalize()
            fecha_futura = fecha_hoy + pd.DateOffset(months=12)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[fecha_hoy], y=[precio_actual], mode="markers", marker=dict(color="white", size=10), name="Precio Actual"))
            fig.add_trace(go.Scatter(x=[fecha_hoy, fecha_futura], y=[precio_actual, p_toro], mode="lines+markers", line=dict(color="#00C0F2", width=3, dash="dot"), name="Caso Toro"))
            fig.add_trace(go.Scatter(x=[fecha_hoy, fecha_futura], y=[precio_actual, p_base], mode="lines+markers", line=dict(color="#8c9bba", width=3), name="Caso Base"))
            fig.add_trace(go.Scatter(x=[fecha_hoy, fecha_futura], y=[precio_actual, p_oso], mode="lines+markers", line=dict(color="#ff4b4b", width=3, dash="dot"), name="Caso Oso"))
            fig.update_layout(height=400, margin=dict(t=20, b=20, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("---")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Score calidad", f"{float(modelo['quality_score']):.0f}/100")
            m2.metric("Crecimiento ref.", _pct(float(modelo["crecimiento"])))
            m3.metric("FCF margin", _pct(float(modelo["fcf_margin"])))
            m4.metric("Volatilidad anual", _pct(float(modelo["volatilidad"])))

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### ⚡ Catalizadores")
                for cat in modelo["catalizadores"]:
                    st.success(f"✔️ {cat}")
            with col_b:
                st.markdown("#### 🛡️ Riesgos a vigilar")
                for riesgo in modelo["riesgos"]:
                    st.warning(f"⚠️ {riesgo}")

            st.markdown("#### 🧠 Tesis del algoritmo")
            st.write(
                f"El escenario base asume retorno esperado de **{ret_base:+.1f}%** con sentimiento "
                f"**{float(modelo['sentimiento']):+.2f}**, sector **{modelo['sector']}** y valoración "
                f"PER **{modelo['pe']:.1f}x**." if isfinite(float(modelo["pe"])) else
                f"El escenario base asume retorno esperado de **{ret_base:+.1f}%** con sentimiento "
                f"**{float(modelo['sentimiento']):+.2f}** y sector **{modelo['sector']}**."
            )

            if modelo["titulares"]:
                with st.expander("Titulares usados por el modelo"):
                    for titular in modelo["titulares"]:
                        st.write(f"- {titular}")

        except Exception as e:
            st.error(f"Error procesando la proyección: {e}")
