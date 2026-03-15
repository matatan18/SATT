import os
import time
import logging
import sys
from datetime import datetime

# Configuración de logging (asegúrate de que esté en DEBUG)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Importar tus clases de los otros módulos
from config_manager import ConfigManager
from api_manager import APIManager
from alert_manager import AlertManager
from ui_manager import UserInterface
from indicator_calculator import IndicatorCalculator

class SATT:
    """
    Sistema Automatizado de Trading e Indicadores (SATT)
    Clase principal que orquesta el funcionamiento de la aplicación.
    """
    def __init__(self):
        logging.info("Inicializando clase SATT")

        self.config_manager = ConfigManager('config.json')
        self.api_manager = APIManager()
        self.ui_manager = UserInterface(self.config_manager, self.api_manager)
        self.alert_manager = AlertManager(self.config_manager, self.api_manager, self.ui_manager)
        self.indicator_calculator = IndicatorCalculator(self.api_manager)

        self.last_update_time = 0

        general_settings = self.config_manager.get_general_settings()
        self.update_interval = general_settings.get('update_interval_seconds', 300)

        self.initial_load()

    def initial_load(self):
        """
        Carga la configuración inicial y precios.
        """
        logging.info("Cargando configuración inicial y precios.")
        self.update_all_asset_data()

    def _calculate_asset_metrics(self, asset_config, current_price, btc_price_usd, total_capital):
        """
        Calcula todos los SL, TP, RR (USD y BTC) para un activo, incluyendo sus órdenes límite.
        Almacena los resultados directamente en el diccionario asset_config.
        Retorna el SL y TP total de este activo para la sumatoria global.
        """
        symbol = asset_config.get('symbol', 'N/A')

        entry_price_main = asset_config.get('entry_price')
        sl_usd_entry_main = asset_config.get('sl_usd_entry')
        tp_usd_entry_main = asset_config.get('tp_usd_entry')

        limit_orders = asset_config.get('limit_orders', [])

        total_sl_activo_usd = 0.0
        total_tp_activo_usd = 0.0
        
        # --- LÓGICA CORREGIDA PARA CALCULAR SL/TP RESPETANDO EL SIGNO ---
        
        # Sumar SL/TP de la entrada principal si existe
        if sl_usd_entry_main is not None:
            total_sl_activo_usd += sl_usd_entry_main
            
        if tp_usd_entry_main is not None:
            total_tp_activo_usd += tp_usd_entry_main

        # Bucle para órdenes límite (CORREGIDO: siempre se ejecuta)
        for ol in limit_orders:
            ol_sl_usd = ol.get('sl_usd')
            ol_tp_usd = ol.get('tp_usd')
            
            if ol_sl_usd is not None:
                total_sl_activo_usd += ol_sl_usd
                
            if ol_tp_usd is not None:
                total_tp_activo_usd += ol_tp_usd

            if btc_price_usd > 0 and ol_sl_usd is not None and ol_tp_usd is not None:
                ol['sl_btc'] = (ol_sl_usd / btc_price_usd)
                ol['tp_btc'] = (ol_tp_usd / btc_price_usd)
            else:
                ol['sl_btc'] = 0.0
                ol['tp_btc'] = 0.0
        
        asset_config['sl_activo_usd'] = total_sl_activo_usd
        asset_config['tp_activo_usd'] = total_tp_activo_usd

        # Calcular porcentajes de SL/TP Activo en relación al CAPITAL TOTAL
        if total_capital is not None and total_capital > 0:
            asset_config['percent_sl_activo'] = (abs(total_sl_activo_usd) / total_capital) * 100 if total_sl_activo_usd != 0 else 0.0
            asset_config['percent_tp_activo'] = (total_tp_activo_usd / total_capital) * 100 if total_tp_activo_usd > 0 else 0.0
        else:
            asset_config['percent_sl_activo'] = 0.0
            asset_config['percent_tp_activo'] = 0.0
            logging.warning(f"Capital total no válido ({total_capital}) para {symbol}. Los porcentajes de SL/TP no pueden ser calculados.")

        # --- LÓGICA CORREGIDA PARA CALCULAR R/R CON ABSOLUTO ---
        if total_sl_activo_usd != 0.0:
            asset_config['relacion_activo'] = abs(total_tp_activo_usd) / abs(total_sl_activo_usd)
        else:
            asset_config['relacion_activo'] = 0.0

        return total_sl_activo_usd, total_tp_activo_usd
    
    def _check_manual_alerts(self, asset_config, current_price):
        """
        Verifica si el precio actual ha cruzado algún soporte o resistencia manual
        y dispara una alerta.
        """
        symbol = asset_config.get('symbol', 'N/A')
        previous_price = asset_config.get('previous_price', 0.0)

        # Añadido: Salir de la función si no hay un precio anterior válido.
        # previous_price ya es 0.0 o un número en la primera iteración,
        # pero el error ocurre con el precio actual.
        if current_price is None or previous_price is None or current_price <= 0 or previous_price <= 0:
            logging.warning(f"No se pudo verificar las alertas para {symbol}: El precio actual ({current_price}) o anterior ({previous_price}) no es válido.")
            return

        # Chequeo de soportes
        for support in asset_config.get('manual_supports', []):
            # Lógica corregida para cruce a la baja (soporte roto)
            if previous_price > support >= current_price:
                message = f"🔔 ¡ALERTA DE SOPORTE! El precio de {symbol} ha tocado o roto el soporte en ${support:,.4f}. Precio actual: ${current_price:,.4f}"
                logging.info(message)
                self.alert_manager.check_and_send_alert(message, "SOPORTE ROTO")
            # Lógica corregida para rebote en el soporte
            elif previous_price < support and current_price >= support:
                message = f"🟢 ¡ALERTA DE REBOTE EN SOPORTE! El precio de {symbol} ha rebotado en el soporte de ${support:,.4f}. Precio actual: ${current_price:,.4f}"
                logging.info(message)
                self.alert_manager.check_and_send_alert(message, "REBOTE EN SOPORTE")
    
        # Chequeo de resistencias
        for resistance in asset_config.get('manual_resistances', []):
            # Lógica corregida para cruce al alza (resistencia rota)
            if previous_price < resistance <= current_price:
                message = f"🔔 ¡ALERTA DE RESISTENCIA! El precio de {symbol} ha tocado o roto la resistencia en ${resistance:,.4f}. Precio actual: ${current_price:,.4f}"
                logging.info(message)
                self.alert_manager.check_and_send_alert(message, "RESISTENCIA ROTA")
            # Lógica corregida para rebote en la resistencia
            elif previous_price > resistance and current_price <= resistance:
                message = f"🔴 ¡ALERTA DE REBOTE EN RESISTENCIA! El precio de {symbol} ha rebotado en la resistencia de ${resistance:,.4f}. Precio actual: ${current_price:,.4f}"
                logging.info(message)
                self.alert_manager.check_and_send_alert(message, "REBOTE EN RESISTENCIA")
    
    def update_all_asset_data(self):
        """
        Actualiza los precios de todos los activos, calcula métricas, indicadores
        y luego los totales globales.
        """
        assets = self.config_manager.get_assets_to_monitor()
        general_settings = self.config_manager.get_general_settings()
        current_capital = general_settings.get('capital_usd', 0.0)

        btc_price_usd = self.api_manager.get_crypto_price('BTCUSDT')
        if btc_price_usd is None or btc_price_usd <= 0:
            logging.error(f"APIManager: Falló al obtener precio de BTCUSDT. Valor devuelto: {btc_price_usd}. Las conversiones a BTC no serán precisas y se usará 1.0 como fallback.")
            btc_price_usd = 1.0

        self.config_manager.get_general_settings()['current_btc_price_usd'] = btc_price_usd

        capital_btc_equivalent = current_capital / btc_price_usd if btc_price_usd > 0 else 0.0

        total_sl_all_assets_usd = 0.0
        total_tp_all_assets_usd = 0.0

        for asset_config in assets:
            symbol = asset_config.get('symbol', '')
            if not symbol:
                logging.warning("Activo sin 'symbol' definido en la configuración. Saltando.")
                continue

            logging.info(f"Actualizando datos para {symbol}")

            # Conservar el precio anterior para la lógica de cruce de alertas
            asset_config['previous_price'] = asset_config.get('last_known_price', 0.0)
            
            # Obtener el precio actual usando la lógica de respaldo (cripto o stock)
            current_price = self.api_manager.get_last_price(symbol)
            
            # Corregido: Solo actualizar el precio si es válido.
            if current_price is not None and current_price > 0:
                asset_config['last_known_price'] = current_price
            else:
                logging.error(f"No hay precio actual ni último precio conocido válido para {symbol}. Saltando cálculos detallados para este activo.")
                self.config_manager.update_asset(symbol, asset_config)
                continue
            
            # Lógica para indicadores y alertas
            # Obtener el tipo de activo de forma dinámica para asegurar la fuente correcta
            asset_type = self.api_manager.get_asset_type(symbol)
            intervals_to_calculate = ['1w', '1M']
            
            indicators_data = self.indicator_calculator.calculate_indicators_for_asset(
                symbol, 
                asset_type,
                intervals_to_calculate,
                60
            )
            
            if '1M' in indicators_data and indicators_data['1M'].get('rsi') is not None:
                asset_config['rsi_monthly_calculated'] = indicators_data['1M']['rsi']
                asset_config['macd_monthly_line'] = indicators_data['1M'].get('macd')
                asset_config['macd_monthly_signal'] = indicators_data['1M'].get('macdsignal')
                asset_config['macd_monthly_hist'] = indicators_data['1M'].get('macdhist')
                if symbol == 'BTCUSDT':
                    logging.debug("Valores de MACD mensual de BTCUSDT guardados.")
            else:
                asset_config['rsi_monthly_calculated'] = None
                asset_config['macd_monthly_line'] = None
                asset_config['macd_monthly_signal'] = None
                asset_config['macd_monthly_hist'] = None

            if '1w' in indicators_data and indicators_data['1w'].get('rsi') is not None:
                asset_config['rsi_weekly_calculated'] = indicators_data['1w']['rsi']
            else:
                asset_config['rsi_weekly_calculated'] = None
                
            # Calcular métricas y actualizar totales globales
            sl_asset_usd, tp_asset_usd = self._calculate_asset_metrics(asset_config, current_price, btc_price_usd, current_capital)
            
            total_sl_all_assets_usd += sl_asset_usd
            total_tp_all_assets_usd += tp_asset_usd
            
            # Llamar a la función de alertas unificada con la configuración completa del activo
            self.alert_manager.check_alerts(asset_config)
            
            # NUEVA LÓGICA: Llamar a la función para chequear alertas manuales
            self._check_manual_alerts(asset_config, current_price)

            self.config_manager.update_asset(symbol, asset_config)

        self.config_manager.update_global_totals(
            total_sl_all_assets_usd,
            total_tp_all_assets_usd,
            capital_btc_equivalent
        )
        self.config_manager.save_config()

        logging.info(f"Todos los datos de activos y totales globales actualizados. SL Total: {total_sl_all_assets_usd:.2f} USD, TP Total: {total_tp_all_assets_usd:.2f} USD, Capital BTC Eq: {capital_btc_equivalent:.8f} BTC")

    def run(self):
        """Bucle principal de ejecución del SATT."""
        while True:
            try:
                current_time = time.time()
                if current_time - self.last_update_time >= self.update_interval:
                    logging.info("Realizando actualización de datos periódica...")
                    self.update_all_asset_data()
                    self.last_update_time = current_time
                
                self.config_manager.reload_config()
                self.ui_manager.display_main_menu()
                choice = self.ui_manager.get_user_choice()

                if choice == 'a':
                    self.ui_manager.add_edit_asset_menu()
                    self.update_all_asset_data()
                elif choice == 'b':
                    self.ui_manager.remove_asset_menu()
                    self.update_all_asset_data()
                elif choice == 'c':
                    old_update_interval = self.update_interval
                    self.ui_manager.adjust_general_config_menu()
                    general_settings = self.config_manager.get_general_settings()
                    self.update_interval = general_settings.get('update_interval_seconds', 300)
                    if old_update_interval != self.update_interval:
                        logging.info(f"Intervalo de actualización cambiado de {old_update_interval}s a {self.update_interval}s.")
                    self.update_all_asset_data()
                elif choice == 'd':
                    self.ui_manager.test_telegram_alert_menu()
                elif choice == 'e':
                    self.ui_manager.display_capital_graph()
                elif choice == 'f': 
                    self.ui_manager.display_alert_history_menu()
                elif choice == 'q':
                    logging.info("Saliendo del SATT. ¡Hasta luego!")
                    self.config_manager.save_config()
                    sys.exit()
                else:
                    print("Opción no válida. Por favor, intenta de nuevo.")
                
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                logging.info("SATT detenido por el usuario. Guardando configuración final.")
                self.config_manager.save_config()
                sys.exit(0)
            except Exception as e:
                logging.error(f"Error inesperado en el ciclo principal: {e}", exc_info=True)
                self.alert_manager.check_and_send_alert(
                    f"🚨 Error crítico en SATT: {e}. Revisa los logs.",
                    "ERROR CRITICO"
                )
                time.sleep(self.update_interval)

if __name__ == "__main__":
    satt = SATT()
    satt.run()
