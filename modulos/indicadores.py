"""Librería de indicadores técnicos: funciones puras sobre OHLCV.

Por qué existe
--------------
Hasta ahora cada indicador vivía incrustado dentro de una función de dibujo de
``charts.py`` (el RSI se calculaba en tres sitios distintos, con matices
diferentes en cada uno). Eso impedía dos cosas que el módulo de swing necesita:
reutilizar los cálculos fuera de un gráfico, y testearlos sin red ni Streamlit.

Todo aquí es determinista y sin efectos secundarios: entra un DataFrame con
columnas Open/High/Low/Close/Volume y sale una Serie o DataFrame. Ninguna
función descarga datos.

Convención de suavizado
-----------------------
RSI, ATR y ADX usan suavizado de Wilder (``alpha = 1/n``), que es el original de
"New Concepts in Technical Trading Systems" y el que replican TradingView y la
mayoría de plataformas. Usar una EMA estándar (``alpha = 2/(n+1)``) da valores
distintos y descuadraría las señales frente a lo que el usuario ve en su gráfico.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "sma", "ema", "wilder", "rsi", "atr", "adx", "macd",
    "bandas_bollinger", "canales_keltner", "squeeze_activo",
    "donchian", "volumen_relativo", "distancia_maximo_52s",
    "distancia_minimo_52s", "pendiente_normalizada", "volatilidad_realizada",
    "enriquecer_ohlcv", "limpiar_velas_incompletas",
]


# --------------------------------------------------------------------------
# Medias y suavizados
# --------------------------------------------------------------------------


def sma(serie: pd.Series, periodo: int) -> pd.Series:
    return serie.rolling(window=periodo, min_periods=periodo).mean()


def ema(serie: pd.Series, periodo: int) -> pd.Series:
    return serie.ewm(span=periodo, adjust=False).mean()


def wilder(serie: pd.Series, periodo: int) -> pd.Series:
    """Suavizado de Wilder: EMA con alpha = 1/n en vez de 2/(n+1)."""
    return serie.ewm(alpha=1.0 / periodo, adjust=False).mean()


# --------------------------------------------------------------------------
# Osciladores y fuerza de tendencia
# --------------------------------------------------------------------------


def rsi(close: pd.Series, periodo: int = 14) -> pd.Series:
    """RSI de Wilder (0-100)."""
    delta = close.diff()
    ganancia = delta.clip(lower=0.0)
    perdida = (-delta).clip(lower=0.0)

    media_ganancia = wilder(ganancia, periodo)
    media_perdida = wilder(perdida, periodo)

    # Sin pérdidas en la ventana el RS es infinito: el RSI satura en 100.
    rs = media_ganancia / media_perdida.replace(0.0, np.nan)
    resultado = 100.0 - (100.0 / (1.0 + rs))
    return resultado.fillna(100.0).where(media_ganancia > 0, 0.0).clip(0.0, 100.0)


def _rango_verdadero(df: pd.DataFrame) -> pd.Series:
    """True Range: el mayor de (H-L), |H-Cierre previo|, |L-Cierre previo|.

    Los dos últimos términos son los que capturan los huecos de apertura, que es
    justo el riesgo que un stop basado en ATR debe cubrir.
    """
    alto, bajo, cierre = df["High"], df["Low"], df["Close"]
    cierre_previo = cierre.shift(1)
    return pd.concat(
        [alto - bajo, (alto - cierre_previo).abs(), (bajo - cierre_previo).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Average True Range: unidad de volatilidad para stops y tamaño de posición."""
    return wilder(_rango_verdadero(df), periodo)


