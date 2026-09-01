"""Punto de entrada: python -m jarvis [--debug] [--profile X]"""

from __future__ import annotations

import argparse
import faulthandler
import sys
import traceback
from datetime import datetime
from pathlib import Path

from jarvis import config as config_module
from jarvis.profile import PROFILE_NAMES, Profile
from jarvis.router import Router

LOG_PATH = Path(__file__).resolve().parent.parent / "jarvis.log"


def _setup_crash_log() -> None:
    """Todo crash (Python o nativo) queda en jarvis.log, pase lo que pase
    con stdout (que en segundo plano va en búfer y se pierde)."""
    log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=log)

    def hook(exc_type, exc, tb):
        log.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        traceback.print_exception(exc_type, exc, tb, file=log)
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = hook


def main() -> None:
    _setup_crash_log()
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("--debug", action="store_true", help="métricas por consola")
    parser.add_argument("--profile", choices=PROFILE_NAMES, help="fuerza el perfil")
    args = parser.parse_args()

    profile = Profile.load(force=args.profile)
    if args.debug:
        print(profile.describe())

    config = config_module.load()
    router = Router(config)

    from jarvis.brain import Brain

    brain = Brain(config, router, profile)

    from jarvis.ui.app import run  # import tardío: PySide6 pesa

    raise SystemExit(run(router, brain=brain, debug=args.debug))


if __name__ == "__main__":
    main()
