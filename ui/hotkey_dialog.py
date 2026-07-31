import os
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from core.hotkey_listener import GlobalHotkeyListener

logger = logging.getLogger("WayVox.HotkeyDialog")

HOTKEY_OPTIONS = [
    ("F1", "KEY_F1"),
    ("F2", "KEY_F2"),
    ("F3", "KEY_F3"),
    ("F4", "KEY_F4"),
    ("F5", "KEY_F5"),
    ("F6", "KEY_F6"),
    ("F7", "KEY_F7"),
    ("F8", "KEY_F8"),
    ("F9", "KEY_F9"),
    ("F10", "KEY_F10"),
    ("F11", "KEY_F11"),
    ("F12", "KEY_F12"),
    ("Strg+M", "KEY_CTRL+KEY_M"),
    ("Strg+^", "KEY_CTRL+KEY_GRAVE"),
    ("Strg+<", "KEY_CTRL+KEY_102ND"),
]


def get_display_name_for_combo(combo_str: str) -> str:
    """Konvertiert eine Hotkey-Kombination in eine lesbare Anzeige (z. B. KEY_CTRL+KEY_GRAVE -> Strg+^)."""
    if not combo_str:
        return "Kein Hotkey"

    # Direct lookup
    for label, combo in HOTKEY_OPTIONS:
        if combo.upper() == combo_str.upper():
            return label

    # Normalized lookup
    hl = GlobalHotkeyListener()
    target_set = {hl._normalize_key(k) for k in combo_str.split("+")}
    for label, combo in HOTKEY_OPTIONS:
        opt_set = {hl._normalize_key(k) for k in combo.split("+")}
        if opt_set == target_set:
            return label

    # Fallback formatting
    parts = combo_str.split("+")
    formatted = []
    for p in parts:
        p_norm = hl._normalize_key(p)
        if p_norm == "KEY_CTRL":
            formatted.append("Strg")
        elif p_norm == "KEY_ALT":
            formatted.append("Alt")
        elif p_norm == "KEY_SHIFT":
            formatted.append("Shift")
        elif p_norm == "KEY_META":
            formatted.append("Super")
        elif p_norm == "KEY_GRAVE":
            formatted.append("^")
        elif p_norm == "KEY_102ND":
            formatted.append("<")
        elif p_norm.startswith("KEY_"):
            formatted.append(p_norm[4:])
        else:
            formatted.append(p)
    return "+".join(formatted)


class HotkeyDialog(QDialog):
    """Dialogfenster zur Auswahl und Anpassung des globalen Hotkeys."""

    def __init__(self, parent=None, current_combo: str = "KEY_F12"):
        super().__init__(parent)
        self.selected_combo = current_combo
        self.setWindowTitle("Hotkey anpassen")
        self.setFixedSize(380, 210)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "WayVox.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._setup_ui(current_combo)

    def _setup_ui(self, current_combo: str):
        # Dark Theme Styling (WayVox Aesthetic)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QComboBox {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                font-weight: bold;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E293B;
                color: #F8FAFC;
                selection-background-color: #3B82F6;
                border: 1px solid #475569;
                padding: 4px;
            }
            QPushButton#saveBtn {
                background-color: #2563EB;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#saveBtn:hover {
                background-color: #3B82F6;
            }
            QPushButton#cancelBtn {
                background-color: #475569;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #64748B;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Titel / Beschreibung
        label = QLabel("Wähle den Hotkey für die Sprachaufnahme:")
        label.setWordWrap(True)
        layout.addWidget(label)

        # Drop-Down (QComboBox)
        self.combo_box = QComboBox(self)

        # Current normalized key set
        hl = GlobalHotkeyListener()
        current_set = {hl._normalize_key(k) for k in current_combo.split("+")}

        selected_idx = 0
        for idx, (label_text, combo_str) in enumerate(HOTKEY_OPTIONS):
            self.combo_box.addItem(label_text, combo_str)
            opt_set = {hl._normalize_key(k) for k in combo_str.split("+")}
            if opt_set == current_set:
                selected_idx = idx

        self.combo_box.setCurrentIndex(selected_idx)
        layout.addWidget(self.combo_box)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        cancel_btn = QPushButton("Abbrechen", self)
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Speichern", self)
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _on_save(self):
        self.selected_combo = self.combo_box.currentData()
        self.accept()

    def get_selected_hotkey(self) -> str:
        return self.selected_combo
