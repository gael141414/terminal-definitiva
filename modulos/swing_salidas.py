"""Gestión de posiciones abiertas: cuándo soltar un largo.

De dónde sale este módulo
-------------------------
La validación histórica dejó claro que las dos estrategias cortas del catálogo
pierden dinero como ENTRADAS (−0,14R y −0,20R, y ningún ajuste de salida las
rescató). Pero que apostar contra un valor que rompe a la baja no sea rentable
no significa que la ruptura no informe: el coste de equivocarse es asimétrico.
Abrir un corto y equivocarse cuesta dinero; cerrar un largo y equivocarse cuesta
la subida que te pierdes, sin riesgo de pérdida adicional.

La idea era reutilizar esas señales como **avisos de salida**. Se midió, y el
resultado obliga a matizar el módulo entero (ver ``RESULTADO_VALIDACION``):

- Salir con señal bajista: sólo se activó en el 0,9% de las operaciones y movió
  la expectativa +0,0005R. Es inerte, no dañino. La razón es estructural: las
  estrategias cortas exigen precio bajo la media de 200 Y media de 50 por debajo
  de la de 200, y un largo abierto en tendencia rara vez se deteriora tanto en el
  horizonte de 30 sesiones.
- Salir con stop dinámico (chandelier a 3 ATR): −0,116R de expectativa y un peor
  caso bastante peor (−1,65R frente a −1,00R), porque la salida en la apertura
  siguiente puede abrir con hueco por debajo del nivel.

Conclusión: sobre 2.377 operaciones y dos estrategias de entrada distintas,
**ninguna gestión activa de salida batió al stop fijo con horizonte**. Este
módulo se conserva como panel INFORMATIVO -- ver qué le está pasando a una
posición abierta tiene valor propio -- pero la interfaz debe advertir de que
actuar sobre estas señales empeoró el resultado en la prueba histórica.

Cuatro señales de salida, de más a menos grave
---------------------------------------------
1. Stop roto: la tesis con la que se entró ya no se sostiene.
2. Señal técnica bajista (las estrategias cortas del catálogo).
3. Pérdida de la media de 50 o de la de 200.
4. Stop dinámico (chandelier): protege el beneficio ya acumulado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from modulos.indicadores import atr

# Múltiplo de ATR del stop dinámico, medido desde el máximo alcanzado. Es más
# ancho que el stop inicial (2 ATR) a propósito: una vez la operación va a favor
# conviene darle margen para respirar en vez de cerrarla en el primer retroceso.
MULTIPLO_CHANDELIER = 3.0

# Cifras de la validación (30 valores, 5 años, 2.377 operaciones simuladas).
# Se guardan aquí para que la interfaz no pueda presentar el panel sin ellas.
RESULTADO_VALIDACION = {
    "operaciones": 2377,
    "expectativa_aguantar": 0.39,
    "expectativa_salida_por_senal": 0.39,
    "expectativa_stop_dinamico": 0.28,
    "conclusion": (
        "Ninguna gestión activa de salida mejoró al stop fijo con horizonte. "
        "Salir con señal bajista resultó inerte (se activa en menos del 1% de los "
        "casos) y el stop dinámico restó unos 0,11R por operación."
    ),
}

MANTENER = "mantener"
VIGILAR = "vigilar"
SALIR = "salir"

ETIQUETAS_ACCION = {
    MANTENER: "Mantener",
    VIGILAR: "Vigilar de cerca",
    SALIR: "Señal de salida",
}


@dataclass
class DecisionSalida:
    """Veredicto sobre una posición abierta."""

    accion: str = MANTENER
    motivos: list[str] = field(default_factory=list)
    stop_sugerido: float | None = None
    precio_actual: float | None = None
    gravedad: int = 0

    @property
    def etiqueta(self) -> str:
        return ETIQUETAS_ACCION.get(self.accion, self.accion)


def stop_chandelier(df: pd.DataFrame, indice_entrada: int, indice_actual: int = -1,
                    multiplo: float = MULTIPLO_CHANDELIER) -> float | None:
    """Stop dinámico anclado al máximo alcanzado desde la entrada.

    Sube cuando el precio sube y nunca baja, que es la propiedad que lo hace
    útil: convierte progresivamente una operación ganadora en una que ya no
    puede perder, sin tener que acertar el techo.
    """
    if df is None or df.empty:
        return None

    fin = indice_actual if indice_actual >= 0 else len(df) + indice_actual
    inicio = max(indice_entrada, 0)
    if fin <= inicio or fin >= len(df):
        return None

    ventana = df.iloc[inicio : fin + 1]
    if ventana.empty or "High" not in ventana.columns:
        return None

    maximo = float(ventana["High"].max())
    rango = atr(df.iloc[: fin + 1]).iloc[-1]
    if not np.isfinite(maximo) or not np.isfinite(rango) or rango <= 0:
        return None

    return round(maximo - multiplo * float(rango), 4)


def evaluar_salida(
    df: pd.DataFrame,
    *,
    entrada: float,
    stop: float | None = None,
    indice_entrada: int | None = None,
    indice: int = -1,
) -> DecisionSalida:
    """Analiza una posición larga abierta y devuelve qué hacer con ella.

    ``df`` debe venir ya enriquecido por ``modulos.indicadores``.
    """
    decision = DecisionSalida()
    if df is None or df.empty:
        return decision

    posicion = indice if indice >= 0 else len(df) + indice
    if posicion < 1 or posicion >= len(df):
        return decision

    fila = df.iloc[posicion]
    cierre = float(fila.get("Close", np.nan))
    if not np.isfinite(cierre):
        return decision

    decision.precio_actual = round(cierre, 4)

    # 1. Stop roto -- la más grave: la tesis ya está invalidada.
    if stop and stop > 0 and cierre <= stop:
        decision.motivos.append(
            f"El precio ({cierre:,.2f}) ha perdido tu stop ({stop:,.2f}): la tesis con la que "
            "entraste ya no se sostiene."
        )
        decision.gravedad += 3

    # 2. Señales técnicas bajistas: las estrategias cortas usadas como aviso.
    from modulos.swing_estrategias import ESTRATEGIAS_POR_ID

    for eid in ("ruptura_bajista", "rebote_fallido"):
        estrategia = ESTRATEGIAS_POR_ID.get(eid)
        if estrategia is None:
            continue
        try:
            señal = estrategia.evaluar(df, None, posicion)
        except Exception:
            continue
        if señal is not None:
            decision.motivos.append(
                f"Señal técnica bajista ({estrategia.nombre}): la estructura del valor se ha girado."
            )
            decision.gravedad += 2
            break

    # 3. Pérdida de referencias de tendencia.
    sma50 = float(fila.get("sma50", np.nan))
    sma200 = float(fila.get("sma200", np.nan))
    previo = df.iloc[posicion - 1]
    if np.isfinite(sma200) and cierre < sma200 <= float(previo.get("Close", np.nan)):
        decision.motivos.append("Acaba de perder la media de 200 sesiones, su referencia de tendencia de fondo.")
        decision.gravedad += 2
    elif np.isfinite(sma50) and cierre < sma50 <= float(previo.get("Close", np.nan)):
        decision.motivos.append("Ha perdido la media de 50 sesiones: primer aviso de deterioro.")
        decision.gravedad += 1

    # 4. Stop dinámico sobre el beneficio ya acumulado.
    if indice_entrada is not None:
        chandelier = stop_chandelier(df, indice_entrada, posicion)
        if chandelier is not None:
            decision.stop_sugerido = chandelier
            if stop is None or chandelier > stop:
                decision.motivos.append(
                    f"Puedes subir el stop a {chandelier:,.2f} (3 ATR bajo el máximo alcanzado) "
                    "y asegurar parte del beneficio."
                )
            if cierre <= chandelier:
                decision.motivos.append(
                    f"El precio ha caído por debajo del stop dinámico ({chandelier:,.2f}): "
                    "el movimiento a favor se ha agotado."
                )
                decision.gravedad += 2

    if decision.gravedad >= 3:
        decision.accion = SALIR
    elif decision.gravedad >= 1:
        decision.accion = VIGILAR

    if not decision.motivos:
        decision.motivos.append("Sin señales de deterioro: la posición sigue su curso.")

    return decision


# --------------------------------------------------------------------------
# Validación de la regla de salida
# --------------------------------------------------------------------------


def validar_regla_de_salida(
    precios: dict[str, pd.DataFrame],
    estrategia_entrada: str = "pullback_tendencia",
    *,
    horizonte: int = 30,
    calentamiento: int = 210,
) -> dict[str, Any]:
    """Compara salir con señal bajista frente a aguantar hasta el horizonte.

    Es la comprobación que justifica (o desmonta) la idea de reciclar las
    señales cortas como salidas. Se simulan las MISMAS entradas por ambos
    caminos, de modo que la única diferencia es la regla de salida.

    Se mide en R para que la comparación no dependa del tamaño de la operación.
    """
    from modulos.indicadores import enriquecer_ohlcv
    from modulos.swing_estrategias import ESTRATEGIAS_POR_ID
    from modulos.swing_riesgo import MULTIPLO_ATR_STOP

    entrada_est = ESTRATEGIAS_POR_ID.get(estrategia_entrada)
    salida_ests = [ESTRATEGIAS_POR_ID.get(e) for e in ("ruptura_bajista", "rebote_fallido")]
    salida_ests = [e for e in salida_ests if e is not None]
    if entrada_est is None or not salida_ests:
        return {}

    r_aguantar: list[float] = []
    r_con_salida: list[float] = []
    r_trailing: list[float] = []
    salidas_anticipadas = 0

    for ohlcv in precios.values():
        try:
            df = enriquecer_ohlcv(ohlcv)
        except Exception:
            continue
        if df.empty or len(df) < calentamiento + horizonte + 5:
            continue

        altos = df["High"].to_numpy(dtype=float)
        bajos = df["Low"].to_numpy(dtype=float)
        cierres = df["Close"].to_numpy(dtype=float)
        aperturas = df["Open"].to_numpy(dtype=float)

        ultima = -10**6
        for i in range(calentamiento, len(df) - horizonte - 2):
            if i - ultima < 5:
                continue
            try:
                señal = entrada_est.evaluar(df, None, i)
            except Exception:
                continue
            if señal is None or señal.atr <= 0:
                continue

            ent = aperturas[i + 1]
            if not np.isfinite(ent) or ent <= 0:
                continue
            riesgo = MULTIPLO_ATR_STOP * señal.atr
            stop = ent - riesgo
            fin = min(i + 1 + horizonte, len(df) - 1)

            # --- Camino A: aguantar (stop fijo u horizonte) ---
            r_a = None
            for j in range(i + 1, fin + 1):
                if bajos[j] <= stop:
                    r_a = -1.0
                    break
            if r_a is None:
                r_a = (cierres[fin] - ent) / riesgo

            # --- Camino C: stop dinámico (chandelier) ---
            # Se recalcula el máximo alcanzado sesión a sesión, que es lo que
            # hace que el stop suba con el precio y nunca baje.
            r_c = None
            maximo = ent
            for j in range(i + 1, fin + 1):
                if bajos[j] <= stop:
                    r_c = -1.0
                    break
                maximo = max(maximo, altos[j])
                trailing = maximo - MULTIPLO_CHANDELIER * señal.atr
                if trailing > stop and bajos[j] <= trailing and j + 1 <= len(df) - 1:
                    r_c = (aperturas[j + 1] - ent) / riesgo
                    break
            if r_c is None:
                r_c = (cierres[fin] - ent) / riesgo
            r_trailing.append(r_c)

            # --- Camino B: igual, pero saliendo también con señal bajista ---
            r_b = None
            for j in range(i + 1, fin + 1):
                if bajos[j] <= stop:
                    r_b = -1.0
                    break
                hay_señal = False
                for est in salida_ests:
                    try:
                        if est.evaluar(df, None, j) is not None:
                            hay_señal = True
                            break
                    except Exception:
                        continue
                if hay_señal and j + 1 <= len(df) - 1:
                    r_b = (aperturas[j + 1] - ent) / riesgo  # salida en la apertura siguiente
                    salidas_anticipadas += 1
                    break
            if r_b is None:
                r_b = (cierres[fin] - ent) / riesgo

            r_aguantar.append(r_a)
            r_con_salida.append(r_b)
            ultima = i

    if not r_aguantar:
        return {}

    a = np.array(r_aguantar, dtype=float)
    b = np.array(r_con_salida, dtype=float)
    c = np.array(r_trailing, dtype=float) if r_trailing else np.array([])
    return {
        "operaciones": int(a.size),
        "salidas_anticipadas": int(salidas_anticipadas),
        "expectativa_aguantar": round(float(a.mean()), 4),
        "expectativa_con_salida": round(float(b.mean()), 4),
        "expectativa_trailing": round(float(c.mean()), 4) if c.size else None,
        "diferencia": round(float(b.mean() - a.mean()), 4),
        "diferencia_trailing": round(float(c.mean() - a.mean()), 4) if c.size else None,
        "peor_aguantar": round(float(a.min()), 2),
        "peor_con_salida": round(float(b.min()), 2),
        "peor_trailing": round(float(c.min()), 2) if c.size else None,
        "mejora": bool(b.mean() > a.mean()),
        "mejora_trailing": bool(c.size and c.mean() > a.mean()),
    }
