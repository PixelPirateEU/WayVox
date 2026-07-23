import json
import os
import logging
from typing import Any, Dict

logger = logging.getLogger("WayVox.Config")

DEFAULT_CONFIG: Dict[str, Any] = {
    "model": {
        "name": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "language": "de",
        "beam_size": 5,
        "initial_prompt": "Das ist ein deutscher Text in hoher Qualität."
    },
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "device_index": None,
        "feedback_sounds": True,
        "feedback_volume": 0.3
    },
    "injection": {
        "method": "wtype",
        "paste_delay_ms": 50,
        "fallback_to_clipboard": True
    },
    "hotkey": {
        "enabled": True,
        "combination": "KEY_LEFTALT+KEY_SPACE",
        "device_path": None
    },
    "ui": {
        "size": 120,
        "border_width": 6,
        "position_x": 100,
        "position_y": 100,
        "always_on_top": True,
        "show_label": True
    }
}

class ConfigManager:
    """Lädt und verwaltet die Konfigurationsparameter für WayVox."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = os.path.abspath(config_path)
        self.config_data = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Lädt die Konfiguration aus der Datei. Verwendet Standards, wenn nicht vorhanden."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_cfg = json.load(f)
                    self._deep_update(self.config_data, user_cfg)
                logger.info(f"Konfiguration aus {self.config_path} geladen.")
            except Exception as e:
                logger.error(f"Fehler beim Laden von {self.config_path}: {e}. Nutze Standardwerte.")
        else:
            logger.info(f"{self.config_path} nicht gefunden. Erstelle Standardkonfiguration.")
            self.save_config()
        return self.config_data

    def save_config(self):
        """Speichert die aktuelle Konfiguration in die JSON-Datei."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Konfiguration in {self.config_path} gespeichert.")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Konfiguration: {e}")

    def _deep_update(self, base_dict: dict, update_dict: dict):
        """Aktualisiert verschachtelte Dictionaries rekursiv."""
        for key, value in update_dict.items():
            if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value

    def get(self, section: str, key: str = None, fallback: Any = None) -> Any:
        """Sicherer Zugriff auf Konfigurationsschlüssel."""
        if section not in self.config_data:
            return fallback
        if key is None:
            return self.config_data[section]
        return self.config_data[section].get(key, fallback)
