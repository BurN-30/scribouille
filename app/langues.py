"""
Langue de l'interface : catalogue des chaînes produites côté Python.

Deux sources jumelées, une par technologie :

  - ce module, pour tout ce que Python fabrique et qui remonte à l'interface :
    messages d'erreur traduits, avertissements matériels, retours de la
    passerelle, libellés des réglages, en-tête des fichiers produits ;
  - `web/langues.js`, pour tout ce que l'interface web écrit elle-même.

Les deux fichiers sont indépendants mais soumis à la même règle : les clés du
français et celles de l'anglais doivent coïncider exactement, des deux côtés.
`outils/verifier_traductions.py` le vérifie et échoue si une clé manque.

Choix assumés, documentés une fois ici :

  - **Langue par défaut hors francophonie : l'anglais.** L'application est
    publiée pour un public mondial. La détection lit la langue d'interface de
    Windows ; français si et seulement si Windows est en français, anglais dans
    tous les autres cas, y compris quand la locale est illisible.
  - **La langue d'interface est indépendante de la langue parlée.** Le sélecteur
    « Langue parlée » pilote le moteur de transcription, celui-ci pilote
    l'affichage. Un anglophone transcrit du français sans rien changer.
  - **Les fichiers produits suivent la langue d'interface au moment de leur
    production.** L'en-tête d'un `.txt` transcrit en français reste en français
    même après une bascule en anglais : un fichier écrit ne se réécrit pas.
  - **Le journal de bord technique (`logs/`) reste en français.** Il s'adresse
    au mainteneur, pas à l'utilisateur, et sert au diagnostic d'incidents
    rapportés au dépôt.
  - **Les fichiers de données de l'utilisateur** (`vocabulaire.txt`,
    `corrections.txt`, `gabarit-ia.txt`) sont créés dans la langue d'interface
    du moment. Un fichier existant n'est jamais retraduit ni réécrit.

Substitution : `t("cle", nom=valeur)` remplace littéralement `{nom}`. Ce n'est
volontairement pas `format()` : certains textes contiennent des accolades qui
doivent rester telles quelles, le gabarit d'instructions par exemple.

Pluriels : `tn("cle", n)` choisit entre `cle.un` et `cle.autres`, et injecte
`{n}`. Les deux variantes existent dans les deux langues, la parité les couvre.
"""

from __future__ import annotations

import os
import sys

LANGUES: tuple[str, ...] = ("fr", "en")

#: Hors francophonie, anglais. Voir la note en tête de module.
LANGUE_DEFAUT = "en"

_courante = LANGUE_DEFAUT


# ---------------------------------------------------------------------------
# Catalogue : français
# ---------------------------------------------------------------------------

