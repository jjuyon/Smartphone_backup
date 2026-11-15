"""Fenêtre « Doublons » : recherche des photos et vidéos en double, puis nettoyage."""
import os
import shutil
import subprocess

from .qt import QFile, QImage, QImageReader, QPixmap, QSize, Qt, QThread, Signal
from .qt import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                 QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import dupes, photos
from ..core.iphone import unique
from .common import GREEN, ORANGE, RED, fit_to_screen, label, progress_bar, settings

KEEP_COLOR, DROP_COLOR = GREEN, RED


def human(n):
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return (f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}").replace(".", ",")
        n /= 1024


def image_hash(path):
    """Empreinte visuelle (dHash 64 bits) : identique pour une photo redimensionnée ou recompressée."""
    r = QImageReader(path)
    r.setAutoTransform(True)       # tient compte de l'orientation EXIF
    r.setScaledSize(QSize(128, 128))  # carré : la rotation ne change pas la taille
    img = r.read()
    if img.isNull():
        return None
    img = img.scaled(9, 8, Qt.IgnoreAspectRatio, Qt.SmoothTransformation) \
        .convertToFormat(QImage.Format_Grayscale8)
    h = 0
    for y in range(8):
        row = [img.pixel(x, y) & 0xFF for x in range(9)]
        for x in range(8):
            h = (h << 1) | (row[x] > row[x + 1])
    return h


def pixels(path):
    sz = QImageReader(path).size()  # lit seulement l'en-tête
    return sz.width() * sz.height() if sz.isValid() else 0


def to_drop(kind, paths):
    """Exemplaires cochés par défaut : identiques → tous sauf le meilleur ; ressemblantes → seulement
    les versions en plus basse résolution que le meilleur (ex. copie WhatsApp réduite), jamais deux
    photos de même taille (rafale, photos presque pareilles : à vous de choisir)."""
    keep = dupes.keeper(paths)
    if kind == "identiques":
        return keep, {p for p in paths if p != keep}
    best = pixels(keep)
    return keep, {p for p in paths if p != keep and pixels(p) < best * 0.9}


class DupeScanner(QThread):
    progress = Signal(int)
    step = Signal(str)
    done = Signal(object)

    def __init__(self, sources, similar, method="checksum"):
        super().__init__()
        self.sources, self.similar, self.method = sources, similar, method
        self.stop = False

    def run(self):
        cancel = lambda: self.stop  # noqa: E731
        span = (lambda a, b: lambda v: self.progress.emit(int(a + (b - a) * v / 100)))
        self.step.emit("Recherche des photos et vidéos…")
        items = photos.scan(self.sources, None, span(0, 35), cancel, find_dupes=False)
        by_path = {it.path: it for it in items}
        exact = dupes.exact_groups([(it.path, it.size) for it in items],
                                   span(35, 60 if self.similar else 100), cancel, self.method,
                                   self.step.emit)
        groups = [("identiques", g) for g in exact]
        if self.similar and not self.stop:
            self.step.emit("Comparaison visuelle des photos (plus long)…")
            rep_of, members = {}, {}
            for g in exact:  # un seul représentant par groupe identique
                for p in g:
                    rep_of[p] = g[0]
                members[g[0]] = g
            reps = [it.path for it in items if not it.video and rep_of.get(it.path, it.path) == it.path]
            sim = dupes.similar_groups(reps, image_hash, span(60, 100), cancel)
            merged = set()
            for g in sim:
                full = [p for r in g for p in members.get(r, [r])]
                merged.update(r for r in g if r in members)
                groups.append(("ressemblantes", full))
            groups = [(k, g) for k, g in groups if not (k == "identiques" and g[0] in merged)]
        if not self.stop:
            self.done.emit([(k, [by_path[p] for p in g]) for k, g in groups])


def to_trash(path):
    """Corbeille du bureau (récupérable). Renvoie True si réussi."""
    try:
        res = QFile.moveToTrash(path)
        if (res[0] if isinstance(res, tuple) else res):
            return True
    except (AttributeError, TypeError):
        pass
    if shutil.which("gio"):
        return subprocess.run(["gio", "trash", path], capture_output=True).returncode == 0
    return False


