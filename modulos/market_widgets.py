from __future__ import annotations

import html
import logging
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from modulos.config import CONFIG


@st.cache_data(ttl=3600, show_spinner=False)
def buscar_etf_yahoo(query):
    """Consulta la API oculta de Yahoo Finance para autocompletar nombres de fondos."""
    if not query or len(query) < 2:
        return []
    
    # Endpoint interno de búsqueda de Yahoo
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=15&newsCount=0"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        datos = res.json()
        resultados = []
        
        for quote in datos.get('quotes', []):
            # Filtramos estrictamente para que solo salgan ETFs y Fondos
            if quote.get('quoteType') in ['ETF', 'MUTUALFUND']:
                simbolo = quote.get('symbol')
                nombre = quote.get('shortname', quote.get('longname', 'Desconocido'))
                resultados.append(f"{simbolo} ➔ {nombre}")
                
        return resultados
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def obtener_datos_ticker_tape() -> str:
    """Genera los items HTML de la cinta de mercado con datos recientes de Yahoo Finance."""
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
    items: list[str] = []

    for nombre, ticker in activos.items():
        try:
            data = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=False)
            if data is None or data.empty or "Close" not in data.columns:
                continue
            cierres = data["Close"].dropna()
            if len(cierres) < 2:
                continue
            precio = float(cierres.iloc[-1])
            previo = float(cierres.iloc[-2])
            if previo == 0:
                continue
            variacion = ((precio - previo) / previo) * 100
            clase = "is-up" if variacion >= 0 else "is-down"
            icono = "bi-caret-up-fill" if variacion >= 0 else "bi-caret-down-fill"
            
            items.append(
                f"<span class='vq-tape-item'>"
                f"<a href='https://finance.yahoo.com/quote/{ticker}' target='_blank' style='text-decoration:none; color:inherit; display:flex; gap:0.42rem; align-items:center;'>"
                f"<strong>{html.escape(nombre)}</strong> "
                f"<span>${precio:,.2f}</span> "
                f"<span class='{clase}'><i class='bi {icono}'></i> {variacion:+.2f}%</span>"
                f"</a></span>"
            )
        except Exception:
            continue

    if not items:
        items = [
            "<span class='vq-tape-item'><strong>SPY</strong> <span>$--</span> <span class='is-flat'>Mercado pendiente</span></span>",
            "<span class='vq-tape-item'><strong>NVDA</strong> <span>$--</span> <span class='is-flat'>Datos no disponibles</span></span>",
        ]
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


@st.cache_data(ttl=86400) # Se guarda en memoria durante 24 horas
def analizar_rotacion_sectores():
    """Descarga el rendimiento de los 11 sectores del S&P 500 usando sus ETFs"""
    etfs = {
        '💻 Tecnología': 'XLK', '💊 Salud': 'XLV', '🏦 Finanzas': 'XLF',
        '🛍️ Cons. Discrecional': 'XLY', '🍞 Cons. Básico': 'XLP', '🛢️ Energía': 'XLE',
        '🏭 Industriales': 'XLI', '🧱 Materiales': 'XLB', '🏠 Inmobiliario': 'XLRE',
        '⚡ Utilities': 'XLU', '📡 Comunicaciones': 'XLC'
    }
    datos = []
    for sector, ticker_etf in etfs.items():
        try:
            # Descargamos 3 meses de historia de cada ETF
            hist = yf.Ticker(ticker_etf).history(period="3mo")
            if len(hist) >= 21: # 21 días laborables = 1 mes
                p_actual = hist['Close'].iloc[-1]
                p_1m = hist['Close'].iloc[-21]
                p_3m = hist['Close'].iloc[0]
                
                r_1m = ((p_actual - p_1m) / p_1m) * 100
                r_3m = ((p_actual - p_3m) / p_3m) * 100
                
                datos.append({'Sector': sector, '1 Mes (%)': r_1m, '3 Meses (%)': r_3m})
        except:
            continue
            
    return pd.DataFrame(datos) if datos else None


