"""Rangement des photos et vidéos par date : années, mois, jours ou événements.

Date de prise de vue, dans l'ordre de fiabilité :
  1. EXIF des photos JPEG (DateTimeOriginal) ;
  2. nom du fichier (IMG_20240315_143205.jpg, PXL_…, Screenshot_2024-03-15-…, IMG-20240315-WA0001…) ;
  3. métadonnées des vidéos MP4/MOV/3GP (en-tête « mvhd ») ;
  4. date de modification du fichier (conservée par la sauvegarde Android).
Sans dépendance externe.
"""
import os
import re
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime

from . import dupes
from .android import TRASH
from .iphone import already_there, unique

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".dng", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".webm", ".avi", ".m4v"}
MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août",
          "Septembre", "Octobre", "Novembre", "Décembre"]

# clé : (nom, exemple affiché)
STRUCTURES = {
    "year_month": ("Par année puis mois", "2024 / 03 - Mars / photo.jpg"),
    "year": ("Par année", "2024 / photo.jpg"),
    "month": ("Par mois (un seul niveau)", "2024-03 Mars / photo.jpg"),
    "year_day": ("Par année puis jour", "2024 / 2024-03-15 / photo.jpg"),
    "event": ("Par événement (sorties, vacances…)", "2024 / 2024-03-15 au 17 / photo.jpg"),
}
ORIGINS = {"camera": "Appareil photo", "screenshot": "Captures d'écran",
           "whatsapp": "WhatsApp", "other": "Autres images"}
MODES = {"link": "Liens physiques : aucun espace disque en plus (recommandé)",
         "copy": "Copier", "move": "Déplacer"}
DUPES_DIR = "_Doublons"  # doublons mis de côté par la fenêtre « Doublons »
DATE_SOURCES = {"exif": "EXIF", "name": "nom du fichier", "video": "métadonnées vidéo",
                "mtime": "date du fichier"}


@dataclass
class Item:
    path: str
    size: int
    date: datetime
    has_time: bool  # faux si seul le jour est connu (ex. IMG-20240315-WA0001.jpg)
    video: bool
    origin: str
    how: str  # clé de DATE_SOURCES
    dup: bool = False  # copie identique d'un autre fichier (un seul exemplaire est gardé)


# ------------------------------------------------------------ dates
def _valid(dt):
    return datetime(1990, 1, 1) <= dt <= datetime.now().replace(year=datetime.now().year + 1)


def _tiff_date(t):
    """Date dans un bloc EXIF (format TIFF)."""
    e = {b"II": "<", b"MM": ">"}.get(t[:2])
    if not e:
        return None

    def ifd(off):
        n = struct.unpack(e + "H", t[off:off + 2])[0]
        out = {}
        for k in range(n):
            p = off + 2 + 12 * k
            tag, _typ, cnt = struct.unpack(e + "HHI", t[p:p + 8])
            out[tag] = (cnt, t[p + 8:p + 12])
        return out

    def text(entry):
        cnt, raw = entry
        s = t[struct.unpack(e + "I", raw)[0]:][:cnt] if cnt > 4 else raw[:cnt]
        return s.split(b"\0")[0].decode("ascii", "replace").strip()

    ifd0 = ifd(struct.unpack(e + "I", t[4:8])[0])
    found = []
    if 0x8769 in ifd0:  # sous-bloc EXIF
        sub = ifd(struct.unpack(e + "I", ifd0[0x8769][1])[0])
        found += [sub.get(0x9003), sub.get(0x9004)]  # DateTimeOriginal, DateTimeDigitized
    found.append(ifd0.get(0x0132))  # DateTime
    for entry in found:
        if entry:
            try:
                dt = datetime.strptime(text(entry)[:19], "%Y:%m:%d %H:%M:%S")
                if _valid(dt):
                    return dt
            except ValueError:
                pass
    return None


def exif_date(path):
    try:
        with open(path, "rb") as f:
            data = f.read(131072)
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    try:
        while i + 4 <= len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker == 0xDA:  # début de l'image : plus de métadonnées
                return None
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
                return _tiff_date(data[i + 10:i + 2 + seg])
            i += 2 + seg
    except (struct.error, IndexError):
        pass
    return None


