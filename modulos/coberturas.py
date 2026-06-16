import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px

@st.cache_data(ttl=86400, show_spinner=False)
def calcular_correlaciones_cobertura(ticker):
    """Calcula la correlación de Pearson entre la acción y los activos refugio tradicionales."""
    try:
        # Cesta de Coberturas Institucionales (Safe Havens)
        activos_refugio = {
            "Oro (Protección Inflación)": "GC=F",
            "Bonos del Tesoro 20A+ (TLT)": "TLT",
            "Dólar Index (DXY)": "DX-Y.NYB",
            "VIX (Índice del Miedo)": "^VIX",
            "Franco Suizo (CHF)": "CHF=X",
            "S&P 500 Inverso (SH)": "SH", # ETF que sube cuando la bolsa baja
            "Bitcoin (Oro Digital)": "BTC-USD"
        }
        
        # Añadimos el ticker del usuario a la lista para descargar
        tickers_descarga = [ticker] + list(activos_refugio.values())
        
        # Descargamos 2 años de historia diaria
        data = yf.download(tickers_descarga, period="2y", interval="1d")['Close']
        
        # Limpiamos y calculamos los retornos diarios (%)
        retornos = data.ffill().dropna().pct_change().dropna()
        
        # Calculamos la matriz de correlación
        matriz_corr = retornos.corr()
        
        # Extraemos solo la columna que nos interesa: cómo se correlacionan con nuestra empresa
        correlaciones = matriz_corr[ticker].drop(ticker) # Quitamos la correlación consigo misma (que es 1.0)
        
        # Mapeamos los Tickers de vuelta a nombres legibles
        mapa_inverso = {v: k for k, v in activos_refugio.items()}
        correlaciones.index = correlaciones.index.map(lambda x: mapa_inverso.get(x, x))
        
        # Formatear en un DataFrame limpio
        df_corr = pd.DataFrame(correlaciones).reset_index()
        df_corr.columns = ['Activo Refugio', 'Correlación']
        df_corr = df_corr.sort_values(by='Correlación', ascending=True) # Los más negativos primero
        
        return df_corr
    except Exception as e:
        return None

def ejecutar_radar_coberturas(ticker_input):
    st.markdown(f"### 🛡️ Radar de Coberturas (Hedging Finder): {ticker_input}")
    st.markdown("Encuentra el activo perfecto para proteger tu cartera. Buscamos correlaciones inversas (cercanas a -1.0): activos matemáticamente probados que tienden a subir los días que tu acción cae.")

    with st.spinner(f"Analizando miles de retornos diarios cruzados para {ticker_input}..."):
        df_corr = calcular_correlaciones_cobertura(ticker_input)
        
        if df_corr is not None and not df_corr.empty:
            
            # --- DIAGNÓSTICO DEL MEJOR SEGURO ---
            mejor_cobertura = df_corr.iloc[0]['Activo Refugio']
            mejor_score = df_corr.iloc[0]['Correlación']
            
            st.markdown("#### 🎯 El Seguro Óptimo")
            c1, c2 = st.columns([1, 2])
            
            with c1:
                st.metric("Mejor Activo de Protección", mejor_cobertura, f"{mejor_score:.2f} (Correlación)")
                
            with c2:
                if mejor_score < -0.3:
                    st.success(f"**Excelente Cobertura:** El **{mejor_cobertura}** se mueve de forma inversa a tu acción. Es un seguro perfecto para estabilizar la volatilidad de tu cartera en momentos de pánico.")
                elif mejor_score < 0:
                    st.info(f"**Cobertura Aceptable:** El **{mejor_cobertura}** ofrece una ligera diversificación. Ayudará a amortiguar las caídas, pero no es un seguro absoluto.")
                else:
                    st.warning("**⚠️ Peligro de Riesgo Sistémico:** Ninguno de los activos refugio tradicionales tiene correlación negativa con tu empresa. En una crisis, todo bajará a la vez. Considera tener liquidez extrema (Cash).")

            # --- GRÁFICO VISUAL (ESCALA DE COLOR) ---
            st.markdown("---")
            st.markdown("#### 📊 Mapa de Descorrelación Institucional")
            
            # Formateo de colores: Verde (Negativo/Bueno para cubrir), Rojo (Positivo/Malo para cubrir)
            fig = px.bar(
                df_corr, 
                x='Correlación', 
                y='Activo Refugio', 
                orientation='h',
                color='Correlación',
                color_continuous_scale='RdYlGn_r', # Invertimos para que lo negativo sea verde
                range_color=[-1, 1],
                text_auto='.2f'
            )
            
            fig.update_layout(
                height=400,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Correlación de Pearson (-1.0 a 1.0)",
                yaxis_title=""
            )
            fig.add_vline(x=0, line_dash="dash", line_color="white", opacity=0.5)
            
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("📖 ¿Cómo interpretar este gráfico?"):
                st.markdown("""
                * **-1.0 (Verde Fuerte):** Correlación inversa perfecta. Si tu acción baja un 1%, este activo sube un 1%. **Es el seguro ideal.**
                * **0.0 (Amarillo):** Sin correlación. El activo va a su bola y no le importa lo que le pase a tu acción. Sirve para diversificar a largo plazo.
                * **+1.0 (Rojo Fuerte):** Correlación positiva perfecta. Se mueven en la misma dirección. **NO sirve como seguro**, si tu acción cae, este activo te arrastrará más al fondo.
                """)
        else:
            st.error("No se han podido calcular las correlaciones. Puede que el ticker sea demasiado nuevo para tener un historial cruzado válido.")
