import pandas as pd
import logging
from api_manager import APIManager
import datetime as dt
import yfinance as yf

class IndicatorCalculator:
    def __init__(self, api_manager: APIManager):
        self.api_manager = api_manager
        logging.info("IndicatorCalculator inicializado con soporte Híbrido.")

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
        """Calcula el RSI (Relative Strength Index) para un DataFrame de velas."""
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
        """Calcula el MACD, la línea de señal y el histograma."""
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
        """Calcula los niveles de retroceso de Fibonacci."""
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
        Obtiene datos OHLCV históricos híbridos. Primero intenta con Binance para Criptos,
        y si falla o el tipo es acción, usa Yahoo Finance como motor de respaldo.
        """
        logging.debug(f"Buscando histórico para {symbol} ({asset_type}) en intervalo {interval} (límite {limit}).")
        
        # --- INTENTO 1: BINANCE (Para Crypto) ---
        if asset_type.lower() != 'stock':
            try:
                klines_raw = self.api_manager.get_historical_klines(symbol, interval, limit, asset_type)
                if klines_raw:
                    df = pd.DataFrame(klines_raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df['open'] = pd.to_numeric(df['open'])
                    df['high'] = pd.to_numeric(df['high'])
                    df['low'] = pd.to_numeric(df['low'])
                    df['close'] = pd.to_numeric(df['close'])
                    df['volume'] = pd.to_numeric(df['volume'])
                    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
                    df = df.set_index('timestamp').sort_index()
                    return df
            except Exception as e:
                logging.info(f"Fallo en Binance para {symbol} o no se encontró el activo. Pasando a Yahoo Finance... [{e}]")

        # --- INTENTO 2: YAHOO FINANCE (Para Acciones y Respaldo) ---
        try:
            # Mapeo de intervalos de Binance a Yahoo Finance
            yf_intervals = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h', '1d': '1d', '1w': '1wk', '1M': '1mo'}
            yf_interval = yf_intervals.get(interval, '1d')
            
            # Estimación burda del periodo según el límite para no descargar de más
            periodo = "1mo"
            if yf_interval == '1d': periodo = "3mo" if limit <= 60 else "6mo"
            elif yf_interval in ['1wk', '1mo']: periodo = "max"
            else: periodo = "7d" # Intervalos de minutos tienen restricciones de días en Yahoo
            
            # Adaptamos formato (ej: por si ingresaste BTC/USD en vez de BTC-USD)
            yf_ticker = symbol.upper().replace("/", "-")
            
            logging.info(f"Descargando históricos de Yahoo Finance para {yf_ticker} (Intervalo: {yf_interval}, Periodo: {periodo})")
            ticker_obj = yf.Ticker(yf_ticker)
            history = ticker_obj.history(period=periodo, interval=yf_interval)
            
            if not history.empty:
                # Estandarizamos el DataFrame al formato del resto del bot
                df_yf = history.reset_index()
                df_yf.rename(columns={'Date': 'timestamp', 'Datetime': 'timestamp', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
                df_yf['timestamp'] = pd.to_datetime(df_yf['timestamp'])
                df_yf = df_yf[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()
                df_yf = df_yf.set_index('timestamp').sort_index()
                
                # Cortamos al límite solicitado para no saturar los indicadores
                return df_yf.tail(limit)
                
        except Exception as e:
            logging.error(f"Error crítico al construir histórico en Yahoo Finance para {symbol}: {e}")
            
        return pd.DataFrame()
