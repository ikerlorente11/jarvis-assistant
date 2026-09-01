"""Panel de la bolita: menús acordeón por categorías (generados del catálogo
de intents), campo de texto libre, respuesta con resultados clicables.

No sabe nada de skills: todo pasa por el router (dispatch directo por id
desde los botones, handle() para el texto libre — el mismo camino que usará
la voz). Las skills corren en un hilo: la UI nunca se congela y siempre hay
feedback inmediato (⏳ + bolita latiendo).
"""

from __future__ import annotations

import os
import subprocess
import threading
import time

from PySide6.QtCore import QFileInfo, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFileIconProvider,
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

WIDTH = 340
MAX_HEIGHT = 540
MAX_ITEMS = 8

STYLE = """
QWidget#panel { background: #1e2430; border-radius: 14px; }
QLabel { color: #e8ecf4; }
QLabel#title { font-weight: bold; font-size: 14px; letter-spacing: 2px; }
QLabel#latency { color: #66738a; font-size: 11px; }
QTextEdit#response {
    background: #141922; color: #e8ecf4; border: none;
    border-radius: 10px; padding: 6px; font-size: 12px;
}
QPushButton {
    background: transparent; color: #cfd8e8; border: none;
    border-radius: 8px; padding: 7px 10px; text-align: left; font-size: 12px;
}
QPushButton:hover { background: #37445c; color: #ffffff; }
QPushButton#category {
    background: #2a3342; font-weight: bold; font-size: 13px;
    color: #e8ecf4; padding: 9px 12px; border-radius: 10px;
}
QPushButton#category:hover { background: #37445c; }
QPushButton#item {
    background: #232b3a; padding: 6px 10px; border-radius: 8px;
}
QPushButton#item:hover { background: #37445c; }
QPushButton#itemAux {
    background: #232b3a; padding: 6px 8px; border-radius: 8px;
    text-align: center;
}
QPushButton#itemAux:hover { background: #37445c; }
QLineEdit {
    background: #141922; color: #e8ecf4; border: 1px solid #2a3342;
    border-radius: 10px; padding: 8px 12px; font-size: 12px;
}
QLineEdit:focus { border: 1px solid #2f6fed; }
QScrollArea { border: none; background: transparent; }
QCheckBox { color: #cfd8e8; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #2a3342; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; margin: -5px 0; background: #8fa3c4; border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #2f6fed; border-radius: 2px; }
QToolTip { background: #141922; color: #e8ecf4; border: 1px solid #37445c; }
"""


