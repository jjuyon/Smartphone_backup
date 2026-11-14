"""Écran Android : synchronisation via adb."""
import os

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit

from ..core import android
from .common import GREEN, GREY, ORANGE, RED, BasePage, card, folder_row, label, status_html


class AndroidPage(BasePage):
    APP = "Sauvegarde Android"
    TARGET = "android"

    def __init__(self):
        super().__init__("Sauvegarde Android", "Copie et synchronise votre téléphone vers cet ordinateur.")

        c, l = card()
        l.addWidget(label("Téléphone et destination", "section"))
        row = QHBoxLayout()
        row.addWidget(label("Téléphone", "hint"))
        self.devs = QComboBox()
        self.devs.currentIndexChanged.connect(self.refresh_storages)
        row.addWidget(self.devs, 1)
        l.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("Stockage", "hint"))
        self.storage_box = QHBoxLayout()
        row.addLayout(self.storage_box, 1)
        l.addLayout(row)
        self.storage_checks = []   # [(QCheckBox, racine, préfixe local)]
        self.storage_serial = None
        self.set_storages(None, [])
        self.out = folder_row(self, l, "Destination", "android/out",
                              os.path.join(os.path.expanduser("~"), "Android-sauvegarde"))
        self.root.addWidget(c)

        c, l = card()
        l.addWidget(label("Contenu à copier", "section"))
        grid = QHBoxLayout()
        self.opts = {}
        for key, text in (("photos", "Photos et vidéos"), ("music", "Musique"),
                          ("docs", "Documents et téléchargements"), ("voice", "Enregistrements"),
                          ("whatsapp", "Médias WhatsApp")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            self.opts[key] = cb
            grid.addWidget(cb)
        l.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(label("Autre dossier", "hint"))
        self.extra = QLineEdit()
        self.extra.setPlaceholderText("Optionnel, ex. /sdcard/Obsidian ou Telegram")
        row.addWidget(self.extra, 1)
        l.addLayout(row)
        self.mirror = QCheckBox("Mode miroir : ranger dans « %s » ce qui a été supprimé du téléphone"
                                % android.TRASH)
        l.addWidget(self.mirror)
        self.root.addWidget(c)

        self.add_progress()
        self.add_buttons([("Sauvegarder / synchroniser", self.start, True)], self.out)
        self.update_devices([], [])

    # ------------------------------------------------------------- appareils
    def set_storages(self, serial, cards):
        """Reconstruit les cases : mémoire interne + une case par carte SD détectée."""
        while self.storage_box.count():
            item = self.storage_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.storage_checks = []
        self.storage_serial = serial
        internal = QCheckBox("Mémoire interne")
        internal.setChecked(True)
        self.storage_box.addWidget(internal)
        self.storage_checks.append((internal, "/sdcard", ""))
        if cards:
            for root, name in cards:
                cb = QCheckBox(f"{name} ({root.split('/')[-1]})")
                cb.setChecked(True)
                self.storage_box.addWidget(cb)
                self.storage_checks.append((cb, root, name))
        else:
            none = QCheckBox("Carte SD (aucune détectée)")
            none.setEnabled(False)
            self.storage_box.addWidget(none)
        self.storage_box.addStretch(1)

    def update_devices(self, _iphones, devs):
        if self.busy():
            return
        if not self.prereqs_ok():
            self.status.setText(status_html(RED, "Prérequis manquants"))
            return
        current = self.devs.currentData()
        listed = [(self.devs.itemText(i), self.devs.itemData(i)) for i in range(self.devs.count())]
        wanted = [(f"{model} ({serial})" + ("" if state == "device" else f" – {state}"), serial)
                  for serial, state, model in devs]
        if listed != wanted:
            self.devs.blockSignals(True)
            self.devs.clear()
            for text, serial in wanted:
                self.devs.addItem(text, serial)
            i = self.devs.findData(current) if current else -1
            if i >= 0:
                self.devs.setCurrentIndex(i)
            self.devs.blockSignals(False)
        self.ready = {serial for serial, state, _ in devs if state == "device"}
        self.refresh_storages()
        if self.ready:
            self.status.setText(status_html(GREEN, "Téléphone prêt"))
        elif any(state == "no" for _, state, _ in devs):  # « no permissions » : règles udev absentes
            self.status.setText(status_html(RED, "Accès USB refusé (règles udev)"))
            self.b_help.show()
        elif devs:
            self.status.setText(status_html(ORANGE, "Autorisez le débogage USB sur le téléphone"))
        else:
            self.status.setText(status_html(GREY, "Aucun téléphone"))

    def refresh_storages(self):
        serial = self.devs.currentData()
        if serial and serial in getattr(self, "ready", ()) and serial != self.storage_serial:
            self.set_storages(serial, android.list_storages(android.Adb(serial)))
        elif not serial and self.storage_serial:
            self.set_storages(None, [])

    # ------------------------------------------------------------- action
    def start(self):
        if not self.prereqs_ok():
            return self.help.emit(self.TARGET)
        serial = self.devs.currentData()
        if not serial or serial not in getattr(self, "ready", ()):
            return self.info("Aucun téléphone prêt. Branchez-le, activez le débogage USB "
                             "et acceptez l'autorisation sur l'écran.")
        storages = [(root, prefix) for cb, root, prefix in self.storage_checks if cb.isChecked()]
        if not storages:
            return self.info("Cochez au moins un stockage.")
        selected = android.build_selection({k: c.isChecked() for k, c in self.opts.items()},
                                           self.extra.text(), storages)
        if not selected:
            return self.info("Cochez au moins un contenu.")
        out, mirror = self.out.text(), self.mirror.isChecked()
        if not self.ensure_dir(out):
            return
        adb = android.Adb(serial)

        def job(log, progress, step, cancelled):
            android.sync(adb, out, selected, mirror, log, progress, cancelled)

        self.run_task(job, "Synchronisation en cours…", adb.cancel)