class DuplicatesDialog(QDialog):
    def __init__(self, parent, sources, android=False):
        super().__init__(parent)
        self.setWindowTitle("Doublons")
        self.setObjectName("root")
        fit_to_screen(self, 980, 740)
        self.sources = [s for s in sources if os.path.isdir(s)]
        self.base = os.path.commonpath(self.sources) if self.sources else ""
        self.scanner = None
        self.stopping = []  # recherches abandonnées, gardées jusqu'à leur arrêt effectif
        self.changed = False  # des fichiers ont été retirés
        self.s = settings()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(12)
        root.addWidget(label("Doublons", "title"))
        where = ", ".join(os.path.basename(s.rstrip(os.sep)) or s for s in self.sources)
        sub = label(f"Photos et vidéos présentes plusieurs fois dans : {where}", "subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)
        if android:
            warn = QLabel(f'<span style="color:{ORANGE}">Ces photos viennent de la sauvegarde du téléphone : '
                          "un doublon retiré ici sera recopié à la prochaine synchronisation s'il est encore "
                          "sur le téléphone. Pour un dossier rangé sans doublons, cochez plutôt « Ne pas "
                          "ranger les doublons » dans le rangement.</span>")
            warn.setWordWrap(True)
            root.addWidget(warn)

        self.similar = QCheckBox("Chercher aussi les photos ressemblantes : même photo redimensionnée ou "
                                 "recompressée (ex. renvoyée par WhatsApp). Plus lent, à vérifier.")
        self.similar.setChecked(self.s.value("dupes/similar", "false") == "true")
        self.similar.toggled.connect(self.start_scan)
        root.addWidget(self.similar)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Fichiers identiques repérés par :"))
        self.compare = QComboBox()
        for key, text in dupes.METHODS.items():
            self.compare.addItem(text, key)
        self.compare.setCurrentIndex(max(0, self.compare.findData(self.s.value("dupes/compare", "checksum"))))
        self.compare.setToolTip("Somme de contrôle : chaque fichier de même taille est lu en entier ; deux "
                                "fichiers ne sont doublons que si leur contenu est exactement le même.\n"
                                "Rapide : seuls le début et la fin sont lus (très fiable pour photos et "
                                "vidéos, mais pas garanti).")
        self.compare.currentIndexChanged.connect(self.start_scan)
        mrow.addWidget(self.compare)
        mrow.addStretch(1)
        root.addLayout(mrow)

        self.status = label("", "hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.bar = progress_bar()
        root.addWidget(self.bar)

        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fichier (coché = à retirer)", "Taille", "Date", "Dossier"])
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 80)
        self.tree.setColumnWidth(2, 130)
        self.tree.itemChanged.connect(self.item_changed)
        self.tree.currentItemChanged.connect(self.show_preview)
        split.addWidget(self.tree)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(220, 220)
        sl.addWidget(self.preview)
        self.info = label("", "hint")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        sl.addWidget(self.info)
        sl.addStretch(1)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        split.setSizes([700, 240])
        root.addWidget(split, 1)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        btns = QHBoxLayout()
        self.b_auto = QPushButton("Sélection automatique")
        self.b_auto.setToolTip("Garde le meilleur exemplaire de chaque groupe : le plus grand, celui de "
                               "l'appareil photo plutôt que WhatsApp/Téléchargements, le plus ancien.")
        self.b_auto.clicked.connect(lambda: self.select(auto=True))
        self.b_none = QPushButton("Tout garder")
        self.b_none.clicked.connect(lambda: self.select(auto=False))
        btns.addWidget(self.b_auto)
        btns.addWidget(self.b_none)
        btns.addStretch(1)
        self.method = QComboBox()
        self.method.addItem("Mettre à la corbeille", "trash")
        self.method.addItem(f"Déplacer dans « {photos.DUPES_DIR} »", "move")
        self.method.setCurrentIndex(max(0, self.method.findData(self.s.value("dupes/method", "trash"))))
        btns.addWidget(self.method)
        b_close = QPushButton("Fermer")
        b_close.clicked.connect(self.accept)
        self.b_remove = QPushButton("Retirer la sélection")
        self.b_remove.setObjectName("danger")
        self.b_remove.clicked.connect(self.remove)
        btns.addWidget(self.b_remove)
        btns.addWidget(b_close)
        root.addLayout(btns)

        self.groups = []
        self.start_scan()

    # ------------------------------------------------------------- recherche
    def stop_scan(self):
        """Arrête la recherche en cours sans bloquer la fenêtre : ses résultats seront ignorés."""
        sc, self.scanner = self.scanner, None
        if sc and sc.isRunning():
            sc.stop = True
            for sig in (sc.progress, sc.step, sc.done):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass
            self.stopping.append(sc)
            sc.finished.connect(lambda sc=sc: sc in self.stopping and self.stopping.remove(sc))

    def done(self, r):
        self.stop_scan()
        for sc in list(self.stopping):
            sc.wait()  # lecture interrompue au bloc suivant : quasi immédiat
        self.stopping.clear()
        super().done(r)

    def start_scan(self):
        self.s.setValue("dupes/similar", "true" if self.similar.isChecked() else "false")
        self.s.setValue("dupes/compare", self.compare.currentData())
        self.stop_scan()
        self.tree.clear()
        self.groups = []
        self.preview.clear()
        self.info.clear()
        self.summary.clear()
        for b in (self.b_auto, self.b_none, self.b_remove):
            b.setEnabled(False)
        if not self.sources:
            self.status.setText("Aucun dossier à analyser.")
            self.bar.hide()
            return
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText("Recherche des photos et vidéos…")
        self.scanner = DupeScanner(self.sources, self.similar.isChecked(), self.compare.currentData())
        self.scanner.progress.connect(self.bar.setValue)
        self.scanner.step.connect(self.status.setText)
        self.scanner.done.connect(self.scanned)
        self.scanner.start()

    def scanned(self, groups):
        self.scanner = None
        self.bar.hide()
        self.groups = sorted(groups, key=lambda kg: -sum(it.size for it in kg[1][1:]))
        if not self.groups:
            self.status.setText(status := "Aucun doublon trouvé ✓")
            self.summary.setText(f'<span style="color:{GREEN}">{status}</span>')
            return
        n_sim = sum(k == "ressemblantes" for k, _ in self.groups)
        self.status.setText(f"{len(self.groups)} groupes de doublons"
                            + (f", dont {n_sim} de photos ressemblantes (vérifiez l'aperçu)" if n_sim else "")
                            + ". Cliquez sur un fichier pour le voir ; cochez ceux à retirer.")
        self.fill()
        for b in (self.b_auto, self.b_none, self.b_remove):
            b.setEnabled(True)

    def fill(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        for kind, items in self.groups:
            keep, drop = to_drop(kind, [it.path for it in items])
            title = f"{os.path.basename(keep)} — {len(items)} exemplaires {kind}"
            g = QTreeWidgetItem([title + (" (à vérifier)" if kind == "ressemblantes" else "")])
            g.setData(0, Qt.UserRole + 1, kind)
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            self.tree.addTopLevelItem(g)
            g.setFirstColumnSpanned(True)  # après l'ajout dans l'arbre, sinon sans effet
            for it in sorted(items, key=lambda i: i.path != keep):
                c = QTreeWidgetItem([os.path.basename(it.path), human(it.size),
                                     f"{it.date:%d/%m/%Y %H:%M}", os.path.dirname(it.path)])
                c.setData(0, Qt.UserRole, it.path)
                c.setData(1, Qt.UserRole, it.size)
                c.setToolTip(3, it.path)
                c.setFlags(c.flags() | Qt.ItemIsUserCheckable)
                c.setCheckState(0, Qt.Checked if it.path in drop else Qt.Unchecked)
                g.addChild(c)
                self.paint(c)
            g.setExpanded(len(self.groups) <= 300)
        self.tree.blockSignals(False)
        self.update_summary()

    def children(self, g):
        return [g.child(i) for i in range(g.childCount())]

    def select(self, auto):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            kids = self.children(g)
            drop = to_drop(g.data(0, Qt.UserRole + 1), [c.data(0, Qt.UserRole) for c in kids])[1] \
                if auto else set()
            for c in kids:
                c.setCheckState(0, Qt.Checked if c.data(0, Qt.UserRole) in drop else Qt.Unchecked)
                self.paint(c)
        self.tree.blockSignals(False)
        self.update_summary()

    def paint(self, c):
        from .qt import QBrush, QColor
        drop = c.checkState(0) == Qt.Checked
        c.setForeground(0, QBrush(QColor(DROP_COLOR if drop else KEEP_COLOR)))

    def item_changed(self, c, col):
        if col == 0 and c.parent():
            self.tree.blockSignals(True)
            self.paint(c)
            self.tree.blockSignals(False)
            self.update_summary()

    def checked(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            out += [c for c in self.children(self.tree.topLevelItem(i)) if c.checkState(0) == Qt.Checked]
        return out

    def update_summary(self):
        sel = self.checked()
        total = sum(c.data(1, Qt.UserRole) for c in sel)
        full = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())
                if all(c.checkState(0) == Qt.Checked for c in self.children(self.tree.topLevelItem(i)))]
        text = f"<b>{len(sel)} fichiers à retirer</b> · {human(total)} libérés"
        if full:
            text += f' · <span style="color:{ORANGE}">{len(full)} groupe(s) sans exemplaire gardé</span>'
        self.summary.setText(text)
        self.b_remove.setEnabled(bool(sel))
        self.b_remove.setText(f"Retirer {len(sel)} fichier(s)" if sel else "Retirer la sélection")

    def show_preview(self, cur, _prev=None):
        path = cur.data(0, Qt.UserRole) if cur else None
        if not path:
            self.preview.clear()
            self.info.clear()
            return
        r = QImageReader(path)
        r.setAutoTransform(True)
        size = r.size()
        if size.isValid():
            size.scale(QSize(240, 240), Qt.KeepAspectRatio)
            r.setScaledSize(size)
        img = r.read()
        if img.isNull():
            self.preview.setText("Aperçu indisponible\n(vidéo ou format non lu)")
        else:
            self.preview.setPixmap(QPixmap.fromImage(img))
        dims = QImageReader(path).size()
        self.info.setText((f"{dims.width()} × {dims.height()} px<br>" if dims.isValid() else "")
                          + f"{cur.text(1)} · {cur.text(2)}<br>{path}")

    # ------------------------------------------------------------- nettoyage
    def remove(self):
        sel = self.checked()
        full = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())
                if all(c.checkState(0) == Qt.Checked for c in self.children(self.tree.topLevelItem(i)))]
        if full:
            return QMessageBox.information(self, "Doublons", "Gardez au moins un exemplaire dans chaque groupe "
                                           f"({len(full)} groupe(s) entièrement cochés).")
        method = self.method.currentData()
        self.s.setValue("dupes/method", method)
        where = "dans la corbeille" if method == "trash" else \
            f"dans « {os.path.join(self.base, photos.DUPES_DIR)} »"
        if QMessageBox.question(self, "Doublons", f"Placer {len(sel)} fichier(s) {where} ?") != QMessageBox.Yes:
            return
        ok, failed = 0, []
        for c in sel:
            path = c.data(0, Qt.UserRole)
            try:
                if method == "trash":
                    if not to_trash(path):
                        raise OSError("corbeille indisponible")
                else:
                    dest = unique(os.path.join(self.base, photos.DUPES_DIR, os.path.relpath(path, self.base)))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(path, dest)
                ok += 1
                c.parent().removeChild(c)
            except OSError as e:
                failed.append(f"{path} : {e}")
        self.changed = self.changed or ok > 0
        # groupes réduits à un seul fichier : plus de doublon
        for i in reversed(range(self.tree.topLevelItemCount())):
            if self.tree.topLevelItem(i).childCount() < 2:
                self.tree.takeTopLevelItem(i)
        self.update_summary()
        msg = f"{ok} fichier(s) retiré(s)."
        if failed:
            msg += f"\n\n{len(failed)} échec(s) :\n" + "\n".join(failed[:10])
            if method == "trash":
                msg += f"\n\nEssayez « Déplacer dans {photos.DUPES_DIR} »."
        QMessageBox.information(self, "Doublons", msg)
        if not self.tree.topLevelItemCount():
            self.status.setText("Plus aucun doublon ✓")
