"""Aplica Sprint 2I: veredicto relativo final en Research Core.

Modifica `modulos/relative_comparison.py` para:
- importar el motor `relative_decision`;
- mostrar un panel ejecutivo de preferencia relativa;
- insertar el veredicto relativo en las filas Markdown del informe.

El script es idempotente y crea backup antes de escribir.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_COMPARISON_PATH = ROOT / "modulos" / "relative_comparison.py"
BACKUP_PATH = ROOT / "modulos" / "relative_comparison.py.bak_sprint_2i"

IMPORT_SNIPPET = "from modulos.utils import calcular_score_buffett, cargar_datos\n"
IMPORT_REPLACEMENT = (
    "from modulos.utils import calcular_score_buffett, cargar_datos\n"
    "from modulos.relative_decision import (\n"
    "    build_relative_decision,\n"
    "    relative_decision_table_rows,\n"
    "    render_relative_decision_panel,\n"
    ")\n"
)

MARKDOWN_OLD = '''    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    rows = comparison.verdict_rows + comparison.component_rows[:4] + comparison.metric_rows[:10]
    return _normalize_rows_for_report(rows, primary_label, competitor_label)[:20]
'''

MARKDOWN_NEW = '''    primary_label = comparison.primary.ticker
    competitor_label = comparison.competitor.ticker
    decision = build_relative_decision(comparison, valuequant_score, res_val, nota_buffett)
    decision_rows = relative_decision_table_rows(decision, primary_label, competitor_label)
    rows = comparison.verdict_rows + comparison.component_rows[:4] + comparison.metric_rows[:10]
    return (decision_rows + _normalize_rows_for_report(rows, primary_label, competitor_label))[:24]
'''

RENDER_OLD = '''    c1.metric(f"{primary_label} VQ", _fmt_score(_score_attr(valuequant_score, "final_score")))
    c2.metric(f"{competitor_label} VQ", _fmt_score(_score_attr(competitor_vq, "final_score")))
    c3.metric(f"{primary_label} FCF Yield", _fmt_pct(comparison.primary.fcf_yield))
    c4.metric(f"{competitor_label} FCF Yield", _fmt_pct(comparison.competitor.fcf_yield))

    if comparison.competitor_score and comparison.competitor_score.error:
'''

RENDER_NEW = '''    c1.metric(f"{primary_label} VQ", _fmt_score(_score_attr(valuequant_score, "final_score")))
    c2.metric(f"{competitor_label} VQ", _fmt_score(_score_attr(competitor_vq, "final_score")))
    c3.metric(f"{primary_label} FCF Yield", _fmt_pct(comparison.primary.fcf_yield))
    c4.metric(f"{competitor_label} FCF Yield", _fmt_pct(comparison.competitor.fcf_yield))

    decision = build_relative_decision(comparison, valuequant_score, res_val, nota_buffett)
    render_relative_decision_panel(decision)

    if comparison.competitor_score and comparison.competitor_score.error:
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"OK: {label} ya estaba aplicado.")
        return text
    if old not in text:
        raise RuntimeError(f"No se encontró el bloque esperado para: {label}")
    return text.replace(old, new, 1)


def main() -> None:
    if not RELATIVE_COMPARISON_PATH.exists():
        raise FileNotFoundError(f"No existe {RELATIVE_COMPARISON_PATH}")

    original = RELATIVE_COMPARISON_PATH.read_text(encoding="utf-8")
    updated = original

    updated = replace_once(updated, IMPORT_SNIPPET, IMPORT_REPLACEMENT, "import relative_decision")
    updated = replace_once(updated, MARKDOWN_OLD, MARKDOWN_NEW, "filas Markdown del informe")
    updated = replace_once(updated, RENDER_OLD, RENDER_NEW, "panel ejecutivo en UI")

    if updated == original:
        print("Sin cambios: Sprint 2I ya estaba aplicado.")
        return

    if not BACKUP_PATH.exists():
        BACKUP_PATH.write_text(original, encoding="utf-8")
        print(f"Backup creado: {BACKUP_PATH.relative_to(ROOT)}")

    RELATIVE_COMPARISON_PATH.write_text(updated, encoding="utf-8")
    print("Sprint 2I aplicado correctamente sobre modulos/relative_comparison.py")


if __name__ == "__main__":
    main()
