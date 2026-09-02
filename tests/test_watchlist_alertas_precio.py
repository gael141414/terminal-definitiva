"""Alertas de precio bidireccionales de la watchlist y endurecimiento de Yahoo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.watchlist import evaluar_alertas_precio
from modulos import yahoo_resilience


# --------------------------------------------------------------------------
# Alertas de precio
# --------------------------------------------------------------------------


def test_dispara_compra_cuando_el_precio_cae_al_objetivo():
    etiqueta, nivel = evaluar_alertas_precio(100.0, 120.0, 0.0)

    assert nivel == "compra"
    assert "120" in etiqueta


def test_dispara_venta_cuando_el_precio_supera_el_objetivo():
    """La alerta al alza no existía: sólo se podía vigilar la caída."""
    etiqueta, nivel = evaluar_alertas_precio(150.0, 0.0, 140.0)

    assert nivel == "venta"
    assert "140" in etiqueta


def test_entre_ambos_objetivos_informa_distancia_sin_alertar():
    etiqueta, nivel = evaluar_alertas_precio(100.0, 80.0, 130.0)

    assert nivel == "neutro"
    assert "%" in etiqueta


def test_la_compra_tiene_prioridad_sobre_la_venta_si_ambas_se_cumplen():
    """Configuración incoherente (compra 120 / venta 90 con precio 100): se
    prioriza la de compra en vez de mostrar dos alertas contradictorias."""
    _, nivel = evaluar_alertas_precio(100.0, 120.0, 90.0)

    assert nivel == "compra"


def test_sin_precio_no_inventa_alerta():
    assert evaluar_alertas_precio(0.0, 100.0, 200.0)[1] == "sin_datos"
    assert evaluar_alertas_precio(None, 100.0, 200.0)[1] == "sin_datos"


def test_sin_objetivos_configurados_no_alerta():
    assert evaluar_alertas_precio(100.0, 0.0, 0.0)[1] == "neutro"


# --------------------------------------------------------------------------
# safe_yfinance_info: reintentos y payloads de relleno
# --------------------------------------------------------------------------


class _YfFalso:
    """Devuelve una secuencia fija de respuestas de .info, una por intento."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = 0

    def Ticker(self, ticker):  # noqa: N802 - imita la API de yfinance
        contexto = self

        class _T:
            @property
            def info(self):
                contexto.llamadas += 1
                valor = contexto.respuestas.pop(0)
                if isinstance(valor, Exception):
                    raise valor
                return valor

        return _T()


def test_descarta_el_payload_de_relleno_de_yahoo(monkeypatch):
    """Yahoo devuelve ~3 claves (maxAge/symbol/...) cuando rechaza quoteSummary.
    Aceptarlo como válido era lo que acababa pintando 0.0 en la interfaz."""
    monkeypatch.setattr(yahoo_resilience.time, "sleep", lambda *_: None)
    relleno = {"maxAge": 1, "symbol": "AAPL", "trailingPegRatio": None}
    falso = _YfFalso([relleno, relleno, relleno])

    assert yahoo_resilience.safe_yfinance_info(falso, "AAPL") == {}
    assert falso.llamadas == 3  # 1 intento + 2 reintentos


def test_reintenta_y_acepta_la_respuesta_util(monkeypatch):
    monkeypatch.setattr(yahoo_resilience.time, "sleep", lambda *_: None)
    bueno = {f"campo_{i}": i for i in range(20)}
    falso = _YfFalso([{"maxAge": 1}, bueno])

    assert yahoo_resilience.safe_yfinance_info(falso, "AAPL") == bueno
    assert falso.llamadas == 2


def test_nunca_propaga_excepciones(monkeypatch):
    monkeypatch.setattr(yahoo_resilience.time, "sleep", lambda *_: None)
    falso = _YfFalso([RuntimeError("429 too many requests")] * 3)

    assert yahoo_resilience.safe_yfinance_info(falso, "AAPL") == {}
