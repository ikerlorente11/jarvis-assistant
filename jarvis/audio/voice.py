"""Entrada por voz (fase 5): micro → "Hey Jarvis" → VAD → STT → texto.

El motor no cambia (docs/01): esta capa produce texto y lo entrega al mismo
router/LLM que usa el panel. Todo corre en un hilo propio:

  sounddevice (16 kHz mono, frames de 80 ms)
    → openWakeWord "hey jarvis" (siempre escuchando, ~1% CPU)
    → ♪ earcon inmediato + estado "listening" (y corta el TTS: barge-in)
    → Silero VAD (el que trae openWakeWord) detecta cuándo dejas de hablar
    → faster-whisper (modelo y dispositivo según el perfil de hardware)

El micrófono se elige por preferencia de config (voice.preferred_mics:
webcam → Momentum 4 → Barracuda X…): se abre el primero que exista Y se
deje abrir — un bluetooth apagado sigue listado por Windows pero falla.

Callbacks (llegan desde el hilo de audio; la UI los envuelve en señales Qt):
  on_text(str)   — comando transcrito, listo para el router
  on_state(str)  — "listening" / "transcribing" / "idle"

Uso CLI: python -m jarvis.audio.voice           → descarga modelos y prueba
         python -m jarvis.audio.voice --mics    → lista los micrófonos
"""

from __future__ import annotations

import io
import math
import re
import struct
import threading
import time
import wave
import winsound
from datetime import datetime
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent.parent / "models"
WAKE_DIR = MODELS / "openwakeword"
WHISPER_DIR = MODELS / "whisper"

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms: el tamaño que espera openWakeWord
FRAME_S = FRAME / SAMPLE_RATE

WAKE_MODEL = "hey_jarvis_v0.1.onnx"
WAKE_KEY = "hey_jarvis_v0.1"  # nombre interno del modelo en openWakeWord
FEATURE_FILES = ("melspectrogram.onnx", "embedding_model.onnx", "silero_vad.onnx")

# Verificador personalizado (se entrena con la voz del usuario:
# python -m jarvis.audio.voice --entrenar). Con él, el modelo base actúa
# solo de filtro grueso y la decisión la toma un clasificador que sabe
# cómo suena ESTE usuario diciendo "hey jarvis" → menos falsos positivos
# y menos detecciones perdidas a la vez.
VERIFIER_PATH = WAKE_DIR / "hey_jarvis_verifier.pkl"
VERIFIER_GATE = 0.03  # score base a partir del cual se consulta el verificador

PALABRAS_CORTAR = {"para", "stop", "callate", "calla", "silencio", "nada"}

# Restos del "Hey Jarvis" que a veces se cuelan al principio del comando
# (la detección salta un pelín tarde y Whisper aún lo oye)
WAKE_RESTOS = re.compile(
    r"^[\s,.!?¡¿]*(oye|hey|ey|ok|okay)?[\s,.!?¡¿]*"
    r"(jarvis|yarvis|charvis|harvis|travis|vis|bis)\b[\s,.!?¡¿]*",
    re.IGNORECASE,
)

# Whisper a veces pega el verbo a una URL dictada («abreyoutube.com»):
# se despega si lo que sigue al verbo es un dominio.
PEGADO_URL = re.compile(
    r"^(ábreme|abreme|abrir|abre|ponme|pon|busca|cierra)"
    r"((?:[\w-]+\.)+[a-z]{2,}(?:/\S*)?)[.!?]?$",
    re.IGNORECASE,
)

LOG_PATH = Path(__file__).resolve().parent.parent.parent / "jarvis.log"


def _log(msg: str) -> None:
    """Traza del pipeline de voz en jarvis.log (para diagnosticar sin UI)."""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} [voz] {msg}\n")
    except OSError:
        pass

