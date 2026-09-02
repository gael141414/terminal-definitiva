"""Interfaz del diario de decisiones."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modulos.config import COLOR_NEGATIVE, COLOR_POSITIVE, COLOR_TEXT_MUTED
from modulos.diario import (
    CERRADA, DESCARTADA, EJECUTADA, MOTIVOS_CIERRE, MOTIVOS_DESCARTE,
    cargar_diario, cerrar_operacion, diario_a_dataframe, operaciones_abiertas,
    registrar_decision, rendimiento_por_estrategia, rendimiento_por_motivo_cierre,
    resumen_global,
)
from modulos.utils import apply_plotly_theme


def _grafico_curva(df: pd.DataFrame):
    """Curva acumulada en R de las operaciones cerradas.

    Se muestra en R y no en euros porque el tamaño de la cuenta cambia con el
    tiempo: en R la curva refleja la calidad de las decisiones, no cuánto
    capital había disponible cuando se tomaron.
    """
    cerradas = df[(df["estado"] == CERRADA) & df["resultado_r"].notna()].copy()
    if cerradas.empty or len(cerradas) < 2:
        return None

    cerradas = cerradas.sort_values("Fecha")
    cerradas["acumulado"] = pd.to_numeric(cerradas["resultado_r"], errors="coerce").cumsum()
    final = float(cerradas["acumulado"].iloc[-1])

    fig = go.Figure(
        go.Scatter(
            x=cerradas["Fecha"], y=cerradas["acumulado"], mode="lines+markers",
            line=dict(width=2, color=COLOR_POSITIVE if final >= 0 else COLOR_NEGATIVE),
            marker=dict(size=7),
            hovertemplate="%{x|%d/%m/%Y}<br>Acumulado: %{y:+.2f}R<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color=COLOR_TEXT_MUTED, opacity=0.5)
    fig.update_layout(height=320, yaxis_title="R acumulado", showlegend=False)
    return apply_plotly_theme(fig)


def _render_abiertas() -> None:
    abiertas = operaciones_abiertas()
    st.markdown("#### 📌 Operaciones abiertas")
    if not abiertas:
        st.info("No hay operaciones abiertas anotadas. Se registran desde el escáner de swing.")
        return

    for operacion in abiertas:
        etiqueta = f"{operacion['ticker']} · {operacion.get('estrategia', 'sin estrategia')}"
        with st.expander(etiqueta):
            c1, c2, c3 = st.columns(3)
            c1.metric("Entrada", f"${float(operacion.get('precio') or 0):,.2f}")
            c2.metric("Stop", f"${float(operacion.get('stop') or 0):,.2f}")
            c3.metric("Acciones", f"{int(operacion.get('acciones') or 0):,}")

            if operacion.get("tesis"):
                st.caption(f"Tesis anotada: {operacion['tesis']}")

            s1, s2 = st.columns(2)
            with s1:
                salida = st.number_input(
                    "Precio de salida ($)", min_value=0.0, value=float(operacion.get("precio") or 0),
                    step=0.01, key=f"sal_{operacion['id']}",
                )
            with s2:
                motivo = st.selectbox("Motivo del cierre", MOTIVOS_CIERRE, key=f"mc_{operacion['id']}")

            notas = st.text_input("Qué aprendiste (opcional)", key=f"nt_{operacion['id']}")
            if st.button("Cerrar operación", key=f"cerrar_{operacion['id']}", type="primary"):
                if cerrar_operacion(operacion["id"], precio_salida=salida, motivo=motivo, notas=notas):
                    st.success("Operación cerrada y anotada.")
                    st.rerun()


def _render_analisis(df: pd.DataFrame) -> None:
    st.markdown("#### 📊 Qué te funciona a ti")
    st.caption(
        "La expectativa que publica el backtest es la de la regla ejecutada mecánicamente, y nadie "
        "opera así. Esto mide lo que realmente pasó cuando la operaste tú."
    )

    por_estrategia = rendimiento_por_estrategia(df)
    if por_estrategia.empty:
        st.info("Aún no hay operaciones cerradas. El análisis aparece en cuanto cierres la primera.")
        return

    fig = _grafico_curva(df)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Por estrategia**")
    st.dataframe(por_estrategia, use_container_width=True, hide_index=True)

    por_motivo = rendimiento_por_motivo_cierre(df)
    if not por_motivo.empty:
        st.markdown("**Por forma de salir**")
        st.dataframe(por_motivo, use_container_width=True, hide_index=True)
        st.caption(
            "Este cruce suele ser el más incómodo y el más útil: revela si cerrar por nervios está "
            "saliendo sistemáticamente más caro que dejar que salte el stop."
        )


def _render_registro_manual() -> None:
    with st.expander("✍️ Anotar una operación a mano"):
        st.caption("Para operaciones que no vengan del escáner.")
        c1, c2, c3 = st.columns(3)
        with c1:
            ticker = st.text_input("Ticker", key="diario_tk").upper().strip()
            direccion = st.radio("Dirección", ["largo", "corto"], horizontal=True, key="diario_dir")
        with c2:
            precio = st.number_input("Precio de entrada ($)", min_value=0.0, value=0.0, step=0.01, key="diario_pr")
            stop = st.number_input("Stop ($)", min_value=0.0, value=0.0, step=0.01, key="diario_st")
        with c3:
            acciones = st.number_input("Acciones", min_value=0, value=0, step=1, key="diario_ac")
            estrategia = st.text_input("Estrategia o motivo", key="diario_es")

        tesis = st.text_area("Por qué entras", key="diario_te", height=90,
                             placeholder="Qué ves, qué esperas que pase y qué invalidaría la idea...")

        if st.button("Anotar operación", type="primary", disabled=not ticker):
            registrar_decision(
                ticker, EJECUTADA, estrategia=estrategia or "manual", direccion=direccion,
                precio=precio, stop=stop, acciones=int(acciones), tesis=tesis,
            )
            st.success(f"{ticker} anotada en el diario.")
            st.rerun()


def render_diario() -> None:
    st.markdown("### 📓 Diario de decisiones")
    st.markdown(
        "El resto del terminal responde a «qué hago». Esto responde a «qué me funciona a mí», "
        "que a la larga es la pregunta más rentable. Se anotan también las operaciones **descartadas**: "
        "un diario que sólo guarda lo ejecutado nunca podrá decirte si tu filtro aporta o sólo te "
        "quita oportunidades."
    )

    df = diario_a_dataframe()
    resumen = resumen_global(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Anotaciones", resumen["total"])
    c2.metric("Abiertas", resumen["ejecutadas"])
    c3.metric("Cerradas", resumen["cerradas"])
    c4.metric(
        "Expectativa real",
        f"{resumen['expectativa_r']:+.3f}R" if resumen["expectativa_r"] is not None else "n/d",
        help="Resultado medio por operación cerrada, medido en unidades de riesgo.",
    )
    c5.metric(
        "Descartadas",
        f"{resumen['ratio_descarte']:.0f}%" if resumen["ratio_descarte"] is not None else "n/d",
        help="Porcentaje de señales consideradas que decidiste no operar.",
    )

    st.markdown("---")
    _render_registro_manual()

    st.markdown("---")
    _render_abiertas()

    if not df.empty:
        st.markdown("---")
        _render_analisis(df)

        with st.expander("📄 Historial completo"):
            columnas = [c for c in ["Fecha", "ticker", "estado", "estrategia", "precio",
                                    "stop", "acciones", "resultado_r", "motivo", "motivo_cierre"]
                        if c in df.columns]
            st.dataframe(df[columnas], use_container_width=True, hide_index=True)
