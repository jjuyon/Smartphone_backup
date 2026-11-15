# Smartphone Backup

Application **Linux et Windows** (Qt) pour sauvegarder / synchroniser un **iPhone** ou un
**Android**, et ranger ou dédoublonner des photos. Au démarrage, un écran d'accueil propose le
choix et indique en direct quel téléphone est branché.

Fonctionne sous tous les bureaux (KDE, GNOME, XFCE, Cinnamon, MATE, LXQt…), en X11
comme en Wayland : thème sombre et icônes sont fournis par l'appli.

## Windows (10 et 11)

Téléchargez l'installateur `SmartphoneBackup-…-windows-setup.exe` ou la version portable
`SmartphoneBackup-…-windows-portable.zip` (à décompresser, sans installation) depuis l'onglet
**Releases** du dépôt GitHub, ou depuis l'onglet **Actions** (dernière fabrication).

- **Android** : au premier lancement, le bandeau « Aide à l'installation » télécharge `adb`
  depuis le site de Google (dans `%LOCALAPPDATA%\SmartphoneBackup`, sans droits administrateur).
  Si le téléphone n'apparaît pas, installez le pilote USB de son fabricant.
- **iPhone, sans iTunes** : les outils de sauvegarde (libimobiledevice) sont fournis avec l'appli.
  Seul le pilote USB d'Apple est nécessaire : il vient de l'application gratuite **Apple Devices**
  (Microsoft Store), que l'appli propose d'installer. Inutile de l'ouvrir : c'est Smartphone
  Backup qui fait la sauvegarde.
- Les noms de fichiers interdits sous Windows (`:` `?` `*`…) sont corrigés pendant la copie.
- Windows SmartScreen peut afficher « Éditeur inconnu » (appli non signée) :
  « Informations complémentaires » puis « Exécuter quand même ».

Fabrication : automatique par GitHub Actions (`.github/workflows/build.yml`) à chaque envoi sur
`main` ; un tag `v1.2.3` publie une Release. À la main sous Windows : `packaging\windows\build.ps1`.

## AppImage Linux (recommandé pour une autre machine)

Fabriquée aussi par GitHub Actions sur Ubuntu 22.04 (compatible avec plus de distributions).

```bash
./build_appimage.sh            # produit dist/Smartphone_Backup-x86_64.AppImage
```
Copiez le fichier sur l'autre PC, rendez-le exécutable (`chmod +x`) et lancez-le.
L'AppImage contient Python, Qt et l'appli ; elle nécessite une glibc au moins aussi récente
que celle de la machine de build.

⚠️ L'AppImage (Qt 6 de pip) exige un processeur **x86-64-v2** (SSE4.2, POPCNT : environ 2009
et après). Pour un processeur plus ancien (Core 2 Duo, MacBook 2008…), utilisez
`install.sh` ci-dessous.

## Installation depuis les sources

```bash
./install.sh                   # libs Qt manquantes, venv, raccourci dans le menu
```
`install.sh` détecte le processeur :
- récent → venv avec PySide6 (pip) ;
- ancien → Qt de la distribution (PySide6, ou PySide2/Qt 5 sur Ubuntu 24.04), via apt/dnf/pacman.
`./install.sh --systeme` force ce second mode. L'appli fonctionne avec Qt 6 comme avec Qt 5
(`smartphone_backup/ui/qt.py`).

Lancement : menu « Smartphone Backup », ou `./lancer.sh`.

Les prérequis sont vérifiés au démarrage (bandeau en bas de l'accueil). S'il en manque,
le bouton « Aide à l'installation » les installe (apt, dnf ou pacman, mot de passe
demandé via pkexec) ou donne la commande à copier. Sans agent polkit graphique
(i3, Sway…), seule la commande à copier est proposée.

## iPhone
- Sauvegarde via `idevicebackup2` (incrémentale), puis rangement en
  `Photos/AAAA/MM`, `Documents`, `Musique/Artiste/Album`, `Notes vocales`.
