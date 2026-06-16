import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import urllib.request
import xml.etree.ElementTree as ET
from textblob import TextBlob
from modulos.gemini_helper import aviso_gemini_no_configurado, obtener_modelo_gemini

# Importamos todos los gráficos necesarios para esta pestaña
from charts import (
    plot_termometro_macro, 
    plot_radar_comparativo,
    plot_rotacion_sectorial,
    plot_estacionalidad_quant,
    plot_frontera_eficiente
)

@st.cache_data(ttl=3600, show_spinner=False)
def analizar_macro_avanzado():
    """Descarga commodities, ratios institucionales y noticias RSS en crudo"""
    def obtener_precio_seguro(ticker_symbol):
        try:
            data = yf.Ticker(ticker_symbol).history(period="5d")
            if not data.empty: return float(data['Close'].iloc[-1])
        except: pass
        return 0.0

    irx = obtener_precio_seguro('^IRX')       
    tnx = obtener_precio_seguro('^TNX')       
    oro = obtener_precio_seguro('GC=F')       
    petroleo = obtener_precio_seguro('CL=F')  
    dxy = obtener_precio_seguro('DX-Y.NYB')   
    cobre = obtener_precio_seguro('HG=F')
    xly = obtener_precio_seguro('XLY') 
    xlp = obtener_precio_seguro('XLP') 
    spy = obtener_precio_seguro('SPY') 
    rsp = obtener_precio_seguro('RSP') 

    spread_curva = tnx - irx if tnx > 0 and irx > 0 else 0
    ratio_cobre_oro = (cobre / oro) * 100 if oro > 0 else 0
    ratio_riesgo = xly / xlp if xlp > 0 else 0
    amplitud_mercado = rsp / spy if spy > 0 else 0

    titulares_macro = []
    polaridad_media = 0
    polaridad_total = 0
    
    try:
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        
        for item in root.findall('./channel/item')[:6]:
            titulo = item.find('title').text
            enlace = item.find('link').text
            
            polaridad = TextBlob(titulo).sentiment.polarity
            estado = "Neutral ⚖️"
            if polaridad > 0.05: estado = "Alcista 🟢"
            elif polaridad < -0.05: estado = "Bajista 🔴"
            
            polaridad_total += polaridad
            titulares_macro.append({"Titular": titulo, "Link": enlace, "Sentimiento": estado})
            
        if titulares_macro:
            polaridad_media = polaridad_total / len(titulares_macro)
    except Exception as e:
        pass

    return {
        "spread_curva": spread_curva, "oro": oro, "petroleo": petroleo, 
        "dxy": dxy, "cobre": cobre, "ratio_cobre_oro": ratio_cobre_oro,
        "ratio_riesgo": ratio_riesgo, "amplitud_mercado": amplitud_mercado,
        "noticias": titulares_macro, "polaridad": polaridad_media
    }

