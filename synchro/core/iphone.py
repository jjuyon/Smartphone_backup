"""Logique iPhone : sauvegarde (idevicebackup2) puis rangement en dossiers lisibles.

  Photos/AAAA/MM/…   Documents/…   Musique/Artiste/Album/…   Notes vocales/…

Prérequis : libimobiledevice-utils (idevicebackup2, idevice_id), iPhone en sauvegarde
NON chiffrée. Optionnel : mutagen (noms de morceaux).

Les deux étapes sont incrémentales : idevicebackup2 ne recopie que ce qui a changé et
le rangement ignore les fichiers déjà présents à destination.
"""
import os
import plistlib
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".dng", ".tif",
             ".tiff", ".webp", ".mov", ".mp4", ".m4v"}
MUSIC_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aif", ".aiff", ".alac", ".m4b"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf",
           ".md", ".csv", ".odt", ".ods", ".odp", ".epub", ".pages", ".numbers", ".key"}
FILE_PROVIDER = "AppDomainGroup-group.com.apple.FileProvider.LocalStorage"

_names = {}  # cache udid -> nom de l'appareil


# ---------------------------------------------------------------- détection
def tools_available():
    return shutil.which("idevicebackup2") is not None and shutil.which("idevice_id") is not None


def list_iphones():
    """[(udid, nom)] des iPhone branchés (nom = « iPhone » si l'appareil n'est pas encore approuvé)."""
    if not shutil.which("idevice_id"):
        return []
    try:
        out = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True, timeout=3).stdout
    except Exception:
        return []
    devs = []
    for udid in (l.strip() for l in out.splitlines()):
        if not udid:
            continue
        if not _names.get(udid) and shutil.which("ideviceinfo"):
            try:
                r = subprocess.run(["ideviceinfo", "-u", udid, "-k", "DeviceName"],
                                   capture_output=True, text=True, timeout=3)
                if r.returncode == 0 and r.stdout.strip():
                    _names[udid] = r.stdout.strip()
            except Exception:
                pass
        devs.append((udid, _names.get(udid) or "iPhone"))
    return devs


# ---------------------------------------------------------------- utilitaires
def clean(part):
    """Nettoie un nom de fichier/dossier (caractères interdits, '..', longueur)."""
    part = re.sub(r'[<>:"|?*\x00-\x1f\\]', "_", part).strip(" .")
    if part in ("", ".", ".."):
        part = "_"
    return part[:150]


def clean_path(rel):
    return os.path.join(*[clean(p) for p in rel.split("/") if p not in ("", ".")] or ["_"])


def variants(path):
    """path, path_1, path_2… tant qu'ils existent."""
    base, ext = os.path.splitext(path)
    yield path
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        yield f"{base}_{i}{ext}"
        i += 1


def already_there(path, size):
    """Vrai si le fichier (ou une de ses variantes _N) existe déjà avec la même taille."""
    for p in variants(path):
        try:
            if os.path.getsize(p) == size:
                return True
        except OSError:
            return False
    return False


