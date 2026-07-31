import re
import numpy as np
import logging
import time
from PySide6.QtCore import QObject, Signal, Slot, QThread

logger = logging.getLogger("WayVox.Transcriber")


def _deduplicate_text(text: str) -> str:
    """Entfernt versehentliche Wort-, Satzdoppelungen und Whisper-Halluzinationen am Textende."""
    if not text:
        return text

    hallucinations = [
        "vielen dank für's zuschauen",
        "vielen dank fürs zuschauen",
        "vielen dank für das zuschauen",
        "vielen dank fürs zusehen",
        "vielen dank für eure aufmerksamkeit",
        "vielen dank.",
        "vielen dank",
        "untertitel der amara.org",
        "untertitel von",
        "subscribe",
        "abonnieren"
    ]

    # Satzenden ohne Leerzeichen trennen (z. B. "einkaufen.Heidi" -> "einkaufen. Heidi")
    text = re.sub(r'(?<=[.!?])(?=[A-Za-zÄÖÜäöüß])', ' ', text)

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s.strip()]
    filtered_sentences = []
    for s in sentences:
        s_lower = s.lower().strip()
        if any(h in s_lower for h in hallucinations) and len(s_lower) < 45:
            continue
        filtered_sentences.append(s)

    unique_sentences = []
    for s in filtered_sentences:
        if not unique_sentences or s != unique_sentences[-1]:
            unique_sentences.append(s)

    result = " ".join(unique_sentences).strip()

    # Wortgruppen-Deduplizierung bei exakter Wiederholung
    words = result.split()
    n = len(words)
    if n >= 4 and n % 2 == 0:
        half = n // 2
        if words[:half] == words[half:]:
            result = " ".join(words[:half])

    return result

class WhisperTranscriberWorker(QObject):
    """Arbeitsthread für die CUDA-beschleunigte lokale Sprachverarbeitung via faster-whisper."""

    model_loaded = Signal()
    transcription_started = Signal()
    transcription_finished = Signal(str)
    transcription_error = Signal(str)

    def __init__(self, model_name: str = "large-v3", device: str = "cuda", 
                 compute_type: str = "float16", language: str = "de", 
                 beam_size: int = 5, initial_prompt: str = None):
        super().__init__()
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.initial_prompt = initial_prompt
        self.model = None

    @Slot()
    def load_model(self):
        """Lädt das faster-whisper Modell (mit CUDA-Unterstützung und CPU-Fallback)."""
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        try:
            logger.info(f"Lade Whisper-Modell '{self.model_name}' auf Gerät '{self.device}' ({self.compute_type})...")
            start_time = time.time()
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )
            load_time = time.time() - start_time
            logger.info(f"Whisper-Modell '{self.model_name}' erfolgreich in {load_time:.2f}s geladen.")
            self.model_loaded.emit()

        except Exception as e:
            if self.device != "cpu":
                logger.warning(f"CUDA-Initialisierung fehlgeschlagen ({e}). Starte Fallback auf CPU (int8)...")
                try:
                    self.device = "cpu"
                    self.compute_type = "int8"
                    start_time = time.time()
                    self.model = WhisperModel(
                        self.model_name,
                        device="cpu",
                        compute_type="int8"
                    )
                    load_time = time.time() - start_time
                    logger.info(f"Whisper-Modell im CPU-Fallback-Modus in {load_time:.2f}s geladen.")
                    self.model_loaded.emit()
                    return
                except Exception as ex_cpu:
                    e = ex_cpu

            error_msg = f"Fehler beim Laden des Whisper-Modells: {e}"
            logger.error(error_msg)
            self.transcription_error.emit(error_msg)

    @Slot(np.ndarray)
    def transcribe(self, audio_data: np.ndarray):
        """Transkribiert das übergebene NumPy Audio-Array (float32, 16kHz)."""
        if audio_data is None or len(audio_data) == 0:
            logger.warning("Keine Audiodaten zur Transkription empfangen.")
            self.transcription_finished.emit("")
            return

        self.transcription_started.emit()

        try:
            if self.model is None:
                self.load_model()
                if self.model is None:
                    raise RuntimeError("Whisper-Modell ist nicht initialisiert.")

            start_time = time.time()
            duration_sec = len(audio_data) / 16000.0
            if duration_sec < 0.5:
                logger.warning("Audioaufnahme ist zu kurz (< 0.5s). Transkription übersprungen.")
                self.transcription_finished.emit("")
                return

            logger.info(f"Starte Transkription auf '{self.device}' (Länge: {duration_sec:.2f}s)...")
            
            try:
                segments, info = self.model.transcribe(
                    audio_data,
                    beam_size=self.beam_size,
                    language=self.language if self.language else None,
                    initial_prompt=self.initial_prompt,
                    condition_on_previous_text=False,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                    repetition_penalty=1.2,
                    no_repeat_ngram_size=3,
                    hallucination_silence_threshold=1.5
                )
                text_segments = [segment.text.strip() for segment in segments]
            except Exception as e_cuda:
                if self.device != "cpu":
                    logger.warning(f"Fehler bei CUDA-Verarbeitung ({e_cuda}). Wechsle auf CPU...")
                    self.device = "cpu"
                    self.compute_type = "int8"
                    from faster_whisper import WhisperModel
                    self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                    segments, info = self.model.transcribe(
                        audio_data,
                        beam_size=self.beam_size,
                        language=self.language if self.language else None,
                        initial_prompt=self.initial_prompt,
                        condition_on_previous_text=False,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500),
                        repetition_penalty=1.2,
                        no_repeat_ngram_size=3,
                        hallucination_silence_threshold=1.5
                    )
                    text_segments = [segment.text.strip() for segment in segments]
                else:
                    raise e_cuda

            full_text = " ".join(text_segments).strip()
            full_text = _deduplicate_text(full_text)
            elapsed = time.time() - start_time
            logger.info(f"Transkription abgeschlossen in {elapsed:.2f}s! Text: '{full_text}'")
            
            self.transcription_finished.emit(full_text)

        except Exception as e:
            error_msg = f"Fehler bei der Transkription: {e}"
            logger.error(error_msg)
            self.transcription_error.emit(error_msg)
