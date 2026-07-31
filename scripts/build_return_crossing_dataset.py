#!/usr/bin/env python3
"""Construye el dataset de cruce score-vs-retorno (Sub-fase 4, calibración del score).

Redescubre el universo FMP accesible, congela un score point-in-time por
cada año fiscal disponible de cada ticker (Sub-fase 3), lo cruza con el
retorno real a 6 meses y 1 año, añade los 3 casos de supervivencia (solo
fundamentales, sin retorno -- ver modulos/survivorship_universe.py), agrega
en deciles + Spearman, y persiste el resultado completo en data/.

Ejemplos:
    python scripts/build_return_crossing_dataset.py
    python scripts/build_return_crossing_dataset.py --limite-anios 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.return_crossing import (  # noqa: E402
    CANDIDATOS_UNIVERSO_FMP,
    construir_dataset_fmp,
    construir_dataset_supervivencia,
    guardar_resultado,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limite-anios", type=int, default=5,
        help="Años fiscales a intentar por ticker FMP (tope 5, como en la Sub-fase 3). Default: 5",
    )
    parser.add_argument(
        "--pausa-segundos", type=float, default=4.0,
        help="Pausa entre tickers candidatos, para no agotar el límite de ráfaga de FMP. Default: 4.0",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Probando {len(CANDIDATOS_UNIVERSO_FMP)} candidatos contra el motor 'as reported' de FMP...")
    resultados_fmp, accesibles = construir_dataset_fmp(
        list(CANDIDATOS_UNIVERSO_FMP), limite_anios=args.limite_anios, verbose=True, pausa_segundos=args.pausa_segundos
    )
    print(f"Accesibles hoy: {len(accesibles)}/{len(CANDIDATOS_UNIVERSO_FMP)} -> {sorted(accesibles)}")
    print(f"Puntos de congelación con score calculado (FMP): {len(resultados_fmp)}")

    print("Casos de supervivencia (BBBY/SHLD/TOYS)...")
    resultados_supervivencia = construir_dataset_supervivencia(años=args.limite_anios)
    print(f"Puntos de congelación con score calculado (supervivencia): {len(resultados_supervivencia)}")

    resultados = resultados_fmp + resultados_supervivencia
    resumen = guardar_resultado(resultados, universo_probado=list(CANDIDATOS_UNIVERSO_FMP), universo_accesible=accesibles)

    print()
    print("=== Resumen ===")
    print(f"Filas totales: {resumen['tamaño_muestra_total_filas']}")
    print(f"Con retorno 6m: {resumen['tamaño_muestra_con_retorno_6m']} | Spearman 6m: {resumen['spearman_6m']}")
    print(f"Con retorno 1y: {resumen['tamaño_muestra_con_retorno_1y']} | Spearman 1y: {resumen['spearman_1y']}")


if __name__ == "__main__":
    main()
