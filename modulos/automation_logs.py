"""Registro local de auditoria para automatizacion operativa.

El modulo guarda eventos ligeros en `data/automation_log.jsonl`. No almacena
credenciales, tokens ni contenido completo de mensajes. Solo registra metadatos
operativos suficientes para auditar generacion de briefings e intentos de envio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import streamlit as st

LOG_PATH = Path("data") / "automation_log.jsonl"
MAX_LOG_ROWS = 1000
DEDUP_WINDOW_MINUTES = 10


@dataclass(frozen=True)
class AutomationEvent:
    timestamp: str
    event_type: str
    status: str
    channel: str
    summary: str
    detail: str = ""
    ticker_count: int = 0
    high_alerts: int = 0
    review_today: int = 0
    recalculation_count: int = 0
    sent_parts: int = 0
    fingerprint: str = ""


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _ensure_log_dir() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _hash_payload(parts: Iterable[Any]) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _read_raw_events(limit: int | None = None) -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []

    rows: list[dict[str, Any]] = []
    with LOG_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if limit is not None and limit > 0:
        return rows[-limit:]
    return rows


def _is_recent_duplicate(event: AutomationEvent) -> bool:
    if not event.fingerprint:
        return False

    cutoff = datetime.now() - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    for row in reversed(_read_raw_events(limit=50)):
        if row.get("fingerprint") != event.fingerprint:
            continue
        if row.get("event_type") != event.event_type:
            continue
        try:
            ts = datetime.fromisoformat(str(row.get("timestamp")))
        except Exception:
            continue
        if ts >= cutoff:
            return True
    return False


def append_automation_event(event: AutomationEvent, *, dedupe: bool = True) -> bool:
    """Anade un evento al log local.

    Devuelve True si se escribio el evento y False si se ignoro por duplicado.
    """

    if dedupe and _is_recent_duplicate(event):
        return False

    _ensure_log_dir()
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
    _trim_log_file()
    return True


def _trim_log_file(max_rows: int = MAX_LOG_ROWS) -> None:
    if not LOG_PATH.exists():
        return
    rows = _read_raw_events()
    if len(rows) <= max_rows:
        return
    with LOG_PATH.open("w", encoding="utf-8") as fh:
        for row in rows[-max_rows:]:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def log_briefing_generated(df_watch: pd.DataFrame, df_alerts: pd.DataFrame, df_briefing: pd.DataFrame) -> bool:
    """Registra la generacion de un briefing operativo.

    Usa deduplicacion temporal para evitar spam por reruns de Streamlit.
    """

    ticker_count = int(len(df_watch)) if df_watch is not None else 0
    high_alerts = 0
    review_today = 0
    recalc = 0
    top_summary = "sin prioridades"

    if df_alerts is not None and not df_alerts.empty and "Prioridad" in df_alerts.columns:
        high_alerts = int((df_alerts["Prioridad"] == "Alta").sum())

    if df_briefing is not None and not df_briefing.empty:
        if "Prioridad" in df_briefing.columns:
            review_today = int((df_briefing["Prioridad"] == "Comprar / revisar hoy").sum())
            recalc = int((df_briefing["Prioridad"] == "Recalcular análisis").sum())
        first = df_briefing.iloc[0].to_dict()
        top_summary = f"{first.get('Ticker', '-')} · {first.get('Prioridad', '-')}"

    fingerprint = _hash_payload([
        "briefing_generated",
        ticker_count,
        high_alerts,
        review_today,
        recalc,
        top_summary,
        datetime.now().strftime("%Y%m%d_%H%M"),
    ])

    event = AutomationEvent(
        timestamp=_now_iso(),
        event_type="briefing_generated",
        status="ok",
        channel="local",
        summary=f"Briefing generado · {top_summary}",
        detail="Generado desde Centro de Automatización / Briefing de Oportunidades.",
        ticker_count=ticker_count,
        high_alerts=high_alerts,
        review_today=review_today,
        recalculation_count=recalc,
        fingerprint=fingerprint,
    )
    return append_automation_event(event, dedupe=True)


def log_delivery_attempt(*, channel: str, status: str, detail: str, sent_parts: int = 0, message: str = "") -> None:
    """Registra un intento de entrega sin almacenar el contenido completo."""

    fingerprint = _hash_payload([
        "delivery_attempt",
        channel,
        status,
        sent_parts,
        detail[:120],
        hashlib.sha256(str(message or "").encode("utf-8", errors="ignore")).hexdigest()[:16],
        datetime.now().strftime("%Y%m%d_%H%M"),
    ])
    event = AutomationEvent(
        timestamp=_now_iso(),
        event_type="delivery_attempt",
        status=status,
        channel=channel,
        summary=f"Intento de envio {channel}: {status}",
        detail=detail,
        sent_parts=int(sent_parts or 0),
        fingerprint=fingerprint,
    )
    append_automation_event(event, dedupe=False)


def load_automation_log(limit: int = 200) -> pd.DataFrame:
    rows = _read_raw_events(limit=limit)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    preferred = [
        "timestamp",
        "event_type",
        "status",
        "channel",
        "summary",
        "detail",
        "ticker_count",
        "high_alerts",
        "review_today",
        "recalculation_count",
        "sent_parts",
    ]
    columns = [col for col in preferred if col in df.columns]
    return df[columns].sort_values("timestamp", ascending=False, ignore_index=True)


def render_automation_log_panel(limit: int = 200) -> None:
    """Renderiza el historial de automatizacion en Streamlit."""

    st.subheader("Historial y auditoría")
    st.caption(
        "Registro local de generación de briefings e intentos de envío. "
        "No almacena tokens ni mensajes completos."
    )

    df_log = load_automation_log(limit=limit)
    if df_log.empty:
        st.info("Todavía no hay eventos registrados.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos", len(df_log))
    c2.metric("Briefings", int((df_log.get("event_type") == "briefing_generated").sum()))
    c3.metric("Envíos OK", int(((df_log.get("event_type") == "delivery_attempt") & (df_log.get("status") == "ok")).sum()))
    c4.metric("Errores envío", int(((df_log.get("event_type") == "delivery_attempt") & (df_log.get("status") != "ok")).sum()))

    event_types = ["Todos"] + sorted(df_log["event_type"].dropna().unique().tolist())
    selected = st.selectbox("Filtrar por tipo", event_types, key="automation_log_event_filter")
    view = df_log if selected == "Todos" else df_log[df_log["event_type"] == selected]

    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "Descargar log JSONL",
        data=LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else "",
        file_name="valuequant_automation_log.jsonl",
        mime="application/jsonl",
        use_container_width=True,
    )
