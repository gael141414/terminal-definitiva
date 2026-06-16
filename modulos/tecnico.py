import streamlit as st
import yfinance as yf
import pandas as pd
import streamlit.components.v1 as components

# Importamos las herramientas de gráficos y utilidades
from charts import plot_flujo_opciones, plot_visor_trend_following, plot_visor_breakout_volatilidad, plot_visor_reversion_media, plot_visor_ichimoku
from modulos.utils import obtener_datos_directiva, obtener_transacciones_insiders

# -------------------------------------------------------------------
# 1. WIDGET NATIVO DE TRADINGVIEW
# -------------------------------------------------------------------
def renderizar_grafico_tradingview(ticker):
    codigo_html = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_container" style="height:600px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
      "autosize": true, "symbol": "{ticker}", "interval": "D", "timezone": "Etc/UTC",
      "theme": "dark", "style": "1", "locale": "es", "enable_publishing": false,
      "backgroundColor": "#0b0e14", "gridColor": "#1f293d", "hide_top_toolbar": false,
      "hide_legend": false, "save_image": false, "container_id": "tv_chart_container",
      "toolbar_bg": "#131722", "studies": ["Volume@tv-basicstudies"]
      }});
      </script>
    </div>
    """
    components.html(codigo_html, height=600)

# -------------------------------------------------------------------
# FUNCIÓN PRINCIPAL DEL MÓDULO
# -------------------------------------------------------------------
def ejecutar_tecnico_y_opciones(ticker_input):
    """Muestra el gráfico interactivo, visores quant y datos de derivados."""
    st.markdown(f"### 📈 Terminal de Análisis Técnico y Flujos: {ticker_input}")
    
    # 1. Gráfico General (TradingView)
    st.caption("Visor interactivo global. Utiliza las herramientas de la izquierda para trazar soportes y resistencias manuales.")
    renderizar_grafico_tradingview(ticker_input)
    
    # ==========================================================
    # 2. CAJA DE CAMBIOS: VISORES CUANTITATIVOS (NUEVO)
    # ==========================================================
    st.markdown("---")
    st.markdown("### 🤖 Motores Algorítmicos de Trading")
    st.markdown("Selecciona un visor estratégico. Cada algoritmo está diseñado para cazar un comportamiento específico del mercado mediante confluencia matemática.")
    
    visor_seleccionado = st.radio(
        "🎯 Selecciona el Motor Algorítmico:",
        [
            "🌊 Visor 1: Trend Following (EMAs + MACD + RSI)",
            "💥 Visor 2: Breakout & Volatilidad (Próximamente)",
            "🧲 Visor 3: Reversión a la Media (Próximamente)",
            "🏯 Visor 4: Ichimoku Cloud (Próximamente)"
        ],
        horizontal=True
    )
    
    if "Visor 1" in visor_seleccionado:
        st.markdown("#### 🌊 Sistema de Seguimiento de Tendencias")
        st.caption("Filtra el ruido diario. Busca subir a olas institucionales confirmando que hay tendencia (EMAs), aceleración (MACD) y margen de subida (RSI < 70).")
        
        with st.spinner("Compilando algoritmo Trend Following..."):
            fig, df = plot_visor_trend_following(ticker_input, period="1y")
            
            if fig is not None and df is not None:
                st.plotly_chart(fig, use_container_width=True)
                
                # --- LECTOR DE SEÑALES INTELIGENTE ---
                st.markdown("##### 🤖 Veredicto Algorítmico del Visor")
                ultimo = df.iloc[-1]
                ayer = df.iloc[-2]
                
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.markdown("**1. Filtro de Tendencia**")
                    if ultimo['EMA_50'] > ultimo['EMA_200']:
                        st.success("🟢 **Alcista:** EMA 50 > EMA 200.")
                        tendencia_ok = True
                    else:
                        st.error("🔴 **Bajista:** EMA 50 < EMA 200.")
                        tendencia_ok = False
                
                with c2:
                    st.markdown("**2. Gatillo de Momentum**")
                    cruce_alcista = ultimo['MACD'] > ultimo['Señal'] and ayer['MACD'] <= ayer['Señal']
                    if cruce_alcista:
                        st.success("🚀 **Señal:** Cruce alcista hoy/ayer.")
                        gatillo_ok = True
                    elif ultimo['MACD'] > ultimo['Señal']:
                        st.info("🟢 MACD en fase compradora.")
                        gatillo_ok = True
                    else:
                        st.warning("🔴 MACD en fase correctora.")
                        gatillo_ok = False
                        
                with c3:
                    st.markdown("**3. Riesgo de Sobrecompra**")
                    if ultimo['RSI'] > 70:
                        st.error(f"🔴 **Peligro ({ultimo['RSI']:.0f}):** Sobrecomprada.")
                        rsi_ok = False
                    elif ultimo['RSI'] < 30:
                        st.success(f"🟢 **Oportunidad ({ultimo['RSI']:.0f}):** Sobrevendida.")
                        rsi_ok = True
                    else:
                        st.info(f"⚖️ **Neutral ({ultimo['RSI']:.0f}):** En rango sano.")
                        rsi_ok = True

                st.markdown("---")
                if tendencia_ok and gatillo_ok and rsi_ok:
                    st.success("✅ **CONFLUENCIA TOTAL: SEÑAL DE COMPRA FUERTE.** Tendencia alcista, momentum positivo y RSI sano.")
                elif tendencia_ok and gatillo_ok and not rsi_ok:
                    st.warning("⚠️ **PRECAUCIÓN: LLEGAS TARDE.** Tendencia y momentum alcistas, pero RSI en extrema sobrecompra.")
                else:
                    st.info("⏳ **SIN CONFLUENCIA:** Los indicadores se contradicen. Mantente al margen.")
            else:
                st.warning("No hay suficientes datos históricos para ejecutar este visor.")

    elif "Visor 2" in visor_seleccionado:
        st.markdown("#### 💥 Sistema de Breakout (Compresión de Volatilidad)")
        st.caption("Detecta explosiones inminentes de precio. Busca momentos donde las Bandas de Bollinger se estrechan dentro de los Canales de Keltner (Squeeze), indicando que el dinero institucional está acumulando antes de un movimiento brusco.")
        
        with st.spinner("Midiendo desviación estándar y rangos de volatilidad..."):
            fig_vol, df_vol = plot_visor_breakout_volatilidad(ticker_input, period="1y")
            
            if fig_vol is not None and df_vol is not None:
                st.plotly_chart(fig_vol, use_container_width=True)
                
                # --- LECTOR DE SEÑALES INTELIGENTE ---
                st.markdown("##### 🤖 Veredicto Algorítmico del Visor")
                
                ultimo = df_vol.iloc[-1]
                ayer = df_vol.iloc[-2]
                
                c1, c2, c3 = st.columns(3)
                
                # 1. Estado de la Volatilidad (Squeeze)
                with c1:
                    st.markdown("**1. Estado de Compresión**")
                    if ultimo['Squeeze_On']:
                        st.error("🔴 **COMPRESIÓN MÁXIMA:** Las Bandas de Bollinger están dentro de Keltner. El mercado está comprimiendo energía como un muelle. Movimiento violento inminente.")
                        squeeze_activo = True
                    elif not ultimo['Squeeze_On'] and ayer['Squeeze_On']:
                        st.success("🚀 **¡RUPTURA (SQUEEZE FIRED)!** El muelle acaba de saltar hoy. La volatilidad se ha liberado.")
                        squeeze_activo = False
                    else:
                        st.info("🟢 **Expansión Normal:** El mercado está en fase de movimiento fluido. No hay acumulación latente.")
                        squeeze_activo = False

                # 2. Dirección del Movimiento (Momentum)
                with c2:
                    st.markdown("**2. Sesgo de Dirección**")
                    if ultimo['Momentum'] > 0 and ultimo['Close'] > ultimo['SMA_20']:
                        st.success("📈 **Sesgo Alcista:** El precio empuja por encima de la media móvil. Mayor probabilidad de que la ruptura sea hacia arriba.")
                        sesgo = "alcista"
                    elif ultimo['Momentum'] < 0 and ultimo['Close'] < ultimo['SMA_20']:
                        st.error("📉 **Sesgo Bajista:** El precio pesa por debajo de la media móvil. Mayor probabilidad de desplome.")
                        sesgo = "bajista"
                    else:
                        st.warning("⚖️ **Dirección Indecisa:** Momentum plano.")
                        sesgo = "neutral"

                # 3. Confirmación de Volumen
                with c3:
                    st.markdown("**3. Flujo Institucional (Volumen)**")
                    if ultimo['Volume'] > ultimo['Vol_SMA'] * 1.5:
                        st.success("🔥 **Volumen Extremo (>150% media):** ¡Dinero inteligente detectado! Si hay ruptura hoy, es muy fiable.")
                        volumen_fuerte = True
                    elif ultimo['Volume'] > ultimo['Vol_SMA']:
                        st.info("📊 **Volumen Alto:** Presión institucional por encima de la media.")
                        volumen_fuerte = True
                    else:
                        st.warning("🔇 **Volumen Bajo:** Movimientos con poco capital de respaldo. Riesgo de falsa ruptura (Fakeout).")
                        volumen_fuerte = False

                # --- SÍNTESIS FINAL DE LA ESTRATEGIA ---
                st.markdown("---")
                if not ultimo['Squeeze_On'] and ayer['Squeeze_On'] and volumen_fuerte:
                    st.success(f"✅ **¡GATILLO DE BREAKOUT {sesgo.upper()}!** El sistema acaba de detectar la liberación de la volatilidad acompañada de fuerte volumen institucional. Punto de entrada óptimo.")
                elif squeeze_activo:
                    st.warning(f"⏳ **MODO ESPERA ACTIVO:** La acción está en extrema compresión con un sesgo **{sesgo}**. Prepara tus órdenes condicionadas. No operes hasta que las bandas rompan.")
                else:
                    st.info("🤷‍♂️ **SIN SETUP CLARO:** El precio se está moviendo con normalidad. Este visor no detecta anomalías de volatilidad en este momento. Revisa el Visor 1 (Tendencia).")
            else:
                st.warning("Datos insuficientes para calcular la volatilidad (Se requieren 50 sesiones).")
    
    elif "Visor 3" in visor_seleccionado:
        st.markdown("#### 🧲 Sistema de Reversión a la Media (Swing Trading)")
        st.caption("Aprovecha los extremos psicológicos. Busca el pánico irracional para comprar barato y la euforia desmedida para vender. El precio siempre tiende a volver a su media institucional (SMA 20).")
        
        with st.spinner("Calculando desviaciones estándar y StochRSI..."):
            fig_rev, df_rev = plot_visor_reversion_media(ticker_input, period="1y")
            
            if fig_rev is not None and df_rev is not None:
                st.plotly_chart(fig_rev, use_container_width=True)
                
                # --- LECTOR DE SEÑALES INTELIGENTE ---
                st.markdown("##### 🤖 Veredicto Algorítmico del Visor")
                
                ultimo = df_rev.iloc[-1]
                ayer = df_rev.iloc[-2]
                
                c1, c2, c3 = st.columns(3)
                
                # 1. Medición de Extremos (Z-Score)
                with c1:
                    st.markdown("**1. Tensión Estadística (Z-Score)**")
                    z_actual = ultimo['Z_Score']
                    if z_actual <= -2:
                        st.success(f"🟢 **Pánico Extremo ({z_actual:.2f}):** El precio se ha hundido muy por debajo de su media. La goma elástica está tensada al máximo hacia abajo.")
                        tension = "sobrevendido"
                    elif z_actual >= 2:
                        st.error(f"🔴 **Euforia Absoluta ({z_actual:.2f}):** El precio se ha disparado. Wall Street está irracionalmente optimista. Riesgo de caída inminente.")
                        tension = "sobrecomprado"
                    else:
                        st.info(f"⚖️ **Zona Neutral ({z_actual:.2f}):** El precio orbita cerca de su media justa de 20 días.")
                        tension = "neutral"

                # 2. Timing de Giro (StochRSI)
                with c2:
                    st.markdown("**2. Aceleración del Giro (StochRSI)**")
                    cruce_alcista_stoch = ultimo['Stoch_K'] > ultimo['Stoch_D'] and ayer['Stoch_K'] <= ayer['Stoch_D']
                    cruce_bajista_stoch = ultimo['Stoch_K'] < ultimo['Stoch_D'] and ayer['Stoch_K'] >= ayer['Stoch_D']
                    
                    if cruce_alcista_stoch and ultimo['Stoch_K'] < 40:
                        st.success("🚀 **Gatillo Alcista:** Oscilador cruzando al alza desde zona baja.")
                        giro = "comprar"
                    elif cruce_bajista_stoch and ultimo['Stoch_K'] > 60:
                        st.error("🩸 **Gatillo Bajista:** Oscilador cruzando a la baja desde la cima.")
                        giro = "vender"
                    elif ultimo['Stoch_K'] < 20:
                        st.info("📉 Agotamiento bajista. Esperando cruce.")
                        giro = "esperar_compra"
                    elif ultimo['Stoch_K'] > 80:
                        st.info("📈 Agotamiento alcista. Esperando cruce.")
                        giro = "esperar_venta"
                    else:
                        st.warning("〰️ Sin momento direccional claro.")
                        giro = "neutral"

                # 3. Margen de Beneficio
                with c3:
                    st.markdown("**3. Distancia a la Media**")
                    distancia_pct = ((ultimo['SMA_20'] - ultimo['Close']) / ultimo['Close']) * 100
                    if distancia_pct > 0:
                        st.success(f"🎯 **Target Alcista:** Si el precio vuelve a la media (SMA 20), el margen de ganancia estimado es del **+{distancia_pct:.2f}%**.")
                    else:
                        st.error(f"📉 **Riesgo de Caída:** Si el precio revierte a la media, la corrección estimada sería del **{distancia_pct:.2f}%**.")

                # --- SÍNTESIS FINAL DE LA ESTRATEGIA ---
                st.markdown("---")
                if tension == "sobrevendido" and (giro == "comprar" or giro == "esperar_compra"):
                    st.success("✅ **SEÑAL DE SWING TRADING (COMPRA):** Máxima tensión bajista + giro detectado. Alta probabilidad matemática de que el precio 'rebote' hacia la línea naranja (SMA 20).")
                elif tension == "sobrecomprado" and (giro == "vender" or giro == "esperar_venta"):
                    st.error("🚨 **SEÑAL DE CORRECCIÓN INMINENTE (VENTA):** El mercado está sobrecalentado y el oscilador empieza a darse la vuelta. Es momento de asegurar ganancias, no de comprar.")
                else:
                    st.info("⏳ **SIN SEÑAL CLARA:** El precio no está en un extremo estadístico lo suficientemente violento como para justificar una operación de reversión a la media.")
            else:
                st.warning("Datos insuficientes para calcular las desviaciones de reversión.")
    
    elif "Visor 4" in visor_seleccionado:
        st.markdown("#### 🏯 Sistema Ichimoku (Equilibrio y Soportes Futuros)")
        st.caption("Un ecosistema holístico. Si el precio está por encima de la Nube (Kumo), estamos en territorio alcista seguro. Comprueba los cruces de las líneas Tenkan y Kijun para el 'Timing' de entrada, y vigila que el Flujo Institucional (OBV) acompañe la subida.")
        
        with st.spinner("Proyectando soportes y resistencias 26 días en el futuro..."):
            fig_ichi, df_ichi = plot_visor_ichimoku(ticker_input, period="1y")
            
            if fig_ichi is not None and df_ichi is not None:
                st.plotly_chart(fig_ichi, use_container_width=True)
                
                # --- LECTOR DE SEÑALES INTELIGENTE ---
                st.markdown("##### 🤖 Veredicto Algorítmico del Visor")
                
                ultimo = df_ichi.iloc[-1]
                ayer = df_ichi.iloc[-2]
                
                c1, c2, c3 = st.columns(3)
                
                # 1. El Precio vs La Nube (Tendencia Macro)
                with c1:
                    st.markdown("**1. Filtro de la Nube (Kumo)**")
                    nube_superior = max(ultimo['Senkou_A'], ultimo['Senkou_B'])
                    nube_inferior = min(ultimo['Senkou_A'], ultimo['Senkou_B'])
                    
                    if ultimo['Close'] > nube_superior:
                        st.success("🟢 **Alcista Fuerte:** El precio navega por encima de la Nube. Cielos despejados para comprar.")
                        kumo_ok = True
                    elif ultimo['Close'] < nube_inferior:
                        st.error("🔴 **Bajista Fuerte:** El precio está hundido bajo la Nube. Prohibido operar en largo.")
                        kumo_ok = False
                    else:
                        st.warning("⚡ **Zona de Turbulencia:** El precio está dentro de la Nube. Consolidación e incertidumbre. No operar.")
                        kumo_ok = False

                # 2. Cruces de Conversión vs Base (Gatillo)
                with c2:
                    st.markdown("**2. Timing (Tenkan vs Kijun)**")
                    cruce_alcista = ultimo['Tenkan'] > ultimo['Kijun'] and ayer['Tenkan'] <= ayer['Kijun']
                    cruce_bajista = ultimo['Tenkan'] < ultimo['Kijun'] and ayer['Tenkan'] >= ayer['Kijun']
                    
                    if cruce_alcista:
                        st.success("🚀 **Señal Fresca:** Línea rápida (Azul) acaba de cruzar al alza la línea base (Naranja).")
                        cruces_ok = True
                    elif ultimo['Tenkan'] > ultimo['Kijun']:
                        st.info("🟢 **Momento Positivo:** Línea rápida sigue liderando por encima de la base.")
                        cruces_ok = True
                    elif cruce_bajista:
                        st.error("🩸 **Corte Bajista:** Línea rápida cruzando a la baja. Cierre de posiciones.")
                        cruces_ok = False
                    else:
                        st.warning("🔴 **Momento Negativo:** Línea rápida por debajo de la base.")
                        cruces_ok = False

                # 3. Flujo Institucional (OBV)
                with c3:
                    st.markdown("**3. Confirmación Institucional**")
                    if ultimo['OBV'] > ultimo['OBV_EMA'] and ayer['OBV'] <= ayer['OBV_EMA']:
                        st.success("💰 **Entrada de Capital:** OBV cruzando su media al alza. Instituciones inyectando dinero.")
                        obv_ok = True
                    elif ultimo['OBV'] > ultimo['OBV_EMA']:
                        st.info("📈 **Acumulación:** Flujo de dinero constante y respaldando el movimiento.")
                        obv_ok = True
                    else:
                        st.error("📉 **Distribución (Riesgo):** Las instituciones están descargando acciones. El volumen no acompaña al precio.")
                        obv_ok = False

                # --- SÍNTESIS FINAL DE LA ESTRATEGIA ---
                st.markdown("---")
                if kumo_ok and cruces_ok and obv_ok:
                    st.success("✅ **CONFLUENCIA JAPONESA (SEÑAL FUERTE):** Cielos despejados por encima de la nube, las líneas rápidas lideran la subida y el volumen confirma que es dinero real, no minorista. Gatillo de compra habilitado.")
                elif kumo_ok and cruces_ok and not obv_ok:
                    st.warning("⚠️ **DIVERGENCIA DE VOLUMEN:** El sistema Ichimoku da compra fuerte, pero las instituciones están sacando dinero (OBV cayendo). Podría ser una trampa alcista (Bull Trap).")
                elif not kumo_ok:
                    st.info("⏳ **ZONA DE EXCLUSIÓN:** Mientras el precio no escape de la Nube (hacia arriba), la estrategia japonesa exige estricta paciencia.")
                else:
                    st.info("〰️ **MERCADO MIXTO:** No hay confluencia clara entre la tendencia macro (Nube) y el momentum a corto plazo. ")
            else:
                st.warning("Datos insuficientes para dibujar el Ichimoku Cloud.")

    # ==========================================================
    # 3. MERCADO DE OPCIONES Y DERIVADOS (TU CÓDIGO ORIGINAL)
    # ==========================================================
    st.markdown("---")
    st.markdown("#### 🕵️ El Rastro del Dinero: Mercado de Derivados (Opciones)")
    st.caption("Los inversores institucionales compran opciones (Calls para apostar al alza, Puts para protegerse). Analizamos el sentimiento de Wall Street.")

    with st.spinner("Descargando la cadena de derivados de Wall Street..."):
        fig_opciones, diag_opciones = plot_flujo_opciones(ticker_input)
        
        if fig_opciones:
            st.plotly_chart(fig_opciones, use_container_width=True)
            if "CODICIA" in diag_opciones:
                st.success(diag_opciones)
            elif "MIEDO" in diag_opciones:
                st.error(diag_opciones)
            else:
                st.info(diag_opciones)
        else:
            st.warning(diag_opciones if diag_opciones else "Datos de opciones no disponibles.")

    # ==========================================================
    # 4. ANÁLISIS DE LA DIRECTIVA (TU CÓDIGO ORIGINAL)
    # ==========================================================
    st.markdown("---")
    st.markdown("#### 👔 Análisis de la Directiva y Sentimiento del Mercado")
    st.caption("Verificamos si los directivos tienen 'Skin in the Game' y sus movimientos recientes de compra/venta (Formulario 4).")
    
    insiders, inst, short = obtener_datos_directiva(ticker_input)
    col_dir1, col_dir2, col_dir3 = st.columns(3)
    
    if insiders is not None:
        estado_insiders = "Excelente" if insiders > 5 else "Bajo"
        col_dir1.metric("Propiedad Insiders", f"{insiders:.2f}%", estado_insiders, delta_color="normal" if insiders > 5 else "off")
        estado_inst = "Alta convicción" if inst > 60 else "Poco respaldo"
        col_dir2.metric("Propiedad Institucional", f"{inst:.2f}%", estado_inst, delta_color="off")
        estado_short = "Ataque Bajista" if short > 5 else "Sano"
        color_short = "inverse" if short > 5 else "normal"
        col_dir3.metric("Short Ratio", f"{short:.2f}", estado_short, delta_color=color_short)
    else:
        st.info("Datos de accionariado no disponibles.")

    df_insiders = obtener_transacciones_insiders(ticker_input)
    if df_insiders is not None and not df_insiders.empty:
        def color_transaction(val):
            if isinstance(val, str):
                if 'Buy' in val or 'Purchase' in val: return 'color: #2ca02c; font-weight: bold'
                elif 'Sale' in val or 'Sell' in val: return 'color: #d62728'
            return ''
        st.dataframe(df_insiders.style.map(color_transaction, subset=['Transaction']), use_container_width=True)
    else:
        st.info("No se han registrado transacciones recientes de insiders.")

    # ==========================================================
    # 5. RANKING DE MERCADO (TU CÓDIGO ORIGINAL MOVIDO AL FINAL)
    # ==========================================================
    st.markdown("---")
    st.markdown("### 🏆 Las Mejores Empresas del Mercado (Buffett Ranking)")
    st.caption("Esta lista se genera automáticamente analizando cientos de empresas mediante el script `screener.py` en segundo plano.")
    
    try:
        df_ranking = pd.read_csv("ranking_mercado.csv")
        podio1, podio2, podio3 = st.columns(3)
        if len(df_ranking) >= 3:
            top1, top2, top3 = df_ranking.iloc[0], df_ranking.iloc[1], df_ranking.iloc[2]
            podio1.metric(f"🥇 1º - {top1['Ticker']}", f"Score: {top1['Buffett Score']}/100", f"ROE: {top1['ROE %']}%")
            podio2.metric(f"🥈 2º - {top2['Ticker']}", f"Score: {top2['Buffett Score']}/100", f"ROE: {top2['ROE %']}%")
            podio3.metric(f"🥉 3º - {top3['Ticker']}", f"Score: {top3['Buffett Score']}/100", f"ROE: {top3['ROE %']}%")
        
        st.dataframe(
            df_ranking.style.background_gradient(subset=['Buffett Score'], cmap='Greens')
                            .background_gradient(subset=['ROE %'], cmap='Blues').format(precision=2),
            use_container_width=True, height=400
        )
    except FileNotFoundError:
        st.warning("⚠️ Todavía no hay datos del mercado. Ejecuta `python screener.py` en tu terminal para generarlos.")
