"""Catálogo de estrategias de swing: reglas explícitas, no un modelo opaco.

Filosofía
---------
Cada estrategia es un conjunto de condiciones escritas que se cumplen o no, y
que devuelven los motivos concretos por los que se ha disparado. Nada de "el
algoritmo dice que compres": si una señal no se puede explicar en una frase, no
se puede confiar en ella ni corregirla cuando falla.

Las seis estrategias no son invenciones: cada una recoge un comportamiento del
mercado documentado. La ventaja de este terminal no está en descubrir una regla
secreta, sino en tres cosas que sí son difíciles de hacer a mano:

1. Aplicarlas sobre cientos de valores cada noche.
2. Activarlas sólo en el régimen de mercado donde funcionan.
3. Cruzarlas con los fundamentales que la app ya calcula -- comprar rupturas
   sólo de empresas de calidad y vender en corto sólo empresas con deterioro
   contable real es algo que un terminal puramente técnico no puede hacer.

Todas las funciones ``evaluar`` son puras: reciben el DataFrame ya enriquecido
por ``modulos.indicadores`` y un contexto fundamental opcional, y no tocan red.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from modulos.swing_regimen import (
    CORRECCION,
    DISTRIBUCION,
    PANICO,
    RANGO_ALCISTA,
    TENDENCIA_ALCISTA,
)

LARGO = "largo"
CORTO = "corto"

# Mínimos de operabilidad: por debajo de esto la señal es estadísticamente
# ruido o directamente no se puede ejecutar sin mover el precio.
VOLUMEN_MINIMO_DIARIO = 300_000
PRECIO_MINIMO = 3.0


@dataclass
class Senal:
    """Una oportunidad detectada, con su porqué explícito."""

    ticker: str
    estrategia: str
    nombre_estrategia: str
    direccion: str
    precio: float
    atr: float
    fuerza: float
    motivos: list[str] = field(default_factory=list)
    datos: dict[str, Any] = field(default_factory=dict)
    fecha: Any = None

    @property
    def es_largo(self) -> bool:
        return self.direccion == LARGO


@dataclass
class Estrategia:
    """Definición de una estrategia y el contexto en el que es válida."""

    id: str
    nombre: str
    direccion: str
    resumen: str
    evidencia: str
    regimenes: tuple[str, ...]
    evaluar: Callable[..., Senal | None]
    horizonte_dias: tuple[int, int] = (5, 30)
    # Expectativa medida en la validación histórica del proyecto (178 valores,
    # 5 años, entrada en apertura siguiente, stop 2 ATR, objetivo 2R). Se guarda
    # en el catálogo para que la interfaz no pueda mostrar una estrategia sin su
    # resultado real al lado: una regla plausible y una regla con ventaja
    # demostrada no se parecen en nada, y el usuario tiene que poder distinguirlas.
    expectativa_medida: float | None = None
    operaciones_medidas: int | None = None
    # Expectativa en el tramo RESERVADO (últimos ~40% del histórico, corte en
    # 2024-08-27). Es la cifra que de verdad importa: la de arriba está medida
    # sobre los mismos años con los que se escribieron las reglas, así que
    # incorpora parte de ajuste al pasado. Cuando ambas divergen mucho, la buena
    # es esta.
    expectativa_fuera_muestra: float | None = None

    @property
    def validada(self) -> bool:
        """True sólo si conserva ventaja FUERA de muestra.

        Se exige la cifra out-of-sample y no la global a propósito: "Ruptura de
        máximos" era positiva in-sample (+0,05R) y se queda en cero fuera, así
        que presentarla como validada sería engañoso.
        """
        referencia = (
            self.expectativa_fuera_muestra
            if self.expectativa_fuera_muestra is not None
            else self.expectativa_medida
        )
        return referencia is not None and referencia > 0.01


# --------------------------------------------------------------------------
# Utilidades comunes
# --------------------------------------------------------------------------


def _valores(df: pd.DataFrame, indice: int = -1) -> tuple[pd.Series, pd.Series] | None:
    """Vela de ``indice`` y la anterior, o None si no hay histórico suficiente.

    ``indice`` existe para el backtest. Rebanar el DataFrame en cada paso
    (``df.iloc[:i+1]``) convertía el recorrido histórico en O(n^2) y hacía
    inviable validar una estrategia sobre 5 años dentro de la aplicación. Como
    todos los indicadores son causales, la fila i ya contiene sólo información
    hasta i: basta con leerla directamente, sin copiar nada.
    """
    if df is None:
        return None
    posicion = indice if indice >= 0 else len(df) + indice
    if posicion < 210 or posicion >= len(df):  # 200 sesiones + margen
        return None
    ultimo = df.iloc[posicion]
    previo = df.iloc[posicion - 1]
    if pd.isna(ultimo.get("Close")) or pd.isna(ultimo.get("sma200")):
        return None
    return ultimo, previo


def _liquidez_suficiente(u: pd.Series) -> bool:
    """Descarta chicharros: sin volumen no hay salida al precio que marca el gráfico."""
    volumen = u.get("Volume", 0)
    precio = u.get("Close", 0)
    if pd.isna(volumen) or pd.isna(precio):
        return False
    return float(volumen) >= VOLUMEN_MINIMO_DIARIO and float(precio) >= PRECIO_MINIMO


def _num(valor: Any, defecto: float = 0.0) -> float:
    try:
        if valor is None or pd.isna(valor):
            return defecto
        return float(valor)
    except (TypeError, ValueError):
        return defecto


def _acotar(valor: float, minimo: float = 0.0, maximo: float = 100.0) -> float:
    return max(minimo, min(valor, maximo))


def _bonus_fundamental(contexto: dict[str, Any] | None, direccion: str) -> tuple[float, list[str]]:
    """Traduce el contexto fundamental a puntos de fuerza y a motivos legibles.

    Es la fusión que diferencia a este escáner de uno puramente técnico: la misma
    ruptura vale más en una empresa rentable que en una que quema caja, y el
    mismo desplome vale más como corto si la contabilidad ya venía dando avisos.
    """
    if not contexto:
        return 0.0, []

    puntos = 0.0
    motivos: list[str] = []

    score = contexto.get("buffett_score")
    banderas = contexto.get("red_flags", 0) or 0
    fcf_negativo = bool(contexto.get("fcf_negativo", False))
    deuda_alta = bool(contexto.get("deuda_alta", False))

    if direccion == LARGO:
        if score is not None and _num(score) >= 60:
            puntos += 10
            motivos.append(f"Calidad fundamental sólida (score {_num(score):.0f}/100)")
        elif score is not None and _num(score) < 40:
            puntos -= 10
            motivos.append(f"Calidad fundamental débil (score {_num(score):.0f}/100): ruptura de menor confianza")
        if banderas:
            puntos -= 8
            motivos.append(f"{int(banderas)} señal(es) forense(s) abiertas pese a la fortaleza técnica")
    else:
        if banderas:
            puntos += 12
            motivos.append(f"{int(banderas)} bandera(s) roja(s) contables: el deterioro no es sólo de precio")
        if fcf_negativo:
            puntos += 8
            motivos.append("Flujo de caja libre negativo: quema caja mientras el precio cae")
        if deuda_alta:
            puntos += 6
            motivos.append("Apalancamiento elevado: menos margen para aguantar una travesía")
        if score is not None and _num(score) >= 70:
            puntos -= 15
            motivos.append(
                f"Cuidado: fundamentales fuertes (score {_num(score):.0f}/100). "
                "Ponerse corto contra una buena empresa suele ser una corrección, no una tendencia"
            )

    return puntos, motivos


# --------------------------------------------------------------------------
# ESTRATEGIAS LARGAS
# --------------------------------------------------------------------------


def _eval_ruptura_maximos(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Ruptura de máximos de 55 sesiones con expansión de volumen."""
    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    techo = _num(u.get("dc_superior55"))
    if techo <= 0 or cierre <= techo:
        return None
    if cierre <= _num(u.get("sma200")):
        return None

    vol_rel = _num(u.get("vol_rel"))
    if vol_rel < 1.3:
        return None

    motivos = [
        f"Cierre en {cierre:.2f} sobre el máximo de 55 sesiones ({techo:.2f})",
        f"Volumen {vol_rel:.1f}x su media: hay demanda real detrás de la ruptura",
        f"Cotiza a un {abs(_num(u.get('dist_max52'))):.1f}% de su máximo de 52 semanas",
    ]

    fuerza = 45.0
    fuerza += min((vol_rel - 1.3) * 12, 18)
    fuerza += min(max(_num(u.get("adx14")) - 20, 0) * 0.8, 15)
    if _num(u.get("dist_max52")) > -3:
        fuerza += 8
        motivos.append("Prácticamente en máximos anuales: sin resistencia de vendedores atrapados encima")

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="ruptura_maximos", nombre_estrategia="Ruptura de máximos",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"vol_rel": round(vol_rel, 2), "adx": round(_num(u.get("adx14")), 1),
               "dist_max52": round(_num(u.get("dist_max52")), 1)},
    )


