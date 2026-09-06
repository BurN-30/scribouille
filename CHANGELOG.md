# Journal des versions

Les versions publiées sont disponibles dans l'onglet
[Releases](../../releases). Chaque entrée de ce fichier sert de notes de
version : la chaîne de publication en extrait la section correspondant au tag.

---

## 2.4.0

*Non publiée.*

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
