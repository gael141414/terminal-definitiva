"""Decisión de venta o reducción sobre una posición YA ABIERTA.

Todo el terminal está orientado a decidir si comprar. Esto responde a la
pregunta contraria, que es la que de verdad cuesta: teniendo ya la acción, con
un precio y una fecha de entrada concretos, ¿se mantiene, se recorta o se vende?

Tres pilares —valoración, deterioro fundamental y técnico— se combinan en un
``sell_score`` de 0 a 100 donde MÁS ES MÁS RAZÓN PARA VENDER. Ninguna señal
decide sola: solo los *overrides* duros (stop roto, tesis rota) mandan por sí
mismos, porque son sucesos binarios y no cuestión de grado.

Qué evidencia hay, y qué evidencia NO hay
------------------------------------------
``modulos/swing_salidas.py`` documenta una validación sobre 2.377 operaciones en
la que **ninguna gestión activa de salida batió a aguantar hasta el horizonte**:
0,39R aguantar, 0,39R salir por señal bajista, 0,28R con stop dinámico. Aquello
medía el pilar técnico en horizonte swing, no valoración ni fundamentales, así
que no invalida este módulo — pero es el prior con el que hay que leer cualquier
resultado, y la interfaz debe decirlo. Ver ``tests/test_decision_venta.py`` y el
informe de ``scripts/backtest_decision_venta.py``.

Separación de entrada/salida y cálculo
--------------------------------------
``evaluar_posicion`` es una función pura: recibe los datos ya reunidos y no toca
la red. ``decidir_venta`` es la que sale a buscarlos. Los tests atacan la
primera, así que se ejecutan sin conexión.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from modulos.config import (
    DIAS_RECOMPRA_ES, FACTOR_REGIMEN_ADVERSO, FACTOR_REGIMEN_FAVORABLE,
    FRACCION_REDUCCION, MARGEN_SOBREVALORACION_VENTA, PERCENTIL_MULTIPLOS_CARO,
    PERFIL_LARGO_PLAZO, PERFIL_SWING, PESOS_VENTA, SEMANAS_REGLA_OCHO,
    STOP_DURO_PCT, SUBIDA_REGLA_OCHO_PCT, UMBRAL_ALTMAN_DP_TESIS_ROTA,
    UMBRAL_ALTMAN_TESIS_ROTA, UMBRAL_BENEISH_TESIS_ROTA,
    UMBRAL_PIOTROSKI_TESIS_ROTA, UMBRAL_REDUCIR, UMBRAL_VENDER,
)
from modulos.forense_scores import altman_z_score, beneish_m_score, piotroski_f_score
from modulos.multiplos_historicos import evaluar_multiplos
from modulos.swing_riesgo import MAX_PESO_POSICION_PCT

LOGGER = logging.getLogger("valuequant.decision_venta")

__all__ = [
    "MANTENER", "REDUCIR", "VENDER",
    "COL_SMA50", "COL_SMA200", "COL_RSI",
    "Posicion", "DatosPosicion", "SubScore", "DecisionVenta",
    "evaluar_posicion", "decidir_venta",
    "ADVERTENCIA_EVIDENCIA",
]

# Nombres de columna de modulos.indicadores.enriquecer_ohlcv. Se declaran aquí
# para que un cambio de nomenclatura allí rompa un test en vez de dejar el pilar
# técnico sin evaluar sin que nadie se entere.
COL_SMA50 = "sma50"
COL_SMA200 = "sma200"
COL_RSI = "rsi14"

MANTENER = "MANTENER"
REDUCIR = "REDUCIR"
VENDER = "VENDER"

ADVERTENCIA_EVIDENCIA = (
    "Sobre 2.377 operaciones históricas, ninguna gestión activa de salida batió a "
    "aguantar hasta el horizonte (swing_salidas.RESULTADO_VALIDACION). Aquella prueba "
    "cubría solo el pilar técnico a 30 sesiones. Trata esta decisión como un panel de "
    "diagnóstico, no como una orden."
)


# ==========================================================================
# ENTRADA Y SALIDA
# ==========================================================================


@dataclass(slots=True)
class Posicion:
    """La posición abierta sobre la que se decide."""

    ticker: str
    entrada: float | None = None
    fecha_entrada: date | None = None
    peso_cartera: float | None = None      # % del capital

    def plusvalia_pct(self, precio_actual: float | None) -> float | None:
        if not self.entrada or precio_actual is None or self.entrada <= 0:
            return None
        return (precio_actual - self.entrada) / self.entrada * 100

    def dias_abierta(self, hoy: date | None = None) -> int | None:
        if self.fecha_entrada is None:
            return None
        return ((hoy or date.today()) - self.fecha_entrada).days


@dataclass(slots=True)
class DatosPosicion:
    """Todo lo que hace falta para decidir, ya reunido.

    Se pasa explícitamente para que ``evaluar_posicion`` sea pura y los tests no
    necesiten red. Cualquier campo puede venir a None: el pilar afectado se
    marca como no evaluable en vez de inventar un valor.
    """

    precio_actual: float | None = None
    precios: pd.Series | None = None            # cierres diarios
    ohlcv: pd.DataFrame | None = None           # ya enriquecido por indicadores
    resultados: Any = None
    balance: Any = None
    flujos: Any = None
    fair_value: float | None = None
    margen_seguridad: float | None = None       # (FV - precio) / precio
    per_actual: float | None = None
    pfcf_actual: float | None = None
    red_flags: list[str] = field(default_factory=list)
    capitalizacion: float | None = None
    regimen_favorable: bool | None = None
    regimen_etiqueta: str = "desconocido"
    posiciones_abiertas: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SubScore:
    """Puntuación de un pilar: 0 = ninguna razón para vender, 100 = todas."""

    nombre: str
    puntuacion: float | None
    triggers: list[str] = field(default_factory=list)
    senales_evaluadas: int = 0

    @property
    def evaluable(self) -> bool:
        return self.puntuacion is not None


@dataclass(slots=True)
class DecisionVenta:
    """Veredicto completo sobre la posición."""

    ticker: str
    accion: str = MANTENER
    reducir_pct: float = 0.0
    precio_objetivo_trim: float | None = None
    precio_objetivo_venta: float | None = None
    fair_value: float | None = None
    precio_actual: float | None = None
    sell_score: float | None = None
    sub_scores: dict[str, float | None] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)
    explicacion: str = ""
    flags: dict[str, bool] = field(default_factory=dict)
    perfil: str = PERFIL_LARGO_PLAZO
    advertencia: str = ADVERTENCIA_EVIDENCIA
    avisos: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializable a JSON para analysis_store y las alertas."""
        datos = asdict(self)
        datos["sub_scores"] = {k: v for k, v in self.sub_scores.items()}
        return datos