DEFAULT_VOICE_CONFIG = {
    "enabled": True,
    "mic": "auto",
    "preferred_mics": ["trust", "webcam", "momentum", "barracuda"],
    "wake_threshold": 0.10,
    "silence_ms": 800,
    "max_command_s": 12,
}


def _config_voz(config: dict) -> dict:
    merged = dict(DEFAULT_VOICE_CONFIG)
    merged.update(config.get("voice", {}) or {})
    return merged


# -- earcons (generados en memoria: sin ficheros, latencia cero) --------------

def _tono(notas: tuple[float, ...], dur: float = 0.09, vol: float = 0.35) -> bytes:
    sr = 22050
    frames = bytearray()
    for freq in notas:
        n = int(sr * dur)
        for i in range(n):
            fade = min(1.0, i / 200, (n - i) / 400)  # sin clicks
            sample = int(vol * fade * 32767 * math.sin(2 * math.pi * freq * i / sr))
            frames += struct.pack("<h", sample)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


EARCON_WAKE = _tono((660, 990))       # ascendente: "te escucho"
EARCON_CANCEL = _tono((440, 330))     # descendente: "no he oído nada"


def _play(earcon: bytes) -> None:
    # winsound no permite SND_MEMORY asíncrono → hilo aparte para no perder
    # los primeros frames del comando mientras suena.
    threading.Thread(
        target=winsound.PlaySound, args=(earcon, winsound.SND_MEMORY), daemon=True
    ).start()


# -- micrófonos ---------------------------------------------------------------

def _bonito(nombre: str) -> str:
    """Los dispositivos WDM-KS traen nombres horribles
    («Auriculares (@System32\\drivers\\...;(MOMENTUM 4))») → legibles."""
    if "@system32" not in nombre.lower():
        return nombre
    interno = re.findall(r"\(([^()]+)\)", nombre)
    base = nombre.split("(@")[0].strip()
    if interno:
        return f"{base} ({interno[-1]})" if base else interno[-1]
    return base or nombre


def list_mics() -> list[str]:
    """Nombres de los micrófonos, legibles y sin duplicar entre host APIs
    (Windows enumera cada uno varias veces: MME, DirectSound, WASAPI...)."""
    import sounddevice as sd

    nombres, vistos = [], set()
    for dev in sd.query_devices():
        if dev["max_input_channels"] <= 0:
            continue
        nombre = _bonito(dev["name"].strip())
        clave = nombre.lower()[:28]  # MME trunca a 31 chars
        if clave in vistos:
            continue
        vistos.add(clave)
        nombres.append(nombre)
    return nombres


def _candidatos(voz: dict) -> list[tuple[int, str]]:
    """Índices de dispositivo a probar, por orden de preferencia."""
    import sounddevice as sd

    entradas = [
        (i, dev["name"].strip())
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] > 0
    ]
    mic = str(voz.get("mic", "auto"))
    prefs = (
        [mic] if mic.lower() != "auto"
        else [str(p) for p in voz.get("preferred_mics", [])]
    )
    orden: list[tuple[int, str]] = []
    for pref in prefs:
        for idx, nombre in entradas:
            # el selector guarda el nombre "bonito"; el dispositivo, el crudo
            if (pref.lower() in nombre.lower()
                    or pref.lower() in _bonito(nombre).lower()) \
                    and (idx, nombre) not in orden:
                orden.append((idx, nombre))
    # último recurso: el predeterminado de Windows
    try:
        default = sd.default.device[0]
        if default is not None and default >= 0:
            nombre = sd.query_devices(default)["name"].strip()
            if (default, nombre) not in orden:
                orden.append((default, nombre))
    except Exception:
        pass
    return orden


