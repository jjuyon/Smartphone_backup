"""Sélecteur de dossier au thème sombre, avec emplacements, périphériques et montages (façon Dolphin).

- Emplacements : dossier personnel, Bureau, Documents…
- Périphériques : disques et partitions (lsblk) ; un clic sur un disque non monté le monte
  (udisksctl, comme Dolphin), clic droit pour démonter.
- Réseau : partages montés (SMB, NFS, sshfs…) et montages GVFS.
"""
import json
import os
import shutil
import subprocess

from .qt import QDir, QFileInfo, QProcess, QSize, QStandardPaths, QStorageInfo, Qt, QTimer
from .qt import (QDialog, QFileIconProvider, QFileSystemModel, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QSplitter, QTreeView, QVBoxLayout)

from .common import fit_to_screen, app_icon, label
from .qt import to_bytes

NETWORK_FS = {"cifs", "smb3", "smbfs", "nfs", "nfs4", "fuse.sshfs", "fuse.rclone", "davfs",
              "fuse.davfs2", "afpfs"}
HIDDEN_MOUNTS = ("/", "/boot", "/boot/efi", "/efi", "[SWAP]")
ROLE_PATH, ROLE_DEV = Qt.UserRole, Qt.UserRole + 1



# ---------------------------------------------------------------- périphériques
def block_devices():
    """[(nom affiché, /dev/…, point de montage ou None, amovible)] d'après lsblk."""
    if not shutil.which("lsblk"):
        return []
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", "NAME,PATH,LABEL,SIZE,FSTYPE,MOUNTPOINT,HOTPLUG,RM,TYPE"],
                             capture_output=True, text=True, timeout=5).stdout
        data = json.loads(out).get("blockdevices", [])
    except Exception:
        return []
    devs = []

    def walk(nodes, removable=False):
        for n in nodes:
            rem = removable or n.get("hotplug") in (True, "1") or n.get("rm") in (True, "1")
            fs, mp = n.get("fstype"), n.get("mountpoint")
            size = int(n.get("size") or 0)
            if fs and fs not in ("swap", "crypto_LUKS", "LVM2_member", "linux_raid_member") \
                    and mp not in HIDDEN_MOUNTS and not (mp or "").startswith(("/snap", "/var", "/usr")):
                # partition EFI non montée : ignorée, comme dans Dolphin
                if not (mp is None and fs == "vfat" and not rem and size < 1_100_000_000):
                    name = n.get("label") or f"Disque de {human(size)}"
                    devs.append((name, n.get("path") or "/dev/" + n["name"], mp, rem))
            walk(n.get("children") or [], rem)

    walk(data)
    return devs


def network_mounts(known):
    res = []
    for v in QStorageInfo.mountedVolumes():
        root = v.rootPath()
        fs = to_bytes(v.fileSystemType()).decode(errors="replace")
        if root in known:
            continue
        if fs in NETWORK_FS or (fs.startswith("fuse.") and root.startswith(("/media", "/run/media", "/mnt"))):
            res.append((os.path.basename(root.rstrip("/")) or root, root))
    gvfs = f"/run/user/{os.getuid()}/gvfs"
    try:
        for e in sorted(os.listdir(gvfs)):
            res.append((e.replace("server=", "").replace(",share=", "/"), os.path.join(gvfs, e)))
    except OSError:
        pass
    return res


def human(n):
    for unit in ("o", "Ko", "Mo", "Go", "To", "Po"):
        if n < 1000 or unit == "Po":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f}".replace(".0", "").replace(".", ",") + f" {unit}"
        n /= 1000


class DirIcons(QFileIconProvider):
    """Icône de dossier du thème (lisible sur fond sombre) pour tous les dossiers."""
    def __init__(self, widget):
        super().__init__()
        self.folder = app_icon("folder")

    def icon(self, arg):
        return self.folder if isinstance(arg, QFileInfo) else super().icon(arg)


