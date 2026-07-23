import enum
import math
import logging
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QRectF
from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QConicalGradient

logger = logging.getLogger("WayVox.CircleOverlay")

class AppState(enum.Enum):
    IDLE = 1          # Grau / Blau: Bereit
    LISTENING = 2     # Rot / Pulsierend: Aufnahme läuft
    TRANSCRIBING = 3  # Gelb / Animiert: Verarbeiten via CUDA
    SUCCESS = 4       # Grün: Erfolgreich eingefügt
    ERROR = 5         # Rot-Blinkend: Fehler

class CircleOverlay(QWidget):
    """Kreisförmiges, transparentes 'Always-on-Top' Overlay-Fenster für Wayland / KDE Plasma 6."""

    clicked = Signal()
    quit_requested = Signal()

    def __init__(self, size: int = 120, border_width: int = 6, 
                 pos_x: int = 100, pos_y: int = 100, show_label: bool = True):
        super().__init__()
        self.overlay_size = size
        self.border_width = border_width
        self.show_label = show_label
        self.current_state = AppState.IDLE

        # Animationsvariablen
        self._anim_angle = 0
        self._pulse_alpha = 1.0
        self._pulse_growing = False
        self._blink_visible = True

        # Dragging Variablen
        self._drag_start_global = QPoint()
        self._drag_start_window = QPoint()
        self._is_dragging = False

        self._init_ui(pos_x, pos_y)
        self._setup_animation_timer()

    def _init_ui(self, x: int, y: int):
        """Initialisiert Fenster-Eigenschaften & Wayland-Overlay Flags."""
        # WICHTIG: Qt.WindowDoesNotAcceptFocus verhindert Fokus-Diebstahl beim Klick unter Wayland
        flags = (
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(self.overlay_size, self.overlay_size)
        self.move(x, y)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Klick oder Alt+Leertaste zum Starten/Stoppen der Sprachaufnahme")

    def _setup_animation_timer(self):
        """Timer für flüssige 60FPS UI-Animationen (Rotations-Spinner, Pulse, Blink)."""
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_animation)
        self.anim_timer.start(20)  # 50 Hz

        # Auto-Reset Timer für Feedback-Zustände (SUCCESS / ERROR)
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self._reset_to_idle)

    def set_state(self, state: AppState, message: str = None):
        """Wechselt den visuellen Status des Overlays."""
        logger.info(f"Overlay Statuswechsel: {self.current_state.name} -> {state.name}")
        self.current_state = state
        self._anim_angle = 0

        if state == AppState.SUCCESS:
            self.reset_timer.start(1500)  # 1.5s Feedback
        elif state == AppState.ERROR:
            self.reset_timer.start(2500)  # 2.5s Fehleranzeige
        else:
            self.reset_timer.stop()

        self.update()

    def _reset_to_idle(self):
        """Setzt das UI auf den Idle-Zustand zurück."""
        self.set_state(AppState.IDLE)

    def _update_animation(self):
        """Aktualisiert Animationsparameter basierend auf dem aktuellen Status."""
        if self.current_state == AppState.TRANSCRIBING:
            self._anim_angle = (self._anim_angle + 6) % 360
            self.update()
        elif self.current_state == AppState.LISTENING:
            # Pulsieren der Deckkraft / Rahmendicke
            if self._pulse_growing:
                self._pulse_alpha += 0.04
                if self._pulse_alpha >= 1.0:
                    self._pulse_alpha = 1.0
                    self._pulse_growing = False
            else:
                self._pulse_alpha -= 0.04
                if self._pulse_alpha <= 0.3:
                    self._pulse_alpha = 0.3
                    self._pulse_growing = True
            self.update()
        elif self.current_state == AppState.ERROR:
            # Rot Blinken
            self._anim_angle = (self._anim_angle + 10) % 360
            if self._anim_angle < 180:
                self._blink_visible = True
            else:
                self._blink_visible = False
            self.update()

    def paintEvent(self, event):
        """Verantwortlich für das Zeichnen des runden transparenten Fensters."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.border_width / 2, self.border_width / 2,
                      self.width() - self.border_width, self.height() - self.border_width)

        # 1. Dunkler halbtransparenter Hintergrundkreis (Glassmorphism)
        bg_color = QColor(15, 23, 42, 220)  # Dark Slate Blue
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect)

        # 2. Zeichnen des Randes je nach Status
        self._draw_border(painter, rect)

        # 3. Status-Text / Icon im Zentrum zeichnen
        if self.show_label:
            self._draw_center_text(painter)

    def _draw_border(self, painter: QPainter, rect: QRectF):
        """Zeichnet den statusabhängigen animierten Rand."""
        if self.current_state == AppState.IDLE:
            # Blau / Grau eleganter Rand
            pen = QPen(QColor(59, 130, 246, 200), self.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

        elif self.current_state == AppState.LISTENING:
            # Rot / Pulsierender Rand
            alpha = int(255 * self._pulse_alpha)
            pen = QPen(QColor(239, 68, 68, alpha), self.border_width + (1 - self._pulse_alpha) * 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

        elif self.current_state == AppState.TRANSCRIBING:
            # Gelb / Animierter Rotations-Gradient (Spinner)
            gradient = QConicalGradient(rect.center(), self._anim_angle)
            gradient.setColorAt(0.0, QColor(245, 158, 11, 255))
            gradient.setColorAt(0.5, QColor(252, 211, 77, 100))
            gradient.setColorAt(1.0, QColor(245, 158, 11, 255))

            pen = QPen(QBrush(gradient), self.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

        elif self.current_state == AppState.SUCCESS:
            # Grün leuchtender Rand
            pen = QPen(QColor(16, 185, 129, 255), self.border_width + 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

        elif self.current_state == AppState.ERROR:
            # Rot-Blinkender Rand
            color = QColor(220, 38, 38, 255) if self._blink_visible else QColor(100, 20, 20, 100)
            pen = QPen(color, self.border_width)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

    def _draw_center_text(self, painter: QPainter):
        """Zeichnet den Statustext in das Zentrum des Kreises."""
        font = QFont("Sans-Serif", 9, QFont.Weight.Bold)
        painter.setFont(font)

        if self.current_state == AppState.IDLE:
            text = "Bereit"
            color = QColor(226, 232, 240)
        elif self.current_state == AppState.LISTENING:
            text = "Aufnahme..."
            color = QColor(248, 113, 113)
        elif self.current_state == AppState.TRANSCRIBING:
            text = "Verarbeitung..."
            color = QColor(253, 224, 71)
        elif self.current_state == AppState.SUCCESS:
            text = "Eingefügt!"
            color = QColor(110, 231, 183)
        elif self.current_state == AppState.ERROR:
            text = "Fehler!"
            color = QColor(252, 165, 165)

        painter.setPen(color)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, event):
        """Unterstützt Drag-and-Drop Verschieben sowie Klick-Erkennung."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_start_window = self.pos()
            self._is_dragging = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        """Verschiebt das Overlay sanft auf dem Bildschirm."""
        if event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_start_global
            if delta.manhattanLength() > 3:
                self._is_dragging = True
                self.move(self._drag_start_window + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        """Löst den Klick-Event aus, wenn nicht gezogen wurde."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._is_dragging:
                logger.info("Overlay per Mäuseklick aktiviert/deaktiviert.")
                self.clicked.emit()
            self._is_dragging = False
            event.accept()

    def _show_context_menu(self, pos):
        """Kontextmenü beim Rechtsklick."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #1E293B; color: white; border: 1px solid #475569; } QMenu::item:selected { background-color: #3B82F6; }")
        
        idle_action = menu.addAction("Reset Status")
        menu.addSeparator()
        quit_action = menu.addAction("Beenden")
        
        action = menu.exec(pos)
        if action == quit_action:
            self.quit_requested.emit()
        elif action == idle_action:
            self.set_state(AppState.IDLE)
