"""Release readiness gate para ValueQuant Terminal.

Este módulo agrega healthcheck + smoke tests en un único informe de preparación
de release. No descarga datos financieros, no modifica archivos y no expone
secretos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from modulos.healthcheck import CheckResult, run_healthcheck
from modulos.smoke_tests import SmokeCheck, run_smoke_tests


@dataclass(frozen=True)
class ReleaseGate:
    name: str
    status: str
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    @property
    def blocking(self) -> bool:
        return self.status == "FAIL"


@dataclass(frozen=True)
class ReleaseReadinessReport:
    generated_at: str
    gates: list[ReleaseGate]
    health_results: list[CheckResult]
    smoke_checks: list[SmokeCheck]

    @property
    def failed_gates(self) -> list[ReleaseGate]:
        return [gate for gate in self.gates if gate.blocking]

    @property
    def warning_gates(self) -> list[ReleaseGate]:
        return [gate for gate in self.gates if gate.status == "WARN"]

    @property
    def ready(self) -> bool:
        return not self.failed_gates

    @property
    def exit_code(self) -> int:
        return 0 if self.ready else 1


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _gate(name: str, status: str, detail: str) -> ReleaseGate:
    return ReleaseGate(name=name, status=status, detail=detail)


def _summarize_health(health_results: list[CheckResult]) -> ReleaseGate:
    errors = [result for result in health_results if result.status == "ERROR"]
    warnings = [result for result in health_results if result.status == "WARN"]

    if errors:
        sample = "; ".join(f"{item.name}: {item.detail}" for item in errors[:3])
        return _gate("healthcheck", "FAIL", f"{len(errors)} errores; sample={sample}")
    if warnings:
        return _gate("healthcheck", "WARN", f"{len(warnings)} advertencias no bloqueantes")
    return _gate("healthcheck", "OK", f"{len(health_results)} checks OK")


def _summarize_smoke(smoke_checks: list[SmokeCheck]) -> ReleaseGate:
    failures = [check for check in smoke_checks if not check.ok]

    if failures:
        sample = "; ".join(f"{item.name}: {item.detail}" for item in failures[:3])
        return _gate("smoke_tests", "FAIL", f"{len(failures)} fallos; sample={sample}")
    return _gate("smoke_tests", "OK", f"{len(smoke_checks)} checks OK")


def _summarize_contract_coverage(smoke_checks: list[SmokeCheck]) -> ReleaseGate:
    contract_checks = [check for check in smoke_checks if "contract" in check.name.lower()]
    behavior_checks = [check for check in contract_checks if ":behavior" in check.name]

    if len(behavior_checks) >= 15:
        return _gate("contract_coverage", "OK", f"{len(behavior_checks)} contratos de comportamiento")
    if behavior_checks:
        return _gate("contract_coverage", "WARN", f"solo {len(behavior_checks)} contratos de comportamiento")
    return _gate("contract_coverage", "FAIL", "no se detectaron contratos de comportamiento")


def _summarize_release_artifacts() -> ReleaseGate:
    """Comprueba que los scripts de QA final existan."""

    from pathlib import Path

    project_root = Path(__file__).resolve().parents[1]
    expected = [
        project_root / "scripts" / "run_healthcheck.py",
        project_root / "scripts" / "run_smoke_tests.py",
        project_root / "scripts" / "run_release_readiness.py",
    ]
    missing = [path.relative_to(project_root).as_posix() for path in expected if not path.exists()]

    if missing:
        return _gate("release_artifacts", "FAIL", f"faltan: {', '.join(missing)}")
    return _gate("release_artifacts", "OK", "scripts de QA disponibles")


def build_release_readiness_report(
    *,
    health_results: list[CheckResult] | None = None,
    smoke_checks: list[SmokeCheck] | None = None,
) -> ReleaseReadinessReport:
    """Construye el informe de readiness.

    Permite inyectar resultados sintéticos para tests contractuales.
    """

    health_results = list(health_results) if health_results is not None else run_healthcheck(fix=False).results
    smoke_checks = list(smoke_checks) if smoke_checks is not None else run_smoke_tests()

    gates = [
        _summarize_health(health_results),
        _summarize_smoke(smoke_checks),
        _summarize_contract_coverage(smoke_checks),
        _summarize_release_artifacts(),
    ]

    return ReleaseReadinessReport(
        generated_at=_now_iso(),
        gates=gates,
        health_results=health_results,
        smoke_checks=smoke_checks,
    )


def release_readiness_payload(report: ReleaseReadinessReport) -> dict[str, Any]:
    """Payload JSON estructurado del readiness report."""

    health_errors = [result for result in report.health_results if result.status == "ERROR"]
    health_warnings = [result for result in report.health_results if result.status == "WARN"]
    smoke_failures = [check for check in report.smoke_checks if not check.ok]

    return {
        "schema_version": "release_readiness_v1",
        "generated_at": report.generated_at,
        "ready": report.ready,
        "exit_code": report.exit_code,
        "summary": {
            "gates": len(report.gates),
            "failed_gates": len(report.failed_gates),
            "warning_gates": len(report.warning_gates),
            "health_checks": len(report.health_results),
            "health_errors": len(health_errors),
            "health_warnings": len(health_warnings),
            "smoke_checks": len(report.smoke_checks),
            "smoke_failures": len(smoke_failures),
        },
        "gates": [
            {
                "name": gate.name,
                "status": gate.status,
                "detail": gate.detail,
                "blocking": gate.blocking,
            }
            for gate in report.gates
        ],
        "health_errors": [
            {"name": result.name, "detail": result.detail}
            for result in health_errors
        ],
        "smoke_failures": [
            {"name": check.name, "detail": check.detail}
            for check in smoke_failures
        ],
    }


def format_release_readiness_report(report: ReleaseReadinessReport) -> str:
    """Formato texto para CLI."""

    payload = release_readiness_payload(report)
    summary = payload["summary"]

    lines = ["=== ValueQuant Release Readiness ==="]
    lines.append(f"Generado: {report.generated_at}")
    lines.append(f"Estado: {'READY' if report.ready else 'BLOCKED'}")
    lines.append("")

    lines.append("Gates:")
    for gate in report.gates:
        prefix = "[OK   ]" if gate.status == "OK" else "[WARN ]" if gate.status == "WARN" else "[FAIL ]"
        lines.append(f"{prefix} {gate.name}: {gate.detail}")

    lines.append("")
    lines.append(
        "Resumen: "
        f"{summary['health_errors']} errores healthcheck, "
        f"{summary['health_warnings']} warnings healthcheck, "
        f"{summary['smoke_failures']} fallos smoke."
    )

    if report.ready:
        lines.append("Resultado: OK para merge/release interno.")
    else:
        lines.append("Resultado: BLOQUEADO. Corrige los fallos antes de fusionar o entregar.")

    return "\n".join(lines)


def run_release_readiness(*, as_json: bool = False) -> tuple[int, str]:
    report = build_release_readiness_report()
    if as_json:
        return report.exit_code, json.dumps(release_readiness_payload(report), ensure_ascii=False, indent=2)
    return report.exit_code, format_release_readiness_report(report)


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(argv if argv is not None else sys.argv[1:])
    as_json = "--json" in argv
    exit_code, output = run_release_readiness(as_json=as_json)
    print(output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
