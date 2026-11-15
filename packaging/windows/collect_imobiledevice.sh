#!/usr/bin/env bash
# Rassemble les outils iPhone (libimobiledevice, compilés par MSYS2) et leurs DLL pour l'appli Windows.
# À lancer dans un shell MSYS2 UCRT64 où « mingw-w64-ucrt-x86_64-libimobiledevice » est installé :
#
#   bash packaging/windows/collect_imobiledevice.sh build/imobiledevice
#
# Sous Windows, ces outils passent par le service Apple Mobile Device (application « Apple Devices »)
# pour parler à l'iPhone : iTunes n'est pas nécessaire.
set -euo pipefail
OUT="$1"
BIN=/ucrt64/bin
rm -rf "$OUT"
mkdir -p "$OUT/licences"

for t in idevicebackup2 idevice_id ideviceinfo; do
    if [ ! -f "$BIN/$t.exe" ]; then
        echo "Introuvable : $BIN/$t.exe" >&2
        ls "$BIN" | grep -i idevice >&2 || true
        exit 1
    fi
    cp "$BIN/$t.exe" "$OUT/"
done

# DLL nécessaires (celles de MSYS2 uniquement, pas celles de Windows)
for f in "$OUT"/*.exe; do
    ldd "$f" | awk '{print $3}' | grep -i "^/ucrt64/" || true
done | sort -u | while read -r dll; do
    cp "$dll" "$OUT/"
done

# licences (LGPL / GPL / OpenSSL…) : obligatoires pour redistribuer
for d in /ucrt64/share/licenses/*; do
    case "$(basename "$d")" in
        *imobiledevice*|*plist*|*usbmuxd*|*openssl*|*libssl*|*gcc*|*winpthreads*|*zlib*|*libtatsu*|*curl*)
            cp -r "$d" "$OUT/licences/" ;;
    esac
done

echo "Outils iPhone rassemblés dans $OUT :"
ls -la "$OUT"
# vérification : les outils démarrent (DLL toutes présentes)
"$OUT/idevice_id.exe" --help >/dev/null 2>&1 || "$OUT/idevice_id.exe" -h >/dev/null 2>&1 || {
    code=$?
    [ $code -eq 127 ] && { echo "idevice_id.exe ne démarre pas" >&2; exit 1; }
}
