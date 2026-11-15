"""Logique Android : sauvegarde / synchronisation via adb.

Copie photos, vidéos, musique, documents, téléchargements, enregistrements et médias
WhatsApp vers un dossier lisible. Les sauvegardes suivantes sont incrémentales : seuls
les fichiers nouveaux ou modifiés sont copiés.

Prérequis : adb (sudo apt install adb), « Débogage USB » activé sur le téléphone
(Paramètres > Options pour les développeurs).
"""
import os
import re
import shutil
import subprocess
from datetime import datetime

# (dossier sur le téléphone, dossier de destination local)
SOURCES = {
    "photos": [("DCIM", "Photos et vidéos/DCIM"), ("Pictures", "Photos et vidéos/Pictures"),
               ("Movies", "Photos et vidéos/Movies")],
    "music": [("Music", "Musique")],
    "voice": [("Recordings", "Enregistrements vocaux")],
    "docs": [("Documents", "Documents"), ("Download", "Téléchargements")],
    "whatsapp": [("Android/media/com.whatsapp/WhatsApp/Media", "WhatsApp"),
                 ("WhatsApp/Media", "WhatsApp")],
}
PHONE_ROOT = "/sdcard"
TRASH = "_Corbeille-sync"


# --------------------------------------------------------------------- adb
class Adb:
    def __init__(self, serial=None):
        self.serial = serial
        self.procs = []

    def cmd(self, *args):
        base = ["adb"] + (["-s", self.serial] if self.serial else [])
        return base + list(args)

    def run(self, *args, timeout=120):
        return subprocess.run(self.cmd(*args), capture_output=True, text=True,
                              errors="replace", timeout=timeout)

    def cancel(self):
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass


def adb_available():
    return shutil.which("adb") is not None


def list_devices():
    """[(serial, état, modèle)] — état : device / unauthorized / offline."""
    if not adb_available():
        return []
    try:
        out = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return []
    devs = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and not line.startswith("*"):
            m = re.search(r"model:(\S+)", line)
            devs.append((parts[0], parts[1], m.group(1).replace("_", " ") if m else parts[0]))
    return devs


