import logging

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from charts import plot_beneish_m_score, plot_auditoria_forense, plot_termometro_deuda
from modulos.data_provider_errors import (
    INSUFFICIENT_COVERAGE,
    INVALID_TICKER,
    NO_DATA,
    PROVIDER_ERROR,
    RATE_LIMITED,
    RESTRICTED,
    TIMEOUT,
)
from modulos.sec_fmp_cross_validation import comparar_estados_financieros
from modulos.sec_validation_store import sec_validation_summary
from modulos.ui_components import format_last_sec_validation_caption, render_cross_validation_table
from modulos.utils import analizar_sentimiento_noticias

logger = logging.getLogger(__name__)

# Mismo criterio que FMP_STATUS_MESSAGES en modulos/fmp_api.py: un mensaje
# accionable por causa real, en vez de un "no se pudo" genérico. El código
# viene de downloader.obtener_estados_financieros_con_diagnostico, que ya
# clasifica el fallo con la jerarquía de modulos/data_provider_errors.py
# (Sub-fase 0/2) sin propagar nunca la excepción original a la UI.
_SEC_STATUS_MESSAGES = {
    INVALID_TICKER: "SEC EDGAR no reconoce este ticker (puede no cotizar en EE.UU. o no presentar 10-K ante la SEC).",
    RATE_LIMITED: "Límite de peticiones de SEC EDGAR alcanzado temporalmente. Inténtalo de nuevo en unos minutos.",
    TIMEOUT: "SEC EDGAR tardó demasiado en responder. Inténtalo de nuevo.",
    RESTRICTED: "Acceso restringido a SEC EDGAR en este momento.",
    NO_DATA: "SEC EDGAR no devolvió estados financieros (10-K) para este ticker.",
    INSUFFICIENT_COVERAGE: "SEC EDGAR no tiene suficiente histórico de 10-K para comparar.",
    PROVIDER_ERROR: "SEC EDGAR no está disponible temporalmente. Inténtalo más tarde.",
}
_SEC_STATUS_DEFAULT_MESSAGE = "No se pudo completar la verificación contra SEC EDGAR."


@st.cache_data(ttl=86400, show_spinner=False)
def _obtener_datos_sec_cacheados(ticker: str, años: int):
    """Cache de sesión (24h) del fetch SEC EDGAR para Modo Auditoría.

    Se usa ``usar_cache=False`` hacia downloader.py a propósito: su propio
    cache en disco (cache_datos/*.csv) no conserva ``df.attrs["period_end_dates"]``
    (no sobrevive un roundtrip por CSV — ver downloader.py), mientras que
    ``st.cache_data`` sí, porque conserva el objeto tal cual (pickle, no CSV).
    Import perezoso de ``downloader`` dentro de la función: Auditoría Forense
    debe seguir abriendo rápido para quien no active el toggle — edgartools
    (pyarrow, httpx, etc.) solo se importa si de verdad se pide la verificación.
    """
    import downloader

    return downloader.obtener_estados_financieros_con_diagnostico(ticker, años=años, usar_cache=False)


def _renderizar_verificacion_sec(ticker_input: str, is_df, bs_df, cf_df) -> None:
    """Sección opt-in de Modo Auditoría: verificación cruzada SEC↔FMP.

    Con su propio try/except, deliberadamente aislado del resto de
    ejecutar_auditoria_forense: un fallo aquí (SEC EDGAR caído, ticker sin
    10-K, timeout) no debe tumbar el Z-Score/M-Score/sentimiento, que
    funcionan sin esto. safe_call (modulos/module_loader.py) ya envuelve toda
    la función con un try/except, pero ese solo protege módulos completos —
    si esta sección lanzara sin capturar, se perdería también todo lo demás
    que ya se pintó en pantalla antes de llegar aquí.
    """
    try:
        with st.spinner(f"Consultando SEC EDGAR para {ticker_input} (puede tardar varios segundos)..."):
            df_is_sec, df_bs_sec, df_cf_sec, codigo_error = _obtener_datos_sec_cacheados(ticker_input, 5)
    except Exception as exc:
        logger.error("Modo Auditoría SEC: fallo inesperado consultando %s: %s", ticker_input, type(exc).__name__)
        st.warning(_SEC_STATUS_DEFAULT_MESSAGE)
        return

    if df_is_sec is None and df_bs_sec is None and df_cf_sec is None:
        st.warning(_SEC_STATUS_MESSAGES.get(codigo_error, _SEC_STATUS_DEFAULT_MESSAGE))
        return

    try:
        comparaciones = comparar_estados_financieros(
            df_is_fmp=is_df, df_cf_fmp=cf_df, df_bs_fmp=bs_df,
            df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=df_bs_sec,
        )
    except Exception as exc:
        logger.error("Modo Auditoría SEC: fallo comparando %s: %s", ticker_input, type(exc).__name__)
        st.warning(_SEC_STATUS_DEFAULT_MESSAGE)
        return

    render_cross_validation_table(comparaciones)


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
                # plot_auditoria_forense no pudo calcular el Z-Score (datos de
                # Yahoo insuficientes o un error interno) — alertas_forenses
                # trae el motivo real en vez de dejarlo caer en silencio.
                mensaje = alertas_forenses[0] if alertas_forenses else "No se pudo calcular el Z-Score para esta empresa."
                st.info(mensaje)
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

    st.markdown("---")
    st.markdown("#### 🔍 Modo Auditoría: Verificación Cruzada SEC EDGAR")
    st.caption(
        "Recalcula los mismos ratios (Margen Bruto/Neto, SG&A, ROE...) a partir de los 10-K "
        "reales presentados en SEC EDGAR y los contrasta con los de FMP. Opcional: la consulta "
        "a SEC EDGAR tarda varios segundos y no se ejecuta salvo que la actives."
    )
    st.caption(format_last_sec_validation_caption(sec_validation_summary(ticker_input)))
    if st.toggle("Verificar contra SEC EDGAR", key=f"modo_auditoria_sec_{ticker_input}"):
        _renderizar_verificacion_sec(ticker_input, is_df, bs_df, cf_df)
