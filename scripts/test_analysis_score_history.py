#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_history() -> dict[str, list[dict]]:
    return {
        "AAPL": [
            {
                "ticker": "AAPL",
                "saved_at": "2026-07-04T18:00:00+00:00",
                "valuequant_score": 72.0,
                "score_raw_score": 78.0,
                "buffett_score": 81.0,
                "margin_of_safety": 0.12,
                "confidence": 0.82,
                "data_coverage": 0.91,
                "score_confidence_label": "Alta",
                "score_decision_action": "Candidato prioritario",
                "score_quality_adjusted": False,
                "score_quality_gate_reason": None,
                "score_red_flags_count": 0,
                "valuation_regime": "Razonable",
                "target": 110.0,
                "action": "Vigilar / estudiar",
            },
            {
                "ticker": "AAPL",
                "saved_at": "2026-06-04T18:00:00+00:00",
                "score_payload": {
                    "final_score": 67.0,
                    "raw_score": 71.0,
                    "confidence": 0.76,
                    "data_coverage": 0.85,
                    "confidence_label": "Media",
                    "decision_action": "Atractiva con matices",
                    "quality_adjusted": False,
                    "red_flags": [],
                },
                "buffett_score": 78.0,
                "margin_of_safety": 0.05,
                "valuation_regime": "Aceptable",
                "target": 100.0,
                "action": "Vigilar",
            },
            {
                "ticker": "AAPL",
                "saved_at": "2026-05-04T18:00:00+00:00",
                "valuequant_score": 60.0,
                "score_raw_score": 65.0,
                "buffett_score": 75.0,
                "margin_of_safety": -0.04,
                "confidence": 0.68,
                "data_coverage": 0.80,
                "score_confidence_label": "Media",
                "score_decision_action": "Esperar más datos",
                "score_quality_adjusted": True,
                "score_quality_gate_reason": "Cobertura limitada.",
                "score_red_flags_count": 1,
                "valuation_regime": "Exigente",
                "target": 90.0,
                "action": "Mantener",
            },
        ]
    }


def run_contract_checks() -> list[str]:
    from modulos.analysis_store import score_evolution_summary, score_history_for_ticker

    checks: list[str] = []
    sample = _sample_history()

    with patch("modulos.analysis_store.load_saved_analyses", return_value=sample):
        df = score_history_for_ticker("AAPL")
        assert_true(len(df) == 3, "Debe devolver tres observaciones")
        assert_true(list(df["VQ Score"]) == [60.0, 67.0, 72.0], "Debe ordenar cronológicamente de antiguo a reciente")
        assert_true(df.iloc[-1]["Acción Score"] == "Candidato prioritario", "Debe preservar acción score")
        assert_true(df.iloc[0]["Quality Gate"] == "Cobertura limitada.", "Debe preservar quality gate histórico")
        assert_true(int(df.iloc[0]["Red Flags"]) == 1, "Debe preservar red flags históricos")
        checks.append("score history normalizes and orders snapshots")

        limited = score_history_for_ticker("AAPL", limit=2)
        assert_true(len(limited) == 2, "limit debe conservar las observaciones más recientes")
        assert_true(list(limited["VQ Score"]) == [67.0, 72.0], "limit debe devolver cola cronológica reciente")
        checks.append("score history supports recent limit")

        summary = score_evolution_summary("AAPL")
        assert_true(summary["observations"] == 3, "Resumen debe contar observaciones")
        assert_true(summary["latest_score"] == 72.0, "Resumen debe usar último score")
        assert_true(summary["previous_score"] == 67.0, "Resumen debe usar score anterior")
        assert_true(summary["delta_score"] == 5.0, "Resumen debe calcular delta de score")
        assert_true(summary["trend_label"] == "Mejora", "Delta positivo debe marcar mejora")
        assert_true(summary["latest_red_flags"] == 0, "Resumen debe exponer red flags actuales")
        checks.append("score evolution summary computes deltas and trend")

        empty = score_history_for_ticker("MSFT")
        assert_true(empty.empty, "Ticker sin histórico debe devolver DataFrame vacío")
        empty_summary = score_evolution_summary("MSFT")
        assert_true(empty_summary["trend_label"] == "Sin histórico", "Ticker sin histórico debe tener resumen vacío")
        checks.append("empty history is handled defensively")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Analysis Score History Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Analysis Score History Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
