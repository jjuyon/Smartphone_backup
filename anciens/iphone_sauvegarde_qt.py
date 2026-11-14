#!/usr/bin/env python3
"""Interface moderne (Qt) pour la sauvegarde d'iPhone.

À placer dans le même dossier que iphone_sauvegarde.py (qui contient la logique).
Installation :  pip install PySide6   (de préférence dans un venv)
Lancement    :  python3 iphone_sauvegarde_qt.py
"""
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from iphone_sauvegarde import organize, run_backup

STYLE = """
* { font-family: "Inter", "Cantarell", "Segoe UI", sans-serif; font-size: 14px; color: #e8eaed; }
QWidget#root { background: #111317; }
QFrame#card { background: #1b1e24; border: 1px solid #272b33; border-radius: 14px; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #8b93a1; }
QLabel#section { font-weight: 600; color: #c4c9d2; }
QLineEdit { background: #111317; border: 1px solid #2d323b; border-radius: 8px; padding: 8px 10px; }
QLineEdit:focus { border-color: #4c8dff; }
QPushButton { background: #262a32; border: none; border-radius: 8px; padding: 9px 16px; }
QPushButton:hover { background: #2f343d; }
QPushButton:disabled { color: #5d6470; background: #1f2229; }
QPushButton#primary { background: #4c8dff; color: white; font-weight: 600; padding: 12px 22px; }
QPushButton#primary:hover { background: #6aa0ff; }
QPushButton#primary:disabled { background: #2a3a58; color: #7d8aa3; }
QPushButton#danger { background: #3a2326; color: #ff8a8a; }
QCheckBox { spacing: 10px; padding: 6px 4px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3a404b; background: #111317; }
QCheckBox::indicator:checked { background: #4c8dff; border-color: #4c8dff; }
QProgressBar { background: #111317; border: none; border-radius: 6px; height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #4c8dff; border-radius: 6px; }
QPlainTextEdit { background: #0d0f12; border: 1px solid #272b33; border-radius: 10px; padding: 8px;
                 font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 12px; color: #aab1bd; }
"""


class Worker(QThread):
    log = Signal(str)
    progress = Signal(int)
    step = Signal(str)
    error = Signal(str)

    def __init__(self, do_backup, raw, out, opts):
        super().__init__()
        self.do_backup, self.raw, self.out, self.opts = do_backup, raw, out, opts
        self.cancelled = False
        self.procs = []

    def cancel(self):
        self.cancelled = True
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass

    def run(self):
        cancel = lambda: self.cancelled
        prog = lambda v: self.progress.emit(int(v))
        try:
            if self.do_backup:
                self.step.emit("Étape 1/2 : sauvegarde de l'iPhone")
                run_backup(self.raw, self.log.emit, prog, cancel, self.procs)
            self.progress.emit(0)
            self.step.emit("Étape 2/2 : rangement des fichiers" if self.do_backup
                           else "Rangement des fichiers")
            organize(self.raw, self.out, self.opts, self.log.emit, prog, cancel)
        except Exception as e:
            self.error.emit(str(e))


