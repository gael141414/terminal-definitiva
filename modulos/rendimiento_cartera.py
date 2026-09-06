"""Rendimiento real de una cartera frente a un benchmark de flujos igualados.

La pregunta que responde: ¿mi selección de valores bate a haber metido *el mismo
dinero en los mismos momentos* en un índice? Comparar la rentabilidad de una
cartera contra la del índice desde su inicio no responde a eso — premia o castiga
según cuándo se aportó dinero. El benchmark money-weighted elimina ese factor:
por cada compra de X € en la fecha D, se compran X € del índice en esa misma
fecha D.

Los cuatro sitios donde estas herramientas fallan en silencio
--------------------------------------------------------------
1. **Convención de precio.** Comparar precio pelado (sin dividendos) contra un
   índice de retorno total regala varios puntos al índice cada año. Aquí ambos
   lados usan ``auto_adjust=True`` y los proxies son ETF de ACUMULACIÓN, así que
   la simetría queda cerrada por construcción, no por disciplina.
2. **Dirección del cambio de divisa.** ``EURUSD=X`` cotiza dólares por euro
   (~1,16). Multiplicar en vez de dividir infla cada posición estadounidense un
   35%, y como el benchmark en EUR no lleva FX, el sesgo cae entero del lado de
   la cartera. Ver ``tipo_de_cambio_a_eur``.
3. **Métricas de riesgo sobre la serie equivocada.** Una aportación de 800 € a
   una cartera de 500 € parece un +160% diario. Volatilidad, Sharpe y drawdown
   se calculan SIEMPRE sobre la serie unitizada (TWR), nunca sobre la de valor.
4. **Fechas no bursátiles.** Se desplazan al siguiente día hábil y queda
   registrado en ``avisos``; silenciarlo escondería compras mal fechadas.

Datos ausentes: se degrada con transparencia. Nunca se inventa un precio ni se
sustituye por un centinela numérico.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Literal, Sequence

import numpy as np
import pandas as pd

from modulos.config import (
    MONEDA_BASE, PARES_FX, PESOS_BENCHMARK_DEFECTO, PROXIES_INDICE,
    TOLERANCIA_RECONSTRUCCION_EUR,
)

LOGGER = logging.getLogger("valuequant.rendimiento_cartera")

__all__ = [
    "Transaccion", "Posicion", "AtribucionPosicion", "RendimientoCartera",
    "calcular_rendimiento", "construir_series", "xirr", "serie_unitizada",
    "tipo_de_cambio_a_eur", "siguiente_dia_habil", "validar_pesos",
    "COMPRA", "VENTA",
]

COMPRA = "compra"
VENTA = "venta"

SESIONES_ANIO = 252


# ==========================================================================
# ENTRADA
# ==========================================================================


@dataclass(slots=True)
class Transaccion:
    """Un movimiento de la cartera. El caso base son solo compras."""

    ticker: str
    importe_eur: float
    fecha: date
    tipo: Literal["compra", "venta"] = COMPRA

    def __post_init__(self) -> None:
        self.ticker = str(self.ticker).strip().upper()
        if isinstance(self.fecha, str):
            self.fecha = pd.Timestamp(self.fecha).date()
        if isinstance(self.fecha, (pd.Timestamp, datetime)):
            self.fecha = self.fecha.date()

    @property
    def signo(self) -> int:
        return 1 if self.tipo == COMPRA else -1


def validar_pesos(pesos: dict[str, float]) -> None:
    """Los pesos deben sumar 1. Un 0,9 silencioso compararía contra un
    benchmark que solo invierte el 90% del dinero, y la cartera ganaría
    'gratis' un 10%."""
    if not pesos:
        raise ValueError("No se han indicado índices para el benchmark.")
    for nombre, peso in pesos.items():
        if not isinstance(peso, (int, float)) or not np.isfinite(peso) or peso < 0:
            raise ValueError(f"Peso no válido para {nombre}: {peso!r}")
    total = sum(pesos.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Los pesos del benchmark suman {total:.4f} y deben sumar 1. "
            "Con otra suma se compararía contra un índice que invierte más o "
            "menos dinero que la cartera."
        )


# ==========================================================================
# PRECIOS Y DIVISA
# ==========================================================================


def siguiente_dia_habil(indice: pd.DatetimeIndex, fecha: date) -> pd.Timestamp | None:
    """Primera sesión con cotización en o después de ``fecha``.

    Devuelve None si la fecha cae más allá del histórico: es preferible a
    devolver la última sesión disponible, que fecharía la compra en un día
    equivocado sin que se note.
    """
    objetivo = pd.Timestamp(fecha)
    posteriores = indice[indice >= objetivo]
    return posteriores[0] if len(posteriores) else None


def tipo_de_cambio_a_eur(serie_par: pd.Series | None, moneda: str) -> pd.Series | None:
    """Factor por el que multiplicar un precio en ``moneda`` para tenerlo en EUR.

    Los pares de Yahoo se cotizan como "unidades de la divisa por 1 EUR"
    (EURUSD=X ~ 1,16 dólares por euro). Así que el factor de conversión A euros
    es el INVERSO: 100 USD / 1,16 = 86 EUR.

    Multiplicar por el par en vez de dividir es un error del 35% que, además, va
    todo en la misma dirección: infla la cartera y deja intacto el benchmark.
    """
    if moneda == MONEDA_BASE:
        return None
    if serie_par is None or serie_par.empty:
        return None
    limpio = pd.Series(serie_par).dropna()
    limpio = limpio[limpio > 0]
    if limpio.empty:
        return None
    return 1.0 / limpio


def _a_eur(precios: pd.Series, factor: pd.Series | None) -> pd.Series:
    """Convierte una serie de precios a EUR alineando por fecha.

    El FX se reindexa con ``ffill``: los festivos de divisa no coinciden con los
    de bolsa, y usar el último cambio conocido es correcto — lo que no se puede
    es usar uno futuro.
    """
    if factor is None:
        return precios
    alineado = factor.reindex(precios.index).ffill()
    convertido = precios * alineado
    return convertido.dropna()


# ==========================================================================
# SALIDA
# ==========================================================================


@dataclass(slots=True)
class Posicion:
    """Una posición viva, con lo que hizo falta para construirla."""

    ticker: str
    participaciones: float
    invertido_eur: float
    fecha_efectiva: date
    precio_entrada_eur: float
    moneda_origen: str = MONEDA_BASE

    def valor_en(self, precio_eur: float) -> float:
        return self.participaciones * precio_eur


@dataclass(slots=True)
class AtribucionPosicion:
    """Cada valor frente a su porción del benchmark, desde su fecha de compra."""

    ticker: str
    invertido_eur: float
    valor_actual_eur: float
    valor_si_indice_eur: float
    alfa_eur: float
    alfa_pct: float
    retorno_pct: float
    retorno_indice_pct: float
    fecha_compra: str

    @property
    def bate_al_indice(self) -> bool:
        return self.alfa_eur > 0


@dataclass(slots=True)
class RendimientoCartera:
    """Resultado completo, serializable a JSON."""

    series: pd.DataFrame = field(default_factory=pd.DataFrame)
    resumen: dict[str, Any] = field(default_factory=dict)
    atribucion: list[AtribucionPosicion] = field(default_factory=list)
    posiciones: list[Posicion] = field(default_factory=list)
    unidades_benchmark: dict[str, float] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    pesos: dict[str, float] = field(default_factory=dict)

    @property
    def valido(self) -> bool:
        return not self.series.empty and bool(self.posiciones)

    def to_dict(self) -> dict[str, Any]:
        return {
            "series": self.series.reset_index().to_dict(orient="records") if not self.series.empty else [],
            "resumen": self.resumen,
            "atribucion": [asdict(a) for a in self.atribucion],
            "posiciones": [asdict(p) | {"fecha_efectiva": str(p.fecha_efectiva)} for p in self.posiciones],
            "unidades_benchmark": self.unidades_benchmark,
            "avisos": self.avisos,
            "pesos": self.pesos,
        }


# ==========================================================================
# XIRR
# ==========================================================================


def _vpn(tasa: float, flujos: Sequence[tuple[date, float]]) -> float:
    inicio = flujos[0][0]
    total = 0.0
    for fecha, importe in flujos:
        anios = (pd.Timestamp(fecha) - pd.Timestamp(inicio)).days / 365.0
        total += importe / ((1.0 + tasa) ** anios)
    return total


def xirr(flujos: Sequence[tuple[date, float]]) -> float | None:
    """Tasa interna de retorno con fechas irregulares.

    Convención: las aportaciones son NEGATIVAS (sale dinero del bolsillo) y el
    valor final POSITIVO. Devuelve None cuando no hay solución en un rango
    razonable, en vez de un número inventado: una TIR de −99% o de 10.000% no
    informa de nada y se leería como un dato.
    """
    if len(flujos) < 2:
        return None
    ordenados = sorted(flujos, key=lambda f: f[0])
    importes = [f[1] for f in ordenados]
    if not (any(i < 0 for i in importes) and any(i > 0 for i in importes)):
        return None

    try:
        from scipy.optimize import brentq
    except ImportError:
        LOGGER.warning("scipy no disponible: no se puede calcular el XIRR.")
        return None

    bajo, alto = -0.9999, 10.0
    try:
        if _vpn(bajo, ordenados) * _vpn(alto, ordenados) > 0:
            return None
        return float(brentq(_vpn, bajo, alto, args=(ordenados,), maxiter=200))
    except (ValueError, RuntimeError):
        return None


# ==========================================================================
# SERIE UNITIZADA (TWR)
# ==========================================================================


def serie_unitizada(valores: pd.Series, aportaciones: pd.Series) -> pd.Series:
    """Serie base 100 que aísla el efecto de las aportaciones.

    En cada fecha con aportación, el retorno del día se mide contra el valor
    ANTERIOR más lo aportado, de modo que meter dinero no cuenta como ganancia.
    Es la serie sobre la que se pueden calcular volatilidad, Sharpe y drawdown;
    hacerlo sobre la serie de valor haría que cada ingreso pareciese un retorno
    gigantesco.
    """
    if valores is None or valores.empty:
        return pd.Series(dtype=float)

    valores = valores.astype(float)
    aportes = aportaciones.reindex(valores.index).fillna(0.0).astype(float)

    unidades = [100.0]
    for i in range(1, len(valores)):
        base = float(valores.iloc[i - 1]) + float(aportes.iloc[i])
        if base <= 0:
            unidades.append(unidades[-1])
            continue
        factor = float(valores.iloc[i]) / base
        unidades.append(unidades[-1] * factor)

    return pd.Series(unidades, index=valores.index)


# ==========================================================================
# CONSTRUCCIÓN
# ==========================================================================


def _indice_comun(series: Iterable[pd.Series]) -> pd.DatetimeIndex:
    indice: pd.DatetimeIndex | None = None
    for s in series:
        if s is None or s.empty:
            continue
        idx = pd.DatetimeIndex(s.index)
        indice = idx if indice is None else indice.union(idx)
    return indice if indice is not None else pd.DatetimeIndex([])


def construir_series(
    transacciones: Sequence[Transaccion],
    precios_eur: dict[str, pd.Series],
    precios_proxy_eur: dict[str, pd.Series],
    pesos: dict[str, float],
    *,
    rebalanceo: str | None = None,
) -> RendimientoCartera:
    """Núcleo puro: no toca la red. Recibe los precios ya en EUR.

    Los tests atacan esta función; ``calcular_rendimiento`` es la que sale a
    buscar los datos.
    """
    validar_pesos(pesos)
    resultado = RendimientoCartera(pesos=dict(pesos))

    if not transacciones:
        resultado.avisos.append("No hay transacciones que valorar.")
        return resultado

    if rebalanceo is not None:
        resultado.avisos.append(
            f"Rebalanceo '{rebalanceo}' solicitado pero no aplicado: el benchmark "
            "money-weighted se construye sin rebalancear por defecto."
        )

    # --- 1. Posiciones y unidades del benchmark ---------------------------
    posiciones: list[Posicion] = []
    unidades: dict[str, float] = {nombre: 0.0 for nombre in pesos}
    aportes_por_fecha: dict[pd.Timestamp, float] = {}
    flujos: list[tuple[date, float]] = []
    detalle_atribucion: list[dict[str, Any]] = []

    for tx in sorted(transacciones, key=lambda t: t.fecha):
        if tx.tipo == VENTA:
            resultado.avisos.append(
                f"Venta de {tx.ticker} el {tx.fecha} ignorada: el caso base solo "
                "contempla compras."
            )
            continue

        serie = precios_eur.get(tx.ticker)
        if serie is None or serie.empty:
            resultado.avisos.append(
                f"Sin precios para {tx.ticker}: la posición se excluye del cálculo "
                "en vez de valorarse con un precio inventado."
            )
            continue

        fecha_efectiva = siguiente_dia_habil(pd.DatetimeIndex(serie.index), tx.fecha)
        if fecha_efectiva is None:
            resultado.avisos.append(
                f"{tx.ticker}: la fecha {tx.fecha} queda fuera del histórico disponible."
            )
            continue
        if fecha_efectiva.date() != tx.fecha:
            resultado.avisos.append(
                f"{tx.ticker}: {tx.fecha} no fue día de cotización; se usa "
                f"{fecha_efectiva.date()}, la siguiente sesión."
            )

        precio = float(serie.loc[fecha_efectiva])
        if not np.isfinite(precio) or precio <= 0:
            resultado.avisos.append(f"{tx.ticker}: precio no válido en {fecha_efectiva.date()}.")
            continue

        participaciones = tx.importe_eur / precio
        posiciones.append(Posicion(
            ticker=tx.ticker, participaciones=participaciones,
            invertido_eur=tx.importe_eur, fecha_efectiva=fecha_efectiva.date(),
            precio_entrada_eur=precio,
        ))

        # Benchmark: el mismo dinero, el mismo día, repartido por pesos.
        unidades_tx: dict[str, float] = {}
        for nombre, peso in pesos.items():
            proxy = precios_proxy_eur.get(nombre)
            if proxy is None or proxy.empty:
                resultado.avisos.append(f"Sin precios del proxy {nombre}: el benchmark queda incompleto.")
                continue
            fecha_proxy = siguiente_dia_habil(pd.DatetimeIndex(proxy.index), tx.fecha)
            if fecha_proxy is None:
                continue
            precio_proxy = float(proxy.loc[fecha_proxy])
            if not np.isfinite(precio_proxy) or precio_proxy <= 0:
                continue
            nuevas = (peso * tx.importe_eur) / precio_proxy
            unidades[nombre] += nuevas
            unidades_tx[nombre] = nuevas

        marca = pd.Timestamp(fecha_efectiva)
        aportes_por_fecha[marca] = aportes_por_fecha.get(marca, 0.0) + tx.importe_eur
        flujos.append((fecha_efectiva.date(), -tx.importe_eur))
        detalle_atribucion.append({
            "ticker": tx.ticker, "invertido": tx.importe_eur,
            "participaciones": participaciones, "unidades": unidades_tx,
            "fecha": fecha_efectiva.date(),
        })

    if not posiciones:
        resultado.avisos.append("Ninguna transacción pudo valorarse.")
        return resultado

    resultado.posiciones = posiciones
    resultado.unidades_benchmark = dict(unidades)

    # --- 2. Serie temporal común ------------------------------------------
    usados = [precios_eur[p.ticker] for p in posiciones if p.ticker in precios_eur]
    usados += [s for s in precios_proxy_eur.values() if s is not None and not s.empty]
    indice = _indice_comun(usados)
    primera = min(pd.Timestamp(p.fecha_efectiva) for p in posiciones)
    indice = indice[indice >= primera]
    if len(indice) == 0:
        resultado.avisos.append("No hay sesiones posteriores a la primera compra.")
        return resultado

    valor_cartera = pd.Series(0.0, index=indice)
    for posicion in posiciones:
        serie = precios_eur[posicion.ticker].reindex(indice).ffill()
        activa = pd.Series(indice >= pd.Timestamp(posicion.fecha_efectiva), index=indice)
        valor_cartera = valor_cartera.add(
            (serie * posicion.participaciones).where(activa, 0.0).fillna(0.0), fill_value=0.0
        )

    # Unidades acumuladas del benchmark en cada fecha: solo cuentan las compradas
    # hasta ese momento, igual que las posiciones.
    valor_benchmark = pd.Series(0.0, index=indice)
    for nombre in pesos:
        proxy = precios_proxy_eur.get(nombre)
        if proxy is None or proxy.empty:
            continue
        serie = proxy.reindex(indice).ffill()
        acumuladas = pd.Series(0.0, index=indice)
        for detalle in detalle_atribucion:
            nuevas = detalle["unidades"].get(nombre)
            if not nuevas:
                continue
            acumuladas += pd.Series(
                np.where(indice >= pd.Timestamp(detalle["fecha"]), nuevas, 0.0), index=indice
            )
        valor_benchmark = valor_benchmark.add((serie * acumuladas).fillna(0.0), fill_value=0.0)

    invertido = pd.Series(0.0, index=indice)
    for marca, importe in aportes_por_fecha.items():
        invertido += pd.Series(np.where(indice >= marca, importe, 0.0), index=indice)

    aportaciones_diarias = pd.Series(0.0, index=indice)
    for marca, importe in aportes_por_fecha.items():
        if marca in aportaciones_diarias.index:
            aportaciones_diarias.loc[marca] += importe

    with np.errstate(divide="ignore", invalid="ignore"):
        ret_cartera = (valor_cartera - invertido) / invertido.replace(0, np.nan) * 100
        ret_benchmark = (valor_benchmark - invertido) / invertido.replace(0, np.nan) * 100

    resultado.series = pd.DataFrame({
        "valor_cartera": valor_cartera,
        "valor_benchmark": valor_benchmark,
        "invertido_acum": invertido,
        "ret_cartera_pct": ret_cartera,
        "ret_benchmark_pct": ret_benchmark,
        "unitizada_cartera": serie_unitizada(valor_cartera, aportaciones_diarias),
        "unitizada_benchmark": serie_unitizada(valor_benchmark, aportaciones_diarias),
    })
    resultado.series.index.name = "fecha"

    # --- 3. Resumen -------------------------------------------------------
    from modulos.riesgo_salidas import metricas_de_serie

    total_invertido = float(invertido.iloc[-1])
    final_cartera = float(valor_cartera.iloc[-1])
    final_benchmark = float(valor_benchmark.iloc[-1])
    ultima = indice[-1].date()

    riesgo_cartera = metricas_de_serie(resultado.series["unitizada_cartera"].pct_change().dropna())
    riesgo_benchmark = metricas_de_serie(resultado.series["unitizada_benchmark"].pct_change().dropna())

    resultado.resumen = {
        "total_invertido_eur": round(total_invertido, 2),
        "valor_cartera_eur": round(final_cartera, 2),
        "valor_benchmark_eur": round(final_benchmark, 2),
        "diferencia_eur": round(final_cartera - final_benchmark, 2),
        "diferencia_pct": round((final_cartera / final_benchmark - 1) * 100, 2) if final_benchmark else None,
        "retorno_cartera_pct": round((final_cartera / total_invertido - 1) * 100, 2) if total_invertido else None,
        "retorno_benchmark_pct": round((final_benchmark / total_invertido - 1) * 100, 2) if total_invertido else None,
        "xirr_cartera": xirr(flujos + [(ultima, final_cartera)]),
        "xirr_benchmark": xirr(flujos + [(ultima, final_benchmark)]),
        "riesgo_cartera": riesgo_cartera.como_fila() if riesgo_cartera else None,
        "riesgo_benchmark": riesgo_benchmark.como_fila() if riesgo_benchmark else None,
        "desde": str(indice[0].date()),
        "hasta": str(ultima),
        "sesiones": int(len(indice)),
    }

    # --- 4. Atribución ----------------------------------------------------
    for detalle in detalle_atribucion:
        ticker = detalle["ticker"]
        serie = precios_eur.get(ticker)
        if serie is None or serie.empty:
            continue
        precio_final = float(serie.reindex(indice).ffill().iloc[-1])
        valor_actual = detalle["participaciones"] * precio_final

        valor_indice = 0.0
        for nombre, nuevas in detalle["unidades"].items():
            proxy = precios_proxy_eur.get(nombre)
            if proxy is None or proxy.empty:
                continue
            valor_indice += nuevas * float(proxy.reindex(indice).ffill().iloc[-1])

        invertido_i = detalle["invertido"]
        resultado.atribucion.append(AtribucionPosicion(
            ticker=ticker,
            invertido_eur=round(invertido_i, 2),
            valor_actual_eur=round(valor_actual, 2),
            valor_si_indice_eur=round(valor_indice, 2),
            alfa_eur=round(valor_actual - valor_indice, 2),
            alfa_pct=round((valor_actual / valor_indice - 1) * 100, 2) if valor_indice else 0.0,
            retorno_pct=round((valor_actual / invertido_i - 1) * 100, 2) if invertido_i else 0.0,
            retorno_indice_pct=round((valor_indice / invertido_i - 1) * 100, 2) if invertido_i else 0.0,
            fecha_compra=str(detalle["fecha"]),
        ))

    return resultado


# ==========================================================================
# ADQUISICIÓN DE DATOS
# ==========================================================================


def _moneda_de(ticker: str) -> str:
    """Divisa de cotización. Ante la duda, USD, que es el caso mayoritario.

    fast_info expone la clave como "currency" en .get(); se prueba también el
    acceso por atributo porque yfinance mantiene las dos convenciones y ya nos
    costó una vez que el mapa de calor saliera vacío durante meses.
    """
    try:
        import yfinance as yf

        fast = getattr(yf.Ticker(ticker), "fast_info", None)
        if fast is not None:
            valor = None
            if hasattr(fast, "get"):
                valor = fast.get("currency")
            if valor is None:
                valor = getattr(fast, "currency", None)
            if valor:
                return str(valor).upper()
    except Exception as exc:
        LOGGER.debug("Sin divisa para %s: %s", ticker, exc)
    return "USD"


def _periodo_necesario(transacciones: Sequence[Transaccion]) -> str:
    """Periodo de descarga que cubre desde la compra más antigua."""
    if not transacciones:
        return "1y"
    primera = min(t.fecha for t in transacciones)
    anios = (date.today() - primera).days / 365.25
    return f"{max(2, int(np.ceil(anios)) + 1)}y"


def _descargar_cierres(tickers: Sequence[str], periodo: str) -> dict[str, pd.Series]:
    """Cierres AJUSTADOS (retorno total) usando la capa resiliente del repo."""
    from modulos.swing_scanner import descargar_universo

    salida: dict[str, pd.Series] = {}
    if not tickers:
        return salida
    try:
        # descargar_universo usa auto_adjust=True y reintenta ante rate limit
        # troceando el lote: es la misma convención de retorno total que exige
        # la comparación con los ETF de acumulación.
        datos = descargar_universo(tuple(dict.fromkeys(tickers)), periodo=periodo)
    except Exception as exc:
        LOGGER.warning("Fallo descargando %s: %s", tickers, exc)
        return salida

    for ticker, df in datos.items():
        if df is None or df.empty or "Close" not in df.columns:
            continue
        serie = df["Close"].dropna()
        if getattr(serie.index, "tz", None) is not None:
            serie.index = serie.index.tz_localize(None)
        if not serie.empty:
            salida[ticker] = serie
    return salida


def calcular_rendimiento(
    transacciones: Sequence[Transaccion | tuple | dict],
    indices_pesos: dict[str, float] | None = None,
    moneda_base: str = MONEDA_BASE,
    proxies: dict[str, str] | None = None,
    rebalanceo: str | None = None,
) -> RendimientoCartera:
    """Punto de entrada con adquisición de datos.

    ``transacciones`` admite objetos Transaccion, tuplas
    ``(ticker, importe, fecha[, tipo])`` o diccionarios.
    """
    normalizadas: list[Transaccion] = []
    for t in transacciones:
        if isinstance(t, Transaccion):
            normalizadas.append(t)
        elif isinstance(t, dict):
            normalizadas.append(Transaccion(**t))
        else:
            normalizadas.append(Transaccion(*t))

    pesos = dict(indices_pesos or PESOS_BENCHMARK_DEFECTO)
    validar_pesos(pesos)

    if moneda_base != MONEDA_BASE:
        raise ValueError(
            f"Solo se admite {MONEDA_BASE} como moneda base; se pidió {moneda_base}. "
            "Cambiarla exigiría revisar la dirección de todos los cruces de divisa."
        )

    mapa_proxies = {
        nombre: (proxies or {}).get(nombre) or PROXIES_INDICE.get(nombre, {}).get("ticker")
        for nombre in pesos
    }
    faltan = [n for n, t in mapa_proxies.items() if not t]
    if faltan:
        raise ValueError(f"Sin proxy configurado para: {', '.join(faltan)}")

    periodo = _periodo_necesario(normalizadas)
    tickers = sorted({t.ticker for t in normalizadas})
    proxy_tickers = sorted(set(mapa_proxies.values()))

    cierres = _descargar_cierres(tickers + proxy_tickers, periodo)

    # Divisa por valor y descarga de los pares que hagan falta.
    monedas = {ticker: _moneda_de(ticker) for ticker in tickers}
    pares = sorted({PARES_FX[m] for m in monedas.values() if m in PARES_FX and m != MONEDA_BASE})
    series_fx = _descargar_cierres(pares, periodo) if pares else {}

    precios_eur: dict[str, pd.Series] = {}
    avisos: list[str] = []
    for ticker in tickers:
        serie = cierres.get(ticker)
        if serie is None:
            avisos.append(f"Sin precios para {ticker}.")
            continue
        moneda = monedas.get(ticker, "USD")
        if moneda == MONEDA_BASE:
            precios_eur[ticker] = serie
            continue
        par = PARES_FX.get(moneda)
        factor = tipo_de_cambio_a_eur(series_fx.get(par) if par else None, moneda)
        if factor is None:
            avisos.append(
                f"{ticker} cotiza en {moneda} y no hay tipo de cambio disponible: "
                "se excluye en vez de mezclar divisas en la misma serie."
            )
            continue
        precios_eur[ticker] = _a_eur(serie, factor)

    precios_proxy_eur: dict[str, pd.Series] = {}
    for nombre, ticker_proxy in mapa_proxies.items():
        serie = cierres.get(ticker_proxy)
        if serie is None:
            avisos.append(f"Sin precios del proxy {ticker_proxy} ({nombre}).")
            continue
        # Los proxies por defecto ya cotizan en EUR: no se les aplica FX.
        moneda_proxy = PROXIES_INDICE.get(nombre, {}).get("moneda", MONEDA_BASE)
        if moneda_proxy != MONEDA_BASE:
            par = PARES_FX.get(moneda_proxy)
            factor = tipo_de_cambio_a_eur(series_fx.get(par) if par else None, moneda_proxy)
            serie = _a_eur(serie, factor) if factor is not None else serie
        precios_proxy_eur[nombre] = serie

    resultado = construir_series(normalizadas, precios_eur, precios_proxy_eur, pesos,
                                 rebalanceo=rebalanceo)
    resultado.avisos = avisos + resultado.avisos
    return resultado
