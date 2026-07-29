"""Columna "SEC" en _build_watchlist_row (Sub-fase 3c).

Integración ligera con el store real (Sub-fase 3a), aislada en un directorio
temporal: confirma que la fila de Watchlist refleja el resumen persistido
por el job nocturno, y que un ticker nunca verificado se distingue
visualmente de uno que coincide (nunca "sin verificar" == "coincide").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.watchlist import _build_watchlist_row
from modulos.sec_fmp_cross_validation import DISCREPANCY, MetricComparison
from modulos.sec_validation_store import save_sec_validation_result


@pytest.fixture(autouse=True)
def _aislar_en_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _minimal_row(ticker: str) -> dict:
    return _build_watchlist_row(
        ticker=ticker,
        item={"source": "Manual"},
        analysis={},
        precio_actual=100.0,
        cambio_pct=0.0,
        target=0.0,
        distancia_alerta="Sin Target",
    )


def test_ticker_nunca_verificado_muestra_sin_verificar():
    row = _minimal_row("ZZZZ")
    assert row["SEC"] == "⚪ Sin verificar"


def test_ticker_con_validacion_exitosa_sin_discrepancias():
    comp = MetricComparison(metric="Margen Bruto %", year="2024", fmp_value=46.2, sec_value=46.2, diff_pct=0.0, classification="coincide")
    save_sec_validation_result("AAPL", [comp], checked_at="2026-07-27T02:00:00+00:00")

    row = _minimal_row("AAPL")
    assert row["SEC"] == "✅ Coincide"


def test_ticker_con_discrepancia_no_se_confunde_con_sin_verificar():
    comp = MetricComparison(metric="ROIC %", year="2024", fmp_value=79.48, sec_value=92.67, diff_pct=16.6, classification=DISCREPANCY)
    save_sec_validation_result("MSFT", [comp], checked_at="2026-07-27T02:00:00+00:00")

    fila_msft = _minimal_row("MSFT")
    fila_nunca_verificada = _minimal_row("ZZZZ")

    assert fila_msft["SEC"] != fila_nunca_verificada["SEC"]
    assert "discrepancia" in fila_msft["SEC"].lower()
    assert "sin verificar" in fila_nunca_verificada["SEC"].lower()
