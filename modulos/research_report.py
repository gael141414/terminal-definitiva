"""Generador de informes para Research Core.

Convierte la tesis de inversión, los scores y los outputs financieros principales
en un informe descargable en Markdown y HTML. La salida está pensada para
revisión humana: no constituye asesoramiento financiero personalizado.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modulos.investment_thesis import build_investment_thesis


DISCLAIMER = (
    "Documento generado automáticamente por ValueQuant Terminal. "
    "No constituye asesoramiento financiero personalizado ni recomendación "
    "individualizada de compra o venta."
)

PRINT_EXPORT_HELP = (
    "Para generar PDF: descarga el HTML, ábrelo en el navegador y usa Ctrl+P "
    "→ Guardar como PDF. El HTML ya incluye estilos específicos de impresión."
)


def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
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


def _fmt_ratio(value: Any) -> str:
    number = _as_float(value)
    return f"{number:.1f}x" if number is not None else "N/D"


def _score_attr(valuequant_score: Any, attr: str, default: Any = None) -> Any:
    if valuequant_score is None:
        return default
    return getattr(valuequant_score, attr, default)


def _component_rows(valuequant_score: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for component in _score_attr(valuequant_score, "components", []) or []:
        rows.append(
            {
                "Componente": getattr(component, "name", "N/D"),
                "Score": _fmt_score(getattr(component, "score", None)),
                "Peso": _fmt_pct(getattr(component, "weight", None)),
                "Comentario": getattr(component, "comment", ""),
            }
        )
    return rows


def _safe_dataframe(value: Any) -> pd.DataFrame | None:
    if isinstance(value, pd.DataFrame) and not value.empty:
        return value
    return None


def _extract_ratios(resultado: dict[str, Any] | None) -> pd.DataFrame | None:
    """Extrae un DataFrame de ratios sin evaluar DataFrames en contexto booleano."""

    if not isinstance(resultado, dict):
        return None
    for key in ("ratios", "data", "df", "metrics"):
        df = _safe_dataframe(resultado.get(key))
        if df is not None:
            return df
    return None


def _latest_available_value(df: pd.DataFrame | None, candidates: list[str]) -> Any:
    if df is None or df.empty:
        return None

    for candidate in candidates:
        if candidate in df.columns:
            series = df[candidate].dropna()
            if not series.empty:
                return series.iloc[-1]

    lower_map = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        col = lower_map.get(candidate.lower())
        if col is not None:
            series = df[col].dropna()
            if not series.empty:
                return series.iloc[-1]
    return None


def _financial_snapshot(
    res_is: dict[str, Any] | None,
    res_bs: dict[str, Any] | None,
    res_cf: dict[str, Any] | None,
) -> list[dict[str, str]]:
    is_ratios = _extract_ratios(res_is)
    bs_ratios = _extract_ratios(res_bs)
    cf_ratios = _extract_ratios(res_cf)

    metrics = [
        ("Margen neto", _latest_available_value(is_ratios, ["Margen Neto", "Net Margin", "net_margin"]), "pct"),
        ("Margen bruto", _latest_available_value(is_ratios, ["Margen Bruto", "Gross Margin", "gross_margin"]), "pct"),
        ("ROE", _latest_available_value(bs_ratios, ["ROE", "Return on Equity", "roe"]), "pct"),
        ("ROIC", _latest_available_value(bs_ratios, ["ROIC", "roic"]), "pct"),
        (
            "Deuda/Capital",
            _latest_available_value(bs_ratios, ["Deuda/Capital", "Debt/Equity", "Debt to Equity", "debt_to_equity"]),
            "x",
        ),
        ("FCF", _latest_available_value(cf_ratios, ["FCF", "Free Cash Flow", "free_cash_flow"]), "money"),
        ("CAPEX/OCF", _latest_available_value(cf_ratios, ["CAPEX/OCF", "Capex/OCF", "capex_ocf"]), "pct"),
    ]

    rows: list[dict[str, str]] = []
    for name, value, kind in metrics:
        if kind == "pct":
            formatted = _fmt_pct(value)
        elif kind == "money":
            formatted = _fmt_money(value)
        elif kind == "x":
            number = _as_float(value)
            formatted = f"{number:.2f}x" if number is not None else "N/D"
        else:
            formatted = str(value) if value is not None else "N/D"
        rows.append({"Métrica": name, "Último dato": formatted})
    return rows


def _markdown_table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["N/D"]
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")
    return lines


def _valuation_scenario_rows(thesis: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    current_price = thesis.current_price
    for scenario in thesis.valuation_scenarios:
        if current_price and current_price > 0 and scenario.price:
            upside = scenario.price / current_price - 1.0
        else:
            upside = None
        rows.append(
            {
                "Escenario": scenario.name,
                "Precio/valor": _fmt_money(scenario.price),
                "Potencial vs actual": _fmt_pct(upside),
                "Lectura": scenario.description,
            }
        )
    return rows


def build_research_report_markdown(
    ticker: str,
    ticker_competidor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    res_is: dict[str, Any] | None,
    res_bs: dict[str, Any] | None,
    res_cf: dict[str, Any] | None,
) -> str:
    """Construye un informe completo en Markdown."""

    thesis = build_investment_thesis(ticker, valuequant_score, res_val, nota_buffett)
    component_rows = _component_rows(valuequant_score)
    financial_rows = _financial_snapshot(res_is, res_bs, res_cf)
    scenario_rows = _valuation_scenario_rows(thesis)
    predictive_confidence = _score_attr(valuequant_score, "predictive_confidence")

    lines: list[str] = [
        f"# Informe Research Core — {ticker}",
        "",
        f"> {DISCLAIMER}",
        "",
        "## 1. Resumen ejecutivo",
        f"- **Acción operativa:** {thesis.action}",
        f"- **Detalle:** {thesis.action_detail}",
        f"- **Comparador:** {ticker_competidor or 'N/D'}",
        f"- **Modelo:** {_score_attr(valuequant_score, 'model_version', 'N/D')}",
        f"- **ValueQuant Score:** {_fmt_score(thesis.final_score)}",
        f"- **Buffett Quality:** {_fmt_score(thesis.buffett_score)}",
        f"- **Cobertura de datos:** {_fmt_pct(_score_attr(valuequant_score, 'data_coverage'))}",
        f"- **Confianza operativa:** {_fmt_pct(_score_attr(valuequant_score, 'confidence'))}",
        f"- **Confianza predictiva:** {_fmt_pct(predictive_confidence) if predictive_confidence is not None else 'Pendiente de backtesting'}",
        "",
        "## 2. Valoración y margen de seguridad",
        f"- **Precio actual:** {_fmt_money(thesis.current_price)}",
        f"- **Valor intrínseco / razonable:** {_fmt_money(thesis.intrinsic_value)}",
        f"- **Margen de seguridad:** {_fmt_pct(thesis.margin_of_safety)}",
        f"- **Régimen de valoración:** {thesis.valuation_regime}",
        f"- **Lectura:** {thesis.valuation_comment}",
        f"- **FCF Yield:** {_fmt_pct(thesis.fcf_yield)}",
        f"- **Earnings Yield:** {_fmt_pct(thesis.earnings_yield)}",
        f"- **PER:** {_fmt_ratio(thesis.pe_actual)}",
        f"- **P/FCF:** {_fmt_ratio(thesis.pfcf_actual)}",
        f"- **Zona razonable de entrada:** {_fmt_money(thesis.reasonable_entry_price)}",
        f"- **Zona conservadora de entrada:** {_fmt_money(thesis.conservative_entry_price)}",
        f"- **Zona de oportunidad fuerte:** {_fmt_money(thesis.deep_value_entry_price)}",
        "",
        "### Escenarios de valoración",
        *_markdown_table(scenario_rows),
        "",
        "## 3. Desglose ValueQuant Score",
        *_markdown_table(component_rows),
        "",
        "## 4. Snapshot financiero",
        *_markdown_table(financial_rows),
        "",
        "## 5. Tesis de inversión",
    ]

    for section in thesis.sections:
        lines.append(f"### {section.title}")
        for bullet in section.bullets:
            lines.append(f"- {bullet}")
        lines.append("")

    if thesis.red_flags:
        lines.extend(["## 6. Banderas rojas", ""])
        for flag in thesis.red_flags:
            lines.append(f"- {flag}")
        lines.append("")

    lines.extend(
        [
            "## 7. Checklist antes de decidir",
            "- Validar manualmente los datos financieros descargados.",
            "- Revisar supuestos de DCF: crecimiento, márgenes, reinversión y WACC.",
            "- Comparar múltiplos, FCF Yield y calidad con competidores directos.",
            "- Verificar si el margen de seguridad procede de supuestos prudentes o de crecimiento agresivo.",
            "- Revisar deuda, recompras, dilución y vencimientos relevantes.",
            "- Confirmar que no hay eventos corporativos o noticias recientes no incorporadas.",
            "",
            "## 8. Limitaciones",
            "- El score todavía requiere validación histórica formal.",
            "- La confianza predictiva debe interpretarse como pendiente si no hay backtesting suficiente.",
            "- La valoración depende de supuestos sensibles: crecimiento, WACC, márgenes, reinversión y múltiplos terminales.",
            "- El informe no sustituye análisis financiero profesional ni valoración independiente.",
            "",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def _inline_markdown_to_html(text: str) -> str:
    """Convierte un subconjunto muy pequeño de Markdown inline a HTML seguro."""

    escaped = escape(text)
    parts = escaped.split("**")
    if len(parts) == 1:
        return escaped

    rendered: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            rendered.append(f"<strong>{part}</strong>")
        else:
            rendered.append(part)
    return "".join(rendered)


def _markdown_body_to_html(markdown: str) -> str:
    escaped_lines = markdown.splitlines()
    body_lines: list[str] = []
    in_ul = False
    in_table = False

    def close_blocks() -> None:
        nonlocal in_ul, in_table
        if in_ul:
            body_lines.append("</ul>")
            in_ul = False
        if in_table:
            body_lines.append("</table>")
            in_table = False

    for line in escaped_lines:
        raw = line.strip()
        if not raw:
            close_blocks()
            body_lines.append('<div class="spacer"></div>')
        elif raw.startswith("# "):
            close_blocks()
            body_lines.append(f"<h1>{_inline_markdown_to_html(raw[2:])}</h1>")
        elif raw.startswith("## "):
            close_blocks()
            body_lines.append(f"<h2>{_inline_markdown_to_html(raw[3:])}</h2>")
        elif raw.startswith("### "):
            close_blocks()
            body_lines.append(f"<h3>{_inline_markdown_to_html(raw[4:])}</h3>")
        elif raw.startswith("> "):
            close_blocks()
            body_lines.append(f"<blockquote>{_inline_markdown_to_html(raw[2:])}</blockquote>")
        elif raw.startswith("- "):
            if not in_ul:
                close_blocks()
                body_lines.append("<ul>")
                in_ul = True
            body_lines.append(f"<li>{_inline_markdown_to_html(raw[2:])}</li>")
        elif raw.startswith("| ") and raw.endswith(" |"):
            if "---" in raw:
                continue
            cells = [cell.strip() for cell in raw.strip("|").split("|")]
            if not in_table:
                close_blocks()
                body_lines.append("<table>")
                in_table = True
                body_lines.append("<tr>" + "".join(f"<th>{_inline_markdown_to_html(cell)}</th>" for cell in cells) + "</tr>")
            else:
                body_lines.append("<tr>" + "".join(f"<td>{_inline_markdown_to_html(cell)}</td>" for cell in cells) + "</tr>")
        else:
            close_blocks()
            body_lines.append(f"<p>{_inline_markdown_to_html(raw)}</p>")

    close_blocks()
    return "\n".join(body_lines)


def research_report_to_html(markdown: str, ticker: str) -> str:
    """Convierte el informe Markdown a HTML imprimible y portable."""

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    body_html = _markdown_body_to_html(markdown)
    title = f"Informe Research Core - {escape(ticker)}"

    return f"""<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #111827;
      --panel-2: #162033;
      --border: #243047;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-2: #93c5fd;
      --violet: #c4b5fd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: Inter, Arial, sans-serif;
      background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.13), transparent 28%), var(--bg);
      color: var(--text);
      margin: 0;
      padding: 36px;
      line-height: 1.55;
    }}
    .toolbar {{
      max-width: 1020px;
      margin: 0 auto 16px auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .print-button {{
      border: 1px solid var(--border);
      background: var(--panel-2);
      color: var(--text);
      border-radius: 10px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 700;
    }}
    .print-button:hover {{ border-color: var(--accent); }}
    main {{
      max-width: 1020px;
      margin: 0 auto;
      background: rgba(17, 24, 39, 0.96);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 40px;
      box-shadow: 0 28px 80px rgba(0, 0, 0, 0.35);
    }}
    h1 {{
      color: #f8fafc;
      border-bottom: 1px solid #334155;
      padding-bottom: 16px;
      margin-top: 0;
      letter-spacing: -0.03em;
    }}
    h2 {{ color: var(--accent-2); margin-top: 36px; padding-top: 8px; break-after: avoid; }}
    h3 {{ color: var(--violet); break-after: avoid; }}
    blockquote {{
      border-left: 4px solid var(--accent);
      padding: 12px 18px;
      background: rgba(56, 189, 248, 0.08);
      color: #cbd5e1;
      margin: 18px 0;
      border-radius: 0 12px 12px 0;
    }}
    table {{ width: 100%; border-collapse: collapse; margin: 18px 0; page-break-inside: avoid; }}
    th, td {{ border: 1px solid #334155; padding: 10px; text-align: left; vertical-align: top; }}
    th {{ background: #1e293b; color: #f8fafc; }}
    tr:nth-child(even) td {{ background: rgba(30, 41, 59, 0.38); }}
    ul {{ padding-left: 22px; }}
    li {{ margin: 7px 0; }}
    strong {{ color: #f8fafc; }}
    .spacer {{ height: 8px; }}
    .footer {{ margin-top: 42px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); padding-top: 14px; }}

    @page {{ size: A4; margin: 16mm 14mm; }}

    @media print {{
      body {{ background: #ffffff !important; color: #111827 !important; padding: 0; font-size: 11pt; }}
      .toolbar {{ display: none !important; }}
      main {{ max-width: none; border: none; box-shadow: none; border-radius: 0; padding: 0; background: #ffffff !important; }}
      h1 {{ color: #111827 !important; border-bottom: 1px solid #cbd5e1; }}
      h2 {{ color: #1d4ed8 !important; page-break-after: avoid; }}
      h3 {{ color: #334155 !important; page-break-after: avoid; }}
      blockquote {{ background: #f8fafc !important; color: #334155 !important; border-left-color: #0284c7; }}
      th {{ background: #e5e7eb !important; color: #111827 !important; }}
      td, th {{ border-color: #cbd5e1 !important; }}
      tr:nth-child(even) td {{ background: #f8fafc !important; }}
      a {{ color: #111827 !important; text-decoration: none; }}
      .footer {{ color: #64748b !important; }}
    }}
  </style>
</head>
<body>
  <div class=\"toolbar\">
    <div><strong>ValueQuant Terminal</strong> · {escape(ticker)} · generado {generated_at}</div>
    <button class=\"print-button\" onclick=\"window.print()\">Imprimir / Guardar PDF</button>
  </div>
  <main>
    {body_html}
    <div class=\"footer\">Generado por ValueQuant Terminal. {escape(PRINT_EXPORT_HELP)}</div>
  </main>
</body>
</html>
"""


def render_research_report_export(
    ticker: str,
    ticker_competidor: str | None,
    valuequant_score: Any,
    res_val: dict[str, Any] | None,
    nota_buffett: float | None,
    res_is: dict[str, Any] | None,
    res_bs: dict[str, Any] | None,
    res_cf: dict[str, Any] | None,
) -> None:
    """Renderiza la pestaña de informe descargable dentro de Research Core."""

    st.markdown("### Informe Research Core")
    st.caption(
        "Informe completo en Markdown y HTML imprimible con tesis, escenarios de valoración, margen de seguridad, "
        "score, snapshot financiero, riesgos y checklist de revisión."
    )

    markdown = build_research_report_markdown(
        ticker=ticker,
        ticker_competidor=ticker_competidor,
        valuequant_score=valuequant_score,
        res_val=res_val,
        nota_buffett=nota_buffett,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
    )
    html = research_report_to_html(markdown, ticker)

    st.info(PRINT_EXPORT_HELP)

    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "Descargar informe Markdown",
            data=markdown,
            file_name=f"research_core_{ticker.lower()}.md",
            mime="text/markdown",
        )
    with col_b:
        st.download_button(
            "Descargar HTML imprimible",
            data=html,
            file_name=f"research_core_{ticker.lower()}_print.html",
            mime="text/html",
        )

    preview_mode = st.radio("Vista previa", ["HTML renderizado", "Markdown", "HTML fuente"], horizontal=True)
    if preview_mode == "HTML renderizado":
        components.html(html, height=820, scrolling=True)
    elif preview_mode == "Markdown":
        st.markdown(markdown)
    else:
        st.code(html, language="html")
