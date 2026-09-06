#!/usr/bin/env python3
"""Eje de riesgo de las reglas de salida: curva, caída, cola y veredicto.

Ejecuta el pre-registro de docs/preregistro_eje_riesgo.md, commiteado antes.

Uso:
    python scripts/riesgo_salidas_informe.py --tickers 120 --anios 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.backtest_salidas import (
    AGUANTAR, ALEATORIA, COMPUESTA, REGLAS, SEMILLA, STOP_FIJO, TECNICA,
    Cierre, aplicar_reglas, generar_entradas,
)
from modulos.config import COLOR_ACCENT, COLOR_NEGATIVE, COLOR_POSITIVE, COLOR_PRIMARY, COLOR_WARNING
from modulos.indicadores import enriquecer_ohlcv
from modulos.riesgo_salidas import (
    CRITERIO, PESO_FIJO_SENSIBILIDAD, comparar_riesgo, curva_equity,
    metricas_riesgo, retornos_diarios_cartera, serie_drawdown, veredicto_seguro,
)

COLORES = {
    AGUANTAR: COLOR_POSITIVE, TECNICA: COLOR_PRIMARY, STOP_FIJO: COLOR_WARNING,
    COMPUESTA: COLOR_NEGATIVE, ALEATORIA: "#93a4bb",
}

# Episodio COVID: del máximo previo al mínimo del S&P 500.
COVID_INICIO, COVID_FIN = "2020-02-19", "2020-04-30"


def _preparar(tickers: list[str], anios: int):
    from modulos.swing_scanner import descargar_universo

    crudos = descargar_universo(tuple(tickers), periodo=f"{anios}y")
    precios = {}
    for ticker, df in crudos.items():
        try:
            precios[ticker] = enriquecer_ohlcv(df)
        except Exception:
            continue
    print(f"  universo con datos: {len(precios)}/{len(tickers)}", flush=True)

    entradas = generar_entradas(precios)
    print(f"  entradas: {len(entradas)}", flush=True)

    spy = precios.get("SPY")
    regimen = None
    if spy is not None:
        cierre = spy["Close"].dropna()
        regimen = cierre > cierre.rolling(200).mean()

    aleatorio = random.Random(SEMILLA)
    cierres: list[Cierre] = []
    for entrada in entradas:
        df = precios.get(entrada.ticker)
        if df is None:
            continue
        favorable = None
        if regimen is not None:
            previos = regimen[regimen.index <= entrada.fecha_entrada]
            if not previos.empty:
                favorable = bool(previos.iloc[-1])
        for c in aplicar_reglas(df, entrada, aleatorio=aleatorio,
                                regimen_favorable=favorable).values():
            c.motivo = f"{c.motivo}|{'alcista' if favorable else 'bajista' if favorable is False else 'nd'}"
            cierres.append(c)
    print(f"  cierres: {len(cierres)}", flush=True)
    return precios, cierres


def _graficas(precios, cierres, destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    generadas = []

    series = {}
    for regla in REGLAS:
        propios = [c for c in cierres if c.regla == regla]
        if propios:
            series[regla] = retornos_diarios_cartera(propios, precios)

    # 1. Curvas de equity
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for regla, diarios in series.items():
        eq = curva_equity(diarios)
        if not eq.empty:
            ax.plot(eq.index, eq.values, label=regla, color=COLORES.get(regla), linewidth=1.6)
    ax.set_yscale("log")
    ax.set_title("Curva de capital por regla de salida (escala logarítmica)")
    ax.set_ylabel("Capital (base 1)")
    ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(destino / "riesgo_equity.png", dpi=120); plt.close(fig)
    generadas.append("riesgo_equity.png")

    # 2. Curvas de drawdown
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for regla, diarios in series.items():
        dd = serie_drawdown(curva_equity(diarios))
        if not dd.empty:
            ax.plot(dd.index, dd.values * 100, label=regla, color=COLORES.get(regla), linewidth=1.4)
    ax.axvspan(pd.Timestamp(COVID_INICIO), pd.Timestamp(COVID_FIN), alpha=0.12,
               color="red", label="COVID 2020")
    ax.set_title("Caída desde máximos (drawdown) por regla")
    ax.set_ylabel("%"); ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(destino / "riesgo_drawdown.png", dpi=120); plt.close(fig)
    generadas.append("riesgo_drawdown.png")

    # 3. Distribución por operación, con la cola marcada
    fig, ax = plt.subplots(figsize=(11, 5.0))
    for regla in (AGUANTAR, COMPUESTA):
        r = np.array([c.retorno_neto for c in cierres if c.regla == regla]) * 100
        if len(r) == 0:
            continue
        ax.hist(r, bins=120, range=(-60, 80), alpha=0.55, label=regla, color=COLORES.get(regla))
        p5 = float(np.percentile(r, 5))
        ax.axvline(p5, color=COLORES.get(regla), linestyle="--", linewidth=1.4)
        ax.text(p5, ax.get_ylim()[1] * 0.9, f" P5 {p5:.1f}%", color=COLORES.get(regla), fontsize=9)
    ax.set_title("Distribución del retorno por operación · cola del 5% marcada")
    ax.set_xlabel("%"); ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(destino / "riesgo_distribucion.png", dpi=120); plt.close(fig)
    generadas.append("riesgo_distribucion.png")

    return generadas


def _drawdown_covid(precios, cierres) -> dict:
    """Cuánto recortó cada regla la caída durante el episodio COVID."""
    salida = {}
    for regla in REGLAS:
        propios = [c for c in cierres if c.regla == regla]
        if not propios:
            continue
        diarios = retornos_diarios_cartera(propios, precios)
        if diarios.empty:
            continue
        ventana = diarios[(diarios.index >= COVID_INICIO) & (diarios.index <= COVID_FIN)]
        if ventana.empty:
            continue
        dd = serie_drawdown(curva_equity(ventana))
        salida[regla] = {
            "sesiones": int(len(ventana)),
            "maxDD_%": round(float(dd.min() * 100), 2),
            "retorno_episodio_%": round(float((curva_equity(ventana).iloc[-1] - 1) * 100), 2),
        }
    return salida


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=int, default=120)
    parser.add_argument("--anios", type=int, default=10)
    parser.add_argument("--salida", type=str, default="")
    args = parser.parse_args()

    from modulos.screener_avanzado import FALLBACK_UNIVERSE

    tickers = sorted({t for l in FALLBACK_UNIVERSE.values() for t in l})[: args.tickers]
    if "SPY" not in tickers:
        tickers.append("SPY")
    print(f"Eje de riesgo · {len(tickers)} valores · {args.anios} años", flush=True)

    precios, cierres = _preparar(tickers, args.anios)
    if not cierres:
        print("Sin cierres: nada que medir.")
        return 1

    metricas = comparar_riesgo(cierres, precios)
    print("\n=== MÉTRICAS DE RIESGO (cartera equiponderada) ===")
    print(pd.DataFrame([m.como_fila() for m in metricas.values()]).set_index("regla").to_string())

    referencia = metricas.get(AGUANTAR)
    print("\n=== VEREDICTO SEGÚN EL CRITERIO PRE-REGISTRADO ===")
    print(f"  A: {CRITERIO['A']}")
    print(f"  B: {CRITERIO['B']}")
    veredictos = {}
    for regla in (COMPUESTA, STOP_FIJO, TECNICA):
        m = metricas.get(regla)
        if m is None or referencia is None:
            continue
        v = veredicto_seguro(m, referencia)
        veredictos[regla] = v
        canje = v["canje_maxdd_por_punto"]
        print(f"  {regla:<10} A={'sí' if v['criterio_A'] else 'no'}  "
              f"B={'sí' if v['criterio_B'] else 'no'}  "
              f"canje={canje if canje is not None else 'n/a'} pts maxDD/pt CAGR  "
              f"-> {'MERECE LA PENA' if v['merece_la_pena'] else 'SEGURO CARO'}")

    # Sensibilidad a la construcción.
    metricas_fijo = comparar_riesgo(cierres, precios, peso_fijo=PESO_FIJO_SENSIBILIDAD)
    print(f"\n=== SENSIBILIDAD · peso fijo {PESO_FIJO_SENSIBILIDAD:.0%} por operación ===")
    print(pd.DataFrame([m.como_fila() for m in metricas_fijo.values()]).set_index("regla")[
        ["CAGR_%", "maxDD_%", "Calmar", "Sortino", "CVaR5_%"]].to_string())

    # Sin 2020.
    sin_2020 = [c for c in cierres if pd.Timestamp(c.fecha_entrada).year != 2020]
    metricas_sin = comparar_riesgo(sin_2020, precios)
    print("\n=== SIN 2020 ===")
    print(pd.DataFrame([m.como_fila() for m in metricas_sin.values()]).set_index("regla")[
        ["CAGR_%", "maxDD_%", "Calmar", "Sortino", "CVaR5_%"]].to_string())

    covid = _drawdown_covid(precios, cierres)
    print("\n=== EPISODIO COVID (19-feb a 30-abr 2020) ===")
    for regla, d in covid.items():
        print(f"  {regla:<10} maxDD {d['maxDD_%']:>7.2f}%   retorno del episodio {d['retorno_episodio_%']:>7.2f}%")

    # Por régimen.
    print("\n=== POR RÉGIMEN ===")
    por_regimen = {}
    for etiqueta in ("alcista", "bajista"):
        sub = [c for c in cierres if c.motivo.endswith(f"|{etiqueta}")]
        if len(sub) < 200:
            continue
        m = comparar_riesgo(sub, precios)
        por_regimen[etiqueta] = {k: v.como_fila() for k, v in m.items()}
        print(f"  -- {etiqueta} --")
        print(pd.DataFrame([x.como_fila() for x in m.values()]).set_index("regla")[
            ["CAGR_%", "maxDD_%", "Calmar", "CVaR5_%"]].to_string())

    graficas = _graficas(precios, cierres, ROOT / "docs" / "img")
    print(f"\nGráficas: {', '.join(graficas)}")

    if args.salida:
        Path(args.salida).write_text(json.dumps({
            "metricas": {k: v.como_fila() for k, v in metricas.items()},
            "metricas_peso_fijo": {k: v.como_fila() for k, v in metricas_fijo.items()},
            "metricas_sin_2020": {k: v.como_fila() for k, v in metricas_sin.items()},
            "veredictos": veredictos, "covid": covid, "por_regimen": por_regimen,
            "ic_cvar5": {k: v.ic_cvar5 for k, v in metricas.items()},
        }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"JSON -> {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
