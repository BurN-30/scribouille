# Ligne de commande

Tout ce que fait la fenêtre, sans fenêtre : par SSH, en tâche planifiée, par un agent de code. Aucun module d'interface n'est chargé (ni pywebview, ni WebView2) ; le calcul tourne dans le processus moteur, comme pour la fenêtre (voir [architecture.md](architecture.md)).

```
scribouille COMMANDE [options] [--json]
```

- Version installée ou portable : `scribouille.com` dans le dossier du programme. Dans `cmd` ou PowerShell, `scribouille` suffit depuis ce dossier (le `.com` passe avant le `.exe`) ; ailleurs, chemin complet ou dossier ajouté au `PATH`.
- Depuis les sources : `.venv\Scripts\python transcriber.pyw COMMANDE`.
- `scribouille aide` : le résumé ; `scribouille version`.

## Garanties

- Aucun téléchargement sans `--telecharger`, aucun écrasement sans `--ecraser`, aucun effacement sans `--oui` (ou confirmation tapée dans un terminal).
- Aucun appel réseau hors téléchargement d'un modèle demandé.
- `transcrire` ne modifie jamais les réglages : ses options valent pour la commande seule.
- `espace`, `effacer --apercu`, `etat`, `lire` et `agent` n'écrivent rien dans le dossier de données.
- Chemins absolus dans les sorties JSON ; aucun texte transcrit dans les journaux.
- Ctrl+C, fermeture de la session SSH ou arrêt de la tâche : le moteur s'arrête avec la commande, le travail fait reste sur le disque, `reprendre` le poursuit.

## Codes de retour

| Code | Sens |
|---|---|
| 0 | Fait. |
| 1 | Au moins un fichier en échec, les autres faits (détail dans `fin`). |
| 2 | Arguments invalides, ou confirmation manquante (`effacer` sans `--oui` hors terminal). |
| 3 | Pas prêt : modèle absent sans `--telecharger`, moteur absent. |
| 4 | Sortie déjà là : fichier déjà transcrit, fiche ou export existant, sans `--ecraser`. |
| 5 | Interrompu : reprenable par `scribouille reprendre`. |
| 6 | Ressource manquante : disque plein, mémoire insuffisante. |

## Commandes

### transcrire

```
scribouille transcrire FICHIER|DOSSIER... [options]
```

| Option | Défaut | Effet |
|---|---|---|
| `--sortie DOSSIER` | à côté de chaque source | Dossier des sorties. |
| `--formats LISTE` | `txt,json` | `txt`, `json` (compagnon structuré), `srt`, `vtt`, `horodatage` (heure de chaque paragraphe dans le `.txt`). `json` implique `txt`. |
| `--langue CODE` | réglage `langue` | `fr`, `en`, ..., `auto`. |
| `--preset qualite\|rapide` | réglage `preset` | large-v3, ou turbo. |
| `--moteur auto\|openvino\|ctranslate2` | `auto` (réglage du poste) | Moteur imposé pour cette commande. |
| `--peripherique CPU\|GPU\|NPU` | `CPU` | Périphérique d'OpenVINO (implique `--moteur openvino`). |
| `--rythme vitesse\|equilibre\|discret\|auto` | réglage `rythme` | Part du poste laissée à l'utilisateur ; `auto` : rythme choisi quand le poste est occupé, vitesse maximale sinon. |
| `--locuteurs auto\|non\|N` | réglage `diarisation` | Séparation des locuteurs (extension installée). |
| `--vocabulaire F.toml` | | Vocabulaire d'équipe en plus du personnel ; répétable. |
| `--sans-vocabulaire` | | Ni amorce ni corrections. |
| `--recursif` | | Sous-dossiers compris. |
| `--telecharger` | | Permet de télécharger un modèle absent. |
| `--ecraser` | | Refait un fichier déjà transcrit (ses anciennes sorties sont remplacées). |

Un fichier est « déjà transcrit » quand le dossier de sortie contient un compagnon `.json` qui le nomme : il est sauté (`fichier_ignore`), code 4 si rien d'autre n'a échoué.

### reprendre

```
scribouille reprendre [CLE|FICHIER] [--sortie D] [--rythme R] [--telecharger]
```

Sans argument, la plus récente. La reprise garde son modèle (le texte ne mêle jamais deux modèles). Sorties à côté de la source par défaut.

