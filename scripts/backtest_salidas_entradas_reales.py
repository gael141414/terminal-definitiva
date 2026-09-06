#!/usr/bin/env python3
"""Ejecuta la validación pre-registrada de las reglas de salida.

Ver docs/preregistro_validacion_salidas.md — hipótesis, benchmarks y métricas se
escribieron y commitearon ANTES de esta ejecución.

Uso:
    python scripts/backtest_salidas_entradas_reales.py --tickers 120 --anios 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.backtest_salidas import (
    AGUANTAR, ALEATORIA, COMPUESTA, REGLAS, SEMILLA, STOP_FIJO, TECNICA,
    Cierre, aplicar_reglas, comparar_reglas, diferencia_significativa,
    generar_entradas,
)
from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_scanner import descargar_universo


def _regimen_por_fecha(spy: pd.DataFrame | None) -> pd.Series | None:
    """Alcista si el S&P cotiza sobre su media de 200; bajista si no.

    Es el mismo sensor que usa swing_regimen.Regimen.indice_sobre_media, que es
    lo que se quiere para contrastar la hipótesis de Kaminski-Lo.
    """
    if spy is None or spy.empty or "Close" not in spy.columns:
        return None
    cierre = spy["Close"].dropna()
    media = cierre.rolling(200).mean()
    return (cierre > media).reindex(cierre.index)


def ejecutar(tickers: list[str], anios: int) -> dict:
    precios = descargar_universo(tuple(tickers), periodo=f"{anios}y")
    print(f"  universo con datos: {len(precios)}/{len(tickers)}", flush=True)

    spy = precios.get("SPY")
    if spy is None:
        spy = descargar_universo(("SPY",), periodo=f"{anios}y").get("SPY")
    regimen = _regimen_por_fecha(spy)

    enriquecidos = {}
    for ticker, df in precios.items():
        try:
            enriquecidos[ticker] = enriquecer_ohlcv(df)
        except Exception:
            continue

    entradas = generar_entradas(enriquecidos)
    print(f"  entradas generadas: {len(entradas)}", flush=True)
    if not entradas:
        return {}

    aleatorio = random.Random(SEMILLA)
    cierres: list[Cierre] = []
    for entrada in entradas:
        df = enriquecidos.get(entrada.ticker)
        if df is None:
            continue
        favorable = None
        if regimen is not None:
            try:
                previos = regimen[regimen.index <= entrada.fecha_entrada]
                if not previos.empty:
                    favorable = bool(previos.iloc[-1])
            except Exception:
                favorable = None
        for cierre in aplicar_reglas(df, entrada, aleatorio=aleatorio,
                                     regimen_favorable=favorable).values():
            cierre.motivo = f"{cierre.motivo}|{'alcista' if favorable else 'bajista' if favorable is False else 'nd'}"
            cierres.append(cierre)

    print(f"  cierres simulados: {len(cierres)}", flush=True)

    global_ = {r: m.como_fila() for r, m in comparar_reglas(cierres).items()}

    # Por estrategia de entrada (hipótesis 3).
    por_estrategia: dict[str, dict] = {}
    for estrategia in sorted({c.estrategia for c in cierres}):
        subconjunto = [c for c in cierres if c.estrategia == estrategia]
        por_estrategia[estrategia] = {
            "metricas": {r: m.como_fila() for r, m in comparar_reglas(subconjunto).items()},
            "vs_aguantar": {
                r: diferencia_significativa(subconjunto, r, AGUANTAR)
                for r in (TECNICA, COMPUESTA, STOP_FIJO, ALEATORIA)
            },
        }

    # Por régimen (hipótesis 2).
    por_regimen: dict[str, dict] = {}
    for etiqueta in ("alcista", "bajista"):
        subconjunto = [c for c in cierres if c.motivo.endswith(f"|{etiqueta}")]
        if len(subconjunto) < 50:
            continue
        por_regimen[etiqueta] = {
            "metricas": {r: m.como_fila() for r, m in comparar_reglas(subconjunto).items()},
            "vs_aguantar": {
                r: diferencia_significativa(subconjunto, r, AGUANTAR)
                for r in (TECNICA, COMPUESTA, STOP_FIJO)
            },
        }

    # Walk-forward por ventanas anuales de la fecha de entrada.
    por_ventana: dict[str, dict] = {}
    años = sorted({pd.Timestamp(c.fecha_entrada).year for c in cierres})
    for año in años:
        subconjunto = [c for c in cierres if pd.Timestamp(c.fecha_entrada).year == año]
        if len(subconjunto) < 50:
            continue
        por_ventana[str(año)] = {
            r: diferencia_significativa(subconjunto, r, AGUANTAR)
            for r in (TECNICA, COMPUESTA)
        }

    return {
        "global": global_,
        "vs_aguantar": {r: diferencia_significativa(cierres, r, AGUANTAR)
                        for r in (TECNICA, COMPUESTA, STOP_FIJO, ALEATORIA)},
        "por_estrategia": por_estrategia,
        "por_regimen": por_regimen,
        "walk_forward": por_ventana,
        "n_cierres": len(cierres),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=int, default=120)
    parser.add_argument("--anios", type=int, default=10)
    parser.add_argument("--salida", type=str, default="")
    parser.add_argument("--universo", choices=("grandes", "alfabetico"), default="grandes")
    args = parser.parse_args()

    if args.universo == "grandes":
        # 119 grandes capitalizaciones repartidas en 11 sectores.
        #
        # IMPORTANTE: _universo_mercado() devuelve los N PRIMEROS de una lista
        # ALFABÉTICA (A, AA, AACG, AADX, AAGH...), no los N mayores. Es un corte
        # dominado por microcaps y sociedades vacías, que no se parece a lo que
        # se analiza con esta aplicación y donde además el coste real de operar
        # es muy superior al 0,1% que asume el backtest.
        from modulos.screener_avanzado import FALLBACK_UNIVERSE

        tickers = sorted({t for lista in FALLBACK_UNIVERSE.values() for t in lista})[: args.tickers]
    else:
        from modulos.swing_ui import _universo_mercado

        tickers = _universo_mercado(args.tickers)
    if "SPY" not in tickers:
        tickers.append("SPY")
    print(f"Validación pre-registrada · {len(tickers)} valores · {args.anios} años", flush=True)

    resultado = ejecutar(tickers, args.anios)
    if not resultado:
        print("Sin entradas: nada que medir.")
        return 1

    print("\n=== GLOBAL ===")
    print(pd.DataFrame(resultado["global"]).T.to_string())
    print("\n=== DIFERENCIA FRENTE A AGUANTAR (emparejada, IC95) ===")
    for regla, d in resultado["vs_aguantar"].items():
        if d["diferencia_pct"] is None:
            continue
        marca = "SIGNIFICATIVA" if d["significativa"] else "no significativa"
        print(f"  {regla:<10} {d['diferencia_pct']:+7.3f} pts  "
              f"IC95 [{d['ic'][0]:+.3f}, {d['ic'][1]:+.3f}]  n={d['n']}  {marca}")

    print("\n=== POR RÉGIMEN (hipótesis Kaminski-Lo) ===")
    for etiqueta, bloque in resultado["por_regimen"].items():
        print(f"  -- {etiqueta} --")
        for regla, d in bloque["vs_aguantar"].items():
            if d["diferencia_pct"] is None:
                continue
            marca = "SIGNIFICATIVA" if d["significativa"] else "no significativa"
            print(f"     {regla:<10} {d['diferencia_pct']:+7.3f} pts  "
                  f"IC95 [{d['ic'][0]:+.3f}, {d['ic'][1]:+.3f}]  n={d['n']}  {marca}")

    print("\n=== POR ESTRATEGIA DE ENTRADA (hipótesis 3) ===")
    for estrategia, bloque in resultado["por_estrategia"].items():
        d = bloque["vs_aguantar"].get(COMPUESTA, {})
        if d.get("diferencia_pct") is None:
            continue
        marca = "SIG" if d["significativa"] else "ns "
        print(f"  {estrategia:<22} compuesta vs aguantar: {d['diferencia_pct']:+7.3f} pts  "
              f"IC95 [{d['ic'][0]:+.3f}, {d['ic'][1]:+.3f}]  n={d['n']}  {marca}")

    print("\n=== WALK-FORWARD (por año de entrada) ===")
    for año, bloque in resultado["walk_forward"].items():
        d = bloque[COMPUESTA]
        if d["diferencia_pct"] is None:
            continue
        print(f"  {año}: compuesta {d['diferencia_pct']:+7.3f} pts  n={d['n']}  "
              f"{'SIG' if d['significativa'] else 'ns'}")

    if args.salida:
        Path(args.salida).write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=str),
                                     encoding="utf-8")
        print(f"\nJSON -> {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
