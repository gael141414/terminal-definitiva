"""Watchlist como embudo de decisión: estados, posiciones reales y alertas técnicas.

El problema que resuelve
------------------------
Una watchlist plana mezcla cosas que no se parecen en nada: una empresa que
acabas de descubrir, otra que ya has analizado y esperas a que caiga de precio,
y una tercera que ya tienes comprada. Todas ocupan la misma fila y compiten por
la misma atención, así que en la práctica se acaba mirando siempre las mismas
cuatro y las demás se pudren en la lista.

Aquí se modela lo que realmente es: un embudo con fases, donde cada fase tiene
una pregunta pendiente distinta y una acción siguiente distinta.

Además incorpora dos cosas que faltaban:

- **Posiciones reales.** Distinguir "la vigilo" de "la tengo comprada a 142,30
  con stop en 131" permite calcular el resultado abierto en R y saber si una
  posición ya ha roto su tesis.
- **Alertas técnicas.** Hasta ahora sólo se podía vigilar un precio fijo. Pero
  las decisiones no siempre son de precio: "avísame si pierde la media de 200"
  o "si el RSI entra en sobreventa" son condiciones igual de operativas, y ahora
  que existe ``modulos.indicadores`` se pueden evaluar sin coste añadido.

Todo el módulo es lógica pura y testable: no dibuja nada ni descarga nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from modulos.indicadores import enriquecer_ohlcv

# --------------------------------------------------------------------------
# Estados del embudo
# --------------------------------------------------------------------------

INVESTIGANDO = "investigando"
ESPERANDO_PRECIO = "esperando_precio"
LISTA_PARA_COMPRAR = "lista_para_comprar"
EN_CARTERA = "en_cartera"
ARCHIVADA = "archivada"

ESTADOS = (INVESTIGANDO, ESPERANDO_PRECIO, LISTA_PARA_COMPRAR, EN_CARTERA, ARCHIVADA)

# Cada estado declara la pregunta que tiene pendiente. Es lo que convierte la
# lista en algo accionable: al abrirla sabes qué te toca hacer en cada nombre.
META_ESTADOS: dict[str, dict[str, str]] = {
    INVESTIGANDO: {
        "etiqueta": "🔍 Investigando",
        "pregunta": "¿Es un buen negocio? Falta completar el análisis fundamental.",
        "siguiente": "Analizar en Research Core",
    },
    ESPERANDO_PRECIO: {
        "etiqueta": "⏳ Esperando precio",
        "pregunta": "El negocio convence, el precio no. ¿A qué precio sí?",
        "siguiente": "Fijar precio objetivo de compra",
    },
    LISTA_PARA_COMPRAR: {
        "etiqueta": "✅ Lista para comprar",
        "pregunta": "Precio y tesis alineados. ¿Cuánto compro y dónde va el stop?",
        "siguiente": "Dimensionar la posición",
    },
    EN_CARTERA: {
        "etiqueta": "📈 En cartera",
        "pregunta": "¿Sigue vigente la tesis? ¿Hay que mover el stop?",
        "siguiente": "Revisar tesis y stop",
    },
    ARCHIVADA: {
        "etiqueta": "🗄️ Archivada",
        "pregunta": "Descartada. Se conserva para aprender del criterio pasado.",
        "siguiente": "Nada pendiente",
    },
}

ORDEN_ESTADOS = {estado: i for i, estado in enumerate(ESTADOS)}


def normalizar_estado(valor: Any) -> str:
    """Estado válido a partir de un dato de disco, con retrocompatibilidad.

    Las fichas guardadas antes de existir los estados no tienen el campo: se
    infieren a partir de lo que sí tienen (una posición abierta o un objetivo
    de compra) en vez de mandarlas todas al mismo cajón.
    """
    texto = str(valor or "").strip().lower()
    return texto if texto in ESTADOS else INVESTIGANDO


def inferir_estado(item: dict[str, Any]) -> str:
    """Deduce el estado de una ficha antigua sin campo ``estado``."""
    if isinstance(item.get("posicion"), dict) and item["posicion"].get("acciones"):
        return EN_CARTERA
    try:
        if float(item.get("target") or 0) > 0:
            return ESPERANDO_PRECIO
    except (TypeError, ValueError):
        pass
    return INVESTIGANDO


# --------------------------------------------------------------------------
# Posiciones abiertas
# --------------------------------------------------------------------------


@dataclass
class ResultadoPosicion:
    """Estado vivo de una posición abierta."""

    acciones: int
    entrada: float
    stop: float | None
    precio_actual: float
    valor_actual: float
    coste: float
    pnl_euros: float
    pnl_pct: float
    resultado_r: float | None
    stop_roto: bool

    @property
    def en_ganancia(self) -> bool:
        return self.pnl_euros > 0


def evaluar_posicion(posicion: dict[str, Any], precio_actual: float) -> ResultadoPosicion | None:
    """Calcula el estado vivo de una posición.

    El resultado en R es lo relevante, no el porcentaje: un +6% puede ser un
    éxito rotundo o irrelevante según lo que se arriesgó para conseguirlo. Sin
    stop registrado no hay R posible, y se devuelve ``None`` en ese campo en vez
    de inventarse una referencia.
    """
    if not isinstance(posicion, dict):
        return None

    try:
        acciones = int(posicion.get("acciones") or 0)
        entrada = float(posicion.get("entrada") or 0.0)
    except (TypeError, ValueError):
        return None

    if acciones <= 0 or entrada <= 0 or not precio_actual or precio_actual <= 0:
        return None

    try:
        stop = float(posicion.get("stop")) if posicion.get("stop") else None
    except (TypeError, ValueError):
        stop = None

    coste = acciones * entrada
    valor = acciones * precio_actual
    pnl = valor - coste

    resultado_r = None
    stop_roto = False
    if stop and stop > 0 and stop != entrada:
        riesgo_accion = abs(entrada - stop)
        resultado_r = round((precio_actual - entrada) / riesgo_accion, 2)
        stop_roto = precio_actual <= stop if stop < entrada else precio_actual >= stop

    return ResultadoPosicion(
        acciones=acciones,
        entrada=round(entrada, 4),
        stop=stop,
        precio_actual=round(precio_actual, 4),
        valor_actual=round(valor, 2),
        coste=round(coste, 2),
        pnl_euros=round(pnl, 2),
        pnl_pct=round(pnl / coste * 100.0, 2) if coste else 0.0,
        resultado_r=resultado_r,
        stop_roto=stop_roto,
    )


# --------------------------------------------------------------------------
# Alertas técnicas
# --------------------------------------------------------------------------


@dataclass
class AlertaTecnica:
    id: str
    etiqueta: str
    descripcion: str
    condicion: Callable[[pd.Series, pd.Series], bool]
    # Sesiones mínimas para que el indicador subyacente signifique algo. El
    # suavizado exponencial del RSI no exige un mínimo de periodos, así que con
    # cinco velas ya devuelve un número perfectamente creíble y perfectamente
    # inútil: sin este umbral, cualquier salida a bolsa reciente dispararía
    # alertas falsas nada más añadirla a la watchlist.
    minimo_sesiones: int = 60


def _c(nombre: str, u: pd.Series, defecto: float = float("nan")) -> float:
    valor = u.get(nombre, defecto)
    try:
        return float(valor)
    except (TypeError, ValueError):
        return float("nan")


def _cruce_alcista_sma50(u: pd.Series, p: pd.Series) -> bool:
    return _c("Close", p) <= _c("sma50", p) and _c("Close", u) > _c("sma50", u)


def _perdida_sma200(u: pd.Series, p: pd.Series) -> bool:
    return _c("Close", p) >= _c("sma200", p) and _c("Close", u) < _c("sma200", u)


def _sobreventa(u: pd.Series, _p: pd.Series) -> bool:
    return _c("rsi14", u) < 30

def _sobrecompra(u: pd.Series, _p: pd.Series) -> bool:
    return _c("rsi14", u) > 70


def _nuevo_maximo_52s(u: pd.Series, _p: pd.Series) -> bool:
    return _c("dist_max52", u) > -0.5


def _volumen_inusual(u: pd.Series, _p: pd.Series) -> bool:
    return _c("vol_rel", u) >= 2.0


def _compresion_volatilidad(u: pd.Series, _p: pd.Series) -> bool:
    return bool(u.get("squeeze", False))


ALERTAS_TECNICAS: tuple[AlertaTecnica, ...] = (
    AlertaTecnica("cruce_sma50", "Cruza al alza la media de 50",
                  "El precio recupera su media de 50 sesiones: suele marcar el fin de una corrección.",
                  _cruce_alcista_sma50, minimo_sesiones=60),
    AlertaTecnica("perdida_sma200", "Pierde la media de 200",
                  "El precio pierde su referencia de tendencia de largo plazo.",
                  _perdida_sma200, minimo_sesiones=210),
    AlertaTecnica("sobreventa", "RSI en sobreventa (<30)",
                  "Caída acelerada: zona donde suelen aparecer rebotes técnicos.",
                  _sobreventa, minimo_sesiones=40),
    AlertaTecnica("sobrecompra", "RSI en sobrecompra (>70)",
                  "Subida acelerada: zona de posible agotamiento o toma de beneficios.",
                  _sobrecompra, minimo_sesiones=40),
    AlertaTecnica("maximo_52s", "Nuevo máximo de 52 semanas",
                  "Rompe su techo anual: no quedan vendedores atrapados por encima.",
                  _nuevo_maximo_52s, minimo_sesiones=210),
    AlertaTecnica("volumen_inusual", "Volumen inusual (2x)",
                  "El volumen dobla su media: algo ha pasado, conviene mirar la noticia.",
                  _volumen_inusual, minimo_sesiones=30),
    AlertaTecnica("compresion", "Compresión de volatilidad",
                  "Volatilidad contraída: suele preceder a un movimiento amplio.",
                  _compresion_volatilidad, minimo_sesiones=40),
)

ALERTAS_POR_ID = {a.id: a for a in ALERTAS_TECNICAS}


def evaluar_alertas_tecnicas(ohlcv: pd.DataFrame, ids_activas: list[str] | None) -> list[dict[str, str]]:
    """Devuelve las alertas técnicas que se cumplen hoy para un valor."""
    if not ids_activas or ohlcv is None or ohlcv.empty:
        return []

    try:
        enriquecido = enriquecer_ohlcv(ohlcv)
    except Exception:
        return []
    if enriquecido.empty or len(enriquecido) < 2:
        return []

    ultimo, previo = enriquecido.iloc[-1], enriquecido.iloc[-2]
    disparadas: list[dict[str, str]] = []

    disponibles = len(enriquecido)
    for alerta_id in ids_activas:
        alerta = ALERTAS_POR_ID.get(alerta_id)
        if alerta is None:
            continue
        if disponibles < alerta.minimo_sesiones:
            continue
        try:
            if alerta.condicion(ultimo, previo):
                disparadas.append({"id": alerta.id, "etiqueta": alerta.etiqueta, "descripcion": alerta.descripcion})
        except Exception:
            continue

    return disparadas


# --------------------------------------------------------------------------
# Vista agregada del embudo
# --------------------------------------------------------------------------


def resumen_embudo(db: dict[str, Any]) -> dict[str, int]:
    """Cuántos valores hay en cada fase."""
    conteo = {estado: 0 for estado in ESTADOS}
    for item in db.values():
        if not isinstance(item, dict):
            continue
        estado = normalizar_estado(item.get("estado")) if item.get("estado") else inferir_estado(item)
        conteo[estado] = conteo.get(estado, 0) + 1
    return conteo


def ordenar_por_embudo(tickers_items: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    """Ordena por fase del embudo: primero lo que está más cerca de decidirse.

    Se invierte el orden natural de los estados a propósito: lo que ya está en
    cartera o listo para comprar exige atención antes que una idea que aún está
    en fase de investigación.
    """
    def clave(par: tuple[str, dict[str, Any]]) -> tuple[int, str]:
        _ticker, item = par
        estado = normalizar_estado(item.get("estado")) if item.get("estado") else inferir_estado(item)
        prioridad = {
            EN_CARTERA: 0,
            LISTA_PARA_COMPRAR: 1,
            ESPERANDO_PRECIO: 2,
            INVESTIGANDO: 3,
            ARCHIVADA: 4,
        }.get(estado, 5)
        return prioridad, par[0]

    return sorted(tickers_items, key=clave)
