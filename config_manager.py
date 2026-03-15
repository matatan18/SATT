import json
import os
import logging
from typing import Optional
from datetime import datetime
import pandas as pd

class ConfigManager:
    """
    Gestión de la configuración del sistema y persistencia en disco.
    """
    _default_alert_settings = {
        "telegram_alerts_enabled": False,
        "telegram_chat_id": "",
        "telegram_bot_token": "",
        "enabled_alert_types": [
            "SL ALCANZADO", "TP ALCANZADO", "RSI CRITICO", "RSI CAMBIO ESTATUS ALCISTA",
            "RSI CAMBIO ESTATUS BAJISTA", "BOS/CHOCH: Confirmación de Ruptura",
            "FIBO (Retroceso/Extensión): Nivel Alcanzado", "MENSAJE DE PRUEBA",
            "ERROR CRITICO", "MACD Mensual BITCOIN", "FIBO_MANUAL: Nivel Alcanzado",
            "SOPORTE ALCANZADO", "RESISTENCIA ALCANZADA"
        ],
        "alert_categories": {
            "SL ALCANZADO": {"description": "Alerta cuando el precio alcanza el Stop Loss de una operación."},
            "TP ALCANZADO": {"description": "Alerta cuando el precio alcanza el Take Profit de una operación."},
            "RSI CRITICO": {"description": "Alerta cuando el RSI cruza niveles de sobrecompra/sobreventa críticos."},
            "RSI CAMBIO ESTATUS ALCISTA": {"description": "Alerta cuando el RSI indica un cambio a estatus alcista."},
            "RSI CAMBIO ESTATUS BAJISTA": {"description": "Alerta cuando el RSI indica un cambio a estatus bajista."},
            "BOS/CHOCH: Confirmación de Ruptura": {"description": "Alerta cuando el precio cruza un nivel de BOS/CHOCH."},
            "FIBO (Retroceso/Extensión): Nivel Alcanzado": {"description": "Alerta cuando el precio toca un nivel de Fibonacci (0.382, 0.5, 0.618, 0.786)."},
            "MENSAJE DE PRUEBA": {"description": "Mensaje de prueba para verificar la integración de Telegram."},
            "ERROR CRITICO": {"description": "Alertas de errores críticos del sistema."},
            "MACD Mensual BITCOIN": {"description": "Alerta sobre el cruce MACD/Signal para Bitcoin en temporalidad mensual."},
            "FIBO_MANUAL: Nivel Alcanzado": {"description": "Alerta cuando el precio alcanza un nivel de Fibonacci calculado con máximos/mínimos locales manuales."},
            "SOPORTE ALCANZADO": {"description": "Alerta cuando el precio alcanza un nivel de soporte definido manualmente."},
            "RESISTENCIA ALCANZADA": {"description": "Alerta cuando el precio alcanza un nivel de resistencia definido manualmente."}
        }
    }

    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.history_file = 'alert_history.json'
        self.config = {
            "general_settings": {
                "capital_usd": 1000.00,
                "update_interval_seconds": 300,
                "total_sl_global": 0.0,
                "total_tp_global": 0.0,
                "capital_btc_equivalent": 0.0,
                "current_btc_price_usd": 0.0,
                "capital_history": []
            },
            "assets_to_monitor": [],
            "alert_settings": self._default_alert_settings.copy()
        }
        self.capital_history = pd.DataFrame(columns=['timestamp', 'capital_usd', 'capital_btc'])
        self.load_config()
        self._load_capital_history()
        logging.info("ConfigManager inicializado.")

    def load_config(self):
        """
        Carga la configuración desde el archivo JSON, migrando si es necesario.
        """
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                self.config["general_settings"].update(loaded_config.get("general_settings", {}))
                self.config["assets_to_monitor"] = loaded_config.get("assets_to_monitor", [])
                
                current_alert_settings = loaded_config.get("alert_settings", {})
                merged_alert_settings = self._default_alert_settings.copy()
                merged_alert_settings.update(current_alert_settings)
                
                existing_enabled_types = set(merged_alert_settings.get('enabled_alert_types', []))
                default_enabled_types = set(self._default_alert_settings['enabled_alert_types'])
                merged_alert_settings['enabled_alert_types'] = sorted(list(existing_enabled_types.union(default_enabled_types)))

                existing_alert_categories = merged_alert_settings.get('alert_categories', {})
                default_alert_categories = self._default_alert_settings['alert_categories']
                
                new_alert_categories = default_alert_categories.copy()
                new_alert_categories.update(existing_alert_categories)
                merged_alert_settings['alert_categories'] = new_alert_categories

                self.config['alert_settings'] = merged_alert_settings

                self.config['general_settings'].setdefault("total_sl_global", 0.0)
                self.config['general_settings'].setdefault("total_tp_global", 0.0)
                self.config['general_settings'].setdefault("capital_btc_equivalent", 0.0)
                self.config['general_settings'].setdefault("current_btc_price_usd", 0.0)
                self.config['general_settings'].setdefault("capital_history", [])
                
                if "enabled_alert_types" in self.config['general_settings']:
                    logging.warning("Migrando 'enabled_alert_types' de general_settings a alert_settings. Se guardará la configuración.")
                    migrated_types = set(self.config['general_settings'].pop("enabled_alert_types"))
                    self.config['alert_settings']['enabled_alert_types'] = sorted(list(set(self.config['alert_settings']['enabled_alert_types']).union(migrated_types)))
                    self.save_config()
                
                for asset in self.config['assets_to_monitor']:
                    asset.setdefault('posible_boss_1d', None)
                    asset.setdefault('posible_choch_1d', None)
                    asset.setdefault('posible_boss_4h', None)
                    asset.setdefault('posible_choch_4h', None)
                    asset.setdefault('posible_boss_1h', None)
                    asset.setdefault('posible_choch_1h', None)
                    
                    asset.setdefault('manual_fib_high', None)
                    asset.setdefault('manual_fib_low', None)
                    
                    asset.setdefault('fibo_levels_reached', {})
                    
                    asset.setdefault('supports', [])
                    asset.setdefault('resistances', [])
                    
                logging.info(f"Configuración cargada desde {self.config_file}")
            except json.JSONDecodeError as e:
                logging.error(f"Error al decodificar JSON de {self.config_file}: {e}. Se usará la configuración por defecto y se sobrescribirá el archivo.")
                self.save_config()
            except Exception as e:
                logging.error(f"Error inesperado al cargar la configuración: {e}. Se usará la configuración por defecto y se sobrescribirá el archivo.")
                self.save_config()
        else:
            logging.warning(f"Archivo de configuración '{self.config_file}' no encontrado. Creando uno por defecto.")
            self.save_config()

    def _load_capital_history(self):
        """
        Carga el historial de capital desde la configuración o crea un nuevo DataFrame.
        """
        history_data = self.config['general_settings'].get('capital_history', [])
        self.capital_history = pd.DataFrame(history_data)
        if not self.capital_history.empty:
            self.capital_history['timestamp'] = pd.to_datetime(self.capital_history['timestamp'])
        else:
            self.capital_history = pd.DataFrame(columns=['timestamp', 'capital_usd', 'capital_btc'])
            
    def update_capital_history(self):
        """
        Añade el capital actual al historial.
        """
        general_settings = self.get_general_settings()
        new_entry = pd.DataFrame([{
            'timestamp': datetime.now(),
            'capital_usd': general_settings['capital_usd'],
            'capital_btc': general_settings['capital_btc_equivalent']
        }])
        self.capital_history = pd.concat([self.capital_history, new_entry], ignore_index=True)
        self.config['general_settings']['capital_history'] = self.capital_history.to_dict('records')
        self.save_config() # ¡Guarda el historial inmediatamente!

    def reload_config(self):
        """
        Recarga la configuración del archivo para reflejar cambios externos.
        """
        self.load_config()
        self._load_capital_history()
        logging.info("Configuración recargada desde el archivo.")

    def save_config(self):
        """
        Guarda la configuración actual en el archivo JSON.
        """
        try:
            config_to_save = self.config.copy()
            if 'alert_settings' in config_to_save and 'enabled_alert_types' in config_to_save['alert_settings']:
                config_to_save['alert_settings']['enabled_alert_types'] = sorted(list(set(config_to_save['alert_settings']['enabled_alert_types'])))
            
            if hasattr(self, 'capital_history'):
                config_to_save['general_settings']['capital_history'] = self.capital_history.to_dict('records')
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save, f, indent=4, ensure_ascii=False, default=str)
                
            logging.info(f"Configuración guardada en {self.config_file}")
        except Exception as e:
            logging.error(f"Error al guardar la configuración en {self.config_file}: {e}")

    def get_general_settings(self) -> dict:
        """
        Retorna la referencia a la sección de configuración general en memoria.
        """
        return self.config['general_settings']

    def update_general_settings(self, new_settings: dict):
        """
        Actualiza las propiedades de general_settings en memoria y guarda.
        """
        self.config['general_settings'].update(new_settings)
        self.save_config()

    def get_alert_settings(self) -> dict:
        """
        Retorna la referencia a la sección de configuración de alertas en memoria.
        """
        return self.config['alert_settings']

    def update_alert_settings(self, new_settings: dict):
        """
        Actualiza las propiedades de alert_settings en memoria y guarda.
        """
        self.config['alert_settings'].update(new_settings)
        self.save_config()

    def get_assets_to_monitor(self) -> list:
        """
        Retorna la lista de activos a monitorear.
        """
        return self.config['assets_to_monitor']

    def set_assets_to_monitor(self, assets_list: list):
        """
        Reemplaza la lista completa de activos.
        """
        self.config['assets_to_monitor'] = assets_list
        self.save_config()

    def get_asset(self, symbol: str) -> Optional[dict]:
        """
        Busca y retorna la configuración de un activo específico por su símbolo.
        """
        for asset in self.config['assets_to_monitor']:
            if asset.get('symbol') == symbol:
                return asset
        return None

    def update_asset(self, symbol: str, new_asset_config: dict):
        """
        Actualiza la configuración de un activo existente o lo añade si no existe.
        """
        found = False
        for i, asset in enumerate(self.config['assets_to_monitor']):
            if asset.get('symbol') == symbol:
                asset.update(new_asset_config)
                self.config['assets_to_monitor'][i] = asset
                found = True
                break
        if not found:
            default_asset_template = {
                'symbol': symbol,
                'limit_orders': [],
                'rsi_monthly_manual_values': [],
                'rsi_weekly_manual_values': [],
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
                'fibo_levels_reached': {},
                'supports': [],
                'resistances': []
            }
            asset_to_add = default_asset_template.copy()
            asset_to_add.update(new_asset_config)
            self.config['assets_to_monitor'].append(asset_to_add)
        self.save_config()

    def remove_asset(self, symbol: str) -> bool:
        """
        Elimina un activo de la lista de monitoreo. Guarda la configuración después.
        """
        initial_len = len(self.config['assets_to_monitor'])
        self.config['assets_to_monitor'] = [
            asset for asset in self.config['assets_to_monitor'] if asset.get('symbol') != symbol
        ]
        if len(self.config['assets_to_monitor']) < initial_len:
            self.save_config()
            return True
        return False

    def get_capital(self) -> float:
        """
        Retorna el capital en USD de la configuración general.
        """
        return self.config['general_settings'].get('capital_usd', 0.0)

    def update_global_totals(self, sl_total: float, tp_total: float, btc_equivalent: float):
        """
        Actualiza los totales globales en la configuración en memoria.
        """
        self.config['general_settings']['total_sl_global'] = sl_total
        self.config['general_settings']['total_tp_global'] = tp_total
        self.config['general_settings']['capital_btc_equivalent'] = btc_equivalent
        self.update_capital_history()

    def update_btc_price(self, price: float):
        """
        Actualiza el precio actual de Bitcoin en la configuración en memoria.
        """
        self.config['general_settings']['current_btc_price_usd'] = price
        self.save_config()
        
    def get_alert_history(self):
        """
        Carga y retorna el historial de alertas desde su archivo JSON.
        """
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return []
        return []
