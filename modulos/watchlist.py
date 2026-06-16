import streamlit as st
import json
import os
import yfinance as yf
import pandas as pd

# Definimos la ruta de la base de datos
DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "watchlist.json")

# --- FUNCIONES DE BASE DE DATOS LOCAL ---
def inicializar_db():
    """Crea la carpeta y el archivo si no existen."""
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, 'w') as f:
            json.dump({}, f)

def cargar_watchlist():
    """Lee el archivo JSON y lo convierte en diccionario."""
    inicializar_db()
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def guardar_watchlist(data):
    """Sobreescribe el archivo JSON con los nuevos datos."""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- INTERFAZ PRINCIPAL ---
def ejecutar_watchlist():
    st.markdown("### 📋 Mi Watchlist Institucional")
    st.markdown("Monitoriza tus acciones favoritas en tiempo real y configura alertas de precio objetivo (Fair Value) para saber exactamente cuándo disparar.")
    
    db = cargar_watchlist()
    
    # -------------------------------------------------------------
    # 1. PANEL DE CONTROL (Añadir / Eliminar Tickers)
    # -------------------------------------------------------------
    with st.expander("⚙️ Gestionar Cartera (Añadir / Eliminar)", expanded=(len(db) == 0)):
        c1, c2, c3 = st.columns([2, 1, 1])
        
        with c1:
            nuevo_ticker = st.text_input("Añadir Ticker (Ej: AAPL, TSLA):").upper().strip()
        with c2:
            precio_objetivo = st.number_input("Precio Objetivo de Compra ($):", min_value=0.0, value=0.0, step=1.0)
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Añadir a Watchlist", type="primary", use_container_width=True):
                if nuevo_ticker:
                    db[nuevo_ticker] = {"target": precio_objetivo}
                    guardar_watchlist(db)
                    st.success(f"✅ {nuevo_ticker} añadido.")
                    st.rerun() # Recarga la app para mostrar el nuevo dato
                    
        st.markdown("---")
        if db:
            c_del1, c_del2 = st.columns([3, 1])
            with c_del1:
                ticker_borrar = st.selectbox("Selecciona un Ticker para eliminar:", list(db.keys()))
            with c_del2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Eliminar", use_container_width=True):
                    del db[ticker_borrar]
                    guardar_watchlist(db)
                    st.warning(f"🗑️ {ticker_borrar} eliminado de la lista.")
                    st.rerun()

    st.markdown("---")

    # -------------------------------------------------------------
    # 2. MOTOR DE DATOS (Extracción Ultra-Robusta)
    # -------------------------------------------------------------
    if not db:
        st.info("Tu Watchlist está vacía. Despliega el menú de arriba para añadir tu primera acción.")
        return

    with st.spinner("Sincronizando precios en tiempo real con Wall Street..."):
        tickers_list = list(db.keys())
        resultados = []
        
        for ticker in tickers_list:
            try:
                # Descargamos 5 días para asegurar que salvamos fines de semana y festivos
                tk = yf.Ticker(ticker)
                hist = tk.history(period="5d")
                
                if not hist.empty and len(hist) >= 2:
                    precio_actual = float(hist['Close'].iloc[-1])
                    precio_ayer = float(hist['Close'].iloc[-2])
                    cambio_pct = ((precio_actual - precio_ayer) / precio_ayer) * 100
                else:
                    # Plan B: Fast Info (Si la historia falla)
                    precio_actual = float(tk.fast_info.last_price)
                    precio_ayer = float(tk.fast_info.previous_close)
                    cambio_pct = ((precio_actual - precio_ayer) / precio_ayer) * 100
                    
                target = float(db[ticker].get("target", 0))
                
                # Calcular alertas matemáticas
                if target > 0:
                    distancia = ((precio_actual - target) / target) * 100
                    alerta = "✅ EN PRECIO" if precio_actual <= target else f"A un -{distancia:.1f}% de caer"
                else:
                    alerta = "Sin Target"
                    
                resultados.append({
                    "Ticker": ticker,
                    "Precio Actual": precio_actual,
                    "Var Diaria (%)": cambio_pct,
                    "Precio Objetivo": target if target > 0 else "-",
                    "Distancia al Target": alerta
                })
                
            except Exception as e:
                # Si algo falla, lo registramos en la tabla en lugar de ocultarlo
                resultados.append({
                    "Ticker": ticker,
                    "Precio Actual": 0.0,
                    "Var Diaria (%)": 0.0,
                    "Precio Objetivo": db[ticker].get("target", 0),
                    "Distancia al Target": f"⚠️ Error de datos"
                })
                
        df_watch = pd.DataFrame(resultados)

    # -------------------------------------------------------------
    # 3. VISUALIZACIÓN (Dashboard)
    # -------------------------------------------------------------
    if not df_watch.empty:
        # KPIs Rápidos (Protegidos contra divisiones por cero o errores en la carga)
        try:
            mejor = df_watch.loc[df_watch['Var Diaria (%)'].idxmax()]
            peor = df_watch.loc[df_watch['Var Diaria (%)'].idxmin()]
            
            c_kpi1, c_kpi2, c_kpi3 = st.columns(3)
            c_kpi1.metric("Activos en Seguimiento", len(df_watch))
            c_kpi2.metric("🚀 Líder del Día", f"{mejor['Ticker']}", f"{mejor['Var Diaria (%)']:.2f}%")
            c_kpi3.metric("🩸 Rezago del Día", f"{peor['Ticker']}", f"{peor['Var Diaria (%)']:.2f}%", delta_color="inverse")
        except:
            st.metric("Activos en Seguimiento", len(df_watch))
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Tabla interactiva con formato
        st.dataframe(
            df_watch.style.format({
                "Precio Actual": "${:.2f}",
                "Var Diaria (%)": "{:+.2f}%",
                "Precio Objetivo": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) and x > 0 else "-"
            }).map(lambda val: 'color: #00ff88; font-weight:bold;' if val > 0 else ('color: #ff0055; font-weight:bold;' if val < 0 else ''), subset=['Var Diaria (%)']),
            use_container_width=True,
            hide_index=True
        )
        
        st.caption("💡 El precio objetivo (Fair Value) lo puedes calcular tú mismo usando el modelo DCF del 'Análisis Fundamental'.")
