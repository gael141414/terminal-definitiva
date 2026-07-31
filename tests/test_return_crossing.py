"""Motor de cruce score-vs-retorno (Sub-fase 4, calibración del score).

Cubre lo que se puede probar de forma determinista, sin red: el cruce
score<->retorno con series de precio sintéticas (incluida la ausencia de
retorno cuando no hay precio, el caso central de los 3 casos de
supervivencia), la agregación en deciles y Spearman con datos controlados,
la construcción del dataset FMP/supervivencia con las dependencias
mockeadas, y la persistencia. La ejecución real (universo FMP + Yahoo en
vivo) se hizo aparte vía scripts/build_return_crossing_dataset.py y se
describe en el informe de la tarea -- mismo criterio que el resto de la
suite desde la Fase 7 (sin red en pytest).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import return_crossing as rc
from modulos.point_in_time_scoring import FrozenScore


def _score_de_prueba(identificador="AAPL", as_of_date="2022-06-01", final_score=70.0) -> FrozenScore:
    return FrozenScore(
        identificador=identificador, fuente="fmp", as_of_date=as_of_date,
        fiscal_year_mas_reciente_incluido="2021", final_score=final_score, confidence=0.8,
        verdict="Comprar", data_coverage=0.9, componentes=[], precio_historico=150.0, red_flags=[],
    )


def _serie_precio(fechas: list[str], valores: list[float]) -> pd.Series:
    idx = pd.DatetimeIndex([pd.Timestamp(f) for f in fechas])
    return pd.Series(valores, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# _rango_precio_necesario
# ---------------------------------------------------------------------------


def test_rango_precio_necesario_cubre_desde_el_primer_punto_hasta_1y_tras_el_ultimo():
    puntos = [{"as_of_date": "2020-05-01"}, {"as_of_date": "2022-06-15"}]
    inicio, fin = rc._rango_precio_necesario(puntos)
    assert inicio == "2020-05-01"
    assert fin == (pd.Timestamp("2022-06-15") + pd.Timedelta(days=rc.HORIZONTE_1A_DIAS + rc._MARGEN_DESCARGA_DIAS)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# _cruzar_retorno: el corazón del cruce
# ---------------------------------------------------------------------------


def test_cruzar_retorno_calcula_6m_y_1y_con_serie_suficiente():
    score = _score_de_prueba(as_of_date="2022-01-03")
    fechas = pd.date_range("2022-01-03", periods=500, freq="D")
    # precio sube linealmente de 100 a 150 a lo largo de la serie
    valores = [100 + i * (50 / 499) for i in range(500)]
    close = pd.Series(valores, index=fechas)

    resultado = rc._cruzar_retorno(score, close, motivo_si_vacio="no debería usarse")

    assert resultado.tiene_retorno is True
    assert resultado.motivo_sin_retorno is None
    assert resultado.retorno_6m is not None and resultado.retorno_6m > 0
    assert resultado.retorno_1y is not None and resultado.retorno_1y > 0
    assert resultado.precio_entrada == pytest.approx(100.0, abs=0.01)
    assert resultado.fecha_entrada == "2022-01-03"


def test_cruzar_retorno_sin_precio_marca_tiene_retorno_false_con_motivo():
    score = _score_de_prueba()

    resultado = rc._cruzar_retorno(score, pd.Series(dtype=float), motivo_si_vacio="sin precio histórico fiable (caso de prueba)")

    assert resultado.tiene_retorno is False
    assert resultado.motivo_sin_retorno == "sin precio histórico fiable (caso de prueba)"
    assert resultado.retorno_6m is None
    assert resultado.retorno_1y is None
    assert resultado.fecha_entrada is None
    assert resultado.precio_entrada is None
    # el score de fundamentales se conserva -- nunca se descarta la fila
    assert resultado.final_score == score.final_score
    assert resultado.identificador == score.identificador


def test_cruzar_retorno_sin_ningun_cierre_tras_la_entrada_marca_motivo_especifico():
    """_entry_exit_prices (signal_backtesting.py, reutilizada tal cual) hace
    fallback al siguiente cierre disponible cuando la fecha objetivo exacta
    no existe -- una serie corta pero con MÁS puntos tras la entrada sigue
    produciendo salida (más corta de lo pedido, comportamiento ya existente
    y fuera del alcance de esta sub-fase). El único caso real sin retorno es
    cuando no hay NINGÚN cierre después de la fecha de entrada."""
    score = _score_de_prueba(as_of_date="2022-01-03")
    close = _serie_precio(["2022-01-03"], [100.0])  # un solo punto: la propia entrada, nada después

    resultado = rc._cruzar_retorno(score, close, motivo_si_vacio="no debería usarse")

    assert resultado.tiene_retorno is False
    assert resultado.motivo_sin_retorno == "sin cierre disponible en ventana suficiente tras la fecha de congelación"


# ---------------------------------------------------------------------------
# descargar_cierre_yahoo_directo: extrae "Close" del histórico compartido
# ---------------------------------------------------------------------------


def test_descargar_cierre_yahoo_directo_extrae_close(monkeypatch):
    fechas = pd.date_range("2022-01-01", periods=3, freq="D")
    df = pd.DataFrame({"Close": [10.0, 11.0, 12.0]}, index=fechas)
    monkeypatch.setattr(rc, "_descargar_historial_yahoo_directo", lambda t, s, e: df)

    serie = rc.descargar_cierre_yahoo_directo("AAPL", "2022-01-01", "2022-01-03")

    assert list(serie.values) == [10.0, 11.0, 12.0]


def test_descargar_cierre_yahoo_directo_vacio_si_no_hay_datos(monkeypatch):
    monkeypatch.setattr(rc, "_descargar_historial_yahoo_directo", lambda t, s, e: pd.DataFrame())

    serie = rc.descargar_cierre_yahoo_directo("NOEXISTE", "2022-01-01", "2022-01-03")

    assert serie.empty


# ---------------------------------------------------------------------------
# Agregación: deciles
# ---------------------------------------------------------------------------


def _df_sintetico(n: int, *, correlacionado: bool) -> pd.DataFrame:
    filas = []
    for i in range(n):
        score = float(i % 100)
        retorno = (score / 100.0) if correlacionado else ((i * 37) % 100) / 1000.0
        filas.append(
            {
                "identificador": f"T{i}", "fuente": "fmp", "as_of_date": "2022-01-01",
                "fiscal_year_mas_reciente_incluido": "2021", "final_score": score, "confidence": 0.8,
                "verdict": "Comprar", "tiene_retorno": True, "motivo_sin_retorno": None,
                "fecha_entrada": "2022-01-01", "precio_entrada": 100.0,
                "retorno_6m": retorno, "fecha_salida_6m": "2022-07-01",
                "retorno_1y": retorno, "fecha_salida_1y": "2023-01-01",
                "generado_en": "2026-01-01T00:00:00+00:00",
            }
        )
    return pd.DataFrame(filas)


def test_calcular_deciles_devuelve_10_grupos_con_muestra_suficiente():
    df = _df_sintetico(100, correlacionado=True)

    deciles = rc.calcular_deciles(df, "retorno_6m")

    assert not deciles.empty
    assert len(deciles) == 10
    assert set(deciles.columns) >= {"decil", "n", "score_medio", "retorno_medio", "retorno_mediana"}
    assert deciles["n"].sum() == 100
    # decil más alto de score debe tener retorno medio mayor (construcción sintética monotónica)
    assert deciles.sort_values("decil").iloc[-1]["retorno_medio"] > deciles.sort_values("decil").iloc[0]["retorno_medio"]


def test_calcular_deciles_vacio_con_muestra_insuficiente():
    df = _df_sintetico(5, correlacionado=True)

    assert rc.calcular_deciles(df, "retorno_6m").empty


def test_calcular_deciles_ignora_filas_sin_retorno():
    df = _df_sintetico(20, correlacionado=True)
    df.loc[0, "tiene_retorno"] = False
    df.loc[0, "retorno_6m"] = None

    deciles = rc.calcular_deciles(df, "retorno_6m")

    assert deciles["n"].sum() == 19


# ---------------------------------------------------------------------------
# Agregación: Spearman
# ---------------------------------------------------------------------------


def test_calcular_spearman_detecta_correlacion_positiva_fuerte():
    df = _df_sintetico(50, correlacionado=True)

    resultado = rc.calcular_spearman(df, "retorno_6m")

    assert resultado["n"] == 50
    assert resultado["rho"] is not None
    assert resultado["rho"] > 0.9  # construcción monotónica exacta -> rho cercano a 1


def test_calcular_spearman_muestra_insuficiente_no_calcula_rho():
    df = _df_sintetico(2, correlacionado=True)

    resultado = rc.calcular_spearman(df, "retorno_6m")

    assert resultado["n"] == 2
    assert resultado["rho"] is None
    assert "nota" in resultado


# ---------------------------------------------------------------------------
# construir_dataset_fmp / construir_dataset_supervivencia (dependencias mockeadas)
# ---------------------------------------------------------------------------


def test_construir_dataset_fmp_omite_tickers_sin_puntos_de_congelacion(monkeypatch):
    def fake_puntos(ticker, *, limite_anios):
        return [{"as_of_date": "2022-01-03", "fiscal_year": "2021"}] if ticker == "AAPL" else []

    monkeypatch.setattr(rc, "generar_puntos_de_congelacion_fmp", fake_puntos)
    monkeypatch.setattr(rc, "congelar_score_fmp", lambda ticker, as_of, **kw: _score_de_prueba(ticker, as_of))
    monkeypatch.setattr(rc, "descargar_cierre_yahoo_directo", lambda ticker, ini, fin: pd.Series(dtype=float))

    resultados, accesibles = rc.construir_dataset_fmp(["AAPL", "RESTRINGIDO"], limite_anios=5)

    assert accesibles == ["AAPL"]
    assert len(resultados) == 1
    assert resultados[0].identificador == "AAPL"
    assert resultados[0].tiene_retorno is False  # sin precio (mock devuelve serie vacía)


def test_construir_dataset_fmp_omite_puntos_donde_el_score_no_se_pudo_calcular(monkeypatch):
    monkeypatch.setattr(
        rc, "generar_puntos_de_congelacion_fmp",
        lambda ticker, *, limite_anios: [{"as_of_date": "2022-01-03"}],
    )
    monkeypatch.setattr(rc, "congelar_score_fmp", lambda ticker, as_of, **kw: None)
    monkeypatch.setattr(rc, "descargar_cierre_yahoo_directo", lambda ticker, ini, fin: pd.Series(dtype=float))

    resultados, accesibles = rc.construir_dataset_fmp(["AAPL"], limite_anios=5)

    assert accesibles == ["AAPL"]  # es accesible (hay puntos), aunque el score puntual falle
    assert resultados == []


def test_construir_dataset_supervivencia_marca_sin_retorno_para_los_3_casos(monkeypatch):
    monkeypatch.setattr(
        rc, "generar_puntos_de_congelacion_sec",
        lambda cik, *, años: [{"as_of_date": "2020-05-01"}],
    )
    monkeypatch.setattr(
        rc, "congelar_score_sec",
        lambda cik, as_of, ticker_historico, **kw: _score_de_prueba(ticker_historico, as_of),
    )

    resultados = rc.construir_dataset_supervivencia(años=5)

    assert len(resultados) == 3
    identificadores = {r.identificador for r in resultados}
    assert identificadores == {"BBBY", "SHLD", "TOYS"}
    for r in resultados:
        assert r.tiene_retorno is False
        assert r.motivo_sin_retorno is not None
        assert r.final_score is not None  # el score de fundamentales se conserva


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def test_guardar_y_cargar_resultado_roundtrip(tmp_path):
    path = tmp_path / "resultado.json"
    resultados = [
        rc._cruzar_retorno(_score_de_prueba("A", final_score=80.0), pd.Series(dtype=float), motivo_si_vacio="sin precio"),
        rc._cruzar_retorno(_score_de_prueba("B", final_score=20.0), pd.Series(dtype=float), motivo_si_vacio="sin precio"),
    ]

    resumen = rc.guardar_resultado(resultados, universo_probado=["A", "B", "C"], universo_accesible=["A", "B"], path=path)

    assert resumen["universo_fmp_probado"] == 3
    assert resumen["universo_fmp_accesible"] == 2
    assert resumen["tamaño_muestra_total_filas"] == 2

    cargado = rc.cargar_resultado(path=path)
    assert cargado is not None
    assert len(cargado["filas"]) == 2
    assert cargado["tickers_fmp_accesibles"] == ["A", "B"]


def test_cargar_resultado_none_si_no_existe(tmp_path):
    assert rc.cargar_resultado(path=tmp_path / "no_existe.json") is None
