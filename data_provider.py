# data_provider.py
import logging
from typing import Optional
from binance.client import Client
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataProvider:
    def __init__(self):
        """
        Inicializa el DataProvider con soporte híbrido para Binance y Yahoo Finance.
        """
        logging.info("Inicializando DataProvider Híbrido (Binance + Yahoo Finance)...")
        # Cliente público de Binance (no requiere API keys para consultar precios públicos)
        try:
            self.binance_client = Client("", "")
            logging.info("Conexión con API pública de Binance establecida.")
        except Exception as e:
            logging.error(f"No se pudo inicializar el cliente de Binance: {e}")
            self.binance_client = None

    def _format_ticker_binance(self, ticker: str) -> str:
        """Adapta formatos comunes como BTC/USD o BTC-USD al estándar de Binance: BTCUSDT"""
        t = ticker.upper().replace("/", "").replace("-", "")
        if t.endswith("USD") and not t.endswith("USDT"):
            t = t + "T"  # Convierte BTCUSD en BTCUSDT
        return t

    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Obtiene el precio actual. Primero intenta en Binance (Crypto), 
        y si falla o no existe, busca en Yahoo Finance (Acciones / Respaldo).
        """
        # --- INTENTO 1: BINANCE ---
        if self.binance_client:
            binance_ticker = self._format_ticker_binance(ticker)
            try:
                logging.info(f"Buscando {binance_ticker} en Binance...")
                ticker_info = self.binance_client.get_symbol_ticker(symbol=binance_ticker)
                price = float(ticker_info['price'])
                logging.info(f"¡Éxito en Binance! {ticker} = {price:.4f}")
                return price
            except Exception:
                logging.info(f"Activo [{ticker}] no encontrado en Binance. Pasando a Yahoo Finance...")

        # --- INTENTO 2: YAHOO FINANCE (Acciones y Respaldo) ---
        try:
            # Para Yahoo, si usan barras o guiones, a veces conviene transformarlos (ej: BTC-USD)
            yf_ticker = ticker.upper().replace("/", "-")
            logging.info(f"Buscando {yf_ticker} en Yahoo Finance...")
            stock = yf.Ticker(yf_ticker)
            
            # Intentamos obtener el precio de la última sesión o del mercado actual
            fast_info = stock.fast_info
            if 'last_price' in fast_info and fast_info['last_price'] is not None:
                price = float(fast_info['last_price'])
                logging.info(f"¡Éxito en Yahoo Finance! {yf_ticker} = {price:.4f}")
                return price
            
            # Respaldo secundario por si fast_info viene vacío
            history = stock.history(period="1d")
            if not history.empty:
                price = float(history['Close'].iloc[-1])
                logging.info(f"¡Éxito en Yahoo Finance (Historial)! {yf_ticker} = {price:.4f}")
                return price
                
        except Exception as e:
            logging.error(f"Error crítico: No se pudo obtener el precio de {ticker} en ningún proveedor. [{e}]")
        
        return None

    def get_historical_data(self, ticker: str, interval: str, limit: int) -> list:
        """
        Obtiene datos históricos para el cálculo de indicadores (RSI, etc.)
        """
        logging.info(f"Solicitando datos históricos para {ticker} (Intervalo: {interval}, Límite: {limit}).")
        # Aquí se puede expandir la misma lógica híbrida para las velas del RSI
        return []

if __name__ == "__main__":
    dp = DataProvider()
    print("\n--- PROBANDO PROVEEDOR HÍBRIDO ---")
    print(f"Precio BTC/USDT (Binance): {dp.get_current_price('BTCUSDT')}")
    print(f"Precio AAPL (Yahoo Finance): {dp.get_current_price('AAPL')}")
    print(f"Precio TSLA (Yahoo Finance): {dp.get_current_price('TSLA')}")
