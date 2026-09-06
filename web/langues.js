/* =========================================================================
   Scribouille : catalogue des chaînes de l'interface web.

   Jumeau de `app/langues.py`, qui porte les chaînes fabriquées par Python.
   Les deux fichiers sont indépendants, mais soumis à la même règle : les clés
   du français et celles de l'anglais coïncident exactement, des deux côtés.
   `outils/verifier_traductions.py` le vérifie et échoue si une clé manque.

   Trois manières d'utiliser ces textes :

     t('cle')                       texte simple
     t('cle', {nom: valeur})        substitution littérale de {nom}
     tn('cle', n, {...})            pluriel, entre 'cle.un' et 'cle.autres'

   La substitution est un remplacement littéral, jamais un `format` : certains
   textes contiennent des accolades qui doivent rester telles quelles.

   Les libellés du HTML sont posés par `traduirePage()`, qui lit les attributs
   data-i18n, data-i18n-html, data-i18n-title, data-i18n-placeholder et
   data-i18n-aria. Le HTML ne contient donc aucun texte en dur.
   ========================================================================= */

'use strict';

const TRADUCTIONS = {

/* ------------------------------------------------------------------ FRANÇAIS */
fr: {

  /* -- unités et formats ------------------------------------------------ */
  'format.decimal': ',',
  'format.heure': 'fr-FR',
  'unite.pourcent': '%',

  /* -- en-tête ---------------------------------------------------------- */
  'ui.entete.local': '100 % local',
  'ui.entete.local_titre': 'Aucune donnée ne quitte cette machine',
  'ui.entete.theme': 'Changer de thème',
  'ui.entete.aide': 'Aide',

  /* -- bandeau de mise à jour ------------------------------------------- */
  'ui.maj.voir': 'Voir la version',
  'ui.maj.masquer': 'Masquer',
  'ui.maj.reinstallation': 'Scribouille {version} est disponible. Cette version demande de '
    + 'désinstaller puis réinstaller : vos données et vos modèles sont conservés.',
  'ui.maj.par_dessus': 'Scribouille {version} est disponible. Téléchargez la mise à jour, '
    + "elle s'installera par-dessus sans rien vous faire perdre.",
  'ui.maj.journal': 'Version {version} disponible.',
  'ui.maj.activee': 'La page des versions du projet sera interrogée au lancement, au plus '
    + 'une fois par jour.',
  'ui.maj.coupee': 'Aucun appel réseau sortant ne sera fait, hors téléchargement des '
    + 'modèles que vous demandez.',

  /* -- matériel --------------------------------------------------------- */
  'ui.materiel.analyse': 'Analyse du matériel...',
  'ui.materiel.processeur': 'Processeur',
  'ui.materiel.coeurs': 'Cœurs',
  'ui.materiel.memoire': 'Mémoire vive',
  'ui.materiel.gpu': 'Carte graphique',
  'ui.materiel.npu': 'Circuit neuronal',
  'ui.materiel.calcul': 'Calcul retenu',
  'ui.materiel.systeme': 'Système',
  'ui.materiel.detail_coeurs': '{physiques}{logiques} logiques, {fils} utilisés',
  'ui.materiel.physiques': '{n} physiques, ',
  'ui.materiel.ram': '{total} Go',
  'ui.materiel.ram_libre': '{total} Go ({libre} Go libres)',
  'ui.materiel.gpu_memoire': '{nom}, {go} Go',
  'ui.materiel.sans_gpu': 'aucune carte dédiée détectée',
  'ui.materiel.calcul_cuda': 'NVIDIA CUDA, précision float16',
  'ui.materiel.calcul_cpu': 'processeur, quantification int8',
  'ui.materiel.estimation': "environ {duree} pour une heure d'audio (facteur {facteur})",
  'ui.materiel.estimation_mesuree': "environ {duree} pour une heure d'audio "
    + '(facteur {facteur}, mesuré sur cette machine)',
  'ui.materiel.avis': "Estimations, pas des garanties : l'interface affiche le temps "
    + 'réellement mesuré à chaque transcription.',

  /* -- presets ---------------------------------------------------------- */
  'ui.preset.conseille': 'conseillé ici',
  'ui.preset.chiffres': "{modele} · environ {duree} pour une heure d'audio · "
    + 'téléchargement {poids}',
  'ui.preset.modele_du_preset': 'Modèle du preset',
  'ui.preset.option_modele': '{nom}, {taille}, qualité {qualite}',

  /* -- zone de dépôt ---------------------------------------------------- */
  'ui.depot.principal': 'Glissez vos enregistrements ici',
  'ui.depot.secondaire': 'ou cliquez pour parcourir vos fichiers',
  'ui.depot.formats': 'm4a, mp3, wav, ogg, flac, opus, webm, wma, et les vidéos courantes',

  /* -- onglets et file -------------------------------------------------- */
  'ui.onglet.file': "File d'attente",
  'ui.onglet.historique': 'Transcriptions',
  'ui.bouton.vider': 'Vider',
  'ui.file.vide': 'Aucun fichier en attente.',
  'ui.file.vide_aide': 'Glissez vos enregistrements dans la zone ci-dessus.',
  'ui.historique.vide': 'Aucune transcription dans le dossier de sortie.',
  'ui.ligne.calcul': 'environ {duree} de calcul',
  'ui.ligne.ecoule': 'écoulé {duree}',
  'ui.ligne.restant': 'reste {duree}',
  'ui.ligne.termine': 'Terminé en {duree}',
  'ui.ligne.facteur': "{facteur} x la durée de l'audio",
  'ui.ligne.locuteurs': '{n} locuteurs',
  'ui.ligne.corrections': '{n} corrections',
  'ui.ligne.echec': 'Échec',
  'ui.ligne.annule': 'Annulé',
  'ui.ligne.arrete': 'Arrêté avant la fin',
  'ui.ligne.lire': 'Lire la transcription',
  'ui.ligne.journal': 'Ouvrir le journal',
  'ui.ligne.retirer': 'Retirer',

  /* -- réglages : qualité ----------------------------------------------- */
  'ui.section.qualite': 'Qualité de transcription',

  /* -- réglages : langue et sortie -------------------------------------- */
  'ui.section.langue_sortie': 'Langue et sortie',
  'ui.champ.langue_parlee': 'Langue parlée',
  'ui.langue.fr': 'Français',
  'ui.langue.en': 'Anglais',
  'ui.langue.es': 'Espagnol',
  'ui.langue.de': 'Allemand',
  'ui.langue.it': 'Italien',
  'ui.langue.nl': 'Néerlandais',
  'ui.langue.pt': 'Portugais',
  'ui.langue.pl': 'Polonais',
  'ui.langue.ro': 'Roumain',
  'ui.langue.ar': 'Arabe',
  'ui.langue.auto': 'Détection automatique',
  'ui.qualite.excellente': "Qualité attendue : excellente, c'est une des langues les mieux "
    + 'couvertes.',
  'ui.qualite.bonne': 'Qualité attendue : bonne, quelques noms propres à relire de plus près.',
  'ui.qualite.variable': "Qualité attendue : variable selon l'accent et la prise de son, "
    + 'relisez le texte.',
  'ui.qualite.auto': "La langue est reconnue au début de l'enregistrement. La préciser reste "
    + "plus sûr, surtout sur un audio de salle.",
  'ui.champ.dossier_sortie': 'Dossier de sortie',
  'ui.titre.choisir_dossier': 'Choisir un dossier',
  'ui.titre.ouvrir_dossier': 'Ouvrir le dossier',
  'ui.champ.motif': 'Nom des fichiers produits',
  'ui.aide.motif': 'Variables : <code>{nom}</code>, <code>{date}</code>, '
    + "<code>{heure}</code>, <code>{modele}</code>. Champ vide, le nommage habituel s'applique.",
  'ui.motif.defaut': 'Par défaut : {exemple}',
  'ui.motif.exemple': 'Exemple : {exemple}',
  'ui.motif.enregistre': 'Nom des fichiers produits : {motif}.',
  'ui.champ.formats': 'Formats produits',
  'ui.format.txt': 'Texte (.txt)',
  'ui.format.srt': 'Sous-titres (.srt)',
  'ui.format.vtt': 'Sous-titres (.vtt)',
  'ui.format.horodatage': 'Horodater chaque paragraphe du texte',
  'ui.format.un_minimum': 'Au moins un format de sortie doit rester coché.',

  /* -- réglages : dossier surveillé ------------------------------------- */
  'ui.section.veille': 'Dossier surveillé',
  'ui.veille.bascule': 'Surveiller un dossier',
  'ui.veille.coupee': 'Coupée',
  'ui.veille.champ': 'Dossier scruté',
  'ui.veille.reprendre_tout': 'Reprendre tout le dossier',
  'ui.aide.veille': 'Les enregistrements déposés dans ce dossier rejoignent la file tout '
    + 'seuls, une fois leur copie terminée. Le dossier est regardé toutes les dix secondes, '
    + 'uniquement quand l\'option est active, et les fichiers déjà transcrits ne sont jamais '
    + 'repris.',
  'ui.veille.indic_actif': 'Surveillance active',
  'ui.veille.indic_defaut': 'Dossier injoignable',
  'ui.veille.etat_defaut': 'En défaut, dossier injoignable',
  'ui.veille.etat_actif': 'Active, regardé toutes les {n} secondes',
  'ui.veille.titre': 'Dossier surveillé : {dossier}',

  /* -- réglages : vocabulaire ------------------------------------------- */
  'ui.section.vocabulaire': 'Vocabulaire',
  'ui.aide.vocabulaire': 'Les noms propres, sociétés et termes anglais sont ce que la '
    + 'transcription écorche le plus. Deux réglages y répondent.',
  'ui.voc.glossaire': 'Souffler le glossaire au modèle',
  'ui.voc.corrections': 'Appliquer les corrections',
  'ui.bouton.glossaire': 'Glossaire',
  'ui.bouton.corrections': 'Corrections',
  'ui.voc.aucun_terme': 'Aucun terme, à remplir',
  'ui.voc.termes.un': '{n} terme actif',
  'ui.voc.termes.autres': '{n} termes actifs',
  'ui.voc.tronque': ' sur {total}, liste tronquée',
  'ui.voc.aucune_regle': 'Aucune règle',
  'ui.voc.regles.un': '{n} règle',
  'ui.voc.regles.autres': '{n} règles',
  'ui.voc.lignes_erreur': ', {n} ligne(s) en erreur',
  'ui.voc.glossaire_enregistre': 'Glossaire enregistré. {message}',
  'ui.voc.regles_enregistrees': '{n} règle(s) de correction enregistrée(s).',

  /* -- réglages : relecture --------------------------------------------- */
  'ui.section.relecture': 'Relecture',
  'ui.aide.relecture': "Ce qui se passe une fois la transcription écrite : la relire dans "
    + "l'application, repérer les passages incertains, corriger, préparer un compte rendu.",
  'ui.relecture.compagnon': 'Enregistrer la confiance des mots',
  'ui.relecture.compagnon_aide': 'Un petit fichier .json à côté de chaque texte',
  'ui.relecture.apprises': 'Mémoriser les corrections relues',
  'ui.relecture.apprises_aide': "Proposer d'ajouter la règle aux corrections",
  'ui.relecture.sauvegarde': 'Sauvegarde progressive',
  'ui.relecture.sauvegarde_aide': 'Une interruption ne perd plus le travail fait',
  'ui.relecture.audio': "Écouter l'audio pendant la relecture",
  'ui.relecture.audio_aide': 'Expérimental, cliquer un paragraphe joue l\'extrait',
  'ui.bouton.gabarit': "Gabarit pour l'IA",
  'ui.aide.gabarit': "Le texte d'instructions copié avec la transcription par le bouton "
    + '« Copier pour l\'IA » de la vue de lecture. Il vous appartient.',

  /* -- réglages : locuteurs --------------------------------------------- */
  'ui.section.locuteurs': 'Locuteurs',
  'ui.loc.bascule': 'Séparer les locuteurs',
  'ui.loc.nombre': 'Nombre de participants',
  'ui.loc.auto': 'Détection automatique',
  'ui.aide.locuteurs': 'Préciser le nombre exact améliore nettement le découpage.',
  'ui.loc.jeton_a_saisir': 'Jeton Hugging Face à renseigner',
  'ui.loc.configurer': "Configurer l'accès",
  'ui.loc.modifier_jeton': 'Modifier le jeton',
  'ui.loc.active': 'Active',
  'ui.loc.disponible': 'Disponible',

  /* -- réglages : installation de la séparation des locuteurs ------------ */
  'ui.ext.absente': 'Composants non installés',
  'ui.ext.chiffres': '{telechargement} Go à télécharger, {installee} Go une fois installée. '
    + 'Il faut {requis} Go de libre sur ce disque, il en reste {libre}.',
  'ui.ext.installer': 'Installer la séparation des locuteurs',
  'ui.ext.aide': "Un seul téléchargement, une seule fois. Vous pouvez continuer à transcrire "
    + 'pendant ce temps.',
  'ui.ext.annuler': "Annuler l'installation",
  'ui.ext.aide_en_cours': "Le téléchargement se poursuit en arrière-plan. L'application reste "
    + 'utilisable, et une annulation ne perd rien de ce qui est déjà reçu.',
  'ui.ext.demarrage': 'Démarrage...',
  'ui.ext.retirer': 'Retirer la séparation des locuteurs ({taille} Go)',
  'ui.ext.note_installee': 'Composants installés dans vos données personnelles, variante '
    + '{variante}.',
  'ui.ext.note_sources': "Composants installés dans l'environnement « .venv » du projet.",
  'ui.ext.variante_cpu': 'processeur',
  'ui.ext.variante_cuda': 'carte NVIDIA',
  'ui.ext.place_manquante': "Il n'y a pas assez de place sur ce disque. Faites de l'espace, "
    + 'puis revenez ici.',
  'ui.ext.echec_lancement': "L'installation n'a pas pu démarrer.",
  'ui.ext.modale.titre': 'Installer la séparation des locuteurs',
  'ui.ext.modale.intro': "Cette fonction reconnaît les voix et étiquette chaque passage "
    + "« Locuteur 1 », « Locuteur 2 ». Elle repose sur PyTorch, qui n'est pas livré avec "
    + "l'application parce qu'il pèse à lui seul plus que tout le reste.",
  'ui.ext.modale.duree': 'Comptez plusieurs minutes selon votre connexion. Le téléchargement se '
    + "fait en arrière-plan : l'application reste utilisable, et il reprend là où il s'arrête.",
  'ui.ext.modale.lancer': 'Installer',

  /* -- réglages : modèles ----------------------------------------------- */
  'ui.section.modeles': 'Modèles',
  'ui.bouton.changer': 'Changer',
  'ui.bouton.stockage': 'Espace utilisé',
  'ui.modeles.tous': 'Tous les modèles sont téléchargés, {occupe} occupés',
  'ui.modeles.partiels': '{present} modèle(s) sur {total} téléchargé(s), {occupe} occupés',
  'ui.modeles.occupe': '{occupe} occupés',
  'ui.modeles.aide': 'Les modèles se téléchargent une seule fois, au premier usage{tailles}. '
    + 'Espace libre sur ce disque : {libre}.',
  'ui.modeles.tailles': ' ({liste})',
  'ui.modeles.incomplets': 'Modèle incomplet détecté ({liste}) : un téléchargement a été '
    + 'interrompu. Il sera renouvelé tout seul au prochain usage, rien à faire.',

  /* -- réglages : mes données ------------------------------------------- */
  'ui.section.donnees': 'Mes données',
  'ui.donnees.etat': 'Glossaire, corrections, gabarit pour l\'IA et réglages',
  'ui.bouton.exporter': 'Exporter mes données',
  'ui.bouton.importer': 'Importer des données',
  'ui.aide.donnees': 'Un seul fichier zip pour sauvegarder votre glossaire professionnel ou '
    + 'le porter sur un autre poste, sans dépôt Git ni service en ligne. Le jeton Hugging '
    + "Face, les journaux et les modèles n'y sont jamais mis.",

  /* -- réglages : application ------------------------------------------- */
  'ui.section.application': 'Application',
  'ui.champ.langue_interface': "Langue de l'interface",
  'ui.aide.langue_interface': 'Change les libellés de la fenêtre, tout de suite. La langue '
    + 'parlée dans vos enregistrements se règle plus haut, les deux sont indépendantes.',
  'ui.app.maj': 'Vérifier les mises à jour au lancement',
  'ui.app.maj_aide': "Coupée, l'application ne fait aucun appel réseau sortant, hors le "
    + 'téléchargement des modèles que vous demandez',
  'ui.app.barre': 'Progression dans la barre des tâches',
  'ui.app.barre_aide': "L'icône se remplit pendant le calcul, sans notification",
  'ui.aide.maj': 'La vérification interroge la page des versions du projet, au plus une fois '
    + "par jour, et se tait complètement si elle n'aboutit pas. Aucune information sur vous "
    + "ni sur vos fichiers n'est transmise.",

  /* -- réglages : mode avancé ------------------------------------------- */
  'ui.avance.bascule': 'Mode avancé',
  'ui.avance.bascule_aide': 'Modèle, faisceau, filtres audio',
  'ui.avance.modele': 'Modèle',
  'ui.avance.modele_aide': "Vide, c'est le modèle du preset qui s'applique.",
  'ui.avance.beam': 'Largeur de faisceau',
  'ui.avance.beam_aide': 'Plus large, meilleure qualité, plus lent. 5 à 10 pour les réunions.',
  'ui.avance.contexte': 'Garder le contexte',
  'ui.avance.contexte_aide': 'À couper si le texte se met à boucler',
  'ui.avance.salle': 'Audio de salle',
  'ui.avance.salle_aide': 'Filtre les basses, normalise le volume',
  'ui.avance.processeur': 'Forcer le processeur',
  'ui.avance.processeur_aide': 'Contourne un souci de carte graphique',

  /* -- pied de fenêtre -------------------------------------------------- */
  'ui.pied.journal': 'Journal',
  'ui.pied.pret_point': 'Prêt.',
  'ui.pied.fichier_detaille': 'Ouvrir le fichier détaillé',
  'ui.pied.pret': 'Prêt',
  'ui.bouton.arreter': 'Arrêter',
  'ui.bouton.lancer': 'Lancer la transcription',
  'ui.bouton.lancer_n': 'Transcrire {n} fichiers',
  'ui.etat.arret': 'Arrêt en cours...',
  'ui.etat.demarrage': 'Démarrage...',
  'ui.etat.bilan_echecs': '{reussis} réussie(s), {echecs} en échec',
  'ui.etat.bilan_arrete': 'Arrêté, {reussis} transcription(s) produite(s)',
  'ui.etat.bilan_ok': '{reussis} transcription(s) terminée(s)',
  'ui.etat.file_terminee': 'File terminée : {reussis} réussie(s), {echecs} en échec, '
    + '{annules} annulée(s).',
  'ui.etat.en_cours': '{message}, {nom}',
  'ui.etat.progression': '{phase} {pct} %, {nom}',

  /* -- journal de l'interface ------------------------------------------- */
  'ui.journal.etat_perdu': "L'interface n'a pas pu récupérer l'état de l'application.",
  'ui.journal.ffmpeg': 'FFmpeg est introuvable : aucun fichier ne pourra être lu. Relancez '
    + '« installer.bat ».',
  'ui.journal.pret': 'Prêt. Journal détaillé : logs/{fichier}',
  'ui.journal.theme': 'Thème : {theme}',
  'ui.journal.langue': "Langue de l'interface : français.",
  'ui.theme.clair': 'clair',
  'ui.theme.sombre': 'sombre',

  /* -- modale glossaire -------------------------------------------------- */
  'ui.modale.glossaire.titre': 'Glossaire de vocabulaire',
  'ui.modale.glossaire.intro': 'Un terme par ligne : prénoms, noms de sociétés, produits, '
    + "sigles. Ces mots sont soufflés au modèle avant qu'il ne transcrive, ce qui l'oriente "
    + 'vers la bonne orthographe.',
  'ui.modale.glossaire.limite': "Le modèle n'accepte qu'une amorce courte, 224 jetons au "
    + 'maximum. Placez les termes les plus importants <strong>en haut</strong> de la liste : '
    + 'au-delà de la limite, les suivants sont ignorés.',

  /* -- modale corrections ------------------------------------------------ */
  'ui.modale.corrections.titre': 'Corrections automatiques',
  'ui.modale.corrections.intro': 'Une règle par ligne, au format <code>forme erronée =&gt; '
    + 'forme correcte</code>. La casse est ignorée et seuls les mots entiers sont remplacés, '
    + 'donc « git » ne touchera pas « digital ». Les corrections sont appliquées au texte '
    + 'final, après la transcription.',

  /* -- modale locuteurs -------------------------------------------------- */
  'ui.modale.jeton.titre': 'Séparation des locuteurs',
  'ui.modale.jeton.intro': 'Le modèle qui reconnaît les voix est mis à disposition '
    + "gratuitement, mais son auteur demande d'accepter ses conditions et de s'identifier par "
    + 'un jeton. Trois étapes, une seule fois.',
  'ui.modale.jeton.page_modele': 'Page du modèle',
  'ui.modale.jeton.creer': 'Créer un jeton',
  'ui.modale.jeton.champ': "Jeton d'accès",
  'ui.modale.jeton.aide': 'Enregistré dans <code>jeton_hf.txt</code>, avec vos données '
    + "personnelles. Ce fichier n'est jamais versionné.",
  'ui.modale.jeton.sans_jeton': 'Sans jeton, la transcription fonctionne normalement, '
    + 'simplement sans étiquettes de locuteur.',
  'ui.modale.jeton.effacer': 'Effacer le jeton',
  'ui.modale.jeton.efface': 'Jeton effacé.',

  /* -- modale import ----------------------------------------------------- */
  'ui.modale.import.titre': 'Importer des données',
  'ui.modale.import.remplacer': 'Remplacer mes données',
  'ui.import.source': 'Fichier « {nom} », exporté le {date} par la version {version}.',
  'ui.import.refuse': 'Import refusé : {message}',
  'ui.import.contenu': 'Ce que contient ce fichier',
  'ui.import.glossaire': 'Glossaire',
  'ui.import.corrections': 'Corrections',
  'ui.import.termes': '{nb} terme(s), au lieu de {actuel} actuellement',
  'ui.import.regles': '{nb} règle(s), au lieu de {actuel} actuellement',
  'ui.import.regles_fautives': '{n} ligne(s) de corrections sont mal écrites dans ce fichier '
    + 'et seront sans effet.',
  'ui.import.reglages': 'Réglages qui changeraient',
  'ui.import.aucun_reglage': 'Aucun réglage ne change.',
  'ui.import.chemins': 'Chemins propres à cette machine',
  'ui.import.filet': 'Avant de remplacer quoi que ce soit, vos données actuelles seront '
    + "enregistrées dans « {dossier} », sous le nom « {nom} ». Rien n'est écrasé sans filet.",
  'ui.import.echec': "L'import n'a pas pu être appliqué. Le détail est dans le journal.",
  'ui.import.rechargee': 'Interface rechargée avec les données importées.',
  'ui.import.non_rechargee': "Les données sont importées, mais l'interface n'a pas pu se "
    + 'recharger : fermez puis rouvrez Scribouille pour les voir.',
  'ui.import.avant': '{avant}  vers  {apres}',

  /* -- modale aperçu ----------------------------------------------------- */
  'ui.modale.apercu.titre': 'Aperçu',
  'ui.modale.apercu.copier': 'Copier le texte',
  'ui.modale.apercu.ouvrir': 'Ouvrir le fichier',
  'ui.apercu.chargement': 'Chargement...',
  'ui.apercu.vide': '(fichier vide ou illisible)',
  'ui.apercu.illisible': '(lecture impossible)',
  'ui.apercu.copie': 'Texte copié dans le presse-papiers.',

  /* -- vue de lecture ---------------------------------------------------- */
  'ui.modale.lecture.titre': 'Transcription',
  'ui.lecture.legende': 'Les mots surlignés ont été entendus avec moins de certitude, '
    + "réécoutez ces passages. Survolez n'importe quel mot pour voir sa confiance.",
  'ui.lecture.legende_chiffree': 'Les mots surlignés ont été entendus avec moins de '
    + 'certitude, réécoutez ces passages ({signales} mots sur {total}, {part}). Survolez '
    + "n'importe quel mot pour voir sa confiance.",
  'ui.lecture.exemple': 'mot',
  'ui.lecture.ouvrir': 'Ouvrir le fichier',
  'ui.lecture.copier': 'Copier le texte',
  'ui.lecture.copier_ia': "Copier pour l'IA",
  'ui.lecture.chargement': 'Chargement...',
  'ui.lecture.non_lue': "Cette transcription n'a pas pu être lue.",
  'ui.lecture.impossible': 'Lecture impossible.',
  'ui.lecture.meta_fichier': 'Fichier',
  'ui.lecture.meta_duree': 'Durée',
  'ui.lecture.meta_date': 'Transcrit le',
  'ui.lecture.meta_modele': 'Modèle',
  'ui.lecture.meta_locuteurs': 'Locuteurs',
  'ui.lecture.audio_illisible': "L'enregistrement d'origine n'a pas pu être lu depuis "
    + "l'application. Le texte reste consultable normalement.",
  'ui.lecture.audio_absent': "L'enregistrement d'origine n'est plus à son emplacement : le "
    + 'texte se lit normalement, mais les extraits ne peuvent pas être joués.',
  'ui.lecture.sans_texte': '(ce fichier ne contient aucun texte)',
  'ui.lecture.confiance': 'Confiance {pct} %',
  'ui.lecture.texte_copie': 'Texte copié.',
  'ui.lecture.texte_copie_journal': 'Texte de la transcription copié.',
  'ui.lecture.ia_copie': 'Instructions et texte copiés.',
  'ui.lecture.copie_impossible': 'Copie impossible.',
  'ui.lecture.corriger': 'Corriger',

  /* -- modale correction ------------------------------------------------- */
  'ui.modale.correction.titre': 'Corriger cette expression',
  'ui.correction.source': 'Forme entendue',
  'ui.correction.cible': 'Forme corrigée',
  'ui.correction.aide': 'La correction est appliquée au texte affiché et au fichier '
    + "enregistré, partout où cette expression apparaît, sans toucher à l'en-tête.",
  'ui.correction.question': 'Ajouter la règle aux corrections ?',
  'ui.correction.question_detaillee': 'Ajouter la règle « {source} » vers « {cible} » aux '
    + 'corrections ?',
  'ui.correction.attente': '...',
  'ui.correction.appliquer': 'Appliquer',
  'ui.correction.journal': 'Correction « {source} » vers « {cible} » : {message}',
  'ui.correction.echec': "La correction n'a pas pu être appliquée. Le détail est dans le "
    + 'journal.',

  /* -- modale gabarit ---------------------------------------------------- */
  'ui.modale.gabarit.titre': "Gabarit d'instructions pour l'IA",
  'ui.modale.gabarit.intro': 'Ce texte est copié dans le presse-papiers avant la '
    + "transcription, quand vous cliquez sur « Copier pour l'IA » dans la vue de lecture. "
    + "Rien n'est envoyé nulle part : la copie reste dans votre presse-papiers, à coller où "
    + 'vous voulez.',
  'ui.modale.gabarit.variables': 'Variables remplacées à la copie : <code>{texte}</code>, '
    + '<code>{fichier}</code>, <code>{date}</code>, <code>{duree}</code>, '
    + '<code>{locuteurs}</code>, <code>{modele}</code>. Les lignes commençant par '
    + '<code>#</code> sont des commentaires et ne sont pas copiées.',
  'ui.gabarit.fichier': 'Fichier : {chemin}',
  'ui.gabarit.enregistre': "Gabarit d'instructions enregistré.",

  /* -- modale espace utilisé --------------------------------------------- */
  'ui.modale.stockage.titre': 'Espace utilisé',
  'ui.modale.stockage.intro': 'Où vivent les fichiers de Scribouille sur ce poste, et ce '
    + "qu'ils occupent. La mesure se fait à chaque ouverture, elle peut prendre quelques "
    + 'secondes sur un gros dossier de modèles.',
  'ui.stockage.mesure': 'Mesure en cours...',
  'ui.stockage.echec': "L'espace occupé n'a pas pu être mesuré.",
  'ui.stockage.ouvrir': 'Ouvrir cet emplacement',
  'ui.stockage.absent': 'Emplacement absent',
  'ui.stockage.total': 'Total mesuré',
  'ui.stockage.libre': 'Espace libre : {libre}',

  /* -- reprises ---------------------------------------------------------- */
  'ui.reprise.meta': 'Transcription interrompue à {position} sur {duree} ({pct} %), '
    + '{ecoule} de calcul déjà faits. Ils seront conservés.',
  'ui.reprise.reprendre': 'Reprendre',
  'ui.reprise.oublier': 'Oublier',
  'ui.reprise.oubliee': 'Reprise oubliée.',

  /* -- modale aide -------------------------------------------------------- */
  'ui.modale.aide.titre': 'Aide',
  'ui.aide.h_outil': 'Ce que fait cet outil',
  'ui.aide.p_outil': 'Il convertit des enregistrements audio en texte, entièrement sur votre '
    + "machine. Aucun fichier, aucun extrait, aucune métadonnée n'est envoyé sur Internet. "
    + 'Les modèles sont téléchargés une seule fois, puis tout fonctionne hors connexion.',
  'ui.aide.h_presets': 'Les deux presets',
  'ui.aide.th_preset': 'Preset',
  'ui.aide.th_modele': 'Modèle',
  'ui.aide.th_usage': 'Pour quoi',
  'ui.aide.preset_qualite': 'Qualité maximale',
  'ui.aide.preset_qualite_usage': 'Réunions, entretiens, tout ce qui sera relu ou résumé '
    + 'ensuite. On lance et on laisse tourner.',
  'ui.aide.preset_rapide': 'Rapide',
  'ui.aide.preset_rapide_usage': 'Environ quatre fois plus rapide, qualité un cran en '
    + 'dessous. Pour dégrossir vite.',
  'ui.aide.h_vocabulaire': 'Vocabulaire et corrections',
  'ui.aide.p_vocabulaire': 'Le <strong>glossaire</strong> est soufflé au modèle avant la '
    + "transcription et l'oriente vers la bonne orthographe des noms propres. Les "
    + '<strong>corrections</strong> réparent après coup les erreurs récurrentes que le '
    + "glossaire n'a pas suffi à éviter.",
  'ui.aide.h_relire': 'Relire une transcription',
  'ui.aide.p_relire1': "Cliquez sur une ligne de l'onglet « Transcriptions », ou sur la loupe "
    + "d'un fichier terminé. Les <strong>mots surlignés en ambre</strong> ont été entendus "
    + 'avec moins de certitude par le modèle : ce sont les passages à réécouter. Survolez '
    + "n'importe quel mot pour voir sa confiance.",
  'ui.aide.p_relire2': '<strong>Sélectionnez</strong> un mot mal transcrit pour le corriger : '
    + 'la correction est appliquée au fichier, et la règle peut être ajoutée aux corrections '
    + "pour ne plus jamais avoir à la refaire. <strong>Copier pour l'IA</strong> place dans "
    + "le presse-papiers des instructions, les métadonnées et le texte, à coller dans "
    + "l'assistant de votre choix. Rien n'est envoyé par l'application.",
  'ui.aide.h_deposer': 'Déposer des fichiers',
  'ui.aide.p_deposer1': "Glissez des enregistrements n'importe où sur la fenêtre. Un "
    + "<strong>dossier</strong> déposé ajoute les fichiers audio qu'il contient, au premier "
    + "niveau seulement : les sous-dossiers ne sont pas parcourus, et l'application dit "
    + "combien de fichiers ont été retenus. Une <strong>archive d'export Scribouille</strong> "
    + "déposée propose l'import de vos données, avec le même aperçu qu'en passant par les "
    + 'réglages.',
  'ui.aide.p_deposer2': 'Le panneau « Dossier surveillé » va plus loin : les enregistrements '
    + "qui arrivent dans le dossier désigné rejoignent la file d'eux-mêmes, une fois leur "
    + 'copie terminée. Ils y attendent que vous lanciez la transcription.',
  'ui.aide.h_raccourcis': 'Raccourcis',
  'ui.aide.raccourci_ouvrir': '<code>Ctrl</code> + <code>O</code> : parcourir vos fichiers',
  'ui.aide.raccourci_lancer': '<code>Ctrl</code> + <code>Entrée</code> : lancer la '
    + 'transcription',
  'ui.aide.raccourci_fermer': '<code>Échap</code> : fermer la fenêtre ouverte',
  'ui.aide.raccourci_zoom': '<code>Ctrl</code> + <code>+</code> / <code>-</code> / '
    + '<code>0</code> : zoom',
  'ui.aide.h_probleme': 'Quand quelque chose ne va pas',
  'ui.aide.p_probleme': 'Chaque échec est expliqué en clair dans la file, et le détail '
    + 'technique complet est écrit dans le fichier de journal, ouvrable depuis la barre du bas.',
  'ui.aide.ouvrir_donnees': 'Ouvrir le dossier de mes données',

  /* -- vérification de mise à jour à la demande, dans l'aide -------------- */
  'ui.aide.h_maj': 'Version et mises à jour',
  'ui.aide.maj_installee': 'Version installée :',
  'ui.aide.maj_bouton': 'Vérifier les mises à jour',
  'ui.aide.maj_en_cours': 'Vérification en cours...',
  'ui.aide.maj_a_jour': 'Vous avez la dernière version ({version}).',
  'ui.aide.maj_echec': 'Vérification impossible, vérifiez votre connexion.',
  'ui.aide.maj_indisponible': 'Vérification indisponible pour le moment.',
  'ui.aide.maj_confidentialite': 'Ceci interroge GitHub une seule fois, à votre demande, et '
    + "n'envoie rien d'autre. Le réglage « Vérifier les mises à jour » des paramètres ne "
    + 'concerne, lui, que la vérification automatique au lancement.',

  /* -- boutons communs --------------------------------------------------- */
  'ui.bouton.annuler': 'Annuler',
  'ui.bouton.enregistrer': 'Enregistrer',
  'ui.bouton.fermer': 'Fermer',
},

/* ------------------------------------------------------------------- ANGLAIS */
en: {

  'format.decimal': '.',
  'format.heure': 'en-GB',
  'unite.pourcent': '%',

  'ui.entete.local': '100 % local',
  'ui.entete.local_titre': 'No data ever leaves this machine',
  'ui.entete.theme': 'Switch theme',
  'ui.entete.aide': 'Help',

  'ui.maj.voir': 'View release',
  'ui.maj.masquer': 'Dismiss',
  'ui.maj.reinstallation': 'Scribouille {version} is available. This one has to be uninstalled '
    + 'and reinstalled: your data and your models are kept.',
  'ui.maj.par_dessus': 'Scribouille {version} is available. Download the update, it installs '
    + 'over this one without losing anything.',
  'ui.maj.journal': 'Version {version} available.',
  'ui.maj.activee': 'The project releases page will be checked at startup, once a day at most.',
  'ui.maj.coupee': 'No outgoing network call will be made, apart from downloading the models '
    + 'you ask for.',

  'ui.materiel.analyse': 'Checking hardware...',
  'ui.materiel.processeur': 'Processor',
  'ui.materiel.coeurs': 'Cores',
  'ui.materiel.memoire': 'Memory',
  'ui.materiel.gpu': 'Graphics card',
  'ui.materiel.npu': 'Neural engine',
  'ui.materiel.calcul': 'Compute used',
  'ui.materiel.systeme': 'System',
  'ui.materiel.detail_coeurs': '{physiques}{logiques} logical, {fils} in use',
  'ui.materiel.physiques': '{n} physical, ',
  'ui.materiel.ram': '{total} GB',
  'ui.materiel.ram_libre': '{total} GB ({libre} GB free)',
  'ui.materiel.gpu_memoire': '{nom}, {go} GB',
  'ui.materiel.sans_gpu': 'no dedicated card detected',
  'ui.materiel.calcul_cuda': 'NVIDIA CUDA, float16 precision',
  'ui.materiel.calcul_cpu': 'processor, int8 quantisation',
  'ui.materiel.estimation': 'about {duree} per hour of audio (factor {facteur})',
  'ui.materiel.estimation_mesuree': 'about {duree} per hour of audio '
    + '(factor {facteur}, measured on this machine)',
  'ui.materiel.avis': 'Estimates, not guarantees: the interface shows the time actually '
    + 'measured for every transcription.',

  'ui.preset.conseille': 'recommended here',
  'ui.preset.chiffres': '{modele} · about {duree} per hour of audio · download {poids}',
  'ui.preset.modele_du_preset': 'Preset model',
  'ui.preset.option_modele': '{nom}, {taille}, {qualite} quality',

  'ui.depot.principal': 'Drop your recordings here',
  'ui.depot.secondaire': 'or click to browse your files',
  'ui.depot.formats': 'm4a, mp3, wav, ogg, flac, opus, webm, wma, and the usual video formats',

  'ui.onglet.file': 'Queue',
  'ui.onglet.historique': 'Transcripts',
  'ui.bouton.vider': 'Clear',
  'ui.file.vide': 'No file waiting.',
  'ui.file.vide_aide': 'Drop your recordings in the area above.',
  'ui.historique.vide': 'No transcript in the output folder.',
  'ui.ligne.calcul': 'about {duree} of compute',
  'ui.ligne.ecoule': 'elapsed {duree}',
  'ui.ligne.restant': '{duree} left',
  'ui.ligne.termine': 'Done in {duree}',
  'ui.ligne.facteur': '{facteur} x the audio duration',
  'ui.ligne.locuteurs': '{n} speakers',
  'ui.ligne.corrections': '{n} corrections',
  'ui.ligne.echec': 'Failed',
  'ui.ligne.annule': 'Cancelled',
  'ui.ligne.arrete': 'Stopped before the end',
  'ui.ligne.lire': 'Read the transcript',
  'ui.ligne.journal': 'Open the log',
  'ui.ligne.retirer': 'Remove',

  'ui.section.qualite': 'Transcription quality',

  'ui.section.langue_sortie': 'Language and output',
  'ui.champ.langue_parlee': 'Spoken language',
  'ui.langue.fr': 'French',
  'ui.langue.en': 'English',
  'ui.langue.es': 'Spanish',
  'ui.langue.de': 'German',
  'ui.langue.it': 'Italian',
  'ui.langue.nl': 'Dutch',
  'ui.langue.pt': 'Portuguese',
  'ui.langue.pl': 'Polish',
  'ui.langue.ro': 'Romanian',
  'ui.langue.ar': 'Arabic',
  'ui.langue.auto': 'Detect automatically',
  'ui.qualite.excellente': 'Expected quality: excellent, one of the best covered languages.',
  'ui.qualite.bonne': 'Expected quality: good, a few proper nouns worth a closer read.',
  'ui.qualite.variable': 'Expected quality: varies with accent and recording conditions, read '
    + 'the text back.',
  'ui.qualite.auto': 'The language is detected at the start of the recording. Setting it is '
    + 'still safer, especially on room audio.',
  'ui.champ.dossier_sortie': 'Output folder',
  'ui.titre.choisir_dossier': 'Choose a folder',
  'ui.titre.ouvrir_dossier': 'Open the folder',
  'ui.champ.motif': 'Output file names',
  'ui.aide.motif': 'Variables: <code>{nom}</code>, <code>{date}</code>, '
    + '<code>{heure}</code>, <code>{modele}</code>. Leave empty for the usual naming.',
  'ui.motif.defaut': 'Default: {exemple}',
  'ui.motif.exemple': 'Example: {exemple}',
  'ui.motif.enregistre': 'Output file names: {motif}.',
  'ui.champ.formats': 'Output formats',
  'ui.format.txt': 'Text (.txt)',
  'ui.format.srt': 'Subtitles (.srt)',
  'ui.format.vtt': 'Subtitles (.vtt)',
  'ui.format.horodatage': 'Timestamp every paragraph of the text',
  'ui.format.un_minimum': 'At least one output format has to stay ticked.',

  'ui.section.veille': 'Watched folder',
  'ui.veille.bascule': 'Watch a folder',
  'ui.veille.coupee': 'Off',
  'ui.veille.champ': 'Folder to watch',
  'ui.veille.reprendre_tout': 'Pick up the whole folder again',
  'ui.aide.veille': 'Recordings dropped in this folder join the queue on their own, once '
    + 'their copy is finished. The folder is checked every ten seconds, only while the option '
    + 'is on, and files already transcribed are never picked up again.',
  'ui.veille.indic_actif': 'Watching',
  'ui.veille.indic_defaut': 'Folder unreachable',
  'ui.veille.etat_defaut': 'Faulty, folder unreachable',
  'ui.veille.etat_actif': 'On, checked every {n} seconds',
  'ui.veille.titre': 'Watched folder: {dossier}',

  'ui.section.vocabulaire': 'Vocabulary',
  'ui.aide.vocabulaire': 'Proper nouns, company names and technical terms are what '
    + 'transcription mangles most. Two settings deal with that.',
  'ui.voc.glossaire': 'Prime the model with the glossary',
  'ui.voc.corrections': 'Apply corrections',
  'ui.bouton.glossaire': 'Glossary',
  'ui.bouton.corrections': 'Corrections',
  'ui.voc.aucun_terme': 'No terms yet',
  'ui.voc.termes.un': '{n} active term',
  'ui.voc.termes.autres': '{n} active terms',
  'ui.voc.tronque': ' out of {total}, list trimmed',
  'ui.voc.aucune_regle': 'No rules',
  'ui.voc.regles.un': '{n} rule',
  'ui.voc.regles.autres': '{n} rules',
  'ui.voc.lignes_erreur': ', {n} line(s) with errors',
  'ui.voc.glossaire_enregistre': 'Glossary saved. {message}',
  'ui.voc.regles_enregistrees': '{n} correction rule(s) saved.',

  'ui.section.relecture': 'Reading back',
  'ui.aide.relecture': 'What happens once the transcript is written: read it in the app, spot '
    + 'the uncertain passages, correct them, prepare a summary.',
  'ui.relecture.compagnon': 'Save word confidence',
  'ui.relecture.compagnon_aide': 'A small .json file next to each text',
  'ui.relecture.apprises': 'Remember corrections made while reading',
  'ui.relecture.apprises_aide': 'Offer to add the rule to your corrections',
  'ui.relecture.sauvegarde': 'Progressive saving',
  'ui.relecture.sauvegarde_aide': 'An interruption no longer loses the work done',
  'ui.relecture.audio': 'Play the audio while reading',
  'ui.relecture.audio_aide': 'Experimental, clicking a paragraph plays that passage',
  'ui.bouton.gabarit': 'AI prompt template',
  'ui.aide.gabarit': 'The instruction text copied along with the transcript by the "Copy for '
    + 'AI" button in the reading view. It belongs to you.',

  'ui.section.locuteurs': 'Speakers',
  'ui.loc.bascule': 'Separate speakers',
  'ui.loc.nombre': 'Number of participants',
  'ui.loc.auto': 'Detect automatically',
  'ui.aide.locuteurs': 'Giving the exact number improves the split noticeably.',
  'ui.loc.jeton_a_saisir': 'Hugging Face token needed',
  'ui.loc.configurer': 'Set up access',
  'ui.loc.modifier_jeton': 'Change the token',
  'ui.loc.active': 'On',
  'ui.loc.disponible': 'Available',

  'ui.ext.absente': 'Components not installed',
  'ui.ext.chiffres': '{telechargement} GB to download, {installee} GB once installed. '
    + '{requis} GB must be free on this drive, {libre} GB are left.',
  'ui.ext.installer': 'Install speaker separation',
  'ui.ext.aide': 'One download, once. You can carry on transcribing while it runs.',
  'ui.ext.annuler': 'Cancel the installation',
  'ui.ext.aide_en_cours': 'The download carries on in the background. The application stays '
    + 'usable, and cancelling loses nothing of what has already arrived.',
  'ui.ext.demarrage': 'Starting...',
  'ui.ext.retirer': 'Remove speaker separation ({taille} GB)',
  'ui.ext.note_installee': 'Components installed in your personal data, {variante} build.',
  'ui.ext.note_sources': 'Components installed in the project ".venv" environment.',
  'ui.ext.variante_cpu': 'CPU',
  'ui.ext.variante_cuda': 'NVIDIA',
  'ui.ext.place_manquante': 'There is not enough room on this drive. Free up some space, then '
    + 'come back here.',
  'ui.ext.echec_lancement': 'The installation could not start.',
  'ui.ext.modale.titre': 'Install speaker separation',
  'ui.ext.modale.intro': 'This feature recognises voices and labels each passage "Speaker 1", '
    + '"Speaker 2". It relies on PyTorch, which does not ship with the application because it '
    + 'weighs more on its own than everything else put together.',
  'ui.ext.modale.duree': 'Expect several minutes depending on your connection. The download '
    + 'runs in the background: the application stays usable, and it picks up where it stops.',
  'ui.ext.modale.lancer': 'Install',

  'ui.section.modeles': 'Models',
  'ui.bouton.changer': 'Change',
  'ui.bouton.stockage': 'Disk usage',
  'ui.modeles.tous': 'All models downloaded, {occupe} used',
  'ui.modeles.partiels': '{present} model(s) out of {total} downloaded, {occupe} used',
  'ui.modeles.occupe': '{occupe} used',
  'ui.modeles.aide': 'Models are downloaded once, on first use{tailles}. Free space on this '
    + 'disk: {libre}.',
  'ui.modeles.tailles': ' ({liste})',
  'ui.modeles.incomplets': 'Incomplete model found ({liste}): a download was interrupted. '
    + 'It will be renewed on its own at the next use, nothing to do.',

  'ui.section.donnees': 'My data',
  'ui.donnees.etat': 'Glossary, corrections, AI template and settings',
  'ui.bouton.exporter': 'Export my data',
  'ui.bouton.importer': 'Import data',
  'ui.aide.donnees': 'A single zip file to back up your professional glossary or carry it to '
    + 'another machine, with no Git repository and no online service. The Hugging Face token, '
    + 'the logs and the models are never included.',

  'ui.section.application': 'Application',
  'ui.champ.langue_interface': 'Interface language',
  'ui.aide.langue_interface': 'Changes the labels of this window, right away. The language '
    + 'spoken in your recordings is set further up, the two are independent.',
  'ui.app.maj': 'Check for updates at startup',
  'ui.app.maj_aide': 'When off, the application makes no outgoing network call at all, apart '
    + 'from downloading the models you ask for',
  'ui.app.barre': 'Progress in the taskbar',
  'ui.app.barre_aide': 'The icon fills up while computing, with no notification',
  'ui.aide.maj': 'The check queries the project releases page, once a day at most, and stays '
    + 'completely silent if it fails. No information about you or your files is sent.',

  'ui.avance.bascule': 'Advanced mode',
  'ui.avance.bascule_aide': 'Model, beam, audio filters',
  'ui.avance.modele': 'Model',
  'ui.avance.modele_aide': 'Leave empty to use the model of the preset.',
  'ui.avance.beam': 'Beam width',
  'ui.avance.beam_aide': 'Wider means better quality and slower. 5 to 10 for meetings.',
  'ui.avance.contexte': 'Keep context',
  'ui.avance.contexte_aide': 'Turn off if the text starts looping',
  'ui.avance.salle': 'Room audio',
  'ui.avance.salle_aide': 'Filters out low frequencies, evens out the volume',
  'ui.avance.processeur': 'Force CPU',
  'ui.avance.processeur_aide': 'Works around a graphics card problem',

  'ui.pied.journal': 'Activity',
  'ui.pied.pret_point': 'Ready.',
  'ui.pied.fichier_detaille': 'Open the detailed log',
  'ui.pied.pret': 'Ready',
  'ui.bouton.arreter': 'Stop',
  'ui.bouton.lancer': 'Start transcription',
  'ui.bouton.lancer_n': 'Transcribe {n} files',
  'ui.etat.arret': 'Stopping...',
  'ui.etat.demarrage': 'Starting...',
  'ui.etat.bilan_echecs': '{reussis} done, {echecs} failed',
  'ui.etat.bilan_arrete': 'Stopped, {reussis} transcript(s) produced',
  'ui.etat.bilan_ok': '{reussis} transcript(s) finished',
  'ui.etat.file_terminee': 'Queue finished: {reussis} done, {echecs} failed, {annules} '
    + 'cancelled.',
  'ui.etat.en_cours': '{message}, {nom}',
  'ui.etat.progression': '{phase} {pct} %, {nom}',

  'ui.journal.etat_perdu': 'The interface could not retrieve the state of the application.',
  'ui.journal.ffmpeg': 'FFmpeg could not be found: no file can be read. Run "installer.bat" '
    + 'again.',
  'ui.journal.pret': 'Ready. Detailed log: logs/{fichier}',
  'ui.journal.theme': 'Theme: {theme}',
  'ui.journal.langue': 'Interface language: English.',
  'ui.theme.clair': 'light',
  'ui.theme.sombre': 'dark',

  'ui.modale.glossaire.titre': 'Vocabulary glossary',
  'ui.modale.glossaire.intro': 'One term per line: first names, company names, products, '
    + 'acronyms. These words are fed to the model before it transcribes, which steers it '
    + 'towards the right spelling.',
  'ui.modale.glossaire.limite': 'The model only accepts a short prompt, 224 tokens at most. '
    + 'Put the most important terms <strong>at the top</strong> of the list: past the limit, '
    + 'the rest are ignored.',

  'ui.modale.corrections.titre': 'Automatic corrections',
  'ui.modale.corrections.intro': 'One rule per line, in the form <code>wrong form =&gt; right '
    + 'form</code>. Case is ignored and only whole words are replaced, so "git" will not '
    + 'touch "digital". Corrections are applied to the final text, after transcription.',

  'ui.modale.jeton.titre': 'Speaker separation',
  'ui.modale.jeton.intro': 'The model that recognises voices is made available free of '
    + 'charge, but its author asks you to accept its terms and identify yourself with a '
    + 'token. Three steps, once and for all.',
  'ui.modale.jeton.page_modele': 'Model page',
  'ui.modale.jeton.creer': 'Create a token',
  'ui.modale.jeton.champ': 'Access token',
  'ui.modale.jeton.aide': 'Saved in <code>jeton_hf.txt</code>, with your personal data. That '
    + 'file is never committed to version control.',
  'ui.modale.jeton.sans_jeton': 'Without a token, transcription works normally, simply '
    + 'without speaker labels.',
  'ui.modale.jeton.effacer': 'Clear the token',
  'ui.modale.jeton.efface': 'Token cleared.',

  'ui.modale.import.titre': 'Import data',
  'ui.modale.import.remplacer': 'Replace my data',
  'ui.import.source': 'File "{nom}", exported on {date} by version {version}.',
  'ui.import.refuse': 'Import rejected: {message}',
  'ui.import.contenu': 'What this file contains',
  'ui.import.glossaire': 'Glossary',
  'ui.import.corrections': 'Corrections',
  'ui.import.termes': '{nb} term(s), instead of {actuel} currently',
  'ui.import.regles': '{nb} rule(s), instead of {actuel} currently',
  'ui.import.regles_fautives': '{n} correction line(s) are badly written in this file and '
    + 'will have no effect.',
  'ui.import.reglages': 'Settings that would change',
  'ui.import.aucun_reglage': 'No setting changes.',
  'ui.import.chemins': 'Paths specific to this machine',
  'ui.import.filet': 'Before anything is replaced, your current data will be saved to '
    + '"{dossier}", under the name "{nom}". Nothing is overwritten without a safety net.',
  'ui.import.echec': 'The import could not be applied. The details are in the log.',
  'ui.import.rechargee': 'Interface reloaded with the imported data.',
  'ui.import.non_rechargee': 'The data was imported, but the interface could not reload: '
    + 'close and reopen Scribouille to see it.',
  'ui.import.avant': '{avant}  to  {apres}',

  'ui.modale.apercu.titre': 'Preview',
  'ui.modale.apercu.copier': 'Copy the text',
  'ui.modale.apercu.ouvrir': 'Open the file',
  'ui.apercu.chargement': 'Loading...',
  'ui.apercu.vide': '(empty or unreadable file)',
  'ui.apercu.illisible': '(cannot be read)',
  'ui.apercu.copie': 'Text copied to the clipboard.',

  'ui.modale.lecture.titre': 'Transcript',
  'ui.lecture.legende': 'Highlighted words were heard with less certainty, listen to those '
    + 'passages again. Hover any word to see its confidence.',
  'ui.lecture.legende_chiffree': 'Highlighted words were heard with less certainty, listen to '
    + 'those passages again ({signales} words out of {total}, {part}). Hover any word to see '
    + 'its confidence.',
  'ui.lecture.exemple': 'word',
  'ui.lecture.ouvrir': 'Open the file',
  'ui.lecture.copier': 'Copy the text',
  'ui.lecture.copier_ia': 'Copy for AI',
  'ui.lecture.chargement': 'Loading...',
  'ui.lecture.non_lue': 'This transcript could not be read.',
  'ui.lecture.impossible': 'Cannot be read.',
  'ui.lecture.meta_fichier': 'File',
  'ui.lecture.meta_duree': 'Length',
  'ui.lecture.meta_date': 'Transcribed on',
  'ui.lecture.meta_modele': 'Model',
  'ui.lecture.meta_locuteurs': 'Speakers',
  'ui.lecture.audio_illisible': 'The original recording could not be played from the '
    + 'application. The text is still readable normally.',
  'ui.lecture.audio_absent': 'The original recording is no longer where it was: the text '
    + 'reads normally, but passages cannot be played.',
  'ui.lecture.sans_texte': '(this file contains no text)',
  'ui.lecture.confiance': 'Confidence {pct} %',
  'ui.lecture.texte_copie': 'Text copied.',
  'ui.lecture.texte_copie_journal': 'Transcript text copied.',
  'ui.lecture.ia_copie': 'Instructions and text copied.',
  'ui.lecture.copie_impossible': 'Copy failed.',
  'ui.lecture.corriger': 'Correct',

  'ui.modale.correction.titre': 'Correct this phrase',
  'ui.correction.source': 'Transcribed form',
  'ui.correction.cible': 'Corrected form',
  'ui.correction.aide': 'The correction is applied to the text shown and to the saved file, '
    + 'everywhere this phrase appears, without touching the header.',
  'ui.correction.question': 'Add the rule to your corrections?',
  'ui.correction.question_detaillee': 'Add the rule "{source}" to "{cible}" to your '
    + 'corrections?',
  'ui.correction.attente': '...',
  'ui.correction.appliquer': 'Apply',
  'ui.correction.journal': 'Correction "{source}" to "{cible}": {message}',
  'ui.correction.echec': 'The correction could not be applied. The details are in the log.',

  'ui.modale.gabarit.titre': 'AI instruction template',
  'ui.modale.gabarit.intro': 'This text is copied to the clipboard ahead of the transcript '
    + 'when you click "Copy for AI" in the reading view. Nothing is sent anywhere: the copy '
    + 'stays in your clipboard, to paste where you like.',
  'ui.modale.gabarit.variables': 'Variables replaced at copy time: <code>{texte}</code>, '
    + '<code>{fichier}</code>, <code>{date}</code>, <code>{duree}</code>, '
    + '<code>{locuteurs}</code>, <code>{modele}</code>. Lines starting with <code>#</code> '
    + 'are comments and are not copied.',
  'ui.gabarit.fichier': 'File: {chemin}',
  'ui.gabarit.enregistre': 'Instruction template saved.',

  'ui.modale.stockage.titre': 'Disk usage',
  'ui.modale.stockage.intro': 'Where the Scribouille files live on this machine, and how much '
    + 'room they take. The measurement runs every time you open this window, and can take a '
    + 'few seconds on a large models folder.',
  'ui.stockage.mesure': 'Measuring...',
  'ui.stockage.echec': 'Disk usage could not be measured.',
  'ui.stockage.ouvrir': 'Open this location',
  'ui.stockage.absent': 'Location missing',
  'ui.stockage.total': 'Total measured',
  'ui.stockage.libre': 'Free space: {libre}',

  'ui.reprise.meta': 'Transcription interrupted at {position} out of {duree} ({pct} %), '
    + '{ecoule} of compute already done. It will be kept.',
  'ui.reprise.reprendre': 'Resume',
  'ui.reprise.oublier': 'Forget',
  'ui.reprise.oubliee': 'Resume point forgotten.',

  'ui.modale.aide.titre': 'Help',
  'ui.aide.h_outil': 'What this tool does',
  'ui.aide.p_outil': 'It turns audio recordings into text, entirely on your machine. No file, '
    + 'no excerpt, no metadata is sent over the Internet. Models are downloaded once, then '
    + 'everything works offline.',
  'ui.aide.h_presets': 'The two presets',
  'ui.aide.th_preset': 'Preset',
  'ui.aide.th_modele': 'Model',
  'ui.aide.th_usage': 'What for',
  'ui.aide.preset_qualite': 'Highest quality',
  'ui.aide.preset_qualite_usage': 'Meetings, interviews, anything you will read back or '
    + 'summarise afterwards. Start it and let it run.',
  'ui.aide.preset_rapide': 'Fast',
  'ui.aide.preset_rapide_usage': 'About four times faster, quality one notch below. To get '
    + 'the gist quickly.',
  'ui.aide.h_vocabulaire': 'Vocabulary and corrections',
  'ui.aide.p_vocabulaire': 'The <strong>glossary</strong> is fed to the model before '
    + 'transcription and steers it towards the right spelling of proper nouns. '
    + '<strong>Corrections</strong> repair, after the fact, the recurring mistakes the '
    + 'glossary was not enough to avoid.',
  'ui.aide.h_relire': 'Reading a transcript',
  'ui.aide.p_relire1': 'Click a line in the "Transcripts" tab, or the magnifier on a finished '
    + 'file. <strong>Words highlighted in amber</strong> were heard with less certainty by '
    + 'the model: those are the passages to listen to again. Hover any word to see its '
    + 'confidence.',
  'ui.aide.p_relire2': '<strong>Select</strong> a badly transcribed word to correct it: the '
    + 'correction is applied to the file, and the rule can be added to your corrections so '
    + 'you never have to do it again. <strong>Copy for AI</strong> puts instructions, '
    + 'metadata and the text in your clipboard, to paste into the assistant of your choice. '
    + 'Nothing is sent by the application.',
  'ui.aide.h_deposer': 'Dropping files',
  'ui.aide.p_deposer1': 'Drag recordings anywhere on the window. A <strong>folder</strong> '
    + 'you drop adds the audio files it contains, at the top level only: subfolders are not '
    + 'scanned, and the application says how many files were kept. A <strong>Scribouille export '
    + 'archive</strong> you drop offers to import your data, with the same preview as going '
    + 'through the settings.',
  'ui.aide.p_deposer2': 'The "Watched folder" panel goes further: recordings that land in the '
    + 'chosen folder join the queue on their own, once their copy is finished. They wait '
    + 'there until you start the transcription.',
  'ui.aide.h_raccourcis': 'Shortcuts',
  'ui.aide.raccourci_ouvrir': '<code>Ctrl</code> + <code>O</code> : browse your files',
  'ui.aide.raccourci_lancer': '<code>Ctrl</code> + <code>Enter</code> : start the transcription',
  'ui.aide.raccourci_fermer': '<code>Esc</code> : close the window on top',
  'ui.aide.raccourci_zoom': '<code>Ctrl</code> + <code>+</code> / <code>-</code> / '
    + '<code>0</code> : zoom',
  'ui.aide.h_probleme': 'When something goes wrong',
  'ui.aide.p_probleme': 'Every failure is explained in plain words in the queue, and the full '
    + 'technical details are written to the log file, which opens from the bottom bar.',
  'ui.aide.ouvrir_donnees': 'Open my data folder',

  'ui.aide.h_maj': 'Version and updates',
  'ui.aide.maj_installee': 'Installed version:',
  'ui.aide.maj_bouton': 'Check for updates',
  'ui.aide.maj_en_cours': 'Checking...',
  'ui.aide.maj_a_jour': 'You are running the latest version ({version}).',
  'ui.aide.maj_echec': 'Check failed, please verify your connection.',
  'ui.aide.maj_indisponible': 'Check unavailable at the moment.',
  'ui.aide.maj_confidentialite': 'This queries GitHub once, at your request, and sends nothing '
    + 'else. The "Check for updates" setting only governs the automatic check at startup.',

  'ui.bouton.annuler': 'Cancel',
  'ui.bouton.enregistrer': 'Save',
  'ui.bouton.fermer': 'Close',
},
};


