"""Rangement des photos : dates, classements, liens / copie / déplacement, doublons."""
import os
import struct
from datetime import datetime

from smartphone_backup.core import dupes, photos, system


def jpeg_with_exif(dt):
    s = dt.encode() + b"\0"
    t = b"II*\0" + struct.pack("<I", 8)
    t += struct.pack("<H", 1) + struct.pack("<HHII", 0x8769, 4, 1, 26) + struct.pack("<I", 0)
    t += struct.pack("<H", 1) + struct.pack("<HHII", 0x9003, 2, len(s), 44) + struct.pack("<I", 0) + s
    app1 = b"Exif\0\0" + t
    return b"\xff\xd8\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xda\0\x02\xff\xd9"


def mp4(ts):
    ct = int(ts) + 2082844800
    mvhd = b"\0\0\0\0" + struct.pack(">II", ct, ct) + b"\0" * 88
    mvhd = struct.pack(">I", len(mvhd) + 8) + b"mvhd" + mvhd
    return struct.pack(">I", 16) + b"ftypisom\0\0\0\0" + struct.pack(">I", len(mvhd) + 8) + b"moov" + mvhd


def write(path, data, mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def test_dates(tmp_path):
    a = write(tmp_path / "DCIM" / "IMG_1.jpg", jpeg_with_exif("2023:07:14 18:05:09"))
    b = write(tmp_path / "x" / "PXL_20240315_143205123.jpg", b"x")
    c = write(tmp_path / "x" / "IMG-20240316-WA0001.jpg", b"y")
    d = write(tmp_path / "x" / "film.mp4", mp4(datetime(2022, 12, 25, 10).timestamp()))
    e = write(tmp_path / "x" / "divers.png", b"z", datetime(2021, 5, 1, 12).timestamp())
    got = {os.path.basename(i.path): (i.date, i.how) for i in photos.scan([str(tmp_path)], None,
                                                                          lambda v: None, lambda: False)}
    assert got["IMG_1.jpg"] == (datetime(2023, 7, 14, 18, 5, 9), "exif")
    assert got["PXL_20240315_143205123.jpg"] == (datetime(2024, 3, 15, 14, 32, 5), "name")
    assert got["IMG-20240316-WA0001.jpg"][0].date() == datetime(2024, 3, 16).date()
    assert got["film.mp4"] == (datetime(2022, 12, 25, 10), "video")
    assert got["divers.png"] == (datetime(2021, 5, 1, 12), "mtime")
    assert all(os.path.exists(p) for p in (a, b, c, d, e))


def test_classements_et_relance(tmp_path):
    src = tmp_path / "src"
    for i, day in enumerate((1, 1, 2, 20)):
        write(src / f"IMG_202403{day:02d}_10{i:02d}00.jpg", bytes([i]) * 100)
    items = photos.scan([str(src)], None, lambda v: None, lambda: False)
    rels = {st: sorted(r.replace(os.sep, "/") for _, r in photos.plan(items, st, min_count=2, gap_hours=30))
            for st in photos.STRUCTURES}
    assert rels["year_month"][0] == "2024/03 - Mars/IMG_20240301_100000.jpg"
    assert rels["year"][0].startswith("2024/IMG_")
    assert rels["month"][0].startswith("2024-03 Mars/")
    assert rels["year_day"][-1].startswith("2024/2024-03-20/")
    assert "2024/2024-03-01 au 02/IMG_20240301_100000.jpg" in rels["event"]
    assert "2024/2024-03 divers/IMG_20240320_100300.jpg" in rels["event"]
    dest = tmp_path / "rangées"
    r = photos.apply(photos.plan(items), str(dest), "link", lambda m: None, lambda v: None, lambda: False)
    assert r["done"] == 4
    r = photos.apply(photos.plan(items), str(dest), "link", lambda m: None, lambda v: None, lambda: False)
    assert r == {"done": 0, "skipped": 4, "errors": 0}


def test_deplacement_et_doublons(tmp_path):
    src = tmp_path / "src"
    write(src / "DCIM" / "IMG_20240101_100000.jpg", b"meme photo")
    write(src / "WhatsApp" / "IMG-20240101-WA0001.jpg", b"meme photo")
    write(src / "DCIM" / "IMG_20240102_100000.jpg", b"autre")
    items = photos.scan([str(src)], None, lambda v: None, lambda: False)
    assert sum(i.dup for i in items) == 1
    kept = [i for i in items if not i.dup]
    assert any("DCIM" in i.path and "20240101" in i.path for i in kept)  # l'original est gardé
    steps = photos.plan(items, skip_dupes=True)
    assert len(steps) == 2
    dest = tmp_path / "dest"
    photos.apply(steps, str(dest), "move", lambda m: None, lambda v: None, lambda: False, [str(src)])
    assert sorted(os.listdir(dest / "2024")) == ["01 - Janvier"]
    assert not (src / "DCIM").exists()  # dossier vidé puis supprimé


def test_doublons_identiques_et_meilleur_exemplaire(tmp_path):
    a = write(tmp_path / "DCIM" / "Camera" / "IMG_1.jpg", b"x" * 70000)
    b = write(tmp_path / "Download" / "IMG_1 (1).jpg", b"x" * 70000)
    c = write(tmp_path / "Download" / "autre.jpg", b"x" * 69999 + b"y")
    groups = dupes.exact_groups([(str(p), os.path.getsize(p)) for p in (a, b, c)])
    assert [sorted(g) for g in groups] == [sorted([str(a), str(b)])]
    assert dupes.keeper(groups[0]) == str(a)


def test_photos_ressemblantes_avec_tolerance():
    base = 0x5A5A_F0F0_1234_ABCD
    hashes = {"original": base, "recompressee": base ^ 0b101, "autre": base ^ 0xFFFF_0000_0000}
    groups = dupes.similar_groups(list(hashes), hashes.get)
    assert [sorted(g) for g in groups] == [["original", "recompressee"]]


def test_noms_windows():
    assert system.safe_name("Screenshot 12:30.png", windows=True) == "Screenshot 12_30.png"
    assert system.safe_name("CON.jpg", windows=True) == "_CON.jpg"
    assert system.safe_name("dossier. ", windows=True) == "dossier"
    assert system.safe_name("a:b", windows=False) == "a:b"


def test_exact_groups_methods(tmp_path):
    """Même taille, même début et même fin mais milieu différent : seule la somme de contrôle les distingue."""
    from smartphone_backup.core import dupes
    head, tail = b"A" * 200_000, b"Z" * 200_000
    a, b, c = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "c.mp4"
    a.write_bytes(head + b"1" * 100_000 + tail)
    b.write_bytes(head + b"2" * 100_000 + tail)
    c.write_bytes(a.read_bytes())
    files = [(str(p), os.path.getsize(p)) for p in (a, b, c)]
    assert sorted(map(sorted, dupes.exact_groups(files))) == [sorted([str(a), str(c)])]
    assert sorted(map(sorted, dupes.exact_groups(files, method="fast"))) == [sorted(map(str, (a, b, c)))]
    assert dupes.exact_groups(files, cancel=lambda: True) == []
