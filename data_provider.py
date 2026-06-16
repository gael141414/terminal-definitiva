import asyncio
import logging
import pandas as pd
import numpy as np
import yfinance as yf
import aiohttp
from config import settings

logger = logging.getLogger(__name__)

class DataOrchestrator:
    def __init__(self):
        self.finnhub_semaphore = asyncio.Semaphore(settings.MAX_RPM_FINNHUB)
        self.yfinance_lock = asyncio.Lock()
        self.request_count = 0

    async def fetch_data(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """
        Orquestador dinámico: Selecciona la fuente en función de la latencia requerida 
        y mitiga anomalías en los datos.
        """
        if timeframe in ['1m', '5m', '15m']:
            # Para alta frecuencia simulamos Finnhub/AllTick con Rate Limiting estricto
            return await self._fetch_finnhub_ws_fallback(symbol, timeframe, limit)
        else:
            # Para media/baja frecuencia usamos yfinance con Lock para evitar bans
            return await self._fetch_yfinance_safe(symbol, timeframe, limit)

    async def _fetch_yfinance_safe(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        async with self.yfinance_lock:
            self.request_count += 1
            if self.request_count > 1900:
                logger.warning("Límite de yfinance cercano. Pausando orquestador 60s.")
                await asyncio.sleep(60)
                self.request_count = 0
            
            try:
                # Ejecutamos llamadas síncronas de yfinance en un hilo separado
                df = await asyncio.to_thread(
                    lambda: yf.download(tickers=symbol, interval=timeframe, period="max", progress=False).tail(limit)
                )
                return self._clean_dataframe(df)
            except Exception as e:
                logger.error(f"Fallo en YFinance para {symbol}: {e}")
                return pd.DataFrame()

    async def _fetch_finnhub_ws_fallback(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Implementación de un cliente REST de alta frecuencia con mitigación de RPM"""
        async with self.finnhub_semaphore:
            try:
                # Placeholder activo para conexión a proveedor de Nivel 1 (IEX/SIP)
                # Se simula el fallback construyendo a partir de yf debido a la ausencia de API Key explícita
                # En producción real se mapea a httpx.AsyncClient -> api.finnhub.io/api/v1/stock/candle
                df = await asyncio.to_thread(
                    lambda: yf.download(tickers=symbol, interval=timeframe, period="5d", progress=False).tail(limit)
                )
                return self._clean_dataframe(df)
            except Exception as e:
                logger.error(f"Fallo en capa de alta frecuencia para {symbol}: {e}")
                return pd.DataFrame()

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Estandarización absoluta del DataFrame. Manejo de NaN por interpolación lineal
        y aplanamiento de MultiIndex de pandas 2.x
        """
        if df.empty:
            return df
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
            
        # Homogenizar nombres de columnas
        expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        available_cols = [c for c in expected_cols if c in df.columns]
        df = df[available_cols].copy()
        
        # Tratamiento estricto de valores nulos (Forward Fill -> Interpolación -> Drop)
        df.ffill(inplace=True)
        df.interpolate(method='linear', limit_direction='both', inplace=True)
        df.dropna(inplace=True)
        
        # Asegurar tipos numéricos para el motor matricial
        return df.astype(np.float64)