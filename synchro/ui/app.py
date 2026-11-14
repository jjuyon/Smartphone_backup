"""Fenêtre principale : accueil + écrans iPhone et Android dans une pile."""
import sys

from .qt import QLocale, QTranslator, before_app, translations_path
from .qt import QApplication, QMessageBox, QStackedWidget

from .android_page import AndroidPage
from .common import STYLE, DeviceWatcher, app_icon, dark_palette
from .home import HomePage
from .iphone_page import IphonePage
from .prereqs_dialog import PrereqDialog

TITLE = "Synchro Smartphone"


class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.resize(820, 820)
        self.home = HomePage()
        self.pages = {"iphone": IphonePage(), "android": AndroidPage()}
        self.addWidget(self.home)
        for p in self.pages.values():
            self.addWidget(p)
            p.back.connect(self.go_home)
        self.home.chosen.connect(self.open_page)
        self.home.help.connect(self.open_prereqs)
        for p in self.pages.values():
            p.help.connect(self.open_prereqs)

        self.watcher = DeviceWatcher()
        self.watcher.changed.connect(self.home.update_devices)
        for p in self.pages.values():
            self.watcher.changed.connect(p.update_devices)
        self.watcher.start()

    def open_page(self, key):
        page = self.pages[key]
        self.setCurrentWidget(page)
        self.setWindowTitle(f"{TITLE} — {page.APP}")

    def open_prereqs(self, target=""):
        PrereqDialog(self, target or None).exec()
        self.home.refresh_prereqs()
        for p in self.pages.values():
            p.prereqs_ok()

    def go_home(self):
        self.setCurrentWidget(self.home)
        self.setWindowTitle(TITLE)

    def closeEvent(self, e):
        running = [p for p in self.pages.values() if p.busy()]
        if running:
            r = QMessageBox.question(self, TITLE, "Une sauvegarde est en cours. L'interrompre et quitter ?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            for p in running:
                p.cancel()
                p.worker.wait(5000)
        self.watcher.requestInterruption()
        self.watcher.wait(5000)
        e.accept()


def load_translations(app):
    """Boîtes de dialogue Qt (sélecteur de dossiers, Oui/Non…) en français."""
    tr = QTranslator(app)
    if tr.load(QLocale("fr_FR"), "qtbase", "_", translations_path()):
        app.installTranslator(tr)


def main():
    before_app()
    app = QApplication(sys.argv)
    app.setApplicationName(TITLE)
    app.setDesktopFileName("synchro-smartphone")
    app.setWindowIcon(app_icon("app"))
    load_translations(app)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
