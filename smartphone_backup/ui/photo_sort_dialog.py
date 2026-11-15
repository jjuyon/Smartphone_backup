"""Rangement des photos : formulaire (dossiers, classement, options, aperçu) partagé par la fenêtre
« Ranger les photos » de l'écran Android et par l'écran « Photos » de l'accueil."""
import hashlib
import os

from .qt import Qt, QThread, Signal
from .qt import (QButtonGroup, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLineEdit,
                 QMessageBox, QPushButton, QRadioButton, QSpinBox, QTreeWidget,
                 QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import photos
from .common import ORANGE, card, fit_to_screen, label, progress_bar, scrollable, settings


def find_sources(root):
    """Dossiers de photos d'une sauvegarde Android : [(chemin, nom affiché, coché par défaut)]."""
    found = []
    if not os.path.isdir(root):
        return found
    tops = [("", root)] + [(d, os.path.join(root, d)) for d in sorted(os.listdir(root))
                           if d.startswith("Carte SD") and os.path.isdir(os.path.join(root, d))]
    for prefix, base in tops:
        p = os.path.join(base, "Photos et vidéos")
        if os.path.isdir(p):
            found.append((p, os.path.join(prefix, "Photos et vidéos"), True))
        wa = os.path.join(base, "WhatsApp")
        if os.path.isdir(wa):
            for d in sorted(os.listdir(wa)):
                if any(k in d for k in ("Images", "Video", "Animated")) and os.path.isdir(os.path.join(wa, d)):
                    found.append((os.path.join(wa, d), os.path.join(prefix, "WhatsApp", d) + " (reçues)", False))
    return found


class Scanner(QThread):
    """Lit les dates de toutes les photos en arrière-plan."""
    progress = Signal(int)
    done = Signal(object)

    def __init__(self, sources, exclude):
        super().__init__()
        self.sources, self.exclude = sources, exclude
        self.stop = False

    def run(self):
        items = photos.scan(self.sources, self.exclude, lambda v: self.progress.emit(int(v)),
                            lambda: self.stop)
        if not self.stop:
            self.done.emit(items)


def dest_key(root):
    """Destination mémorisée pour chaque dossier de départ."""
    return "sort/out_" + hashlib.md5(os.path.abspath(root).encode()).hexdigest()[:12]


class SortPanel(QWidget):
    """Cartes Photos à ranger / Classement / Options / Destination / Aperçu."""
    ready = Signal(bool)  # le rangement peut être lancé

    def __init__(self, parent=None, android=False):
        super().__init__(parent)
        self.android = android
        self.s = settings()
        self.root_dir = ""
        self.items = None       # résultat de l'analyse (None = en cours)
        self.scanner = None
        self.scan_key = None
        self.src_checks = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # --- sources
        c, l = card()
        l.addWidget(label("Photos à ranger", "section"))
        self.top_box = QVBoxLayout()  # choix du dossier de départ (écran Photos)
        l.addLayout(self.top_box)
        self.src_box = QVBoxLayout()
        l.addLayout(self.src_box)
        self.no_src = label("", "hint")
        self.no_src.setWordWrap(True)
        l.addWidget(self.no_src)
        b_add = QPushButton("Ajouter un dossier…")
        b_add.clicked.connect(self.pick_source)
        b_dupes = QPushButton("Rechercher les doublons…")
        b_dupes.setToolTip("Voir les photos et vidéos en double et les retirer avant de ranger")
        b_dupes.clicked.connect(self.open_dupes)
        row = QHBoxLayout()
        row.addWidget(b_add)
        row.addWidget(b_dupes)
        row.addStretch(1)
        l.addLayout(row)
        root.addWidget(c)

        # --- classement
        c, l = card()
        l.addWidget(label("Classement", "section"))
        self.structure = QButtonGroup(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(0)
        current = self.s.value("sort/structure", "year_month")
        for i, (key, (name, example)) in enumerate(photos.STRUCTURES.items()):
            rb = QRadioButton(name)
            rb.setProperty("key", key)
            rb.setChecked(key == current)
            self.structure.addButton(rb, i)
            grid.addWidget(rb, i, 0)
            grid.addWidget(label(example, "hint"), i, 1)
        grid.setColumnStretch(1, 1)
        l.addLayout(grid)
        ev = QGridLayout()
        ev.setContentsMargins(28, 0, 0, 0)
        self.gap = QSpinBox()
        self.gap.setRange(1, 96)
        self.gap.setSuffix(" h")
        self.gap.setValue(int(self.s.value("sort/gap", 8)))
        self.min_count = QSpinBox()
        self.min_count.setRange(1, 100)
        self.min_count.setValue(int(self.s.value("sort/min", 5)))
        ev.addWidget(label("Nouvel événement après une pause de", "hint"), 0, 0)
        ev.addWidget(self.gap, 0, 1)
        ev.addWidget(label("Au moins", "hint"), 1, 0, Qt.AlignRight)
        ev.addWidget(self.min_count, 1, 1)
        small = label("photos par événement, sinon « AAAA-MM divers »", "hint")
        small.setWordWrap(True)
        ev.addWidget(small, 1, 2)
        ev.setColumnStretch(2, 1)
        self.ev_row = QWidget()
        self.ev_row.setLayout(ev)
        l.addWidget(self.ev_row)
        root.addWidget(c)

        # --- options
        c, l = card()
        l.addWidget(label("Options", "section"))
        self.opt = {}
        for key, text, tip in (
                ("skip_dupes", "Ne pas ranger les doublons",
                 "une seule copie de chaque photo ou vidéo identique (rien n'est supprimé)"),
                ("videos_apart", "Séparer photos et vidéos", "Photos / 2024 / …  et  Vidéos / 2024 / …"),
                ("by_origin", "Séparer par origine",
                 "Appareil photo / Captures d'écran / WhatsApp / Autres images, puis la date"),
                ("rename", "Renommer avec la date", "IMG_1234.jpg → 2024-03-15_14-32-05.jpg")):
            cb = QCheckBox(text)
            cb.setChecked(self.s.value("sort/" + key, "true" if key == "skip_dupes" else "false") == "true")
            cb.setToolTip(tip)
            self.opt[key] = cb
            row = QHBoxLayout()
            row.addWidget(cb)
            hint = label(tip, "hint")
            hint.setWordWrap(True)
            row.addWidget(hint, 1)
            l.addLayout(row)
        root.addWidget(c)

        # --- destination
        c, l = card()
        l.addWidget(label("Destination", "section"))
        row = QHBoxLayout()
        row.addWidget(label("Dossier", "hint"))
        self.dest = QLineEdit()
        self.dest.textEdited.connect(self.save_dest)
        self.dest.editingFinished.connect(self.rescan)
        b_dest = QPushButton("Parcourir…")
        b_dest.clicked.connect(self.pick_dest)
        row.addWidget(self.dest, 1)
        row.addWidget(b_dest)
        l.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("Méthode", "hint"))
        self.mode = QComboBox()
        for key, text in photos.MODES.items():
            self.mode.addItem(text, key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.s.value("sort/mode", "link"))))
        row.addWidget(self.mode, 1)
        l.addLayout(row)
        self.mode_hint = label("", "hint")
        self.mode_hint.setWordWrap(True)
        l.addWidget(self.mode_hint)
        root.addWidget(c)

        # --- aperçu
        c, l = card()
        l.addWidget(label("Aperçu", "section"))
        self.summary = label("", "hint")
        self.summary.setWordWrap(True)
        l.addWidget(self.summary)
        self.bar = progress_bar()
        self.bar.hide()
        l.addWidget(self.bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Dossier", "Fichiers"])
        self.tree.setMinimumHeight(220)
        self.tree.setColumnWidth(0, 420)
        l.addWidget(self.tree)
        root.addWidget(c, 1)

        self.structure.buttonClicked.connect(lambda *_: self.refresh())
        for w in (self.gap, self.min_count):
            w.valueChanged.connect(lambda *_: self.refresh())
        for cb in self.opt.values():
            cb.toggled.connect(lambda *_: self.refresh())
        self.mode.currentIndexChanged.connect(lambda *_: self.refresh())

    # ------------------------------------------------------------- dossiers
    def set_root(self, root):
        """Dossier de départ : sauvegarde Android, ou n'importe quel dossier de photos."""
        root = os.path.abspath(os.path.expanduser(root)) if root else ""
        if root == self.root_dir:
            return
        self.root_dir = root
        for cb, _ in self.src_checks:
            cb.deleteLater()
        self.src_checks = []
        found = find_sources(root)
        if not found and not self.android and os.path.isdir(root):
            # dossier quelconque : on le range en entier
            found = [(root, "Tout le dossier, sous-dossiers compris" if self.top_box.count() else root, True)]
        for path, name, default in found:
            self.add_source(path, name, default)
        self.no_src.setText("" if self.src_checks else
                            (f"Aucune photo sauvegardée dans « {root} ». Lancez d'abord une sauvegarde, "
                             "ou ajoutez un dossier." if self.android else
                             f"Le dossier « {root} » n'existe pas. Choisissez un dossier."))
        self.no_src.setVisible(not self.src_checks)
        self.dest.setText(self.s.value(dest_key(root), os.path.join(root, "Photos rangées")))
        self.scan_key = None
        self.rescan()

    def save_dest(self, text):
        self.s.setValue(dest_key(self.root_dir), text)

    def pick_dest(self):
        from .folder_picker import pick_folder
        path = pick_folder(self, "Destination", self.dest.text())
        if path:
            self.dest.setText(path)
            self.save_dest(path)
            self.rescan()

    def add_source(self, path, name, checked):
        self.no_src.hide()
        cb = QCheckBox(name)
        cb.setToolTip(path)
        cb.setChecked(checked)
        cb.toggled.connect(lambda *_: self.rescan())
        self.src_box.addWidget(cb)
        self.src_checks.append((cb, path))

    def pick_source(self):
        from .folder_picker import pick_folder
        start = self.src_checks[0][1] if self.src_checks else (self.root_dir or os.path.expanduser("~"))
        path = pick_folder(self, "Dossier de photos", start)
        if path and all(p != path for _, p in self.src_checks):
            self.add_source(path, path, True)
            self.rescan()

    def sources(self):
        return [p for cb, p in self.src_checks if cb.isChecked()]

    # ------------------------------------------------------------- analyse / aperçu
    def stop_scan(self):
        if self.scanner:
            self.scanner.stop = True
            self.scanner.wait(10000)
            self.scanner = None

    def rescan(self, force=False):
        key = (tuple(self.sources()), self.dest.text())
        if key == self.scan_key and not force:
            return
        self.scan_key = key
        self.stop_scan()
        self.items = None
        self.tree.clear()
        if not self.sources():
            self.bar.hide()
            self.summary.setText("Cochez au moins un dossier de photos.")
            self.refresh()
            return
        self.bar.setValue(0)
        self.bar.show()
        self.summary.setText("Lecture des dates de prise de vue…")
        self.scanner = Scanner(self.sources(), self.dest.text())
        self.scanner.progress.connect(self.bar.setValue)
        self.scanner.done.connect(self.scanned)
        self.scanner.start()
        self.refresh()

    def scanned(self, items):
        self.items = items
        self.bar.hide()
        self.refresh()

    def options(self):
        return dict(structure=self.structure.checkedButton().property("key"),
                    gap_hours=self.gap.value(), min_count=self.min_count.value(),
                    **{k: cb.isChecked() for k, cb in self.opt.items()})

    def refresh(self):
        o = self.options()
        self.ev_row.setVisible(o["structure"] == "event")
        mode = self.mode.currentData()
        origin = "de sauvegarde : la prochaine synchronisation les recopiera depuis le téléphone" \
            if self.android else "d'origine"
        self.mode_hint.setText({
            "link": "Les photos apparaissent aussi dans le dossier rangé sans occuper de place en plus ; "
                    "supprimer l'une des deux ne supprime pas l'autre. Si le disque ne le permet pas "
                    "(clé USB FAT/exFAT, NTFS…), elles sont copiées.",
            "copy": "Les photos sont dupliquées : prévoyez autant de place libre que leur taille.",
            "move": f'<span style="color:{ORANGE}">Les photos quittent le dossier {origin}.</span>',
        }[mode])
        self.ready.emit(bool(self.sources()) and self.items != [])
        if self.items is None:
            return
        if not self.items:
            self.summary.setText("Aucune photo ni vidéo trouvée dans les dossiers cochés.")
            self.tree.clear()
            return
        steps = photos.plan(self.items, **o)
        self.fill_tree(steps)
        n_vid = sum(it.video for it in self.items)
        years = sorted({it.date.year for it in self.items})
        hows = {}
        for it in self.items:
            hows[it.how] = hows.get(it.how, 0) + 1
        sure = 100 - round(hows.get("mtime", 0) * 100 / len(self.items))
        n_dup = sum(it.dup for it in self.items)

        def n(v):  # 12 345
            return f"{v:,}".replace(",", " ")
        n_dirs = len({os.path.dirname(rel) for _, rel in steps})
        self.summary.setText(
            f"<b>{n(len(self.items) - n_vid)} photos et {n(n_vid)} vidéos</b>, de {years[0]} à {years[-1]}, "
            f"rangées dans {n(n_dirs)} dossiers. Date de prise de vue trouvée pour {sure} % des fichiers"
            + (" ; les autres sont classés d'après la date du fichier." if sure < 100 else ".")
            + (f"<br>{n(n_dup)} copies identiques " + ("ne seront pas rangées." if o["skip_dupes"] else
               "seront rangées aussi (renommées _1, _2…).") if n_dup else ""))

    def fill_tree(self, steps):
        counts = {}
        for _, rel in steps:
            parts = rel.split(os.sep)[:-1]
            for i in range(1, len(parts) + 1):
                counts[tuple(parts[:i])] = counts.get(tuple(parts[:i]), 0) + 1
        self.tree.clear()
        nodes = {}
        for key in sorted(counts):
            parent = nodes.get(key[:-1], self.tree.invisibleRootItem())
            it = QTreeWidgetItem([key[-1], str(counts[key])])
            it.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            parent.addChild(it)
            nodes[key] = it
        top = self.tree.invisibleRootItem()
        for i in range(top.childCount()):
            top.child(i).setExpanded(top.childCount() <= 3)  # dossiers Photos/Vidéos ou origines

    # ------------------------------------------------------------- validation
    def config(self):
        """Réglages validés pour lancer le rangement, ou None (message affiché)."""
        title = "Ranger les photos"
        dest = self.dest.text().strip()
        srcs = self.sources()
        if not srcs:
            QMessageBox.information(self, title, "Cochez au moins un dossier de photos.")
            return None
        if not dest:
            QMessageBox.information(self, title, "Choisissez un dossier de destination.")
            return None
        real = os.path.realpath(dest)
        if any(os.path.realpath(s) == real for s in srcs):
            QMessageBox.information(self, title, "La destination doit être différente des dossiers de photos.")
            return None
        mode = self.mode.currentData()
        warn = ("Déplacer les photos hors de la sauvegarde ?\n\nLa prochaine synchronisation les recopiera "
                "depuis le téléphone, sauf si elles en ont été supprimées.") if self.android else \
            "Déplacer les photos hors de leur dossier d'origine vers la destination ?"
        if mode == "move" and QMessageBox.question(self, title, warn) != QMessageBox.Yes:
            return None
        o = self.options()
        for k, v in o.items():
            self.s.setValue("sort/" + {"gap_hours": "gap", "min_count": "min"}.get(k, k),
                            ("true" if v else "false") if isinstance(v, bool) else v)
        self.s.setValue("sort/mode", mode)
        fresh = self.scan_key == (tuple(srcs), self.dest.text())
        return dict(sources=srcs, dest=dest, mode=mode, options=o, items=self.items if fresh else None)

    def open_dupes(self):
        if not self.sources():
            return QMessageBox.information(self, "Doublons", "Cochez au moins un dossier de photos.")
        from .dupes_dialog import DuplicatesDialog
        dlg = DuplicatesDialog(self, self.sources(), self.android)
        dlg.exec()
        dlg.stop_scan()
        dlg.deleteLater()  # libère la fenêtre tout de suite (évite un plantage de PySide à la sortie)
        if dlg.changed:  # des fichiers ont été retirés : nouvelle analyse
            self.rescan(force=True)


class PhotoSortDialog(QDialog):
    """Fenêtre de rangement (écran Android)."""

    def __init__(self, parent, backup_root, android=False):
        super().__init__(parent)
        self.setWindowTitle("Ranger les photos")
        self.setObjectName("root")
        fit_to_screen(self, 860, 780)
        self.result_config = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 16)
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 22, 24, 8)
        root.setSpacing(14)
        root.addWidget(label("Ranger les photos", "title"))
        root.addWidget(label("Classe les photos et vidéos selon leur date de prise de vue.", "subtitle"))
        self.panel = SortPanel(self, android)
        root.addWidget(self.panel, 1)
        outer.addWidget(scrollable(body), 1)

        btns = QHBoxLayout()
        btns.setContentsMargins(24, 0, 24, 0)
        btns.addStretch(1)
        b_cancel = QPushButton("Annuler")
        b_cancel.clicked.connect(self.reject)
        self.b_go = QPushButton("Ranger")
        self.b_go.setObjectName("primary")
        self.b_go.clicked.connect(self.go)
        btns.addWidget(b_cancel)
        btns.addWidget(self.b_go)
        outer.addLayout(btns)
        self.panel.ready.connect(self.b_go.setEnabled)
        self.panel.set_root(backup_root)

    def stop_scan(self):
        self.panel.stop_scan()

    def go(self):
        self.result_config = self.panel.config()
        if self.result_config:
            self.accept()


def start_sort(page, cfg):
    """Lance le rangement dans la page (barre de progression, journal, annulation)."""
    if not page.ensure_dir(cfg["dest"]):
        return

    def job(log, progress, step, cancelled):
        items = cfg["items"]
        if items is None:
            step("Lecture des dates de prise de vue…")
            items = photos.scan(cfg["sources"], cfg["dest"], progress, cancelled)
            progress(0)
        step("Rangement des photos…")
        log(f"{len(items)} fichiers vers {cfg['dest']}")
        photos.apply(photos.plan(items, **cfg["options"]), cfg["dest"], cfg["mode"],
                     log, progress, cancelled, cfg["sources"], step)

    page.run_task(job, "Rangement des photos…")


def run_sort(page, root, android=False):
    """Ouvre la fenêtre de rangement puis lance le rangement dans la page."""
    dlg = PhotoSortDialog(page, root, android)
    ok = dlg.exec()
    dlg.stop_scan()  # aussi quand l'appli est fermée pendant que la fenêtre est ouverte
    dlg.deleteLater()  # libère la fenêtre tout de suite (évite un plantage de PySide à la sortie)
    if ok and dlg.result_config:
        start_sort(page, dlg.result_config)
