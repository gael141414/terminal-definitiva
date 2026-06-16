import re
import logging
import asyncio
from telethon import TelegramClient, events
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from config import settings

logger = logging.getLogger(__name__)

class TelegramRPCController:
    """Bot API para Control Remoto y Kill-Switch"""
    def __init__(self, execution_engine):
        self.app = ApplicationBuilder().token(settings.TELEGRAM_TOKEN).build()
        self.engine = execution_engine
        
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("kill", self.kill_switch))
        self.app.add_handler(CommandHandler("resume", self.resume_trading))

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != settings.TELEGRAM_CHAT_ID:
            return
        msg = (f"🟢 ESTADO DEL SISTEMA\n"
               f"Trades Activos (Intraday): {self.engine.active_trades}\n"
               f"Estado Motor: {'Congelado ❄️' if self.engine.is_killed else 'Operativo 🔥'}\n"
               f"PDT Protection: {settings.PDT_PROTECTION}")
        await update.message.reply_text(msg)

    async def kill_switch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != settings.TELEGRAM_CHAT_ID:
            return
        self.engine.is_killed = True
        # Aquí se iterarían posiciones abiertas en CCXT para ejecutar close_position() o crear market orders contrarias.
        await update.message.reply_text("🚨 KILL SWITCH ACTIVADO 🚨\nEl sistema de ejecución ha sido bloqueado preventivamente.")

    async def resume_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != settings.TELEGRAM_CHAT_ID:
            return
        self.engine.is_killed = False
        await update.message.reply_text("✅ Operaciones reanudadas con éxito.")
        
    async def start(self):
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()


class SignalScraperNLU:
    """User API mediante Telethon para extraer alertas de canales."""
    def __init__(self, data_orchestrator, quant_engine):
        self.client = TelegramClient('trading_session', settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
        self.data_orch = data_orchestrator
        self.quant = quant_engine
        
    async def start(self):
        await self.client.start()
        self.client.add_event_handler(self.parser_handler, events.NewMessage(chats=settings.TARGET_SIGNAL_CHANNELS))
        logger.info("Signal Scraper NLU escuchando a canales target.")

    async def parser_handler(self, event):
        text = event.message.message
        # Expresión regular robusta de extracción (NLU basada en Regex)
        # Detecta formatos como: "BUY BTC/USDT Entry 60000 SL 58000 TP 64000"
        pattern = r'(?i)(BUY|SELL|LONG|SHORT)\s+([A-Z0-9/]+).*?(?:ENTRY|ENTRADA)\s+([\d\.]+).*?(?:SL|STOP)\s+([\d\.]+).*?(?:TP|TARGET)\s+([\d\.]+)'
        match = re.search(pattern, text)
        
        if match:
            side_raw, symbol, entry, sl, tp = match.groups()
            side = 'buy' if side_raw.upper() in ['BUY', 'LONG'] else 'sell'
            
            logger.info(f"Señal extraída: {side.upper()} {symbol} E:{entry} SL:{sl} TP:{tp}")
            await self.validate_and_route_signal(symbol, side, float(entry), float(sl), float(tp))

    async def validate_and_route_signal(self, symbol: str, side: str, entry: float, sl: float, tp: float):
        """Validador Estratégico Cuantitativo"""
        # 1. Filtro Matemático Risk:Reward >= 1:2
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0 or (reward / risk) < 2.0:
            logger.warning(f"Señal rechazada. R:R inaceptable ({reward/risk if risk > 0 else 0}:1)")
            return
            
        # 2. Confluencia con Tendencia Macro (Media de 200)
        try:
            symbol_fmt = symbol.replace('/', '-') # Ajuste a formato YFinance si procede
            df = await self.data_orch.fetch_data(symbol_fmt, '1d', 250)
            if df.empty:
                return
                
            df['SMA_200'] = df['Close'].rolling(200).mean()
            last_close = df['Close'].iloc[-1]
            sma_200 = df['SMA_200'].iloc[-1]
            
            if side == 'buy' and last_close < sma_200:
                logger.warning("Señal de Compra rechazada. Precio por debajo de la SMA 200 (Tendencia Bajista Macro).")
                return
            elif side == 'sell' and last_close > sma_200:
                logger.warning("Señal de Venta rechazada. Precio por encima de la SMA 200 (Tendencia Alcista Macro).")
                return
                
            logger.info("✅ Señal Validada por Algoritmo Quant. Preparando Ejecución.")
            # Aquí se enrutaría hacia el AdvancedExecutionEngine
            
        except Exception as e:
            logger.error(f"Fallo durante la validación NLU: {e}")
            
    async def run_until_disconnected(self):
        await self.client.run_until_disconnected()
        
    async def stop(self):
        await self.client.disconnect()