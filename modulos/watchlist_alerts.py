"""Motor de alertas inteligentes para la watchlist.

Evalua cada activo en seguimiento combinando precio actual, target operativo,
ValueQuant Score, margen de seguridad y antigüedad del análisis guardado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from modulos.sec_fmp_cross_validation import SEVERE_DISCREPANCY_PCT
from modulos.sec_validation_store import sec_validation_summary


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sí", "si", "yes", "y"}
    return bool(value)


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


def _sec_validation_alert(ticker: str) -> WatchlistAlert | None:
    """Alerta a partir del resumen compacto que persiste el job nocturno
    (modulos/sec_validation_store.py, Sub-fase 3b) — se relee por ticker
    directamente (lectura local en JSON, no red) en vez de depender de
    columnas de paso en ``row``, igual que ``score_evolution_summary``.

    ``None`` tanto si nunca hubo verificación como si la hubo y coincide del
    todo: ninguno de los dos casos es una alerta — "sin verificar" no es un
    riesgo en sí mismo, se refleja en la columna "SEC" de Watchlist, no aquí.
    """

    summary = sec_validation_summary(ticker)
    if not summary or not summary.get("last_successful_check_at"):
        return None

    discrepancy_count = int(summary.get("discrepancy_count") or 0)
    period_misaligned_count = int(summary.get("period_misaligned_count") or 0)
    if discrepancy_count == 0 and period_misaligned_count == 0:
        return None

    if discrepancy_count > 0:
        worst_diff = summary.get("worst_diff_pct")
        severa = worst_diff is not None and abs(worst_diff) > SEVERE_DISCREPANCY_PCT
        worst_metric = summary.get("worst_metric")
        detail = f"{discrepancy_count} métrica(s) difieren de SEC EDGAR"
        detail += f" (peor: {worst_metric}, {worst_diff:+.1f}%)." if worst_metric and worst_diff is not None else "."
        return _alert(
            ticker=ticker,
            priority="Alta" if severa else "Media",
            category="SEC EDGAR",
            title="Discrepancia con SEC EDGAR",
            detail=detail,
            action="Revisar en Auditoría Forense → Modo Auditoría",
            score=82 if severa else 60,
        )

    return _alert(
        ticker=ticker,
        priority="Baja",
        category="SEC EDGAR",
        title="Posible restatement SEC EDGAR",
        detail=f"{period_misaligned_count} métrica(s) con fechas de periodo no coincidentes frente a SEC EDGAR.",
        action="Revisar en Auditoría Forense → Modo Auditoría",
        score=48,
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
    score_action = str(row.get("Acción Score", "") or "").strip()
    score_action_lower = score_action.lower()
    confidence = _as_float(row.get("Confianza"))
    confidence_label = str(row.get("Nivel confianza", "") or "").strip().lower()
    quality_adjusted = _as_bool(row.get("Ajuste Calidad"))
    quality_gate = str(row.get("Quality Gate", "") or "").strip()
    red_flags_count = int(_as_float(row.get("Red Flags")) or 0)
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

    if red_flags_count > 0:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Alta",
                category="Score",
                title="Red flags en score",
                detail=f"El último score guardado contiene {red_flags_count} red flag(s).",
                action="Revisar riesgos antes de priorizar",
                score=90,
            )
        )

    sec_alert = _sec_validation_alert(ticker)
    if sec_alert is not None:
        alerts.append(sec_alert)

    if quality_adjusted:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Alta" if red_flags_count > 0 else "Media",
                category="Score",
                title="Score ajustado por quality gates",
                detail=quality_gate if quality_gate and quality_gate != "-" else "El score fue limitado por calidad/cobertura/confianza de datos.",
                action="Validar datos antes de comparar",
                score=84,
            )
        )

    if "prioritario" in score_action_lower and not quality_adjusted and red_flags_count == 0:
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Alta",
                category="Score",
                title="Candidato prioritario por score",
                detail=f"Acción institucional guardada: {score_action}.",
                action="Pasar a tesis y valoración",
                score=88,
            )
        )

    if "esperar" in score_action_lower or confidence_label == "baja" or (confidence is not None and confidence < 0.55):
        alerts.append(
            _alert(
                ticker=ticker,
                priority="Baja",
                category="Score",
                title="Confianza limitada",
                detail=f"Confianza operativa: {confidence:.0%}." if confidence is not None else "El score indica esperar más datos.",
                action="Actualizar datos antes de decidir",
                score=44,
            )
        )

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
