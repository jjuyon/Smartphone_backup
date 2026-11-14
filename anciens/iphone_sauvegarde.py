#!/usr/bin/env python3
"""Sauvegarde d'iPhone sous Linux : photos, documents, musique, notes vocales.

1. Lance la sauvegarde (idevicebackup2 backup) ou utilise une sauvegarde existante.
2. Range le contenu dans des dossiers lisibles :
     Photos/AAAA/MM/…   Documents/…   Musique/Artiste/Album/…   Notes vocales/…

Prérequis : python3-tk, libimobiledevice-utils (idevicebackup2), iPhone en
sauvegarde NON chiffrée. Optionnel : python3-mutagen (noms de morceaux).
"""
import os
import plistlib
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".dng", ".tif",
             ".tiff", ".webp", ".mov", ".mp4", ".m4v"}
MUSIC_EXT = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".aif", ".aiff", ".alac", ".m4b"}
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf",
           ".md", ".csv", ".odt", ".ods", ".odp", ".epub", ".pages", ".numbers", ".key"}
FILE_PROVIDER = "AppDomainGroup-group.com.apple.FileProvider.LocalStorage"


# ---------------------------------------------------------------- utilitaires
def clean(part):
    """Nettoie un nom de fichier/dossier (caractères interdits, '..', longueur)."""
    part = re.sub(r'[<>:"|?*\x00-\x1f\\]', "_", part).strip(" .")
    if part in ("", ".", ".."):
        part = "_"
    return part[:150]


def clean_path(rel):
    return os.path.join(*[clean(p) for p in rel.split("/") if p not in ("", ".")] or ["_"])


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
    """Chemin Musique/Artiste/Album/NN - Titre.ext d'après les tags (mutagen), sinon None."""
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


# ------------------------------------------------------------------ organiser
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
    log(f"{total} fichiers à ranger dans {out}")
    stats = {}
    absent = errors = 0
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
        else:
            rel = clean_path(rel) if cat == "Notes vocales" else rel
        dest = unique(os.path.normpath(os.path.join(out, cat, rel)))
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
    resume = ", ".join(f"{n} {c}" for c, n in stats.items()) or "rien"
    log(f"Terminé : {resume}. Absents de la sauvegarde : {absent}. Erreurs : {errors}.")
    return stats


# --------------------------------------------------------------- sauvegarde
def run_backup(dest, log, progress, cancel, holder):
    if not shutil.which("idevicebackup2"):
        raise RuntimeError("idevicebackup2 est introuvable. Installez-le :\n"
                           "sudo apt install libimobiledevice-utils")
    ids = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True).stdout.strip() \
        if shutil.which("idevice_id") else "?"
    if not ids:
        raise RuntimeError("Aucun iPhone détecté. Branchez-le, déverrouillez-le et "
                           "acceptez « Faire confiance à cet ordinateur ».")
    os.makedirs(dest, exist_ok=True)
    log("Sauvegarde en cours (laissez l'iPhone branché et déverrouillé)…")
    p = subprocess.Popen(["idevicebackup2", "backup", dest], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, bufsize=0)
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


# ------------------------------------------------------------------- interface
def main_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Sauvegarde iPhone")
    root.geometry("720x560")
    q = queue.Queue()
    state = {"cancel": False, "busy": False, "procs": []}
    home = os.path.expanduser("~")
    raw_var = tk.StringVar(value=os.path.join(home, "iPhone-sauvegarde-brute"))
    out_var = tk.StringVar(value=os.path.join(home, "iPhone-contenu"))
    opt_vars = {k: tk.BooleanVar(value=True) for k in ("photos", "docs", "music", "voice")}

    def row(r, label, var):
        ttk.Label(root, text=label).grid(row=r, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(root, textvariable=var, width=60).grid(row=r, column=1, sticky="we", padx=4)
        ttk.Button(root, text="Parcourir…",
                   command=lambda: var.set(filedialog.askdirectory(initialdir=var.get()) or var.get())
                   ).grid(row=r, column=2, padx=8)

    row(0, "Sauvegarde brute :", raw_var)
    row(1, "Dossier de destination :", out_var)
    box = ttk.LabelFrame(root, text="Contenu à récupérer")
    box.grid(row=2, column=0, columnspan=3, sticky="we", padx=8, pady=6)
    for i, (k, t) in enumerate((("photos", "Photos et vidéos"), ("docs", "Documents"),
                                ("music", "Musique"), ("voice", "Notes vocales"))):
        ttk.Checkbutton(box, text=t, variable=opt_vars[k]).grid(row=0, column=i, padx=10, pady=4)

    bar = ttk.Progressbar(root, maximum=100)
    bar.grid(row=4, column=0, columnspan=3, sticky="we", padx=8, pady=4)
    logbox = tk.Text(root, height=18, state="disabled", wrap="word")
    logbox.grid(row=5, column=0, columnspan=3, sticky="nsew", padx=8, pady=4)
    root.columnconfigure(1, weight=1)
    root.rowconfigure(5, weight=1)

    def log(t):
        q.put(("log", t))

    def progress(v):
        q.put(("bar", v))

    def worker(do_backup):
        try:
            opts = {k: v.get() for k, v in opt_vars.items()}
            if not any(opts.values()):
                raise RuntimeError("Cochez au moins un type de contenu.")
            if do_backup:
                run_backup(raw_var.get(), log, progress, lambda: state["cancel"], state["procs"])
            progress(0)
            organize(raw_var.get(), out_var.get(), opts, log, progress, lambda: state["cancel"])
        except Exception as e:
            q.put(("err", str(e)))
        q.put(("done", None))

    def start(do_backup):
        if state["busy"]:
            return
        state.update(cancel=False, busy=True, procs=[])
        for b in (b1, b2):
            b.config(state="disabled")
        bar["value"] = 0
        threading.Thread(target=worker, args=(do_backup,), daemon=True).start()

    def cancel():
        state["cancel"] = True
        for p in state["procs"]:
            try:
                p.terminate()
            except Exception:
                pass

    b1 = ttk.Button(root, text="Sauvegarder l'iPhone puis ranger", command=lambda: start(True))
    b2 = ttk.Button(root, text="Ranger une sauvegarde existante", command=lambda: start(False))
    b3 = ttk.Button(root, text="Annuler", command=cancel)
    b1.grid(row=3, column=0, padx=8, pady=4)
    b2.grid(row=3, column=1, sticky="w")
    b3.grid(row=3, column=2)

    def poll():
        try:
            while True:
                kind, val = q.get_nowait()
                if kind == "log":
                    logbox.config(state="normal")
                    logbox.insert("end", val + "\n")
                    logbox.see("end")
                    logbox.config(state="disabled")
                elif kind == "bar":
                    bar["value"] = val
                elif kind == "err":
                    messagebox.showerror("Erreur", val)
                    log("ERREUR : " + val)
                elif kind == "done":
                    state["busy"] = False
                    for b in (b1, b2):
                        b.config(state="normal")
        except queue.Empty:
            pass
        root.after(100, poll)

    poll()
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 3:  # mode console : iphone_sauvegarde.py SAUVEGARDE DESTINATION
        o = {"photos": True, "docs": True, "music": True, "voice": True}
        organize(sys.argv[1], sys.argv[2], o, print, lambda v: None, lambda: False)
    else:
        main_gui()
