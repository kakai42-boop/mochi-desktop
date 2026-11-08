## Exécution GitHub du 9 novembre 2026

La branche windows11-port et la PR #1 sont publiées sur kakai42-boop/mochi-desktop.
La CI Linux a réussi : 1394 passed, 4 skipped, 4 warnings, 48 subtests passed in 32.17s.
La construction du paquet Windows a réussi. Le premier démarrage natif a échoué :
GdkWin32Toplevel ne publie pas get_handle dans les bindings Python embarqués.
Le pont utilise désormais gdk_win32_surface_get_handle via ctypes et la capsule
GObject, avec types pointeurs explicites. Deux tests de régression supplémentaires
passent (31 tests ciblés au total). Nouvelle exécution native requise.

Ce constat remplace les limites d'accès GitHub et de tests Linux indiquées dans
l'historique ci-dessous. La validation interactive Windows 11 reste à effectuer.

# Avancement du 9 novembre 2026 — qualification en cours

**Sources mises à jour ; l'installateur livré le 29 octobre reste inchangé.**
Aucune version finale ni validation Windows 11 n'est revendiquée.

## Changements de cette révision

- Le test de démarrage supprime son ancien rapport avant initialisation et écrit
  un identifiant propre à son exécution. Le contrôleur rejette les rapports périmés,
  incomplets, les erreurs et les exécutions hors Windows.
- Le scénario CI teste la version portable, l'installation silencieuse dans un
  chemin contenant espaces et accents, la réinstallation, puis la désinstallation.
  Il vérifie la conservation de deux fichiers témoins dans les dossiers des
  préférences et de Pocket ; il ne prouve pas le fonctionnement de Pocket lui-même.
- L'installateur et le désinstallateur retournent une erreur explicite si Mochi
  est ouvert, sans laisser de boîte de dialogue bloquante en mode silencieux.
- La compilation du lanceur traite désormais les avertissements comme des erreurs.

## Vérifications exécutées sur cette révision

- Tests ciblés : **29 passed in 0.23s**, dont dix nouveaux tests de rapport.
  Commande : python3 -m pytest -q tests/test_windows_smoke_report.py tests/test_windows_platform.py
- Compilation Python de src et packaging/windows : réussie.
- Syntaxe du script Bash de construction : réussie.
- Compilation NSIS avec un paquet factice : réussie. Ce binaire de contrôle
  n'est pas un installateur utilisable et n'est pas livré.
- Suite complète : tentative bloquée à la collecte (GTK4 manquant puis
  libjpeg.so.8 absent avec les bibliothèques extraites). Le résultat historique
  de 1390 tests ci-dessous n'est pas un résultat de cette révision.
- PowerShell et scénario Windows : **non exécutés** dans cet environnement Linux.

## Prochaine étape obligatoire

Publier ces sources dans un dépôt autorisé et exécuter le workflow Windows.
Le runner windows-2025 utilise Windows Server 2025, pas Windows 11 :
https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md
Même un succès de cette CI doit être suivi d'essais interactifs Windows 11
sur transparence, DPI, raccourcis, audio, veille et interactions.
Le script test-package.ps1 est réservé à un compte CI jetable, pas au PC personnel.

