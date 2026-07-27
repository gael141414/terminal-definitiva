"""Runner local del job nocturno de validación cruzada SEC↔FMP (Sub-fase 3b).

Calcado de modulos/briefing_runner.py (mismo patrón, Patrón B — cron local,
no GitHub Actions: este job necesita `data/watchlist.json` real, que nunca
existe en un checkout de CI, ver diagnóstico de la Sub-fase 3). No renderiza
nada en Streamlit ni construye superficie en Watchlist/Auditoría Forense —
eso es la Sub-fase 3c.

Por cada ticker seleccionado:
1. Descarga FMP (``extraer_datos_fundamentales_fmp``) y SEC
   (``downloader.obtener_estados_financieros_con_diagnostico``, siempre
   ``usar_cache=False`` para obtener ``period_end_dates`` reales vía
   ``df.attrs`` — ver Sub-fase 1).
2. Compara con ``comparar_estados_financieros`` (Sub-fase 1, sin cambios).
3. Persiste inmediatamente con ``sec_validation_store.save_sec_validation_result``
   (Sub-fase 3a) — un fallo a mitad del batch no pierde lo ya procesado.
4. Si hay discrepancias nuevas (``find_new_discrepancies``, ya calculado por
   el propio ``save_sec_validation_result``), se acumulan para el aviso de
   Telegram agrupado al final de la corrida.

Selección/rotación de tickers
------------------------------
"El más antiguo sin verificar primero": se ordena por
``last_sec_validation.last_attempt_at`` ascendente (no
``last_successful_check_at`` — un ticker que falló anoche por rate limit
debe poder reintentarse pronto, no quedar bloqueado eternamente detrás de
otros que sí tuvieron éxito). Un ticker nunca verificado no tiene ese campo
en absoluto, así que ordena como cadena vacía — antes que cualquier fecha
ISO real — y va primero.

Pausas y tope por corrida
--------------------------
DEFAULT_INTER_TICKER_PAUSE_SECONDS (1.5s) y DEFAULT_MAX_TICKERS_PER_RUN (40)
son los valores propuestos en el diagnóstico de la Sub-fase 3: a ~18s por
ticker (medido en la Sub-fase 2 con AAPL real, años=5) más esta pausa, 40
tickers tardan varios minutos, no horas — el throttle interno de edgartools
(8 req/s) ya se autorregula dentro de este único proceso secuencial; la
pausa es cortesía adicional, no una necesidad estricta a esta escala.

Notificación Telegram
-----------------------
Reutiliza ``modulos.manual_delivery.send_telegram_text`` tal cual — el mismo
cliente que ya usa ``briefing_runner.py``. Su docstring dice "no debe
llamarse desde flujos automáticos", pero ``run_local_briefing`` YA lo hace
desde un cron documentado (docs/automation_scheduler.md) en cuanto
``send_telegram=True, confirmed=True`` — la "confirmación explícita" es que
el usuario haya puesto ``--send-telegram --yes`` en su propia línea de
cron, no una confirmación interactiva por corrida. Este runner sigue
exactamente ese mismo criterio, sin inventar un cliente de Telegram nuevo.

No se reutiliza ``modulos.automation_schedule.evaluate_delivery_frequency``
(el limitador de "cuántos envíos por periodo" del briefing diario): esa
cuota es para no repetir el MISMO briefing de mercado varias veces al día,
un problema distinto. Aquí el propio ``find_new_discrepancies`` ya garantiza
que solo se notifica cuando algo genuinamente cambió desde la corrida
anterior — no hace falta una segunda capa de limitación de frecuencia.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from modulos.automation_logs import log_sec_validation_run
from modulos.data_provider_errors import NO_DATA
from modulos.fmp_api import extraer_datos_fundamentales_fmp
from modulos.manual_delivery import send_telegram_text
from modulos.sec_fmp_cross_validation import MetricComparison, PERIOD_MISALIGNED, comparar_estados_financieros
from modulos.sec_validation_store import save_sec_validation_result, sec_validation_summary
from modulos.watchlist import cargar_watchlist

DEFAULT_MAX_TICKERS_PER_RUN = 40
DEFAULT_INTER_TICKER_PAUSE_SECONDS = 1.5
DEFAULT_YEARS = 5


@dataclass(frozen=True)
class TickerRunResult:
    ticker: str
    ok: bool
    status_code: str | None
    comparisons_count: int
    new_discrepancies: list[MetricComparison] = field(default_factory=list)


@dataclass(frozen=True)
class SecValidationRunResult:
    started_at: str
    finished_at: str
    tickers_selected: list[str]
    ticker_results: list[TickerRunResult]
    telegram_attempted: bool = False
    telegram_ok: bool = False
    telegram_detail: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def select_tickers_to_process(watchlist: dict, *, max_tickers: int) -> list[str]:
    """Ordena la watchlist por ``last_attempt_at`` ascendente (el más antiguo
    sin verificar primero; nunca verificado = primero de todos) y devuelve
    como mucho ``max_tickers``."""

    tickers = sorted({str(t).upper().strip() for t in watchlist.keys() if str(t).strip()})

    def _last_attempt_key(ticker: str) -> str:
        return str(sec_validation_summary(ticker).get("last_attempt_at") or "")

    ordenados = sorted(tickers, key=_last_attempt_key)
    if max_tickers <= 0:
        return ordenados
    return ordenados[:max_tickers]


def _process_ticker(ticker: str, *, años: int) -> TickerRunResult:
    ticker = str(ticker).upper().strip()

    try:
        df_is_fmp, df_bs_fmp, df_cf_fmp, _df_metrics_fmp = extraer_datos_fundamentales_fmp(ticker, años)
    except Exception:
        df_is_fmp = df_bs_fmp = df_cf_fmp = None

    if df_is_fmp is None and df_bs_fmp is None and df_cf_fmp is None:
        # extraer_datos_fundamentales_fmp no expone qué causa concreta tuvo
        # (ya la clasifica y registra internamente, ver fmp_api.py) — NO_DATA
        # es la lectura honesta disponible aquí: no hay nada con qué comparar.
        nuevas = save_sec_validation_result(ticker, [], status_code=NO_DATA)
        return TickerRunResult(ticker=ticker, ok=False, status_code=NO_DATA, comparisons_count=0, new_discrepancies=nuevas)

    import downloader  # perezoso: edgartools solo se importa si de verdad hace falta comparar

    df_is_sec, df_bs_sec, df_cf_sec, sec_status_code = downloader.obtener_estados_financieros_con_diagnostico(
        ticker, años=años, usar_cache=False,
    )
    if sec_status_code is not None:
        nuevas = save_sec_validation_result(ticker, [], status_code=sec_status_code)
        return TickerRunResult(ticker=ticker, ok=False, status_code=sec_status_code, comparisons_count=0, new_discrepancies=nuevas)

    comparisons = comparar_estados_financieros(
        df_is_fmp=df_is_fmp, df_cf_fmp=df_cf_fmp, df_bs_fmp=df_bs_fmp,
        df_is_sec=df_is_sec, df_cf_sec=df_cf_sec, df_bs_sec=df_bs_sec,
    )
    nuevas = save_sec_validation_result(ticker, comparisons, status_code=None)
    return TickerRunResult(ticker=ticker, ok=True, status_code=None, comparisons_count=len(comparisons), new_discrepancies=nuevas)


def _format_comparison_line(comp: MetricComparison) -> str:
    if comp.classification == PERIOD_MISALIGNED:
        return (
            f"{comp.metric} ({comp.year}): fechas de periodo no coinciden — posible restatement "
            f"(FMP {comp.fmp_period_end or '¿?'} vs SEC {comp.sec_period_end or '¿?'})"
        )
    diff_txt = f"{comp.diff_pct:+.1f}%" if comp.diff_pct is not None else "n/d"
    fmp_txt = f"{comp.fmp_value:,.2f}" if comp.fmp_value is not None else "n/d"
    sec_txt = f"{comp.sec_value:,.2f}" if comp.sec_value is not None else "n/d"
    return f"{comp.metric} ({comp.year}): FMP {fmp_txt} vs SEC {sec_txt} ({diff_txt})"


def build_sec_validation_telegram_message(
    new_discrepancies_by_ticker: dict[str, list[MetricComparison]],
) -> str | None:
    """Mensaje agrupado (un mensaje por corrida, no uno por ticker) — mismo
    criterio que el resto de automatizaciones de este proyecto (briefing
    diario, dígest de Telegram): un aviso por corrida, no uno por hallazgo,
    para no generar una ráfaga de mensajes si varios tickers cambian la
    misma noche. Telegram soporta el texto largo resultante vía el
    trocedado ya existente en manual_delivery.send_telegram_text.

    Devuelve ``None`` si no hay nada que notificar (no se envía nada)."""

    if not new_discrepancies_by_ticker:
        return None

    lines = [
        "🔍 ValueQuant — Discrepancias SEC↔FMP nuevas",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        f"{len(new_discrepancies_by_ticker)} ticker(s) con discrepancias nuevas esta noche:",
    ]
    for ticker, comparisons in new_discrepancies_by_ticker.items():
        lines.append("")
        lines.append(f"📌 {ticker}")
        for comp in comparisons:
            lines.append(f"- {_format_comparison_line(comp)}")

    lines.extend(["", "Detalle completo en Auditoría Forense → Modo Auditoría."])
    return "\n".join(lines)


def run_sec_validation_batch(
    *,
    max_tickers: int = DEFAULT_MAX_TICKERS_PER_RUN,
    inter_ticker_pause_seconds: float = DEFAULT_INTER_TICKER_PAUSE_SECONDS,
    años: int = DEFAULT_YEARS,
    send_telegram: bool = False,
    confirmed: bool = False,
) -> SecValidationRunResult:
    """Ejecuta una corrida completa: selecciona tickers, los procesa
    secuencialmente con persistencia inmediata, registra el evento en
    modulos/automation_logs.py y, si se pide, notifica por Telegram."""

    started_at = _now_iso()
    watchlist = cargar_watchlist()
    selected = select_tickers_to_process(watchlist, max_tickers=max_tickers)

    ticker_results: list[TickerRunResult] = []
    new_discrepancies_by_ticker: dict[str, list[MetricComparison]] = {}

    for index, ticker in enumerate(selected):
        result = _process_ticker(ticker, años=años)
        ticker_results.append(result)
        if result.new_discrepancies:
            new_discrepancies_by_ticker[ticker] = result.new_discrepancies
        if index < len(selected) - 1:
            time.sleep(inter_ticker_pause_seconds)

    tickers_processed = sum(1 for r in ticker_results if r.ok)
    tickers_failed = sum(1 for r in ticker_results if not r.ok)
    new_discrepancies_count = sum(len(v) for v in new_discrepancies_by_ticker.values())

    log_sec_validation_run(
        tickers_selected=selected,
        tickers_processed=tickers_processed,
        tickers_failed=tickers_failed,
        new_discrepancies_count=new_discrepancies_count,
    )

    telegram_attempted = False
    telegram_ok = False
    telegram_detail = ""

    message = build_sec_validation_telegram_message(new_discrepancies_by_ticker)
    if message is not None and send_telegram:
        telegram_attempted = True
        if not confirmed:
            telegram_detail = "Envio a Telegram bloqueado: falta confirmacion explicita (--yes)."
        else:
            delivery = send_telegram_text(message)
            telegram_ok = delivery.ok
            telegram_detail = delivery.detail

    return SecValidationRunResult(
        started_at=started_at,
        finished_at=_now_iso(),
        tickers_selected=selected,
        ticker_results=ticker_results,
        telegram_attempted=telegram_attempted,
        telegram_ok=telegram_ok,
        telegram_detail=telegram_detail,
    )
