#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_analyses() -> dict[str, list[dict]]:
    return {
        "AAPL": [
            {
                "ticker": "AAPL",
                "saved_at": "2024-01-03T12:00:00+00:00",
                "valuequant_score": 76.0,
                "score_raw_score": 81.0,
                "score_decision_action": "Candidato prioritario",
                "score_confidence_label": "Alta",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "margin_of_safety": 0.12,
                "confidence": 0.84,
                "action": "Vigilar / estudiar entrada",
            },
            {
                "ticker": "AAPL",
                "saved_at": "2024-02-01T12:00:00+00:00",
                "valuequant_score": 58.0,
                "score_raw_score": 62.0,
                "score_decision_action": "Esperar más datos",
                "score_confidence_label": "Media",
                "score_quality_adjusted": False,
                "score_red_flags_count": 0,
                "margin_of_safety": -0.03,
                "confidence": 0.62,
                "action": "Mantener seguimiento",
            },
        ],
        "XYZ": [
            {
                "ticker": "XYZ",
                "saved_at": "2024-01-03T12:00:00+00:00",
                "valuequant_score": 42.0,
                "score_raw_score": 55.0,
                "score_decision_action": "Baja prioridad",
                "score_confidence_label": "Baja",
                "score_quality_adjusted": False,
                "score_red_flags_count": 1,
                "margin_of_safety": -0.20,
                "confidence": 0.40,
                "action": "Evitar",
            }
        ],
    }


def _price_series(start: str, base: float, step: float) -> pd.Series:
    idx = pd.bdate_range(start, periods=180)
    values = [base + i * step for i in range(len(idx))]
    return pd.Series(values, index=idx, dtype=float)


def run_contract_checks() -> list[str]:
    from modulos.signal_backtesting import (
        build_signal_events,
        classify_snapshot_signal,
        evaluate_signal_events,
        run_basic_signal_backtest,
        summarize_signal_backtest,
    )

    checks: list[str] = []
    sample = _sample_analyses()

    assert_true(classify_snapshot_signal(sample["AAPL"][0]) == "BUY", "Snapshot prioritario debe clasificar BUY")
    assert_true(classify_snapshot_signal(sample["AAPL"][1]) == "WATCH", "Snapshot intermedio debe clasificar WATCH")
    assert_true(classify_snapshot_signal(sample["XYZ"][0]) == "AVOID", "Snapshot con red flags debe clasificar AVOID")
    checks.append("snapshots classify into BUY/WATCH/AVOID")

    events = build_signal_events(sample)
    assert_true(len(events) == 3, "Debe construir tres eventos")
    assert_true(set(events["Señal"]) == {"BUY", "WATCH", "AVOID"}, "Debe preservar las tres clases de señal")
    checks.append("saved analyses convert into signal events")

    price_lookup = {
        "AAPL": _price_series("2024-01-02", 100.0, 0.35),
        "XYZ": _price_series("2024-01-02", 100.0, -0.25),
    }
    results = evaluate_signal_events(events, horizon_days=90, price_lookup=price_lookup)
    assert_true(len(results) == 3, "Debe evaluar tres eventos con precios")
    assert_true("Retorno Futuro" in results.columns, "Debe calcular retorno futuro")
    assert_true(bool(results[results["Señal"] == "BUY"]["Hit"].iloc[0]) is True, "BUY con retorno positivo debe acertar")
    assert_true(bool(results[results["Señal"] == "AVOID"]["Hit"].iloc[0]) is True, "AVOID con retorno negativo debe acertar")
    checks.append("signal events evaluate forward returns and hits")

    summary_payload = summarize_signal_backtest(results)
    summary = summary_payload["summary"]
    assert_true(summary.total_signals == 3, "Resumen debe contar señales")
    assert_true(summary.buy_signals == 1, "Resumen debe contar BUY")
    assert_true(summary.avoid_signals == 1, "Resumen debe contar AVOID")
    assert_true(summary.hit_rate_buy == 1.0, "Hit rate BUY debe ser 100% en muestra")
    assert_true(not summary_payload["by_signal"].empty, "Resumen por señal no debe estar vacío")
    checks.append("signal backtest summary computes aggregates")

    with patch("modulos.signal_backtesting.load_saved_analyses", return_value=sample):
        _, pipeline_results, pipeline_summary = run_basic_signal_backtest(
            tickers=["AAPL", "XYZ"],
            horizon_days=90,
            price_lookup=price_lookup,
        )
    assert_true(len(pipeline_results) == 3, "Pipeline debe evaluar eventos filtrados")
    assert_true(pipeline_summary["summary"].total_signals == 3, "Pipeline debe devolver resumen agregado")
    checks.append("basic signal backtest pipeline works end to end")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Basic Signal Backtesting Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Basic Signal Backtesting Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