Les écarts fonctionnels ci-dessous (mises à jour automatiques, changements
d'onglet, bureaux virtuels) restent à résoudre. Aucune publication distante
ni exécution GitHub Actions n'a eu lieu pendant cette révision.

---

# Bilan du portage Windows 11 — 29 octobre 2026

**Livraison : préversion expérimentale `0.4.1-win-preview1`, pas une version qualifiée à parité complète.**

## Ce qui a été réalisé

Le dépôt amont au commit `471342631206c40d56bbba016578926e16ca8d0b` reste la base. Les assets et la machine de comportement sont conservés. Les nouveaux modules `src/mochi/windows/` fournissent le placement Win32, les zones de travail des moniteurs, la frappe anonyme, les raccourcis, la présence, les catégories d'applications, la session, la batterie/réseau, le thème, les médias, l'audio et la messagerie locale des agents.

Les points de sélection de plateforme sont ajoutés aux détecteurs existants, à l'application, au placement et à la persistance. Les fenêtres auxiliaires réutilisent le contrat de placement existant avec les fonctions Windows. Le mode GNOME/XWayland Linux reste inchangé.

Le lanceur natif `Mochi.exe` démarre Python en mode isolé, sans console, avec une instance par utilisateur/session. Le paquet inclut Python, GTK/PyGObject, Cairo, GStreamer, icônes et sons. L'installateur français NSIS installe par utilisateur, ajoute les raccourcis et conserve les données à la désinstallation. Les diagnostics restent locaux.

## Résultats mesurés

| Vérification | Résultat |
|---|---|
| Suite Python sous Linux, avec GTK4 et affichage Xvfb | **1390 passed, 5 skipped, 2 warnings in 7.14s** |
| Nouveaux tests Windows exécutables sans Windows | Coordonnées négatives, zone de travail, handles 64 bits, absence d'activation lors du déplacement, classification par nom de programme, validation des événements agents, transitions de présence/session, annulation des timers, dossiers Windows et debug sans SIGUSR1 |
| Compilation du lanceur x64 avec MinGW | Réussie avec `-Wall -Wextra -Werror` |
| Compilation Python et contrôle des espaces | Réussis |
| Dépendances Windows | 114 archives MSYS2 UCRT64 ; SHA256 vérifiés contre `packaging/windows/runtime-lock.json` |
| Exécution réelle Windows 11 | **Non réalisée** |
| Tentative de test Windows via Wine | Impossible dans cet environnement : `wineserver: socket: Operation not permitted` ; aucun succès Windows déduit |
| Workflow CI Windows | Ajouté dans `.github/workflows/windows.yml`, **non exécuté à distance** |

Commande de suite : `/usr/bin/python3 -m pytest -q`, avec les bibliothèques GTK/PyGObject extraites dans l'environnement de test et `DISPLAY=127.0.0.1:86`. Les deux avertissements concernent des API GTK dépréciées dans le test de thème existant. Les tests ignorés dépendent d'intégrations optionnelles/conditions d'environnement ; ils ne prouvent pas ces intégrations.

Les cinq tests ignorés sont deux tests Agent Companion/D-Bus, un test helper GNOME/D-Bus nécessitant GJS et deux tests d'installation/mise à jour/reprise Linux exigeant `MOCHI_RUN_UPDATE_E2E=1`.

L'audit statique a inspecté 684 exécutables et bibliothèques PE du runtime. Les dépendances non embarquées sont des bibliothèques système Windows, ainsi que trois sorties optionnelles du lecteur autonome mpg123 (OpenAL, PortAudio et SDL2), non utilisées par les backends GStreamer de Mochi.

Les premières tentatives sans bibliothèques GTK ou sans serveur graphique opérationnel échouaient. Une fois les dépendances et l'affichage disponibles, la suite complète a abouti au résultat ci-dessus. Aucun échec n'a été masqué en supprimant un test.

## Écarts restants par rapport à la demande de parité complète

1. **Mises à jour automatiques Windows** : pas de canal d'artefacts Windows configuré. Le menu explique la mise à jour manuelle par installateur. Le programme ne lance jamais l'installateur Linux sous Windows. La transaction automatique avec restauration prévue dans le plan initial n'est pas livrée.
2. **Changements d'onglet** : pas de source Windows implémentée. Le contexte applicatif et les changements de fenêtre ont un adaptateur distinct, mais ne remplacent pas cette fonction.
3. **Bureaux virtuels** : le placement au-dessus des autres fenêtres ne signifie pas que Mochi est épinglé sur tous les bureaux Windows.
4. **Médias** : le fournisseur WinRT n'accède qu'au statut et au type de lecture. Les applications qui n'exposent pas ces informations ne peuvent pas être classées. Le pont PowerShell doit être validé sur Windows ; aucune donnée média textuelle n'est lue.
5. **Qualification système** : transparence, rendu matériel, écrans à DPI différents, Explorer/Pocket, périphériques audio, veille, applications élevées et raccourcis globaux doivent être testés sur Windows 11 réel. Les tests avec API injectées ne remplacent pas ces essais.
6. **Distribution** : paquet non signé ; pas de certificat de publication fourni. La cible est x64, pas une validation Windows ARM64.

## Reproduction et validation Windows

Sous Linux, avec Python 3.12+, `zstd`, MinGW-w64 et NSIS :

```sh
bash packaging/windows/build.sh
```

Le script construit un installateur et une archive portable. Les bibliothèques sont téléchargées depuis le dépôt MSYS2 et vérifiées ; un paquet retiré du miroir fait échouer la construction au lieu de remplacer silencieusement une version.

Sur un poste Windows ou dans le workflow Windows fourni :

```powershell
$p = Start-Process .\Mochi.exe -ArgumentList '--smoke-test' -PassThru -Wait
$p.ExitCode
Get-Content "$env:LOCALAPPDATA\mochi-desktop\smoke-test.json"
```

Ce test charge le vrai programme, crée la surface native, vérifie le moniteur et les plugins audio, puis ferme l'application. Le code retour doit être zéro. Il utilise une configuration temporaire et ne remplace pas la progression de l'utilisateur. Ensuite appliquer la section Windows de `REGRESSION_WATCHLIST.md` sur un poste réel. Ne déclarer la parité complète qu'après traitement des écarts et réussite de ces vérifications.

## Références techniques consultées

- [GTK sur Windows](https://docs.gtk.org/gtk4/windows.html)
- [PyGObject : installation Windows](https://pygobject.gnome.org/getting_started.html#windows)
- [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos)
- [GetMonitorInfoW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmonitorinfow)
- [GetLastInputInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo)
- [SetWindowsHookExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowshookexw)
- [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)
- [Windows media sessions](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssessionmanager)

La signature de `gdk_win32_surface_get_handle` a également été contrôlée dans le fichier GIR de la version GTK effectivement embarquée.
