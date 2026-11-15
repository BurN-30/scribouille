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
| Plantage du moteur (pilote graphique, mémoire) | La fenêtre reste. Le fichier repart une fois, au segment près, sans la puce graphique si elle était en jeu (la ligne « Chargement du modèle » dit alors « sur le processeur »). Code de plantage (`0xC0000005`...) ou ouverture sur la puce de plus de 10 min : puce suspendue (`app/temoin_puce.py`). La borne part de l'ouverture réelle (message `moteur {etat: ouverture}`, posé avec le témoin) : le téléchargement du modèle n'y compte pas. Un verdict de plantage n'est jamais écrasé par une ouverture en cours ailleurs. Arrêt venu de dehors (Ctrl+C, console fermée, processus tué, poste éteint) : jamais pris pour un plantage, la prochaine ouverture réessaie la puce. Second plantage : fichier en erreur, reprenable. |
| Moteur muet 15 min (hors veille) | Arrêté, traité comme un plantage. |
| Retour de veille | Saut d'horloge reconnu, rien n'est arrêté ; si le pilote n'a pas survécu, repli d'OpenVINO ou plantage géré. |
| Deux Scribouille en même temps | Une seule fenêtre par dossier de données (mutex) ; ligne de commande libre ; un enregistrement n'est transcrit que par un processus (verrou `reprises\<empreinte>.en-cours` : PID et heure de création du processus, né complet par un lien ; repris si ce processus est mort, même quand son PID a été réattribué après un redémarrage). |
| Coupure de courant | Sorties écrites à côté, vidées sur le disque (`fsync`), puis renommées, avant l'effacement de la sauvegarde progressive. À la reprise, les segments se relisent ligne par ligne (une ligne abîmée est écartée et notée), une dernière ligne coupée est retirée avant d'écrire la suite ; une erreur de lecture du disque ne tronque jamais rien. |
| Fichier redéposé, `transcrire` relancé | Une transcription interrompue de ce fichier avec du travail gardé est poursuivie, jamais effacée en silence : la fenêtre la rattache et propose « Recommencer du début » ; la ligne de commande le dit, `--recommencer` repart du début. Même modèle seulement : avec un autre modèle, elle reste telle quelle pour `reprendre`. |
| Fenêtre fermée ou tuée | Le moteur meurt avec elle : objet de travail Windows (`KILL_ON_JOB_CLOSE`), surveillance du PID parent, fin de l'entrée standard. |

## Dossiers et ce qui est écrit où

| Emplacement | Contenu |
|---|---|
| Dossier du programme | `Scribouille.exe`, `scribouille.com`, `_internal\`. Rien n'y est écrit, sauf `emplacement-modeles.txt` par l'installeur. |
| `%LOCALAPPDATA%\Scribouille` (données ; `SCRIBOUILLE_DONNEES` l'impose) | `config.json`, `dossier-modeles.txt`, `vocabulaire.toml`, `vocabulaire.txt`, `corrections.txt`, `gabarit-ia.txt`, `calibration.json`, `materiel.json`, `logs\scribouille\` (nos journaux ; `logs\` lui-même peut tenir ceux d'une 2.x, jamais effacés), `reprises\`, `cache-openvino\`, `extensions-openvino\`, `extensions\`, `cache-pip\`, `paquets-hors-ligne\`, `rapports-banc\`, `comparaisons\`, `campagnes\`, `corpus-campagne\`, `webview\`, `historique-relecture\` (annulations et texte d'origine), `relecture-positions.json`, `exports.json` (empreintes des exports) |
| Dossier des modèles (`modeles\` par défaut, ou celui choisi) | Un dossier `models--<dépôt>` par modèle (cache Hugging Face), `convertis\` |
| Dossier de sortie, ou à côté de la source (ligne de commande) | `<date>-<nom>.txt`, `.json` (compagnon : segments, mots, probabilités, remplacements), `.srt`, `.vtt` |
| Version installée | Raccourcis du menu Démarrer et du bureau, clé `HKCU\...\Uninstall\{4E1B7C86-...}_is1` |

`app/inventaire.py` tient cette liste : `scribouille espace` la mesure, `scribouille effacer` ne supprime que ce qu'elle reconnaît. L'ancien dossier `%LOCALAPPDATA%\WhiScribe` (avant la 3.0) est repris au premier lancement (`app/migration.py`), jamais tant qu'une version 2.x est installée (`chemins.etat_version_2x`) : sa clé de désinstallation Inno (`Uninstall\{4E1B7C86-...}_is1`, HKCU ou HKLM, version 2.x, où qu'elle ait été installée) ou `Programs\WhiScribe\WhiScribe.exe` sans `Scribouille.exe` à côté. Un registre illisible, ou une clé sans version lisible, vaut présence. La 3.x travaille alors dans `WhiScribe`, partagé, si `Scribouille` n'a encore rien de nous, sinon dans `Scribouille`, et `WhiScribe` reste tel quel (`MIGRATION["etat"] = "bloquee"`). Un projet tiers homonyme y range ses modèles, ils ne sont jamais touchés. Non détectée : une 2.x portable décompressée ailleurs (ni clé, ni dossier habituel).

**Ce qui est effacé, et par qui.** Règle unique : la 3.x n'efface jamais ce qu'elle n'a pas écrit elle-même, ni sur une absence qui peut être passagère. D'office : ses vieux journaux (`journal.purger`, seulement `logs\scribouille\`, plus d'un mois et au-delà des 50 derniers), une partie de ses reprises orphelines (`reprise.purger`, à l'ouverture de la fenêtre, chacune notée au journal : verrous morts, écritures provisoires, plus de 30 jours, segments sans aucune ligne valide ; une source introuvable seulement si son dossier répond, datée au premier constat dans `<clé>.absente` et effacée 7 jours plus tard ; jamais une source sur un lecteur qui ne répond pas, ni un état illisible pour l'instant, ni des segments valides sans état lisible avant la rétention), sa propre sauvegarde progressive une fois les sorties sur le disque, son verrou et son témoin de chargement, ses fichiers provisoires, l'historique de relecture d'une transcription introuvable depuis 7 jours, dossier joignable (`lecture._elaguer_historique`, marque `absente-depuis.txt`), un modèle illisible juste avant de le retélécharger. Sur demande : `effacer`, `etat --nettoyer` (sauf une source sur un lecteur qui ne répond pas), retrait d'une extension, oubli du jeton ou des mesures, `--ecraser`, `transcrire --recommencer` et « Recommencer du début » (la reprise de ce fichier), `--recommencer` des mesures (l'endurance garde ses rapports). Réglages : une lecture refusée n'est jamais suivie d'une écriture (`config.sauver` refuse) ; un fichier abîmé est gardé sous `<nom>.illisible-<date>` avant d'être remplacé. Tant qu'une WhiScribe 2.x est installée, `WhiScribe` n'est dans aucun poste de `effacer` ; s'il est partagé (`chemins.donnees_partagees_ancienne_version`), ce que la 2.x écrit aussi (`migration.FICHIERS_2X`, `DOSSIERS_2X`) sort des postes de l'inventaire (`partages`) et le retrait des extensions est refusé ; dans `reprises\`, un état est à la 3.x s'il porte `auteur` ou la demande de départ (`reprise.etat_a_nous`), il s'appelle `<clé>.etat` (la 2.3.3 ne liste ni ne purge que `*.json` ; les états `.json` de la 3.x d'avant le 15/11 sont lus, puis renommés à la reprise), et les clés de la 3.x ne peuvent pas tomber sur celles d'une 2.x.

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
