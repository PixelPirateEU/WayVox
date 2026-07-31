#!/usr/bin/env python3
"""
WayVox - 100% lokale, datenschutzkonforme Voice-to-Text Anwendung für CachyOS / Wayland mit KDE Plasma 6.
CUDA-beschleunigte Transkription mit faster-whisper (NVIDIA RTX 5070 Ti).
"""

import sys
import os
import signal
import logging

# Auto-switch to virtual environment Python if available
script_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(script_dir, "venv", "bin", "python3")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

# Dynamic LD_LIBRARY_PATH update for CUDA / cuBLAS libraries in site-packages & system paths
try:
    import site
    site_pkgs = site.getsitepackages()
    ld_paths = [
        "/opt/cuda/lib64",
        "/opt/cuda/targets/x86_64-linux/lib",
        "/usr/lib",
    ]
    for sp in site_pkgs:
        ld_paths.extend([
            os.path.join(sp, "nvidia", "cublas", "lib"),
            os.path.join(sp, "nvidia", "cudnn", "lib"),
            os.path.join(sp, "nvidia", "cuda_runtime", "lib"),
        ])
    existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join([p for p in ld_paths if os.path.exists(p)]) + (f":{existing_ld}" if existing_ld else "")
except Exception:
    pass

from PySide6.QtCore import QObject, QThread, Slot, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtGui import QIcon

from utils.config import ConfigManager
from utils.audio_feedback import AudioFeedback
from ui.circle_overlay import CircleOverlay, AppState
from ui.hotkey_dialog import HotkeyDialog, get_display_name_for_combo
from core.recorder import AudioRecorder
from core.transcriber import WhisperTranscriberWorker
from core.injector import TextInjector
from core.hotkey_listener import GlobalHotkeyListener

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WayVox.Main")

