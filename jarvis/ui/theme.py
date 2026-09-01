"""Temas del panel: oscuro, claro o el del sistema (config ui.theme).

La hoja de estilos es una plantilla con tokens; cada tema es una paleta.
El tema del sistema se lee del registro (AppsUseLightTheme).
"""

from __future__ import annotations

import winreg
from string import Template

DARK = {
    "bg": "#1b202b", "border": "#2e3746",
    "card": "#232b3a", "cardborder": "#313c50",
    "subtle": "#202836", "control": "#2a3444",
    "hover": "#2c374b", "hover2": "#37445c",
    "accent": "#3f7cff",
    "text": "#e8ecf4", "textstrong": "#f0f4fb",
    "rowtext": "#dbe3f0", "subrowtext": "#c3cddd",
    "soft": "#aeb9cc", "muted": "#66738a",
    "slotbg": "#1f2a3f", "slotlabel": "#9db8e8",
    "scrollbar": "#313c50", "disabledbg": "#1e2531",
    "link": "#6fa8ff",
}

LIGHT = {
    "bg": "#f2f5fa", "border": "#d5dce6",
    "card": "#ffffff", "cardborder": "#c9d2e0",
    "subtle": "#e9edf4", "control": "#dfe6f0",
    "hover": "#dce5f2", "hover2": "#cfdaee",
    "accent": "#2c66d9",
    "text": "#202a3c", "textstrong": "#101827",
    "rowtext": "#2c3850", "subrowtext": "#44506a",
    "soft": "#5a6a8a", "muted": "#7a889e",
    "slotbg": "#e6eefc", "slotlabel": "#2c66d9",
    "scrollbar": "#c2cddc", "disabledbg": "#e8ecf2",
    "link": "#2c66d9",
}

# colores usados en el HTML de las tarjetas (tiempo, hora...) → claro
HTML_LIGHT = {
    "#f0f4fb": "#101827",
    "#e8ecf4": "#202a3c",
    "#c3cddd": "#44506a",
    "#8fa3c4": "#5a6a8a",
    "#6fa8ff": "#2c66d9",
}

TEMPLATE = Template("""
QWidget#panel { background: $bg; border-radius: 16px; border: 1px solid $border; }
QLabel { color: $text; }
QLabel#hint { color: $muted; font-size: 12px; padding-left: 4px; }
QLabel#latency { color: $muted; font-size: 11px; padding-left: 4px; }
QLineEdit#search {
    background: $card; color: $textstrong; border: 1px solid $cardborder;
    border-radius: 12px; padding: 12px 16px; font-size: 16px;
}
QLineEdit#search:focus { border: 1px solid $accent; }
QLineEdit#search:disabled { color: $muted; background: $disabledbg; }
QWidget#slotBox { background: $slotbg; border-radius: 12px; }
QLabel#slotLabel { color: $slotlabel; font-size: 12px; padding: 2px 4px; }
QLineEdit#slotInput {
    background: $card; color: $textstrong; border: 1px solid $accent;
    border-radius: 10px; padding: 9px 12px; font-size: 14px;
}
QTextEdit#response {
    background: $card; color: $text; border: none;
    border-radius: 12px; padding: 8px; font-size: 13px;
}
QPushButton#row, QPushButton#subrow, QPushButton#rowAux {
    background: transparent; color: $rowtext; border: none;
    border-radius: 10px; padding: 10px 12px; text-align: left; font-size: 14px;
}
QPushButton#row:hover, QPushButton#subrow:hover { background: $hover; color: $textstrong; }
QPushButton#subrow {
    padding: 8px 12px 8px 38px; font-size: 13px; color: $subrowtext;
    background: $subtle; border-radius: 8px;
}
QPushButton#rowAux { padding: 10px 10px; text-align: center; }
QPushButton#rowAux:hover { background: $hover; }
QWidget#console { background: $subtle; border-radius: 12px; }
QPushButton#ctrl {
    background: $control; color: $rowtext; border: none; border-radius: 18px;
    min-width: 36px; max-width: 44px; min-height: 36px; text-align: center;
}
QPushButton#ctrl:hover { background: $accent; color: #ffffff; }
QPushButton#step {
    background: $card; color: $rowtext; border: none; border-radius: 8px;
    min-width: 24px; max-width: 24px; min-height: 24px; font-size: 14px;
    text-align: center; padding: 0;
}
QPushButton#step:hover { background: $hover2; }
QPushButton#action {
    background: $control; color: $rowtext; border: none; border-radius: 8px;
    padding: 7px 14px; font-size: 12px; text-align: center;
}
QPushButton#action:hover { background: $accent; color: #ffffff; }
QKeySequenceEdit {
    background: $card; color: $rowtext; border: 1px solid $cardborder;
    border-radius: 8px; padding: 4px 8px; font-size: 12px;
}
QLineEdit#vozPct {
    background: $card; color: $rowtext; border: 1px solid $cardborder;
    border-radius: 8px; padding: 2px; font-size: 12px;
}
QLineEdit#vozPct:focus { border: 1px solid $accent; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: $scrollbar; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { color: $soft; font-size: 12px; }
QComboBox {
    background: $card; color: $rowtext; border: 1px solid $cardborder;
    border-radius: 8px; padding: 4px 10px; font-size: 12px;
}
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: $card; color: $rowtext; border: 1px solid $cardborder;
    selection-background-color: $hover;
}
QSlider::groove:horizontal { height: 4px; background: $control; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; margin: -5px 0; background: $soft; border-radius: 6px;
}
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QToolTip { background: $card; color: $text; border: 1px solid $hover2; }
""")


def system_prefers_light() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return bool(winreg.QueryValueEx(key, "AppsUseLightTheme")[0])
    except OSError:
        return False


def effective(name: str) -> str:
    """'system'/'dark'/'light' → 'dark' o 'light'."""
    name = (name or "system").lower()
    if name == "system":
        return "light" if system_prefers_light() else "dark"
    return "light" if name == "light" else "dark"


def stylesheet(name: str) -> str:
    palette = LIGHT if effective(name) == "light" else DARK
    return TEMPLATE.substitute(palette)


def adapt_html(html: str, name: str) -> str:
    """Colores del HTML de las tarjetas adaptados al tema claro."""
    if effective(name) != "light":
        return html
    for oscuro, claro in HTML_LIGHT.items():
        html = html.replace(oscuro, claro)
    return html
