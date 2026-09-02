"""Validación histórica de las estrategias de swing.

Por qué no se puede prescindir de esto
--------------------------------------
Cualquier conjunto de reglas técnicas *parece* razonable al leerlo. Sin una
validación histórica no hay forma de distinguir una estrategia con ventaja real
de una que sólo suena bien, y publicar señales sin esa cifra sería vender humo.

Reglas de honestidad que aplica este backtest
---------------------------------------------
1. **Sin look-ahead.** Los indicadores de ``modulos.indicadores`` son todos
   causales (medias móviles, suavizados exponenciales, y el canal de Donchian
   con ``shift(1)``): el valor de la fila T sólo usa datos hasta T. Por eso se
   pueden calcular una vez sobre todo el histórico y evaluar fila a fila sin
   contaminar el pasado con el futuro.
2. **Entrada realista.** Se entra en la APERTURA del día siguiente a la señal,
   no en el cierre que la generó. Ese cierre no se conoce hasta que el mercado
   ha cerrado, así que operarlo sería imposible en la práctica y mejoraría los
   resultados de forma artificial.
3. **Salidas intradía.** Stop y objetivo se comprueban contra el máximo y el
   mínimo de cada sesión, no contra el cierre.
4. **Si stop y objetivo caen el mismo día, gana el stop.** Sin datos intradía no
   se sabe cuál se tocó primero; asumir lo contrario sería inflar el resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from modulos.indicadores import enriquecer_ohlcv
from modulos.swing_estrategias import ESTRATEGIAS_POR_ID, Estrategia
from modulos.swing_riesgo import MULTIPLO_ATR_STOP, expectativa_sistema

# Múltiplo de R al que se cierra la posición ganadora.
OBJETIVO_R = 2.0

# Sesiones mínimas antes de empezar a evaluar: las medias de 200 necesitan
# rodaje, y evaluar antes generaría señales con indicadores a medio formar.
CALENTAMIENTO = 210


@dataclass
class Operacion:
    ticker: str
    estrategia: str
    fecha_señal: Any
    fecha_entrada: Any
    entrada: float
    stop: float
    objetivo: float
    fecha_salida: Any
    salida: float
    motivo_salida: str
    resultado_r: float
    dias: int
    direccion: str


@dataclass
class ResultadoBacktest:
    estrategia: str
    nombre: str
    operaciones: list[Operacion] = field(default_factory=list)
    tickers_evaluados: int = 0

    @property
    def total(self) -> int:
        return len(self.operaciones)

    @property
    def metricas(self) -> dict[str, Any]:
        if not self.operaciones:
            return {
                "operaciones": 0, "acierto_pct": None, "r_medio": None,
                "expectativa_r": None, "factor_beneficio": None,
                "r_medio_ganador": None, "r_medio_perdedor": None,
                "dias_medios": None, "mejor_r": None, "peor_r": None,
            }

        erres = np.array([op.resultado_r for op in self.operaciones], dtype=float)
        ganadoras = erres[erres > 0]
        perdedoras = erres[erres <= 0]

        beneficio = float(ganadoras.sum()) if ganadoras.size else 0.0
        perdida = float(abs(perdedoras.sum())) if perdedoras.size else 0.0

        acierto = len(ganadoras) / len(erres) * 100.0
        r_ganador = float(ganadoras.mean()) if ganadoras.size else 0.0
        r_perdedor = float(abs(perdedoras.mean())) if perdedoras.size else 1.0

        return {
            "operaciones": int(len(erres)),
            "acierto_pct": round(acierto, 1),
            "r_medio": round(float(erres.mean()), 3),
            "expectativa_r": expectativa_sistema(acierto, r_ganador, r_perdedor),
            "factor_beneficio": round(beneficio / perdida, 2) if perdida > 0 else None,
            "r_medio_ganador": round(r_ganador, 2),
            "r_medio_perdedor": round(r_perdedor, 2),
            "dias_medios": round(float(np.mean([op.dias for op in self.operaciones])), 1),
            "mejor_r": round(float(erres.max()), 2),
            "peor_r": round(float(erres.min()), 2),
        }

    def a_dataframe(self) -> pd.DataFrame:
        if not self.operaciones:
            return pd.DataFrame()
        return pd.DataFrame([op.__dict__ for op in self.operaciones])


def _simular_operacion(
    df: pd.DataFrame,
    indice_señal: int,
    estrategia: Estrategia,
    atr_señal: float,
    direccion: str,
) -> Operacion | None:
    """Simula una operación desde la señal hasta su salida."""
    if indice_señal + 1 >= len(df) or atr_señal <= 0:
        return None

    entrada_idx = indice_señal + 1
    entrada = float(df["Open"].iloc[entrada_idx])
    if not np.isfinite(entrada) or entrada <= 0:
        return None

    riesgo = MULTIPLO_ATR_STOP * atr_señal
    es_largo = direccion == "largo"
    stop = entrada - riesgo if es_largo else entrada + riesgo
    objetivo = entrada + OBJETIVO_R * riesgo if es_largo else entrada - OBJETIVO_R * riesgo

    max_dias = estrategia.horizonte_dias[1]
    fin = min(entrada_idx + max_dias, len(df) - 1)

    for i in range(entrada_idx, fin + 1):
        alto = float(df["High"].iloc[i])
        bajo = float(df["Low"].iloc[i])

        if es_largo:
            toca_stop = bajo <= stop
            toca_objetivo = alto >= objetivo
        else:
            toca_stop = alto >= stop
            toca_objetivo = bajo <= objetivo

        # El stop tiene prioridad: sin datos intradía no se sabe el orden real,
        # y suponer lo contrario inflaría artificialmente los resultados.
        if toca_stop:
            return Operacion(
                ticker="", estrategia=estrategia.id, fecha_señal=df.index[indice_señal],
                fecha_entrada=df.index[entrada_idx], entrada=round(entrada, 4),
                stop=round(stop, 4), objetivo=round(objetivo, 4),
                fecha_salida=df.index[i], salida=round(stop, 4),
                motivo_salida="stop", resultado_r=-1.0,
                dias=i - entrada_idx, direccion=direccion,
            )
        if toca_objetivo:
            return Operacion(
                ticker="", estrategia=estrategia.id, fecha_señal=df.index[indice_señal],
                fecha_entrada=df.index[entrada_idx], entrada=round(entrada, 4),
                stop=round(stop, 4), objetivo=round(objetivo, 4),
                fecha_salida=df.index[i], salida=round(objetivo, 4),
                motivo_salida="objetivo", resultado_r=OBJETIVO_R,
                dias=i - entrada_idx, direccion=direccion,
            )

    # Se agota el horizonte: se cierra a mercado y se mide el R obtenido.
    salida = float(df["Close"].iloc[fin])
    movimiento = (salida - entrada) if es_largo else (entrada - salida)
    return Operacion(
        ticker="", estrategia=estrategia.id, fecha_señal=df.index[indice_señal],
        fecha_entrada=df.index[entrada_idx], entrada=round(entrada, 4),
        stop=round(stop, 4), objetivo=round(objetivo, 4),
        fecha_salida=df.index[fin], salida=round(salida, 4),
        motivo_salida="horizonte", resultado_r=round(movimiento / riesgo, 3),
        dias=fin - entrada_idx, direccion=direccion,
    )


def backtest_estrategia(
    estrategia_id: str,
    precios: dict[str, pd.DataFrame],
    *,
    separacion_minima_dias: int = 5,
    desde: pd.Timestamp | None = None,
    hasta: pd.Timestamp | None = None,
    enriquecer_extra: Any = None,
) -> ResultadoBacktest:
    """Recorre el histórico de cada valor buscando señales y simulando el trade.

    ``separacion_minima_dias`` evita contar como operaciones distintas la misma
    señal repetida en sesiones consecutivas (un retroceso puede cumplir las
    condiciones cuatro días seguidos y no son cuatro oportunidades: es una).

    ``desde``/``hasta`` acotan las FECHAS DE SEÑAL, no los datos: los indicadores
    se siguen calculando sobre todo el histórico disponible, porque una media de
    200 sesiones necesita 200 sesiones previas exista o no el recorte. Lo que se
    filtra es en qué ventana se permite abrir operaciones, que es lo que hace
    posible separar el periodo de diseño del de prueba.

    ``enriquecer_extra`` es un gancho ``(ticker, df) -> df`` que se aplica
    después de los indicadores. Existe para estrategias que necesitan datos
    ajenos al OHLCV -- hoy sólo el PEAD, que requiere el calendario histórico de
    resultados -- sin obligar al resto a pagar ese coste de red.
    """
    estrategia = ESTRATEGIAS_POR_ID.get(estrategia_id)
    resultado = ResultadoBacktest(estrategia=estrategia_id, nombre=estrategia.nombre if estrategia else estrategia_id)
    if estrategia is None:
        return resultado

    for ticker, ohlcv in precios.items():
        if ohlcv is None or len(ohlcv) < CALENTAMIENTO + 20:
            continue

        try:
            enriquecido = enriquecer_ohlcv(ohlcv)
            if enriquecer_extra is not None and not enriquecido.empty:
                enriquecido = enriquecer_extra(ticker, enriquecido)
        except Exception:
            continue
        if enriquecido is None or enriquecido.empty or len(enriquecido) < CALENTAMIENTO + 20:
            continue

        resultado.tickers_evaluados += 1
        ultima_señal = -10**6

        indice = enriquecido.index
        for i in range(CALENTAMIENTO, len(enriquecido) - 1):
            if i - ultima_señal < separacion_minima_dias:
                continue

            if desde is not None or hasta is not None:
                fecha = indice[i]
                if desde is not None and fecha < desde:
                    continue
                if hasta is not None and fecha > hasta:
                    break  # el índice es creciente: a partir de aquí ya no entra nada

            # Se evalúa la fila i directamente. No hace falta recortar el
            # histórico para evitar look-ahead: todos los indicadores son
            # causales, así que la fila i sólo contiene información hasta i.
            # Recortar sí costaba una copia por iteración, es decir O(n^2).
            try:
                señal = estrategia.evaluar(enriquecido, None, i)
            except Exception:
                continue
            if señal is None:
                continue

            operacion = _simular_operacion(
                enriquecido, i, estrategia, señal.atr, estrategia.direccion
            )
            if operacion is None:
                continue
            operacion.ticker = ticker
            resultado.operaciones.append(operacion)
            ultima_señal = i

    return resultado


def backtest_todas(
    precios: dict[str, pd.DataFrame],
    estrategias: tuple[str, ...] | None = None,
) -> dict[str, ResultadoBacktest]:
    ids = estrategias or tuple(ESTRATEGIAS_POR_ID.keys())
    return {eid: backtest_estrategia(eid, precios) for eid in ids}


def tabla_resumen(resultados: dict[str, ResultadoBacktest]) -> pd.DataFrame:
    """Comparativa de todas las estrategias, ordenada por expectativa."""
    filas = []
    for res in resultados.values():
        m = res.metricas
        estrategia = ESTRATEGIAS_POR_ID.get(res.estrategia)
        filas.append(
            {
                "Estrategia": res.nombre,
                "Dirección": "Largo" if estrategia and estrategia.direccion == "largo" else "Corto",
                "Operaciones": m["operaciones"],
                "Acierto %": m["acierto_pct"],
                "Expectativa (R)": m["expectativa_r"],
                "R medio": m["r_medio"],
                "Factor beneficio": m["factor_beneficio"],
                "Días medios": m["dias_medios"],
                "_id": res.estrategia,
            }
        )
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values("Expectativa (R)", ascending=False, na_position="last").reset_index(drop=True)


# --------------------------------------------------------------------------
# Análisis por régimen de mercado
# --------------------------------------------------------------------------
#
# Esta es la comprobación que valida (o desmonta) la tesis central del módulo:
# si una estrategia sólo debe operarse en su régimen, entonces sus resultados
# dentro y fuera de él tienen que ser claramente distintos. Si no lo son, el
# filtro de régimen es decoración y hay que quitarlo.


def _estado_mercado_historico(spy: pd.Series) -> pd.Series:
    """Serie histórica alcista/bajista del índice según su media de 200.

    Es una versión simplificada de ``modulos.swing_regimen`` (sólo la tendencia
    del índice, sin amplitud ni VIX) porque reconstruir la amplitud histórica
    exigiría el universo completo en cada fecha del pasado. Para separar
    mercado alcista de bajista, que es lo que se quiere medir aquí, basta.
    """
    from modulos.indicadores import sma

    media = sma(spy, 200)
    return pd.Series(
        np.where(spy > media, "alcista", "bajista"),
        index=spy.index,
        name="mercado",
    )


def analizar_por_regimen(
    resultados: dict[str, ResultadoBacktest],
    spy_close: pd.Series,
) -> pd.DataFrame:
    """Desglosa el rendimiento de cada estrategia según el estado del mercado."""
    estado = _estado_mercado_historico(spy_close)
    if estado.empty:
        return pd.DataFrame()

    # Normaliza zonas horarias: los índices de yfinance pueden venir con tz.
    estado.index = pd.to_datetime(estado.index).tz_localize(None)

    filas = []
    for res in resultados.values():
        if not res.operaciones:
            continue
        estrategia = ESTRATEGIAS_POR_ID.get(res.estrategia)

        for op in res.operaciones:
            fecha = pd.to_datetime(op.fecha_entrada)
            if getattr(fecha, "tz", None) is not None:
                fecha = fecha.tz_localize(None)
            previas = estado.index[estado.index <= fecha]
            if len(previas) == 0:
                continue
            filas.append(
                {
                    "Estrategia": res.nombre,
                    "Dirección": "Largo" if estrategia and estrategia.direccion == "largo" else "Corto",
                    "Mercado": estado.loc[previas[-1]],
                    "R": op.resultado_r,
                }
            )

    if not filas:
        return pd.DataFrame()

    detalle = pd.DataFrame(filas)
    resumen = (
        detalle.groupby(["Estrategia", "Dirección", "Mercado"])
        .agg(
            Operaciones=("R", "size"),
            Expectativa_R=("R", "mean"),
            Acierto_pct=("R", lambda s: (s > 0).mean() * 100.0),
        )
        .reset_index()
    )
    resumen["Expectativa_R"] = resumen["Expectativa_R"].round(3)
    resumen["Acierto_pct"] = resumen["Acierto_pct"].round(1)
    return resumen.rename(columns={"Expectativa_R": "Expectativa (R)", "Acierto_pct": "Acierto %"})


# --------------------------------------------------------------------------
# Validación out-of-sample
# --------------------------------------------------------------------------
#
# El backtest de arriba es in-sample: las reglas se escribieron conociendo estos
# años, así que una parte de su rendimiento es inevitablemente ajuste a lo que ya
# había pasado. La única forma de estimar cuánto es partir el histórico en dos y
# medir en el tramo que "no se conocía": si la ventaja desaparece ahí, la regla
# describía el pasado en vez de capturar un comportamiento estable.
#
# No es una prueba definitiva -- las reglas ya existían cuando se hizo el corte,
# así que sigue habiendo contaminación por el conocimiento general del periodo --
# pero distingue lo que se degrada un poco de lo que se derrumba.

# Proporción del histórico que se reserva para diseñar. El resto es la prueba.
CORTE_DISENO = 0.6

# Por debajo de esto la muestra no dice nada y el veredicto sería ruido.
MINIMO_OPERACIONES_VEREDICTO = 30

SOBREVIVE = "sobrevive"
SE_DEGRADA = "se_degrada"
NO_SOBREVIVE = "no_sobrevive"
MUESTRA_INSUFICIENTE = "muestra_insuficiente"

ETIQUETAS_VEREDICTO = {
    SOBREVIVE: "Se mantiene fuera de muestra",
    SE_DEGRADA: "Se degrada fuera de muestra",
    NO_SOBREVIVE: "No sobrevive fuera de muestra",
    MUESTRA_INSUFICIENTE: "Muestra insuficiente para juzgar",
}


@dataclass
class ResultadoOutOfSample:
    """Comparativa entre el periodo de diseño y el de prueba."""

    estrategia: str
    nombre: str
    fecha_corte: Any
    metricas_diseno: dict[str, Any] = field(default_factory=dict)
    metricas_prueba: dict[str, Any] = field(default_factory=dict)
    veredicto: str = MUESTRA_INSUFICIENTE

    @property
    def expectativa_diseno(self) -> float | None:
        return self.metricas_diseno.get("expectativa_r")

    @property
    def expectativa_prueba(self) -> float | None:
        return self.metricas_prueba.get("expectativa_r")

    @property
    def retencion_pct(self) -> float | None:
        """Qué porcentaje de la ventaja del diseño se conserva en la prueba.

        Sólo tiene sentido cuando el diseño era positivo: retener el 80% de una
        expectativa negativa no es una buena noticia.
        """
        ins, oos = self.expectativa_diseno, self.expectativa_prueba
        if ins is None or oos is None or ins <= 0:
            return None
        return round(oos / ins * 100.0, 1)

    @property
    def etiqueta_veredicto(self) -> str:
        return ETIQUETAS_VEREDICTO.get(self.veredicto, self.veredicto)


def _fecha_de_corte(precios: dict[str, pd.DataFrame], corte: float) -> pd.Timestamp | None:
    """Fecha que separa diseño de prueba, común a todos los valores.

    Se usa una única fecha para todo el universo (y no un corte por valor) para
    que ambos periodos correspondan al mismo contexto de mercado: si cada acción
    tuviera su propio corte, el tramo de prueba mezclaría 2022 de unas con 2025
    de otras y la comparación no significaría nada.
    """
    fechas: list[pd.Timestamp] = []
    for df in precios.values():
        if df is None or df.empty:
            continue
        try:
            fechas.append(pd.to_datetime(df.index[0]))
            fechas.append(pd.to_datetime(df.index[-1]))
        except Exception:
            continue

    if not fechas:
        return None

    inicio, fin = min(fechas), max(fechas)
    if pd.isna(inicio) or pd.isna(fin) or fin <= inicio:
        return None

    return inicio + (fin - inicio) * corte


def _dictaminar(diseno: dict[str, Any], prueba: dict[str, Any]) -> str:
    """Traduce las dos expectativas a un veredicto legible."""
    n_diseno = diseno.get("operaciones", 0)
    n_prueba = prueba.get("operaciones", 0)
    if n_diseno < MINIMO_OPERACIONES_VEREDICTO or n_prueba < MINIMO_OPERACIONES_VEREDICTO:
        return MUESTRA_INSUFICIENTE

    exp_diseno = diseno.get("expectativa_r")
    exp_prueba = prueba.get("expectativa_r")
    if exp_diseno is None or exp_prueba is None:
        return MUESTRA_INSUFICIENTE

    # Una regla que ya era mala en su propio periodo de diseño no tiene nada que
    # sobrevivir: no se la premia por seguir siendo mala de forma consistente.
    if exp_diseno <= 0:
        return NO_SOBREVIVE

    if exp_prueba <= 0:
        return NO_SOBREVIVE
    if exp_prueba >= exp_diseno * 0.5:
        return SOBREVIVE
    return SE_DEGRADA


def validar_out_of_sample(
    estrategia_id: str,
    precios: dict[str, pd.DataFrame],
    *,
    corte: float = CORTE_DISENO,
    enriquecer_extra: Any = None,
) -> ResultadoOutOfSample:
    """Compara el rendimiento de una estrategia dentro y fuera de muestra."""
    estrategia = ESTRATEGIAS_POR_ID.get(estrategia_id)
    nombre = estrategia.nombre if estrategia else estrategia_id
    fecha_corte = _fecha_de_corte(precios, corte)

    resultado = ResultadoOutOfSample(estrategia=estrategia_id, nombre=nombre, fecha_corte=fecha_corte)
    if fecha_corte is None or estrategia is None:
        return resultado

    diseno = backtest_estrategia(estrategia_id, precios, hasta=fecha_corte, enriquecer_extra=enriquecer_extra)
    prueba = backtest_estrategia(estrategia_id, precios, desde=fecha_corte, enriquecer_extra=enriquecer_extra)

    resultado.metricas_diseno = diseno.metricas
    resultado.metricas_prueba = prueba.metricas
    resultado.veredicto = _dictaminar(resultado.metricas_diseno, resultado.metricas_prueba)
    return resultado


def tabla_out_of_sample(resultados: list[ResultadoOutOfSample]) -> pd.DataFrame:
    """Comparativa diseño vs prueba de todas las estrategias."""
    filas = []
    for res in resultados:
        filas.append(
            {
                "Estrategia": res.nombre,
                "Ops diseño": res.metricas_diseno.get("operaciones", 0),
                "Expectativa diseño (R)": res.expectativa_diseno,
                "Ops prueba": res.metricas_prueba.get("operaciones", 0),
                "Expectativa prueba (R)": res.expectativa_prueba,
                "Ventaja retenida %": res.retencion_pct,
                "Veredicto": res.etiqueta_veredicto,
                "_codigo": res.veredicto,
            }
        )
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    return df.sort_values("Expectativa prueba (R)", ascending=False, na_position="last").reset_index(drop=True)
