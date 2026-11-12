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

### Le vocabulaire, format 2 (`vocabulaire.toml`)

Le bouton **« Vocabulaire et propositions »** ouvre un écran qui réunit les deux leviers dans un seul fichier, `vocabulaire.toml`, lisible et modifiable à la main (un sous-ensemble de TOML). Chaque terme y porte sa forme correcte, sa catégorie (personne, société, sigle, produit ou outil, terme métier, anglicisme), ce que le modèle écrit à sa place, un poids de 1 à 5, son origine et son état : **actif**, **proposé** ou **refusé**. Seuls les termes actifs servent. Exemple fictif :

```toml
format = "scribouille-vocabulaire"
version = 2

[[terme]]
forme = "Martin Lebrun"
categorie = "personne"
fautes = [
  "martin le brun",
  { forme = "martin", voisins = ["monsieur", "lebrun"] },   # seulement près de ces mots
]
poids = 3
etat = "actif"
```

Ce que l'application en fait, en trois étages :

1. **Amorce.** Les termes sont soufflés au modèle dans la limite des 224 jetons. Quand ils n'y tiennent pas tous, passent d'abord ceux qu'évoque le nom du fichier, puis les plus lourds ; avec OpenVINO, l'amorce est refaite à chaque fenêtre de 30 secondes d'après ce que la fenêtre précédente vient de dire.
2. **Correction après coup**, déterministe : les fautes listées sont ramenées à leur forme (toujours, ou seulement près de leurs voisins), la casse est rétablie (« rgpd » devient « RGPD »), et une forme qui **sonne** comme un terme (« Aokland » pour « Auckland ») est rapprochée, avec des garde-fous : jamais un mot du français courant, jamais un terme de moins de quatre sons, jamais quand deux termes sont aussi proches. Une faute faite de mots courants (« mon entreprise ») n'est appliquée que dans son contexte, ou si vous la forcez. Chaque remplacement est listé dans la vue de relecture, avec un bouton **Annuler**.
3. **Remise en forme par un petit modèle de langue** : non incluse, étudiée seulement (voir le rapport de la version).

**Plusieurs fichiers.** Un vocabulaire d'équipe ou de projet s'ajoute dans **Fichiers partagés** : il est lu en plus du vôtre, qui a le dernier mot (un terme que vous avez refusé le reste). **Exporter** produit un fichier à partager ; **Importer des propositions** verse un fichier dans votre vocabulaire, à l'état « proposé ».

