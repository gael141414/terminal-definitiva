"""Briefing ejecutivo de oportunidades desde watchlist inteligente.

Convierte la watchlist y sus alertas en una vista accionable:
- Comprar / revisar hoy
- Vigilar caída
- Recalcular análisis
- Descartar por ahora

Es una capa local-first para MVP: lee `data/watchlist.json`, sincroniza precios
con yfinance y reutiliza `modulos.watchlist_alerts`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.watchlist_alerts import alert_summary, build_watchlist_alerts

DATA_FOLDER = Path("data")
WATCHLIST_FILE = DATA_FOLDER / "watchlist.json"

_BUCKET_ORDER = {
    "Comprar / revisar hoy": 0,
    "Vigilar caída": 1,
    "Recalcular análisis": 2,
    "Descartar por ahora": 3,
    "Mantener seguimiento": 4,
}

_PRIORITY_SCORE = {
    "Alta": 35,
    "Media": 20,
    "Baja": 8,
    "Info": 0,
}


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or pd.isna(value):
            return default
        if isinstance(value, str) and value.strip() in {"", "-", "N/D"}:
            return default
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number
    except Exception:
        return default


def _read_watchlist() -> dict[str, Any]:
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)
    if not WATCHLIST_FILE.exists():
        return {}
    try:
        with WATCHLIST_FILE.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalizar_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item
    return {"target": 0.0}


def _extraer_last_analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("last_analysis", {})
    return analysis if isinstance(analysis, dict) else {}


@st.cache_data(ttl=900, show_spinner=False)
def _price_snapshot(ticker: str) -> dict[str, float]:
    """Obtiene precio reciente con caché corta para no saturar yfinance."""

    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="5d")
        if not hist.empty and len(hist) >= 2:
            current = float(hist["Close"].iloc[-1])
            previous = float(hist["Close"].iloc[-2])
        else:
            current = float(tk.fast_info.last_price)
            previous = float(tk.fast_info.previous_close)
        change = ((current - previous) / previous) * 100 if previous else 0.0
        return {"price": current, "change_pct": change}
    except Exception:
        return {"price": 0.0, "change_pct": 0.0}


def build_watchlist_dataframe() -> pd.DataFrame:
    """Construye una tabla normalizada de watchlist con precio actual."""

    db = _read_watchlist()
    rows: list[dict[str, Any]] = []

    for ticker, raw_item in db.items():
        ticker = str(ticker).upper().strip()
        if not ticker:
            continue

        item = _normalizar_item(raw_item)
        analysis = _extraer_last_analysis(item)
        price_data = _price_snapshot(ticker)
        current_price = _as_float(price_data.get("price"), 0.0) or 0.0
        target = _as_float(item.get("target"), 0.0) or 0.0

        if target > 0 and current_price > 0:
            distance = (current_price - target) / target
            distance_label = "✅ En target" if current_price <= target else f"{distance:+.1%} vs target"
        elif target > 0:
            distance = None
            distance_label = "⚠️ Precio no disponible"
        else:
            distance = None
            distance_label = "Sin target"

        rows.append(
            {
                "Ticker": ticker,
                "Precio Actual": current_price,
                "Var Diaria (%)": _as_float(price_data.get("change_pct"), 0.0) or 0.0,
                "Precio Objetivo": target if target > 0 else "-",
                "Distancia Num": distance,
                "Distancia al Target": distance_label,
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

    return pd.DataFrame(rows)


def _alerts_for_ticker(df_alerts: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df_alerts is None or df_alerts.empty:
        return pd.DataFrame()
    return df_alerts[df_alerts["Ticker"].astype(str).str.upper() == ticker.upper()]


def _has_alert(alerts: pd.DataFrame, *, priority: str | None = None, contains: str | None = None) -> bool:
    if alerts.empty:
        return False
    df = alerts
    if priority:
        df = df[df["Prioridad"] == priority]
    if contains:
        mask = (
            df["Alerta"].astype(str).str.contains(contains, case=False, na=False)
            | df["Detalle"].astype(str).str.contains(contains, case=False, na=False)
            | df["Acción sugerida"].astype(str).str.contains(contains, case=False, na=False)
        )
        df = df[mask]
    return not df.empty


def _classify_opportunity(row: dict[str, Any], alerts: pd.DataFrame) -> tuple[str, str]:
    ticker = str(row.get("Ticker", "")).upper()
    current_price = _as_float(row.get("Precio Actual"), 0.0) or 0.0
    target = _as_float(row.get("Precio Objetivo"), None)
    vq = _as_float(row.get("ValueQuant"), None)
    margin = _as_float(row.get("Margen Seguridad"), None)
    action = str(row.get("Acción Research", "") or "").lower()
    regime = str(row.get("Régimen Valoración", "") or "").lower()

    if current_price <= 0:
        return "Recalcular análisis", "No hay precio actual fiable; revisar datos antes de decidir."

    if "evitar" in action or (vq is not None and vq < 45):
        return "Descartar por ahora", "La tesis guardada o el score no justifican priorizar esta oportunidad."

    if _has_alert(alerts, priority="Alta", contains="Precio en zona objetivo"):
        return "Comprar / revisar hoy", f"{ticker} está en zona objetivo o por debajo del target operativo."

    if _has_alert(alerts, priority="Alta", contains="Score sólido") or (
        vq is not None and vq >= 65 and margin is not None and margin >= 0
    ):
        return "Comprar / revisar hoy", "Score y margen de seguridad justifican revisar la entrada con prioridad."

    if target is not None and target > 0 and current_price > 0:
        distance = (current_price - target) / target
        if 0 < distance <= 0.10:
            return "Vigilar caída", f"Está a {distance:.1%} de entrar en zona objetivo."
        if vq is not None and vq >= 70 and distance > 0.10:
            return "Vigilar caída", "Alta calidad, pero todavía necesita mejor precio."

    if margin is not None and margin < -0.10 and (
        vq is not None and vq >= 65 or any(term in regime for term in ("cara", "exigente", "sobrevalor"))
    ):
        return "Vigilar caída", "La calidad puede ser buena, pero la valoración sigue exigente."

    if _has_alert(alerts, contains="desactualizado") or _has_alert(alerts, contains="Recalcular"):
        return "Recalcular análisis", "El análisis guardado está anticuado o incompleto."

    return "Mantener seguimiento", "No hay señal prioritaria hoy; mantener en radar."


def _opportunity_score(row: dict[str, Any], alerts: pd.DataFrame) -> int:
    alert_score = int(alerts["Score"].max()) if not alerts.empty and "Score" in alerts else 0
    priority_bonus = 0
    if not alerts.empty and "Prioridad" in alerts:
        priority_bonus = max(_PRIORITY_SCORE.get(str(p), 0) for p in alerts["Prioridad"].unique())

    vq = _as_float(row.get("ValueQuant"), None)
    margin = _as_float(row.get("Margen Seguridad"), None)
    distance = _as_float(row.get("Distancia Num"), None)

    score = alert_score + priority_bonus
    if vq is not None:
        score += max(-15, min(25, int((vq - 50) * 0.5)))
    if margin is not None:
        score += max(-25, min(25, int(margin * 100)))
    if distance is not None:
        if distance <= 0:
            score += 18
        elif distance <= 0.05:
            score += 12
        elif distance <= 0.10:
            score += 6
        elif distance > 0.25:
            score -= 10

    return int(max(0, min(100, score)))


def build_opportunity_briefing() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve watchlist, alertas y briefing priorizado."""

    df_watch = build_watchlist_dataframe()
    if df_watch.empty:
        return df_watch, pd.DataFrame(), pd.DataFrame()

    df_alerts = build_watchlist_alerts(df_watch)
    records: list[dict[str, Any]] = []

    for _, row in df_watch.iterrows():
        row_dict = row.to_dict()
        ticker = str(row_dict.get("Ticker", "")).upper()
        ticker_alerts = _alerts_for_ticker(df_alerts, ticker)
        bucket, reason = _classify_opportunity(row_dict, ticker_alerts)
        score = _opportunity_score(row_dict, ticker_alerts)
        top_alert = ticker_alerts.iloc[0].to_dict() if not ticker_alerts.empty else {}

        records.append(
            {
                "Prioridad": bucket,
                "Ticker": ticker,
                "Score Oportunidad": score,
                "Razón": reason,
                "Acción sugerida": top_alert.get("Acción sugerida", "Mantener seguimiento"),
                "Alerta principal": top_alert.get("Alerta", "Sin alerta relevante"),
                "Precio Actual": row_dict.get("Precio Actual"),
                "Target": row_dict.get("Precio Objetivo"),
                "Distancia": row_dict.get("Distancia al Target"),
                "ValueQuant": row_dict.get("ValueQuant"),
                "Margen Seguridad": row_dict.get("Margen Seguridad"),
                "Acción Research": row_dict.get("Acción Research"),
                "Régimen": row_dict.get("Régimen Valoración"),
                "Último análisis": row_dict.get("Último análisis"),
                "_bucket_order": _BUCKET_ORDER.get(bucket, 999),
            }
        )

    df_briefing = pd.DataFrame(records)
    if not df_briefing.empty:
        df_briefing = df_briefing.sort_values(
            ["_bucket_order", "Score Oportunidad"], ascending=[True, False]
        ).drop(columns=["_bucket_order"])

    return df_watch, df_alerts, df_briefing.reset_index(drop=True)


