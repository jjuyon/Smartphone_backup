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
import tempfile
import time
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
STAGING = ".transfert-en-cours"  # ancienne copie en bloc (versions précédentes de l'appli)
BATCH_FILES = 40                 # fichiers par commande « adb pull »
BATCH_BYTES = 300 * 1024 * 1024  # … ou moins si les fichiers sont gros (vidéos)


def human(n):
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            return (f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}").replace(".", ",")
        n /= 1024


def salvage_staging(out, plans, log):
    """Récupère les fichiers d'une copie en bloc interrompue (anciennes versions) au lieu de les jeter."""
    staging = os.path.join(out, STAGING)
    if not os.path.isdir(staging):
        return
    n = 0
    for src, local_dir in plans:
        made = os.path.join(staging, os.path.basename(src.rstrip("/")))
        for base, _, names in os.walk(made):
            for name in names:
                dest = os.path.join(local_dir, os.path.relpath(os.path.join(base, name), made))
                if not os.path.exists(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(os.path.join(base, name), dest)
                    n += 1
    shutil.rmtree(staging, ignore_errors=True)
    if n:
        log(f"  {n} fichiers récupérés d'une copie précédente interrompue")


def batches(todo, remote):
    """Regroupe les fichiers à copier par dossier, en lots de taille raisonnable."""
    by_dir = {}
    for rel in todo:
        by_dir.setdefault(rel.rpartition("/")[0], []).append(rel)
    for d in sorted(by_dir):
        batch, size = [], 0
        for rel in sorted(by_dir[d]):
            if batch and (len(batch) >= BATCH_FILES or size + remote[rel][0] > BATCH_BYTES):
                yield d, batch
                batch, size = [], 0
            batch.append(rel)
            size += remote[rel][0]
        if batch:
            yield d, batch


def sync(adb, out, selected, mirror, log, progress, cancel, step=lambda t: None):
    """selected : liste de (dossier téléphone absolu, dossier local relatif).

    Copie par lots directement dans la destination : les fichiers apparaissent au fur et à mesure,
    la progression suit les octets reçus et une interruption ne perd que le lot en cours (un
    fichier incomplet a une taille ou une date différente : il est recopié la fois suivante)."""
    plans = []  # (src, local_dir, remote, todo)
    log("Analyse du téléphone…")
    step("Analyse du téléphone…")
    salvage_staging(out, [(src, os.path.join(out, rel)) for src, rel in selected], log)
    for src, local_rel in selected:
        if cancel():
            return {}
        remote = list_remote(adb, src)
        if remote is None:
            log(f"  {src} : absent, ignoré")
            continue
        local_dir = os.path.join(out, local_rel)
        todo = [r for r, (s, m) in remote.items() if needs_copy(os.path.join(local_dir, *r.split("/")), s, m)]
        log(f"  {src} : {len(remote)} fichiers, {len(todo)} à copier "
            f"({human(sum(remote[r][0] for r in todo))})")
        plans.append((src, local_dir, remote, todo))

    total = sum(remote[r][0] for _, _, remote, todo in plans for r in todo) or 1
    n_total = sum(len(todo) for *_, todo in plans)
    done = n_done = 0
    copied = errors = removed = 0
    started = time.time()
    for src, local_dir, remote, todo in plans:
        if cancel():
            break
        if todo:
            log(f"Copie de {src} ({len(todo)} fichiers)…")
        for d, batch in batches(todo, remote):
            if cancel():
                break
            dest_dir = os.path.join(local_dir, *d.split("/")) if d else local_dir
            os.makedirs(dest_dir, exist_ok=True)
            dests = [os.path.join(dest_dir, rel.rpartition("/")[2]) for rel in batch]
            with tempfile.TemporaryFile() as errf:
                p = subprocess.Popen(adb.cmd("pull", "-a", *[f"{src}/{rel}" for rel in batch], dest_dir),
                                     stdout=errf, stderr=subprocess.STDOUT)
                adb.procs.append(p)
                while True:  # progression : taille des fichiers déjà arrivés
                    try:
                        p.wait(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    got = 0
                    for f in dests:
                        try:
                            got += os.path.getsize(f)
                        except OSError:
                            pass
                    progress(min(99, (done + got) * 100 / total))
                adb.procs.remove(p)
                errf.seek(0)
                msg = errf.read().decode("utf-8", "replace").strip()
            for rel, dest in zip(batch, dests):
                size, mtime = remote[rel]
                if needs_copy(dest, size, mtime):
                    if not cancel():  # annulé : le lot interrompu sera repris la prochaine fois
                        errors += 1
                        log(f"  Erreur : {src}/{rel}")
                else:
                    copied += 1
                done += size
                n_done += 1
            if p.returncode not in (0, None) and msg and not cancel():
                log("  adb : " + msg.splitlines()[-1])
            progress(min(99, done * 100 / total))
            speed = done / max(time.time() - started, 1)
            left = (total - done) / speed if speed else 0
            step(f"Copie : {n_done} / {n_total} fichiers · {human(done)} / {human(total)}"
                 + (f" · environ {int(left // 60) + 1} min restantes" if n_done < n_total and done else ""))
    if cancel():
        log(f"Annulé : {copied} fichiers copiés. Relancez la sauvegarde pour copier le reste.")
        return {"copied": copied, "errors": errors, "removed": 0}
    if mirror and not cancel():
        # plusieurs dossiers du téléphone peuvent alimenter le même dossier local
        union = {}
        for _, local_dir, remote, _ in plans:
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
