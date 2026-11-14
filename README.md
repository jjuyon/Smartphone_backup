# Synchro Smartphone

Application Linux (Qt) pour sauvegarder / synchroniser un **iPhone** ou un **Android**.
Au démarrage, un écran d'accueil propose le choix du téléphone et indique en direct
lequel est branché.

Fonctionne sous tous les bureaux (KDE, GNOME, XFCE, Cinnamon, MATE, LXQt…), en X11
comme en Wayland : thème sombre et icônes sont fournis par l'appli.

## AppImage (recommandé pour une autre machine)

```bash
./build_appimage.sh            # produit dist/Synchro_Smartphone-x86_64.AppImage
```
Copiez le fichier sur l'autre PC, rendez-le exécutable (`chmod +x`) et lancez-le.
L'AppImage contient Python, Qt et l'appli ; elle nécessite une glibc au moins aussi récente
que celle de la machine de build.

## Installation depuis les sources

```bash
./install.sh                   # libs Qt manquantes, venv, raccourci dans le menu
```

Lancement : menu « Synchro Smartphone », ou `./lancer.sh`.

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
- Copie incrémentale (taille + date), carte SD, dossier supplémentaire, mode miroir
  (les fichiers supprimés du téléphone vont dans `_Corbeille-sync`).

## Structure
```
synchro_smartphone.py      point d'entrée
synchro/core/iphone.py     logique iPhone (sans interface)
synchro/core/android.py    logique Android (sans interface)
synchro/core/prereqs.py    vérification / installation des prérequis
synchro/ui/                accueil, écrans iPhone / Android, sélecteur de dossier, thème
synchro/icons/             icônes SVG de l'appli
build_appimage.sh          fabrication de l'AppImage
anciens/                   scripts d'origine
```
