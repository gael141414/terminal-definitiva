"""Interfaz del rendimiento de cartera frente al benchmark de flujos igualados."""

from __future__ import annotations

import json
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modulos.config import (
    COLOR_ACCENT, COLOR_NEGATIVE, COLOR_POSITIVE, COLOR_PRIMARY, COLOR_TEXT_MUTED,
    FICHERO_CARTERA, PESOS_BENCHMARK_DEFECTO, PROXIES_INDICE,
)
from modulos.html_markdown import escribir_html
from modulos.rendimiento_cartera import RendimientoCartera, calcular_rendimiento
from modulos.ui_components import render_kpi_card
from modulos.utils import apply_plotly_theme

COLUMNAS = ["Ticker", "Importe (€)", "Fecha"]


# ==========================================================================
# PERSISTENCIA
# ==========================================================================


def cargar_cartera() -> pd.DataFrame:
    if not os.path.exists(FICHERO_CARTERA):
        return pd.DataFrame([
            {"Ticker": "AAPL", "Importe (€)": 500.0, "Fecha": date(2024, 1, 27)},
            {"Ticker": "GOOG", "Importe (€)": 800.0, "Fecha": date(2025, 4, 3)},
            {"Ticker": "NVDA", "Importe (€)": 250.0, "Fecha": date(2026, 1, 15)},
        ])
    try:
        with open(FICHERO_CARTERA, encoding="utf-8") as fichero:
            datos = json.load(fichero)
        df = pd.DataFrame(datos)
        if "Fecha" in df.columns:
            df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.date
        return df[COLUMNAS] if all(c in df.columns for c in COLUMNAS) else df
    except (json.JSONDecodeError, OSError, KeyError):
        return pd.DataFrame(columns=COLUMNAS)


def guardar_cartera(df: pd.DataFrame) -> None:
    os.makedirs(os.path.dirname(FICHERO_CARTERA), exist_ok=True)
    registros = df.dropna(subset=["Ticker"]).copy()
    registros["Fecha"] = registros["Fecha"].astype(str)
    with open(FICHERO_CARTERA, "w", encoding="utf-8") as fichero:
        json.dump(registros.to_dict(orient="records"), fichero, indent=2, ensure_ascii=False)


# ==========================================================================
# GRÁFICAS
# ==========================================================================


def _grafica_dinero(series: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index, y=series["invertido_acum"], name="Capital invertido",
        line=dict(color=COLOR_TEXT_MUTED, width=1.5, shape="hv", dash="dot"),
        hovertemplate="%{x|%d/%m/%Y}<br>Invertido: %{y:,.0f} €<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=series.index, y=series["valor_benchmark"], name="Benchmark (mismo dinero)",
        line=dict(color=COLOR_ACCENT, width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>Índice: %{y:,.0f} €<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=series.index, y=series["valor_cartera"], name="Mi cartera",
        line=dict(color=COLOR_PRIMARY, width=2.4),
        hovertemplate="%{x|%d/%m/%Y}<br>Cartera: %{y:,.0f} €<extra></extra>",
    ))
    fig.update_layout(height=430, yaxis_title="€", hovermode="x unified",
                      legend=dict(orientation="h", y=1.08))
    return apply_plotly_theme(fig)


def _grafica_rentabilidad(series: pd.DataFrame, unitizada: bool) -> go.Figure:
    fig = go.Figure()
    if unitizada:
        cartera, bench = series["unitizada_cartera"], series["unitizada_benchmark"]
        titulo, sufijo = "Base 100", ""
    else:
        cartera, bench = series["ret_cartera_pct"], series["ret_benchmark_pct"]
        titulo, sufijo = "% sobre capital desplegado", "%"

    fig.add_trace(go.Scatter(x=series.index, y=bench, name="Benchmark",
                             line=dict(color=COLOR_ACCENT, width=2),
                             hovertemplate=f"%{{x|%d/%m/%Y}}<br>%{{y:,.2f}}{sufijo}<extra></extra>"))
    fig.add_trace(go.Scatter(x=series.index, y=cartera, name="Mi cartera",
                             line=dict(color=COLOR_PRIMARY, width=2.4),
                             hovertemplate=f"%{{x|%d/%m/%Y}}<br>%{{y:,.2f}}{sufijo}<extra></extra>"))
    fig.update_layout(height=400, yaxis_title=titulo, hovermode="x unified",
                      legend=dict(orientation="h", y=1.08))
    return apply_plotly_theme(fig)