# ==========================================================================
# UTILIDADES
# ==========================================================================


def _escalar(valor: float, malo: float, bueno: float) -> float:
    """Lleva un valor a 0-100 donde 100 es ``malo`` (razón para vender).

    Interpola linealmente y satura en los extremos.
    """
    if malo == bueno:
        return 0.0
    bruto = (valor - bueno) / (malo - bueno) * 100
    return float(min(100.0, max(0.0, bruto)))


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


# ==========================================================================
# PILAR A · VALORACIÓN
# ==========================================================================


def evaluar_valoracion(datos: DatosPosicion) -> SubScore:
    """Cuánto se ha alejado el precio del valor. Más caro, más razón de venta."""
    señales: list[float] = []
    triggers: list[str] = []

    if datos.margen_seguridad is not None:
        # +30% de margen = barata (0). −30% = un 30% por encima del valor (100).
        punto = _escalar(datos.margen_seguridad, malo=-0.30, bueno=0.30)
        señales.append(punto)
        if datos.margen_seguridad < -MARGEN_SOBREVALORACION_VENTA:
            triggers.append(
                f"Cotiza un {abs(datos.margen_seguridad) * 100:.0f}% por encima del valor razonable."
            )

    multiplos = evaluar_multiplos(
        datos.precios, datos.resultados, datos.balance, datos.flujos,
        per_actual=datos.per_actual, pfcf_actual=datos.pfcf_actual,
    )
    percentil = multiplos.percentil_medio
    if percentil is not None:
        señales.append(percentil)
        if percentil >= PERCENTIL_MULTIPLOS_CARO:
            triggers.append(
                f"Múltiplos en el percentil {percentil:.0f} de su propia historia: "
                "rara vez ha estado tan cara."
            )

    return SubScore("valoracion", _media(señales), triggers, len(señales))


