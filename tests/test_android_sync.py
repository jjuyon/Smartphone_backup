"""Sauvegarde Android avec un faux téléphone : copie par lots, reprise, noms Windows, miroir."""
import os

from smartphone_backup.core import android, system
from tests.conftest import put


def run_sync(out, mirror=False, cancel=lambda: False):
    logs = []
    r = android.sync(android.Adb("FAKE"), str(out), android.build_selection({"photos": True}, ""),
                     mirror, logs.append, lambda v: None, cancel)
    return r, logs


def test_copie_puis_rien_a_refaire(fake_phone, tmp_path):
    for i in range(90):  # plus de 2 lots
        put(fake_phone, f"DCIM/Camera/IMG_{i:03d}.jpg", os.urandom(1000 + i), mtime=1_700_000_000 + i)
    put(fake_phone, "DCIM/Camera/VID_1.mp4", os.urandom(50_000))
    out = tmp_path / "out"
    r, _ = run_sync(out)
    assert r["copied"] == 91 and r["errors"] == 0
    dest = out / "Photos et vidéos" / "DCIM" / "Camera"
    assert len(os.listdir(dest)) == 91
    assert int(os.path.getmtime(dest / "IMG_005.jpg")) == 1_700_000_005  # date conservée
    r, _ = run_sync(out)
    assert r["copied"] == 0


def test_reprise_apres_annulation(fake_phone, tmp_path):
    for i in range(120):
        put(fake_phone, f"DCIM/Camera/IMG_{i:03d}.jpg", os.urandom(2000))
    out = tmp_path / "out"
    def cancel_after_first_batch():  # annule dès que le premier lot est arrivé
        return sum(len(f) for _, _, f in os.walk(out)) >= android.BATCH_FILES
    r, logs = run_sync(out, cancel=cancel_after_first_batch)
    assert 0 < r["copied"] < 120 and r["errors"] == 0
    assert any("Annulé" in m for m in logs)
    r2, _ = run_sync(out)
    assert r["copied"] + r2["copied"] == 120 and r2["errors"] == 0


def test_noms_interdits_sous_windows(fake_phone, tmp_path, monkeypatch):
    # sous Windows « : » et « ? » sont interdits : le fichier est copié sous un nom corrigé
    monkeypatch.setattr(android, "safe_name", lambda n: system.safe_name(n, windows=True))
    monkeypatch.setattr(android, "phone_path", lambda r: system.local_rel(r, windows=True))
    put(fake_phone, "DCIM/Screenshots/Screenshot 12:30.png", b"a" * 100)
    put(fake_phone, "DCIM/Album: été?/photo.jpg", b"b" * 100)
    put(fake_phone, "DCIM/Camera/normal.jpg", b"c" * 100)
    out = tmp_path / "out"
    r, _ = run_sync(out)
    assert r["copied"] == 3 and r["errors"] == 0
    base = out / "Photos et vidéos" / "DCIM"
    assert (base / "Screenshots" / "Screenshot 12_30.png").exists()
    assert (base / "Album_ été_" / "photo.jpg").exists()
    r, _ = run_sync(out)
    assert r["copied"] == 0  # les noms corrigés sont reconnus à la sauvegarde suivante


def test_mode_miroir(fake_phone, tmp_path):
    a = put(fake_phone, "DCIM/Camera/a.jpg", b"a" * 10)
    put(fake_phone, "DCIM/Camera/b.jpg", b"b" * 10)
    out = tmp_path / "out"
    run_sync(out, mirror=True)
    os.remove(a)  # supprimée du téléphone
    r, _ = run_sync(out, mirror=True)
    assert r["removed"] == 1
    assert not (out / "Photos et vidéos" / "DCIM" / "Camera" / "a.jpg").exists()
    trash = [f for _, _, fs in os.walk(out / android.TRASH) for f in fs]
    assert trash == ["a.jpg"]


def test_recuperation_ancienne_copie_en_bloc(fake_phone, tmp_path):
    src = put(fake_phone, "DCIM/Camera/a.jpg", b"a" * 5000, mtime=1_700_000_000)
    put(fake_phone, "DCIM/Camera/b.jpg", b"b" * 5000, mtime=1_700_000_000)
    out = tmp_path / "out"
    old = out / android.STAGING / "DCIM" / "Camera"
    old.mkdir(parents=True)
    with open(src, "rb") as f:
        (old / "a.jpg").write_bytes(f.read())
    os.utime(old / "a.jpg", (1_700_000_000, 1_700_000_000))
    (old / "b.jpg").write_bytes(b"b" * 10)  # copie interrompue
    r, logs = run_sync(out)
    assert any("récupérés" in m for m in logs)
    assert r["copied"] == 1  # seul b.jpg (incomplet) est recopié
    assert not (out / android.STAGING).exists()
