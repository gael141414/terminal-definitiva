import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
import os

from downloader import obtener_estados_financieros
from income_analyzer import analizar_cuenta_resultados
from balance_analyzer import analizar_balance
from cashflow_analyzer import analizar_flujo_efectivo
from screener import calcular_score_buffett # Reutilizamos tu función del screener

# Lista de universo de acciones para el backtest (Ampliable)
UNIVERSO_TICKERS = [
    "AAPL", "MSFT", "V", "JNJ", "WMT", "PG", "JPM", "UNH", "HD", "CVX", 
    "KO", "PEP", "MCD", "DIS", "ADBE", "CRM", "INTC", "AMD", "AMZN", "GOOGL",
    "META", "TSLA", "BRK-B", "COST", "ABBV", "BAC", "XOM", "CSCO", "NKE", "PFE"
]

def obtener_score_historico(ticker, anio_evaluacion):
    """Viaja en el tiempo: Calcula el Score usando solo datos hasta 'anio_evaluacion'"""
    try:
        # Usamos caché para no saturar a la SEC
        is_df, bs_df, cf_df = obtener_estados_financieros(ticker, años=10, usar_cache=True)
        if is_df is None or is_df.empty: return 0

        # MÁGIA: Recortamos los dataframes para "cegar" al modelo sobre el futuro
        def recortar_futuro(df, anio):
            metadatos = [c for c in df.columns if not str(c).isdigit()]
            anios_pasados = [c for c in df.columns if str(c).isdigit() and int(c) <= anio]
            return df[metadatos + anios_pasados]

        is_df_hist = recortar_futuro(is_df, anio_evaluacion)
        bs_df_hist = recortar_futuro(bs_df, anio_evaluacion)
        cf_df_hist = recortar_futuro(cf_df, anio_evaluacion)

        # Analizar con los datos limitados
        res_is = analizar_cuenta_resultados(is_df_hist, cf_df_hist)
        res_bs = analizar_balance(bs_df_hist, is_df_hist)
        res_cf = analizar_flujo_efectivo(cf_df_hist, is_df_hist)

        if res_is and res_bs and res_cf:
            return calcular_score_buffett(res_is["ratios"], res_bs["ratios"], res_cf["ratios"])
        return 0
    except Exception as e:
        return 0

