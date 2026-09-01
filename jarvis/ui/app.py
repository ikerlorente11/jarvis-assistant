"""Arranque de la UI: bolita + panel conectados al router."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from jarvis.router import Router
from jarvis.ui.ball import Ball
from jarvis.ui.panel import Panel


def run(router: Router, debug: bool = False) -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # ocultar el panel no cierra el programa

    ball = Ball()
    panel = Panel(router, debug=debug)

    def toggle_panel() -> None:
        if panel.isVisible():
            panel.hide()
        else:
            panel.show_near(ball.frameGeometry())

    ball.clicked.connect(toggle_panel)
    panel.working.connect(
        lambda busy: ball.set_state("working" if busy else "idle")
    )

    ball.show()
    return app.exec()
