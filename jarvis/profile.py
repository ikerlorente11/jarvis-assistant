"""Gestor de perfiles de hardware.

Primer paso del arranque: detecta VRAM/RAM/CPU y fija qué modelos se cargan
y dónde (docs/02 §6). El resto del código pide "el STT" o "el LLM" a través
del perfil y recibe el que toque, o un aviso claro de capacidad desactivada.

Uso: python -m jarvis.profile          → imprime el perfil detectado
     Profile.load() desde el código    → perfil (respetando config.yaml)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import psutil
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

PROFILE_NAMES = ("full", "gpu-lite", "cpu", "minimal")

# Ajustes por perfil (docs/02 §6). device: dónde corre el STT/LLM.
PROFILE_SETTINGS = {
    "full": {
        "stt_model": "large-v3-turbo",
        "stt_device": "cuda",
        "llm_model": "qwen3:8b",
        "llm_enabled": True,
    },
    # 4B en variante instruct-2507: no "piensa" (latencia) y llama mejor a tools
    "gpu-lite": {
        "stt_model": "small",
        "stt_device": "cuda",
        "llm_model": "qwen3:4b-instruct-2507-q4_K_M",
        "llm_enabled": True,
    },
    "cpu": {
        "stt_model": "small",
        "stt_device": "cpu",
        "llm_model": "qwen3:4b-instruct-2507-q4_K_M",
        "llm_enabled": True,
    },
    "minimal": {
        "stt_model": None,  # solo Vosk (fast path)
        "stt_device": "cpu",
        "llm_model": None,
        "llm_enabled": False,
    },
}


@dataclass(frozen=True)
class Hardware:
    """Recursos detectados en la máquina."""

    gpu_name: str | None
    vram_gb: float
    ram_gb: float
    cpu_cores: int

    @staticmethod
    def detect() -> "Hardware":
        gpu_name, vram_gb = _detect_gpu()
        mem = psutil.virtual_memory()
        return Hardware(
            gpu_name=gpu_name,
            vram_gb=vram_gb,
            ram_gb=mem.total / 1024**3,
            cpu_cores=psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
        )


@dataclass(frozen=True)
class Profile:
    """Perfil elegido + ajustes de modelos que implica."""

    name: str
    hardware: Hardware
    forced: bool  # True si viene de config.yaml, no de la detección

    @property
    def stt_model(self) -> str | None:
        return PROFILE_SETTINGS[self.name]["stt_model"]

    @property
    def stt_device(self) -> str:
        return PROFILE_SETTINGS[self.name]["stt_device"]

    @property
    def llm_model(self) -> str | None:
        return PROFILE_SETTINGS[self.name]["llm_model"]

    @property
    def llm_enabled(self) -> bool:
        return PROFILE_SETTINGS[self.name]["llm_enabled"]

    @staticmethod
    def load(force: str | None = None) -> "Profile":
        """Detecta el hardware y devuelve el perfil.

        Prioridad: argumento `force` > config.yaml (`profile:`) > detección.
        """
        hw = Hardware.detect()
        forced = force or _config_override()
        if forced:
            if forced not in PROFILE_NAMES:
                raise ValueError(
                    f"Perfil desconocido: {forced!r} (válidos: {', '.join(PROFILE_NAMES)})"
                )
            return Profile(name=forced, hardware=hw, forced=True)
        return Profile(name=_pick(hw), hardware=hw, forced=False)

    def describe(self) -> str:
        hw = self.hardware
        gpu = f"{hw.gpu_name} ({hw.vram_gb:.1f} GB VRAM)" if hw.gpu_name else "sin GPU NVIDIA"
        origin = "forzado" if self.forced else "autodetectado"
        lines = [
            f"Perfil: {self.name} ({origin})",
            f"  GPU:  {gpu}",
            f"  RAM:  {hw.ram_gb:.1f} GB",
            f"  CPU:  {hw.cpu_cores} núcleos físicos",
            f"  STT:  {self.stt_model or 'solo Vosk (comandos)'} en {self.stt_device}",
            f"  LLM:  {self.llm_model if self.llm_enabled else 'desactivado'}",
        ]
        return "\n".join(lines)


def _pick(hw: Hardware) -> str:
    """Reglas de docs/02 §6. Umbral de RAM en 15: una máquina de 16 GB
    nominales reporta ~15.7 GB usables (reserva de hardware/BIOS)."""
    if hw.vram_gb >= 10:
        return "full"
    if hw.vram_gb >= 6:
        return "gpu-lite"
    if hw.ram_gb >= 15:
        return "cpu"
    return "minimal"


def _detect_gpu() -> tuple[str | None, float]:
    """VRAM total de la primera GPU NVIDIA vía NVML; (None, 0) si no hay."""
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            name = pynvml.nvmlDeviceGetName(handle)
            if isinstance(name, bytes):
                name = name.decode()
            vram = pynvml.nvmlDeviceGetMemoryInfo(handle).total / 1024**3
            return name, vram
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None, 0.0


def _config_override() -> str | None:
    """Lee `profile:` de config.yaml; None si es 'auto', falta o no hay fichero."""
    try:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        return None
    value = config.get("profile")
    if not value or str(value).lower() == "auto":
        return None
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detecta el perfil de hardware")
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        help="fuerza un perfil en vez de autodetectar",
    )
    args = parser.parse_args()
    print(Profile.load(force=args.profile).describe())


if __name__ == "__main__":
    main()
