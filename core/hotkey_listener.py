import os
import glob
import logging
from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("WayVox.HotkeyListener")

class GlobalHotkeyListener(QThread):
    """Wayland-kompatibler globaler Hotkey-Listener unter Nutzung von evdev oder pynput."""

    hotkey_pressed = Signal()

    def __init__(self, combo_str: str = "KEY_LEFTALT+KEY_SPACE", device_path: str = None):
        super().__init__()
        self.combo_str = combo_str.upper()
        self.device_path = device_path
        self._running = False
        self._keys_pressed = set()
        self._target_keys = set(self.combo_str.split("+"))

    def run(self):
        """Thread-Hauptschleife für die Hotkey-Überwachung."""
        self._running = True
        logger.info(f"Starte Hotkey-Listener für Kombination: {self.combo_str}")

        # Versuche zuerst evdev (empfohlener Linux/Wayland Weg)
        if not self._run_evdev():
            logger.warning("evdev konnte nicht gestartet werden. Versuche Fallback auf pynput...")
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
            # Tastaturgeräte in /dev/input/event* suchen
            for path in glob.glob("/dev/input/event*"):
                try:
                    dev = evdev.InputDevice(path)
                    capabilities = dev.capabilities()
                    if ecodes.EV_KEY in capabilities:
                        # Prpfen ob Tastaturschlüssel vorhanden sind
                        keys = capabilities[ecodes.EV_KEY]
                        if ecodes.KEY_A in keys or ecodes.KEY_SPACE in keys:
                            devices.append(dev)
                except (PermissionError, OSError):
                    continue

        if not devices:
            logger.warning("Keine zugänglichen Tastaturgeräte unter /dev/input/ gefunden. (Rechte prüfen: 'sudo usermod -aG input $USER')")
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
                            # key_code kann ein String oder Liste von Strings sein
                            keys = [key_code] if isinstance(key_code, str) else key_code
                            
                            if event.value == 1:  # Key Down
                                for k in keys:
                                    self._keys_pressed.add(k.upper())
                                self._check_combination()

                            elif event.value == 0:  # Key Up
                                for k in keys:
                                    self._keys_pressed.discard(k.upper())
            except Exception as e:
                if self._running:
                    logger.debug(f"evdev Lesefehler: {e}")

        for dev in devices:
            try:
                dev.close()
            except Exception:
                pass
        return True

    def _run_pynput(self):
        """Fallback über pynput Listener."""
        try:
            from pynput import keyboard

            def on_press(key):
                try:
                    key_name = key.name.upper() if hasattr(key, 'name') else str(key).upper()
                    key_str = f"KEY_{key_name}" if not key_name.startswith("KEY_") else key_name
                    self._keys_pressed.add(key_str)
                    self._check_combination()
                except Exception:
                    pass

            def on_release(key):
                try:
                    key_name = key.name.upper() if hasattr(key, 'name') else str(key).upper()
                    key_str = f"KEY_{key_name}" if not key_name.startswith("KEY_") else key_name
                    self._keys_pressed.discard(key_str)
                except Exception:
                    pass

            with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
                while self._running and listener.running:
                    self.msleep(100)
                listener.stop()

        except Exception as e:
            logger.error(f"Fehler beim pynput Hotkey-Listener: {e}")

    def _check_combination(self):
        """Prüft ob alle Tasten der Zielkombination aktuell gedrückt sind."""
        if self._target_keys.issubset(self._keys_pressed):
            logger.info(f"Hotkey getriggert: {self.combo_str}")
            self.hotkey_pressed.emit()
            # Zurücksetzen um Mehrfach-Auslösungen bei gedrückter Taste zu vermeiden
            self._keys_pressed.clear()
