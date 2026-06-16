import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from charts import plot_beneish_m_score, plot_auditoria_forense
from modulos.utils import analizar_sentimiento_noticias

def ejecutar_auditoria_forense(ticker_input, is_df, bs_df, cf_df, res_val, res_bs):
    """Detector de manipulación contable y riesgo de quiebra (Altman Z-Score y Beneish M-Score)"""

    st.markdown("#### ⚖️ Salud del Balance (Termómetro de Deuda)")
    st.caption("Una deuda/capital superior a 0.8 indica que la empresa depende excesivamente de financiación externa.")
    
    # Extraer el último dato válido de Deuda/Capital de res_bs
    try:
        ultima_deuda_capital = res_bs["ratios"]["Deuda / Capital"].dropna().iloc[-1]
        fig_deuda = plot_termometro_deuda(ultima_deuda_capital)
        if fig_deuda:
            st.plotly_chart(fig_deuda, use_container_width=True)
    except Exception as e:
        st.info("Datos de deuda insuficientes para generar el termómetro.")

    st.markdown("---")
    st.markdown("#### 🚨 Auditoría Forense y Riesgo de Quiebra (Altman Z-Score)")
    st.caption("Un modelo institucional para detectar estrés financiero y manipulación antes de que Wall Street se dé cuenta.")
    
    if res_val and res_val.get('precio_actual') and res_val.get('acciones_actuales'):
        with st.spinner("Realizando auditoría contable profunda..."):
            fig_zscore, alertas_forenses, valor_z = plot_auditoria_forense(
                ticker_input, 
                res_val['precio_actual'], 
                res_val['acciones_actuales']
            )
            
            if fig_zscore:
                col_z1, col_z2 = st.columns([1, 1.5])
                
                with col_z1:
                    st.plotly_chart(fig_zscore, use_container_width=True)
                    if valor_z < 1.8:
                        st.error("**ESTADO CRÍTICO:** Alta probabilidad estadística de quiebra en los próximos 2 años.")
                    elif valor_z < 3.0:
                        st.warning("**ZONA GRIS:** Precaución. La empresa tiene algunas tensiones en el balance.")
                    else:
                        st.success("**ZONA SEGURA:** Balance acorazado. Riesgo de quiebra prácticamente nulo.")
                        
                with col_z2:
                    st.markdown("##### 🚩 Banderas Rojas Detectadas")
                    if not alertas_forenses:
                        st.success("✅ **Auditoría Limpia:** No se han detectado anomalías graves de liquidez, dividendos o cobertura de intereses. Los estados financieros parecen íntegros.")
                    else:
                        for alerta in alertas_forenses:
                            st.markdown(alerta)
    else:
        st.info("Faltan datos de precio o acciones en circulación para calcular el Z-Score.")

    st.markdown("---")
    st.markdown("#### 🕵️ Módulo Forense Avanzado: Beneish M-Score (Manipulación Contable)")
    st.caption("Mientras el Z-Score mide la probabilidad de quiebra, el M-Score busca anomalías entre los devengos, la depreciación y las cuentas por cobrar para detectar si la directiva está inflando los beneficios artificialmente (Caso Enron).")
    
    with st.spinner("Cruzando las matrices contables de los últimos 24 meses..."):
        fig_mscore, diag_mscore, detalles_mscore = plot_beneish_m_score(ticker_input)
        
        if fig_mscore:
            col_m1, col_m2 = st.columns([1, 1.2])
            
            with col_m1:
                st.plotly_chart(fig_mscore, use_container_width=True)
                
            with col_m2:
                st.markdown("##### Veredicto del Algoritmo:")
                if "ALERTA" in diag_mscore:
                    st.error(diag_mscore)
                elif "ADVERTENCIA" in diag_mscore:
                    st.warning(diag_mscore)
                else:
                    st.success(diag_mscore)
                    
                if detalles_mscore:
                    st.markdown("##### 🚩 Banderas Ocultas Detectadas:")
                    for alerta in detalles_mscore:
                        st.write(alerta)
                else:
                    st.write("✔️ Todos los sub-índices (Calidad de activos, depreciación, devengos) fluyen con normalidad.")
        else:
            st.info(diag_mscore)

    st.markdown("---")
    st.markdown("#### 🤖 Escáner de Sentimiento con IA (Módulo NLP)")
    st.caption("El algoritmo lee las noticias financieras de los últimos días y analiza la lingüística de los titulares para detectar optimismo institucional o pánico mediático.")
    
    with st.spinner("Leyendo las últimas noticias con Inteligencia Artificial..."):
        noticias_nlp, sentimiento_global = analizar_sentimiento_noticias(ticker_input)
        
        if noticias_nlp:
            c_nlp1, c_nlp2 = st.columns([1, 2])
            
            with c_nlp1:
                # Termómetro del Sentimiento Global
                color_sentimiento = "green" if sentimiento_global > 0.1 else "red" if sentimiento_global < -0.1 else "gray"
                estado_global = "ALCISTA 🐂" if sentimiento_global > 0.1 else "BAJISTA 🐻" if sentimiento_global < -0.1 else "NEUTRAL ⚖️"
                
                st.markdown(f"<h3 style='text-align: center;'>Veredicto de la IA:</h3>", unsafe_allow_html=True)
                st.markdown(f"<h2 style='text-align: center; color: {color_sentimiento};'>{estado_global}</h2>", unsafe_allow_html=True)
                progreso = max(0.0, min(1.0, (sentimiento_global + 1) / 2))
                st.progress(progreso)
                st.caption("Barra hacia la derecha = Noticias Positivas. Hacia la izquierda = Noticias Negativas.")
                
            with c_nlp2:
                st.markdown("##### 📰 Titulares Analizados en Tiempo Real:")
                for noti in noticias_nlp:
                    titulo = noti.get("Titular") or "Titular no disponible"
                    enlace = noti.get("Link") or "#"
                    fuente = noti.get("Fuente") or "N/D"
                    st.markdown(f"- **{noti.get('Sentimiento', 'Neutral ⚖️')}** | [{titulo}]({enlace}) *(Vía {fuente})*")
        else:
            st.info("No se encontraron noticias recientes en inglés para procesar el sentimiento.")
