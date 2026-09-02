"""Escáner de swing: descarga masiva, evaluación y ranking de oportunidades.

Cómo consigue escanear cientos de valores
-----------------------------------------
La clave es no hacer una petición por empresa. ``yf.download`` acepta listas de
símbolos y los resuelve en paralelo: medido sobre este proyecto, unos 70 ms por
ticker, es decir ~36 s para 500 valores. Todos los indicadores se calculan en
local a partir de ese OHLCV, así que el coste de red no crece con el número de
estrategias evaluadas.

El resultado se cachea 30 minutos: los datos son diarios, así que repetir la
descarga en cada rerun de Streamlit sólo serviría para que Yahoo nos limite.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.indicadores import enriquecer_ohlcv, limpiar_velas_incompletas
from modulos.swing_estrategias import ESTRATEGIAS_POR_ID, Senal, evaluar_todas
from modulos.swing_regimen import Regimen, calcular_amplitud, clasificar_regimen
from modulos.swing_riesgo import construir_plan
from modulos.yahoo_resilience import safe_yfinance_download

logger = logging.getLogger(__name__)

# Tamaño de lote. yfinance degrada con listas muy largas en una sola llamada, y
# trocear permite además informar del progreso al usuario.
TAMANO_LOTE = 100

# 2 años cubren con holgura la media de 200 sesiones y el máximo de 52 semanas.
PERIODO_DESCARGA = "2y"


@dataclass
class ResultadoEscaneo:
    """Salida completa de un escaneo, lista para pintar."""

    senales: list[Senal] = field(default_factory=list)
    regimen: Regimen | None = None
    universo_analizado: int = 0
    universo_solicitado: int = 0
    sin_datos: list[str] = field(default_factory=list)
    amplitud_pct: float | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def largos(self) -> list[Senal]:
        return [s for s in self.senales if s.es_largo]

    @property
    def cortos(self) -> list[Senal]:
        return [s for s in self.senales if not s.es_largo]


def _extraer_ohlcv(datos: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    """Aísla el OHLCV de un símbolo del DataFrame multi-índice de yfinance."""
    try:
        if isinstance(datos.columns, pd.MultiIndex):
            if ticker not in datos.columns.get_level_values(0):
                return None
            sub = datos[ticker]
        else:
            sub = datos
        sub = limpiar_velas_incompletas(sub)
        return sub if not sub.empty else None
    except Exception:
        return None


def _descargar_lote(lote: list[str], periodo: str, indice: int) -> pd.DataFrame | None:
    """Descarga un lote reintentando ante rate limit de Yahoo.

    Sin reintento, un único 429 hacía desaparecer el lote entero (hasta 100
    valores) sin más rastro que una línea de log: el escaneo terminaba
    "correctamente" habiendo mirado la mitad del universo, que es peor que
    fallar de forma visible. Se reintenta con backoff y se trocea el lote a la
    mitad, porque un lote más pequeño tiene bastante menos probabilidad de que
    lo rechacen.
    """
    for intento in range(3):
        datos = safe_yfinance_download(
            yf,
            tickers=lote,
            period=periodo,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=True,
            context=f"swing_scanner:lote_{indice}:intento_{intento}",
        )
        if datos is not None and not datos.empty:
            return datos

        if intento < 2:
            espera = 2.0 * (intento + 1)
            logger.warning(
                "Lote %s vacío (posible rate limit); reintentando en %.0fs.", indice, espera
            )
            time.sleep(espera)

    # Último recurso: partir el lote en dos mitades más pequeñas.
    if len(lote) > 10:
        mitad = len(lote) // 2
        logger.warning("Lote %s sigue fallando; se trocea en dos mitades.", indice)
        izquierda = _descargar_lote(lote[:mitad], periodo, indice)
        derecha = _descargar_lote(lote[mitad:], periodo, indice + mitad)
        partes = [d for d in (izquierda, derecha) if d is not None and not d.empty]
        if partes:
            return pd.concat(partes, axis=1)

    return None


@st.cache_data(ttl=1800, show_spinner=False)
def descargar_universo(tickers: tuple[str, ...], periodo: str = PERIODO_DESCARGA) -> dict[str, pd.DataFrame]:
    """Descarga OHLCV de todo el universo por lotes.

    Devuelve un dict ticker -> DataFrame ya limpio. Los símbolos sin datos
    (deslistados, tickers erróneos) simplemente no aparecen: no se inventa un
    DataFrame vacío que luego habría que filtrar en cada consumidor.
    """
    resultado: dict[str, pd.DataFrame] = {}
    lista = [t for t in dict.fromkeys(tickers) if t]

    for inicio in range(0, len(lista), TAMANO_LOTE):
        lote = lista[inicio : inicio + TAMANO_LOTE]
        datos = _descargar_lote(lote, periodo, inicio)
        if datos is None or datos.empty:
            continue

        for ticker in lote:
            ohlcv = _extraer_ohlcv(datos, ticker)
            if ohlcv is not None and len(ohlcv) >= 210:
                resultado[ticker] = ohlcv

    return resultado


# Tope de valores para los que se descarga el calendario de resultados. A
# diferencia del OHLCV, ese endpoint NO admite lotes: es una petición por
# empresa, así que escanear PEAD sobre 500 valores serían 500 llamadas.
MAX_TICKERS_PEAD = 80


def escanear(
    tickers: Iterable[str],
    *,
    estrategias: tuple[str, ...] | None = None,
    contexto_fundamental: dict[str, dict[str, Any]] | None = None,
    respetar_regimen: bool = True,
    progreso: Any = None,
) -> ResultadoEscaneo:
    """Escanea un universo y devuelve las señales ordenadas por fuerza.

    ``respetar_regimen`` no oculta señales: marca cada una según encaje o no con
    el contexto de mercado. Ocultarlas impediría al usuario discrepar del
    clasificador, que es una decisión que le corresponde a él.
    """
    lista = [str(t).strip().upper() for t in tickers if str(t).strip()]
    resultado = ResultadoEscaneo(universo_solicitado=len(lista))
    if not lista:
        return resultado

    if progreso is not None:
        progreso.progress(0.05, text=f"Descargando {len(lista)} valores...")

    precios = descargar_universo(tuple(lista))
    resultado.universo_analizado = len(precios)
    resultado.sin_datos = [t for t in lista if t not in precios]

    if progreso is not None:
        progreso.progress(0.45, text="Calculando amplitud de mercado y régimen...")

    # La amplitud sale gratis: son los mismos precios ya descargados.
    resultado.amplitud_pct = calcular_amplitud(precios)
    resultado.regimen = clasificar_regimen(resultado.amplitud_pct)

    contexto_fundamental = contexto_fundamental or {}
    total = max(len(precios), 1)
    señales: list[Senal] = []

    # El PEAD necesita el calendario de resultados, que no viene con el OHLCV.
    calendarios: dict[str, Any] = {}
    quiere_pead = estrategias is None or "pead" in estrategias
    if quiere_pead and len(precios) <= MAX_TICKERS_PEAD:
        from modulos.pead import obtener_historico_earnings

        if progreso is not None:
            progreso.progress(0.5, text="Descargando calendarios de resultados...")
        for ticker in precios:
            calendario = obtener_historico_earnings(ticker)
            if calendario is not None and not calendario.empty:
                calendarios[ticker] = calendario
    elif quiere_pead:
        resultado.avisos.append(
            f"La deriva post-resultados se ha omitido: requiere una petición por empresa y el "
            f"universo tiene {len(precios)} valores (máximo {MAX_TICKERS_PEAD}). "
            "Escanea tu watchlist o una lista más corta para incluirla."
        )

    for i, (ticker, ohlcv) in enumerate(precios.items()):
        if progreso is not None and i % 25 == 0:
            progreso.progress(0.55 + 0.4 * (i / total), text=f"Evaluando estrategias... ({i}/{total})")
        try:
            enriquecido = enriquecer_ohlcv(ohlcv)
            if enriquecido.empty:
                continue
            if ticker in calendarios:
                from modulos.pead import enriquecer_con_earnings

                enriquecido = enriquecer_con_earnings(enriquecido, calendarios[ticker])
            señales.extend(
                evaluar_todas(
                    enriquecido,
                    ticker,
                    contexto_fundamental=contexto_fundamental.get(ticker),
                    ids=estrategias,
                )
            )
        except Exception as exc:
            logger.debug("Fallo evaluando %s: %s", ticker, exc)
            continue

    # Marcado por régimen y plan de riesgo.
    codigo_regimen = resultado.regimen.codigo if resultado.regimen else None
    for señal in señales:
        estrategia = ESTRATEGIAS_POR_ID.get(señal.estrategia)
        en_regimen = bool(estrategia and codigo_regimen in estrategia.regimenes)
        señal.datos["en_regimen"] = en_regimen
        if respetar_regimen and not en_regimen:
            # Penaliza sin eliminar: la señal existe, pero rema contra corriente.
            señal.fuerza = round(señal.fuerza * 0.6, 1)
            señal.motivos.append(
                f"Fuera de su régimen habitual (mercado en «{resultado.regimen.etiqueta}»): "
                "esta estrategia rinde peor en este contexto"
            )

    señales.sort(key=lambda s: s.fuerza, reverse=True)
    resultado.senales = señales

    if progreso is not None:
        progreso.progress(1.0, text="Escaneo completado")

    return resultado


def señales_a_dataframe(
    resultado: ResultadoEscaneo,
    *,
    capital: float = 10_000.0,
    riesgo_pct: float = 1.0,
) -> pd.DataFrame:
    """Convierte las señales en tabla, añadiendo el plan de riesgo de cada una."""
    if not resultado.senales:
        return pd.DataFrame()

    factor = resultado.regimen.factor_tamano if resultado.regimen else 1.0
    filas: list[dict[str, Any]] = []

    for señal in resultado.senales:
        plan = construir_plan(
            señal.precio,
            señal.atr,
            direccion=señal.direccion,
            capital=capital,
            riesgo_por_operacion_pct=riesgo_pct,
            factor_regimen=factor,
        )
        filas.append(
            {
                "Ticker": señal.ticker,
                "Dirección": "Largo" if señal.es_largo else "Corto",
                "Estrategia": señal.nombre_estrategia,
                "Fuerza": round(señal.fuerza, 1),
                "En régimen": bool(señal.datos.get("en_regimen", False)),
                "Precio": round(señal.precio, 2),
                "Stop": plan.stop,
                "Objetivo 2R": plan.objetivos.get("2R"),
                "Riesgo/acción %": round(plan.distancia_stop_pct, 2),
                "Acciones": plan.acciones,
                "Riesgo €": plan.riesgo_euros,
                "ATR %": round(señal.atr / señal.precio * 100, 2) if señal.precio else None,
                "_motivos": señal.motivos,
                "_id_estrategia": señal.estrategia,
            }
        )

    return pd.DataFrame(filas)
