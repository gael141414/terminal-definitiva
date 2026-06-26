import streamlit as st

st.set_page_config(
    page_title="ValueQuant Terminal",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import tempfile
import requests
import streamlit.components.v1 as components
import os
import logging
import base64
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta, time

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from fpdf import FPDF
except Exception:
    FPDF = None

try:
    from streamlit_option_menu import option_menu
except Exception:
    option_menu = None

try:
    from textblob import TextBlob
except Exception:
    TextBlob = None

try:
    from streamlit_lottie import st_lottie
except Exception:
    def st_lottie(*args, **kwargs):
        return None

from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from valuator import valorar_empresa
from modulos.config import CONFIG
from modulos.app_assets import asset_to_data_uri, strip_visual_prefix
from modulos.app_theme import inject_terminal_theme
from modulos.app_navigation import (
    BLOQUE_UI,
    TOOL_UI_ICONS,
    render_context_header,
    render_option_menu_safe,
)
from modulos.app_runtime import build_runtime_paths
from modulos.module_loader import safe_call
from modulos.utils import cargar_datos, calcular_score_buffett, analizar_sentimiento_noticias as analizar_sentimiento_noticias_utils
from modulos.scoring_engine import calcular_valuequant_score
from modulos.fmp_api import diagnosticar_conexion_fmp
from modulos.ui_components import render_kpi_card
from modulos.tool_catalog import (
    TOOL_CATALOG,
    BLOQUES_HERRAMIENTAS,
    HERRAMIENTAS_POR_LABEL,
    obtener_bloques_por_modo,
    obtener_herramientas_por_bloque,
    obtener_herramientas_por_bloque_y_modo,
    obtener_modos_navegacion,
)
from modulos.tool_router import CompanyToolContext, render_company_tool, render_independent_tool


def inyectar_atajo_teclado():
    """Inyecta un listener global de JavaScript para el atajo Ctrl+K / Cmd+K"""
    js_code = """
    <script>
    const doc = window.parent.document;
    
    // Evitamos duplicar listeners si Streamlit recarga la página
    if (!doc.getElementById('vq-keyboard-listener')) {
        const scriptTag = doc.createElement('div');
        scriptTag.id = 'vq-keyboard-listener';
        scriptTag.style.display = 'none';
        doc.body.appendChild(scriptTag);

        doc.addEventListener('keydown', function(e) {
            // Detecta Ctrl+K en Windows/Linux o Cmd+K en Mac
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault(); // Evita que el navegador abra su propio buscador
                
                // Busca el input dentro del primer selectbox de Streamlit (El buscador de Empresa)
                const inputs = doc.querySelectorAll('.stSelectbox input');
                if (inputs.length > 0) {
                    inputs[0].focus();
                    
                    // Efecto visual: Resalta la barra momentáneamente
                    const container = inputs[0].closest('div[data-baseweb="select"]');
                    if (container) {
                        const originalBoxShadow = container.style.boxShadow;
                        container.style.boxShadow = '0 0 0 3px rgba(59, 130, 246, 0.6)';
                        setTimeout(() => {
                            container.style.boxShadow = originalBoxShadow;
                        }, 400);
                    }
                }
            }
        });
    }
    </script>
    """
    # Inyectamos el HTML sin que ocupe espacio visual en la web
    components.html(js_code, height=0, width=0)

def load_lottieurl(url: str):
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException:
        return None

# ---------------- CONFIGURACIÓN ---------------- #
# 1. CONFIGURACIÓN DE PÁGINA movida al inicio del archivo para cumplir Streamlit.

def obtener_secreto_streamlit(nombre: str):
    """Lee un secreto sin bloquear la app cuando no existe secrets.toml."""
    try:
        return st.secrets.get(nombre)
    except Exception:
        return None

@st.cache_resource(show_spinner=False)
def obtener_modelo_gemini():
    """Inicializa Gemini una sola vez y evita repetir list_models en cada prompt."""
    api_key = CONFIG.gemini_api_key or CONFIG.google_api_key
    if not api_key:
        return None

    if genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        modelo_disponible = None
        for modelo in genai.list_models():
            if 'generateContent' in modelo.supported_generation_methods:
                modelo_disponible = modelo.name
                if "flash" in modelo.name.lower():
                    break
        return genai.GenerativeModel(modelo_disponible) if modelo_disponible else None
    except Exception:
        return None

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

# ==========================================
# MARKET TICKER TAPE FIJO
# ==========================================
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

# ---------------- DATA LOADER ---------------- #
def obtener_transacciones_insiders(ticker):
    """Descarga las últimas compras/ventas de los directivos (Form 4)"""
    try:
        import pandas as pd
        ticker_yf = yf.Ticker(ticker)
        transacciones = ticker_yf.insider_transactions
        
        if transacciones is not None and not transacciones.empty:
            # Seleccionamos columnas útiles si están disponibles
            cols_deseadas = ['Start Date', 'Insider', 'Position', 'Transaction', 'Value', 'Shares']
            cols_presentes = [c for c in cols_deseadas if c in transacciones.columns]
            
            df_limpio = transacciones[cols_presentes].copy()
            # Formatear la fecha para que sea legible
            if 'Start Date' in df_limpio.columns:
                df_limpio['Start Date'] = pd.to_datetime(df_limpio['Start Date']).dt.strftime('%Y-%m-%d')
                
            return df_limpio.head(15) # Devolvemos las 15 más recientes
        return None
    except Exception as e:
        return None

@st.cache_data(ttl=86400 * 7) # Se actualiza 1 vez a la semana
def obtener_tickers_filtrados():
    """Descarga la lista de la SEC y filtra ETFs, SPACS y empresas extranjeras"""
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {'User-Agent': 'ValueQuant Terminal (contacto@valuequant.com)'} 
        r = requests.get(url, headers=headers, timeout=5)
        datos = r.json()
        
        # 🛡️ FILTRO ANTI-BASURA EXTREMO
        filtros_basura = [
            " ADR", " LTD", " LIMITED", " PLC", " S.A.", " N.V.", 
            " FUND", " TRUST", " ETF", " ACQUISITION", " SPAC",
            " BLANK CHECK", " BANCORP" # Añadimos más filtros de Wall Street
        ]
        
        lista_formateada = []
        for v in datos.values():
            nombre_mayus = str(v['title']).upper()
            
            if not any(basura in nombre_mayus for basura in filtros_basura):
                lista_formateada.append(f"{v['ticker']} - {v['title'].title()}")
                
        return sorted(lista_formateada)
    except Exception as e:
        return ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]

