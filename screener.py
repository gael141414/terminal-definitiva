import pandas as pd
import time
import requests
import yfinance as yf

from downloader import obtener_estados_financieros
from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from modulos.utils import calcular_score_buffett
from modulos.yahoo_resilience import safe_yfinance_info

SP500_WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
SP500_WIKI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def obtener_tickers_sp500():
    """Descarga la lista de tickers del S&P 500 desde Wikipedia (llamada de red bajo demanda)."""
    html_content = requests.get(SP500_WIKI_URL, headers=SP500_WIKI_HEADERS).text
    tables = pd.read_html(html_content)

    # La primera tabla (índice 0) contiene la lista de componentes actuales
    df = tables[0]

    # Extraer los tickers como una lista
    tickers = df['Symbol'].tolist()

    # (Opcional) Limpiar tickers: algunos usan '.' en lugar de '-' (ej. BRK.B)
    return [ticker.replace('.', '-') for ticker in tickers]


def ejecutar_screener():
    tickers_a_evaluar = obtener_tickers_sp500()
    print(f"Total de tickers encontrados: {len(tickers_a_evaluar)}")
    print(f"🚀 Iniciando Screener Institucional (Buffett + Greenblatt + Carlisle) para {len(tickers_a_evaluar)} empresas...")
    resultados = []

    for i, ticker in enumerate(tickers_a_evaluar):
        print(f"[{i+1}/{len(tickers_a_evaluar)}] Analizando {ticker}...")
        try:
            # 1. Análisis Fundamental Clásico
            is_df, bs_df, cf_df = obtener_estados_financieros(ticker, años=5, usar_cache=True)
            
            # 2. Extracción de Datos en Vivo (Yahoo Finance) para Valoración Múltiple
            info = safe_yfinance_info(yf, ticker, context="screener")
            
            ev_ebitda = info.get('enterpriseToEbitda', 0)
            if ev_ebitda is None: ev_ebitda = 0
            
            # Earnings Yield (Proxy para Greenblatt: a la inversa del EV/EBITDA)
            # Cuanto mayor sea este porcentaje, más "barata" es la empresa respecto a lo que genera
            earnings_yield = (1 / ev_ebitda) * 100 if ev_ebitda > 0 else 0
            
            if is_df is not None and not is_df.empty:
                res_is = analizar_cuenta_resultados(is_df, cf_df)
                res_bs = analizar_balance(bs_df, is_df)
                res_cf = analizar_flujo_efectivo(cf_df, is_df)
                
                if res_is and res_bs and res_cf:
                    nota = calcular_score_buffett(res_is["ratios"], res_bs["ratios"], res_cf["ratios"])
                    
                    # Extraer ROIC (Retorno sobre Capital Invertido - La "Calidad" de Greenblatt)
                    roic = res_bs["ratios"]["ROIC %"].dropna().iloc[-1] if "ROIC %" in res_bs["ratios"] else 0
                    roe = res_bs["ratios"]["ROE %"].dropna().iloc[-1] if "ROE %" in res_bs["ratios"] else 0
                    deuda = res_bs["ratios"]["Deuda / Capital"].dropna().iloc[-1] if "Deuda / Capital" in res_bs["ratios"] else 0
                    
                    # Solo guardamos empresas con datos válidos
                    if roic > 0 and ev_ebitda > 0:
                        resultados.append({
                            "Ticker": ticker,
                            "Buffett Score": nota,
                            "ROE %": round(roe, 2),
                            "ROIC %": round(roic, 2),
                            "Deuda/Capital": round(deuda, 2),
                            "Acquirer's Multiple (EV/EBITDA)": round(ev_ebitda, 2),
                            "Earnings Yield %": round(earnings_yield, 2)
                        })
            
            # ⚠️ VITAL: Pausa de 2 segundos para no bloquear la IP
            time.sleep(2) 
            
        except Exception as e:
            print(f"❌ Error con {ticker}: {e}")

    # ==========================================
    # 🧠 EL ALGORITMO DE SELECCIÓN (RANKING)
    # ==========================================
    if resultados:
        df_ranking = pd.DataFrame(resultados)
        
        # 1. Ranking de Calidad (ROIC): El #1 es el que tiene el ROIC más ALTO
        df_ranking['Rank Calidad'] = df_ranking['ROIC %'].rank(ascending=False)
        
        # 2. Ranking de Precio (Earnings Yield): El #1 es el que tiene el Yield más ALTO (más barato)
        df_ranking['Rank Precio'] = df_ranking['Earnings Yield %'].rank(ascending=False)
        
        # 3. La "Fórmula Mágica": Sumamos ambos rankings. La puntuación más BAJA gana.
        df_ranking['Puntuacion Greenblatt'] = df_ranking['Rank Calidad'] + df_ranking['Rank Precio']
        
        # Ordenamos la tabla final por la Fórmula Mágica para descubrir las verdaderas gangas
        df_ranking = df_ranking.sort_values(by="Puntuacion Greenblatt", ascending=True)
        
        # Limpiamos columnas auxiliares para que el Excel quede bonito
        columnas_finales = [
            "Ticker", "Puntuacion Greenblatt", "Buffett Score", 
            "Acquirer's Multiple (EV/EBITDA)", "ROIC %", "Earnings Yield %", "ROE %", "Deuda/Capital"
        ]
        df_ranking = df_ranking[columnas_finales]
        
        df_ranking.to_csv("ranking_mercado.csv", index=False)
        print("\n✅ ¡Screener Institucional finalizado!")
        print("🏆 El Top 5 de la Fórmula Mágica es:")
        print(df_ranking[['Ticker', 'Puntuacion Greenblatt', 'ROIC %', "Acquirer's Multiple (EV/EBITDA)"]].head(5).to_string(index=False))
        print("\nResultados guardados en 'ranking_mercado.csv'.")
    else:
        print("\n⚠️ No se pudieron analizar las empresas.")

if __name__ == "__main__":
    ejecutar_screener()
