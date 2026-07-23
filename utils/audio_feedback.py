import numpy as np
import sounddevice as sd
import logging

logger = logging.getLogger("WayVox.AudioFeedback")

class AudioFeedback:
    """Erzeugt synthetische Töne (Sinuswellen) für Start, Stopp und Fehler-Feedback."""

    def __init__(self, enabled: bool = True, volume: float = 0.3, sample_rate: int = 44100):
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume))
        self.sample_rate = sample_rate

    def _play_tone(self, frequencies: list, duration_ms: float = 120):
        """Spielt eine Frequenzfolge oder Kombination synchron/asynchron ab."""
        if not self.enabled:
            return

        try:
            t = np.linspace(0, duration_ms / 1000.0, int(self.sample_rate * (duration_ms / 1000.0)), False)
            signal = np.zeros_like(t)
            
            for freq in frequencies:
                signal += np.sin(2 * np.pi * freq * t)
            
            # Smooth Envelope (Fade In / Fade Out um Knacken zu vermeiden)
            fade_samples = int(self.sample_rate * 0.01)  # 10ms fade
            if len(signal) > 2 * fade_samples:
                fade_in = np.linspace(0, 1, fade_samples)
                fade_out = np.linspace(1, 0, fade_samples)
                signal[:fade_samples] *= fade_in
                signal[-fade_samples:] *= fade_out

            # Lautstärke skalieren
            audio = (signal / len(frequencies) * self.volume).astype(np.float32)
            
            # Asynchrones Abspielen über sounddevice
            sd.play(audio, samplerate=self.sample_rate, blocking=False)
        except Exception as e:
            logger.warning(f"Audio-Feedback konnte nicht abgespielt werden: {e}")

    def play_start(self):
        """Klarer, aufsteigender Signalton beim Start der Aufnahme (880 Hz / 1320 Hz)."""
        self._play_tone([880.0, 1320.0], duration_ms=100)

    def play_stop(self):
        """Klarer, absteigender Signalton beim Beenden der Aufnahme (660 Hz / 440 Hz)."""
        self._play_tone([660.0, 440.0], duration_ms=110)

    def play_success(self):
        """Angenehmer Erfolgs-Signalton beim Einfügen (1046.5 Hz)."""
        self._play_tone([1046.5], duration_ms=90)

    def play_error(self):
        """Tiefer Warn-Signalton bei Fehlern (220 Hz)."""
        self._play_tone([220.0, 233.08], duration_ms=200)
