"""Detección de bases chartistas y puntos pivote (la parte técnica de CAN SLIM).

Qué es una base
---------------
En la metodología de O'Neil una "base" es una consolidación que sigue a un
avance: el valor sube con fuerza, se para, digiere la subida en un rango
lateral o en forma de taza, y desde ahí rompe al alza. El punto de compra no es
un mínimo ni una media, es el **punto pivote**: el máximo de esa consolidación.

Por qué se implementa así
-------------------------
El reconocimiento de patrones de O'Neil es en gran parte visual y subjetivo
("taza con asa", "doble suelo", "base plana"), y su producto comercial dedica
años de datos a ello. Reproducirlo exactamente no es realista ni honesto. Lo
que sí se puede hacer es capturar la **estructura común** a todas esas figuras,
que es lo que de verdad las hace funcionar:

1. Un avance previo significativo (hay algo que consolidar).
2. Una pausa de duración mínima en la que el precio no se derrumba.
3. Un techo bien definido dentro de esa pausa: el pivote.
4. Una ruptura de ese techo con volumen muy por encima de lo normal.

Después se clasifica la figura resultante (plana, taza, doble suelo) según su
profundidad y forma, pero la señal no depende de acertar el nombre.

Causalidad
----------
Toda la detección en la sesión ``i`` mira exclusivamente hacia atrás. Es la
condición que permite validar la estrategia con el backtest existente sin
contaminarla con información futura.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

# --- Parámetros de las figuras (4ª edición del libro, valores de referencia) ---

# Semanas mínimas y máximas de consolidación. Cinco semanas es el mínimo que
# O'Neil exige a una base plana; por encima de 65 la figura deja de ser una
# consolidación y pasa a ser una tendencia bajista larga.
SEMANAS_MIN_BASE = 5
SEMANAS_MAX_BASE = 65

# Profundidad tolerada. Por encima de un tercio, la figura suele ser una caída
# con rebote y no una consolidación sana.
PROFUNDIDAD_MAX_BASE = 0.35
PROFUNDIDAD_MAX_PLANA = 0.15

# Avance previo mínimo que justifica la consolidación.
AVANCE_PREVIO_MIN = 0.20

# Volumen de confirmación en la ruptura: O'Neil exige entre un 40% y un 50%
# sobre la media de 50 sesiones. Sin él, la ruptura falla con mucha frecuencia.
VOLUMEN_RUPTURA_MIN = 1.40

# Zona de compra: desde el pivote hasta un 5% por encima. Perseguir por encima
# de eso ("extended") es una de las causas clásicas de que salte el stop.
ZONA_COMPRA_MAX = 0.05

SESIONES_POR_SEMANA = 5

BASE_PLANA = "base_plana"
BASE_TAZA = "taza"
BASE_DOBLE_SUELO = "doble_suelo"
BASE_GENERICA = "consolidacion"

NOMBRES_BASE = {
    BASE_PLANA: "Base plana",
    BASE_TAZA: "Taza",
    BASE_DOBLE_SUELO: "Doble suelo",
    BASE_GENERICA: "Consolidación",
}


@dataclass
class Base:
    """Una consolidación detectada y su punto de compra."""

    tipo: str
    inicio: int
    fin: int
    pivote: float
    minimo: float
    profundidad_pct: float
    semanas: float
    avance_previo_pct: float

    @property
    def nombre(self) -> str:
        return NOMBRES_BASE.get(self.tipo, "Consolidación")

    def zona_compra(self) -> tuple[float, float]:
        """Rango de precios en el que la compra sigue siendo válida."""
        return self.pivote, round(self.pivote * (1 + ZONA_COMPRA_MAX), 4)

    def objetivo_medido(self) -> float:
        """Proyección de la profundidad de la base desde el pivote.

        Es el objetivo clásico de O'Neil: se asume que el movimiento posterior a
        la ruptura tiene al menos la amplitud de la consolidación que lo precede.
        """
        return round(self.pivote + (self.pivote - self.minimo), 4)


def _clasificar(profundidad: float, cierres: np.ndarray) -> str:
    """Nombra la figura a partir de su profundidad y su forma.

    La clasificación es orientativa: sirve para que el usuario reconozca lo que
    está mirando, no para decidir la señal. Una consolidación con las
    condiciones correctas es operable se llame como se llame.
    """
    if profundidad <= PROFUNDIDAD_MAX_PLANA:
        return BASE_PLANA

    n = len(cierres)
    if n < 9:
        return BASE_GENERICA

    # Doble suelo: dos mínimos separados por un repunte intermedio claro.
    mitad = n // 2
    min_izq = float(np.min(cierres[:mitad]))
    min_der = float(np.min(cierres[mitad:]))
    pico_medio = float(np.max(cierres[mitad // 2 : mitad + mitad // 2])) if n >= 12 else 0.0
    suelo = min(min_izq, min_der)
    if suelo > 0 and pico_medio > suelo * 1.05 and abs(min_izq - min_der) / suelo < 0.08:
        return BASE_DOBLE_SUELO

    # Taza: el mínimo cae en el tercio central (forma de U, no de V ni de L).
    posicion_minimo = int(np.argmin(cierres)) / n
    if 0.25 <= posicion_minimo <= 0.75:
        return BASE_TAZA

    return BASE_GENERICA


def detectar_base(
    df: pd.DataFrame,
    indice: int = -1,
    *,
    semanas_min: int = SEMANAS_MIN_BASE,
    semanas_max: int = SEMANAS_MAX_BASE,
) -> Base | None:
    """Busca la consolidación vigente que precede a la sesión ``indice``.

    Se prueba de la base más corta a la más larga y se devuelve la primera
    válida: entre varias lecturas posibles, la consolidación reciente es la que
    define el nivel que el mercado está mirando ahora mismo.
    """
    if df is None or df.empty:
        return None

    fin = indice if indice >= 0 else len(df) + indice
    if fin < 60 or fin >= len(df):
        return None

    altos = df["High"].to_numpy(dtype=float)
    bajos = df["Low"].to_numpy(dtype=float)
    cierres = df["Close"].to_numpy(dtype=float)

    for semanas in range(semanas_min, semanas_max + 1, 2):
        largo = semanas * SESIONES_POR_SEMANA
        inicio = fin - largo
        if inicio < 20:
            break

        ventana_altos = altos[inicio : fin + 1]
        ventana_bajos = bajos[inicio : fin + 1]
        ventana_cierres = cierres[inicio : fin + 1]
        if np.isnan(ventana_cierres).any():
            continue

        pivote = float(np.max(ventana_altos))
        minimo = float(np.min(ventana_bajos))
        if pivote <= 0 or minimo <= 0:
            continue

        profundidad = (pivote - minimo) / pivote
        if profundidad > PROFUNDIDAD_MAX_BASE:
            continue

        # Avance previo: la consolidación tiene que consolidar algo.
        referencia = max(inicio - largo, 0)
        previo = cierres[referencia:inicio]
        if previo.size < 10 or np.isnan(previo).any():
            continue
        suelo_previo = float(np.min(previo))
        if suelo_previo <= 0:
            continue
        avance = (pivote - suelo_previo) / suelo_previo
        if avance < AVANCE_PREVIO_MIN:
            continue

        # El pivote debe estar en la parte reciente de la base, no al principio:
        # si el techo se formó al inicio y el precio lleva meses cayendo, eso no
        # es una consolidación, es una tendencia bajista.
        posicion_pivote = int(np.argmax(ventana_altos)) / max(len(ventana_altos) - 1, 1)
        if posicion_pivote < 0.15:
            continue

        return Base(
            tipo=_clasificar(profundidad, ventana_cierres),
            inicio=inicio,
            fin=fin,
            pivote=round(pivote, 4),
            minimo=round(minimo, 4),
            profundidad_pct=round(profundidad * 100, 2),
            semanas=round(largo / SESIONES_POR_SEMANA, 1),
            avance_previo_pct=round(avance * 100, 2),
        )

    return None


@dataclass
class Ruptura:
    """Ruptura del pivote de una base, con su contexto."""

    base: Base
    precio: float
    volumen_relativo: float
    extension_pct: float
    en_zona_compra: bool
    sesiones_desde_ruptura: int

    @property
    def fallida(self) -> bool:
        """El precio rompió el pivote y ha vuelto por debajo.

        Es el caso más común de todos: el estudio de Bulkowski sobre 913
        operaciones encontró un 62% de retrocesos ("throwbacks") en la taza con
        asa. Distinguirlo importa porque una ruptura que ya ha fallado no es una
        oportunidad de compra, es justo lo contrario.
        """
        return self.extension_pct < 0

    @property
    def extendida(self) -> bool:
        """Ha subido más de un 5% sobre el pivote: perseguirla sale caro."""
        return self.extension_pct > ZONA_COMPRA_MAX * 100

    @property
    def estado(self) -> str:
        if self.fallida:
            return "Ruptura fallida: el precio ha vuelto por debajo del pivote"
        if self.extendida:
            return f"Extendida un {self.extension_pct:.1f}% sobre el pivote: fuera de la zona de compra"
        return "En zona de compra"


def detectar_ruptura(
    df: pd.DataFrame,
    indice: int = -1,
    *,
    volumen_minimo: float = VOLUMEN_RUPTURA_MIN,
    max_sesiones: int = 5,
) -> Ruptura | None:
    """Detecta si el precio ha roto el pivote de su base con volumen.

    ``max_sesiones`` permite capturar rupturas de días anteriores que siguen en
    zona de compra: exigir el día exacto de la ruptura dejaría fuera casi todas
    las oportunidades reales, porque el escáner se mira una vez al día.
    """
    if df is None or df.empty:
        return None

    fin = indice if indice >= 0 else len(df) + indice
    if fin < 60 or fin >= len(df):
        return None

    cierres = df["Close"].to_numpy(dtype=float)
    vol_rel = df["vol_rel"].to_numpy(dtype=float) if "vol_rel" in df.columns else None
    if vol_rel is None:
        return None

    precio_actual = cierres[fin]
    if not np.isfinite(precio_actual):
        return None

    for retroceso in range(max_sesiones + 1):
        sesion = fin - retroceso
        if sesion < 60:
            break

        # La base se busca en la sesión ANTERIOR a la ruptura: incluir el día
        # que rompe haría que el propio máximo de la ruptura fuese el pivote y
        # ninguna ruptura sería detectable.
        base = detectar_base(df, sesion - 1)
        if base is None:
            continue

        rompe = cierres[sesion] > base.pivote
        anterior_dentro = cierres[sesion - 1] <= base.pivote
        volumen = float(vol_rel[sesion]) if np.isfinite(vol_rel[sesion]) else 0.0

        if rompe and anterior_dentro and volumen >= volumen_minimo:
            extension = (precio_actual - base.pivote) / base.pivote
            return Ruptura(
                base=base,
                precio=round(float(precio_actual), 4),
                volumen_relativo=round(volumen, 2),
                extension_pct=round(extension * 100, 2),
                en_zona_compra=bool(0 <= extension <= ZONA_COMPRA_MAX),
                sesiones_desde_ruptura=retroceso,
            )

    return None
