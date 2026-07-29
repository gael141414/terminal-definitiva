#!/usr/bin/env python3
"""Ejecuta la validación cruzada SEC↔FMP de la watchlist desde terminal.

Ejemplos:
    python scripts/run_sec_validation.py
    python scripts/run_sec_validation.py --max-tickers 20 --years 5
    python scripts/run_sec_validation.py --send-telegram --yes

El envio a Telegram nunca se ejecuta sin `--send-telegram --yes`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.sec_validation_runner import (  # noqa: E402
    DEFAULT_INTER_TICKER_PAUSE_SECONDS,
    DEFAULT_MAX_TICKERS_PER_RUN,
    DEFAULT_YEARS,
    run_sec_validation_batch,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida cruzadamente FMP vs SEC EDGAR la watchlist local, sin abrir Streamlit.",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=DEFAULT_MAX_TICKERS_PER_RUN,
        help=f"Tope de tickers a procesar esta corrida. Default: {DEFAULT_MAX_TICKERS_PER_RUN}",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=DEFAULT_INTER_TICKER_PAUSE_SECONDS,
        help=f"Pausa entre tickers, en segundos. Default: {DEFAULT_INTER_TICKER_PAUSE_SECONDS}",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Años de histórico a comparar (FMP y SEC EDGAR). Default: {DEFAULT_YEARS}",
    )
    parser.add_argument(
        "--send-telegram",
        action="store_true",
        help="Envia un aviso a Telegram si aparecen discrepancias nuevas. Requiere también --yes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmacion explicita para envio a Telegram. Sin este flag no se envia nada.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_sec_validation_batch(
        max_tickers=args.max_tickers,
        inter_ticker_pause_seconds=args.pause_seconds,
        años=args.years,
        send_telegram=args.send_telegram,
        confirmed=args.yes,
    )

    print("=== ValueQuant SEC↔FMP Validation Runner ===")
    print(f"Inicio: {result.started_at}")
    print(f"Fin: {result.finished_at}")
    print(f"Tickers seleccionados ({len(result.tickers_selected)}): {', '.join(result.tickers_selected) or '(ninguno)'}")
    print("")

    for r in result.ticker_results:
        estado = "OK" if r.ok else f"FALLO ({r.status_code})"
        print(f"- {r.ticker}: {estado} · {r.comparisons_count} comparaciones · {len(r.new_discrepancies)} discrepancias nuevas")

    ok_count = sum(1 for r in result.ticker_results if r.ok)
    fail_count = len(result.ticker_results) - ok_count
    print("")
    print(f"Resumen: {ok_count} ok, {fail_count} fallidos.")

    if result.telegram_attempted:
        print("")
        print("Telegram:")
        print(f"- OK: {result.telegram_ok}")
        print(f"- Detalle: {result.telegram_detail}")

    # Fallo del proceso solo si hubo tickers seleccionados y TODOS fallaron
    # (indicio de un problema sistémico, p. ej. SEC EDGAR caído por completo)
    # — algunos fallos transitorios entre muchos éxitos son el caso normal,
    # ya persistido incrementalmente, y se reintentan solos la próxima corrida.
    if result.ticker_results and fail_count == len(result.ticker_results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