def list_remote(adb, src):
    """{chemin relatif: (taille, mtime)} pour un dossier du téléphone, ou None s'il n'existe pas."""
    q = src.replace("'", "'\\''")
    r = adb.run("shell", f"find '{q}' -type f -exec stat -c '%s|%Y|%n' {{}} +", timeout=600)
    files, prefix = {}, src.rstrip("/") + "/"
    for line in r.stdout.splitlines():
        parts = line.rstrip("\r").split("|", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[2].startswith(prefix):
            files[parts[2][len(prefix):]] = (int(parts[0]), int(parts[1]))
    if not files and r.returncode != 0:
        return None
    return files


def needs_copy(local, size, mtime):
    try:
        st = os.stat(local)
    except OSError:
        return True
    return st.st_size != size or abs(int(st.st_mtime) - mtime) > 2


# ------------------------------------------------------------ synchronisation
def sync(adb, out, selected, mirror, log, progress, cancel):
    """selected : liste de (dossier téléphone absolu, dossier local relatif)."""
    plans = []  # (src, local_dir, remote, bulk, todo)
    log("Analyse du téléphone…")
    for src, local_rel in selected:
        if cancel():
            return {}
        remote = list_remote(adb, src)
        if remote is None:
            log(f"  {src} : absent, ignoré")
            continue
        local_dir = os.path.join(out, local_rel)
        # copie en bloc seulement si le dossier local n'existe pas et n'est pas déjà
        # destiné à un autre dossier du téléphone (ex. ancien et nouveau WhatsApp)
        bulk = bool(remote) and not os.path.exists(local_dir) \
            and all(local_dir != p[1] for p in plans)
        todo = list(remote) if bulk else [r for r, (s, m) in remote.items()
                                          if needs_copy(os.path.join(local_dir, *r.split("/")), s, m)]
        log(f"  {src} : {len(remote)} fichiers, {len(todo)} à copier")
        plans.append((src, local_dir, remote, bulk, todo))

    total = sum(remote[r][0] for _, _, remote, _, todo in plans for r in todo) or 1
    done = 0
    copied = errors = removed = 0
    for src, local_dir, remote, bulk, todo in plans:
        if cancel():
            log("Annulé.")
            break
        if bulk:
            n_files = len(todo)
            avg = sum(remote[r][0] for r in todo) / max(n_files, 1)
            staging = os.path.join(out, ".transfert-en-cours")
            shutil.rmtree(staging, ignore_errors=True)
            os.makedirs(staging)
            log(f"Copie de {src} ({n_files} fichiers)…")
            p = subprocess.Popen(adb.cmd("pull", "-a", src, staging), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, bufsize=0)
            adb.procs.append(p)
            buf, n = b"", 0
            while True:
                chunk = p.stdout.read(512)
                if not chunk:
                    break
                buf += chunk
                parts = re.split(rb"[\r\n]", buf)
                buf = parts.pop()
                for raw in parts:
                    if re.match(rb"\[\s*100%\]", raw):
                        n += 1
                        progress(min(100, (done + n * avg) * 100 / total))
            p.wait()
            made = os.path.join(staging, os.path.basename(src.rstrip("/")))
            if p.returncode == 0 and os.path.isdir(made) and not cancel():
                os.makedirs(os.path.dirname(local_dir) or ".", exist_ok=True)
                shutil.move(made, local_dir)
                copied += n_files
            else:
                errors += n_files
                log(f"  Échec ou interruption pour {src}")
            shutil.rmtree(staging, ignore_errors=True)
            done += sum(remote[r][0] for r in todo)
        else:
            for rel in todo:
                if cancel():
                    break
                size, mtime = remote[rel]
                dest = os.path.join(local_dir, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                r = adb.run("pull", "-a", f"{src}/{rel}", dest, timeout=3600)
                if r.returncode == 0:
                    copied += 1
                else:
                    errors += 1
                    log(f"  Erreur : {rel}")
                done += size
                progress(min(100, done * 100 / total))
    if mirror and not cancel():
        # plusieurs dossiers du téléphone peuvent alimenter le même dossier local
        union = {}
        for _, local_dir, remote, _, _ in plans:
            union.setdefault(local_dir, set()).update(remote)
        for local_dir, rels in union.items():
            if not os.path.isdir(local_dir):
                continue
            if not rels:
                log(f"  Miroir ignoré pour {local_dir} : liste du téléphone vide (par sécurité)")
                continue
            removed += move_deleted(out, local_dir, rels, log)
    progress(100)
    log(f"Terminé : {copied} copiés, {errors} erreurs" + (f", {removed} déplacés dans {TRASH}." if mirror else "."))
    return {"copied": copied, "errors": errors, "removed": removed}


def move_deleted(out, local_dir, remote, log):
    """Mode miroir : déplace dans _Corbeille-sync ce qui n'existe plus sur le téléphone."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    n = 0
    for base, _, names in os.walk(local_dir):
        for name in names:
            full = os.path.join(base, name)
            rel = os.path.relpath(full, local_dir).replace(os.sep, "/")
            if rel not in remote:
                dest = os.path.join(out, TRASH, stamp, os.path.relpath(full, out))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(full, dest)
                n += 1
    if n:
        log(f"  {n} fichier(s) supprimés du téléphone déplacés dans {TRASH}/{stamp}")
    return n


def list_storages(adb):
    """Cartes SD / stockages externes : [(chemin, nom)] ex. ('/storage/1A2B-3C4D', 'Carte SD')."""
    try:
        r = adb.run("shell", "ls /storage", timeout=15)
    except Exception:
        return []
    ids = [n.strip() for n in r.stdout.splitlines()
           if n.strip() and n.strip() not in ("emulated", "self") and not n.startswith("ls:")]
    return [(f"/storage/{i}", "Carte SD" if len(ids) == 1 else f"Carte SD {i}") for i in ids]


def build_selection(opts, extra, storages=(("/sdcard", ""),)):
    """storages : [(racine sur le téléphone, préfixe du dossier local)]."""
    sel = []
    for root, prefix in storages:
        for key, entries in SOURCES.items():
            if opts.get(key):
                sel += [(f"{root}/{src}", os.path.join(prefix, local) if prefix else local)
                        for src, local in entries]
    if extra.strip():
        p = extra.strip().rstrip("/")
        sel.append((p if p.startswith("/") else f"{PHONE_ROOT}/{p}", "Autres/" + os.path.basename(p)))
    return sel
