"""Sprint 2G — integra comparativa contra competidor en Research Core.

Modifica localmente:
- modulos/research_core.py: añade pestaña "⚖️ Comparativa".
- modulos/research_report.py: añade sección de comparativa relativa al informe.

El script crea backups antes de escribir.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_CORE_PATH = ROOT / "modulos" / "research_core.py"
RESEARCH_REPORT_PATH = ROOT / "modulos" / "research_report.py"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"No se encontró el bloque esperado: {label}")
    return text.replace(old, new, 1)


def patch_research_core() -> bool:
    path = RESEARCH_CORE_PATH
    text = path.read_text(encoding="utf-8")
    original = text

    if "render_relative_comparison" not in text:
        text = _replace_once(
            text,
            "from modulos.research_report import render_research_report_export\n",
            "from modulos.research_report import render_research_report_export\n"
            "from modulos.relative_comparison import render_relative_comparison\n",
            "import relative_comparison",
        )

    if '"⚖️ Comparativa"' not in text:
        text = _replace_once(
            text,
            '            "🧾 Earnings NLP",\n        ]',
            '            "🧾 Earnings NLP",\n            "⚖️ Comparativa",\n        ]',
            "research core tabs",
        )

    if "with tabs[7]:" not in text:
        text = _replace_once(
            text,
            '    with tabs[6]:\n        safe_call("modulos.nlp_analyzer", "render_nlp_dashboard", ticker_input)\n',
            '    with tabs[6]:\n'
            '        safe_call("modulos.nlp_analyzer", "render_nlp_dashboard", ticker_input)\n\n'
            '    with tabs[7]:\n'
            '        render_relative_comparison(\n'
            '            ticker=ticker_input,\n'
            '            competitor=ticker_competidor,\n'
            '            valuequant_score=valuequant_score,\n'
            '            res_val=res_val,\n'
            '            nota_buffett=nota_buffett,\n'
            '        )\n',
            "comparison tab renderer",
        )

    if text == original:
        print("research_core.py ya estaba actualizado.")
        return False

    backup = path.with_suffix(".py.bak_sprint_2g")
    backup.write_text(original, encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    print("Actualizado modulos/research_core.py")
    return True


def patch_research_report() -> bool:
    path = RESEARCH_REPORT_PATH
    text = path.read_text(encoding="utf-8")
    original = text

    if "relative_comparison_markdown_rows" not in text:
        text = _replace_once(
            text,
            "from modulos.valuation_sensitivity import build_valuation_sensitivity, sensitivity_markdown_rows\n",
            "from modulos.valuation_sensitivity import build_valuation_sensitivity, sensitivity_markdown_rows\n"
            "from modulos.relative_comparison import relative_comparison_markdown_rows\n",
            "import relative comparison rows",
        )

    if "relative_rows =" not in text:
        text = _replace_once(
            text,
            "    sensitivity = build_valuation_sensitivity(thesis)\n    sensitivity_rows = sensitivity_markdown_rows(sensitivity)\n    predictive_confidence = _score_attr(valuequant_score, \"predictive_confidence\")\n",
            "    sensitivity = build_valuation_sensitivity(thesis)\n"
            "    sensitivity_rows = sensitivity_markdown_rows(sensitivity)\n"
            "    relative_rows = relative_comparison_markdown_rows(ticker, ticker_competidor, valuequant_score, res_val, nota_buffett)\n"
            "    predictive_confidence = _score_attr(valuequant_score, \"predictive_confidence\")\n",
            "relative rows build",
        )

    if "## 2. Comparativa relativa" not in text:
        text = _replace_once(
            text,
            '        "",\n        "## 2. Valoración y margen de seguridad",\n',
            '        "",\n'
            '        "## 2. Comparativa relativa",\n'
            '        *(_markdown_table(relative_rows) if relative_rows else ["No hay competidor configurado o datos suficientes para comparación relativa."]),\n'
            '        "",\n'
            '        "## 3. Valoración y margen de seguridad",\n',
            "relative comparison report section",
        )

        replacements = {
            '"## 3. Desglose ValueQuant Score"': '"## 4. Desglose ValueQuant Score"',
            '"## 4. Snapshot financiero"': '"## 5. Snapshot financiero"',
            '"## 5. Tesis de inversión"': '"## 6. Tesis de inversión"',
            '["## 6. Banderas rojas", ""]': '["## 7. Banderas rojas", ""]',
            '"## 7. Checklist antes de decidir"': '"## 8. Checklist antes de decidir"',
            '"## 8. Limitaciones"': '"## 9. Limitaciones"',
        }
        for old, new in replacements.items():
            text = text.replace(old, new, 1)

    if text == original:
        print("research_report.py ya estaba actualizado.")
        return False

    backup = path.with_suffix(".py.bak_sprint_2g")
    backup.write_text(original, encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    print("Actualizado modulos/research_report.py")
    return True


def main() -> None:
    changed_core = patch_research_core()
    changed_report = patch_research_report()
    if changed_core or changed_report:
        print("Sprint 2G aplicado. Ejecuta py_compile antes de abrir Streamlit.")
    else:
        print("No había cambios pendientes del Sprint 2G.")


if __name__ == "__main__":
    main()
