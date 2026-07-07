"""Backtesting básico de señales guardadas desde Research Core.

Este módulo evalúa señales derivadas de snapshots históricos:
- BUY: señal accionable / entrada
- WATCH: seguimiento sin entrada directa
- AVOID: señal de descarte o riesgo

No sustituye un backtesting cuantitativo profesional. Es una capa MVP para medir
si las señales del score y la tesis tuvieron buen comportamiento posterior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.analysis_store import load_saved_analyses


@dataclass(frozen=True)
class SignalBacktestSummary:
    """Resumen agregado del backtesting de señales."""

    total_signals: int
    buy_signals: int
    watch_signals: int
    avoid_signals: int
    avg_forward_return_buy: float | None
    hit_rate_buy: float | None
    avg_forward_return_all: float | None


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sí", "si", "yes", "y"}
    return bool(value)


def _payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw = snapshot.get("score_payload", {})
    return raw if isinstance(raw, dict) else {}


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _snapshot_value(snapshot: dict[str, Any], key: str, payload_key: str | None = None) -> Any:
    payload = _payload(snapshot)
    return _first_not_none(snapshot.get(key), payload.get(payload_key or key))


def _parse_timestamp(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.tz_convert(None)
        return pd.Timestamp(ts)
    except Exception:
        return None


def _red_flags_count(snapshot: dict[str, Any]) -> int:
    explicit = snapshot.get("score_red_flags_count")
    try:
        if explicit is not None:
            return max(0, int(explicit))
    except Exception:
        pass

    payload_flags = _payload(snapshot).get("red_flags")
    if isinstance(payload_flags, list):
        return len(payload_flags)

    thesis_flags = snapshot.get("red_flags")
    if isinstance(thesis_flags, list):
        return len(thesis_flags)

    return 0


def classify_snapshot_signal(snapshot: dict[str, Any]) -> str:
    """Clasifica un snapshot histórico como BUY, WATCH o AVOID."""

    final_score = _as_float(_snapshot_value(snapshot, "valuequant_score", "final_score"), 0.0) or 0.0
    margin = _as_float(snapshot.get("margin_of_safety"), 0.0) or 0.0
    confidence_label = str(_snapshot_value(snapshot, "score_confidence_label", "confidence_label") or "").lower()
    score_action = str(_snapshot_value(snapshot, "score_decision_action", "decision_action") or "").lower()
    research_action = str(snapshot.get("action") or "").lower()
    quality_adjusted = _as_bool(_snapshot_value(snapshot, "score_quality_adjusted", "quality_adjusted"))
    red_flags = _red_flags_count(snapshot)

    combined_action = f"{score_action} {research_action}"

    if red_flags > 0:
        return "AVOID"
    if quality_adjusted:
        return "AVOID"
    if "riesgo" in combined_action or "revisión manual" in combined_action or "baja prioridad" in combined_action:
        return "AVOID"
    if "esperar" in combined_action and (
        final_score < 50 or margin < -0.10 or confidence_label == "baja"
    ):
        return "AVOID"
    if final_score < 50:
        return "AVOID"

    if "prioritario" in combined_action and final_score >= 60 and margin >= -0.05:
        return "BUY"
    if final_score >= 65 and margin >= 0 and confidence_label != "baja":
        return "BUY"
    if "atractiva con matices" in combined_action and final_score >= 62 and margin >= 0:
        return "BUY"

    return "WATCH"


def build_signal_events(
    analyses: dict[str, list[dict[str, Any]]] | None = None,
    *,
    tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Convierte snapshots guardados en eventos de señal."""

    analyses = analyses if analyses is not None else load_saved_analyses()
    tickers_filter = {str(t).upper().strip() for t in tickers or [] if str(t).strip()}
    rows: list[dict[str, Any]] = []

    for ticker, history in analyses.items():
        ticker = str(ticker or "").upper().strip()
        if not ticker:
            continue
        if tickers_filter and ticker not in tickers_filter:
            continue
        if not isinstance(history, list):
            continue

        for snapshot in history:
            if not isinstance(snapshot, dict):
                continue

            saved_at = snapshot.get("saved_at")
            event_ts = _parse_timestamp(saved_at)
            if event_ts is None:
                continue

            signal = classify_snapshot_signal(snapshot)
            rows.append(
                {
                    "Ticker": ticker,
                    "Fecha Señal": event_ts,
                    "Guardado": saved_at,
                    "Señal": signal,
                    "ValueQuant": _as_float(_snapshot_value(snapshot, "valuequant_score", "final_score")),
                    "Score bruto": _as_float(_snapshot_value(snapshot, "score_raw_score", "raw_score")),
                    "Acción Score": _snapshot_value(snapshot, "score_decision_action", "decision_action") or "-",
                    "Acción Research": snapshot.get("action", "-"),
                    "Margen Seguridad": _as_float(snapshot.get("margin_of_safety")),
                    "Confianza": _as_float(_snapshot_value(snapshot, "confidence", "confidence")),
                    "Quality Gate": _snapshot_value(snapshot, "score_quality_gate_reason", "quality_gate_reason") or "-",
                    "Red Flags": _red_flags_count(snapshot),
                }
            )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["Ticker", "Fecha Señal"]).reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _download_close(ticker: str, period: str = "5y") -> pd.Series:
    """Descarga precios ajustados para backtesting ligero."""

    try:
        data = yf.download(ticker, period=period, auto_adjust=True, progress=False, threads=False)
        if data.empty:
            return pd.Series(dtype=float)
        close = data["Close"] if "Close" in data else data.squeeze()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        return _normalise_close_index(pd.to_numeric(close, errors="coerce").dropna())
    except Exception:
        return pd.Series(dtype=float)


