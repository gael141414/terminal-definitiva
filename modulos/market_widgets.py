from __future__ import annotations

import html
import logging
import xml.etree.ElementTree as ET
from typing import Any

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from modulos import quotes as quotes_provider
from modulos.config import CONFIG
from modulos.fmp_api import FMP_STATUS_OK, fetch_fmp_json_classified
from modulos.yahoo_resilience import is_yahoo_rate_limit_error, safe_yfinance_fetch

YAHOO_LOGGER = logging.getLogger("valuequant.yahoo")


def _is_yahoo_rate_limit_error(exc: Exception) -> bool:
    """Detecta errores temporales de rate limit de Yahoo/yfinance.

    Delega en el detector centralizado de ``modulos.yahoo_resilience`` para evitar
    mantener dos implementaciones divergentes del mismo criterio.
    """

    return is_yahoo_rate_limit_error(exc)


def _safe_yahoo_history(
    ticker: str,
    *,
    period: str,
    interval: str = "1d",
    auto_adjust: bool | None = None,
) -> pd.DataFrame:
    """Descarga histórico Yahoo sin propagar ruido por rate limits temporales.

    Envuelto sobre ``yahoo_resilience.safe_yfinance_fetch`` (con reintento corto
    ante rate limit) en vez de un ``try/except`` propio duplicado.
    """

    kwargs: dict[str, Any] = {"period": period, "interval": interval}
    if auto_adjust is not None:
        kwargs["auto_adjust"] = auto_adjust

    data, status = safe_yfinance_fetch(
        lambda: yf.Ticker(str(ticker).strip()).history(**kwargs),
        empty_value=pd.DataFrame(),
        context=f"market_widgets:{ticker}",
    )
    if status == "rate_limited":
        YAHOO_LOGGER.warning("Yahoo rate limit para %s; se omite lectura temporal.", ticker)
    elif status == "error":
        YAHOO_LOGGER.debug("Yahoo history omitido para %s tras error de proveedor.", ticker)
    return data if isinstance(data, pd.DataFrame) else pd.DataFrame()


def _safe_fast_market_cap(yf_ticker: Any) -> float | None:
    """Obtiene market cap desde fast_info sin caer a quoteSummary/info.

    yfinance sirve esta métrica con DOS nombres según cómo se pida: ``.keys()``
    y ``.get()`` la exponen como ``marketCap``, mientras que el acceso por
    atributo acepta ``market_cap``. Pedir solo ``get("market_cap")`` devolvía
    None para todos los tickers sin lanzar ningún error, así que el mapa de
    calor de la Home se quedaba permanentemente vacío mostrando "No hay datos
    suficientes". Se prueban las tres formas.
    """

    try:
        fast_info = getattr(yf_ticker, "fast_info", {}) or {}
        value = None
        if hasattr(fast_info, "get"):
            value = fast_info.get("marketCap")
            if value is None:
                value = fast_info.get("market_cap")
        if value is None:
            value = getattr(fast_info, "market_cap", None)
        if value is None:
            return None
        numeric = float(value)
        return numeric if np.isfinite(numeric) and numeric > 0 else None
    except Exception as exc:
        if _is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo rate limit leyendo fast_info; se omite market cap temporal.")
        else:
            YAHOO_LOGGER.debug("Yahoo fast_info omitido: %s: %s", type(exc).__name__, exc)
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_etf_yahoo(query):
    """Consulta la API oculta de Yahoo Finance para autocompletar nombres de fondos."""
    if not query or len(query) < 2:
        return []

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=15&newsCount=0"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 429:
            YAHOO_LOGGER.warning("Yahoo search rate limit para query=%s", query)
            return []
        datos = res.json()
        resultados = []

        for quote in datos.get("quotes", []):
            if quote.get("quoteType") in ["ETF", "MUTUALFUND"]:
                simbolo = quote.get("symbol")
                nombre = quote.get("shortname", quote.get("longname", "Desconocido"))
                resultados.append(f"{simbolo} ➔ {nombre}")

        return resultados
    except Exception as exc:
        if _is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo search rate limit para query=%s", query)
        return []


