"""Fenêtre « Ranger les photos » : choix des dossiers, du classement et aperçu."""
import os

from .qt import Qt, QThread, Signal
from .qt import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                 QLabel, QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                 QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import photos
from .common import ORANGE, card, fit_to_screen, folder_row, label, settings


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


class PhotoSortDialog(QDialog):
    def __init__(self, parent, backup_root):
        super().__init__(parent)
        self.setWindowTitle("Ranger les photos")
        self.setObjectName("root")
        fit_to_screen(self, 860, 780)
        self.s = settings()
        self.items = None       # résultat de l'analyse (None = en cours)
        self.scanner = None
        self.scan_key = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 16)
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(24, 22, 24, 8)
        root.setSpacing(14)
        sa = QScrollArea()
        sa.setObjectName("pageScroll")
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(body)
        outer.addWidget(sa, 1)

        root.addWidget(label("Ranger les photos", "title"))
        root.addWidget(label("Classe les photos et vidéos sauvegardées selon leur date de prise de vue.",
                             "subtitle"))

        # --- sources
        c, l = card()
        l.addWidget(label("Photos à ranger", "section"))
        self.src_box = QVBoxLayout()
        self.src_checks = []
        for path, name, default in find_sources(backup_root):
            self.add_source(path, name, default)
        if not self.src_checks:
            self.no_src = label("Aucune photo sauvegardée dans « %s ». Lancez d'abord une sauvegarde, "
                                "ou ajoutez un dossier." % backup_root, "hint")
            self.no_src.setWordWrap(True)
            self.src_box.addWidget(self.no_src)
        l.addLayout(self.src_box)
        b_add = QPushButton("Ajouter un dossier…")
        b_add.clicked.connect(self.pick_source)
        row = QHBoxLayout()
        row.addWidget(b_add)
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
            ex = label(example, "hint")
            grid.addWidget(ex, i, 1)
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
                ("videos_apart", "Séparer photos et vidéos", "Photos / 2024 / …  et  Vidéos / 2024 / …"),
                ("by_origin", "Séparer par origine",
                 "Appareil photo / Captures d'écran / WhatsApp / Autres images, puis la date"),
                ("rename", "Renommer avec la date", "IMG_1234.jpg → 2024-03-15_14-32-05.jpg")):
            cb = QCheckBox(text)
            cb.setChecked(self.s.value("sort/" + key, "false") == "true")
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
        self.dest = folder_row(self, l, "Dossier", "sort/out", os.path.join(backup_root, "Photos rangées"))
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
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        l.addWidget(self.bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Dossier", "Fichiers"])
        self.tree.setMinimumHeight(220)
        self.tree.setColumnWidth(0, 420)
        l.addWidget(self.tree)
        root.addWidget(c, 1)

        # --- boutons
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

        self.structure.buttonClicked.connect(lambda *_: self.refresh())
        for w in (self.gap, self.min_count):
            w.valueChanged.connect(lambda *_: self.refresh())
        for cb in self.opt.values():
            cb.toggled.connect(lambda *_: self.refresh())
        self.mode.currentIndexChanged.connect(lambda *_: self.refresh())
        self.dest.editingFinished.connect(self.rescan)
        self.rescan()

    # ------------------------------------------------------------- sources
    def add_source(self, path, name, checked):
        if getattr(self, "no_src", None):
            self.no_src.hide()
        cb = QCheckBox(name)
        cb.setToolTip(path)
        cb.setChecked(checked)
        cb.toggled.connect(lambda *_: self.rescan())
        self.src_box.addWidget(cb)
        self.src_checks.append((cb, path))

    def pick_source(self):
        from .folder_picker import pick_folder
        start = self.src_checks[0][1] if self.src_checks else os.path.expanduser("~")
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

    def rescan(self):
        key = (tuple(self.sources()), self.dest.text())
        if key == self.scan_key:
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
        self.mode_hint.setText({
            "link": "Les photos apparaissent aussi dans le dossier rangé sans occuper de place en plus ; "
                    "supprimer l'une des deux ne supprime pas l'autre. Si le disque ne le permet pas "
                    "(clé USB FAT/exFAT, NTFS…), elles sont copiées.",
            "copy": "Les photos sont dupliquées : prévoyez autant de place libre que leur taille.",
            "move": f'<span style="color:{ORANGE}">Les photos quittent le dossier de sauvegarde : la '
                    "prochaine synchronisation les recopiera depuis le téléphone.</span>",
        }[mode])
        self.b_go.setEnabled(bool(self.sources()) and self.items != [])
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
        def n(v):  # 12 345
            return f"{v:,}".replace(",", "\u202f")
        n_dirs = len({os.path.dirname(rel) for _, rel in steps})
        self.summary.setText(
            f"<b>{n(len(self.items) - n_vid)} photos et {n(n_vid)} vidéos</b>, de {years[0]} à {years[-1]}, "
            f"rangées dans {n(n_dirs)} dossiers. Date de prise de vue trouvée pour {sure} % des fichiers"
            + (" ; les autres sont classés d'après la date du fichier." if sure < 100 else "."))

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
    def go(self):
        dest = self.dest.text().strip()
        srcs = self.sources()
        if not dest:
            return QMessageBox.information(self, "Ranger les photos", "Choisissez un dossier de destination.")
        real = os.path.realpath(dest)
        if any(os.path.realpath(s) == real for s in srcs):
            return QMessageBox.information(self, "Ranger les photos",
                                           "La destination doit être différente des dossiers de photos.")
        mode = self.mode.currentData()
        if mode == "move" and QMessageBox.question(
                self, "Ranger les photos",
                "Déplacer les photos hors de la sauvegarde ?\n\nLa prochaine synchronisation les "
                "recopiera depuis le téléphone, sauf si elles en ont été supprimées.") != QMessageBox.Yes:
            return
        o = self.options()
        for k, v in o.items():
            self.s.setValue("sort/" + {"gap_hours": "gap", "min_count": "min"}.get(k, k),
                            ("true" if v else "false") if isinstance(v, bool) else v)
        self.s.setValue("sort/mode", mode)
        fresh = self.scan_key == (tuple(srcs), self.dest.text())
        self.result_config = dict(sources=srcs, dest=dest, mode=mode, options=o,
                                  items=self.items if fresh else None)
        self.accept()
