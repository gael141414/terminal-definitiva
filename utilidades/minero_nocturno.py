import yfinance as yf
import pandas as pd
import time
import os
import requests

def ejecutar_minero():
    print("🚀 Iniciando el Minero Quant de Small Caps...")

    # 1. Obtener el Universo (S&P 600 Small Caps de Wikipedia)
    print("📥 Descargando lista de candidatos (S&P 600)...")
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        tablas = pd.read_html(response.text)
        df_sp600 = tablas[0]
        tickers = df_sp600['Symbol'].tolist()
    except Exception as e:
        print(f"❌ Error al acceder a Wikipedia: {e}")
        return
        
    df_sp600 = tablas[0]
    tickers = df_sp600['Symbol'].tolist()
    
    # Limpiar tickers (cambiar puntos por guiones para Yahoo Finance)
    tickers = [t.replace('.', '-') for t in tickers]
    
    print(f"🎯 Universo definido: {len(tickers)} empresas. Empezando extracción profunda...")
    
    candidatas_oro = []
    
    # 2. El Embudo (Filtrado empresa por empresa)
    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] Analizando {ticker}...", end="\r")
        try:
            empresa = yf.Ticker(ticker)
            info = empresa.info
            
            # Extraer métricas clave (si no existe, ponemos 0 o False)
            market_cap = info.get('marketCap', 0)
            rev_growth = info.get('revenueGrowth', 0)
            margins = info.get('grossMargins', 0)
            debt_eq = info.get('debtToEquity', 999) # 999 si no hay dato para que falle el filtro
            insider = info.get('heldPercentInsiders', 0)
            
            # --- LOS FILTROS DEL HEDGE FUND ---
            # 1. Tamaño: Entre 50M y 3B (Pequeñas pero no micro-basura)
            if not (50_000_000 < market_cap < 3_000_000_000): continue
            
            # 2. Crecimiento: Ventas creciendo > 15% (Están robando mercado)
            if not (rev_growth and rev_growth > 0.15): continue
            
            # 3. Calidad: Margen Bruto > 40% (Tienen ventaja competitiva)
            if not (margins and margins > 0.40): continue
            
            # 4. Solvencia: Deuda/Equity < 50 (Sanas financieramente)
            if not (debt_eq and debt_eq < 50): continue
            
            # 5. Alineación: Insiders > 5% (Los dueños se juegan su dinero)
            if not (insider and insider > 0.05): continue
            
            # Si sobrevive a todo, la guardamos
            candidatas_oro.append({
                "Ticker": ticker,
                "Nombre": info.get('shortName', ticker),
                "Sector": info.get('sector', 'N/A'),
                "Crecimiento Ventas (%)": round(rev_growth * 100, 2),
                "Margen Bruto (%)": round(margins * 100, 2),
                "Deuda/Capital": round(debt_eq, 2),
                "Insiders (%)": round(insider * 100, 2),
                "Market Cap (M$)": round(market_cap / 1_000_000, 1)
            })
            
        except Exception as e:
            pass # Ignoramos la empresa si hay un error
            
        # ⚠️ VITAL: Pausa para que Yahoo no nos banee la IP
        time.sleep(0.5) 
        
    # 3. Guardar el tesoro
    print(f"\n✅ Minería completada. Joyas encontradas: {len(candidatas_oro)}")
    
    if candidatas_oro:
        df_final = pd.DataFrame(candidatas_oro)
        
        # Sistema de puntuación simple: Ordenamos por crecimiento
        df_final = df_final.sort_values(by="Crecimiento Ventas (%)", ascending=False)
        
        if not os.path.exists("../data"): os.makedirs("../data")
        # Asumiendo que ejecutas esto desde la carpeta utilidades
        df_final.to_csv("../data/small_caps_oro.csv", index=False)
        print("💾 Guardado en 'data/small_caps_oro.csv'. ¡Tu app ya puede leerlo!")
    else:
        print("😭 El mercado está duro. Ninguna empresa superó los filtros estrictos hoy.")

if __name__ == "__main__":
    ejecutar_minero()
