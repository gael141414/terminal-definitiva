import streamlit as st
import yfinance as yf
import streamlit.components.v1 as components
from textblob import TextBlob
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from modulos.fmp_api import extraer_datos_fundamentales_fmp

@st.cache_data(ttl=3600, show_spinner=False)
def obtener_transacciones_insiders(ticker):
    """Descarga las últimas compras/ventas de los directivos (Form 4)"""
    try:
        ticker_yf = yf.Ticker(ticker)
        transacciones = ticker_yf.insider_transactions
        
        if transacciones is not None and not transacciones.empty:
            cols_deseadas = ['Start Date', 'Insider', 'Position', 'Transaction', 'Value', 'Shares']
            cols_presentes = [c for c in cols_deseadas if c in transacciones.columns]
            
            df_limpio = transacciones[cols_presentes].copy()
            if 'Start Date' in df_limpio.columns:
                df_limpio['Start Date'] = pd.to_datetime(df_limpio['Start Date']).dt.strftime('%Y-%m-%d')
                
            return df_limpio.head(15)
        return None
    except Exception:
        return None

PALABRAS_POSITIVAS_FINANCIERAS = (
    "beat", "beats", "surge", "surges", "upgrade", "upgrades", "raises", "record",
    "profit", "profits", "growth", "strong", "outperform", "approval", "approved",
    "partnership", "launch", "launches", "guidance raised", "buy rating",
)

PALABRAS_NEGATIVAS_FINANCIERAS = (
    "miss", "misses", "downgrade", "downgrades", "falls", "plunges", "slump",
    "lawsuit", "probe", "investigation", "loss", "losses", "bankruptcy", "dilution",
    "offering", "weak", "cuts guidance", "layoffs", "sec charges", "warning",
)


def _extraer_url(valor):
    if isinstance(valor, dict):
        return valor.get("url") or valor.get("link") or ""
    return valor if isinstance(valor, str) else ""


def _normalizar_noticia_yahoo(noticia: dict) -> dict[str, str] | None:
    content = noticia.get("content") if isinstance(noticia.get("content"), dict) else {}
    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}

    titulo = (
        noticia.get("title")
        or content.get("title")
        or content.get("headline")
        or ""
    ).strip()
    if not titulo:
        return None

    fuente = (
        noticia.get("publisher")
        or provider.get("displayName")
        or provider.get("name")
        or content.get("publisher")
        or "Yahoo Finance"
    )
    enlace = (
        noticia.get("link")
        or _extraer_url(content.get("clickThroughUrl"))
        or _extraer_url(content.get("canonicalUrl"))
        or ""
    )
    return {"Titular": titulo, "Fuente": str(fuente), "Link": enlace}


