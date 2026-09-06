# Scribouille, le guide complet

[Retour au README](../README.fr.md)

---

## Vocabulaire et corrections

C'est le point faible de toute transcription automatique : les noms propres, les noms de sociétés et les termes techniques sortent massacrés. Deux leviers y répondent, complémentaires.

**Le glossaire, `vocabulaire.txt`.** Un terme par ligne. La liste est envoyée au modèle **avant** qu'il ne transcrive, comme début de contexte, ce qui l'oriente vers ces orthographes.

```
Jean Dupont
MonEntreprise
GitLab
Kubernetes
RGPD
```

L'amorce d'un modèle Whisper ne peut pas dépasser **224 jetons**, soit une petite centaine de termes courts. Au-delà, faster-whisper tronque tout seul, et silencieusement. Scribouille tronque proprement à la place, en gardant les termes **du haut de la liste**, et vous prévient dans l'interface. Mettez donc les plus importants en premier. Le décompte est exact : il utilise le tokeniseur du modèle réellement chargé. La phrase d'introduction de l'amorce suit la **langue parlée** de l'enregistrement, jamais celle de l'interface : le modèle la lit comme un début de texte, une phrase française n'a rien à faire en tête d'un enregistrement anglais.

**Les corrections, `corrections.txt`.** Pour les massacres récurrents que l'amorce ne suffit pas à éviter. Une règle par ligne, appliquée au texte final, insensible à la casse, mot entier uniquement : la règle `git` ne touchera pas `digital`.

```
guitte lab => GitLab
cubernetes => Kubernetes
```

Les deux fichiers sont du texte brut. Ils s'éditent à la main ou depuis les panneaux de l'application. Le panneau **« Mes données »** les exporte, avec vos réglages et votre gabarit pour l'IA s'il existe, dans une archive `scribouille-donnees-AAAA-MM-JJ.zip` que vous rangez où vous voulez, clé USB ou sauvegarde d'entreprise. Un import affiche un aperçu de ce qui va changer et n'écrit rien avant votre confirmation, l'état précédent étant sauvegardé à côté au préalable.

---

---

## Relire une transcription

Une transcription s'ouvre **dans l'application**, sans passer par un éditeur : cliquez sur une ligne de l'onglet « Transcriptions », ou sur le bouton de relecture d'un fichier qui vient de se terminer.

<!-- capture 2 : vue de lecture, un paragraphe avec deux ou trois mots surlignés en ambre, l'infobulle de confiance visible sur l'un d'eux -->

Whisper donne la probabilité de chaque mot qu'il écrit. La vue de lecture **surligne uniquement les mots incertains**, en ambre discret : sous 0,50 la marque est légère, sous 0,30 elle est plus nette. Survoler n'importe quel mot affiche sa confiance, surligné ou non. En pratique cela signale environ un mot sur dix dans le pire des cas, et un sur trente-cinq avec un modèle correct : une poignée d'endroits à réécouter, pas un document bariolé.

Ces valeurs vivent dans un **fichier compagnon `.json`** écrit à côté du texte, quelques dizaines de kilooctets par heure d'audio. Il est facultatif : une transcription plus ancienne, ou produite avec l'option coupée, s'ouvre normalement, simplement sans surlignage.

Sélectionner un mot ou une courte expression propose de le **corriger**. L'application applique le remplacement au texte affiché et au fichier enregistré, met le compagnon à jour, et range la règle dans une section dédiée de `corrections.txt` pour que la même erreur soit corrigée automatiquement ensuite.

**Copier pour l'IA** met dans le presse-papiers un texte d'instructions, les métadonnées de l'enregistrement et la transcription complète. Le gabarit est un fichier à vous, `gabarit-ia.txt`, créé au premier usage et modifiable depuis les réglages, où `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` et `{modele}` sont remplacés au moment de la copie.

---

---

## Vitesse

Le facteur ci-dessous est le rapport durée de calcul sur durée de l'audio. En dessous de 1, c'est plus rapide que l'écoute.

| Matériel | Qualité maximale | Rapide | Une heure d'audio, en qualité |
|---|---|---|---|
| Ultraportable, 12 à 14 fils, sans carte dédiée | environ 1,2 x | environ 0,3 x | environ 1 h 15 |
| Processeur de bureau, 16 fils et plus | environ 0,7 x | environ 0,2 x | environ 40 min |
| Portable modeste, 4 à 8 fils | environ 2 x | environ 0,5 x | environ 2 h |
| Carte NVIDIA (CUDA, float16) | environ 0,1 x | environ 0,05 x | environ 6 min |

