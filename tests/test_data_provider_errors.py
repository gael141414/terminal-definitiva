"""Excepciones tipadas de la capa de datos: fmp_api.py y yahoo_resilience.py.

Verifica que:
1. La jerarquía en modulos/data_provider_errors.py clasifica y formatea bien.
2. fmp_api.py clasifica timeout/rate_limited/restricted/no_data/invalid_ticker/
   provider_error internamente (vía excepciones) pero sigue exponiendo el
   mismo contrato externo de siempre (None / tupla), sin romper a los
   consumidores existentes.
3. yahoo_resilience.py distingue timeout de un error genérico (antes ambos
   caían en STATUS_ERROR sin distinción) sin tocar los valores de status ya
   consumidos en otros módulos (STATUS_ERROR/STATUS_RATE_LIMITED no se renombran).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos import data_provider_errors as errors
from modulos import fmp_api
from modulos import yahoo_resilience


# ---------------------------------------------------------------------------
# modulos/data_provider_errors.py
# ---------------------------------------------------------------------------


def test_cada_excepcion_tiene_su_codigo_por_defecto():
    assert errors.NoDataError("x", context="c").code == errors.NO_DATA
    assert errors.InvalidTickerError("x", context="c").code == errors.INVALID_TICKER
    assert errors.RateLimitedError("x", context="c").code == errors.RATE_LIMITED
    assert errors.RestrictedError("x", context="c").code == errors.RESTRICTED
    assert errors.DataTimeoutError("x", context="c").code == errors.TIMEOUT
    assert errors.ProviderError("x", context="c").code == errors.PROVIDER_ERROR
    assert errors.InsufficientCoverageError("x", context="c").code == errors.INSUFFICIENT_COVERAGE


def test_str_incluye_codigo_contexto_y_mensaje_sin_requerir_url():
    exc = errors.RateLimitedError("HTTP 429.", context="legacy/quote-short/AAPL")
    texto = str(exc)
    assert "rate_limited" in texto
    assert "legacy/quote-short/AAPL" in texto
    assert "HTTP 429" in texto


def test_todas_las_subclases_son_data_provider_error():
    for cls in (
        errors.NoDataError, errors.InvalidTickerError, errors.RateLimitedError,
        errors.RestrictedError, errors.DataTimeoutError, errors.ProviderError,
        errors.InsufficientCoverageError,
    ):
        assert issubclass(cls, errors.DataProviderError)


# ---------------------------------------------------------------------------
# fmp_api.py: _fetch_fmp_payload / _descargar_json (mocking requests.get)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_error=False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._json_data


@pytest.fixture(autouse=True)
def _fmp_api_disponible_true(monkeypatch):
    monkeypatch.setattr(fmp_api, "_fmp_api_disponible", lambda: True)


def test_timeout_se_clasifica_como_data_timeout_error(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.exceptions.Timeout("read timed out")

    monkeypatch.setattr(fmp_api.requests, "get", fake_get)

    with pytest.raises(fmp_api.DataTimeoutError) as excinfo:
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {"apikey": "x"})
    assert excinfo.value.code == errors.TIMEOUT

    # _descargar_json (el contrato público) sigue devolviendo None, no propaga.
    assert fmp_api._descargar_json("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {"apikey": "x"}) is None


def test_429_se_clasifica_como_rate_limited(monkeypatch):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=429))

    with pytest.raises(fmp_api.RateLimitedError) as excinfo:
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/stable/quote-short", {"apikey": "x"})
    assert excinfo.value.code == errors.RATE_LIMITED
    assert fmp_api._descargar_json("https://financialmodelingprep.com/stable/quote-short", {"apikey": "x"}) is None


@pytest.mark.parametrize("status_code", [401, 402, 403])
def test_401_402_403_se_clasifican_como_restricted(monkeypatch, status_code):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=status_code))

    with pytest.raises(fmp_api.RestrictedError) as excinfo:
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {})
    assert excinfo.value.code == errors.RESTRICTED


def test_5xx_se_clasifica_como_provider_error(monkeypatch):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=503))

    with pytest.raises(fmp_api.ProviderError) as excinfo:
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {})
    assert excinfo.value.code == errors.PROVIDER_ERROR


def test_json_invalido_se_clasifica_como_no_data(monkeypatch):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=200, json_error=True))

    with pytest.raises(fmp_api.NoDataError):
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {})


def test_payload_vacio_se_clasifica_como_no_data(monkeypatch):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=200, json_data=[]))

    with pytest.raises(fmp_api.NoDataError):
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/quote-short/AAPL", {})


def test_error_message_con_symbol_se_clasifica_como_invalid_ticker(monkeypatch):
    monkeypatch.setattr(
        fmp_api.requests, "get",
        lambda *a, **k: _FakeResponse(status_code=200, json_data=[{"Error Message": "Invalid symbol: ZZZZINVALID"}]),
    )

    with pytest.raises(fmp_api.InvalidTickerError):
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/income-statement/ZZZZINVALID", {})


def test_error_message_generico_se_clasifica_como_provider_error(monkeypatch):
    monkeypatch.setattr(
        fmp_api.requests, "get",
        lambda *a, **k: _FakeResponse(status_code=200, json_data=[{"Error Message": "Legacy Endpoint Deprecated"}]),
    )

    with pytest.raises(fmp_api.ProviderError):
        fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/income-statement/AAPL", {})


def test_payload_valido_no_lanza_y_se_devuelve_tal_cual(monkeypatch):
    payload = [{"date": "2024-09-28", "revenue": 100}]
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=200, json_data=payload))

    assert fmp_api._fetch_fmp_payload("https://financialmodelingprep.com/api/v3/income-statement/AAPL", {}) == payload
    assert fmp_api._descargar_json("https://financialmodelingprep.com/api/v3/income-statement/AAPL", {}) == payload


def test_endpoint_context_nunca_incluye_query_string_ni_dominio():
    ctx = fmp_api._endpoint_context("https://financialmodelingprep.com/api/v3/quote-short/AAPL?apikey=SECRETO123")
    assert "apikey" not in ctx
    assert "SECRETO123" not in ctx
    assert ctx == "legacy/quote-short/AAPL"


def test_extraer_datos_fundamentales_fmp_no_propaga_excepciones_tipadas(monkeypatch):
    """El contrato externo (4-tupla de None/DataFrame) se mantiene aunque
    todos los endpoints fallen con causas tipadas distintas."""
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=429))
    monkeypatch.setattr(fmp_api, "FMP_API_KEY", "fake-key-for-test")

    resultado = fmp_api.extraer_datos_fundamentales_fmp("AAPL", 3)

    assert resultado == (None, None, None, None)


def test_obtener_cotizacion_fmp_no_propaga_excepciones_tipadas(monkeypatch):
    monkeypatch.setattr(fmp_api.requests, "get", lambda *a, **k: _FakeResponse(status_code=500))
    monkeypatch.setattr(fmp_api, "FMP_API_KEY", "fake-key-for-test")

    assert fmp_api.obtener_cotizacion_fmp("AAPL") == 0.0


# ---------------------------------------------------------------------------
# yahoo_resilience.py: distinción de timeout vs error genérico
# ---------------------------------------------------------------------------


def test_is_yahoo_timeout_error_detecta_requests_timeout_y_builtin():
    assert yahoo_resilience.is_yahoo_timeout_error(requests.exceptions.Timeout("boom")) is True
    assert yahoo_resilience.is_yahoo_timeout_error(TimeoutError("boom")) is True
    assert yahoo_resilience.is_yahoo_timeout_error(ValueError("boom")) is False


def test_safe_yfinance_fetch_timeout_se_clasifica_distinto_de_error_generico():
    def getter_timeout():
        raise requests.exceptions.Timeout("read timed out")

    value, status = yahoo_resilience.safe_yfinance_fetch(
        getter_timeout, empty_value=None, context="test:timeout", retries=0,
    )
    assert value is None
    assert status == yahoo_resilience.STATUS_TIMEOUT
    assert status != yahoo_resilience.STATUS_ERROR  # antes de este fix, caía aquí

    def getter_generic_error():
        raise RuntimeError("algo distinto")

    value2, status2 = yahoo_resilience.safe_yfinance_fetch(
        getter_generic_error, empty_value=None, context="test:generic", retries=0,
    )
    assert status2 == yahoo_resilience.STATUS_ERROR


def test_safe_yfinance_fetch_reintenta_en_timeout(monkeypatch):
    monkeypatch.setattr(yahoo_resilience.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    def getter():
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.Timeout("read timed out")
        return "ok-value"

    value, status = yahoo_resilience.safe_yfinance_fetch(
        getter, empty_value=None, context="test:retry-timeout", retries=1,
    )
    assert calls["n"] == 2
    assert value == "ok-value"
    assert status == yahoo_resilience.STATUS_OK


def test_status_error_y_rate_limited_no_se_renombraron(monkeypatch):
    """Consumidores como modulos/quotes.py y modulos/market_widgets.py comparan
    por valor literal contra estos strings; no deben cambiar de valor."""
    assert yahoo_resilience.STATUS_ERROR == "error"
    assert yahoo_resilience.STATUS_RATE_LIMITED == "rate_limited"
    assert yahoo_resilience.STATUS_NO_DATA == "no_data"
    assert yahoo_resilience.STATUS_OK == "ok"
    assert yahoo_resilience.STATUS_TIMEOUT == "timeout"  # nuevo