class WayVoxApp(QObject):
    """Hauptsteuerungsklasse der WayVox Anwendung."""

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        
        # 1. Konfiguration laden
        self.config = ConfigManager("config.json")

        # 2. Audio-Feedback (Synthetischer Sound)
        audio_cfg = self.config.get("audio")
        self.feedback = AudioFeedback(
            enabled=audio_cfg.get("feedback_sounds", True),
            volume=audio_cfg.get("feedback_volume", 0.3),
            sample_rate=audio_cfg.get("sample_rate", 16000)
        )

        # 3. UI Circle Overlay initialisieren
        ui_cfg = self.config.get("ui")
        self.overlay = CircleOverlay(
            size=ui_cfg.get("size", 120),
            border_width=ui_cfg.get("border_width", 6),
            pos_x=ui_cfg.get("position_x", 100),
            pos_y=ui_cfg.get("position_y", 100),
            show_label=ui_cfg.get("show_label", True)
        )
        self.overlay.show()

        # 4. Audio-Recorder initialisieren
        self.recorder = AudioRecorder(
            sample_rate=audio_cfg.get("sample_rate", 16000),
            channels=audio_cfg.get("channels", 1),
            device_index=audio_cfg.get("device_index")
        )

        # 5. Text-Injector initialisieren
        inj_cfg = self.config.get("injection")
        self.injector = TextInjector(
            method=inj_cfg.get("method", "clipboard"),
            paste_delay_ms=inj_cfg.get("paste_delay_ms", 50),
            fallback_to_clipboard=inj_cfg.get("fallback_to_clipboard", True)
        )

        # 6. Faster-Whisper Transkribier-Arbeitsthread erstellen
        model_cfg = self.config.get("model")
        self.transcriber_thread = QThread()
        self.transcriber_worker = WhisperTranscriberWorker(
            model_name=model_cfg.get("name", "large-v3"),
            device=model_cfg.get("device", "cuda"),
            compute_type=model_cfg.get("compute_type", "float16"),
            language=model_cfg.get("language", "de"),
            beam_size=model_cfg.get("beam_size", 5),
            initial_prompt=model_cfg.get("initial_prompt")
        )
        self.transcriber_worker.moveToThread(self.transcriber_thread)

        # 7. Globalen Hotkey-Listener initialisieren (evdev/pynput Thread)
        hotkey_cfg = self.config.get("hotkey")
        current_hotkey = hotkey_cfg.get("combination", "KEY_F12")
        self.overlay.set_hotkey_tooltip(get_display_name_for_combo(current_hotkey))

        self.hotkey_listener = None
        if hotkey_cfg.get("enabled", True):
            self.hotkey_listener = GlobalHotkeyListener(
                combo_str=current_hotkey,
                device_path=hotkey_cfg.get("device_path")
            )

        # 8. Signal-Slot Verbindungen aufbauen
        self._connect_signals()

        # 9. Threads starten
        self.transcriber_thread.start()
        # Vorab Modell auf GPU laden
        self.transcriber_worker.load_model()

        if self.hotkey_listener:
            self.hotkey_listener.start()

        logger.info("WayVox erfolgreich gestartet! Bereit für Spracheingabe.")

    def _connect_signals(self):
        """Verbindet alle Qt-Signale und Slots zwischen UI, Recorder, Transcriber & Injector."""
        # UI Klick & Hotkey -> Aufnahme Umschalten
        self.overlay.clicked.connect(self.toggle_recording)
        self.overlay.quit_requested.connect(self.quit_app)
        self.overlay.hotkey_change_requested.connect(self.open_hotkey_dialog)

        if self.hotkey_listener:
            self.hotkey_listener.hotkey_pressed.connect(self.toggle_recording)

        # Audio Recorder Signale
        self.recorder.recording_started.connect(self._on_recording_started)
        self.recorder.recording_stopped.connect(self._on_recording_stopped)
        self.recorder.recording_error.connect(self._on_error)

        # Transcriber Signale
        self.transcriber_worker.transcription_started.connect(self._on_transcription_started)
        self.transcriber_worker.transcription_finished.connect(self._on_transcription_finished)
        self.transcriber_worker.transcription_error.connect(self._on_error)

    @Slot()
    def toggle_recording(self):
        """Schaltet die Aufnahme an oder aus."""
        if self.overlay.current_state in [AppState.TRANSCRIBING, AppState.SUCCESS]:
            # Während Transkription oder Bestätigung Klicks ignorieren
            return

        if not self.recorder.is_recording():
            self.feedback.play_start()
            self.recorder.start_recording()
        else:
            self.feedback.play_stop()
            self.recorder.stop_recording()

    @Slot()
    def _on_recording_started(self):
        self.overlay.set_state(AppState.LISTENING)

    @Slot(object)
    def _on_recording_stopped(self, audio_data):
        if audio_data is not None and len(audio_data) > 0:
            self.overlay.set_state(AppState.TRANSCRIBING)
            # Async Aufruf im Worker Thread
            self.transcriber_worker.transcribe(audio_data)
        else:
            self.overlay.set_state(AppState.IDLE)

    @Slot()
    def _on_transcription_started(self):
        self.overlay.set_state(AppState.TRANSCRIBING)

    @Slot(str)
    def _on_transcription_finished(self, text: str):
        if text:
            logger.info(f"Transkription erhalten: '{text}'")
            success = self.injector.inject_text(text)
            if success:
                self.feedback.play_success()
                self.overlay.set_state(AppState.SUCCESS)
            else:
                self.overlay.set_state(AppState.ERROR)
        else:
            logger.info("Leere Transkription. Kehre zu Idle zurück.")
            self.overlay.set_state(AppState.IDLE)

    @Slot(str)
    def _on_error(self, error_message: str):
        logger.error(f"App-Fehler aufgetreten: {error_message}")
        self.feedback.play_error()
        self.overlay.set_state(AppState.ERROR)

    @Slot()
    def open_hotkey_dialog(self):
        """Öffnet das Fenster zur Hotkey-Anpassung."""
        hotkey_cfg = self.config.get("hotkey")
        current_combo = hotkey_cfg.get("combination", "KEY_F12")

        dialog = HotkeyDialog(self.overlay, current_combo=current_combo)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_combo = dialog.get_selected_hotkey()
            if new_combo:
                self.update_hotkey(new_combo)

    def update_hotkey(self, new_combo: str):
        """Aktualisiert die Hotkey-Konfiguration und wendet sie sofort an."""
        logger.info(f"Ändere Hotkey auf: {new_combo}")

        # 1. Config aktualisieren & speichern
        if "hotkey" not in self.config.config_data:
            self.config.config_data["hotkey"] = {}
        self.config.config_data["hotkey"]["combination"] = new_combo
        self.config.save_config()

        # 2. Hotkey Listener aktualisieren
        if self.hotkey_listener:
            self.hotkey_listener.update_combination(new_combo)
        else:
            self.hotkey_listener = GlobalHotkeyListener(combo_str=new_combo)
            self.hotkey_listener.hotkey_pressed.connect(self.toggle_recording)
            self.hotkey_listener.start()

        # 3. Tooltip anpassen
        display_name = get_display_name_for_combo(new_combo)
        self.overlay.set_hotkey_tooltip(display_name)

    def quit_app(self):
        """Beendet die Anwendung sauber."""
        logger.info("Beende WayVox...")
        if self.recorder.is_recording():
            self.recorder.stop_recording()

        if self.hotkey_listener:
            self.hotkey_listener.stop()

        if self.injector:
            self.injector.close()

        if self.transcriber_thread.isRunning():
            self.transcriber_thread.quit()
            self.transcriber_thread.wait(2000)

        self.app.quit()


def main():
    # Signal handling für SIGINT (Strg+C im Terminal)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Einzel-Instanz-Sperre gegen mehrfache Hintergrund-Prozesse
    lock_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wayvox.lock")
    lock_file = QLockFile(lock_file_path)
    if not lock_file.tryLock(100):
        print("[WayVox] Eine Instanz von WayVox läuft bereits im Hintergrund! Beende doppelte Instanz.")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("WayVox")
    app.setOrganizationName("WayVox")
    app.setDesktopFileName("WayVox")

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "WayVox.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    wayvox = WayVoxApp(app)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