# ==========================================================================
# BLOQUES
# ==========================================================================


def _render_resumen(resultado: RendimientoCartera) -> None:
    r = resultado.resumen
    diferencia = r.get("diferencia_eur") or 0.0
    gana = diferencia > 0

    a, b, c, d = st.columns(4)
    with a:
        render_kpi_card("Invertido", f"{r['total_invertido_eur']:,.0f} €",
                        detail=f"Desde {r['desde']}", tag="TOTAL")
    with b:
        render_kpi_card("Mi cartera", f"{r['valor_cartera_eur']:,.0f} €",
                        detail=f"{r['retorno_cartera_pct']:+.1f}% sobre lo invertido",
                        status="favorable" if (r.get("retorno_cartera_pct") or 0) > 0 else "riesgo")
    with c:
        render_kpi_card("Mismo dinero indexado", f"{r['valor_benchmark_eur']:,.0f} €",
                        detail=f"{r['retorno_benchmark_pct']:+.1f}% sobre lo invertido")
    with d:
        render_kpi_card("Diferencia", f"{diferencia:+,.0f} €",
                        detail=("Tu selección bate al índice." if gana
                                else "El índice te habría ido mejor."),
                        status="favorable" if gana else "riesgo")

    if r.get("xirr_cartera") is not None:
        e, f = st.columns(2)
        with e:
            render_kpi_card("TIR anual · cartera", f"{r['xirr_cartera'] * 100:+.2f}%",
                            detail="Ponderada por el momento de cada aportación.")
        with f:
            render_kpi_card("TIR anual · benchmark", f"{r['xirr_benchmark'] * 100:+.2f}%",
                            detail="Mismos flujos, invertidos en el índice.")


def _render_riesgo(resultado: RendimientoCartera) -> None:
    cartera = resultado.resumen.get("riesgo_cartera")
    bench = resultado.resumen.get("riesgo_benchmark")
    if not cartera or not bench:
        st.caption("Sin serie suficiente para calcular el riesgo.")
        return

    st.markdown("##### Comparación ajustada a riesgo")
    st.caption(
        "Calculada sobre la serie unitizada (TWR), no sobre el valor de la cartera: "
        "sobre la serie con aportaciones, cada ingreso de dinero parecería un "
        "retorno enorme y estas métricas mentirían."
    )
    tabla = pd.DataFrame([cartera, bench], index=["Mi cartera", "Benchmark"])
    st.dataframe(tabla, use_container_width=True)


def _render_atribucion(resultado: RendimientoCartera) -> None:
    if not resultado.atribucion:
        return
    st.markdown("##### Atribución: qué posiciones baten al índice")
    st.caption(
        "Cada valor frente a la porción de índice que se habría comprado con ese "
        "mismo dinero, ese mismo día."
    )
    filas = [{
        "Ticker": a.ticker, "Comprado": a.fecha_compra,
        "Invertido (€)": a.invertido_eur, "Valor hoy (€)": a.valor_actual_eur,
        "Si hubiera indexado (€)": a.valor_si_indice_eur,
        "Alfa (€)": a.alfa_eur, "Alfa (%)": a.alfa_pct,
        "Retorno (%)": a.retorno_pct, "Índice (%)": a.retorno_indice_pct,
    } for a in sorted(resultado.atribucion, key=lambda x: x.alfa_eur, reverse=True)]

    st.dataframe(
        pd.DataFrame(filas).style.map(
            lambda v: f"color: {COLOR_POSITIVE}" if isinstance(v, (int, float)) and v > 0
            else (f"color: {COLOR_NEGATIVE}" if isinstance(v, (int, float)) and v < 0 else ""),
            subset=["Alfa (€)", "Alfa (%)"],
        ),
        use_container_width=True, hide_index=True,
    )


# ==========================================================================
# PANTALLA
# ==========================================================================