def _eval_pullback_tendencia(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Retroceso a la media en una tendencia alcista intacta."""
    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    sma50, sma200, ema21 = _num(u.get("sma50")), _num(u.get("sma200")), _num(u.get("ema21"))
    if not (cierre > sma200 and sma50 > sma200):
        return None

    # El retroceso debe tocar la zona de la media rápida sin perder la lenta.
    distancia_ema21 = abs(cierre - ema21) / cierre * 100 if cierre else 99
    if distancia_ema21 > 3.0 or cierre < sma50 * 0.97:
        return None

    rsi = _num(u.get("rsi14"))
    if not (35 <= rsi <= 55):  # enfriado, pero sin romperse
        return None

    motivos = [
        f"Tendencia intacta: precio sobre la media de 200 y media de 50 por encima de la de 200",
        f"Retroceso hasta la media de 21 sesiones (a un {distancia_ema21:.1f}% del precio)",
        f"RSI en {rsi:.0f}: se ha enfriado sin romper la estructura alcista",
    ]

    fuerza = 50.0
    fuerza += min(max(_num(u.get("adx14")) - 20, 0) * 0.7, 12)
    fuerza += min(max(_num(u.get("pendiente50")), 0) * 40, 12)
    if 40 <= rsi <= 50:
        fuerza += 6
        motivos.append("RSI en la zona donde históricamente reanudan las tendencias sanas")

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="pullback_tendencia", nombre_estrategia="Retroceso en tendencia",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"rsi": round(rsi, 1), "adx": round(_num(u.get("adx14")), 1),
               "dist_ema21": round(distancia_ema21, 2)},
    )


def _eval_reversion_rsi2(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Sobreventa extrema de corto plazo dentro de una tendencia alcista."""
    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    if cierre <= _num(u.get("sma200")):  # sólo se compra sobreventa en valores alcistas
        return None

    rsi2 = _num(u.get("rsi2"), 100)
    if rsi2 > 10:
        return None
    if cierre >= _num(u.get("sma20")):  # tiene que estar estirado a la baja
        return None

    motivos = [
        f"RSI de 2 sesiones en {rsi2:.1f}: sobreventa extrema de muy corto plazo",
        "El valor sigue sobre su media de 200: se compra una corrección, no una caída estructural",
        f"Precio por debajo de su media de 20 ({_num(u.get('sma20')):.2f}): estirado a la baja",
    ]

    fuerza = 48.0
    fuerza += (10 - rsi2) * 1.5
    distancia_sma20 = (_num(u.get("sma20")) - cierre) / cierre * 100 if cierre else 0
    fuerza += min(distancia_sma20 * 1.5, 12)
    if distancia_sma20 > 0:
        motivos.append(f"Volver a la media de 20 supondría un +{distancia_sma20:.1f}%")

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="reversion_rsi2", nombre_estrategia="Reversión por sobreventa",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"rsi2": round(rsi2, 1), "dist_sma20": round(distancia_sma20, 2)},
    )


