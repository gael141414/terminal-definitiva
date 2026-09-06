#!/usr/bin/env python3
"""¿Queda selección en la cartera tras descontar el riesgo asumido?

Ejecuta el pre-registro de docs/preregistro_alfa_beta.md, commiteado antes.

Uso:
    python scripts/analisis_alfa_beta.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.config import (
    COLOR_ACCENT, COLOR_NEGATIVE, COLOR_POSITIVE, COLOR_PRIMARY, COLOR_WARNING,
    TICKER_LIBRE_RIESGO,
)
from modulos.rendimiento_cartera import calcular_rendimiento
from modulos.rendimiento_riesgo import analizar, serie_libre_de_riesgo

CARTERA = [
    ("AAPL", 500.0, date(2024, 1, 27)),
    ("GOOG", 800.0, date(2025, 4, 3)),
    ("NVDA", 250.0, date(2026, 1, 15)),
]
PESOS = {"SP500": 0.40, "MSCI_WORLD": 0.60}


def _descargar_libre_riesgo(periodo: str = "5y") -> pd.Series | None:
    from modulos.rendimiento_cartera import _descargar_cierres

    return _descargar_cierres([TICKER_LIBRE_RIESGO], periodo).get(TICKER_LIBRE_RIESGO)


def _graficas(rendimiento, analisis, libre, destino: Path) -> list[str]:
    destino.mkdir(parents=True, exist_ok=True)
    generadas = []
    series = rendimiento.series

    # 1. Equity: cartera, índice y vol-matched.
    fig, ax = plt.subplots(figsize=(11, 5.4))
    ax.plot(series.index, series["unitizada_cartera"], label="Mi cartera",
            color=COLOR_PRIMARY, linewidth=2.2)
    ax.plot(series.index, series["unitizada_benchmark"], label="Índice (mismo dinero)",
            color=COLOR_ACCENT, linewidth=1.8)
    vm = analisis.vol_matched
    if vm is not None and not vm.retornos.empty:
        curva = 100 * (1 + vm.retornos).cumprod()
        ax.plot(curva.index, curva.values,
                label=f"Índice igualado en volatilidad (k={vm.k:.2f})",
                color=COLOR_WARNING, linewidth=1.8, linestyle="--")
    ax.set_title("Capital unitizado (base 100) — el efecto de las aportaciones ya está aislado")
    ax.set_ylabel("Base 100"); ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(destino / "alfa_equity.png", dpi=120); plt.close(fig)
    generadas.append("alfa_equity.png")

    # 2. Dispersión con la recta de regresión.
    r_p = series["unitizada_cartera"].pct_change().dropna()
    r_b = series["unitizada_benchmark"].pct_change().dropna()
    idx = r_p.index.intersection(r_b.index)
    r_f, _ = serie_libre_de_riesgo(idx, libre)
    x = (r_b.loc[idx] - r_f).to_numpy() * 100
    y = (r_p.loc[idx] - r_f).to_numpy() * 100

    fig, ax = plt.subplots(figsize=(7.5, 6.4))
    ax.scatter(x, y, s=9, alpha=0.35, color=COLOR_PRIMARY)
    if analisis.capm is not None:
        rejilla = np.linspace(x.min(), x.max(), 50)
        alfa_d = (1 + analisis.capm.alfa_anual_pct / 100) ** (1 / 252) - 1
        ax.plot(rejilla, analisis.capm.beta * rejilla + alfa_d * 100,
                color=COLOR_NEGATIVE, linewidth=2,
                label=f"β={analisis.capm.beta:.2f}  R²={analisis.capm.r2:.2f}")
        ax.legend()
    ax.axhline(0, color="grey", linewidth=0.8); ax.axvline(0, color="grey", linewidth=0.8)
    ax.set_xlabel("Exceso diario del índice (%)"); ax.set_ylabel("Exceso diario de la cartera (%)")
    ax.set_title("Regresión de excesos diarios"); ax.grid(alpha=0.25)
    fig.tight_layout(); fig.savefig(destino / "alfa_dispersion.png", dpi=120); plt.close(fig)
    generadas.append("alfa_dispersion.png")

    # 3. Descomposición del exceso.
    d = analisis.descomposicion
    if d is not None:
        fig, ax = plt.subplots(figsize=(8.5, 4.4))
        etiquetas = ["Exposición al\nmercado (beta)", "Selección\n(alfa)", "Residuo"]
        valores = [d.por_beta_pct, d.por_alfa_pct, d.residual_pct]
        colores = [COLOR_WARNING, COLOR_POSITIVE if d.por_alfa_pct > 0 else COLOR_NEGATIVE, "#93a4bb"]
        barras = ax.bar(etiquetas, valores, color=colores)
        ax.bar_label(barras, fmt="%+.1f pts")
        ax.axhline(0, color="grey", linewidth=1)
        ax.set_title(f"De {d.exceso_total_pct:+.1f} puntos anuales sobre el índice, ¿cuánto es qué?")
        ax.set_ylabel("puntos anuales"); ax.grid(alpha=0.2, axis="y")
        fig.tight_layout(); fig.savefig(destino / "alfa_descomposicion.png", dpi=120); plt.close(fig)
        generadas.append("alfa_descomposicion.png")

    return generadas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salida", type=str, default="")
    args = parser.parse_args()

    print("Calculando cartera completa…", flush=True)
    rendimiento = calcular_rendimiento(CARTERA, PESOS)
    if not rendimiento.valido:
        print("No se pudo valorar la cartera."); return 1

    mayor = max(rendimiento.atribucion, key=lambda a: abs(a.alfa_eur))
    print(f"Mayor posición por |alfa|: {mayor.ticker} ({mayor.alfa_eur:+,.2f} €)", flush=True)

    print(f"Recalculando sin {mayor.ticker}…", flush=True)
    sin_mayor = calcular_rendimiento(
        [t for t in CARTERA if t[0] != mayor.ticker], PESOS
    )

    print(f"Descargando {TICKER_LIBRE_RIESGO}…", flush=True)
    libre = _descargar_libre_riesgo()

    analisis = analizar(rendimiento, serie_libre=libre,
                        rendimiento_sin_mayor=sin_mayor if sin_mayor.valido else None)

    r = rendimiento.resumen
    print(f"\n=== BRUTO ===")
    print(f"  invertido {r['total_invertido_eur']:,.0f} € · cartera {r['valor_cartera_eur']:,.0f} € "
          f"· índice {r['valor_benchmark_eur']:,.0f} € · diferencia {r['diferencia_eur']:+,.0f} €")

    print("\n=== BENCHMARK IGUALADO EN VOLATILIDAD ===")
    if analisis.vol_matched:
        print(json.dumps(analisis.vol_matched.como_fila(), indent=2, ensure_ascii=False))

    print("\n=== CAPM ===")
    if analisis.capm:
        print(json.dumps(analisis.capm.como_fila(), indent=2, ensure_ascii=False))

    print("\n=== DESCOMPOSICIÓN DEL EXCESO ===")
    if analisis.descomposicion:
        print(json.dumps(analisis.descomposicion.como_fila(), indent=2, ensure_ascii=False))
        print(" ", analisis.descomposicion.como_texto())

    print("\n=== CONCENTRACIÓN ===")
    if analisis.concentracion:
        print(json.dumps(analisis.concentracion.como_fila(), indent=2, ensure_ascii=False))

    print(f"\n=== SIN {mayor.ticker} ===")
    if analisis.capm_sin_mayor:
        print("  CAPM:", json.dumps(analisis.capm_sin_mayor.como_fila(), ensure_ascii=False))
    if analisis.vol_sin_mayor:
        print("  vol-matched:", json.dumps(analisis.vol_sin_mayor.como_fila(), ensure_ascii=False))

    print("\n=== VEREDICTO (criterio pre-registrado) ===")
    v = analisis.veredicto
    print(f"  A · alfa significativo      : {'SÍ' if v.criterio_a else 'NO'}")
    print(f"  B · bate al vol-matched     : {'SÍ' if v.criterio_b else 'NO'}")
    print(f"  C · sobrevive sin la mayor  : {'SÍ' if v.criterio_c else 'NO'}")
    print(f"  --> {'HAY EVIDENCIA DE SELECCIÓN' if v.hay_evidencia else 'INSUFICIENTE EVIDENCIA'}")
    print(f"  {v.motivo}")

    if analisis.avisos:
        print("\nAvisos:")
        for a in analisis.avisos:
            print("  -", a)

    graficas = _graficas(rendimiento, analisis, libre, ROOT / "docs" / "img")
    print(f"\nGráficas: {', '.join(graficas)}")

    if args.salida:
        Path(args.salida).write_text(json.dumps({
            "bruto": r, "analisis": analisis.to_dict(),
            "mayor_posicion": mayor.ticker,
        }, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
