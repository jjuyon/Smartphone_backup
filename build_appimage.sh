#!/usr/bin/env bash
# Fabrique dist/Synchro_Smartphone-x86_64.AppImage (un seul fichier, sans installation).
#
#   ./build_appimage.sh
#
# Étapes : venv de build -> PyInstaller (Python + Qt + appli) -> AppDir -> appimagetool.
# Note : l'AppImage fonctionne sur les distributions dont la glibc est au moins aussi récente
# que celle de la machine qui la fabrique (construire sur la distribution la plus ancienne visée).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD="$DIR/build"
APPDIR="$BUILD/AppDir"
ARCH="$(uname -m)"
OUT="$DIR/dist/Synchro_Smartphone-$ARCH.AppImage"
TOOL="$BUILD/appimagetool-$ARCH.AppImage"

echo "== Environnement de build =="
[ -x "$BUILD/venv/bin/python" ] || python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install -q --upgrade pip
"$BUILD/venv/bin/pip" install -q -r "$DIR/requirements.txt" pyinstaller

echo "== PyInstaller =="
rm -rf "$BUILD/pyi" "$BUILD/work" "$APPDIR"
"$BUILD/venv/bin/pyinstaller" --noconfirm --clean --log-level WARN \
    --name synchro-smartphone --windowed \
    --distpath "$BUILD/pyi" --workpath "$BUILD/work" --specpath "$BUILD" \
    --paths "$DIR" \
    --add-data "$DIR/synchro/icons:synchro/icons" \
    --exclude-module tkinter \
    "$DIR/synchro_smartphone.py"

echo "== AppDir =="
mkdir -p "$APPDIR/usr/bin"
cp -a "$BUILD/pyi/synchro-smartphone/." "$APPDIR/usr/bin/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/synchro-smartphone" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/synchro-smartphone.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Synchro Smartphone
Comment=Sauvegarder un iPhone ou un Android
Exec=synchro-smartphone
Icon=synchro-smartphone
Terminal=false
Categories=Utility;
EOF
# icône PNG 256 px à partir du SVG
QT_QPA_PLATFORM=offscreen "$BUILD/venv/bin/python" - "$DIR/synchro/icons/app.svg" "$APPDIR/synchro-smartphone.png" <<'EOF'
import sys
from PySide6.QtGui import QGuiApplication, QImage, QPainter, Qt
from PySide6.QtSvg import QSvgRenderer
app = QGuiApplication([])
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
QSvgRenderer(sys.argv[1]).render(p)
p.end()
img.save(sys.argv[2])
EOF
ln -sf synchro-smartphone.png "$APPDIR/.DirIcon"

echo "== appimagetool =="
if [ ! -x "$TOOL" ]; then
    curl -fL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
mkdir -p "$DIR/dist"
ARCH="$ARCH" APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$OUT"
echo
echo "AppImage prête : $OUT"
