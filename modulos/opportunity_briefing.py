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

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
import json

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.watchlist_alerts import alert_summary, build_watchlist_alerts
from modulos.briefing_payloads import build_briefing_payloads

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

_EXPORT_COLUMNS = [
    "Prioridad",
    "Ticker",
    "Score Oportunidad",
    "Razón",
    "Acción sugerida",
    "Alerta principal",
    "Precio Actual",
    "Target",
    "Distancia",
    "ValueQuant",
    "Margen Seguridad",
    "Último análisis",
]


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


def _fmt_money(value: Any) -> str:
    number = _as_float(value, None)
    return f"${number:,.2f}" if number is not None and number > 0 else "-"


def _fmt_score(value: Any) -> str:
    number = _as_float(value, None)
    return f"{number:.1f}" if number is not None else "-"


def _fmt_pct(value: Any) -> str:
    number = _as_float(value, None)
    return f"{number:+.1%}" if number is not None else "-"


def _format_export_value(column: str, value: Any) -> str:
    if column in {"Precio Actual", "Target"}:
        return _fmt_money(value)
    if column in {"ValueQuant", "Score Oportunidad"}:
        return _fmt_score(value)
    if column == "Margen Seguridad":
        return _fmt_pct(value)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "Sin elementos.\n"
    safe_headers = [str(h) for h in headers]
    lines = ["| " + " | ".join(safe_headers) + " |", "| " + " | ".join(["---"] * len(safe_headers)) + " |"]
    for row in rows:
        cells = [str(cell).replace("|", "/").replace("\n", " ") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _section_rows(df: pd.DataFrame, bucket: str) -> list[list[str]]:
    if df.empty:
        return []
    subset = df[df["Prioridad"] == bucket]
    rows: list[list[str]] = []
    for _, row in subset.iterrows():
        row_dict = row.to_dict()
        rows.append(
            [
                _format_export_value("Ticker", row_dict.get("Ticker")),
                _format_export_value("Score Oportunidad", row_dict.get("Score Oportunidad")),
                _format_export_value("Precio Actual", row_dict.get("Precio Actual")),
                _format_export_value("Target", row_dict.get("Target")),
                _format_export_value("Distancia", row_dict.get("Distancia")),
                _format_export_value("ValueQuant", row_dict.get("ValueQuant")),
                _format_export_value("Margen Seguridad", row_dict.get("Margen Seguridad")),
                _format_export_value("Razón", row_dict.get("Razón")),
            ]
        )
    return rows


def build_opportunity_briefing_markdown(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
) -> str:
    """Genera un briefing Markdown exportable."""

    generated_at = generated_at or datetime.now()
    summary_alerts = alert_summary(df_alerts)
    top = df_briefing.iloc[0].to_dict() if not df_briefing.empty else {}

    lines: list[str] = [
        "# Briefing de Oportunidades - ValueQuant Terminal",
        "",
        f"**Fecha de generación:** {generated_at.strftime('%Y-%m-%d %H:%M')}",
        "",
        "> Documento de priorización operativa basado en watchlist, análisis Research Core, targets y precios actuales. No constituye asesoramiento financiero personalizado.",
        "",
        "## Resumen ejecutivo",
        "",
        _markdown_table(
            ["Métrica", "Valor"],
            [
                ["Activos en watchlist", len(df_watch)],
                ["Comprar / revisar hoy", int((df_briefing["Prioridad"] == "Comprar / revisar hoy").sum()) if not df_briefing.empty else 0],
                ["Vigilar caída", int((df_briefing["Prioridad"] == "Vigilar caída").sum()) if not df_briefing.empty else 0],
                ["Recalcular análisis", int((df_briefing["Prioridad"] == "Recalcular análisis").sum()) if not df_briefing.empty else 0],
                ["Alertas altas", summary_alerts.get("Alta", 0)],
            ],
        ),
    ]

    if top:
        lines.extend(
            [
                "## Prioridad principal",
                "",
                f"**{top.get('Ticker', '-')}** — {top.get('Prioridad', '-')}  ",
                f"Score oportunidad: **{top.get('Score Oportunidad', '-')}**  ",
                f"Razón: {top.get('Razón', '-')}",
                "",
            ]
        )

    section_headers = ["Ticker", "Score", "Precio", "Target", "Distancia", "VQ", "Margen", "Razón"]
    for bucket in _BUCKET_ORDER:
        if bucket == "Mantener seguimiento":
            title = "Mantener seguimiento"
        else:
            title = bucket
        lines.extend([f"## {title}", "", _markdown_table(section_headers, _section_rows(df_briefing, bucket)), ""])

    lines.extend(["## Todas las alertas", ""])
    if df_alerts.empty:
        lines.append("Sin alertas generadas.\n")
    else:
        alert_rows: list[list[str]] = []
        alert_cols = ["Prioridad", "Ticker", "Categoría", "Alerta", "Detalle", "Acción sugerida", "Score"]
        for _, row in df_alerts.iterrows():
            row_dict = row.to_dict()
            alert_rows.append([str(row_dict.get(col, "-")) for col in alert_cols])
        lines.append(_markdown_table(alert_cols, alert_rows))

    lines.extend(
        [
            "",
            "## Siguiente revisión sugerida",
            "",
            "- Revisar primero los activos en `Comprar / revisar hoy`.",
            "- Mantener vigilancia de precio en los activos de `Vigilar caída`.",
            "- Recalcular los análisis marcados como desactualizados o incompletos.",
            "- No ejecutar órdenes sin revisar tesis, liquidez, riesgo de cartera y contexto macro.",
            "",
            "---",
            "Generado por ValueQuant Terminal.",
        ]
    )

    return "\n".join(lines)


def build_opportunity_briefing_html(
    df_watch: pd.DataFrame,
    df_alerts: pd.DataFrame,
    df_briefing: pd.DataFrame,
    *,
    generated_at: datetime | None = None,
) -> str:
    """Genera un HTML imprimible del briefing semanal."""

    generated_at = generated_at or datetime.now()
    markdown_report = build_opportunity_briefing_markdown(
        df_watch, df_alerts, df_briefing, generated_at=generated_at
    )

    # Conversión ligera de Markdown a HTML controlado para evitar dependencias nuevas.
    html_lines: list[str] = []
    in_table = False
    for raw_line in markdown_report.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            if in_table:
                html_lines.append("</tbody></table>")
                in_table = False
            html_lines.append(f"<h1>{escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_table:
                html_lines.append("</tbody></table>")
                in_table = False
            html_lines.append(f"<h2>{escape(line[3:])}</h2>")
        elif line.startswith("> "):
            html_lines.append(f"<blockquote>{escape(line[2:])}</blockquote>")
        elif line.startswith("- "):
            html_lines.append(f"<p class='bullet'>• {escape(line[2:])}</p>")
        elif line.startswith("| ") and line.endswith(" |"):
            cells = [escape(cell.strip()) for cell in line.strip("|").split("|")]
            if all(cell == "---" for cell in cells):
                continue
            if not in_table:
                html_lines.append("<table><tbody>")
                in_table = True
                html_lines.append("<tr>" + "".join(f"<th>{cell}</th>" for cell in cells) + "</tr>")
            else:
                html_lines.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        elif line.strip() == "":
            if in_table:
                html_lines.append("</tbody></table>")
                in_table = False
            html_lines.append("<br>")
        elif line.startswith("---"):
            html_lines.append("<hr>")
        else:
            safe = escape(line)
            safe = safe.replace("**", "")
            html_lines.append(f"<p>{safe}</p>")
    if in_table:
        html_lines.append("</tbody></table>")

    body = "\n".join(html_lines)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Briefing de Oportunidades - ValueQuant Terminal</title>
  <style>
    :root {{
      --bg: #070a0f;
      --card: #121926;
      --text: #e5edf7;
      --muted: #9aa8bb;
      --accent: #37c6e6;
      --border: rgba(255,255,255,.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 32px;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    .toolbar {{
      position: sticky;
      top: 0;
      display: flex;
      justify-content: flex-end;
      margin-bottom: 24px;
      background: linear-gradient(180deg, var(--bg), rgba(7,10,15,.82));
      padding: 12px 0;
      z-index: 5;
    }}
    button {{
      border: 1px solid rgba(55,198,230,.5);
      background: rgba(55,198,230,.12);
      color: var(--text);
      border-radius: 12px;
      padding: 10px 16px;
      cursor: pointer;
      font-weight: 700;
    }}
    .report {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 2.1rem; margin: 0 0 12px; color: #ffffff; }}
    h2 {{ margin-top: 34px; color: var(--accent); border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
    p, blockquote {{ color: var(--text); }}
    blockquote {{
      margin: 16px 0;
      padding: 14px 18px;
      border-left: 4px solid var(--accent);
      background: rgba(55,198,230,.08);
      border-radius: 10px;
      color: var(--muted);
    }}
    .bullet {{ margin: 6px 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0 22px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      font-size: .92rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ color: #ffffff; background: rgba(255,255,255,.06); }}
    td {{ color: var(--text); }}
    hr {{ border: 0; border-top: 1px solid var(--border); margin: 28px 0; }}
    @media print {{
      body {{ background: white; color: #111827; padding: 0; }}
      .toolbar {{ display: none; }}
      .report {{ max-width: none; }}
      h1 {{ color: #111827; }}
      h2 {{ color: #0f766e; border-bottom: 1px solid #d1d5db; }}
      p, blockquote, td {{ color: #111827; }}
      blockquote {{ background: #f3f4f6; color: #374151; border-left-color: #0f766e; }}
      table {{ background: white; border: 1px solid #d1d5db; page-break-inside: avoid; }}
      th {{ background: #f3f4f6; color: #111827; }}
      th, td {{ border-bottom: 1px solid #e5e7eb; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar"><button onclick="window.print()">Imprimir / Guardar PDF</button></div>
  <main class="report">
    {body}
  </main>
</body>
</html>"""


def _render_export_panel(df_watch: pd.DataFrame, df_alerts: pd.DataFrame, df_briefing: pd.DataFrame) -> None:
    generated_at = datetime.now()
    markdown_report = build_opportunity_briefing_markdown(
        df_watch, df_alerts, df_briefing, generated_at=generated_at
    )
    html_report = build_opportunity_briefing_html(
        df_watch, df_alerts, df_briefing, generated_at=generated_at
    )
    suffix = generated_at.strftime("%Y%m%d_%H%M")

    with st.expander("📤 Exportar briefing semanal", expanded=False):
        st.caption(
            "Descarga un informe de oportunidades para revisión semanal o para enviarlo manualmente por email/Telegram."
        )
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Descargar Markdown",
                data=markdown_report.encode("utf-8"),
                file_name=f"valuequant_opportunity_briefing_{suffix}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Descargar HTML imprimible",
                data=html_report.encode("utf-8"),
                file_name=f"valuequant_opportunity_briefing_{suffix}.html",
                mime="text/html",
                use_container_width=True,
            )
        st.markdown("#### Vista previa")
        st.markdown(markdown_report[:6000])
        if len(markdown_report) > 6000:
            st.caption("Vista previa truncada. El archivo descargado contiene el briefing completo.")

def _render_payload_panel(df_watch: pd.DataFrame, df_alerts: pd.DataFrame, df_briefing: pd.DataFrame) -> None:
    """Panel de preparación de formatos compactos del briefing."""

    payloads = build_briefing_payloads(df_watch, df_alerts, df_briefing)
    suffix = payloads.generated_at.strftime("%Y%m%d_%H%M")

    with st.expander("📨 Preparar briefing para mensajería/email", expanded=False):
        st.caption(
            "Genera versiones compactas del briefing para copiar, revisar o descargar. No envía mensajes automáticamente."
        )

        tab_msg, tab_email, tab_html = st.tabs(["Mensaje compacto", "Email texto", "Email HTML"])

        with tab_msg:
            st.text_area("Vista previa del mensaje compacto", payloads.compact_text, height=360)
            st.download_button(
                "Descargar mensaje compacto",
                data=payloads.compact_text.encode("utf-8"),
                file_name=f"valuequant_briefing_compacto_{suffix}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with tab_email:
            st.text_input("Asunto sugerido", value=payloads.email_subject)
            st.text_area("Vista previa email texto", payloads.email_text, height=360)
            st.download_button(
                "Descargar email texto",
                data=payloads.email_text.encode("utf-8"),
                file_name=f"valuequant_briefing_email_{suffix}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with tab_html:
            st.download_button(
                "Descargar email HTML",
                data=payloads.email_html.encode("utf-8"),
                file_name=f"valuequant_briefing_email_{suffix}.html",
                mime="text/html",
                use_container_width=True,
            )
            st.code(payloads.email_html[:5000], language="html")
            if len(payloads.email_html) > 5000:
                st.caption("Vista previa truncada. El archivo descargado contiene el HTML completo.")

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

    _render_export_panel(df_watch, df_alerts, df_briefing)
    _render_payload_panel(df_watch, df_alerts, df_briefing)

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
