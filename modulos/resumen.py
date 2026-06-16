import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from charts import plot_anillo_puntuacion, plot_dashboard_interactivo, plot_football_field
from modulos.utils import renderizar_grafico_tradingview, escanear_vulnerabilidades
from modulos.scoring_engine import render_valuequant_score_card

# Importa tus gráficos personalizados si los usas aquí
from charts import plot_dashboard_interactivo, plot_calidad_beneficios 

def ejecutar_resumen_ejecutivo(ticker_input, is_df, bs_df, cf_df, res_is, res_bs, res_cf, res_val, nota_buffett, valuequant_score=None):
    """Muestra la vista general, KPIs principales y dashboard interactivo de la empresa."""
    st.markdown(f"### 📊 Resumen Ejecutivo: {ticker_input}")
    
    # ======== HERO SECTION & SCORECARD ========
    precio_mercado = res_val.get('precio_actual', 0) if res_val else 0

    col_hero1, col_hero2, col_hero3 = st.columns([2, 1, 1])
    
    with col_hero1:
        st.markdown(f"<h1 style='font-size: 3.5rem; margin-bottom: 0px;'>{ticker_input}</h1>", unsafe_allow_html=True)
        st.caption("Value Intelligence Terminal | Análisis Cuantitativo")
    
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
    
    st.markdown("#### 📊 Scorecard Ejecutivo")
    
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
    sc1.metric("ROE (Rentabilidad)", f"{sc_roe:.1f}%" if sc_roe else "N/A", "Aprobado" if sc_roe and sc_roe > 15 else "Bajo")
    sc2.metric("ROIC (Calidad)", f"{sc_roic:.1f}%" if sc_roic else "N/A", "Aprobado" if sc_roic and sc_roic > 15 else "Bajo")
    sc3.metric("FCF Último Año", f"${sc_fcf:.1f}B" if sc_fcf else "N/A", "Genera Caja" if sc_fcf and sc_fcf > 0 else "Quema Caja")
    sc4.metric("Deuda / Capital", f"{sc_deuda:.2f}x" if sc_deuda else "N/A", "Sano" if sc_deuda and sc_deuda < 0.8 else "Peligro", delta_color="inverse")

    st.markdown("### 📈 Gráfico Interactivo Pro")
    renderizar_grafico_tradingview(ticker_input)

    # ======== VEREDICTO ========
    if res_val and precio_mercado:
        v_justo = res_val.get('dcf_value') or res_val.get('epv_value') or res_val.get('graham_value', 0)
        margen_seguridad = ((precio_mercado - v_justo) / v_justo) * 100 if v_justo > 0 else 0
        estado_precio = "Infravalorada (Descuento)" if margen_seguridad < 0 else "Sobrevalorada (Prima)"
    else:
        estado_precio = "Datos insuficientes"
    
    st.subheader("🧠 Veredicto del Algoritmo")
    
    nota_global = valuequant_score.final_score if valuequant_score is not None else nota_buffett
    confianza = valuequant_score.confidence if valuequant_score is not None else 1.0

    if nota_global >= 80:
        st.success(
            f"**Tesis de alta calidad:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. Combina calidad, valoración, riesgo, crecimiento, "
            f"momentum y contexto macro. Estado actual: **{estado_precio}**. "
            f"Confianza del modelo: {confianza*100:.0f}%."
        )
    elif nota_global >= 65:
        st.info(
            f"**Empresa atractiva con matices:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. La tesis es razonable, pero conviene revisar valoración, "
            f"riesgos y catalizadores. Estado actual: **{estado_precio}**. "
            f"Confianza del modelo: {confianza*100:.0f}%."
        )
    elif nota_global >= 50:
        st.warning(
            f"**Tesis neutral/exigente:** {ticker_input} obtiene un ValueQuant Score de "
            f"{nota_global:.1f}/100. Hay fortalezas, pero no suficientes para una lectura "
            f"claramente favorable. Estado actual: **{estado_precio}**. "
            f"Confianza del modelo: {confianza*100:.0f}%."
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
    st.markdown("### 🔎 Auditoría de Puntos Débiles (Bear Case)")
    
    alertas_detectadas = escanear_vulnerabilidades(res_is, res_bs, res_cf)
    
    if len(alertas_detectadas) == 0:
        st.success("✅ **Foso Económico Intacto:** El escáner no ha detectado vulnerabilidades estructurales graves a nivel contable en el último año.")
    else:
        st.error(f"Se han detectado **{len(alertas_detectadas)} vulnerabilidades críticas** que debes investigar:")
        for alerta in alertas_detectadas:
            st.markdown(f"- {alerta}")
    
    st.markdown("<br>", unsafe_allow_html=True)
