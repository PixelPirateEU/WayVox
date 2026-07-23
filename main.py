#!/usr/bin/env python3
"""
WayVox - 100% lokale, datenschutzkonforme Voice-to-Text Anwendung für CachyOS / Wayland mit KDE Plasma 6.
CUDA-beschleunigte Transkription mit faster-whisper (NVIDIA RTX 5070 Ti).
"""

import sys
import os
import signal
import logging
from PySide6.QtCore import QApplication, QThread, Slot
from PySide6.QtWidgets import QMessageBox

from utils.config import ConfigManager
from utils.audio_feedback import AudioFeedback
from ui.circle_overlay import CircleOverlay, AppState
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

class WayVoxApp:
    """Hauptsteuerungsklasse der WayVox Anwendung."""

    def __init__(self, app: QApplication):
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
            method=inj_cfg.get("method", "wtype"),
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
        self.hotkey_listener = None
        if hotkey_cfg.get("enabled", True):
            self.hotkey_listener = GlobalHotkeyListener(
                combo_str=hotkey_cfg.get("combination", "KEY_LEFTALT+KEY_SPACE"),
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

    def quit_app(self):
        """Beendet die Anwendung sauber."""
        logger.info("Beende WayVox...")
        if self.recorder.is_recording():
            self.recorder.stop_recording()

        if self.hotkey_listener:
            self.hotkey_listener.stop()

        if self.transcriber_thread.isRunning():
            self.transcriber_thread.quit()
            self.transcriber_thread.wait(2000)

        self.app.quit()


def main():
    # Signal handling für SIGINT (Strg+C im Terminal)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("WayVox")
    app.setOrganizationName("WayVox")

    wayvox = WayVoxApp(app)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