def _abrir_stream(voz: dict):
    """Abre el primer micrófono que funcione; (stream, nombre)."""
    import sounddevice as sd

    ultimo_error: Exception | None = None
    for idx, nombre in _candidatos(voz):
        extra = None
        try:
            if "wasapi" in sd.query_hostapis(
                sd.query_devices(idx)["hostapi"]
            )["name"].lower():
                # WASAPI no remuestrea solo: pedirle 16 kHz necesita esto
                extra = sd.WasapiSettings(auto_convert=True)
        except Exception:
            extra = None
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME,
                device=idx,
                extra_settings=extra,
            )
            stream.start()
            return stream, nombre
        except Exception as exc:  # apagado/ocupado: se prueba el siguiente
            ultimo_error = exc
    raise RuntimeError(f"Ningún micrófono disponible ({ultimo_error})")


# -- VAD ----------------------------------------------------------------------

class _Endpointer:
    """¿Estás hablando? Silero VAD (openWakeWord) con caída a energía RMS."""

    def __init__(self):
        self._vad = None
        try:
            from openwakeword.vad import VAD

            self._vad = VAD(model_path=str(WAKE_DIR / "silero_vad.onnx"))
        except Exception:
            self._vad = None
        self._floor = 250.0  # suelo de ruido adaptativo (fallback RMS)

    def reset(self) -> None:
        if self._vad is not None:
            try:
                self._vad.reset_states()
            except Exception:
                pass

    def is_speech(self, frame) -> bool:
        import numpy as np

        if self._vad is not None:
            try:
                # frame_size=640: divide exacto los frames de 1280 muestras
                return float(self._vad.predict(frame, frame_size=640)) >= 0.3
            except Exception:
                self._vad = None  # modelo roto → energía
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        umbral = max(400.0, self._floor * 3)
        if rms < umbral:
            self._floor = 0.95 * self._floor + 0.05 * rms
        return rms >= umbral


# -- STT ----------------------------------------------------------------------

def _cuda_dlls() -> None:
    """ctranslate2 necesita cuBLAS/cuDNN; en Windows llegan como paquetes
    pip (nvidia-*-cu12) y hay que poner sus carpetas de DLLs en el PATH:
    ctranslate2 las carga en tiempo de ejecución con LoadLibrary, que
    ignora os.add_dll_directory (este solo vale para la carga inicial)."""
    import os
    import sys

    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    dirs = [str(d) for d in base.glob("*/bin")]
    for bin_dir in dirs:
        try:
            os.add_dll_directory(bin_dir)
        except OSError:
            pass
    path = os.environ.get("PATH", "")
    nuevos = [d for d in dirs if d not in path]
    if nuevos:
        os.environ["PATH"] = os.pathsep.join([*nuevos, path])


