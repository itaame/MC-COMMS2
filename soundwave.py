# soundwave.py
import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPainter, QColor, QPen

class SoundwaveWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 42)
        self.amplitude = 0.0
        self.frequency = 2.0
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_phase)
        self.timer.start(30)
        self.setStyleSheet("background: transparent;")

    def update_phase(self):
        self.phase += 0.17 * self.frequency
        self.update()

    def set_wave_params(self, amp, freq):
        amp = np.clip(amp, 0, 1)
        freq = np.clip(freq, 1.5, 6.0)
        self.amplitude = self.amplitude * 0.7 + amp * 0.3
        self.frequency = self.frequency * 0.7 + freq * 0.3
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h / 2

        # Transparent background (don't draw/fill anything)
        pen = QPen(QColor(0, 0, 0), 10)  # Black line
        painter.setPen(pen)

        N = 38
        freq = self.frequency
        amp = self.amplitude * (h / 2 - 7)
        points = []
        if amp < 1e-3:  # Practically zero
            # Draw a flat line (no frequency matters)
            painter.drawLine(0, int(mid_y), w, int(mid_y))
        else:
            for i in range(N + 1):
                x = i * w / N
                y = mid_y + amp * np.sin(2 * np.pi * freq * i / N + self.phase)
                points.append((x, y))
            for i in range(N):
                painter.drawLine(int(points[i][0]), int(points[i][1]), int(points[i+1][0]), int(points[i+1][1]))
        painter.end()
