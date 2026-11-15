"""Différences Linux / Windows regroupées ici.

- emplacement des outils (adb téléchargé par l'appli, libimobiledevice fourni avec l'appli Windows) ;
- lancement des commandes sans fenêtre de console sous Windows ;
- noms de fichiers interdits sous Windows (« : », « ? », « CON »…).
"""
import os
import re
import shutil
import subprocess
import sys

IS_WIN = os.name == "nt"

# sous Windows, chaque commande lancée depuis une appli graphique ouvrirait une console noire
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}


def data_dir():
    """Dossier des données de l'appli (outils téléchargés…)."""
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SmartphoneBackup")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "smartphone-backup")


def bundle_dir():
    """Dossier de l'appli installée (PyInstaller) ou des sources."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tool_dirs():
    dirs = [os.path.join(data_dir(), "platform-tools")]  # adb téléchargé par l'appli
    if getattr(sys, "frozen", False):
        for base in {bundle_dir(), os.path.dirname(sys.executable)}:
            dirs.append(os.path.join(base, "tools", "imobiledevice"))  # outils iPhone (Windows)
    return [d for d in dirs if os.path.isdir(d)]


def setup_path():
    """Ajoute les outils de l'appli au PATH (à appeler au démarrage et après un téléchargement)."""
    current = os.environ.get("PATH", "").split(os.pathsep)
    for d in reversed(tool_dirs()):
        if d not in current:
            current.insert(0, d)
    os.environ["PATH"] = os.pathsep.join(current)


def which(name):
    return shutil.which(name)


def tool(name):
    """Chemin complet d'un outil (adb, idevicebackup2…) ; le nom seul s'il est introuvable."""
    return shutil.which(name) or name


def run(cmd, **kw):
    """subprocess.run sans fenêtre de console sous Windows ; cmd[0] est cherché dans le PATH."""
    return subprocess.run([tool(cmd[0]), *cmd[1:]], **NO_WINDOW, **kw)


def popen(cmd, **kw):
    return subprocess.Popen([tool(cmd[0]), *cmd[1:]], **NO_WINDOW, **kw)


# ------------------------------------------------------------ noms de fichiers
WIN_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)


def safe_name(name, windows=IS_WIN):
    """Nom de fichier ou de dossier utilisable sur ce système (inchangé sous Linux)."""
    if not windows:
        return name
    name = WIN_BAD.sub("_", name).rstrip(" .")
    if not name:
        return "_"
    if WIN_RESERVED.match(name):
        name = "_" + name
    return name


def local_rel(rel, windows=IS_WIN):
    """Chemin relatif du téléphone (avec « / ») → chemin local, chaque élément rendu valide."""
    return os.path.join(*[safe_name(p, windows) for p in rel.split("/") if p]) if rel else ""
