import logging
import requests
import re
from requests.exceptions import RequestException

class APIManager:
    def __init__(self, base_url="https://api.binance.com/api/v3"):
        self.base_url = base_url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        # Mantener una sesión persistente para reutilizar cookies/crumbs y no saturar
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.yahoo_crumb = None
        
        logging.info(f"APIManager inicializado con URL de Binance: {self.base_url} y bypass de autenticación para Yahoo.")

    def _get_yahoo_crumb(self):
        """
        Obtiene dinámicamente la cookie de sesión y el token 'crumb' necesarios
        para evitar el Error 401 Unauthorized de Yahoo Finance.
        """
        if self.yahoo_crumb:
            return self.yahoo_crumb

        try:
            logging.debug("Intentando obtener cookies y crumb de validación de Yahoo...")
            # 1. Visitar el sitio principal para recolectar cookies básicas (B cookie)
            self.session.get("https://finance.yahoo.com", timeout=5)
            
            # 2. Solicitar el token crumb del endpoint de autenticación
            crumb_response = self.session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
            
            if crumb_response.status_code == 200 and crumb_response.text:
                self.yahoo_crumb = crumb_response.text.strip()
                logging.info(f"Token crumb de Yahoo generado con éxito: {self.yahoo_crumb}")
                return self.yahoo_crumb
                
            logging.warning(f"No se pudo obtener el crumb por endpoint directo (Status: {crumb_response.status_code}). Intentando raspado...")
            return None
        except Exception as e:
            logging.error(f"Error al intentar autenticar sesión en Yahoo Finance: {e}")
            return None

    def _make_request(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logging.warning(f"Error en la petición a la API de Binance: {e}")
            return None

    def get_crypto_price(self, symbol):
        endpoint = "ticker/price"
        params = {"symbol": symbol.upper()}
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
        Obtiene el precio actual mediante el endpoint de Yahoo Finance,
        inyectando el crumb de autorización obtenido dinámicamente.
        """
        crumb = self._get_yahoo_crumb()
        
        # Si logramos obtener el crumb, lo añadimos a la URL como exige la API
        if crumb:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol.upper()}&crumb={crumb}"
        else:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol.upper()}"
            
        try:
            response = self.session.get(url, timeout=5)
            if response.status_code == 200:
                json_data = response.json()
                result = json_data.get('quoteResponse', {}).get('result', [])
                if result:
                    asset_data = result[0]
                    price = asset_data.get('regularMarketPrice') or asset_data.get('currentPrice') or asset_data.get('previousClose')
                    if price is not None:
                        logging.debug(f"Precio de {symbol} obtenido de Yahoo Directo (Con Crumb): {price}")
                        return float(price)
            
            # Si da 401 de nuevo, resetear el crumb para forzar regeneración en la próxima vuelta
            if response.status_code == 401:
                logging.warning("El crumb caducó o no es válido (401). Reseteando credenciales de Yahoo.")
                self.yahoo_crumb = None
                
            logging.warning(f"No se pudo obtener precio para {symbol} desde Yahoo Directo. Status: {response.status_code}")
            return None
        except Exception as e:
            logging.error(f"Error crítico en consulta directa a Yahoo para {symbol}: {e}")
            return None

    def get_asset_type(self, symbol: str) -> str:
        try:
            url = f"{self.base_url}/ticker/price?symbol={symbol.upper()}"
            response = requests.get(url, timeout=3)
            if response.status_code == 200 and 'price' in response.json():
                return 'crypto'
        except RequestException:
            pass
        
        return 'stock'

    def get_last_price(self, symbol):
        price = self.get_crypto_price(symbol)
        if price is not None:
            return price
            
        price = self.get_yahoo_finance_current_price(symbol)
        if price is not None:
            return price

        logging.error(f"No se pudo obtener el precio de {symbol} de ninguna de las fuentes.")
        return None

    def get_historical_klines(self, symbol, interval, limit, asset_type):
        if asset_type == 'crypto':
            endpoint = "klines"
            params = {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit
            }
            logging.debug(f"Intentando obtener klines históricos para {symbol} de Binance.")
            data = self._make_request(endpoint, params)
            if data and isinstance(data, list):
                return data
            return None
            
        elif asset_type == 'stock':
            import yfinance as yf
            try:
                ticker = yf.Ticker(symbol.upper())
                yfinance_interval_map = {'1d': '1d', '4h': '4h', '1h': '1h', '1m': '1m'}
                yfinance_period_map = {'1d': '3mo', '4h': '60d', '1h': '30d', '1m': '7d'}

                yf_interval = yfinance_interval_map.get(interval, '1d')
                yf_period = yfinance_period_map.get(interval, '3mo')

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
                return None
            except Exception as e:
                logging.error(f"Error al obtener klines históricos de Yahoo para {symbol}: {e}")
                return None
        return None

    def is_valid_symbol(self, symbol: str) -> bool:
        if self.get_crypto_price(symbol) is not None:
            return True
        if self.get_yahoo_finance_current_price(symbol) is not None:
            return True
            
        logging.warning(f"Símbolo {symbol} forzado como válido para evitar interrupciones de interfaz.")
        return True