_FR: dict[str, str] = {

    # -- noms des langues, pour le sélecteur ------------------------------
    "langue.fr": "Français",
    "langue.en": "Anglais",

    # -- formats et unités -------------------------------------------------
    "format.date_heure": "%d/%m/%Y à %H:%M",
    "format.decimal": ",",
    "format.titre_message": "{titre} : {message}",
    "contexte.export": "export des données",
    "contexte.import": "import des données",
    "duree.heures": "{h} h {m}",
    "duree.minutes": "{m} min {s}",
    "duree.secondes": "{s} s",
    "duree.vide": "--",
    "duree_longue.heures": "{h} h {m} min",
    "duree_longue.minutes": "{m} min {s} s",
    "unite.go": "Go",
    "unite.mo": "Mo",
    "unite.ko": "Ko",
    "unite.octet": "0 octet",
    "unite.octets": "{n} octets",

    # -- incidents traduits (app/journal.py) -------------------------------
    "err.memoire.titre": "Mémoire insuffisante",
    "err.memoire.msg": (
        "La machine n'a pas assez de mémoire vive pour ce modèle. Essayez le preset "
        "« Rapide », désactivez la séparation des locuteurs, ou fermez les autres "
        "applications ouvertes."
    ),
    "err.disque.titre": "Disque plein",
    "err.disque.msg": (
        "Il n'y a plus assez de place sur le disque pour écrire le résultat ou "
        "télécharger le modèle. Libérez de l'espace puis relancez."
    ),
    "err.jeton.titre": "Accès au modèle de diarisation refusé",
    "err.jeton.msg": (
        "Le jeton Hugging Face est absent, invalide, ou les conditions du modèle "
        "pyannote n'ont pas été acceptées. Ouvrez le panneau « Locuteurs » pour "
        "revoir la procédure. La transcription seule fonctionne sans jeton."
    ),
    "err.reseau.titre": "Téléchargement impossible",
    "err.reseau.msg": (
        "Le modèle n'est pas encore présent sur la machine et le téléchargement a "
        "échoué. Vérifiez la connexion Internet, puis relancez : une fois téléchargé, "
        "le modèle reste local et l'application n'a plus besoin du réseau."
    ),
    "err.modele.titre": "Modèle de transcription inutilisable",
    "err.modele.msg": (
        "Les fichiers du modèle sont absents ou abîmés, et le dossier n'a pas pu être "
        "renouvelé automatiquement. Fermez les autres applications qui pourraient "
        "l'ouvrir, puis relancez la transcription : le modèle sera retéléchargé. Le "
        "dossier des modèles se retrouve dans les réglages, section « Modèles »."
    ),
    "err.cuda.titre": "Accélération NVIDIA indisponible",
    "err.cuda.msg": (
        "Les bibliothèques CUDA (cuBLAS, cuDNN) n'ont pas pu être chargées. "
        "Relancez l'installateur, ou forcez le mode processeur dans les réglages avancés."
    ),
    "err.fichier.titre": "Fichier introuvable",
    "err.fichier.msg": (
        "Le fichier a été déplacé, renommé ou supprimé depuis son ajout à la file."
    ),
    "err.acces.titre": "Accès refusé",
    "err.acces.msg": (
        "Windows refuse la lecture ou l'écriture de ce fichier. Vérifiez qu'il n'est "
        "pas ouvert dans une autre application et que le dossier de sortie est "
        "accessible en écriture."
    ),
    "err.inattendu.titre": "Échec inattendu",
    "err.inattendu.titre_contexte": "Échec inattendu ({contexte})",
    "err.inattendu.msg": "Le détail technique est consigné dans logs/{journal}.",

    # -- presets et estimations (app/presets.py) ---------------------------
    "preset.qualite.nom": "Qualité maximale",
    "preset.qualite.resume": "Le meilleur texte possible. Pour les réunions et tout ce qui sera relu.",
    "preset.rapide.nom": "Rapide",
    "preset.rapide.resume": "Environ quatre fois plus rapide, qualité un cran en dessous.",
    "preset.personnalise": "{nom}, réglages personnalisés",
    "modele.qualite.depannage": "Dépannage",
    "modele.qualite.faible": "Faible",
    "modele.qualite.correcte": "Correcte",
    "modele.qualite.bonne": "Bonne",
    "modele.qualite.tres_bonne": "Très bonne",
    "modele.qualite.excellente": "Excellente",
    "reco.memoire_juste": (
        "Mémoire vive détectée : {ram} Go. C'est trop juste pour large-v3, le preset "
        "« Rapide » est conseillé."
    ),
    "reco.cuda": (
        "Carte NVIDIA exploitée : le preset « Qualité maximale » passe largement plus "
        "vite que le temps réel."
    ),
    "reco.processeur": (
        "Transcription sur processeur : le preset « Qualité maximale » est le bon choix "
        "pour les réunions, il suffit de le lancer et de laisser tourner."
    ),
    "avert.memoire_tres_serree": (
        "Cette machine annonce {ram} Go de mémoire vive. Le modèle large-v3 risque de "
        "saturer : préférez le preset « Rapide »."
    ),
    "avert.memoire_serree_diar": (
        "Mémoire vive : {ram} Go. La combinaison large-v3 plus séparation des locuteurs "
        "tient, parce que les deux étapes sont enchaînées et jamais chargées en même "
        "temps. Fermez tout de même les applications lourdes avant de lancer une longue "
        "réunion."
    ),
    "avert.ram_libre": (
        "Il ne reste qu'environ {go} Go de mémoire libre. Fermez quelques applications "
        "avant de lancer la file."
    ),
    "avert.amd": (
        "{carte} détectée mais non utilisée : en v1, seul le processeur travaille sur "
        "les cartes non NVIDIA."
    ),

    # -- matériel (app/materiel.py) ----------------------------------------
    "mat.cpu_inconnu": "Processeur inconnu",
    "mat.fils": "{n} fils",
    "mat.coeurs_fils": "{coeurs} cœurs / {fils} fils",
    "mat.memoire": "{go} Go de mémoire",
    "mat.gpu_accelere": "{nom} (accéléré)",
    "mat.gpu_non_accelere": "{nom} (non accéléré en v1)",
    "mat.sans_gpu": "pas de carte graphique dédiée",
    "mat.npu_non_exploite": "{nom} (non exploité)",
    "gpu.note.cuda_active": "Accélération CUDA active.",
    "gpu.note.cuda_absente": (
        "Carte NVIDIA détectée mais les bibliothèques CUDA de CTranslate2 ne répondent "
        "pas. Relancez l'installateur pour les poser."
    ),
    "gpu.note.amd": (
        "Non accéléré en v1 : CTranslate2 ne gère que CPU et CUDA. L'accélération AMD "
        "via whisper.cpp Vulkan est prévue en v1.x."
    ),
    "gpu.note.intel": (
        "Circuit graphique intégré, détecté mais non exploité en v1 : la transcription "
        "tourne sur le processeur. Pistes v1.x : whisper.cpp Vulkan, ou OpenVINO."
    ),
    "gpu.note.autre": "Non accéléré en v1.",
    "npu.note": (
        "Détecté, non exploité en v1. Un NPU vise surtout l'autonomie sur batterie ; "
        "la piste OpenVINO est documentée comme évolution v1.x."
    ),

    # -- chemins et dossiers (app/chemins.py) ------------------------------
    "chemin.dossier_non_cree": "Ce dossier n'a pas pu être créé ({erreur}).",
    "chemin.dossier_non_ecrivable": "Ce dossier n'est pas accessible en écriture.",

    # -- décodage audio (app/audio.py) -------------------------------------
    "audio.ffmpeg.titre": "FFmpeg introuvable",
    "audio.ffmpeg.msg_installee": (
        "Le décodeur audio est introuvable. Réinstallez l'application depuis son "
        "programme d'installation."
    ),
    "audio.ffmpeg.msg_sources": (
        "Le décodeur audio est introuvable. Relancez « installer.bat », ou installez-le "
        "à la main avec : pip install imageio-ffmpeg"
    ),
    "audio.introuvable.titre": "Fichier introuvable",
    "audio.introuvable.msg": "« {nom} » n'existe plus à l'emplacement indiqué.",
    "audio.decodage.titre": "Décodage impossible",
    "audio.decodage.msg": "FFmpeg n'a pas pu être lancé sur « {nom} ».",
    "audio.illisible.titre": "Fichier audio illisible",
    "audio.illisible.msg": (
        "« {nom} » n'a pas pu être décodé : le fichier est peut-être corrompu, "
        "incomplet, ou ne contient aucune piste audio. Le détail FFmpeg est dans "
        "logs/{journal}."
    ),
    "audio.muet.titre": "Aucun son détecté",
    "audio.muet.msg": "« {nom} » ne contient aucune donnée audio exploitable.",

    # -- moteur (app/moteur.py) --------------------------------------------
    "moteur.non_charge.titre": "Modèle non chargé",
    "moteur.non_charge.msg": "La transcription a été demandée avant le chargement du modèle.",
    "moteur.premier_usage": (
        "Premier usage de ce modèle : téléchargement d'environ {taille}. Cela n'arrive "
        "qu'une fois, ensuite tout reste sur la machine."
    ),
    "moteur.modele_incomplet": (
        "Le modèle « {modele} » était incomplet, un téléchargement précédent a été "
        "interrompu. Il est retéléchargé maintenant, environ {taille}. La transcription "
        "reprendra toute seule ensuite."
    ),
    "moteur.modele_incomplet_bloque": (
        "Le modèle « {modele} » est incomplet et son dossier n'a pas pu être renouvelé. "
        "Il est peut-être ouvert par un autre programme. Fermez les autres applications "
        "puis relancez, ou effacez « {dossier} »."
    ),
    "moteur.telechargement_reprend": (
        "Le téléchargement du modèle « {modele} » ({taille}) avait été coupé. Il "
        "reprend où il s'était arrêté, rien de ce qui était déjà reçu n'est perdu."
    ),
    "moteur.telechargement_echoue.titre": "Téléchargement du modèle incomplet",
    "moteur.telechargement_echoue.msg": (
        "Le téléchargement du modèle {modele} ({taille}) a échoué. Vérifiez la "
        "connexion Internet et l'espace disque (il faut environ {requis} libres), "
        "puis relancez le fichier. Ce qui a déjà été reçu est conservé : la "
        "prochaine tentative repartira de là. Si le problème revient alors que le "
        "reste d'Internet fonctionne, la connexion filtre sans doute le "
        "téléchargement : un antivirus, un pare-feu d'entreprise ou un partage de "
        "connexion mobile suffisent. Essayez depuis un autre réseau."
    ),
    "moteur.disque_insuffisant": (
        "Le modèle {modele} demande environ {requis} d'espace libre pour être "
        "téléchargé, et il n'en reste que {libre} sur le disque des modèles "
        "({dossier}). Libérez de la place, puis relancez le fichier."
    ),
    "moteur.reseau_indisponible": (
        "Le modèle {modele} ({taille}) n'est pas encore sur cette machine, et le "
        "dépôt Hugging Face est injoignable. Vérifiez la connexion Internet, puis "
        "relancez le fichier. Une fois téléchargé, le modèle reste local et "
        "l'application n'a plus besoin du réseau."
    ),
    "moteur.chargement": "Chargement du modèle {modele}...",
    "moteur.taille_inconnue": "quelques centaines de Mo à 3 Go",

    # -- séparation des locuteurs (app/diarisation.py) ---------------------
    "diar.locuteur": "Locuteur {n}",
    # Depuis la version 2.3.0, ces trois phrases ne renvoient plus à une
    # procédure : le bouton « Installer la séparation des locuteurs » du panneau
    # « Locuteurs » fait le travail, dans les deux modes.
    "diar.indispo.installee": (
        "La séparation des locuteurs n'est pas encore installée. Elle repose sur PyTorch, "
        "environ 3,6 Go de composants à poser une seule fois. Le bouton "
        "« Installer la séparation des locuteurs » du panneau « Locuteurs » s'en charge."
    ),
    "diar.indispo.torch": (
        "PyTorch n'est pas installé. Le bouton « Installer la séparation des locuteurs » "
        "du panneau « Locuteurs » le pose pour vous."
    ),
    "diar.indispo.pyannote": (
        "La bibliothèque pyannote.audio n'est pas installée. Le bouton « Installer la "
        "séparation des locuteurs » du panneau « Locuteurs » la pose pour vous."
    ),
    "diar.inaccessible.titre": "Modèle de locuteurs inaccessible",
    "diar.inaccessible.depot": (
        "Le dépôt {depot} n'a rien renvoyé, généralement parce que ses conditions "
        "d'utilisation n'ont pas été acceptées avec ce compte."
    ),
    "diar.inaccessible.aucun": "Aucun dépôt pyannote n'a pu être chargé.",
    "diar.indisponible.titre": "Séparation des locuteurs indisponible",
    "diar.jeton_manquant.titre": "Jeton Hugging Face manquant",
    "diar.jeton_manquant.msg": (
        "La séparation des locuteurs a besoin d'un jeton gratuit. Ouvrez le panneau "
        "« Locuteurs » : la marche à suivre y est détaillée en trois étapes."
    ),
    "diar.chargement": "Chargement du modèle de locuteurs ({depot})...",
    "diar.analyse": "Analyse des voix en cours...",
    "diar.guide.etape1": (
        "Créez un compte gratuit sur huggingface.co, puis ouvrez la page du modèle "
        "pyannote/speaker-diarization-3.1 et acceptez ses conditions d'utilisation."
    ),
    "diar.guide.etape2": "Dans les réglages du compte, créez un jeton d'accès de type « Read ».",
    "diar.guide.etape3": (
        "Collez le jeton dans le champ ci-dessous. Il est enregistré dans le fichier "
        "« jeton_hf.txt » de vos données personnelles, et n'est jamais versionné."
    ),

    # -- installation de l'extension « locuteurs » (app/extensions.py) -----
    "ext.deja_en_cours": "Une installation est déjà en cours.",
    "ext.espace_insuffisant": (
        "Il ne reste que {libre} Go de libre sur ce disque, et il en faut environ {requis}. "
        "Faites de la place, puis relancez l'installation."
    ),
    "ext.lancement_impossible": (
        "L'installation n'a pas pu démarrer. Le journal de bord en dit davantage."
    ),
    "ext.lot.locuteurs": "PyTorch et pyannote.audio",
    "ext.lot.paquets": "composants",
    "ext.etape.preparation": "Préparation de l'installation...",
    "ext.etape.installation": "Installation de {nom}...",
    "ext.etape.lot": "Étape {numero} sur {total} : {nom}",
    "ext.etape.paquet": "Récupération de {paquet}...",
    "ext.etape.telechargement": "Téléchargement de {paquet} : {recu} sur {total}",
    "ext.etape.pose": "Mise en place des composants...",
    "ext.etape.echec_lot": "Une étape a échoué.",
    "ext.annulee": "Installation annulée. Ce qui a été téléchargé est conservé pour une reprise.",
    "ext.echec": (
        "L'installation n'a pas abouti. Vérifiez la connexion Internet et la place "
        "disponible, puis relancez : le téléchargement reprend où il s'était arrêté."
    ),
    "ext.verification_ko": (
        "Les composants ont été posés mais ne se chargent pas. Retirez la séparation "
        "des locuteurs, puis réinstallez-la."
    ),
    "ext.installee": "Séparation des locuteurs installée. Elle est active immédiatement.",
    "ext.installee_redemarrer": (
        "Séparation des locuteurs installée. Redémarrez l'application pour l'activer."
    ),
    "ext.retrait_echec": (
        "Le retrait n'a pas pu se faire entièrement. Fermez l'application, puis "
        "recommencez."
    ),
    "ext.retiree": "Séparation des locuteurs retirée, {taille} Go libérés.",

    # -- glossaire et corrections (app/vocabulaire.py) ---------------------
    "voc.glossaire_vide": "Glossaire vide : aucune amorce envoyée au modèle.",
    "voc.premier_trop_long": "Le premier terme dépasse déjà la limite de l'amorce.",
    "voc.amorce_tronquee": (
        "{retenus} termes sur {total} tiennent dans l'amorce ({jetons} jetons sur "
        "{limite} possibles). Les suivants sont ignorés : placez les plus importants en "
        "haut du fichier."
    ),
    "voc.amorce_ok": "{retenus} termes envoyés au modèle ({jetons} jetons sur {limite}).",
    "voc.err.fleche": "Ligne {ligne} : il manque la flèche « => ».",
    "voc.err.source_vide": "Ligne {ligne} : la forme à corriger est vide.",
    "voc.err.cible_vide": "Ligne {ligne} : la forme correcte est vide.",
    "voc.err.illisible": "Ligne {ligne} : règle illisible ({detail}).",
    "voc.section_apprises": "# Apprises depuis les transcriptions",
    "voc.section_commentaire": "# Ajoutées d'un clic depuis la vue de lecture. Modifiables à la main.",
    "regle.selection_vide": "Sélectionnez d'abord le mot ou l'expression à corriger.",
    "regle.cible_vide": "Indiquez la forme correcte.",
    "regle.identique": "La forme corrigée est identique à la forme entendue.",
    "regle.trop_longue": (
        "La {etiquette} est trop longue : une correction porte sur un mot ou une courte "
        "expression, {max} caractères au maximum."
    ),
    "regle.etiquette.source": "forme entendue",
    "regle.etiquette.cible": "forme corrigée",
    "regle.fleche_interdite": "Une correction ne peut pas contenir la flèche « => ».",
    "regle.diese_interdit": "Une correction ne peut pas commencer par « # ».",
    "regle.deja_enregistree": "Cette règle était déjà enregistrée.",
    "regle.conflit": (
        "Une règle existe déjà pour « {source} », vers « {cible} ». Modifiez-la dans le "
        "panneau « Corrections » si elle n'est plus la bonne."
    ),
    "regle.ajoutee": "Règle « {source} » vers « {cible} » ajoutée aux corrections.",

    # -- nom des fichiers produits (app/nommage.py) ------------------------
    "nom.caracteres_interdits": (
        "Ces caractères sont interdits dans un nom de fichier Windows : {liste}."
    ),
    "nom.caractere_controle": (
        "Ce motif contient un caractère de contrôle, qui n'a pas sa place dans un nom."
    ),
    "nom.aucun_nom": "Ce motif ne produit aucun nom de fichier.",
    "nom.nom_reserve": "« {nom} » est un nom réservé par Windows, choisissez-en un autre.",
    "nom.sans_variable": (
        "Ce motif ne contient aucune variable : tous vos fichiers porteront le même nom, "
        "suivi de -2, -3, et ainsi de suite."
    ),
    "nom.exemple": "Réunion équipe.m4a",
    "nom.repli": "transcription",

    # -- vue de lecture (app/lecture.py) -----------------------------------
    "lect.absent": "Ce fichier n'existe plus à l'emplacement indiqué.",
    "lect.illisible": "Ce fichier n'a pas pu être lu.",
    "lect.sans_compagnon": (
        "Cette transcription n'a pas de fichier compagnon : elle a été produite avant "
        "cette fonction, ou l'option était coupée. Le texte s'affiche normalement, sans "
        "indication de confiance."
    ),
    "lect.tronque": (
        "Ce fichier est très long : seul son début est affiché ici, et la confiance des "
        "mots n'est pas chargée. Ouvrez le fichier pour tout voir."
    ),
    "lect.locuteurs_detectes": "{n} locuteurs détectés",
    "lect.non_separes": "non séparés",
    "lect.non_interpretee": "Cette correction n'a pas pu être interprétée.",
    "lect.non_retrouve": "« {source} » n'a pas été retrouvé dans ce texte.",
    "lect.non_reecrit": "Le fichier n'a pas pu être réécrit.",
    "lect.remplacements.un": "{n} remplacement dans le fichier.",
    "lect.remplacements.autres": "{n} remplacements dans le fichier.",

    # -- espace occupé (app/stockage.py) -----------------------------------
    "stock.modeles.libelle": "Modèles de transcription",
    "stock.modeles.detail": (
        "Téléchargés une seule fois, au premier usage. Les effacer n'abîme rien, ils se "
        "retéléchargent au besoin."
    ),
    "stock.donnees.libelle": "Vos données",
    "stock.donnees.detail": (
        "Réglages, glossaire, corrections, gabarit, journaux et fichiers de reprise. "
        "C'est ce que l'export du panneau « Mes données » sait sauvegarder."
    ),
    "stock.programme.libelle": "Programme",
    "stock.programme.detail_installee": (
        "Le programme installé, dans votre espace utilisateur. Il se remplace par une "
        "réinstallation, jamais à la main."
    ),
    "stock.programme.detail_sources": (
        "Le dossier du projet, sans l'environnement Python « .venv » ni les dossiers de "
        "construction. Depuis les sources, vos données et vos modèles vivent dans ce "
        "même dossier et sont comptés à part."
    ),

    # -- import et export (app/donnees.py) ---------------------------------
    "reglage.preset": "Qualité de transcription",
    "reglage.langue": "Langue parlée",
    "reglage.langue_interface": "Langue de l'interface",
    "reglage.dossier_sortie": "Dossier de sortie",
    "reglage.diarisation": "Séparer les locuteurs",
    "reglage.nb_locuteurs": "Nombre de participants",
    "reglage.formats": "Formats produits",
    "reglage.appliquer_corrections": "Appliquer les corrections",
    "reglage.utiliser_glossaire": "Souffler le glossaire au modèle",
    "reglage.compagnon_confiance": "Enregistrer la confiance des mots",
    "reglage.corrections_apprises": "Mémoriser les corrections relues",
    "reglage.sauvegarde_progressive": "Sauvegarde progressive",
    "reglage.lecture_audio": "Écouter l'audio depuis la vue de lecture",
    "reglage.motif_sortie": "Nom des fichiers produits",
    "reglage.dossier_surveille": "Dossier surveillé",
    "reglage.surveillance": "Surveiller un dossier",
    "reglage.maj_verifier": "Vérifier les mises à jour",
    "reglage.barre_taches": "Progression dans la barre des tâches",
    "reglage.filtres_salle": "Audio de salle",
    "reglage.mode_avance": "Mode avancé",
    "reglage.modele_avance": "Modèle du mode avancé",
    "reglage.beam_size": "Largeur de faisceau",
    "reglage.condition_on_previous_text": "Garder le contexte",
    "reglage.forcer_processeur": "Forcer le processeur",
    "reglage.theme": "Thème",
    "reglage.zoom": "Zoom de l'interface",
    "reglage.journal_ouvert": "Journal déplié",
    "val.oui": "oui",
    "val.non": "non",
    "val.aucun": "aucun",
    "val.auto": "détection automatique",
    "val.preset": "valeur du preset",
    "val.vide": "vide",
    "val.date_inconnue": "date inconnue",
    "arch.type": "Archive de données Scribouille (*.zip)",
    "arch.tous_fichiers": "Tous les fichiers (*.*)",
    "arch.aucun_emplacement": "Aucun emplacement d'enregistrement choisi.",
    "arch.export_message": (
        "{termes} terme(s) de glossaire, {regles} règle(s) de correction et vos réglages "
        "ont été enregistrés dans « {chemin} ». Le jeton Hugging Face, les journaux et "
        "les modèles n'y sont pas."
    ),
    "arch.membre_inattendu": (
        "L'archive contient un élément inattendu (« {nom} »). Ce n'est pas un export "
        "Scribouille, ou il a été modifié."
    ),
    "arch.chemin_invalide": "L'archive contient un chemin de fichier invalide, elle est refusée.",
    "arch.fichier_absent": "Ce fichier n'existe plus, ou n'est pas lisible.",
    "arch.fichier_illisible": "Ce fichier n'a pas pu être lu ({erreur}).",
    "arch.vide": "Ce fichier est vide.",
    "arch.trop_gros": (
        "Ce fichier est bien trop gros pour un export Scribouille ({mo} Mo). Un export pèse "
        "quelques kilooctets."
    ),
    "arch.pas_zip": (
        "Ce fichier n'est pas une archive zip lisible. Il est peut-être abîmé, ou ce "
        "n'est pas le bon fichier."
    ),
    "arch.abimee": "L'archive est abîmée : le fichier « {nom} » qu'elle contient est illisible.",
    "arch.archive_vide": "Cette archive est vide.",
    "arch.membre_trop_gros": (
        "Le fichier « {nom} » de l'archive est anormalement gros, l'import est refusé."
    ),
    "arch.contenu_volumineux": (
        "Le contenu de cette archive est anormalement volumineux, l'import est refusé."
    ),
    "arch.membre_non_texte": (
        "Le fichier « {nom} » de l'archive n'est pas du texte lisible (encodage attendu : "
        "UTF-8)."
    ),
    "arch.zip_corrompue": "Cette archive zip est corrompue et n'a pas pu être ouverte.",
    "arch.manifeste_absent": "Ce fichier n'est pas un export Scribouille : son manifeste est absent.",
    "arch.manifeste_illisible": "Le manifeste de cette archive est illisible.",
    "arch.manifeste_forme": "Le manifeste de cette archive n'a pas la forme attendue.",
    "arch.autre_application": (
        "Ce fichier n'est pas un export Scribouille : son manifeste annonce « {application} »."
    ),
    "arch.application_inconnue": "application inconnue",
    "arch.format_invalide": "Le manifeste de cette archive n'indique pas de format valide.",
    "arch.format_recent": (
        "Cet export a été produit par une version plus récente de {application} (format "
        "{format}, cette version lit le format {lu}). Mettez l'application à jour avant "
        "de l'importer."
    ),
    "arch.aucun_declare": "Le manifeste de cette archive ne déclare aucun fichier.",
    "arch.declare_inattendu": (
        "Le manifeste déclare un fichier inattendu (« {nom} »), l'import est refusé."
    ),
    "arch.declare_absent": "Le manifeste annonce « {nom} », mais l'archive ne le contient pas.",
    "arch.config_illisible": "Les réglages de cette archive (config.json) sont illisibles.",
    "arch.config_forme": "Les réglages de cette archive n'ont pas la forme attendue.",
    "arch.sauvegarde_echouee": (
        "La sauvegarde de vos données actuelles a échoué, l'import est annulé pour ne "
        "rien écraser. {detail}"
    ),
    "arch.libelle.sortie": "Dossier de sortie",
    "arch.libelle.surveille": "Dossier surveillé",
    "arch.libelle.modeles": "Dossier des modèles",
    "arch.chemin_repris": "{libelle} : « {valeur} » sera repris.",
    "arch.chemin_absent": (
        "{libelle} : « {valeur} » n'existe pas sur ce poste, votre réglage actuel est "
        "conservé."
    ),
    "arch.import_message": (
        "Import terminé : {termes} terme(s) de glossaire, {regles} règle(s) de correction "
        "et vos réglages ont été remplacés."
    ),
    "arch.message_sauvegarde": (
        "Vos données d'avant l'import ont été enregistrées dans « {chemin} ». Ce fichier "
        "se réimporte de la même façon si vous voulez revenir en arrière."
    ),
    "arch.gabarit_inclus": (
        "Gabarit personnalisé inclus : le gabarit d'instructions pour l'IA de cette "
        "archive remplacera celui de ce poste."
    ),
    "arch.note.gabarit_repris": "Gabarit d'instructions pour l'IA repris de l'archive.",
    "arch.note.sortie_reprise": "Dossier de sortie repris : « {chemin} ».",
    "arch.note.sortie_absente": (
        "Le dossier de sortie de l'export, « {demande} », n'existe pas sur ce poste : "
        "votre dossier « {actuel} » est conservé."
    ),
    "arch.note.surveille_repris": "Dossier surveillé repris : « {chemin} ».",
    "arch.note.surveille_absent": (
        "Le dossier surveillé de l'export, « {chemin} », n'existe pas sur ce poste : la "
        "surveillance reste coupée."
    ),
    "arch.note.modeles_repris": "Dossier des modèles repris : « {chemin} ».",
    "arch.note.modeles_absents": (
        "Le dossier des modèles de l'export, « {demande} », n'existe pas sur ce poste : "
        "« {actuel} » est conservé."
    ),
    "arch.echec_import": (
        "{titre} : {message} Vos données d'avant l'import ont été sauvegardées dans "
        "« {sauvegarde} »."
    ),

    # -- dossier surveillé (app/surveillance.py) ---------------------------
    "veille.introuvable": "Le dossier surveillé « {chemin} » est introuvable.",
    "veille.pas_dossier": "« {chemin} » n'est pas un dossier.",
    "veille.illisible": "Le dossier surveillé « {chemin} » n'est pas lisible ({erreur}).",
    "veille.reprise_auto": (
        " La surveillance reprendra d'elle-même dès qu'il sera de nouveau accessible."
    ),
    "veille.retour": "Le dossier surveillé est de nouveau accessible.",

    # -- file de traitement (app/traitement.py) ----------------------------
    "etat.lecture": "Lecture du fichier",
    "etat.transcription": "Transcription",
    "etat.locuteurs": "Séparation des locuteurs",
    "etat.ecriture": "Écriture des fichiers",
    "etat.termine": "Terminé",
    "etat.annule": "Annulé",
    "etat.arrete": "Arrêté",
    "phase.transcription": "Transcription",
    "phase.locuteurs": "Locuteurs",
    "phase.termine": "Terminé",
    "phase.bientot": "bientôt",
    "trait.duree_audio": "{nom} : {duree} d'audio",
    "trait.reprise": (
        "Reprise de « {nom} » à {position} d'audio, {segments} segments déjà transcrits "
        "sont conservés, ainsi que {ecoule} de calcul."
    ),
    "trait.sauvegarde_coupee": (
        "Sauvegarde progressive coupée : cette reprise ne sera pas protégée."
    ),
    "trait.glossaire_tronque": "Glossaire tronqué pour tenir dans l'amorce du modèle.",
    "trait.locuteurs_identifies": "{n} locuteurs identifiés.",
    "trait.diar_abandonnee": "{titre} : {message} La transcription continue sans étiquettes.",
    "trait.diar_incident": "{titre} : la transcription continue sans étiquettes.",
    "trait.corrections_fichier": "corrections.txt : {message}",
    "trait.corrections_appliquees": "{n} corrections automatiques appliquées.",
    "trait.disque_plein.msg": (
        "Il reste moins de 50 Mo sur le disque de destination. Libérez de l'espace puis "
        "relancez."
    ),
    "trait.termine": "{nom} transcrit en {duree} ({facteur} x la durée de l'audio).",

    # -- en-tête des fichiers produits (app/sorties.py) --------------------
    "ent.titre": "Transcription : {nom}",
    "ent.source": "Source",
    "ent.duree": "Durée de l'audio",
    "ent.modele": "Modèle",
    "ent.calcul": "Calcul",
    "ent.langue": "Langue",
    "ent.locuteurs": "Locuteurs",
    "ent.corrections": "Corrections",
    "ent.glossaire": "Glossaire",
    "ent.transcrit_le": "Transcrit le",
    "ent.temps_calcul": "Temps de calcul",
    "ent.valeur.modele": "{modele}  ({preset})",
    "ent.valeur.locuteurs": "{n} détectés",
    "ent.valeur.non_separes": "non séparés (voir le journal)",
    "ent.valeur.corrections": "{n} remplacements automatiques",
    "ent.valeur.glossaire": "{n} termes envoyés au modèle",
    "ent.valeur.temps_calcul": "{duree}  (facteur {facteur} x temps réel)",
    "ent.reglages_personnalises": "réglages personnalisés",
    "ent.mention_locale": "Produit localement, aucune donnée n'a quitté cette machine.",
    "sortie.aucune_parole": "(aucune parole détectée dans cet enregistrement)",

    # -- passerelle et fenêtre (transcriber.pyw) ---------------------------
    "app.dependances.titre": "Il manque des composants pour démarrer :",
    "app.dependances.installee": (
        "L'installation est incomplète ou abîmée. Réinstallez l'application depuis son "
        "programme d'installation."
    ),
    "app.dependances.sources": (
        "Lancez « installer.bat » à côté de l'application, il pose tout automatiquement. "
        "Installation manuelle :"
    ),
    "app.fenetre_impossible": (
        "La fenêtre n'a pas pu s'ouvrir.\n\nSous Windows, cela vient presque toujours de "
        "« Microsoft Edge WebView2 Runtime », absent du poste. Installez-le puis "
        "relancez.\n\nDétail : logs/{journal}"
    ),
    "app.telechargement_annonce": (
        "Le modèle « {modele} » n'est pas encore sur cette machine. Il sera téléchargé "
        "une seule fois au lancement de la première transcription, environ {taille}, dans "
        "« {dossier} ». Une connexion Internet est nécessaire pour cette étape, et pour "
        "elle seulement : ensuite l'application fonctionne entièrement hors ligne."
    ),
    "app.telechargement_reparation": (
        "Le modèle « {modele} » est présent mais incomplet : un téléchargement précédent "
        "a été interrompu. Il sera renouvelé automatiquement au lancement de la "
        "prochaine transcription, environ {taille}, dans « {dossier} ». Rien à faire, "
        "une connexion Internet suffit."
    ),
    "app.modeles.range": "Les modèles seront rangés dans « {dossier} ».",
    "app.modeles.ancien": (
        " L'ancien dossier « {ancien} » n'a pas été touché, vous pouvez le supprimer si "
        "vous n'en avez plus besoin."
    ),
    "app.motif.defaut": "Nommage par défaut rétabli.",
    "app.motif.enregistre": "Motif enregistré.",
    "app.veille.choisir": "Choisissez d'abord le dossier à surveiller.",
    "app.veille.pas_accessible": "« {chemin} » n'est pas un dossier accessible.",
    "app.veille.active": "Les nouveaux fichiers déposés dans « {chemin} » rejoindront la file.",
    "app.veille.coupee": "Surveillance coupée.",
    "app.veille.memoire_videe": (
        "Mémoire vidée : les fichiers déjà présents seront repris au prochain passage, "
        "dans une dizaine de secondes."
    ),
    "app.jeton.prefixe": "Un jeton Hugging Face commence par « hf_ ». Vérifiez le copier-coller.",
    "app.jeton.efface": "Jeton effacé.",
    "app.jeton.enregistre": (
        "Jeton enregistré. Il sera vérifié au premier usage de la séparation des locuteurs."
    ),
    "app.export.fenetre": "La fenêtre d'enregistrement n'a pas pu s'ouvrir.",
    "app.dialogue.audio": "Fichiers audio et vidéo ({extensions})",
    "app.depot.dossier": "Dossier « {nom} » : {retenus} fichier(s) audio retenu(s)",
    "app.depot.ignores": ", {n} entrée(s) ignorée(s)",
    "app.depot.sous_dossiers": ". Les sous-dossiers ne sont pas parcourus.",
    "app.depot.aucun": "Aucun fichier audio exploitable dans ce dépôt.",
    "app.depot.chemin_illisible": (
        "Le chemin des fichiers déposés n'a pas pu être lu. Utilisez le bouton "
        "« Parcourir »."
    ),
    "app.ajoutes.un": "{n} fichier ajouté à la file.",
    "app.ajoutes.autres": "{n} fichiers ajoutés à la file.",
    "app.veille.ajoutes.un": "Dossier surveillé : {n} fichier ajouté à la file.",
    "app.veille.ajoutes.autres": "Dossier surveillé : {n} fichiers ajoutés à la file.",
    "app.demarrer.en_cours": "Une transcription est déjà en cours.",
    "app.demarrer.ffmpeg_installee": (
        "Le décodeur audio FFmpeg est introuvable. Réinstallez l'application depuis son "
        "programme d'installation."
    ),
    "app.demarrer.ffmpeg_sources": (
        "Le décodeur audio FFmpeg est introuvable. Relancez « installer.bat » pour le poser."
    ),
    "app.demarrer.sortie": "Le dossier de sortie n'est pas accessible en écriture ({erreur}).",
    "app.demarrer.file_vide": "Aucun fichier en attente dans la file.",
    "app.demarrer.lancee": "Démarrage de la file.",
    "app.diar.ignoree": "Séparation des locuteurs ignorée : {raison}",
    "app.diar.sans_jeton": (
        "Aucun jeton Hugging Face : la transcription se fera sans étiquettes de locuteur."
    ),
    "app.modele.dossier_inutilisable": (
        "Le modèle doit être téléchargé, mais le dossier prévu « {dossier} » n'est pas "
        "utilisable. {probleme} Choisissez un autre emplacement dans les réglages, "
        "section « Modèles »."
    ),
    "app.modele.place": (
        "Il faut environ {taille} pour télécharger ce modèle, et il ne reste que {libre} "
        "Go sur le disque de « {dossier} ». Libérez de la place, ou rangez les modèles "
        "sur un autre disque dans les réglages, section « Modèles »."
    ),
    "app.modele.hors_ligne": (
        "Ce modèle n'est pas encore sur la machine, il pèse environ {taille} et doit être "
        "téléchargé une première fois. Or aucune connexion Internet n'a été trouvée. "
        "Connectez le poste le temps de ce téléchargement, ensuite l'application "
        "fonctionnera définitivement hors ligne. Si un modèle plus léger vous suffit, le "
        "preset « Rapide » demande 1,6 Go au lieu de 3,1 Go."
    ),
    "app.modele.incomplet_hors_ligne": (
        "Le modèle présent sur cette machine est incomplet : le téléchargement précédent "
        "a été interrompu avant la fin. Il doit être repris, environ {taille}, or aucune "
        "connexion Internet n'a été trouvée. Connectez le poste le temps de ce "
        "téléchargement, l'application s'en occupe seule ensuite."
    ),
    "app.modele.premier_usage": (
        "Premier usage de ce modèle : téléchargement d'environ {taille} vers « {dossier} ». "
        "Cela n'arrive qu'une fois, ensuite tout reste sur la machine."
    ),
    "app.modele.incomplet": (
        "Le modèle présent est incomplet, un téléchargement précédent a été interrompu. "
        "Il va être renouvelé automatiquement, environ {taille} vers « {dossier} »."
    ),
    "app.arret": "Arrêt demandé, la transcription en cours va s'interrompre.",
    "app.fichier_disparu": "Ce fichier n'existe plus.",
    "app.copie_ia": (
        "Instructions et transcription copiées, {n} caractères. Collez-les dans "
        "l'assistant de votre choix."
    ),
    "app.gabarit_enregistre": "Gabarit enregistré.",
    "app.reprise.indisponible": "Cette reprise n'est plus disponible.",
    "app.reprise.introuvable": (
        "Le fichier d'origine est introuvable, ou il est déjà en cours de traitement dans "
        "la file."
    ),
    "app.reprise.remise": (
        "« {nom} » remis en file, la transcription reprendra à {position} d'audio."
    ),
    "app.langue.changee": "Langue de l'interface : français.",

    # -- gabarit d'instructions créé au premier usage (app/gabarit.py) -----
    #
    # Contenu du fichier « gabarit-ia.txt ». Il est écrit UNE FOIS, dans la
    # langue d'interface du moment, et n'est plus jamais retouché ensuite : ce
    # fichier appartient à l'utilisateur.
    "gabarit.defaut": """\
# ---------------------------------------------------------------------------
# Gabarit d'instructions pour un assistant IA
#
# Ce texte est copié dans le presse-papiers par le bouton « Copier pour l'IA »
# de la vue de lecture, suivi du texte de la transcription. Il est à vous :
# modifiez-le, il n'est jamais réécrit par l'application.
#
# Les lignes commençant par « # » sont des commentaires, elles ne sont pas
# copiées. Les variables suivantes sont remplacées au moment de la copie :
#
#   {texte}      le texte complet de la transcription
#   {fichier}    le nom du fichier audio d'origine
#   {date}       la date de la transcription
#   {duree}      la durée de l'enregistrement
#   {locuteurs}  le nombre de locuteurs détectés, ou « non séparés »
#   {modele}     le modèle de transcription utilisé
#
# Aucune donnée ne part d'elle-même : la copie reste dans votre presse-papiers.
# ---------------------------------------------------------------------------

Tu es chargé de rédiger le compte rendu d'une réunion à partir de sa
transcription automatique, fournie plus bas.

Cette transcription est brute : elle peut contenir des erreurs de mots, des
hésitations et des répétitions. Ne corrige pas le fond, mais ignore les
scories de l'oral. Si un passage est incompréhensible ou ambigu, signale-le
plutôt que de l'inventer.

Rédige en français, dans un style factuel et sobre, avec les rubriques
suivantes, dans cet ordre :

1. Objet et contexte, en trois lignes au maximum.
2. Participants, tels qu'ils apparaissent dans la transcription. Si les
   locuteurs ne sont pas identifiés, écris-le au lieu de deviner.
3. Points abordés, un paragraphe court par sujet.
4. Décisions prises, sous forme de liste. Une décision par ligne, formulée de
   manière autonome et compréhensible sans le reste du document.
5. Actions à mener, sous forme de liste, avec pour chacune la personne
   responsable et l'échéance si elles sont mentionnées, sinon « non précisé ».
6. Points restés ouverts ou à trancher.

N'ajoute aucune information qui ne figure pas dans la transcription.

Informations sur l'enregistrement :

- Fichier : {fichier}
- Date de la transcription : {date}
- Durée de l'enregistrement : {duree}
- Locuteurs : {locuteurs}
- Modèle de transcription : {modele}

Transcription :

{texte}
""",
}


