"""Thème, petits widgets et classes partagées par toutes les pages."""
import os

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPalette
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget)

ICONS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
_icons = {}


def app_icon(name):
    """Icône SVG fournie avec l'appli (même rendu quel que soit le bureau ou le thème)."""
    if name not in _icons:
        _icons[name] = QIcon(os.path.join(ICONS, name + ".svg"))
    return _icons[name]

STYLE = """
* { font-family: "Inter", "Cantarell", "Segoe UI", sans-serif; font-size: 14px; color: #e8eaed; }
QWidget#root, QStackedWidget { background: #111317; }
QFrame#card { background: #1b1e24; border: 1px solid #272b33; border-radius: 14px; }
QFrame#choice { background: #1b1e24; border: 1px solid #272b33; border-radius: 18px; }
QFrame#choice:hover { background: #20242c; border-color: #4c8dff; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#bigtitle { font-size: 30px; font-weight: 700; }
QLabel#choiceTitle { font-size: 22px; font-weight: 700; }
QLabel#subtitle, QLabel#hint { color: #8b93a1; }
QLabel#section { font-weight: 600; color: #c4c9d2; }
QLineEdit, QComboBox { background: #111317; border: 1px solid #2d323b; border-radius: 8px; padding: 8px 10px; }
QLineEdit:focus, QComboBox:focus { border-color: #4c8dff; }
QPushButton { background: #262a32; border: none; border-radius: 8px; padding: 9px 16px; }
QPushButton:hover { background: #2f343d; }
QPushButton:disabled { color: #5d6470; background: #1f2229; }
QPushButton#primary { background: #4c8dff; color: white; font-weight: 600; padding: 12px 22px; }
QPushButton#primary:hover { background: #6aa0ff; }
QPushButton#primary:disabled { background: #2a3a58; color: #7d8aa3; }
QPushButton#danger { background: #3a2326; color: #ff8a8a; }
QPushButton#back { background: transparent; color: #8b93a1; padding: 6px 10px; }
QPushButton#back:hover { color: #e8eaed; background: #1b1e24; }
QCheckBox { spacing: 10px; padding: 6px 4px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #3a404b; background: #111317; }
QCheckBox::indicator:checked { background: #4c8dff; border-color: #4c8dff; }
QProgressBar { background: #111317; border: none; border-radius: 6px; height: 12px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #4c8dff; border-radius: 6px; }
QPlainTextEdit { background: #0d0f12; border: 1px solid #272b33; border-radius: 10px; padding: 8px;
                 font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 12px; color: #aab1bd; }
QLabel#cmd { background: #0d0f12; border: 1px solid #272b33; border-radius: 8px; padding: 10px;
             font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 13px; }
QTreeView, QListWidget { background: #0d0f12; border: 1px solid #272b33; border-radius: 10px; padding: 4px; outline: 0; }
QTreeView::item, QListWidget::item { padding: 5px 6px; border-radius: 6px; }
QTreeView::item:hover, QListWidget::item:hover { background: #1b1e24; }
QTreeView::item:selected, QListWidget::item:selected { background: #2a3a58; color: #ffffff; }
QListWidget#sidebar { background: #15171c; }
QHeaderView { background: #0d0f12; border: none; }
QHeaderView::section { background: #0d0f12; color: #8b93a1; border: none; border-bottom: 1px solid #272b33; padding: 6px 8px; }
QSplitter::handle { background: transparent; width: 8px; }
QMenu { background: #1b1e24; border: 1px solid #2d323b; padding: 4px; }
QMenu::item { padding: 6px 18px; border-radius: 6px; }
QMenu::item:selected { background: #2a3a58; }
QToolTip { background: #1b1e24; color: #e8eaed; border: 1px solid #2d323b; padding: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2d323b; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #2d323b; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QFrame#banner { background: #1b1e24; border: 1px solid #272b33; border-radius: 12px; }
QFrame#bannerWarn { background: #2b2416; border: 1px solid #5a4620; border-radius: 12px; }
"""


GREEN, ORANGE, RED, GREY = "#3ddc84", "#f0b429", "#ff8a8a", "#8b93a1"


def settings():
    return QSettings("SynchroSmartphone", "SynchroSmartphone")


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


def status_html(color, text):
    return f'<span style="color:{color}">●</span>&nbsp; {text}'


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


def folder_row(parent, layout, name, key, default):
    """Ligne « Nom [chemin] [Parcourir…] » ; le chemin est mémorisé entre deux lancements."""
    s = settings()
    row = QHBoxLayout()
    row.addWidget(label(name, "hint"))
    edit = QLineEdit(s.value(key, default))
    edit.textChanged.connect(lambda t: s.setValue(key, t))
    btn = QPushButton("Parcourir…")
    from .folder_picker import pick_folder
    btn.clicked.connect(lambda: edit.setText(pick_folder(parent, name, edit.text()) or edit.text()))
    row.addWidget(edit, 1)
    row.addWidget(btn)
    layout.addLayout(row)
    return edit


class ClickableCard(QFrame):
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("choice")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()


