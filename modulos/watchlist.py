import json
import os
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.watchlist_alerts import alert_summary, build_watchlist_alerts
from modulos.analysis_store import score_evolution_summary, score_history_for_ticker

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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sí", "si", "yes", "y"}
    return bool(value)


def _analysis_red_flags_count(analysis: dict[str, Any]) -> int:
    explicit = analysis.get("score_red_flags_count")
    try:
        if explicit is not None:
            return max(0, int(explicit))
    except Exception:
        pass

    red_flags = analysis.get("red_flags")
    if isinstance(red_flags, list):
        return len(red_flags)
    return 0


def _score_decision_bucket(
    *,
    score_action: str,
    quality_adjusted: bool,
    red_flags_count: int,
    confidence_label: str,
    final_score: Any,
) -> str:
    """Clasifica el activo para lectura rápida en watchlist."""

    action = str(score_action or "").lower()
    confidence = str(confidence_label or "").lower()
    score = _as_float(final_score, 0.0)

    if red_flags_count > 0:
        return "🔴 Riesgo crítico"
    if quality_adjusted:
        return "🟠 Revisión manual"
    if "prioritario" in action:
        return "🟢 Prioritario"
    if "matices" in action:
        return "🟡 Candidato con matices"
    if "esperar" in action or confidence == "baja":
        return "⚪ Esperar datos"
    if "baja prioridad" in action or score < 50:
        return "⚫ Baja prioridad"
    if score >= 65:
        return "🟡 Candidato"
    return "⚪ Observación"


def _watchlist_priority_score(record: dict[str, Any]) -> float:
    """Ranking 0-100 para ordenar la watchlist por prioridad de análisis."""

    score = _as_float(record.get("ValueQuant"), 0.0)
    raw_score = _as_float(record.get("Score bruto"), score)
    confidence = _as_float(record.get("Confianza"), 0.0)
    margin = _as_float(record.get("Margen Seguridad"), 0.0)
    red_flags = _as_float(record.get("Red Flags"), 0.0)
    action = str(record.get("Acción Score", "") or "").lower()
    quality_adjusted = _as_bool(record.get("Ajuste Calidad"))

    priority = score * 0.62 + raw_score * 0.18 + (confidence * 100.0) * 0.12

    if margin > 0:
        priority += min(10.0, margin * 35.0)
    elif margin < -0.10:
        priority -= min(10.0, abs(margin) * 25.0)

    if "prioritario" in action:
        priority += 8.0
    elif "matices" in action:
        priority += 3.0
    elif "revisión manual" in action or "riesgos críticos" in action:
        priority -= 10.0
    elif "esperar" in action:
        priority -= 8.0
    elif "baja prioridad" in action:
        priority -= 15.0

    if quality_adjusted:
        priority -= 7.0
    if red_flags > 0:
        priority -= min(14.0, red_flags * 7.0)

    return round(max(0.0, min(100.0, priority)), 1)


def _trend_priority_adjustment(summary: dict[str, Any]) -> float:
    """Ajuste pequeño de prioridad por evolución temporal del score."""

    delta = _as_float(summary.get("delta_score"), 0.0)
    trend = str(summary.get("trend_label", "") or "").lower()

    if "mejora" in trend:
        return round(min(8.0, max(2.0, delta * 0.9)), 1)
    if "deterioro" in trend:
        return round(max(-10.0, min(-2.0, delta * 1.1)), 1)
    return 0.0