def unique(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def find_backup(root):
    """Retourne le dossier contenant Manifest.db (root ou son sous-dossier le plus récent)."""
    if os.path.exists(os.path.join(root, "Manifest.db")):
        return root
    best, best_t = None, -1
    if os.path.isdir(root):
        for d in os.listdir(root):
            m = os.path.join(root, d, "Manifest.db")
            if os.path.exists(m) and os.path.getmtime(m) > best_t:
                best, best_t = os.path.join(root, d), os.path.getmtime(m)
    return best


def file_date(blob):
    """Date de dernière modification (epoch) lue dans le plist de la sauvegarde."""
    try:
        for o in plistlib.loads(blob).get("$objects", []):
            if isinstance(o, dict) and "LastModified" in o:
                return int(o["LastModified"])
    except Exception:
        pass
    return None


def music_dest(src, fallback):
    """Chemin Artiste/Album/NN - Titre.ext d'après les tags (mutagen), sinon None."""
    try:
        import mutagen  # type: ignore
        tags = mutagen.File(src, easy=True)
        if not tags:
            return None
        g = lambda k: (tags.get(k) or [""])[0]
        title, artist, album = g("title"), g("artist") or g("albumartist"), g("album")
        if not title:
            return None
        num = re.match(r"\d+", g("tracknumber") or "")
        name = (f"{int(num.group()):02d} - " if num else "") + title + os.path.splitext(fallback)[1]
        return os.path.join(clean(artist or "Artiste inconnu"), clean(album or "Album inconnu"), clean(name))
    except Exception:
        return None


def classify(domain, rel, opts):
    """Retourne (catégorie, chemin relatif de destination) ou None."""
    ext = os.path.splitext(rel.lower())[1]
    name = os.path.basename(rel)
    if opts["photos"] and domain == "CameraRollDomain" and rel.startswith("Media/DCIM/") and ext in PHOTO_EXT:
        return "Photos", name
    if opts["music"] and domain == "MediaDomain" and rel.startswith("Media/iTunes_Control/Music/") and ext in MUSIC_EXT:
        return "Musique", name
    if opts["voice"] and domain == "MediaDomain" and rel.startswith("Media/Recordings/") and ext == ".m4a":
        return "Notes vocales", name
    if opts["docs"]:
        if domain.startswith(FILE_PROVIDER) and rel.startswith("File Provider Storage/"):
            return "Documents", os.path.join("Sur mon iPhone", clean_path(rel[len("File Provider Storage/"):]))
        if domain.startswith("AppDomain-") and rel.startswith("Documents/") and ext in DOC_EXT:
            return "Documents", os.path.join("Applications", clean(domain[len("AppDomain-"):]),
                                             clean_path(rel[len("Documents/"):]))
    return None


# ------------------------------------------------------------------ rangement
def organize(backup_root, out, opts, log, progress, cancel):
    backup = find_backup(backup_root)
    if not backup:
        raise RuntimeError("Aucune sauvegarde (Manifest.db) trouvée dans ce dossier.")
    try:
        con = sqlite3.connect(os.path.join(backup, "Manifest.db"))
        rows = con.execute("SELECT fileID, domain, relativePath, file FROM Files WHERE flags = 1").fetchall()
        con.close()
    except sqlite3.DatabaseError:
        raise RuntimeError("Manifest.db illisible : la sauvegarde est probablement chiffrée. "
                           "Désactivez le chiffrement (idevicebackup2 -i encryption off) et refaites-la.")

    todo = []
    for file_id, domain, rel, blob in rows:
        c = classify(domain, rel, opts)
        if c:
            todo.append((file_id, c[0], c[1], blob))
    total = len(todo)
    log(f"{total} fichiers à examiner pour {out}")
    stats = {}
    absent = errors = skipped = 0
    for i, (file_id, cat, rel, blob) in enumerate(todo, 1):
        if cancel():
            log("Annulé.")
            break
        progress(i * 100 / max(total, 1))
        src = os.path.join(backup, file_id[:2], file_id)
        if not os.path.exists(src):
            absent += 1
            continue
        ts = file_date(blob) if blob else None
        if cat == "Photos":
            d = datetime.fromtimestamp(ts) if ts else None
            rel = os.path.join(f"{d:%Y}" if d else "Sans date", f"{d:%m}" if d else "", clean(rel))
        elif cat == "Musique":
            rel = music_dest(src, rel) or os.path.join("Sans informations", clean(rel))
        elif cat == "Notes vocales":
            rel = clean_path(rel)
        dest = os.path.normpath(os.path.join(out, cat, rel))
        if already_there(dest, os.path.getsize(src)):
            skipped += 1
            continue
        dest = unique(dest)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            if ts:
                os.utime(dest, (ts, ts))
            stats[cat] = stats.get(cat, 0) + 1
        except OSError as e:
            errors += 1
            log(f"Erreur : {rel} ({e})")
    progress(100)
    resume = ", ".join(f"{n} {c}" for c, n in stats.items()) or "aucun nouveau fichier"
    log(f"Terminé : {resume}. Déjà présents : {skipped}. "
        f"Absents de la sauvegarde : {absent}. Erreurs : {errors}.")
    return stats


# --------------------------------------------------------------- sauvegarde
def run_backup(dest, log, progress, cancel, holder, udid=None):
    if not tools_available():
        raise RuntimeError("idevicebackup2 est introuvable. Installez-le :\n"
                           "sudo apt install libimobiledevice-utils")
    if not list_iphones():
        raise RuntimeError("Aucun iPhone détecté. Branchez-le, déverrouillez-le et "
                           "acceptez « Faire confiance à cet ordinateur ».")
    os.makedirs(dest, exist_ok=True)
    log("Sauvegarde en cours (laissez l'iPhone branché et déverrouillé)…")
    cmd = ["idevicebackup2"] + (["-u", udid] if udid else []) + ["backup", dest]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    holder.append(p)
    buf, last = b"", ""
    while True:
        chunk = p.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop()
        for raw in parts:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            m = re.search(r"(\d+)%", line)
            if m:
                progress(int(m.group(1)))
            elif line != last:
                log(line)
            last = line
    p.wait()
    if cancel():
        raise RuntimeError("Sauvegarde annulée.")
    if p.returncode != 0:
        raise RuntimeError(f"idevicebackup2 a échoué (code {p.returncode}).")
    log("Sauvegarde terminée.")
