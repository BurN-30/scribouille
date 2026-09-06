[English](README.md) · **Français**

# Scribouille

Transformez vos enregistrements en texte sur votre propre machine. Pas de compte, pas de cloud, aucun envoi.

[![Version](https://img.shields.io/github/v/release/BurN-30/scribouille?label=release)](https://github.com/BurN-30/scribouille/releases)
[![Licence : MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Plateforme : Windows](https://img.shields.io/badge/platform-Windows%2064--bit-lightgrey)

Scribouille est une application de bureau Windows bâtie sur [faster-whisper](https://github.com/SYSTRAN/faster-whisper). Vous glissez des fichiers audio sur la fenêtre, vous récupérez des fichiers texte à côté. Elle a été écrite pour les réunions : audio de salle, plusieurs voix, noms propres et jargon maison. L'interface existe en français et en anglais.

<!-- capture 1 : fenêtre principale, thème sombre, zone de dépôt vide, carte matériel visible -->

---

## Installation

1. Téléchargez **`Scribouille-Setup-X.Y.Z.exe`** depuis la page [Releases](https://github.com/BurN-30/scribouille/releases).
2. Lancez-le.
3. Ouvrez **Scribouille** depuis le menu Démarrer.

Rien d'autre à installer. L'installation se fait par utilisateur, **sans droits administrateur**, dans `%LOCALAPPDATA%\Programs\Scribouille`. Vos réglages, votre glossaire et vos journaux vivent dans `%LOCALAPPDATA%\WhiScribe`, jamais dans le dossier du programme : réinstaller une version plus récente par-dessus l'ancienne ne fait donc rien perdre.

> **L'application s'appelait WhiScribe jusqu'à la 2.3.3.** Le nom du dépôt a changé, les anciennes adresses redirigent. Sur un poste déjà équipé, la mise à jour se pose par-dessus l'installation existante, dans son dossier d'origine `%LOCALAPPDATA%\Programs\WhiScribe`, et le dossier de données garde lui aussi son nom : rien n'est à déplacer, rien n'est perdu.

L'assistant demande **où ranger les modèles de transcription**, de 1,6 à 3,1 Go selon le preset. Les modèles ne sont pas embarqués : ils se téléchargent une seule fois, au premier usage, et l'application annonce la taille avant de commencer. Ensuite elle fonctionne hors connexion.

Le programme d'installation n'est pas signé, SmartScreen peut donc avertir au premier lancement : « Informations complémentaires », puis « Exécuter quand même ». Voir les [limites connues](#limites-connues).

> La **séparation des locuteurs** n'est pas embarquée dans le programme d'installation, volontairement : elle repose sur PyTorch, environ 3,6 Go une fois posée. Elle s'ajoute **d'un bouton depuis l'application**, panneau « Locuteurs », qui télécharge et installe les composants, annonce la taille et laisse annuler. Rien d'autre à faire.

---

## Ce qu'elle fait

- **Glisser, lancer.** Déposez des fichiers ou un dossier sur la fenêtre, choisissez un preset, lancez. Les fichiers sont traités l'un après l'autre, et un échec n'interrompt pas la file.
- **Formats acceptés :** `m4a` (dont les enregistrements de smartphone), `mp3`, `wav`, `ogg`, `flac`, `opus`, `webm`, `wma`, `aac`, `amr`, et les vidéos courantes (`mp4`, `mkv`, `mov`), dont la piste audio est extraite.
- **Formats produits :** `.txt` avec un en-tête (source, durée, modèle, date, temps de calcul réel), plus `.srt` et `.vtt` en option. Le nom des fichiers suit un motif configurable avec `{nom}`, `{date}`, `{heure}` et `{modele}`.
- **Deux presets.** *Qualité maximale* (`large-v3`) pour tout ce qui sera relu, *Rapide* (`large-v3-turbo`) pour dégrossir. Les autres modèles Whisper restent accessibles en mode avancé.
- **Glossaire et corrections.** Une liste de noms propres oriente le modèle avant qu'il transcrive, une liste de règles nettoie les massacres récurrents après. Voir [Vocabulaire](docs/guide.fr.md#vocabulaire-et-corrections).
- **Relecture dans l'application.** Les mots incertains sont surlignés, n'importe quel mot affiche sa confiance au survol, et corriger une fois peut valoir pour toujours. Voir [Relire une transcription](docs/guide.fr.md#relire-une-transcription).
- **Copier pour l'IA.** Un bouton met votre propre gabarit d'instructions, les métadonnées et le texte complet dans le presse-papiers, prêts à coller dans l'assistant de votre choix. L'application n'envoie rien.
- **Sauvegarde progressive.** Le texte est écrit au fil des segments. Un plantage ou une coupure de courant ne fait plus perdre le travail : l'application propose de reprendre au lancement suivant.
- **Dossier surveillé**, coupé par défaut. Un dossier peut être surveillé pour que les nouveaux enregistrements rejoignent la file tout seuls, ce qui va bien à un dictaphone ou à un enregistreur de réunion qui dépose toujours au même endroit.
- **Séparation des locuteurs**, facultative, installable d'un bouton depuis le panneau « Locuteurs ». Elle produit un texte étiqueté, `Locuteur 1`, `Locuteur 2`, ce qui vaut cher pour un compte rendu.
- **Progression dans la barre des tâches**, état de l'espace occupé, export et import de vos données en un seul fichier zip, thème clair ou sombre, trois raccourcis clavier et pas un de plus : `Ctrl` + `O`, `Ctrl` + `Entrée`, `Échap`.

<!-- gif : dépôt de deux fichiers, choix du preset Rapide, lancement, barre de progression qui se remplit, une ligne terminée avec son bouton de relecture (environ 15 s, sans son) -->

---

## Langues

- **Interface :** français et anglais. Elle suit la langue du système, et se change dans les réglages.
- **Transcription :** dix langues au sélecteur, français, anglais, espagnol, allemand, italien, néerlandais, portugais, polonais, roumain, arabe, chacune avec son indicateur honnête de qualité, plus la **détection automatique**, qui ouvre tout ce que couvrent les modèles Whisper, une centaine de langues. Une seule langue parlée par enregistrement.

---

## Vie privée

**Rien de ce que vous transcrivez ne quitte votre ordinateur.** Pas de compte, pas de clé d'API, pas d'envoi vers un service en ligne, pas de télémétrie. L'audio est lu depuis votre disque, calculé par votre processeur, et le texte est écrit à côté.

Deux choses peuvent passer par le réseau, toutes deux explicites :

- **Le téléchargement d'un modèle**, une fois, au premier usage d'un preset. L'application annonce la taille avant de commencer.
- **La vérification des mises à jour**, qui est **coupée par défaut**. Tant qu'elle est coupée, l'application ne fait aucun appel réseau sortant, hors le téléchargement d'un modèle que vous demandez.

Activée, elle interroge au lancement la liste publique des versions du projet, **au plus une fois par 24 heures**. Rien n'est transmis sur vous ni sur vos fichiers, l'appel a un délai d'attente court, et un échec, qu'il vienne d'un poste hors ligne ou d'un pare-feu, ne produit aucun message : il part dans le journal et c'est tout. Si une version plus récente existe, un bandeau discret le dit, avec un bouton qui ouvre la page de la version dans votre navigateur. Rien ne se télécharge ni ne s'installe tout seul.

Le jeton Hugging Face utilisé par la séparation des locuteurs n'est jamais inclus dans un export, et jamais versionné.

---

## Limites connues

- **Windows 64 bits uniquement.** Le code est portable, mais la détection matérielle et les scripts de lancement visent Windows. L'affichage s'appuie sur Microsoft Edge WebView2 Runtime, présent d'origine sur Windows 11 et sur les Windows 10 à jour ; l'assistant l'installe s'il manque.
- **Une seule langue parlée par enregistrement.** Le mélange de plusieurs langues dans la même conversation est mal géré : Whisper se fixe sur une langue et transcrit le reste au travers. Les termes anglais parsemés dans une discussion française sont un autre sujet, et c'est justement le rôle du glossaire.
- **Conçue d'abord pour le français**, c'est là qu'elle a été le plus éprouvée. La qualité est égale ou meilleure en anglais et dans les langues bien couvertes par Whisper, et l'application annonce sous le sélecteur de langue ce qu'il faut attendre : excellente, bonne ou variable.
- **Le premier lancement a besoin d'Internet** pour télécharger le modèle, de 1,6 à 3,1 Go selon le preset. Ensuite, plus jamais.
- **Aucune accélération AMD ou Intel.** Ces machines transcrivent sur processeur.
- **La séparation des locuteurs s'installe à part**, environ 0,8 Go à télécharger et 3,6 Go sur le disque en version processeur, davantage avec une carte NVIDIA. Comptez 6 Go de libre le temps de l'installation. Le bouton du panneau « Locuteurs » s'en charge, et un jeton Hugging Face gratuit reste à créer ensuite. Sans elle, tout le reste fonctionne.
- **Le programme d'installation n'est pas signé.** SmartScreen peut avertir au premier lancement. Une signature de code coûte plusieurs centaines d'euros par an, ce qui n'a pas de sens pour un outil personnel et gratuit.
- **L'audio est décodé entièrement en mémoire**, environ 230 Mo par heure d'enregistrement. Confortable jusqu'à plusieurs heures, mais ce n'est pas du traitement en flux.
- **Les étiquettes de locuteurs sont utiles, elles ne sont pas une vérité.** Les chevauchements et les voix lointaines sont les cas durs. Préciser le nombre de participants améliore nettement le découpage.

---

**Pour aller plus loin :** glossaire et corrections, vue de lecture, vitesse selon le matériel, installation depuis les sources et diagnostic sont couverts dans **[le guide complet](docs/guide.fr.md)**.

## Installation depuis les sources

Une seule raison désormais : **modifier le code**. La séparation des locuteurs s'installe d'un bouton dans les deux modes, la voie source ne sert plus qu'aux développeurs.

```bat
git clone https://github.com/BurN-30/scribouille
installer.bat
lancer.bat
```

Détails, installation manuelle, locuteurs, organisation du projet et recette de build : **[le guide complet](docs/guide.fr.md#installation-depuis-les-sources)**.

## Contribuer

Les issues et les petites pull requests sont les bienvenues. Voir [CONTRIBUTING.md](CONTRIBUTING.md), rédigé en anglais.

## Licence

MIT, voir [LICENSE](LICENSE). Historique des versions dans [CHANGELOG.md](CHANGELOG.md).

Cet outil s'appuie sur des projets libres : [faster-whisper](https://github.com/SYSTRAN/faster-whisper) et [CTranslate2](https://github.com/OpenNMT/CTranslate2), les modèles [Whisper](https://github.com/openai/whisper) d'OpenAI, [pyannote.audio](https://github.com/pyannote/pyannote-audio), [pywebview](https://pywebview.flowrl.com/) et [FFmpeg](https://ffmpeg.org/).
