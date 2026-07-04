#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_contract_checks() -> list[str]:
    from modulos.scoring_engine import ValueQuantScore, _decision_guidance

    checks: list[str] = []

    action, notes = _decision_guidance(
        final_score=84.0,
        confidence_label="Alta",
        quality_adjusted=False,
        red_flags=[],
        quality_gate_reason=None,
    )
    assert_true(action == "Candidato prioritario para análisis", "Score alto y confianza alta debe priorizar análisis")
    assert_true(any("workflow interno" in item for item in notes), "La guía debe aclarar que no es recomendación de compra/venta")
    checks.append("high-confidence score gets priority analysis action")

    action, notes = _decision_guidance(
        final_score=69.0,
        confidence_label="Media",
        quality_adjusted=True,
        red_flags=[],
        quality_gate_reason="Confianza operativa limitada en bloques críticos.",
    )
    assert_true(action == "Revisión manual obligatoria", "Score ajustado por gates debe exigir revisión manual")
    assert_true(any("quality gates" in item for item in notes), "La guía debe explicar el ajuste por quality gates")
    assert_true(any("Confianza operativa limitada" in item for item in notes), "La guía debe preservar el motivo del gate")
    checks.append("quality-adjusted score gets manual review action")

    action, notes = _decision_guidance(
        final_score=78.0,
        confidence_label="Alta",
        quality_adjusted=False,
        red_flags=["Riesgo forense elevado"],
        quality_gate_reason=None,
    )
    assert_true(action == "Revisar riesgos críticos antes de avanzar", "Red flags deben dominar la acción")
    assert_true(any("red flags" in item for item in notes), "La guía debe mencionar red flags")
    checks.append("red flags dominate decision guidance")

    score = ValueQuantScore(
        final_score=82.0,
        raw_score=82.0,
        quality_adjusted=False,
        quality_gate_reason=None,
        decision_action="Candidato prioritario para análisis",
        decision_notes=["nota"],
        confidence=0.82,
        data_coverage=0.82,
        confidence_label="Alta",
        confidence_notes=[],
        components=[],
        red_flags=[],
        positives=[],
        negatives=[],
        verdict="Excelente",
    )

    assert_true(score.decision_action == "Candidato prioritario para análisis", "ValueQuantScore debe exponer decision_action")
    assert_true(score.decision_notes == ["nota"], "ValueQuantScore debe exponer decision_notes")
    checks.append("score exposes decision guidance fields")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Scoring Decision Guidance Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Scoring Decision Guidance Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