@st.cache_data(ttl=900, show_spinner=False)
def obtener_datos_ticker_tape() -> str:
    """Genera los items HTML de la cinta de mercado con datos recientes.

    Usa ``modulos.quotes.fetch_quotes_with_fallback``: intenta Yahoo Finance primero
    y, si falla, hace fallback a FMP para instrumentos que lo soportan. Los símbolos
    sin dato (rate limit, fuente no disponible, etc.) muestran un estado explícito en
    vez de desaparecer en silencio de la cinta.
    """
    activos = {
        "Oro": "GC=F",
        "Petróleo": "CL=F",
        "SPY": "SPY",
        "AAPL": "AAPL",
        "MSFT": "MSFT",
        "GOOGL": "GOOGL",
        "AMZN": "AMZN",
        "NVDA": "NVDA",
        "META": "META",
        "TSLA": "TSLA",
    }
    resultados = quotes_provider.fetch_quotes_with_fallback(activos.values(), period="5d")
    items: list[str] = []

    for nombre, ticker in activos.items():
        quote = resultados.get(ticker)
        if quote is not None and quote.ok:
            clase = "is-up" if (quote.change_pct or 0) >= 0 else "is-down"
            icono = "bi-caret-up-fill" if (quote.change_pct or 0) >= 0 else "bi-caret-down-fill"
            variacion_html = (
                f"<span class='{clase}'><i class='bi {icono}'></i> {quote.change_pct:+.2f}%</span>"
                if quote.change_pct is not None
                else "<span class='is-flat'>· FMP</span>"
            )
            items.append(
                f"<span class='vq-tape-item'>"
                f"<a href='https://finance.yahoo.com/quote/{ticker}' target='_blank' style='text-decoration:none; color:inherit; display:flex; gap:0.42rem; align-items:center;'>"
                f"<strong>{html.escape(nombre)}</strong> "
                f"<span>${quote.price:,.2f}</span> "
                f"{variacion_html}"
                f"</a></span>"
            )
        else:
            estado = quote.status_label if quote is not None else "Sin datos disponibles"
            items.append(
                f"<span class='vq-tape-item'>"
                f"<strong>{html.escape(nombre)}</strong> "
                f"<span>$--</span> "
                f"<span class='is-flat' title='{html.escape(estado)}'>{html.escape(estado)}</span>"
                f"</span>"
            )

    if not quotes_provider.any_quote_succeeded(resultados):
        # Fallo total del lote: no queremos que un 429 puntual bloquee la cinta
        # durante los 15 minutos completos de TTL. Se limpia la propia caché para
        # que el próximo rerun reintente en vez de servir el fallo congelado.
        obtener_datos_ticker_tape.clear()

    return "".join(items)


