#!/usr/bin/env python3
"""¿Predicen el retorno futuro los pilares de valoración y fundamentales?

Reconstruye los pilares con lo que se sabía en cada FECHA DE FILING real y los
cruza con el retorno posterior. Sin look-ahead.

Uso:
    python scripts/validar_pilares_point_in_time.py --tickers 60
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.validacion_pilares import (
    HORIZONTES, SIGNO_ESPERADO, construir_observaciones, medir_poder_predictivo,
    tabla_por_decil,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=int, default=60)
    parser.add_argument("--salida", type=str, default="")
    args = parser.parse_args()

    from modulos.screener_avanzado import FALLBACK_UNIVERSE
    from modulos.swing_scanner import descargar_universo

    # Grandes capitalizaciones, NO _universo_mercado(): esa función devuelve los
    # N primeros de una lista ALFABÉTICA (A, AA, AACG, AADX...), un corte de
    # microcaps y sociedades vacías cuyos filings a menudo ni traen XBRL.
    tickers = sorted({t for lista in FALLBACK_UNIVERSE.values() for t in lista})[: args.tickers]
    print(f"Reconstrucción point-in-time · {len(tickers)} valores", flush=True)

    precios_por_ticker = {}
    for ticker, df in descargar_universo(tuple(tickers), periodo="10y").items():
        precios_por_ticker[ticker] = df["Close"].dropna()
    print(f"  con precios: {len(precios_por_ticker)}", flush=True)

    observaciones = []
    for i, (ticker, precios) in enumerate(precios_por_ticker.items(), 1):
        nuevas = construir_observaciones(ticker, precios)
        observaciones.extend(nuevas)
        if i % 10 == 0:
            print(f"  {i}/{len(precios_por_ticker)} · {len(observaciones)} observaciones",
                  flush=True)

    print(f"\nObservaciones point-in-time: {len(observaciones)}")
    if not observaciones:
        print("Sin observaciones: nada que medir.")
        return 1

    resumen = medir_poder_predictivo(observaciones)
    print(f"Valores distintos: {resumen.get('tickers')}")

    if not resumen.get("suficiente"):
        print(f"\n{resumen.get('nota')}")
        return 0

    print("\n=== CORRELACIÓN DE SPEARMAN CON EL RETORNO POSTERIOR ===")
    print(f"{'pilar':<22}{'signo esp.':<12}" + "".join(f"{f'{h}d':>16}" for h in HORIZONTES))
    print("-" * 82)
    for pilar in SIGNO_ESPERADO:
        bloque = resumen.get(pilar)
        if not bloque:
            continue
        fila = f"{pilar:<22}{bloque['signo_esperado']:<12}"
        for h in HORIZONTES:
            d = bloque.get(f"{h}d", {})
            rho = d.get("spearman")
            if rho is None:
                fila += f"{'n/d':>16}"
            else:
                marca = "ok" if d.get("coherente") else "AL REVÉS"
                fila += f"{f'{rho:+.3f} {marca}':>16}"
        print(fila)

    print("\n=== RETORNO A 252 SESIONES POR QUINTIL ===")
    for pilar in ("piotroski_norm", "altman", "percentil_multiplos"):
        tabla = tabla_por_decil(observaciones, pilar, 252)
        if tabla.empty:
            continue
        print(f"\n  -- {pilar} (signo esperado: {SIGNO_ESPERADO[pilar]}) --")
        print(tabla.to_string())

    if args.salida:
        Path(args.salida).write_text(
            json.dumps({"resumen": resumen,
                        "observaciones": [o.to_dict() for o in observaciones]},
                       indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
        print(f"\nJSON -> {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