def adx(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """ADX: fuerza de la tendencia (no su dirección).

    Se usa como filtro de régimen: por debajo de ~20 el mercado está en rango y
    las estrategias de ruptura producen sobre todo señales falsas, mientras que
    las de reversión a la media funcionan mejor. Por encima de ~25 ocurre lo
    contrario. Sin este filtro, una misma estrategia parece "dejar de funcionar"
    cuando en realidad se está aplicando en el régimen equivocado.
    """
    alto, bajo = df["High"], df["Low"]
    subida = alto.diff()
    bajada = -bajo.diff()

    dm_mas = pd.Series(np.where((subida > bajada) & (subida > 0), subida, 0.0), index=df.index)
    dm_menos = pd.Series(np.where((bajada > subida) & (bajada > 0), bajada, 0.0), index=df.index)

    tr_suave = wilder(_rango_verdadero(df), periodo).replace(0.0, np.nan)
    di_mas = 100.0 * wilder(dm_mas, periodo) / tr_suave
    di_menos = 100.0 * wilder(dm_menos, periodo) / tr_suave

    suma = (di_mas + di_menos).replace(0.0, np.nan)
    dx = 100.0 * (di_mas - di_menos).abs() / suma
    return wilder(dx.fillna(0.0), periodo)


def macd(
    close: pd.Series,
    rapida: int = 12,
    lenta: int = 26,
    señal: int = 9,
) -> pd.DataFrame:
    linea = ema(close, rapida) - ema(close, lenta)
    linea_señal = ema(linea, señal)
    return pd.DataFrame(
        {"macd": linea, "señal": linea_señal, "histograma": linea - linea_señal}
    )


# --------------------------------------------------------------------------
# Volatilidad y canales
# --------------------------------------------------------------------------


def bandas_bollinger(close: pd.Series, periodo: int = 20, desviaciones: float = 2.0) -> pd.DataFrame:
    media = sma(close, periodo)
    desv = close.rolling(window=periodo, min_periods=periodo).std(ddof=0)
    return pd.DataFrame(
        {
            "bb_media": media,
            "bb_superior": media + desviaciones * desv,
            "bb_inferior": media - desviaciones * desv,
            "bb_ancho": (2 * desviaciones * desv) / media.replace(0.0, np.nan),
        }
    )


def canales_keltner(df: pd.DataFrame, periodo: int = 20, multiplo: float = 1.5) -> pd.DataFrame:
    media = ema(df["Close"], periodo)
    rango = atr(df, periodo)
    return pd.DataFrame(
        {
            "kc_media": media,
            "kc_superior": media + multiplo * rango,
            "kc_inferior": media - multiplo * rango,
        }
    )


def squeeze_activo(df: pd.DataFrame, periodo: int = 20) -> pd.Series:
    """True cuando las Bollinger están DENTRO de las Keltner (compresión).

    La compresión no es una señal de compra ni de venta: sólo indica que la
    volatilidad está contraída y que el siguiente movimiento tiende a ser amplio.
    La dirección la decide la ruptura, no el squeeze.
    """
    bb = bandas_bollinger(df["Close"], periodo)
    kc = canales_keltner(df, periodo)
    return (bb["bb_superior"] < kc["kc_superior"]) & (bb["bb_inferior"] > kc["kc_inferior"])


def donchian(df: pd.DataFrame, periodo: int = 20) -> pd.DataFrame:
    """Canal de máximos/mínimos de N sesiones, base de las rupturas.

    El máximo excluye la vela actual (``shift(1)``): si se incluyera, el precio
    nunca podría "superar su máximo de 20 días" porque él mismo formaría ese
    máximo. Ese error hace que un backtest de rupturas parezca no dar señales.
    """
    return pd.DataFrame(
        {
            "dc_superior": df["High"].rolling(periodo, min_periods=periodo).max().shift(1),
            "dc_inferior": df["Low"].rolling(periodo, min_periods=periodo).min().shift(1),
        }
    )


def volatilidad_realizada(close: pd.Series, periodo: int = 20, anualizar: bool = True) -> pd.Series:
    retornos = close.pct_change(fill_method=None)
    vol = retornos.rolling(periodo, min_periods=periodo).std(ddof=0)
    return vol * np.sqrt(252) if anualizar else vol


# --------------------------------------------------------------------------
# Volumen y posición relativa
# --------------------------------------------------------------------------


def volumen_relativo(volumen: pd.Series, periodo: int = 20) -> pd.Series:
    """Volumen actual dividido por su media. 1.0 = normal, 2.0 = el doble.

    Es el confirmador de las rupturas: un máximo nuevo con volumen por debajo de
    la media suele ser una trampa, porque no hay demanda institucional detrás.
    """
    media = sma(volumen, periodo).replace(0.0, np.nan)
    return volumen / media


def distancia_maximo_52s(close: pd.Series, sesiones: int = 252) -> pd.Series:
    """Distancia porcentual (negativa) al máximo de 52 semanas. 0 = en máximos."""
    maximo = close.rolling(sesiones, min_periods=20).max()
    return (close / maximo - 1.0) * 100.0


def distancia_minimo_52s(close: pd.Series, sesiones: int = 252) -> pd.Series:
    """Distancia porcentual (positiva) al mínimo de 52 semanas."""
    minimo = close.rolling(sesiones, min_periods=20).min()
    return (close / minimo.replace(0.0, np.nan) - 1.0) * 100.0


def pendiente_normalizada(serie: pd.Series, periodo: int = 20) -> pd.Series:
    """Pendiente de la regresión lineal, en % del valor medio de la ventana.

    Normalizar es lo que permite comparar la inclinación de una tendencia entre
    una acción de $5 y otra de $500: la pendiente en unidades de precio no es
    comparable entre valores distintos.
    """
    def _pendiente(ventana: np.ndarray) -> float:
        if np.isnan(ventana).any():
            return np.nan
        x = np.arange(len(ventana), dtype=float)
        pendiente = np.polyfit(x, ventana, 1)[0]
        media = np.mean(ventana)
        return (pendiente / media) * 100.0 if media else np.nan

    return serie.rolling(periodo, min_periods=periodo).apply(_pendiente, raw=True)


# --------------------------------------------------------------------------
# Enriquecimiento en bloque
# --------------------------------------------------------------------------


def limpiar_velas_incompletas(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina las velas sin cierre válido.

    Con el mercado abierto, yfinance añade la sesión en curso con OHLC a NaN
    pero con volumen ya informado. Si esa fila llega a las estrategias, todas
    leen ``iloc[-1]`` y evalúan NaN: el escáner no falla, simplemente deja de
    encontrar señales, que es la peor forma posible de romperse. Filtrar por
    volumen no sirve (viene relleno); hay que filtrar por cierre.
    """
    if df is None or df.empty or "Close" not in df.columns:
        return pd.DataFrame()
    return df.dropna(subset=["Close"]).copy()


def enriquecer_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Añade de una vez todos los indicadores que consumen las estrategias.

    Se calcula todo junto porque el escáner procesa cientos de tickers y hacerlo
    indicador a indicador multiplicaría los recorridos sobre el mismo DataFrame.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    requeridas = {"Open", "High", "Low", "Close", "Volume"}
    if not requeridas.issubset(df.columns):
        return pd.DataFrame()

    datos = limpiar_velas_incompletas(df)
    if datos.empty:
        return pd.DataFrame()

    cierre = datos["Close"]

    datos["sma20"] = sma(cierre, 20)
    datos["sma50"] = sma(cierre, 50)
    datos["sma200"] = sma(cierre, 200)
    datos["ema21"] = ema(cierre, 21)

    datos["rsi14"] = rsi(cierre, 14)
    datos["rsi2"] = rsi(cierre, 2)
    datos["atr14"] = atr(datos, 14)
    datos["atr_pct"] = (datos["atr14"] / cierre.replace(0.0, np.nan)) * 100.0
    datos["adx14"] = adx(datos, 14)

    macd_df = macd(cierre)
    datos["macd"] = macd_df["macd"]
    datos["macd_señal"] = macd_df["señal"]
    datos["macd_hist"] = macd_df["histograma"]

    bb = bandas_bollinger(cierre)
    datos["bb_superior"] = bb["bb_superior"]
    datos["bb_inferior"] = bb["bb_inferior"]
    datos["bb_ancho"] = bb["bb_ancho"]
    datos["squeeze"] = squeeze_activo(datos)

    dc = donchian(datos, 20)
    datos["dc_superior20"] = dc["dc_superior"]
    datos["dc_inferior20"] = dc["dc_inferior"]
    dc55 = donchian(datos, 55)
    datos["dc_superior55"] = dc55["dc_superior"]
    datos["dc_inferior55"] = dc55["dc_inferior"]

    datos["vol_rel"] = volumen_relativo(datos["Volume"])
    datos["dist_max52"] = distancia_maximo_52s(cierre)
    datos["dist_min52"] = distancia_minimo_52s(cierre)
    datos["pendiente50"] = pendiente_normalizada(cierre, 50)
    datos["vol_realizada"] = volatilidad_realizada(cierre)

    return datos
