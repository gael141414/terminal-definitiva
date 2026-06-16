import pandas as pd
import os
import time
from edgar import Company, set_identity

set_identity("Buffett Terminal gaelestgon@gmail.com")

def obtener_estados_financieros(ticker, años=10, usar_cache=True):
    if not os.path.exists("cache_datos"):
        os.makedirs("cache_datos")
        
    rutas_cache = {
        "is": f"cache_datos/{ticker}_is.csv",
        "bs": f"cache_datos/{ticker}_bs.csv",
        "cf": f"cache_datos/{ticker}_cf.csv"
    }

    if usar_cache and all(os.path.exists(ruta) for ruta in rutas_cache.values()):
        try:
            return (pd.read_csv(rutas_cache["is"], index_col=0), 
                    pd.read_csv(rutas_cache["bs"], index_col=0), 
                    pd.read_csv(rutas_cache["cf"], index_col=0))
        except Exception: pass

    try:
        print(f"[*] Conectando con la SEC para: {ticker}...")
        ticker_sec = "GOOGL" if ticker == "GOOG" else ticker
        empresa = Company(ticker_sec)
        
        filings = empresa.get_filings(form="10-K").latest(años)
        if not filings: return None, None, None

        lista_is, lista_bs, lista_cf = [], [], []

        def get_statement_df(statements_obj, possible_names):
            for name in possible_names:
                if hasattr(statements_obj, name):
                    attr = getattr(statements_obj, name)
                    if callable(attr):
                        try: stmt = attr()
                        except: continue
                    else: stmt = attr
                    if stmt is None: continue
                    if hasattr(stmt, 'to_dataframe'): return stmt.to_dataframe() if callable(stmt.to_dataframe) else stmt.to_dataframe
                    elif hasattr(stmt, 'to_pandas'): return stmt.to_pandas() if callable(stmt.to_pandas) else stmt.to_pandas
            return None

        for filing in filings:
            try:
                xbrl = filing.xbrl()
                if not xbrl or not hasattr(xbrl, 'statements'): continue

                df_is = get_statement_df(xbrl.statements, ['income_statement'])
                df_bs = get_statement_df(xbrl.statements, ['balance_sheet'])
                df_cf = get_statement_df(xbrl.statements, ['cashflow_statement', 'cash_flow_statement', 'cashflows'])

                if df_is is not None: lista_is.append(df_is)
                if df_bs is not None: lista_bs.append(df_bs)
                if df_cf is not None: lista_cf.append(df_cf)
                time.sleep(0.8) # Pausa más larga para evitar el error de GOOG (baneos de la SEC)
            except Exception: continue

        # 🛠️ LA MAGIA: ALINEACIÓN POR 'CONCEPT'
        def consolidar_y_limpiar(lista_dfs):
            if not lista_dfs: return None
            
            dfs_alineados = []
            for df in lista_dfs:
                if 'concept' in df.columns:
                    df = df.drop_duplicates(subset=['concept'])
                    df = df.set_index('concept') # Anclamos por etiqueta
                dfs_alineados.append(df)
                
            # Pandas ahora unirá la fila de "NetIncome" de 2025 con la de 2018 correctamente
            df_final = pd.concat(dfs_alineados, axis=1)
            df_final = df_final.reset_index()
            
            cols_limpias = []
            for c in df_final.columns:
                c_str = str(c)
                if c_str.lower() in ['concept', 'label', 'unit', 'standard_concept', 'decimals', 'fact']:
                    cols_limpias.append(c_str.lower())
                elif c_str.startswith('20') and len(c_str) >= 4:
                    cols_limpias.append(c_str[:4])
                else: 
                    cols_limpias.append(c_str)
                    
            df_final.columns = cols_limpias
            df_final = df_final.loc[:, ~df_final.columns.duplicated(keep='first')]
            
            metadata = [c for c in df_final.columns if not c.isdigit()]
            years = sorted([c for c in df_final.columns if c.isdigit()])
            return df_final[metadata + years]

        df_resultados = consolidar_y_limpiar(lista_is)
        df_balance = consolidar_y_limpiar(lista_bs)
        df_caja = consolidar_y_limpiar(lista_cf)
        
        if df_resultados is not None and df_balance is not None and df_caja is not None:
            df_resultados.to_csv(rutas_cache["is"])
            df_balance.to_csv(rutas_cache["bs"])
            df_caja.to_csv(rutas_cache["cf"])
            
        return df_resultados, df_balance, df_caja

    except Exception:
        return None, None, None