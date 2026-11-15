#!/usr/bin/env bash
# Fabrique dist/Smartphone_Backup-x86_64.AppImage (un seul fichier, sans installation).
#
#   ./build_appimage.sh            (VERSION=1.2.3 ./build_appimage.sh pour fixer la version)
#
# Étapes : venv de build -> PyInstaller (Python + Qt + appli) -> AppDir -> appimagetool.
# Note : l'AppImage fonctionne sur les distributions dont la glibc est au moins aussi récente
# que celle de la machine qui la fabrique (construire sur la distribution la plus ancienne visée).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD="$DIR/build"
APPDIR="$BUILD/AppDir"
ARCH="$(uname -m)"
OUT="$DIR/dist/Smartphone_Backup-$ARCH.AppImage"
TOOL="$BUILD/appimagetool-$ARCH.AppImage"

echo "== Environnement de build =="
[ -x "$BUILD/venv/bin/python" ] || python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install -q --upgrade pip
"$BUILD/venv/bin/pip" install -q -r "$DIR/requirements.txt" pyinstaller

if [ -n "${VERSION:-}" ]; then
    echo "VERSION = \"$VERSION\"" > "$DIR/smartphone_backup/_build.py"
fi

echo "== PyInstaller =="
rm -rf "$BUILD/pyi" "$BUILD/work" "$APPDIR"
"$BUILD/venv/bin/pyinstaller" --noconfirm --clean --log-level WARN \
    --name smartphone-backup --windowed \
    --distpath "$BUILD/pyi" --workpath "$BUILD/work" --specpath "$BUILD" \
    --paths "$DIR" \
    --add-data "$DIR/smartphone_backup/icons:smartphone_backup/icons" \
    --exclude-module tkinter \
    "$DIR/main.py"

echo "== AppDir =="
mkdir -p "$APPDIR/usr/bin"
cp -a "$BUILD/pyi/smartphone-backup/." "$APPDIR/usr/bin/"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/smartphone-backup" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/smartphone-backup.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Smartphone Backup
Comment=Sauvegarder un iPhone ou un Android
Exec=smartphone-backup
Icon=smartphone-backup
Terminal=false
Categories=Utility;
EOF
# icône PNG 256 px à partir du SVG
QT_QPA_PLATFORM=offscreen "$BUILD/venv/bin/python" - "$DIR/smartphone_backup/icons/app.svg" "$APPDIR/smartphone-backup.png" <<'EOF'
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
ln -sf smartphone-backup.png "$APPDIR/.DirIcon"

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
