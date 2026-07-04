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


def _sample_score():
    from modulos.scoring_engine import ScoreComponent, ValueQuantScore

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
            score=42.0,
            weight=0.22,
            confidence=0.85,
            negatives=["Múltiplo exigente"],
        ),
        ScoreComponent(
            name="Riesgo y forense",
            score=68.0,
            weight=0.15,
            confidence=0.55,
            red_flags=["Confianza forense limitada"],
        ),
    ]

    return ValueQuantScore(
        final_score=69.0,
        raw_score=82.0,
        quality_adjusted=True,
        quality_gate_reason="Confianza operativa limitada en bloques críticos.",
        decision_action="Revisión manual obligatoria",
        decision_notes=[
            "El score fue ajustado por quality gates; no debe usarse como ranking directo.",
            "La acción es una guía de workflow interno, no una recomendación de compra o venta.",
        ],
        confidence=0.68,
        data_coverage=0.72,
        confidence_label="Media",
        confidence_notes=["Cobertura aceptable."],
        components=components,
        red_flags=["Confianza forense limitada"],
        positives=["ROIC alto"],
        negatives=["Múltiplo exigente"],
        verdict="Atractiva con matices · calidad de datos limitada",
    )


def run_contract_checks() -> list[str]:
    from modulos.investment_thesis import build_investment_thesis, thesis_to_markdown
    from modulos.research_report import build_research_report_markdown

    checks: list[str] = []
    score = _sample_score()
    res_val = {
        "precio_actual": 100.0,
        "valor_intrinseco": 120.0,
        "fcf_yield": 0.045,
        "earnings_yield": 0.04,
        "pe_actual": 25.0,
        "pfcf_actual": 22.0,
    }

    thesis = build_investment_thesis("AAPL", score, res_val, nota_buffett=81.0)

    assert_true(thesis.score_payload.get("ticker") == "AAPL", "La tesis debe conservar el payload del score")
    assert_true(thesis.score_decision_action == "Revisión manual obligatoria", "La tesis debe exponer decision_action del score")
    assert_true(thesis.score_quality_adjusted is True, "La tesis debe exponer quality_adjusted")
    assert_true(thesis.score_quality_gate_reason is not None, "La tesis debe exponer quality_gate_reason")
    assert_true(thesis.score_top_components, "La tesis debe exponer top_components")
    assert_true(thesis.score_weakest_components, "La tesis debe exponer weakest_components")
    assert_true(
        any(section.title == "Lectura del score institucional" for section in thesis.sections),
        "La tesis debe incluir sección de lectura institucional del score",
    )
    checks.append("investment thesis consumes score summary payload")

    thesis_md = thesis_to_markdown(thesis)
    assert_true("Acción del score" in thesis_md, "El markdown de tesis debe incluir acción del score")
    assert_true("Ajuste por calidad" in thesis_md, "El markdown de tesis debe incluir ajuste por calidad")
    checks.append("investment thesis markdown exposes score guidance")

    report_md = build_research_report_markdown(
        ticker="AAPL",
        ticker_competidor=None,
        valuequant_score=score,
        res_val=res_val,
        nota_buffett=81.0,
        res_is=None,
        res_bs=None,
        res_cf=None,
    )

    assert_true("Acción del score" in report_md, "El informe debe incluir acción del score")
    assert_true("Score bruto antes de gates" in report_md, "El informe debe incluir raw score")
    assert_true("Resumen institucional del score" in report_md, "El informe debe incluir resumen institucional")
    assert_true("Top componentes" in report_md, "El informe debe incluir top components")
    assert_true("Componentes más débiles" in report_md, "El informe debe incluir weakest components")
    assert_true("Motivo quality gate" in report_md, "El informe debe incluir motivo de quality gate")
    checks.append("research report exposes score payload in executive and score sections")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Report Score Payload Integration Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Report Score Payload Integration Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
