import streamlit as st
import yfinance as yf
import pandas as pd

def ejecutar_escaner_global():
    st.markdown("### 🌐 Escáner Cuantitativo de Oportunidades")
    st.markdown("Introduce una cesta de acciones y aplica filtros institucionales estrictos para separar las empresas excepcionales de las mediocres.")

    # 1. Input de Tickers
    tickers_input = st.text_area(
        "📦 Cesta de Tickers a escanear (separados por comas):", 
        "AAPL, MSFT, GOOGL, META, TSLA, NVDA, AMZN, NFLX, AMD, INTC, CRM, ADBE",
        help="Escribe los tickers separados por coma."
    )
    
    st.markdown("#### ⚙️ Configura tus Filtros (Reglas Quant)")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        max_per = st.number_input("📉 PER Máximo (Value)", min_value=1.0, max_value=200.0, value=30.0, step=1.0, help="Relación Precio/Beneficio. Menor es más barato.")
    with col2:
        min_roe = st.number_input("📈 ROE Mínimo % (Calidad)", min_value=-50.0, max_value=100.0, value=15.0, step=1.0, help="Retorno sobre el Capital. Mayor a 15% es excelente.")
    with col3:
        min_growth = st.number_input("🚀 Crecimiento Ventas Mínimo %", min_value=-50.0, max_value=200.0, value=10.0, step=1.0, help="Crecimiento de ingresos YoY.")

    # ------------------------------------------------------------------
    # EL BOTÓN DE EJECUCIÓN (Aquí estaba el fallo de la interfaz)
    # ------------------------------------------------------------------
    st.markdown("<br>", unsafe_allow_html=True) # Un poco de espacio
    if st.button("⚡ Ejecutar Escáner Global", type="primary", use_container_width=True):
        
        # Limpiamos la lista de Tickers (quitamos espacios y pasamos a mayúsculas)
        lista_tickers = [t.strip().upper() for t in tickers_input.split(',')]
        
        if not lista_tickers or lista_tickers == ['']:
            st.warning("⚠️ Introduce al menos un Ticker en la caja de texto para escanear.")
        else:
            # Iniciamos la barra de progreso
            barra_progreso = st.progress(0, text="Iniciando conexión con bases de datos...")
            resultados = []
            
            for i, ticker in enumerate(lista_tickers):
                # Actualizamos el texto de la barra para que el usuario sepa qué hace
                barra_progreso.progress((i + 1) / len(lista_tickers), text=f"Analizando fundamentales de: {ticker}...")
                
                try:
                    info = yf.Ticker(ticker).info
                    
                    # Extraer métricas clave de forma segura. Si no existen, ponemos valores por defecto que no rompan el filtro
                    per = info.get('trailingPE', 999) # Si no tiene PER, le ponemos 999 para que suspenda el filtro de barato
                    roe = info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0
                    crecimiento = info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0
                    deuda = info.get('debtToEquity', 0)
                    sector = info.get('sector', 'Desconocido')
                    
                    # Guardar datos en crudo en nuestro diccionario
                    resultados.append({
                        'Ticker': ticker,
                        'Sector': sector,
                        'PER': round(float(per), 2),
                        'ROE (%)': round(float(roe), 2),
                        'Crecimiento YoY (%)': round(float(crecimiento), 2),
                        'Deuda/Equity': round(float(deuda), 2) if deuda else 0.0
                    })
                except Exception as e:
                    # Si un ticker falla (porque está mal escrito o Yahoo no lo tiene), lo ignoramos silenciosamente
                    pass 
                
            # Borrar barra al terminar el bucle
            barra_progreso.empty() 
            
            # --- PROCESAMIENTO DE RESULTADOS ---
            if not resultados:
                st.error("No se ha podido extraer información de ninguno de los Tickers proporcionados. Comprueba que estén bien escritos.")
            else:
                df = pd.DataFrame(resultados)
                
                # 2. Aplicar los Filtros Matemáticos del Usuario
                df_filtrado = df[
                    (df['PER'] <= max_per) & 
                    (df['ROE (%)'] >= min_roe) & 
                    (df['Crecimiento YoY (%)'] >= min_growth)
                ]
                
                st.markdown("---")
                if df_filtrado.empty:
                    st.error("🩸 Masacre Cuantitativa: NINGUNA empresa de tu cesta ha sobrevivido a tus filtros estrictos. El mercado está caro o exige peores calidades.")
                    st.markdown("#### Datos Crudos (Antes de filtrar)")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.success(f"🏆 ¡Éxito! {len(df_filtrado)} empresas han superado el escáner de calidad institucional.")
                    
                    # Mostrar tabla con formato condicional (verde si es muy bueno)
                    st.dataframe(
                        df_filtrado.style.highlight_max(subset=['ROE (%)', 'Crecimiento YoY (%)'], color='#1e4bd8')
                                        .highlight_min(subset=['PER'], color='#00C0F2'),
                        use_container_width=True
                    )
