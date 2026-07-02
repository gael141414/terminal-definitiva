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


def _fake_component(name: str, score: float, weight: float, confidence: float):
    from modulos.scoring_engine import ScoreComponent

    return ScoreComponent(
        name=name,
        score=score,
        weight=weight,
        confidence=confidence,
    )


def run_contract_checks() -> list[str]:
    from modulos.scoring_engine import _apply_quality_gates

    checks: list[str] = []

    strong_components = [
        _fake_component("Calidad fundamental", 90, 0.30, 0.90),
        _fake_component("Valoración", 85, 0.22, 0.90),
        _fake_component("Riesgo y forense", 88, 0.15, 0.90),
    ]

    red_flags: list[str] = []
    negatives: list[str] = []
    score, reason = _apply_quality_gates(88.0, 0.90, 0.86, strong_components, red_flags, negatives)
    assert_true(score == 88.0, "Cobertura alta no debe capar score")
    assert_true(reason is None, "Cobertura alta no debe añadir razón de gate")
    assert_true(not red_flags and not negatives, "Cobertura alta no debe añadir flags")
    checks.append("high coverage allows strong score")

    red_flags = []
    negatives = []
    score, reason = _apply_quality_gates(88.0, 0.30, 0.30, strong_components, red_flags, negatives)
    assert_true(score == 49.0, "Cobertura crítica debe capar a 49")
    assert_true(reason is not None, "Cobertura crítica debe devolver razón")
    assert_true(any("Cobertura de datos crítica" in item for item in red_flags), "Cobertura crítica debe añadir red flag")
    checks.append("critical coverage blocks strong conclusion")

    red_flags = []
    negatives = []
    score, reason = _apply_quality_gates(88.0, 0.50, 0.50, strong_components, red_flags, negatives)
    assert_true(score == 59.0, "Cobertura parcial debe capar a 59")
    assert_true(reason is not None, "Cobertura parcial debe devolver razón")
    assert_true(any("Cobertura de datos parcial" in item for item in negatives), "Cobertura parcial debe añadir negativo")
    checks.append("partial coverage limits conclusion")

    weak_critical_components = [
        _fake_component("Calidad fundamental", 90, 0.30, 0.90),
        _fake_component("Valoración", 85, 0.22, 0.40),
        _fake_component("Riesgo y forense", 88, 0.15, 0.90),
    ]

    red_flags = []
    negatives = []
    score, reason = _apply_quality_gates(88.0, 0.80, 0.80, weak_critical_components, red_flags, negatives)
    assert_true(score == 69.0, "Bloque crítico con baja confianza debe capar a 69")
    assert_true(reason is not None, "Bloque crítico débil debe devolver razón")
    assert_true(any("Confianza operativa limitada" in item for item in negatives), "Bloque crítico débil debe añadir negativo")
    checks.append("critical block confidence gate")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Scoring Quality Gates Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Scoring Quality Gates Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
