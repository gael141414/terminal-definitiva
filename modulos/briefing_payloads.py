"""Payloads reutilizables para briefing de oportunidades.

Genera versiones compactas para revisión manual: texto corto, texto de email y HTML.
No realiza envíos automáticos ni accede a credenciales.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BriefingPayloads:
    generated_at: datetime
    compact_text: str
    email_subject: str
    email_text: str
    email_html: str


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


def _fmt_money(value: Any) -> str:
    number = _as_float(value, None)
    return f"${number:,.2f}" if number is not None and number > 0 else "-"


def _fmt_score(value: Any) -> str:
    number = _as_float(value, None)
    return f"{number:.1f}" if number is not None else "-"


def _fmt_pct(value: Any) -> str:
    number = _as_float(value, None)
    return f"{number:+.1%}" if number is not None else "-"


def _safe_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _bucket(df_briefing: pd.DataFrame, name: str, limit: int) -> pd.DataFrame:
    if df_briefing is None or df_briefing.empty or "Prioridad" not in df_briefing.columns:
        return pd.DataFrame()
    subset = df_briefing[df_briefing["Prioridad"] == name].copy()
    if "Score Oportunidad" in subset.columns:
        subset = subset.sort_values("Score Oportunidad", ascending=False)
    return subset.head(limit)


def build_compact_briefing_text(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
    max_items: int = 8,
) -> str:
    """Genera un briefing compacto para copiar en mensajería."""

    generated_at = generated_at or datetime.now()
    total = len(df_watch) if df_watch is not None else 0
    high_alerts = 0
    if df_alerts is not None and not df_alerts.empty and "Prioridad" in df_alerts.columns:
        high_alerts = int((df_alerts["Prioridad"] == "Alta").sum())

    lines: list[str] = [
        "📌 ValueQuant Briefing",
        generated_at.strftime("%Y-%m-%d %H:%M"),
        "",
        f"Watchlist: {total} activos | Alertas altas: {high_alerts}",
    ]

    if df_briefing is not None and not df_briefing.empty:
        top = df_briefing.iloc[0].to_dict()
        lines.extend(
            [
                "",
                f"Prioridad: {top.get('Ticker', '-')} — {top.get('Prioridad', '-')}",
                f"Score oportunidad: {top.get('Score Oportunidad', '-')}",
                f"Razón: {_safe_text(top.get('Razón'))}",
            ]
        )

    def add_section(title: str, bucket_name: str) -> None:
        subset = _bucket(df_briefing, bucket_name, max_items)
        lines.extend(["", title])
        if subset.empty:
            lines.append("- Sin elementos.")
            return
        for _, row in subset.iterrows():
            r = row.to_dict()
            lines.append(
                "- "
                f"{r.get('Ticker', '-')}: "
                f"score {_fmt_score(r.get('Score Oportunidad'))}, "
                f"precio {_fmt_money(r.get('Precio Actual'))}, "
                f"target {_fmt_money(r.get('Target'))}, "
                f"VQ {_fmt_score(r.get('ValueQuant'))}."
            )

    add_section("✅ Revisar hoy", "Comprar / revisar hoy")
    add_section("👀 Vigilar caída", "Vigilar caída")
    add_section("🔄 Recalcular", "Recalcular análisis")

    lines.extend(
        [
            "",
            "Nota: briefing informativo. Revisar tesis, riesgo de cartera y liquidez antes de operar.",
        ]
    )
    return "\n".join(lines)


def build_email_text(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now()
    return (
        build_compact_briefing_text(
            df_watch, df_alerts, df_briefing, generated_at=generated_at, max_items=12
        )
        + "\n\nFlujo sugerido:\n"
        + "1. Revisar primero los activos marcados como comprar/revisar hoy.\n"
        + "2. Recalcular análisis desactualizados.\n"
        + "3. Contrastar cada oportunidad con liquidez, concentración y contexto macro.\n"
    )


def _email_rows(df_briefing: pd.DataFrame, bucket_name: str, limit: int = 10) -> str:
    subset = _bucket(df_briefing, bucket_name, limit)
    if subset.empty:
        return "<tr><td colspan='7'>Sin elementos.</td></tr>"
    rows: list[str] = []
    for _, row in subset.iterrows():
        r = row.to_dict()
        rows.append(
            "<tr>"
            f"<td>{escape(_safe_text(r.get('Ticker')))}</td>"
            f"<td>{escape(_fmt_score(r.get('Score Oportunidad')))}</td>"
            f"<td>{escape(_fmt_money(r.get('Precio Actual')))}</td>"
            f"<td>{escape(_fmt_money(r.get('Target')))}</td>"
            f"<td>{escape(_fmt_score(r.get('ValueQuant')))}</td>"
            f"<td>{escape(_fmt_pct(r.get('Margen Seguridad')))}</td>"
            f"<td>{escape(_safe_text(r.get('Razón')))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_email_html(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or datetime.now()
    total = len(df_watch) if df_watch is not None else 0
    high_alerts = 0
    if df_alerts is not None and not df_alerts.empty and "Prioridad" in df_alerts.columns:
        high_alerts = int((df_alerts["Prioridad"] == "Alta").sum())

    top_html = "<p>Sin prioridad principal.</p>"
    if df_briefing is not None and not df_briefing.empty:
        top = df_briefing.iloc[0].to_dict()
        top_html = (
            f"<p><strong>{escape(_safe_text(top.get('Ticker')))}</strong> — "
            f"{escape(_safe_text(top.get('Prioridad')))} | "
            f"Score oportunidad: <strong>{escape(_safe_text(top.get('Score Oportunidad')))}</strong></p>"
            f"<p>{escape(_safe_text(top.get('Razón')))}</p>"
        )

    table_header = "<thead><tr><th>Ticker</th><th>Score</th><th>Precio</th><th>Target</th><th>VQ</th><th>Margen</th><th>Razón</th></tr></thead>"

    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>ValueQuant Briefing</title>
  <style>
    body {{ font-family: Arial, sans-serif; background: #f8fafc; color: #111827; margin: 0; padding: 24px; }}
    .card {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
    h1 {{ margin: 0 0 8px; }}
    h2 {{ color: #0f766e; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .muted {{ color: #6b7280; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>📌 ValueQuant Briefing</h1>
    <p class="muted">Generado: {generated_at.strftime('%Y-%m-%d %H:%M')}</p>
    <p>Watchlist: <strong>{total}</strong> activos | Alertas altas: <strong>{high_alerts}</strong></p>
  </div>
  <div class="card"><h2>Prioridad principal</h2>{top_html}</div>
  <div class="card"><h2>Comprar / revisar hoy</h2><table>{table_header}<tbody>{_email_rows(df_briefing, 'Comprar / revisar hoy')}</tbody></table></div>
  <div class="card"><h2>Vigilar caída</h2><table>{table_header}<tbody>{_email_rows(df_briefing, 'Vigilar caída')}</tbody></table></div>
  <div class="card"><h2>Recalcular análisis</h2><table>{table_header}<tbody>{_email_rows(df_briefing, 'Recalcular análisis')}</tbody></table></div>
  <p class="muted">Briefing informativo. No constituye asesoramiento financiero personalizado.</p>
</body>
</html>"""


def build_briefing_payloads(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
) -> BriefingPayloads:
    generated_at = generated_at or datetime.now()
    subject = f"ValueQuant Briefing - {generated_at.strftime('%Y-%m-%d')}"
    return BriefingPayloads(
        generated_at=generated_at,
        compact_text=build_compact_briefing_text(df_watch, df_alerts, df_briefing, generated_at=generated_at),
        email_subject=subject,
        email_text=build_email_text(df_watch, df_alerts, df_briefing, generated_at=generated_at),
        email_html=build_email_html(df_watch, df_alerts, df_briefing, generated_at=generated_at),
    )
