"""Interfaz de la decisión de venta sobre una posición abierta."""

from __future__ import annotations

from datetime import date

import streamlit as st

from modulos.config import (
    PERFIL_LARGO_PLAZO, PERFIL_SWING, UMBRAL_REDUCIR, UMBRAL_VENDER,
)
from modulos.decision_venta import (
    ADVERTENCIA_EVIDENCIA, MANTENER, REDUCIR, VENDER, DecisionVenta, decidir_venta,
)
from modulos.html_markdown import escribir_html
from modulos.ui_components import render_kpi_card

ETIQUETAS_PERFIL = {
    PERFIL_LARGO_PLAZO: "Largo plazo (valoración y negocio pesan más)",
    PERFIL_SWING: "Swing (el precio manda)",
}

COLOR_ACCION = {
    MANTENER: ("#10e39a", "rgba(16,227,154,.12)"),
    REDUCIR: ("#fbbf24", "rgba(251,191,36,.12)"),
    VENDER: ("#fb5e6d", "rgba(251,94,109,.12)"),
}


def _render_veredicto(decision: DecisionVenta) -> None:
    color, fondo = COLOR_ACCION.get(decision.accion, ("#93a4bb", "rgba(147,164,187,.12)"))
    detalle = (
        f"Soltar el {decision.reducir_pct:.0f}% de la posición"
        if decision.accion == REDUCIR
        else "Vender la posición completa" if decision.accion == VENDER
        else "No tocar la posición"
    )
    puntuacion = (f"{decision.sell_score:.0f}/100" if decision.sell_score is not None
                  else "sin puntuación")

    escribir_html(f"""
        <div style="border:1px solid {color}55; border-left:4px solid {color};
                    background:{fondo}; border-radius:12px; padding:20px 24px;">
            <div style="font-size:11px; letter-spacing:.12em; text-transform:uppercase;
                        color:#93a4bb;">Veredicto · {decision.ticker}</div>
            <div style="display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; margin-top:6px;">
                <span style="font-family:'JetBrains Mono',monospace; font-size:34px;
                             font-weight:800; color:{color};">{decision.accion}</span>
                <span style="color:#e8edf5; font-size:15px;">{detalle}</span>
                <span style="margin-left:auto; font-family:'JetBrains Mono',monospace;
                             color:#93a4bb; font-size:13px;">sell score {puntuacion}</span>
            </div>
        </div>
    """)


def _render_pilares(decision: DecisionVenta) -> None:
    st.markdown("##### Los tres pilares")
    st.caption(
        "0 significa ninguna razón para vender; 100, todas. Un pilar sin datos no "
        "puntúa cero: se excluye y los pesos se reparten entre los demás."
    )
    columnas = st.columns(3)
    etiquetas = {
        "valoracion": ("Valoración", "Distancia entre precio y valor, y múltiplos frente a su historia."),
        "fundamentales": ("Fundamentales", "Piotroski, Altman y Beneish sobre las cuentas."),
        "tecnico": ("Técnico", "Medias, RSI y sobreextensión, ajustados al régimen."),
    }
    for columna, (clave, (titulo, ayuda)) in zip(columnas, etiquetas.items()):
        with columna:
            valor = decision.sub_scores.get(clave)
            if valor is None:
                render_kpi_card(titulo, None, detail="Sin datos suficientes para este pilar.")
            else:
                estado = ("riesgo" if valor >= UMBRAL_VENDER
                          else "advertencia" if valor >= UMBRAL_REDUCIR else "favorable")
                render_kpi_card(titulo, f"{valor:.0f}", status=estado, detail=ayuda)


def _render_precios(decision: DecisionVenta) -> None:
    if decision.precio_objetivo_trim is None:
        return
    st.markdown("##### Precios de referencia")
    a, b, c = st.columns(3)
    with a:
        render_kpi_card("Precio actual",
                        f"${decision.precio_actual:,.2f}" if decision.precio_actual else None,
                        detail="Cotización de mercado.")
    with b:
        render_kpi_card("Recortar por encima de", f"${decision.precio_objetivo_trim:,.2f}",
                        status="advertencia", detail="A partir del valor razonable.")
    with c:
        render_kpi_card("Vender por encima de", f"${decision.precio_objetivo_venta:,.2f}",
                        status="riesgo", detail="Sobrevaloración que ya no compensa.")


def render_decision_venta() -> None:
    """Pantalla completa: posición de entrada y veredicto."""
    st.markdown("### Decisión de venta")
    st.caption(
        "Para una posición que YA tienes abierta: mantener, reducir o vender, "
        "combinando valoración, deterioro del negocio y técnica."
    )

    st.warning(ADVERTENCIA_EVIDENCIA, icon="⚠")

    with st.form("vq_decision_venta"):
        c1, c2, c3, c4 = st.columns([1.4, 1, 1, 1.2])
        with c1:
            ticker = st.text_input("Ticker", value="AAPL", placeholder="AAPL")
        with c2:
            entrada = st.number_input("Precio de entrada", min_value=0.0, value=0.0, step=1.0,
                                      help="Déjalo en 0 si no quieres evaluar el stop.")
        with c3:
            peso = st.number_input("Peso en cartera (%)", min_value=0.0, max_value=100.0,
                                   value=0.0, step=1.0)
        with c4:
            fecha = st.date_input("Fecha de entrada", value=None, format="DD/MM/YYYY")

        perfil = st.radio("Perfil", list(ETIQUETAS_PERFIL),
                          format_func=lambda k: ETIQUETAS_PERFIL[k], horizontal=True)
        enviado = st.form_submit_button("Evaluar posición", type="primary",
                                        use_container_width=True)

    if not enviado:
        st.info("Introduce la posición y pulsa «Evaluar posición».")
        return

    if not (ticker or "").strip():
        st.error("Hace falta un ticker.")
        return

    with st.spinner(f"Reuniendo datos de {ticker.upper()}…"):
        try:
            decision = decidir_venta(
                ticker,
                entrada=float(entrada) or None,
                fecha_entrada=fecha if isinstance(fecha, date) else None,
                peso_cartera=float(peso) or None,
                perfil=perfil,
            )
        except Exception as exc:  # la pantalla nunca debe romperse entera
            st.error(f"No se pudo evaluar {ticker.upper()}: {exc}")
            return

    _render_veredicto(decision)
    st.markdown("")
    _render_pilares(decision)
    _render_precios(decision)

    if decision.triggers:
        st.markdown("##### Qué lo ha disparado")
        for trigger in decision.triggers:
            st.markdown(f"- {trigger}")

    if decision.avisos:
        st.markdown("##### Lo que no se ha podido mirar")
        for aviso in decision.avisos:
            st.caption(aviso)

    with st.expander("Explicación completa", expanded=False):
        st.write(decision.explicacion)

    _guardar(decision)


def _guardar(decision: DecisionVenta) -> None:
    """Deja constancia en el historial, como el resto de análisis."""
    try:
        from modulos.analysis_store import save_analysis_snapshot

        save_analysis_snapshot({
            "ticker": decision.ticker,
            "tipo": "decision_venta",
            "accion": decision.accion,
            "sell_score": decision.sell_score,
            "sub_scores": decision.sub_scores,
            "reducir_pct": decision.reducir_pct,
        })
    except Exception:
        # El historial es una ayuda, nunca un bloqueo para ver el veredicto.
        pass