def _normalise_close_index(close: pd.Series) -> pd.Series:
    close = close.dropna().copy()
    if close.empty:
        return close

    idx = pd.to_datetime(close.index, errors="coerce")
    close = close.loc[~pd.isna(idx)].copy()
    idx = pd.to_datetime(close.index, errors="coerce")

    try:
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
    except Exception:
        pass

    close.index = pd.DatetimeIndex(idx)
    close = close.sort_index()
    return close


def _entry_exit_prices(
    close: pd.Series,
    event_date: Any,
    *,
    horizon_days: int,
) -> tuple[pd.Timestamp, float, pd.Timestamp, float] | None:
    close = _normalise_close_index(close)
    if close.empty:
        return None

    event_ts = _parse_timestamp(event_date)
    if event_ts is None:
        return None

    entry_candidates = close[close.index >= event_ts.normalize()]
    if entry_candidates.empty:
        return None

    entry_date = pd.Timestamp(entry_candidates.index[0])
    entry_price = _as_float(entry_candidates.iloc[0])
    if entry_price is None or entry_price <= 0:
        return None

    target_exit_date = entry_date + pd.Timedelta(days=int(horizon_days))
    exit_candidates = close[close.index >= target_exit_date]
    if exit_candidates.empty:
        exit_candidates = close[close.index > entry_date]
    if exit_candidates.empty:
        return None

    exit_date = pd.Timestamp(exit_candidates.index[0])
    exit_price = _as_float(exit_candidates.iloc[0])
    if exit_price is None or exit_price <= 0:
        return None

    return entry_date, entry_price, exit_date, exit_price


def _signal_hit(signal: str, forward_return: float) -> bool | None:
    signal = str(signal or "").upper()
    if signal == "BUY":
        return forward_return > 0
    if signal == "AVOID":
        return forward_return <= 0
    return None


