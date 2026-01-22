"""
AdGuard VPN GUI Control
A simple PyQt5 GUI wrapper for AdGuard VPN CLI on Linux.
"""
import sys
import subprocess
import re
import os
import shutil

# Fix for Wayland/Gnome environments
os.environ["QT_QPA_PLATFORM"] = "xcb"

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QComboBox, QLabel, QMessageBox, QDesktopWidget,
        QStyleFactory, QTextEdit, QDialog
    )
    from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
    from PyQt5.QtGui import QFont
except ImportError:
    print("ERROR: PyQt5 library is not installed.")
    sys.exit(1)

BINARY_NAME = "adguardvpn-cli"
USER_HOME = os.path.expanduser("~")

# Find binary path
BINARY_PATH = shutil.which(BINARY_NAME)
if not BINARY_PATH:
    POSSIBLE_PATHS = [
        "/usr/bin/adguardvpn-cli",
        "/usr/local/bin/adguardvpn-cli",
        "/opt/adguardvpn/bin/adguardvpn-cli"
    ]
    for p in POSSIBLE_PATHS:
        if os.path.exists(p):
            BINARY_PATH = p
            break

def clean_ansi(text):
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class Worker(QThread):
    """Background worker for running shell commands."""
    finished = pyqtSignal(bool, str)

    def __init__(self, cmd, needs_root=False):
        super().__init__()
        self.cmd = cmd
        self.needs_root = needs_root

    def run(self):
        try:
            cmd_exec = self.cmd
            # Replace binary name with full path if available
            if BINARY_PATH and BINARY_NAME in self.cmd and not self.cmd.startswith("/"):
                cmd_exec = self.cmd.replace(BINARY_NAME, BINARY_PATH, 1)

            if self.needs_root:
                # Prepare environment for pkexec
                display = os.environ.get('DISPLAY', ':0')
                xauth = os.environ.get('XAUTHORITY', '')
                env_str = f"DISPLAY={display} XAUTHORITY={xauth} HOME={USER_HOME}"
                final_cmd = f"pkexec env {env_str} {cmd_exec}"
            else:
                final_cmd = cmd_exec

            result = subprocess.run(
                final_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
                check=False
            )

            stdout = clean_ansi(result.stdout).strip()
            stderr = clean_ansi(result.stderr).strip()
            full_output = stdout + "\n" + stderr

            if result.returncode == 0:
                self.finished.emit(True, full_output)
            else:
                if "pkexec" in full_output and "dismissed" in full_output:
                    self.finished.emit(False, "Отмена")
                else:
                    self.finished.emit(False, full_output)
        except Exception as e: # pylint: disable=broad-exception-caught
            self.finished.emit(False, str(e))

class InstructionDialog(QDialog):
    """Dialog to show CLI commands to the user."""
    def __init__(self, title, text, command):
        super().__init__()
        self.setWindowTitle(title)
        self.setFixedSize(400, 250)
        layout = QVBoxLayout(self)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.cmd_box = QTextEdit()
        self.cmd_box.setPlainText(command)
        self.cmd_box.setReadOnly(True)
        self.cmd_box.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        layout.addWidget(self.cmd_box)

        btn_copy = QPushButton("Скопировать команду")
        btn_copy.clicked.connect(self.copy_to_clipboard)
        layout.addWidget(btn_copy)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def copy_to_clipboard(self):
        """Copy command text to clipboard."""
        cb = QApplication.clipboard()
        cb.setText(self.cmd_box.toPlainText())
        QMessageBox.information(self, "Готово", "Скопировано!")

