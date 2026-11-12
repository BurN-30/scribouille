# Journal des versions

Les versions publiées sont disponibles dans l'onglet
[Releases](../../releases). Chaque entrée de ce fichier sert de notes de
version : la chaîne de publication en extrait la section correspondant au tag.

---

## 2.4.1

*Non publiée.*

S'adapter au poste, et travailler pendant que la transcription tourne.

- **Réglage proposé pour ce poste**, au premier lancement et sur le bouton
  **Reconnaître ce poste** (ou `scribouille-verifier.exe --reconnaitre`) : une
  table de décision lisible (`app/adaptation.py`) regarde la carte NVIDIA, la
  puce graphique Intel vue par OpenVINO, la mémoire, le processeur et
  l'alimentation, et propose moteur, preset et rythme en une phrase, avec la
  durée pour une heure. Le verdict d'une campagne ou le conseil d'un banc mené
  sur le poste passent devant la table, tant qu'ils tiennent sur le matériel
  du moment ; sinon la proposition le dit. Rien n'est appliqué, téléchargé ni
  installé sans un clic.
- **Pendant la transcription** : vitesse maximale (le défaut, comportement
  inchangé), équilibré ou discret. Fils de calcul, lots, priorité Windows,
  « mode efficacité » (EcoQoS), priorité des entrées-sorties, cœurs efficaces
  des processeurs hybrides, priorité et cadence de la file de la puce
  graphique (propriétés documentées du greffon GPU d'OpenVINO), pauses entre
  fenêtres. Mémoire libre basse : lots, puis modèle plus léger, et c'est dit.
- **S'adapter tout seul** : rythme choisi quand le poste sert (clavier et
  souris, charge des autres programmes, plein écran, micro ouvert, batterie),
  pleine vitesse au repos. Le temps restant suit la cadence observée.
- **Banc des rythmes** (`--banc --modes`) : vitesse, mémoire, processeur
  laissé libre et gêne d'une tâche témoin, pour chaque rythme ; ses rapports
  de durée remplacent les coefficients de départ des estimations.
- **Fiabilité** : le poste ne se met plus en veille faute d'activité pendant
  une file ; fermer la fenêtre en pleine transcription demande confirmation ;
  un fichier audio abîmé lu en partie est signalé ; l'état de reprise est
  écrit d'un bloc ; une sauvegarde au fil de l'eau qui ne peut plus écrire
  (disque plein) est signalée ; le repli sur le processeur quand la puce
  graphique manque est dit au lancement de la file.
- **Faisceau sur la puce graphique, voie d'essai** : la campagne accepte
  `--peripherique HETERO:GPU,CPU` et `--proprietes-ov CLE=VALEUR`, dans un
  dossier à part, pour mesurer sur un portable Intel si le faisceau y devient
  possible et juste. L'application ne s'en sert pas.

Corrections issues d'une revue d'usage de l'application réelle (vérifiées par
`outils/verifier_parcours.py`) :

- **Relecture fidèle au fichier** : la vue n'ajoute plus d'espace devant une
  apostrophe ou un trait d'union (« c 'est », « peut -être »), garde les mots
  que le moteur n'a pas détaillés, et « Copier le texte » copie le corps du
  fichier lui-même. Une expression avec apostrophe se corrige de nouveau.
- **Corrections de casse** acceptées (« gitlab » vers « GitLab »), et plus
  aucun doublon quand la forme corrigée prolonge la forme entendue
  (« réseaux » vers « réseaux sociaux » ne produit plus « réseaux sociaux
  sociaux ») ; seuls les changements réels sont comptés.
- **Correction depuis la relecture** : l'en-tête du fichier texte reste séparé
  du corps ; la barre de fin d'en-tête et la première phrase ne se retrouvent
  plus sur la même ligne.

Choisir le réglage sur des réunions transcrites à la main : la campagne.