def render_rendimiento_cartera() -> None:
    st.markdown("### Mi cartera frente al índice")
    st.caption(
        "Compara tu cartera con haber invertido **el mismo dinero en los mismos "
        "momentos** en uno o varios índices. Así se aísla si tu selección aporta "
        "algo por encima de indexar."
    )

    izquierda, derecha = st.columns([1.5, 1])

    with izquierda:
        st.markdown("##### Posiciones")
        editada = st.data_editor(
            cargar_cartera(), num_rows="dynamic", use_container_width=True,
            column_config={
                "Ticker": st.column_config.TextColumn("Ticker", required=True),
                "Importe (€)": st.column_config.NumberColumn("Importe (€)", min_value=0.0, format="%.2f"),
                "Fecha": st.column_config.DateColumn("Fecha de compra", format="DD/MM/YYYY"),
            },
            key="vq_cartera_editor",
        )

    with derecha:
        st.markdown("##### Índices de referencia")
        seleccionados = st.multiselect(
            "Índices", list(PROXIES_INDICE),
            default=list(PESOS_BENCHMARK_DEFECTO),
            format_func=lambda k: PROXIES_INDICE[k]["nombre"],
        )
        pesos: dict[str, float] = {}
        for nombre in seleccionados:
            pesos[nombre] = st.slider(
                PROXIES_INDICE[nombre]["nombre"], 0.0, 1.0,
                float(PESOS_BENCHMARK_DEFECTO.get(nombre, 1 / max(len(seleccionados), 1))),
                0.05, key=f"vq_peso_{nombre}",
            )
        total = sum(pesos.values())
        if seleccionados and abs(total - 1.0) > 1e-6:
            st.warning(f"Los pesos suman {total:.2f}; deben sumar 1,00 para que la "
                       "comparación invierta el mismo dinero.")

    unitizada = st.toggle(
        "Vista TWR unitizada (base 100)", value=False,
        help="Aísla el efecto del momento de las aportaciones. Con la vista en % "
             "verás un escalón cada vez que metes dinero nuevo: es intrínseco al "
             "método de flujos igualados, no un error.",
    )

    if not st.button("Calcular rendimiento", type="primary", use_container_width=True):
        st.info("Ajusta las posiciones y pulsa «Calcular rendimiento».")
        return

    limpio = editada.dropna(subset=["Ticker"])
    if limpio.empty:
        st.error("No hay posiciones que valorar.")
        return
    if abs(sum(pesos.values()) - 1.0) > 1e-6:
        st.error("Los pesos del benchmark deben sumar 1,00.")
        return

    guardar_cartera(limpio)
    transacciones = [
        (str(f["Ticker"]).strip().upper(), float(f["Importe (€)"]), f["Fecha"])
        for _, f in limpio.iterrows()
    ]

    with st.spinner("Descargando precios y tipos de cambio…"):
        try:
            resultado = calcular_rendimiento(transacciones, pesos)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"No se pudo calcular el rendimiento: {exc}")
            return

    if not resultado.valido:
        st.error("No se pudo valorar ninguna posición.")
        for aviso in resultado.avisos:
            st.caption(aviso)
        return

    _render_resumen(resultado)
    st.markdown("")
    st.markdown("##### Evolución del dinero")
    st.plotly_chart(_grafica_dinero(resultado.series), use_container_width=True)

    st.markdown("##### Evolución de la rentabilidad")
    if not unitizada:
        st.caption(
            "El escalón que aparece al aportar dinero nuevo es intrínseco al método "
            "de flujos igualados: cambia el denominador. Activa la vista TWR para "
            "aislarlo."
        )
    st.plotly_chart(_grafica_rentabilidad(resultado.series, unitizada), use_container_width=True)

    _render_riesgo(resultado)
    _render_atribucion(resultado)

    if resultado.avisos:
        with st.expander("Avisos sobre los datos", expanded=False):
            for aviso in resultado.avisos:
                st.caption(aviso)

    try:
        from modulos.analysis_store import save_analysis_snapshot

        save_analysis_snapshot({"tipo": "rendimiento_cartera", **resultado.resumen})
    except Exception:
        pass
