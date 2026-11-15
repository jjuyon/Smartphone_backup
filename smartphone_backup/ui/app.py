"""Fenêtre principale : accueil + écrans iPhone et Android dans une pile."""
import signal
import sys

from .qt import QKeySequence, QLocale, QShortcut, QTimer, QTranslator, before_app, translations_path
from .qt import QApplication, QMessageBox, QStackedWidget

from ..core import procs
from .android_page import AndroidPage
from .common import STYLE, DeviceWatcher, app_icon, dark_palette, fit_to_screen, scrollable
from .home import HomePage
from .iphone_page import IphonePage
from .photos_page import PhotosPage
from .prereqs_dialog import PrereqDialog

TITLE = "Smartphone Backup"


class MainWindow(QStackedWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(TITLE)
        self.home = HomePage()
        self.pages = {"iphone": IphonePage(), "android": AndroidPage(), "photos": PhotosPage()}
        # chaque écran défile si la fenêtre est plus petite que lui (petits écrans)
        self.wraps = {}
        for p in [self.home, *self.pages.values()]:
            # l'accueil défile en entier ; les autres écrans gèrent leur défilement
            # eux-mêmes pour garder leurs boutons visibles
            self.wraps[p] = scrollable(p) if p is self.home else p
            self.addWidget(self.wraps[p])
        for p in self.pages.values():
            p.back.connect(self.go_home)
        fit_to_screen(self, 820, 820)
        self.home.chosen.connect(self.open_page)
        self.home.help.connect(self.open_prereqs)
        for p in [self.home, *self.pages.values()]:
            p.quit.connect(self.close)  # même chemin que la croix de la fenêtre
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        self.stopped = False
        self.adb_was_running = procs.adb_server_running()  # avant que l'appli ne lance adb
        for p in self.pages.values():
            p.help.connect(self.open_prereqs)

        self.watcher = DeviceWatcher()
        self.watcher.changed.connect(self.home.update_devices)
        for p in self.pages.values():
            self.watcher.changed.connect(p.update_devices)
        self.watcher.start()

    def open_page(self, key):
        page = self.pages[key]
        self.setCurrentWidget(self.wraps[page])
        self.setWindowTitle(f"{TITLE} — {page.APP}")

    def open_prereqs(self, target=""):
        PrereqDialog(self, target or None).exec()
        self.home.refresh_prereqs()
        for p in self.pages.values():
            p.prereqs_ok()

    def go_home(self):
        self.setCurrentWidget(self.wraps[self.home])
        self.setWindowTitle(TITLE)

    def closeEvent(self, e):
        """Croix de la fenêtre, bouton « Quitter » et Ctrl+Q passent tous par ici."""
        running = [p for p in self.pages.values() if p.busy()]
        if running and not self.stopped:
            r = QMessageBox.question(self, TITLE, "Une sauvegarde est en cours. L'interrompre et quitter ?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.shutdown()
        e.accept()
        QApplication.quit()

    def shutdown(self):
        """Arrête les tâches, la détection des téléphones et tous les processus lancés par l'appli."""
        if self.stopped:
            return
        self.stopped = True
        for p in self.pages.values():
            if p.busy():
                p.cancel()
        self.watcher.requestInterruption()
        threads = [self.watcher] + [p.worker for p in self.pages.values() if p.worker]
        for _ in range(3):  # une tâche peut relancer une commande avant de voir l'annulation
            procs.kill_children()
            if all(t.wait(2000) for t in threads):
                break
        procs.kill_children()
        if not self.adb_was_running and procs.adb_server_running():
            procs.stop_adb_server()  # serveur adb démarré par l'appli : on l'arrête aussi

def load_translations(app):
    """Boîtes de dialogue Qt (sélecteur de dossiers, Oui/Non…) en français."""
    tr = QTranslator(app)
    if tr.load(QLocale("fr_FR"), "qtbase", "_", translations_path()):
        app.installTranslator(tr)


def main():
    before_app()
    app = QApplication(sys.argv)
    app.setApplicationName(TITLE)
    app.setDesktopFileName("smartphone-backup")
    app.setWindowIcon(app_icon("app"))
    load_translations(app)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    w = MainWindow()
    app.aboutToQuit.connect(w.shutdown)
    # arrêt demandé de l'extérieur (Ctrl+C dans le terminal, fin de session…)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)  # laisse Python traiter les signaux
    tick.start(300)
    w.show()
    sys.exit(app.exec())
