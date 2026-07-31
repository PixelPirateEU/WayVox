import os
import glob
import time
import logging
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("WayVox.HotkeyListener")

class GlobalHotkeyListener(QThread):
    """Wayland-kompatibler globaler Hotkey-Listener unter Nutzung von evdev oder pynput."""

    hotkey_pressed = Signal()

    def __init__(self, combo_str: str = "KEY_F12", device_path: str = None):
        super().__init__()
        self.combo_str = combo_str.upper()
        self.device_path = device_path
        self._running = False
        self._keys_pressed = set()
        self._last_trigger_time = 0.0
        self._target_keys = {self._normalize_key(k) for k in self.combo_str.split("+")}

    def _normalize_key(self, key_str: str) -> str:
        """Normalisiert Tastenbezeichnungen für flexible Eingabe (Meta, Alt, Ctrl, F-Tasten, Buchstabentasten)."""
        k = key_str.upper().strip()
        if not k.startswith("KEY_"):
            k = f"KEY_{k}"

        # Meta / Windows / Super Tasten
        if k in ("KEY_LEFTMETA", "KEY_RIGHTMETA", "KEY_META", "KEY_SUPER", "KEY_WIN", "KEY_CMD", "KEY_CMD_L", "KEY_CMD_R"):
            return "KEY_META"
        # Alt Tasten
        elif k in ("KEY_LEFTALT", "KEY_RIGHTALT", "KEY_ALT", "KEY_ALT_L", "KEY_ALT_R"):
            return "KEY_ALT"
        # Ctrl Tasten
        elif k in ("KEY_LEFTCTRL", "KEY_RIGHTCTRL", "KEY_CTRL", "KEY_CTRL_L", "KEY_CTRL_R"):
            return "KEY_CTRL"
        # Shift Tasten
        elif k in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT", "KEY_SHIFT", "KEY_SHIFT_L", "KEY_SHIFT_R"):
            return "KEY_SHIFT"
        # Grave / Circumflex / ^
        elif k in ("KEY_GRAVE", "KEY_^", "KEY_CIRCUMFLEX", "KEY_CARET", "KEY_TILDE"):
            return "KEY_GRAVE"
        # 102ND / < / Less
        elif k in ("KEY_102ND", "KEY_<", "KEY_LESS"):
            return "KEY_102ND"
        # Einzelne Anführungszeichen/Buchstaben wie KEY_'X' -> KEY_X
        elif len(k) > 4 and k.startswith("KEY_'") and k.endswith("'"):
            char = k[5:-1].upper()
            return f"KEY_{char}"
        return k

    def update_combination(self, combo_str: str):
        """Aktualisiert die Hotkey-Kombination zur Laufzeit."""
        self.combo_str = combo_str.upper()
        self._target_keys = {self._normalize_key(k) for k in self.combo_str.split("+")}
        self._keys_pressed.clear()
        logger.info(f"Hotkey aktualisiert auf: {self.combo_str} (Ziel-Tasten: {self._target_keys})")

    def run(self):
        """Thread-Hauptschleife für die Hotkey-Überwachung."""
        self._running = True
        logger.info(f"Starte Hotkey-Listener für Kombination: {self.combo_str}")

        # Versuche zuerst evdev (empfohlener Linux/Wayland Weg)
        if not self._run_evdev():
            logger.info("Nutze pynput für die globale Hotkey-Überwachung...")
            self._run_pynput()

    def stop(self):
        """Stoppt den Listener-Thread."""
        self._running = False
        self.wait(1000)

    def _run_evdev(self) -> bool:
        """Nutzt /dev/input via python-evdev."""
        try:
            import evdev
            from evdev import ecodes
        except ImportError:
            logger.warning("Modul 'evdev' nicht vorhanden. Installiere 'python-evdev'.")
            return False

        devices = []
        if self.device_path and os.path.exists(self.device_path):
            try:
                devices.append(evdev.InputDevice(self.device_path))
            except Exception as e:
                logger.warning(f"Konnte Gerät {self.device_path} nicht öffnen: {e}")

        if not devices:
            for path in glob.glob("/dev/input/event*"):
                try:
                    dev = evdev.InputDevice(path)
                    capabilities = dev.capabilities()
                    if ecodes.EV_KEY in capabilities:
                        keys = capabilities[ecodes.EV_KEY]
                        if ecodes.KEY_A in keys or ecodes.KEY_SPACE in keys or ecodes.KEY_F12 in keys or ecodes.KEY_X in keys:
                            devices.append(dev)
                except (PermissionError, OSError):
                    continue

        if not devices:
            logger.debug("Keine direkt zugänglichen /dev/input/ Geräte gefunden. Wechsel zu pynput...")
            return False

        logger.info(f"Überwache {len(devices)} Eingabegeräte für globale Hotkeys...")

        import select
        device_map = {dev.fd: dev for dev in devices}

        while self._running:
            try:
                r, _, _ = select.select(device_map.keys(), [], [], 0.5)
                for fd in r:
                    dev = device_map[fd]
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            key_code = evdev.categorize(event).keycode
                            keys = [key_code] if isinstance(key_code, str) else key_code
                            
                            if event.value == 1:  # Key Down
                                for k in keys:
                                    norm_key = self._normalize_key(k)
                                    self._keys_pressed.add(norm_key)
                                self._check_combination()

                            elif event.value == 0:  # Key Up
                                for k in keys:
                                    norm_key = self._normalize_key(k)
                                    self._keys_pressed.discard(norm_key)
            except Exception as e:
                if self._running:
                    logger.debug(f"evdev Lesefehler: {e}")

        for dev in devices:
            try:
                dev.close()
            except Exception:
                pass
        return True

    def _extract_pynput_key(self, key) -> str:
        """Extrahiert saubere Key-Strings aus pynput Key / KeyCode Objekten (auch unter Steuerungstasten wie Ctrl)."""
        if hasattr(key, 'vk') and key.vk is not None:
            if 65 <= key.vk <= 90 or 97 <= key.vk <= 122:
                return f"KEY_{chr(key.vk).upper()}"

        if hasattr(key, 'name') and key.name:
            return f"KEY_{key.name.upper()}"

        if hasattr(key, 'char') and key.char:
            c = key.char
            # Steuerzeichen \x01 bis \x1a (Ctrl+A bis Ctrl+Z) abfangen
            if len(c) == 1 and 1 <= ord(c) <= 26:
                return f"KEY_{chr(ord(c) + 64)}"
            return f"KEY_{c.upper()}"

        s = str(key).upper().replace("'", "")
        if not s.startswith("KEY_"):
            s = f"KEY_{s}"
        return s

    def _run_pynput(self):
        """Fallback über pynput Listener."""
        try:
            from pynput import keyboard

            def on_press(key):
                try:
                    key_str = self._extract_pynput_key(key)
                    norm_key = self._normalize_key(key_str)
                    self._keys_pressed.add(norm_key)
                    self._check_combination()
                except Exception:
                    pass

            def on_release(key):
                try:
                    key_str = self._extract_pynput_key(key)
                    norm_key = self._normalize_key(key_str)
                    self._keys_pressed.discard(norm_key)
                except Exception:
                    pass

            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                while self._running and listener.running:
                    self.msleep(100)
                listener.stop()

        except Exception as e:
            logger.error(f"Fehler beim pynput Hotkey-Listener: {e}")

    def _check_combination(self):
        """Prüft ob alle Tasten der Zielkombination aktuell gedrückt sind (mit 350ms Entprellung)."""
        if self._target_keys.issubset(self._keys_pressed):
            now = time.time()
            if now - self._last_trigger_time < 0.35:
                self._keys_pressed.clear()
                return

            self._last_trigger_time = now
            logger.info(f"Hotkey getriggert: {self.combo_str}")
            self.hotkey_pressed.emit()
            self._keys_pressed.clear()