# ---------------------------------------------------------------------------
# Catalogue : anglais
# ---------------------------------------------------------------------------

_EN: dict[str, str] = {

    "langue.fr": "French",
    "langue.en": "English",

    "format.date_heure": "%m/%d/%Y at %H:%M",
    "format.decimal": ".",
    "format.titre_message": "{titre}: {message}",
    "contexte.export": "data export",
    "contexte.import": "data import",
    "duree.heures": "{h} h {m}",
    "duree.minutes": "{m} min {s}",
    "duree.secondes": "{s} s",
    "duree.vide": "--",
    "duree_longue.heures": "{h} h {m} min",
    "duree_longue.minutes": "{m} min {s} s",
    "unite.go": "GB",
    "unite.mo": "MB",
    "unite.ko": "KB",
    "unite.octet": "0 bytes",
    "unite.octets": "{n} bytes",

    "err.memoire.titre": "Not enough memory",
    "err.memoire.msg": (
        "This machine does not have enough RAM for that model. Try the \"Fast\" preset, "
        "turn off speaker separation, or close the other applications you have open."
    ),
    "err.disque.titre": "Disk full",
    "err.disque.msg": (
        "There is no longer enough space on the disk to write the result or download the "
        "model. Free some space, then start again."
    ),
    "err.jeton.titre": "Access to the speaker model was refused",
    "err.jeton.msg": (
        "The Hugging Face token is missing or invalid, or the pyannote model terms have "
        "not been accepted. Open the \"Speakers\" panel to review the steps. "
        "Transcription on its own works without a token."
    ),
    "err.reseau.titre": "Download failed",
    "err.reseau.msg": (
        "The model is not on this machine yet and the download failed. Check your "
        "Internet connection, then start again: once downloaded, the model stays local "
        "and the application no longer needs the network."
    ),
    "err.modele.titre": "Transcription model unusable",
    "err.modele.msg": (
        "The model files are missing or damaged, and the folder could not be renewed "
        "automatically. Close any other application that might be holding it, then "
        "start the transcription again: the model will be downloaded afresh. The models "
        "folder is shown in the settings, \"Models\" section."
    ),
    "err.cuda.titre": "NVIDIA acceleration unavailable",
    "err.cuda.msg": (
        "The CUDA libraries (cuBLAS, cuDNN) could not be loaded. Run the installer "
        "again, or force CPU mode in the advanced settings."
    ),
    "err.fichier.titre": "File not found",
    "err.fichier.msg": (
        "The file was moved, renamed or deleted after it was added to the queue."
    ),
    "err.acces.titre": "Access denied",
    "err.acces.msg": (
        "Windows refused to read or write this file. Check that it is not open in "
        "another application and that the output folder is writable."
    ),
    "err.inattendu.titre": "Unexpected failure",
    "err.inattendu.titre_contexte": "Unexpected failure ({contexte})",
    "err.inattendu.msg": "The technical details are recorded in logs/{journal}.",

    "preset.qualite.nom": "Highest quality",
    "preset.qualite.resume": "The best text possible. For meetings and anything you will read back.",
    "preset.rapide.nom": "Fast",
    "preset.rapide.resume": "About four times faster, quality one notch below.",
    "preset.personnalise": "{nom}, custom settings",
    "modele.qualite.depannage": "Fallback",
    "modele.qualite.faible": "Low",
    "modele.qualite.correcte": "Fair",
    "modele.qualite.bonne": "Good",
    "modele.qualite.tres_bonne": "Very good",
    "modele.qualite.excellente": "Excellent",
    "reco.memoire_juste": (
        "RAM detected: {ram} GB. That is too tight for large-v3, the \"Fast\" preset is "
        "the better choice here."
    ),
    "reco.cuda": (
        "NVIDIA card in use: the \"Highest quality\" preset runs comfortably faster than "
        "real time."
    ),
    "reco.processeur": (
        "Transcription on the CPU: the \"Highest quality\" preset is the right choice for "
        "meetings, just start it and let it run."
    ),
    "avert.memoire_tres_serree": (
        "This machine reports {ram} GB of RAM. The large-v3 model is likely to run out of "
        "memory: use the \"Fast\" preset instead."
    ),
    "avert.memoire_serree_diar": (
        "RAM: {ram} GB. large-v3 plus speaker separation still fits, because the two "
        "stages run one after the other and are never loaded at the same time. Close any "
        "heavy applications before starting a long meeting all the same."
    ),
    "avert.ram_libre": (
        "Only about {go} GB of memory is free. Close a few applications before starting "
        "the queue."
    ),
    "avert.amd": (
        "{carte} detected but not used: in v1, only the CPU works on non NVIDIA cards."
    ),

    "mat.cpu_inconnu": "Unknown processor",
    "mat.fils": "{n} threads",
    "mat.coeurs_fils": "{coeurs} cores / {fils} threads",
    "mat.memoire": "{go} GB of memory",
    "mat.gpu_accelere": "{nom} (accelerated)",
    "mat.gpu_non_accelere": "{nom} (not accelerated in v1)",
    "mat.sans_gpu": "no dedicated graphics card",
    "mat.npu_non_exploite": "{nom} (not used)",
    "gpu.note.cuda_active": "CUDA acceleration active.",
    "gpu.note.cuda_absente": (
        "NVIDIA card detected, but the CUDA libraries used by CTranslate2 are not "
        "answering. Run the installer again to put them in place."
    ),
    "gpu.note.amd": (
        "Not accelerated in v1: CTranslate2 only supports CPU and CUDA. AMD acceleration "
        "through whisper.cpp Vulkan is planned for v1.x."
    ),
    "gpu.note.intel": (
        "Integrated graphics, detected but not used in v1: transcription runs on the "
        "CPU. Options for v1.x: whisper.cpp Vulkan, or OpenVINO."
    ),
    "gpu.note.autre": "Not accelerated in v1.",
    "npu.note": (
        "Detected, not used in v1. An NPU mainly targets battery life; OpenVINO is "
        "documented as a v1.x direction."
    ),

    "chemin.dossier_non_cree": "This folder could not be created ({erreur}).",
    "chemin.dossier_non_ecrivable": "This folder is not writable.",

    "audio.ffmpeg.titre": "FFmpeg not found",
    "audio.ffmpeg.msg_installee": (
        "The audio decoder could not be found. Reinstall the application from its "
        "installer."
    ),
    "audio.ffmpeg.msg_sources": (
        "The audio decoder could not be found. Run \"installer.bat\" again, or install it "
        "by hand with: pip install imageio-ffmpeg"
    ),
    "audio.introuvable.titre": "File not found",
    "audio.introuvable.msg": "\"{nom}\" is no longer at the given location.",
    "audio.decodage.titre": "Decoding failed",
    "audio.decodage.msg": "FFmpeg could not be started on \"{nom}\".",
    "audio.illisible.titre": "Unreadable audio file",
    "audio.illisible.msg": (
        "\"{nom}\" could not be decoded: the file may be corrupted, incomplete, or "
        "contain no audio track. The FFmpeg details are in logs/{journal}."
    ),
    "audio.muet.titre": "No sound found",
    "audio.muet.msg": "\"{nom}\" contains no usable audio data.",

    "moteur.non_charge.titre": "Model not loaded",
    "moteur.non_charge.msg": "Transcription was requested before the model was loaded.",
    "moteur.premier_usage": (
        "First use of this model: about {taille} will be downloaded. This happens only "
        "once, after that everything stays on the machine."
    ),
    "moteur.modele_incomplet": (
        "Model \"{modele}\" was incomplete, an earlier download had been interrupted. "
        "It is being downloaded again now, about {taille}. Transcription will then "
        "resume on its own."
    ),
    "moteur.modele_incomplet_bloque": (
        "Model \"{modele}\" is incomplete and its folder could not be renewed. It may be "
        "open in another program. Close the other applications and start again, or "
        "delete \"{dossier}\"."
    ),
    "moteur.telechargement_reprend": (
        "The download of model \"{modele}\" ({taille}) had been cut short. It resumes "
        "where it stopped, nothing already received is lost."
    ),
    "moteur.telechargement_echoue.titre": "Model download incomplete",
    "moteur.telechargement_echoue.msg": (
        "The download of model {modele} ({taille}) failed. Check your Internet "
        "connection and disk space (about {requis} free is needed), then start the file "
        "again. What was already received is kept: the next attempt will resume from "
        "there. If it keeps failing while the rest of the Internet works, the "
        "connection is most likely filtering the download: an antivirus, a company "
        "firewall or a phone hotspot are enough to do that. Try from another network."
    ),
    "moteur.disque_insuffisant": (
        "Model {modele} needs about {requis} of free space to be downloaded, and only "
        "{libre} is left on the models disk ({dossier}). Free up space, then start the "
        "file again."
    ),
    "moteur.reseau_indisponible": (
        "Model {modele} ({taille}) is not on this machine yet, and the Hugging Face "
        "repository cannot be reached. Check your Internet connection, then start the "
        "file again. Once downloaded, the model stays local and the application no "
        "longer needs the network."
    ),
    "moteur.chargement": "Loading model {modele}...",
    "moteur.taille_inconnue": "a few hundred MB up to 3 GB",

    "diar.locuteur": "Speaker {n}",
    "diar.indispo.installee": (
        "Speaker separation is not installed yet. It relies on PyTorch, about 3.6 GB of "
        "components to install once. The \"Install speaker separation\" button in the "
        "\"Speakers\" panel takes care of it."
    ),
    "diar.indispo.torch": (
        "PyTorch is not installed. The \"Install speaker separation\" button in the "
        "\"Speakers\" panel puts it in place for you."
    ),
    "diar.indispo.pyannote": (
        "The pyannote.audio library is not installed. The \"Install speaker separation\" "
        "button in the \"Speakers\" panel puts it in place for you."
    ),
    "diar.inaccessible.titre": "Speaker model unreachable",
    "diar.inaccessible.depot": (
        "The {depot} repository returned nothing, usually because its terms of use have "
        "not been accepted with this account."
    ),
    "diar.inaccessible.aucun": "No pyannote repository could be loaded.",
    "diar.indisponible.titre": "Speaker separation unavailable",
    "diar.jeton_manquant.titre": "Hugging Face token missing",
    "diar.jeton_manquant.msg": (
        "Speaker separation needs a free token. Open the \"Speakers\" panel: the steps "
        "are set out there, three of them."
    ),
    "diar.chargement": "Loading the speaker model ({depot})...",
    "diar.analyse": "Analysing voices...",
    "diar.guide.etape1": (
        "Create a free account on huggingface.co, then open the page of the "
        "pyannote/speaker-diarization-3.1 model and accept its terms of use."
    ),
    "diar.guide.etape2": "In your account settings, create an access token of type \"Read\".",
    "diar.guide.etape3": (
        "Paste the token in the field below. It is saved in the \"jeton_hf.txt\" file of "
        "your personal data, and is never committed to version control."
    ),

    "ext.deja_en_cours": "An installation is already running.",
    "ext.espace_insuffisant": (
        "Only {libre} GB are free on this drive, and about {requis} are needed. Free up "
        "some space, then start the installation again."
    ),
    "ext.lancement_impossible": (
        "The installation could not start. The log file has more to say."
    ),
    "ext.lot.locuteurs": "PyTorch and pyannote.audio",
    "ext.lot.paquets": "components",
    "ext.etape.preparation": "Preparing the installation...",
    "ext.etape.installation": "Installing {nom}...",
    "ext.etape.lot": "Step {numero} of {total}: {nom}",
    "ext.etape.paquet": "Fetching {paquet}...",
    "ext.etape.telechargement": "Downloading {paquet}: {recu} of {total}",
    "ext.etape.pose": "Putting the components in place...",
    "ext.etape.echec_lot": "A step failed.",
    "ext.annulee": "Installation cancelled. What was downloaded is kept, so it can resume.",
    "ext.echec": (
        "The installation did not complete. Check your Internet connection and the free "
        "space, then start again: the download picks up where it stopped."
    ),
    "ext.verification_ko": (
        "The components were installed but do not load. Remove speaker separation, then "
        "install it again."
    ),
    "ext.installee": "Speaker separation installed. It is active right away.",
    "ext.installee_redemarrer": (
        "Speaker separation installed. Restart the application to activate it."
    ),
    "ext.retrait_echec": (
        "The removal could not complete. Close the application, then try again."
    ),
    "ext.retiree": "Speaker separation removed, {taille} GB freed.",

    "voc.glossaire_vide": "Glossary empty: no prompt is sent to the model.",
    "voc.premier_trop_long": "The first term already exceeds the prompt limit.",
    "voc.amorce_tronquee": (
        "{retenus} terms out of {total} fit in the prompt ({jetons} tokens out of "
        "{limite}). The rest are ignored: put the most important ones at the top of the "
        "file."
    ),
    "voc.amorce_ok": "{retenus} terms sent to the model ({jetons} tokens out of {limite}).",
    "voc.err.fleche": "Line {ligne}: the \"=>\" arrow is missing.",
    "voc.err.source_vide": "Line {ligne}: the form to correct is empty.",
    "voc.err.cible_vide": "Line {ligne}: the correct form is empty.",
    "voc.err.illisible": "Line {ligne}: unreadable rule ({detail}).",
    "voc.section_apprises": "# Learned from transcriptions",
    "voc.section_commentaire": "# Added in one click from the reading view. Editable by hand.",
    "regle.selection_vide": "Select the word or phrase to correct first.",
    "regle.cible_vide": "Enter the correct form.",
    "regle.identique": "The corrected form is identical to the transcribed form.",
    "regle.trop_longue": (
        "The {etiquette} is too long: a correction applies to a word or a short phrase, "
        "{max} characters at most."
    ),
    "regle.etiquette.source": "transcribed form",
    "regle.etiquette.cible": "corrected form",
    "regle.fleche_interdite": "A correction cannot contain the \"=>\" arrow.",
    "regle.diese_interdit": "A correction cannot start with \"#\".",
    "regle.deja_enregistree": "This rule was already saved.",
    "regle.conflit": (
        "A rule already exists for \"{source}\", pointing to \"{cible}\". Edit it in the "
        "\"Corrections\" panel if it is no longer the right one."
    ),
    "regle.ajoutee": "Rule \"{source}\" to \"{cible}\" added to your corrections.",

    "nom.caracteres_interdits": (
        "These characters are not allowed in a Windows file name: {liste}."
    ),
    "nom.caractere_controle": (
        "This pattern contains a control character, which has no place in a file name."
    ),
    "nom.aucun_nom": "This pattern produces no file name at all.",
    "nom.nom_reserve": "\"{nom}\" is a name reserved by Windows, please pick another one.",
    "nom.sans_variable": (
        "This pattern contains no variable: all your files will share the same name, "
        "followed by -2, -3, and so on."
    ),
    "nom.exemple": "Team meeting.m4a",
    "nom.repli": "transcript",

    "lect.absent": "This file is no longer at the given location.",
    "lect.illisible": "This file could not be read.",
    "lect.sans_compagnon": (
        "This transcript has no companion file: it was produced before that feature "
        "existed, or the option was off. The text is shown normally, without confidence "
        "marks."
    ),
    "lect.tronque": (
        "This file is very long: only its beginning is shown here, and word confidence is "
        "not loaded. Open the file to see everything."
    ),
    "lect.locuteurs_detectes": "{n} speakers detected",
    "lect.non_separes": "not separated",
    "lect.non_interpretee": "This correction could not be understood.",
    "lect.non_retrouve": "\"{source}\" was not found in this text.",
    "lect.non_reecrit": "The file could not be written back.",
    "lect.remplacements.un": "{n} replacement in the file.",
    "lect.remplacements.autres": "{n} replacements in the file.",

    "stock.modeles.libelle": "Transcription models",
    "stock.modeles.detail": (
        "Downloaded once, on first use. Deleting them breaks nothing, they are downloaded "
        "again when needed."
    ),
    "stock.donnees.libelle": "Your data",
    "stock.donnees.detail": (
        "Settings, glossary, corrections, prompt template, logs and resume files. This is "
        "what the export in the \"My data\" panel saves."
    ),
    "stock.programme.libelle": "Program",
    "stock.programme.detail_installee": (
        "The installed program, in your user space. It is replaced by reinstalling, never "
        "by hand."
    ),
    "stock.programme.detail_sources": (
        "The project folder, without the \".venv\" Python environment and the build "
        "folders. When running from source, your data and your models live in that same "
        "folder and are counted separately."
    ),

    "reglage.preset": "Transcription quality",
    "reglage.langue": "Spoken language",
    "reglage.langue_interface": "Interface language",
    "reglage.dossier_sortie": "Output folder",
    "reglage.diarisation": "Separate speakers",
    "reglage.nb_locuteurs": "Number of participants",
    "reglage.formats": "Output formats",
    "reglage.appliquer_corrections": "Apply corrections",
    "reglage.utiliser_glossaire": "Prime the model with the glossary",
    "reglage.compagnon_confiance": "Save word confidence",
    "reglage.corrections_apprises": "Remember corrections made while reading",
    "reglage.sauvegarde_progressive": "Progressive saving",
    "reglage.lecture_audio": "Play the audio from the reading view",
    "reglage.motif_sortie": "Output file names",
    "reglage.dossier_surveille": "Watched folder",
    "reglage.surveillance": "Watch a folder",
    "reglage.maj_verifier": "Check for updates",
    "reglage.barre_taches": "Progress in the taskbar",
    "reglage.filtres_salle": "Room audio",
    "reglage.mode_avance": "Advanced mode",
    "reglage.modele_avance": "Advanced mode model",
    "reglage.beam_size": "Beam width",
    "reglage.condition_on_previous_text": "Keep context",
    "reglage.forcer_processeur": "Force CPU",
    "reglage.theme": "Theme",
    "reglage.zoom": "Interface zoom",
    "reglage.journal_ouvert": "Activity log expanded",
    "val.oui": "yes",
    "val.non": "no",
    "val.aucun": "none",
    "val.auto": "automatic detection",
    "val.preset": "preset value",
    "val.vide": "empty",
    "val.date_inconnue": "unknown date",
    "arch.type": "Scribouille data archive (*.zip)",
    "arch.tous_fichiers": "All files (*.*)",
    "arch.aucun_emplacement": "No save location was chosen.",
    "arch.export_message": (
        "{termes} glossary term(s), {regles} correction rule(s) and your settings have "
        "been saved to \"{chemin}\". The Hugging Face token, the logs and the models are "
        "not in it."
    ),
    "arch.membre_inattendu": (
        "The archive contains an unexpected item (\"{nom}\"). This is not a Scribouille "
        "export, or it has been modified."
    ),
    "arch.chemin_invalide": "The archive contains an invalid file path, it is rejected.",
    "arch.fichier_absent": "This file no longer exists, or cannot be read.",
    "arch.fichier_illisible": "This file could not be read ({erreur}).",
    "arch.vide": "This file is empty.",
    "arch.trop_gros": (
        "This file is far too large for a Scribouille export ({mo} MB). An export weighs a "
        "few kilobytes."
    ),
    "arch.pas_zip": (
        "This file is not a readable zip archive. It may be damaged, or it may be the "
        "wrong file."
    ),
    "arch.abimee": "The archive is damaged: the file \"{nom}\" inside it cannot be read.",
    "arch.archive_vide": "This archive is empty.",
    "arch.membre_trop_gros": (
        "The file \"{nom}\" in the archive is abnormally large, the import is rejected."
    ),
    "arch.contenu_volumineux": (
        "The contents of this archive are abnormally large, the import is rejected."
    ),
    "arch.membre_non_texte": (
        "The file \"{nom}\" in the archive is not readable text (expected encoding: UTF-8)."
    ),
    "arch.zip_corrompue": "This zip archive is corrupted and could not be opened.",
    "arch.manifeste_absent": "This file is not a Scribouille export: its manifest is missing.",
    "arch.manifeste_illisible": "The manifest of this archive cannot be read.",
    "arch.manifeste_forme": "The manifest of this archive does not have the expected shape.",
    "arch.autre_application": (
        "This file is not a Scribouille export: its manifest declares \"{application}\"."
    ),
    "arch.application_inconnue": "unknown application",
    "arch.format_invalide": "The manifest of this archive does not declare a valid format.",
    "arch.format_recent": (
        "This export was produced by a newer version of {application} (format {format}, "
        "this version reads format {lu}). Update the application before importing it."
    ),
    "arch.aucun_declare": "The manifest of this archive declares no file.",
    "arch.declare_inattendu": (
        "The manifest declares an unexpected file (\"{nom}\"), the import is rejected."
    ),
    "arch.declare_absent": "The manifest announces \"{nom}\", but the archive does not contain it.",
    "arch.config_illisible": "The settings in this archive (config.json) cannot be read.",
    "arch.config_forme": "The settings in this archive do not have the expected shape.",
    "arch.sauvegarde_echouee": (
        "Backing up your current data failed, so the import was cancelled rather than "
        "overwrite anything. {detail}"
    ),
    "arch.libelle.sortie": "Output folder",
    "arch.libelle.surveille": "Watched folder",
    "arch.libelle.modeles": "Models folder",
    "arch.chemin_repris": "{libelle}: \"{valeur}\" will be used.",
    "arch.chemin_absent": (
        "{libelle}: \"{valeur}\" does not exist on this machine, your current setting is "
        "kept."
    ),
    "arch.import_message": (
        "Import finished: {termes} glossary term(s), {regles} correction rule(s) and your "
        "settings have been replaced."
    ),
    "arch.message_sauvegarde": (
        "Your data from before the import has been saved to \"{chemin}\". That file can be "
        "imported the same way if you want to go back."
    ),
    "arch.gabarit_inclus": (
        "Custom template included: the AI instruction template in this archive will "
        "replace the one on this machine."
    ),
    "arch.note.gabarit_repris": "AI instruction template taken from the archive.",
    "arch.note.sortie_reprise": "Output folder taken from the export: \"{chemin}\".",
    "arch.note.sortie_absente": (
        "The output folder in the export, \"{demande}\", does not exist on this machine: "
        "your folder \"{actuel}\" is kept."
    ),
    "arch.note.surveille_repris": "Watched folder taken from the export: \"{chemin}\".",
    "arch.note.surveille_absent": (
        "The watched folder in the export, \"{chemin}\", does not exist on this machine: "
        "watching stays off."
    ),
    "arch.note.modeles_repris": "Models folder taken from the export: \"{chemin}\".",
    "arch.note.modeles_absents": (
        "The models folder in the export, \"{demande}\", does not exist on this machine: "
        "\"{actuel}\" is kept."
    ),
    "arch.echec_import": (
        "{titre}: {message} Your data from before the import was saved to \"{sauvegarde}\"."
    ),

    "veille.introuvable": "The watched folder \"{chemin}\" cannot be found.",
    "veille.pas_dossier": "\"{chemin}\" is not a folder.",
    "veille.illisible": "The watched folder \"{chemin}\" cannot be read ({erreur}).",
    "veille.reprise_auto": " Watching will resume on its own as soon as it is reachable again.",
    "veille.retour": "The watched folder is reachable again.",

    "etat.lecture": "Reading the file",
    "etat.transcription": "Transcribing",
    "etat.locuteurs": "Speaker separation",
    "etat.ecriture": "Writing the files",
    "etat.termine": "Done",
    "etat.annule": "Cancelled",
    "etat.arrete": "Stopped",
    "phase.transcription": "Transcribing",
    "phase.locuteurs": "Speakers",
    "phase.termine": "Done",
    "phase.bientot": "almost there",
    "trait.duree_audio": "{nom}: {duree} of audio",
    "trait.reprise": (
        "Resuming \"{nom}\" at {position} of audio, {segments} segments already "
        "transcribed are kept, along with {ecoule} of compute."
    ),
    "trait.sauvegarde_coupee": (
        "Progressive saving is off: this resumed run will not be protected."
    ),
    "trait.glossaire_tronque": "Glossary trimmed to fit the model prompt.",
    "trait.locuteurs_identifies": "{n} speakers identified.",
    "trait.diar_abandonnee": "{titre}: {message} Transcription continues without labels.",
    "trait.diar_incident": "{titre}: transcription continues without labels.",
    "trait.corrections_fichier": "corrections.txt: {message}",
    "trait.corrections_appliquees": "{n} automatic corrections applied.",
    "trait.disque_plein.msg": (
        "Less than 50 MB is left on the destination disk. Free some space, then start "
        "again."
    ),
    "trait.termine": "{nom} transcribed in {duree} ({facteur} x the audio duration).",

    "ent.titre": "Transcript: {nom}",
    "ent.source": "Source",
    "ent.duree": "Audio duration",
    "ent.modele": "Model",
    "ent.calcul": "Compute",
    "ent.langue": "Language",
    "ent.locuteurs": "Speakers",
    "ent.corrections": "Corrections",
    "ent.glossaire": "Glossary",
    "ent.transcrit_le": "Transcribed on",
    "ent.temps_calcul": "Compute time",
    "ent.valeur.modele": "{modele}  ({preset})",
    "ent.valeur.locuteurs": "{n} detected",
    "ent.valeur.non_separes": "not separated (see the log)",
    "ent.valeur.corrections": "{n} automatic replacements",
    "ent.valeur.glossaire": "{n} terms sent to the model",
    "ent.valeur.temps_calcul": "{duree}  (factor {facteur} x real time)",
    "ent.reglages_personnalises": "custom settings",
    "ent.mention_locale": "Produced locally, no data left this machine.",
    "sortie.aucune_parole": "(no speech detected in this recording)",

    "app.dependances.titre": "Some components are missing to start:",
    "app.dependances.installee": (
        "The installation is incomplete or damaged. Reinstall the application from its "
        "installer."
    ),
    "app.dependances.sources": (
        "Run \"installer.bat\" next to the application, it sets everything up. Manual "
        "installation:"
    ),
    "app.fenetre_impossible": (
        "The window could not be opened.\n\nOn Windows this almost always comes from "
        "\"Microsoft Edge WebView2 Runtime\" being absent. Install it, then start "
        "again.\n\nDetails: logs/{journal}"
    ),
    "app.telechargement_annonce": (
        "The \"{modele}\" model is not on this machine yet. It will be downloaded once, "
        "when the first transcription starts, about {taille}, into \"{dossier}\". An "
        "Internet connection is needed for that step and for nothing else: after that the "
        "application runs entirely offline."
    ),
    "app.telechargement_reparation": (
        "Model \"{modele}\" is present but incomplete: an earlier download was "
        "interrupted. It will be renewed automatically when the next transcription "
        "starts, about {taille}, in \"{dossier}\". Nothing to do, an Internet connection "
        "is all it takes."
    ),
    "app.modeles.range": "Models will be stored in \"{dossier}\".",
    "app.modeles.ancien": (
        " The former folder \"{ancien}\" was left untouched, you can delete it if you no "
        "longer need it."
    ),
    "app.motif.defaut": "Default naming restored.",
    "app.motif.enregistre": "Pattern saved.",
    "app.veille.choisir": "Choose the folder to watch first.",
    "app.veille.pas_accessible": "\"{chemin}\" is not a reachable folder.",
    "app.veille.active": "New files dropped into \"{chemin}\" will join the queue.",
    "app.veille.coupee": "Folder watching turned off.",
    "app.veille.memoire_videe": (
        "Memory cleared: files already there will be picked up on the next pass, in about "
        "ten seconds."
    ),
    "app.jeton.prefixe": "A Hugging Face token starts with \"hf_\". Check what you pasted.",
    "app.jeton.efface": "Token cleared.",
    "app.jeton.enregistre": (
        "Token saved. It will be checked the first time speaker separation runs."
    ),
    "app.export.fenetre": "The save dialog could not be opened.",
    "app.dialogue.audio": "Audio and video files ({extensions})",
    "app.depot.dossier": "Folder \"{nom}\": {retenus} audio file(s) kept",
    "app.depot.ignores": ", {n} item(s) ignored",
    "app.depot.sous_dossiers": ". Subfolders are not scanned.",
    "app.depot.aucun": "No usable audio file in what was dropped.",
    "app.depot.chemin_illisible": (
        "The path of the dropped files could not be read. Use the \"Browse\" button."
    ),
    "app.ajoutes.un": "{n} file added to the queue.",
    "app.ajoutes.autres": "{n} files added to the queue.",
    "app.veille.ajoutes.un": "Watched folder: {n} file added to the queue.",
    "app.veille.ajoutes.autres": "Watched folder: {n} files added to the queue.",
    "app.demarrer.en_cours": "A transcription is already running.",
    "app.demarrer.ffmpeg_installee": (
        "The FFmpeg audio decoder could not be found. Reinstall the application from its "
        "installer."
    ),
    "app.demarrer.ffmpeg_sources": (
        "The FFmpeg audio decoder could not be found. Run \"installer.bat\" again to put "
        "it in place."
    ),
    "app.demarrer.sortie": "The output folder is not writable ({erreur}).",
    "app.demarrer.file_vide": "No file waiting in the queue.",
    "app.demarrer.lancee": "Queue started.",
    "app.diar.ignoree": "Speaker separation skipped: {raison}",
    "app.diar.sans_jeton": (
        "No Hugging Face token: the transcription will run without speaker labels."
    ),
    "app.modele.dossier_inutilisable": (
        "The model has to be downloaded, but the folder set aside for it, \"{dossier}\", "
        "cannot be used. {probleme} Choose another location in the settings, "
        "\"Models\" section."
    ),
    "app.modele.place": (
        "About {taille} is needed to download this model, and only {libre} GB is left on "
        "the disk holding \"{dossier}\". Free some space, or store the models on another "
        "disk in the settings, \"Models\" section."
    ),
    "app.modele.hors_ligne": (
        "This model is not on the machine yet, it weighs about {taille} and has to be "
        "downloaded once. No Internet connection was found. Connect this machine for the "
        "length of the download, after that the application works offline for good. If a "
        "lighter model is enough for you, the \"Fast\" preset needs 1.6 GB instead of 3.1 GB."
    ),
    "app.modele.incomplet_hors_ligne": (
        "The model on this machine is incomplete: the previous download was interrupted "
        "before the end. It has to be picked up again, about {taille}, but no Internet "
        "connection was found. Connect the machine for the duration of that download, "
        "the application then takes care of it on its own."
    ),
    "app.modele.premier_usage": (
        "First use of this model: about {taille} will be downloaded into \"{dossier}\". "
        "This happens only once, after that everything stays on the machine."
    ),
    "app.modele.incomplet": (
        "The model on this machine is incomplete, an earlier download was interrupted. "
        "It will be renewed automatically, about {taille} into \"{dossier}\"."
    ),
    "app.arret": "Stop requested, the running transcription will be interrupted.",
    "app.fichier_disparu": "This file no longer exists.",
    "app.copie_ia": (
        "Instructions and transcript copied, {n} characters. Paste them into the "
        "assistant of your choice."
    ),
    "app.gabarit_enregistre": "Template saved.",
    "app.reprise.indisponible": "This resume point is no longer available.",
    "app.reprise.introuvable": (
        "The original file cannot be found, or it is already being processed in the queue."
    ),
    "app.reprise.remise": (
        "\"{nom}\" put back in the queue, transcription will resume at {position} of audio."
    ),
    "app.langue.changee": "Interface language: English.",

    "gabarit.defaut": """\
# ---------------------------------------------------------------------------
# Instruction template for an AI assistant
#
# This text is copied to the clipboard by the "Copy for AI" button in the
# reading view, followed by the text of the transcript. It belongs to you:
# edit it freely, the application never rewrites it.
#
# Lines starting with "#" are comments and are not copied. The following
# variables are replaced at copy time:
#
#   {texte}      the full text of the transcript
#   {fichier}    the name of the original audio file
#   {date}       the date of the transcription
#   {duree}      the length of the recording
#   {locuteurs}  the number of speakers detected, or "not separated"
#   {modele}     the transcription model used
#
# Nothing is sent anywhere on its own: the copy stays in your clipboard.
# ---------------------------------------------------------------------------

Write the minutes of a meeting from its automatic transcript, provided below.

The transcript is raw: it may contain misheard words, hesitations and
repetitions. Do not change the substance, but leave out the noise of spoken
language. If a passage is unclear or ambiguous, say so rather than invent it.

Write in English, in a factual and plain style, with the following sections,
in this order:

1. Subject and context, three lines at most.
2. Participants, as they appear in the transcript. If the speakers are not
   identified, say so instead of guessing.
3. Topics discussed, one short paragraph per topic.
4. Decisions made, as a list. One decision per line, each phrased so that it
   stands on its own without the rest of the document.
5. Actions to take, as a list, each with the person responsible and the
   deadline when they are mentioned, otherwise "not specified".
6. Questions left open.

Do not add any information that is not in the transcript.

About the recording:

- File: {fichier}
- Transcription date: {date}
- Recording length: {duree}
- Speakers: {locuteurs}
- Transcription model: {modele}

Transcript:

{texte}
""",
}