def _descargar_noticias_yahoo_rss(ticker: str) -> list[dict[str, str]]:
    try:
        url = "https://feeds.finance.yahoo.com/rss/2.0/headline"
        response = requests.get(
            url,
            params={"s": ticker.upper(), "region": "US", "lang": "en-US"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        noticias = []
        for item in root.findall(".//item")[:10]:
            titulo = (item.findtext("title") or "").strip()
            enlace = (item.findtext("link") or "").strip()
            fuente = (item.findtext("source") or "Yahoo Finance").strip()
            if titulo:
                noticias.append({"Titular": titulo, "Fuente": fuente, "Link": enlace})
        return noticias
    except Exception:
        return []


def _polaridad_financiera(titulo: str) -> float:
    texto = titulo.lower()
    polaridad = TextBlob(titulo).sentiment.polarity
    ajuste = 0.0
    for palabra in PALABRAS_POSITIVAS_FINANCIERAS:
        if palabra in texto:
            ajuste += 0.12
    for palabra in PALABRAS_NEGATIVAS_FINANCIERAS:
        if palabra in texto:
            ajuste -= 0.12
    return max(min(float(polaridad + ajuste), 1.0), -1.0)


@st.cache_data(ttl=3600, show_spinner=False)
def analizar_sentimiento_noticias(ticker):
    """Extrae noticias recientes y calcula sentimiento financiero robusto."""
    try:
        noticias_normalizadas = []

        try:
            noticias_yf = yf.Ticker(ticker).news or []
        except Exception:
            noticias_yf = []

        for noticia in noticias_yf:
            if isinstance(noticia, dict):
                normalizada = _normalizar_noticia_yahoo(noticia)
                if normalizada:
                    noticias_normalizadas.append(normalizada)

        if len(noticias_normalizadas) < 3:
            noticias_normalizadas.extend(_descargar_noticias_yahoo_rss(ticker))

        noticias_unicas = []
        vistos = set()
        for noticia in noticias_normalizadas:
            clave = noticia["Titular"].lower()
            if clave in vistos:
                continue
            vistos.add(clave)
            noticias_unicas.append(noticia)

        if not noticias_unicas:
            return None, 0

        resultados = []
        polaridad_total = 0.0

        for noticia in noticias_unicas[:8]:
            titulo = noticia["Titular"]
            polaridad = _polaridad_financiera(titulo)
            estado = "Neutral ⚖️"
            if polaridad > 0.12:
                estado = "Alcista 🟢"
            elif polaridad < -0.12:
                estado = "Bajista 🔴"

            polaridad_total += polaridad
            resultados.append({
                "Titular": titulo,
                "Fuente": noticia.get("Fuente") or "N/D",
                "Sentimiento": estado,
                "Polaridad": polaridad,
                "Link": noticia.get("Link") or "#",
            })

        polaridad_media = polaridad_total / len(resultados) if resultados else 0
        return resultados, polaridad_media
    except Exception:
        return None, 0

def renderizar_grafico_tradingview(ticker):
    """Inyecta el widget avanzado y nativo de TradingView interactivo"""
    ticker_tv = ticker.replace("-", ".") 
    codigo_html = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_container" style="height:600px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
      "autosize": true, "symbol": "{ticker_tv}", "interval": "D", "timezone": "Etc/UTC",
      "theme": "dark", "style": "1", "locale": "es", "enable_publishing": false,
      "backgroundColor": "#0b0e14", "gridColor": "#1f293d", "hide_top_toolbar": false,
      "hide_legend": false, "save_image": false, "container_id": "tv_chart_container",
      "toolbar_bg": "#131722", "studies": ["Volume@tv-basicstudies", "MASimple@tv-basicstudies"]
      }});
      </script>
    </div>
    """
    components.html(codigo_html, height=600)

@st.cache_data(ttl=86400, show_spinner=False)
def obtener_valoracion_sectorial(ticker):
    """Aplica la regla de valoración relativa según el sector"""
    try:
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'Desconocido')
        multiplos = {
            'P/E (Price/Earnings)': info.get('trailingPE', 0),
            'P/B (Price/Book)': info.get('priceToBook', 0),
            'EV / EBITDA': info.get('enterpriseToEbitda', 0),
            'EV / Ventas': info.get('enterpriseToRevenue', 0)
        }
        for k, v in multiplos.items():
            if v is None: multiplos[k] = 0
            
        metrica_clave = 'P/E (Price/Earnings)'
        racionalidad = "Para empresas maduras, las ganancias netas estables son el mejor indicador de valor."
        umbral_barato = 15.0
        
        if sector in ['Technology', 'Communication Services']:
            metrica_clave, umbral_barato, racionalidad = 'EV / Ventas', 5.0, "En tecnología se valora el crecimiento y captura de mercado."
        elif sector in ['Financial Services', 'Real Estate']:
            metrica_clave, umbral_barato, racionalidad = 'P/B (Price/Book)', 1.2, "Un ratio menor a 1 indica compras con descuento."
        elif sector in ['Industrials', 'Basic Materials', 'Energy', 'Utilities']:
            metrica_clave, umbral_barato, racionalidad = 'EV / EBITDA', 10.0, "Elimina ruido de amortizaciones de maquinaria."
            
        valor_metrica = multiplos.get(metrica_clave, 0)
        return sector, metrica_clave, valor_metrica, racionalidad, multiplos, umbral_barato
    except Exception as e:
        return None, None, 0, str(e), {}, 0

@st.cache_data(ttl=86400, show_spinner=False)
def obtener_datos_directiva(ticker):
    """Extrae qué porcentaje de la empresa tienen los directivos y fondos"""
    try:
        info = yf.Ticker(ticker).info
        return info.get('heldPercentInsiders', 0) * 100, info.get('heldPercentInstitutions', 0) * 100, info.get('shortRatio', 0)
    except:
        return 0, 0, 0

def escanear_vulnerabilidades(res_is, res_bs, res_cf):
    """Escanea los estados financieros en busca de Red Flags críticas."""
    alertas = []
    
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else None
        return None

    # 1. Riesgo de Quiebra (Deuda)
    deuda_cap = get_last(res_bs["ratios"], "Deuda / Capital")
    if deuda_cap and deuda_cap > 1.2:
        alertas.append(f"🚨 **Apalancamiento Peligroso:** Deuda altísima ({deuda_cap:.2f}x el capital).")

    # 2. Hemorragia de Efectivo
    fcf = get_last(res_cf["ratios"], "Free Cash Flow (B USD)")
    if fcf and fcf < 0:
        alertas.append(f"🔥 **Quema de Caja:** El Free Cash Flow es negativo (${fcf:.2f}B).")

    # 3. Rentabilidad Basura (Márgenes)
    margen_neto = get_last(res_is["ratios"], "Margen Neto %")
    if margen_neto and margen_neto < 5:
        alertas.append(f"⚠️ **Márgenes Críticos:** El margen neto es solo del {margen_neto:.1f}%.")

    # 4. Destrucción de Valor (ROIC)
    roic = get_last(res_bs["ratios"], "ROIC %")
    if roic and roic < 7:
        alertas.append(f"📉 **Destrucción de Capital:** El ROIC ({roic:.1f}%) es menor que el coste de capital promedio.")

    return alertas

def render_tradingview_widget(ticker):
    """Inyecta el terminal avanzado interactivo de TradingView mediante iframe"""
    ticker_tv = ticker.replace("-", ".") 
    html_code = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tradingview_terminal" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true, "symbol": "{ticker_tv}", "interval": "D", "timezone": "exchange",
      "theme": "dark", "style": "1", "locale": "es", "enable_publishing": false,
      "backgroundColor": "#0b1426", "gridColor": "#1e3354", "hide_top_toolbar": false,
      "hide_legend": false, "save_image": false, "container_id": "tradingview_terminal",
      "toolbar_bg": "#0b1426"
      }});
      </script>
    </div>
    """
    import streamlit.components.v1 as components
    components.html(html_code, height=600)

