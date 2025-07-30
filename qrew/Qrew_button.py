# Qrew_button.py

from PyQt5 import QtWidgets, QtGui, QtCore
from colour import Color  # pip install colour


class Main(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("QPushButton{height: 30px;width: 200px; }")

        layout = QtWidgets.QHBoxLayout()

        btn = Button("2020 is an interesting year.")

        layout.addStretch()
        layout.addWidget(btn)
        layout.addStretch()
        self.setLayout(layout)


class Button(QtWidgets.QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.shadow = QtWidgets.QGraphicsDropShadowEffect()
        self.setGraphicsEffect(self.shadow)
        self.tm = QtCore.QBasicTimer()
        self.shadow.setOffset(0, 0)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QtGui.QColor("#3F3F3F"))
        self.mouse = ""

        self.changeColor(color="lightgrey")

        # button shadow grading.
        self.expand = 0
        self.maxExpand = 4  # expanding size - #optional
        self.init_s_color = "#3F3F3F"  # optional
        self.end_s_color = "#FFFF33"  # optional
        self.grading_s_seq = self.gradeColor(
            c1=self.init_s_color, c2=self.end_s_color, steps=self.maxExpand
        )
        # button color grading.
        self.grade = 0
        self.maxGrade = 15  # grading size - #optional
        self.init_bg_color = "lightgrey"  # optional
        self.end_bg_color = "darkgrey"  # optional
        self.grading_bg_seq = self.gradeColor(
            c1=self.init_bg_color, c2=self.end_bg_color, steps=self.maxGrade
        )

    def changeColor(self, color=(255, 255, 255)):
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor(color))
        self.setPalette(palette)

    def gradeColor(self, c1, c2, steps):
        return list([str(i) for i in Color(c1).range_to(Color(c2), steps)])

    def enterEvent(self, e) -> None:
        self.mouse = "on"
        # self.setGraphicsEffect(self.shadow)
        self.tm.start(15, self)

    def leaveEvent(self, e) -> None:
        self.mouse = "off"

    def timerEvent(self, e) -> None:

        if self.mouse == "on" and self.grade < self.maxGrade:
            self.grade += 1
            self.changeColor(color=self.grading_bg_seq[self.grade - 1])

        elif self.mouse == "off" and self.grade > 0:
            self.changeColor(color=self.grading_bg_seq[self.grade - 1])
            self.grade -= 1

        if self.mouse == "on" and self.expand < self.maxExpand:
            self.expand += 1
            self.shadow.setColor(QtGui.QColor(self.grading_s_seq[self.expand - 1]))
            self.setGeometry(
                self.x() - 1, int(self.y() - 1), self.width() + 2, self.height() + 2
            )

        elif self.mouse == "off" and self.expand > 0:
            self.expand -= 1
            self.setGeometry(
                self.x() + 1, int(self.y() + 1), self.width() - 2, self.height() - 2
            )

        elif (
            self.mouse == "off"
            and self.expand in [0, self.maxExpand]
            and self.grade in [0, self.maxGrade]
        ):
            self.shadow.setColor(QtGui.QColor(self.init_s_color))
            self.tm.stop()


if __name__ == "__main__":
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    main = Main()
    main.show()
    app.exec_()
