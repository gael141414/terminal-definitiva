"""Aplica el Sprint 1D sobre app.py.

Objetivo:
- Retirar el TOOL_CATALOG embebido de app.py.
- Usar modulos.tool_catalog como fuente única de navegación.

Uso desde la raíz del proyecto:
    python scripts/apply_sprint_1d_tool_catalog.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"

IMPORT_LINE = (
    "from modulos.tool_catalog import (\n"
    "    TOOL_CATALOG,\n"
    "    BLOQUES_HERRAMIENTAS,\n"
    "    HERRAMIENTAS_POR_LABEL,\n"
    "    obtener_herramientas_por_bloque,\n"
    ")\n"
)

BLOCK_START = "TOOL_CATALOG = [\n"
BLOCK_END = "\ndef ultimo_ratio(resultado, columna):\n"


def main() -> None:
    if not APP_PATH.exists():
        raise FileNotFoundError(f"No se encontró app.py en {APP_PATH}")

    content = APP_PATH.read_text(encoding="utf-8")
    original = content

    if IMPORT_LINE not in content:
        anchor = "from modulos.ui_components import render_kpi_card\n"
        if anchor not in content:
            raise RuntimeError("No se encontró el import de ui_components; revisa app.py antes de aplicar Sprint 1D.")
        content = content.replace(anchor, anchor + IMPORT_LINE)

    if BLOCK_START in content and BLOCK_END in content:
        start = content.index(BLOCK_START)
        end = content.index(BLOCK_END)
        content = content[:start] + content[end + 1:]
    elif "from modulos.tool_catalog import" in content:
        print("TOOL_CATALOG embebido no encontrado. Puede que app.py ya esté migrado.")
    else:
        raise RuntimeError("No se pudo localizar el bloque TOOL_CATALOG en app.py.")

    if content == original:
        print("No se aplicaron cambios. Puede que app.py ya estuviera migrado.")
    else:
        APP_PATH.write_text(content, encoding="utf-8")
        print("OK: app.py usa modulos.tool_catalog como fuente única del catálogo.")

    forbidden = [
        "TOOL_CATALOG = [",
        "BLOQUES_HERRAMIENTAS = tuple(dict.fromkeys",
        "HERRAMIENTAS_POR_LABEL = {h[\"label\"]: h for h in TOOL_CATALOG}",
        "def obtener_herramientas_por_bloque(bloque):",
    ]
    remaining = [item for item in forbidden if item in content]
    if remaining:
        print("AVISO: quedan definiciones del catálogo embebidas en app.py:")
        for item in remaining:
            print(f"- {item}")
        raise SystemExit(1)

    print("Siguiente comprobación recomendada:")
    print("python -m py_compile app.py modulos/tool_catalog.py")


if __name__ == "__main__":
    main()
