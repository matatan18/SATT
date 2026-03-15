import os
import time
import logging
import sys
import requests
import json
from datetime import datetime

# Ancho del terminal para el formato de la línea
TERMINAL_WIDTH = 87

def format_line(text, width=TERMINAL_WIDTH):
    return f"║ {text.ljust(width)} ║"
class UserInterface:
    RSI_OVERBOUGHT = 70.0
    RSI_OVERSOLD = 30.0
    HISTORY_FILE = 'capital_history.json'

    def __init__(self, config_manager, api_manager):
        self.config_manager = config_manager
        self.api_manager = api_manager
        self.expanded_assets = []  # Lista para los activos desplegados
        self.persistent_alerts = [] # Nueva lista para alertas persistentes
        logging.info("UIManager inicializado.")

    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def _get_float_input_with_validation(self, prompt, current_value):
        while True:
            input_str = input(f"{prompt} ({current_value if current_value is not None else 'N/A'}): ").strip()
            if not input_str:
                return current_value
            try:
                value = float(input_str)
                return value
            except ValueError:
                print("Valor inválido. Por favor, ingrese un número o deje vacío para mantener el valor actual.")

    def _get_fib_range_input_with_validation(self, prompt_high, current_high, prompt_low, current_low):
        while True:
            print("\n--- Ingrese Rango para Fibonacci Manual (Máximo y Mínimo Local) ---")
            print("Nota: Ingrese ambos valores, o deje AMBOS vacíos para mantenerlos.")

            new_high_str = input(f"{prompt_high} ({current_high if current_high is not None else 'N/A'}): ").strip()
            new_low_str = input(f"{prompt_low} ({current_low if current_low is not None else 'N/A'}): ").strip()

            new_high = current_high
            new_low = current_low

            if new_high_str:
                try:
                    new_high = float(new_high_str)
                except ValueError:
                    print("Valor de Máximo Local inválido. Debe ser un número.")
                    continue

            if new_low_str:
                try:
                    new_low = float(new_low_str)
                except ValueError:
                    print("Valor de Mínimo Local inválido. Debe ser un número.")
                    continue

            if (new_high is None or new_low is None) and (new_high_str or new_low_str):
                print("ADVERTENCIA: Debe ingresar AMBOS valores para Máximo y Mínimo Local si no existen, o dejar AMBOS vacíos para no configurarlos.")
                continue

            if new_high is not None and new_low is not None and new_low >= new_high:
                print("ADVERTENCIA: El Mínimo Local debe ser MENOR que el Máximo Local. Por favor, reingrese.")
                continue

            if new_high is None and new_low is None:
                print("Configuración de Fibonacci Manual mantenida sin cambios.")
                return current_high, current_low

            print("Máximo y Mínimo Local configurados exitosamente.")
            return new_high, new_low

    def _calculate_fibonacci_levels(self, choch_price, boss_price):
        """
        Calcula los precios para los niveles de Fibonacci.
        El cálculo siempre se hace desde CHOCH (100%) hasta BOS (0%).
        """
        levels = [0, 0.382, 0.5, 0.618, 0.786, 1]
        fib_levels = {}

        # El rango se calcula como la diferencia entre CHOCH y BOS.
        # Esto asegura que el 100% siempre sea el CHOCH y el 0% el BOS.
        price_range = boss_price - choch_price

        for level in levels:
            price = choch_price + (price_range * (1 - level))
            fib_levels[level] = price

        return fib_levels

    def _calculate_manual_fibonacci_levels(self, high_price, low_price):
        """
        Calcula los precios para los niveles de Fibonacci manuales.
        El cálculo siempre se hace desde el Mínimo Local (100%) hasta el Máximo Local (0%).
        """
        levels = [0, 0.382, 0.5, 0.618, 0.786, 1]
        fib_levels = {}

        price_range = high_price - low_price

        for level in levels:
            price = low_price + (price_range * (1 - level))
            fib_levels[level] = price

        return fib_levels

    def _check_and_send_fibonacci_alert(self, symbol, current_price, fib_levels, timeframe):
        """Revisa si el precio actual ha tocado un nivel de Fibonacci y envía una alerta."""
        for level, price in fib_levels.items():
            # Considerar un pequeño rango para la alerta
            if abs(current_price - price) < 0.01: # Ajusta el umbral según la precisión deseada
                message = f"🔔 ALERTA de Fibonacci para {symbol} en temporalidad {timeframe.upper()}:\n" \
                          f"El precio actual ${current_price:,.4f} ha tocado el nivel {level:.3f} (${price:,.4f})."
                logging.info(message)
                self.persistent_alerts.append(message) # Almacena la alerta para mostrarla

    def _get_rsi_state(self, rsi_value: float) -> str:
        if rsi_value is None:
            return "N/A"
        elif rsi_value >= self.RSI_OVERBOUGHT:
            return "Sobrecompra"
        elif rsi_value <= self.RSI_OVERSOLD:
            return "Sobreventa"
        else:
            return "Neutral"

    # --- Nuevo método para mostrar las alertas persistentes ---
    def _display_persistent_alerts(self):
        if self.persistent_alerts:
            print("╠═════════════════════════════════════════════════════════════════════════════════════════╣")
            print("║     🚨 Alertas Activas 🚨                                                            ║")
            for alert in self.persistent_alerts:
                for line in alert.split('\n'):
                    print(format_line(line.strip()))
            print("╠═════════════════════════════════════════════════════════════════════════════════════════╣")

    # --- Nuevo método para mostrar un resumen o los detalles completos del activo ---
    def _display_asset_info(self, index, asset, btc_price_usd_for_header, capital_usd):
        symbol = asset.get('symbol', 'N/A')
        last_known_price = asset.get('last_known_price')

        is_expanded = symbol in self.expanded_assets

        # Siempre mostrar el encabezado del activo con su número
        price_display = f"${last_known_price:,.4f} USD" if last_known_price is not None else "N/A"
        print(format_line(f"{index}. {symbol} | Precio: {price_display}"))

        if is_expanded:
            entry_price = asset.get('entry_price')
            sl_usd_entry = asset.get('sl_usd_entry')
            tp_usd_entry = asset.get('tp_usd_entry')

            sl_activo_total = asset.get('sl_activo_usd', 0)
            tp_activo_total = asset.get('tp_activo_usd', 0)

            percent_sl_activo = asset.get('percent_sl_activo')
            percent_tp_activo = asset.get('percent_tp_activo')
            relacion_activo = asset.get('relacion_activo')

            rsi_monthly_value = asset.get('rsi_monthly_calculated')
            rsi_monthly_state = self._get_rsi_state(rsi_monthly_value)
            rsi_weekly_value = asset.get('rsi_weekly_calculated')
            rsi_weekly_state = self._get_rsi_state(rsi_weekly_value)

            manual_fib_high = asset.get('manual_fib_high')
            manual_fib_low = asset.get('manual_fib_low')

            if entry_price is not None:
                entry_btc = entry_price / btc_price_usd_for_header if btc_price_usd_for_header and btc_price_usd_for_header > 0 else 0.0
                print(format_line(f"  Precio de Entrada: ${entry_price:,.4f} USD (~{entry_btc:,.8f} BTC)"))
            else:
                print(format_line("  Precio de Entrada: N/A"))

            sl_entry_display = "N/A"
            if sl_usd_entry is not None and capital_usd > 0:
                sl_btc_entry = sl_usd_entry / btc_price_usd_for_header if btc_price_usd_for_header and btc_price_usd_for_header > 0 else None
                percent_sl_entry = (abs(sl_usd_entry) / capital_usd) * 100
                sl_entry_display = f"${sl_usd_entry:,.2f} USD (~{sl_btc_entry:,.8f} BTC) ({percent_sl_entry:.2f}%)"
            print(format_line(f"  SL Entrada: {sl_entry_display}"))

            tp_entry_display = "N/A"
            if tp_usd_entry is not None and capital_usd > 0:
                tp_btc_entry = tp_usd_entry / btc_price_usd_for_header if btc_price_usd_for_header and btc_price_usd_for_header > 0 else None
                percent_tp_entry = (tp_usd_entry / capital_usd) * 100
                tp_entry_display = f"${tp_usd_entry:,.2f} USD (~{tp_btc_entry:,.8f} BTC) ({percent_tp_entry:.2f}%)"
            print(format_line(f"  TP Entrada: {tp_entry_display}"))

            rr_entrada_display = "N/A"
            if tp_usd_entry is not None and sl_usd_entry is not None and sl_usd_entry != 0:
                rr_entrada = tp_usd_entry / abs(sl_usd_entry)
                rr_entrada_display = f"{rr_entrada:.2f}"
            print(format_line(f"  R/R Entrada: {rr_entrada_display}"))

            sl_activo_usd_display = f"${sl_activo_total:,.2f} USD" if sl_activo_total is not None else "N/A"
            tp_activo_usd_display = f"${tp_activo_total:,.2f} USD" if tp_activo_total is not None else "N/A"
            sl_activo_btc_display = f"~{sl_activo_total / btc_price_usd_for_header:,.8f} BTC" if sl_activo_total is not None and btc_price_usd_for_header > 0 else "N/A"
            tp_activo_btc_display = f"~{tp_activo_total / btc_price_usd_for_header:,.8f} BTC" if tp_activo_total is not None and btc_price_usd_for_header > 0 else "N/A"
            percent_sl_activo_display = f"({percent_sl_activo:,.2f}%)" if percent_sl_activo is not None else "N/A"
            percent_tp_activo_display = f"({percent_tp_activo:,.2f}%)" if percent_tp_activo is not None else "N/A"
            relacion_activo_display = f"{relacion_activo:,.2f}" if relacion_activo is not None else "N/A"
            if relacion_activo == float('inf'):
                relacion_activo_display = "∞"

            print(format_line(f"  SL Activo Total: {sl_activo_usd_display} ({sl_activo_btc_display}) {percent_sl_activo_display}"))
            print(format_line(f"  TP Activo Total: {tp_activo_usd_display} ({tp_activo_btc_display}) {percent_tp_activo_display}"))
            print(format_line(f"  R/R Activo: {relacion_activo_display}"))

            limit_orders = asset.get('limit_orders', [])
            if limit_orders:
                print(format_line("  Órdenes Límite:"))
                for i, ol in enumerate(limit_orders):
                    # Añadido: Se verifica si el precio de la orden es mayor que 0
                    if ol.get('price') is not None and ol.get('price') > 0:
                        ol_price = ol.get('price')
                        ol_sl_usd = ol.get('sl_usd')
                        ol_tp_usd = ol.get('tp_usd')
                        ol_sl_btc = ol.get('sl_btc')
                        ol_tp_btc = ol.get('tp_btc')

                        ol_price_display = f"${ol_price:,.4f}" if ol_price is not None else "N/A"
                        ol_sl_usd_display = f"${ol_sl_usd:,.2f}" if ol_sl_usd is not None else "N/A"
                        ol_tp_usd_display = f"${ol_tp_usd:,.2f}" if ol_tp_usd is not None else "N/A"
                        ol_sl_btc_display = f"~{ol_sl_btc:,.8f} BTC" if ol_sl_btc is not None else "N/A"
                        ol_tp_btc_display = f"~{ol_tp_btc:,.8f} BTC" if ol_tp_btc is not None else "N/A"

                        line1 = f"    OL {i+1}: Precio {ol_price_display} | SL {ol_sl_usd_display} ({ol_sl_btc_display})"
                        print(format_line(line1))
                        line2 = f"    TP {ol_tp_usd_display} ({ol_tp_btc_display})"
                        print(format_line(line2))
            # Monitoreo de RSI
            if asset.get('rsi_enabled', False):
                rsi_mensual_display = f"{rsi_monthly_value:.2f}" if rsi_monthly_value is not None else "N/A"
                rsi_semanal_display = f"{rsi_weekly_value:.2f}" if rsi_weekly_value is not None else "N/A"
                print(format_line(f"  RSI Mensual: {rsi_mensual_display} - Estado: {rsi_monthly_state}"))
                print(format_line(f"  RSI Semanal: {rsi_semanal_display} - Estado: {rsi_weekly_state}"))
            else:
                print(format_line("  Monitoreo RSI: Deshabilitado"))
            
            # Monitoreo de BOS/CHOCH
            if asset.get('bos_choch_enabled', False):
                print(format_line("  Precios BOS/CHOCH (para cálculo Fibonacci por Temporalidad):"))
                timeframes = ['1d', '4h', '1h']
                for tf in timeframes:
                    boss_key = f'posible_boss_{tf}'
                    choch_key = f'posible_choch_{tf}'
                    
                    boss_value = asset.get(boss_key)
                    choch_value = asset.get(choch_key)

                    if boss_value is not None and choch_value is not None:
                        fib_levels = self._calculate_fibonacci_levels(choch_value, boss_value)
                        
                        print(format_line(f"    Vela {tf.upper()}:"))
                        print(format_line(f"      - 0% BOS: ${fib_levels[0]:,.4f}"))
                        print(format_line(f"      - 38.2%: ${fib_levels[0.382]:,.4f}"))
                        print(format_line(f"      - 50%: ${fib_levels[0.5]:,.4f}"))
                        print(format_line(f"      - 61.8%: ${fib_levels[0.618]:,.4f}"))
                        print(format_line(f"      - 78.6%: ${fib_levels[0.786]:,.4f}"))
                        print(format_line(f"      - 100% CHOCH: ${fib_levels[1]:,.4f}"))

                        if last_known_price:
                            self._check_and_send_fibonacci_alert(symbol, last_known_price, fib_levels, tf)
                    else:
                        print(format_line(f"    Vela {tf.upper()}: No configurado."))
            else:
                print(format_line("  Monitoreo BOS/CHOCH: Deshabilitado"))
            
            # Monitoreo de Fibonacci Manual
            if asset.get('manual_fib_enabled', False):
                print(format_line("  Máximo y Mínimo Histórico Local (Fibonacci Manual):"))
                manual_fib_high = asset.get('manual_fib_high')
                manual_fib_low = asset.get('manual_fib_low')

                if manual_fib_high is not None and manual_fib_low is not None:
                    if last_known_price is not None and (manual_fib_high - last_known_price < 0):
                        message = f"🚨 ALERTA de Fibonacci Manual para {symbol}:\n" \
                                  f"El precio actual ${last_known_price:,.4f} ha superado el Máximo Local ${manual_fib_high:,.4f}.\n" \
                                  f"Se requiere ingresar nuevos puntos de Máximo y Mínimo Local."
                        logging.info(message)
                        self.persistent_alerts.append(message)
                    else:
                        manual_fib_levels = self._calculate_manual_fibonacci_levels(manual_fib_high, manual_fib_low)
                        print(format_line(f"    Máximo Local: ${manual_fib_high:,.4f} USD"))
                        print(format_line(f"    Mínimo Local: ${manual_fib_low:,.4f} USD"))
                        
                        print(format_line(f"    Niveles de Fibonacci:"))
                        print(format_line(f"      - 0%: ${manual_fib_levels[0]:,.4f}"))
                        print(format_line(f"      - 38.2%: ${manual_fib_levels[0.382]:,.4f}"))
                        print(format_line(f"      - 50%: ${manual_fib_levels[0.5]:,.4f}"))
                        print(format_line(f"      - 61.8%: ${manual_fib_levels[0.618]:,.4f}"))
                        print(format_line(f"      - 78.6%: ${manual_fib_levels[0.786]:,.4f}"))
                        print(format_line(f"      - 100%: ${manual_fib_levels[1]:,.4f}"))

                        if last_known_price:
                            self._check_and_send_fibonacci_alert(symbol, last_known_price, manual_fib_levels, "Manual")
                        
                        # --- MODIFICACIÓN: Mostrar soportes y resistencias debajo de los niveles de Fibonacci ---
                        if asset.get('manual_supports'):
                            supports_str = ", ".join([f"${s:,.4f}" for s in sorted(asset['manual_supports'])])
                            print(format_line(f"    Soportes: {supports_str}"))
                        
                        if asset.get('manual_resistances'):
                            resistances_str = ", ".join([f"${r:,.4f}" for r in sorted(asset['manual_resistances'])])
                            print(format_line(f"    Resistencias: {resistances_str}"))
                else:
                    print(format_line("    No configurado."))
            else:
                print(format_line("  Monitoreo Fibonacci Manual: Deshabilitado"))
        
        print(format_line("-" * (TERMINAL_WIDTH - 2)))
        

    def display_main_menu(self):
        self.clear_screen()
        general_settings = self.config_manager.get_general_settings()
        assets = self.config_manager.get_assets_to_monitor()

        capital_usd = general_settings.get('capital_usd', 0.0)
        capital_btc_equivalent = general_settings.get('capital_btc_equivalent', 0.0)
        total_sl_global = general_settings.get('total_sl_global', 0.0)
        total_tp_global = general_settings.get('total_tp_global', 0.0)
        btc_price_usd_for_header = general_settings.get('current_btc_price_usd', 0.0)

        # Totales para las entradas
        total_sl_entradas = sum(asset.get('sl_usd_entry', 0) for asset in assets if asset.get('sl_usd_entry') is not None)
        total_tp_entradas = sum(asset.get('tp_usd_entry', 0) for asset in assets if asset.get('tp_usd_entry') is not None)
        
        sl_btc_entradas = total_sl_entradas / btc_price_usd_for_header if btc_price_usd_for_header > 0 else 0.0
        tp_btc_entradas = total_tp_entradas / btc_price_usd_for_header if btc_price_usd_for_header > 0 else 0.0
        
        percent_sl_entradas = (abs(total_sl_entradas) / capital_usd) * 100 if capital_usd > 0 else 0.0
        percent_tp_entradas = (total_tp_entradas / capital_usd) * 100 if capital_usd > 0 else 0.0

        rr_entradas_display = "N/A"
        if total_tp_entradas is not None and total_sl_entradas is not None and total_sl_entradas != 0:
            rr_entradas = total_tp_entradas / abs(total_sl_entradas)
            rr_entradas_display = f"{rr_entradas:.2f}"

        # Totales Globales
        sl_percentage_global = (abs(total_sl_global) / capital_usd) * 100 if capital_usd > 0 else 0.0
        tp_percentage_global = (total_tp_global / capital_usd) * 100 if capital_usd > 0 else 0.0
        sl_btc_global = total_sl_global / btc_price_usd_for_header if btc_price_usd_for_header > 0 else 0.0
        tp_btc_global = total_tp_global / btc_price_usd_for_header if btc_price_usd_for_header > 0 else 0.0
        
        rr_global_display = "N/A"
        if total_tp_global is not None and total_sl_global is not None and total_sl_global != 0:
            rr_global = total_tp_global / abs(total_sl_global)
            rr_global_display = f"{rr_global:.2f}"

        print("╔═════════════════════════════════════════════════════════════════════════════════════════╗")
        print("║                    Sistema Alerta Temprana de Trading (SATT)                            ║")
        print("║═════════════════════════════════════════════════════════════════════════════════════════╣")
        print(format_line(f"Capital Total: ${capital_usd:,.2f} USD (~{capital_btc_equivalent:,.8f} BTC)"))
        
        print(format_line(f"SL Global: ${total_sl_global:,.2f} USD (~{sl_btc_global:,.8f} BTC) ({sl_percentage_global:.2f}%)"))
        print(format_line(f"TP Global: ${total_tp_global:,.2f} USD (~{tp_btc_global:,.8f} BTC) ({tp_percentage_global:.2f}%)"))
        print(format_line(f"R/R Total Global: {rr_global_display}"))
        
        print(format_line(f"SL Entradas: ${total_sl_entradas:,.2f} USD (~{sl_btc_entradas:,.8f} BTC) ({percent_sl_entradas:.2f}%)"))
        print(format_line(f"TP Entradas: ${total_tp_entradas:,.2f} USD (~{tp_btc_entradas:,.8f} BTC) ({percent_tp_entradas:.2f}%)"))
        print(format_line(f"R/R Entradas: {rr_entradas_display}"))

        print(format_line(f"1 BTC = ${btc_price_usd_for_header:,.2f} USD"))
        
        # --- NUEVO: Mostrar las alertas persistentes aquí ---
        self._display_persistent_alerts()
        # --- Limpiar las alertas después de mostrarlas ---
        self.persistent_alerts = []

        print("╠═════════════════════════════════════════════════════════════════════════════════════════╣")
        print("║                                   Activos Monitoreados                                  ║")
        print("╠═════════════════════════════════════════════════════════════════════════════════════════╣")

        if not assets:
            print(format_line("        No hay activos configurados. Añade uno con la opción 'a'."))
            print("╚═════════════════════════════════════════════════════════════════════════════════════╝")
        else:
            for i, asset in enumerate(assets):
                self._display_asset_info(i + 1, asset, btc_price_usd_for_header, capital_usd)

        print("╠═════════════════════════════════════════════════════════════════════════════════════════╣")
        print("║        a. Añadir/Editar Activo    b. Eliminar Activo    c. Ajustar Config. General      ║")
        print("║ d. Probar Alerta Telegram  e. Gráfica de Capital    f. Historial de alertas             ║")
        print("║        q. Salir                                                                         ║")
        print("╚═════════════════════════════════════════════════════════════════════════════════════════╝")

    def get_user_choice(self):
        """Obtiene la opción del menú del usuario."""
        assets_count = len(self.config_manager.get_assets_to_monitor())
        while True:
            choice = input("Selecciona una opción: ").strip().lower()

            # Comprobar si la entrada es una letra del menú fijo
            if choice in ['q', 'a', 'b', 'c', 'd', 'e', 'f']:
                if choice in ['a', 'b', 'c', 'd', 'e', 'f']:
                    self.persistent_alerts = []  # Limpiar alertas al cambiar de menú
                return choice
            
            # Comprobar si la entrada es un número de activo
            try:
                choice_num = int(choice)
                if 1 <= choice_num <= assets_count:
                    symbol = self.config_manager.get_assets_to_monitor()[choice_num - 1]['symbol']
                    if symbol in self.expanded_assets:
                        self.expanded_assets.remove(symbol)
                    else:
                        self.expanded_assets.append(symbol)
                    return "refresh" # Indicador para refrescar el menú
                else:
                    print("Opción no válida. Por favor, ingresa un número de activo o una opción del menú.")
            except ValueError:
                # La entrada no es ni una letra ni un número válido
                print("Opción no válida. Por favor, ingresa un número o una letra del menú.")
    
    def _get_rsi_values_input(self, prompt, current_values):
        """Función auxiliar para gestionar la entrada de valores de RSI."""
        while True:
            values_str = input(f"{prompt} ({', '.join(map(str, current_values))}): ").strip()
            if not values_str:
                return current_values
            if values_str.lower() == 'c':
                return []
            try:
                new_values = [float(v.strip()) for v in values_str.split(',') if v.strip()]
                return new_values
            except ValueError:
                print("Error: Ingrese números separados por comas o 'c' para borrar.")

    def _get_float_list_input_with_validation(self, prompt, current_values):
        """Función auxiliar para gestionar la entrada de listas de floats."""
        while True:
            values_str = input(f"{prompt} ({', '.join(map(str, current_values))}): ").strip()
            if not values_str:
                return current_values
            if values_str.lower() == 'c':
                return []
            try:
                new_values = [float(v.strip()) for v in values_str.split(',') if v.strip()]
                return new_values
            except ValueError:
                print("Error: Ingrese números separados por comas o 'c' para borrar.")

    def add_edit_asset_menu(self):
        self.persistent_alerts = []  # Limpiar alertas al entrar a otro menú
        self.clear_screen()
        print("╔═════════════════════════════════════════════════════════════════════════════════════╗")
        print("║                                Añadir/Editar Activo                                 ║")
        print("╠═════════════════════════════════════════════════════════════════════════════════════╣")
        symbol = input("Ingrese el símbolo del activo (ej. ETHUSDT): ").strip().upper()

        # --- MODIFICACIÓN: Validar si el símbolo existe antes de continuar ---
        # No se cuelga si el activo no existe, simplemente se crea una configuración nueva
        if not self.api_manager.is_valid_symbol(symbol):
            print(f"ADVERTENCIA: El símbolo '{symbol}' no pudo ser validado por la API.")
            print("Se procederá a crear un nuevo activo, pero es posible que no se puedan obtener datos de precios.")
            if input("¿Desea continuar de todas formas? (s/n): ").strip().lower() != 's':
                return
                
        current_asset_config = self.config_manager.get_asset(symbol)
        if current_asset_config is None:
            current_asset_config = {
                'symbol': symbol,
                'limit_orders': [],
                'rsi_monthly_manual_values': [],
                'rsi_weekly_manual_values': [],
                'rsi_enabled': False,
                'macd_enabled': False,
                'bos_choch_enabled': False,
                'manual_fib_enabled': False,
                'entry_price': None,
                'sl_usd_entry': None,
                'tp_usd_entry': None,
                'posible_boss_1d': None,
                'posible_choch_1d': None,
                'posible_boss_4h': None,
                'posible_choch_4h': None,
                'posible_boss_1h': None,
                'posible_choch_1h': None,
                'manual_fib_high': None,
                'manual_fib_low': None,
                'manual_supports': [],
                'manual_resistances': []
            }
            print(f"Creando nuevo activo: {symbol}")
        else:
            print(f"Editando activo existente: {symbol}")

        current_asset_config['entry_price'] = self._get_float_input_with_validation(
            "Ingrese precio de entrada",
            current_asset_config.get('entry_price')
        )
        current_asset_config['sl_usd_entry'] = self._get_float_input_with_validation(
            "Ingrese SL en USD (negativo para pérdida)",
            current_asset_config.get('sl_usd_entry')
        )
        current_asset_config['tp_usd_entry'] = self._get_float_input_with_validation(
            "Ingrese TP en USD (positivo para ganancia)",
            current_asset_config.get('tp_usd_entry')
        )

        while True:
            add_ol = input("¿Desea añadir/editar órdenes límite? (s/n): ").strip().lower()
            if add_ol == 's':
                order_index_str = input("Ingrese el número de la orden límite a editar (ej. 1, 2) o 'n' para una nueva: ").strip()
                ol_index = -1
                if order_index_str.isdigit():
                    ol_index = int(order_index_str) - 1
                    if ol_index < 0 or ol_index >= len(current_asset_config['limit_orders']):
                        print("Número de orden inválido. Se creará una nueva.")
                        ol_index = -1
                
                if ol_index == -1:
                    new_order = {'price': None, 'sl_usd': None, 'tp_usd': None}
                    print("Ingrese datos para la NUEVA orden límite:")
                else:
                    new_order = current_asset_config['limit_orders'][ol_index]
                    print(f"Editando orden límite {ol_index + 1}:")

                new_order['price'] = self._get_float_input_with_validation(
                    "  Precio de OL",
                    new_order.get('price')
                )
                new_order['sl_usd'] = self._get_float_input_with_validation(
                    "  SL de OL en USD",
                    new_order.get('sl_usd')
                )
                new_order['tp_usd'] = self._get_float_input_with_validation(
                    "  TP de OL en USD",
                    new_order.get('tp_usd')
                )

                if ol_index == -1:
                    current_asset_config['limit_orders'].append(new_order)
            elif add_ol == 'n':
                break
            else:
                print("Opción no válida. Por favor, ingrese 's' o 'n'.")

        print("\n--- Configuración de Alertas por Indicador ---")
        
        # Opciones para habilitar/deshabilitar indicadores
        current_rsi_enabled = current_asset_config.get('rsi_enabled', False)
        choice_rsi = input(f"¿Desea monitorear el RSI? (s/n, actual: {'s' if current_rsi_enabled else 'n'}): ").strip().lower()
        if choice_rsi == 's':
            current_asset_config['rsi_enabled'] = True
        elif choice_rsi == 'n':
            current_asset_config['rsi_enabled'] = False

        current_macd_enabled = current_asset_config.get('macd_enabled', False)
        choice_macd = input(f"¿Desea monitorear el MACD? (s/n, actual: {'s' if current_macd_enabled else 'n'}): ").strip().lower()
        if choice_macd == 's':
            current_asset_config['macd_enabled'] = True
        elif choice_macd == 'n':
            current_asset_config['macd_enabled'] = False

        current_bos_choch_enabled = current_asset_config.get('bos_choch_enabled', False)
        choice_bos_choch = input(f"¿Desea monitorear los puntos BOS/CHOCH para Fibonacci? (s/n, actual: {'s' if current_bos_choch_enabled else 'n'}): ").strip().lower()
        if choice_bos_choch == 's':
            current_asset_config['bos_choch_enabled'] = True
        elif choice_bos_choch == 'n':
            current_asset_config['bos_choch_enabled'] = False

        current_manual_fib_enabled = current_asset_config.get('manual_fib_enabled', False)
        choice_manual_fib = input(f"¿Desea monitorear el rango de Fibonacci Manual? (s/n, actual: {'s' if current_manual_fib_enabled else 'n'}): ").strip().lower()
        if choice_manual_fib == 's':
            current_asset_config['manual_fib_enabled'] = True
        elif choice_manual_fib == 'n':
            current_asset_config['manual_fib_enabled'] = False

        # Solo pedimos los valores si el monitoreo de RSI está activado
        if current_asset_config['rsi_enabled']:
            print("\n--- Configuración de RSI Manual ---")
            current_asset_config['rsi_monthly_manual_values'] = self._get_rsi_values_input(
                f"Ingrese valores de RSI mensuales a monitorear (separados por comas o 'c' para borrar)",
                current_asset_config.get('rsi_monthly_manual_values', [])
            )
            current_asset_config['rsi_weekly_manual_values'] = self._get_rsi_values_input(
                f"Ingrese valores de RSI semanales a monitorear (separados por comas o 'c' para borrar)",
                current_asset_config.get('rsi_weekly_manual_values', [])
            )
        else:
            print("\n--- Monitoreo RSI Deshabilitado ---")

        # Solo pedimos los valores si el monitoreo de BOS/CHOCH está activado
        if current_asset_config['bos_choch_enabled']:
            print("\n--- Configuración de Puntos para Fibonacci (BOS/CHOCH por Temporalidad) ---")
            print("Nota: Ingrese ambos valores para una temporalidad, o deje ambos vacíos/cero para no configurar.")
            timeframes_data = [('1d', 'Diaria'), ('4h', '4 Horas'), ('1h', '1 Hora')]

            for tf_key, tf_name in timeframes_data:
                boss_key = f'posible_boss_{tf_key}'
                choch_key = f'posible_choch_{tf_key}'
                
                current_boss = current_asset_config.get(boss_key)
                current_choch = current_asset_config.get(choch_key)

                while True:
                    print(f"\n--- Vela {tf_name.upper()} ---")
                    new_boss = self._get_float_input_with_validation(
                        f"Ingrese Posible BOS {tf_name} (0% Fibonacci)",
                        current_boss
                    )
                    new_choch = self._get_float_input_with_validation(
                        f"Ingrese Posible CHOCH {tf_name} (100% Fibonacci)",
                        current_choch
                    )

                    if (new_boss is None and new_choch is None) or (new_boss == 0.0 and new_choch == 0.0):
                        current_asset_config[boss_key] = None
                        current_asset_config[choch_key] = None
                        print(f"Puntos BOS/CHOCH para Vela {tf_name} no configurados.")
                        break
                    elif (new_boss is not None and new_choch is None) or \
                         (new_boss is None and new_choch is not None) or \
                         (new_boss == 0.0 and new_choch != 0.0 and new_choch is not None) or \
                         (new_boss != 0.0 and new_boss is not None and new_choch == 0.0):
                        print(f"ADVERTENCIA: Para la vela {tf_name}, debe ingresar AMBOS valores de BOS y CHOCH (o dejar AMBOS vacíos/cero).")
                        continue
                    else:
                        current_asset_config[boss_key] = new_boss
                        current_asset_config[choch_key] = new_choch
                        print(f"Puntos BOS/CHOCH para Vela {tf_name} configurados exitosamente.")
                        break
        else:
            print("\n--- Monitoreo BOS/CHOCH Deshabilitado ---")

        # Solo pedimos los valores si el monitoreo de Fibonacci Manual está activado
        if current_asset_config['manual_fib_enabled']:
            print("\n--- Configuración de Rango Histórico Local para Fibonacci Manual ---")
            current_manual_high = current_asset_config.get('manual_fib_high')
            current_manual_low = current_asset_config.get('manual_fib_low')

            new_manual_high, new_manual_low = self._get_fib_range_input_with_validation(
                "Ingrese Máximo Local (punto alto para Fibonacci Manual)", current_manual_high,
                "Ingrese Mínimo Local (punto bajo para Fibonacci Manual)", current_manual_low
            )

            current_asset_config['manual_fib_high'] = new_manual_high
            current_asset_config['manual_fib_low'] = new_manual_low
        else:
            print("\n--- Monitoreo Fibonacci Manual Deshabilitado ---")

        # AÑADIDO: Nuevas entradas para soportes y resistencias manuales
        print("\n--- Configuración de Alertas de Soportes y Resistencias Manuales ---")
        current_supports = current_asset_config.get('manual_supports', [])
        current_resistances = current_asset_config.get('manual_resistances', [])

        current_asset_config['manual_supports'] = self._get_float_list_input_with_validation(
            f"Ingrese valores de soportes a monitorear (separados por comas o 'c' para borrar)",
            current_supports
        )

        current_asset_config['manual_resistances'] = self._get_float_list_input_with_validation(
            f"Ingrese valores de resistencia a monitorear (separados por comas o 'c' para borrar)",
            current_resistances
        )

        self.config_manager.update_asset(symbol, current_asset_config)
        
        print(f"\nConfiguración del activo {symbol} guardada exitosamente.")
        self.wait_for_user_input()

    def remove_asset_menu(self):
        self.persistent_alerts = []  # Limpiar alertas al entrar a otro menú
        self.clear_screen()
        self.display_header("<<< ELIMINAR ACTIVO >>>")
        assets = self.config_manager.get_assets_to_monitor()
        if not assets:
            self.display_message("No hay activos para eliminar.")
            self.wait_for_user_input()
            return

        for i, asset in enumerate(assets):
            self.display_message(f"{i+1}. {asset['symbol']}")
        
        while True:
            try:
                choice = input("\nIngrese el número del activo a eliminar (o 'c' para cancelar): ").strip()
                if choice.lower() == 'c':
                    print("Operación cancelada.")
                    break
                
                choice_index = int(choice) - 1
                if 0 <= choice_index < len(assets):
                    symbol_to_remove = assets[choice_index]['symbol']
                    confirm = input(f"¿Estás seguro de que deseas eliminar '{symbol_to_remove}'? (s/n): ").strip().lower()
                    if confirm == 's':
                        self.config_manager.remove_asset(symbol_to_remove)
                        self.display_message(f"Activo '{symbol_to_remove}' eliminado exitosamente.")
                        # --- MODIFICACIÓN: Quitar el activo de la lista de expandidos si se elimina
                        if symbol_to_remove in self.expanded_assets:
                             self.expanded_assets.remove(symbol_to_remove)
                    else:
                        self.display_message("Eliminación cancelada.")
                    break
                else:
                    print("Opción inválida.")
            except ValueError:
                print("Entrada inválida. Por favor, ingrese un número o 'c'.")
        
        self.wait_for_user_input()

    def adjust_general_config_menu(self):
        """
        Menú para ajustar la configuración general y registrar capital.
        Ahora el valor de capital en USD se usa para el registro histórico.
        """
        self.persistent_alerts = []  # Limpiar alertas al entrar a otro menú
        self.clear_screen()
        self.display_header("<<< CONFIGURACIÓN GENERAL Y REGISTRO DE CAPITAL >>>")
        general_settings = self.config_manager.get_general_settings()
        
        # --- Parte 1: Ajustar la Configuración General ---
        print("\n--- Ajustar Configuración General ---")
        
        # Opción para activar/desactivar alertas de Telegram
        telegram_alerts_enabled = general_settings.get('telegram_alerts_enabled', False)
        status_text = "Habilitadas" if telegram_alerts_enabled else "Deshabilitadas"
        new_status_input = input(f"Alertas de Telegram actualmente: {status_text}. ¿Deseas cambiarlas? (s/n, dejar vacío para no cambiar): ").strip().lower()
        
        if new_status_input == 's':
            general_settings['telegram_alerts_enabled'] = not telegram_alerts_enabled
            self.config_manager.save_config()
            new_status_text = "Habilitadas" if general_settings['telegram_alerts_enabled'] else "Deshabilitadas"
            self.display_message(f"\nAlertas de Telegram ahora: {new_status_text}.")
            self.wait_for_user_input()
            return
        
        capital_usd_input = input(f"Ingrese el capital total en USD ({general_settings.get('capital_usd') if general_settings.get('capital_usd') is not None else 'N/A'}): ").strip()
        capital_usd_prev = general_settings.get('capital_usd')
        
        capital_changed = False
        if capital_usd_input:
            try:
                new_capital_usd = float(capital_usd_input)
                general_settings['capital_usd'] = new_capital_usd
                capital_changed = True
            except ValueError:
                print("Valor inválido. Se mantendrá el valor actual.")

        new_telegram_chat_id = input(f"Ingrese el Chat ID de Telegram ({general_settings.get('telegram_chat_id', 'N/A')}): ").strip()
        if new_telegram_chat_id:
            general_settings['telegram_chat_id'] = new_telegram_chat_id
        
        new_telegram_bot_token = input(f"Ingrese el Token del Bot de Telegram ({general_settings.get('telegram_bot_token', 'N/A')}): ").strip()
        if new_telegram_bot_token:
            general_settings['telegram_bot_token'] = new_telegram_bot_token

        self.config_manager.save_config()
        self.display_message("\nConfiguración general guardada exitosamente.")
        self.wait_for_user_input()

        # --- Parte 2: Registrar una nueva entrada de capital ---
        if capital_changed:
            while True:
                should_add_capital = input("\n¿Desea registrar este nuevo capital en el historial? (s/n): ").strip().lower()
                if should_add_capital == 's':
                    self.clear_screen()
                    self.display_header("<<< REGISTRAR NUEVO CAPITAL HISTÓRICO >>>")
                    
                    date_str = input(f"Ingrese la fecha del registro (formato YYYY-MM-DD) o deje vacío para usar hoy ({datetime.now().strftime('%Y-%m-%d')}): ").strip()
                    if not date_str:
                        date_str = datetime.now().strftime('%Y-%m-%d')
                    
                    try:
                        datetime.strptime(date_str, '%Y-%m-%d')
                    except ValueError:
                        self.display_message("Formato de fecha inválido. Por favor, use YYYY-MM-DD.")
                        self.wait_for_user_input()
                        continue
                    
                    capital_usd = general_settings.get('capital_usd')
                    btc_price = general_settings.get('current_btc_price_usd', 0)
                    
                    if btc_price > 0:
                        capital_btc = capital_usd / btc_price
                        print(f"Capital en USD: ${capital_usd:,.2f}")
                        print(f"Calculando capital en BTC usando el precio de la API (${btc_price:,.2f})...")
                        print(f"Capital en BTC: {capital_btc:,.8f}")
                    else:
                        print("No se pudo obtener el precio de Bitcoin de la API. Ingrese el capital en BTC manualmente.")
                        capital_btc = self._get_float_input_with_validation("Ingrese el capital en BTC", None)
                        if capital_btc is None:
                            self.display_message("No se puede registrar sin el valor de capital en BTC.")
                            self.wait_for_user_input()
                            continue

                    new_entry = {
                        "date": date_str,
                        "capital_usd": capital_usd,
                        "capital_btc": capital_btc
                    }

                    history_data = self._load_history_data()
                    history_data.append(new_entry)
                    history_data.sort(key=lambda x: x['date'])
                    self._save_history_data(history_data)

                    self.display_message("\n¡Registro de capital añadido exitosamente!")
                    self.wait_for_user_input()
                    break
                
                elif should_add_capital == 'n':
                    self.display_message("Registro de capital cancelado.")
                    self.wait_for_user_input()
                    break
                else:
                    self.display_message("Opción no válida. Por favor, ingrese 's' o 'n'.")


    def test_telegram_alert_menu(self):
        """Menú para probar la configuración de la alerta de Telegram."""
        self.persistent_alerts = []  # Limpiar alertas al entrar a otro menú
        self.clear_screen()
        self.display_header("<<< PROBAR ALERTA DE TELEGRAM >>>")
        general_settings = self.config_manager.get_general_settings()
        
        telegram_enabled = general_settings.get('telegram_alerts_enabled')
        chat_id = general_settings.get('telegram_chat_id')
        bot_token = general_settings.get('telegram_bot_token')
        
        if not telegram_enabled:
            self.display_message("Las alertas de Telegram están deshabilitadas en la configuración general.")
        elif not chat_id or not bot_token:
            self.display_message("Faltan el Chat ID o el Bot Token en la configuración. No se puede probar la alerta.")
        else:
            self.display_message("Enviando un mensaje de prueba a Telegram...")
            test_message = "✅ Alerta de prueba de SATT enviada con éxito."
            try:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {'chat_id': chat_id, 'text': test_message, 'parse_mode': 'HTML'}
                response = requests.post(url, data=payload, timeout=10)
                response.raise_for_status()
                self.display_message("¡Mensaje de prueba enviado con éxito!")
            except requests.exceptions.RequestException as e:
                self.display_message(f"Error al enviar el mensaje de prueba: {e}")
        
        self.wait_for_user_input()

    def display_message(self, message):
        print(message)
    
    def display_header(self, title):
        print("\n" + "=" * 70)
        print(f"  {title}  ")
        print("=" * 70)

    def display_separator(self, separator_char='-'):
        print(separator_char * 70)

    def wait_for_user_input(self, prompt="Presiona Enter para continuar..."):
        input(prompt)

    # --- Funcionalidad para la gráfica de capital ---
    def _load_history_data(self):
        """Carga los datos históricos del archivo JSON, ignorando la coma final si existe."""
        if os.path.exists(self.HISTORY_FILE):
            try:
                with open(self.HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []

    def _save_history_data(self, data):
        """Guarda los datos históricos en el archivo JSON."""
        try:
            with open(self.HISTORY_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError as e:
            self.display_message(f"Error al guardar el archivo de historial: {e}")

    def _plot_terminal_graph(self, data, currency_type):
        """Dibuja una gráfica simple en el terminal con líneas continuas."""
        self.clear_screen()
        
        is_satoshi = (currency_type == 'satoshi')
        display_currency = 'SATOSHI' if is_satoshi else 'USD'
        data_key = 'capital_btc' if is_satoshi else 'capital_usd'
        
        if is_satoshi:
            # Convertir valores de BTC a Satoshi para la visualización
            values = [entry[data_key] * 100_000_000 for entry in data]
        else:
            values = [entry[data_key] for entry in data]

        if len(data) < 2:
            self.display_header(f"GRÁFICA DE CAPITAL en {display_currency}")
            self.display_message("No hay suficientes datos para generar una gráfica. Necesitas al menos dos registros.")
            self.wait_for_user_input()
            return
        
        dates = [entry['date'] for entry in data]

        min_val = min(values)
        max_val = max(values)
        val_range = max_val - min_val

        if val_range == 0:
            self.display_header(f"GRÁFICA DE CAPITAL en {display_currency}")
            self.display_message("Los valores de capital son todos iguales. No se puede graficar el movimiento.")
            self.wait_for_user_input()
            return

        graph_width = 60
        graph_height = 20
        
        # Escalar los valores a la altura de la gráfica (0 a graph_height-1)
        scaled_values = [int(((v - min_val) / val_range) * (graph_height - 1)) for v in values]
        
        grid = [[' ' for _ in range(graph_width)] for _ in range(graph_height)]

        for i, val in enumerate(scaled_values):
            x = int(i * (graph_width - 1) / (len(values) - 1))
            y = graph_height - 1 - val
            grid[y][x] = '●'
            
            if i > 0:
                prev_x = int((i - 1) * (graph_width - 1) / (len(values) - 1))
                prev_y = graph_height - 1 - scaled_values[i-1]
                
                # Unir el punto anterior con el actual
                dx = x - prev_x
                dy = y - prev_y
                
                # Usar una interpolación lineal para rellenar los puntos intermedios
                num_steps = abs(dx) if abs(dx) > abs(dy) else abs(dy)
                if num_steps > 0:
                    for j in range(num_steps):
                        step_x = prev_x + int(dx * (j / num_steps))
                        step_y = prev_y + int(dy * (j / num_steps))
                        
                        if 0 <= step_y < graph_height and 0 <= step_x < graph_width:
                            grid[step_y][step_x] = '•'
        
        # Dibujar los puntos principales encima de las líneas
        for i, val in enumerate(scaled_values):
            x = int(i * (graph_width - 1) / (len(values) - 1))
            y = graph_height - 1 - val
            if 0 <= y < graph_height and 0 <= x < graph_width:
                grid[y][x] = '●'
        
        self.display_header(f"GRÁFICA DE CAPITAL en {display_currency}")
        print(format_line(""))
        print(format_line(f"Valores: {min_val:,.2f} a {max_val:,.2f} {display_currency}"))
        print(format_line(""))
        
        for i, row in enumerate(grid):
            y_val = min_val + (val_range * (1 - i / (graph_height - 1)))
            label = f"{int(y_val):,}" if is_satoshi else f"{y_val:,.2f}"
            print(f"║ {label.ljust(9)} ║ {''.join(row).ljust(graph_width)}║")

        date_labels = [dates[0], dates[-1]]
        date_line = f"║{' ' * 11}╚{'═' * (graph_width-1)}╝"
        print(date_line)
        print(f"║{' ' * 11}{date_labels[0].ljust(int((graph_width-1)/2))}{date_labels[1].rjust(int((graph_width-1)/2))}║")
        print("╚══════════════════════════════════════════════════════════════════════════════╝")
        self.wait_for_user_input()
    def display_capital_graph(self):
        """Menú para la gráfica de capital."""
        self.persistent_alerts = []  # Limpiar alertas al entrar a otro menú
        data = self._load_history_data()

        if not data:
            self.clear_screen()
            self.display_header("GRÁFICA DE CAPITAL")
            self.display_message("No hay datos históricos de capital para graficar. Añade registros con la opción 'c'.")
            self.wait_for_user_input()
            return

        while True:
            self.clear_screen()
            self.display_header("GRÁFICA DE CAPITAL")
            self.display_message("¿Qué capital desea graficar?")
            self.display_message("1. Capital en USD")
            self.display_message("2. Capital en BTC (mostrado en Satoshi)")
            self.display_message("0. Volver al menú principal")

            choice = input("\nSelecciona una opción: ").strip()

            if choice == '1':
                self._plot_terminal_graph(data, 'usd')
            elif choice == '2':
                self._plot_terminal_graph(data, 'satoshi')
            elif choice == '0':
                break
            else:
                self.display_message("Opción no válida. Inténtalo de nuevo.")
                time.sleep(1)

    def display_alert_history_menu(self):
        """Muestra las últimas 20 alertas del archivo alert_history.json."""
        self.clear_screen()
        self.display_header("<<< HISTORIAL DE ALERTAS >>>")
        
        history = self.config_manager.get_alert_history()
        
        if not history:
            self.display_message("No hay alertas registradas en el historial.")
        else:
            sorted_history = sorted(history, key=lambda x: x.get('timestamp', '0'), reverse=True)
            
            alerts_to_display = sorted_history[:20]

            self.display_separator()
            for alert in alerts_to_display:
                timestamp = alert.get('timestamp', 'N/A')
                symbol = alert.get('symbol', 'N/A')
                alert_type = alert.get('type', 'N/A')
                message = alert.get('message', 'N/A')
                
                print(f"[{timestamp}] - Activo: {symbol} | Tipo: {alert_type}")
                print(f"Mensaje: {message}\n")
            self.display_separator()

        self.wait_for_user_input()
