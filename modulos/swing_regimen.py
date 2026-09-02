"""Régimen de mercado: decide qué estrategias tienen sentido HOY.

La idea central
---------------
La razón más común por la que una estrategia de swing "deja de funcionar" no es
que la estrategia sea mala, sino que se está aplicando en el régimen equivocado:
una ruptura alcista falla sistemáticamente en un mercado lateral, y una compra
por sobreventa falla sistemáticamente en un mercado en caída libre. Son la misma
regla dando resultados opuestos según el contexto.

Por eso el escáner no muestra señales sueltas: primero clasifica el régimen y
después marca cada señal como operable o fuera de contexto. El usuario sigue
viéndolas todas -- ocultarlas sería paternalista y le impediría discrepar -- pero
sabe cuáles rema a favor de corriente.

Los cuatro sensores
-------------------
1. Tendencia del índice: SPY sobre/bajo su media de 200 sesiones.
2. Amplitud (breadth): qué porcentaje del universo está sobre SU media de 200.
   Es el sensor que detecta la divergencia peligrosa -- el índice en máximos
   sostenido por cuatro valores mientras el resto ya ha girado.
3. Volatilidad: nivel del VIX.
4. Direccionalidad: ADX del índice, que separa tendencia de rango.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from modulos.indicadores import adx, enriquecer_ohlcv, limpiar_velas_incompletas, sma
from modulos.yahoo_resilience import safe_yfinance_download

# Identificadores de régimen. Se usan como claves en las estrategias, así que
# son constantes y no texto suelto.
TENDENCIA_ALCISTA = "tendencia_alcista"
RANGO_ALCISTA = "rango_alcista"
DISTRIBUCION = "distribucion"
CORRECCION = "correccion"
PANICO = "panico"
DESCONOCIDO = "desconocido"

ETIQUETAS_REGIMEN = {
    TENDENCIA_ALCISTA: "Tendencia alcista",
    RANGO_ALCISTA: "Rango alcista",
    DISTRIBUCION: "Distribución",
    CORRECCION: "Corrección",
    PANICO: "Pánico",
    DESCONOCIDO: "Indeterminado",
}

DESCRIPCIONES_REGIMEN = {
    TENDENCIA_ALCISTA: (
        "Índice sobre su media de 200 con amplitud sana y direccionalidad. "
        "Es el contexto natural de las rupturas y el momentum."
    ),
    RANGO_ALCISTA: (
        "Índice sostenido pero sin dirección clara. Las rupturas tienden a fallar "
        "por agotamiento; la reversión a la media es lo que funciona."
    ),
    DISTRIBUCION: (
        "El índice aguanta pero la amplitud se deteriora: la subida la sostienen "
        "cada vez menos valores. Conviene reducir tamaño y exigir más calidad."
    ),
    CORRECCION: (
        "Índice bajo su media de 200. Los largos pierden viento de cola y los "
        "cortos sobre empresas deterioradas pasan a tener contexto favorable."
    ),
    PANICO: (
        "Volatilidad extrema. Históricamente es donde mejor funciona comprar "
        "sobreventa, pero también donde más rápido salta un stop: media posición."
    ),
}

UMBRAL_VIX_PANICO = 30.0
UMBRAL_VIX_TENSION = 22.0
UMBRAL_ADX_TENDENCIA = 20.0
UMBRAL_AMPLITUD_SANA = 50.0
UMBRAL_AMPLITUD_DEBIL = 35.0


@dataclass
class Regimen:
    """Foto del contexto de mercado en la que se evalúan las señales."""

    codigo: str = DESCONOCIDO
    indice_sobre_media: bool | None = None
    distancia_media_pct: float | None = None
    adx_indice: float | None = None
    vix: float | None = None
    amplitud_pct: float | None = None
    avisos: list[str] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS_REGIMEN.get(self.codigo, "Indeterminado")

    @property
    def descripcion(self) -> str:
        return DESCRIPCIONES_REGIMEN.get(self.codigo, "No hay datos suficientes del índice.")

    @property
    def favorable_a_largos(self) -> bool:
        return self.codigo in {TENDENCIA_ALCISTA, RANGO_ALCISTA}

    @property
    def favorable_a_cortos(self) -> bool:
        return self.codigo in {CORRECCION, DISTRIBUCION}

    @property
    def factor_tamano(self) -> float:
        """Multiplicador sugerido sobre el tamaño normal de la posición.

        No es una recomendación financiera: es la traducción mecánica de "en un
        contexto peor, arriesga menos por operación" a un número que el
        calculador de posición pueda usar.
        """
        return {
            TENDENCIA_ALCISTA: 1.0,
            RANGO_ALCISTA: 0.75,
            DISTRIBUCION: 0.5,
            CORRECCION: 0.5,
            PANICO: 0.4,
        }.get(self.codigo, 0.5)


def _serie_cierre(datos: pd.DataFrame, ticker: str) -> pd.Series | None:
    """Extrae el cierre de un símbolo tolerando las dos formas de yf.download."""
    if datos is None or datos.empty:
        return None
    try:
        if isinstance(datos.columns, pd.MultiIndex):
            if ticker in datos.columns.get_level_values(0):
                sub = datos[ticker]
            else:
                return None
        else:
            sub = datos
        cierre = sub["Close"].dropna()
        return cierre if not cierre.empty else None
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def _descargar_contexto() -> dict[str, Any]:
    """Descarga índice y volatilidad. Cacheado: cambia una vez por sesión."""
    datos = safe_yfinance_download(
        yf,
        tickers=["SPY", "^VIX"],
        period="2y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
        context="swing_regimen",
    )

    spy = _serie_cierre(datos, "SPY")
    vix = _serie_cierre(datos, "^VIX")

    # El ADX necesita OHLC completo, no sólo el cierre.
    ohlc_spy = None
    try:
        if isinstance(datos.columns, pd.MultiIndex) and "SPY" in datos.columns.get_level_values(0):
            ohlc_spy = limpiar_velas_incompletas(datos["SPY"])
    except Exception:
        ohlc_spy = None

    return {
        "spy": spy,
        "vix": vix,
        "adx_spy": float(adx(ohlc_spy).iloc[-1]) if ohlc_spy is not None and len(ohlc_spy) > 30 else None,
    }


def calcular_amplitud(precios_por_ticker: dict[str, pd.DataFrame]) -> float | None:
    """Porcentaje del universo cotizando sobre su media de 200 sesiones.

    Se calcula con los mismos datos que ya descargó el escáner, así que no
    cuesta ni una petición adicional. Es el sensor que distingue una subida
    sana de una sostenida por un puñado de valores.
    """
    if not precios_por_ticker:
        return None

    total = 0
    encima = 0
    for df in precios_por_ticker.values():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        cierre = df["Close"].dropna()
        if len(cierre) < 200:
            continue
        media = sma(cierre, 200).iloc[-1]
        if pd.isna(media):
            continue
        total += 1
        if float(cierre.iloc[-1]) > float(media):
            encima += 1

    if total < 20:  # muestra insuficiente para ser representativa
        return None
    return round(encima / total * 100.0, 1)


def clasificar_regimen(amplitud_pct: float | None = None) -> Regimen:
    """Clasifica el contexto actual de mercado.

    ``amplitud_pct`` se pasa desde el escáner cuando ya ha descargado el
    universo; si no se pasa, el régimen se decide sin ese sensor y se deja
    constancia en ``avisos`` en vez de fingir un dato que no se tiene.
    """
    contexto = _descargar_contexto()
    spy = contexto.get("spy")
    vix_serie = contexto.get("vix")
    adx_indice = contexto.get("adx_spy")

    regimen = Regimen(amplitud_pct=amplitud_pct, adx_indice=adx_indice)

    if spy is None or len(spy) < 200:
        regimen.avisos.append("Sin histórico suficiente del índice: régimen indeterminado.")
        return regimen

    media200 = sma(spy, 200).iloc[-1]
    ultimo = float(spy.iloc[-1])
    regimen.indice_sobre_media = bool(ultimo > float(media200))
    regimen.distancia_media_pct = round((ultimo / float(media200) - 1.0) * 100.0, 2)

    if vix_serie is not None and not vix_serie.empty:
        regimen.vix = round(float(vix_serie.iloc[-1]), 2)
    else:
        regimen.avisos.append("VIX no disponible: la detección de pánico queda desactivada.")

    if amplitud_pct is None:
        regimen.avisos.append("Amplitud no calculada todavía (se obtiene al lanzar el escáner).")

    # --- Clasificación, de la condición más excluyente a la más general ---
    if regimen.vix is not None and regimen.vix >= UMBRAL_VIX_PANICO:
        regimen.codigo = PANICO
        return regimen

    if not regimen.indice_sobre_media:
        regimen.codigo = CORRECCION
        return regimen

    # Índice sostenido: lo que decide es la amplitud y la direccionalidad.
    if amplitud_pct is not None and amplitud_pct < UMBRAL_AMPLITUD_DEBIL:
        regimen.codigo = DISTRIBUCION
        regimen.avisos.append(
            f"Sólo el {amplitud_pct:.0f}% del universo está sobre su media de 200: "
            "la subida del índice la sostienen pocos valores."
        )
        return regimen

    if regimen.vix is not None and regimen.vix >= UMBRAL_VIX_TENSION:
        regimen.codigo = DISTRIBUCION
        return regimen

    tendencia = adx_indice is not None and adx_indice >= UMBRAL_ADX_TENDENCIA
    amplitud_ok = amplitud_pct is None or amplitud_pct >= UMBRAL_AMPLITUD_SANA

    regimen.codigo = TENDENCIA_ALCISTA if (tendencia and amplitud_ok) else RANGO_ALCISTA
    return regimen


# =============================================================================
# Mecánica de O'Neil: días de distribución y día de confirmación
# =============================================================================
#
# El criterio "M" de CAN SLIM no es "el índice está sobre su media": O'Neil lo
# medía con dos señales concretas que detectan la actividad institucional
# directamente en el precio y el volumen del índice.
#
# - Día de distribución: el índice cae con MÁS volumen que la víspera. Significa
#   que quien vende es grande, porque mover el índice a la baja con volumen
#   creciente no lo hace el minorista. Acumular varios en pocas semanas avisa de
#   que el dinero institucional está saliendo.
# - Día de confirmación (follow-through): tras un intento de rebote desde un
#   mínimo, una sesión de subida fuerte con volumen creciente. Es la señal que
#   O'Neil exigía para volver a comprar; sin ella, un rebote es sólo un rebote.

CAIDA_MIN_DISTRIBUCION = 0.2       # % de caída que cuenta como distribución
VENTANA_DISTRIBUCION = 25          # sesiones que un día de distribución sigue contando
DISTRIBUCION_PRESION = 4           # a partir de aquí, mercado "bajo presión"
DISTRIBUCION_CORRECCION = 6        # a partir de aquí, suele venir corrección
SUBIDA_MIN_CONFIRMACION = 1.2      # % mínimo del día de confirmación
CADUCIDAD_DISTRIBUCION_PCT = 5.0   # si el índice sube esto desde el día, deja de contar


def contar_dias_distribucion(ohlc: pd.DataFrame, ventana: int = VENTANA_DISTRIBUCION) -> dict[str, Any]:
    """Cuenta los días de distribución vigentes en el índice.

    Un día deja de contar por dos vías, ambas de O'Neil: cuando han pasado 25
    sesiones, o cuando el índice ha subido un 5% desde su cierre (la debilidad
    que señalaba quedó superada por los hechos).
    """
    vacio = {"dias": 0, "fechas": [], "estado": "sin_datos"}
    if ohlc is None or ohlc.empty or "Close" not in ohlc.columns or "Volume" not in ohlc.columns:
        return vacio

    datos = limpiar_velas_incompletas(ohlc)
    if len(datos) < ventana + 2:
        return vacio

    cierres = datos["Close"].to_numpy(dtype=float)
    volumenes = datos["Volume"].to_numpy(dtype=float)
    fechas = datos.index

    ultimo_cierre = float(cierres[-1])
    inicio = len(datos) - ventana
    encontrados: list[Any] = []

    for i in range(max(inicio, 1), len(datos)):
        if not (np.isfinite(cierres[i]) and np.isfinite(cierres[i - 1])):
            continue
        variacion = (cierres[i] / cierres[i - 1] - 1.0) * 100.0
        if variacion > -CAIDA_MIN_DISTRIBUCION:
            continue
        if not (np.isfinite(volumenes[i]) and np.isfinite(volumenes[i - 1])):
            continue
        if volumenes[i] <= volumenes[i - 1]:
            continue

        # Caducidad por recuperación del índice.
        if cierres[i] > 0 and (ultimo_cierre / cierres[i] - 1.0) * 100.0 >= CADUCIDAD_DISTRIBUCION_PCT:
            continue

        encontrados.append(fechas[i])

    total = len(encontrados)
    if total >= DISTRIBUCION_CORRECCION:
        estado = "corrección probable"
    elif total >= DISTRIBUCION_PRESION:
        estado = "bajo presión"
    else:
        estado = "sano"

    return {"dias": total, "fechas": encontrados, "estado": estado}


def detectar_dia_confirmacion(
    ohlc: pd.DataFrame,
    *,
    ventana_busqueda: int = 40,
    subida_minima: float = SUBIDA_MIN_CONFIRMACION,
) -> dict[str, Any]:
    """Busca el día de confirmación más reciente tras un mínimo del índice.

    El patrón que se persigue: el índice marca un mínimo, rebota, y entre el
    cuarto y el séptimo día de ese intento aparece una sesión de subida fuerte
    con volumen creciente. Ese es el permiso de compra de O'Neil.
    """
    vacio = {"encontrado": False, "fecha": None, "subida_pct": None, "sesiones_desde": None}
    if ohlc is None or ohlc.empty:
        return vacio

    datos = limpiar_velas_incompletas(ohlc)
    if len(datos) < ventana_busqueda + 10:
        return vacio

    cierres = datos["Close"].to_numpy(dtype=float)
    volumenes = datos["Volume"].to_numpy(dtype=float)
    fechas = datos.index
    n = len(datos)

    # Mínimo reciente desde el que pudo arrancar el intento de rebote.
    tramo = cierres[n - ventana_busqueda : n]
    if np.isnan(tramo).any():
        return vacio
    indice_minimo = int(np.argmin(tramo)) + (n - ventana_busqueda)

    # El día de confirmación llega a partir del cuarto día del intento.
    for i in range(max(indice_minimo + 3, 1), n):
        if not (np.isfinite(cierres[i]) and np.isfinite(cierres[i - 1])):
            continue
        subida = (cierres[i] / cierres[i - 1] - 1.0) * 100.0
        if subida < subida_minima:
            continue
        if not (np.isfinite(volumenes[i]) and np.isfinite(volumenes[i - 1])):
            continue
        if volumenes[i] <= volumenes[i - 1]:
            continue

        return {
            "encontrado": True,
            "fecha": fechas[i],
            "subida_pct": round(subida, 2),
            "sesiones_desde": n - 1 - i,
        }

    return vacio


@st.cache_data(ttl=1800, show_spinner=False)
def analizar_mercado_oneil() -> dict[str, Any]:
    """Lectura del mercado con los criterios de O'Neil sobre el S&P 500."""
    datos = safe_yfinance_download(
        yf, tickers="SPY", period="6mo", interval="1d", auto_adjust=True,
        progress=False, threads=True, context="canslim_mercado",
    )
    if datos is None or datos.empty:
        return {"disponible": False}

    if isinstance(datos.columns, pd.MultiIndex):
        datos.columns = datos.columns.droplevel(1)

    distribucion = contar_dias_distribucion(datos)
    confirmacion = detectar_dia_confirmacion(datos)

    return {
        "disponible": True,
        "distribucion": distribucion,
        "confirmacion": confirmacion,
        "permiso_compra": distribucion["estado"] == "sano",
    }