# ---------------------------------------------------------------- threads
class TaskWorker(QThread):
    """Exécute job(log, progress, step, cancelled) dans un thread."""
    log = Signal(str)
    progress = Signal(int)
    step = Signal(str)
    error = Signal(str)

    def __init__(self, job, on_cancel=None):
        super().__init__()
        self.job, self.on_cancel = job, on_cancel
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        if self.on_cancel:
            self.on_cancel()

    def run(self):
        try:
            self.job(self.log.emit, lambda v: self.progress.emit(int(v)), self.step.emit,
                     lambda: self.cancelled)
        except Exception as e:
            self.error.emit(str(e))


class DeviceWatcher(QThread):
    """Détecte les iPhone et Android branchés toutes les 3 s, sans bloquer l'interface."""
    changed = Signal(list, list)  # [(udid, nom)], [(serial, état, modèle)]

    def run(self):
        from ..core import android, iphone
        while not self.isInterruptionRequested():
            self.changed.emit(iphone.list_iphones(), android.list_devices())
            for _ in range(30):
                if self.isInterruptionRequested():
                    return
                self.msleep(100)


# ---------------------------------------------------------------- page de base
class BasePage(QWidget):
    """En-tête (retour, titre, état de l'appareil), carte de progression, barre de boutons."""
    back = Signal()
    help = Signal(str)  # ouvre la fenêtre des prérequis
    APP = ""
    TARGET = ""

    def __init__(self, title, subtitle):
        super().__init__()
        self.worker = None
        self.errored = False
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(26, 18, 26, 24)
        self.root.setSpacing(14)

        self.b_back = QPushButton("← Accueil")
        self.b_back.setObjectName("back")
        self.b_back.clicked.connect(self.back.emit)
        top = QHBoxLayout()
        top.addWidget(self.b_back)
        top.addStretch(1)
        self.root.addLayout(top)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label(title, "title"))
        titles.addWidget(label(subtitle, "subtitle"))
        head.addLayout(titles, 1)
        right = QVBoxLayout()
        self.status = QLabel()
        right.addWidget(self.status, 0, Qt.AlignRight)
        self.b_help = QPushButton("Installer les prérequis…")
        self.b_help.setObjectName("primary")
        self.b_help.clicked.connect(lambda: self.help.emit(self.TARGET))
        self.b_help.hide()
        right.addWidget(self.b_help, 0, Qt.AlignRight)
        head.addLayout(right)
        self.root.addLayout(head)

    def prereqs_ok(self):
        """Affiche le bouton d'aide s'il manque un outil indispensable ; renvoie True si tout va bien."""
        from ..core import prereqs
        ok = not prereqs.missing(self.TARGET, required_only=True)
        self.b_help.setVisible(not ok)
        return ok

    def add_progress(self):
        c, l = card()
        self.step = label("Prêt.", "section")
        l.addWidget(self.step)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        l.addWidget(self.bar)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMinimumHeight(150)
        l.addWidget(self.logbox)
        self.root.addWidget(c, 1)

    def add_buttons(self, actions, out_edit):
        """actions : [(texte, callback, principal?)] ; ajoute aussi « Ouvrir le dossier » et « Annuler »."""
        btns = QHBoxLayout()
        self.action_buttons = []
        for text, cb, primary in actions:
            b = QPushButton(text)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(cb)
            btns.addWidget(b)
            self.action_buttons.append(b)
        btns.addStretch(1)
        b_open = QPushButton("Ouvrir le dossier")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(out_edit.text())))
        btns.addWidget(b_open)
        self.b_cancel = QPushButton("Annuler")
        self.b_cancel.setObjectName("danger")
        self.b_cancel.setEnabled(False)
        self.b_cancel.clicked.connect(self.cancel)
        btns.addWidget(self.b_cancel)
        self.root.addLayout(btns)

    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    def run_task(self, job, first_step, on_cancel=None):
        self.logbox.clear()
        self.bar.setValue(0)
        self.step.setText(first_step)
        self.errored = False
        self.worker = TaskWorker(job, on_cancel)
        self.worker.log.connect(self.logbox.appendPlainText)
        self.worker.progress.connect(self.bar.setValue)
        self.worker.step.connect(self.step.setText)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.set_busy(True)
        self.worker.start()

    def set_busy(self, busy):
        for b in self.action_buttons:
            b.setEnabled(not busy)
        self.b_back.setEnabled(not busy)
        self.b_cancel.setEnabled(busy)

    def cancel(self):
        if self.worker:
            self.worker.cancel()

    def on_error(self, msg):
        self.errored = True
        self.logbox.appendPlainText("ERREUR : " + msg)
        if self.worker and self.worker.cancelled:
            return
        self.step.setText("Une erreur est survenue")
        QMessageBox.critical(self, "Erreur", msg)

    def on_finished(self):
        self.set_busy(False)
        if self.worker.cancelled:
            self.step.setText("Annulé")
        elif not self.errored:
            self.step.setText("Terminé ✓")

    def info(self, text):
        QMessageBox.information(self, self.APP, text)

    def ensure_dir(self, path):
        try:
            os.makedirs(path, exist_ok=True)
            return True
        except OSError as e:
            QMessageBox.critical(self, self.APP, f"Impossible de créer le dossier :\n{path}\n\n{e}")
            return False
