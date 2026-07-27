"""Alerta SEC EDGAR en watchlist_alerts.py (Sub-fase 3c).

Cubre que evaluate_watchlist_row genera una alerta categoría "SEC EDGAR"
cuando el resumen compacto persistido por el job nocturno (Sub-fase 3b)
tiene discrepancias o desalineamientos de periodo, y que NUNCA la genera
cuando no hay verificación previa o cuando coincide del todo — "sin
verificar" no es una alerta, se refleja en la columna de Watchlist, no aquí.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import watchlist_alerts


def _row(ticker="AAPL", **overrides) -> dict:
    base = {
        "Ticker": ticker,
        "Precio Actual": 200.0,
        "Precio Objetivo": "-",
        "ValueQuant": 60.0,
        "Margen Seguridad": 0.0,
        "Acción Research": "-",
        "Régimen Valoración": "-",
        "Fuente": "Manual",
        "Acción Score": "-",
        "Confianza": 0.7,
        "Nivel confianza": "media",
        "Ajuste Calidad": False,
        "Quality Gate": "-",
        "Red Flags": 0,
    }
    base.update(overrides)
    return base


@pytest.fixture
def _sin_verificacion(monkeypatch):
    monkeypatch.setattr(watchlist_alerts, "sec_validation_summary", lambda ticker: {})


def _con_resumen(monkeypatch, summary: dict):
    monkeypatch.setattr(watchlist_alerts, "sec_validation_summary", lambda ticker: summary)


def _sec_alerts(alerts):
    return [a for a in alerts if a.category == "SEC EDGAR"]


def test_sin_verificacion_previa_no_genera_alerta_sec(_sin_verificacion):
    alerts = watchlist_alerts.evaluate_watchlist_row(_row())
    assert _sec_alerts(alerts) == []


def test_intento_fallido_sin_exito_previo_no_genera_alerta_sec(monkeypatch):
    _con_resumen(monkeypatch, {"last_attempt_at": "2026-07-27T02:00:00+00:00", "last_attempt_status_code": "rate_limited"})
    alerts = watchlist_alerts.evaluate_watchlist_row(_row())
    assert _sec_alerts(alerts) == []


def test_exito_sin_discrepancias_no_genera_alerta_sec(monkeypatch):
    _con_resumen(monkeypatch, {
        "last_successful_check_at": "2026-07-27T02:00:00+00:00",
        "discrepancy_count": 0,
        "period_misaligned_count": 0,
    })
    alerts = watchlist_alerts.evaluate_watchlist_row(_row())
    assert _sec_alerts(alerts) == []


def test_discrepancia_leve_genera_alerta_prioridad_media(monkeypatch):
    _con_resumen(monkeypatch, {
        "last_successful_check_at": "2026-07-27T02:00:00+00:00",
        "discrepancy_count": 2,
        "period_misaligned_count": 0,
        "worst_metric": "SG&A % (s/MB)",
        "worst_diff_pct": 4.5,
    })
    sec_alerts = _sec_alerts(watchlist_alerts.evaluate_watchlist_row(_row()))
    assert len(sec_alerts) == 1
    assert sec_alerts[0].priority == "Media"
    assert sec_alerts[0].title == "Discrepancia con SEC EDGAR"
    assert "SG&A" in sec_alerts[0].detail


def test_discrepancia_severa_genera_alerta_prioridad_alta(monkeypatch):
    _con_resumen(monkeypatch, {
        "last_successful_check_at": "2026-07-27T02:00:00+00:00",
        "discrepancy_count": 3,
        "period_misaligned_count": 0,
        "worst_metric": "ROIC %",
        "worst_diff_pct": 22.0,
    })
    sec_alerts = _sec_alerts(watchlist_alerts.evaluate_watchlist_row(_row()))
    assert len(sec_alerts) == 1
    assert sec_alerts[0].priority == "Alta"
    assert sec_alerts[0].score > 70


def test_periodo_no_alineado_genera_alerta_prioridad_baja(monkeypatch):
    _con_resumen(monkeypatch, {
        "last_successful_check_at": "2026-07-27T02:00:00+00:00",
        "discrepancy_count": 0,
        "period_misaligned_count": 1,
    })
    sec_alerts = _sec_alerts(watchlist_alerts.evaluate_watchlist_row(_row()))
    assert len(sec_alerts) == 1
    assert sec_alerts[0].priority == "Baja"
    assert sec_alerts[0].title == "Posible restatement SEC EDGAR"


def test_alerta_sec_convive_con_las_demas_alertas_de_la_fila(monkeypatch):
    _con_resumen(monkeypatch, {
        "last_successful_check_at": "2026-07-27T02:00:00+00:00",
        "discrepancy_count": 1,
        "period_misaligned_count": 0,
        "worst_diff_pct": 15.0,
    })
    alerts = watchlist_alerts.evaluate_watchlist_row(_row(**{"Red Flags": 2}))
    categorias = {a.category for a in alerts}
    assert "SEC EDGAR" in categorias
    assert "Score" in categorias  # la alerta de red flags sigue generandose