/* ------------------------------------------------------------------ Mécanique */

const LANGUES_DISPONIBLES = ['fr', 'en'];
const LANGUE_PAR_DEFAUT = 'en';
/* Clé historique, conservée telle quelle : la renommer ferait oublier la langue
   déjà choisie sur les postes qui tournaient avant le renommage de la 2.4.0. */
const CLE_MEMOIRE = 'whiscribe.langue';

let _langue = LANGUE_PAR_DEFAUT;

function normaliserLangue(code) {
  const texte = String(code || '').trim().toLowerCase().replace('_', '-');
  const racine = texte.split('-')[0];
  return LANGUES_DISPONIBLES.includes(racine) ? racine : '';
}

/* Langue provisoire, le temps que Python réponde : celle du dernier lancement,
   sinon celle du navigateur intégré. Python a toujours le dernier mot. */
function langueProvisoire() {
  let memorisee = '';
  try { memorisee = window.localStorage.getItem(CLE_MEMOIRE) || ''; } catch (e) { memorisee = ''; }
  return normaliserLangue(memorisee)
    || normaliserLangue(navigator.language)
    || LANGUE_PAR_DEFAUT;
}

function definirLangue(code) {
  _langue = normaliserLangue(code) || LANGUE_PAR_DEFAUT;
  try { window.localStorage.setItem(CLE_MEMOIRE, _langue); } catch (e) { /* sans conséquence */ }
  document.documentElement.setAttribute('lang', _langue);
  return _langue;
}

