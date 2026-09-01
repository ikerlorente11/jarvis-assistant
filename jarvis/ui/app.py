"""Arranque de la UI: bolita + panel + icono de bandeja conectados al router."""

from __future__ import annotations

import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from jarvis.router import Router
from jarvis.ui.ball import Ball
from jarvis.ui.panel import Panel


def _tray_icon() -> QIcon:
    """La misma bola azul de JARVIS, pintada como icono."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QRadialGradient(24, 22, 46)
    gradient.setColorAt(0.0, QColor("#6f9dff"))
    gradient.setColorAt(1.0, QColor("#2456c8"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(4, 4, 56, 56))
    painter.end()
    return QIcon(pixmap)


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

    # Icono en la bandeja: abrir, ajustes, bolita sí/no y salir limpio.
    tray = QSystemTrayIcon(_tray_icon(), app)
    tray.setToolTip("JARVIS")
    menu = QMenu()
    accion_abrir = QAction("Abrir JARVIS")
    accion_abrir.triggered.connect(toggle_panel)
    menu.addAction(accion_abrir)
    accion_ajustes = QAction("⚙ Ajustes")

    def abrir_ajustes() -> None:
        if not panel.isVisible():
            panel.show_near(ball.frameGeometry())
        panel._show_settings()

    accion_ajustes.triggered.connect(abrir_ajustes)
    menu.addAction(accion_ajustes)
    menu.addSeparator()
    accion_bolita = QAction("Mostrar la bolita")
    accion_bolita.setCheckable(True)
    accion_bolita.setChecked(bool(ui_config.get("ball", True)))
    accion_bolita.toggled.connect(panel._on_ball_toggled)

    def _sync_bolita(visible: bool) -> None:
        accion_bolita.blockSignals(True)
        accion_bolita.setChecked(visible)
        accion_bolita.blockSignals(False)

    panel.ball_visible.connect(_sync_bolita)
    menu.addAction(accion_bolita)
    menu.addSeparator()
    accion_salir = QAction("Salir")
    accion_salir.triggered.connect(app.quit)
    menu.addAction(accion_salir)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: toggle_panel()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    if ui_config.get("ball", True):
        ball.show()
    return app.exec()
