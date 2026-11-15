#!/usr/bin/env python3
"""Smartphone Backup : sauvegarde / synchronisation d'un iPhone ou d'un Android sous Linux."""
import os
import sys

if getattr(sys, "frozen", False):
    # Version empaquetée (AppImage / PyInstaller) : les programmes externes lancés par l'appli
    # (adb, idevicebackup2, pkexec, udisksctl…) doivent utiliser les bibliothèques du système,
    # pas celles embarquées dans l'appli.
    orig = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig:
        os.environ["LD_LIBRARY_PATH"] = orig
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from smartphone_backup.ui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
