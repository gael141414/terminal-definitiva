"""Gestión de riesgo: del "esto pinta bien" a "compra N acciones, stop en X".

Por qué este módulo es el más importante del bloque de swing
------------------------------------------------------------
Una señal sin tamaño de posición no es operable. Dos traders con la misma señal
y el mismo acierto terminan con resultados opuestos si uno arriesga el 1% por
operación y el otro el 15%: el segundo se arruina con una racha perdedora
perfectamente normal, incluso teniendo razón a largo plazo.

La regla implementada es la estándar de riesgo fijo por operación: se decide
cuánto se está dispuesto a perder *antes* de entrar, y de ahí sale el número de
acciones. Nunca al revés.

Todo es matemática pura y determinista: ni red, ni Streamlit, ni estado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Direccion = Literal["largo", "corto"]

# El stop por defecto se sitúa a 2 ATR. Más cerca y el ruido normal del valor lo
# barre antes de que la tesis tenga tiempo de desarrollarse; más lejos y el
# tamaño de posición se vuelve tan pequeño que la operación no compensa.
MULTIPLO_ATR_STOP = 2.0

# Ninguna posición debe superar este porcentaje del capital aunque el cálculo de
# riesgo lo permita: un valor muy poco volátil daría un stop tan estrecho que el
# número de acciones se dispararía, concentrando la cartera sin darse cuenta.
MAX_PESO_POSICION_PCT = 20.0

# Por debajo de este ratio la operación no compensa: hay que acertar demasiadas
# veces para compensar las pérdidas.
RATIO_MINIMO_ACEPTABLE = 1.5


@dataclass
class PlanOperacion:
    """Plan completo y ejecutable de una operación."""

    direccion: Direccion
    entrada: float
    stop: float
    objetivos: dict[str, float]
    acciones: int
    capital_comprometido: float
    riesgo_euros: float
    riesgo_pct_real: float
    peso_cartera_pct: float
    ratio_riesgo_beneficio: float | None
    avisos: list[str]

    @property
    def operable(self) -> bool:
        """Si el plan tiene sentido ejecutarlo tal cual."""
        return self.acciones > 0 and not any(a.startswith("BLOQUEO") for a in self.avisos)

    @property
    def distancia_stop_pct(self) -> float:
        if not self.entrada:
            return 0.0
        return abs(self.entrada - self.stop) / self.entrada * 100.0


def calcular_stop(
    entrada: float,
    atr: float,
    direccion: Direccion = "largo",
    multiplo: float = MULTIPLO_ATR_STOP,
) -> float:
    """Stop situado a N veces el ATR del precio de entrada.

    Se usa el ATR y no un porcentaje fijo porque el mismo -8% significa cosas
    distintas en una utility y en una biotech: en la primera es una ruptura
    grave de la tesis, en la segunda es un martes cualquiera. El ATR adapta la
    distancia a la volatilidad propia de cada valor.
    """
    if entrada <= 0 or atr <= 0:
        return 0.0
    desplazamiento = multiplo * atr
    return round(entrada - desplazamiento if direccion == "largo" else entrada + desplazamiento, 4)


def calcular_objetivos(
    entrada: float,
    stop: float,
    direccion: Direccion = "largo",
    multiplos: tuple[float, ...] = (1.0, 2.0, 3.0),
) -> dict[str, float]:
    """Objetivos expresados en múltiplos de R (R = riesgo asumido por acción).

    Razonar en R en lugar de en euros es lo que permite comparar operaciones de
    tamaños distintos y saber si el sistema gana dinero: un sistema con 40% de
    aciertos es rentable si sus ganancias son de 3R y sus pérdidas de 1R.
    """
    riesgo_accion = abs(entrada - stop)
    if riesgo_accion <= 0:
        return {}

    objetivos: dict[str, float] = {}
    for m in multiplos:
        precio = entrada + m * riesgo_accion if direccion == "largo" else entrada - m * riesgo_accion
        objetivos[f"{m:g}R"] = round(precio, 4)
    return objetivos


def dimensionar_posicion(
    capital: float,
    riesgo_por_operacion_pct: float,
    entrada: float,
    stop: float,
    *,
    factor_regimen: float = 1.0,
    max_peso_pct: float = MAX_PESO_POSICION_PCT,
) -> tuple[int, list[str]]:
    """Número de acciones que hace que perder en el stop cueste el riesgo fijado.

    Fórmula: acciones = (capital x riesgo%) / |entrada - stop|.

    Después se aplican dos topes: el factor de régimen (arriesgar menos cuando el
    contexto es peor) y el peso máximo por posición.
    """
    avisos: list[str] = []

    if capital <= 0 or entrada <= 0:
        return 0, ["BLOQUEO: capital o precio de entrada no válidos."]

    riesgo_accion = abs(entrada - stop)
    if riesgo_accion <= 0:
        return 0, ["BLOQUEO: el stop coincide con la entrada, no hay riesgo definido."]

    riesgo_objetivo = capital * (riesgo_por_operacion_pct / 100.0) * factor_regimen
    acciones = int(riesgo_objetivo // riesgo_accion)

    if acciones <= 0:
        avisos.append(
            "BLOQUEO: con este capital y este riesgo por operación no sale ni una acción. "
            "El stop está demasiado lejos para el tamaño de la cuenta."
        )
        return 0, avisos

    # Tope de concentración
    peso = (acciones * entrada) / capital * 100.0
    if peso > max_peso_pct:
        acciones = int((capital * max_peso_pct / 100.0) // entrada)
        avisos.append(
            f"Tamaño recortado al {max_peso_pct:.0f}% del capital: el stop era tan estrecho "
            "que el cálculo por riesgo concentraba demasiado en un solo valor."
        )

    if factor_regimen < 1.0:
        avisos.append(
            f"Tamaño reducido al {factor_regimen:.0%} por el régimen de mercado actual."
        )

    return max(acciones, 0), avisos


def construir_plan(
    entrada: float,
    atr: float,
    *,
    direccion: Direccion = "largo",
    capital: float = 10_000.0,
    riesgo_por_operacion_pct: float = 1.0,
    multiplo_atr: float = MULTIPLO_ATR_STOP,
    factor_regimen: float = 1.0,
    objetivo_principal: float = 2.0,
) -> PlanOperacion:
    """Plan de operación completo a partir del precio y su volatilidad."""

    stop = calcular_stop(entrada, atr, direccion, multiplo_atr)

    # Sin ATR válido no hay stop posible. calcular_stop devuelve 0.0 en ese
    # caso, y dejarlo pasar produciría un plan con el stop en un precio de cero:
    # aparentemente operable, con un riesgo real del 100% por acción. Un valor
    # suspendido de cotización o recién salido a bolsa cae justo aquí.
    if stop <= 0 or atr <= 0:
        return PlanOperacion(
            direccion=direccion, entrada=round(entrada, 4), stop=0.0, objetivos={},
            acciones=0, capital_comprometido=0.0, riesgo_euros=0.0, riesgo_pct_real=0.0,
            peso_cartera_pct=0.0, ratio_riesgo_beneficio=None,
            avisos=["BLOQUEO: sin volatilidad medible (ATR) no se puede situar un stop."],
        )

    objetivos = calcular_objetivos(entrada, stop, direccion)
    acciones, avisos = dimensionar_posicion(
        capital,
        riesgo_por_operacion_pct,
        entrada,
        stop,
        factor_regimen=factor_regimen,
    )

    riesgo_accion = abs(entrada - stop)
    riesgo_euros = acciones * riesgo_accion
    capital_comprometido = acciones * entrada

    objetivo_precio = objetivos.get(f"{objetivo_principal:g}R")
    ratio = None
    if objetivo_precio and riesgo_accion > 0:
        ratio = round(abs(objetivo_precio - entrada) / riesgo_accion, 2)
        if ratio < RATIO_MINIMO_ACEPTABLE:
            avisos.append(
                f"Ratio beneficio/riesgo de {ratio:.1f}: por debajo de {RATIO_MINIMO_ACEPTABLE} "
                "hay que acertar demasiado a menudo para que el sistema sea rentable."
            )

    distancia_pct = (riesgo_accion / entrada * 100.0) if entrada else 0.0
    if distancia_pct > 15.0:
        avisos.append(
            f"El stop queda a un {distancia_pct:.1f}% de la entrada: es un valor muy volátil "
            "y la posición resultante será pequeña."
        )

    return PlanOperacion(
        direccion=direccion,
        entrada=round(entrada, 4),
        stop=stop,
        objetivos=objetivos,
        acciones=acciones,
        capital_comprometido=round(capital_comprometido, 2),
        riesgo_euros=round(riesgo_euros, 2),
        riesgo_pct_real=round(riesgo_euros / capital * 100.0, 3) if capital else 0.0,
        peso_cartera_pct=round(capital_comprometido / capital * 100.0, 2) if capital else 0.0,
        ratio_riesgo_beneficio=ratio,
        avisos=avisos,
    )


def expectativa_sistema(tasa_acierto_pct: float, r_medio_ganador: float, r_medio_perdedor: float = 1.0) -> float:
    """Expectativa en R por operación.

    Es la única cifra que dice si un sistema gana dinero, y desmonta la trampa
    clásica del swing: acertar mucho no basta. Un sistema que acierta el 60% de
    las veces pero recoge sólo 0.5R en cada acierto y pierde 1R en cada fallo
    tiene expectativa NEGATIVA (0.6x0.5 - 0.4x1 = -0.10R), mientras que otro que
    sólo acierta el 40% pero deja correr las ganancias hasta 3R gana 0.60R por
    operación. El tamaño de las ganancias pesa más que la frecuencia.
    """
    p = max(0.0, min(tasa_acierto_pct, 100.0)) / 100.0
    return round(p * r_medio_ganador - (1.0 - p) * abs(r_medio_perdedor), 4)
