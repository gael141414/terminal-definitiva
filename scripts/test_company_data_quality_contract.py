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


class FakeTicker:
    info = {
        "sector": "Technology",
        "trailingPE": None,
        "priceToBook": "bad",
        "enterpriseToEbitda": float("inf"),
        "enterpriseToRevenue": "7.5",
        "heldPercentInsiders": 0.123,
        "heldPercentInstitutions": 0.456,
        "shortRatio": "2.5",
    }

    insider_transactions = pd.DataFrame(
        {
            "Start Date": ["2024-01-01", "bad-date"],
            "Insider": ["A", "B"],
            "Position": ["CEO", "CFO"],
            "Transaction": ["Buy", "Sell"],
            "Value": ["1000", None],
            "Shares": [10, 5],
            "Noise": ["x", "y"],
        }
    )


class EmptyTicker:
    info = {}
    insider_transactions = pd.DataFrame()


def run_contract_checks() -> list[str]:
    import modulos.company_data_helpers as helpers

    checks: list[str] = []
    original_ticker = helpers.yf.Ticker

    try:
        helpers.yf.Ticker = lambda ticker: FakeTicker()

        insiders = helpers.obtener_transacciones_insiders("AAA")
        assert_true(isinstance(insiders, pd.DataFrame), "Insiders válido debe devolver DataFrame")
        assert_true("Noise" not in insiders.columns, "Debe filtrar columnas no deseadas")
        assert_true("Start Date" in insiders.columns, "Debe conservar Start Date si existe")
        assert_true(len(insiders) == 2, "Debe conservar filas disponibles")
        checks.append("insider transactions dataframe")

        sector, metrica, valor, racionalidad, multiplos, umbral = helpers.obtener_valoracion_sectorial("AAA")
        assert_true(sector == "Technology", "Debe leer sector Technology")
        assert_true(metrica == "EV / Ventas", "Technology debe usar EV / Ventas")
        assert_true(valor == 7.5, "Debe convertir múltiplo numérico válido")
        assert_true(multiplos["P/E (Price/Earnings)"] == 0.0, "None debe limpiarse a 0.0")
        assert_true(multiplos["P/B (Price/Book)"] == 0.0, "Texto inválido debe limpiarse a 0.0")
        assert_true(multiplos["EV / EBITDA"] == 0.0, "Inf debe limpiarse a 0.0")
        assert_true(umbral == 5.0, "Technology debe usar umbral 5.0")
        checks.append("sector valuation sanitization")

        ownership = helpers.obtener_datos_directiva("AAA")
        assert_true(ownership == (12.3, 45.6, 2.5), "Debe convertir ownership y short ratio")
        checks.append("ownership sanitization")

        helpers.yf.Ticker = lambda ticker: EmptyTicker()

        assert_true(helpers.obtener_transacciones_insiders("EMPTY") is None, "Insiders vacío debe devolver None")
        checks.append("empty insider transactions")

        empty_sector = helpers.obtener_valoracion_sectorial("EMPTY")
        assert_true(empty_sector[0] is None, "Info vacío debe bloquear valoración sectorial")
        checks.append("empty valuation info")

        empty_ownership = helpers.obtener_datos_directiva("EMPTY")
        assert_true(empty_ownership == (None, None, None), "Info vacío debe bloquear directiva")
        checks.append("empty ownership info")

    finally:
        helpers.yf.Ticker = original_ticker

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== Company Data Quality Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== Company Data Quality Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
