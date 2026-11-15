"""Thème, petits widgets et classes partagées par toutes les pages."""
import os

from .qt import QSettings, Qt, QThread, QUrl, Signal
from .qt import event_pos
from .qt import QColor, QDesktopServices, QIcon, QPalette
from .qt import (QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget)

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
QRadioButton { spacing: 10px; padding: 5px 4px; }
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px; border: 1px solid #3a404b; background: #111317; }
QRadioButton::indicator:checked { border-color: #4c8dff; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
    fx:0.5, fy:0.5, stop:0 #4c8dff, stop:0.5 #4c8dff, stop:0.6 #111317, stop:1 #111317); }
QSpinBox { background: #111317; border: 1px solid #2d323b; border-radius: 8px; padding: 6px 8px; min-width: 64px; }
QSpinBox::up-button, QSpinBox::down-button { width: 18px; background: #262a32; border: none; }
QSpinBox::up-button { border-top-right-radius: 8px; }
QSpinBox::down-button { border-bottom-right-radius: 8px; }

QComboBox QAbstractItemView { background: #1b1e24; selection-background-color: #2a3a58; }
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
QTreeView::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #6b7280; background: #111317; }
QTreeView::indicator:checked { background: #e5484d; border-color: #e5484d; }
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
QScrollArea#pageScroll, QScrollArea#pageScroll > QWidget > QWidget { background: #111317; }
QFrame#bannerWarn { background: #2b2416; border: 1px solid #5a4620; border-radius: 12px; }
"""

# flèches des compteurs (le chemin des icônes n'est connu qu'au lancement)
STYLE += "".join(f"QSpinBox::{d}-arrow {{ image: url(\"{ICONS}/arrow-{d}.svg\"); width: 10px; height: 10px; }}\n"
                 for d in ("up", "down"))

GREEN, ORANGE, RED, GREY = "#3ddc84", "#f0b429", "#ff8a8a", "#8b93a1"


def settings():
    s = QSettings("SmartphoneBackup", "SmartphoneBackup")
    if not s.allKeys():  # reprend les réglages de l'ancien nom de l'appli
        old = QSettings("SynchroSmartphone", "SynchroSmartphone")
        for k in old.allKeys():
            s.setValue(k, old.value(k))
    return s


def fit_to_screen(w, width, height):
    """Taille de départ souhaitée, réduite si l'écran est plus petit (ex. 1280×800)."""
    scr = w.screen() if hasattr(w, "screen") else None
    scr = scr or QApplication.primaryScreen()
    if scr:
        g = scr.availableGeometry()
        width = min(width, g.width() - 40)
        height = min(height, g.height() - 60)  # place pour la barre de titre
    w.resize(width, height)


def scrollable(page):
    """Met une page dans une zone défilante : la fenêtre peut alors être plus petite que son contenu."""
    sa = QScrollArea()
    sa.setObjectName("pageScroll")
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    sa.setWidget(page)
    return sa


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
        if e.button() == Qt.LeftButton and self.rect().contains(event_pos(e)):
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


def quit_button(signal):
    b = QPushButton("Quitter")
    b.setObjectName("back")
    b.setToolTip("Fermer l'application (Ctrl+Q)")
    b.clicked.connect(signal.emit)
    return b


# ---------------------------------------------------------------- page de base
class BasePage(QWidget):
    """En-tête (retour, titre, état de l'appareil), carte de progression, barre de boutons."""
    back = Signal()
    quit = Signal()
    help = Signal(str)  # ouvre la fenêtre des prérequis
    APP = ""
    TARGET = ""

    def __init__(self, title, subtitle):
        super().__init__()
        self.worker = None
        self.errored = False
        # contenu défilant + barre de boutons fixe en bas (toujours visible sur petit écran)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QWidget()
        self.root = QVBoxLayout(body)
        self.root.setContentsMargins(26, 18, 26, 10)
        self.root.setSpacing(14)
        self.scroll = scrollable(body)
        outer.addWidget(self.scroll, 1)
        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(26, 10, 26, 18)
        self.footer.setSpacing(10)
        outer.addLayout(self.footer)

        self.b_back = QPushButton("← Accueil")
        self.b_back.setObjectName("back")
        self.b_back.clicked.connect(self.back.emit)
        top = QHBoxLayout()
        top.addWidget(self.b_back)
        top.addStretch(1)
        top.addWidget(quit_button(self.quit))
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
        self.logbox.setMinimumHeight(90)
        l.addWidget(self.logbox)
        self.root.addWidget(c, 1)

    def add_buttons(self, actions, out_edit):
        """actions : [(texte, callback, principal?)] ; ajoute aussi « Ouvrir le dossier » et « Annuler »."""
        btns = self.footer
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

    def busy(self):
        return bool(self.worker and self.worker.isRunning())

    def stop_background(self):
        """Arrête les analyses en arrière-plan propres à l'écran (à la fermeture de l'appli)."""

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
        sb = self.scroll.verticalScrollBar()  # petit écran : montre la progression
        sb.setValue(sb.maximum())
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
