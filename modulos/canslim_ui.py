"""Interfaz del escáner CAN SLIM dentro del apartado de swing."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from modulos.canslim import ADVERTENCIA_EVIDENCIA, ResultadoCanSlim
from modulos.canslim_screener import candidatos_a_dataframe, escanear_canslim
from modulos.config import (
    COLOR_ACCENT, COLOR_NEGATIVE, COLOR_POSITIVE, COLOR_TEXT_MUTED, COLOR_WARNING,
)
from modulos.swing_riesgo import construir_plan

_ESTADO = "vq_canslim_resultado"


def _render_estado_mercado(mercado: dict) -> None:
    """Criterio M con la mecánica original: distribución y confirmación."""
    if not mercado.get("disponible"):
        st.warning("No se pudo leer el estado del mercado; el criterio M queda sin evaluar.")
        return

    distribucion = mercado.get("distribucion", {})
    confirmacion = mercado.get("confirmacion", {})
    estado = distribucion.get("estado", "sin_datos")
    dias = distribucion.get("dias", 0)

    color = {"sano": COLOR_POSITIVE, "bajo presión": COLOR_WARNING, "corrección probable": COLOR_NEGATIVE}.get(
        estado, COLOR_TEXT_MUTED
    )

    st.markdown(
        f"""
        <div style="background:#121926; border:1px solid rgba(147,164,187,0.35);
                    border-left:4px solid {color}; border-radius:10px; padding:16px 20px; margin-bottom:12px;">
            <div style="font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:{COLOR_TEXT_MUTED};">
                Criterio M · dirección del mercado
            </div>
            <div style="font-size:19px; font-weight:800; color:{color}; margin-top:4px;">
                {dias} día(s) de distribución · mercado {estado}
            </div>
            <div style="color:#93a4bb; font-size:13.5px; margin-top:6px; line-height:1.5;">
                Un día de distribución es una sesión en la que el índice cae con MÁS volumen que la
                víspera: mover el índice a la baja con volumen creciente no lo hace el minorista.
                A partir de 4 el mercado queda «bajo presión»; a partir de 6 suele venir corrección.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        if confirmacion.get("encontrado"):
            c1.success(
                f"✅ Día de confirmación el {pd.Timestamp(confirmacion['fecha']).date()} "
                f"({confirmacion['subida_pct']:+.1f}% con volumen creciente), "
                f"hace {confirmacion['sesiones_desde']} sesiones."
            )
        else:
            c1.info("Sin día de confirmación reciente: no hay permiso de compra según el método.")
    with c2:
        if mercado.get("permiso_compra"):
            c2.success("🟢 O'Neil permitiría comprar en este contexto.")
        else:
            c2.error(
                "🔴 O'Neil NO compraría ahora. Su regla es tajante: al menos la mitad del resultado "
                "de una operación depende del mercado general."
            )


def _render_letras(resultado: ResultadoCanSlim) -> None:
    """Las siete letras como fichas de color."""
    piezas = []
    for letra in "CANSLIM":
        criterio = resultado.criterios.get(letra)
        if criterio is None or not criterio.evaluable:
            color, fondo = COLOR_TEXT_MUTED, "rgba(147,164,187,0.10)"
        elif criterio.cumple:
            color, fondo = COLOR_POSITIVE, "rgba(61,220,151,0.14)"
        else:
            color, fondo = COLOR_NEGATIVE, "rgba(243,108,108,0.12)"
        piezas.append(
            f"<span style='display:inline-block; width:30px; height:30px; line-height:30px;"
            f" text-align:center; margin-right:5px; border-radius:6px; font-weight:800;"
            f" background:{fondo}; color:{color};'>{letra}</span>"
        )
    st.markdown("".join(piezas), unsafe_allow_html=True)


