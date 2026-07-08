#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _sample_results() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Ticker": "AAA",
                "Señal": "BUY",
                "ValueQuant": 82.0,
                "Confianza": 0.80,
                "Confianza Predictiva": 0.82,
                "Retorno Futuro": 0.12,
                "Hit": True,
            },
            {
                "Ticker": "BBB",
                "Señal": "BUY",
                "ValueQuant": 76.0,
                "Confianza": 0.78,
                "Confianza Predictiva": 0.80,
                "Retorno Futuro": -0.04,
                "Hit": False,
            },
            {
                "Ticker": "CCC",
                "Señal": "AVOID",
                "ValueQuant": 44.0,
                "Confianza": 0.62,
                "Confianza Predictiva": 0.60,
                "Retorno Futuro": -0.10,
                "Hit": True,
            },
            {
                "Ticker": "DDD",
                "Señal": "AVOID",
                "ValueQuant": 48.0,
                "Confianza": 0.58,
                "Confianza Predictiva": 0.55,
                "Retorno Futuro": 0.05,
                "Hit": False,
            },
            {
                "Ticker": "EEE",
                "Señal": "WATCH",
                "ValueQuant": 60.0,
                "Confianza": 0.50,
                "Confianza Predictiva": 0.52,
                "Retorno Futuro": 0.01,
                "Hit": None,
            },
        ]
    )


def run_contract_checks() -> list[str]:
    from modulos.signal_backtesting import (
        apply_calibrated_confidence_to_results,
        build_predictive_confidence_calibration,
        calibration_eligible_results,
        summarize_predictive_confidence_calibration,
    )

    checks: list[str] = []
    results = _sample_results()

    eligible = calibration_eligible_results(results)
    assert_true(len(eligible) == 4, "WATCH sin hit no debe entrar en calibración")
    assert_true("Confianza Calibración" in eligible.columns, "Debe crear confianza de calibración")
    assert_true("Banda Confianza" in eligible.columns, "Debe crear banda de confianza")
    checks.append("eligible calibration sample filters observable directional signals")

    table = build_predictive_confidence_calibration(results)
    assert_true(not table.empty, "Tabla de calibración no debe estar vacía")
    expected_cols = {
        "Banda Confianza",
        "Señales",
        "Confianza_Media",
        "Hit_Rate_Observado",
        "Gap_Calibración",
        "Error_Absoluto",
    }
    assert_true(expected_cols.issubset(set(table.columns)), "Tabla de calibración debe tener columnas esperadas")
    assert_true(float(table["Error_Absoluto"].max()) >= 0.0, "Error absoluto debe ser numérico")
    checks.append("calibration table compares expected confidence with observed hit rate")

    summary = summarize_predictive_confidence_calibration(results)
    assert_true(summary["eligible_signals"] == 4, "Resumen debe contar señales calibrables")
    assert_true(0.0 <= summary["reliability_score"] <= 1.0, "Fiabilidad debe estar entre 0 y 1")
    assert_true(summary["label"] in {"Muestra insuficiente", "Bien calibrada", "Calibración aceptable", "Mal calibrada"}, "Etiqueta inválida")
    assert_true(summary["table"] is not None and not summary["table"].empty, "Resumen debe incluir tabla")
    checks.append("calibration summary computes reliability score and label")

    enriched = apply_calibrated_confidence_to_results(results)
    assert_true("Banda Confianza" in enriched.columns, "Resultados enriquecidos deben incluir banda")
    assert_true("Gap Banda" in enriched.columns, "Resultados enriquecidos deben incluir gap por banda")
    assert_true(enriched["Gap Banda"].notna().sum() >= 4, "Debe mapear gap a señales calibrables")
    checks.append("calibration diagnostics are mapped back to event results")

    no_data = summarize_predictive_confidence_calibration(pd.DataFrame())
    assert_true(no_data["eligible_signals"] == 0, "Sin datos debe devolver cero señales")
    assert_true(no_data["label"] == "Sin datos suficientes", "Sin datos debe devolver etiqueta explícita")
    checks.append("empty calibration input is handled safely")

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Predictive Confidence Calibration Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Predictive Confidence Calibration Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
