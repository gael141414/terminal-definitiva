"""Historial de KPIs: deduplicación diaria, parseo de timestamps y badge."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import historial


@pytest.fixture(autouse=True)
def historial_aislado(tmp_path, monkeypatch):
    """Cada test escribe en su propio JSON, nunca en data/historial.json."""
    carpeta = tmp_path / "data"
    carpeta.mkdir()
    monkeypatch.setattr(historial, "DB_FOLDER", str(carpeta))
    monkeypatch.setattr(historial, "DB_FILE", str(carpeta / "historial.json"))
    return carpeta


def _resultados(roe=28.4, roic=41.0, margen=25.3, deuda=1.3):
    return (
        {"ratios": pd.DataFrame({"Margen Neto %": [margen]})},
        {"ratios": pd.DataFrame({"ROE %": [roe], "ROIC %": [roic], "Deuda / Capital": [deuda]})},
        {"ratios": pd.DataFrame({"Free Cash Flow (B USD)": [99.0]})},
    )


def test_registra_kpis_principales():
    res_is, res_bs, res_cf = _resultados()
    historial.registrar_analisis("AAPL", res_is, res_bs, res_cf, 82)

    df = historial.historial_ticker("AAPL")
    assert len(df) == 1
    fila = df.iloc[0]
    assert fila["ROE %"] == 28.4
    assert fila["ROIC %"] == 41.0
    assert fila["Margen Neto %"] == 25.3
    assert fila["Deuda / Capital"] == 1.3
    assert fila["Buffett Score"] == 82.0


def test_reabrir_la_ficha_el_mismo_dia_no_duplica_puntos():
    """Abrir cinco veces la misma empresa en una tarde no son cinco análisis."""
    res_is, res_bs, res_cf = _resultados()
    for _ in range(5):
        historial.registrar_analisis("AAPL", res_is, res_bs, res_cf, 82)

    assert len(historial.historial_ticker("AAPL")) == 1


def test_la_entrada_del_dia_refleja_el_ultimo_valor():
    historial.registrar_analisis("AAPL", *_resultados(roe=20.0), nota_buffett=60)
    historial.registrar_analisis("AAPL", *_resultados(roe=31.0), nota_buffett=88)

    df = historial.historial_ticker("AAPL")
    assert len(df) == 1
    assert df.iloc[0]["ROE %"] == 31.0
    assert df.iloc[0]["Buffett Score"] == 88.0


def test_timestamps_con_precision_distinta_no_se_descartan(historial_aislado):
    """Regresión: pandas infería el formato del primer registro y convertía a
    NaT los que llevaban microsegundos, así que el histórico perdía puntos en
    silencio y la evolución mostraba menos análisis de los reales."""
    fichero = historial_aislado / "historial.json"
    fichero.write_text(
        json.dumps(
            {
                "AAPL": [
                    {"timestamp": "2026-01-05T10:00:00+00:00", "ROE %": 22.0},
                    {"timestamp": "2026-02-05T10:00:00.123456+00:00", "ROE %": 25.0},
                    {"timestamp": "2026-03-05T10:00:00+00:00", "ROE %": 28.0},
                ]
            }
        ),
        encoding="utf-8",
    )

    df = historial.historial_ticker("AAPL")
    assert len(df) == 3
    assert list(df["ROE %"]) == [22.0, 25.0, 28.0]


def test_analisis_sin_ningun_kpi_no_ensucia_el_historico():
    vacio = {"ratios": pd.DataFrame()}
    historial.registrar_analisis("VACIO", vacio, vacio, vacio, None)

    assert historial.historial_ticker("VACIO").empty


def test_badge_distingue_primer_analisis_de_revision_previa(historial_aislado):
    assert historial.etiqueta_ultima_revision("NUEVO") == "Primer análisis registrado"

    (historial_aislado / "historial.json").write_text(
        json.dumps({"AAPL": [{"timestamp": "2020-01-01T10:00:00+00:00", "ROE %": 22.0}]}),
        encoding="utf-8",
    )
    etiqueta = historial.etiqueta_ultima_revision("AAPL")
    assert etiqueta.startswith("Última revisión: hace ")


def test_json_corrupto_no_tumba_la_ficha(historial_aislado):
    (historial_aislado / "historial.json").write_text("{esto no es json", encoding="utf-8")

    assert historial.cargar_historial_completo() == {}
    assert historial.historial_ticker("AAPL").empty
