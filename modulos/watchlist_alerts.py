"""Motor de alertas inteligentes para la watchlist.

Evalua cada activo en seguimiento combinando precio actual, target operativo,
ValueQuant Score, margen de seguridad y antigüedad del análisis guardado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class WatchlistAlert:
    ticker: str
    priority: str
    category: str
    title: str
    detail: str
    action: str
    score: int


_PRIORITY_ORDER = {
    "Alta": 3,
    "Media": 2,
    "Baja": 1,
    "Info": 0,
}


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        if isinstance(value, str) and value.strip() in {"", "-", "N/D"}:
            return None
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except Exception:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _days_since(value: Any) -> int | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0, (datetime.now(timezone.utc) - parsed).days)


def _alert(
    *,
    ticker: str,
    priority: str,
    category: str,
    title: str,
    detail: str,
    action: str,
    score: int,
) -> WatchlistAlert:
    return WatchlistAlert(
        ticker=ticker,
        priority=priority,
        category=category,
        title=title,
        detail=detail,
        action=action,
        score=score,
    )


def evaluate_watchlist_row(row: dict[str, Any]) -> list[WatchlistAlert]:
    """Genera alertas para una fila normalizada de watchlist."""

    ticker = str(row.get("Ticker", "")).upper().strip()
    if not ticker:
        return []

    current_price = _as_float(row.get("Precio Actual"))
    target = _as_float(row.get("Precio Objetivo"))
    valuequant = _as_float(row.get("ValueQuant"))
    margin = _as_float(row.get("Margen Seguridad"))
    action_research = str(row.get("Acción Research", "") or "").strip()
    valuation_regime = str(row.get("Régimen Valoración", "") or "").lower()
    source = str(row.get("Fuente", "") or "")
    last_analysis = row.get("Último análisis")
    days_old = _days_since(last_analysis)

    alerts: list[WatchlistAlert] = []

    if current_price is None or current_price <= 0:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Info",
                category="Datos",
                title="Precio no disponible",
                detail="No se pudo sincronizar el precio actual. Revisa yfinance/FMP antes de decidir.",
                action="Revisar datos",
                score=10,
            )
        )
        return alerts

    if target is not None and target > 0:
        distance_to_target = (current_price - target) / target

        if current_price <= target:
            priority = "Alta" if (valuequant or 0) >= 60 else "Media"
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority=priority,
                    category="Precio",
                    title="Precio en zona objetivo",
                    detail=f"Cotiza a ${current_price:.2f}, igual o por debajo del target ${target:.2f}.",
                    action="Revisar entrada",
                    score=95 if priority == "Alta" else 78,
                )
            )
        elif distance_to_target <= 0.05:
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority="Alta" if (valuequant or 0) >= 70 else "Media",
                    category="Precio",
                    title="Muy cerca del target",
                    detail=f"Está solo un {distance_to_target:.1%} por encima del target operativo.",
                    action="Preparar seguimiento",
                    score=86,
                )
            )
        elif distance_to_target <= 0.10:
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority="Media",
                    category="Precio",
                    title="Cerca del target",
                    detail=f"Necesita caer aproximadamente un {distance_to_target:.1%} para tocar target.",
                    action="Vigilar precio",
                    score=68,
                )
            )
    else:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Info",
                category="Valoración",
                title="Sin target operativo",
                detail="No hay precio objetivo guardado. Guarda un análisis desde Research Core o introduce target manual.",
                action="Completar target",
                score=20,
            )
        )

    if valuequant is not None and valuequant >= 75 and margin is not None and margin < -0.10:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Media",
                category="Calidad/Precio",
                title="Alta calidad, precio exigente",
                detail=f"ValueQuant {valuequant:.1f}/100, pero margen de seguridad {margin:+.1%}.",
                action="Esperar mejor precio",
                score=74,
            )
        )

    if valuequant is not None and valuequant >= 65 and margin is not None and margin >= 0:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Alta" if margin >= 0.15 else "Media",
                category="Oportunidad",
                title="Score sólido con margen positivo",
                detail=f"ValueQuant {valuequant:.1f}/100 y margen de seguridad {margin:+.1%}.",
                action="Analizar compra",
                score=92 if margin >= 0.15 else 82,
            )
        )

    if valuequant is not None and valuequant < 45:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Baja",
                category="Calidad",
                title="Score débil",
                detail=f"ValueQuant {valuequant:.1f}/100. No priorizar salvo tesis especial.",
                action="Revisar o descartar",
                score=42,
            )
        )

    if "evitar" in action_research.lower():
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Media",
                category="Tesis",
                title="Research recomienda evitar",
                detail=f"Acción operativa guardada: {action_research}.",
                action="No priorizar",
                score=62,
            )
        )

    if any(term in valuation_regime for term in ("cara", "exigente", "sobrevalor")):
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Baja",
                category="Valoración",
                title="Valoración exigente",
                detail=f"Régimen de valoración guardado: {row.get('Régimen Valoración', '-')}.",
                action="Exigir margen",
                score=45,
            )
        )

    if source == "Research Core":
        if days_old is None:
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority="Info",
                    category="Seguimiento",
                    title="Fecha de análisis no disponible",
                    detail="El snapshot Research no tiene fecha interpretable.",
                    action="Recalcular análisis",
                    score=25,
                )
            )
        elif days_old >= 90:
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority="Media",
                    category="Seguimiento",
                    title="Análisis desactualizado",
                    detail=f"El último análisis tiene {days_old} días. Puede haber cambiado la tesis.",
                    action="Recalcular Research Core",
                    score=66,
                )
            )
        elif days_old >= 30:
            alerts.append(
                _alert(
                    ticker=ticker,
                    priority="Baja",
                    category="Seguimiento",
                    title="Análisis con más de 30 días",
                    detail=f"Último análisis hace {days_old} días.",
                    action="Revisar próximamente",
                    score=38,
                )
            )

    if not alerts:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Info",
                category="Seguimiento",
                title="Sin alerta relevante",
                detail="El activo no está cerca de target ni muestra una señal prioritaria con los datos actuales.",
                action="Mantener en seguimiento",
                score=15,
            )
        )

    alerts.sort(key=lambda item: (_PRIORITY_ORDER.get(item.priority, 0), item.score), reverse=True)
    return alerts


def build_watchlist_alerts(df_watch: pd.DataFrame) -> pd.DataFrame:
    """Construye un DataFrame de alertas para toda la watchlist."""

    if df_watch is None or df_watch.empty:
        return pd.DataFrame(
            columns=["Prioridad", "Ticker", "Categoría", "Alerta", "Detalle", "Acción sugerida", "Score"]
        )

    records: list[dict[str, Any]] = []
    for _, row in df_watch.iterrows():
        for alert in evaluate_watchlist_row(row.to_dict()):
            records.append(
                {
                    "Prioridad": alert.priority,
                    "Ticker": alert.ticker,
                    "Categoría": alert.category,
                    "Alerta": alert.title,
                    "Detalle": alert.detail,
                    "Acción sugerida": alert.action,
                    "Score": alert.score,
                    "_rank": _PRIORITY_ORDER.get(alert.priority, 0),
                }
            )

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(
            columns=["Prioridad", "Ticker", "Categoría", "Alerta", "Detalle", "Acción sugerida", "Score"]
        )

    df = df.sort_values(["_rank", "Score"], ascending=[False, False]).drop(columns=["_rank"])
    return df.reset_index(drop=True)


def alert_summary(df_alerts: pd.DataFrame) -> dict[str, int]:
    """Resumen rápido por prioridad."""

    if df_alerts is None or df_alerts.empty:
        return {"Alta": 0, "Media": 0, "Baja": 0, "Info": 0}

    counts = df_alerts["Prioridad"].value_counts().to_dict()
    return {priority: int(counts.get(priority, 0)) for priority in ("Alta", "Media", "Baja", "Info")}
