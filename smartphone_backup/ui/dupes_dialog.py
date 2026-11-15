"""Fenêtre « Doublons » : recherche des photos et vidéos en double, puis nettoyage."""
import html
import os
import shutil
import subprocess

from .qt import QFile, QImage, QImageReader, QPixmap, QSize, Qt, Signal
from .qt import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                 QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import dupes, photos
from ..core.iphone import unique
from .common import GREEN, ORANGE, RED, Thread, join, card, fit_to_screen, label, progress_bar, settings

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


def in_folder(path, folder):
    return bool(folder) and photos._inside(os.path.abspath(path), os.path.abspath(folder))


def to_drop(kind, paths, ref=""):
    """Exemplaires cochés par défaut : identiques → tous sauf le meilleur ; ressemblantes → seulement
    les versions en plus basse résolution que le meilleur (ex. copie WhatsApp réduite), jamais deux
    photos de même taille (rafale, photos presque pareilles : à vous de choisir).
    ref : dossier de référence, jamais coché ; s'il contient un exemplaire, c'est lui qui est gardé."""
    in_ref = [p for p in paths if in_folder(p, ref)]
    keep = dupes.keeper(in_ref or paths)
    candidates = [p for p in paths if p != keep and p not in in_ref]
    if kind == "identiques":
        return keep, set(candidates)
    best = pixels(keep)
    # avec une référence, sa version suffit si l'autre n'est pas meilleure ; sinon il faut nettement moins bien
    limit = best if in_ref else best * 0.9
    return keep, {p for p in candidates if (pixels(p) <= limit if in_ref else pixels(p) < limit)}


class DupeScanner(Thread):
    progress = Signal(int)
    step = Signal(str)
    done = Signal(object)

    def __init__(self, sources, similar, method="checksum", exclude=(), ref=""):
        super().__init__()
        self.sources, self.similar, self.method = sources, similar, method
        self.exclude, self.ref = list(exclude), ref
        self.stop = False

    def run(self):
        cancel = lambda: self.stop  # noqa: E731
        span = (lambda a, b: lambda v: self.progress.emit(int(a + (b - a) * v / 100)))
        self.step.emit("Recherche des photos et vidéos…")
        ref_apart = self.ref and not any(in_folder(self.ref, s) for s in self.sources)
        roots = self.sources + ([self.ref] if ref_apart else [])
        exclude = [e for e in self.exclude if not in_folder(self.ref, e)]  # la référence n'est jamais exclue
        items = photos.scan(roots, exclude, span(0, 35), cancel, find_dupes=False)
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
        if ref_apart:  # référence à part : seuls comptent ses doublons dans les dossiers analysés
            groups = [(k, g) for k, g in groups if not all(in_folder(p, self.ref) for p in g)]
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


def remove_file(path, method, base):
    if method == "trash":
        if not to_trash(path):
            raise OSError("corbeille indisponible")
    elif method == "delete":
        os.remove(path)
    else:
        rel = os.path.relpath(path, base)
        if rel.startswith(".."):  # fichier hors des dossiers analysés (dossier de référence à part)
            rel = os.path.join("Autres", os.path.basename(path))
        dest = unique(os.path.join(base, photos.DUPES_DIR, rel))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(path, dest)


class Remover(Thread):
    """Retire les fichiers en arrière-plan (la fenêtre reste réactive, barre de progression)."""
    progress = Signal(int, int)      # fichiers traités, total
    done = Signal(object, object)    # chemins retirés, échecs

    def __init__(self, paths, method, base):
        super().__init__()
        self.paths, self.method, self.base = paths, method, base
        self.stop = False

    def run(self):
        removed, failed = [], []
        for i, path in enumerate(self.paths):
            if self.stop:
                break
            try:
                remove_file(path, self.method, self.base)
                removed.append(path)
            except OSError as e:
                failed.append(f"{path} : {e}")
            self.progress.emit(i + 1, len(self.paths))
        self.done.emit(removed, failed)


