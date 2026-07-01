from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "docs" / "data_resilience_audit.md"

TARGETS: dict[str, list[str]] = {
    "modulos/fmp_api.py": [
        "_descargar_json",
        "_endpoint_a_dataframe",
        "diagnosticar_conexion_fmp",
        "extraer_datos_fundamentales_fmp",
        "obtener_cotizacion_fmp",
    ],
    "modulos/company_data_helpers.py": [
        "obtener_transacciones_insiders",
        "obtener_tickers_filtrados",
        "obtener_valoracion_sectorial",
        "obtener_datos_directiva",
    ],
    "modulos/scoring_engine.py": [
        "_is_valid",
        "_get_series",
        "_last",
        "_coverage",
        "_market_data_snapshot",
    ],
}

DATA_GUARD_PATTERNS = [
    ".empty",
    ".columns",
    "dropna",
    "pd.to_numeric",
    "pd.to_datetime",
    "isinstance",
    "np.isfinite",
    "replace([np.inf, -np.inf]",
    "validate_dataframe",
]

NETWORK_PATTERNS = [
    "requests.get",
    "yf.Ticker",
]


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    path: str
    detail: str


@dataclass
class FileAudit:
    path: str
    functions: set[str] = field(default_factory=set)
    missing_expected: list[str] = field(default_factory=list)
    broad_except_count: int = 0
    silent_except_count: int = 0
    return_none_count: int = 0
    request_calls: int = 0
    request_calls_without_timeout: int = 0
    yf_ticker_calls: int = 0
    data_guard_hits: list[str] = field(default_factory=list)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def returns_none(node: ast.Return) -> bool:
    return node.value is None or isinstance(node.value, ast.Constant) and node.value.value is None


def except_is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in {"Exception", "BaseException"}
    return False


def handler_is_silent(handler: ast.ExceptHandler) -> bool:
    for child in ast.walk(handler):
        if isinstance(child, ast.Raise):
            return False
    for stmt in handler.body:
        if isinstance(stmt, ast.Pass):
            return True
        if isinstance(stmt, ast.Return) and returns_none(stmt):
            return True
    return False


def analyze_file(path_text: str, expected_functions: list[str]) -> tuple[FileAudit, list[AuditIssue]]:
    path = PROJECT_ROOT / path_text
    audit = FileAudit(path=path_text)
    issues: list[AuditIssue] = []

    if not path.exists():
        issues.append(AuditIssue("FAIL", "missing_file", path_text, "Archivo crítico ausente."))
        return audit, issues

    source = path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source, filename=path_text)
    except SyntaxError as exc:
        issues.append(AuditIssue("FAIL", "syntax_error", path_text, f"{exc.lineno}: {exc.msg}"))
        return audit, issues

    audit.functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    audit.missing_expected = [name for name in expected_functions if name not in audit.functions]
    for name in audit.missing_expected:
        issues.append(AuditIssue("FAIL", "missing_expected_function", path_text, name))

    for pattern in DATA_GUARD_PATTERNS:
        if pattern in source:
            audit.data_guard_hits.append(pattern)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and except_is_broad(node):
            audit.broad_except_count += 1
            if handler_is_silent(node):
                audit.silent_except_count += 1
                issues.append(
                    AuditIssue(
                        "WARN",
                        "silent_broad_except",
                        path_text,
                        f"Except amplio y silencioso cerca de línea {getattr(node, 'lineno', '?')}.",
                    )
                )

        if isinstance(node, ast.Return) and returns_none(node):
            audit.return_none_count += 1

        if isinstance(node, ast.Call):
            name = call_name(node.func)
            if name == "requests.get":
                audit.request_calls += 1
                has_timeout = any(keyword.arg == "timeout" for keyword in node.keywords)
                if not has_timeout:
                    audit.request_calls_without_timeout += 1
                    issues.append(
                        AuditIssue(
                            "FAIL",
                            "request_without_timeout",
                            path_text,
                            f"requests.get sin timeout en línea {getattr(node, 'lineno', '?')}.",
                        )
                    )
            elif name == "yf.Ticker":
                audit.yf_ticker_calls += 1

    if not audit.data_guard_hits:
        issues.append(
            AuditIssue(
                "WARN",
                "no_dataframe_guards_detected",
                path_text,
                "No se han detectado patrones obvios de validación de DataFrame/datos.",
            )
        )

    return audit, issues


def render_report(audits: list[FileAudit], issues: list[AuditIssue]) -> str:
    fail_count = sum(1 for issue in issues if issue.severity == "FAIL")
    warn_count = sum(1 for issue in issues if issue.severity == "WARN")

    lines: list[str] = [
        "# Data Resilience Audit",
        "",
        "Auditoría estática ligera de módulos críticos de datos.",
        "",
        "## Resumen",
        "",
        f"- Archivos auditados: {len(audits)}",
        f"- Fallos: {fail_count}",
        f"- Avisos: {warn_count}",
        "",
        "## Superficie auditada",
        "",
        "| Archivo | Funciones | Requests | Requests sin timeout | Yahoo Ticker | Except amplios | Except silenciosos | Return None | Guards detectados |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]

    for audit in audits:
        lines.append(
            "| "
            + " | ".join(
                [
                    audit.path,
                    str(len(audit.functions)),
                    str(audit.request_calls),
                    str(audit.request_calls_without_timeout),
                    str(audit.yf_ticker_calls),
                    str(audit.broad_except_count),
                    str(audit.silent_except_count),
                    str(audit.return_none_count),
                    ", ".join(audit.data_guard_hits) or "—",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Incidencias", ""])

    if not issues:
        lines.append("No se han detectado incidencias.")
    else:
        lines.append("| Severidad | Código | Archivo | Detalle |")
        lines.append("|---|---|---|---|")
        for issue in issues:
            detail = issue.detail.replace("|", "\\|")
            lines.append(f"| {issue.severity} | {issue.code} | {issue.path} | {detail} |")

    lines.extend(
        [
            "",
            "## Recomendaciones Sprint 4B",
            "",
            "- Crear un helper común para validar DataFrames obligatorios antes de calcular ratios.",
            "- Diferenciar explícitamente entre `sin datos`, `API caída`, `ticker inválido` y `cobertura insuficiente`.",
            "- Elevar avisos de baja cobertura cuando el score se calcule con demasiados defaults neutrales.",
            "- Evitar que errores de Yahoo/FMP/SEC terminen como ceros silenciosos si esos ceros afectan a valoración o riesgo.",
            "",
        ]
    )

    return "\n".join(lines)


def run_audit() -> tuple[list[FileAudit], list[AuditIssue]]:
    audits: list[FileAudit] = []
    issues: list[AuditIssue] = []

    for path_text, expected_functions in TARGETS.items():
        audit, file_issues = analyze_file(path_text, expected_functions)
        audits.append(audit)
        issues.extend(file_issues)

    return audits, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Escribe docs/data_resilience_audit.md")
    parser.add_argument("--strict", action="store_true", help="Devuelve código 1 si hay fallos.")
    args = parser.parse_args()

    audits, issues = run_audit()
    report = render_report(audits, issues)

    print(report)

    if args.write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"\nInforme escrito en: {REPORT_PATH.relative_to(PROJECT_ROOT)}")

    failures = [issue for issue in issues if issue.severity == "FAIL"]
    if args.strict and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
