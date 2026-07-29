#!/usr/bin/env python3
"""Guards the FMP news integration fix: news/stock is restricted on the
configured plan (HTTP 402: "Restricted Endpoint: This endpoint is not
available under your current subscription"). This is a plan limitation, not
an invalid key, a bad connection or a wrong endpoint — so it must never be
confused with 401 (bad key), must never retry endlessly, must never mark the
whole FMP integration as down, and must never block the rest of the company
analysis (profile, quote, financials).
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.url = "https://financialmodelingprep.com/api/v3/stock_news?apikey=SHOULD-NEVER-BE-LOGGED"

    def json(self):
        return self._payload


def _capture_logs(*logger_names: str) -> tuple[io.StringIO, list[logging.Handler]]:
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handlers: list[logging.Handler] = []
    for name in logger_names:
        logger = logging.getLogger(name)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        handlers.append(logger)
    return buffer, handlers


def _release_logs(handlers: list[logging.Handler], handler: logging.Handler) -> None:
    for logger in handlers:
        logger.removeHandler(handler)


def run_contract_checks() -> list[str]:
    import modulos.fmp_api as fmp
    from modulos import alt_data
    from modulos.config import CONFIG

    checks: list[str] = []
    fake_api_key = "SHOULD-NEVER-BE-LOGGED"

    original_get = fmp.requests.get
    original_fmp_key = fmp.FMP_API_KEY
    original_alt_key = alt_data.FMP_API_KEY
    original_news_enabled = CONFIG.fmp_news_enabled

    def _set_news_enabled(value: bool) -> None:
        object.__setattr__(CONFIG, "fmp_news_enabled", value)

    try:
        fmp.FMP_API_KEY = fake_api_key
        alt_data.FMP_API_KEY = fake_api_key
        # FMP_NEWS_ENABLED defaults to false; estos escenarios verifican qué pasa
        # cuando la llamada a FMP se realiza y falla (402/403/429/timeout), así
        # que se habilita explícitamente aquí. El escenario "disabled" más abajo
        # lo vuelve a poner en false para probar el propio interruptor.
        _set_news_enabled(True)

        # --- 200 OK: normal news payload ---------------------------------
        def fake_get_200(url, params=None, timeout=None):
            return _FakeResponse(200, [
                {"title": "Company beats earnings and raises guidance", "publishedDate": "2026-07-09", "site": "Reuters", "url": "https://example.com/1"},
                {"title": "Analysts warn of margin pressure", "publishedDate": "2026-07-08", "site": "Bloomberg", "url": "https://example.com/2"},
            ])

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_200
            mocked_requests.exceptions = requests.exceptions
            fetch_fmp_news = alt_data.fetch_fmp_news
            fetch_fmp_news.clear()
            news_df, status = fetch_fmp_news("AAPL", 20)
            assert_true(status == fmp.FMP_STATUS_OK, "200 debe clasificarse como ok")
            assert_true(not news_df.empty, "200 con payload debe devolver noticias")
            gauge, scored = alt_data.aggregate_media_sentiment(news_df)
            assert_true(gauge is not None, "Con noticias reales el gauge debe calcularse (no N/D)")
            assert_true(0 <= gauge <= 100, "El gauge debe quedar en rango 0-100")
        checks.append("200 OK returns news and a real sentiment gauge")

        # --- 402: restricted plan ----------------------------------------
        def fake_get_402(url, params=None, timeout=None):
            return _FakeResponse(402, {"Error Message": "Restricted Endpoint: This endpoint is not available under your current subscription"})

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_402
            mocked_requests.exceptions = requests.exceptions
            log_buffer, handlers = _capture_logs("valuequant.fmp")
            handler = log_buffer and logging.getLogger("valuequant.fmp").handlers[-1]
            fetch_fmp_news.clear()
            news_df, status = fetch_fmp_news("AAPL", 20)
            _release_logs(handlers, handler)

            assert_true(status == fmp.FMP_STATUS_RESTRICTED_PLAN, "402 debe clasificarse como restricted_plan, no como clave inválida")
            assert_true(status != fmp.FMP_STATUS_UNAUTHORIZED, "402 nunca debe confundirse con 401 (clave inválida)")
            assert_true(news_df.empty, "402 no debe fabricar noticias sustitutas")
            assert_true(fake_api_key not in log_buffer.getvalue(), "La API key nunca debe aparecer en los logs")
            assert_true("apikey" not in log_buffer.getvalue().lower(), "La URL con apikey nunca debe registrarse en los logs")

            gauge, scored = alt_data.aggregate_media_sentiment(news_df)
            assert_true(gauge is None, "Sin noticias el sentimiento debe ser N/D (None), no neutral (50.0) ni 0")
            assert_true(scored.empty, "No debe inventarse una tabla de noticias sustituta")

            message = fmp.FMP_STATUS_MESSAGES[fmp.FMP_STATUS_RESTRICTED_PLAN]
            assert_true(message == "Noticias no disponibles con el plan actual de FMP.", "El mensaje de UI debe ser exactamente el especificado para 402/403")
        checks.append("402 restricted_plan: no fake data, sentiment is N/D, no API key in logs")

        # --- 403 "Restricted Endpoint" (the exact real-world response) ----
        # This is the literal response FMP returns today for news/stock on the
        # configured plan: HTTP 403 with an "Restricted Endpoint" error body
        # (FMP uses 402 and 403 interchangeably across endpoints/plans for
        # this same "not included in your subscription" condition).
        call_count_403 = {"n": 0}

        def fake_get_403_restricted(url, params=None, timeout=None):
            call_count_403["n"] += 1
            if "stock_news" in url:
                return _FakeResponse(
                    403,
                    {"Error Message": "Restricted Endpoint: This endpoint is not available under your current subscription"},
                )
            # A different FMP endpoint (e.g. quote/profile) keeps working —
            # proves a restricted news endpoint doesn't take the rest of FMP down.
            return _FakeResponse(200, [{"symbol": "AAPL", "price": 316.22}])

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_403_restricted
            mocked_requests.exceptions = requests.exceptions
            log_buffer, handlers = _capture_logs("valuequant.fmp")
            handler = logging.getLogger("valuequant.fmp").handlers[-1]

            fetch_fmp_news.clear()
            exploded = False
            try:
                news_df, status = fetch_fmp_news("AAPL", 20)
            except Exception:
                exploded = True
            _release_logs(handlers, handler)

            assert_true(not exploded, "Un 403 Restricted Endpoint nunca debe propagar una excepción visible")
            assert_true(status == fmp.FMP_STATUS_RESTRICTED_PLAN, "403 'Restricted Endpoint' debe clasificarse como restricted_plan")
            assert_true(call_count_403["n"] == 1, f"Un 403 (causa permanente, no transitoria) no debe reintentarse — esperado 1 llamada, obtuvo {call_count_403['n']}")
            assert_true(news_df.empty, "403 Restricted Endpoint no debe fabricar noticias sustitutas")
            assert_true(fake_api_key not in log_buffer.getvalue(), "La API key nunca debe aparecer en los logs del caso 403")

            gauge, _scored = alt_data.aggregate_media_sentiment(news_df)
            assert_true(gauge is None, "Con 403 Restricted Endpoint el sentimiento debe quedar como None (N/D)")

            # El resto del análisis (otro endpoint FMP, ej. cotización) debe seguir funcionando
            # en la misma ejecución, sin verse afectado por el 403 de noticias.
            quote_payload, quote_status = fmp.fetch_fmp_json_classified(
                f"{fmp.BASE_URL}/quote-short/AAPL", {"apikey": fake_api_key}, context="test:quote_after_news_403",
            )
            assert_true(quote_status == fmp.FMP_STATUS_OK, "Un 403 en noticias no debe impedir que otro endpoint FMP siga respondiendo en la misma ejecución")
            assert_true(quote_payload is not None and quote_payload[0]["price"] == 316.22, "El resto del análisis debe continuar devolviendo datos reales")
        checks.append("403 'Restricted Endpoint': classified correctly, no retry, no visible exception, sentiment is None, rest of analysis continues")

        # --- 401: invalid/missing key, must differ from 402 --------------
        def fake_get_401(url, params=None, timeout=None):
            return _FakeResponse(401, {"Error Message": "Invalid API KEY."})

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_401
            mocked_requests.exceptions = requests.exceptions
            fetch_fmp_news.clear()
            _, status = fetch_fmp_news("AAPL", 20)
            assert_true(status == fmp.FMP_STATUS_UNAUTHORIZED, "401 debe clasificarse como unauthorized")
        checks.append("401 unauthorized is classified distinctly from 402 restricted_plan")

        # --- 429: rate limited, must retry at most once then give up -----
        call_count = {"n": 0}

        def fake_get_429(url, params=None, timeout=None):
            call_count["n"] += 1
            return _FakeResponse(429, {"Error Message": "Limit Reach"})

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_429
            mocked_requests.exceptions = requests.exceptions
            with patch.object(fmp.time, "sleep", return_value=None):
                fetch_fmp_news.clear()
                _, status = fetch_fmp_news("AAPL", 20)
            assert_true(status == fmp.FMP_STATUS_RATE_LIMITED, "429 persistente debe clasificarse como rate_limited")
            assert_true(call_count["n"] == 2, f"Debe reintentar como máximo una vez (esperado 2 llamadas, obtuvo {call_count['n']}) — no debe machacar el endpoint")
        checks.append("429 retries exactly once, then gives up without hammering the endpoint")

        # --- Timeout: transient provider failure --------------------------
        def fake_get_timeout(url, params=None, timeout=None):
            raise requests.exceptions.Timeout("simulated timeout")

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_timeout
            mocked_requests.exceptions = requests.exceptions
            log_buffer, handlers = _capture_logs("valuequant.fmp")
            handler = logging.getLogger("valuequant.fmp").handlers[-1]
            with patch.object(fmp.time, "sleep", return_value=None):
                fetch_fmp_news.clear()
                news_df, status = fetch_fmp_news("AAPL", 20)
            _release_logs(handlers, handler)
            assert_true(status == fmp.FMP_STATUS_PROVIDER_ERROR, "Timeout debe clasificarse como provider_error")
            assert_true(news_df.empty, "Timeout no debe fabricar noticias")
            assert_true(fake_api_key not in log_buffer.getvalue(), "La API key nunca debe aparecer en logs de timeout")
        checks.append("Timeout is classified as provider_error without raising and without leaking the key")

        # --- FMP_NEWS_ENABLED=false: no request should be made at all -----
        _set_news_enabled(False)
        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = AssertionError("no debe llamarse a requests.get con FMP_NEWS_ENABLED=false")
            fetch_fmp_news.clear()
            news_df, status = fetch_fmp_news("AAPL", 20)
            assert_true(status == fmp.FMP_STATUS_DISABLED, "Con FMP_NEWS_ENABLED=false el status debe ser disabled")
            assert_true(news_df.empty, "Con noticias desactivadas no debe haber datos")
        _set_news_enabled(True)  # reactivar para los escenarios restantes de esta suite
        checks.append("FMP_NEWS_ENABLED=false makes zero network calls")

        # --- Full analysis keeps working when news is restricted ----------
        def fake_get_402_again(url, params=None, timeout=None):
            return _FakeResponse(402, {"Error Message": "Restricted Endpoint"})

        with patch.object(fmp, "requests") as mocked_requests:
            mocked_requests.get.side_effect = fake_get_402_again
            mocked_requests.exceptions = requests.exceptions
            fetch_fmp_news.clear()
            try:
                _, status = fetch_fmp_news("AAPL", 20)
                exploded = False
            except Exception:
                exploded = True
            assert_true(not exploded, "Un fallo de noticias nunca debe propagar una excepción")

        assert_true(fmp._fmp_api_disponible() == bool(fake_api_key), "Un 402 en noticias no debe marcar la clave/integración FMP como no disponible para el resto del análisis")
        checks.append("A restricted news endpoint never marks the whole FMP integration as down")

    finally:
        fmp.requests.get = original_get
        fmp.FMP_API_KEY = original_fmp_key
        alt_data.FMP_API_KEY = original_alt_key
        _set_news_enabled(original_news_enabled)
        alt_data.fetch_fmp_news.clear()

    return checks


def main() -> int:
    try:
        checks = run_contract_checks()
    except Exception as exc:
        print("=== FMP News Resilience Contract Checks ===")
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1

    print("=== FMP News Resilience Contract Checks ===")
    for check in checks:
        print(f"[OK] {check}")
    print("")
    print(f"Resultado: OK ({len(checks)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
