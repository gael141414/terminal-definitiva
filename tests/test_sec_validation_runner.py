"""Runner del job nocturno de validación cruzada SEC↔FMP (Sub-fase 3b).

Deterministas, sin red real: FMP, downloader.py (SEC) y el envío a Telegram
se mockean en el límite del módulo (mismo criterio que test_data_provider_errors.py
mockeando requests.get, o test_sec_edgar_downloader.py mockeando Company) — la
validación con datos reales de verdad se hizo aparte, manualmente, y se
describe en el informe de la tarea, no aquí (no se puede depender de red real
en la suite por defecto).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import downloader
import modulos.sec_validation_runner as runner
from modulos.data_provider_errors import INVALID_TICKER, NO_DATA, RATE_LIMITED
from modulos.sec_fmp_cross_validation import DISCREPANCY, MATCH, PERIOD_MISALIGNED, MetricComparison


@pytest.fixture(autouse=True)
def _aislar_en_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _comp(classification, *, metric="Margen Bruto %", year="2024", diff_pct=0.0, **kw) -> MetricComparison:
    defaults = dict(fmp_value=46.21, sec_value=46.21, note="")
    defaults.update(kw)
    return MetricComparison(metric=metric, year=year, diff_pct=diff_pct, classification=classification, **defaults)


# ---------------------------------------------------------------------------
# select_tickers_to_process: rotación "el mas antiguo sin verificar primero"
# ---------------------------------------------------------------------------


def test_select_tickers_todos_nunca_verificados_entran_todos():
    watchlist = {"AAPL": {}, "MSFT": {}, "NVDA": {}}
    seleccion = runner.select_tickers_to_process(watchlist, max_tickers=10)
    assert set(seleccion) == {"AAPL", "MSFT", "NVDA"}


def test_select_tickers_respeta_el_tope():
    watchlist = {t: {} for t in ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]}
    seleccion = runner.select_tickers_to_process(watchlist, max_tickers=2)
    assert len(seleccion) == 2


def test_select_tickers_nunca_verificado_va_antes_que_uno_ya_verificado():
    from modulos.sec_validation_store import save_sec_validation_result

    save_sec_validation_result("AAPL", [_comp(MATCH)], checked_at="2026-07-20T02:00:00+00:00")
    watchlist = {"AAPL": {}, "MSFT": {}}
    seleccion = runner.select_tickers_to_process(watchlist, max_tickers=10)
    assert seleccion[0] == "MSFT"  # nunca verificado, va primero
    assert seleccion[1] == "AAPL"


def test_select_tickers_el_intento_mas_antiguo_va_primero():
    from modulos.sec_validation_store import save_sec_validation_result

    save_sec_validation_result("AAPL", [_comp(MATCH)], checked_at="2026-07-25T02:00:00+00:00")
    save_sec_validation_result("MSFT", [_comp(MATCH)], checked_at="2026-07-20T02:00:00+00:00")
    watchlist = {"AAPL": {}, "MSFT": {}}
    seleccion = runner.select_tickers_to_process(watchlist, max_tickers=10)
    assert seleccion == ["MSFT", "AAPL"]  # MSFT se verifico hace mas tiempo


def test_select_tickers_un_fallo_reciente_no_queda_bloqueado_detras_de_exitos_antiguos():
    """Un ticker que fallo ANOCHE (rate limit) debe poder reintentarse pronto,
    no quedar atascado detras de tickers con exito hace semanas — por eso la
    rotacion usa last_attempt_at, no last_successful_check_at."""
    from modulos.sec_validation_store import save_sec_validation_result

    save_sec_validation_result("AAPL", [_comp(MATCH)], checked_at="2026-06-01T02:00:00+00:00")
    save_sec_validation_result("MSFT", [], status_code=RATE_LIMITED, checked_at="2026-07-27T02:00:00+00:00")
    watchlist = {"AAPL": {}, "MSFT": {}}
    seleccion = runner.select_tickers_to_process(watchlist, max_tickers=10)
    # AAPL lleva sin intentarse desde junio; MSFT desde anoche -> AAPL primero.
    assert seleccion == ["AAPL", "MSFT"]


def test_select_tickers_watchlist_vacia():
    assert runner.select_tickers_to_process({}, max_tickers=10) == []


# ---------------------------------------------------------------------------
# build_sec_validation_telegram_message
# ---------------------------------------------------------------------------


def test_mensaje_telegram_vacio_es_none():
    assert runner.build_sec_validation_telegram_message({}) is None


def test_mensaje_telegram_agrupado_por_ticker():
    payload = {
        "AAPL": [_comp(DISCREPANCY, metric="ROIC %", diff_pct=16.6, fmp_value=79.48, sec_value=92.67)],
        "MSFT": [_comp(PERIOD_MISALIGNED, metric="Margen Bruto %", note="posible restatement",
                        fmp_period_end="2023-06-30", sec_period_end="2022-12-31")],
    }
    mensaje = runner.build_sec_validation_telegram_message(payload)
    assert mensaje is not None
    assert "AAPL" in mensaje
    assert "MSFT" in mensaje
    assert "ROIC %" in mensaje
    assert "79.48" in mensaje and "92.67" in mensaje
    assert "+16.6%" in mensaje
    assert "restatement" in mensaje
    assert "2023-06-30" in mensaje and "2022-12-31" in mensaje
    assert "Discrepancias SEC" in mensaje


def test_mensaje_telegram_no_es_json_crudo():
    payload = {"AAPL": [_comp(DISCREPANCY, diff_pct=10.0)]}
    mensaje = runner.build_sec_validation_telegram_message(payload)
    assert "{" not in mensaje and "MetricComparison" not in mensaje


# ---------------------------------------------------------------------------
# _process_ticker: orquestacion FMP + SEC + comparacion, mockeados
# ---------------------------------------------------------------------------


def _fmp_ok(*_a, **_k):
    df = pd.DataFrame({"revenue": [100.0]}, index=pd.to_datetime(["2024-09-30"]))
    return df, df, df, df


def test_process_ticker_sin_datos_fmp_devuelve_no_data(monkeypatch):
    monkeypatch.setattr(runner, "extraer_datos_fundamentales_fmp", lambda *a, **k: (None, None, None, None))
    resultado = runner._process_ticker("ZZZZ", años=5)
    assert resultado.ok is False
    assert resultado.status_code == NO_DATA
    assert resultado.comparisons_count == 0


def test_process_ticker_sec_falla_devuelve_su_status_code(monkeypatch):
    monkeypatch.setattr(runner, "extraer_datos_fundamentales_fmp", _fmp_ok)
    monkeypatch.setattr(
        downloader, "obtener_estados_financieros_con_diagnostico",
        lambda *a, **k: (None, None, None, INVALID_TICKER),
    )
    resultado = runner._process_ticker("AAPL", años=5)
    assert resultado.ok is False
    assert resultado.status_code == INVALID_TICKER


def test_process_ticker_exito_persiste_y_devuelve_comparaciones(monkeypatch):
    monkeypatch.setattr(runner, "extraer_datos_fundamentales_fmp", _fmp_ok)
    monkeypatch.setattr(
        downloader, "obtener_estados_financieros_con_diagnostico",
        lambda *a, **k: (_fmp_ok()[0], _fmp_ok()[0], _fmp_ok()[0], None),
    )
    comparaciones_fake = [_comp(MATCH), _comp(DISCREPANCY, metric="ROIC %", diff_pct=12.0)]
    monkeypatch.setattr(runner, "comparar_estados_financieros", lambda **k: comparaciones_fake)

    resultado = runner._process_ticker("AAPL", años=5)
    assert resultado.ok is True
    assert resultado.status_code is None
    assert resultado.comparisons_count == 2
    assert len(resultado.new_discrepancies) == 1  # primera corrida: la discrepancia es "nueva"

    from modulos.sec_validation_store import sec_validation_summary
    resumen = sec_validation_summary("AAPL")
    assert resumen["discrepancy_count"] == 1


# ---------------------------------------------------------------------------
# run_sec_validation_batch: orquestacion completa (pausas, log, telegram)
# ---------------------------------------------------------------------------


def _fake_process_ticker_factory(resultados_por_ticker):
    def _fake(ticker, *, años):
        return resultados_por_ticker[ticker]
    return _fake


def test_batch_pausa_entre_tickers_pero_no_tras_el_ultimo(monkeypatch):
    from modulos.sec_validation_runner import TickerRunResult

    resultados = {
        "AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=1),
        "MSFT": TickerRunResult(ticker="MSFT", ok=True, status_code=None, comparisons_count=1),
    }
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}, "MSFT": {}})
    sleeps = []
    monkeypatch.setattr(runner.time, "sleep", lambda s: sleeps.append(s))

    resultado = runner.run_sec_validation_batch(max_tickers=10, inter_ticker_pause_seconds=1.5)
    assert len(resultado.ticker_results) == 2
    assert sleeps == [1.5]  # una pausa entre 2 tickers, ninguna al final


def test_batch_registra_evento_de_automation_log(monkeypatch):
    from modulos.sec_validation_runner import TickerRunResult

    resultados = {"AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=3)}
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}})

    llamadas = []
    monkeypatch.setattr(
        runner, "log_sec_validation_run",
        lambda **kwargs: llamadas.append(kwargs),
    )
    runner.run_sec_validation_batch(max_tickers=10)
    assert len(llamadas) == 1
    assert llamadas[0]["tickers_processed"] == 1
    assert llamadas[0]["tickers_failed"] == 0


def test_batch_sin_send_telegram_no_envia_aunque_haya_discrepancias_nuevas(monkeypatch):
    from modulos.sec_validation_runner import TickerRunResult

    nuevas = [_comp(DISCREPANCY, diff_pct=20.0)]
    resultados = {"AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=1, new_discrepancies=nuevas)}
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}})
    monkeypatch.setattr(
        runner, "send_telegram_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no deberia llamarse")),
    )

    resultado = runner.run_sec_validation_batch(max_tickers=10, send_telegram=False)
    assert resultado.telegram_attempted is False


def test_batch_send_telegram_sin_yes_queda_bloqueado(monkeypatch):
    from modulos.sec_validation_runner import TickerRunResult

    nuevas = [_comp(DISCREPANCY, diff_pct=20.0)]
    resultados = {"AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=1, new_discrepancies=nuevas)}
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}})
    monkeypatch.setattr(
        runner, "send_telegram_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no deberia llamarse sin --yes")),
    )

    resultado = runner.run_sec_validation_batch(max_tickers=10, send_telegram=True, confirmed=False)
    assert resultado.telegram_attempted is True
    assert resultado.telegram_ok is False
    assert "confirmacion" in resultado.telegram_detail.lower()


def test_batch_send_telegram_con_yes_envia_cuando_hay_discrepancias_nuevas(monkeypatch):
    from modulos.manual_delivery import DeliveryResult
    from modulos.sec_validation_runner import TickerRunResult

    nuevas = [_comp(DISCREPANCY, diff_pct=20.0)]
    resultados = {"AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=1, new_discrepancies=nuevas)}
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}})

    enviados = []
    monkeypatch.setattr(
        runner, "send_telegram_text",
        lambda texto: (enviados.append(texto), DeliveryResult(True, 1, "Enviado correctamente en 1 parte(s)."))[1],
    )

    resultado = runner.run_sec_validation_batch(max_tickers=10, send_telegram=True, confirmed=True)
    assert resultado.telegram_attempted is True
    assert resultado.telegram_ok is True
    assert len(enviados) == 1
    assert "AAPL" in enviados[0]


def test_batch_sin_discrepancias_nuevas_no_intenta_telegram_ni_con_yes(monkeypatch):
    from modulos.sec_validation_runner import TickerRunResult

    resultados = {"AAPL": TickerRunResult(ticker="AAPL", ok=True, status_code=None, comparisons_count=1, new_discrepancies=[])}
    monkeypatch.setattr(runner, "_process_ticker", _fake_process_ticker_factory(resultados))
    monkeypatch.setattr(runner, "cargar_watchlist", lambda: {"AAPL": {}})
    monkeypatch.setattr(
        runner, "send_telegram_text",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no deberia llamarse sin discrepancias nuevas")),
    )

    resultado = runner.run_sec_validation_batch(max_tickers=10, send_telegram=True, confirmed=True)
    assert resultado.telegram_attempted is False
