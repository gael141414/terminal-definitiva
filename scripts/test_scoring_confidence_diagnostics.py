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


def _component(name: str, confidence: float):
    from modulos.scoring_engine import ScoreComponent

    return ScoreComponent(
        name=name,
        score=70,
        weight=0.10,
        confidence=confidence,
    )


def run_contract_checks() -> list[str]:
    from modulos.scoring_engine import ValueQuantScore, _confidence_diagnostics

    checks: list[str] = []

    strong_components = [
        _component("Calidad fundamental", 0.90),
        _component("Valoración", 0.88),
        _component("Riesgo y forense", 0.86),
        _component("Momentum y timing", 0.80),
    ]
    label, notes = _confidence_diagnostics(0.82, 0.82, strong_components)
    assert_true(label == "Alta", "Cobertura alta debe etiquetarse como Alta")
    assert_true(any("Cobertura suficiente" in note for note in notes), "Confianza alta debe explicar cobertura suficiente")
    assert_true(any("no equivale a confianza predictiva" in note for note in notes), "Debe separar confianza operativa y predictiva")
    checks.append("high confidence diagnostics")

    medium_components = [
        _component("Calidad fundamental", 0.70),
        _component("Valoración", 0.58),
        _component("Riesgo y forense", 0.62),
        _component("Momentum y timing", 0.50),
    ]
    label, notes = _confidence_diagnostics(0.62, 0.62, medium_components)
    assert_true(label == "Media", "Cobertura media debe etiquetarse como Media")
    assert_true(any("Momentum y timing" in note for note in notes), "Debe listar bloques débiles")
    checks.append("medium confidence diagnostics")

    low_components = [
        _component("Calidad fundamental", 0.40),
        _component("Valoración", 0.42),
        _component("Riesgo y forense", 0.60),
    ]
    label, notes = _confidence_diagnostics(0.40, 0.40, low_components)
    assert_true(label == "Baja", "Cobertura baja debe etiquetarse como Baja")
    assert_true(any("orientación preliminar" in note for note in notes), "Confianza baja debe advertir lectura preliminar")
    assert_true(any("bloques críticos" in note for note in notes), "Debe advertir bloques críticos débiles")
    checks.append("low confidence diagnostics")

    score = ValueQuantScore(
        final_score=60,
        confidence=0.50,
        data_coverage=0.50,
        confidence_label="Media",
        confidence_notes=["nota de prueba"],
        components=[],
        red_flags=[],
        positives=[],
        negatives=[],
        verdict="Neutral / exigente",
    )
    assert_true(score.confidence_label == "Media", "ValueQuantScore debe exponer confidence_label")
    assert_true(score.confidence_notes == ["nota de prueba"], "ValueQuantScore debe exponer confidence_notes")
    checks.append("score exposes confidence diagnostics")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Scoring Confidence Diagnostics Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Scoring Confidence Diagnostics Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
