"""TTS con Piper: lee las respuestas en voz alta (opcional, config tts.enabled).

- La voz se carga una sola vez (perezosamente) y se queda en memoria.
- Cola de un elemento: hablar algo nuevo descarta lo pendiente y corta lo
  que esté sonando — la última respuesta es la que importa.
- Sin dependencia de Qt: la UI (y en fase 5 la voz) le pasan un callback
  opcional para reflejar el estado "hablando".
"""

from __future__ import annotations

import io
import queue
import threading
import wave
import winsound
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "piper"
DEFAULT_VOICE = "es_ES-davefx-medium"


class TTS:
    def __init__(self, config: dict, on_speaking=None):
        tts_config = config.get("tts", {}) or {}
        self.enabled = bool(tts_config.get("enabled", False))
        self.volume = int(tts_config.get("volume", 80))  # 0-100
        self.voice_name = tts_config.get("voice", DEFAULT_VOICE)
        self.replacements = tts_config.get("replacements", {}) or {}
        self._on_speaking = on_speaking or (lambda speaking: None)
        self._voice = None
        self._load_lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        if self.enabled:
            self.preload()  # que la primera respuesta no pague la carga

    # -- API -----------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Encola el texto (si está activado); descarta lo pendiente."""
        from jarvis.audio.speech_text import normalizar

        text = normalizar(text, self.replacements)
        if not self.enabled or not text:
            return
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        winsound.PlaySound(None, winsound.SND_PURGE)  # corta lo que suene
        self._queue.put(text)

    def preload(self) -> None:
        """Carga la voz en un hilo aparte sin bloquear el arranque."""
        threading.Thread(target=self._load_voice, daemon=True).start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.preload()
        else:
            winsound.PlaySound(None, winsound.SND_PURGE)

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))

    @property
    def available(self) -> bool:
        return (MODELS_DIR / f"{self.voice_name}.onnx").exists()

    # -- worker --------------------------------------------------------------

    def _run(self) -> None:
        while True:
            text = self._queue.get()
            try:
                self._on_speaking(True)
                self._speak(text)
            except Exception:
                pass  # sin voz no se rompe nada: la respuesta ya está en pantalla
            finally:
                self._on_speaking(False)

    def _speak(self, text: str) -> None:
        voice = self._load_voice()
        if voice is None:
            return
        from piper import SynthesisConfig

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            voice.synthesize_wav(
                text, wav, syn_config=SynthesisConfig(volume=self.volume / 100)
            )
        winsound.PlaySound(buffer.getvalue(), winsound.SND_MEMORY)

    def _load_voice(self):
        with self._load_lock:
            if self._voice is None and self.available:
                from piper import PiperVoice

                self._voice = PiperVoice.load(MODELS_DIR / f"{self.voice_name}.onnx")
            return self._voice