def _eval_squeeze_disparo(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """La compresión de volatilidad acaba de liberarse al alza."""
    par = _valores(df, indice)
    if par is None:
        return None
    u, p = par
    if not _liquidez_suficiente(u):
        return None

    # El disparo es el momento exacto en que la compresión termina.
    if not (bool(p.get("squeeze", False)) and not bool(u.get("squeeze", False))):
        return None

    cierre = _num(u["Close"])
    if cierre <= _num(u.get("sma20")) or cierre <= _num(u.get("sma200")):
        return None

    vol_rel = _num(u.get("vol_rel"))
    if vol_rel < 1.2:
        return None

    motivos = [
        "La compresión de volatilidad (Bollinger dentro de Keltner) acaba de liberarse",
        f"La ruptura es al alza y con volumen {vol_rel:.1f}x la media",
        "Tras una compresión, el movimiento suele ser amplio; la dirección la marca la ruptura",
    ]

    fuerza = 46.0
    fuerza += min((vol_rel - 1.2) * 14, 18)
    fuerza += min(max(_num(u.get("macd_hist")), 0) * 8, 10)

    bonus, motivos_fund = _bonus_fundamental(contexto, LARGO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="squeeze_disparo", nombre_estrategia="Disparo de compresión",
        direccion=LARGO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"vol_rel": round(vol_rel, 2), "bb_ancho": round(_num(u.get("bb_ancho")), 4)},
    )