# ==========================================
# WIDGET RADICAL 2: MOTOR TRADINGVIEW EN VIVO
# ==========================================
def render_tradingview_widget(ticker):
    """Inyecta el terminal avanzado interactivo de TradingView mediante iframe"""
    
    # Algunos tickers de Yahoo Finance (ej. BRK-B) necesitan limpieza para TradingView
    ticker_tv = ticker.replace("-", ".") 
    
    html_code = f"""
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tradingview_terminal" style="height:calc(100% - 32px);width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true,
      "symbol": "{ticker_tv}",
      "interval": "D",
      "timezone": "exchange",
      "theme": "dark",
      "style": "1",
      "locale": "es",
      "enable_publishing": false,
      "backgroundColor": "#0b1426",
      "gridColor": "#1e3354",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tradingview_terminal",
      "toolbar_bg": "#0b1426"
    }}
      );
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    # Renderizamos el HTML incrustado con una altura de 600 píxeles
    components.html(html_code, height=600)

def renderizar_grafico_tradingview(ticker):
    """Inyecta el widget avanzado y nativo de TradingView interactivo"""
    codigo_html = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_container" style="height:600px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
      "autosize": true,
      "symbol": "{ticker}",
      "interval": "D",
      "timezone": "Etc/UTC",
      "theme": "dark",
      "style": "1",
      "locale": "es",
      "enable_publishing": false,
      "backgroundColor": "#0b0e14",
      "gridColor": "#1f293d",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tv_chart_container",
      "toolbar_bg": "#131722",
      "studies": [
        "Volume@tv-basicstudies",
        "MASimple@tv-basicstudies"
      ]
    }}
      );
      </script>
    </div>
    """
    components.html(codigo_html, height=600)

def obtener_valoracion_sectorial(ticker):
    """Aplica la regla de valoración relativa según el sector (Basado en el marco institucional)"""
    try:
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'Desconocido')
        
        # Rescatamos todos los múltiplos posibles
        multiplos = {
            'P/E (Price/Earnings)': info.get('trailingPE', 0),
            'P/B (Price/Book)': info.get('priceToBook', 0),
            'EV / EBITDA': info.get('enterpriseToEbitda', 0),
            'EV / Ventas': info.get('enterpriseToRevenue', 0)
        }
        
        # Limpiamos nulos
        for k, v in multiplos.items():
            if v is None: multiplos[k] = 0
            
        # Lógica de Selección Institucional
        metrica_clave = 'P/E (Price/Earnings)' # Métrica por defecto
        racionalidad = "Para empresas maduras, las ganancias netas estables son el mejor indicador de valor."
        umbral_barato = 15.0
        
        if sector in ['Technology', 'Communication Services']:
            metrica_clave = 'EV / Ventas'
            racionalidad = "En tecnología y software, se valora el crecimiento y la captura de mercado (Top-Line). Muchas reinvierten todo y no tienen beneficio neto hoy."
            umbral_barato = 5.0
            
        elif sector in ['Financial Services', 'Real Estate']:
            metrica_clave = 'P/B (Price/Book)'
            racionalidad = "En bancos y aseguradoras, los activos financieros son un proxy directo del valor. Un ratio menor a 1 indica que compras sus activos con descuento."
            umbral_barato = 1.2
            
        elif sector in ['Industrials', 'Basic Materials', 'Energy', 'Utilities']:
            metrica_clave = 'EV / EBITDA'
            racionalidad = "En industria pesada, elimina el ruido de las agresivas políticas de amortización de maquinaria y diferencias impositivas."
            umbral_barato = 10.0
            
        elif sector in ['Consumer Defensive', 'Healthcare']:
            metrica_clave = 'P/E (Price/Earnings)'
            racionalidad = "Sectores estables y predecibles. El mercado paga por la seguridad del beneficio neto constante."
            umbral_barato = 15.0
            
        valor_metrica = multiplos.get(metrica_clave, 0)
        
        return sector, metrica_clave, valor_metrica, racionalidad, multiplos, umbral_barato
        
    except Exception as e:
        return None, None, 0, str(e), {}, 0