def video_date(path):
    """Date de création d'une vidéo MP4/MOV/3GP (stockée en UTC, convertie en heure locale)."""
    try:
        with open(path, "rb") as f:
            end_file = os.fstat(f.fileno()).st_size

            def boxes(start, end):
                pos = start
                while pos + 8 <= end:
                    f.seek(pos)
                    size, typ = struct.unpack(">I4s", f.read(8))
                    hdr = 8
                    if size == 1:
                        size, hdr = struct.unpack(">Q", f.read(8))[0], 16
                    elif size == 0:
                        size = end - pos
                    if size < hdr:
                        return
                    yield typ, pos + hdr, pos + size
                    pos += size

            for typ, start, end in boxes(0, end_file):
                if typ != b"moov":
                    continue
                for typ2, start2, _ in boxes(start, end):
                    if typ2 == b"mvhd":
                        f.seek(start2)
                        version = f.read(4)[0]
                        ct = struct.unpack(">Q", f.read(8))[0] if version == 1 \
                            else struct.unpack(">I", f.read(4))[0]
                        if ct:
                            dt = datetime.fromtimestamp(ct - 2082844800)  # secondes depuis 1904
                            return dt if _valid(dt) else None
                return None
    except (OSError, struct.error, IndexError, ValueError, OverflowError):
        pass
    return None


RE_DATETIME = re.compile(r"(?<!\d)((?:19|20)\d\d)[-_.]?(\d\d)[-_.]?(\d\d)[-_ T.]?(\d\d)[-_.:h]?(\d\d)[-_.:m]?(\d\d)")
RE_DATE = re.compile(r"(?<!\d)((?:19|20)\d\d)[-_.]?(\d\d)[-_.]?(\d\d)(?!\d)")
RE_EPOCH = re.compile(r"(?<!\d)(1[3-9]\d{8})(\d{3})?(?!\d)")  # ex. FB_IMG_1712345678901.jpg


def name_date(name):
    """(date, heure connue ?) d'après le nom du fichier, ou (None, False)."""
    for rx, has_time in ((RE_DATETIME, True), (RE_DATE, False)):
        for m in rx.finditer(name):
            try:
                dt = datetime(*map(int, m.groups()))
            except ValueError:
                continue
            if _valid(dt):
                return dt, has_time
    m = RE_EPOCH.search(name)
    if m:
        dt = datetime.fromtimestamp(int(m.group(1)))
        if _valid(dt):
            return dt, True
    return None, False


def origin(rel):
    low = rel.lower().replace("\\", "/")
    name = os.path.basename(low)
    if "screenshot" in low or "capture" in name or "screenrecord" in low or "screen_record" in low:
        return "screenshot"
    if "whatsapp" in low or re.search(r"-wa\d{4}", name):
        return "whatsapp"
    if "/dcim/" in f"/{low}" or re.match(r"(img|vid|pxl|mvimg|pano|dsc|p)_?\d{8}", name):
        return "camera"
    return "other"


def describe(path, rel):
    """Item pour un fichier, ou None si ce n'est ni une photo ni une vidéo."""
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    video = ext in VIDEO_EXT
    if not video and ext not in PHOTO_EXT:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    dt, has_time, how = None, True, ""
    if ext in (".jpg", ".jpeg"):
        dt, how = exif_date(path), "exif"
    if not dt:
        dt, has_time = name_date(name)
        how = "name"
    if not dt and video:
        dt, has_time, how = video_date(path), True, "video"
    if not dt:
        dt, has_time, how = datetime.fromtimestamp(st.st_mtime), True, "mtime"
    return Item(path, st.st_size, dt, has_time, video, origin(rel), how)


# ------------------------------------------------------------ analyse
def _inside(path, folder):
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def scan(sources, exclude, progress, cancel, find_dupes=True):
    """Liste les photos/vidéos des dossiers sources (sans les dossiers cachés, la corbeille de
    synchronisation, les doublons mis de côté ni le dossier de destination).
    find_dupes : marque (dup=True) les copies identiques, sauf le meilleur exemplaire."""
    exclude = os.path.realpath(exclude) if exclude else None
    files, seen = [], set()
    for src in sources:
        for base, dirs, names in os.walk(src):
            if cancel():
                return []
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (TRASH, DUPES_DIR)
                       and not (exclude and _inside(os.path.realpath(os.path.join(base, d)), exclude))]
            for n in names:
                full = os.path.join(base, n)
                real = os.path.realpath(full)
                if n.startswith(".") or real in seen:  # .trashed-…, .pending-…, doublons de sources
                    continue
                seen.add(real)
                files.append((full, os.path.relpath(full, os.path.dirname(src.rstrip(os.sep)))))
    items = []
    span = 85 if find_dupes else 100
    for i, (full, rel) in enumerate(files):
        if cancel():
            return []
        it = describe(full, rel)
        if it:
            items.append(it)
        if i % 50 == 0:
            progress(i * span / max(len(files), 1))
    if find_dupes:
        by_path = {it.path: it for it in items}
        for g in dupes.exact_groups([(it.path, it.size) for it in items],
                                    lambda v: progress(85 + v * 0.15), cancel):
            keep = dupes.keeper(g)
            for p in g:
                by_path[p].dup = p != keep
    progress(100)
    return items


