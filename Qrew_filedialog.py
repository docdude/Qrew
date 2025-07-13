# Qrew_filedialog.py
from PyQt5.QtWidgets import QFileDialog
_DARK_SHEET = """
QFileDialog { background: rgba(20,20,20,0.95); color: white; }
QPushButton { background: #4c4c4c; color: white; border-radius:4px; padding:4px 12px; }
QPushButton:hover { background: #606060; }
QLineEdit, QListView, QTreeView { background:#2a2a2a; selection-background-color:#555; }
"""
def get_open_file(parent, dir_, filt):
    dlg = QFileDialog(parent, "Select Stimulus WAV File", dir_, filt)
    dlg.setOption(QFileDialog.DontUseNativeDialog, True)
    dlg.setStyleSheet(_DARK_SHEET)
    if dlg.exec_():
        return dlg.selectedFiles()[0]
    return ""
