# Qrew_messagebox.py
"""
Custom message boxes and dialogs using consistent styling
"""

import os
from PyQt5.QtWidgets import (
    QDialog,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QLineEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal

try:
    from .Qrew_button import Button
    from .Qrew_styles import HTML_ICONS, BUTTON_STYLES
except ImportError:
    from Qrew_button import Button
    from Qrew_styles import HTML_ICONS, BUTTON_STYLES


class QrewMessageBox(QDialog):
    """Custom message box with consistent styling"""

    # Message box types
    Information = 0
    Warning = 1
    Critical = 2
    Question = 3

    # Standard buttons
    Ok = 0x00000400
    Cancel = 0x00400000
    Yes = 0x00004000
    No = 0x00010000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(True)
        self._setup_ui()
        self._result = None

    def _setup_ui(self):
        """Setup the UI layout"""
        self.setStyleSheet(
            """
            QDialog {
                border: 2px solid #555;
                border-radius: 8px;
            }
        """
        )

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(10, 10, 20, 20)

        # Icon and title layout
        self.title_layout = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setTextFormat(Qt.RichText)
        self.title_layout.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.title_layout.addWidget(self.title_label)
        self.title_layout.addStretch()

        layout.addLayout(self.title_layout)

        # Message
        self.message_label = QLabel()
        self.message_label.setTextFormat(Qt.RichText)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-size: 14px; line-height: 1.4;")
        self.message_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message_label)

        layout.addStretch()

        # Buttons
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch()
        layout.addLayout(self.button_layout)

        self.setLayout(layout)

    def set_icon(self, msg_type):
        """Set icon based on message type"""
        if msg_type == self.Information:
            icon = HTML_ICONS["info"]
            color = "#2196F3"
        elif msg_type == self.Warning:
            icon = HTML_ICONS["warning"]
            color = "#ff9800"
        elif msg_type == self.Critical:
            icon = HTML_ICONS["no_entry"]
            #   icon = '<img src="./no_entry.png" width="50" height="50">'
            color = "#f44336"
        else:  # Question
            icon = "?"
            color = "#2196F3"

        self.icon_label.setText(
            f'<span style="color: {color}; font-size: 50px;">{icon}</span>'
        )
        self.title_label.setStyleSheet(
            f"font-weight: bold; font-size: 16px; color: {color};"
        )

    def _add_button(self, text, button_type, style_name="secondary"):
        """Add a button to the dialog"""
        button = Button(text)
        style = BUTTON_STYLES.get(style_name, BUTTON_STYLES["secondary"])
        button.setStyleSheet(style)
        button.clicked.connect(lambda: self._button_clicked(button_type))
        self.button_layout.addWidget(button)
        return button

    def _button_clicked(self, button_type):
        """Handle button click"""
        self._result = button_type
        self.accept()

    def setWindowTitle(self, title):
        """Override to also set title label"""
        super().setWindowTitle(title)
        self.title_label.setText(title)

    def setText(self, text):
        """Set the message text"""
        self.message_label.setText(text)

    def setStandardButtons(self, buttons):
        """Set standard buttons"""
        # Clear existing buttons
        while self.button_layout.count() > 1:  # Keep the stretch
            item = self.button_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        # Add requested buttons
        if buttons & self.Ok:
            self._add_button("OK", self.Ok, "primary")
        if buttons & self.Cancel:
            self._add_button("Cancel", self.Cancel, "secondary")
        if buttons & self.Yes:
            self._add_button("Yes", self.Yes, "primary")
        if buttons & self.No:
            self._add_button("No", self.No, "danger")

    def exec_(self):
        """Execute and return button clicked"""
        super().exec_()
        return self._result or self.Cancel

    @staticmethod
    def information(parent, title, text):
        """Show information message box"""
        box = QrewMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.set_icon(QrewMessageBox.Information)
        box.setStandardButtons(QrewMessageBox.Ok)
        box.setFixedSize(450, 210)
        return box.exec_()

    @staticmethod
    def warning(parent, title, text):
        """Show warning message box"""
        box = QrewMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.set_icon(QrewMessageBox.Warning)
        box.setStandardButtons(QrewMessageBox.Ok)
        box.setFixedSize(450, 210)
        return box.exec_()

    @staticmethod
    def critical(parent, title, text):
        """Show critical message box"""
        box = QrewMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.set_icon(QrewMessageBox.Critical)
        box.setStandardButtons(QrewMessageBox.Ok)
        box.setFixedSize(450, 210)
        return box.exec_()

    @staticmethod
    def question(parent, title, text, buttons=None):
        """Show question message box"""
        if buttons is None:
            buttons = QrewMessageBox.Yes | QrewMessageBox.No
        box = QrewMessageBox(parent)
        box.setWindowTitle(title)
        box.setText(text)
        box.set_icon(QrewMessageBox.Question)
        box.setStandardButtons(buttons)
        box.setFixedSize(450, 210)
        return box.exec_()


