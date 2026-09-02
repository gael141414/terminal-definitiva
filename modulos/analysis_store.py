"""Persistencia local de análisis Research Core y watchlist inteligente.

El módulo guarda snapshots ligeros de análisis en JSON local. No sustituye una base
de datos real; es una capa persistente suficiente para MVP/local-first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

import pandas as pd
import streamlit as st

from modulos.investment_thesis import build_investment_thesis

DATA_FOLDER = Path("data")
WATCHLIST_FILE = DATA_FOLDER / "watchlist.json"
SAVED_ANALYSES_FILE = DATA_FOLDER / "research_analyses.json"
MAX_ANALYSES_PER_TICKER = 25


# -----------------------------------------------------------------------------
# IO JSON
# -----------------------------------------------------------------------------

def _ensure_data_folder() -> None:
    DATA_FOLDER.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    _ensure_data_folder()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    _ensure_data_folder()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return None


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _score_summary_payload(valuequant_score: Any, ticker: str) -> dict[str, Any]:
    """Obtiene el payload estructurado del score con fallback defensivo."""

    if valuequant_score is None:
        return {}

    builder = getattr(valuequant_score, "to_summary_payload", None)
    if callable(builder):
        try:
            payload = builder(ticker)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    return {
        "ticker": ticker,
        "model_version": _score_attr(valuequant_score, "model_version"),
        "final_score": _as_float(_score_attr(valuequant_score, "final_score")),
        "raw_score": _as_float(_score_attr(valuequant_score, "raw_score")),
        "verdict": _score_attr(valuequant_score, "verdict"),
        "confidence": _as_float(_score_attr(valuequant_score, "confidence")),
        "data_coverage": _as_float(_score_attr(valuequant_score, "data_coverage")),
        "confidence_label": _score_attr(valuequant_score, "confidence_label"),
        "predictive_confidence": _as_float(_score_attr(valuequant_score, "predictive_confidence")),
        "quality_adjusted": bool(_score_attr(valuequant_score, "quality_adjusted", False)),
        "quality_gate_reason": _score_attr(valuequant_score, "quality_gate_reason"),
        "decision_action": _score_attr(valuequant_score, "decision_action"),
        "decision_notes": list(_score_attr(valuequant_score, "decision_notes", []) or []),
        "top_components": [],
        "weakest_components": [],
        "red_flags": list(_score_attr(valuequant_score, "red_flags", []) or []),
        "positives": list(_score_attr(valuequant_score, "positives", []) or []),
        "negatives": list(_score_attr(valuequant_score, "negatives", []) or []),
    }


def _component_score(valuequant_score: Any, keyword: str) -> float | None:
    components = _score_attr(valuequant_score, "components", []) or []
    target = keyword.lower()
    for component in components:
        name = str(getattr(component, "name", "")).lower()
        if target in name:
            return _as_float(getattr(component, "score", None))
    return None


def _fmt_score(value: Any) -> str:
    number = _as_float(value)
    return f"{number:.1f}/100" if number is not None else "N/D"


def _fmt_money(value: Any) -> str:
    number = _as_float(value)
    return f"${number:,.2f}" if number is not None else "N/D"


def _fmt_pct(value: Any) -> str:
    number = _as_float(value)
    return f"{number * 100:+.1f}%" if number is not None else "N/D"


def _target_from_snapshot(snapshot: dict[str, Any]) -> float:
    """Precio objetivo operativo para watchlist.

    Prioridad:
    1. entrada razonable
    2. entrada conservadora
    3. valor intrínseco
    4. 0 si no hay valoración
    """

    for key in ("reasonable_entry_price", "conservative_entry_price", "intrinsic_value"):
        value = _as_float(snapshot.get(key))
        if value is not None and value > 0:
            return value
    return 0.0


# -----------------------------------------------------------------------------
# API pública
# -----------------------------------------------------------------------------

def build_research_snapshot(
    *,
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    source: str = "Research Core",
) -> dict[str, Any]:
    """Construye un snapshot persistible desde el análisis actual."""

    ticker = str(ticker or "").upper().strip()
    competitor = str(competitor or "").upper().strip()
    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)
    score_payload = _score_summary_payload(valuequant_score, ticker)

    snapshot = {
        "ticker": ticker,
        "competitor": competitor,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "action": thesis.action,
        "action_detail": thesis.action_detail,
        "score_payload": score_payload,
        "score_decision_action": score_payload.get("decision_action") or getattr(thesis, "score_decision_action", None),
        "score_decision_notes": list(score_payload.get("decision_notes") or [])[:5],
        "score_raw_score": _as_float(score_payload.get("raw_score")),
        "score_quality_adjusted": bool(score_payload.get("quality_adjusted", False)),
        "score_quality_gate_reason": score_payload.get("quality_gate_reason"),
        "score_confidence_label": score_payload.get("confidence_label"),
        "score_top_components": list(score_payload.get("top_components") or [])[:3],
        "score_weakest_components": list(score_payload.get("weakest_components") or [])[:3],
        "score_red_flags_count": len(score_payload.get("red_flags") or []),
        "valuequant_score": _as_float(score_payload.get("final_score")) if score_payload else _as_float(thesis.final_score),
        "buffett_score": _as_float(thesis.buffett_score),
        "quality_score": _as_float(thesis.quality_score),
        "valuation_score": _as_float(thesis.valuation_score),
        "risk_score": _as_float(thesis.risk_score),
        "growth_score": _as_float(thesis.growth_score),
        "data_coverage": _as_float(score_payload.get("data_coverage")) if score_payload else _as_float(_score_attr(valuequant_score, "data_coverage")),
        "confidence": _as_float(score_payload.get("confidence")) if score_payload else _as_float(_score_attr(valuequant_score, "confidence")),
        "predictive_confidence": _as_float(score_payload.get("predictive_confidence")) if score_payload else _as_float(_score_attr(valuequant_score, "predictive_confidence")),
        "model_version": score_payload.get("model_version") or _score_attr(valuequant_score, "model_version", "N/D"),
        "current_price": _as_float(thesis.current_price),
        "intrinsic_value": _as_float(thesis.intrinsic_value),
        "margin_of_safety": _as_float(thesis.margin_of_safety),
        "reasonable_entry_price": _as_float(thesis.reasonable_entry_price),
        "conservative_entry_price": _as_float(thesis.conservative_entry_price),
        "deep_value_entry_price": _as_float(thesis.deep_value_entry_price),
        "fcf_yield": _as_float(thesis.fcf_yield),
        "earnings_yield": _as_float(thesis.earnings_yield),
        "pe_actual": _as_float(thesis.pe_actual),
        "pfcf_actual": _as_float(thesis.pfcf_actual),
        "valuation_regime": thesis.valuation_regime,
        "valuation_comment": thesis.valuation_comment,
        "red_flags": list(thesis.red_flags or []),
        "positives": list(thesis.positives or []),
        "negatives": list(thesis.negatives or []),
    }
    snapshot["target"] = _target_from_snapshot(snapshot)
    return snapshot


def load_saved_analyses() -> dict[str, list[dict[str, Any]]]:
    """Carga histórico de análisis guardados."""

    data = _read_json(SAVED_ANALYSES_FILE, {})
    return data if isinstance(data, dict) else {}


def save_analysis_snapshot(snapshot: dict[str, Any]) -> None:
    """Guarda snapshot y actualiza watchlist enriquecida."""

    ticker = str(snapshot.get("ticker", "")).upper().strip()
    if not ticker:
        raise ValueError("No se puede guardar un análisis sin ticker.")

    analyses = load_saved_analyses()
    ticker_history = analyses.get(ticker, [])
    if not isinstance(ticker_history, list):
        ticker_history = []
    ticker_history.insert(0, snapshot)
    analyses[ticker] = ticker_history[:MAX_ANALYSES_PER_TICKER]
    _write_json(SAVED_ANALYSES_FILE, analyses)

    watchlist = _read_json(WATCHLIST_FILE, {})
    if not isinstance(watchlist, dict):
        watchlist = {}

    existing = watchlist.get(ticker, {})
    if not isinstance(existing, dict):
        existing = {}

    target = _target_from_snapshot(snapshot)
    existing.update(
        {
            "target": target or _as_float(existing.get("target")) or 0.0,
            "source": "Research Core",
            "last_saved_at": snapshot.get("saved_at"),
            "last_analysis": {
                "action": snapshot.get("action"),
                "score_decision_action": snapshot.get("score_decision_action"),
                "score_decision_notes": snapshot.get("score_decision_notes"),
                "score_raw_score": snapshot.get("score_raw_score"),
                "score_quality_adjusted": snapshot.get("score_quality_adjusted"),
                "score_quality_gate_reason": snapshot.get("score_quality_gate_reason"),
                "score_confidence_label": snapshot.get("score_confidence_label"),
                "score_top_components": snapshot.get("score_top_components"),
                "score_weakest_components": snapshot.get("score_weakest_components"),
                "score_red_flags_count": snapshot.get("score_red_flags_count"),
                "valuequant_score": snapshot.get("valuequant_score"),
                "buffett_score": snapshot.get("buffett_score"),
                "data_coverage": snapshot.get("data_coverage"),
                "confidence": snapshot.get("confidence"),
                "margin_of_safety": snapshot.get("margin_of_safety"),
                "valuation_regime": snapshot.get("valuation_regime"),
                "competitor": snapshot.get("competitor"),
                "model_version": snapshot.get("model_version"),
            },
        }
    )
    watchlist[ticker] = existing
    _write_json(WATCHLIST_FILE, watchlist)


def latest_snapshots() -> list[dict[str, Any]]:
    """Devuelve el último análisis guardado por ticker."""

    analyses = load_saved_analyses()
    latest: list[dict[str, Any]] = []
    for ticker, history in analyses.items():
        if isinstance(history, list) and history:
            item = dict(history[0])
            item.setdefault("ticker", ticker)
            latest.append(item)
    latest.sort(key=lambda row: str(row.get("saved_at", "")), reverse=True)
    return latest


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _parse_saved_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _score_payload_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = snapshot.get("score_payload", {})
    return payload if isinstance(payload, dict) else {}


def _snapshot_red_flags_count(snapshot: dict[str, Any]) -> int:
    explicit = snapshot.get("score_red_flags_count")
    try:
        if explicit is not None:
            return max(0, int(explicit))
    except Exception:
        pass

    payload = _score_payload_from_snapshot(snapshot)
    payload_flags = payload.get("red_flags")
    if isinstance(payload_flags, list):
        return len(payload_flags)

    thesis_flags = snapshot.get("red_flags")
    if isinstance(thesis_flags, list):
        return len(thesis_flags)

    return 0


def score_history_for_ticker(ticker: str, *, limit: int | None = None) -> pd.DataFrame:
    """Devuelve histórico normalizado de score para un ticker.

    La salida está ordenada cronológicamente de antiguo a reciente para facilitar
    gráficos de evolución temporal.
    """

    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return pd.DataFrame()

    history = load_saved_analyses().get(ticker, [])
    if not isinstance(history, list):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for snapshot in history:
        if not isinstance(snapshot, dict):
            continue

        payload = _score_payload_from_snapshot(snapshot)
        saved_at = snapshot.get("saved_at")
        parsed_at = _parse_saved_at(saved_at)

        row = {
            "Ticker": str(snapshot.get("ticker") or ticker).upper(),
            "Fecha": parsed_at or saved_at,
            "Guardado": saved_at,
            "VQ Score": _as_float(_first_not_none(snapshot.get("valuequant_score"), payload.get("final_score"))),
            "Score bruto": _as_float(_first_not_none(snapshot.get("score_raw_score"), payload.get("raw_score"))),
            "Buffett": _as_float(snapshot.get("buffett_score")),
            "Calidad": _as_float(snapshot.get("quality_score")),
            "Valoración": _as_float(snapshot.get("valuation_score")),
            "Riesgo": _as_float(snapshot.get("risk_score")),
            "Crecimiento": _as_float(snapshot.get("growth_score")),
            "Margen Seguridad": _as_float(snapshot.get("margin_of_safety")),
            "Confianza": _as_float(_first_not_none(snapshot.get("confidence"), payload.get("confidence"))),
            "Cobertura": _as_float(_first_not_none(snapshot.get("data_coverage"), payload.get("data_coverage"))),
            "Confianza Predictiva": _as_float(
                _first_not_none(snapshot.get("predictive_confidence"), payload.get("predictive_confidence"))
            ),
            "Nivel confianza": _first_not_none(snapshot.get("score_confidence_label"), payload.get("confidence_label"), "-"),
            "Acción Score": _first_not_none(snapshot.get("score_decision_action"), payload.get("decision_action"), "-"),
            "Acción Research": snapshot.get("action", "-"),
            "Ajuste Calidad": bool(_first_not_none(snapshot.get("score_quality_adjusted"), payload.get("quality_adjusted"), False)),
            "Quality Gate": _first_not_none(snapshot.get("score_quality_gate_reason"), payload.get("quality_gate_reason"), "-"),
            "Red Flags": _snapshot_red_flags_count(snapshot),
            "Régimen": snapshot.get("valuation_regime", "-"),
            "Target": _as_float(snapshot.get("target")),
            "_sort_ts": parsed_at.timestamp() if parsed_at else 0.0,
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("_sort_ts", ascending=True).drop(columns=["_sort_ts"]).reset_index(drop=True)
    if limit is not None and limit > 0:
        df = df.tail(limit).reset_index(drop=True)
    return df


def score_evolution_summary(ticker: str) -> dict[str, Any]:
    """Resumen de evolución temporal del score para un ticker."""

    df = score_history_for_ticker(ticker)
    ticker = str(ticker or "").upper().strip()

    if df.empty:
        return {
            "ticker": ticker,
            "observations": 0,
            "trend_label": "Sin histórico",
            "trend_detail": "No hay análisis guardados para calcular evolución temporal.",
        }

    latest = df.iloc[-1].to_dict()
    previous = df.iloc[-2].to_dict() if len(df) >= 2 else {}

    latest_score = _as_float(latest.get("VQ Score"))
    previous_score = _as_float(previous.get("VQ Score")) if previous else None
    latest_margin = _as_float(latest.get("Margen Seguridad"))
    previous_margin = _as_float(previous.get("Margen Seguridad")) if previous else None

    delta_score = (
        round(latest_score - previous_score, 2)
        if latest_score is not None and previous_score is not None
        else None
    )
    delta_margin = (
        round(latest_margin - previous_margin, 4)
        if latest_margin is not None and previous_margin is not None
        else None
    )

    if delta_score is None:
        trend_label = "Sin histórico suficiente"
        trend_detail = "Solo hay un análisis guardado; aún no puede calcularse tendencia."
    elif delta_score >= 2:
        trend_label = "Mejora"
        trend_detail = f"El score ha subido {delta_score:+.1f} puntos frente al análisis anterior."
    elif delta_score <= -2:
        trend_label = "Deterioro"
        trend_detail = f"El score ha caído {delta_score:+.1f} puntos frente al análisis anterior."
    else:
        trend_label = "Estable"
        trend_detail = f"El score se mantiene estable ({delta_score:+.1f} puntos)."

    return {
        "ticker": ticker,
        "observations": int(len(df)),
        "latest_score": latest_score,
        "previous_score": previous_score,
        "delta_score": delta_score,
        "latest_margin": latest_margin,
        "delta_margin": delta_margin,
        "latest_confidence": _as_float(latest.get("Confianza")),
        "latest_action_score": latest.get("Acción Score"),
        "latest_quality_gate": latest.get("Quality Gate"),
        "latest_red_flags": int(_as_float(latest.get("Red Flags")) or 0),
        "latest_saved_at": latest.get("Guardado"),
        "trend_label": trend_label,
        "trend_detail": trend_detail,
    }


def render_save_to_watchlist_panel(
    *,
    ticker: str,
    competitor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
) -> None:
    """Panel Streamlit para guardar el análisis actual."""

    snapshot = build_research_snapshot(
        ticker=ticker,
        competitor=competitor,
        valuequant_score=valuequant_score,
        res_val=res_val,
        nota_buffett=nota_buffett,
    )

    st.markdown("### Guardar análisis y seguimiento")
    st.caption(
        "Guarda el snapshot actual en `data/research_analyses.json` y actualiza la watchlist local con precio objetivo, score y acción operativa."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Acción", str(snapshot.get("action", "N/D")))
    c2.metric("ValueQuant", _fmt_score(snapshot.get("valuequant_score")))
    c3.metric("Margen seguridad", _fmt_pct(snapshot.get("margin_of_safety")))
    c4.metric("Target seguimiento", _fmt_money(snapshot.get("target")))

    with st.expander("Ver datos que se guardarán", expanded=False):
        st.json(snapshot)

    if st.button("💾 Guardar en watchlist inteligente", type="primary", use_container_width=True):
        try:
            save_analysis_snapshot(snapshot)
            st.success(f"{ticker.upper()} guardado en watchlist inteligente.")
            st.info("Puedes revisarlo en 💼 Cartera y Decisión → 📋 Mi Watchlist (Cartera).")
        except Exception as exc:
            st.error(f"No se pudo guardar el análisis: {exc}")


def render_saved_research_dashboard() -> None:
    """Panel independiente de análisis guardados."""

    st.markdown("### Análisis Guardados")
    st.caption("Últimos snapshots guardados desde Research Core. Persistencia local en JSON.")

    rows = latest_snapshots()
    if not rows:
        st.info("Todavía no hay análisis guardados. Abre 🧩 Research Core y usa la pestaña 💾 Seguimiento.")
        return

    df = pd.DataFrame(
        [
            {
                "Ticker": row.get("ticker"),
                "Comparador": row.get("competitor") or "-",
                "Acción": row.get("action"),
                "VQ Score": row.get("valuequant_score"),
                "Buffett": row.get("buffett_score"),
                "Margen Seguridad": row.get("margin_of_safety"),
                "Target": row.get("target"),
                "Régimen": row.get("valuation_regime"),
                "Guardado": row.get("saved_at"),
            }
            for row in rows
        ]
    )

    st.dataframe(
        df.style.format(
            {
                "VQ Score": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Buffett": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "N/D",
                "Target": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "N/D",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    tickers = [str(row.get("ticker")) for row in rows if row.get("ticker")]
    selected = st.selectbox("Detalle histórico por ticker", tickers)
    history_df = score_history_for_ticker(selected)
    summary = score_evolution_summary(selected)

    if history_df.empty:
        st.info("No hay histórico normalizado disponible para este ticker.")
        return

    st.markdown(f"#### Evolución temporal — {selected}")

    e1, e2, e3, e4, e5 = st.columns(5)
    e1.metric("Observaciones", summary.get("observations", 0))
    e2.metric(
        "Último VQ",
        _fmt_score(summary.get("latest_score")),
        f"{summary.get('delta_score'):+.1f}" if isinstance(summary.get("delta_score"), (int, float)) else None,
    )
    e3.metric(
        "Margen",
        _fmt_pct(summary.get("latest_margin")),
        f"{summary.get('delta_margin'):+.1%}" if isinstance(summary.get("delta_margin"), (int, float)) else None,
    )
    e4.metric("Confianza", _fmt_pct(summary.get("latest_confidence")))
    e5.metric("Red Flags", summary.get("latest_red_flags", 0))

    st.info(f"**Tendencia:** {summary.get('trend_label')} — {summary.get('trend_detail')}")

    quality_gate = summary.get("latest_quality_gate")
    if quality_gate and quality_gate != "-":
        st.warning(f"Quality gate activo en último análisis: {quality_gate}")

    chart_df = history_df.copy()
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

    if len(chart_df) >= 2 and chart_cols:
        chart_df["Fecha"] = pd.to_datetime(chart_df["Guardado"], errors="coerce")
        chart_ready = chart_df.dropna(subset=["Fecha"]).set_index("Fecha")[chart_cols]
        if not chart_ready.empty:
            st.line_chart(chart_ready)

    display_cols = [
        "Guardado",
        "VQ Score",
        "Score bruto",
        "Buffett",
        "Margen Seguridad",
        "Confianza",
        "Cobertura",
        "Nivel confianza",
        "Acción Score",
        "Ajuste Calidad",
        "Quality Gate",
        "Red Flags",
        "Régimen",
        "Target",
    ]
    display_cols = [col for col in display_cols if col in history_df.columns]

    st.dataframe(
        history_df[display_cols].style.format(
            {
                "VQ Score": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Score bruto": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Buffett": lambda x: f"{x:.1f}" if isinstance(x, (int, float)) else "N/D",
                "Margen Seguridad": lambda x: f"{x:+.1%}" if isinstance(x, (int, float)) else "N/D",
                "Confianza": lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "N/D",
                "Cobertura": lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "N/D",
                "Target": lambda x: f"${x:,.2f}" if isinstance(x, (int, float)) and x > 0 else "N/D",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Ver snapshots brutos guardados", expanded=False):
        raw_history = load_saved_analyses().get(selected, [])
        st.dataframe(pd.DataFrame(raw_history), use_container_width=True, hide_index=True)

    st.markdown("---")
    try:
        from modulos.signal_backtesting import render_signal_backtest_panel

        render_signal_backtest_panel(default_ticker=selected)
    except Exception as exc:
        st.warning(f"No se pudo cargar el backtesting básico de señales: {exc}")
