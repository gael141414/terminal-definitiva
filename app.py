import streamlit as st

st.set_page_config(
    page_title="ValueQuant Terminal",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import pandas as pd
import yfinance as yf
import requests
import streamlit.components.v1 as components
import html

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
from modulos.app_home import render_home_page
from modulos.market_widgets import (
    analizar_rotacion_sectores,
    buscar_etf_yahoo,
    render_ticker_tape,
)
from modulos.tradingview_widgets import render_tradingview_widget, renderizar_grafico_tradingview
from modulos.company_data_helpers import obtener_datos_directiva, obtener_tickers_filtrados, obtener_transacciones_insiders, obtener_valoracion_sectorial
from modulos.app_company_ui import render_company_empty_state
from modulos.app_integrations import inyectar_atajo_teclado, load_lottieurl, obtener_modelo_gemini, obtener_secreto_streamlit
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
    obtener_herramientas_por_bloque_y_modo,
    obtener_modos_navegacion,
)
from modulos.tool_router import CompanyToolContext, render_company_tool, render_independent_tool

# ---------------- CONFIGURACIÓN ---------------- #
# 1. CONFIGURACIÓN DE PÁGINA movida al inicio del archivo para cumplir Streamlit.

# ==========================================
# MARKET TICKER TAPE FIJO
# ==========================================

# ---------------- DATA LOADER ---------------- #

# ==========================================
# WIDGET RADICAL 2: MOTOR TRADINGVIEW EN VIVO
# ==========================================

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
    render_home_page(LOGO_PATH, HOME_BG_PATH)
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