class AdGuardVPNGUI(QMainWindow): # pylint: disable=too-many-instance-attributes
    """Main Application Window."""
    def __init__(self):
        super().__init__()
        self.current_city = None
        self.is_logged_in = False
        self.w_login = None
        self.w_status = None
        self.w_act = None

        self.init_ui()
        self.center()

        if not BINARY_PATH:
            self.show_install_screen()
        else:
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_status_routine)
            self.timer.start(5000)
            QTimer.singleShot(100, self.check_login)

    def init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("AdGuard VPN Control")
        self.setFixedSize(420, 280)

        main = QWidget()
        self.setCentralWidget(main)
        layout = QVBoxLayout(main)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.status_label = QLabel("Загрузка...")
        self.status_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #666;")
        layout.addWidget(self.info_label)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(35)
        self.combo.setMaxVisibleItems(15)
        self.combo.setStyleSheet("QComboBox { combobox-popup: 0; }")
        layout.addWidget(self.combo)

        self.control_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Подключить")
        self.btn_connect.setMinimumHeight(45)
        style_green = (
            "background-color: #2E7D32; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_connect.setStyleSheet(style_green)
        self.btn_connect.clicked.connect(self.connect_vpn)

        self.btn_disconnect = QPushButton("Отключить")
        self.btn_disconnect.setMinimumHeight(45)
        style_red = (
            "background-color: #C62828; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_disconnect.setStyleSheet(style_red)
        self.btn_disconnect.clicked.connect(self.disconnect_vpn)

        self.control_layout.addWidget(self.btn_connect)
        self.control_layout.addWidget(self.btn_disconnect)
        layout.addLayout(self.control_layout)

        self.btn_login = QPushButton("🔐 Требуется вход")
        self.btn_login.setMinimumHeight(45)
        self.btn_login.setStyleSheet(
            "background-color: #FF9800; color: white; font-weight: bold;"
        )
        self.btn_login.clicked.connect(self.show_login_instruction)
        self.btn_login.hide()
        layout.addWidget(self.btn_login)

        self.btn_install = QPushButton("📥 Как установить?")
        self.btn_install.setMinimumHeight(45)
        self.btn_install.setStyleSheet(
            "background-color: #0288D1; color: white; font-weight: bold;"
        )
        self.btn_install.clicked.connect(self.show_install_instruction)
        self.btn_install.hide()
        layout.addWidget(self.btn_install)

    def center(self):
        """Center the window on screen."""
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def set_buttons_logic(self):
        """Enable/Disable buttons based on connection status."""
        is_connected = (
            "CONNECTED" in self.status_label.text() and
            "DIS" not in self.status_label.text()
        )

        if is_connected:
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.combo.setEnabled(False)
        else:
            self.btn_connect.setEnabled(True)
            self.btn_disconnect.setEnabled(False)
            self.combo.setEnabled(True)

    def show_install_screen(self):
        """Show installation required screen."""
        self.status_label.setText("Программа не найдена")
        self.status_label.setStyleSheet("color: #D32F2F")
        self.combo.hide()
        self.clear_layout(self.control_layout)
        self.btn_login.hide()
        self.btn_install.show()

    def show_login_screen(self):
        """Show login required screen."""
        self.is_logged_in = False
        self.status_label.setText("Не выполнен вход")
        self.status_label.setStyleSheet("color: #E65100")
        self.combo.hide()
        self.btn_connect.hide()
        self.btn_disconnect.hide()
        self.btn_login.show()

    def show_main_screen(self):
        """Show main control screen."""
        self.is_logged_in = True
        self.btn_login.hide()
        self.btn_install.hide()
        self.combo.show()
        self.btn_connect.show()
        self.btn_disconnect.show()
        self.combo.setEnabled(True)

    def clear_layout(self, layout):
        """Hide all widgets in a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()

    def show_install_instruction(self):
        """Show installation instruction dialog."""
        cmd = (
            "curl -s https://raw.githubusercontent.com/AdguardTeam/"
            "AdGuardVPNCLI/master/scripts/install.sh | sh"
        )
        InstructionDialog(
            "Установка", "Выполните эту команду в терминале:", cmd
        ).exec_()

    def show_login_instruction(self):
        """Show login instruction dialog."""
        cmd = f"{BINARY_NAME} login"
        InstructionDialog(
            "Вход", "Откройте терминал и выполните команду входа:", cmd
        ).exec_()

    def check_login(self):
        """Start background check for login status."""
        self.w_login = Worker(f"{BINARY_NAME} list-locations")
        self.w_login.finished.conn
