> **Mise à jour du 29 octobre 2026 :** le second message utilisateur a validé l'implémentation et précisé Windows 11 avec lancement simple. Une préversion est implémentée ; ce document conserve le plan initial, pas une déclaration d'achèvement. Voir `docs/WINDOWS_VALIDATION.md` pour les résultats et écarts actuels.

# Portage Windows — conception à valider

**Date :** 2026-10-27
**Statut :** proposition, aucune modification du programme effectuée.
**Source auditée :** `https://github.com/miflow13/mochi-desktop`, commit `471342631206c40d56bbba016578926e16ca8d0b`, version déclarée 0.4.1.

## Objectif

Faire fonctionner Mochi nativement sous Windows, avec les fonctions du commit de référence, les mêmes illustrations et la même logique de comportement. Cible proposée : Windows 10/11 x64. ARM64 et les versions antérieures ne sont pas implicitement couverts. La qualification Windows reste à faire ; aucun exécutable Windows validé n'existe dans cette livraison de conception.

## Constats vérifiés dans le code

| Domaine | Code actuel | Travail nécessaire |
|---|---|---|
| Démarrage | `main.py` enregistre `signal.SIGUSR1` en mode debug | Diagnostic compatible Windows ; conserver le choix XWayland existant sur Linux |
| Interface | `app.py`, GTK4/PyGObject/Cairo et chaîne de mixins | Embarquer les bibliothèques nécessaires et valider leur rendu Windows avant généralisation |
| Placement | `windowing.py`, `x11.py`, sélection du buddy X11 quand layer-shell est absent | Backend Windows distinct : déplacement, pointeur, focus, transparence, moniteurs et DPI |
| Audio | `sound.py`, effets via `pw-play`/`paplay`, ambiance via GStreamer | Backend pour effets et ambiance, avec volume, pause, reprise et libération des ressources |
| Contexte | Helper GNOME/D-Bus, adaptateurs UPower et NetworkManager, session logind | Sources Windows des événements sémantiques existants |
| Agents | `agent_signal.py` utilise `gdbus`; actions exportées par `Gtk.Application` | Transport local Windows validant les événements et les jetons, sans contenu des agents |
| Données | `config.py` utilise XDG ; `pocket_store.py` utilise XDG_DATA_HOME | Répertoires utilisateur Windows, écriture atomique, conservation des données |
| Mise à jour | `update/worker.py` appelle `install.sh`; bootstrap Linux | Transaction Windows séparée, installation côte à côte, contrôle de démarrage et restauration |
| Pocket | Dépôt de fichiers/texte/images et ouverture par Gio | Vérifier Explorer, chemins Unicode/UNC, fichiers absents, glisser-déposer et associations |

Cet audit identifie les points d'entrée principaux ; le premier lot d'implémentation doit compléter l'inventaire des imports et appels propres à Linux.

## Architecture proposée

Conserver GTK4/PyGObject/Cairo et le moteur existant dans un premier temps. Fournir un environnement Windows isolé contenant Python et les bibliothèques natives, à partir d'une chaîne reproductible dont les versions seront fixées après vérification. Ne pas imposer une installation Python au destinataire de la version finale.

Ajouter des adaptateurs de plateforme injectables. Les modules métier ne doivent pas importer directement les API Windows. Les sources Linux ne doivent pas être démarrées sous Windows. Les événements Windows passent par les contrôleurs et `PresenceEngine` existants, sans seconde machine à états. Chaque hook, abonnement, thread et timer possède un arrêt explicite.

Le prototype graphique est un jalon bloquant : transparence réelle, déplacement sans vol de focus, menus fonctionnels et DPI mixtes. Si GTK Windows ne satisfait pas ces exigences, documenter les échecs et proposer une révision d'architecture avant une migration d'interface. Une réécriture Qt n'est pas incluse silencieusement.

## Parité attendue

