"""Démarrage de l'interface (hors écran) et arrêt des processus enfants."""
import subprocess
import sys
import time

import pytest

from smartphone_backup.core import procs


@pytest.fixture(scope="module")
def app():
    from smartphone_backup.ui.common import STYLE, dark_palette
    from smartphone_backup.ui.qt import QApplication
    a = QApplication.instance() or QApplication(sys.argv)
    a.setStyle("Fusion")
    a.setPalette(dark_palette())
    a.setStyleSheet(STYLE)
    return a


def test_ecrans(app, tmp_path):
    from smartphone_backup.ui.app import MainWindow
    from smartphone_backup.ui.dupes_dialog import DuplicatesDialog
    from smartphone_backup.ui.folder_picker import FolderPicker
    from smartphone_backup.ui.photo_sort_dialog import PhotoSortDialog
    from smartphone_backup.ui.prereqs_dialog import PrereqDialog
    w = MainWindow()
    w.show()
    for key in ("iphone", "android", "photos"):
        w.open_page(key)
        app.processEvents()
    for d in (FolderPicker(w, "Test", str(tmp_path)), PrereqDialog(w, None),
              PhotoSortDialog(w, str(tmp_path)), DuplicatesDialog(w, [str(tmp_path)])):
        d.show()
        app.processEvents()
        if hasattr(d, "stop_scan"):
            d.stop_scan()
        d.deleteLater()
    w.shutdown()
    w.deleteLater()
    app.processEvents()


def test_arret_des_processus_enfants():
    code = "import time; time.sleep(60)"
    kids = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(2)]
    time.sleep(0.3)
    names = procs.kill_children(timeout=3)
    assert len(names) >= 2
    for k in kids:
        assert k.wait(timeout=5) is not None
