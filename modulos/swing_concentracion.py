"""Control de concentración antes de abrir una posición.

El riesgo que no se ve
----------------------
El módulo de riesgo dimensiona cada operación por separado y garantiza que
ninguna pierda más del 1% de la cuenta. Eso es correcto y también insuficiente:
cinco posiciones tecnológicas con un 1% de riesgo cada una no son cinco apuestas
del 1%, son una apuesta del 5% al mismo factor. El día que el sector corrige,
los cinco stops saltan juntos.

Este módulo mide esa exposición agregada por tres vías complementarias:

1. **Sector.** El agrupador más obvio y el que el usuario reconoce.
2. **Correlación.** El más honesto: dos valores de sectores distintos pueden
   moverse igual. Reutiliza ``detectar_correlaciones_altas`` de portfolio.py en
   vez de duplicar el cálculo.
3. **Calor de cartera.** La suma del riesgo abierto. Es la cifra que responde a
   "¿cuánto pierdo si hoy salta todo?", que no aparece en ninguna posición vista
   de forma aislada.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

import streamlit as st
import yfinance as yf

from modulos.yahoo_resilience import safe_yfinance_info

logger = logging.getLogger(__name__)

# A partir de esta cuota del sector en la cartera, la diversificación es aparente.
MAX_POSICIONES_POR_SECTOR = 3
MAX_PESO_SECTOR_PCT = 40.0

# Correlación por encima de la cual dos posiciones son, a efectos de riesgo, una.
UMBRAL_CORRELACION = 0.80

# Riesgo abierto total tolerable. Con un 6% arriesgado a la vez, una corrección
# generalizada se lleva por delante un semestre de trabajo.
MAX_CALOR_CARTERA_PCT = 6.0


@dataclass
class AvisoConcentracion:
    tipo: str
    mensaje: str
    gravedad: str = "aviso"  # "aviso" | "bloqueo"


@dataclass
class InformeConcentracion:
    avisos: list[AvisoConcentracion] = field(default_factory=list)
    calor_actual_pct: float = 0.0
    calor_con_nueva_pct: float = 0.0
    sectores: dict[str, int] = field(default_factory=dict)

    @property
    def hay_bloqueo(self) -> bool:
        return any(a.gravedad == "bloqueo" for a in self.avisos)

    @property
    def despejado(self) -> bool:
        return not self.avisos


@st.cache_data(ttl=86400, show_spinner=False)
def obtener_sector(ticker: str) -> str:
    """Sector de un valor. Cacheado un día: no cambia."""
    info = safe_yfinance_info(yf, ticker, context=f"concentracion:{ticker}")
    return str(info.get("sector") or "Desconocido")


def calor_cartera(posiciones: Iterable[dict[str, Any]], capital: float) -> float:
    """Porcentaje del capital en riesgo si saltan todos los stops a la vez.

    Sólo cuenta las posiciones con stop definido: sin stop no hay riesgo
    acotado que sumar, y meterlas con riesgo cero daría una falsa sensación de
    seguridad. Esas se avisan aparte.
    """
    if capital <= 0:
        return 0.0

    total = 0.0
    for posicion in posiciones:
        try:
            acciones = float(posicion.get("acciones") or 0)
            entrada = float(posicion.get("entrada") or 0)
            stop = float(posicion.get("stop") or 0)
        except (TypeError, ValueError):
            continue
        if acciones <= 0 or entrada <= 0 or stop <= 0:
            continue
        total += acciones * abs(entrada - stop)

    return round(total / capital * 100.0, 2)


def analizar_concentracion(
    candidato: str,
    posiciones_abiertas: dict[str, dict[str, Any]],
    *,
    capital: float,
    riesgo_nuevo_euros: float = 0.0,
    incluir_correlacion: bool = True,
) -> InformeConcentracion:
    """Evalúa si abrir ``candidato`` desequilibra la cartera.

    ``posiciones_abiertas`` es ``{ticker: {acciones, entrada, stop}}``.
    """
    informe = InformeConcentracion()
    candidato = str(candidato or "").strip().upper()
    tickers_abiertos = [t for t in posiciones_abiertas if t and t != candidato]

    # --- Calor de cartera ---
    informe.calor_actual_pct = calor_cartera(posiciones_abiertas.values(), capital)
    informe.calor_con_nueva_pct = round(
        informe.calor_actual_pct + (riesgo_nuevo_euros / capital * 100.0 if capital > 0 else 0.0), 2
    )

    if informe.calor_con_nueva_pct > MAX_CALOR_CARTERA_PCT:
        informe.avisos.append(
            AvisoConcentracion(
                "calor",
                f"Con esta posición tendrías un {informe.calor_con_nueva_pct:.1f}% del capital en "
                f"riesgo simultáneo (límite sugerido: {MAX_CALOR_CARTERA_PCT:.0f}%). Cada operación "
                "cumple su riesgo individual, pero sumadas exponen mucho más de lo que parece.",
                "bloqueo" if informe.calor_con_nueva_pct > MAX_CALOR_CARTERA_PCT * 1.5 else "aviso",
            )
        )

    sin_stop = [
        t for t, p in posiciones_abiertas.items()
        if not (isinstance(p, dict) and p.get("stop"))
    ]
    if sin_stop:
        informe.avisos.append(
            AvisoConcentracion(
                "sin_stop",
                f"{len(sin_stop)} posición(es) sin stop definido ({', '.join(sin_stop[:4])}): "
                "su riesgo no entra en el cálculo, así que la exposición real es mayor que la mostrada.",
            )
        )

    if not tickers_abiertos:
        return informe

    # --- Sector ---
    try:
        sectores = {t: obtener_sector(t) for t in tickers_abiertos}
        sector_candidato = obtener_sector(candidato) if candidato else "Desconocido"
    except Exception:
        return informe

    conteo: dict[str, int] = {}
    for sector in sectores.values():
        conteo[sector] = conteo.get(sector, 0) + 1
    informe.sectores = conteo

    mismos = conteo.get(sector_candidato, 0)
    if sector_candidato != "Desconocido" and mismos >= MAX_POSICIONES_POR_SECTOR:
        companeros = [t for t, s in sectores.items() if s == sector_candidato]
        informe.avisos.append(
            AvisoConcentracion(
                "sector",
                f"Ya tienes {mismos} posición(es) en «{sector_candidato}» "
                f"({', '.join(companeros[:5])}). Esta sería la {mismos + 1}ª: estarías "
                "concentrando en un solo factor, no diversificando.",
            )
        )

    # --- Correlación ---
    if incluir_correlacion and candidato:
        try:
            from modulos.portfolio import detectar_correlaciones_altas

            avisos_corr = detectar_correlaciones_altas(
                tickers_abiertos + [candidato], threshold=UMBRAL_CORRELACION
            )
            relevantes = [a for a in avisos_corr if candidato in a]
            for aviso in relevantes[:3]:
                informe.avisos.append(AvisoConcentracion("correlacion", aviso))
        except Exception as exc:
            logger.debug("Correlación no disponible: %s", exc)

    return informe