def _build_watchlist_row(
    *,
    ticker: str,
    item: dict[str, Any],
    analysis: dict[str, Any],
    precio_actual: float,
    cambio_pct: float,
    target: float,
    distancia_alerta: str,
) -> dict[str, Any]:
    """Construye una fila enriquecida de watchlist con score payload."""

    score_action = analysis.get("score_decision_action") or analysis.get("decision_action") or "-"
    quality_adjusted = _as_bool(analysis.get("score_quality_adjusted", False))
    red_flags_count = _analysis_red_flags_count(analysis)
    confidence_label = analysis.get("score_confidence_label") or analysis.get("confidence_label") or "-"

    evolution = score_evolution_summary(ticker)
    trend_adjustment = _trend_priority_adjustment(evolution)

    record = {
        "Ticker": ticker,
        "Precio Actual": precio_actual,
        "Var Diaria (%)": cambio_pct,
        "Precio Objetivo": target if target > 0 else "-",
        "Distancia al Target": distancia_alerta,
        "Acción Research": analysis.get("action", "-"),
        "Acción Score": score_action,
        "Bucket Score": _score_decision_bucket(
            score_action=score_action,
            quality_adjusted=quality_adjusted,
            red_flags_count=red_flags_count,
            confidence_label=str(confidence_label),
            final_score=analysis.get("valuequant_score"),
        ),
        "ValueQuant": analysis.get("valuequant_score"),
        "Score bruto": analysis.get("score_raw_score"),
        "Buffett": analysis.get("buffett_score"),
        "Confianza": analysis.get("confidence"),
        "Nivel confianza": confidence_label,
        "Ajuste Calidad": quality_adjusted,
        "Quality Gate": analysis.get("score_quality_gate_reason") or "-",
        "Red Flags": red_flags_count,
        "Margen Seguridad": analysis.get("margin_of_safety"),
        "Régimen Valoración": analysis.get("valuation_regime", "-"),
        "Comparador": analysis.get("competitor", "-"),
        "Fuente": item.get("source", "Manual"),
        "Último análisis": item.get("last_saved_at", "-"),
        "Histórico Score": evolution.get("observations", 0),
        "Tendencia Score": evolution.get("trend_label", "Sin histórico"),
        "Detalle Tendencia": evolution.get("trend_detail", "-"),
        "Delta Score": evolution.get("delta_score"),
        "Ajuste Tendencia": trend_adjustment,
        "Último histórico": evolution.get("latest_saved_at"),
    }

    base_priority = _watchlist_priority_score(record)
    record["Prioridad Score"] = round(max(0.0, min(100.0, base_priority + trend_adjustment)), 1)
    return record


