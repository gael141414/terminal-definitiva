"""Persistencia local de resultados de validación cruzada SEC↔FMP (Sub-fase 3a).

Calcado de modulos/analysis_store.py (mismo patrón: JSON local, sin base de
datos real, suficiente para MVP/local-first) — no un archivo nuevo para el
campo compacto, reutiliza el mismo ``data/watchlist.json`` que ya usa
``last_analysis``.

Dos piezas de almacenamiento:

1. ``data/sec_validation_history.json`` — historial completo por ticker, una
   entrada por corrida (éxito o fallo), capado a
   ``MAX_SEC_VALIDATION_RUNS_PER_TICKER``.
2. ``last_sec_validation`` dentro del item existente de ``watchlist.json`` —
   resumen compacto de la última corrida, para lecturas rápidas (Watchlist,
   Modo Auditoría) sin cargar el historial completo. Mismo mecanismo que
   ``last_analysis`` (``existing.update({...})``), sin pisar ``target``,
   ``source`` ni ``last_analysis``.

Distinción clave, ya pensada para el aviso de Telegram de la Sub-fase 3b: un
intento fallido (rate limit, ticker no encontrado en EDGAR, timeout — los
códigos tipados de ``modulos/data_provider_errors.py``) nunca debe pisar el
resultado de la última corrida CORRECTA con ceros falsos — eso se leería como
"auditoría limpia" cuando en realidad la comprobación no pudo hacerse. Por
eso el resumen compacto separa ``last_attempt_at``/``last_attempt_status_code``
(se actualizan siempre) de ``last_successful_check_at`` y los contadores
(solo se actualizan en una corrida sin ``status_code``).

``find_new_discrepancies`` compara la corrida actual contra la entrada más
reciente del historial (antes de añadir la nueva) para distinguir una
discrepancia "ya vista antes" de una "nueva desde la última corrida" — la
señal que necesitará el aviso de Telegram de la Sub-fase 3b. No se implementa
el envío aquí, solo la detección.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from modulos.analysis_store import DATA_FOLDER, WATCHLIST_FILE, _read_json, _write_json
from modulos.sec_fmp_cross_validation import (
    DISCREPANCY,
    MATCH,
    NOT_COMPARABLE,
    PERIOD_MISALIGNED,
    MetricComparison,
)

SEC_VALIDATION_HISTORY_FILE = DATA_FOLDER / "sec_validation_history.json"

# Cadencia distinta de MAX_ANALYSES_PER_TICKER (25): aquellos son snapshots
# manuales de Research Core, guardados con poca frecuencia; una corrida SEC es
# nocturna (Sub-fase 3b), así que 25 serían menos de un mes de histórico. 60
# cubre al menos un ciclo trimestral de resultados completo sin crecer sin
# límite.
MAX_SEC_VALIDATION_RUNS_PER_TICKER = 60

# Clasificaciones que ameritan aviso: una discrepancia numérica real y un
# desalineamiento de periodo (posible restatement) — ambas son "algo cambió
# que merece una mirada", aunque period_no_alineado no sea una discrepancia
# de valor de fiar en sí misma (ver modulos/sec_fmp_cross_validation.py).
_NOTEWORTHY_CLASSIFICATIONS = (DISCREPANCY, PERIOD_MISALIGNED)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_safe_comparison(comp: MetricComparison) -> dict[str, Any]:
    """``asdict`` con NaN saneado a None (nunca debería llegar NaN — ver
    ``_to_float_or_none`` en sec_fmp_cross_validation.py, que ya convierte NaN
    a None antes de construir el dataclass — pero es la frontera de
    persistencia, y NaN no es JSON válido, así que se sanea aquí también)."""

    payload = asdict(comp)
    for key in ("fmp_value", "sec_value", "diff_pct"):
        value = payload.get(key)
        if isinstance(value, float) and not math.isfinite(value):
            payload[key] = None
    return payload


def _comparison_from_dict(raw: dict[str, Any]) -> MetricComparison | None:
    try:
        return MetricComparison(**raw)
    except TypeError:
        return None


def load_sec_validation_history() -> dict[str, list[dict[str, Any]]]:
    """Historial completo, sin normalizar. Cada entrada:
    ``{"checked_at": iso, "status_code": str|None, "comparisons": [dict, ...]}``,
    más reciente primero."""

    data = _read_json(SEC_VALIDATION_HISTORY_FILE, {})
    return data if isinstance(data, dict) else {}


def _previous_entry(ticker: str) -> dict[str, Any] | None:
    """Entrada más reciente ya guardada para ``ticker``, o ``None`` si nunca
    se ha corrido una validación para él."""

    history = load_sec_validation_history().get(ticker, [])
    if isinstance(history, list) and history:
        first = history[0]
        return first if isinstance(first, dict) else None
    return None


def find_new_discrepancies(
    ticker: str,
    current_comparisons: list[MetricComparison],
) -> list[MetricComparison]:
    """Discrepancias/desalineamientos de periodo en ``current_comparisons``
    que NO lo eran (o no existían) en la corrida anterior guardada para
    ``ticker``. Compara por (métrica, año) — no por posición.

    Si nunca hubo una corrida anterior, todo lo que hoy sea discrepancia o
    periodo_no_alineado cuenta como "nuevo" (nunca se había visto).
    """

    ticker = str(ticker or "").upper().strip()
    noteworthy_now = [c for c in current_comparisons if c.classification in _NOTEWORTHY_CLASSIFICATIONS]
    if not noteworthy_now:
        return []

    previous = _previous_entry(ticker)
    if previous is None:
        return noteworthy_now

    previous_classification_by_key: dict[tuple[str, str], str] = {}
    for raw in previous.get("comparisons", []) or []:
        if not isinstance(raw, dict):
            continue
        key = (raw.get("metric"), raw.get("year"))
        previous_classification_by_key[key] = raw.get("classification")

    return [
        comp
        for comp in noteworthy_now
        if previous_classification_by_key.get((comp.metric, comp.year)) not in _NOTEWORTHY_CLASSIFICATIONS
    ]


def _summarize_counts(comparisons: list[MetricComparison]) -> dict[str, int]:
    counts = {MATCH: 0, DISCREPANCY: 0, NOT_COMPARABLE: 0, PERIOD_MISALIGNED: 0}
    for comp in comparisons:
        counts[comp.classification] = counts.get(comp.classification, 0) + 1
    return counts


def _worst_discrepancy(comparisons: list[MetricComparison]) -> MetricComparison | None:
    """La discrepancia (no el desalineamiento de periodo, que no tiene una
    diferencia de fiar) con mayor magnitud relativa."""

    candidatos = [c for c in comparisons if c.classification == DISCREPANCY and c.diff_pct is not None]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: abs(c.diff_pct))


def _append_history_entry(
    ticker: str,
    *,
    checked_at: str,
    status_code: str | None,
    comparisons: list[MetricComparison],
) -> None:
    history = load_sec_validation_history()
    ticker_history = history.get(ticker, [])
    if not isinstance(ticker_history, list):
        ticker_history = []

    entry = {
        "checked_at": checked_at,
        "status_code": status_code,
        "comparisons": [_json_safe_comparison(c) for c in comparisons],
    }
    ticker_history.insert(0, entry)
    history[ticker] = ticker_history[:MAX_SEC_VALIDATION_RUNS_PER_TICKER]
    _write_json(SEC_VALIDATION_HISTORY_FILE, history)


def _update_watchlist_summary(
    ticker: str,
    *,
    checked_at: str,
    status_code: str | None,
    comparisons: list[MetricComparison],
) -> None:
    watchlist = _read_json(WATCHLIST_FILE, {})
    if not isinstance(watchlist, dict):
        watchlist = {}

    existing = watchlist.get(ticker, {})
    if not isinstance(existing, dict):
        existing = {}

    previous_summary = existing.get("last_sec_validation", {})
    summary = dict(previous_summary) if isinstance(previous_summary, dict) else {}

    # Se actualiza siempre, éxito o fallo: cuándo fue el último intento y por
    # qué código (None si tuvo éxito).
    summary["last_attempt_at"] = checked_at
    summary["last_attempt_status_code"] = status_code

    if status_code is None:
        # Solo una corrida sin fallo actualiza el resultado real — un fallo
        # transitorio nunca debe pisar esto con ceros falsos (se leería como
        # "auditoría limpia" cuando en realidad no se pudo comprobar).
        counts = _summarize_counts(comparisons)
        worst = _worst_discrepancy(comparisons)
        summary.update(
            {
                "last_successful_check_at": checked_at,
                "match_count": counts.get(MATCH, 0),
                "discrepancy_count": counts.get(DISCREPANCY, 0),
                "period_misaligned_count": counts.get(PERIOD_MISALIGNED, 0),
                "not_comparable_count": counts.get(NOT_COMPARABLE, 0),
                "worst_metric": worst.metric if worst else None,
                "worst_year": worst.year if worst else None,
                "worst_diff_pct": worst.diff_pct if worst else None,
            }
        )

    existing["last_sec_validation"] = summary
    watchlist[ticker] = existing
    _write_json(WATCHLIST_FILE, watchlist)


def save_sec_validation_result(
    ticker: str,
    comparisons: list[MetricComparison],
    *,
    status_code: str | None = None,
    checked_at: str | None = None,
) -> list[MetricComparison]:
    """Persiste una corrida de validación cruzada SEC↔FMP para ``ticker``.

    Añade una entrada al historial (capada) y actualiza el resumen compacto
    en ``watchlist.json`` sin pisar ``target``/``source``/``last_analysis``.

    ``status_code``: ``None`` si la corrida obtuvo datos SEC y se pudo
    comparar; un código de ``modulos/data_provider_errors.py`` (p. ej.
    ``RATE_LIMITED``, ``INVALID_TICKER``) si la corrida falló antes de poder
    comparar nada — en ese caso ``comparisons`` debe venir vacía.

    Devuelve las discrepancias/desalineamientos de periodo que son nuevos
    frente a la corrida anterior (pensado para que la Sub-fase 3b decida si
    avisa por Telegram; el envío no es parte de esta función).
    """

    ticker = str(ticker or "").upper().strip()
    if not ticker:
        raise ValueError("No se puede guardar una validación SEC sin ticker.")

    checked_at = checked_at or _now_iso()

    nuevas = find_new_discrepancies(ticker, comparisons)
    _append_history_entry(ticker, checked_at=checked_at, status_code=status_code, comparisons=comparisons)
    _update_watchlist_summary(ticker, checked_at=checked_at, status_code=status_code, comparisons=comparisons)

    return nuevas


def sec_validation_summary(ticker: str) -> dict[str, Any]:
    """Resumen compacto de la última corrida para ``ticker`` (lectura directa
    de ``watchlist.json``, sin cargar el historial completo)."""

    ticker = str(ticker or "").upper().strip()
    watchlist = _read_json(WATCHLIST_FILE, {})
    if not isinstance(watchlist, dict):
        return {}

    item = watchlist.get(ticker, {})
    if not isinstance(item, dict):
        return {}

    summary = item.get("last_sec_validation", {})
    return summary if isinstance(summary, dict) else {}


def sec_validation_history_for_ticker(ticker: str, *, limit: int | None = None) -> pd.DataFrame:
    """Historial normalizado (una fila por corrida) para ``ticker``, ordenado
    cronológicamente de antiguo a reciente."""

    ticker = str(ticker or "").upper().strip()
    if not ticker:
        return pd.DataFrame()

    history = load_sec_validation_history().get(ticker, [])
    if not isinstance(history, list):
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for entry in history:
        if not isinstance(entry, dict):
            continue
        raw_comparisons = entry.get("comparisons", []) or []
        comparisons = [c for c in (_comparison_from_dict(r) for r in raw_comparisons if isinstance(r, dict)) if c]
        counts = _summarize_counts(comparisons)
        worst = _worst_discrepancy(comparisons)
        rows.append(
            {
                "Ticker": ticker,
                "Verificado": entry.get("checked_at"),
                "Estado": entry.get("status_code") or "ok",
                "Coincide": counts.get(MATCH, 0),
                "Discrepancia": counts.get(DISCREPANCY, 0),
                "Periodo no alineado": counts.get(PERIOD_MISALIGNED, 0),
                "No comparable": counts.get(NOT_COMPARABLE, 0),
                "Peor métrica": worst.metric if worst else None,
                "Peor diferencia %": worst.diff_pct if worst else None,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).iloc[::-1].reset_index(drop=True)
    if limit is not None and limit > 0:
        df = df.tail(limit).reset_index(drop=True)
    return df
