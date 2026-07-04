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
    from modulos.scoring_engine import ScoreComponent, ValueQuantScore, _apply_quality_gates

    checks: list[str] = []

    score = ValueQuantScore(
        final_score=69.0,
        raw_score=84.0,
        quality_adjusted=True,
        quality_gate_reason="Confianza operativa limitada en bloques críticos.",
        confidence=0.58,
        data_coverage=0.58,
        confidence_label="Media",
        confidence_notes=["nota"],
        components=[],
        red_flags=[],
        positives=[],
        negatives=[],
        verdict="Atractiva con matices · calidad de datos limitada",
    )

    assert_true(score.raw_score == 84.0, "ValueQuantScore debe exponer raw_score")
    assert_true(score.quality_adjusted is True, "ValueQuantScore debe exponer quality_adjusted")
    assert_true(
        score.quality_gate_reason == "Confianza operativa limitada en bloques críticos.",
        "ValueQuantScore debe exponer quality_gate_reason",
    )
    checks.append("score exposes audit trail fields")

    components = [
        ScoreComponent("Calidad fundamental", 90, 0.30, 0.90),
        ScoreComponent("Valoración", 90, 0.22, 0.90),
        ScoreComponent("Riesgo y forense", 90, 0.15, 0.40),
    ]

    red_flags: list[str] = []
    negatives: list[str] = []
    gated_score, reason = _apply_quality_gates(
        final_score=88.0,
        data_coverage=0.80,
        confidence=0.80,
        components=components,
        red_flags=red_flags,
        negatives=negatives,
    )

    assert_true(gated_score == 69.0, "Gate de bloque crítico debe capar a 69")
    assert_true(reason == "Confianza operativa limitada en bloques críticos.", "Gate debe devolver razón trazable")
    assert_true(any("Confianza operativa limitada" in item for item in negatives), "Gate debe añadir negativo explicativo")
    checks.append("quality gate returns traceable reason")

    score_without_gate = ValueQuantScore(
        final_score=82.0,
        raw_score=82.0,
        quality_adjusted=False,
        quality_gate_reason=None,
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

    assert_true(score_without_gate.raw_score == score_without_gate.final_score, "Sin gate, raw_score y final_score pueden coincidir")
    assert_true(score_without_gate.quality_adjusted is False, "Sin gate, quality_adjusted debe ser False")
    assert_true(score_without_gate.quality_gate_reason is None, "Sin gate, quality_gate_reason debe ser None")
    checks.append("score supports no-gate audit state")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Scoring Audit Trail Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Scoring Audit Trail Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