# ==========================================================================
# PILAR B · FUNDAMENTALES
# ==========================================================================


def evaluar_fundamentales(datos: DatosPosicion) -> SubScore:
    """Deterioro del negocio. Reutiliza las tres métricas forenses."""
    señales: list[float] = []
    triggers: list[str] = []

    piotroski = piotroski_f_score(datos.balance, datos.resultados, datos.flujos)
    if piotroski.evaluable and piotroski.evaluados:
        # Se normaliza por los criterios EVALUADOS, no por 9: un 4 sobre 4 no es
        # un 4 sobre 9.
        proporcion = piotroski.valor / piotroski.evaluados
        señales.append((1 - proporcion) * 100)
        if piotroski.valor <= UMBRAL_PIOTROSKI_TESIS_ROTA:
            triggers.append(
                f"F-Score de Piotroski {piotroski.valor}/{piotroski.evaluados}: "
                "fundamentales débiles."
            )

    altman = altman_z_score(datos.balance, datos.resultados, capitalizacion=datos.capitalizacion)
    if not altman.evaluable:
        altman = altman_z_score(datos.balance, datos.resultados, modelo="doble_prima")
    if altman.evaluable:
        umbral = (UMBRAL_ALTMAN_DP_TESIS_ROTA if altman.modelo == "doble_prima"
                  else UMBRAL_ALTMAN_TESIS_ROTA)
        señales.append(_escalar(altman.valor, malo=umbral, bueno=umbral * 2.5))
        if altman.en_peligro:
            triggers.append(
                f"Altman Z ({altman.modelo}) {altman.valor:.2f}, por debajo de {umbral}: "
                "zona de riesgo de quiebra."
            )

    beneish = beneish_m_score(datos.balance, datos.resultados, datos.flujos)
    if beneish.evaluable:
        señales.append(_escalar(beneish.valor, malo=UMBRAL_BENEISH_TESIS_ROTA, bueno=-3.5))
        if beneish.sospechoso(UMBRAL_BENEISH_TESIS_ROTA):
            triggers.append(
                f"Beneish M {beneish.valor:.2f} por encima de {UMBRAL_BENEISH_TESIS_ROTA}: "
                "patrón compatible con maquillaje contable."
            )

    if datos.red_flags:
        señales.append(min(100.0, len(datos.red_flags) * 25.0))
        triggers.append(f"{len(datos.red_flags)} banderas rojas en el score.")

    return SubScore("fundamentales", _media(señales), triggers, len(señales))


# ==========================================================================
# PILAR C · TÉCNICO
# ==========================================================================


def evaluar_tecnico(datos: DatosPosicion, posicion: Posicion) -> SubScore:
    """Estado del precio, condicionado al régimen de mercado."""
    señales: list[float] = []
    triggers: list[str] = []

    df = datos.ohlcv
    if df is not None and not df.empty and datos.precio_actual:
        cierre = datos.precio_actual
        # Los nombres son los que produce modulos.indicadores.enriquecer_ohlcv:
        # sma50 / sma200 / rsi14, sin guion bajo. Un nombre inventado aquí no
        # daría error, simplemente dejaría el pilar sin evaluar en silencio.
        for columna, etiqueta, castigo in ((COL_SMA50, "media de 50", 55.0),
                                           (COL_SMA200, "media de 200", 80.0)):
            if columna in df.columns and not pd.isna(df[columna].iloc[-1]):
                media = float(df[columna].iloc[-1])
                if cierre < media:
                    señales.append(castigo)
                    triggers.append(f"Precio por debajo de su {etiqueta}.")
                else:
                    señales.append(15.0)

        if COL_RSI in df.columns and not pd.isna(df[COL_RSI].iloc[-1]):
            rsi = float(df[COL_RSI].iloc[-1])
            # Sobrecompra no es razón de venta por sí sola, pero suma.
            señales.append(_escalar(rsi, malo=85.0, bueno=45.0))
            if rsi >= 80:
                triggers.append(f"RSI {rsi:.0f}: sobrecompra extrema.")

        # Sobreextensión sobre la media de 50 en desviaciones típicas.
        if COL_SMA50 in df.columns and len(df) > 60:
            distancia = (df["Close"] - df[COL_SMA50]) / df[COL_SMA50]
            desviacion = float(distancia.tail(250).std())
            if desviacion and not pd.isna(desviacion):
                z = float(distancia.iloc[-1]) / desviacion
                señales.append(_escalar(z, malo=3.0, bueno=0.0))
                if z >= 2.5:
                    triggers.append(f"Precio a {z:.1f} desviaciones sobre su media de 50.")

    if not señales:
        return SubScore("tecnico", None, triggers, 0)

    puntuacion = _media(señales) or 0.0

    # El régimen endurece o relaja: la misma señal bajista pesa más cuando el
    # mercado ya está en distribución.
    if datos.regimen_favorable is False:
        puntuacion = min(100.0, puntuacion * FACTOR_REGIMEN_ADVERSO)
        triggers.append(f"Régimen de mercado adverso ({datos.regimen_etiqueta}): señales endurecidas.")
    elif datos.regimen_favorable is True:
        puntuacion = puntuacion * FACTOR_REGIMEN_FAVORABLE
        triggers.append(f"Régimen favorable ({datos.regimen_etiqueta}): señales relajadas.")

    return SubScore("tecnico", round(puntuacion, 1), triggers, len(señales))


