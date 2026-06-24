"""Local smoke tests for ValueQuant Terminal.

These checks are intentionally lightweight. They validate that critical modules can be
compiled/imported and that key registries expose the expected routes, without starting
Streamlit or downloading financial data.
"""

from __future__ import annotations

import importlib
import py_compile
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "OK"


CRITICAL_FILES = [
    "app.py",
    "modulos/config.py",
    "modulos/scoring_engine.py",
    "modulos/tool_catalog.py",
    "modulos/tool_router.py",
    "modulos/research_core.py",
    "modulos/investment_thesis.py",
    "modulos/research_report.py",
    "modulos/watchlist.py",
    "modulos/watchlist_alerts.py",
    "modulos/opportunity_briefing.py",
    "modulos/automation_center.py",
    "modulos/automation_logs.py",
    "modulos/automation_schedule.py",
    "modulos/briefing_runner.py",
    "modulos/healthcheck.py",
]

CRITICAL_IMPORTS = [
    "modulos.config",
    "modulos.scoring_engine",
    "modulos.module_loader",
    "modulos.tool_consolidation",
    "modulos.tool_catalog",
    "modulos.tool_router",
    "modulos.investment_thesis",
    "modulos.research_report",
    "modulos.valuation_sensitivity",
    "modulos.relative_comparison",
    "modulos.relative_decision",
    "modulos.analysis_store",
    "modulos.watchlist_alerts",
    "modulos.opportunity_briefing",
    "modulos.briefing_payloads",
    "modulos.manual_delivery",
    "modulos.automation_center",
    "modulos.automation_logs",
    "modulos.automation_schedule",
    "modulos.briefing_runner",
    "modulos.healthcheck",
]

EXPECTED_TOOLS = [
    "🧩 Research Core",
    "📊 Resumen Ejecutivo",
    "🔎 Análisis Fundamental",
    "📋 Mi Watchlist (Cartera)",
    "📌 Briefing de Oportunidades",
    "⚙️ Centro de Automatización",
    "🧭 Mapa del Producto",
]

EXPECTED_ROUTES = [
    "🧩 Research Core",
    "📌 Briefing de Oportunidades",
    "⚙️ Centro de Automatización",
    "🧭 Mapa del Producto",
]


class SmokeFailure(RuntimeError):
    """Raised when smoke tests fail in strict mode."""


def _check_file_exists(relative_path: str) -> SmokeCheck:
    path = PROJECT_ROOT / relative_path
    if path.exists():
        return SmokeCheck(f"file:{relative_path}", "OK", "exists")
    return SmokeCheck(f"file:{relative_path}", "FAIL", "missing")


def _check_compile(relative_path: str) -> SmokeCheck:
    path = PROJECT_ROOT / relative_path
    try:
        py_compile.compile(str(path), doraise=True)
        return SmokeCheck(f"compile:{relative_path}", "OK", "compiled")
    except Exception as exc:  # pragma: no cover - diagnostic path
        return SmokeCheck(f"compile:{relative_path}", "FAIL", str(exc))


def _check_import(module_name: str) -> SmokeCheck:
    try:
        importlib.import_module(module_name)
        return SmokeCheck(f"import:{module_name}", "OK", "imported")
    except Exception as exc:  # pragma: no cover - diagnostic path
        return SmokeCheck(f"import:{module_name}", "FAIL", f"{type(exc).__name__}: {exc}")


