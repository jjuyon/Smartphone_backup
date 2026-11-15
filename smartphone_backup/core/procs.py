"""Arrêt propre des processus lancés par l'appli (adb, idevicebackup2…) à la fermeture.

Linux uniquement : la parenté des processus est lue dans /proc.
"""
import os
import signal
import subprocess
import time


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
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"  # zombie = déjà terminé
    except (OSError, IndexError):
        return False


def descendants(root=None):
    """Tous les processus enfants (et petits-enfants…) de root (par défaut : l'appli)."""
    root = root or os.getpid()
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


def kill_children(timeout=1.5):
    """SIGTERM à tous les descendants, puis SIGKILL à ceux qui restent. Renvoie les noms arrêtés."""
    pids = descendants()
    names = [os.path.basename(_cmdline(p)[0]) if _cmdline(p) else str(p) for p in pids]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in pids:
            try:
                os.kill(p, sig)
            except OSError:
                pass
        end = time.time() + timeout
        while time.time() < end and any(_alive(p) for p in pids):
            time.sleep(0.05)
        pids = [p for p in pids if _alive(p)]
        if not pids:
            break
    return names


def adb_server_running():
    """Le serveur adb (démon détaché, lancé par la première commande adb) tourne-t-il ?"""
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
        subprocess.run(["adb", "kill-server"], capture_output=True, timeout=5)
    except Exception:
        pass
