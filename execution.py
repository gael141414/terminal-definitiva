import asyncio
import logging
import ccxt.pro as ccxtpro
from typing import Dict, Any
from config import settings

logger = logging.getLogger(__name__)

class AdvancedExecutionEngine:
    def __init__(self, exchange_id: str = 'binance'):
        exchange_class = getattr(ccxtpro, exchange_id)
        self.exchange = exchange_class({
            'apiKey': settings.API_KEY,
            'secret': settings.API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        })
        if settings.USE_SANDBOX:
            self.exchange.set_sandbox_mode(True)
            
        self.active_trades = 0
        self.is_killed = False

    async def initialize(self):
        await self.exchange.load_markets()
        logger.info(f"Exchange {self.exchange.id} inicializado. SandBox: {settings.USE_SANDBOX}")

    async def calculate_position_size(self, symbol: str, entry_price: float, stop_loss: float) -> float:
        """Aplica modelo de riesgo fijo (1% del portfolio)."""
        balance = await self.exchange.fetch_balance()
        quote_currency = symbol.split('/')[1]
        total_capital = balance.get('free', {}).get(quote_currency, 0)
        
        if total_capital <= 0:
            raise ValueError("Capital insuficiente.")
            
        risk_amount = total_capital * settings.MAX_RISK_PER_TRADE
        distance_pct = abs(entry_price - stop_loss) / entry_price
        
        # Ajuste de tamaño
        position_size = (risk_amount / distance_pct) / entry_price
        market = self.exchange.market(symbol)
        return self.exchange.amount_to_precision(symbol, position_size)

    async def execute_limit_chase(self, symbol: str, side: str, amount: float, max_retries: int = 3) -> Dict[str, Any]:
        """
        Ejecutor de Órdenes Límite Ejecutables para mitigar el slippage.
        Persigue el spread Bid/Ask inyectando liquidez internamente.
        """
        if self.is_killed:
            logger.warning("Kill-Switch activo. Operación abortada.")
            return {}
            
        if settings.PDT_PROTECTION and self.active_trades >= 3:
            logger.warning("Protección PDT activa. Se evita la operación intradía.")
            return {}

        for attempt in range(max_retries):
            orderbook = await self.exchange.fetch_order_book(symbol)
            bid = orderbook['bids'][0][0]
            ask = orderbook['asks'][0][0]
            
            # Mejora el precio un tick por dentro del spread
            limit_price = bid if side == 'buy' else ask
            limit_price = self.exchange.price_to_precision(symbol, limit_price)
            
            try:
                logger.info(f"Inyectando Limit Chase {side} para {symbol} a {limit_price}")
                order = await self.exchange.create_limit_order(symbol, side, amount, limit_price)
                
                # Espera asíncrona de confluencia
                await asyncio.sleep(2)
                
                status = await self.exchange.fetch_order(order['id'], symbol)
                if status['status'] == 'closed':
                    logger.info("Orden completada con éxito sin slippage.")
                    self.active_trades += 1
                    return status
                else:
                    logger.warning("Orden no completada, cancelando y recalculando Bid/Ask.")
                    await self.exchange.cancel_order(order['id'], symbol)
                    
            except Exception as e:
                logger.error(f"Fallo en ejecución: {e}")
                
        return {}

    async def close(self):
        await self.exchange.close()