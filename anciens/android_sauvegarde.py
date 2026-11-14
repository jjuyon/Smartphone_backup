#!/usr/bin/env python3
"""Sauvegarde / synchronisation d'un téléphone Android vers Linux (via adb).

Copie photos, vidéos, musique, documents, téléchargements, enregistrements et médias
WhatsApp vers un dossier lisible. Les sauvegardes suivantes sont incrémentales : seuls
les fichiers nouveaux ou modifiés sont copiés.

Prérequis : adb (sudo apt install adb), « Débogage USB » activé sur le téléphone
(Paramètres > Options pour les développeurs), PySide6 (pip install PySide6).
Doit être placé à côté de iphone_sauvegarde_qt.py (qui fournit le style).
"""
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

# (dossier sur le téléphone, dossier de destination local)
SOURCES = {
    "photos": [("DCIM", "Photos et vidéos/DCIM"), ("Pictures", "Photos et vidéos/Pictures"),
               ("Movies", "Photos et vidéos/Movies")],
    "music": [("Music", "Musique")],
    "voice": [("Recordings", "Enregistrements vocaux")],
    "docs": [("Documents", "Documents"), ("Download", "Téléchargements")],
    "whatsapp": [("Android/media/com.whatsapp/WhatsApp/Media", "WhatsApp"),
                 ("WhatsApp/Media", "WhatsApp")],
}
PHONE_ROOT = "/sdcard"
TRASH = "_Corbeille-sync"


