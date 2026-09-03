#!/usr/bin/env python3
"""Backtest honesto de la regla de salida de modulos.decision_venta.

Qué se mide y qué NO
--------------------
Se miden el pilar TÉCNICO y el stop. Los pilares de valoración y fundamentales
NO se pueden reconstruir sin look-ahead: harían falta las cuentas tal y como se
conocían en cada fecha pasada, y el repositorio tiene 0 scores congelados
(``point_in_time_scoring``). Puntuarlos con las cuentas de hoy sobre precios de
hace cinco años sería exactamente el sesgo que este backtest existe para evitar.
Así que aquí se valida un tercio del motor, y el informe lo dice.

Las cuatro reglas que se comparan
--------------------------------
1. AGUANTAR      -- comprar y no tocar hasta el horizonte. Es el listón real.
2. REGLA         -- salir cuando el pilar técnico supera el umbral de venta.
3. ALEATORIA     -- salir en un día al azar, con la MISMA frecuencia de salidas
                    que la regla. Sin este control, cualquier regla que salga a
                    menudo parece buena en un mercado alcista.
4. STOP FIJO     -- salir solo si el precio cae el stop duro desde la entrada.

Entradas sintéticas: se compra cada valor el primer día hábil de cada mes. No
pretende ser una estrategia; sirve para que las cuatro reglas se midan sobre
exactamente los mismos puntos de partida.

Uso:
    python scripts/backtest_decision_venta.py [--tickers N] [--anios N]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modulos.config import STOP_DURO_PCT, UMBRAL_VENDER
from modulos.decision_venta import COL_RSI, COL_SMA50, COL_SMA200
from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_scanner import descargar_universo

HORIZONTE = 252          # un año hábil
COSTE_POR_LADO = 0.001   # 0,1% por operación, ida y vuelta
SEMILLA = 20260903


@dataclass
class Resultado:
    nombre: str
    retornos: list[float] = field(default_factory=list)
    dias: list[int] = field(default_factory=list)
    salidas_anticipadas: int = 0

    def metricas(self) -> dict[str, float]:
        if not self.retornos:
            return {}
        r = np.array(self.retornos)
        dias = np.array(self.dias)
        aciertos = float((r > 0).mean() * 100)
        ganadores, perdedores = r[r > 0], r[r <= 0]

        # CAGR medio por operación, anualizado por su duración real.
        anios = np.maximum(dias / 252.0, 1 / 252.0)
        cagr = float((np.power(1 + r, 1 / anios) - 1).mean() * 100)

        # Sharpe y Sortino sobre la distribución de retornos por operación.
        desv = float(r.std(ddof=1)) if len(r) > 1 else 0.0
        bajista = r[r < 0]
        desv_bajista = float(bajista.std(ddof=1)) if len(bajista) > 1 else 0.0

        # Peor caída: la operación más negativa.
        return {
            "operaciones": int(len(r)),
            "retorno_medio_pct": round(float(r.mean() * 100), 2),
            "cagr_pct": round(cagr, 2),
            "acierto_pct": round(aciertos, 1),
            "peor_operacion_pct": round(float(r.min() * 100), 2),
            "sharpe": round(float(r.mean() / desv), 3) if desv else 0.0,
            "sortino": round(float(r.mean() / desv_bajista), 3) if desv_bajista else 0.0,
            "expectativa_pct": round(float(r.mean() * 100), 2),
            "ganancia_media_pct": round(float(ganadores.mean() * 100), 2) if len(ganadores) else 0.0,
            "perdida_media_pct": round(float(perdedores.mean() * 100), 2) if len(perdedores) else 0.0,
            "dias_medios": round(float(dias.mean()), 1),
            "salidas_anticipadas": self.salidas_anticipadas,
            "rotacion_anual": round(float(252 / dias.mean()), 2) if dias.mean() else 0.0,
        }


def _puntuacion_tecnica(df: pd.DataFrame, i: int) -> float | None:
    """Réplica del pilar técnico de decision_venta sobre un índice concreto.

    Se recalcula aquí en vez de llamar a evaluar_tecnico para no construir un
    DatosPosicion por cada una de las decenas de miles de sesiones evaluadas.
    Las reglas son las mismas.
    """
    cierre = float(df["Close"].iloc[i])
    señales: list[float] = []

    for columna, castigo in ((COL_SMA50, 55.0), (COL_SMA200, 80.0)):
        valor = df[columna].iloc[i]
        if not pd.isna(valor):
            señales.append(castigo if cierre < float(valor) else 15.0)

    rsi = df[COL_RSI].iloc[i]
    if not pd.isna(rsi):
        señales.append(min(100.0, max(0.0, (float(rsi) - 45.0) / 40.0 * 100)))

    if not señales:
        return None
    return sum(señales) / len(señales)


def _simular(df: pd.DataFrame, entradas: list[int], aleatoria_dias: dict[int, int]) -> dict[str, Resultado]:
    """Aplica las cuatro reglas sobre las MISMAS entradas."""
    salidas = {n: Resultado(n) for n in ("aguantar", "regla", "aleatoria", "stop_fijo")}
    cierres = df["Close"].to_numpy(dtype=float)

    for i in entradas:
        fin = min(i + HORIZONTE, len(df) - 1)
        if fin <= i:
            continue
        entrada = cierres[i]
        if not np.isfinite(entrada) or entrada <= 0:
            continue

        def cerrar(nombre: str, j: int, anticipada: bool) -> None:
            bruto = (cierres[j] - entrada) / entrada
            neto = bruto - 2 * COSTE_POR_LADO
            salidas[nombre].retornos.append(float(neto))
            salidas[nombre].dias.append(int(j - i))
            if anticipada:
                salidas[nombre].salidas_anticipadas += 1

        cerrar("aguantar", fin, False)

        # Regla: primera sesión en la que el pilar técnico supera el umbral.
        j_regla = fin
        for j in range(i + 1, fin + 1):
            punto = _puntuacion_tecnica(df, j)
            if punto is not None and punto >= UMBRAL_VENDER:
                j_regla = j
                break
        cerrar("regla", j_regla, j_regla < fin)

        # Stop fijo.
        j_stop = fin
        for j in range(i + 1, fin + 1):
            if (cierres[j] - entrada) / entrada * 100 <= -STOP_DURO_PCT:
                j_stop = j
                break
        cerrar("stop_fijo", j_stop, j_stop < fin)

        # Aleatoria: misma duración que la regla, pero en un punto al azar.
        duracion = aleatoria_dias.get(i)
        j_azar = min(i + duracion, fin) if duracion else fin
        cerrar("aleatoria", j_azar, j_azar < fin)

    return salidas


def ejecutar(tickers: list[str], anios: int) -> dict[str, dict]:
    random.seed(SEMILLA)
    precios = descargar_universo(tuple(tickers), periodo=f"{anios}y")
    print(f"  universo con datos: {len(precios)}/{len(tickers)}", flush=True)

    acumulado = {n: Resultado(n) for n in ("aguantar", "regla", "aleatoria", "stop_fijo")}

    for ticker, df in precios.items():
        if df is None or len(df) < HORIZONTE + 250:
            continue
        try:
            enriquecido = enriquecer_ohlcv(df)
        except Exception:
            continue

        # Entradas: primer día hábil de cada mes, tras el calentamiento.
        indice = enriquecido.index
        entradas = []
        mes_anterior = None
        for pos in range(250, len(enriquecido) - HORIZONTE):
            clave = (indice[pos].year, indice[pos].month)
            if clave != mes_anterior:
                entradas.append(pos)
                mes_anterior = clave
        if not entradas:
            continue

        aleatoria = {i: random.randint(1, HORIZONTE) for i in entradas}
        parcial = _simular(enriquecido, entradas, aleatoria)
        for nombre, resultado in parcial.items():
            acumulado[nombre].retornos.extend(resultado.retornos)
            acumulado[nombre].dias.extend(resultado.dias)
            acumulado[nombre].salidas_anticipadas += resultado.salidas_anticipadas

    return {n: r.metricas() for n, r in acumulado.items()}


def informe(metricas: dict[str, dict]) -> str:
    lineas = ["", "=" * 78, "BACKTEST DE LA REGLA DE SALIDA", "=" * 78, ""]
    lineas.append("MEDIDO (coste 0,1% por lado incluido):")
    lineas.append("")
    cabecera = f"{'regla':<14}{'ops':>7}{'ret.medio':>11}{'acierto':>9}{'sharpe':>8}{'sortino':>9}{'peor':>9}{'días':>7}{'rot./año':>10}"
    lineas.append(cabecera)
    lineas.append("-" * len(cabecera))
    for nombre in ("aguantar", "stop_fijo", "regla", "aleatoria"):
        m = metricas.get(nombre) or {}
        if not m:
            continue
        lineas.append(
            f"{nombre:<14}{m['operaciones']:>7}{m['retorno_medio_pct']:>10.2f}%"
            f"{m['acierto_pct']:>8.1f}%{m['sharpe']:>8.3f}{m['sortino']:>9.3f}"
            f"{m['peor_operacion_pct']:>8.1f}%{m['dias_medios']:>7.0f}{m['rotacion_anual']:>10.2f}"
        )

    aguantar = metricas.get("aguantar", {}).get("retorno_medio_pct")
    regla = metricas.get("regla", {}).get("retorno_medio_pct")
    azar = metricas.get("aleatoria", {}).get("retorno_medio_pct")
    stop = metricas.get("stop_fijo", {}).get("retorno_medio_pct")

    lineas += ["", "INTERPRETACIÓN:", ""]
    if regla is None or aguantar is None:
        lineas.append("  Sin datos suficientes para concluir nada.")
        return "\n".join(lineas)

    if regla > aguantar:
        lineas.append(f"  La regla bate a aguantar por {regla - aguantar:+.2f} puntos.")
    else:
        lineas.append(
            f"  La regla NO bate a aguantar: {regla - aguantar:+.2f} puntos. "
            "Salir empeora el resultado."
        )
    if azar is not None:
        if regla > azar:
            lineas.append(f"  Bate a la venta aleatoria por {regla - azar:+.2f} puntos.")
        else:
            lineas.append(
                f"  NO bate a la venta aleatoria ({regla - azar:+.2f}). Es decir: la "
                "regla no aporta información, solo reduce el tiempo en mercado."
            )
    if stop is not None:
        mejor = "mejor" if regla > stop else "peor"
        lineas.append(f"  Frente a solo-stop-fijo es {mejor} ({regla - stop:+.2f}).")

    lineas += [
        "",
        "LÍMITES DE ESTA PRUEBA:",
        "  · Mide el pilar TÉCNICO y el stop. Valoración y fundamentales no se",
        "    pueden reconstruir sin look-ahead (0 scores congelados disponibles),",
        "    así que quedan SIN VALIDAR.",
        "  · Entradas sintéticas mensuales: no es una estrategia, es un banco de",
        "    pruebas para que las cuatro reglas partan de los mismos puntos.",
        "  · Universo actual: hay sesgo de supervivencia. Las empresas que",
        "    quebraron no están, y son justo donde una regla de venta ayudaría.",
        "",
    ]
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", type=int, default=60)
    parser.add_argument("--anios", type=int, default=10)
    parser.add_argument("--salida", type=str, default="")
    args = parser.parse_args()

    from modulos.swing_ui import _universo_mercado

    tickers = _universo_mercado(args.tickers)
    print(f"Backtest sobre {len(tickers)} valores, {args.anios} años...", flush=True)

    metricas = ejecutar(tickers, args.anios)
    texto = informe(metricas)
    print(texto)

    if args.salida:
        Path(args.salida).write_text(
            json.dumps({"metricas": metricas, "informe": texto}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
