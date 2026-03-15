import logging
import requests
from requests.exceptions import RequestException
import yfinance as yf

class APIManager:
    def __init__(self, base_url="https://api.binance.com/api/v3"):
        self.base_url = base_url
        logging.info(f"APIManager inicializado con URL de Binance: {self.base_url}")

    def _make_request(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logging.warning(f"Error en la petición a la API de Binance: {e}")
            return None

    def get_crypto_price(self, symbol):
        endpoint = "ticker/price"
        params = {"symbol": symbol}
        logging.debug(f"Intentando obtener precio para {symbol} de Binance.")
        data = self._make_request(endpoint, params)
        if data and 'price' in data:
            price = float(data['price'])
            logging.debug(f"Precio de {symbol} obtenido de Binance: {price}")
            return price
        
        logging.debug(f"No se pudo obtener el precio para {symbol} de Binance. Retornando None.")
        return None

    def get_yahoo_finance_current_price(self, symbol):
        """
        Obtiene el precio actual de un activo de Yahoo Finance.
        """
        try:
            ticker = yf.Ticker(symbol)
            price_info = ticker.info
            price = price_info.get('regularMarketPrice')
            
            if price:
                logging.debug(f"Precio de {symbol} obtenido de Yahoo Finance: {price}")
                return price
            else:
                logging.warning(f"No se encontró el precio actual para el símbolo {symbol} en Yahoo Finance.")
                return None
        except Exception as e:
            logging.error(f"Error al obtener el precio de {symbol} de Yahoo Finance: {e}")
            return None

    def get_asset_type(self, symbol: str) -> str:
        """
        Determina si un símbolo es una criptomoneda o una acción.
        """
        # Intentar con Binance para determinar si es una cripto
        try:
            url = f"{self.base_url}/ticker/price?symbol={symbol.upper()}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and 'price' in response.json():
                return 'crypto'
        except RequestException:
            pass # Si falla, podría ser una acción
        
        # Si no es una cripto en Binance, asumimos que es una acción
        return 'stock'

    def get_last_price(self, symbol):
        """
        Obtiene el último precio de un activo, priorizando Binance y usando Yahoo Finance como fallback.
        
        Args:
            symbol (str): El símbolo del activo (ej. BTCUSDT, AAPL, EURUSD=X).
            
        Returns:
            float: El último precio, o None si no se puede obtener de ninguna de las dos fuentes.
        """
        asset_type = self.get_asset_type(symbol)
        
        if asset_type == 'crypto':
            price = self.get_crypto_price(symbol)
        else:
            price = self.get_yahoo_finance_current_price(symbol)
        
        if price is not None:
            return price
        else:
            logging.error(f"No se pudo obtener el precio de {symbol} de ninguna de las fuentes.")
            return None

    def get_historical_klines(self, symbol, interval, limit, asset_type):
        """
        Obtiene los datos históricos de velas (OHLCV) para un símbolo e intervalo dados.
        """
        if asset_type == 'crypto':
            endpoint = "klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            logging.debug(f"Intentando obtener klines históricos para {symbol} en intervalo {interval} con límite {limit}.")
            data = self._make_request(endpoint, params)
            if data and isinstance(data, list):
                logging.debug(f"Klines históricos para {symbol} en {interval} obtenidos.")
                return data
            logging.error(f"No se pudieron obtener klines históricos para {symbol}.")
            return None
        elif asset_type == 'stock':
            try:
                ticker = yf.Ticker(symbol)
                # Mapear intervalos de Binance a intervalos de yfinance
                yfinance_interval_map = {
                    '1d': '1d',
                    '4h': '4h',
                    '1h': '1h',
                    '1m': '1m'
                }
                yfinance_period_map = {
                    '1d': '3mo',
                    '4h': '60d',
                    '1h': '30d',
                    '1m': '7d'
                }

                yf_interval = yfinance_interval_map.get(interval)
                yf_period = yfinance_period_map.get(interval)

                if not yf_interval or not yf_period:
                    logging.error(f"Intervalo de tiempo no soportado por Yahoo Finance: {interval}")
                    return None
                    
                data = ticker.history(period=yf_period, interval=yf_interval)
                if not data.empty:
                    klines = []
                    for index, row in data.iterrows():
                        klines.append([
                            index.timestamp() * 1000,
                            row['Open'],
                            row['High'],
                            row['Low'],
                            row['Close'],
                            row['Volume'],
                            index.timestamp() * 1000 + (60*60*1000 - 1) if yf_interval == '1h' else None,
                        ])
                    return klines
                else:
                    logging.error(f"No se pudieron obtener datos históricos de {symbol} de Yahoo Finance.")
                    return None
            except Exception as e:
                logging.error(f"Error al obtener datos históricos de Yahoo Finance para {symbol}: {e}")
                return None
        else:
            logging.warning(f"Tipo de activo no soportado para datos históricos: {asset_type}")
            return None
            
    def send_telegram_message(self, bot_token, chat_id, message):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message
        }
        try:
            response = requests.post(url, data=payload)
            response.raise_for_status()
            if response.status_code == 200:
                logging.info(f"Mensaje de Telegram enviado con éxito a chat ID {chat_id}.")
                return True
            else:
                logging.error(f"Error al enviar mensaje de Telegram: {response.text}")
                return False
        except RequestException as e:
            logging.error(f"Error de conexión al enviar mensaje de Telegram: {e}")
            return False

    def is_valid_symbol(self, symbol: str) -> bool:
        """
        Verifica si un símbolo es válido usando Binance y luego Yahoo Finance como fallback.
        """
        # Intentar con Binance primero
        try:
            url = f"{self.base_url}/ticker/price?symbol={symbol.upper()}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200 and 'price' in response.json():
                logging.debug(f"Validación exitosa de {symbol} con Binance.")
                return True
        except RequestException:
            pass # No hay problema, probamos con Yahoo Finance

        # Si Binance falla, intentar con Yahoo Finance
        try:
            ticker = yf.Ticker(symbol)
            price_info = ticker.info
            # Si el diccionario info no está vacío y no hay errores, asumimos que es válido
            if price_info and price_info.get('regularMarketPrice') is not None:
                logging.debug(f"Validación exitosa de {symbol} con Yahoo Finance.")
                return True
        except Exception:
            pass # Si Yahoo Finance falla, asumimos que no es válido

        logging.warning(f"El símbolo {symbol} no es válido en ninguna de las fuentes.")
        return False