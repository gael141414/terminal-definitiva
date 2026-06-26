"""Healthcheck local para ValueQuant Terminal.

Este módulo valida la configuración mínima del proyecto sin exponer secretos.
No envía mensajes, no descarga datos financieros y no modifica archivos salvo que se use --fix.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
import os
import platform
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRS = (
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "exports",
    PROJECT_ROOT / "exports" / "briefings",
    PROJECT_ROOT / "logs",
)

REQUIRED_FILES = (
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "requirements.txt",
    PROJECT_ROOT / ".env.example",
    PROJECT_ROOT / "modulos" / "config.py",
    PROJECT_ROOT / "modulos" / "scoring_engine.py",
    PROJECT_ROOT / "modulos" / "research_core.py",
    PROJECT_ROOT / "modulos" / "opportunity_briefing.py",
)

REQUIRED_IMPORTS = (
    ("streamlit", "streamlit"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("yfinance", "yfinance"),
    ("plotly", "plotly"),
    ("requests", "requests"),
    ("dotenv", "python-dotenv"),
)

EXPECTED_GITIGNORE_PATTERNS = (
    ".env",
    ".streamlit/secrets.toml",
    "data/",
    "exports/",
    "logs/",
    "*.local.sh",
)

PLACEHOLDER_PREFIXES = (
    "your_",
    "tu_",
    "changeme",
    "replace_me",
    "none",
    "null",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class HealthcheckReport:
    results: list[CheckResult]

    @property
    def has_errors(self) -> bool:
        return any(result.status == "ERROR" for result in self.results)

    @property
    def has_warnings(self) -> bool:
        return any(result.status == "WARN" for result in self.results)

    @property
    def exit_code(self) -> int:
        return 1 if self.has_errors else 0


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    cleaned = str(value).strip().strip('"').strip("'").lower()
    if not cleaned:
        return True
    return any(cleaned.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def _masked(value: str | None, visible: int = 4) -> str:
    if _is_placeholder(value):
        return "NO CONFIGURADO"
    text = str(value)
    if len(text) <= visible:
        return "*" * len(text)
    return f"{text[:visible]}{'*' * 8}"


def _check_python_version() -> CheckResult:
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        return CheckResult("Python", "OK", platform.python_version())
    return CheckResult("Python", "ERROR", f"Versión {platform.python_version()} detectada. Recomendado: Python >= 3.10")


def _check_required_files() -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in REQUIRED_FILES:
        rel = path.relative_to(PROJECT_ROOT)
        if path.exists():
            results.append(CheckResult(f"Archivo {rel}", "OK", "existe"))
        else:
            results.append(CheckResult(f"Archivo {rel}", "ERROR", "no existe"))
    return results


def _check_runtime_dirs(fix: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in RUNTIME_DIRS:
        rel = path.relative_to(PROJECT_ROOT)
        if path.exists():
            results.append(CheckResult(f"Directorio {rel}", "OK", "existe"))
            continue
        if fix:
            path.mkdir(parents=True, exist_ok=True)
            results.append(CheckResult(f"Directorio {rel}", "OK", "creado"))
        else:
            results.append(CheckResult(f"Directorio {rel}", "WARN", "no existe; ejecuta healthcheck con --fix para crearlo"))
    return results


def _check_imports() -> list[CheckResult]:
    results: list[CheckResult] = []
    for import_name, package_name in REQUIRED_IMPORTS:
        if find_spec(import_name) is None:
            results.append(CheckResult(f"Paquete {package_name}", "ERROR", "no instalado en el entorno activo"))
        else:
            results.append(CheckResult(f"Paquete {package_name}", "OK", "disponible"))
    return results


def _check_gitignore() -> list[CheckResult]:
    gitignore = PROJECT_ROOT / ".gitignore"
    if not gitignore.exists():
        return [CheckResult(".gitignore", "ERROR", "no existe")]

    content = gitignore.read_text(encoding="utf-8")
    results: list[CheckResult] = []
    for pattern in EXPECTED_GITIGNORE_PATTERNS:
        if pattern in content:
            results.append(CheckResult(f".gitignore {pattern}", "OK", "ignorado"))
        else:
            results.append(CheckResult(f".gitignore {pattern}", "WARN", "patrón no encontrado"))
    return results


def _check_config() -> list[CheckResult]:
    results: list[CheckResult] = []
    try:
        from modulos.config import CONFIG
    except Exception as exc:  # pragma: no cover - diagnóstico defensivo
        return [CheckResult("Config", "ERROR", f"no se pudo importar CONFIG: {exc}")]

    if _is_placeholder(CONFIG.fmp_api_key):
        results.append(CheckResult("FMP_API_KEY", "ERROR", "no configurada o placeholder"))
    else:
        results.append(CheckResult("FMP_API_KEY", "OK", _masked(CONFIG.fmp_api_key)))

    if _is_placeholder(CONFIG.telegram_bot_token):
        results.append(CheckResult("TELEGRAM_BOT_TOKEN", "WARN", "no configurado; Telegram manual quedará desactivado"))
    else:
        results.append(CheckResult("TELEGRAM_BOT_TOKEN", "OK", _masked(CONFIG.telegram_bot_token)))

    if _is_placeholder(CONFIG.telegram_chat_id):
        results.append(CheckResult("TELEGRAM_CHAT_ID", "WARN", "no configurado; Telegram manual quedará desactivado"))
    else:
        results.append(CheckResult("TELEGRAM_CHAT_ID", "OK", _masked(CONFIG.telegram_chat_id)))

    return results


def _check_local_risky_files() -> list[CheckResult]:
    tracked_risk_paths = (
        PROJECT_ROOT / ".env",
        PROJECT_ROOT / ".streamlit" / "secrets.toml",
    )
    results: list[CheckResult] = []
    for path in tracked_risk_paths:
        rel = path.relative_to(PROJECT_ROOT)
        if path.exists():
            results.append(CheckResult(f"Secreto local {rel}", "OK", "existe localmente; debe estar ignorado por Git"))
        else:
            results.append(CheckResult(f"Secreto local {rel}", "WARN", "no existe; crea el archivo si necesitas esas claves"))
    return results


def run_healthcheck(fix: bool = False) -> HealthcheckReport:
    results: list[CheckResult] = []
    results.append(_check_python_version())
    results.extend(_check_required_files())
    results.extend(_check_runtime_dirs(fix=fix))
    results.extend(_check_imports())
    results.extend(_check_gitignore())
    results.extend(_check_config())
    results.extend(_check_local_risky_files())
    return HealthcheckReport(results=results)


def format_report(report: HealthcheckReport) -> str:
    lines = ["=== ValueQuant Local Healthcheck ==="]
    for result in report.results:
        lines.append(f"[{result.status:<5}] {result.name}: {result.detail}")

    if report.has_errors:
        lines.append("\nResultado: ERROR. Corrige los errores antes de desplegar o automatizar.")
    elif report.has_warnings:
        lines.append("\nResultado: OK con advertencias. Puede ejecutarse, pero revisa los avisos.")
    else:
        lines.append("\nResultado: OK. Entorno local preparado.")
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    fix = "--fix" in argv
    report = run_healthcheck(fix=fix)
    print(format_report(report))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
