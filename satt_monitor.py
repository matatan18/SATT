import time
import logging
import numpy as np
from datetime import datetime
# No necesitamos importar ConfigManager, APIManager, etc. aquí si los recibimos como argumentos
# from config_manager import ConfigManager # <- Eliminar esta línea
# from api_manager import APIManager       # <- Eliminar esta línea
# from alert_manager import AlertManager   # <- Eliminar esta línea
# from ui_manager import UIManager         # <- Eliminar esta línea
from indicator_calculator import IndicatorCalculator # Esta sí la necesitamos para crear una instancia
from typing import Union

# Configuración básica de logging (asegúrate de que sea la misma en todos tus archivos)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SATTMonitor:
    # MODIFICADO: Ahora el constructor recibe las instancias de los managers
    def __init__(self, config_manager, api_manager, ui_manager, alert_manager, data_provider):
        logging.info("Inicializando clase SATTMonitor...")
        
        # Asignamos las instancias de los managers que nos fueron pasadas
        self.config_manager = config_manager
        self.api_manager = api_manager
        self.ui_manager = ui_manager
        self.alert_manager = alert_manager
        # self.data_provider = data_provider # Si SATTMonitor directamente no usa data_provider, no es estrictamente necesario pasarlo aquí

        # IndicatorCalculator sí puede crearse aquí, ya que usa el api_manager compartido
        self.indicator_calculator = IndicatorCalculator(self.api_manager)
        
        self.is_running = True
        self.monitor_interval_seconds = 60 # Frecuencia de chequeo principal (ej. cada 60 segundos)
        self.macro_check_interval_seconds = 3600 # Chequeo de macro indicadores (ej. cada 1 hora)
        self.last_macro_check_time = 0

        # Mapeo de intervalos para Binance (si usas otro exchange, ajusta aquí)
        self.interval_map = {
            "mensual": "1M",
            "semanal": "1w",
            "1d": "1d",
            "4h": "4h",
            "1h": "1h",
            "15min": "15m"
        }
        logging.info("Clase SATTMonitor inicializada.")

    def _get_ohlcv_data(self, ticker: str, interval: str, limit: int = 100) -> Union[list, None]:
        """
        Wrapper para obtener datos de velas del APIManager, incluyendo manejo de símbolos.
        """
        api_symbol = ticker.replace('/USD', 'USDT')
        klines = self.api_manager.get_candlestick_data(api_symbol, interval, limit)
        if not klines:
            logging.error(f"No se pudieron obtener datos de velas para {ticker} ({interval}).")
        return klines

    def _check_rsi_alerts(self, asset: dict):
        ticker = asset['ticker']
        current_time = datetime.now()

        # --- RSI Mensual ---
        klines_monthly = self._get_ohlcv_data(ticker, self.interval_map["mensual"], limit=100)
        if klines_monthly:
            close_prices_monthly = [kline['close'] for kline in klines_monthly]
            current_rsi_monthly = self.indicator_calculator.calculate_rsi(close_prices_monthly)
            
            # Formatear el RSI a dos decimales o None si no se pudo calcular
            formatted_rsi_monthly = f"{current_rsi_monthly:.2f}" if current_rsi_monthly is not None and not np.isnan(current_rsi_monthly) else "N/A"
            
            rsi_manual_monthly = asset.get('rsi_mensual_manual')

            if rsi_manual_monthly is not None and current_rsi_monthly is not None and not np.isnan(current_rsi_monthly):
                old_status = asset.get('rsi_mensual_status', 'Pendiente')
                new_status = self.indicator_calculator.get_rsi_status(rsi_manual_monthly, current_rsi_monthly)
                
                # Actualizar el RSI actual en la configuración para persistencia y UI
                asset['rsi_mensual_actual'] = float(formatted_rsi_monthly) if formatted_rsi_monthly != "N/A" else None

                if new_status != old_status:
                    asset['rsi_mensual_status'] = new_status
                    message = f"ALERTA RSI Mensual para {ticker}: Ha cambiado de '{old_status}' a '{new_status}'. RSI Actual: {formatted_rsi_monthly}, RSI Manual: {rsi_manual_monthly:.2f}"
                    self.alert_manager.send_alert("RSI Mensual", message)
                    logging.info(message)
                else:
                    logging.debug(f"RSI Mensual para {ticker} se mantiene en '{new_status}'.")
            else:
                asset['rsi_mensual_status'] = "Datos insuficientes/Manual no establecido"
                asset['rsi_mensual_actual'] = None
                logging.warning(f"No se pudo calcular el RSI Mensual para {ticker} o RSI manual no configurado.")
        else:
            asset['rsi_mensual_status'] = "Error al obtener datos"
            asset['rsi_mensual_actual'] = None
            logging.error(f"No se pudieron obtener las velas mensuales para {ticker}.")


        # --- RSI Semanal ---
        klines_weekly = self._get_ohlcv_data(ticker, self.interval_map["semanal"], limit=100)
        if klines_weekly:
            close_prices_weekly = [kline['close'] for kline in klines_weekly]
            current_rsi_weekly = self.indicator_calculator.calculate_rsi(close_prices_weekly)
            
            formatted_rsi_weekly = f"{current_rsi_weekly:.2f}" if current_rsi_weekly is not None and not np.isnan(current_rsi_weekly) else "N/A"
            
            rsi_manual_weekly = asset.get('rsi_semanal_manual')

            if rsi_manual_weekly is not None and current_rsi_weekly is not None and not np.isnan(current_rsi_weekly):
                old_status = asset.get('rsi_semanal_status', 'Pendiente')
                new_status = self.indicator_calculator.get_rsi_status(rsi_manual_weekly, current_rsi_weekly)

                asset['rsi_semanal_actual'] = float(formatted_rsi_weekly) if formatted_rsi_weekly != "N/A" else None
                
                if new_status != old_status:
                    asset['rsi_semanal_status'] = new_status
                    message = f"ALERTA RSI Semanal para {ticker}: Ha cambiado de '{old_status}' a '{new_status}'. RSI Actual: {formatted_rsi_weekly}, RSI Manual: {rsi_manual_weekly:.2f}"
                    self.alert_manager.send_alert("RSI Semanal", message)
                    logging.info(message)
                else:
                    logging.debug(f"RSI Semanal para {ticker} se mantiene en '{new_status}'.")
            else:
                asset['rsi_semanal_status'] = "Datos insuficientes/Manual no establecido"
                asset['rsi_semanal_actual'] = None
                logging.warning(f"No se pudo calcular el RSI Semanal para {ticker} o RSI manual no configurado.")
        else:
            asset['rsi_semanal_status'] = "Error al obtener datos"
            asset['rsi_semanal_actual'] = None
            logging.error(f"No se pudieron obtener las velas semanales para {ticker}.")

        # --- Lógica de Tendencia de Mercado General para el activo ---
        rsi_statuses_for_trend = []
        if asset.get('rsi_mensual_status') not in ["Pendiente", "Datos insuficientes/Manual no establecido", "Error al obtener datos"]:
            rsi_statuses_for_trend.append(asset['rsi_mensual_status'])
        if asset.get('rsi_semanal_status') not in ["Pendiente", "Datos insuficientes/Manual no establecido", "Error al obtener datos"]:
            rsi_statuses_for_trend.append(asset['rsi_semanal_status'])
        
        if rsi_statuses_for_trend:
            old_trend_status = asset.get('market_trend_status', 'Pendiente')
            new_trend_status = self.indicator_calculator.get_market_trend_status(rsi_statuses_for_trend)
            
            if new_trend_status != old_trend_status:
                asset['market_trend_status'] = new_trend_status
                message = f"ALERTA Tendencia de Mercado para {ticker}: Ha cambiado de '{old_trend_status}' a '{new_trend_status}' según los RSI."
                self.alert_manager.send_alert("Tendencia Mercado", message)
                logging.info(message)
            else:
                logging.debug(f"Tendencia de Mercado para {ticker} se mantiene en '{new_trend_status}'.")
        else:
            asset['market_trend_status'] = "Datos insuficientes para tendencia"
            logging.info(f"No hay suficientes datos de RSI para determinar la tendencia de mercado para {ticker}.")


    def _check_asset_conditions(self, asset: dict):
        ticker = asset['ticker']
        entry_price = asset['entry_price']
        sl_price = asset.get('sl_price')
        tp_price = asset.get('tp_price')
        max_price_alert = asset.get('maximo')
        min_price_alert = asset.get('minimo')

        # Obtener el precio actual directamente del api_manager
        # Es crucial que api_manager.get_current_price() sepa cómo manejar el formato 'ETH/USD'
        # o que hagas la conversión aquí a 'ETHUSDT' si tu API lo requiere.
        api_formatted_ticker = ticker.replace('/USD', 'USDT') # Por ejemplo, si la API usa USDT
        current_price = self.api_manager.get_current_price(api_formatted_ticker)

        if current_price is None:
            logging.error(f"No se pudo obtener el precio actual para {ticker}. Saltando chequeo de condiciones.")
            return

        # Actualizar el caché de precios en ui_manager para que el menú principal lo tenga
        # Esto es importante para mantener un estado compartido de los precios
        self.ui_manager.update_price_cache({ticker: current_price}) 
        
        asset['current_price'] = current_price # Guardar en el asset para persistencia si es necesario

        logging.info(f"Chequeando {ticker}. Precio actual: {current_price:.4f}")

        # --- Chequeo de SL ---
        if sl_price is not None:
            sl_alert_state = asset.get('sl_alert_state', 'Pendiente')
            if current_price <= sl_price and sl_alert_state == 'Pendiente':
                message = f"ALERTA: El precio de {ticker} ha caído a {current_price:.4f} o por debajo de su SL ({sl_price:.4f})."
                self.alert_manager.send_alert("SL ALCANZADO", message)
                asset['sl_alert_state'] = 'Disparada'
                asset['status'] = 'SL Alcanzado'
                logging.warning(message)
            elif current_price > sl_price and sl_alert_state == 'Disparada':
                asset['sl_alert_state'] = 'Pendiente'
                asset['status'] = 'Monitoreando'
                logging.info(f"SL para {ticker} reseteado a Pendiente. Precio actual: {current_price:.4f}")

        # --- Chequeo de TP ---
        if tp_price is not None:
            tp_alert_state = asset.get('tp_alert_state', 'Pendiente')
            if current_price >= tp_price and tp_alert_state == 'Pendiente':
                message = f"ALERTA: El precio de {ticker} ha subido a {current_price:.4f} o por encima de su TP ({tp_price:.4f})."
                self.alert_manager.send_alert("TP ALCANZADO", message)
                asset['tp_alert_state'] = 'Disparada'
                asset['status'] = 'TP Alcanzado'
                logging.warning(message)
            elif current_price < tp_price and tp_alert_state == 'Disparada':
                asset['tp_alert_state'] = 'Pendiente'
                asset['status'] = 'Monitoreando'
                logging.info(f"TP para {ticker} reseteado a Pendiente. Precio actual: {current_price:.4f}")

        # --- Chequeo de Máximo ---
        if max_price_alert is not None:
            maximo_status = asset.get('maximo_status', 'Pendiente')
            if current_price >= max_price_alert and maximo_status == 'Pendiente':
                message = f"ALERTA: El precio de {ticker} ha superado el máximo establecido de {max_price_alert:.4f}. Precio actual: {current_price:.4f}."
                self.alert_manager.send_alert("MÁXIMO ALCANZADO", message)
                asset['maximo_status'] = 'Disparada'
                logging.warning(message)
            elif current_price < max_price_alert and maximo_status == 'Disparada':
                asset['maximo_status'] = 'Pendiente'
                logging.info(f"Máximo para {ticker} reseteado a Pendiente. Precio actual: {current_price:.4f}")


        # --- Chequeo de Mínimo ---
        if min_price_alert is not None:
            minimo_status = asset.get('minimo_status', 'Pendiente')
            if current_price <= min_price_alert and minimo_status == 'Pendiente':
                message = f"ALERTA: El precio de {ticker} ha caído por debajo del mínimo establecido de {min_price_alert:.4f}. Precio actual: {current_price:.4f}."
                self.alert_manager.send_alert("MÍNIMO ALCANZADO", message)
                asset['minimo_status'] = 'Disparada'
                logging.warning(message)
            elif current_price > min_price_alert and minimo_status == 'Disparada':
                asset['minimo_status'] = 'Pendiente'
                logging.info(f"Mínimo para {ticker} reseteado a Pendiente. Precio actual: {current_price:.4f}")


        # --- Chequeo de OLS (Ordenes Límite / Recompras) ---
        if 'ols' in asset and isinstance(asset['ols'], list):
            for i, ol_data in enumerate(asset['ols']):
                ol_price = ol_data.get('price')
                ol_status = ol_data.get('status', 'Pendiente')

                if ol_price is not None:
                    ol_type = f"OL {i+1}"

                    if current_price <= ol_price and ol_status == 'Pendiente':
                        message = f"ALERTA: El precio de {ticker} ha alcanzado o superado tu {ol_type} de {ol_price:.4f}. Precio actual: {current_price:.4f}."
                        self.alert_manager.send_alert(f"{ol_type} ALCANZADA", message)
                        ol_data['status'] = 'Disparada'
                        logging.warning(message)
                    elif current_price > ol_price and ol_status == 'Disparada':
                        ol_data['status'] = 'Pendiente'
                        logging.info(f"{ol_type} para {ticker} reseteada a Pendiente. Precio actual: {current_price:.4f}")

        # Chequeo de Alertas de RSI (Mensual y Semanal)
        self._check_rsi_alerts(asset)


    def start_monitoring(self):
        logging.info("Iniciando monitoreo de SATT...")
        try:
            while self.is_running:
                config = self.config_manager.get_config()
                assets_to_monitor = config.get('assets_to_monitor', [])

                for asset in assets_to_monitor:
                    if asset.get('status') == 'Monitoreando':
                        self._check_asset_conditions(asset)
                    else:
                        logging.info(f"Saltando {asset.get('ticker')}: Estatus '{asset.get('status')}'.")

                self.config_manager.save_config(config)

                # Eliminamos esta línea del monitor, ya que el display_main_menu
                # es parte del bucle principal en main.py y se encarga de la UI.
                # self.ui_manager.display_main_menu(config) # <- Eliminar o comentar esta línea

                time.sleep(self.monitor_interval_seconds)

        except KeyboardInterrupt:
            logging.info("Monitoreo detenido por el usuario (Ctrl+C).")
        except Exception as e:
            logging.critical(f"Error crítico en el monitoreo: {e}", exc_info=True)
        finally:
            logging.info("SATT ha terminado.")

    def stop_monitoring(self):
        self.is_running = False
        logging.info("Deteniendo monitoreo...")

# Este bloque __main__ ya no es necesario aquí, ya que SATTMonitor será instanciado
# y ejecutado desde main.py en un hilo.
# if __name__ == "__main__":
#     monitor = SATTMonitor()
#     monitor.start_monitoring()
