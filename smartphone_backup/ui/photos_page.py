"""Écran « Photos » : ranger et dédoublonner n'importe quel dossier, sans téléphone."""
import os

from .qt import QStandardPaths

from .common import GREY, BasePage, card, folder_row, label, status_html


class PhotosPage(BasePage):
    APP = "Photos"
    TARGET = ""

    def __init__(self):
        super().__init__("Ranger des photos", "Classez par date et nettoyez les doublons de n'importe "
                                               "quel dossier.")
        pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) \
            or os.path.expanduser("~")
        c, l = card()
        l.addWidget(label("Dossier de photos", "section"))
        self.folder = folder_row(self, l, "Dossier", "photos/folder", pictures)
        hint = label("Par exemple une ancienne sauvegarde, la carte mémoire d'un appareil photo, un disque "
                     "externe… Les sous-dossiers sont inclus.", "hint")
        hint.setWordWrap(True)
        l.addWidget(hint)
        self.root.addWidget(c)

        c, l = card()
        l.addWidget(label("Que faire ?", "section"))
        for title, text in (
                ("Rechercher les doublons", "Trouve les photos et vidéos présentes plusieurs fois (copies "
                 "identiques, et si vous le souhaitez photos redimensionnées ou recompressées), puis les met "
                 "à la corbeille ou de côté après votre vérification."),
                ("Ranger les photos", "Les classe par année, mois, jour ou événement dans un nouveau dossier, "
                 "sans doublons ; les originaux ne bougent pas, sauf si vous choisissez « Déplacer ».")):
            l.addWidget(label(f"<b>{title}</b>"))
            t = label(text, "hint")
            t.setWordWrap(True)
            l.addWidget(t)
        self.root.addWidget(c)

        self.add_progress()
        self.add_buttons([("Ranger les photos…", self.sort, True),
                          ("Rechercher les doublons…", self.find_dupes, False)], self.folder)
        self.status.setText(status_html(GREY, "Aucun téléphone nécessaire"))

    def prereqs_ok(self):
        return True  # n'utilise ni adb ni libimobiledevice

    def update_devices(self, _iphones, _androids):
        pass

    def check_folder(self):
        path = self.folder.text().strip()
        if not os.path.isdir(path):
            self.info("Choisissez un dossier de photos existant.")
            return None
        return path

    def sort(self):
        path = self.check_folder()
        if path:
            from .photo_sort_dialog import run_sort
            run_sort(self, path)

    def find_dupes(self):
        path = self.check_folder()
        if path:
            from .dupes_dialog import DuplicatesDialog
            dlg = DuplicatesDialog(self, [path])
            dlg.exec()
            dlg.stop_scan()
            dlg.deleteLater()  # libère la fenêtre tout de suite (évite un plantage de PySide à la sortie)