def _render_bucket(df: pd.DataFrame, bucket: str, empty_message: str) -> None:
    subset = df[df["Prioridad"] == bucket]
    if subset.empty:
        st.info(empty_message)
        return
    st.dataframe(
        subset[
            [
                "Ticker",
                "Score Oportunidad",
                "Razón",
                "Acción sugerida",
                "Precio Actual",
                "Target",
                "Distancia",
                "ValueQuant",
                "Margen Seguridad",
                "Régimen",
            ]
        ].style.format(
            {
                "Precio Actual": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "-",
                "Target": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "-",
                "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "-",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_opportunity_briefing() -> None:
    """Panel Streamlit de briefing ejecutivo de oportunidades."""

    st.markdown("### 📌 Briefing de Oportunidades")
    st.caption(
        "Convierte la watchlist inteligente en una cola de decisión: revisar hoy, vigilar caída, recalcular o descartar temporalmente."
    )

    with st.spinner("Construyendo briefing desde watchlist, precios y alertas inteligentes..."):
        df_watch, df_alerts, df_briefing = build_opportunity_briefing()

    if df_watch.empty:
        st.info(
            "No hay activos en watchlist. Guarda un análisis desde 🧩 Research Core → 💾 Seguimiento o añade tickers en 📋 Mi Watchlist."
        )
        return

    summary_alerts = alert_summary(df_alerts)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Activos", len(df_watch))
    c2.metric("Revisar hoy", int((df_briefing["Prioridad"] == "Comprar / revisar hoy").sum()))
    c3.metric("Vigilar caída", int((df_briefing["Prioridad"] == "Vigilar caída").sum()))
    c4.metric("Recalcular", int((df_briefing["Prioridad"] == "Recalcular análisis").sum()))
    c5.metric("Alertas altas", summary_alerts.get("Alta", 0))

    st.markdown("---")
    if not df_briefing.empty:
        top = df_briefing.iloc[0].to_dict()
        st.info(
            f"Prioridad principal: **{top.get('Ticker')}** — {top.get('Prioridad')} | "
            f"Score oportunidad: **{top.get('Score Oportunidad')}** | {top.get('Razón')}"
        )

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Resumen",
            "Comprar / revisar hoy",
            "Vigilar caída",
            "Recalcular",
            "Descartar",
            "Todas las alertas",
        ]
    )

    with tab1:
        st.markdown("#### Cola de decisión completa")
        st.dataframe(
            df_briefing[
                [
                    "Prioridad",
                    "Ticker",
                    "Score Oportunidad",
                    "Razón",
                    "Alerta principal",
                    "Precio Actual",
                    "Target",
                    "Distancia",
                    "ValueQuant",
                    "Margen Seguridad",
                    "Último análisis",
                ]
            ].style.format(
                {
                    "Precio Actual": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "-",
                    "Target": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "-",
                    "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "-",
                    "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "-",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        _render_bucket(
            df_briefing,
            "Comprar / revisar hoy",
            "No hay compras/revisiones prioritarias con los datos actuales.",
        )

    with tab3:
        _render_bucket(
            df_briefing,
            "Vigilar caída",
            "No hay activos de calidad cerca de zona objetivo pendientes de caída.",
        )

    with tab4:
        _render_bucket(
            df_briefing,
            "Recalcular análisis",
            "No hay análisis que requieran recalculo prioritario.",
        )

    with tab5:
        _render_bucket(
            df_briefing,
            "Descartar por ahora",
            "No hay activos marcados para descartar temporalmente.",
        )

    with tab6:
        if df_alerts.empty:
            st.info("No hay alertas generadas.")
        else:
            st.dataframe(df_alerts, use_container_width=True, hide_index=True)

    st.caption(
        "Este briefing no ejecuta órdenes ni sustituye criterio inversor. Sirve para priorizar revisión basada en datos guardados y precios actuales."
    )
