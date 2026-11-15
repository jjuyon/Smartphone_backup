"""Écran « Photos » : ranger et dédoublonner n'importe quel dossier, sans téléphone.

Mêmes options de classement que le rangement de l'écran Android (formulaire SortPanel partagé),
affichées directement dans l'écran.
"""
import os

from .qt import QStandardPaths, QTimer

from .common import GREY, BasePage, folder_row, label, status_html
from .photo_sort_dialog import SortPanel, start_sort


class PhotosPage(BasePage):
    APP = "Photos"
    TARGET = ""

    def __init__(self):
        super().__init__("Ranger des photos", "Classez par date et nettoyez les doublons de n'importe "
                                               "quel dossier.")
        pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) \
            or os.path.expanduser("~")
        self.panel = SortPanel(self)
        # dossier de départ en tête de la carte « Photos à ranger » du formulaire
        top = self.panel.top_box
        self.folder = folder_row(self, top, "Dossier", "photos/folder", pictures)
        hint = label("Par exemple une ancienne sauvegarde, la carte mémoire d'un appareil photo, un disque "
                     "externe… Cochez ci-dessous ce qu'il faut ranger ; « Ajouter un dossier… » pour en "
                     "ranger plusieurs ensemble.", "hint")
        hint.setWordWrap(True)
        top.addWidget(hint)
        self.root.addWidget(self.panel)

        self.add_progress()
        self.add_buttons([("Ranger les photos", self.sort, True)], self.panel.dest)
        self.status.setText(status_html(GREY, "Aucun téléphone nécessaire"))
        self.panel.ready.connect(self.update_go)

        # dossier tapé à la main : on attend la fin de la saisie avant d'analyser
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(700)
        self.debounce.timeout.connect(self.apply_folder)
        self.folder.textChanged.connect(lambda *_: self.debounce.start())
        self.shown_once = False

    def showEvent(self, e):
        # analyse seulement quand l'écran est ouvert (pas au démarrage de l'appli)
        super().showEvent(e)
        if not self.shown_once:
            self.shown_once = True
            self.apply_folder()

    def apply_folder(self):
        path = self.folder.text().strip()
        if os.path.isdir(os.path.expanduser(path)) or not path:
            self.panel.set_root(path)

    def update_go(self, ok):
        if not self.busy():
            self.action_buttons[0].setEnabled(ok)

    def prereqs_ok(self):
        return True  # n'utilise ni adb ni libimobiledevice

    def update_devices(self, _iphones, _androids):
        pass

    def set_busy(self, busy):
        super().set_busy(busy)
        self.panel.setEnabled(not busy)

    def on_finished(self):
        super().on_finished()
        self.panel.rescan(force=True)  # les fichiers ont pu changer (déplacement, nouveaux rangés)

    def stop_background(self):
        self.debounce.stop()
        self.panel.stop_scan()

    def sort(self):
        cfg = self.panel.config()
        if cfg:
            start_sort(self, cfg)