def _render_score_ranking_panel(df_watch: pd.DataFrame) -> None:
    """Panel de ranking operativo basado en score payload."""

    st.markdown("### Ranking operativo por score")
    st.caption(
        "Ordena la watchlist por score final, score bruto, confianza, quality gates, red flags y acción institucional del score."
    )

    if df_watch.empty:
        st.info("No hay datos suficientes para ranking.")
        return

    buckets = list(dict.fromkeys(str(item) for item in df_watch.get("Bucket Score", pd.Series(dtype=str)).dropna().tolist()))
    selected_buckets = st.multiselect(
        "Filtrar por bucket de score",
        options=buckets,
        default=buckets,
        key="watchlist_score_bucket_filter",
    )

    filtered = df_watch[df_watch["Bucket Score"].isin(selected_buckets)] if selected_buckets else df_watch
    if filtered.empty:
        st.info("No hay activos con el filtro seleccionado.")
        return

    display_cols = [
        "Prioridad Score",
        "Ticker",
        "Bucket Score",
        "Acción Score",
        "ValueQuant",
        "Score bruto",
        "Confianza",
        "Nivel confianza",
        "Ajuste Calidad",
        "Red Flags",
        "Margen Seguridad",
        "Tendencia Score",
        "Delta Score",
        "Ajuste Tendencia",
        "Histórico Score",
        "Quality Gate",
        "Último análisis",
    ]
    display_cols = [col for col in display_cols if col in filtered.columns]

    st.dataframe(
        filtered[display_cols].style.format(
            {
                "Prioridad Score": "{:.1f}",
                "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                "Score bruto": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                "Confianza": lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "-",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "-",
                "Delta Score": lambda x: f"{x:+.1f}" if isinstance(x, (int, float)) else "-",
                "Ajuste Tendencia": lambda x: f"{x:+.1f}" if isinstance(x, (int, float)) else "-",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_score_evolution_panel(df_watch: pd.DataFrame) -> None:
    """Panel visual de evolución temporal del score para la watchlist."""

    st.markdown("### Evolución temporal del score")
    st.caption(
        "Muestra si el score mejora, se deteriora o se mantiene estable usando los snapshots guardados en Research Core."
    )

    if df_watch.empty or "Ticker" not in df_watch.columns:
        st.info("No hay activos para mostrar evolución.")
        return

    tickers = [str(t).upper() for t in df_watch["Ticker"].dropna().unique().tolist()]
    if not tickers:
        st.info("No hay tickers válidos.")
        return

    selected = st.selectbox(
        "Ticker para evolución temporal",
        options=tickers,
        key="watchlist_score_evolution_ticker",
    )

    summary = score_evolution_summary(selected)
    history = score_history_for_ticker(selected)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Observaciones", summary.get("observations", 0))
    c2.metric(
        "Último VQ",
        _fmt_score(summary.get("latest_score")),
        f"{summary.get('delta_score'):+.1f}" if isinstance(summary.get("delta_score"), (int, float)) else None,
    )
    c3.metric(
        "Margen",
        _fmt_pct(summary.get("latest_margin")),
        f"{summary.get('delta_margin'):+.1%}" if isinstance(summary.get("delta_margin"), (int, float)) else None,
    )
    c4.metric("Tendencia", str(summary.get("trend_label", "Sin histórico")))

    st.info(summary.get("trend_detail", "No hay detalle de tendencia."))

    if history.empty or len(history) < 2:
        st.caption("Guarda al menos dos análisis del mismo ticker para ver gráfico temporal.")
        return

    chart_df = history.copy()
    chart_df["Fecha"] = pd.to_datetime(chart_df["Guardado"], errors="coerce")
    chart_cols: list[str] = []
    for col in ("VQ Score", "Score bruto", "Buffett"):
        if col in chart_df.columns:
            chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")
            if chart_df[col].notna().any():
                chart_cols.append(col)

    if "Confianza" in chart_df.columns:
        chart_df["Confianza (%)"] = pd.to_numeric(chart_df["Confianza"], errors="coerce") * 100
        if chart_df["Confianza (%)"].notna().any():
            chart_cols.append("Confianza (%)")

    chart_ready = chart_df.dropna(subset=["Fecha"]).set_index("Fecha")[chart_cols] if chart_cols else pd.DataFrame()
    if chart_ready.empty:
        st.caption("No hay columnas numéricas suficientes para graficar.")
    else:
        st.line_chart(chart_ready)

    display_cols = [
        "Guardado",
        "VQ Score",
        "Score bruto",
        "Buffett",
        "Margen Seguridad",
        "Confianza",
        "Nivel confianza",
        "Acción Score",
        "Ajuste Calidad",
        "Quality Gate",
        "Red Flags",
        "Régimen",
    ]
    display_cols = [col for col in display_cols if col in history.columns]

    st.dataframe(
        history[display_cols].style.format(
            {
                "VQ Score": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Score bruto": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Buffett": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "N/D",
                "Confianza": lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "N/D",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_alerts_panel(df_alerts: pd.DataFrame) -> None:
    """Panel visual de alertas priorizadas."""

    st.markdown("### 🚨 Alertas inteligentes")
    st.caption(
        "Prioriza la watchlist según precio vs target, margen de seguridad, ValueQuant Score, régimen de valoración y antigüedad del análisis."
    )

    if df_alerts.empty:
        st.info("No hay alertas disponibles todavía.")
        return

    summary = alert_summary(df_alerts)
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Alta", summary.get("Alta", 0))
    a2.metric("Media", summary.get("Media", 0))
    a3.metric("Baja", summary.get("Baja", 0))
    a4.metric("Info", summary.get("Info", 0))

    priority_filter = st.multiselect(
        "Filtrar por prioridad",
        options=["Alta", "Media", "Baja", "Info"],
        default=["Alta", "Media"],
        key="watchlist_alert_priority_filter",
    )

    filtered_alerts = df_alerts[df_alerts["Prioridad"].isin(priority_filter)] if priority_filter else df_alerts

    if filtered_alerts.empty:
        st.info("No hay alertas con el filtro seleccionado.")
        return

    st.dataframe(
        filtered_alerts[["Prioridad", "Ticker", "Categoría", "Alerta", "Detalle", "Acción sugerida", "Score"]],
        use_container_width=True,
        hide_index=True,
    )

    top_alert = filtered_alerts.iloc[0].to_dict()
    st.info(
        f"Prioridad principal: {top_alert.get('Ticker')} — {top_alert.get('Alerta')} | Acción sugerida: {top_alert.get('Acción sugerida')}"
    )


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

    with st.spinner("Sincronizando precios, snapshots y alertas inteligentes..."):
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

                record = _build_watchlist_row(
                    ticker=ticker,
                    item=item,
                    analysis=analysis,
                    precio_actual=precio_actual,
                    cambio_pct=cambio_pct,
                    target=target,
                    distancia_alerta=alerta,
                )
                resultados.append(record)

            except Exception:
                record = _build_watchlist_row(
                    ticker=ticker,
                    item=item,
                    analysis=analysis,
                    precio_actual=0.0,
                    cambio_pct=0.0,
                    target=_as_float(item.get("target"), 0.0),
                    distancia_alerta="⚠️ Error de datos",
                )
                resultados.append(record)

        df_watch = pd.DataFrame(resultados)
        if not df_watch.empty and "Prioridad Score" in df_watch.columns:
            df_watch = df_watch.sort_values(["Prioridad Score", "ValueQuant"], ascending=[False, False]).reset_index(drop=True)
        df_alerts = build_watchlist_alerts(df_watch)

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
        _render_score_ranking_panel(df_watch)

        st.markdown("---")
        _render_score_evolution_panel(df_watch)

        st.markdown("---")
        _render_alerts_panel(df_alerts)

        st.markdown("---")
        st.markdown("### Tabla de seguimiento")
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
            "Los tickers guardados desde Research Core incluyen acción operativa, score, margen de seguridad, target de seguimiento y alertas inteligentes."
        )