# ==========================================================================
# OVERRIDES DUROS
# ==========================================================================


def _overrides(datos: DatosPosicion, posicion: Posicion) -> tuple[list[str], dict[str, bool]]:
    """Sucesos binarios que mandan por sí solos. No son cuestión de grado."""
    triggers: list[str] = []
    flags = {"override_stop": False, "tesis_rota": False}

    plusvalia = posicion.plusvalia_pct(datos.precio_actual)
    if plusvalia is not None and plusvalia <= -STOP_DURO_PCT:
        flags["override_stop"] = True
        triggers.append(
            f"Stop duro: {plusvalia:.1f}% desde la entrada, por debajo de −{STOP_DURO_PCT}%."
        )

    altman = altman_z_score(datos.balance, datos.resultados, capitalizacion=datos.capitalizacion)
    if not altman.evaluable:
        altman = altman_z_score(datos.balance, datos.resultados, modelo="doble_prima")
    if altman.evaluable and altman.en_peligro:
        flags["tesis_rota"] = True
        triggers.append(f"Tesis rota: Altman Z {altman.valor:.2f} en zona de quiebra.")

    beneish = beneish_m_score(datos.balance, datos.resultados, datos.flujos)
    if beneish.evaluable and beneish.sospechoso(UMBRAL_BENEISH_TESIS_ROTA):
        flags["tesis_rota"] = True
        triggers.append(f"Tesis rota: Beneish M {beneish.valor:.2f} indica posible manipulación.")

    piotroski = piotroski_f_score(datos.balance, datos.resultados, datos.flujos)
    if (piotroski.evaluable and piotroski.evaluados >= 7
            and piotroski.valor <= UMBRAL_PIOTROSKI_TESIS_ROTA):
        flags["tesis_rota"] = True
        triggers.append(f"Tesis rota: F-Score {piotroski.valor}/{piotroski.evaluados}.")

    return triggers, flags


# ==========================================================================
# CUÁNTO REDUCIR
# ==========================================================================


def _cuanto_reducir(accion: str, posicion: Posicion, datos: DatosPosicion) -> tuple[float, list[str], bool]:
    """Porcentaje de la posición a soltar, y si manda la concentración."""
    if accion == VENDER:
        return 100.0, [], False
    if accion == MANTENER:
        return 0.0, [], False

    reducir = FRACCION_REDUCCION * 100
    avisos: list[str] = []
    por_concentracion = False

    peso = posicion.peso_cartera
    if peso is not None and peso > MAX_PESO_POSICION_PCT:
        # Recortar hasta el tope aunque los fundamentales aguanten: el exceso de
        # peso es un riesgo por sí mismo.
        exceso = (peso - MAX_PESO_POSICION_PCT) / peso * 100
        if exceso > reducir:
            reducir = exceso
            por_concentracion = True
            avisos.append(
                f"El peso ({peso:.1f}%) supera el tope de {MAX_PESO_POSICION_PCT}%: "
                f"se recorta {exceso:.0f}% para volver al límite."
            )

    return round(reducir, 1), avisos, por_concentracion


