# Ligne de commande

Tout ce que fait la fenêtre, sans fenêtre : par SSH, en tâche planifiée, par un agent de code. Aucun module d'interface n'est chargé (ni pywebview, ni WebView2) ; le calcul tourne dans le processus moteur, comme pour la fenêtre (voir [architecture.md](architecture.md)).

```
scribouille COMMANDE [options] [--json]
```

- Version installée ou portable : `scribouille.com` dans le dossier du programme. Dans `cmd` ou PowerShell, `scribouille` suffit depuis ce dossier (le `.com` passe avant le `.exe`) ; ailleurs, chemin complet ou dossier ajouté au `PATH`.
- Depuis les sources : `.venv\Scripts\python transcriber.pyw COMMANDE`.
- `scribouille aide` : le résumé de toutes les commandes ; `scribouille aide COMMANDE`, `scribouille COMMANDE --aide` (ou `-h`, `--help`) : les options d'une commande, générées depuis l'analyseur ; `scribouille version`.

## Garanties

- `scribouille.com` n'ouvre jamais la fenêtre : une commande inconnue, une faute de frappe, une option inconnue, une valeur manquante ou une combinaison contradictoire rendent un message sur la sortie d'erreur (et l'enveloppe d'erreur avec `--json`) et le code 2, sans rien faire. Seul `Scribouille.exe` ouvre la fenêtre.
- Aucun téléchargement sans `--telecharger`, aucun écrasement sans `--ecraser`, aucun effacement sans `--oui` (ou confirmation tapée dans un terminal).
- Aucun appel réseau hors téléchargement d'un modèle demandé.
- `transcrire` ne modifie jamais les réglages : ses options valent pour la commande seule.
- **Les commandes de lecture n'écrivent rien**, nulle part : ni réglages, ni journal, ni témoin, ni reprise de l'ancien dossier. Ce sont `version`, `aide` (et toute demande d'aide), `diagnostic`, `verifier` (et `--verifier`), `lire`, `espace`, `etat` sans `--nettoyer`, `agent afficher`, `reglages liste|lire`, `vocabulaire etat`, `materiel proposer` sans `--appliquer`, `materiel puce` sans `--lever`. `diagnostic --materiel` et `materiel detecter` relancent la détection : `materiel.json` n'est réécrit que s'il a changé. `effacer --apercu` n'efface rien.
- **WhiScribe 2.x encore installée**, qui lit le même dossier (`%LOCALAPPDATA%\WhiScribe`) : son `config.json` n'est jamais modifié, ni clé ajoutée ni clé retirée. Les réglages de la 3.x vont dans `config-scribouille.json`, à côté, et seulement ceux qui diffèrent ; une fois la 2.x partie, la première sauvegarde les reverse dans `config.json` (en gardant ses clés) et retire ce fichier.
- **Jamais d'effacement de ce qui n'est pas à Scribouille 3.x.** Ses journaux vont dans `logs\scribouille\` (une 2.x ne regarde pas les sous-dossiers de `logs\`) ; seuls ceux-là sont purgés, et doucement : rien de moins d'un mois, toujours les 50 derniers. Dans `reprises\`, une 2.x installée garde ses fichiers : la 3.x ne lit, ne propose et n'efface que les siens (états marqués). Ce que la 2.x écrit aussi (réglages, glossaire, jeton, modèles, extensions, caches) n'est dans aucun poste de `espace` et `effacer` : montré à part (`partages`), jamais effacé. Une fois la 2.x désinstallée, tout redevient à la 3.x. La 2.x est reconnue à sa clé de désinstallation (HKCU ou HKLM, version 2.x, où qu'elle ait été installée) ou à `Programs\WhiScribe\WhiScribe.exe` ; un registre illisible vaut présence. Tant qu'elle est là, `WhiScribe` n'est jamais repris ni effacé, même quand la 3.x travaille dans `Scribouille`.
- Chemins absolus dans les sorties JSON ; aucun texte transcrit dans les journaux.
- Ctrl+C ou Ctrl+Pause : arrêt propre, code 5, le travail fait reste sur le disque, `reprendre` le poursuit. Fermeture de la session SSH ou arrêt de la tâche : le moteur s'arrête avec la commande, le travail fait reste aussi sur le disque.

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
| `--moteur auto\|openvino\|ctranslate2` | `auto` (réglage du poste) | Moteur imposé pour cette commande ; OpenVINO absent ou périphérique non vu : code 3, rien n'est fait. |
| `--peripherique CPU\|GPU\|NPU` | `CPU` | Périphérique d'OpenVINO (implique `--moteur openvino`). |
| `--rythme vitesse\|equilibre\|discret\|auto` | réglage `rythme` | Part du poste laissée à l'utilisateur ; `auto` : rythme choisi quand le poste est occupé, vitesse maximale sinon. |
| `--locuteurs auto\|non\|N` | réglage `diarisation` | Séparation des locuteurs ; extension absente : code 3, rien n'est fait. |
| `--noms Alice,Bob` | | Noms des voix séparées, dans l'ordre (`Locuteur 1`, `Locuteur 2`...), ou `"Locuteur 2=Bob"` ; demande des voix séparées (`--locuteurs`, sinon code 2). Un nom sans voix détectée est dit (`journal`, `attention`). Annulable en relecture. |
| `--vocabulaire F.toml` | | Vocabulaire d'équipe en plus du personnel ; répétable. |
| `--sans-vocabulaire` | | Ni amorce ni corrections. |
| `--recursif` | | Sous-dossiers compris. |
| `--telecharger` | | Permet de télécharger un modèle absent. |
| `--ecraser` | | Refait un fichier déjà transcrit (ses anciennes sorties sont remplacées). |
| `--recommencer` | | Repart du début même si une transcription interrompue de ce fichier existe avec ce modèle (`reprise_abandonnee`) : elle n'est remplacée qu'au départ de la transcription, sous le verrou du fichier (rien n'est touché si un autre processus le transcrit). Une reprise d'un autre modèle, ou d'une version antérieure du fichier, reste telle quelle. |

Une transcription interrompue du même fichier (même taille, même date), avec le même modèle et au moins un segment gardé, est poursuivie par défaut, au segment près, et c'est dit (`reprise_trouvee`, `poursuivie: true`, et sur la sortie d'erreur) : relancer `transcrire` ne perd jamais le calcul déjà fait. Gardée avec un autre modèle, ou pour une version antérieure du fichier : elle reste telle quelle (`reprise_trouvee`, `poursuivie: false` ; autre modèle : `scribouille reprendre CLE` la poursuit), et ce fichier part du début avec le modèle demandé.

Une option demandée qu'on ne peut pas honorer n'est jamais ignorée : elle rend son code (2 ou 3) avant tout calcul. La même demande venue des réglages (réglage OpenVINO du poste) est dite (`journal`, niveau `attention`, et sur la sortie d'erreur), puis contournée. La séparation des voix cochée dans les réglages mais non installée (souvent héritée d'une 2.x, où elle était cochée par défaut) est dite une seule fois pour de bon ; ensuite, seulement `diagnostic` (`avertissements`) et, en JSON, le champ `locuteurs` de l'événement `debut`.

Puce graphique suspendue après un plantage (`materiel puce`) : `--moteur openvino --peripherique GPU`, nommés dans la commande, valent demande de réessai. L'ouverture repart sur la puce, dans le processus moteur et sous la garde du superviseur ; la commande le dit (`journal`, `attention`, et sur la sortie d'erreur) comme le journal ; un nouveau plantage la suspend de nouveau et le fichier repart sur le processeur. Sans `--peripherique`, la suspension tient.

Un fichier est « déjà transcrit » quand le dossier de sortie contient un compagnon `.json` qui le nomme : il est sauté (`fichier_ignore`), code 4 si rien d'autre n'a échoué.

### reprendre

```
scribouille reprendre [CLE|FICHIER] [--sortie D] [--formats LISTE] [--rythme vitesse|equilibre|discret|auto] [--telecharger]
```

Sans argument, la plus récente que personne ne transcrit en ce moment. La reprise rétablit tout ce que la demande de départ prévoyait : modèle (le texte ne mêle jamais deux modèles), formats, dossier de sortie, langue, vocabulaire, voix et leurs noms, rythme, moteur. `--sortie`, `--formats` et `--rythme` remplacent la valeur de départ. Une reprise laissée par la 3.0.0, qui ne gardait pas la demande, repart des réglages actuels, et le dit (`journal`, niveau `attention`).

Rien de reprenable, mais une transcription interrompue gardée parce que sa source est introuvable (lecteur réseau ou amovible qui ne répond pas, fichier déplacé) : code 2, erreur `source_introuvable`, avec pour chacune où la source était attendue et quoi faire (rebrancher le lecteur, remettre le fichier, puis `scribouille reprendre CLE`). Même réponse pour `reprendre CLE` qui désigne une telle reprise.

### etat

```
scribouille etat [--nettoyer]
```

Transcriptions reprenables, avec position, pourcentage, clé, `modele` (celui qui calcule vraiment : sur la puce, le modèle OpenVINO), `calcul` (`openvino-gpu`, `cpu`...) et `modele_demande` (celui du catalogue, d'après lequel `reprendre` rechoisit son réglage) : `interrompue`, ou `en_cours` (avec `pid`) quand un autre processus la transcrit en ce moment ; processus moteurs actifs (PID, mémoire). Une transcription coupée avant son premier segment (pendant la lecture de l'audio ou le chargement du modèle) est reprenable aussi : `depuis_debut` vaut `true`, `reprendre` la refait du début avec la demande de départ. Un échec (audio illisible, mémoire, deux plantages du moteur) avant le premier segment ne laisse rien à reprendre.

`puce` : l'état du témoin de la puce graphique, comme `materiel puce`.

`orphelines` : ce qui ne peut plus être repris, avec sa raison (`source_absente` : dossier joignable, fichier introuvable, avec `absente_depuis` et `source` ; `source_injoignable` : lecteur ou dossier qui ne répond pas, avec `source` ; `etat_illisible` et `segments_sans_etat`, avec `segments`, le nombre de lignes encore valides, et `segments_fichier` ; `trop_vieille` au-delà de 30 jours ; `verrou_mort` ; `provisoire`), `effacable` (`--nettoyer` l'efface) et `purgeable` (la fenêtre peut le faire seule) ; `gardees` : celles que `--nettoyer` laisse. La sortie texte les compte à part et dit, pour chaque gardée, où sa source était attendue (ou dans quel fichier est le texte déjà transcrit) et quoi faire. Un état qui ne se lit pas pour l'instant (accès refusé), ou des segments qui ne se lisent pas pour l'instant, ne sont pas listés. Un état perdu ou abîmé par une coupure se reconstruit avec la demande de départ (`<clé>.depart`) : la transcription reste dans les reprenables. Le verrou laissé par une coupure va avec sa transcription reprenable : il n'est pas une orpheline (`reprendre` le reprend puis le retire). Rien n'est effacé sans `--nettoyer`, qui garde toujours une source injoignable et des segments valides (redéposer le même fichier avec le même modèle les poursuit), et n'efface rien de ce qui a changé depuis le constat. La fenêtre, à son ouverture, n'efface que ce que rien ne peut rendre utile, chacune notée au journal : jamais une source injoignable ni des segments valides (avant 30 jours) ; une source introuvable est datée au premier constat et effacée 7 jours plus tard. Seuls les fichiers de la 3.x sont regardés (voir Garanties).

### lire

```
scribouille lire SORTIE.json|SORTIE.txt [--limite N] [--decalage N] [--depuis S] [--jusqua S] [--douteux] [--texte]
```

Lecture bornée d'un compagnon : au plus `--limite` mots (2 000 par défaut) à partir du segment `--decalage` ; `pagination.suivant` donne le décalage de la page suivante (`null` à la fin). `--douteux` : seulement les segments qui ont des mots sous le seuil (0,5), avec ces mots. `--texte` : texte lisible horodaté au lieu du JSON.

### exporter

```
scribouille exporter SORTIE.txt [--format md] [--remplacer | --nouveau]
```

Export Markdown à côté de la transcription (titre, repères, paragraphes avec heure et voix), le même que la relecture. Le `.txt` n'est jamais touché. Un export déjà là, écrit par Scribouille et resté intact, est remplacé ; retouché à la main ou venu d'ailleurs, il est gardé et l'export part dans une variante numérotée (`-2.md`), ce que la sortie dit (`remplace`, `variante`). `--remplacer` ou `--nouveau` forcent l'un ou l'autre.

### reglages

```
scribouille reglages [liste]
scribouille reglages lire CLE
scribouille reglages definir CLE=VALEUR [CLE=VALEUR...]
scribouille reglages defaut CLE [CLE...]
scribouille reglages decrire [CLE=VALEUR...|proposition|banc|automatique]
```

Actions : `liste` (défaut), `lire`, `definir`, `defaut`, `decrire`. Une clé inconnue fait tout refuser, rien n'est changé.

`decrire` dit ce que la transcription appliquerait réellement sur ce poste, avec les mêmes lignes que la fiche « ce que ça change » de la fenêtre (`app/description_reglage.py`), sans rien enregistrer ni écrire :

- **ce qui calcule** : modèle (et fichier chargé), moteur (CTranslate2 ou OpenVINO), périphérique (processeur, puce graphique, NPU, carte NVIDIA), précision (int8, float16), faisceau (et pourquoi : glouton imposé sur la puce, faisceau du réglage mesuré du poste), lots (et ce qui les borne : mémoire vive, rythme, banc), texte précédent, garde-fous ;
- **le rythme** : fils de calcul sur combien de processeurs logiques, priorité du processus, énergie (HighQoS, EcoQoS), lectures et écritures, cœurs permis, propriétés demandées à OpenVINO, pauses, adaptation automatique (quand elle bascule, ce qui est fixé au chargement), garde de la mémoire (seuils en Go) ;
- **le coût sur ce poste** : durée pour une heure d'audio (la même que les cartes de la fenêtre) et d'où elle vient (mesurée sur ce poste, avec les minutes et leur poids, ou estimation), effet du rythme (coefficient mesuré ou de repli), mémoire au pic, processeur ;
- **la justesse mesurée** : seulement les chiffres que Scribouille possède, avec ce sur quoi ils ont été mesurés ; aucune ligne inventée ;
- **ce qui est allégé pour gagner du temps**, et ce que les mesures en disent.

Sans argument : le réglage en service. Paires `CLE=VALEUR` (rien n'est enregistré) : `preset`, `rythme`, `rythme_auto`, `moteur`, `peripherique`, `mode_avance`, `modele_avance`, `beam_size`, `forcer_processeur`, `condition_on_previous_text`. Mots : `proposition` (le réglage proposé pour ce poste, tel que `materiel proposer` le poserait une fois appliqué), `banc` (le conseil du dernier banc d'essai ; code 2 s'il n'y en a pas), `automatique` (le réglage du poste remis à l'automatique). Exemples : `scribouille reglages decrire preset=qualite rythme=vitesse --json` (le texte le plus juste, au plus vite) ; `scribouille reglages decrire moteur=openvino peripherique=GPU`. En JSON : `donnees.fiche` porte le plan structuré (`modele`, `modele_calcule`, `moteur`, `peripherique`, `precision`, `faisceau`, `lots`, `rythme`, `garde_memoire`, `cout`...) et `sections` (`titre`, `lignes` de `libelle` et `valeur`), dans la langue de l'interface.

Chaque réglage, sa valeur par défaut et son effet : [reglages.md](reglages.md). Pseudo-clés : `moteur`, `peripherique`, `dossier_modeles`.

### diagnostic

`scribouille diagnostic [--materiel]` : version, mode (installée, portable, sources), dossiers, matériel, moteurs (CTranslate2, OpenVINO et ses périphériques), réglage effectif, modèles du catalogue et leur état, locuteurs, vocabulaire, verdict de campagne, durée prévue pour une heure, `puce` (témoin de la puce graphique, voir `materiel puce`), `donnees_partagees` (l'exécutable d'une WhiScribe 2.x qui lit le même dossier, sinon vide), `donnees_raison` (où sont les données et pourquoi : « Données gardées dans … : la version installée … le lit encore », la phrase du journal, aussi dans la sortie texte), `cache_openvino` (cache de compilation d'OpenVINO : `octets`, `nombre` de fichiers, `compiles`, `noyaux`, `reconnues` et `reconnues_octets` comme écrites par la 3.x, `non_reconnues_octets`, `reglages` notés, `dernier_usage`, `delai_jours`, `plafond_octets` ; une ligne dans la sortie texte s'il n'est pas vide), `pret` et `raisons`, `avertissements` (ce qui ne bloque pas mais change le résultat : puce suspendue ou à vérifier, séparation des voix cochée mais non installée). Code 3 si pas prêt. `--materiel` relance d'abord la détection lente (cartes, NPU, OpenVINO).

### espace

`scribouille espace` : ce que Scribouille occupe, poste par poste : programme, chaque modèle, moteur Intel, locuteurs, caches (OpenVINO, pip), profil d'affichage, journaux, reprises, mesures, vocabulaire, réglages, sauvegardes, reste de l'ancien dossier `WhiScribe`, raccourcis et clé de la version installée. `liberable` : se libère sans rien perdre (caches, journaux, modèles que le réglage n'utilise pas, retéléchargés au besoin). Les transcriptions sont comptées à part (`transcriptions_octets`), jamais dans le total. `non_reconnus` : ce qui est dans nos dossiers sans être à nous, jamais touché. `partages` (avec `partage_avec`) : ce qu'une WhiScribe 2.x installée, qui lit le même dossier, écrit aussi ; jamais libéré ni effacé tant qu'elle est là. Une 2.3.3 (ou antérieure) reconnue par sa clé de désinstallation n'a pas de moteur OpenVINO : le cache et le moteur d'OpenVINO, `calibration.json` et le témoin de la puce sont alors à la 3.x seule ; avec une 2.4 (ou une détection incertaine), ils restent partagés, et le poste `cache_openvino` ne tient que les entrées notées par la 3.x.

Le cache d'OpenVINO se borne tout seul (`app/cache_openvino.py`) : à l'ouverture de la fenêtre et avant une transcription en ligne de commande, les entrées d'un réglage inutilisé depuis 30 jours, et celles d'avant ce suivi 30 jours après leur premier constat, partent ; au-delà de 4 Go, les moins utiles partent d'abord, jamais le réglage le plus récent. Jamais pendant un calcul (marque d'usage d'un processus vivant), jamais une entrée écrite dans la journée, jamais ce qui n'est pas reconnu. `effacer cache_openvino` le libère tout de suite (refusé pendant un calcul) ; le prochain chargement sur la puce reprend 40 s à 2 min.

### effacer

```
scribouille effacer CLE [CLE...] [--apercu] [--oui]
scribouille effacer --liberable [--apercu] [--oui]
scribouille effacer --complet [--avec-transcriptions] [--garder-programme] [--resume F] [--apercu] [--oui]
```

- `CLE` : clés de `espace` (`cache_openvino`, `journaux`, `modele:OpenVINO/whisper-large-v3-int8-ov`...).
- `--complet` : tout ce que Scribouille a écrit, sauf les transcriptions. Version installée : une fois la commande finie, le désinstalleur retire en silence le programme, ses raccourcis et sa clé de registre (`--garder-programme` l'évite). Version portable : le dossier du programme reste, à supprimer à la main.
- `--avec-transcriptions` : les transcriptions reconnues du dossier de sortie aussi (jamais les autres fichiers de ce dossier). Confirmation exigée comme le reste.
- `--resume F` : écrit dans `F` le résumé que le désinstalleur montre avant sa question (usage interne de `setup.iss`).
- Liste et tailles d'abord ; rien n'est fait sans `--oui` ou « oui » tapé dans un terminal. `--apercu` montre seulement.

### vocabulaire

```
scribouille vocabulaire [etat]
scribouille vocabulaire importer F.toml          propositions ou vocabulaire d'équipe, versés « à relire »
scribouille vocabulaire exporter F.toml [--ecraser]
scribouille vocabulaire appliquer TEXTE.txt (--sortie F.txt | --ecraser)
scribouille vocabulaire apprendre --brut B.txt --propre RELUE.txt [--cr CR] [--sortie F.toml] [--importer]
scribouille vocabulaire retirer-exemples | remettre-exemples
```

`appliquer` passe les corrections du vocabulaire effectif sur un texte existant et liste les remplacements. `apprendre` : par paires `--brut`/`--propre` (transcription brute, la même relue), `--cr` facultatif ; écrit des propositions à relire.

`retirer-exemples` : `vocabulaire.txt` et `corrections.txt` restés tels que les versions 1.x à 2.3 les livraient, avec leurs exemples fictifs actifs (Jean Dupont, MonEntreprise...), envoyés au modèle à chaque transcription, reprennent le modèle actuel (exemples en commentaire) ; l'ancien contenu est gardé dans `vocabulaire-exemples-anciens.txt` et `corrections-exemples-anciens.txt`. Un fichier retouché n'est jamais touché. `remettre-exemples` le défait (sauf un fichier retouché depuis, dit). `vocabulaire etat` dit ce qui reste (`exemples_anciens`). La fenêtre fait ce retrait à son ouverture et l'annonce (avec « Remettre ») ; quand une version 2.x installée (WhiScribe) lit le même dossier de données, elle le propose seulement. La ligne de commande ne le fait jamais d'office.

### agent

`scribouille agent [afficher]` : la fiche d'usage pour Claude Code ou Codex, avec les chemins du poste. `agent installer --cible claude|codex [--dossier D] [--ecraser]` l'écrit dans `~/.claude/skills/scribouille/SKILL.md` ou `~/.codex/skills/scribouille/SKILL.md` ; `--dossier` remplace le dossier personnel `~`.

### mesurer

`scribouille mesurer campagne|banc|rythmes|endurance|comparer|vocabulaire [options]` : les outils de mesure, sous un même toit ; leurs options sont celles d'origine, détaillées dans [guide.fr.md](guide.fr.md). Une option qu'un outil ne connaît pas est refusée (code 2). Avec `--json`, le texte de l'outil part sur la sortie d'erreur et l'enveloppe donne son code (`code_retour`).

| Outil | Options |
|---|---|
| `campagne` | `--appliquer`, `--corpus`, `--debut`, `--duree`, `--limite-extraits`, `--peripherique`, `--proprietes-ov`, `--recommencer`, `--reglages`, `--reunion`, `--sans-temoin`, `--telecharger` |
| `banc` | `--appliquer`, `--npu`, `--telecharger` |
| `rythmes` | `--moteur`, `--peripherique`, `--repetitions`, `--rythmes`, `--sans-enregistrer`, `--sans-temoin-passif`, `--variantes-ov` |
| `endurance` | `--corpus`, `--memoire-libre`, `--passages`, `--peripherique`, `--pression`, `--recommencer`, `--reglage` |
| `comparer FICHIER` | `--debut`, `--duree`, `--faisceau-ctranslate2`, `--faisceau-openvino`, `--glossaire`, `--ouvrir`, `--peripherique`, `--preset`, `--reference`, `--sans-corrections`, `--sans-glossaire`, `--sortie` |
| `vocabulaire` | `--corpus`, `--corpus-paquet`, `--peripherique`, `--recommencer`, `--reference`, `--reglage`, `--reunion`, `--vocabulaire` |

### materiel

`scribouille materiel [detecter]` : relance la détection lente (cartes, NPU, OpenVINO) et l'écrit dans `materiel.json`. `scribouille materiel proposer [--appliquer]` : le poste, le réglage proposé et pourquoi ; `--appliquer` l'enregistre. Ce que ce réglage changerait, ligne à ligne (moteur, périphérique, faisceau, fils, durée, justesse) : `scribouille reglages decrire proposition`.

`scribouille materiel puce [--lever]` : le témoin de la puce graphique (`openvino-chargement-en-cours.txt`), posé pendant chaque ouverture d'un modèle sur la puce ou le NPU. `etat` vaut :

| `etat` | Sens | La puce sert-elle ? |
|---|---|---|
| `libre` | Pas de témoin. | Oui. |
| `en_cours` | Une ouverture se fait en ce moment dans un autre processus (`pid`, vivant). | Oui. |
| `a_verifier` | Une ouverture n'a pas abouti sans plantage prouvé : processus tué, console fermée, poste éteint (`origine` : `coupure`, `extinction`), témoin d'une version antérieure (`ancien_format`), ou plantage d'avant une mise à jour de Scribouille, d'OpenVINO ou du pilote graphique (`mise_a_jour`). | Oui : la prochaine ouverture tranche, dans le processus moteur, sous la garde du superviseur. |
| `suspendue` | Le moteur est mort sur la puce avec un code de plantage (`code`, par exemple `0xC0000005`), ou son ouverture a dépassé 10 min (`cause` : `blocage`). | Non, d'office : CTranslate2 sur le processeur. La puce nommée dans la commande `transcrire` elle-même vaut demande de réessai, sous garde, et c'est dit (voir `transcrire`). |

Un arrêt venu de dehors (Ctrl+C, console fermée, `0xC000013A`, arrêt par un autre programme) n'est jamais pris pour un plantage. `--lever` lève la suspension : la prochaine ouverture réessaie la puce, protégée (un nouveau plantage la suspend de nouveau et le fichier repart sur le processeur). La fenêtre a le même bouton (Réglages, Poste, « Réessayer la puce graphique »).

**Essai du repli sur une vraie machine** : `set SCRIBOUILLE_ESSAI_PUCE=plantage` avant une commande fait tomber le moteur au moment d'ouvrir la puce ou le NPU, comme une violation d'accès du pilote ; `erreur` lui fait lever une erreur (repli propre), `blocage` l'arrête net (borné par la garde). Sans la variable, rien ne change ; le journal dit chaque échec simulé. Exemple : `set SCRIBOUILLE_ESSAI_PUCE=plantage`, puis une transcription sur la puce (réglage du poste, ou la puce imposée à `transcrire`) : le fichier est fait sur le processeur, `materiel puce` dit `suspendue`, `materiel puce --lever` la lève.

### donnees

`scribouille donnees revenir-whiscribe` : remet les données dans l'ancien dossier `WhiScribe`, pour revenir à une version antérieure à la 2.4.

### verifier

`scribouille verifier` : bilan de l'installation (imports, décodeur, droit d'écrire dans les dossiers, vérifié sans rien écrire) ; code 3 si quelque chose manque. Le dossier de données est dit avec sa raison quand il n'est pas le dossier habituel (« Données gardées dans … » : partagé avec une 2.x). La ligne du matériel distingue les fils logiques du poste et les fils de calcul (sur un Core Ultra 5 225U : 14 fils logiques, 12 cœurs, calcul sur 10 fils au plus, un par cœur performant ou efficace).

### aide, version

`scribouille aide [COMMANDE]` ; `scribouille version`.

### Anciennes formes

Toujours acceptées, telles quelles, par `scribouille.com` :

| Commande | Ancienne forme |
|---|---|
| `mesurer campagne [--appliquer] ...` | `--campagne ...` |
| `mesurer banc ...` | `--banc ...` |
| `mesurer rythmes ...` | `--banc --modes ...` |
| `mesurer endurance ...` | `--endurance ...` |
| `mesurer comparer FICHIER ...` | `--comparer FICHIER ...` |
| `mesurer vocabulaire ...` | `--mesurer-vocabulaire ...` |
| `vocabulaire apprendre ...` | `--apprendre-vocabulaire ...` |
| `materiel [detecter]` | `--detecter-materiel` |
| `materiel proposer [--appliquer]` | `--reconnaitre [--appliquer]` |
| `materiel puce [--lever]` | (nouvelle en 3.0) |
| `donnees revenir-whiscribe` | `--revenir-whiscribe` |
| `verifier` | `--verifier` (et `scribouille-verifier.exe` seul, avant la 3.0) |

## Plusieurs Scribouille en même temps

- Une seule **fenêtre** par dossier de données : la seconde ramène la première au premier plan et se ferme.
- La **ligne de commande** reste libre pendant que la fenêtre est ouverte. Réglages, vocabulaire et reprises sont partagés ; la fenêtre relit les réglages du disque avant d'écrire les siens.
- Un **même enregistrement** n'est transcrit que par un processus à la fois : le second s'arrête (`fichier_echec`, code 1) avec « Déjà en cours ailleurs ». Le verrou d'un processus disparu est repris.

## Sortie JSON

Schéma `scribouille.cli/1`. Une enveloppe par réponse :

```json
{"schema": "scribouille.cli/1", "commande": "diagnostic", "donnees": {"pret": true, "raisons": [], "...": "..."}}
{"schema": "scribouille.cli/1", "commande": "transcrire", "erreur": {"code": "modele_absent", "message": "...", "code_retour": 3, "suggestion": "relancer avec --telecharger ..."}}
```

`transcrire` et `reprendre` écrivent une ligne par événement :

| Événement | Champs |
|---|---|
| `debut` | `fichiers`, `version`, `preset`, `rythme`, `pour_une_heure`, `locuteurs` (`demandes`, `disponibles`) |
| `etat` | `id`, `etat` (decodage, transcription, locuteurs, ecriture, termine, annule, erreur), `message` |
| `progres` | `id`, `fichier`, `pct`, `phase`, `ecoule_s`, `reste_s` (une ligne par seconde au plus) |
| `journal` | `niveau` (info, ok, attention, erreur), `texte` : replis, reprises, plantages du moteur |
| `fichier_fini` | `id`, `fichier`, `sorties`, `json`, `duree`, `facteur`, `locuteurs`, `corrections` |
| `fichier_echec` | `id`, `fichier`, `annule`, `erreur`, `detail`, `reprise` |
| `fichier_ignore` | `fichier`, `raison` (`deja_transcrit`), `sorties` |
| `reprise_trouvee` | `fichier`, `cle`, `poursuivie` (vrai : même modèle, poursuivie ; faux : autre modèle, gardée), `position_s` ou `modele` |
| `reprise_abandonnee` | `fichier`, `cles` (`--recommencer`) |
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

Les mots `m` d'un segment, mis bout à bout, redonnent son texte `t` au caractère près (blancs mis à part), et aucun ne contient de blanc ; c'est tenu à l'écriture et après chaque modification faite en relecture. Un mot écrit par le vocabulaire porte `c: 1` et `p: -1`.

## Exemples

Sorties réelles du paquet gelé (turbo par CTranslate2, processeur, extrait FLEURS de 43 s) ; chemins raccourcis en `…`.

```
> scribouille transcrire point-hebdo.wav --preset rapide --json
{"schema": "scribouille.cli/1", "commande": "transcrire", "evenement": "debut", "fichiers": ["…\\point-hebdo.wav"], "version": "3.0.0", "preset": "rapide", "rythme": "vitesse", "pour_une_heure": "7 min 58"}
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
  p.wav : 60 % (26 s sur 43 s), interrompue, modèle deepdml/faster-whisper-large-v3-turbo-ct2 (cpu), clé 1273ad8298811040

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