**Apprendre à partir de vos corrections.** Une correction faite dans la vue de relecture sans mémoriser de règle devient une proposition. Et `scribouille-verifier.exe --apprendre-vocabulaire --brut BRUT.txt --propre RELUE.docx [--cr COMPTE-RENDU.docx] [--importer]` compare des transcriptions brutes à leurs versions relues (texte, Word, Markdown, PDF texte) et propose les fautes systématiques (avec leur nombre d'occurrences et de réunions), ainsi que les noms propres et sigles des documents propres. Rien ne sert avant d'avoir été accepté dans l'écran Vocabulaire (accepter, refuser, modifier, par lots). Le rapport de chiffres qui l'accompagne ne contient aucun terme.

**L'ancien format reste lu.** Tant que `vocabulaire.txt` et `corrections.txt` contiennent des termes, ils servent tels quels. Le bouton **Convertir** les intègre à `vocabulaire.toml` sans rien perdre et garde une copie des anciens fichiers à côté.

**Mesurer.** `scribouille-verifier.exe --mesurer-vocabulaire --vocabulaire V.toml --reunion AUDIO --reference RELUE` transcrit chaque réunion sans puis avec amorce, applique la correction, et donne le taux d'erreur, le rappel et la précision des termes par catégorie, et le nombre de fausses corrections. Mesurez sur des réunions qui n'ont pas servi à apprendre le vocabulaire.

Les deux fichiers du format 1 sont du texte brut. Ils s'éditent à la main ou depuis les panneaux de l'application. Le panneau **« Mes données »** les exporte, avec vos réglages et votre gabarit pour l'IA s'il existe, dans une archive `scribouille-donnees-AAAA-MM-JJ.zip` que vous rangez où vous voulez, clé USB ou sauvegarde d'entreprise. Un import affiche un aperçu de ce qui va changer et n'écrit rien avant votre confirmation, l'état précédent étant sauvegardé à côté au préalable.

---

---

## Relire une transcription

Une transcription s'ouvre **dans l'application**, sans passer par un éditeur : cliquez sur une ligne de l'onglet « Transcriptions », ou sur le bouton de relecture d'un fichier qui vient de se terminer.

<!-- capture 2 : vue de lecture, un paragraphe avec deux ou trois mots surlignés en ambre, l'infobulle de confiance visible sur l'un d'eux -->

Whisper donne la probabilité de chaque mot qu'il écrit. La vue de lecture **surligne uniquement les mots incertains**, en ambre discret : sous 0,50 la marque est légère, sous 0,30 elle est plus nette. Survoler n'importe quel mot affiche sa confiance, surligné ou non. En pratique cela signale environ un mot sur dix dans le pire des cas, et un sur trente-cinq avec un modèle correct : une poignée d'endroits à réécouter, pas un document bariolé.

Ces valeurs vivent dans un **fichier compagnon `.json`** écrit à côté du texte, quelques dizaines de kilooctets par heure d'audio. Il est facultatif : une transcription plus ancienne, ou produite avec l'option coupée, s'ouvre normalement, simplement sans surlignage.

Sélectionner un mot ou une courte expression propose de le **corriger**. Avant d'appliquer, la fenêtre montre combien d'endroits du fichier changeront, et lesquels, avec leur contexte. L'application applique alors le remplacement au texte affiché et au fichier enregistré, et met le compagnon à jour ; **Annuler la correction** (ou Ctrl+Z) remet le fichier dans son état d'avant. Une correction de casse (« gitlab » vers « GitLab ») est acceptée. Si vous cochez la case prévue, décochée par défaut, la règle rejoint aussi une section dédiée de `corrections.txt`, pour que la même erreur soit corrigée automatiquement dans les transcriptions suivantes.

**Copier pour l'IA** met dans le presse-papiers un texte d'instructions, les métadonnées de l'enregistrement et la transcription complète. Le gabarit est un fichier à vous, `gabarit-ia.txt`, créé au premier usage et modifiable depuis les réglages, où `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}` et `{modele}` sont remplacés au moment de la copie.

---

---

## Vitesse

Le facteur ci-dessous est le rapport durée de calcul sur durée de l'audio. En dessous de 1, c'est plus rapide que l'écoute.

| Matériel | Qualité maximale | Rapide | Une heure d'audio, en qualité |
|---|---|---|---|
| Processeur de bureau, 8 cœurs / 16 fils (Ryzen 7 7800X3D), **mesuré** | 0,4 x | 0,15 x | environ 23 min |
| Même processeur, moteur OpenVINO, **mesuré** | 0,24 x | 0,09 x | environ 14 min |
| Puce graphique Intel d'un Core Ultra 7 265U, OpenVINO, mesure publiée par un tiers | non mesuré | 0,12 x | estimé autour de 20 min |
| Processeur seul du même Core Ultra 7 265U, faster-whisper, mesure publiée par un tiers | non mesuré | 1,04 x | plus d'une heure |
| Carte NVIDIA (CUDA, float16), estimation non mesurée | environ 0,1 x | environ 0,05 x | environ 6 min |

La ligne mesurée l'a été en novembre 2026 sur un extrait français de trois minutes, machine occupée par d'autres programmes : sur une machine au repos, c'est un peu plus rapide. Un processeur plus modeste demande davantage. Depuis la 2.4.0, les passages de parole sont décodés **par lots**, ce qui, avec un fil de calcul par cœur physique, divise le temps de calcul par deux et demi à trois à qualité égale, au prix d'environ 2,5 Go de mémoire de plus. Sous 12 Go de mémoire vive, l'application s'en passe et le calcul est environ deux fois plus long.

**Avant la première transcription, l'application annonce une estimation de départ, pas une garantie.** Elle est calée sur des mesures publiques et ajustée au nombre de cœurs de votre machine. L'application affiche le **temps réellement mesuré** après chaque transcription, et l'écrit dans l'en-tête du fichier produit. La séparation des locuteurs ajoute à peu près 0,2 x sur processeur.

**Elles se corrigent toutes seules.** Dès qu'une transcription arrive à son terme, le facteur observé est retenu, et c'est lui qui sert aux annonces suivantes : la carte du matériel précise alors « mesuré sur cette machine ». Les cinq dernières mesures sont moyennées, la plus récente et la plus longue pesant le plus, et chaque combinaison de modèle et de largeur de faisceau est suivie à part. Rien à régler, et rien qui parte en ligne : les mesures vivent dans `calibration.json`, à côté de vos réglages.

Ce qui est accéléré : le **processeur, partout**, en quantification `int8` ; les **cartes NVIDIA** en CUDA `float16`, automatiquement, si le pilote et les bibliothèques répondent ; et, depuis la 2.4.0, **la puce graphique Intel intégrée** (et à titre expérimental le NPU) par le moteur **OpenVINO**, à installer en option. Les cartes AMD Radeon sont détectées et affichées mais pas exploitées.

### Portable Intel (Core Ultra et apparentés)

Sur un portable de 15 W sans carte dédiée, le processeur seul peut mettre plus longtemps à transcrire que la réunion n'a duré. Trois choses changent la donne, toutes dans la section **Vitesse de cette machine** des réglages :

- **Le nombre de fils de calcul suit l'architecture.** Les Core Ultra série U mêlent cœurs performants, efficaces et « basse consommation » (2 + 8 + 2 sur un Core Ultra 5 225U). L'application les reconnaît et laisse de côté les cœurs basse consommation, plafonnés à 2,4 GHz et sans cache L3, qui freineraient tout le calcul. Elle empêche aussi Windows de brider la transcription quand la fenêtre est réduite.
- **Le moteur OpenVINO** (Intel, licence Apache 2.0, environ 90 Mo depuis PyPI) transcrit sur la puce graphique intégrée. Seule mesure publiée sur un processeur de la même famille (Core Ultra 7 265U) : 0,12 x avec le modèle Rapide sur la puce graphique, contre 1,04 x sur son processeur, texte identique. Les modèles au format OpenVINO (0,8 Go pour Rapide, 1,6 Go pour Qualité) se téléchargent au premier usage. Ce que l'on perd : la probabilité de chaque mot, que ce moteur ne donne pas (la vue de relecture ne surligne alors aucun mot incertain). Tout le reste est gardé : segments horodatés, horodatage des mots pour les locuteurs, glossaire, reprise après coupure, arrêt. En cas de panne d'OpenVINO, le moteur habituel prend le relais sans perdre ce qui est déjà transcrit.
- **Le banc d'essai** transcrit un extrait de 44 s livré avec l'application sous plusieurs réglages (fils de calcul, lots, modèle Rapide et modèle Qualité, chaque moteur et périphérique disponible), compare le texte obtenu à la référence, puis conseille le plus rapide qui reste juste. Il dure cinq à dix minutes. Rien ne change tant que vous n'avez pas cliqué sur **Appliquer le réglage conseillé** ; **Revenir au réglage automatique** défait tout. Le rapport (`rapports-banc\` dans le dossier de données) ne contient ni nom d'utilisateur, ni nom de machine, ni chemin : il peut être envoyé tel quel. Branchez le portable sur secteur avant de le lancer.

En ligne de commande, sans fenêtre : `scribouille-verifier.exe --banc` dans le dossier d'installation (ou `.venv\Scripts\python transcriber.pyw --banc` depuis les sources) ; ajoutez `--telecharger` pour récupérer les modèles manquants, `--npu` pour essayer le NPU, `--appliquer` pour appliquer le conseil.

**Comparer les deux moteurs sur vos propres enregistrements.** Le banc mesure la vitesse sur 44 s de phrases lues d'une seule voix : il ne dit rien de la justesse sur une vraie réunion (plusieurs voix, phrases coupées, mots avalés, mots anglais, vocabulaire de l'équipe). La comparaison transcrit le même extrait d'un de vos fichiers avec CTranslate2 et avec OpenVINO, chacun dans son réglage Qualité, avec votre langue, votre glossaire et vos corrections, puis écrit dans `comparaisons\` du dossier de données :

