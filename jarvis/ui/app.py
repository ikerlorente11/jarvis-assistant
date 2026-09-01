"""Arranque de la UI: bolita + panel conectados al router."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from jarvis.router import Router
from jarvis.ui.ball import Ball
from jarvis.ui.panel import Panel


def run(router: Router, brain=None, debug: bool = False) -> int:
    from jarvis.ui.hotkey import GlobalHotkey

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # ocultar el panel no cierra el programa

    ball = Ball(router.config)
    panel = Panel(router, debug=debug, brain=brain)

    def toggle_panel() -> None:
        if panel.isVisible():
            panel.hide()
        else:
            panel.show_near(ball.frameGeometry())

    ball.clicked.connect(toggle_panel)
    panel.working.connect(
        lambda busy: ball.set_state("working" if busy else "idle")
    )
    panel.speaking.connect(
        lambda talking: ball.set_state("speaking" if talking else "idle")
    )
    panel.ball_visible.connect(ball.setVisible)

    ui_config = router.config.get("ui", {}) or {}
    hotkey = GlobalHotkey(app, toggle_panel)
    hotkey.register(str(ui_config.get("hotkey", "ctrl+alt+j")))
    panel.hotkey_changed.connect(hotkey.register)

    if ui_config.get("ball", True):
        ball.show()
    return app.exec()