def evaluate_signal_events(
    events: pd.DataFrame,
    *,
    horizon_days: int = 90,
    price_lookup: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Evalúa retorno futuro de cada evento de señal."""

    if events is None or events.empty:
        return pd.DataFrame()

    price_lookup = price_lookup or {}
    rows: list[dict[str, Any]] = []

    for _, event in events.iterrows():
        ticker = str(event.get("Ticker", "")).upper().strip()
        if not ticker:
            continue

        close = price_lookup.get(ticker)
        if close is None:
            close = _download_close(ticker)
        if close is None or close.empty:
            continue

        prices = _entry_exit_prices(close, event.get("Fecha Señal"), horizon_days=horizon_days)
        if prices is None:
            continue

        entry_date, entry_price, exit_date, exit_price = prices
        forward_return = (exit_price / entry_price) - 1.0
        signal = str(event.get("Señal", "WATCH")).upper()
        hit = _signal_hit(signal, forward_return)

        row = dict(event)
        row.update(
            {
                "Horizonte días": int(horizon_days),
                "Fecha Entrada": entry_date,
                "Precio Entrada": entry_price,
                "Fecha Salida": exit_date,
                "Precio Salida": exit_price,
                "Retorno Futuro": round(float(forward_return), 6),
                "Hit": hit,
            }
        )
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(["Ticker", "Fecha Entrada"]).reset_index(drop=True)


def summarize_signal_backtest(results: pd.DataFrame) -> dict[str, Any]:
    """Resumen agregado del backtest de señales."""

    if results is None or results.empty:
        empty = SignalBacktestSummary(
            total_signals=0,
            buy_signals=0,
            watch_signals=0,
            avoid_signals=0,
            avg_forward_return_buy=None,
            hit_rate_buy=None,
            avg_forward_return_all=None,
        )
        return {"summary": empty, "by_signal": pd.DataFrame()}

    df = results.copy()
    df["Retorno Futuro"] = pd.to_numeric(df["Retorno Futuro"], errors="coerce")
    df["Señal"] = df["Señal"].astype(str).str.upper()

    buy = df[df["Señal"] == "BUY"]
    watch = df[df["Señal"] == "WATCH"]
    avoid = df[df["Señal"] == "AVOID"]

    hit_rate_buy = None
    if not buy.empty and "Hit" in buy:
        hit_rate_buy = float(buy["Hit"].dropna().mean()) if not buy["Hit"].dropna().empty else None

    by_signal = (
        df.groupby("Señal", dropna=False)
        .agg(
            Señales=("Señal", "size"),
            Retorno_Medio=("Retorno Futuro", "mean"),
            Retorno_Mediano=("Retorno Futuro", "median"),
            Hit_Rate=("Hit", "mean"),
        )
        .reset_index()
    )

    summary = SignalBacktestSummary(
        total_signals=int(len(df)),
        buy_signals=int(len(buy)),
        watch_signals=int(len(watch)),
        avoid_signals=int(len(avoid)),
        avg_forward_return_buy=float(buy["Retorno Futuro"].mean()) if not buy.empty else None,
        hit_rate_buy=hit_rate_buy,
        avg_forward_return_all=float(df["Retorno Futuro"].mean()) if not df.empty else None,
    )

    return {"summary": summary, "by_signal": by_signal}


def run_basic_signal_backtest(
    *,
    tickers: list[str] | None = None,
    horizon_days: int = 90,
    price_lookup: dict[str, pd.Series] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Pipeline completo: snapshots -> eventos -> evaluación -> resumen."""

    events = build_signal_events(tickers=tickers)
    results = evaluate_signal_events(events, horizon_days=horizon_days, price_lookup=price_lookup)
    summary = summarize_signal_backtest(results)
    return events, results, summary


def _fmt_pct(value: Any) -> str:
    number = _as_float(value)
    return f"{number:+.1%}" if number is not None else "N/D"


def render_signal_backtest_panel(default_ticker: str | None = None) -> None:
    """Panel Streamlit para backtesting básico de señales."""

    st.markdown("### Backtesting básico de señales")
    st.caption(
        "Evalúa cómo se comportaron después las señales BUY / WATCH / AVOID derivadas de snapshots guardados."
    )

    analyses = load_saved_analyses()
    available_tickers = sorted(str(t).upper() for t, h in analyses.items() if isinstance(h, list) and h)
    if not available_tickers:
        st.info("No hay snapshots guardados suficientes para ejecutar backtesting de señales.")
        return

    default_selection = [default_ticker.upper()] if default_ticker and default_ticker.upper() in available_tickers else available_tickers[:5]
    selected = st.multiselect(
        "Tickers a evaluar",
        options=available_tickers,
        default=default_selection,
        key="signal_backtest_tickers",
    )
    horizon = st.selectbox(
        "Horizonte de evaluación",
        options=[30, 60, 90, 180, 365],
        index=2,
        key="signal_backtest_horizon",
    )

    if not selected:
        st.info("Selecciona al menos un ticker.")
        return

    with st.spinner("Ejecutando backtesting básico de señales..."):
        events, results, summary_payload = run_basic_signal_backtest(tickers=selected, horizon_days=int(horizon))

    st.markdown("#### Eventos detectados")
    if events.empty:
        st.info("No hay eventos de señal válidos para los filtros seleccionados.")
        return

    st.dataframe(
        events[
            [
                "Ticker",
                "Fecha Señal",
                "Señal",
                "ValueQuant",
                "Acción Score",
                "Margen Seguridad",
                "Confianza",
                "Red Flags",
            ]
        ].style.format(
            {
                "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "N/D",
                "Confianza": lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "N/D",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    if results.empty:
        st.warning("No se pudieron cruzar los eventos con precios históricos suficientes.")
        return

    summary: SignalBacktestSummary = summary_payload["summary"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Señales evaluadas", summary.total_signals)
    c2.metric("BUY", summary.buy_signals)
    c3.metric("Retorno medio BUY", _fmt_pct(summary.avg_forward_return_buy))
    c4.metric("Hit rate BUY", _fmt_pct(summary.hit_rate_buy))

    by_signal = summary_payload.get("by_signal", pd.DataFrame())
    if isinstance(by_signal, pd.DataFrame) and not by_signal.empty:
        st.markdown("#### Resumen por señal")
        st.dataframe(
            by_signal.style.format(
                {
                    "Retorno_Medio": "{:+.1%}",
                    "Retorno_Mediano": "{:+.1%}",
                    "Hit_Rate": "{:.0%}",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    chart_df = results.copy()
    chart_df["Fecha Entrada"] = pd.to_datetime(chart_df["Fecha Entrada"], errors="coerce")
    chart_df["Retorno Futuro"] = pd.to_numeric(chart_df["Retorno Futuro"], errors="coerce")
    chart_ready = chart_df.dropna(subset=["Fecha Entrada", "Retorno Futuro"])
    if not chart_ready.empty:
        st.markdown("#### Retorno futuro por evento")
        st.bar_chart(chart_ready.set_index("Fecha Entrada")["Retorno Futuro"])

    st.markdown("#### Detalle de resultados")
    display_cols = [
        "Ticker",
        "Fecha Entrada",
        "Señal",
        "ValueQuant",
        "Precio Entrada",
        "Fecha Salida",
        "Precio Salida",
        "Retorno Futuro",
        "Hit",
    ]
    display_cols = [col for col in display_cols if col in results.columns]

    st.dataframe(
        results[display_cols].style.format(
            {
                "ValueQuant": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Precio Entrada": "${:.2f}",
                "Precio Salida": "${:.2f}",
                "Retorno Futuro": "{:+.1%}",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Interpretación: BUY acierta si el retorno futuro es positivo; AVOID acierta si el retorno futuro es negativo o plano. WATCH no se contabiliza como acierto/fallo directo."
    )
