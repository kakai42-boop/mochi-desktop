# Parité fonctionnelle Windows

La rubrique Quick Start de Mochi fixe le minimum. Les composants partagés
restent ceux du projet Linux. Pour chaque ligne, le test Windows doit passer
par la source d'activité ou la commande correspondante. Ouvrir une fenêtre
prouve son ouverture, pas la disponibilité de toutes ses fonctions.

| Fonction attendue | Couverture acquise | Essai Windows 11 à effectuer |
|---|---|---|
| Frappe et frappe soutenue | Hook Windows actif en mode normal. Temporisation couverte par la suite partagée. | Taper puis arrêter dans un éditeur. Vérifier entrée et sortie de l'animation. |
| Éditeur, VS Code, terminal | Catégories par nom d'exécutable et transitions partagées. | Alterner VS Code, éditeur et terminal. Observer les réactions et le retour à l'état normal. |
| Musique | Détecteur Windows initialisé. Bibliothèques audio présentes. | Lire, mettre en pause, reprendre et arrêter de la musique sur un lecteur compatible. |
| YouTube et vidéos compatibles | Détecteur Windows fondé sur le type de lecture déclaré par l'application. | Vérifier YouTube dans Edge, Chrome et Firefox et distinguer vidéo et musique. Un lecteur sans type déclaré reste un cas à résoudre. |
| Inactivité, retour, veille et verrouillage | Adaptateur Windows et tests de transitions avec signaux simulés. | Laisser le poste inactif, reprendre, verrouiller puis déverrouiller, suspendre puis reprendre. |
| Navigation de fichiers | Adaptateur Explorer et activité locale des téléchargements. | Utiliser l'Explorateur et revenir à un autre programme. |
| Batterie et réseau | Contrat AmbiSense corrigé et couvert par un test. Aucun échec du mode normal dans la CI de qualification c635ea0. | Vérifier branchement secteur, batterie faible et transition réseau, selon le matériel. |
| Changements d'onglet | Notifications Windows sans lecture de titre. Activation du hook et filtrage couverts. | Changer d'onglet à la souris et au clavier, puis laisser une page se retitrer en arrière-plan. |
| Survol et cœur | Gestionnaire partagé. | Survoler puis quitter la zone. Contrôler le délai et la limitation de répétition. |
| Clic gauche, double-clic, déplacement | Correctif du double-clic et vérification par événements Win32 sur la branche. | Vérifier le clic et son bip, le cœur, le dépôt et la reprise avec plusieurs échelles d'affichage. |
| Clic droit et contenu du menu | Les 13 lignes du menu et sa surface native sont vérifiées en mode normal. | Ouvrir, choisir un élément, fermer par Échap et rouvrir près de chaque bord. |
| Petites phrases et mode silencieux | Moteur et réglages partagés. Fenêtre Mochi Lab vérifiée. | Déclencher une phrase contextuelle, désactiver les bulles, puis activer le mode silencieux. |
| Focus et pauses | Ouverture de Focus vérifiée. Contrôles début/pause/reprise/arrêt ajoutés au scénario Windows. | Finir un cycle avec pause, vérifier le lien et l'ambiance sonore. |
| Sommeil, réveil, Edge roam, Stay put, fermeture | Lignes du menu vérifiées. Persistance de Stay put vérifiée. | Basculer chaque commande, contrôler l'état de Mochi et la persistance après relance. |
| Pocket | Fenêtre native ouverte en CI. | Déposer fichier, image, texte ou lien, rouvrir l'élément, vérifier la persistance. |
| Lien, nourriture, nom et emotes | Code partagé, présence des lignes et ouverture du catalogue vérifiées. | Nourrir, gagner du lien, débloquer et rejouer une emote. |
| Guide, catalogue et Mochi Lab | Fenêtres natives vérifiées. | Tester les raccourcis et les actions du catalogue et du Lab. |
| Agent Companion | Récepteur local Windows créé en mode normal. | Envoyer des événements d'agent et vérifier animations et fin de session. |
| Installation et données | Installation, réinstallation et désinstallation silencieuses vérifiées en CI avec chemins accentués et fichiers témoins préservés. | Installer avec l'assistant sous un compte Windows 11 standard et démarrer par le raccourci. |
| Mise à jour et retour arrière | Installation manuelle disponible. | Fournir et qualifier le canal Windows, la mise à jour intégrée et le retour arrière. |
| Bureaux virtuels | Le suivi utilise une fenêtre au premier plan et, à défaut, l’identifiant du bureau actif quand l’Explorateur le fournit. Tests de décision et nettoyage COM couverts. | Basculer entre deux bureaux, puis vérifier le comportement sur un bureau vide. L'épinglage dans la Vue des tâches reste un comportement distinct. |

La suite Linux de cette révision donne 1 420 tests réussis, 5 ignorés et deux avertissements GTK.
Le premier essai Win32 a confirmé le clic droit, le clic gauche et les commandes de Focus.
Le correctif du double-clic et le contrôle du glisser nécessitent la nouvelle exécution.

Le runner Windows Server valide les composants Win32 et GTK sur lesquels ces
scénarios s'exécutent. Le résultat de Windows 11 interactif reste un jalon distinct.

[Première qualification des menus et du mode normal](https://github.com/kakai42-boop/mochi-desktop/actions/runs/42538729337)

## Retour du premier essai Windows 11

L'utilisateur a confirmé l'installation, le démarrage, la position mémorisée, les clics et menus, les sons, le catalogue, le sommeil et le réveil, la nourriture, le volume, le mode silencieux, la frappe, la musique, Focus, le dépôt dans Pocket et la réaction à l'Explorateur. Il a signalé que la taille restait bloquée après agrandissement, que Chrome ou Spotify masquaient Mochi, que l'ouverture du dossier Pocket échouait, et que les changements d'onglet et de bureau étaient difficiles à observer.

Le test de qualification vérifie maintenant l'agrandissement et le rétrécissement d'un vrai HWND, le rétablissement du statut topmost sans activation, le menu près de la barre des tâches et l'ouverture d'un dossier de test accentué dans l'Explorateur. Le changement d'onglet dépend toujours d'une notification Windows émise par le navigateur. Le passage sur un bureau virtuel vide et le changement d'écran à DPI mixte restent des essais Windows 11.