- La sauvegarde doit être **non chiffrée** ; accepter « Faire confiance à cet ordinateur ».
- Les fichiers déjà rangés ne sont pas recopiés.

## Android
- Activer « Débogage USB » (Options pour les développeurs) et accepter l'autorisation.
- Copie incrémentale (taille + date) par lots, directement dans la destination : les fichiers
  apparaissent au fur et à mesure et une interruption ne perd que le lot en cours.
- Carte SD, dossier supplémentaire, mode miroir
  (les fichiers supprimés du téléphone vont dans `_Corbeille-sync`).

## Photos (rangement et doublons)

Accessible depuis la carte « Photos » de l'accueil, pour n'importe quel dossier (ancienne sauvegarde,
carte d'appareil photo, disque externe…), avec les options affichées directement dans l'écran, et
depuis le bouton « Ranger les photos… » de l'écran Android. Les deux partagent le même formulaire,
donc exactement les mêmes options.

**Rangement** : classe les photos et vidéos dans un dossier séparé (par défaut `Photos rangées`),
avec un aperçu avant de lancer.

- Classements : par année puis mois, par année, par mois, par année puis jour, ou par
  événement (photos prises sans longue pause regroupées, pause et taille minimale réglables).
- Options : ne pas ranger les doublons (activé par défaut, rien n'est supprimé), séparer photos
  et vidéos, séparer par origine (appareil photo, captures d'écran, WhatsApp, autres), renommer avec la date.
- Date de prise de vue : EXIF, sinon nom du fichier, sinon métadonnées vidéo, sinon date du fichier.
- Méthode : liens physiques (aucun espace disque en plus, copie automatique si le disque ne
  les permet pas), copie, ou déplacement (la synchronisation suivante recopiera alors les photos).
- Relancer le rangement n'ajoute que les nouvelles photos.

**Doublons** : recherche les photos et vidéos présentes plusieurs fois, avec aperçu.

- Copies identiques (même contenu, octet pour octet) ; en option, photos ressemblantes (même photo
  redimensionnée ou recompressée, ex. renvoyée par WhatsApp), à vérifier.
- Pré-sélection : on garde le meilleur exemplaire (plus grande résolution, dossier de l'appareil
  photo plutôt que WhatsApp/Téléchargements, nom sans « (1) » ou « copie », le plus ancien).
  Les photos ressemblantes de même taille (rafales) ne sont jamais pré-cochées.
- Les fichiers retirés vont à la corbeille (récupérables) ou dans un dossier `_Doublons`.

## Tests

```bash
pip install -r requirements.txt pytest
QT_QPA_PLATFORM=offscreen python -m pytest tests
```
Les tests Android utilisent un faux téléphone (`tests/fake_adb.py`).

## Structure
```
main.py                              point d'entrée
smartphone_backup/core/iphone.py     logique iPhone (sans interface)
smartphone_backup/core/android.py    logique Android (sans interface)
smartphone_backup/core/prereqs.py    vérification / installation des prérequis
smartphone_backup/core/photos.py     rangement des photos par date
smartphone_backup/core/dupes.py      détection des doublons (identiques, ressemblantes)
smartphone_backup/core/system.py     différences Linux / Windows (outils, noms de fichiers)
smartphone_backup/core/procs.py      arrêt des processus lancés par l'appli à la fermeture
smartphone_backup/ui/                accueil, écrans iPhone / Android, sélecteur de dossier, thème
smartphone_backup/icons/             icônes SVG de l'appli
build_appimage.sh                    fabrication de l'AppImage Linux
packaging/windows/                   fabrication Windows (PyInstaller, Inno Setup, outils iPhone)
tests/                               tests automatiques (faux téléphone Android)
.github/workflows/build.yml          tests + fabrication Windows / Linux sur GitHub
```
