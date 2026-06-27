from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path("app.py")
EXPORT_PATH = Path("modulos/app_pdf_export.py")

TARGET_FUNCTION = "generar_reporte_pdf"

IMPORT_ANCHOR = "from modulos.app_analysis_helpers import analizar_sentimiento_noticias, escanear_vulnerabilidades, ultimo_ratio\n"
IMPORT_LINE = "from modulos.app_pdf_export import generar_reporte_pdf\n"

FPDF_IMPORT_BLOCK = '''try:
    from fpdf import FPDF
except Exception:
    FPDF = None

'''

MODULE_HEADER = '''from __future__ import annotations

try:
    from fpdf import FPDF
except Exception:
    FPDF = None


'''


def collect_function_span(source: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name != TARGET_FUNCTION:
            continue

        if node.lineno is None or node.end_lineno is None:
            raise RuntimeError(f"No se pudo localizar el rango de {TARGET_FUNCTION}.")

        start_index = node.lineno - 1
        end_index = node.end_lineno

        if node.decorator_list:
            start_index = min(decorator.lineno for decorator in node.decorator_list) - 1

        while start_index > 0 and lines[start_index - 1].strip() == "":
            start_index -= 1

        block = "".join(lines[start_index:end_index]).strip() + "\n"
        return start_index, end_index, block

    raise RuntimeError(f"No se encontró {TARGET_FUNCTION} en app.py.")


def main() -> int:
    if not APP_PATH.exists():
        raise FileNotFoundError("No se encuentra app.py. Ejecuta este script desde la raíz del proyecto.")

    source = APP_PATH.read_text(encoding="utf-8")

    if "st.set_page_config(" not in source[:400]:
        raise RuntimeError("st.set_page_config no parece estar al inicio. Revisa app.py antes de aplicar Sprint 2Q.")

    if IMPORT_LINE in source and EXPORT_PATH.exists():
        print("Sin cambios: Sprint 2Q ya parece aplicado.")
        return 0

    start, end, function_block = collect_function_span(source)
    module_source = MODULE_HEADER + function_block + "\n"

    required_tokens = [
        "def generar_reporte_pdf(",
        "FPDF is None",
        "pdf.output",
        "TEAR SHEET VALUE",
        "BUFFETT SCORE",
        "fcf_yield + buyback_yield",
    ]
    missing_tokens = [token for token in required_tokens if token not in module_source]
    if missing_tokens:
        raise RuntimeError(f"La extracción no contiene la exportación PDF esperada. Faltan: {missing_tokens}")

    lines = source.splitlines(keepends=True)
    del lines[start:end]
    new_source = "".join(lines)

    if IMPORT_LINE not in new_source:
        if IMPORT_ANCHOR not in new_source:
            raise RuntimeError("No se encontró el import de app_analysis_helpers para insertar app_pdf_export.")
        new_source = new_source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if FPDF_IMPORT_BLOCK in new_source:
        new_source = new_source.replace(FPDF_IMPORT_BLOCK, "", 1)

    backup = APP_PATH.with_suffix(".py.bak_sprint_2q")
    backup.write_text(source, encoding="utf-8")

    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPORT_PATH.write_text(module_source, encoding="utf-8")
    APP_PATH.write_text(new_source, encoding="utf-8")

    print("OK: Sprint 2Q aplicado.")
    print(f"Exportación PDF extraída a: {EXPORT_PATH}")
    print(f"Backup creado: {backup}")
    print("Valida con: python -m py_compile app.py modulos/app_pdf_export.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
