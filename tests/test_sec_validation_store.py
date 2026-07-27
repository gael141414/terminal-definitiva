"""Persistencia de resultados de validación cruzada SEC↔FMP (Sub-fase 3a).

Cubre lo pedido para cerrar el store antes de construir el job (Sub-fase 3b)
y la superficie en Watchlist (Sub-fase 3c):

1. Guardar una corrida y leerla de vuelta (historial + resumen compacto).
2. Detectar una discrepancia "nueva" frente a la corrida anterior (la señal
   que usará el aviso de Telegram en 3b) — y confirmar que una discrepancia
   YA vista antes no se vuelve a marcar como nueva.
3. El cap de MAX_SEC_VALIDATION_RUNS_PER_TICKER funcionando.
4. El campo compacto ``last_sec_validation`` en watchlist.json convive con
   ``target``/``source``/``last_analysis`` sin pisarlos.
5. Un intento fallido (status_code tipado) nunca pisa el último resultado
   real con ceros falsos — solo actualiza cuándo fue el último intento.

Todo aislado en un directorio temporal (monkeypatch.chdir): nunca toca
data/watchlist.json ni data/sec_validation_history.json del repo real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import sec_validation_store as store
from modulos.sec_fmp_cross_validation import (
    DISCREPANCY,
    MATCH,
    NOT_COMPARABLE,
    PERIOD_MISALIGNED,
    MetricComparison,
)


@pytest.fixture(autouse=True)
def _aislar_en_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def _comp(
    classification,
    *,
    metric="Margen Bruto %",
    year="2024",
    fmp_value=46.21,
    sec_value=46.21,
    diff_pct=0.0,
    note="",
) -> MetricComparison:
    return MetricComparison(
        metric=metric, year=year, fmp_value=fmp_value, sec_value=sec_value,
        diff_pct=diff_pct, classification=classification, note=note,
    )


# ---------------------------------------------------------------------------
# Guardar y leer de vuelta
# ---------------------------------------------------------------------------


def test_guardar_primera_corrida_crea_historial_y_resumen():
    comparaciones = [_comp(MATCH), _comp(DISCREPANCY, metric="ROIC %", diff_pct=15.0)]

    nuevas = store.save_sec_validation_result("AAPL", comparaciones, checked_at="2026-07-27T02:00:00+00:00")

    # Primera corrida: la discrepancia ya presente cuenta como "nueva" (nunca vista).
    assert len(nuevas) == 1
    assert nuevas[0].metric == "ROIC %"

    historia = store.load_sec_validation_history()
    assert "AAPL" in historia
    assert len(historia["AAPL"]) == 1
    assert historia["AAPL"][0]["status_code"] is None
    assert len(historia["AAPL"][0]["comparisons"]) == 2

    resumen = store.sec_validation_summary("AAPL")
    assert resumen["last_successful_check_at"] == "2026-07-27T02:00:00+00:00"
    assert resumen["last_attempt_status_code"] is None
    assert resumen["match_count"] == 1
    assert resumen["discrepancy_count"] == 1
    assert resumen["worst_metric"] == "ROIC %"
    assert resumen["worst_diff_pct"] == 15.0


def test_historial_guarda_json_valido_en_disco():
    store.save_sec_validation_result("AAPL", [_comp(MATCH)], checked_at="2026-07-27T02:00:00+00:00")
    contenido = json.loads(store.SEC_VALIDATION_HISTORY_FILE.read_text(encoding="utf-8"))
    assert "AAPL" in contenido
    assert contenido["AAPL"][0]["comparisons"][0]["classification"] == MATCH


# ---------------------------------------------------------------------------
# Detección de discrepancia nueva vs. ya vista
# ---------------------------------------------------------------------------


def test_discrepancia_ya_vista_no_se_marca_como_nueva():
    store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, metric="ROIC %", diff_pct=15.0)],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    # Segunda corrida: la MISMA discrepancia sigue presente (magnitud distinta,
    # pero sigue siendo "discrepancia" en el mismo metric/year) -> no es nueva.
    nuevas = store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, metric="ROIC %", diff_pct=17.0)],
        checked_at="2026-07-27T02:00:00+00:00",
    )
    assert nuevas == []


def test_discrepancia_nueva_en_metrica_distinta_si_se_detecta():
    store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, metric="ROIC %", diff_pct=15.0)],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    # Segunda corrida: ROIC sigue igual (no nueva) pero aparece una discrepancia
    # nueva en Deuda / Capital que antes era "coincide".
    nuevas = store.save_sec_validation_result(
        "AAPL",
        [
            _comp(DISCREPANCY, metric="ROIC %", diff_pct=15.0),
            _comp(DISCREPANCY, metric="Deuda / Capital", diff_pct=-12.0),
        ],
        checked_at="2026-07-27T02:00:00+00:00",
    )
    assert [c.metric for c in nuevas] == ["Deuda / Capital"]


def test_metrica_que_pasa_de_coincide_a_discrepancia_es_nueva():
    store.save_sec_validation_result(
        "AAPL", [_comp(MATCH, metric="Margen Neto %")],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    nuevas = store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, metric="Margen Neto %", diff_pct=8.0)],
        checked_at="2026-07-27T02:00:00+00:00",
    )
    assert len(nuevas) == 1
    assert nuevas[0].metric == "Margen Neto %"


def test_metrica_que_pasa_de_discrepancia_a_coincide_no_genera_nueva():
    store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, metric="Margen Neto %", diff_pct=8.0)],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    nuevas = store.save_sec_validation_result(
        "AAPL", [_comp(MATCH, metric="Margen Neto %")],
        checked_at="2026-07-27T02:00:00+00:00",
    )
    assert nuevas == []


def test_periodo_no_alineado_tambien_cuenta_como_noteworthy():
    comp = _comp(PERIOD_MISALIGNED, metric="Margen Bruto %", diff_pct=32.0, note="posible restatement")
    nuevas = store.save_sec_validation_result("AAPL", [comp], checked_at="2026-07-27T02:00:00+00:00")
    assert len(nuevas) == 1
    assert nuevas[0].classification == PERIOD_MISALIGNED


def test_no_comparable_nunca_se_marca_como_discrepancia_nueva():
    comp = _comp(NOT_COMPARABLE, metric="Intereses % (s/OpInc)", sec_value=None, diff_pct=None,
                 note="concepto no encontrado en SEC")
    nuevas = store.save_sec_validation_result("AAPL", [comp], checked_at="2026-07-27T02:00:00+00:00")
    assert nuevas == []


def test_find_new_discrepancies_funcion_directa_sin_guardar():
    store.save_sec_validation_result(
        "MSFT", [_comp(MATCH, metric="Margen Bruto %")],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    actuales = [_comp(DISCREPANCY, metric="Margen Bruto %", diff_pct=9.0)]
    nuevas = store.find_new_discrepancies("MSFT", actuales)
    assert len(nuevas) == 1


# ---------------------------------------------------------------------------
# Cap de historial
# ---------------------------------------------------------------------------


def test_cap_de_60_corridas_por_ticker():
    for i in range(65):
        store.save_sec_validation_result(
            "AAPL", [_comp(MATCH)], checked_at=f"2026-01-{(i % 28) + 1:02d}T02:00:00+00:00",
        )
    historia = store.load_sec_validation_history()
    assert len(historia["AAPL"]) == store.MAX_SEC_VALIDATION_RUNS_PER_TICKER == 60


def test_cap_conserva_las_mas_recientes_primero():
    for i in range(62):
        store.save_sec_validation_result("AAPL", [_comp(MATCH)], checked_at=f"corrida-{i}")
    historia = store.load_sec_validation_history()["AAPL"]
    # Las 2 primeras (mas antiguas, corrida-0 y corrida-1) deben haberse descartado.
    checked_ats = [entry["checked_at"] for entry in historia]
    assert "corrida-0" not in checked_ats
    assert "corrida-1" not in checked_ats
    assert checked_ats[0] == "corrida-61"  # la mas reciente va primero


# ---------------------------------------------------------------------------
# Convivencia con target/source/last_analysis en watchlist.json
# ---------------------------------------------------------------------------


def test_no_pisa_target_source_ni_last_analysis_existentes():
    Path("data").mkdir(parents=True, exist_ok=True)
    watchlist_previo = {
        "AAPL": {
            "target": 150.0,
            "source": "Research Core",
            "last_saved_at": "2026-07-01T00:00:00+00:00",
            "last_analysis": {"valuequant_score": 82.5, "action": "Comprar"},
        }
    }
    Path("data/watchlist.json").write_text(json.dumps(watchlist_previo), encoding="utf-8")

    store.save_sec_validation_result("AAPL", [_comp(DISCREPANCY, diff_pct=12.0)], checked_at="2026-07-27T02:00:00+00:00")

    watchlist_final = json.loads(Path("data/watchlist.json").read_text(encoding="utf-8"))
    item = watchlist_final["AAPL"]
    assert item["target"] == 150.0
    assert item["source"] == "Research Core"
    assert item["last_analysis"] == {"valuequant_score": 82.5, "action": "Comprar"}
    assert "last_sec_validation" in item
    assert item["last_sec_validation"]["discrepancy_count"] == 1


def test_funciona_con_ticker_nuevo_que_no_existe_aun_en_watchlist():
    store.save_sec_validation_result("NVDA", [_comp(MATCH)], checked_at="2026-07-27T02:00:00+00:00")
    watchlist = json.loads(Path("data/watchlist.json").read_text(encoding="utf-8"))
    assert "last_sec_validation" in watchlist["NVDA"]


# ---------------------------------------------------------------------------
# Fallo (status_code) nunca pisa el ultimo resultado real con ceros falsos
# ---------------------------------------------------------------------------


def test_fallo_no_pisa_counts_del_ultimo_exito():
    store.save_sec_validation_result(
        "AAPL", [_comp(DISCREPANCY, diff_pct=20.0), _comp(MATCH, metric="Margen Neto %")],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    # Corrida siguiente: fallo de rate limit, sin comparaciones (no se llego a comparar nada).
    nuevas = store.save_sec_validation_result(
        "AAPL", [], status_code="rate_limited", checked_at="2026-07-27T02:00:00+00:00",
    )
    assert nuevas == []

    resumen = store.sec_validation_summary("AAPL")
    # Se actualiza el intento...
    assert resumen["last_attempt_at"] == "2026-07-27T02:00:00+00:00"
    assert resumen["last_attempt_status_code"] == "rate_limited"
    # ...pero el ultimo EXITO y sus contadores siguen siendo los de la corrida anterior.
    assert resumen["last_successful_check_at"] == "2026-07-26T02:00:00+00:00"
    assert resumen["discrepancy_count"] == 1
    assert resumen["match_count"] == 1


def test_primer_intento_que_falla_no_inventa_counts_falsos():
    store.save_sec_validation_result("TSLA", [], status_code="invalid_ticker", checked_at="2026-07-27T02:00:00+00:00")
    resumen = store.sec_validation_summary("TSLA")
    assert resumen["last_attempt_status_code"] == "invalid_ticker"
    assert "last_successful_check_at" not in resumen
    assert "discrepancy_count" not in resumen


def test_fallo_se_guarda_en_el_historial_con_comparaciones_vacias():
    store.save_sec_validation_result("TSLA", [], status_code="timeout", checked_at="2026-07-27T02:00:00+00:00")
    historia = store.load_sec_validation_history()["TSLA"]
    assert historia[0]["status_code"] == "timeout"
    assert historia[0]["comparisons"] == []


# ---------------------------------------------------------------------------
# Lectura normalizada para UI (Sub-fase 3c)
# ---------------------------------------------------------------------------


def test_sec_validation_history_for_ticker_normaliza_por_corrida():
    store.save_sec_validation_result(
        "AAPL", [_comp(MATCH), _comp(DISCREPANCY, metric="ROIC %", diff_pct=15.0)],
        checked_at="2026-07-26T02:00:00+00:00",
    )
    store.save_sec_validation_result("AAPL", [], status_code="rate_limited", checked_at="2026-07-27T02:00:00+00:00")

    df = store.sec_validation_history_for_ticker("AAPL")
    assert list(df["Verificado"]) == ["2026-07-26T02:00:00+00:00", "2026-07-27T02:00:00+00:00"]
    assert df.iloc[0]["Discrepancia"] == 1
    assert df.iloc[1]["Estado"] == "rate_limited"


def test_sec_validation_history_for_ticker_vacio_sin_corridas():
    assert store.sec_validation_history_for_ticker("ZZZZ").empty


def test_sec_validation_summary_vacio_sin_corridas():
    assert store.sec_validation_summary("ZZZZ") == {}