def escanear_vulnerabilidades(res_is, res_bs, res_cf):
    """Escanea los estados financieros en busca de Red Flags críticas."""
    alertas = []
    
    # Función auxiliar rápida
    def get_last(df, col):
        if df is not None and col in df.columns:
            s = df[col].dropna()
            return s.iloc[-1] if not s.empty else None
        return None

    # 1. Riesgo de Quiebra (Deuda)
    deuda_cap = get_last(res_bs["ratios"], "Deuda / Capital")
    if deuda_cap and deuda_cap > 1.2:
        alertas.append(f"🚨 **Apalancamiento Peligroso:** Deuda altísima ({deuda_cap:.2f}x el capital). Muy vulnerable a subidas de tipos de interés.")

    # 2. Hemorragia de Efectivo
    fcf = get_last(res_cf["ratios"], "Free Cash Flow (B USD)")
    if fcf and fcf < 0:
        alertas.append(f"🔥 **Quema de Caja:** El Free Cash Flow es negativo (${fcf:.2f}B). La empresa está perdiendo dinero real y podría necesitar emitir acciones o más deuda.")

    # 3. Rentabilidad Basura (Márgenes)
    margen_neto = get_last(res_is["ratios"], "Margen Neto %")
    if margen_neto and margen_neto < 5:
        alertas.append(f"⚠️ **Márgenes Críticos:** El margen neto es solo del {margen_neto:.1f}%. La empresa no tiene poder de fijación de precios (Moat débil).")

    # 4. Destrucción de Valor (ROIC)
    roic = get_last(res_bs["ratios"], "ROIC %")
    if roic and roic < 7:
        alertas.append(f"📉 **Destrucción de Capital:** El ROIC ({roic:.1f}%) es menor que el coste de capital promedio. Crecer destruye valor para el accionista.")

    return alertas

def analizar_sentimiento_noticias(ticker):
    """Compatibilidad: delega en el motor NLP robusto de modulos.utils."""
    return analizar_sentimiento_noticias_utils(ticker)

def generar_reporte_pdf(ticker, precio, res_val, nota, fcf_yield, buyback_yield):
    """Genera un informe institucional en PDF de 1 página (Tear Sheet)"""
    if FPDF is None:
        raise RuntimeError("fpdf2 no está instalado. Instálalo o desactiva la exportación PDF.")

    pdf = FPDF()
    pdf.add_page()
    
    # --- CABECERA ---
    pdf.set_fill_color(31, 119, 180) # Azul corporativo
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 22)
    pdf.cell(0, 18, f" TEAR SHEET VALUE: {ticker} ", ln=True, align='C', fill=True)
    
    pdf.set_text_color(100, 100, 100)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 8, "Generado por Buffett Terminal Analytics (IA Cuantitativa)", ln=True, align='C')
    pdf.ln(5)
    
    # --- 1. SCORE GENERAL ---
    color_score = (44, 160, 44) if nota >= 80 else (255, 127, 14) if nota >= 50 else (214, 39, 40)
    pdf.set_fill_color(*color_score)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 12, f" CALIDAD FUNDAMENTAL (BUFFETT SCORE): {nota} / 100 ", ln=True, align='C', fill=True)
    pdf.ln(8)
    
    # --- 2. VALORACIÓN Y MARGEN DE SEGURIDAD ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "1. Valoracion Intrinseca (Modelo DCF Automizado)", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y()) # Línea separadora
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    if res_val and precio:
        g = res_val.get('crecimiento_sostenible', 0.05)
        r = res_val.get('tasa_descuento_capm', 0.10)
        eps = res_val.get('eps_actual', 0)
        per = res_val.get('per_asumido', 15)
        
        v_i = (eps * ((1 + g)**10) * per) / ((1 + r)**10)
        margen = ((precio - v_i) / v_i) * 100
        estado = "SOBREVALORADA" if margen > 0 else "INFRAVALORADA (Ganga)"
        
        pdf.cell(90, 8, f"Precio Mercado Hoy: ${precio:.2f}")
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 8, f"Valor Intrinseco Justo: ${v_i:.2f}", ln=True)
        pdf.set_font("Arial", '', 11)
        
        pdf.cell(90, 8, f"Crecimiento asig. (g): {g*100:.1f}%")
        pdf.cell(0, 8, f"Tasa Descuento (CAPM): {r*100:.1f}%", ln=True)
        
        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(*((214,39,40) if margen > 0 else (44,160,44)))
        pdf.cell(0, 10, f">> ESTADO ACTUAL: {estado} ({abs(margen):.1f}%)", ln=True)
    else:
        pdf.cell(0, 8, "Datos insuficientes para valoracion matematica.", ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)
    
    # --- 3. RETORNO AL ACCIONISTA ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "2. Retribucion Real al Accionista", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    total_yield = fcf_yield + buyback_yield
    pdf.cell(0, 8, f"- FCF Yield (Caja libre sobre precio): {fcf_yield:.2f}%", ln=True)
    pdf.cell(0, 8, f"- Buyback Yield (Recompra de acciones): {buyback_yield:.2f}%", ln=True)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f">> RENDIMIENTO TOTAL EFECTIVO: {total_yield:.2f}%", ln=True)
    pdf.ln(8)
    
    # --- 4. VEREDICTO ---
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "3. Veredicto del Algoritmo Value", ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    pdf.set_font("Arial", '', 11)
    if nota >= 80:
        texto = "EXCELENTE. Foso economico inquebrantable, rentabilidad sobresaliente y deuda controlada. Un claro candidato para mantener a largo plazo al estilo Berkshire Hathaway."
    elif nota >= 50:
        texto = "PRECAUCION. Negocio solido pero presenta debilidades en margenes, niveles de deuda, o su cotizacion exige demasiado crecimiento futuro. Mantener en el radar."
    else:
        texto = "ALERTA ROJA. Fundamentales deteriorados. Alta probabilidad de destruccion de valor por mala asignacion de capital o deuda asfixiante."
        
    pdf.multi_cell(0, 6, texto)
    
    # Guardar en memoria y devolver bytes en lugar de fugar almacenamiento en disco
    try:
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
    except TypeError:
        # Para versiones modernas de fpdf2 que retornan bytearray
        pdf_bytes = bytes(pdf.output())
    return pdf_bytes