def _render_candidato(resultado: ResultadoCanSlim, capital: float, riesgo_pct: float) -> None:
    base = resultado.base
    ruptura = resultado.ruptura
    titulo = f"{resultado.ticker} · {resultado.cumplidos}/{resultado.evaluados} criterios"
    if resultado.rs_rating is not None:
        titulo += f" · RS {resultado.rs_rating:.0f}"

    with st.expander(titulo):
        _render_letras(resultado)
        st.markdown("")

        for letra in "CANSLIM":
            criterio = resultado.criterios.get(letra)
            if criterio is None:
                continue
            if not criterio.evaluable:
                icono, color = "·", COLOR_TEXT_MUTED
            elif criterio.cumple:
                icono, color = "✓", COLOR_POSITIVE
            else:
                icono, color = "✗", COLOR_NEGATIVE
            valor = f" — **{criterio.valor}**" if criterio.valor else ""
            st.markdown(
                f"<span style='color:{color}; font-weight:700;'>{icono} {criterio.letra}</span> "
                f"{criterio.nombre}{valor}<br>"
                f"<span style='color:#93a4bb; font-size:12.5px;'>{criterio.detalle}</span>",
                unsafe_allow_html=True,
            )

        if base is not None:
            st.markdown("---")
            st.markdown("**La base y su punto de compra**")
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Figura", base.nombre)
            b2.metric("Pivote", f"${base.pivote:,.2f}",
                      help="Punto de compra: el máximo de la consolidación.")
            desde, hasta = base.zona_compra()
            b3.metric("Zona de compra", f"${desde:,.2f}–{hasta:,.2f}",
                      help="Hasta un 5% sobre el pivote. Por encima, la entrada es 'extended'.")
            b4.metric("Objetivo medido", f"${base.objetivo_medido():,.2f}",
                      help="Proyecta la profundidad de la base desde el pivote.")
            st.caption(
                f"Consolidación de {base.semanas:.0f} semanas con una corrección del "
                f"{base.profundidad_pct:.1f}%, tras un avance previo del {base.avance_previo_pct:.0f}%."
            )

            if ruptura is not None:
                if ruptura.fallida:
                    st.error(f"⚠️ {ruptura.estado}. No es una compra.")
                elif ruptura.extendida:
                    st.warning(f"⚠️ {ruptura.estado}. Perseguir una ruptura extendida es una causa clásica de stop.")
                else:
                    st.success(f"✅ {ruptura.estado}, con volumen {ruptura.volumen_relativo:.1f}x la media.")

            # Plan de riesgo con los parámetros del propio O'Neil para swing.
            precio = ruptura.precio if ruptura is not None else base.pivote
            st.markdown("**Plan de la operación**")
            modo = st.radio(
                "Parámetros",
                ["Swing (stop 3%, objetivo 8%)", "Clásico (stop 7%, objetivo 22%)"],
                horizontal=True, key=f"modo_{resultado.ticker}",
            )
            stop_pct, objetivo_pct = (0.03, 0.08) if modo.startswith("Swing") else (0.07, 0.22)
            stop = precio * (1 - stop_pct)
            objetivo = precio * (1 + objetivo_pct)
            riesgo_accion = precio - stop
            acciones = int((capital * riesgo_pct / 100.0) // riesgo_accion) if riesgo_accion > 0 else 0

            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Entrada", f"${precio:,.2f}")
            p2.metric("Stop", f"${stop:,.2f}", f"-{stop_pct*100:.0f}%", delta_color="inverse")
            p3.metric("Objetivo", f"${objetivo:,.2f}", f"+{objetivo_pct*100:.0f}%")
            p4.metric("Acciones", f"{acciones:,}", f"riesgo {acciones*riesgo_accion:,.0f}€")
            st.caption(
                f"Relación beneficio/riesgo ≈ 1:{objetivo_pct/stop_pct:.1f}. O'Neil era tajante con el "
                "stop: «el secreto no es tener razón siempre, sino perder lo mínimo cuando te equivocas»."
            )


def render_canslim() -> None:
    st.markdown("#### Escáner CAN SLIM")
    st.markdown(
        "Los siete criterios de William O'Neil aplicados sobre el mercado: crecimiento de beneficios "
        "(**C**, **A**), ruptura de una base con nuevos máximos (**N**), oferta y volumen (**S**), "
        "liderazgo por fuerza relativa (**L**), respaldo institucional (**I**) y dirección del "
        "mercado (**M**)."
    )
    st.info(ADVERTENCIA_EVIDENCIA)

    col_a, col_b, col_c = st.columns([1.5, 1, 1])
    with col_a:
        origen = st.radio("Universo", ["Mercado (muestra)", "Mi watchlist", "Lista personalizada"], horizontal=True)
    with col_b:
        capital = st.number_input("Capital (€)", min_value=500.0, value=10_000.0, step=500.0, key="cs_cap")
    with col_c:
        riesgo_pct = st.number_input("Riesgo por operación (%)", min_value=0.1, max_value=5.0,
                                     value=1.0, step=0.1, key="cs_riesgo")

    tickers: list[str] = []
    if origen == "Mercado (muestra)":
        limite = st.select_slider("Tamaño de la muestra", options=[100, 250, 500, 750], value=250)
        from modulos.swing_ui import _universo_mercado

        tickers = _universo_mercado(limite)
        st.caption(
            f"{len(tickers)} valores. El RS Rating es un ranking relativo: cuanto mayor sea el "
            "universo, más significativo es."
        )
    elif origen == "Mi watchlist":
        from modulos.swing_ui import _universo_watchlist

        tickers = _universo_watchlist()
        if len(tickers) < 20:
            st.warning(
                "El RS Rating necesita al menos 20 valores para significar algo: con una watchlist "
                "corta ese criterio quedará sin evaluar."
            )
    else:
        texto = st.text_area("Tickers separados por comas", "NVDA, AAPL, MSFT, META, AMD, GOOGL, AMZN, NFLX")
        tickers = [t.strip().upper() for t in texto.split(",") if t.strip()]

    f1, f2, f3 = st.columns(3)
    with f1:
        rs_minimo = st.slider("RS Rating mínimo", 50, 95, 80, 5,
                              help="O'Neil compraba a partir de 80, idealmente 90.")
    with f2:
        minimo_criterios = st.slider("Criterios mínimos a cumplir", 3, 7, 5)
    with f3:
        st.markdown("<div style='height:1.72rem;'></div>", unsafe_allow_html=True)
        exigir_ruptura = st.checkbox("Sólo rupturas confirmadas", value=False,
                                     help="Exige que el precio haya roto el pivote de una base con volumen.")

    if st.button("🎯 Buscar candidatos CAN SLIM", type="primary", use_container_width=True, disabled=not tickers):
        barra = st.progress(0.0, text="Iniciando...")
        resultado = escanear_canslim(
            tickers, rs_minimo=float(rs_minimo), exigir_ruptura=exigir_ruptura,
            minimo_criterios=int(minimo_criterios), progreso=barra,
        )
        barra.empty()
        st.session_state[_ESTADO] = resultado

    resultado = st.session_state.get(_ESTADO)
    if resultado is None:
        st.info("Configura el universo y pulsa «Buscar candidatos CAN SLIM».")
        return

    st.markdown("---")
    _render_estado_mercado(resultado.mercado)

    m1, m2, m3 = st.columns(3)
    m1.metric("Valores analizados", f"{resultado.universo_analizado}/{resultado.universo_solicitado}")
    m2.metric("Pasan el filtro técnico", resultado.supervivientes_tecnicos)
    m3.metric("Candidatos finales", len(resultado.candidatos))

    for aviso in resultado.avisos:
        st.info(aviso)

    if not resultado.candidatos:
        return

    st.markdown(f"##### {len(resultado.candidatos)} candidato(s)")
    st.caption("Las letras en verde cumplen el criterio; en rojo no; en gris no hay datos para juzgarlo.")

    for candidato in resultado.candidatos:
        _render_candidato(candidato, capital, riesgo_pct)

    with st.expander("📄 Tabla resumen"):
        df = candidatos_a_dataframe(resultado)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
