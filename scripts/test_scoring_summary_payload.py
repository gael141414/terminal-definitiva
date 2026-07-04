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
    from modulos.scoring_engine import ScoreComponent, ValueQuantScore

    checks: list[str] = []

    components = [
        ScoreComponent(
            name="Calidad fundamental",
            score=90.0,
            weight=0.30,
            confidence=0.90,
            positives=["ROIC alto"],
        ),
        ScoreComponent(
            name="Valoración",
            score=35.0,
            weight=0.22,
            confidence=0.85,
            negatives=["Múltiplo exigente"],
        ),
        ScoreComponent(
            name="Riesgo y forense",
            score=60.0,
            weight=0.15,
            confidence=0.40,
            red_flags=["Baja confianza forense"],
        ),
    ]

    score = ValueQuantScore(
        final_score=72.0,
        raw_score=84.0,
        quality_adjusted=True,
        quality_gate_reason="Confianza operativa limitada en bloques críticos.",
        decision_action="Revisión manual obligatoria",
        decision_notes=["El score fue ajustado por quality gates."],
        confidence=0.68,
        data_coverage=0.72,
        confidence_label="Media",
        confidence_notes=["Cobertura aceptable."],
        components=components,
        red_flags=["Baja confianza forense"],
        positives=["ROIC alto"],
        negatives=["Múltiplo exigente"],
        verdict="Atractiva con matices · calidad de datos limitada",
    )

    top = score.top_components(limit=2)
    assert_true(len(top) == 2, "top_components debe respetar el límite")
    assert_true(top[0]["name"] == "Calidad fundamental", "El mejor componente debe aparecer primero")
    assert_true("contribution" in top[0], "top_components debe incluir contribution")
    checks.append("top_components returns ranked contribution payload")

    weak = score.weakest_components(limit=1)
    assert_true(len(weak) == 1, "weakest_components debe respetar el límite")
    assert_true(weak[0]["name"] == "Valoración", "El componente con peor score debe aparecer primero")
    assert_true("negatives" in weak[0], "weakest_components debe incluir negatives")
    checks.append("weakest_components returns weakest block payload")

    payload = score.to_summary_payload(ticker="AAPL")
    assert_true(payload["ticker"] == "AAPL", "El payload debe preservar ticker")
    assert_true(payload["final_score"] == 72.0, "El payload debe exponer final_score")
    assert_true(payload["raw_score"] == 84.0, "El payload debe exponer raw_score")
    assert_true(payload["quality_adjusted"] is True, "El payload debe exponer quality_adjusted")
    assert_true(payload["decision_action"] == "Revisión manual obligatoria", "El payload debe exponer decision_action")
    assert_true(payload["top_components"][0]["name"] == "Calidad fundamental", "El payload debe incluir top_components")
    assert_true(payload["weakest_components"][0]["name"] == "Valoración", "El payload debe incluir weakest_components")
    assert_true(payload["red_flags"] == ["Baja confianza forense"], "El payload debe incluir red_flags")
    checks.append("summary payload exposes score, audit, guidance and component rankings")

    empty_payload = score.to_summary_payload()
    assert_true(empty_payload["ticker"] is None, "ticker debe ser opcional")
    checks.append("summary payload supports optional ticker")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Scoring Summary Payload Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Scoring Summary Payload Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
