"""Panel lanzador de JARVIS, estilo Spotlight / PowerToys Run.

Barra de búsqueda grande arriba y una única lista debajo que va cambiando:
categorías → acciones del grupo → sugerencias mientras escribes → resultados
clicables. Tamaño fijo y centrado en pantalla: nada se solapa ni se corta.

No sabe nada de skills: todo pasa por el router. Las skills corren en un
hilo: la UI nunca se congela y siempre hay feedback inmediato.
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
    QComboBox,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from rapidfuzz import fuzz

from jarvis import config as config_module
from jarvis.audio.tts import TTS
from jarvis.router import Result, Router

WIDTH = 480
HEIGHT = 580
MAX_ITEMS = 8
MAX_SUGGESTIONS = 7
SUGGESTION_CUTOFF = 55

# Acciones que se pintan como barra de control compacta, no como filas
CONTROL_BARS = (
    ("anterior", "play_pausa", "siguiente"),
    ("volumen_bajar", "silenciar", "volumen_subir"),
)
CONTROL_ICONS = {
    "anterior": "⏮",
    "play_pausa": "⏯",
    "siguiente": "⏭",
    "volumen_bajar": "🔉",
    "silenciar": "🔇",
    "volumen_subir": "🔊",
}

STYLE = """
QWidget#panel {
    background: #1b202b; border-radius: 16px;
    border: 1px solid #2e3746;
}
QLabel { color: #e8ecf4; }
QLabel#hint { color: #66738a; font-size: 12px; padding-left: 4px; }
QLabel#latency { color: #66738a; font-size: 11px; padding-left: 4px; }
QLineEdit#search {
    background: #232b3a; color: #f0f4fb; border: 1px solid #313c50;
    border-radius: 12px; padding: 12px 16px; font-size: 16px;
}
QLineEdit#search:focus { border: 1px solid #3f7cff; }
QLineEdit#search:disabled { color: #66738a; background: #1e2531; }
QWidget#slotBox { background: #1f2a3f; border-radius: 12px; }
QLabel#slotLabel { color: #9db8e8; font-size: 12px; padding: 2px 4px; }
QLineEdit#slotInput {
    background: #232b3a; color: #f0f4fb; border: 1px solid #3f7cff;
    border-radius: 10px; padding: 9px 12px; font-size: 14px;
}
QTextEdit#response {
    background: #232b3a; color: #e8ecf4; border: none;
    border-radius: 12px; padding: 8px; font-size: 13px;
}
QPushButton#row, QPushButton#subrow, QPushButton#rowAux {
    background: transparent; color: #dbe3f0; border: none;
    border-radius: 10px; padding: 10px 12px; text-align: left; font-size: 14px;
}
QPushButton#row:hover, QPushButton#subrow:hover {
    background: #2c374b; color: #ffffff;
}
QPushButton#subrow {
    padding: 8px 12px 8px 38px; font-size: 13px; color: #c3cddd;
    background: #202836; border-radius: 8px;
}
QPushButton#rowAux { padding: 10px 10px; text-align: center; }
QPushButton#rowAux:hover { background: #2c374b; }
QPushButton#ctrl {
    background: #232b3a; color: #dbe3f0; border: none; border-radius: 10px;
    padding: 8px; font-size: 17px; text-align: center;
}
QPushButton#ctrl:hover { background: #37445c; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #313c50; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { color: #aeb9cc; font-size: 12px; }
QComboBox {
    background: #232b3a; color: #dbe3f0; border: 1px solid #313c50;
    border-radius: 8px; padding: 4px 10px; font-size: 12px;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: #232b3a; color: #dbe3f0; border: 1px solid #313c50;
    selection-background-color: #2c374b;
}
QSlider::groove:horizontal { height: 4px; background: #2a3342; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; margin: -5px 0; background: #8fa3c4; border-radius: 6px;
}
QSlider::sub-page:horizontal { background: #3f7cff; border-radius: 2px; }
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
        self._pending_intent = None  # intent esperando su valor en la barra
        self._current_cat = None  # grupo abierto: se vuelve a él tras la acción
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
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        self.input = QLineEdit(objectName="search")
        self.input.setPlaceholderText("🔍  Pídeme algo o elige una acción…")
        self.input.returnPressed.connect(self._on_text)
        self.input.textChanged.connect(self._on_typing)
        layout.addWidget(self.input)

        self.hint = QLabel("", objectName="hint")
        layout.addWidget(self.hint)

        # Input independiente para pedir un valor ("¿Qué programa?"…):
        # aparece solo en modo captura, con su propio estilo.
        self.slot_box = QWidget(objectName="slotBox")
        slot_layout = QVBoxLayout(self.slot_box)
        slot_layout.setContentsMargins(10, 8, 10, 10)
        slot_layout.setSpacing(4)
        self.slot_label = QLabel("", objectName="slotLabel")
        self.slot_label.setWordWrap(True)
        slot_layout.addWidget(self.slot_label)
        self.slot_input = QLineEdit(objectName="slotInput")
        self.slot_input.returnPressed.connect(
            lambda: self._submit_slot(self.slot_input.text())
        )
        slot_layout.addWidget(self.slot_input)
        self.slot_box.hide()
        layout.addWidget(self.slot_box)

        self.response = QTextEdit(objectName="response")
        self.response.setReadOnly(True)  # seleccionable y con scroll
        self.response.setLineWrapMode(QTextEdit.WidgetWidth)
        self.response.setMinimumHeight(44)
        self.response.setMaximumHeight(120)
        self.response.hide()
        layout.addWidget(self.response)

        # La lista única: categorías / acciones / sugerencias / resultados
        rows_host = QWidget()
        self.rows = QVBoxLayout(rows_host)
        self.rows.setContentsMargins(0, 0, 4, 0)
        self.rows.setSpacing(2)
        self.rows.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_host)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        self.latency = QLabel("", objectName="latency")
        self.latency.hide()
        layout.addWidget(self.latency)

        # Voz del asistente: interruptor + selector de voz + volumen propio.
        voz_row = QHBoxLayout()
        self.voz_check = QCheckBox("🔊")
        self.voz_check.setChecked(self.tts.enabled)
        self.voz_check.setToolTip("Leer las respuestas en voz alta")
        self.voz_check.toggled.connect(self._on_voz_toggled)
        voz_row.addWidget(self.voz_check)
        self.voz_combo = QComboBox()
        self.voz_combo.setToolTip("Voz del asistente — al cambiarla la oyes")
        for voice in TTS.installed_voices():
            self.voz_combo.addItem(self._voice_label(voice), voice)
        index = self.voz_combo.findData(self.tts.voice_name)
        if index >= 0:
            self.voz_combo.setCurrentIndex(index)
        self.voz_combo.currentIndexChanged.connect(self._on_voz_cambiada)
        voz_row.addWidget(self.voz_combo)
        self.voz_slider = QSlider(Qt.Horizontal)
        self.voz_slider.setRange(0, 100)
        self.voz_slider.setValue(self.tts.volume)
        self.voz_slider.setToolTip("Volumen de la voz del asistente")
        self.voz_slider.valueChanged.connect(self._on_voz_volumen)
        voz_row.addWidget(self.voz_slider, stretch=1)
        layout.addLayout(voz_row)

        self.setFixedSize(WIDTH, HEIGHT)
        self._show_categories()

    # -- la lista ------------------------------------------------------------

    def _clear_rows(self) -> None:
        while self.rows.count() > 1:  # el stretch final se queda
            widget = self.rows.takeAt(0).widget()
            if widget:
                widget.deleteLater()

    def _add_row(self, text: str, on_click, icon=None, tooltip: str = "",
                 aux: tuple | None = None, kind: str = "row") -> None:
        """Una fila de la lista; aux = (emoji, tooltip, callback) opcional."""
        main = QPushButton(text, objectName=kind)
        if icon is not None:
            main.setIcon(icon)
        if tooltip:
            main.setToolTip(tooltip)
        main.clicked.connect(lambda _=False: on_click())
        if aux is None:
            self.rows.insertWidget(self.rows.count() - 1, main)
            return
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(main, stretch=1)
        emoji, aux_tip, aux_cb = aux
        aux_btn = QPushButton(emoji, objectName="rowAux")
        aux_btn.setToolTip(aux_tip)
        aux_btn.clicked.connect(lambda _=False: aux_cb())
        row.addWidget(aux_btn)
        self.rows.insertWidget(self.rows.count() - 1, holder)

    def _show_categories(self) -> None:
        self._clear_rows()
        self._view = "categories"
        self._current_cat = None
        self.hint.setText("Grupos de acciones — o escribe directamente")
        for cat_id, cat in self.router.categories.items():
            self._add_row(
                f"{cat['icon']}   {cat['label']}",
                lambda c=cat_id: self._show_category(c),
            )

    def _show_category(self, cat_id: str) -> None:
        self._clear_rows()
        self._view = "category"
        self._current_cat = cat_id
        cat = self.router.categories[cat_id]
        self.hint.setText(f"{cat['icon']} {cat['label']} — Esc para volver")
        self._add_row("←   Volver a los grupos", self._show_categories)
        del_grupo = [i for i in self.router.intents if i.category == cat_id]
        ids = {i.id for i in del_grupo}
        pintados: set[str] = set()
        for intent in del_grupo:
            if intent.id in pintados:
                continue
            barra = next(
                (b for b in CONTROL_BARS if intent.id in b and set(b) <= ids), None
            )
            if barra:
                self._add_control_bar([i for j in barra
                                       for i in del_grupo if i.id == j])
                pintados.update(barra)
                continue
            self._add_row(
                self._button_text(intent),
                lambda i=intent: self._on_intent(i),
                tooltip=intent.description,
                kind="subrow",
            )

    def _add_control_bar(self, intents) -> None:
        """Fila de botones compactos tipo reproductor (⏮ ⏯ ⏭ / 🔉 🔇 🔊)."""
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)
        for intent in intents:
            button = QPushButton(CONTROL_ICONS.get(intent.id, "•"), objectName="ctrl")
            button.setToolTip(intent.label + (
                f" — {intent.description}" if intent.description else ""))
            button.clicked.connect(lambda _=False, i=intent: self._on_intent(i))
            row.addWidget(button, stretch=1)
        self.rows.insertWidget(self.rows.count() - 1, holder)

    def _on_typing(self, text: str) -> None:
        if self._busy or self._pending_intent is not None:
            return
        text = text.strip()
        if not text:
            self._show_categories()
            return
        self._show_suggestions(text)

    def _show_suggestions(self, query: str) -> None:
        self._clear_rows()
        self._view = "suggestions"
        self._current_cat = None
        self.hint.setText("Sugerencias — Enter para enviar tal cual")
        scored = []
        for intent in self.router.intents:
            score = fuzz.WRatio(query.lower(), intent.label.lower())
            for pattern in intent.patterns:
                base = pattern.split("{")[0].strip()
                if base:
                    score = max(score, fuzz.WRatio(query.lower(), base))
            if score >= SUGGESTION_CUTOFF:
                scored.append((score, intent))
        scored.sort(key=lambda pair: -pair[0])
        for _, intent in scored[:MAX_SUGGESTIONS]:
            cat = self.router.categories[intent.category]
            self._add_row(
                f"{cat['icon']}   {self._button_text(intent)}",
                lambda i=intent: self._on_intent(i),
                tooltip=intent.description,
            )
        if self.brain is not None and self.brain.enabled:
            self._add_row(
                f"🤖   Preguntar a JARVIS: “{query}”",
                self._on_text,
            )

    def _show_items(self, items) -> None:
        self._clear_rows()
        if not items:
            return
        self._view = "items"
        self.hint.setText("Resultados — click para abrir, Esc para volver")
        self._add_row("←   Volver", self._show_categories)
        for item in items[:MAX_ITEMS]:
            aux = None
            if item.kind in ("file", "folder"):
                aux = ("📂", "Abrir la carpeta que lo contiene",
                       lambda i=item: self._open_location(i))
            self._add_row(
                item.label,
                lambda i=item: self._open_item(i),
                icon=self._icons.icon(QFileInfo(item.path)),
                tooltip=item.path,
                aux=aux,
            )

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
        if intent.slot:
            self._enter_slot_mode(intent)
            return
        self._run_intent(intent, None)

    def _enter_slot_mode(self, intent) -> None:
        """El valor se pide en su propio input, bajo la barra principal."""
        self._pending_intent = intent
        self._view = "slot"
        self.input.setEnabled(False)  # se ve claro qué input toca usar
        prompt = intent.description or f"¿Qué {intent.slot}?"
        self.slot_label.setText(f"✏️  {self._button_text(intent)} — {prompt}")
        self.slot_input.clear()
        self.slot_box.show()
        self.hint.setText("Escribe y pulsa Enter · Esc cancela")
        self._clear_rows()
        if intent.options_from:
            # Las opciones salen de config.yaml (p. ej. app_profiles);
            # también se puede escribir otra cosa a mano.
            for opcion in self.router.config.get(intent.options_from, {}):
                self._add_row(
                    f"▸   {opcion}",
                    lambda o=opcion: self._submit_slot(o),
                    kind="subrow",
                )
        self._add_row("←   Cancelar", self._cancel_slot)
        self.slot_input.setFocus()

    def _submit_slot(self, value: str) -> None:
        intent = self._pending_intent
        self._exit_slot_mode()
        if intent is not None and value.strip():
            self._run_intent(intent, value.strip())

    def _cancel_slot(self) -> None:
        self._exit_slot_mode()
        self._show_categories()

    def _exit_slot_mode(self) -> None:
        self._pending_intent = None
        self.slot_box.hide()
        self.slot_input.clear()
        self.input.setEnabled(True)
        self.input.setFocus()

    def _run_intent(self, intent, slot_value: str | None) -> None:
        self._start_busy(self._button_text(intent))
        threading.Thread(
            target=lambda: self.fast_done.emit(
                self.router.run_intent(intent.id, slot_value)
            ),
            daemon=True,
        ).start()

    def _on_text(self) -> None:
        text = self.input.text().strip()
        if self._busy or not text:
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
        self._set_response(text=f"⏳ {label}…")
        self._clear_rows()
        self.latency.hide()

    def _set_response(self, text: str | None = None, html: str | None = None) -> None:
        """Pinta la respuesta y ajusta la altura al contenido (sin hueco)."""
        if html is not None:
            self.response.setHtml(f"<div align='center'>{html}</div>")
        else:
            self.response.setPlainText(text or "")
        self.response.show()
        doc = self.response.document()
        doc.setTextWidth(self.response.viewport().width() or WIDTH - 64)
        alto = int(doc.size().height()) + 14
        self.response.setFixedHeight(max(44, min(alto, 240)))

    def _on_fast_done(self, result: Result) -> None:
        self._busy = False
        self._placeholder = False
        self.working.emit(False)
        if result.html:
            self._set_response(html=result.html)
        else:
            self._set_response(text=result.text)
        if result.items:
            self._show_items(result.items)
        elif self._current_cat:  # quedarse donde estaba el usuario
            self._show_category(self._current_cat)
        else:
            self._show_categories()
        if self.debug:
            self.latency.setText(
                f"{result.elapsed_ms:.1f} ms · intent={result.intent_id}"
            )
            self.latency.show()
        # speak="" = acción evidente, no se dicta; None = se lee el texto
        hablado = result.speak if result.speak is not None else result.text
        if hablado:
            self.tts.speak(hablado)

    def _on_token(self, token: str) -> None:
        if self._placeholder:
            self.response.setPlainText("")
            self._placeholder = False
        cursor = self.response.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(token)
        alto = int(self.response.document().size().height()) + 14
        self.response.setFixedHeight(max(44, min(alto, 240)))
        self.response.ensureCursorVisible()

    def _on_llm_done(self, full: str, elapsed_ms: float) -> None:
        self._busy = False
        self._placeholder = False
        self.working.emit(False)
        self._show_categories()
        if self.debug:
            self.latency.setText(f"{elapsed_ms:.0f} ms · slow path (LLM)")
            self.latency.show()
        self.tts.speak(full)

    # -- resultados clicables ------------------------------------------------

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

    @staticmethod
    def _voice_label(voice: str) -> str:
        # "es_ES-davefx-medium" → "Davefx (es-ES)"; "kokoro:dora" → "Dora (Kokoro)"
        if voice.startswith("kokoro:"):
            return f"{voice.split(':', 1)[1].capitalize()} (Kokoro)"
        try:
            region, nombre, _calidad = voice.split("-", 2)
            return f"{nombre.capitalize()} ({region.replace('_', '-')})"
        except ValueError:
            return voice

    def _on_voz_cambiada(self, index: int) -> None:
        voice = self.voz_combo.itemData(index)
        if not voice or voice == self.tts.voice_name:
            return
        self.tts.set_voice(voice)
        config_module.save_local({"tts": {"voice": voice}})
        # se oye al momento aunque la voz esté desactivada: así se elige
        self.tts.preview("Hola, así sueno yo. ¿Qué te parece?")

    def _on_voz_toggled(self, checked: bool) -> None:
        self.tts.set_enabled(checked)
        config_module.save_local({"tts": {"enabled": checked}})

    def _on_voz_volumen(self, value: int) -> None:
        self.tts.set_volume(value)
        config_module.save_local({"tts": {"volume": value}})

    # -- posición / teclado --------------------------------------------------

    def show_near(self, ball_geometry) -> None:
        """Centrado en la pantalla donde vive la bolita, estilo lanzador."""
        # reflejar cambios hechos por comando ("desactiva la voz")
        self.voz_check.blockSignals(True)
        self.voz_check.setChecked(self.tts.enabled)
        self.voz_check.blockSignals(False)
        area = self.screen().availableGeometry()
        x = area.center().x() - self.width() // 2
        y = area.top() + int(area.height() * 0.16)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def keyPressEvent(self, event) -> None:
        # Esc retrocede un nivel; en la vista raíz, cierra el panel.
        if event.key() == Qt.Key_Escape:
            if self._pending_intent is not None:
                self._cancel_slot()
            elif self.input.text():
                self.input.clear()  # textChanged → vuelve a los grupos
            elif self._view != "categories":
                self.response.hide()
                self.latency.hide()
                self._show_categories()
            else:
                self.hide()
        else:
            super().keyPressEvent(event)
