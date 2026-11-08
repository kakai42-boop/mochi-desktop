> **Mise à jour du 29 octobre 2026 :** le second message utilisateur a validé l'implémentation et précisé Windows 11 avec lancement simple. Une préversion est implémentée ; ce document conserve le plan initial, pas une déclaration d'achèvement. Voir `docs/WINDOWS_VALIDATION.md` pour les résultats et écarts actuels.

# Portage Windows — plan d'implémentation

**Statut :** en attente de validation de la conception et du plan, conformément à `AGENTS.md`.
**Conception :** `../specs/2026-10-27-windows-port-design.md`
**But :** Windows 10/11 x64 natif avec parité fonctionnelle mesurée et paquet installable.

## Lot 1 — Référence et faisabilité graphique

- [ ] Créer une branche de travail depuis `471342631206c40d56bbba016578926e16ca8d0b`.
- [ ] Installer les dépendances de test dans un environnement isolé ; établir le bilan de la suite originale, avec les skips et leurs raisons.
- [ ] Compléter l'inventaire des appels/imports Linux et des fonctions exposées par les menus.
- [ ] Vérifier les instructions officielles GTK/PyGObject Windows et les API système retenues ; fixer la chaîne de construction.
- [ ] Construire sur Windows un prototype utilisant les assets originaux : transparence, focus, menus, placement, DPI et moniteurs.
- [ ] Bloquer la suite si ce prototype ne permet pas de conserver les interactions requises ; présenter alors une architecture révisée.

## Lot 2 — Démarrage et placement

Fichiers concernés : `main.py`, `app.py`, `windowing.py`, `x11_buddy.py`, `mochi_launcher.py`, nouveaux adaptateurs Windows et tests.

- [ ] Écrire les tests de sélection de plateforme et de debug sans SIGUSR1.
- [ ] Isoler les opérations natives ; éviter le démarrage des composants X11/Wayland sur Windows.
- [ ] Implémenter déplacement, lecture du pointeur, état du bouton, maintien au-dessus et absence de vol de focus.
- [ ] Gérer conversions DPI, limites de zone de travail, coordonnées négatives et restauration après changement d'écran.
- [ ] Réutiliser les contrôleurs d'interaction et transitions existants ; vérifier menus et récupération après interruption.

## Lot 3 — Audio, données et interface complète

Fichiers concernés : `sound.py`, `config.py`, `pocket_store.py`, fenêtres Pocket/menus et résolution des assets.

- [ ] Tester puis adapter chemins utilisateur et écritures atomiques ; couvrir Unicode et chemins avec espaces.
- [ ] Implémenter effets courts et ambiance longue, mute/volume séparés, pause/reprise et nettoyage.
- [ ] Valider catalogue, niveaux, Focus, fenêtres secondaires, thème et outils développeur.
- [ ] Tester glisser-déposer Explorer, URL, texte et images ; ouvrir avec les associations Windows sans construire de commande shell depuis les entrées.
- [ ] Vérifier que tous les assets audio et image sont distribués et chargés depuis l'installation.

## Lot 4 — AmbiSense et Agent Companion

Fichiers concernés : détecteurs `typing_activity.py`, `media_activity.py`, helper/session/signals, raccourcis et `agent_signal.py`.

- [ ] Définir des contrats injectables identiques pour les événements sémantiques Linux et Windows.
- [ ] Ajouter frappe anonyme, présence, verrouillage/reprise, catégories d'apps, batterie/réseau et raccourcis, avec nettoyage et dégradation explicite.
- [ ] Implémenter les réactions médias à partir d'une source Windows vérifiée ; ne lire aucun titre ni contenu.
- [ ] Qualifier les signaux fichiers/onglets/vidéo et documenter toute différence encore bloquante pour la parité.
- [ ] Ajouter un transport IPC local pour les agents, limité à l'utilisateur, messages bornés et validation des événements/jetons ; test absent/crash/redémarrage.
- [ ] Tester priorités, absence de double événements, silence/quiet mode, expiration et reprise après interruption.

## Lot 5 — Installation et mise à jour

Fichiers concernés : nouvelle chaîne `packaging/windows`, scripts, workflow CI Windows, `update/` et lanceur.

- [ ] Produire une archive portable autonome et un installateur par utilisateur sans droits administrateur habituels.
- [ ] Ajouter raccourcis, instance unique, diagnostics et désinstallation conservant les données par défaut.
- [ ] Séparer le canal Windows du canal Linux ; ne pas annoncer de mise à jour installable sans artefact Windows correspondant.
- [ ] Tester préparation côte à côte, arrêt, remplacement, handshake et rollback, y compris fichiers verrouillés, interruption et disque plein.
- [ ] Tester installation et désinstallation dans des chemins accentués et avec espaces.

## Lot 6 — Qualification et livraison

- [ ] Ajouter une matrice de parité pour chaque fonction de la conception et chaque commande des menus.
- [ ] Exécuter `python3 -m pytest -q` sur Linux et l'équivalent sur Windows ; publier résultats exacts et skips.
- [ ] Exécuter compilation Python, construction des paquets, contrôle des assets et `git diff --check`.
- [ ] Effectuer les essais manuels Windows de la conception, avec versions OS et provenance des builds.
- [ ] Actualiser `README.md`, `CHANGELOG.md`, `REGRESSION_WATCHLIST.md` et fournir un guide Windows en français.
- [ ] Livrer source, historique des changements, paquet Windows réellement construit et bilan des limites. Ne pas étiqueter une compilation non testée « stable ».

## État initial enregistré

Seuls ces deux documents sont ajoutés ; aucune fonctionnalité du programme n'est modifiée. Aucun test ajouté au stade conception. `python3 -m pytest -q` ne peut pas démarrer : `No module named pytest`. Aucun accès à un poste Windows ni exécution CI distante n'a été établi. Les cases ci-dessus décrivent du travail à effectuer, pas du travail déjà livré.
