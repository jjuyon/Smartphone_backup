"""Compatibilité Qt 6 (PySide6) / Qt 5 (PySide2).

PySide6 installé par pip exige un processeur récent (x86-64-v2 : SSE4.2, POPCNT). Sur les
machines plus anciennes (ex. Core 2 Duo), l'appli tourne avec le PySide2 de la distribution.
Tous les modules de l'interface importent Qt depuis ici.
"""
try:
    from PySide6.QtCore import *  # noqa: F401,F403
    from PySide6.QtGui import *  # noqa: F401,F403
    from PySide6.QtWidgets import *  # noqa: F401,F403
    QT6 = True
except ImportError:
    from PySide2.QtCore import *  # noqa: F401,F403
    from PySide2.QtGui import *  # noqa: F401,F403
    from PySide2.QtWidgets import *  # noqa: F401,F403
    QT6 = False
    # noms Qt 6 utilisés par l'appli
    for _cls in (QApplication, QDialog, QMenu):  # noqa: F405
        _cls.exec = _cls.exec_


def event_pos(e):
    """Position d'un événement souris (QPoint)."""
    return e.position().toPoint() if QT6 else e.pos()


def translations_path():
    if QT6:
        return QLibraryInfo.path(QLibraryInfo.TranslationsPath)  # noqa: F405
    return QLibraryInfo.location(QLibraryInfo.TranslationsPath)  # noqa: F405


def to_bytes(qbytearray):
    return bytes(qbytearray.data())


def before_app():
    """Réglages à faire avant de créer QApplication (Qt 5 : écrans haute densité)."""
    if not QT6:
        QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)  # noqa: F405
        QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)  # noqa: F405
