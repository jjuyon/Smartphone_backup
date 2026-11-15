import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def fake_phone(tmp_path, monkeypatch):
    """Faux téléphone + faux adb placé en tête du PATH. Renvoie le dossier « /sdcard »."""
    phone = tmp_path / "phone"
    phone.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = os.path.join(ROOT, "tests", "fake_adb.py")
    if os.name == "nt":
        (bindir / "adb.bat").write_text(f'@"{sys.executable}" "{script}" %*\n')
    else:
        launcher = bindir / "adb"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(0o755)
    monkeypatch.setenv("FAKEPHONE", str(phone))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return phone


def put(phone, rel, data, mtime=None):
    """Crée un fichier sur le faux téléphone (rel avec « / », noms interdits sous Windows permis)."""
    def enc(name):  # même encodage que fake_adb.py
        return "".join(f"%{ord(c):02X}" if c in ':?*"<>|%' else c for c in name)
    parts = [enc(p) for p in rel.split("/")]
    path = os.path.join(phone, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path
