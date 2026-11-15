"""Vérification et installation des prérequis (outils système et module Python optionnel)."""
import importlib.util
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass, field

SBIN = ("/usr/sbin", "/sbin", "/usr/bin", "/usr/local/sbin")
UDEV_DIRS = ("/etc/udev/rules.d", "/lib/udev/rules.d", "/usr/lib/udev/rules.d")


def _which(name):
    return shutil.which(name) or next((os.path.join(d, name) for d in SBIN
                                       if os.path.exists(os.path.join(d, name))), None)


def _android_udev():
    return any(os.path.exists(os.path.join(d, f)) for d in UDEV_DIRS
               for f in ("51-android.rules", "70-android-tools.rules", "51-android-udev.rules"))


def _in_venv():
    return sys.prefix != sys.base_prefix


@dataclass
class Prereq:
    key: str
    name: str
    desc: str
    target: str            # "iphone", "android" ou "commun"
    required: bool
    check: callable
    pkgs: dict = field(default_factory=dict)  # gestionnaire -> paquet système
    pip: str = None        # paquet pip (utilisé si l'appli tourne dans un venv)


PREREQS = [
    Prereq("adb", "adb", "Communication avec le téléphone Android", "android", True,
           lambda: bool(_which("adb")),
           {"apt": "adb", "dnf": "android-tools", "pacman": "android-tools"}),
    Prereq("udev", "Règles udev Android", "Autorise l'accès USB au téléphone sans être root",
           "android", False, _android_udev,
           {"apt": "android-sdk-platform-tools-common", "dnf": "android-tools", "pacman": "android-udev"}),
    Prereq("imobile", "libimobiledevice", "Sauvegarde et détection de l'iPhone "
           "(idevicebackup2, idevice_id)", "iphone", True,
           lambda: all(_which(t) for t in ("idevicebackup2", "idevice_id", "ideviceinfo")),
           {"apt": "libimobiledevice-utils", "dnf": "libimobiledevice-utils", "pacman": "libimobiledevice"}),
    Prereq("usbmuxd", "usbmuxd", "Service qui gère la connexion USB de l'iPhone", "iphone", True,
           lambda: bool(_which("usbmuxd")),
           {"apt": "usbmuxd", "dnf": "usbmuxd", "pacman": "usbmuxd"}),
    Prereq("mutagen", "mutagen (Python)", "Nomme la musique iPhone par artiste / album / titre",
           "iphone", False, lambda: importlib.util.find_spec("mutagen") is not None,
           {"apt": "python3-mutagen", "dnf": "python3-mutagen", "pacman": "python-mutagen"},
           pip="mutagen"),
]

MANAGERS = {
    "apt": ("apt-get", "sudo apt install {}",
            lambda p: ["sh", "-c", "apt-get update && DEBIAN_FRONTEND=noninteractive "
                                   "apt-get install -y " + " ".join(map(shlex.quote, p))]),
    "dnf": ("dnf", "sudo dnf install {}", lambda p: ["dnf", "install", "-y", *p]),
    "pacman": ("pacman", "sudo pacman -S {}", lambda p: ["pacman", "-S", "--needed", "--noconfirm", *p]),
}


AGENT_RE = re.compile(r"polkit.*(agent|auth|dialog)|policykit|lxpolkit|mate-polkit|xfce-polkit"
                      r"|^gnome-shell$|^cinnamon$|^budgie-polkit|hyprpolkitagent")


def polkit_agent_running():
    """Vrai si un agent polkit graphique tourne (nécessaire pour que pkexec demande le mot de passe).

    GNOME Shell, Cinnamon et Plasma intègrent leur propre agent ; ailleurs c'est un processus dédié
    (polkit-gnome, lxqt-policykit, mate-polkit…). Sous Linux uniquement (lecture de /proc).
    """
    uid = os.getuid()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return True  # impossible de vérifier : on suppose que oui
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid:
                continue
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                exe = f.read().split(b"\0", 1)[0].decode(errors="replace")
        except OSError:
            continue
        if exe and AGENT_RE.search(os.path.basename(exe)):
            return True
    return False


def package_manager():
    return next((k for k, (exe, _, _) in MANAGERS.items() if shutil.which(exe)), None)


def check_all():
    """[(Prereq, installé ?)]"""
    return [(p, bool(p.check())) for p in PREREQS]


def missing(target=None, required_only=False):
    return [p for p, ok in check_all() if not ok
            and (target is None or p.target == target)
            and (p.required or not required_only)]


def install_plan(items):
    """Retourne (commandes à exécuter [list], texte à afficher, explication si impossible).

    Les paquets système passent par pkexec (fenêtre de mot de passe) ; mutagen passe par pip
    quand l'appli tourne dans son environnement virtuel.
    """
    pm = package_manager()
    use_pip = _in_venv()
    sys_pkgs, pip_pkgs, unknown = [], [], []
    for p in items:
        if p.pip and use_pip:
            pip_pkgs.append(p.pip)
        elif pm and p.pkgs.get(pm):
            if p.pkgs[pm] not in sys_pkgs:
                sys_pkgs.append(p.pkgs[pm])
        else:
            unknown.append(p.name)
    cmds, shown = [], []
    if sys_pkgs:
        _, display, build = MANAGERS[pm]
        shown.append(display.format(" ".join(sys_pkgs)))
        cmds.append(["pkexec"] + build(sys_pkgs))
    if pip_pkgs:
        cmds.append([sys.executable, "-m", "pip", "install", *pip_pkgs])
        shown.append(f"{shlex.quote(sys.executable)} -m pip install {' '.join(pip_pkgs)}")
    note = ""
    if unknown:
        note = ("Gestionnaire de paquets non reconnu : installez manuellement "
                + ", ".join(unknown) + " avec l'outil de votre distribution.")
    if sys_pkgs and not shutil.which("pkexec"):
        note = "pkexec est absent : copiez la commande et lancez-la dans un terminal."
        cmds = [c for c in cmds if c[0] != "pkexec"]
    elif sys_pkgs and not polkit_agent_running():
        note = ("Aucun agent d'authentification graphique (polkit) n'est actif sur ce bureau : "
                "la fenêtre de mot de passe ne pourrait pas s'afficher. Copiez la commande et "
                "lancez-la dans un terminal.")
        cmds = [c for c in cmds if c[0] != "pkexec"]
    return cmds, "\n".join(shown), note
