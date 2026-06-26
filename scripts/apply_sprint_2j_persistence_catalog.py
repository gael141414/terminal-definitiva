"""Sprint 2J: registra herramientas de persistencia en catálogo/consolidación.

Ejecutar desde la raíz del proyecto:
    python scripts/apply_sprint_2j_persistence_catalog.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_CATALOG = ROOT / "modulos" / "tool_catalog.py"
TOOL_CONSOLIDATION = ROOT / "modulos" / "tool_consolidation.py"


def patch_file(path: Path, replacements: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in replacements:
        if new in text:
            continue
        if old not in text:
            raise RuntimeError(f"No se encontró el anclaje esperado en {path}: {old[:80]!r}")
        text = text.replace(old, new)
    if text != original:
        backup = path.with_suffix(path.suffix + ".bak_sprint_2j")
        backup.write_text(original, encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    catalog_old = '    {"label": "📋 Mi Watchlist (Cartera)", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Seguimiento de cartera y prioridades de análisis.", "strategic_group": "portfolio"},\n'
    catalog_new = catalog_old + '    {"label": "📚 Análisis Guardados", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Histórico de snapshots guardados desde Research Core.", "strategic_group": "portfolio"},\n'

    consolidation_old = '    "📋 Mi Watchlist (Cartera)": {"group": "portfolio_decision", "status": "core", "order": 10, "visible_in_mvp": True},\n'
    consolidation_new = consolidation_old + '    "📚 Análisis Guardados": {"group": "portfolio_decision", "status": "core", "order": 15, "visible_in_mvp": True},\n'

    changed_catalog = patch_file(TOOL_CATALOG, [(catalog_old, catalog_new)])
    changed_consolidation = patch_file(TOOL_CONSOLIDATION, [(consolidation_old, consolidation_new)])

    print("Sprint 2J aplicado.")
    print(f"- tool_catalog.py cambiado: {changed_catalog}")
    print(f"- tool_consolidation.py cambiado: {changed_consolidation}")


if __name__ == "__main__":
    main()
