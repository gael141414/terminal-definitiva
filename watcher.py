import time
import requests
import yfinance as yf
from downloader import obtener_estados_financieros
from valuator import valorar_empresa

# ==========================================
# ⚙️ CONFIGURACIÓN DEL BOT
# ==========================================
TELEGRAM_TOKEN = "8554966720:AAEi0LLckJNN8wbH6KW3oVsRiSsHWm_sNUI"
TELEGRAM_CHAT_ID = "6244982134"

# ¿Qué descuento mínimo exiges para que el bot te moleste? (Ej: 20%)
MARGEN_SEGURIDAD_DESEADO = 20.0 

# Tu lista personal de seguimiento (Empresas extraordinarias que comprarías a buen precio)
WATCHLIST = ["AAPL", "MSFT", "V", "MA", "GOOGL", "ASML", "LVMUY", "PEP", "JNJ"]

def enviar_mensaje_telegram(mensaje):
    """Envía una alerta push a tu móvil vía Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown" # Permite usar negritas y formato
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("✅ Mensaje de Telegram enviado con éxito.")
        else:
            print(f"⚠️ Error de Telegram: {response.text}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

def escanear_mercado():
    print(f"🔍 Iniciando escaneo de la Watchlist ({len(WATCHLIST)} empresas)...")
    alertas = []
    
    for ticker in WATCHLIST:
        print(f"Evaluando {ticker}...")
        try:
            # Descargamos solo 2 años (es suficiente para tener el EPS y el balance actual)
            is_df, bs_df, cf_df = obtener_estados_financieros(ticker, años=2, usar_cache=True)
            res_val = valorar_empresa(is_df, bs_df, cf_df, ticker)
            
            if res_val and res_val.get('precio_actual'):
                precio = res_val['precio_actual']
                eps = res_val.get('eps_actual', 0)
                per = res_val.get('per_asumido', 15)
                g = res_val.get('crecimiento_sostenible', 0.05)
                r = res_val.get('tasa_descuento_capm', 0.10)
                
                # Si la empresa gana dinero, calculamos su DCF
                if eps > 0:
                    v_i = (eps * ((1 + g)**10) * per) / ((1 + r)**10)
                    
                    # Calculamos el margen: (Valor Real - Precio Mercado) / Valor Real
                    # Un 20% significa que cotiza un 20% por debajo de lo que vale
                    descuento = ((v_i - precio) / v_i) * 100 
                    
                    if descuento >= MARGEN_SEGURIDAD_DESEADO:
                        msg = f"🚨 *OPORTUNIDAD VALUE: {ticker}*\n"
                        msg += f"💰 Precio Mercado: `${precio:.2f}`\n"
                        msg += f"🎯 Valor Intrínseco: `${v_i:.2f}`\n"
                        msg += f"🔥 *Descuento: {descuento:.1f}%*"
                        alertas.append(msg)
                        
            # Pausa obligatoria para no saturar a la SEC
            time.sleep(2) 
            
        except Exception as e:
            print(f"⚠️ No se pudo evaluar {ticker}: {e}")
            
    # --- ENVÍO DE RESULTADOS ---
    if alertas:
        print(f"\n📩 ¡Se encontraron {len(alertas)} empresas en zona de compra! Enviando alertas...")
        mensaje_final = "🦅 *BUFFETT TERMINAL ALERTS*\n_El mercado está ofreciendo descuentos:_\n\n"
        mensaje_final += "\n\n".join(alertas)
        enviar_mensaje_telegram(mensaje_final)
    else:
        print("\n💤 Fin del escaneo. Ninguna empresa de tu lista cumple el margen de seguridad hoy. El mercado está caro.")

if __name__ == "__main__":
    escanear_mercado()