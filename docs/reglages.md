# Réglages

Fichier : `config.json` dans le dossier de données (`%LOCALAPPDATA%\Scribouille` ; `%LOCALAPPDATA%\WhiScribe` tant qu'une version 2.x installée le lit ; ou `SCRIBOUILLE_DONNEES`). Une clé absente prend sa valeur par défaut ; une clé inconnue est ignorée, et gardée telle quelle à la sauvegarde. Lire les réglages ne les réécrit jamais (aucune commande de lecture n'écrit quoi que ce soit). Tant qu'une WhiScribe 2.x installée lit le même dossier, son `config.json` n'est jamais modifié : les réglages de la 3.x qui en diffèrent vont dans `config-scribouille.json`, relu par-dessus ; une fois la 2.x partie, la première sauvegarde les reverse dans `config.json` et retire ce fichier.

En ligne de commande : `scribouille reglages` (liste), `reglages lire CLE`, `reglages definir CLE=VALEUR [CLE=VALEUR...]`, `reglages defaut CLE`. Booléens : `oui`/`non` ; listes : séparées par `;` ; `formats` : `txt,srt`. `transcrire` n'enregistre jamais rien : ses options ne valent que pour la commande.

## Transcription

| Clé | Défaut | Effet |
|---|---|---|
| `preset` | `qualite` | `qualite` : large-v3, faisceau 5. `rapide` : large-v3-turbo. Avec le moteur OpenVINO, l'équivalent OpenVINO du même modèle. |
| `langue` | `fr` | Langue parlée (code ISO), ou `auto` pour la détection. |
| `diarisation` | `false` | Séparer les locuteurs (extension à installer depuis Réglages, Transcription). Sans l'extension : ignoré. |
| `nb_locuteurs` | `0` | Nombre de locuteurs attendu ; `0` : détection. |
| `filtres_salle` | `false` | Passe-haut, passe-bas et niveau avant transcription (audio de salle). |
| `sauvegarde_progressive` | `true` | Chaque segment écrit au fil de l'eau dans `reprises\` : reprise au segment près après une coupure ou un plantage. |

## Moteur et rythme

