"""TTS: lee las respuestas en voz alta (opcional, config tts.enabled).

Dos motores:
- Piper (rápido, varias voces es_ES). Se sintetiza frase a frase y se
  insertan pausas reales entre frases: Piper no respeta bien la puntuación.
- Kokoro (más calidad; voces es: Dora ♀, Alex ♂, Santa ♂), nombres
  "kokoro:dora" etc. Modelo en models/kokoro (lo descarga install.ps1).

Comportamiento común: el motor se carga una vez (precarga al arrancar o al
activar), cola de un elemento (hablar algo nuevo corta lo anterior) y
volumen propio 0-100. Sin dependencia de Qt.
"""

from __future__ import annotations

import io
import queue
import re
import threading
import wave
import winsound
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent.parent / "models"
PIPER_DIR = MODELS / "piper"
KOKORO_DIR = MODELS / "kokoro"
DEFAULT_VOICE = "es_ES-davefx-medium"

KOKORO_VOICES = {  # nombre visible → id interno del modelo
    "kokoro:dora": "ef_dora",
    "kokoro:alex": "em_alex",
    "kokoro:santa": "em_santa",
}
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")

PAUSA_S = 0.28  # silencio entre frases (Piper)
FRASES = re.compile(r"(?<=[.!?;:])\s+")


class TTS:
    def __init__(self, config: dict, on_speaking=None):
        tts_config = config.get("tts", {}) or {}
        self.enabled = bool(tts_config.get("enabled", False))
        self.volume = int(tts_config.get("volume", 80))  # 0-100
        self.voice_name = tts_config.get("voice", DEFAULT_VOICE)
        self.replacements = tts_config.get("replacements", {}) or {}
        self._on_speaking = on_speaking or (lambda speaking: None)
        self._piper = None
        self._kokoro = None
        self._load_lock = threading.Lock()
        # generación: interrupt() la sube y lo pendiente/sintetizándose
        # se descarta antes de sonar (sin esto, cortar al TTS mientras
        # sintetiza dejaba que la frase sonara igual después)
        self._gen = 0
        self._queue: queue.Queue[tuple[int, str]] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()
        if self.enabled:
            self.preload()  # que la primera respuesta no pague la carga

    # -- API -----------------------------------------------------------------

    def speak(self, text: str) -> None:
        """Encola el texto (si está activado); descarta lo pendiente."""
        if not self.enabled:
            return
        self._enqueue(text)

    def preview(self, text: str) -> None:
        """Habla aunque la voz esté desactivada (probar voces del selector)."""
        self._enqueue(text)

    def interrupt(self) -> None:
        """Corta lo que esté sonando y vacía la cola (barge-in de la voz)."""
        self._gen += 1
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        winsound.PlaySound(None, winsound.SND_PURGE)

    def preload(self) -> None:
        """Carga el motor en un hilo aparte sin bloquear el arranque."""
        threading.Thread(target=self._load_engine, daemon=True).start()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.preload()
        else:
            winsound.PlaySound(None, winsound.SND_PURGE)

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))

    def set_voice(self, voice_name: str) -> None:
        if voice_name == self.voice_name:
            return
        winsound.PlaySound(None, winsound.SND_PURGE)
        with self._load_lock:
            self.voice_name = voice_name
            self._piper = None  # el kokoro cargado se reutiliza entre sus voces
        self.preload()

    @property
    def available(self) -> bool:
        if self.voice_name in KOKORO_VOICES:
            return all((KOKORO_DIR / f).exists() for f in KOKORO_FILES)
        return (PIPER_DIR / f"{self.voice_name}.onnx").exists()

    @staticmethod
    def installed_voices() -> list[str]:
        voices = []
        if PIPER_DIR.is_dir():
            voices += sorted(p.stem for p in PIPER_DIR.glob("*.onnx"))
        if all((KOKORO_DIR / f).exists() for f in KOKORO_FILES):
            voices += list(KOKORO_VOICES)
        return voices

    # -- worker --------------------------------------------------------------

    def _enqueue(self, text: str) -> None:
        from jarvis.audio.speech_text import normalizar

        text = normalizar(text, self.replacements)
        if not text:
            return
        self._gen += 1
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        winsound.PlaySound(None, winsound.SND_PURGE)  # corta lo que suene
        self._queue.put((self._gen, text))

    def _run(self) -> None:
        while True:
            gen, text = self._queue.get()
            try:
                self._on_speaking(True)
                self._speak(gen, text)
            except Exception:
                pass  # sin voz no se rompe nada: la respuesta ya está en pantalla
            finally:
                self._on_speaking(False)

    def _speak(self, gen: int, text: str) -> None:
        if self.voice_name in KOKORO_VOICES:
            self._speak_kokoro(gen, text)
        else:
            self._speak_piper(gen, text)

    # -- Piper ---------------------------------------------------------------

    def _speak_piper(self, gen: int, text: str) -> None:
        voice = self._load_engine()
        if voice is None:
            return
        from piper import SynthesisConfig

        syn = SynthesisConfig(volume=self.volume / 100)
        frames: list[bytes] = []
        params = None
        for frase in FRASES.split(text):
            if not frase.strip():
                continue
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                voice.synthesize_wav(frase.strip(), wav, syn_config=syn)
            buffer.seek(0)
            with wave.open(buffer, "rb") as wav:
                if params is None:
                    params = wav.getparams()
                frames.append(wav.readframes(wav.getnframes()))
        if not frames or params is None:
            return
        silencio = b"\x00" * (
            int(params.framerate * PAUSA_S) * params.sampwidth * params.nchannels
        )
        salida = io.BytesIO()
        with wave.open(salida, "wb") as wav:
            wav.setparams(params)
            wav.writeframes(silencio.join(frames))
        if gen != self._gen:  # interrumpido mientras se sintetizaba
            return
        winsound.PlaySound(salida.getvalue(), winsound.SND_MEMORY)

    # -- Kokoro --------------------------------------------------------------

    def _speak_kokoro(self, gen: int, text: str) -> None:
        engine = self._load_engine()
        if engine is None:
            return
        import numpy as np

        samples, framerate = engine.create(
            text, voice=KOKORO_VOICES[self.voice_name], speed=1.0, lang="es"
        )
        samples = (samples * (self.volume / 100) * 32767).clip(-32768, 32767)
        salida = io.BytesIO()
        with wave.open(salida, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(framerate)
            wav.writeframes(samples.astype(np.int16).tobytes())
        if gen != self._gen:  # interrumpido mientras se sintetizaba
            return
        winsound.PlaySound(salida.getvalue(), winsound.SND_MEMORY)

    # -- carga ---------------------------------------------------------------

    def _load_engine(self):
        with self._load_lock:
            if self.voice_name in KOKORO_VOICES:
                if self._kokoro is None and self.available:
                    from kokoro_onnx import Kokoro

                    self._kokoro = Kokoro(
                        str(KOKORO_DIR / KOKORO_FILES[0]),
                        str(KOKORO_DIR / KOKORO_FILES[1]),
                    )
                return self._kokoro
            if self._piper is None and self.available:
                from piper import PiperVoice

                self._piper = PiperVoice.load(
                    PIPER_DIR / f"{self.voice_name}.onnx"
                )
            return self._piper
