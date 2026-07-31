import subprocess
import shutil
import logging
import time
from PySide6.QtGui import QGuiApplication

logger = logging.getLogger("WayVox.Injector")

class TextInjector:
    """Modul zur automatischen Textinjektion in das aktive Fenster unter Wayland / X11."""

    def __init__(self, method: str = "wtype", paste_delay_ms: int = 50, fallback_to_clipboard: bool = True):
        self.method = method.lower()
        self.paste_delay_ms = paste_delay_ms
        self.fallback_to_clipboard = fallback_to_clipboard
        self._wtype_supported = True
        self._uinput_device = None
        self._init_uinput()

    def _init_uinput(self):
        """Initialisiert ein einziges, dauerhaftes virtuelles Tastaturgerät beim Start der Anwendung."""
        try:
            import evdev
            from evdev import ecodes
            capabilities = {
                ecodes.EV_KEY: [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]
            }
            self._uinput_device = evdev.UInput(events=capabilities, name="WayVox-Virtual-Keyboard")
            logger.info("Dauerhaftes uinput-Tastaturgerät für WayVox erfolgreich registriert.")
        except Exception as e:
            logger.warning(f"Konnte uinput-Tastaturgerät nicht registrieren ({e}). Verwende Fallbacks...")
            self._uinput_device = None

    def inject_text(self, text: str) -> bool:
        """Fügt den transkribierten Text in das aktive Fenster ein."""
        if not text:
            logger.info("Kein Text zum Einfügen vorhanden.")
            return False

        logger.info(f"Füge Text ein ({len(text)} Zeichen)...")
        time.sleep(self.paste_delay_ms / 1000.0)

        # 1. Hauptmethode: Direktes dauerhaftes uinput-Gerät (100% präzises 1x Strg+V ohne Hotplug-Loops)
        if self._inject_evdev_uinput(text):
            return True

        # 2. Falls uinput nicht verfügbar ist, versuche ydotool
        if self.method == "ydotool":
            if self._inject_ydotool(text):
                return True

        # 3. Fallback: Standard-Zwischenablage via pynput/xdotool
        return self._inject_clipboard(text)

    def _inject_evdev_uinput(self, text: str) -> bool:
        """Nutzt das permanente uinput Tastaturgerät für 1x Strg+V ohne Hotplug-Events."""
        if not self._uinput_device:
            return False

        try:
            import evdev
            from evdev import ecodes

            # 1. Text in die Qt-Zwischenablage setzen
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)

            time.sleep(0.05)

            # 2. Strg+V über das bestehende uinput-Gerät senden
            ui = self._uinput_device
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 1)
            ui.syn()
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 1)
            ui.syn()
            ui.write(ecodes.EV_KEY, ecodes.KEY_V, 0)
            ui.syn()
            ui.write(ecodes.EV_KEY, ecodes.KEY_LEFTCTRL, 0)
            ui.syn()

            logger.info("Text via uinput (1x Strg+V) erfolgreich eingefügt!")
            return True
        except Exception as e:
            logger.warning(f"uinput Injektion fehlgeschlagen: {e}")
            return False

    def close(self):
        """Schließt das virtuelle uinput-Gerät sauber beim Beenden."""
        if self._uinput_device:
            try:
                self._uinput_device.close()
                self._uinput_device = None
            except Exception:
                pass

    def _inject_ydotool(self, text: str) -> bool:
        """Fallback via 'ydotool'."""
        if not shutil.which("ydotool"):
            return False

        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            time.sleep(0.05)
            res = subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], capture_output=True, timeout=2.0)
            return res.returncode == 0
        except Exception:
            return False

    def _inject_clipboard(self, text: str) -> bool:
        """Kopiert den Text in die Zwischenablage und simuliert Strg+V."""
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            time.sleep(0.05)

            try:
                from pynput.keyboard import Controller, Key
                kb = Controller()
                kb.press(Key.ctrl)
                time.sleep(0.01)
                kb.press('v')
                time.sleep(0.02)
                kb.release('v')
                time.sleep(0.01)
                kb.release(Key.ctrl)
                logger.info("Strg+V erfolgreich via pynput simuliert.")
                return True
            except Exception:
                pass

            return True
        except Exception as e:
            logger.error(f"Fehler bei Clipboard-Injektion: {e}")
            return False
