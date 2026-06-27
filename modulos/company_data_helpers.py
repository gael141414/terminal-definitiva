from __future__ import annotations

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


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