TEXTES: dict[str, dict[str, str]] = {"fr": _FR, "en": _EN}


# ---------------------------------------------------------------------------
# Choix de la langue
# ---------------------------------------------------------------------------

def normaliser(code: str | None) -> str:
    """Ramène un code quelconque à « fr », « en », ou une chaîne vide."""
    texte = str(code or "").strip().lower().replace("_", "-")
    if not texte:
        return ""
    racine = texte.split("-")[0]
    return racine if racine in LANGUES else ""


def detecter_systeme() -> str:
    """
    Langue de l'interface du système : « fr » ou « en ».

    Sous Windows on interroge la langue d'interface de l'utilisateur, ce qui est
    plus fiable que la locale de formatage : un poste anglais réglé sur les
    formats français reste un poste anglais. Ailleurs, ou en cas d'échec, on lit
    les variables d'environnement habituelles. Une locale illisible donne
    l'anglais, choix documenté en tête de module.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            identifiant = int(ctypes.windll.kernel32.GetUserDefaultUILanguage() or 0)
            primaire = identifiant & 0x3FF
            if primaire == 0x0C:            # LANG_FRENCH
                return "fr"
            if primaire:
                return "en"
        except Exception:
            pass

    brut = ""
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        valeur = (os.environ.get(variable) or "").strip()
        if valeur:
            brut = valeur
            break
    if not brut:
        try:
            import locale

            brut = (locale.getlocale()[0] or "")
        except Exception:
            brut = ""
    return "fr" if str(brut).lower().startswith("fr") else LANGUE_DEFAUT


def definir(code: str | None) -> str:
    """Fixe la langue d'interface pour tout le processus. Renvoie celle retenue."""
    global _courante
    _courante = normaliser(code) or LANGUE_DEFAUT
    return _courante


