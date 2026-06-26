"""Lightweight local smoke tests for ValueQuant Terminal."""

from __future__ import annotations

import importlib
import py_compile
import sys
from dataclasses import dataclass
from pathlib import Path

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

EXPECTED_DIRECT_ROUTES = [
    "📌 Briefing de Oportunidades",
    "⚙️ Centro de Automatización",
    "🧭 Mapa del Producto",
]

EXPECTED_SPECIAL_COMPANY_TOOLS = [
    "🧩 Research Core",
    "📊 Resumen Ejecutivo",
    "🔎 Análisis Fundamental",
]


def _ok(name: str, detail: str = "") -> SmokeCheck:
    return SmokeCheck(name, "OK", detail)


def _fail(name: str, detail: str = "") -> SmokeCheck:
    return SmokeCheck(name, "FAIL", detail)


def _check_file(path_text: str) -> list[SmokeCheck]:
    path = PROJECT_ROOT / path_text
    checks = [_ok(f"file:{path_text}", "exists") if path.exists() else _fail(f"file:{path_text}", "missing")]
    if path.exists():
        try:
            py_compile.compile(str(path), doraise=True)
            checks.append(_ok(f"compile:{path_text}", "compiled"))
        except Exception as exc:
            checks.append(_fail(f"compile:{path_text}", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_import(module_name: str) -> SmokeCheck:
    try:
        importlib.import_module(module_name)
        return _ok(f"import:{module_name}", "imported")
    except Exception as exc:
        return _fail(f"import:{module_name}", f"{type(exc).__name__}: {exc}")


def _check_catalog() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        mod = importlib.import_module("modulos.tool_catalog")
        catalog = getattr(mod, "TOOL_CATALOG")
        labels = {item.get("label") for item in catalog}
        checks.append(_ok("catalog:loaded", f"{len(catalog)} tools"))
        for label in EXPECTED_TOOLS:
            checks.append(_ok(f"catalog:{label}", "registered") if label in labels else _fail(f"catalog:{label}", "missing"))

        raw_modes = getattr(mod, "obtener_modos_navegacion")()
        mode_labels = {
            str(mode.get("label") or mode.get("key") or "")
            for mode in raw_modes
            if isinstance(mode, dict)
        }
        mode_keys = {
            str(mode.get("key") or "")
            for mode in raw_modes
            if isinstance(mode, dict)
        }
        for mode in ("MVP", "Consolidado", "Completo"):
            checks.append(
                _ok(f"catalog_mode:{mode}", "available")
                if mode in mode_labels
                else _fail(f"catalog_mode:{mode}", f"missing; available={sorted(mode_labels or mode_keys)}")
            )
    except Exception as exc:
        checks.append(_fail("catalog:loaded", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_router() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        mod = importlib.import_module("modulos.tool_router")
        direct_routes = set(getattr(mod, "INDEPENDENT_TOOL_ROUTES")) | set(getattr(mod, "COMPANY_TOOL_ROUTES"))
        checks.append(_ok("router:loaded", f"{len(direct_routes)} direct routes"))

        for label in EXPECTED_DIRECT_ROUTES:
            checks.append(_ok(f"router:{label}", "registered") if label in direct_routes else _fail(f"router:{label}", "missing"))

        # Research Core, Resumen Ejecutivo and Fundamental are intentionally routed
        # through explicit branches in render_company_tool because they need custom
        # argument binding. They do not live in COMPANY_TOOL_ROUTES.
        has_company_renderer = callable(getattr(mod, "render_company_tool", None))
        for label in EXPECTED_SPECIAL_COMPANY_TOOLS:
            checks.append(
                _ok(f"router:{label}", "registered via render_company_tool")
                if has_company_renderer
                else _fail(f"router:{label}", "render_company_tool missing")
            )
    except Exception as exc:
        checks.append(_fail("router:loaded", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_scoring_model() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    try:
        mod = importlib.import_module("modulos.scoring_engine")
        version = getattr(mod, "MODEL_VERSION", "")
        cap = getattr(mod, "CONFIDENCE_CAP", None)
        checks.append(_ok("scoring:model_version", str(version)) if str(version).startswith("VQ_SCORE_") else _fail("scoring:model_version", str(version)))
        checks.append(_ok("scoring:confidence_cap", str(cap)) if isinstance(cap, (int, float)) and 0 < cap <= 1 else _fail("scoring:confidence_cap", str(cap)))
    except Exception as exc:
        checks.append(_fail("scoring:loaded", f"{type(exc).__name__}: {exc}"))
    return checks


def run_smoke_tests() -> list[SmokeCheck]:
    checks: list[SmokeCheck] = []
    for path in CRITICAL_FILES:
        checks.extend(_check_file(path))
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
    lines.append(f"Resultado: {'OK' if not failed else 'FAIL'} ({len(failed)} fallos / {len(checks)} checks)")
    return "\n".join(lines)


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
