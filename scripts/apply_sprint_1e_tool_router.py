"""Migra app.py para usar modulos.tool_router.

Uso:
    python scripts/apply_sprint_1e_tool_router.py

El script es intencionalmente conservador: busca anclajes concretos en app.py,
crea app.py.bak antes de escribir y falla si no encuentra los bloques esperados.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
BACKUP_PATH = ROOT / "app.py.bak"

TOOL_CATALOG_IMPORT = """from modulos.tool_catalog import (
    TOOL_CATALOG,
    BLOQUES_HERRAMIENTAS,
    HERRAMIENTAS_POR_LABEL,
    obtener_herramientas_por_bloque,
)
"""

TOOL_ROUTER_IMPORT = """from modulos.tool_router import CompanyToolContext, render_company_tool, render_independent_tool
"""

INDEPENDENT_START = "# CASOS INDEPENDIENTES (No necesitan darle al botón del sidebar)"
COMPANY_MARKER = "# CASOS DE EMPRESA (Requieren pulsar el botón del sidebar la primera vez)"
COMPANY_ROUTER_START = "    # Invocamos la herramienta correspondiente"
CHAT_LEGACY_MARKER = "# Chat lateral legacy retirado: la nueva arquitectura usa navegación superior sin sidebar."

NEW_INDEPENDENT_BLOCK = """# CASOS INDEPENDIENTES (No necesitan darle al botón del sidebar)
if seccion_actual in herramientas_independientes:
    st.markdown("<br>", unsafe_allow_html=True)
    render_independent_tool(seccion_actual, etf_input=etf_input)

# CASOS DE EMPRESA (Requieren pulsar el botón del sidebar la primera vez)
else:"""

NEW_COMPANY_ROUTER_BLOCK = """    # Invocamos la herramienta correspondiente desde el router central
    tool_context = CompanyToolContext(
        ticker=ticker_input,
        competitor=ticker_competidor,
        years=años_hist,
        is_df=is_df,
        bs_df=bs_df,
        cf_df=cf_df,
        metrics_df=metrics_df,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
        res_val=res_val,
        nota_buffett=nota_buffett,
        valuequant_score=valuequant_score,
        sector_rotation_fn=analizar_rotacion_sectores,
    )
    render_company_tool(seccion_actual, tool_context)
"""


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise SystemExit(f"No se encontró el bloque esperado:\n{old[:160]}")
    return text.replace(old, new, 1)


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")
    original = text

    if TOOL_ROUTER_IMPORT not in text:
        text = replace_once(text, TOOL_CATALOG_IMPORT, TOOL_CATALOG_IMPORT + TOOL_ROUTER_IMPORT)

    try:
        independent_start = text.index(INDEPENDENT_START)
        company_marker = text.index(COMPANY_MARKER, independent_start)
        company_else = text.index("else:", company_marker)
        company_else_end = text.index("\n", company_else)
    except ValueError as exc:
        raise SystemExit(f"No se pudo localizar el bloque de herramientas independientes: {exc}") from exc

    text = text[:independent_start] + NEW_INDEPENDENT_BLOCK + text[company_else_end:]

    try:
        company_router_start = text.index(COMPANY_ROUTER_START)
        chat_marker = text.index(CHAT_LEGACY_MARKER, company_router_start)
    except ValueError as exc:
        raise SystemExit(f"No se pudo localizar el bloque de router de empresa: {exc}") from exc

    text = text[:company_router_start] + NEW_COMPANY_ROUTER_BLOCK + "\n" + text[chat_marker:]

    if text == original:
        print("No se realizaron cambios. app.py ya parecía migrado.")
        return

    BACKUP_PATH.write_text(original, encoding="utf-8")
    APP_PATH.write_text(text, encoding="utf-8")

    print("OK: app.py migrado para usar modulos.tool_router")
    print(f"Backup creado en: {BACKUP_PATH}")
    print("Ejecuta ahora:")
    print("  python -m py_compile app.py modulos/tool_router.py")


if __name__ == "__main__":
    main()
