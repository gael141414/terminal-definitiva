import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from charts import plot_anillo_puntuacion, plot_dashboard_interactivo, plot_football_field
from modulos.config import DEBT_EQUITY_RED_FLAG, DEBT_EQUITY_WARNING
from modulos.utils import renderizar_grafico_tradingview, escanear_vulnerabilidades
from modulos.scoring_engine import render_valuequant_score_card
from modulos.ui_components import kpi_status_from_thresholds, render_kpi_card
from modulos.historial import (
    registrar_analisis,
    render_badge_ultima_revision,
    render_evolucion_kpis,
)

# Importa tus gráficos personalizados si los usas aquí
from charts import plot_dashboard_interactivo, plot_calidad_beneficios 

def ejecutar_resumen_ejecutivo(ticker_input, is_df, bs_df, cf_df, res_is, res_bs, res_cf, res_val, nota_buffett, valuequant_score=None):
    """Muestra la vista general, KPIs principales y dashboard interactivo de la empresa."""
    st.markdown(f"### Resumen Ejecutivo: {ticker_input}")

    # El registro va ANTES de pintar el badge: así "Última revisión" compara
    # contra el análisis anterior y no contra el que se acaba de guardar.
    dias_previos = None
    try:
        from modulos.historial import dias_desde_ultima_revision

        dias_previos = dias_desde_ultima_revision(ticker_input)
        registrar_analisis(ticker_input, res_is, res_bs, res_cf, nota_buffett, valuequant_score)
    except Exception:
        # El historial es una ayuda, nunca un bloqueo para ver la ficha.
        pass

    # ======== HERO SECTION & SCORECARD ========
    precio_mercado = res_val.get('precio_actual', 0) if res_val else 0

    col_hero1, col_hero2, col_hero3 = st.columns([2, 1, 1])
    
    with col_hero1:
        st.markdown(f"<h1 style='font-size: 3.5rem; margin-bottom: 0px;'>{ticker_input}</h1>", unsafe_allow_html=True)
        st.caption("Value Intelligence Terminal | Análisis Cuantitativo")
        try:
            render_badge_ultima_revision(ticker_input) if dias_previos is None else st.markdown(
                "<span class='vq-badge vq-badge-primary'><i class='bi bi-clock-history'></i> "
                + ("Última revisión: hoy" if dias_previos == 0
                   else "Última revisión: ayer" if dias_previos == 1
                   else f"Última revisión: hace {dias_previos} días")
                + "</span>",
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    
    with col_hero2:
        st.metric("Precio de Mercado", f"${precio_mercado:.2f}" if precio_mercado else "N/A")
    
    with col_hero3:
        if valuequant_score is not None:
            render_valuequant_score_card(valuequant_score)
        else:
            fig_score_hero = plot_anillo_puntuacion(
                nota_buffett,
                100,
                "Buffett Score (Calidad)",
                "#00C0F2"
            )
            st.plotly_chart(fig_score_hero, use_container_width=True)
    
    st.markdown("#### Scorecard Ejecutivo")
    
    # Función auxiliar rápida para el scorecard
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else None
        return None
    
    sc_roe = get_last(res_bs["ratios"], "ROE %")
    sc_roic = get_last(res_bs["ratios"], "ROIC %")
    sc_fcf = get_last(res_cf["ratios"], "Free Cash Flow (B USD)")
    sc_deuda = get_last(res_bs["ratios"], "Deuda / Capital")

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        # ROE se muestra en estado "normal" (sin juicio de valor), igual que
        # el ejemplo del propio mockup: informativo, no hay un umbral único
        # y objetivo para "ROE bueno" salvo el que ya cubre ROIC.
        render_kpi_card(
            "ROE (Rentabilidad)",
            f"{sc_roe:.1f}%" if sc_roe is not None else None,
            detail="Retorno sobre patrimonio, último año." if sc_roe is not None else "",
            tag="TTM",
        )
    with sc2:
        roic_favorable = sc_roic is not None and sc_roic > 15
        render_kpi_card(
            "ROIC (Calidad)",
            f"{sc_roic:.1f}%" if sc_roic is not None else None,
            status="favorable" if roic_favorable else "normal",
            detail="Supera el 15%: crea valor por encima del coste de capital." if sc_roic is not None else "",
        )
    with sc3:
        fcf_favorable = sc_fcf is not None and sc_fcf >= 0
        render_kpi_card(
            "FCF Último Año",
            f"${sc_fcf:.1f}B" if sc_fcf is not None else None,
            status="favorable" if fcf_favorable else ("riesgo" if sc_fcf is not None else "normal"),
            detail=("Genera caja real." if fcf_favorable else "Quema de caja: revisar sostenibilidad.") if sc_fcf is not None else "",
        )
    with sc4:
        deuda_status = kpi_status_from_thresholds(sc_deuda, warning=DEBT_EQUITY_WARNING, danger=DEBT_EQUITY_RED_FLAG)
        deuda_detail = {
            "normal": "Apalancamiento moderado.",
            "advertencia": f"Entre el aviso ({DEBT_EQUITY_WARNING}x) y el umbral crítico ({DEBT_EQUITY_RED_FLAG}x).",
            "riesgo": f"Supera el umbral crítico de {DEBT_EQUITY_RED_FLAG}x — red flag.",
            "no_disponible": "",
        }.get(deuda_status, "")
        render_kpi_card(
            "Deuda / Capital",
            f"{sc_deuda:.2f}x" if sc_deuda is not None else None,
            status=deuda_status,
            detail=deuda_detail,
        )

    # El scorecard de arriba es una foto fija del último ejercicio; esto añade
    # la dimensión que le falta: si esos mismos ratios mejoran o empeoran
    # respecto a las veces anteriores que se analizó la empresa.
    try:
        render_evolucion_kpis(ticker_input)
    except Exception:
        pass

    st.markdown("### Gráfico Interactivo Pro")
    renderizar_grafico_tradingview(ticker_input)

    # ======== VEREDICTO ========
    # Convención unificada de margen de seguridad: (fair_value - price) / price
    # (misma que modulos/scoring_engine.py y modulos/investment_thesis.py/Tesis/
    # Watchlist ya usaban). Antes aquí era (price - fair_value) / fair_value:
    # signo y denominador contrarios al resto de la app.
    v_justo = res_val.get('dcf_value') or res_val.get('epv_value') or res_val.get('graham_value') if res_val else None
    if res_val and precio_mercado and v_justo:
        margen_seguridad = ((v_justo - precio_mercado) / precio_mercado) * 100
        estado_precio = "Infravalorada (Descuento)" if margen_seguridad > 0 else "Sobrevalorada (Prima)"
    else:
        estado_precio = "Datos insuficientes"
    
    st.subheader("Veredicto del Algoritmo")
    
    nota_global = valuequant_score.final_score if valuequant_score is not None else nota_buffett
    # Sin ValueQuantScore no hay confianza que declarar. Antes se ponía 1.0 y la
    # pantalla imprimía "Confianza del modelo: 100%" justo cuando NO había
    # modelo: la ausencia de información presentada como certeza máxima.
    confianza = valuequant_score.confidence if valuequant_score is not None else None
    texto_confianza = (
        f"Confianza del modelo: {confianza * 100:.0f}%."
        if confianza is not None
        else "Sin ValueQuant Score: la nota es el Buffett Score histórico, sin confianza asociada."
    )

    if nota_global >= 80:
        st.success(
            f"**Tesis de alta calidad:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. Combina calidad, valoración, riesgo, crecimiento, "
            f"momentum y contexto macro. Estado actual: **{estado_precio}**. "
            f"{texto_confianza}"
        )
    elif nota_global >= 65:
        st.info(
            f"**Empresa atractiva con matices:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. La tesis es razonable, pero conviene revisar valoración, "
            f"riesgos y catalizadores. Estado actual: **{estado_precio}**. "
            f"{texto_confianza}"
        )
    elif nota_global >= 50:
        st.warning(
            f"**Tesis neutral/exigente:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. Hay fortalezas, pero no suficientes para una lectura "
            f"claramente favorable. Estado actual: **{estado_precio}**. "
            f"{texto_confianza}"
        )
    else:
        st.error(
            f"**Riesgo de inversión elevado:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. La máquina detecta deterioro, precio exigente o riesgo "
            f"operativo/financiero significativo."
        )

    st.caption(
        f"Buffett Quality Score histórico: {nota_buffett}/100. "
        f"Esta subnota mide solo calidad fundamental, no oportunidad total de inversión."
    )
    
    st.markdown("<br>", unsafe_allow_html=True) # Espacio antes de las pestañas

    # ======== VULNERABILIDADES ========
    st.markdown("### Auditoría de Puntos Débiles (Bear Case)")
    
    alertas_detectadas = escanear_vulnerabilidades(res_is, res_bs, res_cf)
    
    if len(alertas_detectadas) == 0:
        st.success("**Foso Económico Intacto:** El escáner no ha detectado vulnerabilidades estructurales graves a nivel contable en el último año.")
    else:
        st.error(f"Se han detectado **{len(alertas_detectadas)} vulnerabilidades críticas** que debes investigar:")
        for alerta in alertas_detectadas:
            st.markdown(f"- {alerta}")
    
    st.markdown("<br>", unsafe_allow_html=True)
