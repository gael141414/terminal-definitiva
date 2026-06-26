"""Sprint 2L: registra el Briefing de Oportunidades en catálogo y router.

Ejecutar desde la raíz del proyecto:
    python scripts/apply_sprint_2l_opportunity_briefing.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_CATALOG = ROOT / "modulos" / "tool_catalog.py"
TOOL_CONSOLIDATION = ROOT / "modulos" / "tool_consolidation.py"
TOOL_ROUTER = ROOT / "modulos" / "tool_router.py"

BRIEFING_LABEL = "📌 Briefing de Oportunidades"


def _backup(path: Path, suffix: str) -> None:
    backup = path.with_suffix(path.suffix + suffix)
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def patch_tool_catalog() -> bool:
    text = TOOL_CATALOG.read_text(encoding="utf-8")
    if BRIEFING_LABEL in text:
        return False

    needle = '    {"label": "📋 Mi Watchlist (Cartera)", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Seguimiento de cartera y prioridades de análisis.", "strategic_group": "portfolio"},\n'
    insert = needle + '    {"label": "📌 Briefing de Oportunidades", "bloque": "💼 Cartera y Decisión", "input_mode": "standalone", "descripcion": "Vista ejecutiva de oportunidades: revisar hoy, vigilar caída, recalcular y descartar.", "strategic_group": "portfolio"},\n'

    if needle not in text:
        raise RuntimeError("No se encontró el punto de inserción en modulos/tool_catalog.py")

    _backup(TOOL_CATALOG, ".bak_sprint_2l")
    TOOL_CATALOG.write_text(text.replace(needle, insert), encoding="utf-8")
    return True


def patch_tool_consolidation() -> bool:
    text = TOOL_CONSOLIDATION.read_text(encoding="utf-8")
    if BRIEFING_LABEL in text:
        return False

    needle = '    "📋 Mi Watchlist (Cartera)": {"group": "portfolio_decision", "status": "core", "order": 10, "visible_in_mvp": True},\n'
    insert = needle + '    "📌 Briefing de Oportunidades": {"group": "portfolio_decision", "status": "core", "order": 15, "visible_in_mvp": True},\n'

    if needle not in text:
        raise RuntimeError("No se encontró el punto de inserción en modulos/tool_consolidation.py")

    _backup(TOOL_CONSOLIDATION, ".bak_sprint_2l")
    TOOL_CONSOLIDATION.write_text(text.replace(needle, insert), encoding="utf-8")
    return True


def patch_tool_router() -> bool:
    text = TOOL_ROUTER.read_text(encoding="utf-8")
    if BRIEFING_LABEL in text:
        return False

    needle = '    "📋 Mi Watchlist (Cartera)": ("modulos.watchlist", "ejecutar_watchlist"),\n'
    insert = needle + '    "📌 Briefing de Oportunidades": ("modulos.opportunity_briefing", "render_opportunity_briefing"),\n'

    if needle not in text:
        raise RuntimeError("No se encontró el punto de inserción en modulos/tool_router.py")

    _backup(TOOL_ROUTER, ".bak_sprint_2l")
    TOOL_ROUTER.write_text(text.replace(needle, insert), encoding="utf-8")
    return True


def main() -> None:
    changed = {
        "tool_catalog.py": patch_tool_catalog(),
        "tool_consolidation.py": patch_tool_consolidation(),
        "tool_router.py": patch_tool_router(),
    }

    if any(changed.values()):
        print("Sprint 2L aplicado correctamente:")
        for filename, did_change in changed.items():
            status = "modificado" if did_change else "sin cambios"
            print(f"- {filename}: {status}")
    else:
        print("Sprint 2L ya estaba aplicado. No se realizaron cambios.")


if __name__ == "__main__":
    main()
