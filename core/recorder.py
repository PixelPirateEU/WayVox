import sounddevice as sd
import numpy as np
import logging
from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger("WayVox.Recorder")

class AudioRecorder(QObject):
    """Audio-Recorder für Mikrofonaufnahme unter Nutzung von sounddevice und NumPy."""

    recording_started = Signal()
    recording_stopped = Signal(np.ndarray)
    recording_error = Signal(str)

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index: int = None):
        super().__init__()
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self._is_recording = False
        self._audio_chunks = []
        self._stream = None

    def start_recording(self):
        """Startet die Aufzeichnung vom Mikrofon."""
        if self._is_recording:
            return

        self._audio_chunks.clear()
        self._is_recording = True

        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio Stream Status Warning: {status}")
            if self._is_recording:
                # Monokanal in 1D Float32 Array konvertieren
                self._audio_chunks.append(indata.copy())

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                device=self.device_index,
                dtype="float32",
                callback=audio_callback
            )
            self._stream.start()
            logger.info("Audioaufnahme gestartet.")
            self.recording_started.emit()
        except Exception as e:
            self._is_recording = False
            error_msg = f"Fehler beim Starten der Audioaufnahme: {e}"
            logger.error(error_msg)
            self.recording_error.emit(error_msg)

    def stop_recording(self):
        """Stoppt die Aufnahme und sendet die aufgenommenen Audiodaten als NumPy Array."""
        if not self._is_recording:
            return

        self._is_recording = False
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            
            logger.info("Audioaufnahme gestoppt.")
            
            if self._audio_chunks:
                # Alle Audioschnipsel zu einem durchgehenden 1D-Array zusammenfügen
                full_audio = np.concatenate(self._audio_chunks, axis=0).flatten()
                self.recording_stopped.emit(full_audio)
            else:
                logger.warning("Keine Audiodaten aufgenommen.")
                self.recording_stopped.emit(np.array([], dtype=np.float32))

        except Exception as e:
            error_msg = f"Fehler beim Stoppen der Audioaufnahme: {e}"
            logger.error(error_msg)
            self.recording_error.emit(error_msg)

    def is_recording(self) -> bool:
        return self._is_recording
