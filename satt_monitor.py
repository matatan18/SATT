import time
import logging
import numpy as np
from datetime import datetime
from indicator_calculator import IndicatorCalculator
from typing import Union

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SATTMonitor:
    def __init__(self, config_manager, api_manager, ui_manager, alert_manager, data_provider):
        logging.info("Inicializando clase SATTMonitor...")
        
        self.config_manager = config_manager
        self.api_manager = api_manager
        self.ui_manager = ui_manager
        self.alert_manager = alert_manager
        # ACTIVADO: Ahora guardamos el data_provider híbrido
        self.data_provider = data_provider 

        self.indicator_calculator = IndicatorCalculator(self.api_manager)
        
        self.is_running = True
        self.monitor_interval_seconds = 60 
        self.macro_check_interval_seconds = 3600 
        self.last_macro_check_time = 0

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
        """Wrapper para obtener datos de velas."""
        api_symbol = ticker.replace('/USD', 'USDT')
        klines = self.api_manager.get_candlestick_data(api_symbol, interval, limit)
        if not klines:
            logging.error(f"No se pudieron obtener datos de velas para {ticker} ({interval}).")
        return klines

    def _check_rsi_alerts(self, asset: dict):
        ticker = asset['ticker']
        klines_monthly = self._get_ohlcv_data(ticker, self.interval_map["mensual"], limit=100)
        if klines_monthly:
            close_prices_monthly = [kline['close'] for kline in klines_monthly]
            current_rsi_monthly = self.indicator_calculator.calculate_rsi(close_prices_monthly)
            
            formatted_rsi_monthly = f"{current_rsi_monthly:.2f}" if current_rsi_monthly is not None and not np.isnan(current_rsi_monthly) else "N/A"
            rsi_manual_monthly = asset.get('rsi_mensual_manual')

            if rsi_manual_monthly is not None and current_rsi_monthly is not None and not np.isnan(current_rsi_monthly):
                old_status = asset.get('rsi_mensual_status', 'Pendiente')
                new_status = self.indicator_calculator.get_rsi_status(rsi_manual_monthly, current_rsi_monthly)
                asset['rsi_mensual_actual'] = float(formatted_rsi_monthly) if formatted_rsi_monthly != "N/A" else None

                if new_status != old_status:
                    asset['rsi_mensual_status'] = new_status
                    message = f"ALERTA RSI Mensual para {ticker}: Ha cambiado de '{old_status}' a '{new_status}'. RSI Actual: {formatted_rsi_monthly}, RSI Manual: {rsi_manual_monthly:.2f}"
                    self.alert_manager.send_alert("RSI Mensual", message)
                    logging.info(message)
            else:
                asset['rsi_mensual_status'] = "Datos insuficientes/Manual no establecido"
                asset['rsi_mensual_actual'] = None
        else:
            asset['rsi_mensual_status'] = "Error al obtener datos"
            asset['rsi_mensual_actual'] = None

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
                asset['rsi_semanal_status'] = "Datos insuficientes/Manual no establecido"
                asset['rsi_semanal_actual'] = None
        else:
            asset['rsi_semanal_status'] = "Error al obtener datos"
            asset['rsi_semanal_actual'] = None

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
                message = f"ALERTA Tendencia de Mercado para {ticker}: Ha cambiado de '{old_trend_status}' a '{new_trend_status}'."
                self.alert_manager.send_alert("Tendencia Mercado", message)
                logging.info(message)
        else:
            asset['market_trend_status'] = "Datos insuficientes para tendencia"

    def _check_asset_conditions(self, asset: dict):
        ticker = asset['ticker']
        sl_price = asset.get('sl_price')
        tp_price = asset.get('tp_price')
        max_price_alert = asset.get('maximo')
        min_price_alert = asset.get('minimo')

        # MODIFICADO: Usamos el DataProvider Híbrido en lugar del api_manager roto
        if hasattr(self, 'data_provider') and self.data_provider is not None:
            current_price = self.data_provider.get_current_price(ticker)
        else:
            api_formatted_ticker = ticker.replace('/USD', 'USDT')
            current_price = self.api_manager.get_current_price(api_formatted_ticker)

        if current_price is None:
            logging.error(f"No se pudo obtener el precio actual para {ticker} desde el DataProvider.")
            return

        self.ui_manager.update_price_cache({ticker: current_price}) 
        asset['current_price'] = current_price 

        logging.info(f"Chequeando {ticker}. Precio actual: {current_price:.4f}")

        # --- Chequeo de SL ---
        if sl_price is not None:
            sl_alert_state = asset.get('sl_alert_state', 'Pendiente')
            if current_price <= sl_price and sl_alert_state == 'Pendiente':
                message = f"ALERTA: {ticker} cayó a {current_price:.4f} (SL: {sl_price:.4f})."
                self.alert_manager.send_alert("SL ALCANZADO", message)
                asset['sl_alert_state'] = 'Disparada'
                asset['status'] = 'SL Alcanzado'
            elif current_price > sl_price and sl_alert_state == 'Disparada':
                asset['sl_alert_state'] = 'Pendiente'
                asset['status'] = 'Monitoreando'

        # --- Chequeo de TP ---
        if tp_price is not None:
            tp_alert_state = asset.get('tp_alert_state', 'Pendiente')
            if current_price >= tp_price and tp_alert_state == 'Pendiente':
                message = f"ALERTA: {ticker} subió a {current_price:.4f} (TP: {tp_price:.4f})."
                self.alert_manager.send_alert("TP ALCANZADO", message)
                asset['tp_alert_state'] = 'Disparada'
                asset['status'] = 'TP Alcanzado'
            elif current_price < tp_price and tp_alert_state == 'Disparada':
                asset['tp_alert_state'] = 'Pendiente'
                asset['status'] = 'Monitoreando'

        # --- Chequeo de Máximo ---
        if max_price_alert is not None:
            maximo_status = asset.get('maximo_status', 'Pendiente')
            if current_price >= max_price_alert and maximo_status == 'Pendiente':
                asset['maximo_status'] = 'Disparada'
            elif current_price < max_price_alert and maximo_status == 'Disparada':
                asset['maximo_status'] = 'Pendiente'

        # --- Chequeo de Mínimo ---
        if min_price_alert is not None:
            minimo_status = asset.get('minimo_status', 'Pendiente')
            if current_price <= min_price_alert and minimo_status == 'Pendiente':
                asset['minimo_status'] = 'Disparada'
            elif current_price > min_price_alert and minimo_status == 'Disparada':
                asset['minimo_status'] = 'Pendiente'

        # --- Chequeo de OLS ---
        if 'ols' in asset and isinstance(asset['ols'], list):
            for i, ol_data in enumerate(asset['ols']):
                ol_price = ol_data.get('price')
                ol_status = ol_data.get('status', 'Pendiente')
                if ol_price is not None:
                    ol_type = f"OL {i+1}"
                    if current_price <= ol_price and ol_status == 'Pendiente':
                        ol_data['status'] = 'Disparada'
                    elif current_price > ol_price and ol_status == 'Disparada':
                        ol_data['status'] = 'Pendiente'

        # Solo procesamos alertas de indicadores si no es una acción o si implementamos soporte completo
        if asset.get('asset_type', '').lower() != 'stock':
            self._check_rsi_alerts(asset)

    def start_monitoring(self):
        logging.info("Iniciando monitoreo de SATT...")
        try:
            while self.is_running:
                config = self.config_manager.get_config()
                assets_to_monitor = config.get('assets_to_monitor', [])

                for asset in assets_to_monitor:
                    if asset.get('status') == 'Monitoreando' or asset.get('current_price') is None or asset.get('current_price') == 0:
                        self._check_asset_conditions(asset)
                    else:
                        logging.info(f"Saltando {asset.get('ticker')}: Estatus '{asset.get('status')}'")

                self.config_manager.save_config(config)
                time.sleep(self.monitor_interval_seconds)

        except KeyboardInterrupt:
            logging.info("Monitoreo detenido.")
        except Exception as e:
            logging.critical(f"Error en monitoreo: {e}", exc_info=True)
