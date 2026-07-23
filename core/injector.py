import subprocess
import shutil
import logging
import time
from PySide6.QtGui import QGuiApplication

logger = logging.getLogger("WayVox.Injector")

class TextInjector:
    """Modul zur automatischen Textinjektion in das aktive Fenster unter Wayland (KDE Plasma 6)."""

    def __init__(self, method: str = "wtype", paste_delay_ms: int = 50, fallback_to_clipboard: bool = True):
        self.method = method.lower()
        self.paste_delay_ms = paste_delay_ms
        self.fallback_to_clipboard = fallback_to_clipboard

    def inject_text(self, text: str) -> bool:
        """Fügt den transkribierten Text in das aktive Fenster ein."""
        if not text:
            logger.info("Kein Text zum Einfügen vorhanden.")
            return False

        logger.info(f"Füge Text via '{self.method}' ein ({len(text)} Zeichen)...")
        time.sleep(self.paste_delay_ms / 1000.0)

        success = False
        if self.method == "wtype":
            success = self._inject_wtype(text)
        elif self.method == "ydotool":
            success = self._inject_ydotool(text)
        elif self.method == "clipboard":
            success = self._inject_clipboard(text)
        else:
            logger.warning(f"Unbekannte Injektionsmethode: {self.method}. Nutze wtype Fallback.")
            success = self._inject_wtype(text)

        if not success and self.fallback_to_clipboard and self.method != "clipboard":
            logger.warning("Primäre Injektionsmethode fehlgeschlagen. Versuche Clipboard-Fallback...")
            success = self._inject_clipboard(text)

        return success

    def _inject_wtype(self, text: str) -> bool:
        """Nutzt native Wayland Virtual Keyboard Protokoll via 'wtype'."""
        if not shutil.which("wtype"):
            logger.error("'wtype' nicht im PATH gefunden. Bitte mit 'sudo pacman -S wtype' installieren.")
            return False

        try:
            # wtype unterstützt '--' um Optionen von Text zu trennen
            result = subprocess.run(["wtype", "--", text], capture_output=True, text=True, check=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Fehler bei wtype Injektion: {e}")
            return False

    def _inject_ydotool(self, text: str) -> bool:
        """Nutzt uinput Daemon via 'ydotool'."""
        if not shutil.which("ydotool"):
            logger.error("'ydotool' nicht im PATH gefunden. Bitte installieren und 'ydotoold' starten.")
            return False

        try:
            result = subprocess.run(["ydotool", "type", "--", text], capture_output=True, text=True, check=True)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Fehler bei ydotool Injektion: {e}")
            return False

    def _inject_clipboard(self, text: str) -> bool:
        """Kopiert den Text in die Wayland-Zwischenablage und simuliert Strg+V."""
        try:
            # Option 1: wl-copy nutzen falls verfügbar
            if shutil.which("wl-copy"):
                subprocess.run(["wl-copy", text], check=True)
            else:
                # Option 2: Qt Clipboard
                clipboard = QGuiApplication.clipboard()
                if clipboard:
                    clipboard.setText(text)

            time.sleep(0.05)

            # Tastenkombination Strg+V zum Einfügen senden
            if shutil.which("wtype"):
                subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"], check=True)
                return True
            elif shutil.which("ydotool"):
                # ydotool key combo für Ctrl+V (29:1 = Ctrl Down, 47:1 = V Down, 47:0 = V Up, 29:0 = Ctrl Up)
                subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], check=True)
                return True
            else:
                logger.warning("Text wurde in die Zwischenablage kopiert, aber Strg+V konnte nicht simuliert werden.")
                return True

        except Exception as e:
            logger.error(f"Fehler bei Clipboard-Injektion: {e}")
            return False