@st.cache_data(ttl=600, show_spinner=False)
def obtener_market_snapshot() -> list[dict[str, str]]:
    """Obtiene una lectura breve de mercado para la pantalla Home, incluyendo indicadores macro."""
    activos = {
        "SPY": "SPY", 
        "Nasdaq": "QQQ", 
        "Oro": "GC=F", 
        "Petróleo": "CL=F", 
        "NVDA": "NVDA", 
        "AAPL": "AAPL",
        "VIX": "^VIX",
        "US 10Y": "^TNX"
    }
    snapshot: list[dict[str, str]] = []
    for nombre, ticker in activos.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            close = hist["Close"].dropna()
            if len(close) < 2:
                continue
            precio = float(close.iloc[-1])
            cambio = ((precio - float(close.iloc[-2])) / float(close.iloc[-2])) * 100
            
            if ticker in ["^VIX", "^TNX"]:
                precio_str = f"{precio:,.2f}" if ticker == "^VIX" else f"{precio:.2f}%"
            else:
                precio_str = f"${precio:,.2f}"
                
            snapshot.append({
                "nombre": nombre, 
                "precio": precio_str, 
                "change_val": cambio,
                "cambio": f"{cambio:+.2f}%", 
                "clase": "is-up" if cambio >= 0 else "is-down"
            })
        except Exception:
            continue
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
            hist = yf_ticker.history(period="5d", interval="1d", auto_adjust=False)
            close = hist["Close"].dropna() if hist is not None and not hist.empty and "Close" in hist.columns else pd.Series(dtype=float)
            if len(close) < 2:
                continue
            info = getattr(yf_ticker, "fast_info", {}) or {}
            market_cap = info.get("market_cap") if hasattr(info, "get") else None
            if not market_cap:
                market_cap = (yf_ticker.info or {}).get("marketCap")
            if not market_cap:
                continue
            daily_return = ((float(close.iloc[-1]) - float(close.iloc[-2])) / float(close.iloc[-2])) * 100
            rows.append({"Ticker": ticker, "Sector": sector, "MarketCap": float(market_cap), "Rendimiento_Diario": daily_return})
        except Exception as exc:
            print(f"[ValueQuant][Treemap] {ticker} omitido: {type(exc).__name__}: {exc}")
            continue
    return pd.DataFrame(rows, columns=["Ticker", "Sector", "MarketCap", "Rendimiento_Diario"])


@st.cache_data(ttl=1800, show_spinner=False)
def obtener_ultimas_noticias(limit: int = 6) -> list[dict[str, str]]:
    """Descarga noticias recientes desde FMP con logging de diagnóstico y Yahoo RSS como respaldo."""
    noticias: list[dict[str, str]] = []
    logger = logging.getLogger("valuequant.news")

    try:
        clave_api = CONFIG.fmp_api_key
        if not clave_api:
            raise RuntimeError("FMP_API_KEY no configurada")

        url = "https://financialmodelingprep.com/api/v3/stock_news"
        params = {"tickers": "AAPL,MSFT,NVDA,SPY,QQQ", "limit": limit, "apikey": clave_api}
        headers = {"User-Agent": "ValueQuantTerminal/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"[ValueQuant][FMP news] status={response.status_code} url={response.url}")
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            print(f"[ValueQuant][FMP news] JSON inesperado: {data}")
            logger.warning("FMP stock_news devolvió un JSON no-list: %s", data)
        elif not data:
            print("[ValueQuant][FMP news] Lista vacía desde FMP.")
        else:
            print(f"[ValueQuant][FMP news] primer item crudo: {data[0]}")
            for item in data[:limit]:
                if not isinstance(item, dict):
                    print(f"[ValueQuant][FMP news] item ignorado por tipo inválido: {item}")
                    continue
                img_src = _normalizar_url_imagen_noticia(item)
                if not img_src:
                    print(f"[ValueQuant][FMP news] noticia sin miniatura válida. keys={list(item.keys())} title={item.get('title')}")
                noticias.append({
                    "title": str(item.get("title") or item.get("headline") or "Noticia financiera"),
                    "date": str(item.get("publishedDate") or item.get("publishedAt") or item.get("date") or "")[:16],
                    "image": img_src,
                    "url": str(item.get("url") or item.get("link") or "#"),
                })
    except Exception as exc:
        print(f"[ValueQuant][FMP news] ERROR exacto: {type(exc).__name__}: {exc}")
        logger.exception("Error descargando noticias FMP")
        noticias = []

    if noticias:
        return noticias[:limit]

    try:
        rss_url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY,QQQ,AAPL&region=US&lang=en-US"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        rss = requests.get(rss_url, headers=headers, timeout=8)
        print(f"[ValueQuant][Yahoo RSS] status={rss.status_code} url={rss.url}")
        rss.raise_for_status()
        root = ET.fromstring(rss.content)
        for item in root.findall("./channel/item")[:limit]:
            noticias.append({
                "title": item.findtext("title") or "Noticia financiera",
                "date": item.findtext("pubDate") or "",
                "image": "",
                "url": item.findtext("link") or "#",
            })
    except Exception as exc:
        print(f"[ValueQuant][Yahoo RSS] ERROR exacto: {type(exc).__name__}: {exc}")
        logger.exception("Error descargando noticias Yahoo RSS")

    return noticias[:limit]