- Toutes les animations livrées, clignements, déplacement autonome, Stay put et Edge Roam.
- Clics simples/multiples, caresses, nourriture, prise en main, déplacement, lâcher, sommeil manuel et autonome.
- Bond XP, niveaux, déblocages, célébrations, catalogue, Mochi Lab, bulles et préférences.
- Focus : travail, pauses, tours, encouragements, ambiance pluie et attribution correcte des XP.
- Pocket : fichiers, URL, texte, images, persistance, ouverture et suppression des références.
- AmbiSense : frappe anonyme, inactivité, verrouillage/reprise, catégories d'applications, médias, batterie et réseau ; activité de fichiers et curiosité à inventorier précisément.
- Agent Companion : réception locale des événements permis et conservation des règles de priorité.
- Installation, lancement sans console, raccourcis, instance unique, mise à jour et désinstallation.

Chaque fonction doit figurer dans une matrice « implémentée / testée automatiquement / testée sur Windows / limitation ». Une source indisponible peut se dégrader proprement à l'exécution, mais ne compte pas comme parité accomplie.

## Intégrations Windows à qualifier

Évaluer les API Windows documentées pour le placement et les coordonnées DPI, les notifications de session/alimentation, la catégorie du processus actif, la frappe réduite immédiatement à des impulsions anonymes, les raccourcis globaux et la lecture multimédia. Valider les API, signatures 64 bits et bibliothèques nécessaires contre la documentation officielle avant codage.

Ne pas utiliser de titres de fenêtres, caractères saisis, noms de documents ou contenu du presse-papiers pour déduire le contexte. Les données déposées volontairement dans Pocket restent une exception explicite. Les signaux GNOME de changement d'onglet et de contexte vidéo peuvent ne pas avoir d'équivalent respectant ces limites : qualifier leur faisabilité et présenter toute différence avant de déclarer la parité. Ne pas remplacer une détection manquante par une heuristique trompeuse.

## Distribution et mise à jour

Prévoir une archive portable et un installateur par utilisateur ; garder les données hors du répertoire remplaçable. Un processus externe attend la fermeture de Mochi avant remplacement des binaires Windows verrouillés. Valider les chemins d'extraction, l'identité de l'artefact et sa compatibilité, puis restaurer l'ancienne version si le démarrage échoue.

Le canal Linux amont ne doit jamais être installé par la version Windows. Le fournisseur et le canal d'artefacts Windows devront être définis avant activation de la mise à jour. Aucune publication dans le dépôt amont n'est autorisée implicitement. La signature de code nécessite une identité de publication appropriée ; ne pas prétendre qu'un paquet non signé est signé.

## Contraintes et décisions

Conserver la licence MIT et les crédits. Préserver les règles de priorité, la progression sans pénalité, les assets et le comportement Linux. La demande de portage inclut les adaptations nécessaires du lanceur, du packaging et de l'updater, tout en conservant le choix XWayland Linux. Garder `dependencies = []` si les bibliothèques existantes embarquées suffisent ; justifier toute dépendance Windows supplémentaire avant de la retenir.

Les fonctions locales n'ajoutent ni télémétrie ni service cloud. La mise à jour reste le mécanisme réseau explicite déjà présent dans le produit.

## Validation et définition de terminé

Tests unitaires des adaptateurs avec API injectées, tests de non-régression du métier, compilation Python, construction du paquet et inventaire des assets. Exécuter une CI Windows réelle et la suite Linux. Tester le paquet final sur Windows 10/11 x64 sans environnement de développement : DPI 100/125/150/200 %, plusieurs moniteurs dont coordonnées négatives, déconnexion d'écran, veille/reprise, verrouillage, raccourcis occupés, médias indisponibles, chemins accentués et fonctionnement hors ligne.

Tester aussi les interruptions croisées (drag, sleep, Focus, menus et réactions), la libération des hooks à la fermeture, le redémarrage, et la conservation de Bond/Pocket lors d'une mise à jour et d'un retour arrière. L'interaction doit toujours redevenir disponible.

**Limite actuelle :** environnement de travail Linux, aucune session Windows testée. Tentative de référence `python3 -m pytest -q` : arrêt immédiat, `No module named pytest`. Aucun test n'a donc passé à ce stade. Le portage ne peut être qualifié « parfaitement fonctionnel » sur cette seule analyse.