- `cote-a-cote.html`, à ouvrir dans le navigateur : les deux textes horodatés face à face, les passages où ils divergent surlignés, les mots dont CTranslate2 doute soulignés en pointillé, un clic sur une heure réécoute le passage. Cette page contient la transcription, comme les fichiers `textes-*.json` posés à côté : ils restent sur le poste ;
- `rapport-chiffres.txt` : des nombres seulement (durées de calcul, nombre de mots, taux de désaccord, passages divergents par nature, écarts d'horodatage, segments, termes du glossaire, mots anglais courants, mots incertains), sans un mot de la transcription ni nom ni chemin. Lui peut être transmis.

Depuis la fenêtre : section **Vitesse de cette machine**, bloc **Comparer les deux moteurs** (visible une fois OpenVINO installé). En ligne de commande :

```
scribouille-verifier.exe --comparer "D:\Réunions\point-hebdo.m4a" --debut 00:05:00 --duree 600 --ouvrir
```

`--debut` et `--duree` (secondes, ou `hh:mm:ss`) choisissent l'extrait ; ses bords sont ramenés sur la pause la plus proche, pour ne pas couper une phrase. `--reference FICHIER` ajoute une transcription déjà relue du même enregistrement (texte, SRT, VTT, export texte ou compagnon `.json` de Scribouille ; horodatages et noms de locuteurs ignorés) : le rapport donne alors le taux d'erreur de chaque moteur, et la page une troisième colonne. Sur un extrait, la référence doit être horodatée (SRT, ou export avec horodatage) : sans horodatages, la comparaison à la référence n'est possible que sur le fichier entier. Une référence produite par Scribouille puis peu corrigée favorise CTranslate2, qui l'a écrite. Autres options : `--peripherique GPU|CPU|NPU` (par défaut la puce graphique Intel si OpenVINO la voit), `--preset rapide`, `--sans-glossaire`, `--sans-corrections`, `--faisceau-openvino 5`. Compter deux à trois fois la durée de l'extrait sur un portable, beaucoup moins avec la puce graphique.

Ce que l'on sait déjà, mesuré sur trois réunions publiques à trois ou quatre voix (corpus SUMM-RE) avec le processeur : OpenVINO n'y est pas moins juste que CTranslate2, à égalité sur la parole d'une seule voix, un peu meilleur là où les voix se chevauchent. Ce n'est pas une garantie pour vos réunions, ni pour la puce graphique, qui calcule autrement (fp16) : la comparaison sert à le vérifier.

**Choisir le réglage sur des réunions transcrites à la main : la campagne.** La comparaison montre où deux moteurs divergent, sans dire lequel a raison. La campagne le mesure, sur 22,8 minutes de réunions publiques en français à trois ou quatre voix, transcrites à la main (corpus SUMM-RE ASRU, Laboratoire Parole et Langage et LINAGORA, licence CC BY-SA 4.0) :

```
scribouille-verifier.exe --campagne
```

Sept réglages passent l'un après l'autre (CTranslate2 et OpenVINO, large-v3 et turbo, faisceaux 1 et 5), glossaire et corrections éteints. Le rapport, sans un mot transcrit ni chemin, donne pour chacun le taux d'erreur de mots avec son intervalle de confiance, les mots perdus quand deux personnes parlent en même temps, les insertions longues, la vitesse, puis le verdict : parmi les réglages plus rapides que la réunion et aussi justes que le meilleur, le plus rapide. `--appliquer` l'enregistre comme réglage du poste ; sans lui, rien ne change. Le corpus est lu dans `corpus-campagne-v1.zip` posé à côté du programme, ou téléchargé (476 Mo, Hugging Face puis ORTOLANG). Une campagne interrompue reprend où elle s'est arrêtée ; le poste ne se met pas en veille pendant le calcul. Compter une heure et demie sur un portable Core Ultra avec la puce graphique. `--reunion FICHIER --debut 00:05:00 --duree 600` passe ensuite les mêmes réglages sur une de vos réunions et donne leur accord avec le réglage retenu, toujours sans un mot du texte. Autres options : `--reglages ov-v3-f1,ct2-v3-f5`, `--limite-extraits 3`, `--recommencer`, `--corpus PAQUET.zip`, `--telecharger`.

**Vérifier que le réglage tient : l'épreuve d'endurance.** `scribouille-verifier.exe --endurance` passe le réglage retenu par la campagne trente fois d'affilée, sur des extraits d'environ deux minutes du même corpus, comme la file de l'application. Le rapport, toujours sans texte, donne le taux de panne avant et après le rejeu automatique, l'erreur exacte de chaque incident et la mémoire libre du poste à chaque ouverture du modèle. `--pression` charge en plus, un passage sur deux, le modèle CTranslate2 large-v3 et ne laisse que 4 Go libres (`--memoire-libre 4`), pour éprouver un poste chargé. Compter une demi-heure à trois quarts d'heure sur un portable Core Ultra. Autres options : `--passages 30`, `--reglage ov-turbo-f1`, `--recommencer`, `--sans-diagnostic`.

Sur la puce graphique Intel, OpenVINO ne décode qu'en glouton (faisceau 1) : c'est une limite d'OpenVINO GenAI 2026.4, et l'application n'applique jamais de faisceau plus large sur ce circuit. Si OpenVINO rate une fenêtre, l'application rouvre le modèle et reprend sur la puce graphique ; si cela se répète, elle termine la transcription avec le moteur habituel, sans rien perdre de ce qui était déjà transcrit.

### Réglage proposé pour ce poste

Au premier lancement, et à chaque clic sur **Reconnaître ce poste** (section **Vitesse de cette machine**), l'application regarde le poste (processeur et familles de cœurs, mémoire, puce graphique Intel vue ou non par OpenVINO, carte NVIDIA, NPU, batterie ou secteur, mode d'alimentation de Windows) et propose un réglage, expliqué en une phrase, avec la durée attendue pour une heure de réunion. Si une campagne ou un banc d'essai a été mené sur le poste, son résultat passe devant la table ; s'il ne tient plus (puce graphique absente, pilote en panne, OpenVINO retiré), la proposition le dit et repart du matériel. Rien ne change sans **Appliquer**, rien n'est téléchargé ni installé d'office : un modèle manquant est annoncé avec sa taille et ne descend qu'au lancement d'une transcription ; le moteur Intel reste à installer par son propre bouton. En ligne de commande : `scribouille-verifier.exe --reconnaitre`, puis `--reconnaitre --appliquer`.

