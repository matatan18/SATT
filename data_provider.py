# data_provider.py
import time
import random
import logging
from typing import Optional # ¡Añade esta importación!

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DataProvider:
    def __init__(self):
        """
        Inicializa el DataProvider.
        En una implementación real, aquí se configurarían las APIs de exchange.
        """
        logging.info("DataProvider inicializado. Usando precios simulados.")
        # Podemos almacenar algunos precios simulados para prueba
        self._simulated_prices = {
            "BTC/USD": 60000.00,
            "ETH/USD": 3000.00,
            "XRP/USD": 0.50,
            "ADA/USD": 0.30,
        }

    # Cambia la línea de abajo de 'float | None' a 'Optional[float]'
    def get_current_price(self, ticker: str) -> Optional[float]:
        """
        Obtiene el precio actual de un activo dado su ticker.
        Por ahora, devuelve un precio simulado que varía ligeramente.
        """
        if ticker in self._simulated_prices:
            # Simular una pequeña variación en el precio
            variation = (random.random() - 0.5) * 0.01 * self._simulated_prices[ticker] # +/- 0.5%
            current_price = self._simulated_prices[ticker] + variation
            self._simulated_prices[ticker] = current_price # Actualiza el precio simulado
            logging.debug(f"Simulando precio para {ticker}: {current_price:.4f}")
            return current_price
        else:
            logging.warning(f"No se encontró precio simulado para el ticker: {ticker}. Devolviendo None.")
            return None

    def get_historical_data(self, ticker: str, interval: str, limit: int) -> list:
        """
        Método para obtener datos históricos (placeholder por ahora).
        Será implementado cuando se agreguen indicadores técnicos (RSI, MACD).
        """
        logging.info(f"Solicitando datos históricos para {ticker}, intervalo {interval}, límite {limit}.")
        # Devolver datos de ejemplo o vacíos por ahora
        return []

# Ejemplo de uso (opcional, para probar la clase directamente)
if __name__ == "__main__":
    dp = DataProvider()
    print("Precios iniciales simulados:")
    print(f"BTC/USD: {dp.get_current_price('BTC/USD'):.2f}")
    print(f"ETH/USD: {dp.get_current_price('ETH/USD'):.2f}")
    
    print("\nPrecios después de unas segundos (simulando variación):")
    time.sleep(2)
    print(f"BTC/USD: {dp.get_current_price('BTC/USD'):.2f}")
    print(f"ETH/USD: {dp.get_current_price('ETH/USD'):.2f}")
    
    print(f"\nIntentando obtener un ticker no definido: {dp.get_current_price('XYZ/USD')}")
