#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract_checks() -> list[str]:
    from modulos.healthcheck import CheckResult
    from modulos.release_readiness import (
        build_release_readiness_report,
        format_release_readiness_report,
        release_readiness_payload,
    )
    from modulos.smoke_tests import SmokeCheck

    checks: list[str] = []

    health_ok = [
        CheckResult("Python", "OK", "3.12"),
        CheckResult("Config", "WARN", "telegram no configurado"),
    ]
    smoke_ok = [
        SmokeCheck("compile:app.py", "OK", "compiled"),
        SmokeCheck("research_core_ux_contract:behavior", "OK", "contract OK"),
        SmokeCheck("institutional_export_pack_contract:behavior", "OK", "contract OK"),
        SmokeCheck("release_readiness_contract:behavior", "OK", "contract OK"),
        SmokeCheck("scoring_summary_payload_contract:behavior", "OK", "contract OK"),
        SmokeCheck("basic_signal_backtesting_contract:behavior", "OK", "contract OK"),
        SmokeCheck("predictive_confidence_calibration_contract:behavior", "OK", "contract OK"),
        SmokeCheck("watchlist_score_payload_integration_contract:behavior", "OK", "contract OK"),
        SmokeCheck("opportunity_briefing_score_payload_contract:behavior", "OK", "contract OK"),
        SmokeCheck("report_score_payload_integration_contract:behavior", "OK", "contract OK"),
        SmokeCheck("data_quality_contract:behavior", "OK", "contract OK"),
        SmokeCheck("module_loader_contract:behavior", "OK", "contract OK"),
        SmokeCheck("scoring_quality_gates_contract:behavior", "OK", "contract OK"),
        SmokeCheck("scoring_confidence_diagnostics_contract:behavior", "OK", "contract OK"),
        SmokeCheck("scoring_audit_trail_contract:behavior", "OK", "contract OK"),
        SmokeCheck("scoring_decision_guidance_contract:behavior", "OK", "contract OK"),
    ]

    report = build_release_readiness_report(health_results=health_ok, smoke_checks=smoke_ok)
    assert_true(report.ready is True, "Warnings de healthcheck no deben bloquear release")
    assert_true(report.exit_code == 0, "Ready report debe devolver exit_code 0")
    assert_true(any(gate.name == "healthcheck" and gate.status == "WARN" for gate in report.gates), "Debe conservar warning healthcheck")
    checks.append("release readiness accepts non-blocking warnings")

    payload = release_readiness_payload(report)
    assert_true(payload["schema_version"] == "release_readiness_v1", "Schema incorrecto")
    assert_true(payload["ready"] is True, "Payload debe marcar ready")
    assert_true(payload["summary"]["smoke_failures"] == 0, "No debe haber fallos smoke")
    json.dumps(payload, ensure_ascii=False)
    checks.append("release readiness payload is JSON serializable")

    formatted = format_release_readiness_report(report)
    assert_true("ValueQuant Release Readiness" in formatted, "Debe incluir título")
    assert_true("Estado: READY" in formatted, "Debe incluir estado READY")
    assert_true("Resultado: OK" in formatted, "Debe incluir resultado OK")
    checks.append("release readiness text report is formatted")

    health_bad = [CheckResult("FMP_API_KEY", "ERROR", "no configurada")]
    smoke_bad = [SmokeCheck("compile:app.py", "FAIL", "SyntaxError")]
    blocked = build_release_readiness_report(health_results=health_bad, smoke_checks=smoke_bad)
    blocked_payload = release_readiness_payload(blocked)

    assert_true(blocked.ready is False, "Errores deben bloquear release")
    assert_true(blocked.exit_code == 1, "Blocked report debe devolver exit_code 1")
    assert_true(blocked_payload["summary"]["health_errors"] == 1, "Debe contar errores healthcheck")
    assert_true(blocked_payload["summary"]["smoke_failures"] == 1, "Debe contar fallos smoke")
    assert_true(len(blocked.failed_gates) >= 2, "Debe haber gates bloqueantes")
    checks.append("release readiness blocks on health errors and smoke failures")

    low_contracts = build_release_readiness_report(
        health_results=[CheckResult("Python", "OK", "3.12")],
        smoke_checks=[SmokeCheck("compile:app.py", "OK", "compiled")],
    )
    assert_true(
        any(gate.name == "contract_coverage" and gate.status in {"WARN", "FAIL"} for gate in low_contracts.gates),
        "Debe detectar cobertura contractual insuficiente",
    )
    checks.append("release readiness detects low contract coverage")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Release Readiness Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Release Readiness Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