def _regla_ocho_semanas(posicion: Posicion, datos: DatosPosicion) -> str | None:
    """O'Neil: una subida fuerte y rápida merece dejarla correr."""
    plusvalia = posicion.plusvalia_pct(datos.precio_actual)
    dias = posicion.dias_abierta()
    if plusvalia is None or dias is None:
        return None
    if plusvalia >= SUBIDA_REGLA_OCHO_PCT and dias <= SEMANAS_REGLA_OCHO * 7:
        return (
            f"Regla de las 8 semanas: +{plusvalia:.0f}% en {dias} días. "
            "Una subida así de rápida suele merecer dejarla correr."
        )
    return None


# ==========================================================================
# ORQUESTACIÓN
# ==========================================================================


def evaluar_posicion(
    datos: DatosPosicion,
    posicion: Posicion,
    perfil: str = PERFIL_LARGO_PLAZO,
) -> DecisionVenta:
    """Decide sobre una posición abierta. Función pura: no toca la red."""
    if perfil not in PESOS_VENTA:
        perfil = PERFIL_LARGO_PLAZO

    decision = DecisionVenta(
        ticker=posicion.ticker,
        perfil=perfil,
        precio_actual=datos.precio_actual,
        fair_value=datos.fair_value,
    )

    pilares = {
        "valoracion": evaluar_valoracion(datos),
        "fundamentales": evaluar_fundamentales(datos),
        "tecnico": evaluar_tecnico(datos, posicion),
    }
    decision.sub_scores = {n: p.puntuacion for n, p in pilares.items()}
    for pilar in pilares.values():
        decision.triggers.extend(pilar.triggers)

    # El sell score se reparte solo entre los pilares evaluables, renormalizando
    # los pesos: si no hay fundamentales, el peso no se regala a cero, se
    # redistribuye. Puntuar un pilar sin datos como 0 sería afirmar que ahí no
    # hay ninguna razón para vender, y eso no se sabe.
    pesos = PESOS_VENTA[perfil]
    vivos = {n: p for n, p in pilares.items() if p.evaluable}
    if vivos:
        peso_total = sum(pesos[n] for n in vivos)
        decision.sell_score = round(
            sum(pesos[n] * p.puntuacion for n, p in vivos.items()) / peso_total, 1
        )
        if len(vivos) < len(pilares):
            ausentes = sorted(set(pilares) - set(vivos))
            decision.avisos.append(
                f"Sin datos para {', '.join(ausentes)}: el score se reparte entre los "
                "pilares restantes, no se rellena con ceros."
            )
    else:
        decision.avisos.append("Ningún pilar evaluable: no hay decisión que dar.")

    triggers_duros, flags = _overrides(datos, posicion)
    decision.triggers.extend(triggers_duros)
    decision.flags = dict(flags)

    # Decisión.
    if flags["override_stop"] or flags["tesis_rota"]:
        decision.accion = VENDER
    elif decision.sell_score is None:
        decision.accion = MANTENER
        decision.avisos.append("Se mantiene por falta de datos, no por convicción.")
    elif decision.sell_score >= UMBRAL_VENDER:
        decision.accion = VENDER
    elif decision.sell_score >= UMBRAL_REDUCIR:
        decision.accion = REDUCIR
    else:
        decision.accion = MANTENER

    # La regla de las 8 semanas frena un recorte, nunca un override duro.
    freno = _regla_ocho_semanas(posicion, datos)
    if freno and decision.accion == REDUCIR and not any(flags.values()):
        decision.accion = MANTENER
        decision.avisos.append(freno)

    reducir, avisos_reduccion, por_concentracion = _cuanto_reducir(decision.accion, posicion, datos)
    decision.reducir_pct = reducir
    decision.avisos.extend(avisos_reduccion)
    decision.flags["concentracion"] = por_concentracion
    decision.flags["fiscal_es"] = decision.accion in (REDUCIR, VENDER)

    if datos.fair_value:
        decision.precio_objetivo_trim = round(datos.fair_value, 2)
        decision.precio_objetivo_venta = round(
            datos.fair_value * (1 + MARGEN_SOBREVALORACION_VENTA), 2
        )

    decision.explicacion = _explicar(decision, pilares, posicion, datos)
    return decision


