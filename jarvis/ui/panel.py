"""Panel de la bolita: menús por categorías (generados del catálogo de
intents) + campo de texto libre + zona de respuesta.

No sabe nada de skills: todo pasa por el router (dispatch directo por id
desde los botones, handle() para el texto libre — el mismo camino que usará
la voz).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.router import Result, Router

WIDTH = 320
MAX_HEIGHT = 480

STYLE = """
QWidget#panel { background: #1e2430; border-radius: 12px; }
QLabel { color: #e8ecf4; }
QLabel#category { color: #8fa3c4; font-weight: bold; padding-top: 6px; }
QLabel#response { background: #141922; border-radius: 8px; padding: 8px; }
QLabel#latency { color: #66738a; font-size: 11px; }
QPushButton {
    background: #2a3342; color: #e8ecf4; border: none;
    border-radius: 8px; padding: 7px 10px; text-align: left;
}
QPushButton:hover { background: #37445c; }
QLineEdit {
    background: #141922; color: #e8ecf4; border: 1px solid #2a3342;
    border-radius: 8px; padding: 7px 10px;
}
QScrollArea { border: none; background: transparent; }
"""


class Panel(QWidget):
    working = Signal(bool)  # para que la bolita cambie de estado

    def __init__(self, router: Router, debug: bool = False):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.router = router
        self.debug = debug
        self._build()

    # -- construcción --------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QWidget(objectName="panel")
        frame.setStyleSheet(STYLE)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("JARVIS")
        title.setStyleSheet("font-weight: bold; letter-spacing: 2px;")
        layout.addWidget(title)

        # Menús generados desde el catálogo: skill nueva → botón nuevo solo.
        menu = QWidget()
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(4)
        for cat_id, cat_label in self.router.categories.items():
            header = QLabel(cat_label, objectName="category")
            menu_layout.addWidget(header)
            for intent in self.router.intents:
                if intent.category != cat_id:
                    continue
                button = QPushButton(self._button_text(intent))
                button.clicked.connect(
                    lambda _=False, i=intent: self._on_intent(i)
                )
                menu_layout.addWidget(button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(menu)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        # Texto libre: mismo router que usará la voz.
        self.input = QLineEdit(placeholderText="Escribe una orden…")
        self.input.returnPressed.connect(self._on_text)
        layout.addWidget(self.input)

        self.response = QLabel("", objectName="response")
        self.response.setWordWrap(True)
        self.response.hide()
        layout.addWidget(self.response)

        self.latency = QLabel("", objectName="latency")
        self.latency.hide()
        layout.addWidget(self.latency)

        self.setFixedWidth(WIDTH)
        self.setMaximumHeight(MAX_HEIGHT)

    @staticmethod
    def _button_text(intent) -> str:
        # "Abrir programa: {app}" → "Abrir programa…" (el valor se pide al pulsar)
        if intent.slot:
            base = intent.label.split("{")[0].rstrip(" :…")
            return base + "…"
        return intent.label

    # -- acciones ------------------------------------------------------------

    def _on_intent(self, intent) -> None:
        slot_value = None
        if intent.slot:
            slot_value, ok = QInputDialog.getText(
                self, "JARVIS", f"¿Qué {intent.slot}?"
            )
            if not ok or not slot_value.strip():
                return
        self.working.emit(True)
        result = self.router.run_intent(intent.id, slot_value)
        self._show(result)
        self.working.emit(False)

    def _on_text(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.working.emit(True)
        result = self.router.handle(text)
        self._show(result)
        self.working.emit(False)
        self.input.clear()

    def _show(self, result: Result) -> None:
        self.response.setText(result.text)
        self.response.show()
        if self.debug:
            self.latency.setText(
                f"{result.elapsed_ms:.1f} ms · intent={result.intent_id}"
            )
            self.latency.show()

    # -- posición / teclado --------------------------------------------------

    def show_near(self, ball_geometry) -> None:
        """Encima de la bolita, sin salirse de la pantalla."""
        area = self.screen().availableGeometry()
        self.adjustSize()
        x = min(ball_geometry.x(), area.right() - self.width() - 8)
        y = ball_geometry.y() - self.height() - 8
        if y < area.top():
            y = ball_geometry.bottom() + 8
        self.move(max(area.left() + 8, x), y)
        self.show()
        self.input.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