**Ce sont des estimations de départ, pas des garanties.** Elles sont calées sur des mesures publiques et ajustées au nombre de cœurs de votre machine. L'application affiche le **temps réellement mesuré** après chaque transcription, et l'écrit dans l'en-tête du fichier produit. La séparation des locuteurs ajoute à peu près 0,2 x sur processeur.

**Elles se corrigent toutes seules.** Dès qu'une transcription arrive à son terme, le facteur observé est retenu, et c'est lui qui sert aux annonces suivantes : la carte du matériel précise alors « mesuré sur cette machine ». Les cinq dernières mesures sont moyennées, la plus récente et la plus longue pesant le plus, et chaque combinaison de modèle et de largeur de faisceau est suivie à part. Rien à régler, et rien qui parte en ligne : les mesures vivent dans `calibration.json`, à côté de vos réglages.

Ce qui est accéléré dans cette version : le **processeur, partout**, en quantification `int8`, qui est le mode par défaut et reste parfaitement utilisable, et les **cartes NVIDIA** en CUDA `float16`, automatiquement, si le pilote et les bibliothèques répondent. Les cartes AMD Radeon, les circuits graphiques intégrés Intel et les NPU sont détectés et affichés mais **pas exploités**, parce que faster-whisper repose sur [CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html), qui ne supporte que le CPU x86-64 ou ARM64 et les GPU NVIDIA. L'application le dit noir sur blanc plutôt que de laisser croire à une accélération qui n'existe pas.

<details>
<summary>Ce qui pourrait changer cela, plus tard</summary>

**whisper.cpp avec le backend Vulkan** est la piste solide, et la seule réaliste pour accélérer un Radeon sous Windows : un portage C/C++ indépendant de PyTorch et de CUDA, qui fait de l'inférence GPU multi-vendeur sans code spécifique au constructeur. Les mesures publiques donnent environ 8 x le temps réel sur une RX 9070 XT, et un facteur 3 à 4 fois meilleur que le CPU seul sur un iGPU Radeon 680M. La livraison envisagée est un binaire Windows Vulkan pré-compilé, piloté en sous-processus, pour ne demander à personne d'installer une chaîne de compilation C++. Le coût est un deuxième format de modèles, GGUF au lieu de CTranslate2, et une couche d'abstraction de moteur : c'est pour cela que ce n'est pas encore là.

**OpenVINO pour l'iGPU et le NPU Intel** est intéressant mais pas mûr pour un outil clé en main : le backend réclame une version précise d'OpenVINO, et la conversion des modèles Whisper casse avec certaines versions de `transformers`. Quant au NPU lui-même, son intérêt est l'autonomie, quelques watts contre 15 à 25 pour l'iGPU, pas la vitesse brute. Si l'accélération Intel devient un objectif, passer par Vulkan est plus simple et plus robuste.

</details>

---

---

## Installation depuis les sources

Une seule raison d'emprunter cette voie : **modifier le code**. La séparation des locuteurs, elle, s'installe d'un bouton depuis l'application, quelle que soit la version employée. Pour un usage normal, l'installation ci-dessus suffit.