# --------------------------------------------------------------------- adb
class Adb:
    def __init__(self, serial=None):
        self.serial = serial
        self.procs = []

    def cmd(self, *args):
        base = ["adb"] + (["-s", self.serial] if self.serial else [])
        return base + list(args)

    def run(self, *args, timeout=120):
        return subprocess.run(self.cmd(*args), capture_output=True, text=True,
                              errors="replace", timeout=timeout)

    def cancel(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass


def adb_available():
    return shutil.which("adb") is not None


def list_devices():
    """[(serial, état, modèle)] — état : device / unauthorized / offline."""
    if not adb_available():
        return []
    try:
        out = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return []
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("*"):
            m = re.search(r"model:(\S+)", line)
            devs.append((parts[0], parts[1], m.group(1).replace("_", " ") if m else parts[0]))
    return devs


def list_remote(adb, src):
    """{chemin relatif: (taille, mtime)} pour un dossier du téléphone, ou None s'il n'existe pas."""
    q = src.replace("'", "'\\''")
    r = adb.run("shell", f"find '{q}' -type f -exec stat -c '%s|%Y|%n' {{}} +", timeout=600)
    files, prefix = {}, src.rstrip("/") + "/"
    for line in r.stdout.splitlines():
        parts = line.rstrip("\r").split("|", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[2].startswith(prefix):
            files[parts[2][len(prefix):]] = (int(parts[0]), int(parts[1]))
    if not files and r.returncode != 0:
        return None
    return files


def needs_copy(local, size, mtime):
    try:
        st = os.stat(local)
    except OSError:
        return True
    return st.st_size != size or abs(int(st.st_mtime) - mtime) > 2


# ------------------------------------------------------------ synchronisation
def sync(adb, out, selected, mirror, log, progress, cancel):
    """selected : liste de (dossier téléphone absolu, dossier local relatif)."""
    plans = []  # (src, local_dir, remote, bulk, todo)
    log("Analyse du téléphone…")
    for src, local_rel in selected:
        if cancel():
            return {}
        remote = list_remote(adb, src)
        if remote is None:
            log(f"  {src} : absent, ignoré")
            continue
        local_dir = os.path.join(out, local_rel)
        # copie en bloc seulement si le dossier local n'existe pas et n'est pas déjà
        # destiné à un autre dossier du téléphone (ex. ancien et nouveau WhatsApp)
        bulk = bool(remote) and not os.path.exists(local_dir) \
            and all(local_dir != p[1] for p in plans)
        todo = list(remote) if bulk else [r for r, (s, m) in remote.items()
                                          if needs_copy(os.path.join(local_dir, *r.split("/")), s, m)]
        log(f"  {src} : {len(remote)} fichiers, {len(todo)} à copier")
        plans.append((src, local_dir, remote, bulk, todo))

    total = sum(remote[r][0] for _, _, remote, _, todo in plans for r in todo) or 1
    done = 0
    copied = errors = removed = 0
    for src, local_dir, remote, bulk, todo in plans:
        if cancel():
            log("Annulé.")
            break
        if bulk:
            n_files = len(todo)
            avg = sum(remote[r][0] for r in todo) / max(n_files, 1)
            staging = os.path.join(out, ".transfert-en-cours")
            shutil.rmtree(staging, ignore_errors=True)
            os.makedirs(staging)
            log(f"Copie de {src} ({n_files} fichiers)…")
            p = subprocess.Popen(adb.cmd("pull", "-a", src, staging), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, bufsize=0)
            adb.procs.append(p)
            buf, n = b"", 0
            while True:
                chunk = p.stdout.read(512)
                if not chunk:
                    break
                buf += chunk
                parts = re.split(rb"[\r\n]", buf)
                buf = parts.pop()
                for raw in parts:
                    if re.match(rb"\[\s*100%\]", raw):
                        n += 1
                        progress(min(100, (done + n * avg) * 100 / total))
            p.wait()
            made = os.path.join(staging, os.path.basename(src.rstrip("/")))
            if p.returncode == 0 and os.path.isdir(made) and not cancel():
                os.makedirs(os.path.dirname(local_dir) or ".", exist_ok=True)
                shutil.move(made, local_dir)
                copied += n_files
            else:
                errors += n_files
                log(f"  Échec ou interruption pour {src}")
            shutil.rmtree(staging, ignore_errors=True)
            done += sum(remote[r][0] for r in todo)
        else:
            for rel in todo:
                if cancel():
                    break
                size, mtime = remote[rel]
                dest = os.path.join(local_dir, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                r = adb.run("pull", "-a", f"{src}/{rel}", dest, timeout=3600)
                if r.returncode == 0:
                    copied += 1
                else:
                    errors += 1
                    log(f"  Erreur : {rel}")
                done += size
                progress(min(100, done * 100 / total))
    if mirror and not cancel():
        # plusieurs dossiers du téléphone peuvent alimenter le même dossier local
        union = {}
        for _, local_dir, remote, _, _ in plans:
            union.setdefault(local_dir, set()).update(remote)
        for local_dir, rels in union.items():
            if not os.path.isdir(local_dir):
                continue
            if not rels:
                log(f"  Miroir ignoré pour {local_dir} : liste du téléphone vide (par sécurité)")
                continue
            removed += move_deleted(out, local_dir, rels, log)
    progress(100)
    log(f"Terminé : {copied} copiés, {errors} erreurs" + (f", {removed} déplacés dans {TRASH}." if mirror else "."))
    return {"copied": copied, "errors": errors, "removed": removed}


def move_deleted(out, local_dir, remote, log):
    """Mode miroir : déplace dans _Corbeille-sync ce qui n'existe plus sur le téléphone."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    n = 0
    for base, _, names in os.walk(local_dir):
        for name in names:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, local_dir).replace(os.sep, "/")
            if rel not in remote:
                dest = os.path.join(out, TRASH, stamp, os.path.relpath(full, out))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(full, dest)
                n += 1
    if n:
        log(f"  {n} fichier(s) supprimés du téléphone déplacés dans {TRASH}/{stamp}")
    return n


def list_storages(adb):
    """Cartes SD / stockages externes : [(chemin, nom)] ex. ('/storage/1A2B-3C4D', 'Carte SD')."""
    try:
        r = adb.run("shell", "ls /storage", timeout=15)
    except Exception:
        return []
    ids = [n.strip() for n in r.stdout.splitlines()
           if n.strip() and n.strip() not in ("emulated", "self") and not n.startswith("ls:")]
    return [(f"/storage/{i}", "Carte SD" if len(ids) == 1 else f"Carte SD {i}") for i in ids]


def build_selection(opts, extra, storages=(("/sdcard", ""),)):
    """storages : [(racine sur le téléphone, préfixe du dossier local)]."""
    sel = []
    for root, prefix in storages:
        for key, entries in SOURCES.items():
            if opts.get(key):
                sel += [(f"{root}/{src}", os.path.join(prefix, local) if prefix else local)
                        for src, local in entries]
    if extra.strip():
        p = extra.strip().rstrip("/")
        sel.append((p if p.startswith("/") else f"{PHONE_ROOT}/{p}", "Autres/" + os.path.basename(p)))
    return sel


# ------------------------------------------------------------------ interface
def main_gui():
    from PySide6.QtCore import QThread, QTimer, QUrl, Signal
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                                   QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
                                   QPushButton, QVBoxLayout, QWidget)
    from iphone_sauvegarde_qt import STYLE, card, dark_palette, label

    class Worker(QThread):
        log = Signal(str)
        progress = Signal(int)
        error = Signal(str)

        def __init__(self, adb, out, selected, mirror):
            super().__init__()
            self.adb, self.out, self.selected, self.mirror = adb, out, selected, mirror
            self.cancelled = False

        def cancel(self):
            self.cancelled = True
            self.adb.cancel()

        def run(self):
            try:
                os.makedirs(self.out, exist_ok=True)
                sync(self.adb, self.out, self.selected, self.mirror, self.log.emit,
                     lambda v: self.progress.emit(int(v)), lambda: self.cancelled)
            except Exception as e:
                self.error.emit(str(e))

    class Window(QWidget):
        def __init__(self):
            super().__init__()
            self.setObjectName("root")
            self.setWindowTitle("Sauvegarde Android")
            self.resize(760, 800)
            self.worker = None
            self.errored = False
            root = QVBoxLayout(self)
            root.setContentsMargins(26, 24, 26, 24)
            root.setSpacing(14)

            head = QHBoxLayout()
            titles = QVBoxLayout()
            titles.addWidget(label("Sauvegarde Android", "title"))
            titles.addWidget(label("Copie et synchronise votre téléphone vers cet ordinateur.", "subtitle"))
            head.addLayout(titles, 1)
            self.status = QLabel()
            head.addWidget(self.status)
            root.addLayout(head)

            c, l = card()
            l.addWidget(label("Téléphone et destination", "section"))
            row = QHBoxLayout()
            row.addWidget(label("Téléphone", "hint"))
            self.devs = QComboBox()
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
            row = QHBoxLayout()
            row.addWidget(label("Destination", "hint"))
            self.out = QLineEdit(os.path.join(os.path.expanduser("~"), "Android-sauvegarde"))
            b = QPushButton("Parcourir…")
            b.clicked.connect(lambda: self.out.setText(
                QFileDialog.getExistingDirectory(self, "Destination", self.out.text()) or self.out.text()))
            row.addWidget(self.out, 1)
            row.addWidget(b)
            l.addLayout(row)
            root.addWidget(c)

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
            self.mirror = QCheckBox("Mode miroir : ranger dans « %s » ce qui a été supprimé du téléphone" % TRASH)
            l.addWidget(self.mirror)
            root.addWidget(c)

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
            root.addWidget(c, 1)

            btns = QHBoxLayout()
            self.b_go = QPushButton("Sauvegarder / synchroniser")
            self.b_go.setObjectName("primary")
            self.b_open = QPushButton("Ouvrir le dossier")
            self.b_cancel = QPushButton("Annuler")
            self.b_cancel.setObjectName("danger")
            self.b_cancel.setEnabled(False)
            btns.addWidget(self.b_go)
            btns.addStretch(1)
            btns.addWidget(self.b_open)
            btns.addWidget(self.b_cancel)
            root.addLayout(btns)
            self.b_go.clicked.connect(self.start)
            self.b_cancel.clicked.connect(lambda: self.worker and self.worker.cancel())
            self.b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.out.text())))

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(3000)
            self.refresh()

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

        def refresh(self):
            if self.worker and self.worker.isRunning():
                return
            if not adb_available():
                self.status.setText('<span style="color:#ff8a8a">●</span>&nbsp; adb introuvable')
                return
            devs = list_devices()
            current = self.devs.currentData()
            self.devs.clear()
            ready = [d for d in devs if d[1] == "device"]
            for serial, state, model in devs:
                self.devs.addItem(f"{model} ({serial})" + ("" if state == "device" else f" – {state}"), serial)
            if current:
                i = self.devs.findData(current)
                if i >= 0:
                    self.devs.setCurrentIndex(i)
            serial = self.devs.currentData()
            if ready and serial and serial != self.storage_serial:
                self.set_storages(serial, list_storages(Adb(serial)))
            if ready:
                self.status.setText('<span style="color:#3ddc84">●</span>&nbsp; Téléphone prêt')
            elif devs:
                self.status.setText('<span style="color:#f0b429">●</span>&nbsp; Autorisez le débogage USB')
            else:
                self.status.setText('<span style="color:#8b93a1">●</span>&nbsp; Aucun téléphone')

        def start(self):
            if not adb_available():
                QMessageBox.critical(self, "adb introuvable", "Installez adb :\nsudo apt install adb")
                return
            serial = self.devs.currentData()
            if not serial:
                QMessageBox.information(self, "Sauvegarde Android",
                                        "Aucun téléphone. Branchez-le, activez le débogage USB "
                                        "et acceptez l'autorisation sur l'écran.")
                return
            storages = [(root, prefix) for cb, root, prefix in self.storage_checks if cb.isChecked()]
            if not storages:
                QMessageBox.information(self, "Sauvegarde Android", "Cochez au moins un stockage.")
                return
            selected = build_selection({k: c.isChecked() for k, c in self.opts.items()},
                                       self.extra.text(), storages)
            if not selected:
                QMessageBox.information(self, "Sauvegarde Android", "Cochez au moins un contenu.")
                return
            self.logbox.clear()
            self.bar.setValue(0)
            self.step.setText("Synchronisation en cours…")
            self.errored = False
            self.worker = Worker(Adb(serial), self.out.text(), selected, self.mirror.isChecked())
            self.worker.log.connect(self.logbox.appendPlainText)
            self.worker.progress.connect(self.bar.setValue)
            self.worker.error.connect(self.on_error)
            self.worker.finished.connect(self.on_finished)
            self.b_go.setEnabled(False)
            self.b_cancel.setEnabled(True)
            self.worker.start()

        def on_error(self, msg):
            self.errored = True
            self.logbox.appendPlainText("ERREUR : " + msg)
            self.step.setText("Une erreur est survenue")
            QMessageBox.critical(self, "Erreur", msg)

        def on_finished(self):
            self.b_go.setEnabled(True)
            self.b_cancel.setEnabled(False)
            if not self.errored:
                self.step.setText("Annulé" if self.worker.cancelled else "Terminé ✓")
            self.refresh()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(dark_palette())
    app.setStyleSheet(STYLE)
    w = Window()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main_gui()