La comparaison dit où deux moteurs divergent, pas lequel a raison. La campagne
de mesure tranche : `scribouille-verifier.exe --campagne` transcrit 22,8
minutes de réunions publiques en français (vingt extraits du corpus SUMM-RE
ASRU, trois ou quatre voix, transcription manuelle alignée au mot, licence
CC BY-SA 4.0) sous sept réglages, à armes égales : CTranslate2 large-v3
faisceaux 5 et 1, OpenVINO large-v3 faisceaux 1 et 5, OpenVINO large-v3-turbo
faisceaux 1 et 5, CTranslate2 large-v3-turbo faisceau 5. Pour chacun : taux
d'erreur de mots avec intervalle à 95 %, substitutions, omissions, insertions,
mots perdus quand deux personnes parlent en même temps, insertions longues
(indice d'invention), vitesse, mémoire, segments trop longs, et un témoin de
parole lue.

- **Verdict**, la fiabilité d'abord : tout réglage plus lent que la réunion est
  écarté ; parmi ceux dont le taux d'erreur ne se distingue pas du meilleur
  (moins d'un point, ou écart apparié non significatif et sous deux points),
  le plus rapide. Le rapport dit pourquoi, et ce que le choix coûte. Rien n'est
  appliqué sans `--appliquer`, qui écrit moteur, périphérique, faisceau et
  preset dans le réglage du poste.
- **Corpus non embarqué** : le dépôt ne contient que la liste des extraits et
  leurs empreintes. Le programme prend un paquet préparé posé à côté de lui
  (`corpus-campagne-v1.zip`, 35 Mo, même licence que sa source) ou télécharge
  les seules secondes utiles depuis Hugging Face, puis ORTOLANG (476 Mo).
- **Reprise** : chaque réglage terminé est enregistré ; une relance ne refait
  que ce qui manque. Le rapport donne l'heure de début et de fin de chaque
  réglage.
- **Réunion réelle** (`--reunion FICHIER --debut --duree`) : les mêmes
  réglages sur un extrait confidentiel, l'accord de chacun avec le réglage
  retenu et les termes du glossaire retrouvés, sans un mot du texte.
- **Mots douteux** : OpenVINO ne donne aucune probabilité (vérifié : scores à
  1, `logprobs` ignoré, une seule séquence rendue). La campagne mesure ce que
  vaudrait une seconde passe d'un autre modèle pour les signaler, et à quel
  coût, à côté des probabilités de CTranslate2.

- **Épreuve d'endurance** (`--endurance [--passages 30] [--pression]`) : le
  réglage retenu passé de nombreuses fois d'affilée sur des extraits du corpus,
  comme dans la file de l'application. Pour chaque passage : réussi ou non,
  erreur exacte, rejeu, repli, mémoire libre du poste avant l'ouverture du
  modèle et avant le passage, vitesse ; puis le taux de panne avant et après
  rejeu, avec sa borne haute à 95 %. `--pression` recrée, un passage sur deux,
  un poste chargé : CTranslate2 large-v3 en mémoire et 4 Go libres seulement.
  Rapport de chiffres, sans texte.

Corrigé

- **OpenVINO sur la puce graphique, faisceau** : OpenVINO GenAI 2026.4 ne sait
  pas décoder Whisper en faisceau sur la puce graphique (erreur « Not
  Implemented » de `iremote_tensor.hpp`, à chaque fois ; ticket openvino.genai
  n° 2746). Le garde-fou des répétitions refaisait une fenêtre qui boucle avec
  un faisceau de 5 : sur la puce graphique, une transcription pourtant
  gloutonne pouvait donc tomber dès qu'une fenêtre bouclait. Il la refait
  désormais par échantillonnage à température croissante sur la puce
  graphique et le NPU (faisceau de 5 sur le processeur, comme avant), et une
  reprise ratée garde la première version au lieu d'emporter le fichier. Le
  faisceau n'est jamais appliqué à OpenVINO sur ces deux circuits, et la
  campagne marque ces réglages « non pris en charge » au lieu d'une panne.
- **Un raté d'OpenVINO ne coûte plus la vitesse** : à la première erreur, à
  l'ouverture comme en cours de transcription, le modèle est libéré, rouvert,
  et la transcription reprend sur la puce graphique à la fin du dernier
  segment sorti. Si l'erreur revient, CTranslate2 prend le relais au même
  endroit, comme avant. Une ligne le dit dans l'interface.
- **Réglage de comparaison des réunions** : le rapport d'une réunion écrivait
  « pas de verdict public » quand le réglage retenu avait échoué sur cette
  réunion. Il le dit désormais, et le verdict est lu au lancement.
- **Veille du poste** : une comparaison lancée en fin de journée ne démarrait
  qu'au réveil du portable. Comparaison et campagne demandent à Windows de ne
  pas mettre le système en veille pendant le calcul (`SetThreadExecutionState`,
  demande propre au processus, relâchée à la fin ; aucun réglage modifié).
- **Glossaire d'une installation ancienne** : jusqu'à la 2.3, les exemples
  (« Jean Dupont », « MonEntreprise »...) étaient livrés actifs et le fichier
  n'est jamais réécrit : ils partaient en amorce de chaque transcription, et la
  règle « mon entreprise => MonEntreprise » réécrivait une tournure courante.
  Un glossaire ou une table de corrections resté EXACTEMENT tel que livré est
  remplacé à l'ouverture de la fenêtre par le modèle actuel (exemples en
  commentaire), avec une copie de l'ancien. Un fichier retouché n'est pas
  touché. L'amorce elle-même agit : vérifié sur les trois chemins de calcul.

Comparer les deux moteurs sur ses propres enregistrements.

Le banc d'essai de la 2.4.0 dit quel moteur va le plus vite, sur 44 s de
phrases lues d'une seule voix. Il ne dit rien de la justesse sur une vraie
réunion. La nouvelle comparaison transcrit le même extrait d'un de vos
fichiers avec CTranslate2 et avec OpenVINO, chacun dans son réglage Qualité,
avec votre langue, votre glossaire et vos corrections, et écrit dans
`comparaisons\` du dossier de données :

- **une page côte à côte** (`cote-a-cote.html`) : les deux textes horodatés
  face à face, les passages qui divergent surlignés, les mots dont CTranslate2
  doute soulignés, un clic sur une heure pour réécouter. Elle contient la
  transcription et reste sur le poste ;
- **un rapport de chiffres** (`rapport-chiffres.txt`) sans un mot de la
  transcription, ni nom, ni chemin : durées de calcul, nombre de mots, taux de
  désaccord (WER de l'un rapporté à l'autre), passages divergents par nature
  (un mot, plusieurs mots, morceau entendu par un seul moteur), écarts
  d'horodatage de plus d'une seconde, longueur des segments (sur lesquels
  s'appuie la séparation des locuteurs), termes du glossaire retrouvés, mots
  anglais courants écrits en anglais, mots incertains de CTranslate2 et part de
  ceux qui tombent là où les moteurs divergent ;
- **avec une transcription déjà relue** (`--reference`, texte, SRT, VTT, export
  ou compagnon de Scribouille), le taux d'erreur de chaque moteur et une
  troisième colonne. Sur un extrait, la référence est recalée par ses
  horodatages ; sans horodatages, elle ne sert que sur le fichier entier.
  Normalisation commune : casse, ponctuation, nombres en lettres, élisions,
  hésitations.

Depuis la section « Vitesse de cette machine », ou en ligne de commande :
`scribouille-verifier.exe --comparer FICHIER --debut 00:05:00 --duree 600`.
Les bords de l'extrait sont ramenés sur une pause : une phrase coupée au début
d'un extrait a fait sauter au faisceau de CTranslate2 tout le début de la
fenêtre, ce qui n'arrive pas à un enregistrement qui commence normalement.

Mesuré sur trois réunions publiques en français, à trois ou quatre voix
(corpus SUMM-RE, CC BY-SA 4.0, 10 minutes chacune, pistes mélangées, processeur
Ryzen 7 7800X3D) : OpenVINO sur processeur n'est pas moins juste que
CTranslate2 (taux d'erreur cumulé 37,6 % contre 40,3 % avec un glossaire,
38,1 % contre 38,8 % sans ; à égalité sur la parole d'une seule voix), pour
1,3 à 1,6 fois moins de calcul. Les deux perdent surtout la parole qui se
chevauche et les « ouais » d'approbation. Un faisceau de 5 n'apporte rien de
constant à OpenVINO ; à CTranslate2, passer en glouton coûte 1 à 4 points.
Rien de tout cela ne vaut pour la puce graphique Intel (calcul en fp16), ni
pour une réunion donnée : c'est l'objet de la comparaison.

Corrigé

- **OpenVINO, langue détectée** : le moteur lisait un attribut qui n'existe
  pas (`language` au lieu de `languages`). En détection automatique, la langue
  était redemandée à chaque fenêtre de 30 s au lieu d'être fixée sur la
  première, et l'en-tête du fichier produit ne donnait pas la langue
  trouvée. Sans effet quand la langue est choisie (le français par défaut).
- OpenVINO compte les fenêtres de 30 s qu'il a dû décoder en deux passes
  (plafond de jetons, ou phrase annoncée comme continuant au-delà) : la
  seconde passe se fait sans l'amorce du glossaire. Le rapport de comparaison
  en donne le nombre.

---

## 2.4.0

*Non publiée.*

Les portables Intel ne sont plus laissés au seul processeur.

Sur un portable de 15 W sans carte dédiée (Core Ultra série U), le processeur
seul pouvait mettre plus longtemps à transcrire qu'il n'en fallait pour écouter
la réunion. Trois changements, réunis dans une nouvelle section des réglages,
« Vitesse de cette machine ».

- **Processeurs hybrides reconnus.** L'application lit dans Windows la famille
  de chaque cœur : performants, efficaces et « basse consommation » (2 + 8 + 2
  sur un Core Ultra 5 225U). Elle calcule sur un fil par cœur performant ou
  efficace et laisse de côté les cœurs basse consommation, plafonnés à 2,4 GHz
  et sans cache L3 (10 fils au lieu de 12 sur ce processeur). Rien ne change
  sur un processeur de bureau homogène : 8 fils sur un 8 cœurs, comme avant.
- **Pleine vitesse fenêtre réduite.** Windows 11 range d'office sur les cœurs
  efficaces, à fréquence réduite, un programme dont la fenêtre est réduite
  (« EcoQoS »). L'application s'en exempte le temps de la file, comme le
  documente Microsoft, puis rend la main au système.
- **Estimations honnêtes sur un processeur basse consommation.** Les durées
  annoncées avant toute mesure y étaient deux à trois fois trop optimistes ;
  elles s'appuient désormais sur la seule mesure publiée pour cette famille
  (Core Ultra 7 265U), et le preset « Rapide » est conseillé, chiffres à
  l'appui, quand « Qualité maximale » dépasserait la durée de l'audio.
- **Moteur OpenVINO, en option.** Le moteur d'Intel (licence Apache 2.0,
  environ 90 Mo, installé depuis l'application, sans droits d'administrateur)
  transcrit sur la puce graphique intégrée, sur le processeur, et à titre
  expérimental sur le NPU, avec les modèles Whisper déjà convertis en int8 par
  Intel (0,8 Go pour Rapide, 1,6 Go pour Qualité). Seule mesure publiée sur un
  processeur de la même famille : 0,12 x avec turbo sur la puce graphique,
  contre 1,04 x sur le processeur. Les segments horodatés, l'horodatage des
  mots, le glossaire, la reprise après coupure et l'arrêt sont gardés ; la
  probabilité de chaque mot, que ce moteur ne donne pas, est marquée inconnue.
  En cas de panne, CTranslate2 prend le relais sans perdre ce qui est déjà
  transcrit, et un chargement qui ferait tomber l'application suspend le
  réglage au démarrage suivant. Les trois paquets sont posés sans leurs
  dépendances : le module de télémétrie qu'OpenVINO déclare, et qui ne sert
  qu'à son outil de conversion, n'est pas installé.
- **Banc d'essai.** Un extrait de 44 s livré avec l'application (phrases du jeu
  FLEURS, licence CC-BY-4.0) est transcrit sous plusieurs réglages : nombre de
  fils, taille des lots, modèle Rapide et modèle Qualité, chaque moteur et
  périphérique disponible. Chaque essai tourne dans son propre processus, avec
  un délai : un périphérique qui bloque est abandonné sans emporter
  l'application. Le banc conseille le réglage le plus rapide qui reste juste,
  écrit un rapport sans nom d'utilisateur, nom de machine ni chemin, et
  n'applique rien sans un clic. Aussi en ligne de commande :
  `scribouille-verifier.exe --banc`.
- **Réseau d'entreprise filtré** : les messages d'échec de téléchargement
  donnent une voie hors ligne, pour les modèles (recopier leur dossier depuis
  un autre poste) comme pour OpenVINO (déposer les roues dans
  `paquets-hors-ligne`).

Mesures (Ryzen 7 7800X3D, occupé par d'autres programmes, coup sur coup) :

| Réglage, chemin réel de l'application | Français 3 min 06 : calcul, WER | Anglais 2 min 06 : calcul, WER |
|---|---|---|
| Rapide, CTranslate2 par lots, 8 fils | 25,0 s, 8,3 % | 15,7 s, 12,9 % |
| Rapide, OpenVINO processeur | 16,0 s, 8,3 % | 9,9 s, 10,7 % |
| Qualité maximale, CTranslate2 par lots, 8 fils | 66,1 s, 7,3 % | 34,1 s, 8,9 % |
| Qualité maximale, OpenVINO processeur | 44,0 s, 8,5 % | 30,2 s, 8,1 % |

Un mot d'écart vaut environ 0,25 point en français et 0,37 en anglais : les
écarts de justesse tiennent en quelques mots, dans un sens ou dans l'autre.
Dans la vraie fenêtre, après application du conseil du banc, la vidéo de
3 min 06 a été transcrite en 22 s avec le preset Rapide (0,12 x).

La puce graphique Intel et le NPU n'ont pas pu être essayés : la machine de
développement n'en a pas. Le greffon graphique d'OpenVINO voit bien les cartes
AMD, mais ses noyaux n'y compilent pas ; l'application ne garde donc que les
puces Intel.

La séparation des locuteurs passe à pyannote « community-1 ».

Le modèle de septembre 2025 (licence CC-BY-4.0) est essayé en premier : sa
fiche le donne meilleur que 3.1 sur presque tous les jeux de test (AMI IHM :
17,0 % d'erreur de diarisation contre 18,8 %), il tient en un seul dépôt et
fournit la sortie « exclusive » faite pour l'alignement avec une transcription.
3.1 reste essayé ensuite, pour qui n'a accepté que ses conditions. Nouvel outil
`outils/verifier_locuteurs.py` : essai de bout en bout, jeton lu dans un fichier.

Le dépôt public ne porte plus de nom complet : licence, éditeur de
l'exécutable et programme d'installation sont au pseudonyme du projet.

L'application s'appelle Scribouille.

« WhiScribe » entrait en collision avec deux autres projets du même nom, ce
qui rendait le dépôt introuvable et le nom impossible à dire à voix haute.
Le renommage touche tout ce qui se voit : la fenêtre, les README, le guide,
le programme d'installation, la recette de construction et l'adresse du dépôt,
dont les anciennes URL redirigent.

- **Deux choses n'ont pas été renommées, exprès.** Le dossier de données
  `%LOCALAPPDATA%\WhiScribe`, où vivent la configuration, le glossaire, les
  corrections et les modèles téléchargés ; et l'identifiant Inno du programme
  d'installation, qui est ce qui fait qu'une version se pose PAR-DESSUS
  l'ancienne. Les changer aurait donné, sur les postes déjà équipés, une
  deuxième installation à côté de la première et des réglages abandonnés sur
  place. Une mise à jour reste donc une mise à jour, et rien n'est à déplacer.
- **Ce qui a été écrit sous l'ancien nom continue d'être lu.** Les fichiers
  compagnons de confiance produits jusqu'à la 2.3.3 s'ouvrent toujours dans la
  vue de relecture, et une archive de données exportée avant le renommage se
  réimporte sans être prise pour l'export d'un autre logiciel.
- **La désinstallation nettoie ce qu'elle laissait derrière elle** : le gabarit
  pour l'IA et le dossier des reprises restaient sur le disque, et empêchaient
  au passage la suppression du dossier de données.

Le téléchargement des modèles ne s'arrête plus en une seconde sans rien dire.

Sur certaines connexions, le protocole de transfert maison de Hugging Face
(« xet ») rendait la main immédiatement sans transférer un octet, alors que le
même fichier se téléchargeait sans peine depuis un navigateur. L'application
croyait tenir un modèle et échouait plus loin sur un fichier absent.

- **Les poids passent désormais par le HTTPS ordinaire**, celui qui marche
  partout, y compris derrière un antivirus ou un pare-feu d'entreprise. Le
  choix est fait au tout premier instant du programme, avant même que la
  bibliothèque de téléchargement soit chargée, sans quoi il serait sans effet.
  Une variable d'environnement posée à la main par un utilisateur averti garde
  le dernier mot.
- **La bibliothèque native de ce protocole n'est plus embarquée** dans le
  programme d'installation, où elle était ramassée sans avoir été demandée.
- **Le message d'échec nomme la piste du réseau filtrant** : quand le reste
  d'Internet fonctionne mais que le téléchargement échoue encore, la cause est
  presque toujours un antivirus, un pare-feu ou un partage de connexion mobile.

Les durées annoncées se corrigent d'elles-mêmes.

Le preset « Qualité maximale » annonçait 1,35 fois la durée de l'audio et en
demandait 2,07 sur un Ryzen 7800X3D : une réunion de vingt-trois minutes
annoncée pour une demi-heure en prenait trois quarts. Les facteurs livrés
viennent de mesures faites sur une autre machine que la vôtre, ils ne pouvaient
pas tomber juste.

- **Chaque transcription menée à son terme est mesurée**, et c'est le facteur
  observé qui sert aux annonces suivantes. La carte du matériel le précise :
  « mesuré sur cette machine ». Rien à régler, rien qui parte en ligne.
- **La mesure porte sur la transcription seule** : ni le décodage du fichier, ni
  le chargement du modèle, ni la séparation des locuteurs, qui a son propre
  surcoût. Une transcription reprise après coupure n'est pas mesurée, son temps
  de calcul étant réparti sur deux exécutions.
- **Les cinq dernières mesures sont moyennées**, la plus récente et la plus
  longue pesant le plus : une réunion transcrite pendant une sauvegarde du
  système ne fausse pas durablement les annonces. Les enregistrements de moins
  d'une minute et les valeurs aberrantes sont écartés d'entrée.
- **Chaque situation de calcul est suivie à part** : modèle, processeur ou carte
  graphique, et largeur de faisceau, qui à elle seule change le coût du simple
  au double. Un dossier de données recopié sur une autre machine repart d'une
  page blanche plutôt que d'annoncer les durées de la première.
- Au passage, **la documentation de `presets.py` disait vrai** : elle promettait
  cette recalibration depuis des mois sans qu'aucune ligne ne l'implémente.

Le panneau d'aide ne sort plus de l'écran quand l'interface est grossie.

Les fenêtres de l'application étaient bornées à 85 % de la hauteur de l'écran
depuis la 2.3.2, et cela suffisait tant que l'interface restait à sa taille
d'origine. Le grossissement, lui, multiplie tout ce qu'il touche, y compris
cette borne : à 125 %, une fenêtre censée occuper 85 % en réclamait 106, et
le panneau d'aide, le plus long de tous, sortait par le bas sans que rien ne
défile.

- **Les fenêtres se mesurent maintenant sur la fenêtre réelle**, grossissement
  déduit, et non plus sur une hauteur d'écran qui ne veut plus rien dire une
  fois multipliée. Le contenu défile à l'intérieur, l'en-tête et le pied
  restent en place, comme prévu.
- **Le corps de page souffrait du même mal** : au-delà de 100 % de
  grossissement, il dépassait la fenêtre par le bas.
- La taille est reprise à chaque changement de grossissement et à chaque
  redimensionnement de la fenêtre.

La transcription va deux fois et demie plus vite, à qualité égale.

Les passages de parole repérés par la détection de voix sont maintenant décodés
par lots de huit au lieu d'un par un, avec un fil de calcul par cœur physique.
Mesuré coup sur coup sur les mêmes extraits (3 min 06 en français, 2 min 06 en
anglais), sur un Ryzen 7 7800X3D occupé par d'autres programmes :

| Réglage | Français : calcul, WER | Anglais : calcul, WER |
|---|---|---|
| Qualité maximale avant : large-v3, faisceau 8, un à un, 14 fils | 181 s, 7,5 % | 107 s, 9,2 % |
| Qualité maximale 2.4.0 : large-v3, faisceau 5, par lots, 8 fils | 69 s, 7,3 % | 38 s, 8,9 % |
| Rapide avant : turbo, un à un, 14 fils | 49 s, 10,2 % | 29 s, 11,4 % |
| Rapide 2.4.0 : turbo, par lots, 8 fils | 27 s, 8,3 % | 18 s, 12,9 % |

- **Le faisceau de la « Qualité maximale » passe de 8 à 5.** Par lots, la
  largeur 8 alourdissait le calcul de 40 à 90 % sans changer un seul mot du
  texte.
- **Un fil de calcul par cœur physique**, comme le recommande CTranslate2 :
  14 fils sur un 8 cœurs / 16 fils allaient moins vite que 8, et laissaient la
  machine sans souffle.
- **Il en coûte environ 2,5 Go de mémoire** au pic (5,8 Go avec large-v3).
  Sous 12 Go de mémoire vive, l'application garde le traitement un à un.
- **Chaque passage est transcrit sans le texte du précédent.** Les boucles de
  répétition, qui se propageaient d'une fenêtre à l'autre sur les longues
  réunions, n'ont plus de chemin pour le faire. L'option « Garder le contexte »
  du mode avancé ne joue plus que sans lots.
- **Un arrêt demandé attend la fin du lot en cours**, plus d'une minute
  parfois sur processeur avec large-v3 : le message le dit.
- **Point de vigilance relevé à la mesure** : en anglais, le preset « Rapide »
  par lots a sauté une fin de phrase de huit mots que le traitement un à un
  rendait. Rien de tel en français, ni avec large-v3.
- Les mesures de recalibration du traitement par lots sont suivies à part :
  celles déjà prises restent valables pour le traitement un à un.
- **CTranslate2 passe de 4.7.1 à 4.9.0**, à vitesse et texte identiques sur
  les extraits mesurés. La 4.8.1 corrige une division par zéro qui pouvait tuer
  le processus pendant le calcul des horodatages de mots, que l'application
  demande toujours.

La séparation des locuteurs fonctionne avec pyannote.audio 4.

La version 4 de pyannote.audio rend un objet là où la 3 rendait directement les
tours de parole. L'application ne savait pas le lire : l'incident était
rattrapé comme non bloquant, et toute transcription sortait sans locuteurs.
C'est désormais la version « exclusive » des tours, sans chevauchement, qui est
retenue : celle que pyannote destine au rapprochement avec une transcription.

- **Et sans télémétrie.** pyannote.audio 4 envoie par défaut à son éditeur le
  nom du pipeline, la durée de chaque fichier traité et le nombre de locuteurs
  demandé. L'application coupe cet envoi avant de charger la bibliothèque,
  comme elle le promet dans « Vie privée ».
- **Une transcription reprise après une coupure** passait à la séparation des
  locuteurs le seul morceau retranscrit : les étiquettes étaient décalées de la
  position de reprise. Elle reçoit maintenant l'enregistrement entier.

Le glossaire et les corrections d'exemple ne s'appliquent plus d'office.

À la première installation, « Jean Dupont, MonEntreprise, Kubernetes... »
partait en amorce dans chaque transcription, et la règle d'exemple
« mon entreprise => MonEntreprise » réécrivait une tournure française courante.
Les exemples restent visibles dans les deux fichiers, en commentaire. Les
fichiers déjà en place chez un utilisateur ne sont pas touchés.

La carte graphique affichée est la bonne.

Les écrans virtuels des logiciels de bureau à distance (Parsec et consorts)
passaient avant la vraie carte, et la mémoire des cartes de plus de 4 Go était
annoncée à 4 Go, plafond de l'interface Windows interrogée. La carte dédiée la
mieux dotée passe en tête, avec sa vraie mémoire, lue chez le pilote.

---

## 2.3.3

*Publiée le 21 août 2026.*

Un téléchargement de modèle qui échoue le dit, et ne recommence pas de zéro.

La réparation automatique livrée en 2.3.1 supprimait bien le dossier d'un
modèle incomplet, mais le retéléchargement qui suivait pouvait échouer sans
rien dire : huggingface avale la panne réseau et rend le dossier de cache tel
quel, poids manquants compris. L'application croyait donc tenir un modèle,
et l'écran finissait sur « Unable to open file 'model.bin' », un message qui
parle d'un fichier alors que la cause est une connexion coupée ou un disque
trop plein.

- **Les poids sont désormais téléchargés par l'application**, et contrôlés
  juste après. Sans « model.bin » de taille plausible, rien n'est chargé et
  l'incident est annoncé en français : « Le téléchargement du modèle large-v3
  (3,1 Go) a échoué. Vérifiez la connexion Internet et l'espace disque (il
  faut environ 4,0 Go libres), puis relancez le fichier. » Plus aucun message
  technique brut pour ce cas.
- **La cause est nommée quand elle est identifiable.** Un disque trop plein
  est vu AVANT de commencer, et le message oppose la place restante à la
  place nécessaire. Un dépôt injoignable est annoncé comme tel, avec le
  rappel qu'une fois téléchargé le modèle reste local.
- **Un téléchargement coupé reprend où il s'était arrêté.** Le dossier n'est
  plus effacé avant de retélécharger : un échec à 80 % d'un fichier de 3 Go
  ne fait plus tout recommencer. Seuls des poids que le moteur refuse
  d'ouvrir alors qu'ils paraissent sains valent encore un renouvellement du
  dossier, une fois par modèle et par file de traitement, jamais deux.
- **Le hors-ligne est tenu par construction.** Un modèle déjà complet est
  chargé par son dossier, ce qui ne produit plus aucun appel réseau, là où la
  désignation par nom de dépôt interrogeait le hub à chaque chargement.
- **Le contrôle de place avant lancement couvre aussi les modèles du mode
  avancé**, que l'ancien calcul laissait passer sans rien vérifier.

## 2.3.2

*Publiée le 20 août 2026.*

Les mises à jour se vérifient d'un clic, sans attendre le lendemain.

La vérification n'existait qu'au lancement, à condition d'avoir activé le
réglage, et une seule fois par 24 heures : trois conditions à réunir pour
voir passer un bandeau qu'on rate de toute façon si on regarde ailleurs.
Savoir si une nouvelle version existe ne devrait pas demander de relancer
l'application.

- **La fenêtre d'aide**, ouverte par le point d'interrogation en haut à
  droite, se termine désormais par une section « Version et mises à jour ».
  Elle affiche la version installée et porte un bouton « Vérifier les mises à
  jour » qui interroge GitHub tout de suite. Pendant l'appel, le bouton passe
  à « Vérification en cours... » et se désactive.
- **La réponse s'affiche là, dans la fenêtre** : « Vous avez la dernière
  version », ou l'annonce de la version disponible avec un bouton qui ouvre la
  page de la publication dans le navigateur. Le cas rare des versions qui
  demandent une réinstallation est annoncé comme dans le bandeau, avec les
  mêmes mots. Hors ligne, le message reste « Vérification impossible, vérifiez
  votre connexion. », jamais un message technique.
- **Ce bouton ne dépend pas du réglage** de vérification automatique : c'est un
  clic volontaire, il vaut consentement pour cet appel unique, et un libellé le
  dit sous le bouton. Le réglage, lui, continue de ne gouverner que la
  vérification silencieuse au lancement, coupée par défaut.
- **Le bandeau du démarrage est réparé.** L'horodatage de la dernière
  vérification était écrit avant l'appel, donc même quand celui-ci échouait.
  Un poste qui avait essayé pendant que le dépôt était encore privé, et
  recevait un 404, se retrouvait bloqué pour 24 heures de plus à chaque
  lancement, sans jamais retenter. Désormais seule une réponse effectivement
  reçue de GitHub consomme la fenêtre du jour.
- **Les fenêtres se tiennent mieux.** La fenêtre d'aide s'étirait du haut au bas
  de l'écran, sans respiration. Toutes les modales gardent maintenant une marge
  franche en haut comme en bas, leur en-tête et leur pied restent en place, et
  c'est le contenu qui défile entre les deux.

## 2.3.1

*Publiée le 19 août 2026.*

Un modèle laissé à moitié téléchargé se répare tout seul.

Un premier téléchargement de large-v3 interrompu laissait le dossier du
modèle en place, sans ses poids. huggingface le voyait alors comme déjà
présent, et le lancement suivant se terminait sur un message technique brut,
« Unable to open file model.bin ». La seule issue était de supprimer le
dossier à la main, dans un terminal : inacceptable pour un outil qui se veut
prêt à l'emploi.

- **Avant de charger**, l'application contrôle que les poids sont réellement
  là et utilisables : « model.bin » présent dans l'instantané, d'une taille
  plausible, avec sa configuration, et aucun fichier encore en cours de
  réception. Le contrôle traverse les liens symboliques comme les copies,
  les deux formes de rangement que huggingface utilise selon le poste.
- **Si le modèle est incomplet**, son dossier de cache est supprimé, lui seul,
  et le téléchargement repart de zéro dans la foulée, avec les mêmes messages
  que le premier usage. L'interface annonce que le modèle était incomplet et
  qu'il est renouvelé, la file suit son cours, le fichier en cours n'est pas
  perdu. Si le réseau manque, le message reste en français et le fichier est
  traité comme les autres échecs réseau.
- **Un filet de sécurité** rattrape le cas où le contrôle n'aurait rien vu :
  un refus d'ouverture des poids déclenche une réparation puis un seul
  nouvel essai. Plus aucun traceback ne peut remonter à l'écran pour ce motif.
- **Le panneau « Modèles »** ne compte plus un modèle incomplet comme
  téléchargé, il le signale et annonce qu'il sera renouvelé au prochain usage.
- **La vérification de mise à jour** ne crie plus au loup : un dépôt privé
  répond 404 à l'API publique, un quota atteint répond 403. Ce sont des
  « vérification indisponible », désormais journalisés en information. Rien
  n'a jamais été affiché à l'utilisateur dans ces cas, rien ne change de ce
  côté.
- **Le harnais de vérification** couvre l'ensemble sans rien télécharger :
  faux dossiers de cache fabriqués dans un dossier temporaire, détection,
  suppression du bon dossier et de lui seul, enchaînement sur le
  téléchargement, et niveaux de journal de la vérification de mise à jour.

---

## 2.3.0

*Publiée le 19 août 2026.*

La séparation des locuteurs s'installe d'un bouton. Elle était jusqu'ici
réservée à la version source, ce qui revenait à demander à un utilisateur
normal d'installer Python, de cloner un dépôt et de lancer un script pour
obtenir « Locuteur 1 » et « Locuteur 2 ». C'est fini : le panneau
« Locuteurs » porte désormais un bouton qui fait tout, dans les deux modes.

**Le parcours**

- **Avant de lancer**, l'application annonce ce qui va se passer : environ
  0,8 Go à télécharger et 3,6 Go sur le disque en variante processeur,
  6 Go à avoir de libre, et ce qu'il en reste réellement. Ces chiffres sont
  mesurés sur une installation réelle, pas estimés. La confirmation est demandée, et le bouton est refusé
  quand la place manque, avec la raison.
- **Pendant**, la progression s'affiche paquet par paquet, avec le
  pourcentage du téléchargement en cours. Le travail vit dans un processus
  de fond : la transcription reste utilisable, et l'annulation est propre à
  tout instant.
- **Après**, l'import de torch et de pyannote est réellement essayé, dans un
  processus neuf. Ce n'est qu'à cette condition que la fonction est déclarée
  disponible, et elle s'active alors sans redémarrage. Si l'import échoue,
  l'application le dit au lieu de laisser croire à une réussite.
- **Une coupure réseau ne fait pas tout retélécharger.** Le cache vit avec
  les données de l'utilisateur, et une relance ne redemande au réseau que ce
  qui manque. Elle repose en revanche les fichiers, quelques minutes de
  disque : c'est le prix d'une reprise sûre, faute de quoi les fichiers
  tronqués de la tentative interrompue resteraient en place.
- **Un bouton retire l'extension**, avec son poids affiché. La
  désinstallation du programme la compte elle aussi dans la question
  « supprimer vos données », et annonce les gigaoctets concernés.

**Sous le capot**

- **pip est embarqué dans la version installée.** Il devait être collecté en
  fichiers `.py` sur le disque et non dans l'archive du gel : sans cela,
  `pip._vendor.distlib` ne trouve pas son chargeur de ressources et
  l'installation s'arrête sur « Unable to locate finder ». C'est le mode de
  collecte `{"pip": "py"}` du fichier `.spec`.
- **La bibliothèque standard est désormais gelée en entier.** Un gel n'emporte
  que les modules que le programme importe lui-même, ce qui suffisait tant que
  rien ne s'ajoutait après coup. PyTorch, lui, importe des modules dont
  WhiScribe n'a aucun usage : le premier essai s'est arrêté sur
  « No module named 'timeit' ». Quelques mégaoctets de plus, à comparer aux
  gigaoctets téléchargés ensuite.
- **Les paquets vont dans un dossier d'extensions**,
  `%LOCALAPPDATA%\WhiScribe\extensions`, ajouté au chemin d'import au
  démarrage, avant tout import de torch. Le programme installé n'écrit
  toujours rien dans son propre dossier.
- **La variante suit le matériel** : index processeur par défaut, index
  CUDA quand le pilote NVIDIA répond.
- **Correction de deux vrais gâchis, trouvés en installant pour de vrai.**
  pyannote.audio demande « torch>=2.8.0 » et « torchcodec>=0.7.0 » : sans
  contrainte, pip repartait chercher sur PyPI les dernières versions, qui
  embarquent CUDA, écrasant la version processeur à peine posée. Un
  gigaoctet téléchargé pour rien et deux `dist-info` de torch côte à côte.
  Pire pour torchcodec : la version prise était compilée contre un autre
  PyTorch, elle se chargeait sur une erreur « WinError 127, la procédure
  spécifiée est introuvable ». Les versions sont désormais figées et
  répétées au second lot. Le correctif vaut aussi pour
  `installer.bat --locuteurs`.
- **Les dossiers de bibliothèques natives de l'extension sont déclarés à
  Windows** avant tout import. Depuis Python 3.8, un dossier de DLL n'est
  plus fouillé parce qu'il est à côté du module : il faut le nommer.
- **Tout est demandé à pip en une seule fois.** Le découpage en deux passes
  obligeait, pour figer les versions, à renommer PyTorch dans la seconde,
  et « --upgrade » le reposait alors intégralement : trois gigaoctets
  effacés puis recopiés, plusieurs minutes de disque pour rien.
- Limite connue, écrite noir sur blanc : torchcodec cherche les
  bibliothèques partagées de FFmpeg, que WhiScribe ne pose pas, et signale
  bruyamment que ses décodeurs sont inertes. Sans conséquence, la
  diarisation recevant un signal déjà décodé en mémoire.
- Nouveaux modes de diagnostic, sans fenêtre :
  `--installer-locuteurs`, `--verifier-locuteurs` et `--retirer-locuteurs`.
  Le bilan de `--verifier` gagne une ligne « séparation des locuteurs »,
  qui teste l'import réel et non la simple présence des dossiers.

**Interface**

- Le panneau « Locuteurs » a trois états qui se remplacent : composants
  absents avec le bouton et les chiffres, installation en cours avec la
  progression et l'annulation, composants en place avec la bascule
  habituelle et le retrait.
- L'avertissement « non incluse dans la version installée » disparaît, il
  n'a plus lieu d'être. Le jeton Hugging Face reste demandé à part, après :
  ce sont deux choses différentes.
- Textes français et anglais, à parité.

## 2.2.1

*Publiée le 18 août 2026.*

- Correction : les boutons Exporter et Importer débordaient de la colonne des réglages et y créaient un défilement horizontal, ils sont empilés en pleine largeur et le volet refuse désormais tout défilement horizontal.
- Correction : le clic sur la zone de dépôt (et Ctrl+O) n'ouvrait jamais le sélecteur de fichiers, le filtre d'extensions étant séparé par des espaces là où pywebview exige des points-virgules. Tous les filtres de dialogue sont désormais validés par le parseur de pywebview lui-même.

## 2.2.0

*Publiée le 18 août 2026.*

Relire une transcription dans l'application, repérer ce que le modèle a mal
entendu, corriger une fois pour toutes, et préparer un compte rendu. Et, tout
autour, ce qui fait gagner du temps sans rien demander : un dossier surveillé,
une reprise après coupure, une interface qui existe enfin en anglais.

**Vue de lecture**

- Une transcription s'ouvre désormais **dans l'application** : depuis l'onglet
  « Transcriptions », depuis les sorties d'un fichier qui vient de se terminer,
  ou par le bouton de relecture de la ligne. Paragraphes lisibles, locuteurs
  affichés quand ils ont été séparés, thème clair ou sombre respecté.
- Les sous-titres `.srt` et `.vtt` gardent leur aperçu brut : personne ne lit
  un fichier de sous-titres en paragraphes.

**Confiance mot à mot**

- Le moteur donne déjà la probabilité de chaque mot. Elle est maintenant
  conservée et **seuls les mots incertains sont surlignés**, en ambre discret :
  sous 0,50 la marque est légère, sous 0,30 elle est plus nette. Le reste du
  texte n'est pas décoré. Les seuils sont calés sur la distribution réelle des
  probabilités, médiane autour de 0,90 et premier décile autour de 0,48.
- **N'importe quel mot** affiche sa confiance au survol, par une infobulle
  native, posée à la volée pour ne pas alourdir un texte de plusieurs milliers
  de mots.
- Une légende sobre rappelle ce que veut dire le surlignage, avec le nombre de
  mots concernés.
- Ces données vivent dans un **fichier compagnon `.json`**, écrit à côté du
  texte, de même nom, format versionné et documenté. Il pèse quelques dizaines
  de kilooctets par heure d'audio.
- **Il est facultatif** : une transcription produite avant cette version, ou
  avec l'option coupée, s'ouvre normalement, sans surlignage, avec une phrase
  qui l'explique.

**Copier pour l'IA**

- Un bouton met dans le presse-papiers un **gabarit d'instructions**, les
  métadonnées de l'enregistrement et le texte complet, prêts à coller dans
  l'assistant de son choix. Aucune marque, aucun envoi, aucun compte.
- Le gabarit est un fichier à vous, `gabarit-ia.txt`, créé au premier usage
  dans le dossier de vos données et modifiable depuis les réglages. Variables
  reconnues : `{texte}`, `{fichier}`, `{date}`, `{duree}`, `{locuteurs}`,
  `{modele}`.
- Le gabarit **voyage avec vos données** : il est joint à l'export du panneau
  « Mes données » quand il existe, repris à l'import, et l'aperçu le signale
  avant toute écriture. Une archive produite par la version 2.1.0 s'importe
  toujours, et laisse en place le gabarit de ce poste.

**Corrections apprises**

- Sélectionner un mot ou une courte expression dans la vue de lecture propose
  de le corriger. L'application demande alors d'**ajouter la règle aux
  corrections**, applique le remplacement au texte affiché et au fichier `.txt`
  enregistré, met le compagnon à jour, et n'écrit jamais deux fois la même
  règle. L'en-tête du fichier, qui décrit la production, n'est pas touché.
- Les règles apprises sont rangées dans une section dédiée de
  `corrections.txt`, où elles restent modifiables à la main.
- Débrayable dans les réglages, active par défaut.

**Sauvegarde progressive et reprise**

- Le texte est écrit **au fil des segments**. Une coupure de courant, une
  fermeture de fenêtre ou un plantage ne fait plus perdre le calcul déjà fait.
- Au lancement suivant, l'application propose de **reprendre** : le fichier
  retourne dans la file, la transcription repart du dernier segment enregistré,
  et le **temps déjà écoulé est conservé** dans le compteur.
- Mesuré avant d'être intégré, dix passes alternées sur le même audio :
  **0,23 % du temps de transcription** avec le modèle le plus rapide, donc le
  cas le plus défavorable, environ 2 ms par segment écrit. Aucune mémoire
  supplémentaire mesurable, et environ 9 Ko de fichiers de reprise par minute
  d'audio, effacés dès qu'une transcription se termine normalement. Les traces
  de plus de trente jours, et celles dont le fichier source a disparu, sont
  purgées au démarrage.
- Débrayable dans les réglages, active par défaut.

**Dossier surveillé**

- Un dossier peut être **désigné pour être surveillé** : les enregistrements
  qui y arrivent rejoignent la file tout seuls. Pensé pour un dictaphone ou un
  enregistreur de réunion qui dépose toujours au même endroit.
- **Coupé par défaut**, et sans aucune dépendance nouvelle : le dossier est
  regardé toutes les dix secondes, uniquement quand l'option est active.
- Un fichier n'est pris que lorsque **sa taille a cessé de bouger** : une copie
  de 300 Mo en cours d'écriture n'est pas transcrite à moitié.
- Les fichiers déjà traités sont **mémorisés sur disque** : rien n'est
  retranscrit au redémarrage. Ce qui était déjà là quand vous désignez le
  dossier est considéré comme connu, et un bouton « Reprendre tout le dossier »
  remet tout en jeu.
- Un dossier supprimé, débranché ou illisible **se signale en défaut sans rien
  casser**, le dit une seule fois, et la surveillance repart d'elle-même.
- Indicateur discret dans l'en-tête quand la surveillance est active.

**Vérification des mises à jour, facultative et coupée par défaut**

- Nouveau panneau « Application ». Tant que l'option est coupée,
  **l'application ne fait aucun appel réseau sortant**, hors le téléchargement
  d'un modèle que vous demandez. C'est écrit tel quel dans le réglage.
- Activée, elle interroge la liste publique des versions du projet au
  lancement, **au plus une fois par 24 heures**, avec un délai d'attente court.
  Un échec, hors ligne ou pare-feu, ne produit **aucun message** : journal
  seulement.
- Une version plus récente affiche un bandeau discret et un bouton qui ouvre la
  page de la version dans le navigateur. Rien ne se télécharge tout seul.
- Comparaison de versions **numérique** : 2.10.0 est bien supérieur à 2.9.0, et
  une préversion précède la version finale du même numéro.
- Le mainteneur peut écrire `[reinstallation-requise]` dans les notes d'une
  version : le bandeau annonce alors la désinstallation préalable, en précisant
  que données et modèles sont conservés. Marqueur documenté dans le README et
  dans le workflow de publication.

**Espace utilisé**

- Nouveau bouton dans le panneau « Modèles » : taille et **chemin réel** des
  modèles, de vos données et du programme, avec un bouton pour ouvrir chaque
  emplacement.
- Mesure en tâche de fond, la fenêtre ne se fige pas sur un dossier de trois
  gigaoctets, et **aucune élévation de droits n'est demandée**.

**Nom des fichiers produits**

- Le nommage devient un **motif configurable**, avec quatre variables :
  `{nom}`, `{date}`, `{heure}`, `{modele}`. Aperçu du résultat sous le champ
  pendant la frappe.
- Le défaut ne change pas : champ vide, on retrouve exactement
  `AAAA-MM-JJ-nom-du-fichier`. Les caractères refusés par Windows sont
  signalés au lieu d'être avalés, et la protection contre l'écrasement reste
  la même.

**Dépôt et raccourcis**

- Déposer un **dossier** sur la fenêtre ajoute ses fichiers audio, premier
  niveau seulement, en disant combien ont été retenus et combien écartés.
- Déposer une **archive d'export WhiScribe** propose l'import, avec l'aperçu
  habituel avant toute écriture.
- `Ctrl` + `O` ouvre le sélecteur de fichiers, `Ctrl` + `Entrée` lance la
  transcription, `Échap` ferme la fenêtre du dessus. Rappelés dans l'aide.

**Progression dans la barre des tâches**

- L'icône de la barre des tâches se remplit pendant le calcul, et passe
  brièvement au rouge sur un échec avant de s'effacer. Aucune notification,
  aucun clignotement, aucune fenêtre qui passe devant. Se coupe dans les
  réglages.

**Indicateur de langue**

- Une ligne sous le sélecteur annonce la qualité à attendre, « excellente »,
  « bonne » ou « variable », d'après les taux d'erreur publiés pour
  `large-v3`. Aucune proposition d'un autre modèle : c'est déjà le meilleur
  multilingue disponible.

**Réglages et outils**

- Nouveau panneau « Relecture » : confiance des mots, corrections apprises,
  sauvegarde progressive, écoute de l'audio pendant la relecture
  (expérimentale, coupée par défaut), et accès au gabarit pour l'IA.
- Quatre harnais reproductibles dans `outils/` : la mesure du coût de la
  sauvegarde progressive, la vérification de bout en bout de la chaîne de
  relecture, celle des fonctions périphériques, qui éprouve la scrutation du
  dossier surveillé sur de vrais fichiers, la comparaison de versions, le motif
  de nommage, la mesure d'espace et l'amorce du glossaire, et celle de l'import
  et de l'export de vos données, qui rejoue un aller-retour complet, gabarit
  compris, et la relecture d'une archive de l'ancien format. Sans réseau ni
  fenêtre, dans un dossier temporaire, sans jamais toucher à vos fichiers.

**Français et anglais**

- L'interface existe désormais **en français et en anglais**, entièrement :
  libellés, aides, encarts, journal utilisateur, modales, messages d'erreur
  traduits, avertissements matériels, phrases de recommandation, presets, états
  de la file, et l'en-tête des fichiers produits.
- Au premier lancement, l'application **suit la langue de Windows** : français
  si Windows est en français, **anglais dans tous les autres cas**, y compris
  quand la locale est illisible. C'est une application publiée pour un public
  mondial, l'anglais est le repli.
- Le choix se change dans les réglages, panneau « Application », ligne
  « Langue de l'interface », et il est **appliqué tout de suite**, sans
  redémarrage : les libellés sont reposés et l'interface redemande à Python ses
  propres textes.
- **Ce réglage est sans effet sur la langue parlée.** Le sélecteur « Langue
  parlée » pilote le moteur de transcription, celui-ci pilote l'affichage : un
  anglophone transcrit du français sans rien changer.
- L'**amorce envoyée au moteur** à partir de votre glossaire suit elle aussi la
  langue parlée, pas celle de l'interface : sa phrase d'introduction est lue par
  le modèle comme un début de texte, une phrase française pousserait le décodeur
  vers le français au milieu d'un enregistrement anglais. Le budget de 224
  jetons est compté sur la forme réellement envoyée.
- **Rien de déjà écrit n'est retraduit.** L'en-tête d'un `.txt` porte la langue
  d'interface du moment de sa production, et la vue de lecture sait relire les
  en-têtes des deux langues. `vocabulaire.txt`, `corrections.txt` et
  `gabarit-ia.txt` sont créés dans la langue du moment, puis n'y touchent plus
  jamais : ces fichiers appartiennent à l'utilisateur. La section des règles
  apprises est reconnue dans les deux langues, pour qu'un `corrections.txt`
  français ne se voie pas ajouter une seconde section en anglais.
- Le **journal de bord technique de `logs/` reste en français** : il s'adresse
  au mainteneur et sert au diagnostic des incidents rapportés au dépôt. Ce que
  l'utilisateur lit dans la barre du bas, lui, suit la langue de l'interface.
- Les nombres, les unités et les dates suivent la langue : virgule décimale et
  « Go » en français, point décimal et « GB » en anglais.
- **Aucune dépendance nouvelle, aucun framework.** Deux catalogues jumelés de
  dictionnaires par langue, `app/langues.py` et `web/langues.js`, une fonction
  `t()` de substitution nommée et un pluriel explicite. Le HTML ne porte plus
  aucun texte : tout passe par des attributs `data-i18n`.
- Le **programme d'installation est bilingue** lui aussi, désinstallation
  comprise. Inno Setup retient la langue de Windows tout seul, l'anglais en
  tête de liste faisant office de repli.
- Cinquième harnais, `outils/verifier_traductions.py` : parité des clés
  français et anglais des deux côtés, existence de toute clé citée par le code,
  absence de français en dur dans `web/app.js` et `web/index.html`, égalité des
  variables de substitution entre les deux langues, et chasse aux tirets
  cadratins. Sort avec le code 0 si tout passe.

**Documentation, en vue du passage en public**

- Le README devient **anglais par défaut**, avec sa version française dans
  `README.fr.md` et un lien de bascule en tête des deux fichiers. Structure
  identique de part et d'autre, resserrée : promesse, installation en trois
  lignes, fonctionnalités, vie privée, limites connues, voie source, le détail
  technique replié dans des sections dépliables.
- Nouveau `CONTRIBUTING.md` : setup de développement, harnais de `outils/` à
  faire tourner, et le français comme langue source des chaînes avec parité
  anglaise vérifiée par `outils/verifier_traductions.py`.
- Gabarits d'issues dans `.github/ISSUE_TEMPLATE/` : rapport de bug qui demande
  la version, le mode d'installation et le **fichier de journal**, jamais
  l'audio, et demande de fonctionnalité. Les issues vides sont désactivées.
- `docs/publication-github.md` : check-list de mise en public, description et
  topics du dépôt, aperçu social, réglages recommandés, et une évaluation
  argumentée de la publication sur winget, sans manifeste à ce stade.

---

## 2.1.0

Import et export des données personnelles par fichier. Un glossaire
professionnel se construit sur des mois et n'a pas sa place dans un dépôt en
ligne : un seul fichier zip suffit désormais à le sauvegarder ou à le porter
sur un autre poste.

**Nouveau panneau « Mes données », dans les réglages**

- **Exporter mes données** écrit une archive `whiscribe-donnees-AAAA-MM-JJ.zip`
  à l'emplacement choisi : glossaire, corrections, réglages, et un manifeste
  qui note la version de l'application, la date et la liste des fichiers.
- Le **jeton Hugging Face n'est jamais exporté**, c'est un secret personnel.
  Les modèles et les journaux non plus. L'interface le dit à l'écran.
- **Importer des données** relit une archive de ce type. L'archive est
  validée avant tout : zip réellement lisible, manifeste présent et cohérent,
  aucun fichier inattendu, aucun chemin qui sortirait de l'archive, tailles
  bornées.
- Un **aperçu** s'affiche avant la moindre écriture : nombre de termes et de
  règles apportés face à ceux déjà en place, réglages qui changeraient avec
  leur valeur avant et après. Il faut confirmer pour que quoi que ce soit soit
  remplacé.
- **Sauvegarde automatique avant tout import**, dans
  `whiscribe-donnees-avant-import-AAAA-MM-JJ-HHMMSS.zip`, posée dans le
  dossier de vos données, dont l'emplacement est affiché. Si cette sauvegarde
  échoue, l'import est annulé plutôt que risqué. Elle se réimporte comme
  n'importe quel export pour revenir en arrière.
- Le **dossier de sortie et le dossier des modèles ne sont repris que s'ils
  existent** sur le poste d'arrivée. Sinon les valeurs locales sont conservées
  et l'aperçu le signale.
- L'interface se recharge seule après un import : ni redémarrage ni
  manipulation.
- Les refus sont expliqués en français, du fichier corrompu à l'archive qui
  n'est pas un export WhiScribe, et toutes les opérations sont journalisées.

---

## 2.0.0

Première version installable. Jusqu'ici, faire tourner l'outil demandait
d'installer Python et de lancer un script. Ce n'est plus le cas : un programme
d'installation unique se télécharge depuis les Releases, se double-clique, et
l'application fonctionne sur un poste où rien n'a été préparé.

**Programme d'installation**

- Fichier unique `WhiScribe-Setup-2.0.0.exe`, assistant en français.
- Installation par utilisateur, **sans droits administrateur**, dans
  `%LOCALAPPDATA%\Programs\WhiScribe`. Le dossier reste modifiable.
- Page dédiée au choix de l'emplacement des modèles de transcription : ils
  pèsent de 1,6 à 3,1 Go et peuvent partir sur un autre disque. Ce choix reste
  modifiable ensuite dans les réglages de l'application.
- Raccourci dans le menu Démarrer, icône sur le Bureau en option.
- Le composant Microsoft WebView2, nécessaire à l'affichage, est détecté et
  téléchargé depuis le site de Microsoft s'il manque.
- Réinstaller par-dessus met à jour sans rien perdre : réglages, glossaire,
  corrections et modèles sont conservés.
- La désinstallation pose deux questions distinctes, avec la taille réellement
  occupée, avant de toucher aux modèles et aux données personnelles. Répondre
  non aux deux ne retire que le programme.

**Application**

- L'application s'appelle désormais **WhiScribe**.
- La version installée écrit ses réglages, ses journaux et ses modèles dans
  `%LOCALAPPDATA%\WhiScribe`, plus dans son dossier d'installation. Lancée
  depuis les sources, elle continue de tout ranger à côté du script.
- Nouveau panneau « Modèles » dans les réglages : emplacement, place occupée,
  espace libre, modèles déjà téléchargés, et changement de dossier.
- Le téléchargement du premier modèle est annoncé avant d'être lancé, avec sa
  taille et son emplacement. Un poste sans connexion reçoit une explication au
  lieu d'une erreur technique, et un disque trop plein est signalé avant de
  commencer.
- Dans la version installée, la séparation des locuteurs indique clairement
  qu'elle n'est pas incluse, et pourquoi, au lieu d'échouer. Elle reste
  disponible dans la version source.
- Démarrage nettement plus rapide : la passerelle vers l'interface n'expose plus
  l'objet fenêtre, dont l'inspection coûtait une vingtaine de secondes au
  lancement.
- Nouveau mode `--verifier` : contrôle les composants, FFmpeg et l'écriture des
  dossiers de travail, puis sort avec un code de retour. La chaîne de
  publication le lance sur l'exécutable construit avant de fabriquer le
  programme d'installation.

**Limites assumées**

- Les modèles de transcription ne sont pas embarqués : ils se téléchargent au
  premier usage, une seule fois. Ensuite l'application n'a plus besoin d'Internet.
- La séparation des locuteurs reste hors du programme d'installation, parce
  qu'elle repose sur PyTorch, environ 2,5 Go.
- Windows 64 bits uniquement.

---

## 1.0.0

Version initiale, installation depuis les sources par `installer.bat`.

- Transcription entièrement locale par faster-whisper (CTranslate2), sans compte
  ni clé d'API, presets « Qualité maximale » et « Rapide ».
- Séparation des locuteurs optionnelle par pyannote.audio.
- Glossaire et règles de correction, sorties `.txt`, `.srt` et `.vtt`.
- Détection du matériel, estimations de durée, garde-fous mémoire.
- Diagnostic en français et journaux horodatés.
