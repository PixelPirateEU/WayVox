import subprocess
import shutil
import logging
import time
from PySide6.QtGui import QGuiApplication

logger = logging.getLogger("WayVox.Injector")

class TextInjector:
    """Modul zur automatischen Textinjektion in das aktive Fenster unter Wayland / X11."""

    def __init__(self, method: str = "ydotool", paste_delay_ms: int = 50, fallback_to_clipboard: bool = True):
        self.method = method.lower()
        self.paste_delay_ms = paste_delay_ms
        self.fallback_to_clipboard = fallback_to_clipboard
        self._uinput_device = None
        if self.method != "clipboard":
            self._init_uinput()

    def _init_uinput(self):
        """Initialisiert ein virtuelles Tastaturgerät beim Start der Anwendung."""
        try:
            import evdev
            from evdev import ecodes
            capabilities = {
                ecodes.EV_KEY: [ecodes.KEY_LEFTCTRL, ecodes.KEY_V]
            }
            self._uinput_device = evdev.UInput(events=capabilities, name="WayVox-Virtual-Keyboard")
            logger.info("Dauerhaftes uinput-Tastaturgerät für WayVox erfolgreich registriert.")
        except Exception as e:
            logger.warning(f"Konnte uinput-Tastaturgerät nicht registrieren ({e}).")
            self._uinput_device = None

    def _copy_to_clipboard(self, text: str):
        """Kopiert den Text zuverlässig in die Qt- und Wayland-Zwischenablage."""
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        if shutil.which("wl-copy"):
            try:
                subprocess.run(["wl-copy"], input=text.encode("utf-8"), capture_output=True, timeout=0.5)
            except Exception:
                pass

    def inject_text(self, text: str) -> bool:
        """Fügt den transkribierten Text ein oder legt ihn in der Zwischenablage ab."""
        if not text:
            logger.info("Kein Text zum Einfügen vorhanden.")
            return False

        logger.info(f"Füge Text ein ({len(text)} Zeichen)...")
        time.sleep(self.paste_delay_ms / 1000.0)

        # 1. Text immer in die System-Zwischenablage legen
        self._copy_to_clipboard(text)

        # 2. Falls Methode 'clipboard' ist, fertig (0 Popups, 0 Mehrfachauslösung)
        if self.method == "clipboard":
            logger.info("Text erfolgreich in Zwischenablage kopiert (bereit für Strg+V).")
            return True

        # 3. Automatische Tastatursimulation via uinput (1x Strg+V)
        if self._inject_evdev_uinput():
            return True

        # 4. Fallback ydotool CLI
        if self._inject_ydotool():
            return True

        return True

    def _inject_evdev_uinput(self) -> bool:
        """Nutzt das permanente uinput Tastaturgerät für 1x Strg+V."""
        if not self._uinput_device:
            return False

        try:
            import evdev
            from evdev import ecodes

            time.sleep(0.05)
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

    def _inject_ydotool(self) -> bool:
        """Fallback via 'ydotool' CLI."""
        if not shutil.which("ydotool"):
            return False

        try:
            time.sleep(0.05)
            res = subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], capture_output=True, timeout=2.0)
            return res.returncode == 0
        except Exception:
            return False

    def close(self):
        """Schließt das virtuelle uinput-Gerät sauber beim Beenden."""
        if self._uinput_device:
            try:
                self._uinput_device.close()
                self._uinput_device = None
            except Exception:
                pass
