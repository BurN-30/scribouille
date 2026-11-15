# Architecture

Deux processus. La fenêtre (ou la ligne de commande) ne calcule jamais ; le moteur calcule et rien d'autre.

```
Scribouille.exe (fenêtre)            scribouille.com transcrire ... (ligne de commande)
  pywebview + WebView2                 aucun module d'interface
  file, historique, réglages           file, progression, codes de retour
        │                                      │
        └──── superviseur (app/superviseur.py) ┘
                     │  JSON par lignes, stdin / stdout, protocole 1
                     ▼
        scribouille.com --moteur (app/moteur_processus.py)
          décodage (PyAV), CTranslate2 ou OpenVINO, locuteurs,
          vocabulaire, écriture des sorties, sauvegarde par segment
```

Depuis les sources, `transcriber.pyw` joue les trois rôles : sans argument la fenêtre, avec une commande la ligne de commande, avec `--moteur` le moteur.

## Cycle de vie du moteur

- Lancé à la première file, ou pour lire la durée des fichiers ajoutés (il s'arrête alors après 30 s sans file).
- Une file : `ouvrir` (réglages, rythme, moteur de calcul), un `traiter` par fichier, `fermer`, puis `quitter`. Le modèle reste chargé d'un fichier à l'autre ; il est rendu avant la séparation des locuteurs, après un échec, sous 2 Go de mémoire libre, et avec le processus en fin de file : la fenêtre revient à sa mémoire de repos.
- Le rythme (priorité, EcoQoS, affinité, pauses) et la demande « pas de mise en veille » s'appliquent au moteur seul.

## Protocole (version 1)

Une ligne JSON par message, UTF-8. Ordres sur l'entrée standard du moteur, chacun avec un numéro `n` repris dans la réponse : `ouvrir {config, options}`, `traiter {element}`, `fermer`, `durees {elements}`, `quitter`. Événements sur la sortie standard : `pret {protocole, version, pid}` (premier message), `vie` (toutes les 5 s), `moteur {etat, modele, peripherique, sur_puce}`, `etat`, `progression`, `journal`, `reprise {id, cle}`, `termine`, puis les réponses `ouvert`, `fini {statut, element}`, `ferme`, `durees`, ou `erreur`. Détail : en-tête de `app/protocole.py`.

Pourquoi les flux standard : pas de port à ouvrir ni à protéger, pas de fichier partagé, le canal meurt avec le processus, et une fin de flux dit au moteur que son parent est parti. La sortie standard du moteur est réservée au protocole (le descripteur 1 est redirigé vers l'erreur standard au démarrage). Sous Windows, le moteur ne laisse jamais de lecture en attente sur son entrée (`PeekNamedPipe`) : une lecture synchrone suspendue bloque le chargement des DLL dans les autres fils.

Une clé ajoutée ne change pas la version ; une clé retirée ou un sens changé, si. Le parent refuse un moteur d'une autre version.

## Garanties

| Situation | Effet |
|---|---|
| Annulation | Le processus est arrêté (TerminateProcess), quelle que soit la phase : quelques millisecondes. Le fichier finit « arrêté », sa reprise intacte. |
| Plantage du moteur (pilote graphique, mémoire) | La fenêtre reste. Le fichier repart une fois, au segment près, sans la puce graphique si elle était en jeu. Code de plantage (`0xC0000005`...) ou ouverture sur la puce de plus de 10 min : puce suspendue (`app/temoin_puce.py`). Arrêt venu de dehors (Ctrl+C, console fermée, processus tué, poste éteint) : jamais pris pour un plantage, la prochaine ouverture réessaie la puce. Second plantage : fichier en erreur, reprenable. |
| Moteur muet 15 min (hors veille) | Arrêté, traité comme un plantage. |
| Retour de veille | Saut d'horloge reconnu, rien n'est arrêté ; si le pilote n'a pas survécu, repli d'OpenVINO ou plantage géré. |
| Deux Scribouille en même temps | Une seule fenêtre par dossier de données (mutex) ; ligne de commande libre ; un enregistrement n'est transcrit que par un processus (verrou `reprises\<empreinte>.en-cours`, repris si son PID est mort). |
| Fenêtre fermée ou tuée | Le moteur meurt avec elle : objet de travail Windows (`KILL_ON_JOB_CLOSE`), surveillance du PID parent, fin de l'entrée standard. |

## Dossiers et ce qui est écrit où

| Emplacement | Contenu |
|---|---|
| Dossier du programme | `Scribouille.exe`, `scribouille.com`, `_internal\`. Rien n'y est écrit, sauf `emplacement-modeles.txt` par l'installeur. |
| `%LOCALAPPDATA%\Scribouille` (données ; `SCRIBOUILLE_DONNEES` l'impose) | `config.json`, `dossier-modeles.txt`, `vocabulaire.toml`, `vocabulaire.txt`, `corrections.txt`, `gabarit-ia.txt`, `calibration.json`, `materiel.json`, `logs\scribouille\` (nos journaux ; `logs\` lui-même peut tenir ceux d'une 2.x, jamais effacés), `reprises\`, `cache-openvino\`, `extensions-openvino\`, `extensions\`, `cache-pip\`, `paquets-hors-ligne\`, `rapports-banc\`, `comparaisons\`, `campagnes\`, `corpus-campagne\`, `webview\`, `historique-relecture\` (annulations et texte d'origine), `relecture-positions.json`, `exports.json` (empreintes des exports) |
| Dossier des modèles (`modeles\` par défaut, ou celui choisi) | Un dossier `models--<dépôt>` par modèle (cache Hugging Face), `convertis\` |
| Dossier de sortie, ou à côté de la source (ligne de commande) | `<date>-<nom>.txt`, `.json` (compagnon : segments, mots, probabilités, remplacements), `.srt`, `.vtt` |
| Version installée | Raccourcis du menu Démarrer et du bureau, clé `HKCU\...\Uninstall\{4E1B7C86-...}_is1` |

`app/inventaire.py` tient cette liste : `scribouille espace` la mesure, `scribouille effacer` ne supprime que ce qu'elle reconnaît. L'ancien dossier `%LOCALAPPDATA%\WhiScribe` (avant la 3.0) est repris au premier lancement (`app/migration.py`), sauf tant qu'une version 2.x installée le lit encore (`chemins._garder_ancien_dossier` : la 3.0 y travaille alors, partagé) ; un projet tiers homonyme y range ses modèles, ils ne sont jamais touchés.

**Ce qui est effacé, et par qui.** Règle unique : la 3.x n'efface jamais ce qu'elle n'a pas écrit elle-même. D'office : ses vieux journaux (`journal.purger`, seulement `logs\scribouille\`, plus d'un mois et au-delà des 50 derniers), ses reprises orphelines (`reprise.purger`, à l'ouverture de la fenêtre, chacune notée au journal), sa propre sauvegarde progressive une fois le fichier fini, son verrou et son témoin de chargement, ses fichiers provisoires, l'historique de relecture d'une transcription disparue, un modèle illisible juste avant de le retélécharger. Sur demande : `effacer`, `etat --nettoyer`, retrait d'une extension, oubli du jeton ou des mesures, `--ecraser`, `--recommencer` des mesures. Tant qu'une WhiScribe 2.x installée partage le dossier (`chemins.donnees_partagees_ancienne_version`), ce qu'elle écrit aussi (`migration.FICHIERS_2X`, `DOSSIERS_2X`) sort des postes de l'inventaire (`partages`) et le retrait des extensions est refusé ; dans `reprises\`, un état est à la 3.x s'il porte `auteur` ou la demande de départ (`reprise.etat_a_nous`), et les clés de la 3.x ne peuvent pas tomber sur celles d'une 2.x.

## Repères dans le code

| Fichier | Rôle |
|---|---|
| `transcriber.pyw` | Point d'entrée, aiguillage, passerelle de la fenêtre (`Passerelle`) |
| `app/superviseur.py` | Lance, pilote, surveille, arrête le moteur |
| `app/temoin_puce.py` | Témoin de la puce graphique : en cours, à vérifier, suspendue après un plantage constaté |
| `app/moteur_processus.py` | Boucle du moteur, relais des rappels en messages |
| `app/protocole.py` | Messages et version |
| `app/traitement.py` | La file : `ouvrir_file`, `traiter_element`, `fermer_file` ; locale ou distante |
| `app/processus.py` | Objet de travail Windows, surveillance du parent, mesure mémoire et processeur |
| `app/cli.py` | Ligne de commande |
| `app/inventaire.py` | Inventaire, libération, effacement |
| `app/instance.py` | Fenêtre unique, verrou d'un fichier en cours |
| `app/lecture.py`, `app/relecture.py` | Relecture : situer, corriger, annuler, exporter |
