"""Controles locales de frecuencia para futuras automatizaciones.

Este módulo no programa tareas ni ejecuta envíos en segundo plano. Solo guarda
preferencias locales y comprueba si un envío manual/programado respetaría la
frecuencia configurada.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from modulos.automation_logs import load_automation_log

SETTINGS_PATH = Path("data") / "automation_settings.json"
FREQUENCY_LABELS = {
    "manual": "Solo manual",
    "daily": "Diaria",
    "weekly": "Semanal",
}


@dataclass(frozen=True)
class AutomationScheduleSettings:
    automation_enabled: bool = False
    frequency: str = "manual"
    channel: str = "telegram"
    max_deliveries_per_period: int = 1
    allow_manual_override: bool = True
    updated_at: str = ""


@dataclass(frozen=True)
class DeliveryFrequencyDecision:
    allowed: bool
    reason: str
    period_key: str
    deliveries_in_period: int
    max_deliveries_per_period: int
    last_successful_delivery: str | None = None


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _normalise_frequency(value: Any) -> str:
    raw = str(value or "manual").strip().lower()
    return raw if raw in FREQUENCY_LABELS else "manual"


def _normalise_settings(raw: dict[str, Any] | None) -> AutomationScheduleSettings:
    raw = raw or {}
    max_deliveries = int(raw.get("max_deliveries_per_period") or 1)
    max_deliveries = max(1, min(max_deliveries, 5))
    return AutomationScheduleSettings(
        automation_enabled=bool(raw.get("automation_enabled", False)),
        frequency=_normalise_frequency(raw.get("frequency")),
        channel=str(raw.get("channel") or "telegram").strip().lower() or "telegram",
        max_deliveries_per_period=max_deliveries,
        allow_manual_override=bool(raw.get("allow_manual_override", True)),
        updated_at=str(raw.get("updated_at") or ""),
    )


def load_automation_settings() -> AutomationScheduleSettings:
    """Carga la configuración local de frecuencia."""

    if not SETTINGS_PATH.exists():
        return AutomationScheduleSettings()
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return AutomationScheduleSettings()
    return _normalise_settings(raw)


def save_automation_settings(settings: AutomationScheduleSettings) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    payload["updated_at"] = _now_iso()
    SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _period_key(ts: datetime, frequency: str) -> str:
    frequency = _normalise_frequency(frequency)
    if frequency == "weekly":
        year, week, _ = ts.isocalendar()
        return f"{year}-W{week:02d}"
    if frequency == "daily":
        return ts.strftime("%Y-%m-%d")
    return "manual"


def _successful_delivery_rows(channel: str = "telegram") -> pd.DataFrame:
    df = load_automation_log(limit=1000)
    if df.empty:
        return df
    required = {"event_type", "status", "channel", "timestamp"}
    if not required.issubset(set(df.columns)):
        return pd.DataFrame()
    view = df[
        (df["event_type"] == "delivery_attempt")
        & (df["status"] == "ok")
        & (df["channel"].astype(str).str.lower() == str(channel).lower())
    ].copy()
    if view.empty:
        return view
    view["_timestamp_dt"] = pd.to_datetime(view["timestamp"], errors="coerce")
    view = view.dropna(subset=["_timestamp_dt"])
    return view.sort_values("_timestamp_dt", ascending=False)


def evaluate_delivery_frequency(
    *,
    channel: str = "telegram",
    frequency: str | None = None,
    max_deliveries_per_period: int | None = None,
    now: datetime | None = None,
) -> DeliveryFrequencyDecision:
    """Evalúa si un envío respetaría la frecuencia configurada."""

    settings = load_automation_settings()
    frequency = _normalise_frequency(frequency or settings.frequency)
    max_allowed = int(max_deliveries_per_period or settings.max_deliveries_per_period or 1)
    max_allowed = max(1, min(max_allowed, 5))
    now = now or datetime.now()

    if frequency == "manual":
        rows = _successful_delivery_rows(channel)
        last = None
        if not rows.empty:
            last = str(rows.iloc[0].get("timestamp") or "")
        return DeliveryFrequencyDecision(
            allowed=True,
            reason="Modo solo manual: no se aplica bloqueo por periodo.",
            period_key="manual",
            deliveries_in_period=0,
            max_deliveries_per_period=max_allowed,
            last_successful_delivery=last,
        )

    current_period = _period_key(now, frequency)
    rows = _successful_delivery_rows(channel)
    if rows.empty:
        return DeliveryFrequencyDecision(
            allowed=True,
            reason=f"No hay envíos correctos registrados en el periodo {current_period}.",
            period_key=current_period,
            deliveries_in_period=0,
            max_deliveries_per_period=max_allowed,
            last_successful_delivery=None,
        )

    rows["_period"] = rows["_timestamp_dt"].apply(lambda x: _period_key(x.to_pydatetime(), frequency))
    in_period = int((rows["_period"] == current_period).sum())
    last = str(rows.iloc[0].get("timestamp") or "")
    allowed = in_period < max_allowed
    if allowed:
        reason = f"Periodo {current_period}: {in_period}/{max_allowed} envíos correctos registrados."
    else:
        reason = f"Bloqueo de frecuencia: ya hay {in_period}/{max_allowed} envíos correctos en {current_period}."
    return DeliveryFrequencyDecision(
        allowed=allowed,
        reason=reason,
        period_key=current_period,
        deliveries_in_period=in_period,
        max_deliveries_per_period=max_allowed,
        last_successful_delivery=last,
    )


def render_schedule_control_panel() -> None:
    """Panel Streamlit de configuración segura de frecuencia."""

    st.subheader("Control de frecuencia")
    st.caption(
        "Configura límites para futuros envíos programados. Esto no activa procesos en segundo plano; "
        "solo guarda preferencias locales y evita duplicados cuando se usa el envío manual."
    )

    settings = load_automation_settings()

    frequency_options = list(FREQUENCY_LABELS.keys())
    current_frequency_idx = frequency_options.index(settings.frequency) if settings.frequency in frequency_options else 0

    c1, c2 = st.columns(2)
    with c1:
        automation_enabled = st.checkbox(
            "Preparar automatización futura",
            value=settings.automation_enabled,
            help="Interruptor declarativo. No programa tareas por sí solo.",
            key="automation_settings_enabled",
        )
        frequency = st.selectbox(
            "Frecuencia permitida",
            frequency_options,
            index=current_frequency_idx,
            format_func=lambda value: FREQUENCY_LABELS.get(value, value),
            key="automation_settings_frequency",
        )
    with c2:
        max_deliveries = st.number_input(
            "Máximo de envíos correctos por periodo",
            min_value=1,
            max_value=5,
            value=int(settings.max_deliveries_per_period),
            step=1,
            key="automation_settings_max_deliveries",
        )
        allow_override = st.checkbox(
            "Permitir override manual con confirmación adicional",
            value=settings.allow_manual_override,
            key="automation_settings_override",
        )

    draft = AutomationScheduleSettings(
        automation_enabled=automation_enabled,
        frequency=frequency,
        channel="telegram",
        max_deliveries_per_period=int(max_deliveries),
        allow_manual_override=allow_override,
        updated_at=settings.updated_at,
    )

    decision = evaluate_delivery_frequency(
        channel=draft.channel,
        frequency=draft.frequency,
        max_deliveries_per_period=draft.max_deliveries_per_period,
    )

    s1, s2, s3 = st.columns(3)
    s1.metric("Periodo actual", decision.period_key)
    s2.metric("Envíos del periodo", f"{decision.deliveries_in_period}/{decision.max_deliveries_per_period}")
    s3.metric("Último envío OK", decision.last_successful_delivery or "Sin registros")

    if decision.allowed:
        st.success(decision.reason)
    else:
        st.warning(decision.reason)

    if st.button("Guardar configuración de frecuencia", use_container_width=True):
        save_automation_settings(draft)
        st.success("Configuración de frecuencia guardada.")
        st.rerun()

    with st.expander("Archivo local de configuración", expanded=False):
        st.code(str(SETTINGS_PATH), language="text")
        if SETTINGS_PATH.exists():
            st.code(SETTINGS_PATH.read_text(encoding="utf-8"), language="json")
        else:
            st.caption("Aún no existe. Se creará al guardar configuración.")
