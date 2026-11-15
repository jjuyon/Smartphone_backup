"""Arrêt propre des processus lancés par l'appli (adb, idevicebackup2…) à la fermeture.

Avec psutil (Windows, appli installée, venv) ; sinon, sous Linux, lecture directe de /proc
(ex. vieux Mac avec le Python du système, sans psutil).
"""
import os
import signal
import time

from . import system

try:
    import psutil
except ImportError:  # pragma: no cover - dépend de l'installation
    psutil = None


# ------------------------------------------------------------ /proc (Linux sans psutil)
def _ppid(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            # le nom (2e champ) peut contenir des espaces : on coupe après la dernière ')'
            return int(f.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def _cmdline(pid):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    except OSError:
        return []


def _alive(pid):
    if psutil:
        try:
            return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"  # zombie = déjà terminé
    except (OSError, IndexError):
        return False


def descendants(root=None):
    """Tous les processus enfants (et petits-enfants…) de root (par défaut : l'appli)."""
    root = root or os.getpid()
    if psutil:
        try:
            return [c.pid for c in psutil.Process(root).children(recursive=True)]
        except psutil.Error:
            return []
    parents = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            pp = _ppid(int(d))
            if pp is not None:
                parents.setdefault(pp, []).append(int(d))
    found, todo = [], [root]
    while todo:
        for c in parents.get(todo.pop(), []):
            found.append(c)
            todo.append(c)
    return found


def _name(pid):
    if psutil:
        try:
            return psutil.Process(pid).name()
        except psutil.Error:
            return str(pid)
    args = _cmdline(pid)
    return os.path.basename(args[0]) if args else str(pid)


def _signal(pid, hard):
    if psutil:
        try:
            p = psutil.Process(pid)
            p.kill() if hard else p.terminate()
        except psutil.Error:
            pass
        return
    try:
        os.kill(pid, signal.SIGKILL if hard else signal.SIGTERM)
    except OSError:
        pass


def kill_children(timeout=1.5):
    """Demande l'arrêt de tous les descendants, puis force ceux qui restent. Renvoie leurs noms."""
    pids = descendants()
    names = [_name(p) for p in pids]
    for hard in (False, True):
        for p in pids:
            _signal(p, hard)
        end = time.time() + timeout
        while time.time() < end and any(_alive(p) for p in pids):
            time.sleep(0.05)
        pids = [p for p in pids if _alive(p)]
        if not pids:
            break
    return names


def adb_server_running():
    """Le serveur adb (démon détaché, lancé par la première commande adb) tourne-t-il ?"""
    if psutil:
        me = None
        try:
            me = psutil.Process().username()
        except psutil.Error:
            pass
        for p in psutil.process_iter(["name", "cmdline", "username"]):
            try:
                name = (p.info["name"] or "").lower()
                if name in ("adb", "adb.exe") and "fork-server" in (p.info["cmdline"] or []) \
                        and (me is None or p.info["username"] == me):
                    return True
            except psutil.Error:
                continue
        return False
    uid = os.getuid()
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            if os.stat(f"/proc/{d}").st_uid != uid:
                continue
        except OSError:
            continue
        args = _cmdline(int(d))
        if args and os.path.basename(args[0]) == "adb" and "fork-server" in args:
            return True
    return False


def stop_adb_server():
    try:
        system.run(["adb", "kill-server"], capture_output=True, timeout=5)
    except Exception:
        pass
