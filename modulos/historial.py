"""Historial de KPIs por empresa: cómo han cambiado los ratios entre análisis.

Complementa a ``modulos.analysis_store`` (que guarda snapshots completos de
Research Core cuando el usuario los archiva a mano) resolviendo otra pregunta:
*¿esta empresa está mejorando o deteriorándose desde la última vez que la miré?*

El registro es automático — se dispara al abrir el Resumen Ejecutivo — y guarda
sólo cinco KPIs estructurales en ``data/historial.json``. Se limita a una
entrada por ticker y día: reabrir la misma ficha cinco veces en una tarde no
debe inventar cinco puntos de "evolución" que en realidad son el mismo dato.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modulos.config import PLOTLY_COLORWAY
from modulos.utils import apply_plotly_theme

logger = logging.getLogger(__name__)

DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "historial.json")

# KPI visible -> (dataframe de ratios, columna). El orden fija el de la leyenda.
KPIS_SEGUIDOS: tuple[tuple[str, str, str], ...] = (
    ("ROE %", "bs", "ROE %"),
    ("ROIC %", "bs", "ROIC %"),
    ("Margen Neto %", "is", "Margen Neto %"),
    ("Deuda / Capital", "bs", "Deuda / Capital"),
)

MAX_ENTRADAS_POR_TICKER = 60


def _inicializar_db() -> None:
    os.makedirs(DB_FOLDER, exist_ok=True)
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as fichero:
            json.dump({}, fichero)


def cargar_historial_completo() -> dict[str, list[dict[str, Any]]]:
    """Lee el historial entero. Nunca lanza: un JSON corrupto no debe tumbar la ficha."""
    _inicializar_db()
    try:
        with open(DB_FILE, "r", encoding="utf-8") as fichero:
            datos = json.load(fichero)
        return datos if isinstance(datos, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Historial ilegible (%s); se parte de vacío.", type(exc).__name__)
        return {}


def _guardar(datos: dict[str, list[dict[str, Any]]]) -> None:
    _inicializar_db()
    try:
        with open(DB_FILE, "w", encoding="utf-8") as fichero:
            json.dump(datos, fichero, indent=2, ensure_ascii=False)
    except OSError as exc:
        logger.warning("No se pudo escribir el historial: %s", exc)


def _ultimo_valor(df: Any, columna: str) -> float | None:
    if df is None or not hasattr(df, "columns") or columna not in df.columns:
        return None
    serie = df[columna].dropna()
    if serie.empty:
        return None
    try:
        return round(float(serie.iloc[-1]), 4)
    except (TypeError, ValueError):
        return None


def registrar_analisis(
    ticker: str,
    res_is: dict[str, Any] | None,
    res_bs: dict[str, Any] | None,
    res_cf: dict[str, Any] | None,
    nota_buffett: float | int | None = None,
    valuequant_score: Any = None,
) -> None:
    """Añade (o refresca) la entrada de hoy para ``ticker``."""
    simbolo = str(ticker or "").strip().upper()
    if not simbolo:
        return

    ratios = {
        "is": res_is.get("ratios") if isinstance(res_is, dict) else None,
        "bs": res_bs.get("ratios") if isinstance(res_bs, dict) else None,
        "cf": res_cf.get("ratios") if isinstance(res_cf, dict) else None,
    }

    # Segundos, sin microsegundos: precisión uniforme en todo el fichero.
    entrada: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    }
    for etiqueta, origen, columna in KPIS_SEGUIDOS:
        entrada[etiqueta] = _ultimo_valor(ratios.get(origen), columna)

    try:
        entrada["Buffett Score"] = float(nota_buffett) if nota_buffett is not None else None
    except (TypeError, ValueError):
        entrada["Buffett Score"] = None

    puntuacion = getattr(valuequant_score, "final_score", None)
    try:
        entrada["ValueQuant Score"] = float(puntuacion) if puntuacion is not None else None
    except (TypeError, ValueError):
        entrada["ValueQuant Score"] = None

    # Si todos los KPIs vienen vacíos no hay nada que historiar: guardar la
    # entrada sólo ensuciaría el gráfico con un punto sin información.
    if all(entrada.get(etiqueta) is None for etiqueta, _, _ in KPIS_SEGUIDOS):
        return

    datos = cargar_historial_completo()
    registros = [r for r in datos.get(simbolo, []) if isinstance(r, dict)]

    hoy = entrada["timestamp"][:10]
    registros = [r for r in registros if str(r.get("timestamp", ""))[:10] != hoy]
    registros.append(entrada)
    registros.sort(key=lambda r: str(r.get("timestamp", "")))

    datos[simbolo] = registros[-MAX_ENTRADAS_POR_TICKER:]
    _guardar(datos)


def historial_ticker(ticker: str) -> pd.DataFrame:
    """Historial de un ticker como DataFrame ordenado por fecha."""
    simbolo = str(ticker or "").strip().upper()
    registros = cargar_historial_completo().get(simbolo, [])
    if not registros:
        return pd.DataFrame()

    df = pd.DataFrame(registros)
    if "timestamp" not in df.columns:
        return pd.DataFrame()

    # format="ISO8601" es obligatorio, no cosmético: sin él pandas infiere el
    # formato del primer elemento y convierte a NaT los timestamps con precisión
    # distinta (los antiguos no llevan microsegundos y los nuevos sí), de modo
    # que los registros se caían en silencio y la "evolución" mostraba menos
    # puntos de los reales.
    df["Fecha"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True, format="ISO8601")
    df = df.dropna(subset=["Fecha"]).sort_values("Fecha")
    return df.reset_index(drop=True)


def dias_desde_ultima_revision(ticker: str) -> int | None:
    """Días transcurridos desde el análisis anterior (excluyendo el de hoy).

    Devuelve ``None`` si es la primera vez que se analiza esta empresa.
    """
    df = historial_ticker(ticker)
    if df.empty:
        return None

    ahora = pd.Timestamp.now(tz="UTC")
    previos = df[df["Fecha"].dt.date < ahora.date()]
    referencia = previos["Fecha"].max() if not previos.empty else df["Fecha"].max()
    if pd.isna(referencia):
        return None
    return max(int((ahora - referencia).days), 0)


def etiqueta_ultima_revision(ticker: str) -> str:
    """Texto para el badge junto al título del ticker."""
    dias = dias_desde_ultima_revision(ticker)
    if dias is None:
        return "Primer análisis registrado"
    if dias == 0:
        return "Última revisión: hoy"
    if dias == 1:
        return "Última revisión: ayer"
    return f"Última revisión: hace {dias} días"


def _grafico_evolucion(df: pd.DataFrame, columnas: list[str]):
    """Serie temporal de los KPIs seleccionados.

    Deuda/Capital se deja fuera del mismo eje cuando conviven con porcentajes:
    mezclar un ratio 0-2x con márgenes 0-40% en un solo eje aplasta la línea de
    la deuda contra el suelo y da una lectura falsa de estabilidad. Por eso el
    selector permite elegir qué comparar, en vez de forzar un segundo eje Y.
    """
    fig = go.Figure()
    for i, columna in enumerate(columnas):
        serie = pd.to_numeric(df[columna], errors="coerce")
        if serie.dropna().empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["Fecha"],
                y=serie,
                mode="lines+markers",
                name=columna,
                line=dict(width=2, color=PLOTLY_COLORWAY[i % len(PLOTLY_COLORWAY)]),
                marker=dict(size=8),
                hovertemplate="%{x|%d/%m/%Y}<br>" + columna + ": %{y:.2f}<extra></extra>",
            )
        )

    if not fig.data:
        return None

    fig.update_layout(height=360, hovermode="x unified", legend=dict(orientation="h", y=-0.18))
    return apply_plotly_theme(fig)


def render_evolucion_kpis(ticker: str) -> None:
    """Expander «Evolución de KPIs» para el Resumen Ejecutivo."""
    df = historial_ticker(ticker)

    with st.expander("📈 Evolución de KPIs entre análisis", expanded=False):
        if df.empty or len(df) < 2:
            st.info(
                "Todavía no hay histórico suficiente para dibujar una evolución: hace falta "
                "haber analizado esta empresa en al menos dos días distintos. Este primer "
                "análisis ya ha quedado registrado."
            )
            if not df.empty:
                st.caption(f"Registros guardados: {len(df)}.")
            return

        disponibles = [
            etiqueta
            for etiqueta in [k[0] for k in KPIS_SEGUIDOS] + ["Buffett Score", "ValueQuant Score"]
            if etiqueta in df.columns and pd.to_numeric(df[etiqueta], errors="coerce").notna().any()
        ]
        if not disponibles:
            st.info("El histórico existe pero no contiene KPIs numéricos comparables.")
            return

        por_defecto = [c for c in ["ROE %", "ROIC %", "Margen Neto %"] if c in disponibles] or disponibles[:1]
        seleccion = st.multiselect(
            "KPIs a comparar",
            options=disponibles,
            default=por_defecto,
            key=f"hist_kpis_{ticker}",
            help="Se muestran en el mismo eje, así que conviene comparar magnitudes parecidas.",
        )

        if not seleccion:
            st.caption("Selecciona al menos un KPI para dibujar la evolución.")
            return

        fig = _grafico_evolucion(df, seleccion)
        if fig is None:
            st.info("Los KPIs seleccionados no tienen valores numéricos en el histórico.")
            return

        st.plotly_chart(fig, use_container_width=True)

        primero = df.iloc[0]
        ultimo = df.iloc[-1]
        columnas = st.columns(len(seleccion))
        for columna_ui, kpi in zip(columnas, seleccion):
            try:
                inicial = float(primero[kpi])
                final = float(ultimo[kpi])
                columna_ui.metric(kpi, f"{final:.2f}", f"{final - inicial:+.2f}")
            except (TypeError, ValueError):
                columna_ui.metric(kpi, "n/d")

        st.caption(
            f"{len(df)} análisis registrados entre "
            f"{df['Fecha'].min().strftime('%d/%m/%Y')} y {df['Fecha'].max().strftime('%d/%m/%Y')}. "
            "El delta compara el primer registro con el último."
        )


def render_badge_ultima_revision(ticker: str) -> None:
    """Badge discreto con la antigüedad del análisis previo."""
    st.markdown(
        f"<span class='vq-badge vq-badge-primary'>"
        f"<i class='bi bi-clock-history'></i> {etiqueta_ultima_revision(ticker)}</span>",
        unsafe_allow_html=True,
    )
