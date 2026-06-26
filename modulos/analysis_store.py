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

    snapshot = {
        "ticker": ticker,
        "competitor": competitor,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "action": thesis.action,
        "action_detail": thesis.action_detail,
        "valuequant_score": _as_float(thesis.final_score),
        "buffett_score": _as_float(thesis.buffett_score),
        "quality_score": _as_float(thesis.quality_score),
        "valuation_score": _as_float(thesis.valuation_score),
        "risk_score": _as_float(thesis.risk_score),
        "growth_score": _as_float(thesis.growth_score),
        "data_coverage": _as_float(_score_attr(valuequant_score, "data_coverage")),
        "confidence": _as_float(_score_attr(valuequant_score, "confidence")),
        "predictive_confidence": _as_float(_score_attr(valuequant_score, "predictive_confidence")),
        "model_version": _score_attr(valuequant_score, "model_version", "N/D"),
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
                "valuequant_score": snapshot.get("valuequant_score"),
                "buffett_score": snapshot.get("buffett_score"),
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

    st.markdown("### 📚 Análisis Guardados")
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
    history = load_saved_analyses().get(selected, [])
    if history:
        st.markdown(f"#### Histórico — {selected}")
        st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)
