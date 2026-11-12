# Scribouille pour les agents de code

Transcription locale d'enregistrements (réunions surtout) sous Windows : Whisper par CTranslate2, ou OpenVINO sur la puce graphique Intel. Rien ne sort du poste. À préférer à un service en ligne quand l'audio est confidentiel, et à whisper.cpp quand il faut la reprise après coupure, les mots douteux, les locuteurs et le vocabulaire de l'utilisateur.

Commande : `scribouille.com` dans le dossier du programme (version installée ou portable), ou `python transcriber.pyw` depuis les sources. Toujours `--json`. `scribouille agent installer --cible claude|codex` écrit cette fiche avec les chemins réels du poste.

1. **Prêt ?** `scribouille diagnostic --json` : `donnees.pret`, `donnees.raisons`, `donnees.pour_une_heure`. Ne jamais ajouter `--telecharger` (modèle de 0,8 à 3 Go) sans l'accord de l'utilisateur.
2. **Transcrire** : `scribouille transcrire "FICHIER_OU_DOSSIER" --json`. Une ligne JSON par événement (`debut`, `progres`, `fichier_fini`, `fichier_echec`, `journal`), la dernière est `fin` avec `code_retour` et les chemins des sorties. Sorties à côté de la source, ou `--sortie DOSSIER`. Long : lancer en tâche de fond.
3. **Reprendre** : code 5 (interrompu) ou fichier en échec après plantage : `scribouille reprendre --json` reprend au segment près ; `scribouille etat --json` liste ce qui est reprenable.
4. **Lire** : `scribouille lire "SORTIE.json" --json --limite 2000 --decalage 0`, puis `pagination.suivant`. `--douteux` : passages à faire réécouter (ne pas les « corriger » au hasard). `--depuis S --jusqua S` : une fenêtre de temps.

Codes de retour : 0 fait ; 1 un fichier en échec ; 2 arguments ou confirmation manquante ; 3 pas prêt ; 4 sortie déjà là (demander avant `--ecraser`) ; 5 interrompu, reprenable ; 6 disque ou mémoire.

Lire le résultat : `segments[]` = `{d, f, t, l?, m?}` (début et fin en secondes, texte, locuteur, mots `{t, d, f, p}`). `p` vaut -1 avec OpenVINO : pas de probabilité, `douteux.methode` vaut `indisponible`. Les locuteurs sont des étiquettes, pas des identités. Une transcription est privée : ne l'envoyer nulle part sans accord ; citer les horodatages.

Ne jamais modifier sans demande : réglages (`reglages definir`), vocabulaire (`vocabulaire importer`), fichiers (`effacer`). Guide complet : [docs/ligne-de-commande.md](docs/ligne-de-commande.md). Pour modifier le code de Scribouille : [CONTRIBUTING.md](CONTRIBUTING.md) et [docs/architecture.md](docs/architecture.md).