1. Installez [Python 3.9 ou plus récent](https://www.python.org/downloads/) en cochant **« Add python.exe to PATH »**.
2. Double-cliquez sur **`installer.bat`**.
3. Répondez à la question sur la séparation des locuteurs, puis laissez faire.
4. Double-cliquez sur **`lancer.bat`**.

L'installateur est relançable, ne réinstalle que ce qui manque, et crée un environnement isolé dans `.venv` sans toucher au Python du système. Il n'a besoin ni de droits administrateur, ni de winget, ni de Chocolatey : FFmpeg est posé par un paquet Python qui embarque le binaire.

| Option | Effet |
|---|---|
| `installer.bat` | Installation standard, pose la question sur les locuteurs |
| `installer.bat --locuteurs` | Ajoute la séparation des locuteurs (PyTorch et pyannote), équivalent en ligne de commande du bouton de l'application |
| `installer.bat --sans-locuteurs` | Installation légère, sans question |
| `installer.bat --verifier` | N'affiche que le bilan de l'état du poste |

Lancée depuis les sources, l'application range tout à côté du script : `config.json`, `logs/`, `modeles/`, glossaire et corrections. C'est la seule différence de comportement avec la version installée.

<details>
<summary>Installation manuelle, pour qui préfère garder la main</summary>

```bat
python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

REM Seulement si une carte NVIDIA est présente : évite l'erreur
REM « cublas64_12.dll introuvable » sans toucher au PATH système.
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.*

REM Seulement pour la separation des locuteurs, et seulement si l'on tient a
REM la poser a la main : le bouton de l'application fait la meme chose.
REM Sans carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cpu
REM Avec carte NVIDIA :
pip install torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cu124
REM Les versions sont repetees a dessein : pyannote.audio se contente de
REM bornes basses, et pip irait sinon chercher sur PyPI des versions plus
REM recentes, compilees contre un autre PyTorch.
pip install -r requirements-locuteurs.txt torch==2.8.0 torchaudio==2.8.0 torchcodec==0.7.0 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple

.venv\Scripts\pythonw transcriber.pyw
```

Le socle fait environ 250 Mo. La séparation des locuteurs ajoute 3,55 Go, mesurés, parce qu'elle tire PyTorch : c'est précisément pourquoi elle est optionnelle, et pourquoi elle reste hors du programme d'installation.

Contrôler l'état du poste, le décodeur FFmpeg, les dossiers de travail et la détection matérielle :

```bat
.venv\Scripts\python transcriber.pyw --verifier
```

</details>

<details>
<summary>Mettre en place la séparation des locuteurs</summary>

**Depuis l'application, c'est un bouton.** Ouvrez le panneau « Locuteurs », cliquez sur « Installer la séparation des locuteurs ». L'application annonce la taille à télécharger, environ 0,8 Go en variante processeur, l'espace nécessaire sur le disque, 6 Go, et ce qu'il reste de libre. Ces chiffres sont mesurés sur une installation réelle : 0,71 Go de roues téléchargées, 3,55 Go de fichiers posés. Elle demande confirmation, puis télécharge en arrière-plan : la progression s'affiche, l'annulation est possible à tout moment, et la transcription reste utilisable pendant ce temps. Une coupure réseau n'oblige pas à tout retélécharger : ce qui est déjà arrivé est gardé, et une relance ne redemande au réseau que ce qui manque. Elle repose en revanche les fichiers sur le disque, quelques minutes, seule façon sûre de ne pas laisser en place les restes d'une tentative interrompue.

Le bouton choisit tout seul la variante adaptée au poste : processeur par défaut, CUDA si une carte NVIDIA répond. Dans la version installée, les composants vont dans `%LOCALAPPDATA%\WhiScribe\extensions`, et un second bouton permet de les retirer, avec leur poids affiché. Depuis les sources, ils vont dans le `.venv` du projet, exactement comme le fait `installer.bat --locuteurs`.

**Ensuite, le jeton.** C'est une étape distincte, et elle n'a rien à voir avec le téléchargement : le modèle qui reconnaît les voix, pyannote, est gratuit mais sous conditions, et son auteur demande de les accepter et de s'identifier.

1. Créez un compte sur [huggingface.co](https://huggingface.co).
2. Ouvrez [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) et acceptez les conditions.
3. Créez un jeton d'accès **Read** dans les réglages du compte.
4. Collez-le dans le panneau « Locuteurs » de l'application.

Le jeton est enregistré dans `jeton_hf.txt`, avec vos données, et n'est jamais versionné. La variable d'environnement `HF_TOKEN` est également reconnue, et prioritaire. Sans jeton, tout fonctionne quand même, simplement sans étiquettes et avec un message clair au lieu d'une erreur.

Whisper et pyannote sont **séquencés**, jamais chargés en même temps : l'application transcrit, libère explicitement le modèle Whisper, force un passage du ramasse-miettes, puis charge la diarisation. Les pics se suivent au lieu de s'additionner, et `large-v3` plus pyannote tiennent dans 16 Go.

</details>

<details>
<summary>Comment le projet est organisé</summary>

Un seul moteur, faster-whisper sur CTranslate2. whisperX a été retiré : il impose PyTorch, son alignement mot à mot ne sert pas ici, sa VAD est désormais intégrée à faster-whisper, et piloter une bibliothèque plutôt qu'un sous-processus donne la progression segment par segment, le contrôle exact de la libération mémoire entre les étapes, les erreurs typées, et l'accès au tokeniseur du modèle pour mesurer le budget de l'amorce.

```
transcriber.pyw       fenêtre, passerelle vers l'interface, mode --verifier
installer.py          installateur relançable, version source
app/
  chemins.py          emplacements, selon source ou version installée
  materiel.py         détection processeur, mémoire, GPU, NPU
  presets.py          presets, estimations, garde-fous mémoire
  audio.py            FFmpeg, durée, décodage 16 kHz mono
  moteur.py           faster-whisper, chargement et libération
  diarisation.py      pyannote, jeton, attribution des locuteurs
  extensions.py       installation de la séparation des locuteurs, pip embarqué
  vocabulaire.py      glossaire, amorce, corrections
  sorties.py          txt, srt, vtt, en-têtes
  nommage.py          motif de nom des fichiers produits
  surveillance.py     dossier surveillé, scrutation et mémoire
  stockage.py         espace occupé par les modèles, les données, le programme
  maj.py              vérification facultative des versions publiées
  barre_taches.py     progression dans la barre des tâches Windows
  compagnon.py        fichier .json de confiance mot à mot
  lecture.py          vue de lecture, corrections relues, copie pour l'IA
  gabarit.py          gabarit d'instructions pour un assistant IA
  reprise.py          sauvegarde progressive et reprise après interruption
  traitement.py       file séquentielle
  config.py           configuration
  journal.py          journalisation et traduction des incidents
  langues.py          catalogues français et anglais, côté Python
web/                  interface (HTML, CSS, JavaScript), langues.js
outils/               harnais de mesure et de vérification, hors application
packaging/            recette PyInstaller, script Inno Setup, icône
.github/workflows/    chaîne de publication
```

Où vivent les fichiers, selon la manière dont l'application est lancée :

| | Version installée | Version source |
|---|---|---|
| Programme | `%LOCALAPPDATA%\Programs\Scribouille` | le dépôt cloné |
| Réglages, journaux, glossaire | `%LOCALAPPDATA%\WhiScribe` | à côté du script |
| Modèles | choisi à l'installation, modifiable dans les réglages | `modeles/`, modifiable dans les réglages |

Le dossier de données porte encore l'ancien nom de l'application, et c'est délibéré : le renommer à la 2.4.0 aurait laissé sur place les réglages, le glossaire et les modèles de toutes les installations existantes.

</details>

<details>
<summary>Fabriquer le programme d'installation</summary>

La publication est automatisée : poser un tag `vX.Y.Z` déclenche `.github/workflows/release.yml`, qui construit, vérifie, fabrique le programme d'installation et crée la Release avec le fichier en pièce jointe. Les notes de version sont la section correspondante de [CHANGELOG.md](CHANGELOG.md). Le même workflow se lance à la main depuis l'onglet Actions, sans tag : il construit et vérifie tout, mais ne publie rien.

```bat
pip install -r requirements.txt -r requirements-build.txt
pyinstaller --noconfirm --clean --distpath dist --workpath build packaging\scribouille.spec
dist\Scribouille\scribouille-verifier.exe
iscc /DVersionApp=2.3.0 packaging\setup.iss
```

Le numéro de version a une seule source, `VERSION` dans `app/__init__.py`, et le workflow refuse de publier si le tag ne lui correspond pas. PyInstaller 6.22 est le minimum : les versions antérieures ne savent pas geler numpy 2.5.

Une version qui ne peut pas se mettre à jour en place s'annonce en écrivant `[reinstallation-requise]` n'importe où dans sa section du CHANGELOG. Le bandeau de mise à jour dit alors qu'il faut désinstaller d'abord, et que les données et les modèles sont conservés, ce qui est vrai puisqu'ils vivent hors du dossier du programme.

</details>

---

---

## Diagnostic

Chaque échec est expliqué dans l'interface, en clair : fichier illisible, modèle à télécharger, mémoire insuffisante, jeton absent ou invalide, disque plein, bibliothèques CUDA manquantes. Aucun traceback n'apparaît à l'écran.

Le détail technique part dans un fichier horodaté du dossier `logs/`, dont le nom est cité dans le message d'erreur. Le bouton **« Ouvrir le fichier détaillé »**, dans la barre du bas, l'ouvre directement. Les 30 derniers journaux sont conservés. C'est ce fichier qu'il faut joindre à un rapport de bug, et il est écrit en français : il s'adresse au mainteneur, pas à l'utilisateur.

Trois modes s'ajoutent pour la séparation des locuteurs, sans fenêtre eux non plus. Ce sont ceux que l'application se lance à elle-même, dans un processus de fond, quand on clique sur le bouton du panneau « Locuteurs » ; ils servent aussi à valider une version construite sans rien cliquer :

```bat
REM Poser les composants, ici dans un dossier d'essai plutot que le dossier reel
dist\Scribouille\scribouille-verifier.exe --installer-locuteurs --cible D:\essai --cpu

REM Essayer l'import reel de torch et de pyannote. Code 0 si tout repond.
dist\Scribouille\scribouille-verifier.exe --verifier-locuteurs --cible D:\essai

REM Tout effacer
dist\Scribouille\scribouille-verifier.exe --retirer-locuteurs --cible D:\essai
```

`--paquets` remplace la liste par la sienne, ce qui permet d'éprouver le mécanisme avec un paquet léger sans télécharger plusieurs gigaoctets. Sans `--cible`, le dossier d'extensions réel est utilisé. Depuis les sources, les mêmes options existent sur `python -m app.extensions`.


---