def _check_catalog() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        catalog_mod = importlib.import_module("modulos.tool_catalog")
        catalog = getattr(catalog_mod, "TOOL_CATALOG")
        labels = {item.get("label") for item in catalog}
        checks.append(SmokeCheck("catalog:loaded", "OK", f"{len(catalog)} tools"))

        for label in EXPECTED_TOOLS:
            if label in labels:
                checks.append(SmokeCheck(f"catalog:{label}", "OK", "registered"))
            else:
                checks.append(SmokeCheck(f"catalog:{label}", "FAIL", "missing"))

        modes = getattr(catalog_mod, "obtener_modos_navegacion")()
        for mode in ("MVP", "Consolidado", "Completo"):
            status = "OK" if mode in modes else "FAIL"
            detail = "available" if status == "OK" else "missing"
            checks.append(SmokeCheck(f"catalog_mode:{mode}", status, detail))
    except Exception as exc:  # pragma: no cover - diagnostic path
        checks.append(SmokeCheck("catalog:loaded", "FAIL", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_router() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        router_mod = importlib.import_module("modulos.tool_router")
        independent_routes = getattr(router_mod, "INDEPENDENT_TOOL_ROUTES")
        company_routes = getattr(router_mod, "COMPANY_TOOL_ROUTES")
        routes = set(independent_routes) | set(company_routes)
        checks.append(SmokeCheck("router:loaded", "OK", f"{len(routes)} routes"))

        for label in EXPECTED_ROUTES:
            if label in routes:
                checks.append(SmokeCheck(f"router:{label}", "OK", "registered"))
            else:
                checks.append(SmokeCheck(f"router:{label}", "FAIL", "missing"))
    except Exception as exc:  # pragma: no cover - diagnostic path
        checks.append(SmokeCheck("router:loaded", "FAIL", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_scoring_model() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        scoring_mod = importlib.import_module("modulos.scoring_engine")
        version = getattr(scoring_mod, "MODEL_VERSION", "")
        cap = getattr(scoring_mod, "CONFIDENCE_CAP", None)
        checks.append(
            SmokeCheck(
                "scoring:model_version",
                "OK" if str(version).startswith("VQ_SCORE_") else "FAIL",
                str(version) or "missing",
            )
        )
        checks.append(
            SmokeCheck(
                "scoring:confidence_cap",
                "OK" if isinstance(cap, (int, float)) and 0 < cap <= 1 else "FAIL",
                str(cap),
            )
        )
    except Exception as exc:  # pragma: no cover - diagnostic path
        checks.append(SmokeCheck("scoring:loaded", "FAIL", f"{type(exc).__name__}: {exc}"))
    return checks


def _run_many(functions: Iterable[Callable[[], SmokeCheck]]) -> list[SmokeCheck]:
    return [fn() for fn in functions]


def run_smoke_tests() -> list[SmokeCheck]:
    """Run all local smoke checks and return structured results."""

    checks: list[SmokeCheck] = []

    checks.extend(_check_file_exists(path) for path in CRITICAL_FILES)
    checks.extend(_check_compile(path) for path in CRITICAL_FILES)
    checks.extend(_check_import(name) for name in CRITICAL_IMPORTS)
    checks.extend(_check_catalog())
    checks.extend(_check_router())
    checks.extend(_check_scoring_model())

    return checks


def format_smoke_results(checks: list[SmokeCheck]) -> str:
    lines = ["=== ValueQuant Local Smoke Tests ==="]
    for check in checks:
        prefix = "[OK   ]" if check.ok else "[FAIL ]"
        detail = f" — {check.detail}" if check.detail else ""
        lines.append(f"{prefix} {check.name}{detail}")

    failed = [check for check in checks if not check.ok]
    lines.append("")
    if failed:
        lines.append(f"Resultado: FAIL ({len(failed)} fallos / {len(checks)} checks)")
    else:
        lines.append(f"Resultado: OK ({len(checks)} checks)")
    return "\n".join(lines)


def assert_smoke_tests_pass(checks: list[SmokeCheck]) -> None:
    failed = [check for check in checks if not check.ok]
    if failed:
        details = "\n".join(f"- {check.name}: {check.detail}" for check in failed)
        raise SmokeFailure(f"Smoke tests failed:\n{details}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv
    checks = run_smoke_tests()
    print(format_smoke_results(checks))

    failed = [check for check in checks if not check.ok]
    if strict and failed:
        return 1
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
