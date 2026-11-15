"""Fenêtre « Prérequis » : état de chaque outil et installation assistée."""
import subprocess

from .qt import Qt, QThread, Signal
from .qt import (QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ..core import prereqs
from .common import fit_to_screen, GREEN, ORANGE, RED, card, label, status_html


class Installer(QThread):
    log = Signal(str)
    done = Signal(bool)

    def __init__(self, cmds):
        super().__init__()
        self.cmds = cmds

    def run(self):
        ok = True
        for cmd in self.cmds:
            self.log.emit("$ " + " ".join(cmd))
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, errors="replace", bufsize=1)
                for line in p.stdout:
                    self.log.emit(line.rstrip())
                p.wait()
            except OSError as e:
                self.log.emit(str(e))
                ok = False
                break
            if p.returncode != 0:
                self.log.emit("Annulé ou échec (mot de passe refusé ?)" if p.returncode in (126, 127)
                              else f"Échec (code {p.returncode})")
                ok = False
                break
        self.done.emit(ok)


class PrereqDialog(QDialog):
    def __init__(self, parent=None, target=None):
        super().__init__(parent)
        self.setWindowTitle("Prérequis")
        self.setObjectName("root")
        fit_to_screen(self, 720, 560)
        self.target = target
        self.installer = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        root.addWidget(label("Prérequis", "title"))
        root.addWidget(label("Outils nécessaires pour communiquer avec les téléphones.", "subtitle"))

        c, l = card()
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(8)
        l.addLayout(self.grid)
        root.addWidget(c)

        c, l = card()
        l.addWidget(label("Installation", "section"))
        self.cmd = QLabel()
        self.cmd.setObjectName("cmd")
        self.cmd.setWordWrap(True)
        self.cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        l.addWidget(self.cmd)
        self.note = label("", "hint")
        self.note.setWordWrap(True)
        l.addWidget(self.note)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMinimumHeight(120)
        self.logbox.hide()
        l.addWidget(self.logbox, 1)
        root.addWidget(c, 1)

        btns = QHBoxLayout()
        self.b_install = QPushButton("Installer maintenant")
        self.b_install.setObjectName("primary")
        self.b_install.clicked.connect(self.install)
        self.b_copy = QPushButton("Copier la commande")
        self.b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.shown))
        self.b_recheck = QPushButton("Vérifier à nouveau")
        self.b_recheck.clicked.connect(self.refresh)
        self.b_close = QPushButton("Fermer")
        self.b_close.clicked.connect(self.accept)
        btns.addWidget(self.b_install)
        btns.addWidget(self.b_copy)
        btns.addStretch(1)
        btns.addWidget(self.b_recheck)
        btns.addWidget(self.b_close)
        root.addLayout(btns)
        self.refresh()

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        names = {"iphone": "iPhone", "android": "Android", "commun": "Commun"}
        self.todo = []
        for i, (p, ok) in enumerate(prereqs.check_all()):
            if ok:
                st = status_html(GREEN, "Installé")
            elif p.required:
                st = status_html(RED, "Manquant")
            else:
                st = status_html(ORANGE, "Recommandé")
            if not ok:
                self.todo.append(p)
            name = label(f"<b>{p.name}</b>")
            desc = label(p.desc, "hint")
            desc.setWordWrap(True)
            self.grid.addWidget(label(names[p.target], "hint"), i, 0)
            self.grid.addWidget(name, i, 1)
            self.grid.addWidget(desc, i, 2)
            self.grid.addWidget(QLabel(st), i, 3)
        self.grid.setColumnStretch(2, 1)

        cmds, self.shown, note = prereqs.install_plan(self.todo)
        self.cmds = cmds
        if not self.todo:
            self.cmd.setText(status_html(GREEN, "Tout est installé ✓"))
            self.note.setText("Branchez votre téléphone : il apparaîtra sur l'écran d'accueil.")
        else:
            self.cmd.setText(f"<code>{self.shown}</code>" if self.shown else "")
            self.note.setText(note or "« Installer maintenant » demandera votre mot de passe administrateur.")
        busy = bool(self.installer and self.installer.isRunning())
        self.b_install.setEnabled(bool(cmds) and not busy)
        self.b_copy.setEnabled(bool(self.shown))

    def install(self):
        self.logbox.clear()
        self.logbox.show()
        self.b_install.setEnabled(False)
        self.b_close.setEnabled(False)
        self.installer = Installer(self.cmds)
        self.installer.log.connect(self.logbox.appendPlainText)
        self.installer.done.connect(self.on_done)
        self.installer.start()

    def on_done(self, ok):
        self.b_close.setEnabled(True)
        self.refresh()
        if ok:
            self.logbox.appendPlainText("\nInstallation terminée. Débranchez puis rebranchez le téléphone.")

    def reject(self):
        if self.installer and self.installer.isRunning():
            return  # pas de fermeture pendant l'installation
        super().reject()