def courante() -> str:
    return _courante


# ---------------------------------------------------------------------------
# Accès aux chaînes
# ---------------------------------------------------------------------------

def t(cle: str, **valeurs) -> str:
    """
    Texte de la clé, dans la langue courante, variables substituées.

    Une clé absente renvoie la clé elle-même : une chaîne oubliée doit se voir à
    l'écran, pas planter l'application. Le script de contrôle de parité est là
    pour que ce cas ne survienne pas en production.
    """
    texte = TEXTES.get(_courante, _EN).get(cle)
    if texte is None:
        texte = _EN.get(cle, _FR.get(cle, cle))
    for nom, valeur in valeurs.items():
        texte = texte.replace("{" + nom + "}", str(valeur))
    return texte


def tn(cle: str, nombre_element: int, **valeurs) -> str:
    """Pluriel simple : `cle.un` au singulier, `cle.autres` sinon. `{n}` injecté."""
    suffixe = ".un" if abs(int(nombre_element)) <= 1 else ".autres"
    return t(cle + suffixe, n=nombre_element, **valeurs)


def nombre(valeur: float, decimales: int = 1) -> str:
    """Nombre décimal au séparateur de la langue courante."""
    texte = f"{float(valeur):.{decimales}f}"
    return texte.replace(".", t("format.decimal"))


def octets(valeur: float) -> str:
    """« 3,1 Go », « 348 Mo », « 12 Ko », « 0 octet », dans la langue courante."""
    reste = float(valeur or 0)
    if reste < 1:
        return t("unite.octet")
    for cle, seuil in (("unite.go", 1024 ** 3), ("unite.mo", 1024 ** 2), ("unite.ko", 1024)):
        if reste >= seuil:
            valeur_unite = reste / seuil
            return nombre(valeur_unite, 1 if valeur_unite < 100 else 0) + " " + t(cle)
    return t("unite.octets", n=int(reste))


def liste_langues() -> list[dict]:
    """Options du sélecteur « Langue de l'interface », dans la langue courante."""
    return [{"cle": code, "nom": t("langue." + code)} for code in LANGUES]
