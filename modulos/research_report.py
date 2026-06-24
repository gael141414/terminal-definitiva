"""Generador de informes para Research Core.

Este módulo convierte la tesis de inversión, los scores y los outputs financieros
principales en un informe descargable en Markdown y HTML. La salida está pensada
para revisión humana: no constituye asesoramiento financiero personalizado.
"""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from modulos.investment_thesis import build_investment_thesis, thesis_to_markdown


DISCLAIMER = (
    "Documento generado automáticamente por ValueQuant Terminal. "
    "No constituye asesoramiento financiero personalizado ni recomendación "
    "individualizada de compra o venta."
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


def _extract_ratios(resultado: dict[str, Any] | None) -> pd.DataFrame | None:
    if not isinstance(resultado, dict):
        return None
    return _safe_dataframe(resultado.get("ratios")) or _safe_dataframe(resultado.get("data"))


def _financial_snapshot(
    res_is: dict[str, Any] | None,
    res_bs: dict[str, Any] | None,
    res_cf: dict[str, Any] | None,
) -> list[dict[str, str]]:
    is_ratios = _extract_ratios(res_is)
    bs_ratios = _extract_ratios(res_bs)
    cf_ratios = _extract_ratios(res_cf)

    metrics = [
        (
            "Margen neto",
            _latest_available_value(is_ratios, ["Margen Neto", "Net Margin", "net_margin"]),
            "pct",
        ),
        (
            "Margen bruto",
            _latest_available_value(is_ratios, ["Margen Bruto", "Gross Margin", "gross_margin"]),
            "pct",
        ),
        (
            "ROE",
            _latest_available_value(bs_ratios, ["ROE", "Return on Equity", "roe"]),
            "pct",
        ),
        (
            "ROIC",
            _latest_available_value(bs_ratios, ["ROIC", "roic"]),
            "pct",
        ),
        (
            "Deuda/Capital",
            _latest_available_value(bs_ratios, ["Deuda/Capital", "Debt/Equity", "Debt to Equity", "debt_to_equity"]),
            "x",
        ),
        (
            "FCF",
            _latest_available_value(cf_ratios, ["FCF", "Free Cash Flow", "free_cash_flow"]),
            "money",
        ),
        (
            "CAPEX/OCF",
            _latest_available_value(cf_ratios, ["CAPEX/OCF", "Capex/OCF", "capex_ocf"]),
            "pct",
        ),
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
        f"- **Confianza predictiva:** {_fmt_pct(_score_attr(valuequant_score, 'predictive_confidence')) if _score_attr(valuequant_score, 'predictive_confidence') is not None else 'Pendiente de backtesting'}",
        "",
        "## 2. Valoración y zona de entrada",
        f"- **Precio actual:** {_fmt_money(thesis.current_price)}",
        f"- **Valor intrínseco / razonable:** {_fmt_money(thesis.intrinsic_value)}",
        f"- **Margen de seguridad:** {_fmt_pct(thesis.margin_of_safety)}",
        f"- **Zona razonable de entrada:** {_fmt_money(thesis.reasonable_entry_price)}",
        f"- **Zona conservadora de entrada:** {_fmt_money(thesis.conservative_entry_price)}",
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
            "- Comparar múltiplos y calidad con competidores directos.",
            "- Revisar deuda, recompras, dilución y vencimientos relevantes.",
            "- Confirmar que no hay eventos corporativos o noticias recientes no incorporadas.",
            "",
            "## 8. Limitaciones",
            "- El score todavía requiere validación histórica formal.",
            "- La confianza predictiva debe interpretarse como pendiente si no hay backtesting suficiente.",
            "- El informe no sustituye análisis financiero profesional ni valoración independiente.",
            "",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def research_report_to_html(markdown: str, ticker: str) -> str:
    """Convierte el informe Markdown a una plantilla HTML sencilla y portable."""

    escaped_lines = [escape(line) for line in markdown.splitlines()]
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
            body_lines.append("<br>")
            continue
        if raw.startswith("# "):
            close_blocks()
            body_lines.append(f"<h1>{raw[2:]}</h1>")
        elif raw.startswith("## "):
            close_blocks()
            body_lines.append(f"<h2>{raw[3:]}</h2>")
        elif raw.startswith("### "):
            close_blocks()
            body_lines.append(f"<h3>{raw[4:]}</h3>")
        elif raw.startswith("&gt; "):
            close_blocks()
            body_lines.append(f"<blockquote>{raw[5:]}</blockquote>")
        elif raw.startswith("- "):
            if not in_ul:
                body_lines.append("<ul>")
                in_ul = True
            body_lines.append(f"<li>{raw[2:]}</li>")
        elif raw.startswith("| ") and raw.endswith(" |"):
            if "---" in raw:
                continue
            cells = [cell.strip() for cell in raw.strip("|").split("|")]
            if not in_table:
                close_blocks()
                body_lines.append("<table>")
                in_table = True
                body_lines.append("<tr>" + "".join(f"<th>{cell}</th>" for cell in cells) + "</tr>")
            else:
                body_lines.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        else:
            close_blocks()
            body_lines.append(f"<p>{raw}</p>")

    close_blocks()

    return f"""<!doctype html>
<html lang=\"es\">
<head>
  <meta charset=\"utf-8\">
  <title>Informe Research Core - {escape(ticker)}</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; background: #0b1020; color: #e5e7eb; margin: 0; padding: 40px; }}
    main {{ max-width: 980px; margin: 0 auto; background: #111827; border: 1px solid #243047; border-radius: 18px; padding: 34px; }}
    h1 {{ color: #f8fafc; border-bottom: 1px solid #334155; padding-bottom: 14px; }}
    h2 {{ color: #93c5fd; margin-top: 34px; }}
    h3 {{ color: #c4b5fd; }}
    blockquote {{ border-left: 4px solid #38bdf8; padding: 10px 16px; background: rgba(56, 189, 248, 0.08); color: #cbd5e1; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    th, td {{ border: 1px solid #334155; padding: 10px; text-align: left; }}
    th {{ background: #1e293b; }}
    li {{ margin: 7px 0; }}
    .footer {{ margin-top: 42px; color: #94a3b8; font-size: 12px; }}
  </style>
</head>
<body>
  <main>
    {''.join(body_lines)}
    <div class=\"footer\">Generado por ValueQuant Terminal.</div>
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
        "Informe completo en Markdown y HTML con tesis, valoración, score, snapshot financiero, "
        "riesgos y checklist de revisión."
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
            "Descargar informe HTML",
            data=html,
            file_name=f"research_core_{ticker.lower()}.html",
            mime="text/html",
        )

    preview_mode = st.radio("Vista previa", ["Markdown", "HTML fuente"], horizontal=True)
    if preview_mode == "Markdown":
        st.markdown(markdown)
    else:
        st.code(html, language="html")
