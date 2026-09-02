"""Escáner CAN SLIM: localiza candidatos aplicando los siete criterios.

Estrategia de ejecución
-----------------------
Escanear el mercado entero pidiendo fundamentales de cada empresa es inviable:
el endpoint de Yahoo que los publica no admite lotes, así que serían tantas
peticiones como valores. La solución es el orden de trabajo del propio O'Neil,
que también miraba primero el gráfico:

1. **Pasada técnica** sobre todo el universo, a partir del OHLCV que ya se
   descarga en lote. Aquí se resuelven L (fuerza relativa), N (ruptura de base)
   y el volumen. Coste de red: cero adicional.
2. **Pasada fundamental** sólo sobre los supervivientes. Aquí entran C, A e I.
   Coste: una petición por candidato, y los candidatos son pocos por diseño.

Sobre la escasez de resultados
------------------------------
Que el escáner no devuelva nada es el comportamiento normal, no un fallo. En el
periodo que estudió AAII, cerca de un tercio de los meses pasaban tres empresas
o menos el filtro, y en un 9% de los meses no pasaba ninguna. Un escáner CAN SLIM
que devuelve treinta candidatos todos los días es un escáner mal calibrado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd
import streamlit as st

from modulos.canslim import (
    ADVERTENCIA_EVIDENCIA,
    ResultadoCanSlim,
    calcular_rs_ratings,
    combinar,
    evaluar_fundamentales,
    evaluar_tecnicos,
    _datos_fundamentales,
)
from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_regimen import analizar_mercado_oneil, clasificar_regimen
from modulos.swing_scanner import descargar_universo

logger = logging.getLogger(__name__)

# Tope de candidatos a los que se piden fundamentales. Protege de que un filtro
# técnico demasiado laxo dispare cientos de peticiones sin que nadie lo note.
MAX_CANDIDATOS_FUNDAMENTALES = 60


@dataclass
class ResultadoScreenerCanSlim:
    candidatos: list[ResultadoCanSlim] = field(default_factory=list)
    universo_analizado: int = 0
    universo_solicitado: int = 0
    supervivientes_tecnicos: int = 0
    mercado: dict[str, Any] = field(default_factory=dict)
    regimen: Any = None
    avisos: list[str] = field(default_factory=list)

    @property
    def hay_permiso_mercado(self) -> bool:
        return bool(self.mercado.get("permiso_compra", False))


def _pasa_filtro_tecnico(criterios: dict[str, Any], rs_minimo: float, exigir_ruptura: bool, ruptura: Any) -> bool:
    """Criterio de supervivencia a la primera pasada."""
    liderazgo = criterios.get("L")
    if liderazgo is None or liderazgo.cumple is not True:
        return False

    if exigir_ruptura:
        return ruptura is not None and not ruptura.fallida

    nuevos_maximos = criterios.get("N")
    return nuevos_maximos is not None and nuevos_maximos.cumple is True


def escanear_canslim(
    tickers: Iterable[str],
    *,
    rs_minimo: float = 80.0,
    exigir_ruptura: bool = False,
    minimo_criterios: int = 5,
    progreso: Any = None,
) -> ResultadoScreenerCanSlim:
    """Ejecuta el escáner completo sobre un universo."""
    lista = [str(t).strip().upper() for t in tickers if str(t).strip()]
    resultado = ResultadoScreenerCanSlim(universo_solicitado=len(lista))
    if not lista:
        return resultado

    if progreso is not None:
        progreso.progress(0.05, text=f"Descargando {len(lista)} valores...")

    precios = descargar_universo(tuple(lista))
    resultado.universo_analizado = len(precios)
    if not precios:
        resultado.avisos.append("No se pudo descargar el histórico de ningún valor del universo.")
        return resultado

    # --- Contexto de mercado (criterio M) ---
    if progreso is not None:
        progreso.progress(0.3, text="Leyendo la dirección del mercado...")
    resultado.mercado = analizar_mercado_oneil()
    try:
        resultado.regimen = clasificar_regimen()
    except Exception:
        resultado.regimen = None

    mercado_alcista = resultado.mercado.get("permiso_compra") if resultado.mercado.get("disponible") else None

    # --- Pasada 1: técnica sobre todo el universo ---
    if progreso is not None:
        progreso.progress(0.4, text="Calculando fuerza relativa del universo...")
    ratings = calcular_rs_ratings(precios)
    if not ratings:
        resultado.avisos.append(
            "El universo es demasiado pequeño para calcular el RS Rating, que es un ranking "
            "relativo y necesita al menos 20 valores con un año de histórico. Amplía la muestra."
        )

    supervivientes: list[tuple[str, dict[str, Any], Any, Any, float | None]] = []
    total = max(len(precios), 1)

    for i, (ticker, ohlcv) in enumerate(precios.items()):
        if progreso is not None and i % 25 == 0:
            progreso.progress(0.4 + 0.35 * (i / total), text=f"Analizando gráficos... ({i}/{total})")
        try:
            enriquecido = enriquecer_ohlcv(ohlcv)
            if enriquecido.empty or len(enriquecido) < 260:
                continue
            rs = ratings.get(ticker)
            criterios, base, ruptura = evaluar_tecnicos(
                enriquecido, rs, mercado_alcista=mercado_alcista
            )
        except Exception as exc:
            logger.debug("CAN SLIM técnico falló en %s: %s", ticker, exc)
            continue

        if rs is not None and rs < rs_minimo:
            continue
        if not _pasa_filtro_tecnico(criterios, rs_minimo, exigir_ruptura, ruptura):
            continue

        supervivientes.append((ticker, criterios, base, ruptura, rs))

    resultado.supervivientes_tecnicos = len(supervivientes)

    if len(supervivientes) > MAX_CANDIDATOS_FUNDAMENTALES:
        # Se priorizan los de mayor fuerza relativa: es el criterio que O'Neil
        # consideraba decisivo para elegir entre varios candidatos válidos.
        supervivientes.sort(key=lambda x: (x[4] or 0), reverse=True)
        resultado.avisos.append(
            f"{len(supervivientes)} valores superaron el filtro técnico. Se piden fundamentales "
            f"sólo de los {MAX_CANDIDATOS_FUNDAMENTALES} de mayor fuerza relativa para no disparar "
            "el número de peticiones."
        )
        supervivientes = supervivientes[:MAX_CANDIDATOS_FUNDAMENTALES]

    # --- Pasada 2: fundamentales sobre los supervivientes ---
    candidatos: list[ResultadoCanSlim] = []
    for i, (ticker, criterios, base, ruptura, rs) in enumerate(supervivientes):
        if progreso is not None:
            progreso.progress(
                0.75 + 0.2 * (i / max(len(supervivientes), 1)),
                text=f"Comprobando fundamentales... ({i + 1}/{len(supervivientes)})",
            )
        try:
            fundamentales = evaluar_fundamentales(ticker)
        except Exception:
            fundamentales = {}

        completo = combinar(ticker, criterios, fundamentales, rs_rating=rs, base=base, ruptura=ruptura)
        if completo.cumplidos >= minimo_criterios:
            candidatos.append(completo)

    candidatos.sort(key=lambda c: (c.cumplidos, c.rs_rating or 0), reverse=True)
    resultado.candidatos = candidatos

    if not candidatos:
        resultado.avisos.append(
            "Ningún valor cumple los criterios exigidos hoy. Es el comportamiento esperado de este "
            "método: en el periodo estudiado por AAII, en cerca de un tercio de los meses pasaban "
            "tres empresas o menos, y en un 9% ninguna."
        )

    if progreso is not None:
        progreso.progress(1.0, text="Escaneo completado")

    return resultado


def candidatos_a_dataframe(resultado: ResultadoScreenerCanSlim) -> pd.DataFrame:
    """Tabla resumida de candidatos para vista rápida."""
    if not resultado.candidatos:
        return pd.DataFrame()

    filas = []
    for c in resultado.candidatos:
        datos = _datos_fundamentales(c.ticker)
        precio = c.ruptura.precio if c.ruptura is not None else None
        filas.append(
            {
                "Ticker": c.ticker,
                "Nombre": datos.get("nombre", c.ticker),
                "Sector": datos.get("sector", "n/d"),
                "CAN SLIM": c.letras_cumplidas,
                "Cumple": f"{c.cumplidos}/{c.evaluados}",
                "Puntuación": c.puntuacion,
                "RS": c.rs_rating,
                "Base": c.base.nombre if c.base is not None else "n/d",
                "Pivote": c.base.pivote if c.base is not None else None,
                "Precio": precio,
                "Estado ruptura": c.ruptura.estado if c.ruptura is not None else "sin ruptura reciente",
            }
        )
    return pd.DataFrame(filas)
