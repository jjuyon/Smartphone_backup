"""Fabrique l'icône Windows (.ico, plusieurs tailles) à partir de smartphone_backup/icons/app.svg.

    python packaging/windows/make_icon.py build/app.ico
"""
import io
import os
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter, Qt
from PySide6.QtSvg import QSvgRenderer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SVG = os.path.join(ROOT, "smartphone_backup", "icons", "app.svg")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
app = QGuiApplication([])
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
QSvgRenderer(SVG).render(p)
p.end()
buf = QBuffer()
buf.open(QIODevice.WriteOnly)
img.save(buf, "PNG")
out = sys.argv[1]
os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
Image.open(io.BytesIO(bytes(buf.data()))).save(
    out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icône :", out)
