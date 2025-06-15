# -*- coding: utf-8 -*-
"""
Created on Thu May 29 17:45:21 2025

@author: windows
"""

import sys
import json
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QComboBox
)

CONFIG_FILE = "run_config.json"

ROLES = [
    "FLIGHT", "CAPCOM", "FAO", "BME", "CPOO", "SCIENCE", "EVA"
]

def get_config_from_dialog():
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("Mission Control Config")
    layout = QVBoxLayout()

    server_input = QLineEdit("comms.a.pinggy.link")
    port_input = QLineEdit("23234")
    botname_input = QLineEdit("CAPCOM")
    role_select = QComboBox()
    role_select.addItems(ROLES)

    layout.addWidget(QLabel("Server address:"))
    layout.addWidget(server_input)
    layout.addWidget(QLabel("Server port:"))
    layout.addWidget(port_input)
    layout.addWidget(QLabel("Bot base name:"))
    layout.addWidget(botname_input)
    layout.addWidget(QLabel("Role:"))
    layout.addWidget(role_select)

    hbox = QHBoxLayout()
    ok_btn = QPushButton("OK")
    hbox.addStretch(1)
    hbox.addWidget(ok_btn)
    layout.addLayout(hbox)

    window.setLayout(layout)

    result = {}

    def on_ok():
        result['server'] = server_input.text().strip()
        result['port'] = int(port_input.text().strip())
        result['bot_base'] = botname_input.text().strip()
        result['role'] = role_select.currentText()
        with open(CONFIG_FILE, "w") as f:
            json.dump(result, f)
        window.close()
        app.quit()

    ok_btn.clicked.connect(on_ok)
    window.show()
    app.exec()

    if not result and os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            result = json.load(f)
    return result

def read_config():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return None

def write_config(server, port, bot_base, role):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"server": server, "port": port, "bot_base": bot_base, "role": role}, f)