### etat

Transcriptions reprenables (`interrompue`, ou `en_cours` si un moteur tourne et que la sauvegarde a bougé dans la minute), avec position, pourcentage et clé ; processus moteurs actifs (PID, mémoire).

### lire

```
scribouille lire SORTIE.json|SORTIE.txt [--limite N] [--decalage N] [--depuis S] [--jusqua S] [--douteux] [--texte]
```

Lecture bornée d'un compagnon : au plus `--limite` mots (2 000 par défaut) à partir du segment `--decalage` ; `pagination.suivant` donne le décalage de la page suivante (`null` à la fin). `--douteux` : seulement les segments qui ont des mots sous le seuil (0,5), avec ces mots. `--texte` : texte lisible horodaté au lieu du JSON.

### reglages

```
scribouille reglages [liste]
scribouille reglages lire CLE
scribouille reglages definir CLE=VALEUR [CLE=VALEUR...]
scribouille reglages defaut CLE [CLE...]
```

Chaque réglage, sa valeur par défaut et son effet : [reglages.md](reglages.md). Pseudo-clés : `moteur`, `peripherique`, `dossier_modeles`.

### diagnostic

`scribouille diagnostic [--materiel]` : version, mode (installée, portable, sources), dossiers, matériel, moteurs (CTranslate2, OpenVINO et ses périphériques), réglage effectif, modèles du catalogue et leur état, locuteurs, vocabulaire, verdict de campagne, durée prévue pour une heure, `pret` et `raisons`. Code 3 si pas prêt. `--materiel` relance d'abord la détection lente (cartes, NPU, OpenVINO).

### espace

