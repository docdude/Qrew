# Qrew_gridwidget.py

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QPointF, QLineF, QSize
import sys

class GridWidget(QtWidgets.QWidget):
    _P = {}
    _P[1] = dict(coords={0: (0, 0)}, edges=[])
    _P[2] = dict(coords={1: (0, -1), 0: (0, 0)}, edges=[(1, 0)])
    _P[3] = dict(coords={2: (-1, 0), 0: (0, 0), 1: (1, 0)}, edges=[(2, 0), (0, 1)])
    _P[4] = dict(coords={3: (0, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0)}, edges=[(3, 0), (2, 0), (0, 1)])
    _P[5] = dict(coords={3: (0, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0), 4: (0, 1)}, edges=[(3, 0), (2, 0), (0, 1), (0, 4)])
    _P[6] = dict(coords={3: (-1, -1), 4: (0, -1), 5: (1, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0)}, edges=[(3, 2), (4, 0), (5, 1), (2, 0), (0, 1)])
    _P[7] = dict(coords={3: (-1, -1), 4: (1, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0), 5: (-1, 1), 6: (1, 1)}, edges=[(3, 2), (2, 5), (4, 1), (1, 6), (2, 0), (0, 1)])
    _P[8] = dict(coords={3: (-1, -1), 4: (0, -1), 5: (1, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0), 6: (-1, 1), 7: (1, 1)}, edges=[(3, 2), (5, 1), (4, 0), (2, 0), (0, 1), (2, 6), (1, 7)])
    _P[9] = dict(coords={3: (-1, -1), 4: (0, -1), 5: (1, -1), 2: (-1, 0), 0: (0, 0), 1: (1, 0), 6: (-1, 1), 7: (0, 1), 8: (1, 1)}, edges=[(3, 2), (4, 0), (5, 1), (2, 0), (0, 1), (2, 6), (0, 7), (1, 8)])

    def __init__(self, positions=9, current_pos=0, parent=None):
        super().__init__(parent)
        if positions not in self._P:
            raise ValueError('positions must be 1-9')
        self.positions = positions
        self.current_pos = current_pos
        self.flash_on = False
        self.horizontal_stretch = 1.0
        self.coords_def = self._P[positions]['coords']
        self.edges_def = self._P[positions]['edges']

    def set_current_pos(self, idx: int):
        self.current_pos = idx
        self.update()

    def set_flash(self, state: bool):
        self.flash_on = state
        self.update()

    def set_horizontal_stretch(self, stretch: float):
        self.horizontal_stretch = stretch
        self.update()

    def paintEvent(self, event):
        if not self.isVisible():          # <-- guard ①
            return
        if getattr(self, "_painting", False):
            return                        # <-- guard ②   (re-entrancy blocker)
        self._painting = True
        try:
            p = QtGui.QPainter(self)
            ...
        finally:
            p.end()
            self._painting = False

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        
        center_x = self.width() / 2
        center_y = self.height() / 2
        
        # Calculate actual extents
        max_x = 0
        max_y = 0
        for (x, y) in self.coords_def.values():
            max_x = max(max_x, abs(x))
            max_y = max(max_y, abs(y))
        
        # Use the maximum dimension to ensure consistent scaling across all patterns
        max_dimension = max(max_x, max_y)
        if max_dimension == 0:
            max_dimension = 0.5
        
        margin = 25
        available_width = self.width() - 2 * margin
        available_height = self.height() - 2 * margin
        
        # Base scale using the maximum dimension - this ensures all patterns scale consistently
        base_scale = min(available_width, available_height) / (2 * max_dimension)
        
        # Apply horizontal stretch
        final_scale_x = base_scale * self.horizontal_stretch
        final_scale_y = base_scale
        
        # Position all nodes
        coords = {}
        for (i, (x, y)) in self.coords_def.items():
            screen_x = center_x + x * final_scale_x
            screen_y = center_y + y * final_scale_y
            coords[i] = QPointF(screen_x, screen_y)
        
        # Draw edges with consistent gap
        node_radius = 12
        gap = node_radius + 3
        
        p.setPen(QtGui.QPen(QtCore.Qt.lightGray, 2))
        for (a, b) in self.edges_def:
            (pa, pb) = (coords[a], coords[b])
            v = pb - pa
            length = (v.x() ** 2 + v.y() ** 2) ** 0.5
            if length <= 2 * gap:
                continue
            shrink = gap / length
            start_point = QPointF(pa.x() + v.x() * shrink, pa.y() + v.y() * shrink)
            end_point = QPointF(pb.x() - v.x() * shrink, pb.y() - v.y() * shrink)
            p.drawLine(QLineF(start_point, end_point))
        
        # Draw node numbers
        p.setFont(QtGui.QFont('Monaco', 18, QtGui.QFont.Bold))
        for (idx, pt) in coords.items():
            if idx == self.current_pos and self.flash_on:
                p.setPen(QtCore.Qt.green)
            else:
                p.setPen(QtCore.Qt.white)
            txt = str(idx)
            br = p.boundingRect(QtCore.QRectF(), txt)
            p.drawText(QPointF(pt.x() - br.width() / 2, pt.y() + br.height() / 2), txt)

if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = QtWidgets.QMainWindow()
    grid = GridWidget(positions=9, current_pos=0)
    grid.setMinimumSize(300, 250)
    grid.set_horizontal_stretch(1.3)
    t = QtCore.QTimer()
    t.timeout.connect(lambda: grid.set_flash(not grid.flash_on))
    t.start(400)
    pos_timer = QtCore.QTimer()
    current_test_pos = 0

    def change_pos():
        global current_test_pos
        current_test_pos = (current_test_pos + 1) % grid.positions
        grid.set_current_pos(current_test_pos)
    pos_timer.timeout.connect(change_pos)
    pos_timer.start(2000)
    w.setCentralWidget(grid)
    w.resize(420, 420)
    w.setWindowTitle(f'GridWidget Test - {grid.positions} positions')
    w.show()
    sys.exit(app.exec_())
