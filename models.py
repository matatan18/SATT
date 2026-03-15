import json

class ActivoConfig:
    """
    Representa la configuración de un activo individual a monitorear
    en la ficha estándar (TON/USDT, ETH/USDT, materias primas, etc.).
    """
    def __init__(self, ticker, sl=None, tp=None, estrategia="", rsi_mensual_manual=None, rsi_semanal_manual=None,
                 bos_1d=None, choch_1d=None, bos_4h=None, choch_4h=None,
                 bos_1h=None, choch_1h=None, bos_15min=None, choch_15min=None,
                 maximo=None, minimo=None):
        self.ticker = ticker  # Ej: "TON/USDT", "EUR/USD", "AAPL"
        self.sl = sl
        self.tp = tp
        self.estrategia = estrategia

        # Configuración de RSI para este activo
        self.rsi_mensual_manual = rsi_mensual_manual
        self.rsi_semanal_manual = rsi_semanal_manual

        # Configuración de BOS/CHOCH para diferentes temporalidades
        self.bos_1d = bos_1d
        self.choch_1d = choch_1d
        self.bos_4h = bos_4h
        self.choch_4h = choch_4h
        self.bos_1h = bos_1h
        self.choch_1h = choch_1h
        self.bos_15min = bos_15min
        self.choch_15min = choch_15min

        # Configuración de Máximo/Mínimo para Fibonacci condicional
        self.maximo = maximo
        self.minimo = minimo

    def to_dict(self):
        """Convierte el objeto ActivoConfig a un diccionario para guardar."""
        return {
            "ticker": self.ticker,
            "sl": self.sl,
            "tp": self.tp,
            "estrategia": self.estrategia,
            "rsi_mensual_manual": self.rsi_mensual_manual,
            "rsi_semanal_manual": self.rsi_semanal_manual,
            "bos_1d": self.bos_1d,
            "choch_1d": self.choch_1d,
            "bos_4h": self.bos_4h,
            "choch_4h": self.choch_4h,
            "bos_1h": self.bos_1h,
            "choch_1h": self.choch_1h,
            "bos_15min": self.bos_15min,
            "choch_15min": self.choch_15min,
            "maximo": self.maximo,
            "minimo": self.minimo
        }

    @classmethod
    def from_dict(cls, data):
        """Crea un objeto ActivoConfig desde un diccionario."""
        return cls(**data)


class MacroIndicadorConfig:
    """
    Representa la configuración de los indicadores macro (BTC, TOTAL2, TOTAL3).
    Estos son estáticos y no tienen SL/TP ni estrategia.
    """
    def __init__(self, name, rsi_mensual_manual=None, rsi_semanal_manual=None,
                 bos_1d=None, choch_1d=None, bos_4h=None, choch_4h=None,
                 bos_1h=None, choch_1h=None, bos_15min=None, choch_15min=None,
                 maximo=None, minimo=None):
        self.name = name  # Ej: "BTC/USD", "TOTAL2", "TOTAL3"
        self.rsi_mensual_manual = rsi_mensual_manual
        self.rsi_semanal_manual = rsi_semanal_manual
        # Nota: MACD no tiene entrada manual, se calcula automáticamente.

        # Solo para BTC, los BOS/CHOCH y Max/Min
        self.bos_1d = bos_1d
        self.choch_1d = choch_1d
        self.bos_4h = bos_4h
        self.choch_4h = choch_4h
        self.bos_1h = bos_1h
        self.choch_1h = choch_1h
        self.bos_15min = bos_15min
        self.choch_15min = choch_15min
        self.maximo = maximo
        self.minimo = minimo

    def to_dict(self):
        """Convierte el objeto MacroIndicadorConfig a un diccionario para guardar."""
        return {
            "name": self.name,
            "rsi_mensual_manual": self.rsi_mensual_manual,
            "rsi_semanal_manual": self.rsi_semanal_manual,
            "bos_1d": self.bos_1d,
            "choch_1d": self.choch_1d,
            "bos_4h": self.bos_4h,
            "choch_4h": self.choch_4h,
            "bos_1h": self.bos_1h,
            "choch_1h": self.choch_1h,
            "bos_15min": self.bos_15min,
            "choch_15min": self.choch_15min,
            "maximo": self.maximo,
            "minimo": self.minimo
        }

    @classmethod
    def from_dict(cls, data):
        """Crea un objeto MacroIndicadorConfig desde un diccionario."""
        return cls(**data)

class Alerta:
    """
    Representa una alerta generada por el sistema.
    """
    def __init__(self, timestamp, activo, tipo_alerta, precio, estatus):
        self.timestamp = timestamp  # Formato YYYY-MM-DD HH:MM:SS
        self.activo = activo
        self.tipo_alerta = tipo_alerta
        self.precio = precio
        self.estatus = estatus

    def to_dict(self):
        """Convierte la alerta a un diccionario para guardar."""
        return {
            "timestamp": self.timestamp,
            "activo": self.activo,
            "tipo_alerta": self.tipo_alerta,
            "precio": self.precio,
            "estatus": self.estatus
        }

    @classmethod
    def from_dict(cls, data):
        """Crea un objeto Alerta desde un diccionario."""
        return cls(**data)