class SpeechToText:
    """faster-whisper según el perfil; si la GPU falla, cae a CPU y avisa."""

    def __init__(self, profile):
        self.model_name = profile.stt_model
        self.device = profile.stt_device
        self._model = None
        self.note = ""  # qué se cargó de verdad (para --debug / CLI)

    def load(self) -> bool:
        if self.model_name is None:
            self.note = "perfil sin STT (minimal): voz desactivada"
            return False
        if self._model is not None:
            return True
        from faster_whisper import WhisperModel

        intentos = [(self.model_name, self.device, "float16")]
        if self.device == "cuda":
            intentos.append(("small", "cpu", "int8"))  # plan B sin GPU
        else:
            intentos = [(self.model_name, "cpu", "int8")]
        for modelo, device, ctype in intentos:
            try:
                if device == "cuda":
                    _cuda_dlls()
                self._model = WhisperModel(
                    modelo,
                    device=device,
                    compute_type=ctype,
                    download_root=str(WHISPER_DIR),
                )
                self.note = f"{modelo} en {device} ({ctype})"
                return True
            except Exception as exc:
                self.note = f"STT no disponible: {exc}"
        return False

    def transcribe(self, audio) -> str:
        """audio: np.float32 mono 16 kHz → texto (es)."""
        if self._model is None and not self.load():
            return ""
        try:
            return self._transcribe(audio)
        except Exception as exc:
            # la GPU puede fallar en runtime (DLLs, VRAM llena…): se recarga
            # en CPU y la voz sigue funcionando, aunque tarde algo más
            _log(f"STT falló ({exc}); reintento en CPU")
            self._model = None
            self.model_name, self.device = "small", "cpu"
            if not self.load():
                return ""
            return self._transcribe(audio)

    def _transcribe(self, audio) -> str:
        segments, _info = self._model.transcribe(
            audio,
            language="es",
            beam_size=2,
            vad_filter=True,
            condition_on_previous_text=False,
            without_timestamps=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


# -- modelos de wake word -----------------------------------------------------

def ensure_wake_models() -> None:
    """Descarga hey_jarvis + modelos de features/VAD a models/openwakeword
    (solo la primera vez; install.ps1 también lo deja hecho)."""
    faltan = [
        f for f in (WAKE_MODEL, *FEATURE_FILES) if not (WAKE_DIR / f).exists()
    ]
    if not faltan:
        return
    WAKE_DIR.mkdir(parents=True, exist_ok=True)
    from openwakeword.utils import download_models

    download_models(model_names=["hey_jarvis"], target_directory=str(WAKE_DIR))


# -- el hilo principal --------------------------------------------------------

class VoiceInput:
    def __init__(self, config: dict, profile, on_text=None, on_state=None):
        self.config = config
        self.profile = profile
        self._on_text = on_text or (lambda text: None)
        self._on_state = on_state or (lambda state: None)
        self.stt = SpeechToText(profile)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._followup = threading.Event()
        self.mic_name = ""  # micro realmente abierto (para Ajustes/CLI)
        self.status = "apagado"  # texto de estado legible

    # -- API -----------------------------------------------------------------

    @property
    def supported(self) -> bool:
        return self.profile.stt_model is not None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def set_enabled(self, enabled: bool) -> None:
        self.start() if enabled else self.stop()

    def follow_up(self) -> None:
        """El asistente acaba de hacer una pregunta: escuchar la respuesta
        sin exigir otro «Hey Jarvis»."""
        if self._thread is not None and self._thread.is_alive():
            self._followup.set()

    def set_mic(self, _name: str) -> None:
        """El micro cambió en Ajustes: reabrir el stream con la config nueva."""
        if self._thread is not None and self._thread.is_alive():
            self.stop()
            self._thread.join(timeout=3)
            self.start()

    # -- pipeline ------------------------------------------------------------

    def _run(self) -> None:
        import numpy as np  # noqa: F401  (dependencia del pipeline entero)

        try:
            self.status = "cargando modelos…"
            ensure_wake_models()
            oww = self._load_wakeword()
            if not self.stt.load():
                self.status = self.stt.note
                return
            endpointer = _Endpointer()
            stream, self.mic_name = _abrir_stream(_config_voz(self.config))
        except Exception as exc:
            self.status = f"voz no disponible: {exc}"
            return
        self.status = f"escuchando «Hey Jarvis» por {self.mic_name} · STT {self.stt.note}"
        voz = _config_voz(self.config)
        umbral = _umbral_wake(voz)
        try:
            while not self._stop.is_set():
                frame = self._leer(stream)
                if frame is None:
                    continue
                try:
                    if self._followup.is_set():
                        # el asistente acaba de preguntar algo: se escucha
                        # la respuesta directamente, sin exigir el wake
                        self._followup.clear()
                        _log("seguimiento: escuchando la respuesta")
                        self._atender(stream, oww, endpointer)
                        continue
                    self._ciclo(stream, oww, endpointer, frame, umbral)
                except Exception as exc:
                    # un fallo puntual no mata la escucha: se sigue
                    _log(f"error en el ciclo de voz: {exc}")
                    self._on_state("idle")
                    oww.reset()
                    endpointer.reset()
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self.status = "apagado"

    def _ciclo(self, stream, oww, endpointer, frame, umbral) -> None:
        """Una vuelta del bucle: ¿wake? → earcon → captura → STT → router."""
        score = max(oww.predict(frame).values())
        if score < umbral:
            return
        _log(f"wake (score {score:.2f})")
        self._atender(stream, oww, endpointer)

    def _atender(self, stream, oww, endpointer) -> None:
        """Tras el wake (o en seguimiento): earcon → captura → STT → router."""
        tts = self.config.get("_tts")
        if tts is not None:
            tts.interrupt()
        _play(EARCON_WAKE)
        self._on_state("listening")
        audio = self._capturar(stream, endpointer)
        oww.reset()
        endpointer.reset()
        if audio is None:
            _log("sin voz tras el wake")
            _play(EARCON_CANCEL)
            self._on_state("idle")
            return
        self._on_state("transcribing")
        t0 = time.perf_counter()
        texto = self.stt.transcribe(audio)
        stt_ms = (time.perf_counter() - t0) * 1000
        self._on_state("idle")
        # restos del propio "hey jarvis" colados al principio
        texto = WAKE_RESTOS.sub("", texto).strip()
        texto = PEGADO_URL.sub(r"\1 \2", texto)  # «abreyoutube.com»
        # Whisper remata con puntuación («Abre WhatsApp.») y eso ensucia
        # los slots (whatsapp. → whatsapp..com). Se limpia el final —
        # el «?» se respeta, que a las preguntas del LLM les viene bien.
        texto = re.sub(r"[.,;:!¡¿\s]+$", "", texto.strip())
        limpio = texto.lower().strip(" .,!?¡¿")
        _log(f"«{texto}» (STT {stt_ms:.0f} ms, "
             f"{len(audio) / SAMPLE_RATE:.1f} s de audio)")
        if not limpio:
            _play(EARCON_CANCEL)
        elif limpio in PALABRAS_CORTAR:
            pass  # solo quería cortar al asistente: ya está cortado
        else:
            self._on_text(texto)

    def _leer(self, stream):
        try:
            data, _overflow = stream.read(FRAME)
        except Exception:
            time.sleep(0.2)
            return None
        return data.reshape(-1)

    def _capturar(self, stream, endpointer):
        """Graba hasta que el VAD marque el final; None si no dijiste nada."""
        import numpy as np

        voz = _config_voz(self.config)
        max_s = float(voz.get("max_command_s", 12))
        silencio_fin = float(voz.get("silence_ms", 800)) / 1000
        frames: list = []
        hablando = False
        silencio = espera = total = 0.0
        while not self._stop.is_set() and total < max_s:
            frame = self._leer(stream)
            if frame is None:
                return None
            frames.append(frame)
            total += FRAME_S
            if endpointer.is_speech(frame):
                hablando, silencio = True, 0.0
            elif hablando:
                silencio += FRAME_S
                if silencio >= silencio_fin:
                    break
            else:
                espera += FRAME_S
                if espera >= 7.0:  # nadie habló tras el wake
                    return None
        if not hablando:
            return None
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        return audio

    def _load_wakeword(self):
        return load_wakeword()


def load_wakeword():
    from openwakeword.model import Model

    extra = {}
    if VERIFIER_PATH.exists():
        extra = {
            "custom_verifier_models": {WAKE_KEY: str(VERIFIER_PATH)},
            "custom_verifier_threshold": VERIFIER_GATE,
        }
    return Model(
        wakeword_models=[str(WAKE_DIR / WAKE_MODEL)],
        melspec_model_path=str(WAKE_DIR / "melspectrogram.onnx"),
        embedding_model_path=str(WAKE_DIR / "embedding_model.onnx"),
        inference_framework="onnx",
        **extra,
    )


def _umbral_wake(voz: dict) -> float:
    """Sin verificador manda wake_threshold (calibrado bajo); con él, el
    score ya es la probabilidad del clasificador personal → umbral alto."""
    if VERIFIER_PATH.exists():
        return float(voz.get("wake_threshold_verified", 0.55))
    return float(voz.get("wake_threshold", 0.10))


# -- CLI: descarga de modelos, diagnóstico y entrenamiento -------------------

def _vaciar_buffer(stream) -> None:
    """Descarta el audio acumulado mientras no se leía (pausas, tonos)."""
    try:
        while stream.read_available >= FRAME:
            stream.read(FRAME)
    except Exception:
        pass


def _grabar(stream, segundos: float):
    import numpy as np

    _vaciar_buffer(stream)
    frames = []
    for _ in range(int(segundos / FRAME_S)):
        data, _overflow = stream.read(FRAME)
        frames.append(data.reshape(-1))
    return np.concatenate(frames)


def _guardar_wav(ruta: Path, audio) -> None:
    with wave.open(str(ruta), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(audio.tobytes())


def _entrenar() -> None:
    """Entrena el verificador personal: aprende cómo suena ESTE usuario
    diciendo «Hey Jarvis» frente a su habla normal. Guiado por tonos:
    agudo = habla ya, grave = toma cerrada."""
    import numpy as np

    from jarvis import config as config_module

    POSITIVOS, SEG_POS, SEG_NEG = 8, 2.6, 30
    ensure_wake_models()
    voz = _config_voz(config_module.load())
    stream, nombre = _abrir_stream(voz)
    clips = WAKE_DIR / "clips_verificador"
    (clips / "pos").mkdir(parents=True, exist_ok=True)
    (clips / "neg").mkdir(parents=True, exist_ok=True)
    print(f"Micro: {nombre}")
    print(f"Di «Hey Jarvis» {POSITIVOS} veces: habla justo tras cada tono "
          "AGUDO; el grave cierra la toma. Empezamos en 3 s…", flush=True)
    time.sleep(3)
    positivos = []
    for i in range(POSITIVOS):
        print(f"  ({i + 1}/{POSITIVOS}) di «Hey Jarvis»…", flush=True)
        _play(EARCON_WAKE)
        time.sleep(0.35)  # que el tono no se cuele en la toma
        audio = _grabar(stream, SEG_POS)
        _play(EARCON_CANCEL)
        ruta = clips / "pos" / f"hey_jarvis_{i + 1}.wav"
        _guardar_wav(ruta, audio)
        positivos.append(str(ruta))
        time.sleep(0.6)
    print(f"\nAhora habla NORMAL durante {SEG_NEG} s (lee algo en voz alta), "
          "SIN decir «Hey Jarvis»…", flush=True)
    _play(EARCON_WAKE)
    negativo = _grabar(stream, SEG_NEG)
    _play(EARCON_CANCEL)
    stream.stop()
    stream.close()
    negativos = []
    paso = SAMPLE_RATE * 3
    for i in range(0, len(negativo) - paso + 1, paso):
        ruta = clips / "neg" / f"habla_{i // paso + 1}.wav"
        _guardar_wav(ruta, negativo[i:i + paso])
        negativos.append(str(ruta))

    print("\nEntrenando el verificador…", flush=True)
    from openwakeword.custom_verifier_model import train_custom_verifier

    train_custom_verifier(
        positive_reference_clips=positivos,
        negative_reference_clips=negativos,
        output_path=str(VERIFIER_PATH),
        model_name=str(WAKE_DIR / WAKE_MODEL),
        melspec_model_path=str(WAKE_DIR / "melspectrogram.onnx"),
        embedding_model_path=str(WAKE_DIR / "embedding_model.onnx"),
        inference_framework="onnx",
    )
    print(f"[ok] Verificador guardado: {VERIFIER_PATH.name}")

    # validación: ¿las tomas del usuario superan el umbral nuevo?
    oww = load_wakeword()
    umbral = 0.55
    aciertos = 0
    for ruta in positivos:
        with wave.open(ruta) as wav:
            pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        mejor = 0.0
        for i in range(0, len(pcm) - FRAME, FRAME):
            mejor = max(mejor, max(oww.predict(pcm[i:i + FRAME]).values()))
        oww.reset()
        aciertos += mejor >= umbral
        print(f"  toma {Path(ruta).stem}: {mejor:.2f}")
    print(f"[{'ok' if aciertos >= 6 else '!!'}] {aciertos}/{len(positivos)} "
          f"tomas superan el umbral {umbral}. "
          + ("" if aciertos >= 6 else "Repite el entrenamiento en un momento "
             "con menos ruido."))


def _listen_test(segundos: int) -> None:
    """Prueba en vivo del wake word: imprime cada ½ s la mejor puntuación
    y el nivel del micro (rms). rms < 100 sostenido = el micro no capta."""
    import numpy as np

    from jarvis import config as config_module

    ensure_wake_models()
    voz = _config_voz(config_module.load())
    umbral = _umbral_wake(voz)
    stream, nombre = _abrir_stream(voz)
    oww = load_wakeword()
    print(f"Micro: {nombre} · umbral {umbral} · {segundos} s — di «Hey Jarvis»",
          flush=True)
    fin = time.time() + segundos
    mejor = rms_max = 0.0
    ultimo = time.time()
    detecciones = 0
    while time.time() < fin:
        try:
            data, _overflow = stream.read(FRAME)
        except Exception as exc:
            print(f"[!!] error leyendo el micro: {exc}", flush=True)
            break
        frame = data.reshape(-1)
        score = float(max(oww.predict(frame).values()))
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        mejor, rms_max = max(mejor, score), max(rms_max, rms)
        if score >= umbral:
            detecciones += 1
            print(f"  ✔ ¡WAKE! score={score:.2f}", flush=True)
            oww.reset()
        if time.time() - ultimo >= 0.5:
            print(f"  score={mejor:.2f}  rms={rms_max:5.0f}", flush=True)
            mejor = rms_max = 0.0
            ultimo = time.time()
    stream.stop()
    stream.close()
    print(f"Fin: {detecciones} detecciones.", flush=True)


def main() -> None:
    import argparse

    from jarvis import config as config_module
    from jarvis.profile import Profile

    parser = argparse.ArgumentParser(description="Diagnóstico de la voz (fase 5)")
    parser.add_argument("--mics", action="store_true", help="lista los micrófonos")
    parser.add_argument("--setup", action="store_true",
                        help="descarga los modelos (wake word + whisper) y sale")
    parser.add_argument("--listen", type=int, nargs="?", const=30, default=None,
                        metavar="SEG", help="prueba en vivo: di «Hey Jarvis» y "
                        "mira la puntuación del wake word y el nivel del micro")
    parser.add_argument("--entrenar", action="store_true",
                        help="entrena el verificador con tu voz (~2 min): "
                        "menos falsos positivos y mejor detección")
    args = parser.parse_args()

    if args.entrenar:
        _entrenar()
        return
    if args.listen:
        _listen_test(args.listen)
        return

    if args.mics:
        config = config_module.load()
        voz = _config_voz(config)
        elegidos = [nombre for _idx, nombre in _candidatos(voz)]
        for nombre in list_mics():
            marca = " ← se probaría" if nombre in elegidos[:1] else ""
            print(f"  {nombre}{marca}")
        return

    print("[..] Modelos de wake word (hey_jarvis)…")
    ensure_wake_models()
    print(f"[ok] {WAKE_DIR}")
    profile = Profile.load()
    stt = SpeechToText(profile)
    print(f"[..] STT {profile.stt_model} ({profile.stt_device})… (descarga si falta)")
    ok = stt.load()
    print(f"[{'ok' if ok else '!!'}] {stt.note}")
    if args.setup:
        return
    config = config_module.load()
    voz = _config_voz(config)
    try:
        stream, nombre = _abrir_stream(voz)
        stream.stop()
        stream.close()
        print(f"[ok] Micrófono: {nombre}")
    except RuntimeError as exc:
        print(f"[!!] {exc}")


if __name__ == "__main__":
    main()
