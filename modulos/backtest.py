import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import numpy as np
from modulos.gemini_helper import aviso_gemini_no_configurado, obtener_modelo_gemini


def _retro_analisis_local(ticker: str, fecha_pasada: str, rentabilidad_real: float) -> str:
    if rentabilidad_real > 80:
        veredicto = "el mercado infravaloró de forma clara la opcionalidad del negocio"
        conclusion = "habría merecido una posición satélite con control de riesgo."
    elif rentabilidad_real > 15:
        veredicto = "la tesis habría sido razonable, aunque no necesariamente obvia en aquel momento"
        conclusion = "habría encajado como compra gradual si los fundamentales acompañaban."
    elif rentabilidad_real > -15:
        veredicto = "la oportunidad real fue mediocre frente al coste de oportunidad"
        conclusion = "habría exigido mucha disciplina en valoración y tamaño de posición."
    else:
        veredicto = "el mercado estaba descontando riesgos que terminaron pesando en la rentabilidad"
        conclusion = "habría sido mejor esperar confirmación o evitar la posición."

    return (
        f"**Veredicto en {fecha_pasada}:** para {ticker}, {veredicto}. "
        f"**Choque con la realidad:** la rentabilidad posterior fue de {rentabilidad_real:+.2f}%, "
        f"por lo que {conclusion}"
    )

def ejecutar_maquina_del_tiempo(ticker_input):
    """Simulador histórico comparativo contra el S&P 500 y retro-auditoría IA"""
    
    st.markdown(f"### ⏳ Máquina del Tiempo: Backtesting de {ticker_input}")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        inversion_inicial = st.number_input("💰 Inversión Inicial ($)", min_value=1000, max_value=1000000, value=10000, step=1000)
        anios_backtest = st.slider("📅 ¿Cuántos años atrás viajamos?", min_value=1, max_value=10, value=5)
        
    with st.spinner("Viajando en el tiempo y calculando rendimientos diarios..."):
        try:
            import yfinance as yf
            import pandas as pd
            import plotly.express as px
            import numpy as np
            
            fecha_inicio = pd.Timestamp.today() - pd.DateOffset(years=anios_backtest)
            
            df_ticker = yf.download(ticker_input, start=fecha_inicio, progress=False)
            df_spy = yf.download("SPY", start=fecha_inicio, progress=False)
            
            if df_ticker.empty or df_spy.empty:
                st.error(f"⚠️ No hay suficientes datos para {ticker_input} en ese periodo.")
            else:
                col_ticker = 'Adj Close' if 'Adj Close' in df_ticker.columns else 'Close'
                col_spy = 'Adj Close' if 'Adj Close' in df_spy.columns else 'Close'
                
                serie_ticker = df_ticker[col_ticker].squeeze()
                serie_spy = df_spy[col_spy].squeeze()
                
                datos_historicos = pd.DataFrame({
                    ticker_input: serie_ticker,
                    'SPY': serie_spy
                }).dropna()
                
                if not datos_historicos.empty:
                    retornos_acumulados = datos_historicos / datos_historicos.iloc[0]
                    cartera_ticker = retornos_acumulados[ticker_input] * inversion_inicial
                    cartera_spy = retornos_acumulados['SPY'] * inversion_inicial
                    
                    valor_final_ticker = float(np.array(cartera_ticker)[-1])
                    valor_final_spy = float(np.array(cartera_spy)[-1])
                    
                    rentabilidad_ticker = ((valor_final_ticker / inversion_inicial) - 1) * 100
                    rentabilidad_spy = ((valor_final_spy / inversion_inicial) - 1) * 100
                    alpha = rentabilidad_ticker - rentabilidad_spy 
                    
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    c1.metric(f"Valor Actual ({ticker_input})", f"${valor_final_ticker:,.2f}", f"{rentabilidad_ticker:+.2f}% Total")
                    c2.metric("Valor Actual (S&P 500)", f"${valor_final_spy:,.2f}", f"{rentabilidad_spy:+.2f}% Total")
                    c3.metric("🔥 Alpha Generado", f"{alpha:+.2f}%")
                    
                    df_plot = pd.DataFrame({
                        'Fecha': datos_historicos.index,
                        f"{ticker_input}": np.array(cartera_ticker),
                        'S&P 500': np.array(cartera_spy)
                    }).melt(id_vars=['Fecha'], var_name='Activo', value_name='Capital ($)')
                    
                    fig_backtest = px.line(df_plot, x='Fecha', y='Capital ($)', color='Activo', color_discrete_map={f"{ticker_input}": '#00C0F2', 'S&P 500': '#8c9bba'})
                    fig_backtest.update_xaxes(rangeslider_visible=True)
                    fig_backtest.update_layout(height=450, margin=dict(t=10, b=20, l=0, r=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode='x unified')
                    st.plotly_chart(fig_backtest, use_container_width=True)

                    # GUARDA DATOS EN MEMORIA PARA EL RETRO-ANÁLISIS
                    st.session_state['backtest_data'] = {
                        'fecha': fecha_inicio.strftime('%Y-%m-%d'),
                        'rentabilidad': rentabilidad_ticker
                    }
                    
        except Exception as e:
            st.error(f"Error en la simulación: {e}")

    # --- MOTOR DE RETRO-ANÁLISIS IA ---
    if 'backtest_data' in st.session_state:
        st.markdown("---")
        st.markdown("### 🕵️‍♂️ Auditoría Forense del Pasado (Retro-Análisis)")
        st.markdown(f"¿Habría detectado nuestro algoritmo esta oportunidad (o trampa) si estuviéramos exactamente en **{st.session_state['backtest_data']['fecha']}**?")
        
        with st.spinner("Desconectando datos futuros... Simulando análisis en el pasado..."):
            try:
                fecha_pasada = st.session_state['backtest_data']['fecha']
                rentabilidad_real = st.session_state['backtest_data']['rentabilidad']
                
                prompt_retro = f"""
                Actúa como un analista financiero que ha viajado en el tiempo al año {fecha_pasada}.
                Estás analizando la empresa {ticker_input} en ESE momento exacto. NO conoces el futuro. 
                
                Escribe un breve informe con estas 2 partes:
                1. 🕰️ **Veredicto en {fecha_pasada}:** ¿Qué opinaba el mercado de esta empresa en ese año? ¿Parecía una buena compra basándonos en lo que sabíamos entonces? Mójate y di si hubieras recomendado comprarla o no.
                2. 💥 **Choque con la Realidad (Actualidad):** Hoy sabemos que la rentabilidad real desde ese día ha sido del {rentabilidad_real:+.2f}%. ¿Acertaste en tu veredicto del pasado? ¿Qué evento inesperado ocurrió en estos años que el mercado no supo prever?
                """
                
                model = obtener_modelo_gemini()
                if model:
                    response = model.generate_content(prompt_retro)
                    st.info(response.text)
                else:
                    aviso_gemini_no_configurado()
                    st.info(_retro_analisis_local(ticker_input, fecha_pasada, rentabilidad_real))
            except Exception as e:
                st.error(f"Error al generar el retro-análisis: {e}")
