#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _score(**kwargs):
    defaults = {
        "final_score": 78.0,
        "raw_score": 82.0,
        "data_coverage": 0.88,
        "confidence": 0.76,
        "predictive_confidence": 0.68,
        "model_version": "VQ_SCORE_TEST",
        "decision_action": "Candidato prioritario",
        "quality_adjusted": False,
        "quality_gate_reason": "",
        "red_flags": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def run_contract_checks() -> list[str]:
    from modulos.research_core import (
        build_research_ux_summary,
        build_research_workflow_steps,
        _score_bucket,
    )

    checks: list[str] = []

    summary = build_research_ux_summary(
        ticker_input="aapl",
        ticker_competidor="msft",
        nota_buffett=71.5,
        valuequant_score=_score(),
    )

    assert_true(summary["ticker"] == "AAPL", "Ticker debe normalizarse a mayúsculas")
    assert_true(summary["competitor"] == "MSFT", "Competidor debe normalizarse a mayúsculas")
    assert_true(summary["final_score"] == 78.0, "Debe extraer score final")
    assert_true(summary["primary_action"] == "Candidato prioritario", "Debe priorizar acción del score")
    assert_true(summary["risk_state"] == "Controlado", "Sin flags debe mostrar riesgo controlado")
    assert_true(summary["priority_label"] == "Prioridad media", "Score 78 debe ser prioridad media")
    checks.append("research UX summary extracts decision payload")

    high_bucket = _score_bucket(85.0)
    low_bucket = _score_bucket(42.0)
    assert_true(high_bucket[1] == "Alta prioridad", "Score alto debe ser alta prioridad")
    assert_true(low_bucket[1] == "Descartar / recalcular", "Score bajo debe recomendar descarte/recalcular")
    checks.append("score buckets map score into UX priorities")

    alert_summary = build_research_ux_summary(
        ticker_input="xyz",
        ticker_competidor="",
        nota_buffett=45.0,
        valuequant_score=_score(final_score=61.0, quality_adjusted=True, quality_gate_reason="Quality gate aplicado"),
    )
    assert_true(alert_summary["risk_state"] == "Alerta", "Quality gate debe generar alerta")
    assert_true("Quality gate" in alert_summary["risk_detail"], "Detalle de alerta debe conservar razón del gate")
    checks.append("quality gates surface as visible UX alerts")

    steps = build_research_workflow_steps(summary)
    assert_true(len(steps) >= 6, "Debe haber al menos seis pasos de workflow")
    assert_true({"Paso", "Estado", "Lectura"}.issubset(steps[0].keys()), "Cada paso debe tener campos UX")
    assert_true(any(step["Estado"] == "OK" for step in steps), "Debe haber pasos OK")
    assert_true(any(step["Estado"] == "Acción" for step in steps), "Debe haber paso accionable")
    checks.append("research workflow steps are generated for the command center")

    incomplete = build_research_ux_summary(
        ticker_input="none",
        ticker_competidor="",
        nota_buffett=0.0,
        valuequant_score=None,
    )
    incomplete_steps = build_research_workflow_steps(incomplete)
    assert_true(incomplete["verdict"] == "Pendiente", "Sin score debe quedar pendiente")
    assert_true(any(step["Estado"] in {"Pendiente", "Revisar"} for step in incomplete_steps), "Sin score debe pedir revisión")
    checks.append("missing score input is handled safely")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Research Core UX Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Research Core UX Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
