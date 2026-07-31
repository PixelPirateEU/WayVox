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

        logger.info(f"Füge Text ein ({len(text)} Zeichen)...")
        time.sleep(self.paste_delay_ms / 1000.0)

        # 1. Falls ydotool explizit als Methode gewählt ist
        if self.method == "ydotool":
            if self._inject_ydotool(text):
                return True
            elif self.fallback_to_clipboard:
                logger.info("ydotool fehlgeschlagen. Versuche Zwischenablage-Fallback...")

        # 2. Falls wtype gewählt ist und unterstützt wird
        elif self.method == "wtype" and self._wtype_supported:
            if self._inject_wtype(text):
                return True

        # 3. Standard- / Fallback-Methode: Zwischenablage + Strg+V
        return self._inject_clipboard(text)

    def _inject_ydotool(self, text: str) -> bool:
        """Nutzt uinput Kernel Daemon via 'ydotool' mit 100% UTF-8 QWERTZ-Unterstützung (Clipboard + Strg+V)."""
        if not shutil.which("ydotool"):
            logger.info("ydotool ist nicht im PATH installiert.")
            return False

        try:
            logger.info("Füge Text via ydotool (Clipboard + Strg+V) für 100% QWERTZ-Darstellung ein...")
            # 1. Text in Zwischenablage setzen (Qt Clipboard & wl-copy)
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            if shutil.which("wl-copy"):
                try:
                    subprocess.run(["wl-copy"], input=text.encode("utf-8"), capture_output=True, timeout=1.0)
                except Exception:
                    pass

            time.sleep(0.05)
            # 2. Strg+V via ydotool key auslösen (-d 12 = 12ms Verzögerung zwischen Events verhindert Mehrfachauslösung in KWin/Wayland)
            res = subprocess.run(["ydotool", "key", "-d", "12", "29:1", "47:1", "47:0", "29:0"], capture_output=True, timeout=2.0)
            if res.returncode == 0:
                logger.info("Text erfolgreich via ydotool (Strg+V) eingefügt!")
                return True
            else:
                err = res.stderr.strip() or res.stdout.strip()
                logger.info(f"ydotool key Rückmeldung: {err}")
                return False
        except Exception as e:
            logger.info(f"ydotool Ausführung fehlgeschlagen ({e}).")
            return False

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
                logger.info(f"wtype vom Compositor nicht unterstützt ({err_msg}). Verwende Zwischenablage (Strg+V).")
                self._wtype_supported = False
                return False
        except Exception as e:
            logger.info(f"wtype nicht verfügbar ({e}). Verwende Zwischenablage (Strg+V).")
            self._wtype_supported = False
            return False

    def _inject_clipboard(self, text: str) -> bool:
        """Kopiert den Text in die Zwischenablage (Qt / wl-copy) und simuliert sicher Strg+V."""
        copied = False
        try:
            # 1. Text in die Qt-Zwischenablage setzen
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                copied = True

            # 2. Zusätzlich per wl-copy via Stdin absichern
            if shutil.which("wl-copy"):
                try:
                    subprocess.run(["wl-copy"], input=text.encode("utf-8"), capture_output=True, timeout=1.0)
                    copied = True
                except Exception:
                    pass

            if not copied:
                logger.error("Konnte Text nicht in die Zwischenablage kopieren.")
                return False

            time.sleep(0.05)

            # 3. Tastenkombination Strg+V sicher simulieren (mit try...finally gegen Hängenbleiben)
            pasted = False

            # Versuch A: pynput Keyboard Controller
            try:
                from pynput.keyboard import Controller, Key
                kb = Controller()
                try:
                    kb.press(Key.ctrl)
                    time.sleep(0.015)
                    kb.press('v')
                    time.sleep(0.03)
                    kb.release('v')
                    time.sleep(0.015)
                finally:
                    kb.release(Key.ctrl)
                pasted = True
                logger.info("Strg+V erfolgreich via pynput simuliert.")
            except Exception as ex_pynput:
                logger.debug(f"pynput Strg+V Simulation fehlgeschlagen: {ex_pynput}")

            # Versuch B: wtype (falls unterstützt)
            if not pasted and self._wtype_supported and shutil.which("wtype"):
                try:
                    res = subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"], capture_output=True, timeout=1.0)
                    pasted = (res.returncode == 0)
                except Exception:
                    pass

            # Versuch C: xdotool (falls Xwayland / X11)
            if not pasted and shutil.which("xdotool"):
                try:
                    res = subprocess.run(["xdotool", "key", "ctrl+v"], capture_output=True, timeout=1.0)
                    pasted = (res.returncode == 0)
                except Exception:
                    pass

            if pasted:
                logger.info("Text via Zwischenablage (Strg+V) erfolgreich eingefügt!")
                return True
            else:
                logger.info("Text wurde in die Zwischenablage kopiert. (Strg+V manuell möglich).")
                return True

        except Exception as e:
            logger.error(f"Fehler bei Clipboard-Injektion: {e}")
            return False
