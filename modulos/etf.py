import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from modulos.gemini_helper import aviso_gemini_no_configurado, obtener_modelo_gemini

def ejecutar_radiografia_etf(ticker_input):
    st.markdown(f"### 🩻 ETF X-Ray: Radiografía del Fondo {ticker_input}")
    st.markdown("Audita el interior de los ETFs. Descubre en qué invierten realmente tu dinero, si están demasiado concentrados y si las comisiones que te cobran están justificadas.")

    with st.spinner("Desempaquetando holdings, sectores y folletos del fondo..."):
        try:
            fondo = yf.Ticker(ticker_input)
            info = fondo.info
            
            # Comprobar si realmente es un ETF/Fondo
            tipo_activo = info.get('quoteType', '')
            if tipo_activo not in ['ETF', 'MUTUALFUND']:
                st.warning(f"⚠️ {ticker_input} parece ser una acción individual ('{tipo_activo}'), no un ETF o Fondo Mutuo. Algunos datos podrían no mostrarse correctamente.")

            # 1. Extracción de Datos Clave
            nombre_fondo = info.get('longName', ticker_input)
            aum = info.get('totalAssets', 0) # Activos bajo gestión
            comision = info.get('annualReportExpenseRatio', info.get('navPrice', 0)) 
            if comision and comision < 1: comision = comision * 100 # Convertir a porcentaje
            
            yield_fondo = info.get('yield', 0) * 100 if info.get('yield') else 0
            beta = info.get('beta3Year', info.get('beta', 'N/A'))
            resumen = info.get('longBusinessSummary', 'Sin descripción disponible.')

            # Tarjetas de Resumen
            st.markdown("---")
            st.markdown(f"#### 🏦 {nombre_fondo}")
            
            c1, c2, c3, c4 = st.columns(4)
            
            # Formatear AUM en Billones/Millones
            if aum > 1e9: aum_str = f"${aum/1e9:.2f}B"
            elif aum > 1e6: aum_str = f"${aum/1e6:.2f}M"
            else: aum_str = "Desconocido"
            
            c1.metric("💰 Activos bajo Gestión (AUM)", aum_str)
            
            # Alerta visual si la comisión es abusiva (>0.50%)
            if isinstance(comision, (int, float)) and comision > 0.50:
                c2.metric("💸 Comisión Anual (TER)", f"{comision:.2f}%", "- Cara 🔴")
            elif isinstance(comision, (int, float)):
                c2.metric("💸 Comisión Anual (TER)", f"{comision:.2f}%", "+ Barata 🟢")
            else:
                c2.metric("💸 Comisión Anual", "N/A")
                
            c3.metric("💧 Dividend Yield", f"{yield_fondo:.2f}%" if yield_fondo else "N/A")
            c4.metric("⚖️ Riesgo (Beta a 3 años)", f"{beta:.2f}" if isinstance(beta, (int, float)) else beta)

            st.markdown("<br>", unsafe_allow_html=True)

            # 2. Extracción de Entrañas (Holdings y Sectores)
            # Nota: yfinance a veces bloquea o cambia la estructura de los holdings. Hacemos un try-except robusto.
            holdings = info.get('holdings', [])
            sectores = info.get('sectorWeightings', [])
            
            col_graficos_1, col_graficos_2 = st.columns(2)
            
            # Gráfico de Holdings (Top 10)
            datos_holdings = ""
            with col_graficos_1:
                st.markdown("#### 🔝 Top 10 Posiciones (Concentración)")
                if holdings and len(holdings) > 0:
                    df_holdings = pd.DataFrame(holdings)
                    # Normalizar nombres de columnas si vienen raros de Yahoo
                    if 'holdingName' in df_holdings.columns and 'holdingPercent' in df_holdings.columns:
                        df_holdings['holdingPercent'] = df_holdings['holdingPercent'] * 100
                        df_holdings = df_holdings.sort_values(by='holdingPercent', ascending=True).tail(10)
                        
                        fig_holdings = px.bar(df_holdings, x='holdingPercent', y='holdingName', orientation='h', text='holdingPercent')
                        fig_holdings.update_traces(texttemplate='%{text:.2f}%', textposition='outside', marker_color='#00C0F2')
                        fig_holdings.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', xaxis_title="% del Fondo", yaxis_title="")
                        st.plotly_chart(fig_holdings, use_container_width=True)
                        
                        datos_holdings = df_holdings[['holdingName', 'holdingPercent']].to_string()
                    else:
                        st.info("Formato de posiciones no compatible en la API.")
                else:
                    st.info("Yahoo Finance no proporciona el Top 10 para este fondo.")

            # Gráfico de Sectores
            datos_sectores = ""
            with col_graficos_2:
                st.markdown("#### 🍕 Exposición Sectorial")
                if sectores and len(sectores) > 0:
                    # yfinance devuelve a veces una lista de diccionarios con claves raras
                    sectores_limpios = {list(s.keys())[0]: list(s.values())[0] * 100 for s in sectores if isinstance(s, dict)}
                    if sectores_limpios:
                        df_sectores = pd.DataFrame(list(sectores_limpios.items()), columns=['Sector', 'Peso (%)'])
                        
                        fig_sectores = px.pie(df_sectores, values='Peso (%)', names='Sector', hole=0.4, color_discrete_sequence=px.colors.sequential.Tealgrn)
                        fig_sectores.update_traces(textposition='inside', textinfo='percent+label')
                        fig_sectores.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0), showlegend=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_sectores, use_container_width=True)
                        
                        datos_sectores = df_sectores.to_string()
                    else:
                        st.info("Formato de sectores no compatible en la API.")
                else:
                    st.info("Datos sectoriales ocultos o no disponibles.")

            # 3. Veredicto Forense de la IA
            st.markdown("---")
            st.markdown("### 🧠 Auditoría Cualitativa (Analista de Fondos)")
            with st.spinner("La IA está leyendo el folleto del fondo y buscando riesgos ocultos de concentración..."):
                prompt_etf = f"""
                Actúa como un Auditor de Fondos de Inversión Institucional (crítico y objetivo).
                Estás auditando el ETF/Fondo: {nombre_fondo} ({ticker_input}).
                Comisión (TER): {comision}%
                Descripción oficial: {resumen[:800]}...
                
                Top Posiciones:
                {datos_holdings if datos_holdings else "No disponibles"}
                
                Exposición Sectorial:
                {datos_sectores if datos_sectores else "No disponibles"}
                
                Escribe un informe forense en 3 puntos breves:
                1. 🔍 **Diagnóstico de Concentración:** ¿Está realmente diversificado o es una apuesta camuflada en 2 o 3 acciones gigantes? (Ej: "Dice ser de IA, pero es solo un clon del Nasdaq").
                2. 💸 **Análisis de Comisiones:** ¿Está justificada la comisión del {comision}% para lo que ofrece, o es un atraco comparado con un ETF pasivo genérico (0.05%)?
                3. ⚖️ **Veredicto:** ¿Para qué tipo de cartera sirve este ETF (Core, Satélite táctico, o Trampa para novatos)?
                """
                
                model = obtener_modelo_gemini()
                if model:
                    response = model.generate_content(prompt_etf)
                    st.write(response.text)
                else:
                    aviso_gemini_no_configurado()
                    concentracion = "no disponible" if not datos_holdings else "revisar el peso de las primeras posiciones"
                    st.write(
                        f"Auditoría local: **{nombre_fondo}** tiene comisión estimada de **{comision}%**. "
                        f"Concentración: {concentracion}. Úsalo como core solo si replica un índice amplio; "
                        "si es temático, debe tratarse como satélite táctico."
                    )

        except Exception as e:
            st.error(f"Error al destripar el ETF: {e}. Puede que el Ticker no exista o Yahoo Finance haya bloqueado los datos de este fondo en concreto.")
