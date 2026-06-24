import json
import os
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

# Definimos la ruta de la base de datos
DB_FOLDER = "data"
DB_FILE = os.path.join(DB_FOLDER, "watchlist.json")


# --- FUNCIONES DE BASE DE DATOS LOCAL ---
def inicializar_db():
    """Crea la carpeta y el archivo si no existen."""
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)


def cargar_watchlist():
    """Lee el archivo JSON y lo convierte en diccionario."""
    inicializar_db()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def guardar_watchlist(data):
    """Sobreescribe el archivo JSON con los nuevos datos."""
    inicializar_db()
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.1f}/100"
    except Exception:
        return "-"


def _fmt_pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:+.1f}%"
    except Exception:
        return "-"


def _normalizar_item(item: Any) -> dict[str, Any]:
    """Normaliza watchlist antigua y nueva.

    Formato antiguo: {"AAPL": {"target": 150}}
    Formato nuevo: añade last_analysis con score, acción y margen de seguridad.
    """

    if isinstance(item, dict):
        return item
    return {"target": 0.0}


def _extraer_last_analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("last_analysis", {})
    return analysis if isinstance(analysis, dict) else {}


# --- INTERFAZ PRINCIPAL ---
def ejecutar_watchlist():
    st.markdown("### 📋 Mi Watchlist Institucional")
    st.markdown(
        "Monitoriza tus acciones favoritas, precios objetivo y snapshots guardados desde Research Core. "
        "La watchlist funciona en local con `data/watchlist.json`."
    )

    db = cargar_watchlist()

    # -------------------------------------------------------------
    # 1. PANEL DE CONTROL (Añadir / Eliminar Tickers)
    # -------------------------------------------------------------
    with st.expander("⚙️ Gestionar Watchlist", expanded=(len(db) == 0)):
        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            nuevo_ticker = st.text_input("Añadir Ticker (Ej: AAPL, TSLA):").upper().strip()
        with c2:
            precio_objetivo = st.number_input("Precio Objetivo de Compra ($):", min_value=0.0, value=0.0, step=1.0)
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Añadir a Watchlist", type="primary", use_container_width=True):
                if nuevo_ticker:
                    existing = _normalizar_item(db.get(nuevo_ticker, {}))
                    existing["target"] = precio_objetivo
                    existing.setdefault("source", "Manual")
                    db[nuevo_ticker] = existing
                    guardar_watchlist(db)
                    st.success(f"✅ {nuevo_ticker} añadido.")
                    st.rerun()

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
    # 2. MOTOR DE DATOS
    # -------------------------------------------------------------
    if not db:
        st.info("Tu Watchlist está vacía. Añade una acción manualmente o guarda un análisis desde 🧩 Research Core → 💾 Seguimiento.")
        return

    with st.spinner("Sincronizando precios y snapshots de análisis..."):
        tickers_list = list(db.keys())
        resultados = []

        for ticker in tickers_list:
            item = _normalizar_item(db.get(ticker, {}))
            analysis = _extraer_last_analysis(item)

            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="5d")

                if not hist.empty and len(hist) >= 2:
                    precio_actual = float(hist["Close"].iloc[-1])
                    precio_ayer = float(hist["Close"].iloc[-2])
                    cambio_pct = ((precio_actual - precio_ayer) / precio_ayer) * 100
                else:
                    precio_actual = float(tk.fast_info.last_price)
                    precio_ayer = float(tk.fast_info.previous_close)
                    cambio_pct = ((precio_actual - precio_ayer) / precio_ayer) * 100

                target = _as_float(item.get("target"), 0.0)

                if target > 0:
                    distancia = ((precio_actual - target) / target) * 100
                    alerta = "✅ EN PRECIO" if precio_actual <= target else f"A un -{distancia:.1f}% de caer"
                else:
                    alerta = "Sin Target"

                resultados.append(
                    {
                        "Ticker": ticker,
                        "Precio Actual": precio_actual,
                        "Var Diaria (%)": cambio_pct,
                        "Precio Objetivo": target if target > 0 else "-",
                        "Distancia al Target": alerta,
                        "Acción Research": analysis.get("action", "-"),
                        "ValueQuant": analysis.get("valuequant_score"),
                        "Buffett": analysis.get("buffett_score"),
                        "Margen Seguridad": analysis.get("margin_of_safety"),
                        "Régimen Valoración": analysis.get("valuation_regime", "-"),
                        "Comparador": analysis.get("competitor", "-"),
                        "Fuente": item.get("source", "Manual"),
                        "Último análisis": item.get("last_saved_at", "-"),
                    }
                )

            except Exception:
                resultados.append(
                    {
                        "Ticker": ticker,
                        "Precio Actual": 0.0,
                        "Var Diaria (%)": 0.0,
                        "Precio Objetivo": item.get("target", 0),
                        "Distancia al Target": "⚠️ Error de datos",
                        "Acción Research": analysis.get("action", "-"),
                        "ValueQuant": analysis.get("valuequant_score"),
                        "Buffett": analysis.get("buffett_score"),
                        "Margen Seguridad": analysis.get("margin_of_safety"),
                        "Régimen Valoración": analysis.get("valuation_regime", "-"),
                        "Comparador": analysis.get("competitor", "-"),
                        "Fuente": item.get("source", "Manual"),
                        "Último análisis": item.get("last_saved_at", "-"),
                    }
                )

        df_watch = pd.DataFrame(resultados)

    # -------------------------------------------------------------
    # 3. VISUALIZACIÓN
    # -------------------------------------------------------------
    if not df_watch.empty:
        try:
            mejor = df_watch.loc[df_watch["Var Diaria (%)"].idxmax()]
            peor = df_watch.loc[df_watch["Var Diaria (%)"].idxmin()]
            con_research = df_watch[df_watch["Fuente"] == "Research Core"]

            c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
            c_kpi1.metric("Activos", len(df_watch))
            c_kpi2.metric("Con Research", len(con_research))
            c_kpi3.metric("🚀 Líder Día", f"{mejor['Ticker']}", f"{mejor['Var Diaria (%)']:.2f}%")
            c_kpi4.metric("🩸 Rezago Día", f"{peor['Ticker']}", f"{peor['Var Diaria (%)']:.2f}%", delta_color="inverse")
        except Exception:
            st.metric("Activos en Seguimiento", len(df_watch))

        st.markdown("<br>", unsafe_allow_html=True)

        st.dataframe(
            df_watch.style.format(
                {
                    "Precio Actual": "${:.2f}",
                    "Var Diaria (%)": "{:+.2f}%",
                    "Precio Objetivo": lambda x: f"${x:.2f}" if isinstance(x, (int, float)) and x > 0 else "-",
                    "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                    "Buffett": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                    "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "-",
                }
            ).map(
                lambda val: "color: #00ff88; font-weight:bold;" if val > 0 else ("color: #ff0055; font-weight:bold;" if val < 0 else ""),
                subset=["Var Diaria (%)"],
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Los tickers guardados desde Research Core incluyen acción operativa, score, margen de seguridad y target de seguimiento."
        )
