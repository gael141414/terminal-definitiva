#!/usr/bin/env python3
"""Audit product catalog and router coverage for ValueQuant Terminal.

This script is intentionally static: it parses route target files instead of importing
all product modules, so the audit does not execute Streamlit code or trigger network
side effects.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REPORT_PATH = PROJECT_ROOT / "docs" / "product_surface_audit.md"
VALID_INPUT_MODES = {"company", "standalone", "etf"}

SPECIAL_INDEPENDENT_ROUTES = {
    "🩻 Radiografía de ETFs (X-Ray)": ("modulos.etf", "ejecutar_radiografia_etf"),
}

SPECIAL_COMPANY_ROUTES = {
    "🧩 Research Core": ("modulos.research_core", "ejecutar_research_core"),
    "📊 Resumen Ejecutivo": ("modulos.resumen", "ejecutar_resumen_ejecutivo"),
    "🔎 Análisis Fundamental": ("modulos.fundamental", "ejecutar_analisis_fundamental"),
    "🌍 Radar Macro y Sectores": ("modulos.macro", "ejecutar_radar_macro"),
    "🧠 Auditoría Forense": ("modulos.forense", "ejecutar_auditoria_forense"),
    "🎓 Visor de Gurús (Estrategias)": ("modulos.gurus", "ejecutar_visor_gurus"),
}


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    label: str
    detail: str


@dataclass(frozen=True)
class RouteAudit:
    label: str
    input_mode: str
    module_path: str
    callable_name: str
    status: str
    detail: str


def module_to_path(module_path: str) -> Path:
    return PROJECT_ROOT / (module_path.replace(".", "/") + ".py")


def top_level_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def resolve_route(label: str, input_mode: str, independent_routes: dict, company_routes: dict) -> tuple[str, str] | None:
    if input_mode == "etf":
        return SPECIAL_INDEPENDENT_ROUTES.get(label) or independent_routes.get(label)
    if input_mode == "standalone":
        return SPECIAL_INDEPENDENT_ROUTES.get(label) or independent_routes.get(label)
    if input_mode == "company":
        return SPECIAL_COMPANY_ROUTES.get(label) or company_routes.get(label)
    return None


def audit_catalog() -> tuple[list[AuditIssue], list[RouteAudit], dict[str, int]]:
    from modulos.tool_catalog import TOOL_CATALOG, obtener_modos_navegacion, obtener_catalogo_por_modo
    from modulos.tool_router import COMPANY_TOOL_ROUTES, INDEPENDENT_TOOL_ROUTES

    issues: list[AuditIssue] = []
    route_audits: list[RouteAudit] = []

    labels = [str(tool.get("label", "")) for tool in TOOL_CATALOG]
    seen: set[str] = set()
    duplicates: set[str] = set()
    for label in labels:
        if label in seen:
            duplicates.add(label)
        seen.add(label)

    for label in sorted(duplicates):
        issues.append(AuditIssue("FAIL", "duplicate_label", label, "La etiqueta aparece más de una vez en TOOL_CATALOG."))

    catalog_labels = set(labels)
    route_labels = set(INDEPENDENT_TOOL_ROUTES) | set(COMPANY_TOOL_ROUTES) | set(SPECIAL_INDEPENDENT_ROUTES) | set(SPECIAL_COMPANY_ROUTES)
    for label in sorted(route_labels - catalog_labels):
        issues.append(AuditIssue("WARN", "orphan_route", label, "Existe ruta en el router pero no aparece en TOOL_CATALOG."))

    for tool in TOOL_CATALOG:
        label = str(tool.get("label", ""))
        input_mode = str(tool.get("input_mode", ""))
        if input_mode not in VALID_INPUT_MODES:
            issues.append(AuditIssue("FAIL", "invalid_input_mode", label, f"input_mode no válido: {input_mode!r}"))
            continue

        route = resolve_route(label, input_mode, INDEPENDENT_TOOL_ROUTES, COMPANY_TOOL_ROUTES)
        if route is None:
            issues.append(AuditIssue("FAIL", "missing_route", label, f"No hay ruta efectiva para input_mode={input_mode}."))
            route_audits.append(RouteAudit(label, input_mode, "", "", "FAIL", "missing route"))
            continue

        module_path, callable_name = route
        file_path = module_to_path(module_path)
        if not file_path.exists():
            issues.append(AuditIssue("FAIL", "missing_module", label, f"No existe {file_path.relative_to(PROJECT_ROOT)}."))
            route_audits.append(RouteAudit(label, input_mode, module_path, callable_name, "FAIL", "missing module file"))
            continue

        try:
            symbols = top_level_symbols(file_path)
        except SyntaxError as exc:
            issues.append(AuditIssue("FAIL", "syntax_error", label, f"{file_path.relative_to(PROJECT_ROOT)}: {exc}"))
            route_audits.append(RouteAudit(label, input_mode, module_path, callable_name, "FAIL", "syntax error"))
            continue

        if callable_name not in symbols:
            issues.append(AuditIssue("FAIL", "missing_callable", label, f"{module_path}.{callable_name} no existe como símbolo top-level."))
            route_audits.append(RouteAudit(label, input_mode, module_path, callable_name, "FAIL", "missing callable"))
            continue

        route_audits.append(RouteAudit(label, input_mode, module_path, callable_name, "OK", "resolved"))

    mode_counts: dict[str, int] = {}
    for mode in obtener_modos_navegacion():
        key = str(mode.get("key", ""))
        mode_counts[key] = len(obtener_catalogo_por_modo(key))

    return issues, route_audits, mode_counts


def table_row(values: Iterable[object]) -> str:
    escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
    return "| " + " | ".join(escaped) + " |"


def render_report(issues: list[AuditIssue], routes: list[RouteAudit], mode_counts: dict[str, int]) -> str:
    failures = [issue for issue in issues if issue.severity == "FAIL"]
    warnings = [issue for issue in issues if issue.severity == "WARN"]
    ok_routes = [route for route in routes if route.status == "OK"]

    lines = [
        "# Product surface audit",
        "",
        "Auditoría estática del catálogo de herramientas y su cobertura real en `tool_router`.",
        "",
        "## Resumen",
        "",
        f"- Rutas auditadas: {len(routes)}",
        f"- Rutas OK: {len(ok_routes)}",
        f"- Fallos: {len(failures)}",
        f"- Avisos: {len(warnings)}",
        "",
        "## Herramientas por modo",
        "",
        table_row(["Modo", "Herramientas visibles"]),
        table_row(["---", "---:"]),
    ]

    for mode, count in sorted(mode_counts.items()):
        lines.append(table_row([mode, count]))

    lines.extend(["", "## Incidencias", ""])
    if issues:
        lines.append(table_row(["Severidad", "Código", "Herramienta", "Detalle"]))
        lines.append(table_row(["---", "---", "---", "---"]))
        for issue in issues:
            lines.append(table_row([issue.severity, issue.code, issue.label, issue.detail]))
    else:
        lines.append("Sin incidencias detectadas.")

    lines.extend(["", "## Cobertura de rutas", ""])
    lines.append(table_row(["Estado", "Herramienta", "Modo", "Módulo", "Callable"]))
    lines.append(table_row(["---", "---", "---", "---", "---"]))
    for route in sorted(routes, key=lambda item: (item.status != "OK", item.input_mode, item.label)):
        lines.append(table_row([route.status, route.label, route.input_mode, route.module_path, route.callable_name]))

    lines.extend([
        "",
        "## Lectura recomendada",
        "",
        "- Un fallo `missing_route` implica que una herramienta aparece en navegación pero cae en mensaje genérico del router.",
        "- Un fallo `missing_callable` implica que el router apunta a una función inexistente o renombrada.",
        "- Los avisos `orphan_route` no rompen la app, pero señalan rutas que ya no son visibles desde el catálogo.",
        "- Esta auditoría no ejecuta herramientas ni llama APIs externas; solo comprueba coherencia estática.",
        "",
    ])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    write = "--write" in argv
    strict = "--strict" in argv

    issues, routes, mode_counts = audit_catalog()
    report = render_report(issues, routes, mode_counts)
    print(report)

    if write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"\nAuditoría escrita en: {REPORT_PATH.relative_to(PROJECT_ROOT)}")

    failures = [issue for issue in issues if issue.severity == "FAIL"]
    if strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
