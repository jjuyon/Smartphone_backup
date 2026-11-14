#!/usr/bin/env bash
# Installe Synchro Smartphone (depuis les sources) pour l'utilisateur courant :
#   - bibliothèques système dont Qt a besoin pour démarrer (selon la distribution)
#   - environnement Python (.venv) avec PySide6 et mutagen
#   - lanceur dans le menu des applications
# Les outils des téléphones (adb, libimobiledevice…) s'installent ensuite depuis l'appli.
# Alternative sans installation : l'AppImage (voir build_appimage.sh).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# ------------------------------------------------------------ paquets système
if command -v apt-get >/dev/null; then PM=apt
elif command -v dnf >/dev/null; then PM=dnf
elif command -v pacman >/dev/null; then PM=pacman
else PM=""; fi

need=()
# venv : paquet séparé sur Debian/Ubuntu
if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    case $PM in apt) need+=(python3-venv) ;; *) need+=("python3 (module venv)") ;; esac
fi
# Qt 6 (≥ 6.5) exige libxcb-cursor pour démarrer sous X11
if ! ldconfig -p 2>/dev/null | grep -q "libxcb-cursor.so.0"; then
    case $PM in apt) need+=(libxcb-cursor0) ;; dnf|pacman) need+=(xcb-util-cursor) ;; *) need+=(libxcb-cursor) ;; esac
fi

if [ ${#need[@]} -gt 0 ]; then
    echo "== Paquets système nécessaires : ${need[*]}"
    case $PM in
        apt) cmd=(sudo apt-get install -y "${need[@]}") ;;
        dnf) cmd=(sudo dnf install -y "${need[@]}") ;;
        pacman) cmd=(sudo pacman -S --needed --noconfirm "${need[@]}") ;;
        *) echo "Installez-les avec le gestionnaire de paquets de votre distribution, puis relancez."; exit 1 ;;
    esac
    read -r -p "Lancer « ${cmd[*]} » ? [O/n] " rep
    case "$rep" in [nN]*) echo "Abandon."; exit 1 ;; esac
    [ "$PM" = apt ] && sudo apt-get update
    "${cmd[@]}"
fi

# ------------------------------------------------------------ Python
echo "== Environnement Python =="
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

cat > "$DIR/lancer.sh" <<EOF
#!/usr/bin/env bash
exec "$DIR/.venv/bin/python" "$DIR/synchro_smartphone.py" "\$@"
EOF
chmod +x "$DIR/lancer.sh"

# ------------------------------------------------------------ menu
echo "== Raccourci dans le menu =="
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/synchro-smartphone.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Synchro Smartphone
Comment=Sauvegarder un iPhone ou un Android
Exec=$DIR/lancer.sh
Icon=$DIR/synchro/icons/app.svg
Terminal=false
Categories=Utility;
EOF

echo
echo "Terminé. Lancez « Synchro Smartphone » depuis le menu, ou : $DIR/lancer.sh"
echo "Les outils des téléphones (adb, libimobiledevice…) s'installent depuis l'appli"
echo "(bandeau « Aide à l'installation » sur l'écran d'accueil)."
