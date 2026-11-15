#!/usr/bin/env bash
# Installe Smartphone Backup (depuis les sources) pour l'utilisateur courant.
#
#   ./install.sh            choix automatique
#   ./install.sh --systeme  force le Qt de la distribution (vieux processeur, ou sans pip)
#
# Deux modes :
#   - pip     : processeur récent (x86-64-v2 : SSE4.2 + POPCNT) -> venv avec PySide6 de pip
#   - systeme : processeur ancien (ex. Core 2 Duo, Mac 2008) -> PySide6 ou PySide2 de la
#               distribution, compilés pour tous les processeurs 64 bits
# Les outils des téléphones (adb, libimobiledevice…) s'installent ensuite depuis l'appli.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v apt-get >/dev/null; then PM=apt
elif command -v dnf >/dev/null; then PM=dnf
elif command -v pacman >/dev/null; then PM=pacman
else PM=""; fi

if grep -qw sse4_2 /proc/cpuinfo && grep -qw popcnt /proc/cpuinfo && [ "${1:-}" != "--systeme" ]; then
    MODE=pip
else
    MODE=systeme
fi
echo "== Mode : $MODE"
[ "$MODE" = systeme ] && [ "${1:-}" != "--systeme" ] && \
    echo "   Processeur sans SSE4.2/POPCNT : utilisation du Qt de la distribution."

# ------------------------------------------------------------ paquets système
need=()
if [ "$MODE" = pip ]; then
    # venv : paquet séparé sur Debian/Ubuntu
    if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
        case $PM in apt) need+=(python3-venv) ;; *) need+=("python3 (module venv)") ;; esac
    fi
    # Qt 6 (≥ 6.5) exige libxcb-cursor pour démarrer sous X11
    if ! ldconfig -p 2>/dev/null | grep -q "libxcb-cursor.so.0"; then
        case $PM in apt) need+=(libxcb-cursor0) ;; dnf|pacman) need+=(xcb-util-cursor) ;; *) need+=(libxcb-cursor) ;; esac
    fi
else
    case $PM in
        apt)
            if apt-cache show python3-pyside6.qtwidgets >/dev/null 2>&1; then
                need+=(python3-pyside6.qtwidgets qt6-svg-plugins qt6-translations-l10n python3-mutagen)
            else  # ex. Ubuntu 24.04 : seul PySide2 (Qt 5) est disponible
                need+=(python3-pyside2.qtwidgets libqt5svg5 qttranslations5-l10n python3-mutagen)
            fi ;;
        dnf) need+=(python3-pyside6 qt6-qtsvg qt6-qttranslations python3-mutagen) ;;
        pacman) need+=(pyside6 qt6-svg qt6-translations python-mutagen) ;;
        *) echo "Installez PySide6 (ou PySide2) et mutagen pour Python 3 avec votre gestionnaire de paquets."; exit 1 ;;
    esac
fi

if [ ${#need[@]} -gt 0 ]; then
    echo "== Paquets système : ${need[*]}"
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
if [ "$MODE" = pip ]; then
    echo "== Environnement Python =="
    python3 -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install --upgrade pip >/dev/null
    "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"
    PY="$DIR/.venv/bin/python"
else
    PY="/usr/bin/python3"
    "$PY" -c "import sys; sys.path.insert(0, '$DIR'); from smartphone_backup.ui import qt; print('   Qt', 6 if qt.QT6 else 5, 'OK')"
fi

cat > "$DIR/lancer.sh" <<EOF
#!/usr/bin/env bash
exec "$PY" "$DIR/main.py" "\$@"
EOF
chmod +x "$DIR/lancer.sh"

# ------------------------------------------------------------ menu
echo "== Raccourci dans le menu =="
APPS="$HOME/.local/share/applications"
NEW="$APPS/smartphone-backup.desktop"
mkdir -p "$APPS"
# anciens lanceurs de l'appli, quel que soit leur nom de fichier : ancien nom « Synchro
# Smartphone », ancien dossier, AppImage intégrée au menu, raccourci créé à la main…
for f in "$APPS"/*.desktop; do
    [ -f "$f" ] && [ "$f" != "$NEW" ] || continue
    if grep -qiE '^Name(\[[^]]*\])?=(Synchro Smartphone|Smartphone Backup)[[:space:]]*$' "$f" \
        || grep -qiE '^(Exec|TryExec)=.*(synchro_smartphone\.py|synchro-smartphone|Synchro_Smartphone|Smartphone_Backup)' "$f"; then
        echo "   Ancien raccourci supprimé : $f"
        rm -f "$f"
    fi
done
cat > "$NEW" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Smartphone Backup
Comment=Sauvegarder un iPhone ou un Android
Exec=$DIR/lancer.sh
Icon=$DIR/smartphone_backup/icons/app.svg
Terminal=false
Categories=Utility;
StartupWMClass=smartphone-backup
DESKTOP
chmod +x "$NEW"
echo "   $NEW -> $DIR"
# mise à jour immédiate du menu (sinon KDE peut garder l'ancienne entrée jusqu'à la reconnexion)
if command -v update-desktop-database >/dev/null; then update-desktop-database "$APPS" 2>/dev/null || true; fi
for k in kbuildsycoca6 kbuildsycoca5; do
    if command -v "$k" >/dev/null; then "$k" >/dev/null 2>&1 || true; break; fi
done
if command -v xdg-desktop-menu >/dev/null; then xdg-desktop-menu forceupdate 2>/dev/null || true; fi

echo
echo "Terminé. Lancez « Smartphone Backup » depuis le menu, ou : $DIR/lancer.sh"
echo "Les outils des téléphones (adb, libimobiledevice…) s'installent depuis l'appli"
echo "(bandeau « Aide à l'installation » sur l'écran d'accueil)."
echo "Si l'appli était épinglée (barre des tâches, favoris du menu, dock), retirez l'ancienne"
echo "icône et épinglez de nouveau « Smartphone Backup »."