# 🛠️ CORRECCIÓN DE SYNTAX: Retirado el ="" del ticker_competidor
def ejecutar_radar_macro(ticker_input, ticker_competidor, df_sectores=None):
    """Analiza el entorno macroeconómico, comparativas sectoriales y head-to-head."""
    st.markdown(f"### 🌍 Radar Macro y Sectores: {ticker_input}")

    if df_sectores is not None and not df_sectores.empty:
        st.markdown("#### 🔄 Rotación Sectorial (Último Mes)")
        st.dataframe(df_sectores, use_container_width=True)
    else:
        st.info("Datos de rotación sectorial no disponibles en este momento.")
    
    # ======== RADAR ROTACIÓN SECTORIAL ========
    with st.expander("🌍 Radar Macro: ¿Dónde está fluyendo el dinero? (Rotación Sectorial)", expanded=False):
        st.markdown("Los grandes fondos de inversión rotan su capital constantemente. Aquí puedes ver qué sectores están calentándose y cuáles se están quedando atrás.")
        
        if df_sectores is not None and not df_sectores.empty:
            col_sec1, col_sec2 = st.columns([1, 1.5])
            
            with col_sec1:
                st.dataframe(
                    df_sectores.set_index("Sector").style.background_gradient(subset=['1 Mes (%)', '3 Meses (%)'], cmap='RdYlGn'),
                    height=350,
                    use_container_width=True
                )
            
            with col_sec2:
                fig_sectores = plot_rotacion_sectorial(df_sectores)
                st.plotly_chart(fig_sectores, use_container_width=True)
                
            mejor_sector = df_sectores.loc[df_sectores['1 Mes (%)'].idxmax()]['Sector']
            peor_sector = df_sectores.loc[df_sectores['1 Mes (%)'].idxmin()]['Sector']
            st.info(f"💡 **Insight Macro:** En los últimos 30 días, el capital institucional está rotando agresivamente hacia **{mejor_sector}**, mientras abandona **{peor_sector}**.")

    # ======== TAB 9: ESTACIONALIDAD ========
    st.markdown("### 🎲 Probabilidad y Estacionalidad (Los últimos 20 años)")
    st.caption("Los fondos Quant no adivinan, cuentan cartas. Este mapa de calor analiza la historia completa de la acción para decirte en qué meses tienes las probabilidades matemáticas a tu favor.")
    
    with st.spinner(f"Procesando miles de velas históricas de {ticker_input}..."):
        fig_estacional, diagnostico_estacional = plot_estacionalidad_quant(ticker_input)
        
        if fig_estacional:
            st.plotly_chart(fig_estacional, use_container_width=True)
            st.info(diagnostico_estacional)
            
            st.markdown("---")
            st.markdown("""
            **💡 ¿Cómo usar esta ventaja injusta?**
            * **Barras Verdes (>60%):** En estos meses, jugar a la baja (cortos) es un suicidio estadístico.
            * **Barras Rojas (<40%):** Meses de purga. Es el momento perfecto para guardar liquidez y cazar chollos a final de mes.
            """)
        else:
            st.warning(diagnostico_estacional)

    # ======== TAB 6: FRONTERA EFICIENTE ========
    st.markdown("### ⚖️ Laboratorio Quant: Optimización de Cartera")
    st.caption("Introduce al menos 3 tickers separados por comas. El algoritmo simulará 2,000 combinaciones para encontrar los pesos exactos que maximizan tu rentabilidad (Modelo Markowitz).")
    
    tickers_cartera = st.text_input("Tickers de tu Cartera (Ej: AAPL, KO, JNJ, V, XOM):", value="AAPL, MSFT, KO, JNJ, V")
    
    if st.button("🚀 Optimizar Pesos (Correr Monte Carlo)"):
        lista_tickers = [t.strip().upper() for t in tickers_cartera.split(",")]
        
        if len(lista_tickers) < 2:
            st.warning("Necesitas al menos 2 empresas para optimizar una cartera.")
        else:
            with st.spinner("Simulando miles de escenarios de mercado..."):
                fig_mark, pesos_rec = plot_frontera_eficiente(lista_tickers)
                
                if fig_mark and pesos_rec:
                    c_opt1, c_opt2 = st.columns([2, 1])
                    
                    with c_opt1:
                        st.plotly_chart(fig_mark, use_container_width=True)
                        
                    with c_opt2:
                        st.markdown("#### 🎯 Asignación Óptima")
                        st.success("Para conseguir el mejor Ratio Sharpe, el modelo matemático recomienda:")
                        for tick, peso in pesos_rec.items():
                            if peso > 1.0:
                                st.write(f"**{tick}:** {peso}%")
                                st.progress(peso / 100)

    # ======== TAB 7: MACRO INSTITUCIONAL ========
    st.markdown("### 🌍 Visión Macro Institucional")
    st.caption("Analizando el flujo del 'Smart Money'. Los grandes fondos no miran las noticias, miran cómo se mueve el capital.")
    
    with st.spinner("Descargando métricas globales e índices adelantados..."):
        fig_macro, diagnostico_macro = plot_termometro_macro()
        
        if fig_macro:
            st.plotly_chart(fig_macro, use_container_width=True)
            
            datos_macro = analizar_macro_avanzado()
            
            st.markdown("---")
            st.markdown("#### 🧭 Dinámicas de Mercado (Smart Money Ratios)")
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            
            spread = datos_macro['spread_curva']
            col_r1.metric("Curva Tipos (10Y-3M)", f"{spread:+.2f} pts", "Invertida 🚨" if spread < 0 else "Normal 🟢", delta_color="inverse" if spread < 0 else "normal")
            
            r_riesgo = datos_macro['ratio_riesgo']
            col_r2.metric("Apetito Riesgo (XLY/XLP)", f"{r_riesgo:.2f}x", "Apetito 🐂" if r_riesgo > 2.2 else "Miedo 🐻", delta_color="normal" if r_riesgo > 2.2 else "inverse")
            
            r_cu_au = datos_macro['ratio_cobre_oro']
            col_r3.metric("Dr. Copper (Cobre/Oro)", f"{r_cu_au:.3f}", "Expansión 🏭" if r_cu_au > 0.18 else "Contracción 📉", delta_color="normal" if r_cu_au > 0.18 else "inverse")
            
            amplitud = datos_macro['amplitud_mercado']
            col_r4.metric("Amplitud (RSP/SPY)", f"{amplitud:.2f}x", "Sano 🌲" if amplitud > 0.30 else "Peligro ⚠️", delta_color="normal" if amplitud > 0.30 else "inverse")

            st.markdown("---")
            st.markdown("#### 🛢️ Inflación y Costes de Capital")
            col_i1, col_i2, col_i3, col_i4 = st.columns(4)
            col_i1.metric("Oro (Refugio)", f"${datos_macro['oro']:,.2f}" if datos_macro['oro'] else "N/A")
            col_i2.metric("Cobre (Industria)", f"${datos_macro['cobre']:,.2f}" if datos_macro['cobre'] else "N/A")
            col_i3.metric("Petróleo WTI (Energía)", f"${datos_macro['petroleo']:,.2f}" if datos_macro['petroleo'] else "N/A")
            col_i4.metric("Índice Dólar DXY", f"{datos_macro['dxy']:,.2f}" if datos_macro['dxy'] else "N/A")
            
            st.markdown("---")
            st.markdown("#### 🤖 Procesamiento de Noticias (Wall Street Newsfeed)")
            
            c_mac1, c_mac2 = st.columns([1, 2.5])
            pol = datos_macro['polaridad']
            with c_mac1:
                if pol > 0.05:
                    st.success("##### 🐂 Tono IA: ALCISTA")
                elif pol < -0.05:
                    st.error("##### 🐻 Tono IA: BAJISTA")
                else:
                    st.info("##### ⚖️ Tono IA: NEUTRAL")
                    
            with c_mac2:
                noticias = datos_macro['noticias']
                if noticias:
                    for noti in noticias:
                        st.markdown(f"**{noti['Sentimiento']}** | [{noti['Titular']}]({noti['Link']})")
                else:
                    st.warning("⚠️ El servidor de noticias está bloqueando la conexión temporalmente.")
        else:
            st.error(f"🚨 Fallo técnico detectado:\n\n{diagnostico_macro}")

    # ======== ORÁCULO TÁCTICO IA ========
    st.markdown("---")
    st.markdown("### 🔮 Oráculo Táctico: Playbook de Inversión IA")

    if st.button("🧠 Generar Playbook Estratégico", use_container_width=True):
        with st.spinner("La IA está cruzando los datos macroeconómicos..."):
            try:
                spread = datos_macro.get('spread_curva', 0) if 'datos_macro' in locals() else 0
                r_riesgo = datos_macro.get('ratio_riesgo', 0) if 'datos_macro' in locals() else 0
                r_cu_au = datos_macro.get('ratio_cobre_oro', 0) if 'datos_macro' in locals() else 0
                
                mejor_sec = df_sectores.loc[df_sectores['1 Mes (%)'].idxmax()]['Sector'] if df_sectores is not None and not df_sectores.empty else "Desconocido"
                peor_sec = df_sectores.loc[df_sectores['1 Mes (%)'].idxmin()]['Sector'] if df_sectores is not None and not df_sectores.empty else "Desconocido"

                prompt_oraculo = f"""
                Eres el Estratega Jefe Macro de un Hedge Fund Cuantitativo.
                Tu trabajo es decirle a los clientes qué hacer basándote en estos datos de mercado:
                - Curva de Tipos: {spread:+.2f} pts
                - Apetito al Riesgo: {r_riesgo:.2f}x 
                - Cobre vs Oro: {r_cu_au:.3f} 
                - Momentum: El dinero entra en {mejor_sec} y huye de {peor_sec}.

                Escribe un "Playbook Táctico":
                1. 🌡️ Diagnóstico del Ciclo.
                2. 🎯 Asset Allocation recomendado.
                3. ⚔️ Estrategia Táctica actual.
                """

                model = obtener_modelo_gemini()
                if model:
                    response = model.generate_content(prompt_oraculo)
                    st.success("✅ Playbook generado con éxito.")
                    with st.expander("📖 LEER PLAYBOOK TÁCTICO DE LA IA", expanded=True):
                        st.markdown(response.text)
                else:
                    aviso_gemini_no_configurado()
                    sesgo = "riesgo defensivo" if r_riesgo < 1 else "riesgo moderado/positivo"
                    st.markdown(
                        f"**Playbook local:** curva {spread:+.2f}, apetito de riesgo {r_riesgo:.2f}x y cobre/oro {r_cu_au:.3f}. "
                        f"El sesgo táctico actual es **{sesgo}**. Favorece sectores con momentum relativo como **{mejor_sec}** "
                        f"y reduce exposición a rezagados como **{peor_sec}**."
                    )
            except Exception as e:
                st.error(f"Error generando el oráculo: {e}")
