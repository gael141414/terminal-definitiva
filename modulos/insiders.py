import streamlit as st
import yfinance as yf
import pandas as pd
from modulos.gemini_helper import aviso_gemini_no_configurado, obtener_modelo_gemini


def _interpretacion_insiders_local(compras_totales, ventas_totales):
    if compras_totales > ventas_totales:
        return "Señal local: sesgo alcista. Hay más compras que ventas recientes, lo que sugiere cierta alineación directiva."
    if ventas_totales > compras_totales * 2:
        return "Señal local: sesgo bajista o de prudencia. Las ventas dominan ampliamente; revisa si son ventas programadas o compensación."
    return "Señal local: neutral. La actividad insider no muestra una lectura clara por sí sola."

def ejecutar_rastreador_insiders(ticker_input):
    st.markdown(f"### 🕵️‍♂️ Rastreador de 'Smart Money' (SEC Form 4): {ticker_input}")
    st.markdown("Analiza las compras y ventas recientes de los directivos (CEOs, CFOs, Board). Si los que dirigen la empresa compran agresivamente, es la señal alcista más fuerte que existe.")

    with st.spinner("Conectando con bases de datos regulatorias y extrayendo transacciones..."):
        try:
            empresa = yf.Ticker(ticker_input)
            # Extraemos las transacciones de insiders
            transacciones = empresa.insider_transactions
            
            if transacciones is None or transacciones.empty:
                st.warning("No se han registrado movimientos recientes de insiders en la SEC para esta empresa.")
            else:
                # Limpiamos y formateamos la tabla
                df_insiders = transacciones.copy()
                
                # Identificar compras y ventas
                df_insiders['Tipo de Operación'] = df_insiders['Shares'].apply(lambda x: '🟢 COMPRA' if x > 0 else '🔴 VENTA')
                
                # Formatear números para que sean legibles
                df_insiders['Shares'] = df_insiders['Shares'].apply(lambda x: f"{int(x):,}")
                if 'Value' in df_insiders.columns:
                    df_insiders['Value'] = df_insiders['Value'].apply(lambda x: f"${int(x):,}" if pd.notnull(x) else "N/A")
                
                # Mostrar métricas rápidas
                compras_totales = len(df_insiders[df_insiders['Tipo de Operación'] == '🟢 COMPRA'])
                ventas_totales = len(df_insiders[df_insiders['Tipo de Operación'] == '🔴 VENTA'])
                
                c1, c2 = st.columns(2)
                c1.metric("🟢 Operaciones de Compra Recientes", compras_totales)
                c2.metric("🔴 Operaciones de Venta Recientes", ventas_totales)
                
                st.markdown("#### 📋 Últimas Transacciones (Filtro SEC)")
                st.dataframe(df_insiders[['Insider', 'Position', 'Tipo de Operación', 'Shares', 'Value', 'Start Date']], use_container_width=True)

                # --- ANÁLISIS DE IA SOBRE EL SENTIMIENTO INSIDER ---
                st.markdown("---")
                st.markdown("### 🧠 Interpretación de la IA (Sentiment Analysis)")
                
                # Preparamos un resumen de datos para no saturar el prompt
                resumen_datos = df_insiders.head(10).to_string()
                
                prompt_insiders = f"""
                Actúa como un analista de 'Insider Trading'. Aquí tienes las últimas transacciones de los directivos de {ticker_input}:
                {resumen_datos}
                
                Analiza esta actividad en un párrafo corto y directo:
                1. ¿Hay pánico vendedor (las ratas abandonan el barco) o convicción compradora?
                2. Ojo: Es normal que los directivos vendan un poco para pagar impuestos o comprarse casas, pero las COMPRAS masivas siempre significan convicción. 
                Da tu veredicto final: ¿La señal de los insiders es Alcista, Bajista o Neutral?
                """
                
                model = obtener_modelo_gemini()
                if model:
                    response = model.generate_content(prompt_insiders)
                    st.info(response.text)
                else:
                    aviso_gemini_no_configurado()
                    st.info(_interpretacion_insiders_local(compras_totales, ventas_totales))

        except Exception as e:
            st.error(f"Error extrayendo datos de Insiders: {e}. Es posible que no haya datos públicos recientes para este Ticker.")
