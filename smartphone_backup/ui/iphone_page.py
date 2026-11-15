"""Écran iPhone : sauvegarde idevicebackup2 puis rangement."""
import os

from .qt import QCheckBox, QGridLayout, QHBoxLayout

from ..core import iphone
from .common import GREEN, GREY, ORANGE, RED, BasePage, card, folder_row, label, status_html


class IphonePage(BasePage):
    APP = "Sauvegarde iPhone"
    TARGET = "iphone"

    def __init__(self):
        super().__init__("Sauvegarde iPhone", "Récupérez vos photos, documents et musique.")
        self.udids = []
        home = os.path.expanduser("~")

        c, l = card()
        l.addWidget(label("Dossiers", "section"))
        self.raw = folder_row(self, l, "Sauvegarde brute", "iphone/raw",
                              os.path.join(home, "iPhone-sauvegarde-brute"))
        self.out = folder_row(self, l, "Destination", "iphone/out", os.path.join(home, "iPhone-contenu"))
        self.root.addWidget(c)

        c, l = card()
        l.addWidget(label("Contenu à récupérer", "section"))
        grid = QGridLayout()
        self.opts = {}
        for i, (key, text) in enumerate((("photos", "Photos et vidéos"), ("docs", "Documents"),
                          ("music", "Musique"), ("voice", "Notes vocales"))):
            cb = QCheckBox(text)
            cb.setChecked(True)
            self.opts[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        l.addLayout(grid)
        l.addWidget(label("La sauvegarde de l'iPhone doit être non chiffrée. Les fichiers déjà "
                          "rangés ne sont pas recopiés.", "hint"))
        self.root.addWidget(c)

        self.add_progress()
        self.add_buttons([("Sauvegarder l'iPhone puis ranger", lambda: self.start(True), True),
                          ("Ranger une sauvegarde existante", lambda: self.start(False), False)],
                         self.out)
        self.update_devices([], [])

    def update_devices(self, iphones, _androids):
        if self.busy():
            return
        self.udids = [u for u, _ in iphones]
        if not self.prereqs_ok():
            self.status.setText(status_html(RED, "Prérequis manquants"))
        elif len(iphones) == 1:
            self.status.setText(status_html(GREEN, f"{iphones[0][1]} détecté"))
        elif iphones:
            self.status.setText(status_html(ORANGE, f"{len(iphones)} iPhone branchés (un seul à la fois)"))
        else:
            self.status.setText(status_html(GREY, "Aucun iPhone détecté"))

    def start(self, do_backup):
        opts = {k: cb.isChecked() for k, cb in self.opts.items()}
        if do_backup and not self.prereqs_ok():
            return self.help.emit(self.TARGET)
        if not any(opts.values()):
            return self.info("Cochez au moins un type de contenu.")
        if do_backup and len(self.udids) > 1:
            return self.info("Plusieurs iPhone sont branchés : n'en laissez qu'un.")
        raw, out = self.raw.text(), self.out.text()
        if not self.ensure_dir(out):
            return
        udid = self.udids[0] if self.udids else None
        procs = []

        def job(log, progress, step, cancelled):
            if do_backup:
                step("Étape 1/2 : sauvegarde de l'iPhone")
                iphone.run_backup(raw, log, progress, cancelled, procs, udid)
            progress(0)
            step("Étape 2/2 : rangement des fichiers" if do_backup else "Rangement des fichiers")
            iphone.organize(raw, out, opts, log, progress, cancelled)

        def on_cancel():
            for p in procs:
                try:
                    p.terminate()
                except Exception:
                    pass

        self.run_task(job, "Démarrage…", on_cancel)
