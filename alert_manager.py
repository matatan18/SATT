import json
import os
import time
import requests
import threading
import logging
from datetime import datetime
from typing import Union
import pandas as pd

class AlertManager:
    ALERT_HISTORY_FILE = 'alert_history.json'
    RSI_OVERBOUGHT = 70.0
    RSI_OVERSOLD = 30.0
    # Lista de niveles de Fibonacci para la lógica del CHOCH
    FIBO_CHOCH_LEVELS = [0.382, 0.5, 0.618]
    
    # Códigos de color ANSI para la terminal
    ROJO = '\033[91m'
    RESET = '\033[0m'

    def __init__(self, config_manager, api_manager=None, ui_manager=None):
        self.config_manager = config_manager
        self.api_manager = api_manager
        self.ui_manager = ui_manager
        self.alert_history = self._load_alert_history()
        self.telegram_send_lock = threading.Lock()
        
        # Diccionarios para evitar alertas duplicadas
        self.last_rsi_status = {}
        self.last_fibo_alert_status = {}
        self.last_manual_fibo_alert_status = {}
        self.last_support_alert = {}
        self.last_resistance_alert = {}
        self.last_bos_choch_alert = {}
        self.last_macd_alert_status = {}

        logging.info("AlertManager inicializado.")

    def _load_alert_history(self) -> list:
        if os.path.exists(self.ALERT_HISTORY_FILE):
            try:
                with open(self.ALERT_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logging.warning(f"Advertencia: Archivo de historial de alertas '{self.ALERT_HISTORY_FILE}' corrupto o no encontrado. Se creará uno nuevo. Error: {e}")
                return []
            except Exception as e:
                logging.error(f"Error inesperado al cargar el historial de alertas: {e}. Se creará uno nuevo.")
                return []
        return []

    def _save_alert_history(self):
        self.alert_history = self.alert_history[-1000:]
        try:
            with open(self.ALERT_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.alert_history, f, indent=4)
        except IOError as e:
            logging.error(f"Error al guardar el historial de alertas en '{self.ALERT_HISTORY_FILE}': {e}")
    
    def _get_rsi_state(self, rsi_value: float) -> str:
        if rsi_value >= self.RSI_OVERBOUGHT:
            return "Sobrecompra"
        elif rsi_value <= self.RSI_OVERSOLD:
            return "Sobreventa"
        else:
            return "Neutral"

    def _evaluate_rsi_trend(self, symbol: str, rsi_current: float, rsi_manuals: list, interval: str) -> Union[tuple, None]:
        if rsi_current is None or not rsi_manuals:
            return None
        
        positive_diffs = 0
        negative_diffs = 0
        
        for rsi_manual in rsi_manuals:
            if rsi_manual - rsi_current > 0:
                positive_diffs += 1
            elif rsi_manual - rsi_current < 0:
                negative_diffs += 1
        
        total_manuals = len(rsi_manuals)
        current_status = ""
        message = ""
        
        if positive_diffs == total_manuals:
            current_status = f"Sobreventa Fuerte ({interval})"
            message = f"🚨 Alerta RSI {interval} para {symbol}: Tendencia a sobreventa fuerte. El RSI ({rsi_current:.2f}) está por debajo de todos los niveles manuales."
        elif negative_diffs == total_manuals:
            current_status = f"Sobrecompra Fuerte ({interval})"
            message = f"⚠️ Alerta RSI {interval} para {symbol}: Tendencia a sobrecompra fuerte. El RSI ({rsi_current:.2f}) está por encima de todos los niveles manuales."
        elif positive_diffs > negative_diffs:
            current_status = f"Sobreventa Normal ({interval})"
            message = f"📉 Alerta RSI {interval} para {symbol}: Tendencia a sobreventa. El RSI ({rsi_current:.2f}) está por debajo de la mayoría de los niveles manuales."
        elif negative_diffs > positive_diffs:
            current_status = f"Sobrecompra Normal ({interval})"
            message = f"📈 Alerta RSI {interval} para {symbol}: Tendencia a sobrecompra. El RSI ({rsi_current:.2f}) está por encima de la mayoría de los niveles manuales."
        else:
            current_status = f"Mercado Normal ({interval})"
            message = f"⚖️ Alerta RSI {interval} para {symbol}: Tendencia de mercado normal. El RSI ({rsi_current:.2f}) está balanceado entre los niveles manuales."

        last_status_key = f"{symbol}_{interval}_rsi_status"
        if self.last_rsi_status.get(last_status_key) != current_status:
            self.last_rsi_status[last_status_key] = current_status
            return (message, "RSI CRITICO")
        
        return None

    def check_macd_alert(self, asset_config: dict):
        symbol = asset_config.get('symbol')
        if symbol != 'BTCUSDT': return
        
        current_price = asset_config.get('last_known_price')
        macd_line_series = asset_config.get('macd_monthly_line')
        macd_signal_series = asset_config.get('macd_monthly_signal')
        
        if macd_line_series is None or macd_signal_series is None or len(macd_line_series) < 2 or len(macd_signal_series) < 2:
            return

        last_macd = macd_line_series.iloc[-1]
        last_signal = macd_signal_series.iloc[-1]
        prev_macd = macd_line_series.iloc[-2]
        prev_signal = macd_signal_series.iloc[-2]

        alert_key = f"{symbol}_macd_monthly"
        current_state = "neutral"

        if prev_macd > prev_signal and last_macd < last_signal:
            current_state = "bajista"
            if self.last_macd_alert_status.get(alert_key) != current_state:
                message = f"🚨 **ALERTA BTCUSDT - MACD MENSUAL**\n\n" \
                          f"La línea MACD ha cruzado por debajo de la línea de señal.\n" \
                          f"Posible mercado bajista a largo plazo.\n" \
                          f"Precio actual: ${current_price:,.2f} USD"
                self.check_and_send_alert(message, "MACD Mensual BITCOIN")
                self.last_macd_alert_status[alert_key] = current_state

        elif prev_macd < prev_signal and last_macd > last_signal:
            current_state = "alcista"
            if self.last_macd_alert_status.get(alert_key) != current_state:
                message = f"🟢 **ALERTA BTCUSDT - MACD MENSUAL**\n\n" \
                          f"La línea MACD ha cruzado por encima de la línea de señal.\n" \
                          f"Posible mercado alcista a largo plazo.\n" \
                          f"Precio actual: ${current_price:,.2f} USD"
                self.check_and_send_alert(message, "MACD Mensual BITCOIN")
                self.last_macd_alert_status[alert_key] = current_state
        
        if self.last_macd_alert_status.get(alert_key) == current_state:
            # Resetea el estado si el cruce ya no se mantiene
            if (current_state == "bajista" and last_macd > last_signal) or \
               (current_state == "alcista" and last_macd < last_signal):
                del self.last_macd_alert_status[alert_key]


    def check_and_send_fibo_alert(self, symbol: str, temporalidad: str, precio_anterior: float, precio_actual: float, fibonacci_levels: dict, max_local: float, min_local: float):
        if precio_anterior is None: return

        # 1. Verificar si el precio ha roto el Máximo o Mínimo Local
        alert_max_key = f"{symbol}_manual_max_{max_local}"
        alert_min_key = f"{symbol}_manual_min_{min_local}"

        if max_local is not None and precio_actual > max_local and precio_anterior <= max_local:
            if self.last_manual_fibo_alert_status.get(alert_max_key) is None:
                message = f"🚀 **¡ALERTA MÁXIMO LOCAL ROTO!** ({temporalidad})\n\n" \
                          f"El precio de {symbol} (${precio_actual:.4f}) ha superado tu máximo local anterior de ${max_local:.4f}.\n" \
                          f"⚠️ **Acción requerida:** Por favor, actualiza el valor del Máximo Local en la configuración para recalcular los niveles de Fibonacci."
                self.check_and_send_alert(message, "FIBO_MANUAL: Maximo Roto")
                self.last_manual_fibo_alert_status[alert_max_key] = True
        elif max_local is not None and precio_actual < max_local and alert_max_key in self.last_manual_fibo_alert_status:
            del self.last_manual_fibo_alert_status[alert_max_key]
        
        if min_local is not None and precio_actual < min_local and precio_anterior >= min_local:
            if self.last_manual_fibo_alert_status.get(alert_min_key) is None:
                message = f"🚨 **¡ALERTA MÍNIMO LOCAL ROTO!** ({temporalidad})\n\n" \
                          f"El precio de {symbol} (${precio_actual:.4f}) ha caído por debajo de tu mínimo local anterior de ${min_local:.4f}.\n" \
                          f"⚠️ **Acción requerida:** Por favor, actualiza el valor del Mínimo Local en la configuración para recalcular los niveles de Fibonacci."
                self.check_and_send_alert(message, "FIBO_MANUAL: Minimo Roto")
                self.last_manual_fibo_alert_status[alert_min_key] = True
        elif min_local is not None and precio_actual > min_local and alert_min_key in self.last_manual_fibo_alert_status:
            del self.last_manual_fibo_alert_status[alert_min_key]

        # 2. Verificar los cruces de niveles intermedios de Fibonacci
        if not fibonacci_levels: return

        for level_name, price_value in fibonacci_levels.items():
            try:
                if price_value is None: continue
                price_value = float(price_value)
                alert_key = f"{symbol}_{temporalidad}_{level_name}"

                if (precio_anterior < price_value and precio_actual >= price_value) or \
                   (precio_anterior > price_value and precio_actual <= price_value):
                    
                    direction = "al alza" if precio_actual > precio_anterior else "a la baja"
                    emoji = "🟢" if precio_actual > precio_anterior else "🔴"
                    
                    if self.last_manual_fibo_alert_status.get(alert_key) != direction:
                        message = f"{emoji} **ALERTA FIBO MANUAL** ({temporalidad})\n\n" \
                                  f"El precio de {symbol} ha cruzado {direction} el nivel de Fibonacci **{level_name}** del rango de Máximo/Mínimo Local (${price_value:.4f}).\n" \
                                  f"Precio actual: ${precio_actual:.4f}"
                        self.check_and_send_alert(message, "FIBO_MANUAL: Nivel Alcanzado")
                        self.last_manual_fibo_alert_status[alert_key] = direction
                
                # Resetear el estado si el precio se aleja del nivel
                elif abs(precio_actual - price_value) / price_value > 0.005:
                    if alert_key in self.last_manual_fibo_alert_status:
                        del self.last_manual_fibo_alert_status[alert_key]
            
            except (ValueError, TypeError):
                logging.warning(f"Advertencia: El nivel de Fibonacci '{level_name}' con valor '{price_value}' para {symbol} no es válido.")

    def check_and_send_sr_alert(self, symbol: str, current_price: float, supports: list, resistances: list):
        # Chequear soportes
        for support_price in supports:
            try:
                support_price_float = float(support_price)
                alert_key = f"{symbol}_support_{support_price_float}"
                
                if current_price <= support_price_float:
                    if self.last_support_alert.get(alert_key) is None:
                        message = f"🟢 **ALERTA SOPORTE**\n\n" \
                                  f"El precio de **{symbol}** ha tocado el nivel de soporte en **${support_price_float:.4f}**.\n\n" \
                                  f"Precio actual: ${current_price:.4f}"
                        self.check_and_send_alert(message, "SOPORTE ALCANZADO")
                        self.last_support_alert[alert_key] = True
                else:
                    if self.last_support_alert.get(alert_key) is not None and current_price > support_price_float * 1.005:
                        del self.last_support_alert[alert_key]
            except (ValueError, TypeError):
                logging.warning(f"Advertencia: El valor de soporte '{support_price}' para {symbol} no es un número válido.")

        # Chequear resistencias
        for resistance_price in resistances:
            try:
                resistance_price_float = float(resistance_price)
                alert_key = f"{symbol}_resistance_{resistance_price_float}"

                if current_price >= resistance_price_float:
                    if self.last_resistance_alert.get(alert_key) is None:
                        message = f"🔴 **ALERTA RESISTENCIA**\n\n" \
                                  f"El precio de **{symbol}** ha tocado el nivel de resistencia en **${resistance_price_float:.4f}**.\n\n" \
                                  f"Precio actual: ${current_price:.4f}"
                        self.check_and_send_alert(message, "RESISTENCIA ALCANZADA")
                        self.last_resistance_alert[alert_key] = True
                else:
                    if self.last_resistance_alert.get(alert_key) is not None and current_price < resistance_price_float * 0.995:
                        del self.last_resistance_alert[alert_key]
            except (ValueError, TypeError):
                logging.warning(f"Advertencia: El valor de resistencia '{resistance_price}' para {symbol} no es un número válido.")

    def check_and_send_bos_choch_alert(self, symbol: str, temporalidad: str, precio_actual: float, precio_anterior: float, posible_boss: float, posible_choch: float, asset_config: dict):
        if precio_anterior is None or (posible_boss is None and posible_choch is None): return

        # Chequear posible BOS (sin mencionar Fibonacci)
        if posible_boss is not None:
            alert_key_boss = f"{symbol}_{temporalidad}_boss_{posible_boss}"
            if precio_actual >= posible_boss and precio_anterior < posible_boss and self.last_bos_choch_alert.get(alert_key_boss) is None:
                message = f"🟢 **ALERTA BOS** ({temporalidad})\n\n" \
                          f"El precio de {symbol} ha cruzado el posible BOS en ${posible_boss:.4f}, indicando la continuación de la tendencia alcista.\n" \
                          f"Precio actual: ${precio_actual:.4f}"
                self.check_and_send_alert(message, "BOS/CHOCH: Ruptura")
                self.last_bos_choch_alert[alert_key_boss] = True
            elif precio_actual < posible_boss and self.last_bos_choch_alert.get(alert_key_boss) is not None:
                del self.last_bos_choch_alert[alert_key_boss]

        # Chequear posible CHOCH (sin mencionar Fibonacci)
        if posible_choch is not None:
            alert_key_choch = f"{symbol}_{temporalidad}_choch_{posible_choch}"
            if precio_actual <= posible_choch and precio_anterior > posible_choch and self.last_bos_choch_alert.get(alert_key_choch) is None:
                message = f"🔴 **ALERTA CHOCH** ({temporalidad})\n\n" \
                          f"El precio de {symbol} ha cruzado el posible CHOCH en ${posible_choch:.4f}, indicando un posible cambio de tendencia a bajista.\n" \
                          f"Precio actual: ${precio_actual:.4f}"
                self.check_and_send_alert(message, "BOS/CHOCH: Ruptura")
                self.last_bos_choch_alert[alert_key_choch] = True
            elif precio_actual > posible_choch and self.last_bos_choch_alert.get(alert_key_choch) is not None:
                del self.last_bos_choch_alert[alert_key_choch]
            
            # Alertas para los niveles de Fibonacci DENTRO de la estructura BOS/CHOCH
            fibo_high_price = asset_config.get(f'posible_boss_{temporalidad.lower()}')
            fibo_low_price = asset_config.get(f'posible_choch_{temporalidad.lower()}')
            
            if fibo_high_price is not None and fibo_low_price is not None:
                for level in self.FIBO_CHOCH_LEVELS:
                    fibo_price = fibo_low_price + (fibo_high_price - fibo_low_price) * (1 - level)
                    alert_key_fibo_choch = f"{symbol}_{temporalidad}_fibo{level}_choch"

                    if (precio_actual <= fibo_price and precio_anterior > fibo_price) or (precio_actual >= fibo_price and precio_anterior < fibo_price):
                        if self.last_bos_choch_alert.get(alert_key_fibo_choch) is None:
                            message = f"🟡 **ALERTA FIBO ESTRUCTURA** ({temporalidad})\n\n" \
                                      f"El precio de {symbol} ha cruzado el nivel **{level}** del rango de BOS/CHOCH.\n" \
                                      f"Nivel Fibo: ${fibo_price:.4f}\n" \
                                      f"Precio actual: ${precio_actual:.4f}"
                            self.check_and_send_alert(message, "FIBO_CHOCH: Nivel Alcanzado")
                            self.last_bos_choch_alert[alert_key_fibo_choch] = True
                    elif abs(precio_actual - fibo_price) / fibo_price > 0.005:
                        if alert_key_fibo_choch in self.last_bos_choch_alert:
                            del self.last_bos_choch_alert[alert_key_fibo_choch]


    def check_alerts(self, asset_config: dict) -> None:
        symbol = asset_config.get('symbol', 'N/A')
        current_price = asset_config.get('last_known_price')
        previous_price = asset_config.get('previous_price')

        if current_price is None or previous_price is None:
            logging.warning(f"No se pudo verificar las alertas para {symbol}: No hay precio actual o anterior.")
            return

        # 1. Alertas de RSI
        rsi_monthly_calculated = asset_config.get('rsi_monthly_calculated')
        rsi_monthly_manuals = sorted(asset_config.get('rsi_monthly_manual_values', []))
        monthly_alert = self._evaluate_rsi_trend(symbol, rsi_monthly_calculated, rsi_monthly_manuals, "Mensual")
        if monthly_alert: self.check_and_send_alert(monthly_alert[0], monthly_alert[1])

        rsi_weekly_calculated = asset_config.get('rsi_weekly_calculated')
        rsi_weekly_manuals = sorted(asset_config.get('rsi_weekly_manual_values', []))
        weekly_alert = self._evaluate_rsi_trend(symbol, rsi_weekly_calculated, rsi_weekly_manuals, "Semanal")
        if weekly_alert: self.check_and_send_alert(weekly_alert[0], weekly_alert[1])

        # 2. Alertas de Soportes y Resistencias
        supports = asset_config.get('manual_supports', [])
        resistances = asset_config.get('manual_resistances', [])
        self.check_and_send_sr_alert(symbol, current_price, supports, resistances)

        # 3. Alertas de Fibonacci Manual (Máximo/Mínimo)
        fibo_levels = asset_config.get('manual_fibo_levels', {})
        max_local = asset_config.get('max_local')
        min_local = asset_config.get('min_local')
        self.check_and_send_fibo_alert(symbol, "Manual", previous_price, current_price, fibo_levels, max_local, min_local)

        # 4. Alertas de MACD (solo para BTC)
        if symbol == 'BTCUSDT':
            self.check_macd_alert(asset_config)

        # 5. Alertas de BOS/CHOCH (se asume que los datos están bajo las claves 'posible_boss_1d', etc.)
        self.check_and_send_bos_choch_alert(symbol, '1D', current_price, previous_price, asset_config.get('posible_boss_1d'), asset_config.get('posible_choch_1d'), asset_config)
        self.check_and_send_bos_choch_alert(symbol, '4H', current_price, previous_price, asset_config.get('posible_boss_4h'), asset_config.get('posible_choch_4h'), asset_config)
        self.check_and_send_bos_choch_alert(symbol, '1H', current_price, previous_price, asset_config.get('posible_boss_1h'), asset_config.get('posible_choch_1h'), asset_config)

    def check_and_send_alert(self, message: str, alert_type: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_entry = {
            "timestamp": timestamp,
            "type": alert_type,
            "message": message
        }
        self.alert_history.append(alert_entry)
        self._save_alert_history()
        
        alert_config = self.config_manager.get_alert_settings()
        telegram_enabled = alert_config.get('telegram_alerts_enabled', False)
        chat_id = alert_config.get('telegram_chat_id', '')
        bot_token = alert_config.get('telegram_bot_token', '')
        enabled_alert_types = alert_config.get('enabled_alert_types', [])
        
        # Muestra la alerta en el terminal con color rojo
        colored_message = f"{self.ROJO}[{timestamp}] ALERTA ({alert_type}): {message}{self.RESET}"
        print(colored_message)

        if alert_type not in enabled_alert_types:
            logging.info(f"[{timestamp}] ALERTA '{alert_type}' no enviada a Telegram (tipo deshabilitado).")
            return

        if telegram_enabled and chat_id and bot_token:
            telegram_thread = threading.Thread(
                target=self._send_telegram_message_threaded,
                args=(bot_token, chat_id, f"🚨 SATT ALERTA: {alert_type}\n\n{message}")
            )
            telegram_thread.start()
        else:
            if telegram_enabled:
                logging.error(f"[{timestamp}] Advertencia: Configuración de Telegram (chat_id o bot_token) incompleta.")
            else:
                logging.info(f"[{timestamp}] ALERTA '{alert_type}' procesada (Telegram deshabilitado).")

    def _send_telegram_message_threaded(self, bot_token: str, chat_id: str, text: str):
        with self.telegram_send_lock:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            try:
                response = requests.post(url, data=payload, timeout=10)
                response.raise_for_status()
                logging.info(f"Mensaje de Telegram enviado con éxito a chat ID {chat_id}.")
            except requests.exceptions.Timeout:
                logging.error(f"Error: Tiempo de espera agotado al enviar mensaje a Telegram (chat ID: {chat_id}).")
            except requests.exceptions.RequestException as e:
                error_detail = ""
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_json = e.response.json()
                        error_detail = f" Respuesta de Telegram: {error_json.get('description', e.response.text)}"
                    except json.JSONDecodeError:
                        error_detail = f" Respuesta de Telegram (texto): {e.response.text}"
                    finally:
                        logging.error(f"Error al enviar mensaje a Telegram (chat ID: {chat_id}): {error_detail}")
                else:
                    error_detail = str(e)
                logging.error(f"Error al enviar mensaje a Telegram (chat ID: {chat_id}): {error_detail}")
            except Exception as e:
                logging.error(f"Ocurrió un error inesperado al enviar la alerta a Telegram: {e}")
            finally:
                time.sleep(0.5)

    def display_alert_history(self):
        if self.ui_manager:
            self.ui_manager.clear_screen()
            self.ui_manager.display_header("<<< SATT - HISTORIAL DE ALERTAS >>>")
        else:
            print("\n" + "=" * 70)
            print("     <<< SATT - HISTORIAL DE ALERTAS >>>")
            print("=" * 70)

        if not self.alert_history:
            if self.ui_manager:
                self.ui_manager.display_message("\n      (No hay alertas registradas aún.)")
            else:
                print("\n      (No hay alertas registradas aún.)")
        else:
            for alert in reversed(self.alert_history):
                alert_text = f"[{alert['timestamp']}] [{alert['type']}] {alert['message']}"
                if self.ui_manager:
                    self.ui_manager.display_message(alert_text)
                    self.ui_manager.display_separator()
                else:
                    print(alert_text)
                    print("-" * 70)
            
        if self.ui_manager:
            self.ui_manager.wait_for_user_input("\nPresiona Enter para volver al menú principal...")
        else:
            input("\nPresiona Enter para volver al menú principal...")
