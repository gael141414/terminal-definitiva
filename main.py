import asyncio
import logging
import math
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
import uvicorn

from config import settings
from data_provider import DataOrchestrator
from engine import QuantitativeEngine
from execution import AdvancedExecutionEngine
from telegram_bot import TelegramRPCController, SignalScraperNLU

# Configuración de Logging Producción
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Instancias de Arquitectura Core
data_orch = DataOrchestrator()
engine = QuantitativeEngine()
exec_engine = AdvancedExecutionEngine()

# Servidor FastAPI para TradingView Webhooks
app = FastAPI()

@app.post("/tv-webhook")
async def tradingview_webhook(request: Request):
    """Endpoint Alternativo Costo Cero para recibir alertas HTTP directas"""
    data = await request.json()
    if data.get('secret') != settings.WEBHOOK_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    logger.info(f"Webhook recibido: {data}")
    # Extraer variables y despachar ejecución asíncrona (Fire & Forget)
    # asyncio.create_task(exec_engine.execute_limit_chase(...))
    return {"status": "Processing"}

async def check_github_actions_jitter():
    """Mitigación de colas en Serverless. Si hay retraso > 5 min, aborta la iteración técnica."""
    now = datetime.now(timezone.utc)
    if now.minute % 15 > settings.GITHUB_ACTIONS_DRIFT_TOLERANCE_MIN:
        logger.warning(f"Jitter Serverless detectado. Retraso de {now.minute % 15} minutos. Ignorando vela.")
        # Aquí se dispararía httpx.post a un webhook externo para recalibrar
        return True
    return False

async def oracle_reclamation_mitigation():
    """Carga computacional de bajo nivel para mantener CPU > 15% en Oracle Free Tier"""
    logger.info("Servicio de Mitigación de Reclamación Oracle Iniciado.")
    while True:
        if settings.ORACLE_CPU_THRESHOLD_BURN:
            # Operación cripto/matemática pesada que consume ciclos de CPU
            _ = [math.sqrt(i ** 2) for i in range(1500000)]
        await asyncio.sleep(120)  # Picos cada 2 minutos

async def main_trading_loop():
    """Bucle Principal del Orquestador Algorítmico"""
    symbols = ['BTC/USDT', 'ETH/USDT']
    
    while True:
        if await check_github_actions_jitter():
            await asyncio.sleep(60)
            continue
            
        for symbol in symbols:
            df = await data_orch.fetch_data(symbol, '15m', 100)
            if not df.empty:
                df = engine.apply_dynamic_bollinger(df)
                df = engine.apply_volume_flows(df)
                df, signal = engine.identify_patterns_and_signals(df)
                
                if signal == 1 and not exec_engine.is_killed:
                    logger.info(f"Oportunidad detectada en {symbol}. Calculando posición...")
                    # Inyección Limit Chase
        
        await asyncio.sleep(60 * 15) # Ciclo de 15 minutos

async def main():
    await exec_engine.initialize()
    
    rpc_bot = TelegramRPCController(exec_engine)
    scraper = SignalScraperNLU(data_orch, engine)
    
    await rpc_bot.start()
    await scraper.start()
    
    server = uvicorn.Server(uvicorn.Config(app=app, host="0.0.0.0", port=8080, log_level="info"))
    
    # Agrupación y ejecución concurrente de todos los microservicios sin bloqueo
    await asyncio.gather(
        server.serve(),
        main_trading_loop(),
        scraper.run_until_disconnected(),
        oracle_reclamation_mitigation()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Sistema apagándose... Cerrando conexiones.")
        asyncio.run(exec_engine.close())