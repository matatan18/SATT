import pandas as pd
import logging
from api_manager import APIManager
import datetime as dt

class IndicatorCalculator:
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        logging.info("IndicatorCalculator inicializado.")

    def calculate_indicators_for_asset(self, symbol: str, asset_type: str, intervals: list, limit: int) -> dict:
        data = {}
        for interval in intervals:
            try:
                # Obtener klines históricos y convertirlos a DataFrame
                klines_df = self._get_historical_ohlcv(symbol, interval, limit, asset_type)

                if klines_df.empty:
                    logging.warning(f"No se pudieron calcular indicadores para {symbol} en {interval} debido a la falta de datos.")
                    continue

                # Cálculo del RSI
                rsi_value = self._calculate_rsi(klines_df)
                
                # Cálculo del MACD
                macd_line = None
                macd_signal = None
                macd_hist = None
                
                if symbol == 'BTCUSDT' and interval == '1M':
                    macd_line, macd_signal, macd_hist = self._calculate_macd(klines_df)
                    logging.debug(f"MACD mensual calculado para BTCUSDT. MACD: {macd_line.iloc[-1]:.2f}, Señal: {macd_signal.iloc[-1]:.2f}")

                # Guardar los indicadores en el diccionario de datos
                data[interval] = {
                    "rsi": rsi_value,
                    "macd": macd_line,
                    "macdsignal": macd_signal,
                    "macd_hist": macd_hist
                }
                
            except Exception as e:
                logging.error(f"Error al calcular indicadores para {symbol} ({asset_type}) en el intervalo {interval}: {e}", exc_info=True)
        return data

    def _calculate_rsi(self, df: pd.DataFrame, window: int = 14) -> float:
        """
        Calcula el RSI (Relative Strength Index) para un DataFrame de velas.
        """
        if len(df) < window + 1:
            logging.warning("No hay suficientes datos para calcular el RSI.")
            return None
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
        avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]

    def _calculate_macd(self, df: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> tuple:
        """
        Calcula el MACD, la línea de señal y el histograma.
        """
        if len(df) < slow_period:
            logging.warning("No hay suficientes datos para calcular el MACD.")
            return (None, None, None)
        
        ema_fast = df['close'].ewm(span=fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow_period, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        macd_signal = macd_line.ewm(span=signal_period, adjust=False).mean()
        macd_hist = macd_line - macd_signal
        
        return macd_line, macd_signal, macd_hist

    def calculate_manual_fibonacci(self, choch_precio: float, bos_precio: float) -> dict:
        """
        Calcula los niveles de retroceso de Fibonacci basándose en los precios de CHOCH y BOS.
        CHOCH es 100% y BOS es 0%.
        """
        try:
            niveles = {
                "100%": choch_precio,
                "0.786": choch_precio - (choch_precio - bos_precio) * 0.786,
                "0.618": choch_precio - (choch_precio - bos_precio) * 0.618,
                "0.5": choch_precio - (choch_precio - bos_precio) * 0.5,
                "0.382": choch_precio - (choch_precio - bos_precio) * 0.382,
                "0%": bos_precio
            }
            logging.debug(f"Niveles de Fibonacci calculados: {niveles}")
            return niveles
        except Exception as e:
            logging.error(f"Error al calcular niveles de Fibonacci con CHOCH={choch_precio} y BOS={bos_precio}: {e}")
            return {}

    def _get_historical_ohlcv(self, symbol: str, interval: str, limit: int, asset_type: str) -> pd.DataFrame:
        """
        Obtiene datos OHLCV históricos desde la API y los convierte a un DataFrame de Pandas.
        """
        logging.debug(f"Intentando obtener klines históricos para {symbol} en intervalo {interval} con límite {limit}.")
        try:
            klines_raw = self.api_manager.get_historical_klines(symbol, interval, limit, asset_type)

            if not klines_raw:
                logging.warning(f"No se obtuvieron datos históricos para {symbol} ({asset_type}) con intervalo {interval} y límite {limit}.")
                return pd.DataFrame() 

            df = pd.DataFrame(klines_raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['open'] = pd.to_numeric(df['open'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['close'] = pd.to_numeric(df['close'])
            df['volume'] = pd.to_numeric(df['volume'])
            
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
            df = df.set_index('timestamp')
            df = df.sort_index()

            logging.debug(f"Klines históricos para {symbol} en {interval} obtenidos.")
            return df
            
        except Exception as e:
            logging.error(f"Error al obtener o procesar datos históricos para {symbol} ({asset_type}) {interval}: {e}", exc_info=True)
            return pd.DataFrame()