Ce que Scribouille occupe, poste par poste : programme, chaque modèle, moteur Intel, locuteurs, caches (OpenVINO, pip), profil d'affichage, journaux, reprises, mesures, vocabulaire, réglages, sauvegardes, reste de l'ancien dossier `WhiScribe`, raccourcis et clé de la version installée. `liberable` : se libère sans rien perdre (caches, journaux, modèles que le réglage n'utilise pas, retéléchargés au besoin). Les transcriptions sont comptées à part (`transcriptions_octets`), jamais dans le total. `non_reconnus` : ce qui est dans nos dossiers sans être à nous, jamais touché.

### effacer

```
scribouille effacer CLE [CLE...] [--apercu] [--oui]
scribouille effacer --liberable [--apercu] [--oui]
scribouille effacer --complet [--avec-transcriptions] [--garder-programme] [--apercu] [--oui]
```

- `CLE` : clés de `espace` (`cache_openvino`, `journaux`, `modele:OpenVINO/whisper-large-v3-int8-ov`...).
- `--complet` : tout ce que Scribouille a écrit, sauf les transcriptions. Version installée : une fois la commande finie, le désinstalleur retire en silence le programme, ses raccourcis et sa clé de registre (`--garder-programme` l'évite). Version portable : le dossier du programme reste, à supprimer à la main.
- `--avec-transcriptions` : les transcriptions reconnues du dossier de sortie aussi (jamais les autres fichiers de ce dossier). Confirmation exigée comme le reste.
- Liste et tailles d'abord ; rien n'est fait sans `--oui` ou « oui » tapé dans un terminal. `--apercu` montre seulement.

### vocabulaire

```
scribouille vocabulaire etat
scribouille vocabulaire importer F.toml          propositions ou vocabulaire d'équipe, versés « à relire »
scribouille vocabulaire exporter F.toml [--ecraser]
scribouille vocabulaire appliquer TEXTE.txt (--sortie F.txt | --ecraser)
scribouille vocabulaire apprendre --brut B.txt --propre RELUE.txt [--cr CR] [--sortie F.toml] [--importer]
```

`appliquer` passe les corrections du vocabulaire effectif sur un texte existant et liste les remplacements. `apprendre` : par paires `--brut`/`--propre` (transcription brute, la même relue), `--cr` facultatif ; écrit des propositions à relire.

### agent

`scribouille agent afficher` : la fiche d'usage pour Claude Code ou Codex, avec les chemins du poste. `agent installer --cible claude|codex [--ecraser]` l'écrit dans `~/.claude/skills/scribouille/SKILL.md` ou `~/.codex/skills/scribouille/SKILL.md`.

### mesurer, materiel, donnees, verifier

Les outils de mesure, sous un même toit ; leurs options sont celles d'origine ([guide.fr.md](guide.fr.md)).

| Commande | Ancienne forme, toujours acceptée |
|---|---|
| `scribouille mesurer campagne [--appliquer] ...` | `--campagne ...` |
| `scribouille mesurer banc ...` | `--banc ...` |
| `scribouille mesurer rythmes ...` | `--banc --modes ...` |
| `scribouille mesurer endurance ...` | `--endurance ...` |
| `scribouille mesurer comparer FICHIER ...` | `--comparer FICHIER ...` |
| `scribouille mesurer vocabulaire ...` | `--mesurer-vocabulaire ...` |
| `scribouille vocabulaire apprendre ...` | `--apprendre-vocabulaire ...` |
| `scribouille materiel [detecter]` | `--detecter-materiel` |
| `scribouille materiel proposer [--appliquer]` | `--reconnaitre [--appliquer]` |
| `scribouille donnees revenir-whiscribe` | `--revenir-whiscribe` |
| `scribouille verifier` | `--verifier` (et `scribouille-verifier.exe` seul, avant la 2.5) |

## Sortie JSON

Schéma `scribouille.cli/1`. Une enveloppe par réponse :

```json
{"schema": "scribouille.cli/1", "commande": "diagnostic", "donnees": {"pret": true, "raisons": [], "...": "..."}}
{"schema": "scribouille.cli/1", "commande": "transcrire", "erreur": {"code": "modele_absent", "message": "...", "code_retour": 3, "suggestion": "relancer avec --telecharger ..."}}
```

`transcrire` et `reprendre` écrivent une ligne par événement :

| Événement | Champs |
|---|---|
| `debut` | `fichiers`, `version`, `preset`, `rythme`, `pour_une_heure` |
| `etat` | `id`, `etat` (decodage, transcription, locuteurs, ecriture, termine, annule, erreur), `message` |
| `progres` | `id`, `fichier`, `pct`, `phase`, `ecoule_s`, `reste_s` (une ligne par seconde au plus) |
| `journal` | `niveau` (info, ok, attention, erreur), `texte` : replis, reprises, plantages du moteur |
| `fichier_fini` | `id`, `fichier`, `sorties`, `json`, `duree`, `facteur`, `locuteurs`, `corrections` |
| `fichier_echec` | `id`, `fichier`, `annule`, `erreur`, `detail`, `reprise` |
| `fichier_ignore` | `fichier`, `raison` (`deja_transcrit`), `sorties` |
| `fin` | `reussis`, `echecs`, `annules`, `ignores`, `code_retour`, `fichiers` (un résultat par fichier) |

Résultat structuré : le compagnon `.json` (`format: scribouille-transcription`, version 1) ; `lire` en donne des pages :

```json
{"fichier": "...", "source": {"nom": "...", "chemin": "...", "duree": 43.58},
 "transcription": {"modele": "...", "langue": "fr", "temps_calcul": 6.1, "nb_locuteurs": 0, "corrections_appliquees": 0},
 "locuteurs": [],
 "segments": [{"rang": 0, "d": 0.0, "f": 6.52, "t": "...", "l": "Locuteur 1", "m": [{"t": "...", "d": 0.0, "f": 0.4, "p": 0.98}], "douteux": ["..."]}],
 "pagination": {"decalage": 0, "limite_mots": 2000, "suivant": null, "total": 12},
 "douteux": {"methode": "probabilite<0.5", "nombre": 3},
 "remplacements_vocabulaire": [{"s": 4, "o": 12, "a": "cube air nettesse", "b": "Kubernetes"}]}
```

`p` vaut -1 quand le moteur ne donne pas de probabilité (OpenVINO) : `douteux.methode` vaut alors `indisponible` et `nombre` `null`.

## Exemples

Sorties réelles du paquet gelé (turbo par CTranslate2, processeur, extrait FLEURS de 43 s) ; chemins raccourcis en `…`.

```
> scribouille transcrire point-hebdo.wav --preset rapide --json
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "debut", "fichiers": ["…\\point-hebdo.wav"], "version": "2.4.0", "preset": "rapide", "rythme": "vitesse", "pour_une_heure": "7 min 58"}
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "etat", "id": "c1", "etat": "decodage", "message": "Lecture du fichier"}
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "journal", "niveau": "info", "texte": "Modèle chargé en 2 s, transcription en cours."}
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "progres", "id": "c1", "fichier": "…\\point-hebdo.wav", "pct": 20, "phase": "Transcription", "ecoule_s": 11.9, "reste_s": 3.2}
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "fichier_fini", "id": "c1", "fichier": "…\\point-hebdo.wav", "ok": true, "sorties": ["…\\2026-11-12-point-hebdo.txt", "…\\2026-11-12-point-hebdo.json"], "json": "…\\2026-11-12-point-hebdo.json", "duree": "11 s", "facteur": 0.27, "locuteurs": 0, "corrections": 0}
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "fin", "reussis": 1, "echecs": 0, "annules": 0, "ignores": 0, "code_retour": 0, "fichiers": [...], "ignores_detail": []}
```

```
> scribouille transcrire point-hebdo.wav
point-hebdo.wav : déjà transcrit (2026-11-12-point-hebdo.json), --ecraser pour refaire
(code 4)

> scribouille lire 2026-11-12-point-hebdo.json --texte --limite 40
[00:00:02] Les plages sont nombreuses car Aokland est à cheval sur deux ports. Les plus populaires se trouvent dans trois zones.
[00:00:12] L'Amazone est également le fleuve le plus large de la planète, atteignant parfois 10 km de large.
... suite : --decalage 2
```

Plantage du moteur simulé à chaque essai (moteur factice des vérifications, depuis les sources), puis reprise :

```
> scribouille transcrire p.wav
  Le moteur de calcul s'est arrêté brutalement (code 3). La fenêtre n'est pas touchée.
  Le moteur de calcul s'est arrêté brutalement (code 3). La fenêtre n'est pas touchée.
  p.wav : le moteur s'est arrêté deux fois. La transcription reste reprenable.
[1/1] p.wav : échec : p.wav : le moteur s'est arrêté deux fois. La transcription reste reprenable.
(code 1)

> scribouille etat
Moteurs actifs : 0
Transcriptions reprenables : 1
  p.wav : 60 % (26 s sur 43 s), interrompue, clé 1273ad8298811040

> scribouille reprendre
Reprise de p.wav à 26 s sur 43 s.
[1/1] p.wav : fait en 1 s
    …6-11-12-p.txt
    …6-11-12-p.json
```

```
> scribouille effacer --liberable --apercu
À libérer : 30,2 Go
  Modèle bofenghuang/whisper-large-v3-french-distil-dec16              6,3 Go  libérable
  Modèle bofenghuang/whisper-large-v3-french                           5,9 Go  libérable
  Modèle bofenghuang/whisper-large-v3-distil-fr-v0.2                   4,2 Go  libérable
  ...
```

## Par SSH

Le serveur OpenSSH de Windows ouvre `cmd` : `scribouille` y résout `scribouille.com`. Une transcription longue survit à la déconnexion si elle est lancée en tâche planifiée (ci-dessous) ; lancée directement, elle s'arrête avec la session, et `reprendre` la poursuit.

```
ssh poste "C:\Users\moi\AppData\Local\Programs\Scribouille\scribouille.com" transcrire "D:\Réunions\point.m4a" --json
```

## En tâche planifiée

La ligne de commande n'a besoin ni de bureau ni de console (vérifié sur un bureau Windows invisible, sans console : `outils/verifier_moteur.py`).

```
schtasks /create /tn "Scribouille nuit" /sc daily /st 02:00 ^
  /tr "\"%LOCALAPPDATA%\Programs\Scribouille\scribouille.com\" transcrire \"D:\Réunions\" --json --rythme discret"
```

Ainsi créée, la tâche tourne quand l'utilisateur a une session ouverte ; pour qu'elle tourne session fermée, ajouter `/ru UTILISATEUR /rp` (« exécuter même si l'utilisateur n'est pas connecté »), si la politique du poste le permet. Pour garder la trace, rediriger dans un fichier : `/tr "cmd /c \"...scribouille.com\" transcrire ... --json > D:\Réunions\scribouille.ndjson"`. Les fichiers déjà transcrits sont sautés (code 4 s'il n'y avait rien d'autre).
