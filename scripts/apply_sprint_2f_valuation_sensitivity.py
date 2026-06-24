#!/usr/bin/env python3
"""Aplica Sprint 2F: sensibilidad de valoración en Research Core.

Modifica localmente:
- modulos/investment_thesis.py
- modulos/research_report.py

El script es idempotente y crea backups .bak_sprint_2f antes de escribir.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVESTMENT_THESIS = ROOT / "modulos" / "investment_thesis.py"
RESEARCH_REPORT = ROOT / "modulos" / "research_report.py"


def _backup(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak_sprint_2f")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def patch_investment_thesis() -> bool:
    text = INVESTMENT_THESIS.read_text(encoding="utf-8")
    original = text

    import_line = "from modulos.valuation_sensitivity import render_valuation_sensitivity\n"
    if import_line not in text:
        anchor = "import streamlit as st\n"
        if anchor not in text:
            raise RuntimeError("No se encontró el import de Streamlit en investment_thesis.py")
        text = text.replace(anchor, anchor + "\n" + import_line, 1)

    call_line = "        render_valuation_sensitivity(thesis)\n"
    if call_line not in text:
        anchor = "        st.dataframe(_scenario_dataframe(thesis), use_container_width=True, hide_index=True)\n"
        if anchor not in text:
            raise RuntimeError("No se encontró el dataframe de escenarios en investment_thesis.py")
        text = text.replace(anchor, anchor + "\n" + call_line, 1)

    if text != original:
        _backup(INVESTMENT_THESIS)
        INVESTMENT_THESIS.write_text(text, encoding="utf-8")
        return True
    return False


def patch_research_report() -> bool:
    text = RESEARCH_REPORT.read_text(encoding="utf-8")
    original = text

    import_line = "from modulos.valuation_sensitivity import build_valuation_sensitivity, sensitivity_markdown_rows\n"
    if import_line not in text:
        anchor = "from modulos.investment_thesis import build_investment_thesis\n"
        if anchor not in text:
            raise RuntimeError("No se encontró el import de investment_thesis en research_report.py")
        text = text.replace(anchor, anchor + import_line, 1)

    sensitivity_compute = "    sensitivity = build_valuation_sensitivity(thesis)\n    sensitivity_rows = sensitivity_markdown_rows(sensitivity)\n"
    if sensitivity_compute not in text:
        anchor = "    scenario_rows = _valuation_scenario_rows(thesis)\n"
        if anchor not in text:
            raise RuntimeError("No se encontró scenario_rows en research_report.py")
        text = text.replace(anchor, anchor + sensitivity_compute, 1)

    sensitivity_section = '''        "### Sensibilidad crecimiento vs tasa de descuento",
        *(_markdown_table(sensitivity_rows) if sensitivity_rows else ["No hay datos suficientes para construir sensibilidad de valoración."]),
        "",
'''
    if "### Sensibilidad crecimiento vs tasa de descuento" not in text:
        anchor = '''        "### Escenarios de valoración",
        *_markdown_table(scenario_rows),
        "",
'''
        if anchor not in text:
            raise RuntimeError("No se encontró la sección de escenarios de valoración en research_report.py")
        text = text.replace(anchor, anchor + sensitivity_section, 1)

    checklist_line = '            "- Revisar la matriz de sensibilidad y confirmar que la tesis no depende solo del escenario optimista.",'
    if "Revisar la matriz de sensibilidad" not in text:
        anchor = '            "- Revisar supuestos de DCF: crecimiento, márgenes, reinversión y WACC.",'
        if anchor not in text:
            raise RuntimeError("No se encontró la línea de checklist DCF en research_report.py")
        text = text.replace(anchor, anchor + "\n" + checklist_line, 1)

    if text != original:
        _backup(RESEARCH_REPORT)
        RESEARCH_REPORT.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = []
    if patch_investment_thesis():
        changed.append(str(INVESTMENT_THESIS.relative_to(ROOT)))
    if patch_research_report():
        changed.append(str(RESEARCH_REPORT.relative_to(ROOT)))

    if changed:
        print("Sprint 2F aplicado en:")
        for path in changed:
            print(f"- {path}")
        print("Backups creados con sufijo .bak_sprint_2f")
    else:
        print("Sprint 2F ya estaba aplicado. No se hicieron cambios.")


if __name__ == "__main__":
    main()
