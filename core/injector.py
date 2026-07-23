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

    def inject_text(self, text: str) -> bool:
        """Fügt den transkribierten Text in das aktive Fenster ein."""
        if not text:
            logger.info("Kein Text zum Einfügen vorhanden.")
            return False

        logger.info(f"Füge Text via '{self.method}' ein ({len(text)} Zeichen)...")
        time.sleep(self.paste_delay_ms / 1000.0)

        success = False
        if self.method == "wtype" and self._wtype_supported:
            success = self._inject_wtype(text)

        if not success and shutil.which("ydotool"):
            logger.info("Versuche Injektion via ydotool...")
            success = self._inject_ydotool(text)

        if not success and self.fallback_to_clipboard:
            logger.warning("Direkte Tastatur-Injektion fehlgeschlagen. Versuche Zwischenablage-Fallback (Strg+V)...")
            success = self._inject_clipboard(text)

        return success

    def _inject_wtype(self, text: str) -> bool:
        """Nutzt native Wayland Virtual Keyboard Protokoll via 'wtype'."""
        if not shutil.which("wtype"):
            self._wtype_supported = False
            return False

        try:
            result = subprocess.run(["wtype", "--", text], capture_output=True, text=True, timeout=1.5)
            if result.returncode == 0:
                return True
            else:
                err_msg = result.stderr.strip() or result.stdout.strip()
                logger.warning(f"wtype vom Compositor nicht unterstützt ({err_msg}). Deaktiviere wtype.")
                self._wtype_supported = False
                return False
        except Exception as e:
            logger.warning(f"Fehler bei wtype Injektion: {e}")
            self._wtype_supported = False
            return False

    def _inject_ydotool(self, text: str) -> bool:
        """Nutzt uinput Daemon via 'ydotool'."""
        if not shutil.which("ydotool"):
            return False

        try:
            result = subprocess.run(["ydotool", "type", "--", text], capture_output=True, text=True, timeout=1.5)
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Fehler bei ydotool Injektion (Ist ydotoold gestartet?): {e}")
            return False

    def _inject_clipboard(self, text: str) -> bool:
        """Kopiert den Text in die Zwischenablage (wl-copy / Qt Clipboard) und simuliert Strg+V."""
        copied = False
        try:
            if shutil.which("wl-copy"):
                res = subprocess.run(["wl-copy", text], capture_output=True, timeout=1.5)
                copied = (res.returncode == 0)
            
            if not copied:
                clipboard = QGuiApplication.clipboard()
                if clipboard:
                    clipboard.setText(text)
                    copied = True

            time.sleep(0.08)

            # Tastenkombination Strg+V versuchen
            pasted = False
            if self._wtype_supported and shutil.which("wtype"):
                try:
                    res = subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"], capture_output=True, timeout=1.5)
                    pasted = (res.returncode == 0)
                    if not pasted:
                        self._wtype_supported = False
                except Exception:
                    self._wtype_supported = False

            if not pasted:
                try:
                    from pynput.keyboard import Controller, Key
                    kb = Controller()
                    with kb.pressed(Key.ctrl):
                        kb.press('v')
                        kb.release('v')
                    pasted = True
                    logger.info("Strg+V Tasteneingabe via pynput simuliert.")
                except Exception as ex_pynput:
                    logger.debug(f"pynput Strg+V fehlgeschlagen: {ex_pynput}")

            if not pasted and shutil.which("ydotool"):
                try:
                    res = subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], capture_output=True, timeout=1.5)
                    pasted = (res.returncode == 0)
                except Exception:
                    pass

            if not pasted and shutil.which("xdotool"):
                try:
                    res = subprocess.run(["xdotool", "key", "ctrl+v"], capture_output=True, timeout=1.5)
                    pasted = (res.returncode == 0)
                except Exception:
                    pass

            if pasted:
                logger.info("Text via Zwischenablage (Strg+V) erfolgreich eingefügt.")
                return True
            elif copied:
                logger.info("Text wurde erfolgreich in die Zwischenablage kopiert! (Strg+V manuell möglich).")
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"Fehler bei Clipboard-Injektion: {e}")
            return False
