"""Punto de entrada: python -m jarvis [--debug] [--profile X]"""

from __future__ import annotations

import argparse

from jarvis import config as config_module
from jarvis.profile import PROFILE_NAMES, Profile
from jarvis.router import Router


def main() -> None:
    parser = argparse.ArgumentParser(prog="jarvis")
    parser.add_argument("--debug", action="store_true", help="métricas por consola")
    parser.add_argument("--profile", choices=PROFILE_NAMES, help="fuerza el perfil")
    args = parser.parse_args()

    profile = Profile.load(force=args.profile)
    if args.debug:
        print(profile.describe())

    config = config_module.load()
    router = Router(config)

    from jarvis.ui.app import run  # import tardío: PySide6 pesa

    raise SystemExit(run(router, debug=args.debug))


if __name__ == "__main__":
    main()
