"""Vérification et installation des prérequis (outils système et module Python optionnel)."""
import importlib.util
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass, field

from . import system

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
    win_install: callable = None  # Windows : étape d'installation écrite en Python
    win_label: str = ""           # Windows : texte affiché pour cette étape


PREREQS_LINUX = [
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

# ------------------------------------------------------------ Windows
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
APPLE_DEVICES_ID = "9NP83LWLPZ9K"  # « Apple Devices » sur le Microsoft Store
APPLE_SERVICE = "Apple Mobile Device Service"


def _apple_service():
    """Service Apple qui gère l'iPhone en USB (installé par Apple Devices ou iTunes)."""
    try:
        return system.run(["sc", "query", APPLE_SERVICE], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def download_adb(log):
    """Télécharge les outils Android officiels de Google dans le dossier de l'appli (sans droits admin)."""
    import urllib.request
    import zipfile
    dest = system.data_dir()
    os.makedirs(dest, exist_ok=True)
    tmp = os.path.join(dest, "platform-tools.zip")
    log(f"Téléchargement de {PLATFORM_TOOLS_URL}")
    with urllib.request.urlopen(PLATFORM_TOOLS_URL, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, shown = 0, -1
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            pct = got * 100 // total if total else -1
            if pct >= shown + 20:
                log(f"  {pct} %")
                shown = pct
    log("Extraction…")
    with zipfile.ZipFile(tmp) as z:
        z.extractall(dest)  # crée dest/platform-tools/
    os.remove(tmp)
    system.setup_path()
    log("adb installé dans " + os.path.join(dest, "platform-tools"))


def install_apple_devices(log):
    """Installe « Apple Devices » (pilote + service iPhone, sans iTunes) depuis le Microsoft Store."""
    if system.which("winget"):
        cmd = ["winget", "install", "--id", APPLE_DEVICES_ID, "--source", "msstore",
               "--accept-package-agreements", "--accept-source-agreements"]
        log("$ " + " ".join(cmd))
        r = system.run(cmd, capture_output=True, text=True, errors="replace")
        for line in (r.stdout or "").splitlines():
            if line.strip() and not set(line.strip()) <= set("-\\|/ █▒"):
                log(line.rstrip())
        if r.returncode == 0 or _apple_service():
            log("Apple Devices est installé. Débranchez puis rebranchez l'iPhone.")
            return
        log("winget n'a pas pu l'installer : ouverture du Microsoft Store.")
    os.startfile("ms-windows-store://search/?query=Apple%20Devices")  # noqa: S606 (Windows)
    raise RuntimeError("Installez « Apple Devices » depuis le Microsoft Store (gratuit), "
                       "puis cliquez sur « Vérifier à nouveau ».")


PREREQS_WIN = [
    Prereq("adb", "adb (outils Android de Google)", "Communication avec le téléphone Android",
           "android", True, lambda: bool(system.which("adb")),
           win_install=download_adb, win_label="Télécharger adb depuis le site de Google (environ 7 Mo)"),
    Prereq("imobile", "libimobiledevice", "Sauvegarde et détection de l'iPhone (fourni avec l'appli)",
           "iphone", True, lambda: all(system.which(t) for t in ("idevicebackup2", "idevice_id", "ideviceinfo"))),
    Prereq("apple", "Pilote iPhone (Apple Devices)",
           "Service Apple qui gère l'iPhone en USB. Fourni par l'application gratuite « Apple Devices » "
           "(Microsoft Store) : inutile de l'ouvrir, et iTunes n'est pas nécessaire.",
           "iphone", True, _apple_service,
           win_install=install_apple_devices, win_label="Installer « Apple Devices » depuis le Microsoft Store"),
    Prereq("mutagen", "mutagen (Python)", "Nomme la musique iPhone par artiste / album / titre",
           "iphone", False, lambda: importlib.util.find_spec("mutagen") is not None),
]

PREREQS = PREREQS_WIN if system.IS_WIN else PREREQS_LINUX

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
    if system.IS_WIN:
        cmds = [p.win_install for p in items if p.win_install]
        shown = "\n".join(p.win_label for p in items if p.win_install)
        manual = [p.name for p in items if not p.win_install]
        note = ("« Installer maintenant » s'en occupe ; Windows peut demander une confirmation."
                if cmds else "")
        if manual:
            note += (" " if note else "") + ("Élément manquant dans l'appli : " + ", ".join(manual)
                                             + ". Réinstallez Smartphone Backup.")
        return cmds, shown, note
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