def ejecutar_backtest(anios_historia=6, top_n=5):
    anio_actual = pd.Timestamp.now().year
    anio_inicio = anio_actual - anios_historia
    
    print(f"🚀 Iniciando Backtest: {anio_inicio} a {anio_actual}")
    print(f"Estrategia: Comprar el Top {top_n} de acciones con mayor Buffett Score cada año.")
    
    # 1. Descargar precios históricos de todo el universo y del S&P500
    print("[*] Descargando histórico de precios (Yahoo Finance)...")
    tickers_yf = UNIVERSO_TICKERS + ["SPY"]
    
    # Forzamos descargar los precios de "Close"
    datos_precios = yf.download(tickers_yf, start=f"{anio_inicio}-01-01", end=f"{anio_actual}-12-31", progress=False)['Close']

    # 🛡️ BLINDAJE 1: Quitar la zona horaria para que no rompa los filtros
    if datos_precios.index.tz is not None:
        datos_precios.index = datos_precios.index.tz_localize(None)

    # Capital inicial
    cartera_value = 10000
    cartera_spy = 10000
    
    # 🛡️ BLINDAJE 2: Añadimos el año inicial a la gráfica para que parta de 10.000
    historial_cartera = [cartera_value]
    historial_spy = [cartera_spy]
    fechas = [pd.to_datetime(f"{anio_inicio}-01-01")]

    # 2. Bucle de los Años (Rebalanceo Anual)
    for anio in range(anio_inicio, anio_actual):
        print(f"\n--- 📅 Evaluación a finales de {anio} para invertir en {anio + 1} ---")
        
        # Evaluar el mercado con datos hasta el 'anio'
        scores = []
        for ticker in UNIVERSO_TICKERS:
            score = obtener_score_historico(ticker, anio)
            scores.append({'Ticker': ticker, 'Score': score})
            
        # Elegir el Top N
        df_scores = pd.DataFrame(scores).sort_values(by="Score", ascending=False)
        top_acciones = df_scores.head(top_n)['Ticker'].tolist()
        print(f"🏆 Top {top_n} seleccionadas para {anio+1}: {top_acciones}")

        # Calcular retornos durante el año siguiente (anio + 1)
        fecha_ini_inversion = pd.to_datetime(f"{anio+1}-01-01")
        fecha_fin_inversion = pd.to_datetime(f"{anio+1}-12-31")
        
        # Filtro matemático de Pandas
        mask = (datos_precios.index >= fecha_ini_inversion) & (datos_precios.index <= fecha_fin_inversion)
        precios_periodo = datos_precios.loc[mask]
        
        if not precios_periodo.empty:
            # 🛡️ NUEVO: Extraemos los precios al final de cada mes para la gráfica
            try:
                precios_mensuales = precios_periodo.resample('ME').last() # Para versiones nuevas de Pandas
            except:
                precios_mensuales = precios_periodo.resample('M').last()  # Para versiones antiguas
            
            # Guardamos el capital que teníamos al empezar el año
            cap_inicio_spy = cartera_spy
            cap_inicio_cartera = cartera_value
            
            # Precios de compra el día 1 de enero
            try:
                precio_base_spy = precios_periodo['SPY'].dropna().iloc[0]
                precio_base_acciones = {t: precios_periodo[t].dropna().iloc[0] for t in top_acciones}
            except Exception as e:
                print(f"⚠️ Error obteniendo precios base para {anio+1}: {e}")
                continue

            # Bucle MES A MES para pintar la gráfica detallada
            for fecha_mes, fila_precios in precios_mensuales.iterrows():
                # Retorno del S&P 500 desde enero hasta este mes
                ret_spy_mes = (fila_precios['SPY'] / precio_base_spy) - 1
                
                # Retorno de nuestra Cartera desde enero hasta este mes
                ret_cartera_mes = 0
                for ticker in top_acciones:
                    if ticker in precio_base_acciones and pd.notna(fila_precios[ticker]):
                        p_actual = fila_precios[ticker]
                        p_ini = precio_base_acciones[ticker]
                        ret_accion = (p_actual / p_ini) - 1
                        ret_cartera_mes += ret_accion / top_n
                
                # Añadimos los puntos mensuales a las listas de la gráfica
                fechas.append(fecha_mes)
                historial_spy.append(cap_inicio_spy * (1 + ret_spy_mes))
                historial_cartera.append(cap_inicio_cartera * (1 + ret_cartera_mes))
            
            # Actualizamos el capital real para el año siguiente usando el último mes (diciembre)
            cartera_spy = historial_spy[-1]
            cartera_value = historial_cartera[-1]
            
            # Cálculo para imprimir en la consola
            retorno_anual_cartera = (cartera_value / cap_inicio_cartera) - 1
            retorno_anual_spy = (cartera_spy / cap_inicio_spy) - 1
            print(f"💰 Rentabilidad en {anio+1}: Estrategia ({retorno_anual_cartera*100:.1f}%) vs S&P500 ({retorno_anual_spy*100:.1f}%)")
        else:
            print(f"⚠️ No hay datos de precios para el año {anio+1}.")

    # ==========================================
    # 3. ANALÍTICAS DE RIESGO Y GRÁFICO AVANZADO
    # ==========================================
    print("\n📊 Calculando métricas de riesgo institucional...")
    
    # Convertimos las listas a un DataFrame para hacer magia matemática
    df_res = pd.DataFrame({
        'Fecha': fechas,
        'Estrategia': historial_cartera,
        'SP500': historial_spy
    }).set_index('Fecha')

    # 1. Calcular Retornos Mensuales
    retornos = df_res.pct_change().dropna()

    # 2. Calcular CAGR (Tasa de Crecimiento Anual Compuesta)
    cagr_est = (df_res['Estrategia'].iloc[-1] / df_res['Estrategia'].iloc[0]) ** (1 / anios_historia) - 1
    cagr_spy = (df_res['SP500'].iloc[-1] / df_res['SP500'].iloc[0]) ** (1 / anios_historia) - 1

    # 3. Volatilidad Anualizada (Desviación Estándar Mensual * Raíz de 12 meses)
    vol_est = retornos['Estrategia'].std() * np.sqrt(12)
    vol_spy = retornos['SP500'].std() * np.sqrt(12)

    # 4. Sharpe Ratio (Asumimos tasa libre de riesgo del 4%)
    tasa_libre_riesgo = 0.04
    sharpe_est = (cagr_est - tasa_libre_riesgo) / vol_est
    sharpe_spy = (cagr_spy - tasa_libre_riesgo) / vol_spy

    # 5. Maximum Drawdown (Peor caída desde un máximo histórico)
    roll_max_est = df_res['Estrategia'].cummax()
    drawdown_est = (df_res['Estrategia'] / roll_max_est) - 1
    max_dd_est = drawdown_est.min()

    roll_max_spy = df_res['SP500'].cummax()
    drawdown_spy = (df_res['SP500'] / roll_max_spy) - 1
    max_dd_spy = drawdown_spy.min()

    # Imprimir resumen en consola
    print("-" * 50)
    print(f"📈 CAGR (Retorno Anual): Estrategia {cagr_est*100:.2f}% | S&P500 {cagr_spy*100:.2f}%")
    print(f"📉 Max Drawdown (Peor Caída): Estrategia {max_dd_est*100:.2f}% | S&P500 {max_dd_spy*100:.2f}%")
    print(f"⚖️ Sharpe Ratio (Riesgo/Beneficio): Estrategia {sharpe_est:.2f} | S&P500 {sharpe_spy:.2f}")
    print("-" * 50)

    # --- CREACIÓN DEL GRÁFICO DOBLE ---
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3], # 70% arriba, 30% abajo
        subplot_titles=("Evolución del Capital ($)", "Drawdown (Caídas desde Máximos)")
    )

    # Panel 1: Curva de Capital (Arriba)
    titulo_est = f"Estrategia Value (CAGR: {cagr_est*100:.1f}%, Sharpe: {sharpe_est:.2f})"
    titulo_spy = f"S&P 500 (CAGR: {cagr_spy*100:.1f}%, Sharpe: {sharpe_spy:.2f})"
    
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res['Estrategia'], mode='lines', name=titulo_est, line=dict(color='#2ca02c', width=3)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_res.index, y=df_res['SP500'], mode='lines', name=titulo_spy, line=dict(color='#1f77b4', width=2, dash='dash')), row=1, col=1)

    # Panel 2: Curva de Drawdown (Abajo) - Rellenada en rojo
    fig.add_trace(go.Scatter(x=df_res.index, y=drawdown_est, mode='lines', name='Drawdown Estrategia', fill='tozeroy', line=dict(color='#d62728', width=1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_res.index, y=drawdown_spy, mode='lines', name='Drawdown S&P 500', line=dict(color='#1f77b4', width=1, dash='dot')), row=2, col=1)

    # Formato
    fig.update_yaxes(title_text="Capital (USD)", row=1, col=1)
    fig.update_yaxes(title_text="Caída %", tickformat=".1%", row=2, col=1)
    
    fig.update_layout(
        title=f"Backtest Institucional (10 Años): Estrategia Quant vs Mercado",
        hovermode="x unified",
        template="plotly_white",
        height=800,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    fig.write_html("resultado_backtest.html", auto_open=True)
    print("\n✅ Backtest finalizado. Se ha abierto el reporte analítico en tu navegador.")

if __name__ == "__main__":
    ejecutar_backtest(anios_historia=10, top_n=5)