La table, lue de haut en bas : carte NVIDIA, Qualité maximale sur la carte ; puce graphique Intel vue par OpenVINO, Rapide sur la puce (une heure en 7 minutes environ, aussi juste que Qualité maximale sur le processeur d'après la campagne du PC de test) ; puce Intel présente mais inutilisable, Rapide avec OpenVINO sur le processeur ; moins de 10 Go de mémoire, Rapide ; processeur seul, OpenVINO s'il est installé, sinon Rapide sur un processeur modeste (moins de 12 fils ou série U) et Qualité maximale sur un processeur de bureau. Le rythme proposé est **Équilibré, qui s'adapte tout seul**.

### Travailler pendant une transcription

La section **Pendant la transcription** des réglages borne ce que la transcription prend au poste :

| | Vitesse maximale (défaut) | Équilibré | Discret |
|---|---|---|---|
| Fils de calcul | tous ceux du réglage du poste | environ les trois quarts, deux fils logiques laissés libres | la moitié, rangés sur les cœurs efficaces d'un processeur hybride |
| Lots de passages | ceux du preset | 4 au plus | un passage à la fois (moins de mémoire) |
| Priorité Windows | normale | inférieure à la normale | basse, et entrées-sorties en priorité basse |
| Fréquence (qualité de service) | bridage levé (comme avant) | décidée par Windows | « mode efficacité » de Windows (EcoQoS) |
| Puce graphique (OpenVINO) | inchangée | file en priorité basse | file en priorité et cadence basses, une pause égale au calcul après chaque fenêtre |
| Mémoire libre basse | rien ne change | lots, puis modèle plus léger, et c'est dit | idem |

**S'adapter tout seul** : la transcription prend le rythme choisi pendant que vous vous servez du poste (clavier ou souris touchés depuis moins de deux minutes, autres programmes qui occupent plus de 30 % du processeur, plein écran ou présentation, micro ouvert pour un appel, portable sur batterie) et la vitesse maximale quand il est au repos. Les fils et les lots se fixent au chargement du modèle : ce sont alors ceux de la vitesse maximale, et la bascule se fait par la priorité, la qualité de service et les pauses. Sur batterie, le rythme choisi est gardé jusqu'à ce que le portable soit branché. Le temps restant affiché suit la cadence réellement observée, bascules comprises. Le choix vaut pour la prochaine transcription.

Mesurer chaque rythme sur le poste : `scribouille-verifier.exe --banc --modes` (ajouter `--peripherique GPU` pour la puce graphique). Pour chaque rythme : vitesse, mémoire, processeur laissé libre, et gêne mesurée sur une petite tâche témoin qui joue le rôle de vos applications. Les rapports de durée mesurés remplacent ensuite les coefficients de départ des estimations.

Pendant une transcription, le poste ne se met plus en veille faute d'activité (fermer le capot garde son effet), et fermer la fenêtre demande confirmation : ce qui est déjà transcrit est gardé et proposé à la reprise.

**Réseau d'entreprise filtré.** Si PyPI ou Hugging Face sont bloqués, les messages d'erreur donnent la voie hors ligne : pour un modèle, recopier son dossier `models--...` depuis un poste qui l'a déjà téléchargé dans le dossier des modèles ; pour OpenVINO, déposer les trois fichiers `.whl` (obtenus ailleurs par `pip download`) dans `paquets-hors-ligne\` du dossier de données, puis relancer l'installation. Aucun droit d'administrateur n'est demandé : tout s'installe dans le dossier de l'utilisateur.

<details>
<summary>Pistes écartées pour l'instant, et pourquoi</summary>

**whisper.cpp avec Vulkan ou OpenVINO** : aucun binaire Windows officiel avec ces moteurs (version 1.9.5, octobre 2026), il faudrait le construire soi-même et changer de format de modèles (GGUF). OpenVINO GenAI s'installe en trois paquets Python et lit des modèles déjà convertis par Intel : c'est la voie retenue.

**Le NPU** : pris en charge par OpenVINO, mais le seul essai publié sur un portable de cette famille l'a vu bloquer avec le modèle Rapide (Core Ultra 7 265U, octobre 2026). Il reste proposé au banc, à titre expérimental, et n'est jamais choisi sans y avoir réussi.

**Les cartes AMD Radeon** : CTranslate2 sait calculer dessus avec ROCm sous Windows depuis la 4.9.0, mais l'application n'embarque pas encore ces bibliothèques (environ 1,1 Go).

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
2. Ouvrez [pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1) et acceptez les conditions (licence CC-BY-4.0 ; le formulaire demande une organisation et un usage, et pyannote peut vous écrire de temps en temps). Ce modèle, plus juste que l'ancien 3.1, est essayé en premier ; 3.1 reste utilisé si vous n'avez accepté que ses conditions.
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
  audio.py            décodage 16 kHz mono (FFmpeg par PyAV), durée
  moteur.py           faster-whisper, chargement et libération
  diarisation.py      pyannote, jeton, attribution des locuteurs
  extensions.py       installation de la séparation des locuteurs, pip embarqué
  vocabulaire.py      glossaire, amorce, corrections (format 1)
  vocabulaire_v2.py   vocabulaire format 2 : fichier, fusion, migration, revue
  vocabulaire_usage.py amorce choisie, correction après coup et garde-fous
  vocabulaire_interface.py écran Vocabulaire
  lexique.py          mots courants du français, clé phonétique
  apprentissage.py    propositions tirées des transcriptions relues
  documents.py        texte des documents (Word, PDF texte, Markdown, sous-titres)
  mesure_vocabulaire.py gain de chaque étage, avec référence
  sorties.py          txt, srt, vtt, en-têtes
  nommage.py          motif de nom des fichiers produits
  surveillance.py     dossier surveillé, scrutation et mémoire
  stockage.py         espace occupé par les modèles, les données, le programme
  maj.py              vérification facultative des versions publiées
  barre_taches.py     progression dans la barre des tâches Windows
  compagnon.py        fichier .json de confiance mot à mot
  lecture.py          vue de lecture, corrections relues, copie pour l'IA
  ecoute.py           serveur local de l'audio pour la relecture
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

