"""Faux adb pour les tests : le « téléphone » est le dossier $FAKEPHONE (= /sdcard).

Les caractères interdits sous Windows sont stockés encodés sur le disque (%3A pour « : »…), ce qui
permet de simuler, sur tous les systèmes, un téléphone dont des fichiers ont des noms comme
« Screenshot 12:30.png ».
"""
import os
import re
import sys
import time

PH = os.environ["FAKEPHONE"]
sys.stdout.reconfigure(encoding="utf-8")  # comme le vrai adb, y compris sous Windows
BAD = ':?*"<>|'


def enc(name):
    return "".join(f"%{ord(c):02X}" if c in BAD or c == "%" else c for c in name)


def dec(name):
    return re.sub(r"%([0-9A-F]{2})", lambda m: chr(int(m.group(1), 16)), name)


def to_disk(phone_path):
    if not phone_path.startswith("/sdcard"):
        return None
    parts = [enc(p) for p in phone_path[len("/sdcard"):].split("/") if p]
    return os.path.join(PH, *parts)


def to_phone(disk_path):
    rel = os.path.relpath(disk_path, PH).replace(os.sep, "/")
    return "/sdcard/" + "/".join(dec(p) for p in rel.split("/"))


args = sys.argv[1:]
if args[:1] == ["-s"]:
    args = args[2:]
if not args:
    sys.exit(1)
if args[0] == "shell":
    m = re.search(r"find '([^']*)'", args[1])
    root = to_disk(m.group(1)) if m else None
    if not root or not os.path.isdir(root):
        print(f"find: {m.group(1) if m else '?'}: No such file or directory")
        sys.exit(1)
    for base, _, files in os.walk(root):
        for f in files:
            full = os.path.join(base, f)
            st = os.stat(full)
            print(f"{st.st_size}|{int(st.st_mtime)}|{to_phone(full)}")
elif args[0] == "pull":
    srcs = [a for a in args[1:-1] if a != "-a"]
    dest = args[-1]
    for s in srcs:
        src = to_disk(s)
        target = os.path.join(dest, s.rsplit("/", 1)[1]) if os.path.isdir(dest) else dest
        with open(src, "rb") as fi, open(target, "wb") as fo:
            while True:
                chunk = fi.read(256 * 1024)
                if not chunk:
                    break
                fo.write(chunk)
                time.sleep(0.001)
        st = os.stat(src)
        os.utime(target, (st.st_mtime, st.st_mtime))
    print(f"{len(srcs)} files pulled.")
elif args[0] == "devices":
    print("List of devices attached")
elif args[0] == "kill-server":
    pass
