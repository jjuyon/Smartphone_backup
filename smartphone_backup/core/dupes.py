"""Détection des photos et vidéos en double.

- identiques : même contenu. Seuls les fichiers de même taille sont lus, puis comparés soit par
  somme de contrôle du fichier entier (sûr), soit par le début et la fin du fichier (rapide) ;
- ressemblantes : même image redimensionnée ou recompressée (ex. photo renvoyée par WhatsApp),
  repérée par une empreinte visuelle fournie par l'interface (lecture des images avec Qt).
"""
import hashlib
import os
import re

PARTIAL = 64 * 1024


CHUNK = 1 << 20


class Cancelled(Exception):
    pass


def file_hash(path, limit=None, cancel=lambda: False, read=lambda n: None):
    """Somme de contrôle BLAKE2 du fichier (ou de ses `limit` premiers octets).
    read(n) est appelé après chaque bloc lu (progression) ; cancel() interrompt la lecture."""
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        if limit:
            h.update(f.read(limit))
        else:
            for chunk in iter(lambda: f.read(CHUNK), b""):
                if cancel():
                    raise Cancelled
                h.update(chunk)
                read(len(chunk))
    return h.hexdigest()


def ends_hash(path):
    """Empreinte rapide : taille + début + fin du fichier."""
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        h.update(f.read(PARTIAL))
        size = os.fstat(f.fileno()).st_size
        if size > 2 * PARTIAL:
            f.seek(size - PARTIAL)
            h.update(f.read(PARTIAL))
    return h.hexdigest()


def _split(groups, key, cancel, done):
    """Redécoupe chaque groupe selon key(path) ; ne garde que les sous-groupes d'au moins 2.
    done(path) est appelé après chaque fichier."""
    out = []
    for g in groups:
        sub = {}
        for p in g:
            if cancel():
                raise Cancelled
            try:
                sub.setdefault(key(p), []).append(p)
            except OSError:
                pass
            done(p)
        out += [s for s in sub.values() if len(s) > 1]
    return out


METHODS = {"checksum": "Somme de contrôle du fichier entier (sûr)",
           "fast": "Rapide : taille + début et fin du fichier"}


def exact_groups(files, progress=lambda v: None, cancel=lambda: False, method="checksum",
                 step=lambda t: None):
    """files : [(chemin, taille)] → [[chemins identiques], …]. Renvoie [] si annulé."""
    by_size = {}
    for path, size in files:
        if size > 0:
            by_size.setdefault(size, []).append(path)
    groups = [g for g in by_size.values() if len(g) > 1]
    sizes = {p: s for p, s in files}
    try:
        n = sum(len(g) for g in groups)
        count = [0]

        def one(_p, a=0, b=100):
            count[0] += 1
            if count[0] % 10 == 0:
                progress(a + (b - a) * count[0] / max(n, 1))

        if method == "fast":
            step(f"Comparaison rapide de {n} fichiers de même taille (début et fin)…")
            groups = _split(groups, ends_hash, cancel, one)
        else:
            # écarte d'abord, sans tout lire, les fichiers de même taille mais différents dès le début
            step(f"Comparaison de {n} fichiers de même taille…")
            groups = _split(groups, lambda p: file_hash(p, PARTIAL), cancel, lambda p: one(p, 0, 10))
            small = [g for g in groups if sizes[g[0]] <= PARTIAL]
            big = [g for g in groups if sizes[g[0]] > PARTIAL]
            total = sum(sizes[p] for g in big for p in g) or 1
            read = [0]

            def advance(k):
                read[0] += k
                progress(10 + 90 * read[0] / total)

            step(f"Calcul des sommes de contrôle ({sum(len(g) for g in big)} fichiers, "
                 f"{total / 1e9:.1f} Go)…".replace(".", ",", 1))
            groups = small + _split(big, lambda p: file_hash(p, cancel=cancel, read=advance),
                                    cancel, lambda p: None)
    except Cancelled:
        return []
    progress(100)
    return groups


MAX_DIST = 5      # bits différents tolérés sur 64 (décodage, recompression)
CHUNKS = MAX_DIST + 1  # principe des tiroirs : deux empreintes proches ont un morceau identique


def similar_groups(paths, image_hash, progress=lambda v: None, cancel=lambda: False):
    """Photos à l'empreinte visuelle presque identique. image_hash(path) → int ou None."""
    hashes = []
    for i, p in enumerate(paths):
        if cancel():
            return []
        h = image_hash(p)
        # empreintes presque uniformes (photo noire, ciel blanc…) : trop de faux doublons
        if h is not None and 6 <= bin(h).count("1") <= 58:
            hashes.append((p, h))
        if i % 10 == 0:
            progress(i * 95 / max(len(paths), 1))
    # index par morceau d'empreinte, puis comparaison des seuls candidats
    width = -(-64 // CHUNKS)
    index = {}
    for n, (_, h) in enumerate(hashes):
        for c in range(CHUNKS):
            index.setdefault((c, (h >> (c * width)) & ((1 << width) - 1)), []).append(n)
    parent = list(range(len(hashes)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for bucket in index.values():
        if cancel():
            return []
        for i, a in enumerate(bucket):
            for b in bucket[i + 1:]:
                if bin(hashes[a][1] ^ hashes[b][1]).count("1") <= MAX_DIST:
                    parent[find(a)] = find(b)
    groups = {}
    for n, (p, _) in enumerate(hashes):
        groups.setdefault(find(n), []).append(p)
    progress(100)
    return [g for g in groups.values() if len(g) > 1]


# ------------------------------------------------------------ quel exemplaire garder
SECONDARY = re.compile(r"whatsapp|telegram|download|téléchargement|sent|envoy|received|reçu|messenger|"
                       r"facebook|instagram|snapchat|signal|_doublons|copie|copy", re.I)
COPY_NAME = re.compile(r"(\(\d+\)|[ _-](copie|copy|\d{1,2}))\.[^.]+$", re.I)


def keep_score(path, size=0):
    """Plus petit = meilleur exemplaire à garder."""
    low = path.lower()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    return (
        -size,                                       # la plus grande (ressemblantes : meilleure qualité)
        0 if "/dcim/" in low or "/camera/" in low else 1,
        1 if SECONDARY.search(low) else 0,
        1 if COPY_NAME.search(os.path.basename(path)) else 0,  # « photo (1).jpg », « photo_copie.jpg »
        mtime,                                       # la plus ancienne
        len(path),
    )


def keeper(group):
    sizes = {}
    for p in group:
        try:
            sizes[p] = os.path.getsize(p)
        except OSError:
            sizes[p] = 0
    return min(group, key=lambda p: keep_score(p, sizes[p]))