class QrewFileDialog(QDialog):
    """Custom file dialog with consistent styling"""

    fileSelected = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
        mode="open",
        caption="Select File",
        directory="",
        filter="All Files (*.*)",
        default_suffix="",
    ):
        super().__init__(parent)
        self.setWindowTitle(caption)
        self.setModal(True)
        self.mode = mode  # 'open' or 'save'
        self.directory = directory or os.path.expanduser("~")
        self.filter = filter
        self.default_suffix = default_suffix
        self.selected_file = None

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            """
            QDialog {
                border: 2px solid #555;
                border-radius: 8px;
            }
            QLabel {
                font-size: 14px;
            }
            QLineEdit {
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px;
                font-size: 14px;
            }
        """
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QLabel(self.windowTitle())
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; ")
        layout.addWidget(title_label)

        # File path input
        path_layout = QHBoxLayout()
        path_label = QLabel("File:")
        path_label.setFixedWidth(60)

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select a file...")

        # Browse button
        self.browse_button = Button("Browse...")
        self.browse_button.setStyleSheet(BUTTON_STYLES["secondary"])
        self.browse_button.clicked.connect(self._open_native_dialog)

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_button)
        layout.addLayout(path_layout)

        # File info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #999; font-size: 12px;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = Button("Cancel")
        self.cancel_button.setStyleSheet(BUTTON_STYLES["secondary"])
        self.cancel_button.clicked.connect(self.reject)

        self.ok_button = Button("OK")
        self.ok_button.setStyleSheet(BUTTON_STYLES["primary"])
        self.ok_button.clicked.connect(self._accept)

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.resize(500, 200)

    def _open_native_dialog(self):
        """Open the native file dialog"""
        if self.mode == "open":
            # Open file dialog
            file_path, _ = QFileDialog.getOpenFileName(
                self, self.windowTitle(), self.directory, self.filter
            )
        else:
            # Save file dialog
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                self.windowTitle(),
                self.directory,
                self.filter,
                self.default_suffix,
            )

        if file_path:
            self.path_input.setText(file_path)
            self._update_file_info(file_path)

    def _update_file_info(self, file_path):
        """Update file information label"""
        if os.path.exists(file_path):
            # Existing file
            size = os.path.getsize(file_path)
            modified = os.path.getmtime(file_path)
            size_str = (
                f"{size / 1024 / 1024:.1f} MB"
                if size > 1024 * 1024
                else f"{size / 1024:.1f} KB"
            )

            info_text = f"Size: {size_str}<br>" f"Modified: {modified}"
            self.info_label.setText(info_text)
            self.ok_button.setEnabled(True)
        elif self.mode == "save":
            # New file in save mode
            self.info_label.setText("New file will be created")
            self.ok_button.setEnabled(True)
        else:
            # File not found in open mode
            self.info_label.setText("<span style='color: red;'>File not found</span>")
            self.ok_button.setEnabled(False)

    def _accept(self):
        """Accept the selected file"""
        file_path = self.path_input.text().strip()

        if not file_path:
            # No file selected
            return

        if self.mode == "open" and not os.path.exists(file_path):
            # File doesn't exist in open mode
            return

        self.selected_file = file_path
        self.fileSelected.emit(file_path)
        self.accept()

    @classmethod
    def getOpenFileName(
        cls,
        parent=None,
        caption="Open File",
        directory="",
        filter="All Files (*.*)",
        default_suffix="",
    ):
        """Class method to get open file name"""
        dialog = cls(
            parent,
            mode="open",
            caption=caption,
            directory=directory,
            filter=filter,
            default_suffix=default_suffix,
        )
        if dialog.exec_():
            return dialog.selected_file
        return None

    @classmethod
    def getSaveFileName(
        cls,
        parent=None,
        caption="Save File",
        directory="",
        filter="All Files (*.*)",
        default_suffix="",
    ):
        """Class method to get save file name"""
        dialog = cls(
            parent,
            mode="save",
            caption=caption,
            directory=directory,
            filter=filter,
            default_suffix=default_suffix,
        )
        if dialog.exec_():
            return dialog.selected_file
        return None