function langueCourante() { return _langue; }

function t(cle, valeurs) {
  const table = TRADUCTIONS[_langue] || TRADUCTIONS[LANGUE_PAR_DEFAUT];
  let texte = table[cle];
  if (texte === undefined) texte = TRADUCTIONS[LANGUE_PAR_DEFAUT][cle];
  if (texte === undefined) return cle;
  if (valeurs) {
    Object.keys(valeurs).forEach((nom) => {
      texte = texte.split('{' + nom + '}').join(String(valeurs[nom]));
    });
  }
  return texte;
}

/* Pluriel : 'cle.un' au singulier, 'cle.autres' sinon. {n} est injecté. */
function tn(cle, n, valeurs) {
  const suffixe = Math.abs(Number(n)) <= 1 ? '.un' : '.autres';
  return t(cle + suffixe, Object.assign({ n: n }, valeurs || {}));
}

/* Nombre décimal au séparateur de la langue courante. */
function nb(valeur, decimales) {
  const chiffres = decimales === undefined ? 2 : decimales;
  return Number(valeur).toFixed(chiffres).replace('.', t('format.decimal'));
}

/* Pose les libellés du HTML. Le document ne porte aucun texte en dur : tout
   passe par ces attributs, ce qui rend la bascule de langue instantanée. */
function traduirePage(racine) {
  const base = racine || document;
  base.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  base.querySelectorAll('[data-i18n-html]').forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  base.querySelectorAll('[data-i18n-title]').forEach((el) => {
    el.setAttribute('title', t(el.dataset.i18nTitle));
  });
  base.querySelectorAll('[data-i18n-aria]').forEach((el) => {
    el.setAttribute('aria-label', t(el.dataset.i18nAria));
  });
  base.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
    el.setAttribute('placeholder', t(el.dataset.i18nPlaceholder));
  });
}
