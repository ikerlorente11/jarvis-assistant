"""Panel de la bolita: menús por categorías (generados del catálogo de
intents) + campo de texto libre + zona de respuesta.

No sabe nada de skills: todo pasa por el router (dispatch directo por id
desde los botones, handle() para el texto libre — el mismo camino que usará
la voz).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvis import config as config_module
from jarvis.audio.tts import TTS
from jarvis.router import Result, Router

WIDTH = 320
MAX_HEIGHT = 480

STYLE = """
QWidget#panel { background: #1e2430; border-radius: 12px; }
QLabel { color: #e8ecf4; }
QLabel#category { color: #8fa3c4; font-weight: bold; padding-top: 6px; }
QTextEdit#response {
    background: #141922; color: #e8ecf4; border: none;
    border-radius: 8px; padding: 6px; font-size: 12px;
}
QLabel#latency { color: #66738a; font-size: 11px; }
QToolTip { background: #141922; color: #e8ecf4; border: 1px solid #37445c; }
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
QCheckBox { color: #e8ecf4; }
QSlider::groove:horizontal {
    height: 4px; background: #2a3342; border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 12px; margin: -5px 0; background: #8fa3c4; border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #2f6fed; border-radius: 2px; }
"""


class Panel(QWidget):
    working = Signal(bool)  # para que la bolita cambie de estado
    speaking = Signal(bool)  # ídem, mientras el TTS habla

    def __init__(self, router: Router, debug: bool = False):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.router = router
        self.debug = debug
        # emitir una señal Qt desde el hilo del TTS es seguro (conexión en cola)
        self.tts = TTS(router.config, on_speaking=self.speaking.emit)
        router.config["_tts"] = self.tts  # para las skills de voz
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
                if intent.description:
                    button.setToolTip(intent.description)
                button.clicked.connect(
                    lambda _=False, i=intent: self._on_intent(i)
                )
                menu_layout.addWidget(button)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(menu)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        # Voz del asistente: interruptor + volumen propio (no el del sistema).
        voz_row = QHBoxLayout()
        self.voz_check = QCheckBox("Voz")
        self.voz_check.setChecked(self.tts.enabled)
        self.voz_check.setToolTip("Leer las respuestas en voz alta (Piper)")
        self.voz_check.toggled.connect(self._on_voz_toggled)
        voz_row.addWidget(self.voz_check)
        self.voz_slider = QSlider(Qt.Horizontal)
        self.voz_slider.setRange(0, 100)
        self.voz_slider.setValue(self.tts.volume)
        self.voz_slider.setToolTip("Volumen de la voz del asistente")
        self.voz_slider.valueChanged.connect(self._on_voz_volumen)
        voz_row.addWidget(self.voz_slider, stretch=1)
        layout.addLayout(voz_row)

        # Texto libre: mismo router que usará la voz.
        self.input = QLineEdit(placeholderText="Escribe una orden…")
        self.input.returnPressed.connect(self._on_text)
        layout.addWidget(self.input)

        self.response = QTextEdit(objectName="response")
        self.response.setReadOnly(True)  # seleccionable y con scroll
        self.response.setLineWrapMode(QTextEdit.WidgetWidth)
        self.response.setMinimumHeight(60)
        self.response.setMaximumHeight(150)
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
            prompt = intent.description or f"¿Qué {intent.slot}?"
            if intent.options_from:
                # Las opciones salen de config.yaml (p. ej. app_profiles);
                # editable: también se puede escribir otra cosa.
                opciones = list(
                    self.router.config.get(intent.options_from, {}).keys()
                )
                slot_value, ok = QInputDialog.getItem(
                    self, "JARVIS", prompt, opciones, 0, True
                )
            else:
                slot_value, ok = QInputDialog.getText(self, "JARVIS", prompt)
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

    def _on_voz_toggled(self, checked: bool) -> None:
        self.tts.set_enabled(checked)
        config_module.save_local({"tts": {"enabled": checked}})

    def _on_voz_volumen(self, value: int) -> None:
        self.tts.set_volume(value)
        config_module.save_local({"tts": {"volume": value}})

    def _show(self, result: Result) -> None:
        self.response.setPlainText(result.text)
        self.response.show()
        self.tts.speak(result.text)
        if self.debug:
            self.latency.setText(
                f"{result.elapsed_ms:.1f} ms · intent={result.intent_id}"
            )
            self.latency.show()

    # -- posición / teclado --------------------------------------------------

    def show_near(self, ball_geometry) -> None:
        """Encima de la bolita, sin salirse de la pantalla."""
        # reflejar cambios hechos por comando ("desactiva la voz")
        self.voz_check.blockSignals(True)
        self.voz_check.setChecked(self.tts.enabled)
        self.voz_check.blockSignals(False)
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
