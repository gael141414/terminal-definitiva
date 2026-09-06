#!/usr/bin/env python3
"""Job: congela la decisión de venta de la watchlist, para validación forward.

Se ejecuta periódicamente (diario o semanal). Cada ejecución añade una
observación por valor: la decisión tal y como se tomó ese día, SIN saber qué
pasó después. Es la única validación que nadie puede acusar de contaminada,
porque el registro se escribe antes de que exista el retorno con el que se
comparará.

Uso:
    python jobs/congelar_decisiones.py                    # watchlist
    python jobs/congelar_decisiones.py --tickers AAPL,MSFT
    python jobs/congelar_decisiones.py --informe          # lee, no escribe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _universo(explicitos: str | None) -> list[str]:
    if explicitos:
        return [t.strip().upper() for t in explicitos.split(",") if t.strip()]
    try:
        from modulos.watchlist import cargar_watchlist

        df = cargar_watchlist()
        if df is not None and not df.empty and "Ticker" in df.columns:
            return [str(t).strip().upper() for t in df["Ticker"].dropna().unique()]
    except Exception as exc:
        print(f"[aviso] no se pudo leer la watchlist: {exc}")
    return []


def congelar(tickers: list[str], perfil: str) -> int:
    from modulos.congelado_forward import congelar_universo, guardar_registros

    registros = congelar_universo(tickers, perfil=perfil)
    if not registros:
        print("Sin decisiones que congelar.")
        return 0

    nuevos = guardar_registros(registros)
    print(f"Congeladas {len(registros)} decisiones; {nuevos} nuevas en el histórico.")
    for r in registros[:10]:
        score = f"{r.sell_score:.0f}" if r.sell_score is not None else "n/d"
        print(f"  {r.ticker:<6} {r.accion:<9} score {score:>4}  precio {r.precio}")
    return nuevos


def informe(horizonte: int) -> None:
    """Cruza lo congelado con el retorno posterior ya realizado."""
    import pandas as pd

    from modulos.congelado_forward import (
        INICIO_CONGELADO, cargar_registros, cruzar_con_retorno_posterior,
        resumen_poder_predictivo,
    )

    registros = cargar_registros()
    print(f"Registro forward desde {INICIO_CONGELADO}: {len(registros)} observaciones.")
    if not registros:
        return

    tickers = sorted({r["ticker"] for r in registros})
    precios: dict[str, pd.Series] = {}
    try:
        from modulos.swing_scanner import descargar_universo

        for ticker, df in descargar_universo(tuple(tickers), periodo="2y").items():
            precios[ticker] = df["Close"].dropna()
    except Exception as exc:
        print(f"[aviso] sin precios para cruzar: {exc}")
        return

    cruce = cruzar_con_retorno_posterior(registros, precios, horizonte_dias=horizonte)
    resumen = resumen_poder_predictivo(cruce)
    print(json.dumps(resumen, indent=2, ensure_ascii=False))

    if not resumen.get("suficiente"):
        print(
            "\nEsto es lo esperado al principio: el registro forward necesita que "
            f"pasen {horizonte} sesiones desde cada snapshot antes de poder medir nada."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=str, default="")
    parser.add_argument("--perfil", type=str, default="largo_plazo")
    parser.add_argument("--informe", action="store_true")
    parser.add_argument("--horizonte", type=int, default=63)
    args = parser.parse_args()

    if args.informe:
        informe(args.horizonte)
        return 0

    tickers = _universo(args.tickers)
    if not tickers:
        print("Sin valores que congelar: pasa --tickers o guarda algo en la watchlist.")
        return 1
    congelar(tickers, args.perfil)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
