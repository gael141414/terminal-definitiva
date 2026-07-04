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
            score=88.0,
            weight=0.30,
            confidence=0.90,
            positives=["ROIC alto"],
        ),
        ScoreComponent(
            name="Valoración",
            score=45.0,
            weight=0.22,
            confidence=0.80,
            negatives=["Múltiplo exigente"],
        ),
        ScoreComponent(
            name="Riesgo y forense",
            score=58.0,
            weight=0.15,
            confidence=0.42,
            red_flags=["Confianza forense crítica"],
        ),
    ]

    return ValueQuantScore(
        final_score=69.0,
        raw_score=83.0,
        quality_adjusted=True,
        quality_gate_reason="Confianza operativa limitada en bloques críticos.",
        decision_action="Revisión manual obligatoria",
        decision_notes=["El score fue ajustado por quality gates."],
        confidence=0.57,
        data_coverage=0.74,
        confidence_label="Media",
        confidence_notes=["Cobertura aceptable."],
        components=components,
        red_flags=["Confianza forense crítica"],
        positives=["ROIC alto"],
        negatives=["Múltiplo exigente"],
        verdict="Atractiva con matices · calidad de datos limitada",
    )


def run_contract_checks() -> list[str]:
    from modulos.analysis_store import build_research_snapshot
    from modulos.watchlist import _build_watchlist_row
    from modulos.watchlist_alerts import evaluate_watchlist_row

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

    snapshot = build_research_snapshot(
        ticker="AAPL",
        competitor="MSFT",
        valuequant_score=score,
        res_val=res_val,
        nota_buffett=82.0,
    )

    assert_true(snapshot["score_decision_action"] == "Revisión manual obligatoria", "Snapshot debe guardar action del score")
    assert_true(snapshot["score_raw_score"] == 83.0, "Snapshot debe guardar raw score")
    assert_true(snapshot["score_quality_adjusted"] is True, "Snapshot debe guardar quality_adjusted")
    assert_true(snapshot["score_quality_gate_reason"], "Snapshot debe guardar quality gate reason")
    assert_true(snapshot["score_confidence_label"] == "Media", "Snapshot debe guardar confidence label")
    assert_true(snapshot["score_red_flags_count"] == 1, "Snapshot debe contar red flags")
    assert_true(snapshot["score_top_components"], "Snapshot debe guardar top components")
    assert_true(snapshot["score_weakest_components"], "Snapshot debe guardar weakest components")
    checks.append("research snapshot persists score payload fields")

    item = {
        "target": snapshot.get("target"),
        "source": "Research Core",
        "last_saved_at": snapshot.get("saved_at"),
    }
    row = _build_watchlist_row(
        ticker="AAPL",
        item=item,
        analysis=snapshot,
        precio_actual=101.0,
        cambio_pct=1.2,
        target=float(snapshot.get("target") or 0.0),
        distancia_alerta="A un -5.0% de caer",
    )

    assert_true(row["Acción Score"] == "Revisión manual obligatoria", "Watchlist row debe exponer Acción Score")
    assert_true(row["Score bruto"] == 83.0, "Watchlist row debe exponer score bruto")
    assert_true(row["Ajuste Calidad"] is True, "Watchlist row debe exponer ajuste calidad")
    assert_true(row["Red Flags"] == 1, "Watchlist row debe exponer red flags")
    assert_true(isinstance(row["Prioridad Score"], float), "Watchlist row debe calcular prioridad score")
    assert_true("Revisión" in row["Bucket Score"] or "Riesgo" in row["Bucket Score"], "Watchlist row debe clasificar bucket")
    checks.append("watchlist row exposes score ranking fields")

    alerts = evaluate_watchlist_row(row)
    alert_titles = {alert.title for alert in alerts}
    assert_true("Red flags en score" in alert_titles, "Alertas deben detectar red flags del score")
    assert_true("Score ajustado por quality gates" in alert_titles, "Alertas deben detectar quality gates")
    checks.append("watchlist alerts consume score payload fields")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Watchlist Score Payload Integration Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Watchlist Score Payload Integration Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