# --------------------------------------------------------------------------
# ESTRATEGIAS CORTAS
# --------------------------------------------------------------------------


def _eval_ruptura_bajista(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Pérdida de mínimos de 55 sesiones en una estructura ya bajista."""
    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    suelo = _num(u.get("dc_inferior55"))
    if suelo <= 0 or cierre >= suelo:
        return None
    if cierre >= _num(u.get("sma200")) or _num(u.get("sma50")) >= _num(u.get("sma200")):
        return None

    vol_rel = _num(u.get("vol_rel"))
    if vol_rel < 1.3:
        return None

    motivos = [
        f"Cierre en {cierre:.2f} bajo el mínimo de 55 sesiones ({suelo:.2f})",
        f"Volumen {vol_rel:.1f}x la media: hay venta institucional, no goteo",
        "Estructura bajista confirmada: precio bajo la media de 200 y media de 50 por debajo de la de 200",
    ]

    fuerza = 44.0
    fuerza += min((vol_rel - 1.3) * 12, 16)
    fuerza += min(max(_num(u.get("adx14")) - 20, 0) * 0.8, 14)

    bonus, motivos_fund = _bonus_fundamental(contexto, CORTO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="ruptura_bajista", nombre_estrategia="Ruptura bajista",
        direccion=CORTO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"vol_rel": round(vol_rel, 2), "adx": round(_num(u.get("adx14")), 1),
               "dist_min52": round(_num(u.get("dist_min52")), 1)},
    )


def _eval_rebote_fallido(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Rebote agotado contra la media en un valor en tendencia bajista.

    Es el corto de menor riesgo de los dos: se entra tras un rebote, no
    persiguiendo una caída, así que el stop queda cerca y arriba.
    """
    par = _valores(df, indice)
    if par is None:
        return None
    u, _p = par
    if not _liquidez_suficiente(u):
        return None

    cierre = _num(u["Close"])
    sma50, sma200 = _num(u.get("sma50")), _num(u.get("sma200"))
    if cierre >= sma200 or sma50 >= sma200:
        return None

    # El precio ha rebotado hasta la zona de la media de 50 y ahí se ha frenado.
    distancia_sma50 = (cierre - sma50) / cierre * 100 if cierre else -99
    if not (-4.0 <= distancia_sma50 <= 1.5):
        return None

    rsi = _num(u.get("rsi14"))
    if not (45 <= rsi <= 65):
        return None

    motivos = [
        "Tendencia bajista intacta: precio bajo la media de 200 y media de 50 por debajo de la de 200",
        f"El rebote ha llegado a la zona de la media de 50 y se ha frenado (a un {distancia_sma50:+.1f}%)",
        f"RSI en {rsi:.0f}: el rebote ha consumido su impulso sin llegar a sobrecompra",
    ]

    fuerza = 46.0
    fuerza += min(max(_num(u.get("adx14")) - 18, 0) * 0.7, 12)
    if _num(u.get("macd_hist")) < 0:
        fuerza += 6
        motivos.append("El MACD ya ha girado a la baja: el rebote pierde fuerza")

    bonus, motivos_fund = _bonus_fundamental(contexto, CORTO)
    fuerza += bonus
    motivos.extend(motivos_fund)

    return Senal(
        ticker="", estrategia="rebote_fallido", nombre_estrategia="Rebote agotado",
        direccion=CORTO, precio=cierre, atr=_num(u.get("atr14")),
        fuerza=_acotar(fuerza), motivos=motivos, fecha=df.index[indice],
        datos={"rsi": round(rsi, 1), "dist_sma50": round(distancia_sma50, 2)},
    )


# --------------------------------------------------------------------------
# Catálogo
# --------------------------------------------------------------------------

def _eval_pead(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Delega en modulos.pead.

    Vive en su propio módulo porque, a diferencia del resto, necesita un dato
    externo al OHLCV (el calendario de resultados) y su propia lógica de
    alineación temporal. El import es diferido para romper el ciclo: pead
    importa utilidades de este módulo.
    """
    from modulos.pead import evaluar_pead

    return evaluar_pead(df, contexto, indice)


def _eval_canslim(df: pd.DataFrame, contexto: dict[str, Any] | None = None, indice: int = -1) -> Senal | None:
    """Delega en modulos.canslim (import diferido para romper el ciclo)."""
    from modulos.canslim import evaluar_canslim_tecnico

    return evaluar_canslim_tecnico(df, contexto, indice)


ESTRATEGIAS: tuple[Estrategia, ...] = (
    Estrategia(
        id="ruptura_maximos",
        nombre="Ruptura de máximos",
        direccion=LARGO,
        resumen="Compra valores que superan su máximo de 55 sesiones con volumen, cerca de máximos anuales.",
        evidencia=(
            "Recoge el efecto momentum y el 'efecto máximo de 52 semanas': los valores cerca de "
            "máximos tienden a seguir subiendo porque no hay vendedores atrapados por encima."
        ),
        regimenes=(TENDENCIA_ALCISTA,),
        evaluar=_eval_ruptura_maximos,
        horizonte_dias=(10, 40),
        expectativa_fuera_muestra=-0.001,
        expectativa_medida=0.021,
        operaciones_medidas=866,
    ),
    Estrategia(
        id="pullback_tendencia",
        nombre="Retroceso en tendencia",
        direccion=LARGO,
        resumen="Compra el retroceso a la media rápida en un valor cuya tendencia alcista sigue intacta.",
        evidencia=(
            "Es el setup de continuación clásico: se entra en la pausa de una tendencia ya "
            "demostrada, con el stop apoyado en una referencia técnica cercana."
        ),
        regimenes=(TENDENCIA_ALCISTA, RANGO_ALCISTA),
        evaluar=_eval_pullback_tendencia,
        horizonte_dias=(5, 25),
        expectativa_fuera_muestra=0.152,
        expectativa_medida=0.1,
        operaciones_medidas=2908,
    ),
    Estrategia(
        id="reversion_rsi2",
        nombre="Reversión por sobreventa",
        direccion=LARGO,
        resumen="Compra sobreventa extrema de 2 sesiones, sólo en valores por encima de su media de 200.",
        evidencia=(
            "Estrategia de reversión a la media de horizonte muy corto: alta frecuencia de acierto "
            "y ganancias pequeñas. El filtro de media de 200 es lo que evita comprar caídas libres."
        ),
        regimenes=(RANGO_ALCISTA, PANICO, TENDENCIA_ALCISTA),
        evaluar=_eval_reversion_rsi2,
        horizonte_dias=(2, 10),
        expectativa_fuera_muestra=0.123,
        expectativa_medida=0.076,
        operaciones_medidas=1425,
    ),
    Estrategia(
        id="squeeze_disparo",
        nombre="Disparo de compresión",
        direccion=LARGO,
        resumen="Entra cuando una compresión de volatilidad se libera al alza con volumen.",
        evidencia=(
            "La volatilidad es cíclica: los periodos de contracción extrema tienden a resolverse "
            "en movimientos amplios. La compresión avisa del momento, no de la dirección."
        ),
        regimenes=(TENDENCIA_ALCISTA, RANGO_ALCISTA),
        evaluar=_eval_squeeze_disparo,
        horizonte_dias=(5, 25),
        expectativa_fuera_muestra=0.102,
        expectativa_medida=0.163,
        operaciones_medidas=192,
    ),
    Estrategia(
        id="ruptura_bajista",
        nombre="Ruptura bajista",
        direccion=CORTO,
        resumen="Corto sobre valores que pierden su mínimo de 55 sesiones con volumen y estructura bajista.",
        evidencia=(
            "El momentum también funciona a la baja, pero con un matiz: es asimétrico. Las caídas "
            "son más rápidas y violentas, y el riesgo de un rebote brusco es mayor que en los largos."
        ),
        regimenes=(CORRECCION, DISTRIBUCION),
        evaluar=_eval_ruptura_bajista,
        horizonte_dias=(5, 25),
        expectativa_fuera_muestra=-0.14,
        expectativa_medida=-0.201,
        operaciones_medidas=372,
    ),
    Estrategia(
        id="rebote_fallido",
        nombre="Rebote agotado",
        direccion=CORTO,
        resumen="Corto cuando un rebote se frena contra la media de 50 en una tendencia bajista.",
        evidencia=(
            "Entrar tras un rebote y no persiguiendo la caída permite un stop cercano por encima de "
            "la media, que es lo que hace viable el corto sin un riesgo desproporcionado."
        ),
        regimenes=(CORRECCION, DISTRIBUCION),
        evaluar=_eval_rebote_fallido,
        horizonte_dias=(5, 20),
        expectativa_fuera_muestra=-0.107,
        expectativa_medida=-0.14,
        operaciones_medidas=1644,
    ),
    Estrategia(
        id="pead",
        nombre="Deriva post-resultados",
        direccion=LARGO,
        resumen="Compra tras una sorpresa positiva en resultados que el mercado ha validado con subida.",
        evidencia=(
            "Post-Earnings Announcement Drift: el precio no incorpora de golpe una sorpresa en "
            "beneficios, sino que sigue derivando en esa dirección durante semanas. Documentada "
            "desde 1989 y superviviente de décadas de escrutinio académico, lo que la distingue "
            "de la mayoría de reglas técnicas."
        ),
        regimenes=(TENDENCIA_ALCISTA, RANGO_ALCISTA, DISTRIBUCION),
        evaluar=_eval_pead,
        horizonte_dias=(10, 60),
        expectativa_fuera_muestra=0.22,
        expectativa_medida=0.318,
        operaciones_medidas=321,
    ),
    Estrategia(
        id="canslim",
        nombre="Ruptura CAN SLIM",
        direccion=LARGO,
        resumen="Compra la ruptura del pivote de una base en un valor con fuerza relativa de líder.",
        evidencia=(
            "Parte técnica del sistema de William O'Neil (N, L y volumen). El screen completo midió "
            "un 24,4% anual entre 1998 y 2013 según AAII, pero su versión invertible (el ETF de la "
            "lista IBD 50) rindió un 5,77% anual a diez años frente al 13,47% del S&P 500. La cifra "
            "de aquí abajo es la medida sobre este universo, no la del estudio."
        ),
        regimenes=(TENDENCIA_ALCISTA, RANGO_ALCISTA),
        evaluar=_eval_canslim,
        horizonte_dias=(5, 40),
        expectativa_medida=0.088,
        operaciones_medidas=417,
        expectativa_fuera_muestra=0.133,
    ),
)

ESTRATEGIAS_POR_ID = {e.id: e for e in ESTRATEGIAS}


def evaluar_todas(
    df: pd.DataFrame,
    ticker: str,
    *,
    contexto_fundamental: dict[str, Any] | None = None,
    ids: tuple[str, ...] | None = None,
    indice: int = -1,
) -> list[Senal]:
    """Evalúa el catálogo completo sobre un valor y devuelve las señales activas."""
    señales: list[Senal] = []
    for estrategia in ESTRATEGIAS:
        if ids and estrategia.id not in ids:
            continue
        try:
            señal = estrategia.evaluar(df, contexto_fundamental, indice)
        except Exception:
            # Una estrategia con un dato raro no puede tumbar el escaneo entero.
            continue
        if señal is not None:
            señal.ticker = ticker
            señal.nombre_estrategia = estrategia.nombre
            señales.append(señal)
    return señales
