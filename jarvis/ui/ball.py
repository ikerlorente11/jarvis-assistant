"""La bolita: widget circular sin marco, siempre encima, arrastrable.

Estados (color): reposo (azul), trabajando (ámbar), hablando (verde),
escuchando (violeta, tras "Hey Jarvis"). Click sin arrastre → abre/cierra
el panel. Permanente como ayuda de accesibilidad.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

SIZE = 56
DRAG_THRESHOLD = 6  # px: menos que esto al soltar = click, no arrastre

COLORS = {
    "idle": QColor("#2f6fed"),
    "working": QColor("#e8a13c"),
    "speaking": QColor("#2fae5f"),
    "listening": QColor("#9a5cf0"),
}


class Ball(QWidget):
    clicked = Signal()

    def __init__(self, config: dict | None = None):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(SIZE, SIZE)
        self._config = config or {}
        self._state = "idle"
        self._press_global = QPoint()
        self._press_offset = QPoint()
        self._dragging = False
        self._phase = 0.0
        self._pulse = QTimer(self, interval=50, timeout=self._tick)
        self._restore_position()

    # -- estado --------------------------------------------------------------

    def set_state(self, state: str) -> None:
        self._state = state if state in COLORS else "idle"
        if self._state in ("working", "speaking", "listening"):  # latido
            self._pulse.start()
        else:
            self._pulse.stop()
            self._phase = 0.0
        self.update()

    def _tick(self) -> None:
        self._phase += 0.25
        self.update()

    # -- pintura -------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = COLORS[self._state]
        brillo = 150 + int(45 * math.sin(self._phase))  # latido sutil
        gradient = QRadialGradient(SIZE * 0.38, SIZE * 0.34, SIZE * 0.75)
        gradient.setColorAt(0.0, color.lighter(brillo))
        gradient.setColorAt(1.0, color.darker(115))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, SIZE - 4, SIZE - 4)

    # -- arrastre / click ----------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            pos = event.globalPosition().toPoint()
            if (pos - self._press_global).manhattanLength() > DRAG_THRESHOLD:
                self._dragging = True
            if self._dragging:
                self.move(pos - self._press_offset)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._dragging:
                self._save_position()
            else:
                self.clicked.emit()

    # -- interno -------------------------------------------------------------

    def _save_position(self) -> None:
        from jarvis import config as config_module

        pos = self.frameGeometry().topLeft()
        config_module.save_local({"ui": {"ball_pos": [pos.x(), pos.y()]}})

    def _restore_position(self) -> None:
        """La posición guardada, si sigue dentro de alguna pantalla;
        si no, la esquina inferior derecha del monitor primario."""
        from PySide6.QtGui import QGuiApplication

        guardada = (self._config.get("ui", {}) or {}).get("ball_pos")
        if isinstance(guardada, (list, tuple)) and len(guardada) == 2:
            x, y = int(guardada[0]), int(guardada[1])
            for screen in QGuiApplication.screens():
                if screen.availableGeometry().adjusted(0, 0, -SIZE, -SIZE).contains(x, y):
                    self.move(x, y)
                    return
        area = self.screen().availableGeometry()
        margin = 24
        self.move(
            area.right() - SIZE - margin,
            area.bottom() - SIZE - margin,
        )