class Panel(QWidget):
    working = Signal(bool)  # para que la bolita cambie de estado
    speaking = Signal(bool)  # ídem, mientras el TTS habla
    fast_done = Signal(object)  # Result de un intent ejecutado en hilo
    token = Signal(str)  # streaming del LLM (emitida desde su hilo)
    llm_done = Signal(str, float)  # respuesta completa + latencia ms

    def __init__(self, router: Router, debug: bool = False, brain=None):
        super().__init__(
            None,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.router = router
        self.brain = brain
        self.debug = debug
        self._busy = False
        self._placeholder = False  # la respuesta muestra el "⏳…" inicial
        self._icons = QFileIconProvider()
        # emitir una señal Qt desde el hilo del TTS es seguro (conexión en cola)
        self.tts = TTS(router.config, on_speaking=self.speaking.emit)
        router.config["_tts"] = self.tts  # para las skills de voz
        self._build()
        self.fast_done.connect(self._on_fast_done)
        self.token.connect(self._on_token)
        self.llm_done.connect(self._on_llm_done)

    # -- construcción --------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QWidget(objectName="panel")
        frame.setStyleSheet(STYLE)
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        layout.addWidget(QLabel("✨ JARVIS", objectName="title"))

        # Acordeón: solo los grupos a la vista; uno abierto a la vez.
        menu = QWidget()
        menu_layout = QVBoxLayout(menu)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(4)
        self._open_cat: str | None = None
        self._sections: dict[str, tuple[QPushButton, QWidget]] = {}
        for cat_id, cat in self.router.categories.items():
            header = QPushButton(objectName="category")
            header.clicked.connect(lambda _=False, c=cat_id: self._toggle(c))
            menu_layout.addWidget(header)
            section = QWidget()
            section_layout = QVBoxLayout(section)
            section_layout.setContentsMargins(10, 0, 0, 4)
            section_layout.setSpacing(2)
            for intent in self.router.intents:
                if intent.category != cat_id:
                    continue
                button = QPushButton(self._button_text(intent))
                if intent.description:
                    button.setToolTip(intent.description)
                button.clicked.connect(lambda _=False, i=intent: self._on_intent(i))
                section_layout.addWidget(button)
            section.setVisible(False)
            menu_layout.addWidget(section)
            self._sections[cat_id] = (header, section)
        self._refresh_headers()
        menu_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(menu)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        # Voz del asistente: interruptor + volumen propio (no el del sistema).
        voz_row = QHBoxLayout()
        self.voz_check = QCheckBox("🔊 Voz")
        self.voz_check.setChecked(self.tts.enabled)
        self.voz_check.setToolTip("Leer las respuestas en voz alta")
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
        self.input = QLineEdit(placeholderText="Pídeme algo…")
        self.input.returnPressed.connect(self._on_text)
        layout.addWidget(self.input)

        self.response = QTextEdit(objectName="response")
        self.response.setReadOnly(True)  # seleccionable y con scroll
        self.response.setLineWrapMode(QTextEdit.WidgetWidth)
        self.response.setMinimumHeight(48)
        self.response.setMaximumHeight(130)
        self.response.hide()
        layout.addWidget(self.response)

        # Resultados clicables (archivos, carpetas, programas)
        self.items_box = QWidget()
        self.items_layout = QVBoxLayout(self.items_box)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(3)
        self.items_box.hide()
        layout.addWidget(self.items_box)

        self.latency = QLabel("", objectName="latency")
        self.latency.hide()
        layout.addWidget(self.latency)

        self.setFixedWidth(WIDTH)
        self.setMaximumHeight(MAX_HEIGHT)

    def _toggle(self, cat_id: str) -> None:
        opening = self._open_cat != cat_id
        for cid, (_, section) in self._sections.items():
            section.setVisible(opening and cid == cat_id)
        self._open_cat = cat_id if opening else None
        self._refresh_headers()

    def _refresh_headers(self) -> None:
        for cat_id, (header, _) in self._sections.items():
            cat = self.router.categories[cat_id]
            arrow = "▾" if self._open_cat == cat_id else "▸"
            header.setText(f"{cat['icon']}  {cat['label']}   {arrow}")

    @staticmethod
    def _button_text(intent) -> str:
        # "Abrir programa: {app}" → "Abrir programa…" (el valor se pide al pulsar)
        if intent.slot:
            base = intent.label.split("{")[0].rstrip(" :…")
            return base + "…"
        return intent.label

    # -- acciones ------------------------------------------------------------

    def _on_intent(self, intent) -> None:
        if self._busy:
            return
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
        self._start_busy(self._button_text(intent))
        threading.Thread(
            target=lambda: self.fast_done.emit(
                self.router.run_intent(intent.id, slot_value)
            ),
            daemon=True,
        ).start()

    def _on_text(self) -> None:
        text = self.input.text().strip()
        if not text or self._busy:
            return
        self.input.clear()
        self._start_busy(text)
        threading.Thread(target=self._text_worker, args=(text,), daemon=True).start()

    def _text_worker(self, text: str) -> None:
        result = self.router.handle(text)
        if result.matched or self.brain is None or not self.brain.enabled:
            self.fast_done.emit(result)
            return
        problema = self.brain.available()
        if problema:
            self.fast_done.emit(Result(problema, False, None, 0.0))
            return
        try:
            full = self.brain.chat(text, on_token=self.token.emit)
        except Exception as exc:
            full = f"Error del LLM: {exc.__class__.__name__}."
            self.token.emit(full)
        self.llm_done.emit(full, (time.perf_counter() - self._t0) * 1000)

    # -- feedback ------------------------------------------------------------

    def _start_busy(self, label: str) -> None:
        """Feedback inmediato: se ve al instante que está en ello."""
        self._busy = True
        self._t0 = time.perf_counter()
        self.working.emit(True)
        self._placeholder = True
        self.response.setPlainText(f"⏳ {label}…")
        self.response.show()
        self._clear_items()
        self.latency.hide()

    def _on_fast_done(self, result: Result) -> None:
        self._busy = False
        self._placeholder = False
        self.working.emit(False)
        self.response.setPlainText(result.text)
        self.response.show()
        self._show_items(result.items)
        if self.debug:
            self.latency.setText(
                f"{result.elapsed_ms:.1f} ms · intent={result.intent_id}"
            )
            self.latency.show()
        self.tts.speak(result.text)

    def _on_token(self, token: str) -> None:
        if self._placeholder:
            self.response.setPlainText("")
            self._placeholder = False
        cursor = self.response.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        self.response.ensureCursorVisible()

    def _on_llm_done(self, full: str, elapsed_ms: float) -> None:
        self._busy = False
        self._placeholder = False
        self.working.emit(False)
        if self.debug:
            self.latency.setText(f"{elapsed_ms:.0f} ms · slow path (LLM)")
            self.latency.show()
        self.tts.speak(full)

    # -- resultados clicables ------------------------------------------------

    def _clear_items(self) -> None:
        while self.items_layout.count():
            widget = self.items_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.items_box.hide()

    def _show_items(self, items) -> None:
        self._clear_items()
        if not items:
            return
        for item in items[:MAX_ITEMS]:
            row = QHBoxLayout()
            row.setSpacing(3)
            main = QPushButton(item.label, objectName="item")
            main.setIcon(self._icons.icon(QFileInfo(item.path)))
            main.setToolTip(item.path)
            main.clicked.connect(lambda _=False, i=item: self._open_item(i))
            row.addWidget(main, stretch=1)
            if item.kind in ("file", "folder"):
                aux = QPushButton("📂", objectName="itemAux")
                aux.setToolTip("Abrir la carpeta que lo contiene")
                aux.clicked.connect(lambda _=False, i=item: self._open_location(i))
                row.addWidget(aux)
            holder = QWidget()
            holder.setLayout(row)
            self.items_layout.addWidget(holder)
        self.items_box.show()

    def _open_item(self, item) -> None:
        try:
            os.startfile(item.path)
            self.response.setPlainText(f"Abriendo {item.label}.")
        except OSError:
            self.response.setPlainText(f"No he podido abrir {item.label}.")

    def _open_location(self, item) -> None:
        # Explorador con el elemento seleccionado
        subprocess.Popen(["explorer", "/select,", item.path])

    # -- voz -----------------------------------------------------------------

    def _on_voz_toggled(self, checked: bool) -> None:
        self.tts.set_enabled(checked)
        config_module.save_local({"tts": {"enabled": checked}})

    def _on_voz_volumen(self, value: int) -> None:
        self.tts.set_volume(value)
        config_module.save_local({"tts": {"volume": value}})

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