def dark_palette():
    """Palette sombre pour toute l'appli, y compris les boîtes de dialogue."""
    p = QPalette()
    roles = {
        QPalette.Window: "#111317", QPalette.WindowText: "#e8eaed",
        QPalette.Base: "#0d0f12", QPalette.AlternateBase: "#1b1e24",
        QPalette.Text: "#e8eaed", QPalette.Button: "#262a32",
        QPalette.ButtonText: "#e8eaed", QPalette.ToolTipBase: "#1b1e24",
        QPalette.ToolTipText: "#e8eaed", QPalette.PlaceholderText: "#8b93a1",
        QPalette.Highlight: "#4c8dff", QPalette.HighlightedText: "#ffffff",
        QPalette.Link: "#6aa0ff",
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#5d6470"))
    return p


def card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    return f, lay


def label(text, name=None):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    return l


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Sauvegarde iPhone")
        self.resize(760, 760)
        self.worker = None
        home = os.path.expanduser("~")

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 24)
        root.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("Sauvegarde iPhone", "title"))
        titles.addWidget(label("Récupérez vos photos, documents et musique.", "subtitle"))
        head.addLayout(titles, 1)
        self.device = QLabel()
        head.addWidget(self.device)
        root.addLayout(head)

        c, l = card()
        l.addWidget(label("Dossiers", "section"))
        self.raw = self.folder_row(l, "Sauvegarde brute", os.path.join(home, "iPhone-sauvegarde-brute"))
        self.out = self.folder_row(l, "Destination", os.path.join(home, "iPhone-contenu"))
        root.addWidget(c)

        c, l = card()
        l.addWidget(label("Contenu à récupérer", "section"))
        grid = QHBoxLayout()
        self.opts = {}
        for key, text in (("photos", "Photos et vidéos"), ("docs", "Documents"),
                          ("music", "Musique"), ("voice", "Notes vocales")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            self.opts[key] = cb
            grid.addWidget(cb)
        l.addLayout(grid)
        root.addWidget(c)

        c, l = card()
        self.stepLabel = label("Prêt.", "section")
        l.addWidget(self.stepLabel)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        l.addWidget(self.bar)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMinimumHeight(160)
        l.addWidget(self.logbox)
        root.addWidget(c, 1)

        btns = QHBoxLayout()
        self.b_all = QPushButton("Sauvegarder l'iPhone puis ranger")
        self.b_all.setObjectName("primary")
        self.b_org = QPushButton("Ranger une sauvegarde existante")
        self.b_open = QPushButton("Ouvrir le dossier")
        self.b_cancel = QPushButton("Annuler")
        self.b_cancel.setObjectName("danger")
        self.b_cancel.setEnabled(False)
        for b in (self.b_all, self.b_org):
            btns.addWidget(b)
        btns.addStretch(1)
        btns.addWidget(self.b_open)
        btns.addWidget(self.b_cancel)
        root.addLayout(btns)

        self.b_all.clicked.connect(lambda: self.start(True))
        self.b_org.clicked.connect(lambda: self.start(False))
        self.b_cancel.clicked.connect(self.cancel)
        self.b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.out.text())))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_device)
        self.timer.start(3000)
        self.check_device()

    def folder_row(self, layout, name, default):
        row = QHBoxLayout()
        row.addWidget(label(name, "hint"))
        edit = QLineEdit(default)
        btn = QPushButton("Parcourir…")
        btn.clicked.connect(lambda: edit.setText(
            QFileDialog.getExistingDirectory(self, name, edit.text()) or edit.text()))
        row.addWidget(edit, 1)
        row.addWidget(btn)
        layout.addLayout(row)
        return edit

    def check_device(self):
        if self.worker and self.worker.isRunning():
            return
        ok = False
        if shutil.which("idevice_id"):
            try:
                ok = bool(subprocess.run(["idevice_id", "-l"], capture_output=True,
                                         text=True, timeout=2).stdout.strip())
            except Exception:
                pass
        color, text = ("#3ddc84", "iPhone détecté") if ok else ("#8b93a1", "Aucun iPhone détecté")
        self.device.setText(f'<span style="color:{color}">●</span>&nbsp; {text}')

    def start(self, do_backup):
        opts = {k: cb.isChecked() for k, cb in self.opts.items()}
        if not any(opts.values()):
            QMessageBox.information(self, "Sauvegarde iPhone", "Cochez au moins un type de contenu.")
            return
        self.logbox.clear()
        self.bar.setValue(0)
        self.worker = Worker(do_backup, self.raw.text(), self.out.text(), opts)
        self.worker.log.connect(self.logbox.appendPlainText)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.step.connect(self.stepLabel.setText)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        for b in (self.b_all, self.b_org):
            b.setEnabled(False)
        self.b_cancel.setEnabled(True)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel()

    def on_error(self, msg):
        self.logbox.appendPlainText("ERREUR : " + msg)
        self.stepLabel.setText("Une erreur est survenue")
        QMessageBox.critical(self, "Erreur", msg)
        self.errored = True

    def on_finished(self):
        for b in (self.b_all, self.b_org):
            b.setEnabled(True)
        self.b_cancel.setEnabled(False)
        if not getattr(self, "errored", False) and not self.worker.cancelled:
            self.stepLabel.setText("Terminé ✓")
        self.errored = False
        self.check_device()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    sys.exit(app.exec())
