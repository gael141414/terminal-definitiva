import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any

class QuantitativeEngine:
    @staticmethod
    def apply_dynamic_bollinger(df: pd.DataFrame, window: int = 20, base_alpha: float = 2.0) -> pd.DataFrame:
        """
        Bollinger Bands Modificadas: Adapta el ancho del canal según la volatilidad extrema (ATR).
        """
        df['SMA'] = df['Close'].rolling(window=window).mean()
        df['STD'] = df['Close'].rolling(window=window).std()
        
        # Cálculo de True Range y ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        df['TR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATR'] = df['TR'].rolling(window=14).mean()
        
        # Alpha adaptativo
        mean_atr = df['ATR'].rolling(window=window).mean()
        adaptive_alpha = base_alpha * (df['ATR'] / mean_atr).fillna(1.0)
        
        df['Upper_Band'] = df['SMA'] + (adaptive_alpha * df['STD'])
        df['Lower_Band'] = df['SMA'] - (adaptive_alpha * df['STD'])
        return df

    @staticmethod
    def apply_volume_flows(df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica On-Balance Volume (OBV) y Money Flow Index (MFI) de forma vectorizada.
        """
        # OBV
        direction = np.sign(df['Close'].diff()).fillna(0)
        df['OBV'] = (df['Volume'] * direction).cumsum()
        df['OBV_SMA'] = df['OBV'].rolling(window=20).mean()
        
        # MFI (14)
        typical_price = (df['High'] + df['Low'] + df['Close']) / 3
        raw_money_flow = typical_price * df['Volume']
        
        pos_flow = np.where(typical_price > typical_price.shift(1), raw_money_flow, 0)
        neg_flow = np.where(typical_price < typical_price.shift(1), raw_money_flow, 0)
        
        pos_flow_sum = pd.Series(pos_flow).rolling(window=14).sum()
        neg_flow_sum = pd.Series(neg_flow).rolling(window=14).sum()
        
        money_ratio = pos_flow_sum / neg_flow_sum.replace(0, 1e-10) # Prevenir div by 0
        df['MFI'] = 100 - (100 / (1 + money_ratio))
        return df

    @staticmethod
    def identify_patterns_and_signals(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """
        Cruza la volatilidad de bandas dinámicas con flujos institucionales y price action.
        Señal: 1 (Compra), -1 (Venta), 0 (Mantener)
        """
        # Identificación Vectorizada de Martillo (Hammer)
        body = np.abs(df['Close'] - df['Open'])
        lower_shadow = np.minimum(df['Close'], df['Open']) - df['Low']
        upper_shadow = df['High'] - np.maximum(df['Close'], df['Open'])
        df['Is_Hammer'] = (lower_shadow >= 2 * body) & (upper_shadow <= body * 0.2)
        
        # Generación de Señal Combinada
        df['Signal'] = 0
        
        # Condición Compra: Toca banda inferior + Patrón Martillo + MFI sobrevendido + OBV revirtiendo
        buy_cond = (df['Low'] <= df['Lower_Band']) & df['Is_Hammer'] & (df['MFI'] < 35) & (df['OBV'] > df['OBV_SMA'])
        df.loc[buy_cond, 'Signal'] = 1
        
        # Condición Venta: Toca banda superior + MFI sobrecomprado
        sell_cond = (df['High'] >= df['Upper_Band']) & (df['MFI'] > 80)
        df.loc[sell_cond, 'Signal'] = -1
        
        last_signal = int(df['Signal'].iloc[-1])
        return df, last_signal