# ------------------------------------------------------------ plan de rangement
def _event_name(first, last):
    if first.date() == last.date():
        return f"{first:%Y-%m-%d}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{first:%Y-%m-%d} au {last:%d}"
    if first.year == last.year:
        return f"{first:%Y-%m-%d} au {last:%m-%d}"
    return f"{first:%Y-%m-%d} au {last:%Y-%m-%d}"


def events(items, gap_hours, min_count):
    """{id(item): dossier} : une série de photos sans pause de plus de gap_hours forme un
    événement ; les séries trop courtes vont dans « AAAA-MM divers »."""
    out = {}
    group = []

    def flush():
        if not group:
            return
        first, last = group[0].date, group[-1].date
        if len(group) >= min_count:
            folder = os.path.join(str(first.year), _event_name(first, last))
            for it in group:
                out[id(it)] = folder
        else:
            for it in group:
                out[id(it)] = os.path.join(str(it.date.year), f"{it.date:%Y-%m} divers")

    def when(it):  # jour seul connu (ex. WhatsApp) : compté à midi
        return it.date if it.has_time else it.date.replace(hour=12)

    for it in sorted(items, key=when):
        if group and (when(it) - when(group[-1])).total_seconds() > gap_hours * 3600:
            flush()
            group = []
        group.append(it)
    flush()
    return out


def date_folder(dt, structure):
    if structure == "year":
        return str(dt.year)
    if structure == "month":
        return f"{dt:%Y-%m} {MONTHS[dt.month - 1]}"
    if structure == "year_day":
        return os.path.join(str(dt.year), f"{dt:%Y-%m-%d}")
    return os.path.join(str(dt.year), f"{dt:%m} - {MONTHS[dt.month - 1]}")


def new_name(it):
    name = os.path.basename(it.path)
    ext = os.path.splitext(name)[1].lower()
    if it.has_time:
        return f"{it.date:%Y-%m-%d_%H-%M-%S}{ext}"
    return f"{it.date:%Y-%m-%d}_{name}"


def plan(items, structure="year_month", videos_apart=False, by_origin=False, rename=False,
         gap_hours=8, min_count=5, skip_dupes=False):
    """[(item, chemin relatif de destination)], trié par date."""
    if skip_dupes:
        items = [it for it in items if not it.dup]
    ev = events(items, gap_hours, min_count) if structure == "event" else {}
    out = []
    for it in sorted(items, key=lambda x: x.date):
        parts = []
        if videos_apart:
            parts.append("Vidéos" if it.video else "Photos")
        if by_origin:
            parts.append(ORIGINS[it.origin])
        parts.append(ev[id(it)] if structure == "event" else date_folder(it.date, structure))
        parts.append(new_name(it) if rename else os.path.basename(it.path))
        out.append((it, os.path.join(*parts)))
    return out


# ------------------------------------------------------------ rangement
def apply(steps, dest_root, mode, log, progress, cancel, sources=(), step=lambda t: None):
    """mode : link (liens physiques, copie si impossible), copy ou move."""
    import time
    done = skipped = errors = 0
    link_ok = mode == "link"
    verb_ing = {"link": "Rangement", "copy": "Copie", "move": "Déplacement"}[mode]
    total = len(steps)
    shown = 0.0
    for i, (it, rel) in enumerate(steps):
        now = time.monotonic()
        if now - shown > 0.2 or i == total - 1:  # texte mis à jour 5 fois par seconde au plus
            shown = now
            progress(i * 100 / max(total, 1))
            step(f"{verb_ing} des photos : {i + 1} / {total} fichiers")
        if cancel():
            log("Annulé.")
            break
        dest = os.path.join(dest_root, rel)
        if already_there(dest, it.size):
            skipped += 1
            continue
        dest = unique(dest)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if mode == "move":
                shutil.move(it.path, dest)
            elif link_ok:
                try:
                    os.link(it.path, dest)
                except OSError as e:
                    link_ok = False
                    log(f"Liens physiques impossibles ici ({e.strerror}) : les photos sont copiées.")
                    shutil.copy2(it.path, dest)
            else:
                shutil.copy2(it.path, dest)
            done += 1
        except OSError as e:
            errors += 1
            log(f"  Erreur : {it.path} : {e}")
    if mode == "move":
        for src in sources:  # dossiers vidés par le déplacement
            for base, _, _ in sorted(os.walk(src), key=lambda w: -len(w[0])):
                if base != src:
                    try:
                        os.rmdir(base)
                    except OSError:
                        pass
    progress(100)
    verb = {"link": "rangés", "copy": "copiés", "move": "déplacés"}[mode]
    log(f"Terminé : {done} {verb}, {skipped} déjà présents, {errors} erreurs.")
    return {"done": done, "skipped": skipped, "errors": errors}
