"""Imprime el plan de consolidación de herramientas.

Uso:
    python scripts/print_tool_consolidation_plan.py
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.tool_catalog import TOOL_CATALOG, obtener_catalogo_mvp  # noqa: E402
from modulos.tool_consolidation import CONSOLIDATION_GROUPS, get_consolidation_groups_ordered  # noqa: E402


def main() -> None:
    tools_by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    for tool in TOOL_CATALOG:
        tools_by_group[str(tool.get("consolidation_group", "unassigned"))].append(tool)

    print("=== VALUEQUANT TOOL CONSOLIDATION PLAN ===")
    print(f"Herramientas totales: {len(TOOL_CATALOG)}")
    print(f"Herramientas candidatas MVP: {len(obtener_catalogo_mvp())}")
    print()

    for group in get_consolidation_groups_ordered():
        print(f"[{group.priority}] {group.name} ({group.key})")
        print(f"    Área: {group.strategic_area}")
        print(f"    Target: {group.target_module or 'sin módulo objetivo'}")
        print(f"    {group.description}")

        tools = sorted(
            tools_by_group.get(group.key, []),
            key=lambda item: int(item.get("consolidation_order", 999)),
        )
        for tool in tools:
            mvp = "MVP" if tool.get("visible_in_mvp") else "post-MVP"
            print(
                f"    - {tool['label']} | {tool.get('consolidation_status')} | {mvp}"
            )
        print()

    assigned = {str(tool.get("consolidation_group")) for tool in TOOL_CATALOG}
    unknown = sorted(assigned - set(CONSOLIDATION_GROUPS))
    if unknown:
        print("WARNING: grupos no definidos:", ", ".join(unknown))


if __name__ == "__main__":
    main()
