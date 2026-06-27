from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "app.py"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "app_legacy_inventory.md"

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "cache_datos",
    "data",
    "exports",
    "logs",
}

EXCLUDED_FILE_PREFIXES = (
    "apply_sprint_",
)


@dataclass(frozen=True)
class FunctionRecord:
    name: str
    start_line: int
    end_line: int
    doc: str
    internal_calls: int
    repo_calls: int
    category: str
    recommendation: str


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.name.startswith(EXCLUDED_FILE_PREFIXES):
            continue
        yield path


def read_tree(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def call_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def top_level_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    return [node for node in tree.body if isinstance(node, ast.FunctionDef)]


def first_docline(node: ast.FunctionDef) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.strip().splitlines()[0] if doc.strip() else ""


def classify_function(name: str, node: ast.FunctionDef, internal_calls: int, repo_calls: int) -> tuple[str, str]:
    doc = first_docline(node).lower()

    if name in {"inyectar_atajo_teclado", "load_lottieurl", "obtener_modelo_gemini", "obtener_secreto_streamlit"}:
        category = "runtime/helper"
    elif name.startswith("render") or name.startswith("renderizar"):
        category = "ui/widget"
    elif name.startswith("obtener") or name.startswith("cargar"):
        category = "data/helper"
    elif name.startswith("analizar") or name.startswith("escanear") or name.startswith("calcular"):
        category = "analysis/helper"
    elif name.startswith("generar") or "pdf" in name.lower():
        category = "export/helper"
    else:
        category = "legacy/helper"

    if "compatibilidad" in doc:
        recommendation = "mantener como wrapper hasta confirmar consumidores"
    elif repo_calls == 0:
        recommendation = "candidata a revisar; sin llamadas detectadas"
    elif internal_calls == 0 and repo_calls > 0:
        recommendation = "posible API usada fuera de app.py; no borrar"
    elif category in {"ui/widget", "data/helper"}:
        recommendation = "candidata a extracción modular posterior"
    else:
        recommendation = "mantener temporalmente"

    return category, recommendation


def build_inventory(app_path: Path) -> list[FunctionRecord]:
    app_tree = read_tree(app_path)
    if app_tree is None:
        raise RuntimeError(f"No se pudo parsear {app_path}")

    functions = top_level_functions(app_tree)
    function_names = {node.name for node in functions}

    app_calls = call_names(app_tree)
    internal_counts = {name: app_calls.count(name) for name in function_names}

    repo_counts = {name: 0 for name in function_names}
    for path in iter_python_files(PROJECT_ROOT):
        tree = read_tree(path)
        if tree is None:
            continue
        calls = call_names(tree)
        for name in function_names:
            repo_counts[name] += calls.count(name)

    records: list[FunctionRecord] = []
    for node in functions:
        internal = max(0, internal_counts.get(node.name, 0))
        repo = max(0, repo_counts.get(node.name, 0))
        category, recommendation = classify_function(node.name, node, internal, repo)
        records.append(
            FunctionRecord(
                name=node.name,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                doc=first_docline(node),
                internal_calls=internal,
                repo_calls=repo,
                category=category,
                recommendation=recommendation,
            )
        )

    return records


def render_markdown(records: list[FunctionRecord]) -> str:
    total = len(records)
    no_calls = sum(1 for item in records if item.repo_calls == 0)
    extraction_candidates = sum(1 for item in records if "extracción" in item.recommendation or item.category in {"ui/widget", "data/helper"})

    lines = [
        "# App legacy inventory",
        "",
        "Inventario estático de funciones top-level restantes en `app.py`.",
        "",
        "Este informe no borra código. Sirve para decidir el siguiente refactor con menor riesgo.",
        "",
        "## Resumen",
        "",
        f"- Funciones top-level detectadas: {total}",
        f"- Sin llamadas detectadas en el repositorio: {no_calls}",
        f"- Candidatas a extracción/revisión: {extraction_candidates}",
        "",
        "## Inventario",
        "",
        "| Función | Líneas | Categoría | Llamadas en app.py | Llamadas repo | Recomendación |",
        "|---|---:|---|---:|---:|---|",
    ]

    for item in records:
        lines.append(
            "| "
            f"`{item.name}` | "
            f"{item.start_line}-{item.end_line} | "
            f"{item.category} | "
            f"{item.internal_calls} | "
            f"{item.repo_calls} | "
            f"{item.recommendation} |"
        )

    lines.extend(
        [
            "",
            "## Lectura recomendada",
            "",
            "- No eliminar funciones solo porque tengan pocas llamadas: algunas pueden ser entrypoints indirectos de Streamlit o rutas antiguas.",
            "- Priorizar extracción de widgets/UI antes que lógica financiera.",
            "- Convertir wrappers de compatibilidad en delegaciones explícitas cuando haya consumidores externos.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventaría funciones legacy restantes en app.py.")
    parser.add_argument("--write", action="store_true", help="Escribe docs/app_legacy_inventory.md además de imprimir el resumen.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Ruta de salida Markdown si se usa --write.")
    args = parser.parse_args()

    records = build_inventory(APP_PATH)
    markdown = render_markdown(records)

    print(markdown)

    if args.write:
        output_path = args.output
        if not output_path.is_absolute():
            output_path = PROJECT_ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"\nInventario escrito en: {output_path.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