def _explicar(decision: DecisionVenta, pilares: dict[str, SubScore],
              posicion: Posicion, datos: DatosPosicion) -> str:
    """Texto legible. Dice también lo que NO se ha podido mirar."""
    partes: list[str] = []
    plusvalia = posicion.plusvalia_pct(datos.precio_actual)

    if decision.accion == VENDER:
        cabeza = "Vender la posición completa"
    elif decision.accion == REDUCIR:
        cabeza = f"Reducir un {decision.reducir_pct:.0f}% de la posición"
    else:
        cabeza = "Mantener la posición"
    if plusvalia is not None:
        cabeza += f" (actualmente {plusvalia:+.1f}% desde la entrada)"
    partes.append(cabeza + ".")

    if decision.sell_score is not None:
        detalle = ", ".join(
            f"{n} {p.puntuacion:.0f}" for n, p in pilares.items() if p.evaluable
        )
        partes.append(f"Sell score {decision.sell_score:.0f}/100 ({detalle}).")

    if decision.flags.get("override_stop"):
        partes.append("Manda el stop duro: por debajo de ese nivel la entrada ya no se sostiene.")
    elif decision.flags.get("tesis_rota"):
        partes.append("Manda la tesis rota: el negocio ya no es el que se compró.")

    if decision.triggers:
        partes.append("Motivos: " + " ".join(f"· {t}" for t in decision.triggers[:6]))
    if decision.avisos:
        partes.append(" ".join(decision.avisos))
    if decision.flags.get("fiscal_es"):
        partes.append(
            f"Fiscalidad (informativo): la plusvalía tributa en la base del ahorro y "
            f"recomprar en {DIAS_RECOMPRA_ES} días impide compensar la pérdida."
        )
    return " ".join(partes)


def decidir_venta(
    ticker: str,
    entrada: float | None = None,
    fecha_entrada: date | None = None,
    peso_cartera: float | None = None,
    perfil: str = PERFIL_LARGO_PLAZO,
    *,
    datos: DatosPosicion | None = None,
) -> DecisionVenta:
    """Punto de entrada con adquisición de datos.

    Si se pasa ``datos`` ya reunidos, no toca la red — es la vía que usan los
    tests y el backtest.
    """
    posicion = Posicion(ticker=ticker.strip().upper(), entrada=entrada,
                        fecha_entrada=fecha_entrada, peso_cartera=peso_cartera)
    if datos is None:
        datos = reunir_datos(posicion.ticker)
    return evaluar_posicion(datos, posicion, perfil)


def reunir_datos(ticker: str) -> DatosPosicion:
    """Descarga lo necesario. Cada fallo degrada un pilar, nunca rompe."""
    from modulos.indicadores import enriquecer_ohlcv, limpiar_velas_incompletas

    datos = DatosPosicion()

    try:
        import yfinance as yf

        from modulos.yahoo_resilience import safe_yfinance_fetch

        historico, estado = safe_yfinance_fetch(
            lambda: yf.Ticker(ticker).history(period="10y", interval="1d", auto_adjust=False),
            empty_value=pd.DataFrame(),
            context=f"decision_venta:{ticker}",
        )
        if historico is not None and not historico.empty:
            historico = limpiar_velas_incompletas(historico)
            datos.ohlcv = enriquecer_ohlcv(historico)
            datos.precios = historico["Close"].dropna()
            if not datos.precios.empty:
                datos.precio_actual = float(datos.precios.iloc[-1])
        elif estado:
            LOGGER.warning("Histórico no disponible para %s (%s)", ticker, estado)
    except Exception as exc:
        LOGGER.warning("Sin histórico para %s: %s", ticker, exc)

    try:
        from modulos.yfinance_fundamentals import obtener_fundamentales_yfinance

        # Devuelve la 4-tupla (is_df, bs_df, cf_df, key_metrics) para respetar
        # la firma de extraer_datos_fundamentales_fmp; el cuarto es siempre None.
        resultados, balance, flujos, _metricas = obtener_fundamentales_yfinance(ticker)
        datos.resultados, datos.balance, datos.flujos = resultados, balance, flujos
    except Exception as exc:
        LOGGER.warning("Sin fundamentales para %s: %s", ticker, exc)

    try:
        from modulos.swing_regimen import clasificar_regimen

        regimen = clasificar_regimen()
        datos.regimen_favorable = regimen.favorable_a_largos
        datos.regimen_etiqueta = regimen.etiqueta
    except Exception as exc:
        LOGGER.warning("Sin régimen de mercado: %s", exc)

    return datos
