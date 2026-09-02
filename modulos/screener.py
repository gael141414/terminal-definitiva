"""Escáner cuantitativo global: tabla de filtros + mapa de mercado.

La vista de tabla responde a "¿qué empresas de mi cesta pasan mis filtros?".
El mapa de mercado responde a una pregunta distinta y complementaria: "¿dónde
está concentrado el tamaño y dónde está la calidad?" — algo que una tabla
ordenada no deja ver de un vistazo.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from modulos.config import (
    BUFFETT_DEUDA_EXCELENTE,
    BUFFETT_MARGEN_BRUTO_BUENO,
    BUFFETT_MARGEN_BRUTO_EXCELENTE,
    BUFFETT_MARGEN_NETO_BUENO,
    BUFFETT_MARGEN_NETO_EXCELENTE,
    BUFFETT_ROE_MINIMO,
    BUFFETT_SCORE_BAJO,
    BUFFETT_SCORE_MEDIO,
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    COLOR_WARNING,
    DEBT_EQUITY_RED_FLAG,
)
from modulos.utils import apply_plotly_theme
from modulos.yahoo_resilience import safe_yfinance_info

# Clave de session_state donde vive el último escaneo: sin esto, cambiar de
# pestaña (que provoca un rerun) borraría los resultados y obligaría a relanzar
# el escáner entero.
_STATE_RESULTADOS = "vq_screener_resultados"


def _pct(valor: Any, factor: float = 100.0) -> float:
    """Convierte un ratio de yfinance (0-1) a porcentaje, tolerando None/NaN."""
    try:
        if valor is None or pd.isna(valor):
            return 0.0
        return float(valor) * factor
    except (TypeError, ValueError):
        return 0.0


def buffett_score_express(info: dict[str, Any]) -> float:
    """Score de calidad 0-100 calculado sobre métricas en vivo de Yahoo.

    No es el Buffett Score completo de ``modulos.utils.calcular_score_buffett``:
    ese necesita los tres estados financieros (una descarga por empresa) y aquí
    se escanean decenas de tickers seguidos. Esta variante usa los mismos
    umbrales de ``modulos.config`` sobre los ratios que Yahoo ya devuelve en la
    misma llamada de ``info`` que el escáner hace de todas formas, así que no
    añade ni una petición de red.

    Diferencias frente al completo: no puntúa recompras ni intensidad de CAPEX
    (Yahoo no los publica de forma fiable en ``info``), así que esos 20 puntos se
    redistribuyen entre márgenes, rentabilidad y solidez. El resultado es
    comparable en la misma escala e interpretación (rojo/ámbar/verde), pero no
    idéntico al de la ficha de empresa.
    """
    score = 0.0

    margen_bruto = _pct(info.get("grossMargins"))
    margen_neto = _pct(info.get("profitMargins"))
    roe = _pct(info.get("returnOnEquity"))
    roa = _pct(info.get("returnOnAssets"))
    deuda_equity = info.get("debtToEquity")
    fcf = info.get("freeCashflow")

    # 1. Poder de precios (30 pts)
    if margen_bruto > BUFFETT_MARGEN_BRUTO_EXCELENTE:
        score += 12
    elif margen_bruto > BUFFETT_MARGEN_BRUTO_BUENO:
        score += 6
    if margen_neto > BUFFETT_MARGEN_NETO_EXCELENTE:
        score += 18
    elif margen_neto > BUFFETT_MARGEN_NETO_BUENO:
        score += 9

    # 2. Rentabilidad (35 pts). ROA sustituye al ROIC, que Yahoo no publica:
    #    es más conservador (denominador mayor), así que se exige menos umbral.
    if roe > BUFFETT_ROE_MINIMO:
        score += 20
    elif roe > BUFFETT_ROE_MINIMO / 2:
        score += 10
    if roa > 8:
        score += 15
    elif roa > 4:
        score += 7

    # 3. Solidez financiera (35 pts)
    if deuda_equity is not None and not pd.isna(deuda_equity):
        # Yahoo publica debtToEquity en porcentaje (154.5 = 1.545x).
        ratio = float(deuda_equity) / 100.0
        if ratio < BUFFETT_DEUDA_EXCELENTE:
            score += 20
        elif ratio < DEBT_EQUITY_RED_FLAG:
            score += 10
    if fcf is not None and not pd.isna(fcf) and float(fcf) > 0:
        score += 15

    return round(min(score, 100.0), 1)


def _recolectar(lista_tickers: list[str]) -> tuple[pd.DataFrame, dict[str, str]]:
    """Descarga métricas de cada ticker con barra de progreso."""
    barra = st.progress(0, text="Iniciando conexión con bases de datos...")
    resultados: list[dict[str, Any]] = []
    fallos: dict[str, str] = {}

    for i, ticker in enumerate(lista_tickers):
        barra.progress((i + 1) / len(lista_tickers), text=f"Analizando fundamentales de: {ticker}...")

        info = safe_yfinance_info(yf, ticker, context=f"screener:{ticker}")
        if not info:
            fallos[ticker] = "Sin datos (rate limit temporal o ticker inválido)"
            continue

        per = info.get("trailingPE", 999)
        if per is None or pd.isna(per):
            per = 999.0

        resultados.append(
            {
                "Ticker": ticker,
                "Nombre": info.get("shortName") or ticker,
                "Sector": info.get("sector") or "Desconocido",
                "PER": round(float(per), 2),
                "ROE (%)": round(_pct(info.get("returnOnEquity")), 2),
                "Crecimiento YoY (%)": round(_pct(info.get("revenueGrowth")), 2),
                "Deuda/Equity": round(float(info.get("debtToEquity") or 0.0), 2),
                "Market Cap": float(info.get("marketCap") or 0.0),
                "Buffett Score": buffett_score_express(info),
            }
        )

    barra.empty()
    return pd.DataFrame(resultados), fallos


def _render_tabla(df: pd.DataFrame, max_per: float, min_roe: float, min_growth: float) -> pd.DataFrame:
    """Vista de tabla con los filtros aplicados. Devuelve el df filtrado."""
    df_filtrado = df[
        (df["PER"] <= max_per)
        & (df["ROE (%)"] >= min_roe)
        & (df["Crecimiento YoY (%)"] >= min_growth)
    ]

    if df_filtrado.empty:
        st.error(
            "🩸 Masacre cuantitativa: ninguna empresa de tu cesta ha superado los filtros. "
            "El mercado está caro o los umbrales son demasiado estrictos."
        )
        st.markdown("#### Datos crudos (antes de filtrar)")
        st.dataframe(df, use_container_width=True, hide_index=True)
        return df_filtrado

    st.success(f"🏆 {len(df_filtrado)} de {len(df)} empresas superan el escáner de calidad institucional.")
    st.dataframe(
        df_filtrado.style.format(
            {
                "Market Cap": lambda v: f"${v/1e9:,.1f}B" if v else "n/d",
                "Buffett Score": "{:.0f}",
                "PER": "{:.2f}",
                "ROE (%)": "{:.2f}",
                "Crecimiento YoY (%)": "{:.2f}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )
    return df_filtrado


def construir_treemap(df: pd.DataFrame):
    """Treemap de mercado: tamaño = capitalización, color = calidad.

    El color usa una escala por tramos (rojo <40, ámbar 40-60, verde >60) en vez
    de un degradado continuo porque la lectura que interesa es de estado
    ("¿esto es bueno, regular o malo?"), no de magnitud fina. El ticker y el
    score van escritos dentro del bloque para que la identidad no dependa sólo
    del color.
    """
    datos = df[df["Market Cap"] > 0].copy()
    if datos.empty:
        return None

    datos["Cap (B$)"] = (datos["Market Cap"] / 1e9).round(2)
    datos["Etiqueta"] = datos["Ticker"] + "<br>" + datos["Buffett Score"].round(0).astype(int).astype(str)

    fig = px.treemap(
        datos,
        path=[px.Constant("Mercado"), "Sector", "Etiqueta"],
        values="Market Cap",
        color="Buffett Score",
        color_continuous_scale=[
            (0.0, COLOR_NEGATIVE),
            (0.399, COLOR_NEGATIVE),
            (0.40, COLOR_WARNING),
            (0.599, COLOR_WARNING),
            (0.60, COLOR_POSITIVE),
            (1.0, COLOR_POSITIVE),
        ],
        range_color=(0, 100),
        custom_data=["Ticker", "Sector", "Cap (B$)", "Buffett Score", "PER"],
    )

    fig.update_traces(
        marker=dict(cornerradius=4, line=dict(color="#070a0f", width=2)),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Sector: %{customdata[1]}<br>"
            "Capitalización: $%{customdata[2]:,.1f}B<br>"
            "Buffett Score: %{customdata[3]:.0f}/100<br>"
            "PER: %{customdata[4]:.1f}"
            "<extra></extra>"
        ),
        textfont=dict(size=13),
    )
    fig.update_layout(
        height=560,
        coloraxis_colorbar=dict(
            title="Score",
            tickvals=[0, BUFFETT_SCORE_BAJO, BUFFETT_SCORE_MEDIO, 100],
            ticktext=["0", "40", "60", "100"],
            thickness=12,
            len=0.7,
        ),
    )
    return apply_plotly_theme(fig, show_grid=False)


def _render_mapa(df_filtrado: pd.DataFrame) -> None:
    """Vista de mapa de mercado."""
    if df_filtrado.empty:
        st.info("Ninguna empresa supera los filtros actuales, así que el mapa está vacío. Relaja los umbrales en la pestaña de tabla.")
        return

    fig = construir_treemap(df_filtrado)
    if fig is None:
        st.warning("Las empresas filtradas no tienen capitalización disponible, que es lo que define el tamaño de cada bloque.")
        return

    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    verdes = int((df_filtrado["Buffett Score"] >= BUFFETT_SCORE_MEDIO).sum())
    ambar = int(
        ((df_filtrado["Buffett Score"] >= BUFFETT_SCORE_BAJO) & (df_filtrado["Buffett Score"] < BUFFETT_SCORE_MEDIO)).sum()
    )
    rojas = int((df_filtrado["Buffett Score"] < BUFFETT_SCORE_BAJO).sum())
    c1.metric("🟢 Calidad alta (≥60)", verdes)
    c2.metric("🟡 Calidad media (40-59)", ambar)
    c3.metric("🔴 Calidad baja (<40)", rojas)

    st.caption(
        "El tamaño de cada bloque es la capitalización bursátil y el color el Buffett Score "
        "(rojo <40, ámbar 40-59, verde ≥60). Es un score express calculado sobre métricas en "
        "vivo de Yahoo, no sobre los estados financieros completos: sirve para comparar dentro "
        "de la cesta, no para sustituir a la ficha de empresa."
    )


def ejecutar_escaner_global():
    st.markdown("### 🌐 Escáner Cuantitativo de Oportunidades")
    st.markdown(
        "Introduce una cesta de acciones y aplica filtros institucionales estrictos para separar "
        "las empresas excepcionales de las mediocres."
    )

    tickers_input = st.text_area(
        "📦 Cesta de Tickers a escanear (separados por comas):",
        "AAPL, MSFT, GOOGL, META, TSLA, NVDA, AMZN, NFLX, AMD, INTC, CRM, ADBE",
        help="Escribe los tickers separados por coma.",
    )

    st.markdown("#### ⚙️ Configura tus Filtros (Reglas Quant)")
    col1, col2, col3 = st.columns(3)
    with col1:
        max_per = st.number_input("📉 PER Máximo (Value)", min_value=1.0, max_value=200.0, value=30.0, step=1.0, help="Relación Precio/Beneficio. Menor es más barato.")
    with col2:
        min_roe = st.number_input("📈 ROE Mínimo % (Calidad)", min_value=-50.0, max_value=100.0, value=15.0, step=1.0, help="Retorno sobre el Capital. Mayor a 15% es excelente.")
    with col3:
        min_growth = st.number_input("🚀 Crecimiento Ventas Mínimo %", min_value=-50.0, max_value=200.0, value=10.0, step=1.0, help="Crecimiento de ingresos YoY.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("⚡ Ejecutar Escáner Global", type="primary", use_container_width=True):
        lista_tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
        if not lista_tickers:
            st.warning("⚠️ Introduce al menos un Ticker en la caja de texto para escanear.")
        else:
            df, fallos = _recolectar(lista_tickers)
            st.session_state[_STATE_RESULTADOS] = {"df": df, "fallos": fallos}

    estado = st.session_state.get(_STATE_RESULTADOS)
    if not estado:
        st.info("Configura los filtros y pulsa «Ejecutar Escáner Global» para ver la tabla y el mapa de mercado.")
        return

    df: pd.DataFrame = estado["df"]
    fallos: dict[str, str] = estado["fallos"]

    if fallos:
        detalle = ", ".join(f"{t} ({motivo})" for t, motivo in fallos.items())
        st.warning(f"⚠️ No se pudo obtener información de {len(fallos)} ticker(s): {detalle}")

    if df.empty:
        st.error(
            "No se ha podido extraer información de ninguno de los tickers proporcionados. "
            "Comprueba que estén bien escritos o reinténtalo en unos minutos si Yahoo Finance "
            "está limitando peticiones."
        )
        return

    st.markdown("---")
    tab_tabla, tab_mapa = st.tabs(["📋 Tabla de resultados", "🗺️ Mapa de Mercado"])
    with tab_tabla:
        df_filtrado = _render_tabla(df, max_per, min_roe, min_growth)
    with tab_mapa:
        _render_mapa(df_filtrado)