| Clé | Défaut | Effet |
|---|---|---|
| `moteur` (pseudo-clé) | `auto` | `ctranslate2` ou `openvino`. Écrit dans `reglage_machine`, signé pour ce poste (ignoré sur un autre). |
| `peripherique` (pseudo-clé) | `CPU` | Périphérique d'OpenVINO : `CPU`, `GPU` (puce graphique Intel), `NPU`. Sur `GPU` et `NPU`, décodage glouton. Poser un périphérique pose aussi `moteur=openvino`. |
| `rythme` | vide | Part du poste laissée à l'utilisateur. Vide : selon le moteur, `vitesse` quand la puce graphique (OpenVINO) ou une carte NVIDIA calcule (le processeur reste libre : une heure en 5 min 06 sur la puce d'un Core Ultra 5 225U, 92 % du processeur libre), `equilibre` sur le processeur seul. `vitesse` : tout le processeur. `equilibre` : environ trois quarts des fils, priorité inférieure, lots de 4 au plus. `discret` : moitié des fils (cœurs efficaces sur un processeur hybride), priorité basse, EcoQoS, pauses. Appliqué au processus moteur seul. |
| `rythme_auto` | `false` | Passer seul en vitesse maximale quand le poste est inoccupé (2 min sans clavier ni souris, pas de plein écran ni de micro ouvert), revenir au rythme choisi sinon. |
| `dossier_modeles` (pseudo-clé) | `modeles\` des données | Dossier des modèles, noté dans `dossier-modeles.txt`. Les modèles déjà là ne sont pas déplacés. Changé en ligne de commande pendant que la fenêtre est ouverte : pris en compte à son prochain démarrage. |

## Vocabulaire

| Clé | Défaut | Effet |
|---|---|---|
| `utiliser_glossaire` | `true` | Les termes du vocabulaire passent au modèle comme amorce. |
| `appliquer_corrections` | `true` | Corrections du vocabulaire après la transcription, notées dans le compagnon et annulables en relecture. |
| `rapprochement_vocabulaire` | `true` | Corrections par rapprochement phonétique borné, en plus des fautes listées. |
| `vocabulaires_partages` | `[]` | Fichiers de vocabulaire d'équipe (`.toml`), lus en plus du vocabulaire personnel. |
| `corrections_apprises` | `true` | En relecture, proposer de mémoriser une correction. |

## Sorties

| Clé | Défaut | Effet |
|---|---|---|
| `dossier_sortie` | `Documents\Transcriptions` ; avec `SCRIBOUILLE_DONNEES`, `Transcriptions` dans ce dossier | Dossier des transcriptions de la fenêtre. La ligne de commande écrit à côté de la source, ou dans `--sortie`. |
| `formats` | `txt`, avec `horodatage` | `txt`, `srt`, `vtt` ; `horodatage` met l'heure en tête de chaque paragraphe du `.txt`. `definir formats=...` donne la liste complète : un format absent est coupé (`formats=txt,srt` coupe `vtt` et `horodatage`, ce que la commande affiche). L'en-tête du `.txt` : titre, durée, date, voix séparées ; le reste est dans le compagnon. |
| `compagnon_confiance` | `true` | Écrire le `.json` compagnon : segments, mots horodatés, probabilités, remplacements. Nécessaire à la relecture et à `scribouille lire`. |
| `motif_sortie` | vide | Nom des fichiers : `{nom}`, `{date}`, `{heure}`, `{modele}`. Vide : `{date}-{nom}`. |

## Mode avancé

Sans `mode_avance`, les quatre clés suivantes sont ignorées.

| Clé | Défaut | Effet |
|---|---|---|
| `mode_avance` | `false` | Active les clés ci-dessous. |
| `modele_avance` | vide | Modèle imposé (nom faster-whisper, dépôt Hugging Face ou dossier). Vide : celui du preset. Proposé pour le français, jamais par défaut : `bofenghuang/whisper-large-v3-distil-fr-v0.2` (1,5 Go, poids CTranslate2 de l'auteur, licence MIT), 32,2 % d'erreur contre 33,3 % pour turbo sur la campagne de novembre 2026, écart dans le bruit de la mesure ; pas de version OpenVINO publiée, il calcule donc sur le processeur, même quand la puce graphique est réglée. |
| `beam_size` | `0` | Largeur du faisceau ; `0` : celle du preset. |
| `condition_on_previous_text` | `true` | Le modèle tient compte du texte précédent. |
| `forcer_processeur` | `false` | CTranslate2 sur processeur, quel que soit le réglage du poste. |

## Fenêtre et poste

| Clé | Défaut | Effet |
|---|---|---|
| `langue_interface` | vide | `fr` ou `en` ; vide : celle de Windows (enregistrée avec la première sauvegarde des réglages, jamais à la lecture). Vaut aussi pour les en-têtes des fichiers produits. |
| `surveillance` | `false` | Transcrire ce qui arrive dans `dossier_surveille`. |
| `dossier_surveille` | vide | Dossier scruté. |
| `barre_taches` | `true` | Progression sur l'icône de la barre des tâches. |
| `prevenir_fin` | `true` | Fin de file, fenêtre en arrière-plan : clignotement, titre, notification Windows sans son. |
| `maj_verifier` | `false` | Vérifier les nouvelles versions sur GitHub, une fois par jour au plus. Seul appel réseau hors téléchargement d'un modèle. |
| `theme` | `auto` | Thème de la fenêtre : `auto` (celui de Windows), `clair` ou `sombre`. |

Clés internes, tenues par l'application et refusées par `reglages` : `zoom`, `journal_ouvert` (état de la fenêtre), `proposition_ecartee` (réglage proposé écarté sur ce poste), `exemples_anciens` (retrait des exemples fictifs des versions 2.x de `vocabulaire.txt` et `corrections.txt` : vide, `retires`, `vus`, `gardes`), `avis_locuteurs` (séparation des voix cochée mais non installée, déjà dite une fois par la ligne de commande ; remis à faux quand `diarisation` change), `reglage_machine` (écrit par les pseudo-clés `moteur` et `peripherique`, le banc et la campagne).

## Variables d'environnement

| Variable | Effet |
|---|---|
| `SCRIBOUILLE_DONNEES` | Dossier de données imposé (un chemin relatif est rendu absolu), sans reprise de l'ancien dossier `WhiScribe` (essais, mesures, agents). Le dossier de sortie par défaut est alors `Transcriptions` dans ce dossier, jamais le `Documents` de l'utilisateur : rien n'est écrit hors de ce dossier sans qu'on le demande (sauf les modèles, si `dossier-modeles.txt` en désigne d'autres). |
| `SCRIBOUILLE_ESSAI_REGISTRE` | Vérifications seulement : clés de désinstallation simulées (JSON, ou `erreur`) à la place du registre, pour éprouver la détection d'une WhiScribe 2.x. Lue seulement quand `LOCALAPPDATA` désigne un autre dossier que le vrai : elle ne peut jamais lever la protection d'une vraie 2.x. |
| `TRANSCRIPTEUR_DEBUG` | Outils de développement de la fenêtre. |