class DuplicatesDialog(QDialog):
    def __init__(self, parent, sources, android=False, exclude=(), root=""):
        super().__init__(parent)
        self.exclude = list(exclude)
        self.setWindowTitle("Doublons")
        self.setObjectName("root")
        fit_to_screen(self, 980, 740)
        self.sources = [s for s in sources if os.path.isdir(s)]
        self.base = os.path.commonpath(self.sources) if self.sources else ""
        self.scanner = None
        self.remover = None
        self.stopping = []  # recherches abandonnées, gardées jusqu'à leur arrêt effectif
        self.changed = False  # des fichiers ont été retirés
        self.s = settings()
        from .photo_sort_dialog import dest_key
        self.ref_key = dest_key(root or self.base or "-", "ref")
        self.ref = self.s.value(self.ref_key, "") or ""
        if self.ref and not os.path.isdir(self.ref):
            self.ref = ""

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
        self.similar.toggled.connect(self.options_changed)
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
        self.compare.currentIndexChanged.connect(self.options_changed)
        mrow.addWidget(self.compare)
        mrow.addStretch(1)
        self.b_go = QPushButton()
        self.b_go.setObjectName("primary")
        self.b_go.clicked.connect(self.go)
        mrow.addWidget(self.b_go)
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Dossier de référence :"))
        self.ref_label = label("", "hint")
        self.ref_label.setWordWrap(True)
        self.ref_label.setToolTip("Ses fichiers ne sont jamais cochés par la sélection automatique : en cas de "
                                  "doublon, c'est son exemplaire qui est gardé et les autres qui sont retirés.\n"
                                  "Il peut être dans les dossiers analysés ou ailleurs (ex. photothèque déjà "
                                  "rangée).")
        rrow.addWidget(self.ref_label, 1)
        self.b_ref = QPushButton("Choisir…")
        self.b_ref.clicked.connect(self.pick_ref)
        self.b_noref = QPushButton("Aucun")
        self.b_noref.clicked.connect(lambda: self.set_ref(""))
        rrow.addWidget(self.b_ref)
        rrow.addWidget(self.b_noref)
        root.addLayout(rrow)
        self.show_ref()
        if self.exclude:
            ex = label("Sous-dossiers exclus : " + ", ".join(os.path.basename(e) for e in self.exclude), "hint")
            ex.setToolTip("\n".join(self.exclude))
            ex.setWordWrap(True)
            root.addWidget(ex)
        root.addLayout(mrow)

        self.status = label("", "hint")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.bar = progress_bar()
        root.addWidget(self.bar)

        split = QSplitter()
        split.setHandleWidth(12)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fichier (coché = à retirer)", "Taille", "Date", "Dossier"])
        self.tree.setColumnWidth(0, 280)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 150)
        self.tree.header().setStretchLastSection(True)  # « Dossier » occupe le reste de la largeur
        self.tree.itemChanged.connect(self.item_changed)
        self.tree.currentItemChanged.connect(self.show_preview)
        split.addWidget(self.tree)
        side, sl = card()  # panneau d'aperçu encadré, visible même vide
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
        split.setStretchFactor(1, 0)
        split.setSizes([10000, 260])
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
        self.method.addItem("Supprimer définitivement", "delete")
        self.method.setToolTip("Corbeille et « _Doublons » : récupérable.\n"
                               "Supprimer définitivement : place libérée tout de suite, sans retour possible.")
        self.method.setCurrentIndex(max(0, self.method.findData(self.s.value("dupes/method", "trash"))))
        btns.addWidget(self.method)
        b_close = self.b_close = QPushButton("Fermer")
        b_close.clicked.connect(self.close_clicked)
        self.b_remove = QPushButton("Retirer la sélection")
        self.b_remove.setObjectName("danger")
        self.b_remove.clicked.connect(self.remove)
        btns.addWidget(self.b_remove)
        btns.addWidget(b_close)
        root.addLayout(btns)

        self.groups = []
        self.reset("Choisissez les options, puis cliquez sur « Démarrer la recherche ».")

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

    def close_clicked(self):
        if self.remover:  # arrêt après le fichier en cours ; la liste est mise à jour
            self.remover.stop = True
        else:
            self.accept()

    def done(self, r):
        if self.remover:  # fenêtre fermée pendant le retrait : on termine le fichier en cours
            self.remover.stop = True
            join(self.remover)
            self.remover = None
        self.stop_scan()
        for sc in list(self.stopping):
            join(sc, 5000)  # lecture interrompue au bloc suivant : quasi immédiat
        self.stopping.clear()
        super().done(r)

    def show_ref(self):
        self.ref_label.setText(self.ref or "aucun : le meilleur exemplaire de chaque groupe est gardé")
        self.b_noref.setEnabled(bool(self.ref))

    def pick_ref(self):
        from .folder_picker import pick_folder
        path = pick_folder(self, "Dossier de référence", self.ref or self.base)
        if path:
            self.set_ref(os.path.abspath(path))

    def set_ref(self, path):
        if path == self.ref:
            return
        self.ref = path
        self.s.setValue(self.ref_key, path)
        self.show_ref()
        if self.groups and not self.scanner:
            # dans les dossiers analysés : la liste reste valable, seule la sélection change
            if not path or any(in_folder(path, s) for s in self.sources):
                self.fill()
                return
        self.options_changed(force=True)

    def go(self):
        if self.scanner:
            self.reset("Recherche arrêtée. Cliquez sur « Démarrer la recherche » pour recommencer.")
        else:
            self.start_scan()

    def options_changed(self, *_, force=False):
        self.s.setValue("dupes/similar", "true" if self.similar.isChecked() else "false")
        self.s.setValue("dupes/compare", self.compare.currentData())
        if self.scanner or self.groups or force:
            self.reset("Options modifiées : cliquez sur « Démarrer la recherche » pour relancer.")

    def reset(self, message):
        """Arrête une éventuelle recherche et vide les résultats."""
        self.stop_scan()
        self.tree.clear()
        self.groups = []
        self.clear_preview()
        self.summary.clear()
        self.bar.hide()
        for b in (self.b_auto, self.b_none, self.b_remove):
            b.setEnabled(False)
        self.b_go.setText("Démarrer la recherche")
        self.b_go.setEnabled(bool(self.sources))
        self.status.setText(message if self.sources else "Aucun dossier à analyser.")

    def start_scan(self):
        self.reset("")
        if not self.sources:
            return
        self.b_go.setText("Arrêter")
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText("Recherche des photos et vidéos…")
        self.scanner = DupeScanner(self.sources, self.similar.isChecked(), self.compare.currentData(),
                                   self.exclude, self.ref)
        self.scanner.progress.connect(self.bar.setValue)
        self.scanner.step.connect(self.status.setText)
        self.scanner.done.connect(self.scanned)
        self.scanner.start()

    def scanned(self, groups):
        self.scanner = None
        self.bar.hide()
        self.b_go.setText("Relancer la recherche")
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
            keep, drop = to_drop(kind, [it.path for it in items], self.ref)
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
                                     f"{it.date:%d/%m/%Y %H:%M}", self.folder_name(it.path)])
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

    def folder_name(self, path):
        """Dossier relatif au dossier analysé (plus court que le chemin complet)."""
        if in_folder(path, self.ref):
            rel = os.path.relpath(os.path.dirname(path), self.ref)
            return "★ Référence" + ("" if rel == "." else " / " + rel)
        rel = os.path.relpath(os.path.dirname(path), self.base) if self.base else os.path.dirname(path)
        return "(dossier analysé)" if rel == "." else rel

    def children(self, g):
        return [g.child(i) for i in range(g.childCount())]

    def select(self, auto):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            kids = self.children(g)
            drop = to_drop(g.data(0, Qt.UserRole + 1), [c.data(0, Qt.UserRole) for c in kids], self.ref)[1] \
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

    def clear_preview(self):
        self.preview.clear()
        self.preview.setText("Aperçu\n\nCliquez sur un fichier\npour le voir ici")
        self.info.clear()

    def show_preview(self, cur, _prev=None):
        path = cur.data(0, Qt.UserRole) if cur else None
        if not path:
            self.clear_preview()
            return
        r = QImageReader(path)
        r.setAutoTransform(True)
        size = r.size()
        if size.isValid():
            size.scale(QSize(220, 220), Qt.KeepAspectRatio)
            r.setScaledSize(size)
        img = r.read()
        if img.isNull():
            self.preview.setText("Aperçu indisponible\n(vidéo ou format non lu)")
        else:
            self.preview.setPixmap(QPixmap.fromImage(img))
        dims = QImageReader(path).size()
        self.info.setText((f"{dims.width()} × {dims.height()} px<br>" if dims.isValid() else "")
                          + f"{cur.text(1)} · {cur.text(2)}<br>"
                          # coupure possible après chaque séparateur : chemin lisible sur plusieurs lignes
                          + html.escape(path).replace(os.sep, os.sep + "\u200b"))

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
        if method == "delete":
            total = human(sum(c.data(1, Qt.UserRole) for c in sel))
            similar = sum(c.parent().data(0, Qt.UserRole + 1) == "ressemblantes" for c in sel)
            text = (f"Supprimer définitivement {len(sel)} fichier(s) ({total}) ?\n\n"
                    "Ils ne passeront pas par la corbeille : impossible de les récupérer ensuite.")
            if similar:
                text += (f"\n\nAttention : {similar} d'entre eux sont des photos « ressemblantes », pas "
                         "identiques. Vérifiez-les dans l'aperçu avant de continuer.")
            box = QMessageBox(QMessageBox.Warning, "Supprimer définitivement", text,
                              QMessageBox.Yes | QMessageBox.Cancel, self)
            box.button(QMessageBox.Yes).setText("Supprimer définitivement")
            box.button(QMessageBox.Cancel).setText("Annuler")
            box.setDefaultButton(QMessageBox.Cancel)
            if box.exec() != QMessageBox.Yes:
                return
        else:
            where = "dans la corbeille" if method == "trash" else \
                f"dans « {os.path.join(self.base, photos.DUPES_DIR)} »"
            if QMessageBox.question(self, "Doublons", f"Placer {len(sel)} fichier(s) {where} ?") \
                    != QMessageBox.Yes:
                return
        self.removing = method
        verb = {"trash": "Mise à la corbeille", "move": "Déplacement", "delete": "Suppression"}[method]
        self.remove_verb = verb
        self.lock(True)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText(f"{verb} : 0 / {len(sel)} fichiers…")
        self.remover = Remover([c.data(0, Qt.UserRole) for c in sel], method, self.base)
        self.remover.progress.connect(self.remove_progress)
        self.remover.done.connect(self.removed)
        self.remover.start()

    def lock(self, busy):
        """Pendant le retrait des fichiers : rien d'autre ne peut être lancé."""
        for w in (self.tree, self.similar, self.compare, self.b_go, self.b_auto, self.b_none,
                  self.method, self.b_remove, self.b_ref, self.b_noref):
            w.setEnabled(not busy)
        self.b_close.setText("Arrêter" if busy else "Fermer")

    def remove_progress(self, n, total):
        self.bar.setValue(int(n * 100 / max(total, 1)))
        self.status.setText(f"{self.remove_verb} : {n} / {total} fichiers…")

    def removed(self, removed, failed):
        method, self.remover = self.removing, None
        self.bar.hide()
        self.lock(False)
        gone = set(removed)
        self.tree.blockSignals(True)
        for i in reversed(range(self.tree.topLevelItemCount())):
            g = self.tree.topLevelItem(i)
            for c in self.children(g):
                if c.data(0, Qt.UserRole) in gone:
                    g.removeChild(c)
            if g.childCount() < 2:  # groupe réduit à un seul fichier : plus de doublon
                self.tree.takeTopLevelItem(i)
        self.tree.blockSignals(False)
        self.changed = self.changed or bool(removed)
        self.update_summary()
        ok = len(removed)
        msg = f"{ok} fichier(s) " + ("supprimé(s) définitivement." if method == "delete" else "retiré(s).")
        if failed:
            msg += f"\n\n{len(failed)} échec(s) :\n" + "\n".join(failed[:10])
            if method == "trash":
                msg += f"\n\nEssayez « Déplacer dans {photos.DUPES_DIR} »."
        n = self.tree.topLevelItemCount()
        self.status.setText("Plus aucun doublon ✓" if not n else f"{n} groupe(s) de doublons restant(s).")
        QMessageBox.information(self, "Doublons", msg)