def render_ticker_tape() -> None:
    """Renderiza una cinta de mercado fija y continua en la parte superior."""
    items_html = obtener_datos_ticker_tape()
    st.markdown(
        f"""
        <div class="vq-ticker-fixed" aria-label="Market ticker tape">
            <div class="vq-ticker-track">
                <div class="vq-ticker-content">{items_html}{items_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=86400)
def analizar_rotacion_sectores():
    """Descarga el rendimiento de los 11 sectores del S&P 500 usando sus ETFs."""
    # Los nombres van sin emoji: son un dato, no presentación. Con el emoji
    # dentro acababa en el eje del gráfico, en cualquier exportación y en toda
    # comparación de cadenas. La iconografía se aplica al pintar.
    etfs = {
        "Tecnología": "XLK", "Salud": "XLV", "Finanzas": "XLF",
        "Cons. Discrecional": "XLY", "Cons. Básico": "XLP", "Energía": "XLE",
        "Industriales": "XLI", "Materiales": "XLB", "Inmobiliario": "XLRE",
        "Utilities": "XLU", "Comunicaciones": "XLC",
    }
    datos = []
    for sector, ticker_etf in etfs.items():
        hist = _safe_yahoo_history(ticker_etf, period="3mo")
        if len(hist) >= 21 and "Close" in hist.columns:
            p_actual = hist["Close"].iloc[-1]
            p_1m = hist["Close"].iloc[-21]
            p_3m = hist["Close"].iloc[0]

            r_1m = ((p_actual - p_1m) / p_1m) * 100
            r_3m = ((p_actual - p_3m) / p_3m) * 100

            datos.append({"Sector": sector, "1 Mes (%)": r_1m, "3 Meses (%)": r_3m})

    return pd.DataFrame(datos) if datos else None


@st.cache_data(ttl=600, show_spinner=False)
def obtener_market_snapshot() -> list[dict[str, str]]:
    """Obtiene una lectura breve de mercado para la pantalla Home, incluyendo indicadores macro.

    Símbolos sin dato disponible (rate limit, sin fallback para índices/futuros...)
    muestran un estado explícito en el propio snapshot en vez de desaparecer.
    """
    activos = {
        "SPY": "SPY",
        "Nasdaq": "QQQ",
        "Oro": "GC=F",
        "Petróleo": "CL=F",
        "NVDA": "NVDA",
        "AAPL": "AAPL",
        "VIX": "^VIX",
        "US 10Y": "^TNX",
    }
    resultados = quotes_provider.fetch_quotes_with_fallback(activos.values(), period="5d")
    snapshot: list[dict[str, str]] = []
    for nombre, ticker in activos.items():
        quote = resultados.get(ticker)
        if quote is None or not quote.ok:
            estado = quote.status_label if quote is not None else "Sin datos disponibles"
            snapshot.append({
                "nombre": nombre,
                "precio": "--",
                "change_val": 0.0,
                "cambio": estado,
                "clase": "is-flat",
            })
            continue

        precio = quote.price
        if ticker in ["^VIX", "^TNX"]:
            precio_str = f"{precio:,.2f}" if ticker == "^VIX" else f"{precio:.2f}%"
        else:
            precio_str = f"${precio:,.2f}"

        if quote.change_pct is not None:
            cambio_val = quote.change_pct
            cambio_str = f"{cambio_val:+.2f}%"
            clase = "is-up" if cambio_val >= 0 else "is-down"
        else:
            cambio_val = 0.0
            cambio_str = quote.status_label
            clase = "is-flat"

        snapshot.append({
            "nombre": nombre,
            "precio": precio_str,
            "change_val": cambio_val,
            "cambio": cambio_str,
            "clase": clase,
        })

    if not quotes_provider.any_quote_succeeded(resultados):
        obtener_market_snapshot.clear()
    return snapshot


def _normalizar_url_imagen_noticia(item: dict) -> str:
    """Extrae una miniatura válida de FMP aunque la API cambie el nombre de la clave."""
    candidatos = (
        item.get("image"),
        item.get("imageUrl"),
        item.get("image_url"),
        item.get("thumbnail"),
        item.get("thumbnailUrl"),
        item.get("urlToImage"),
        item.get("siteImage"),
    )
    for candidato in candidatos:
        if not candidato:
            continue
        url = str(candidato).strip()
        if url.startswith("//"):
            url = f"https:{url}"
        if url.startswith(("http://", "https://")):
            return url
    return ""


@st.cache_data(ttl=900, show_spinner=False)
def obtener_market_treemap_data() -> pd.DataFrame:
    """Construye un DataFrame ligero para el mapa de calor de mercado de la Home."""
    universo = {
        "AAPL": "Tecnología", "MSFT": "Tecnología", "NVDA": "Semiconductores", "GOOGL": "Comunicación",
        "AMZN": "Consumo discrecional", "META": "Comunicación", "TSLA": "Consumo discrecional", "JPM": "Finanzas",
        "XOM": "Energía", "LLY": "Salud", "UNH": "Salud", "V": "Finanzas", "AVGO": "Semiconductores",
        "WMT": "Consumo defensivo", "COST": "Consumo defensivo", "HD": "Consumo discrecional",
    }
    rows: list[dict[str, object]] = []
    for ticker, sector in universo.items():
        try:
            yf_ticker = yf.Ticker(ticker)
            hist = _safe_yahoo_history(ticker, period="5d", interval="1d", auto_adjust=False)
            close = hist["Close"].dropna() if hist is not None and not hist.empty and "Close" in hist.columns else pd.Series(dtype=float)
            if len(close) < 2:
                continue
            market_cap = _safe_fast_market_cap(yf_ticker)
            if not market_cap:
                continue
            previous_close = float(close.iloc[-2])
            if previous_close == 0:
                continue
            daily_return = ((float(close.iloc[-1]) - previous_close) / previous_close) * 100
            rows.append({"Ticker": ticker, "Sector": sector, "MarketCap": float(market_cap), "Rendimiento_Diario": daily_return})
        except Exception as exc:
            if _is_yahoo_rate_limit_error(exc):
                YAHOO_LOGGER.warning("Yahoo rate limit para treemap %s; se omite temporalmente.", ticker)
            else:
                YAHOO_LOGGER.debug("Treemap omitido para %s: %s: %s", ticker, type(exc).__name__, exc)
            continue
    if not rows:
        # Igual que el ticker tape: no bloquear el treemap 30 minutos si el lote
        # entero falló por un rate limit puntual.
        obtener_market_treemap_data.clear()
    return pd.DataFrame(rows, columns=["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"])


@st.cache_data(ttl=1800, show_spinner=False)
def obtener_ultimas_noticias(limit: int = 6) -> list[dict[str, str]]:
    """Descarga noticias recientes desde FMP, con Yahoo RSS como respaldo.

    Las noticias de Home son opcionales: un fallo aquí nunca debe romper el
    resto de la página. Nunca se registra la URL de la petición ni la API key
    (ni siquiera vía el texto de una excepción de requests, que embebe la URL
    completa) — solo el status clasificado (ok/disabled/unauthorized/
    restricted_plan/rate_limited/provider_error/no_data).
    """
    noticias: list[dict[str, str]] = []
    logger = logging.getLogger("valuequant.news")

    if CONFIG.fmp_news_enabled:
        payload, status = fetch_fmp_json_classified(
            "https://financialmodelingprep.com/api/v3/stock_news",
            {"tickers": "AAPL,MSFT,NVDA,SPY,QQQ", "limit": limit, "apikey": CONFIG.fmp_api_key},
            context="market_widgets:home_news",
        )
        if status == FMP_STATUS_OK and payload:
            for item in payload[:limit]:
                if not isinstance(item, dict):
                    continue
                noticias.append({
                    "title": str(item.get("title") or item.get("headline") or "Noticia financiera"),
                    "date": str(item.get("publishedDate") or item.get("publishedAt") or item.get("date") or "")[:16],
                    "image": _normalizar_url_imagen_noticia(item),
                    "url": str(item.get("url") or item.get("link") or "#"),
                    "source": "FMP",
                })
        elif status != FMP_STATUS_OK:
            logger.info("FMP news no disponible para Home (status=%s); se prueba Yahoo RSS.", status)
    else:
        logger.debug("FMP_NEWS_ENABLED=false; se omite noticias FMP en Home.")

    if noticias:
        return noticias[:limit]

    try:
        rss_url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,AAPL&region=US&lang=en-US"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        rss = requests.get(rss_url, headers=headers, timeout=8)
        if rss.status_code == 429:
            YAHOO_LOGGER.warning("Yahoo RSS rate limit; se omiten noticias de respaldo.")
            return noticias[:limit]
        rss.raise_for_status()
        root = ET.fromstring(rss.content)
        for item in root.findall("./channel/item")[:limit]:
            noticias.append({
                "title": item.findtext("title") or "Noticia financiera",
                "date": item.findtext("pubDate") or "",
                "image": "",
                "url": item.findtext("link") or "#",
                "source": "Yahoo RSS",
            })
    except Exception as exc:
        if _is_yahoo_rate_limit_error(exc):
            YAHOO_LOGGER.warning("Yahoo RSS rate limit; se omiten noticias de respaldo.")
        else:
            logger.warning("Yahoo RSS no disponible: %s", type(exc).__name__)

    return noticias[:limit]