# ---------------------------------------------------------------- fenêtre
class FolderPicker(QDialog):
    def __init__(self, parent, title, start):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("root")
        fit_to_screen(self, 900, 560)
        self.history, self.chosen = [], ""
        self.devices_sig = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # barre du haut : précédent, parent, chemin, nouveau dossier
        top = QHBoxLayout()
        self.b_prev = QPushButton(app_icon("go-back"), "")
        self.b_prev.setToolTip("Précédent")
        self.b_prev.clicked.connect(self.go_back)
        self.b_up = QPushButton(app_icon("go-up"), "")
        self.b_up.setToolTip("Dossier parent")
        self.b_up.clicked.connect(lambda: self.navigate(os.path.dirname(self.current.rstrip("/")) or "/"))
        self.path = QLineEdit()
        self.path.returnPressed.connect(lambda: self.navigate(os.path.expanduser(self.path.text())))
        b_new = QPushButton(app_icon("folder-new"), " Nouveau dossier")
        b_new.clicked.connect(self.new_folder)
        for w in (self.b_prev, self.b_up):
            top.addWidget(w)
        top.addWidget(self.path, 1)
        top.addWidget(b_new)
        root.addLayout(top)

        # panneau latéral + contenu
        split = QSplitter()
        split.setChildrenCollapsible(False)
        self.side = QListWidget()
        self.side.setObjectName("sidebar")
        self.side.setMinimumWidth(230)
        self.side.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.side.setTextElideMode(Qt.ElideMiddle)
        self.side.itemClicked.connect(self.side_clicked)
        self.side.setContextMenuPolicy(Qt.CustomContextMenu)
        self.side.customContextMenuRequested.connect(self.side_menu)
        split.addWidget(self.side)

        self.model = QFileSystemModel(self)
        self.model.setIconProvider(DirIcons(self))
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        self.model.setRootPath("/")
        self.view = QTreeView()
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setIconSize(QSize(22, 22))
        self.view.setItemsExpandable(False)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(0, Qt.AscendingOrder)
        for col in (1, 2):
            self.view.hideColumn(col)
        self.view.setColumnWidth(0, 420)
        self.view.doubleClicked.connect(lambda i: self.navigate(self.model.filePath(i)))
        self.view.selectionModel().selectionChanged.connect(self.update_choice)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([250, 630])
        root.addWidget(split, 1)

        # bas : dossier qui sera choisi
        bottom = QHBoxLayout()
        self.choice = label("", "hint")
        bottom.addWidget(self.choice, 1)
        b_cancel = QPushButton("Annuler")
        b_cancel.clicked.connect(self.reject)
        self.b_ok = QPushButton("Choisir ce dossier")
        self.b_ok.setObjectName("primary")
        self.b_ok.setDefault(True)
        self.b_ok.clicked.connect(self.accept_choice)
        bottom.addWidget(b_cancel)
        bottom.addWidget(self.b_ok)
        root.addLayout(bottom)

        self.current = ""
        start = start if start and os.path.isdir(start) else \
            next((p for p in (os.path.dirname(start or ""),) if p and os.path.isdir(p)), QDir.homePath())
        self.fill_sidebar()
        self.navigate(start, remember=False)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.fill_sidebar)
        self.timer.start(3000)

    # ------------------------------------------------------------ panneau latéral
    def section(self, text):
        it = QListWidgetItem(text.upper())
        it.setFlags(Qt.NoItemFlags)
        f = it.font()
        f.setPointSizeF(f.pointSizeF() * 0.8)
        f.setBold(True)
        it.setFont(f)
        it.setForeground(Qt.gray)
        self.side.addItem(it)

    def entry(self, text, ico, path=None, dev=None, tip=None):
        it = QListWidgetItem(ico, text)
        it.setData(ROLE_PATH, path)
        it.setData(ROLE_DEV, dev)
        it.setToolTip(tip or path or dev or "")
        self.side.addItem(it)

    def fill_sidebar(self):
        devs = block_devices()
        known = {mp for _, _, mp, _ in devs if mp}
        net = network_mounts(known)
        sig = (tuple(devs), tuple(net))
        if sig == self.devices_sig:
            return
        self.devices_sig = sig
        self.side.clear()

        self.section("Emplacements")
        home = QDir.homePath()
        self.entry("Dossier personnel", app_icon("place-home"), home)
        for loc, ico, text in (
                (QStandardPaths.DesktopLocation, "place-desktop", "Bureau"),
                (QStandardPaths.DocumentsLocation, "place-documents", "Documents"),
                (QStandardPaths.DownloadLocation, "place-download", "Téléchargements"),
                (QStandardPaths.PicturesLocation, "place-pictures", "Images"),
                (QStandardPaths.MusicLocation, "place-music", "Musique"),
                (QStandardPaths.MoviesLocation, "place-videos", "Vidéos")):
            p = QStandardPaths.writableLocation(loc)
            if p and p != home and os.path.isdir(p):
                self.entry(os.path.basename(p) or text, app_icon(ico), p)
        self.entry("Racine", app_icon("place-root"), "/")

        if devs:
            self.section("Périphériques")
            for name, dev, mp, rem in devs:
                ico = app_icon("usb" if rem else "drive")
                state = f"Monté sur {mp}" if mp else "Non monté — cliquez pour monter"
                self.entry(name, ico, mp, dev, f"{dev}\n{state}")
                if not mp:
                    it = self.side.item(self.side.count() - 1)
                    f = it.font()
                    f.setItalic(True)
                    it.setFont(f)

        if net:
            self.section("Réseau")
            for name, path in net:
                self.entry(name, app_icon("network"), path)

    def side_clicked(self, it):
        path, dev = it.data(ROLE_PATH), it.data(ROLE_DEV)
        if path:
            self.navigate(path)
        elif dev:
            self.mount(dev)

    def side_menu(self, pos):
        it = self.side.itemAt(pos)
        if not it or not it.data(ROLE_DEV):
            return
        dev, path = it.data(ROLE_DEV), it.data(ROLE_PATH)
        m = QMenu(self)
        if path:
            m.addAction("Ouvrir", lambda: self.navigate(path))
            m.addAction("Démonter", lambda: self.udisks("unmount", dev, path))
        else:
            m.addAction("Monter", lambda: self.mount(dev))
        m.exec(self.side.mapToGlobal(pos))

    def mount(self, dev):
        self.udisks("mount", dev)

    def udisks(self, action, dev, mountpoint=None):
        if not shutil.which("udisksctl"):
            QMessageBox.information(self, "Périphérique", "udisksctl est introuvable : montez le disque "
                                    "depuis votre gestionnaire de fichiers.")
            return
        self.setCursor(Qt.BusyCursor)
        proc = QProcess(self)

        def done(code, _status=None):
            self.unsetCursor()
            out = to_bytes(proc.readAllStandardOutput()).decode(errors="replace")
            err = to_bytes(proc.readAllStandardError()).decode(errors="replace").strip()
            if code != 0:
                QMessageBox.warning(self, "Périphérique", err or f"Échec ({action}).")
            self.devices_sig = None
            self.fill_sidebar()
            if action == "mount" and code == 0:
                mp = next((m for _, d, m, _ in block_devices() if d == dev and m), None)
                if not mp and " at " in out:
                    mp = out.split(" at ", 1)[1].strip().rstrip(".")
                if mp:
                    self.navigate(mp)
            elif action == "unmount" and code == 0 and mountpoint and \
                    (self.current + "/").startswith(mountpoint.rstrip("/") + "/"):
                self.navigate(QDir.homePath(), remember=False)

        proc.finished.connect(done)
        proc.start("udisksctl", [action, "-b", dev])

    # ------------------------------------------------------------ navigation
    def navigate(self, path, remember=True):
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Dossier", f"Dossier introuvable :\n{path}")
            self.path.setText(self.current)
            return
        if remember and self.current and path != self.current:
            self.history.append(self.current)
        self.current = path
        self.view.setRootIndex(self.model.index(path))
        self.view.clearSelection()
        self.path.setText(path)
        self.b_prev.setEnabled(bool(self.history))
        self.b_up.setEnabled(path != "/")
        self.highlight_sidebar()
        self.update_choice()

    def go_back(self):
        if self.history:
            self.navigate(self.history.pop(), remember=False)

    def highlight_sidebar(self):
        self.side.clearSelection()
        best, best_len = None, -1
        for i in range(self.side.count()):
            p = self.side.item(i).data(ROLE_PATH)
            if p and (self.current == p or self.current.startswith(p.rstrip("/") + "/")) and len(p) > best_len:
                best, best_len = self.side.item(i), len(p)
        if best:
            best.setSelected(True)

    def selected_path(self):
        idx = self.view.selectionModel().selectedRows()
        return self.model.filePath(idx[0]) if idx else self.current

    def update_choice(self, *_):
        self.choice.setText("Dossier choisi : " + self.selected_path())

    def new_folder(self):
        name, ok = QInputDialog.getText(self, "Nouveau dossier", "Nom du dossier :")
        if not ok or not name.strip():
            return
        p = os.path.join(self.current, name.strip())
        try:
            os.makedirs(p)
        except OSError as e:
            QMessageBox.warning(self, "Nouveau dossier", str(e))
            return
        QTimer.singleShot(200, lambda: self.view.setCurrentIndex(self.model.index(p)))

    def accept_choice(self):
        self.chosen = self.selected_path()
        self.accept()


def pick_folder(parent, title, start):
    """Renvoie le dossier choisi, ou '' si annulé."""
    d = FolderPicker(parent, title, start)
    return d.chosen if d.exec() else ""