@st.cache_data(show_spinner=False)
def obtener_datos_directiva(ticker):
    """Extrae qué porcentaje de la empresa tienen los directivos y fondos"""
    try:
        info = yf.Ticker(ticker).info
        insiders = info.get('heldPercentInsiders', 0) * 100
        instituciones = info.get('heldPercentInstitutions', 0) * 100
        short_ratio = info.get('shortRatio', 0)
        return insiders, instituciones, short_ratio
    except:
        return None, None, None

def ultimo_ratio(resultado, columna):
    """Extrae el último dato no nulo de un dataframe o diccionario de ratios."""
    try:
        df = resultado.get("ratios") if isinstance(resultado, dict) else resultado
        if df is not None and columna in df.columns:
            serie = df[columna].dropna()
            return serie.iloc[-1] if not serie.empty else None
    except Exception:
        return None
    return None

# ---------------- TERMINAL UI 2026: ASSETS, CSS, HOME Y NAVEGACIÓN ---------------- #
RUNTIME_PATHS = build_runtime_paths(__file__)
APP_DIR = RUNTIME_PATHS.app_dir
LOGO_PATH = RUNTIME_PATHS.logo_path
HOME_BG_PATH = RUNTIME_PATHS.home_bg_path
FMP_API_KEY = CONFIG.fmp_api_key

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

def render_module_showcase(limit: int = 9) -> None:
    """Muestra módulos principales en la home como tarjetas de producto."""
    destacados = TOOL_CATALOG[:limit]

    cards = ""
    for tool in destacados:
        label_original = tool["label"]
        label = strip_visual_prefix(label_original)
        icon = TOOL_UI_ICONS.get(label_original, "grid")
        bloque = strip_visual_prefix(tool["bloque"])
        desc = tool["descripcion"]
        input_mode = tool["input_mode"]

        if input_mode == "company":
            mode_label = "Empresa"
        elif input_mode == "standalone":
            mode_label = "Autónomo"
        elif input_mode == "etf":
            mode_label = "ETF / Fondo"
        else:
            mode_label = "Módulo"

        # HTML Compactado sin saltos de línea para evitar el Bug de Streamlit
        cards += f"<article class='vq-module-card'><div class='vq-module-icon'><i class='bi bi-{html.escape(icon)}'></i></div><div class='vq-module-eyebrow'>{html.escape(bloque)} · {html.escape(mode_label)}</div><div class='vq-module-title'>{html.escape(label)}</div><div class='vq-module-desc'>{html.escape(desc)}</div></article>"

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-grid-1x2'></i> Módulos principales</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div class='vq-module-grid'>{cards}</div>",
        unsafe_allow_html=True,
    )

