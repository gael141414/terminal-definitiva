import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

@st.cache_data(ttl=86400, show_spinner=False)
def calcular_z_score(ticker):
    # 1. Protección contra ticker vacío
    if not ticker or str(ticker).strip() == "":
        return None
        
    try:
        # 2. Descarga robusta usando el objeto Ticker
        accion = yf.Ticker(ticker)
        df = accion.history(period="5y")
        
        # 3. Comprobar si hay datos y si superan los 200 días
        if df.empty or len(df) < 200:
            return None
            
        # 4. Asegurar el formato del DataFrame (aislar el Cierre)
        df = df[['Close']].copy()

        # 5. Matemáticas Cuantitativas: SMA 200 y Desviación Estándar
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        df['STD_200'] = df['Close'].rolling(window=200).std()
        
        # 6. Cálculo del Z-Score
        df['Z_Score'] = (df['Close'] - df['SMA_200']) / df['STD_200']
        
        return df.dropna()
    except Exception as e:
        return None

def ejecutar_predictor_techos_suelos(ticker_input):
    st.markdown(f"### 🔭 Predictor de Ciclos Extremos: {ticker_input}")
    
    with st.spinner("Calculando zonas de probabilidad estadística..."):
        df = calcular_z_score(ticker_input)
        
        if df is not None and not df.empty:
            z_actual = df['Z_Score'].iloc[-1]
            
            # 1. Diagnóstico de un vistazo
            st.markdown("#### 🎯 Situación de Mercado")
            c1, c2, c3 = st.columns([1, 1, 2])
            
            c1.metric("Z-Score Actual", f"{z_actual:.2f} σ")
            
            # Clasificación para el semáforo
            if z_actual >= 2:
                estado = "🔴 TECHO (Burbuja)"
                color_msg = "error"
            elif z_actual <= -2:
                estado = "🟢 SUELO (Oportunidad)"
                color_msg = "success"
            else:
                estado = "⚪ ZONA NEUTRAL"
                color_msg = "info"
            
            c2.markdown(f"**Estado:** \n {estado}")
            
            with c3:
                if color_msg == "error":
                    st.error("Probabilidad de reversión a la baja: >95%")
                elif color_msg == "success":
                    st.success("Probabilidad de rebote al alza: >95%")
                else:
                    st.info("El precio oscila dentro de su volatilidad normal.")

            # 2. Gráfico Profesional con Zonas de Intervalo
            st.markdown("#### 📊 Mapa de Desviación Estándar (5 Años)")
            
            fig = go.Figure()

            # --- ZONAS DE INTERVALO (LAS CAJAS PROFESIONALES) ---
            # Zona de Techo (Rojo suave)
            fig.add_hrect(y0=2, y1=max(4, df['Z_Score'].max()), 
                          fillcolor="rgba(255, 0, 0, 0.15)", line_width=0,
                          annotation_text="ZONA DE DISTRIBUCIÓN (VENTA)", annotation_position="top left")
            
            # Zona de Suelo (Verde suave)
            fig.add_hrect(y0=min(-4, df['Z_Score'].min()), y1=-2, 
                          fillcolor="rgba(0, 255, 0, 0.15)", line_width=0,
                          annotation_text="ZONA DE ACUMULACIÓN (COMPRA)", annotation_position="bottom left")

            # Línea de Z-Score principal
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Z_Score'],
                mode='lines', name='Z-Score',
                line=dict(color='#00C0F2', width=2),
                hovertemplate="Fecha: %{x}<br>Z-Score: %{y:.2f}σ<extra></extra>"
            ))
            
            # Líneas de referencia sutiles
            fig.add_hline(y=2, line_dash="dot", line_color="red", opacity=0.5)
            fig.add_hline(y=-2, line_dash="dot", line_color="green", opacity=0.5)
            fig.add_hline(y=0, line_color="white", opacity=0.3)

            # Estética Profesional
            fig.update_layout(
                height=500,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(
                    title="Desviaciones Estándar (σ)",
                    gridcolor="rgba(255,255,255,0.05)",
                    zeroline=False
                ),
                xaxis=dict(
                    title="",
                    gridcolor="rgba(255,255,255,0.05)"
                ),
                margin=dict(l=0, r=0, t=30, b=0),
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.caption("ℹ️ El sombreado indica anomalías estadísticas fuera del 95% de los movimientos normales.")
            
        else:
            st.warning("No hay suficientes datos históricos (200+ días) para calcular los ciclos de esta empresa.")