def cargar_datos(ticker: str, años: int):
    try:
        resultado = extraer_datos_fundamentales_fmp(ticker, años)

        # Evita que un fallo transitorio de red/API quede congelado en cache 24h.
        if resultado[0] is None:
            try:
                extraer_datos_fundamentales_fmp.clear()
            except Exception:
                pass
            resultado = extraer_datos_fundamentales_fmp(ticker, años)

        return resultado
    except Exception as e:
        st.error(f"Error descargando datos desde FMP: {e}")
        return None, None, None, None

def calcular_score_buffett(df_is, df_bs, df_cf):
    """Calcula una nota del 0 al 100 basada en las reglas estrictas de Buffett"""
    score = 0
    
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else None
        return None

    mb = get_last(df_is, "Margen Bruto %")
    mn = get_last(df_is, "Margen Neto %")
    roe = get_last(df_bs, "ROE %")
    roic = get_last(df_bs, "ROIC %")
    deuda = get_last(df_bs, "Deuda / Capital")
    capex = get_last(df_cf, "CAPEX % sobre Beneficio")
    fcf = get_last(df_cf, "Free Cash Flow (B USD)")
    buybacks = get_last(df_cf, "Recompras (B USD)")

    # 1. Poder de Precios (25 pts)
    if mb and mb > 40: score += 10
    elif mb and mb > 20: score += 5
    if mn and mn > 20: score += 15
    elif mn and mn > 10: score += 7

    # 2. Eficiencia (30 pts)
    if roe and roe > 15: score += 15
    if roic and roic > 15: score += 15

    # 3. Solidez (25 pts)
    if deuda is not None and deuda < 0.8: score += 15
    elif deuda is not None and deuda < 1.5: score += 7
    if capex is not None and capex < 25: score += 10
    elif capex is not None and capex < 50: score += 5

    # 4. Trato al Accionista (20 pts)
    if fcf and fcf > 0: score += 10
    if buybacks and buybacks > 0: score += 10

    return score