def render_home_page() -> None:
    """Pantalla inicial institucional con identidad visual, mercado, estado de bolsas y termómetro sectorial."""
    logo_uri = asset_to_data_uri(LOGO_PATH)
    bg_uri = asset_to_data_uri(HOME_BG_PATH)
    bg_style = f"url('{bg_uri}')" if bg_uri else "linear-gradient(135deg, #09111f, #05070b)"
    logo_html = f"<img class='vq-home-logo' src='{logo_uri}' alt='ValueQuant Terminal'>" if logo_uri else ""

    # Hero Principal (Ajustado al margen izquierdo estricto para evitar bugs de markdown)
    st.markdown(
f"""<section class="vq-home-hero" style="--home-bg: {bg_style};">
<div class="vq-home-content">
{logo_html}
<h1 class="vq-home-title">ValueQuant Terminal</h1>
<p class="vq-home-subtitle">Research fundamental, riesgo, timing cuantitativo y automatización de alertas en una mesa de análisis unificada.</p>
</div>
</section>""",
        unsafe_allow_html=True,
    )

    # 1. RELOJES DE MERCADO (Market Status Bar)
    ahora_utc = datetime.now(timezone.utc)
    
    # NYSE: EDT (UTC-4) en mayo. Abierto: lunes a viernes de 09:30 a 16:00 local.
    ny_time = ahora_utc - timedelta(hours=4)
    ny_open = (0 <= ny_time.weekday() <= 4) and (time(9, 30) <= ny_time.time() <= time(16, 0))
    
    # LSE: BST (UTC+1) en mayo. Abierto: lunes a viernes de 08:00 a 16:30 local.
    lon_time = ahora_utc + timedelta(hours=1)
    lon_open = (0 <= lon_time.weekday() <= 4) and (time(8, 0) <= lon_time.time() <= time(16, 30))
    
    # TSE: JST (UTC+9). Abierto: lunes a viernes de 09:00-11:30 y 12:30-15:00 local.
    tok_time = ahora_utc + timedelta(hours=9)
    tok_open = (0 <= tok_time.weekday() <= 4) and (
        (time(9, 0) <= tok_time.time() <= time(11, 30)) or 
        (time(12, 30) <= tok_time.time() <= time(15, 0))
    )
    
    status_ny = "<span style='color: #36c486;'>●</span> OPEN" if ny_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"
    status_lon = "<span style='color: #36c486;'>●</span> OPEN" if lon_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"
    status_tok = "<span style='color: #36c486;'>●</span> OPEN" if tok_open else "<span style='color: #ef5b6b;'>●</span> CLOSED"

    st.markdown(
f"<div style='display: flex; gap: 2rem; justify-content: center; background: #111827; padding: 0.55rem; border-radius: 10px; border: 1px solid rgba(148, 163, 184, 0.12); margin-top: -0.6rem; margin-bottom: 1.6rem; font-size: 0.82rem; font-weight: 700; color: #93a4bb;'>"
f"<div>NYSE (New York): <strong style='color:#eef4ff;'>{status_ny}</strong></div>"
f"<div>LSE (London): <strong style='color:#eef4ff;'>{status_lon}</strong></div>"
f"<div>TSE (Tokyo): <strong style='color:#eef4ff;'>{status_tok}</strong></div>"
f"</div>",
        unsafe_allow_html=True
    )

    # 2. GRID DE MERCADO (Con VIX y US 10Y integrados)
    snapshot = obtener_market_snapshot()
    if snapshot:
        cards = "".join(
f"<article class='vq-market-card'>"
f"<div class='vq-market-label'>{html.escape(item['nombre'])}</div>"
f"<div class='vq-market-value'>{html.escape(item['precio'])}</div>"
f"<div class='{item['clase']}' style='font-weight:800; margin-top:.25rem;'>{html.escape(item['cambio'])}</div>"
f"</article>"
            for item in snapshot
        )
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-activity'></i> Resumen de mercado</h2></div>", unsafe_allow_html=True)
        st.markdown(f"<div class='vq-market-grid'>{cards}</div>", unsafe_allow_html=True)

    st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-grid-3x3-gap'></i> Mapa de calor del mercado</h2></div>", unsafe_allow_html=True)
    try:
        df_treemap = obtener_market_treemap_data()
        if df_treemap is not None and not df_treemap.empty:
            st.plotly_chart(render_market_treemap(df_treemap), use_container_width=True)
        else:
            st.info("No hay datos suficientes para construir el mapa de calor en este momento.")
    except Exception as exc:
        st.warning(f"No se pudo renderizar el mapa de calor: {exc}")

    # 3. LAYOUT DOBLE COLUMNA: NOTICIAS VS ROTACIÓN SECTORIAL
    col_noticias, col_sectores = st.columns([2.2, 1.2])

    with col_noticias:
        noticias = obtener_ultimas_noticias(6)
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-newspaper'></i> Últimas noticias financieras</h2></div>", unsafe_allow_html=True)
        if noticias:
            news_html = ""
            for noticia in noticias:
                title = html.escape(noticia.get("title", "Noticia financiera"))
                date = html.escape(noticia.get("date", ""))[:32]
                url = html.escape(noticia.get("url", "#"))
                
                image_url = noticia.get("image")
                img_src = html.escape(image_url) if image_url and len(image_url) > 5 else logo_uri
                
                # HTML Compactado con estilos in-line (object-fit: cover) para que la imagen quede perfecta
                news_html += f"<a class='vq-news-card' href='{url}' target='_blank' rel='noopener noreferrer' style='text-decoration:none;'><img src='{img_src}' alt='News image' onerror=\"this.src='{logo_uri}'\" style='width: 100%; height: 140px; object-fit: cover; border-radius: 6px 6px 0 0; border-bottom: 1px solid rgba(148, 163, 184, 0.1);'><div class='vq-news-body'><div class='vq-news-date'>{date}</div><div class='vq-news-title'>{title}</div></div></a>"
                
            st.markdown(f"<div class='vq-news-grid'>{news_html}</div>", unsafe_allow_html=True)

    with col_sectores:
        st.markdown("<div class='vq-section-title'><h2 style='margin:0;'><i class='bi bi-pie-chart-fill'></i> Rotación Sectorial (1 Mes)</h2></div>", unsafe_allow_html=True)
        try:
            df_sectores = analizar_rotacion_sectores() # Llama a la función de tu ecosistema
            if df_sectores is not None and not df_sectores.empty:
                df_plot = df_sectores.sort_values(by="1 Mes (%)", ascending=True)
                colores = ["#36c486" if x >= 0 else "#ef5b6b" for x in df_plot["1 Mes (%)"]]
                
                fig = go.Figure(go.Bar(
                    x=df_plot["1 Mes (%)"],
                    y=df_plot["Sector"],
                    orientation='h',
                    marker_color=colores,
                    text=df_plot["1 Mes (%)"].round(2).astype(str) + "%",
                    textposition='auto',
                    hovertemplate="Sector: %{y}<br>Rendimiento: %{x:.2f}%<extra></extra>"
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(family="Inter", color="#CBD5E1", size=11),
                    margin=dict(l=10, r=10, t=10, b=10),
                    showlegend=False,
                    height=440,
                )
                fig.update_xaxes(showgrid=False, zeroline=True, zerolinecolor="rgba(148, 163, 184, 0.2)")
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Datos de rotación sectorial no disponibles actualmente.")
        except Exception as e:
            st.caption(f"Panel sectorial en mantenimiento: {e}")

def render_company_empty_state(ticker: str, herramienta: dict) -> None:
    """Estado vacío premium para módulos que requieren ejecutar análisis."""
    nombre_herramienta = strip_visual_prefix(herramienta.get("label", "Módulo"))

    # Blindamos el HTML concatenando en una sola línea lógica para evitar bugs de Markdown
    html_state = (
        f"<section class='vq-empty-state' style='padding:1.15rem 1.25rem; margin-top:.85rem;'>"
        f"<div style='display:flex; align-items:flex-start; justify-content:space-between; gap:1rem;'>"
        f"<div>"
        f"<div class='vq-context-eyebrow'>Pendiente de ejecución</div>"
        f"<h3 style='margin:.2rem 0 .45rem; font-size:1.35rem;'>"
        f"Genera el análisis para activar {html.escape(nombre_herramienta)}"
        f"</h3>"
        f"<p style='color:var(--vq-muted); margin:0; line-height:1.6; max-width:900px;'>"
        f"Selecciona la compañía, define el histórico y ejecuta el análisis para cargar ratios, valoración, señales de riesgo y visualizaciones del módulo."
        f"</p>"
        f"</div>"
        f"<span class='vq-badge vq-badge-primary'><i class='bi bi-play-circle'></i> Esperando análisis</span>"
        f"</div>"
        f"<div style='display:flex; gap:.5rem; flex-wrap:wrap; margin-top:1.2rem;'>"
        f"<span class='vq-badge'><i class='bi bi-building'></i> Ticker actual: {html.escape(ticker)}</span>"
        f"<span class='vq-badge'><i class='bi bi-database'></i> Datos financieros</span>"
        f"<span class='vq-badge'><i class='bi bi-graph-up'></i> Visualización institucional</span>"
        f"</div>"
        f"</section>"
    )

    st.markdown(html_state, unsafe_allow_html=True)

inject_terminal_theme()

inyectar_atajo_teclado()

# ---------------- UI PREMIUM & CONTROL CENTRAL ---------------- #        

# ---------------------------------------------------------
# 1. NAVEGACIÓN SUPERIOR Y CONTROL CENTRAL
# ---------------------------------------------------------
render_ticker_tape()

logo_uri_nav = asset_to_data_uri(LOGO_PATH)
logo_tag_nav = f"<img src='{logo_uri_nav}' alt='ValueQuant Terminal'>" if logo_uri_nav else ""
st.markdown(
    f"""
    <div class="vq-nav-shell">
        <div class="vq-brand-row">
            <div class="vq-brand">{logo_tag_nav}<span>ValueQuant Terminal</span></div>
            <div class="vq-session-pill"><i class="bi bi-broadcast-pin"></i> Research desk active</div>
        </div>
    """,
    unsafe_allow_html=True,
)

modos_navegacion = obtener_modos_navegacion()
modo_labels = [modo["label"] for modo in modos_navegacion]
modo_keys = [modo["key"] for modo in modos_navegacion]
modo_default_idx = modo_keys.index("mvp") if "mvp" in modo_keys else 0

with st.sidebar:
    st.markdown("### Modo de producto")
    modo_label = st.radio(
        "Modo de navegación",
        modo_labels,
        index=modo_default_idx,
        key="vq_navigation_mode",
        label_visibility="collapsed",
        help="MVP muestra solo el producto principal. Consolidado agrupa herramientas por arquitectura objetivo. Completo muestra todo.",
    )

modo_navegacion = modo_keys[modo_labels.index(modo_label)] if modo_label in modo_labels else "mvp"
modo_meta = next((modo for modo in modos_navegacion if modo["key"] == modo_navegacion), modos_navegacion[0])

bloques_internos = list(obtener_bloques_por_modo(modo_navegacion))
if not bloques_internos:
    bloques_internos = list(BLOQUES_HERRAMIENTAS)

menu_interno = ["__home__"] + bloques_internos
menu_labels = ["Home"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[0] for b in bloques_internos]
menu_icons = ["house"] + [BLOQUE_UI.get(b, (strip_visual_prefix(b), "grid"))[1] for b in bloques_internos]
seleccion_menu = render_option_menu_safe(menu_labels, menu_icons, key=f"vq_main_nav_{modo_navegacion}")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="vq-control-panel" style="padding:.75rem 1rem; margin-bottom:.85rem;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
            <div>
                <div class="vq-context-eyebrow">Modo de navegación</div>
                <div style="color:#FFFFFF; font-weight:800;">{html.escape(str(modo_meta.get('label', 'MVP')))}</div>
                <div style="color:var(--vq-muted); font-size:.86rem; margin-top:.15rem;">{html.escape(str(modo_meta.get('caption', '')))}</div>
            </div>
            <span class="vq-badge vq-badge-success"><i class="bi bi-layers"></i> {html.escape(str(modo_meta.get('badge', 'Producto')))}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

seleccion_idx = menu_labels.index(seleccion_menu) if seleccion_menu in menu_labels else 0
if menu_interno[seleccion_idx] == "__home__":
    render_home_page()
    st.stop()

bloque_actual = menu_interno[seleccion_idx]
herramientas_bloque = obtener_herramientas_por_bloque_y_modo(bloque_actual, modo_navegacion)
etiquetas_bloque = [h["label"] for h in herramientas_bloque]
tool_labels = [strip_visual_prefix(label) for label in etiquetas_bloque]
tool_icons = [TOOL_UI_ICONS.get(label, "circle") for label in etiquetas_bloque]

st.markdown(
    f"""
    <div class="vq-control-panel">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.75rem;">
            <div>
                <div class="vq-context-eyebrow">Área de trabajo</div>
                <div style="color:#FFFFFF; font-weight:800; font-size:1.05rem;">
                    {html.escape(strip_visual_prefix(bloque_actual))}
                </div>
            </div>
            <span class="vq-badge vq-badge-primary">
                <i class="bi bi-command"></i> Command Center
            </span>
        </div>
    """,
    unsafe_allow_html=True,
)

seleccion_herramienta = render_option_menu_safe(
    tool_labels,
    tool_icons,
    key=f"vq_tool_nav_{seleccion_idx}"
)

seleccion_tool_idx = tool_labels.index(seleccion_herramienta) if seleccion_herramienta in tool_labels else 0
seccion_actual = etiquetas_bloque[seleccion_tool_idx]
herramienta_actual = HERRAMIENTAS_POR_LABEL[seccion_actual]

st.markdown(
    f"<div class='vq-tool-caption'>{html.escape(herramienta_actual['descripcion'])}</div>",
    unsafe_allow_html=True,
)

# Variables contextuales compartidas por el router
ticker_input = "AAPL"
etf_input = "SPY"
ticker_competidor = ""
años_hist = 10
analizar_btn = False

if herramienta_actual["input_mode"] == "etf":
    col_a, col_b = st.columns([1.3, 2.7])
    with col_a:
        st.caption("Análisis de fondos")
        busqueda_etf = st.text_input("Buscar ETF", value="", placeholder="Vanguard, SPY, QQQ...", label_visibility="collapsed")
    with col_b:
        if busqueda_etf:
            try:
                resultados_busqueda = buscar_etf_yahoo(busqueda_etf)
                if resultados_busqueda:
                    seleccion = st.selectbox("Selecciona fondo", resultados_busqueda, label_visibility="collapsed")
                    etf_input = seleccion.split(" ➔ ")[0].strip()
                else:
                    etf_input = busqueda_etf.upper().strip()
                    st.info(f"Usando ticker exacto: {etf_input}")
            except Exception:
                etf_input = busqueda_etf.upper().strip()
        else:
            st.info("Introduce un ETF para iniciar la radiografía.")
elif herramienta_actual["input_mode"] == "standalone":
    st.caption("Herramienta independiente. Los controles específicos aparecen en el panel central.")
else:
    try:
        lista_tickers_sec = obtener_tickers_filtrados()
    except Exception:
        lista_tickers_sec = ["AAPL - Apple Inc.", "MSFT - Microsoft Corp."]

    indice_aapl = next((i for i, item in enumerate(lista_tickers_sec) if item.startswith("AAPL -")), 0)
    col_1, col_2, col_3, col_4 = st.columns([2.2, 2.2, 1, 1])
    with col_1:
        seleccion_principal = st.selectbox("Empresa", options=lista_tickers_sec, index=indice_aapl)
        ticker_input = seleccion_principal.split(" - ")[0]
    with col_2:
        lista_competidores = [""] + lista_tickers_sec
        seleccion_competidor = st.selectbox("Comparador", options=lista_competidores, index=0)
        ticker_competidor = seleccion_competidor.split(" - ")[0] if seleccion_competidor else ""
    with col_3:
        años_hist = st.slider("Años FMP", 1, 5, 5)
    with col_4:
        st.markdown("<div style='height:1.72rem;'></div>", unsafe_allow_html=True)
        analizar_btn = st.button("Analizar", use_container_width=True, type="primary")

st.markdown('</div>', unsafe_allow_html=True)

render_context_header(
    bloque=bloque_actual,
    herramienta=herramienta_actual,
    ticker=ticker_input if herramienta_actual["input_mode"] == "company" else None,
    competidor=ticker_competidor if ticker_competidor else None,
    años=años_hist if herramienta_actual["input_mode"] == "company" else None,
)

# ---------------------------------------------------------
# 2. ENRUTADOR PRINCIPAL (Gestión de la pantalla central)
# ---------------------------------------------------------

herramientas_independientes = [
    h["label"] for h in TOOL_CATALOG if h["input_mode"] in {"standalone", "etf"}
]

# CASOS INDEPENDIENTES (No necesitan darle al botón del sidebar)
if seccion_actual in herramientas_independientes:
    st.markdown("<br>", unsafe_allow_html=True)
    render_independent_tool(seccion_actual, etf_input=etf_input)

# CASOS DE EMPRESA (Requieren pulsar el botón del sidebar la primera vez)
else:
    # ---------------------------------------------------------
    # RUTA B: HERRAMIENTAS DE EMPRESA (Requieren pulsar el botón)
    # ---------------------------------------------------------
    
    # 1. Escuchamos al botón de la barra lateral
    if analizar_btn:
        st.session_state['empresa_analizada'] = True
        st.session_state['ticker_analizado'] = ticker_input
        st.session_state['competidor_analizado'] = ticker_competidor
        st.session_state['años_analizados'] = años_hist

    # 2. Si AÚN NO han pulsado el botón -> Mostramos la Landing Page
    empresa_no_analizada = (
        not st.session_state.get('empresa_analizada', False)
        or st.session_state.get('ticker_analizado') != ticker_input
        or st.session_state.get('competidor_analizado') != ticker_competidor
        or st.session_state.get('años_analizados') != años_hist
    )

    if empresa_no_analizada:
        render_company_empty_state(ticker_input, herramienta_actual)
        st.stop()

    # 3. Si YA han pulsado el botón -> Cargamos los datos y mostramos la herramienta
    with st.spinner(f"Sincronizando con Wall Street... Descargando {años_hist} años de datos para {ticker_input}"):
        is_df, bs_df, cf_df, metrics_df = cargar_datos(ticker_input, años_hist)

    datos_fmp = {
        "income_statement": None if is_df is None else is_df.shape,
        "balance_sheet": None if bs_df is None else bs_df.shape,
        "cash_flow": None if cf_df is None else cf_df.shape,
        "key_metrics": None if metrics_df is None else metrics_df.shape,
    }

    if is_df is None or bs_df is None or cf_df is None:
        st.error(f"🚨 FMP no devolvió estados financieros completos para `{ticker_input}`.")
        st.caption("Prueba primero con `AAPL`, `MSFT` o `GOOGL`. Algunos tickers con clases de acciones pueden requerir formato FMP, por ejemplo `BRK-B`.")
        with st.expander("Diagnóstico FMP"):
            st.json(datos_fmp)
            with st.spinner("Probando endpoints FMP sin caché..."):
                st.json(diagnosticar_conexion_fmp(ticker_input, 2))
            if st.button("Limpiar caché FMP y reintentar"):
                try:
                    st.cache_data.clear()
                except Exception:
                    pass
                st.rerun()
        st.stop()

    # Procesamiento matemático de fondo (Para el Chatbot y otras funciones futuras)
    res_is = analizar_cuenta_resultados(is_df, cf_df)
    res_bs = analizar_balance(bs_df, is_df)
    res_cf = analizar_flujo_efectivo(cf_df, is_df)
    res_val = valorar_empresa(is_df, bs_df, cf_df, metrics_df, ticker_input)

    nota_buffett = calcular_score_buffett(
        res_is["ratios"],
        res_bs["ratios"],
        res_cf["ratios"]
    )

    valuequant_score = calcular_valuequant_score(
        ticker=ticker_input,
        is_df=is_df,
        bs_df=bs_df,
        cf_df=cf_df,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
        res_val=res_val,
    )

    st.session_state["nota_buffett"] = nota_buffett
    st.session_state["valuequant_score"] = valuequant_score

    st.markdown(
        "<div class='vq-section-title'><i class='bi bi-speedometer2'></i>Panel ejecutivo</div>",
        unsafe_allow_html=True,
    )

    col_kpi_1, col_kpi_2, col_kpi_3 = st.columns(3)

    with col_kpi_1:
        render_kpi_card(
            label="Empresa analizada",
            value=ticker_input,
            detail=f"Histórico cargado: {años_hist} años",
            status="neutral"
        )

    with col_kpi_2:
        render_kpi_card(
            label="Módulo activo",
            value=strip_visual_prefix(herramienta_actual["label"]),
            detail=strip_visual_prefix(bloque_actual),
            status="positive"
        )

    with col_kpi_3:
        render_kpi_card(
            label="Comparador",
            value=ticker_competidor if ticker_competidor else "No definido",
            detail="Benchmark relativo",
            status="positive" if ticker_competidor else "warning"
        )
    
    # Invocamos la herramienta correspondiente desde el router central
    tool_context = CompanyToolContext(
        ticker=ticker_input,
        competitor=ticker_competidor,
        years=años_hist,
        is_df=is_df,
        bs_df=bs_df,
        cf_df=cf_df,
        metrics_df=metrics_df,
        res_is=res_is,
        res_bs=res_bs,
        res_cf=res_cf,
        res_val=res_val,
        nota_buffett=nota_buffett,
        valuequant_score=valuequant_score,
        sector_rotation_fn=analizar_rotacion_sectores,
    )
    render_company_tool(seccion_actual, tool_context)

# Chat lateral legacy retirado: la nueva arquitectura usa navegación superior sin sidebar.
