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
    "reco.processeur_lent": (
        "Processeur peu puissant : une heure de réunion demanderait environ {qualite} "
        "en « Qualité maximale », contre {rapide} en « Rapide ». Le banc d'essai "
        "(réglages, section Vitesse de cette machine) mesure les vrais chiffres en "
        "quelques minutes."
    ),
    "reco.openvino": (
        "Puce Intel exploitée par OpenVINO : une heure de réunion demanderait environ "
        "{qualite} en « Qualité maximale », {rapide} en « Rapide »."
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
        "{carte} détectée mais non utilisée : seul le processeur travaille sur les "
        "cartes non NVIDIA."
    ),

    # -- matériel (app/materiel.py) ----------------------------------------
    "mat.cpu_inconnu": "Processeur inconnu",
    "mat.fils": "{n} fils",
    "mat.coeurs_fils": "{coeurs} cœurs / {fils} fils",
    "mat.hybride_trois": (
        "{p} cœurs performants, {e} efficaces et {lp} basse consommation / {fils} fils"
    ),
    "mat.hybride_deux": "{p} cœurs performants et {e} efficaces / {fils} fils",
    "mat.memoire": "{go} Go de mémoire",
    "mat.gpu_accelere": "{nom} (accéléré)",
    "mat.gpu_non_accelere": "{nom} (non exploitée)",
    "mat.sans_gpu": "pas de carte graphique dédiée",
    "mat.npu_non_exploite": "{nom} (non exploité)",
    "gpu.note.cuda_active": "Accélération CUDA active.",
    "gpu.note.cuda_absente": (
        "Carte NVIDIA détectée mais les bibliothèques CUDA de CTranslate2 ne répondent "
        "pas. Relancez l'installateur pour les poser."
    ),
    "gpu.note.amd": (
        "Non exploitée : la transcription tourne sur le processeur. Le moteur sait "
        "calculer sur les cartes AMD récentes (ROCm), mais l'application ne l'embarque "
        "pas encore."
    ),
    "gpu.note.intel": (
        "Circuit graphique intégré. Le moteur OpenVINO, à installer en option "
        "(réglages, section Vitesse de cette machine), sait y transcrire ; sans lui, "
        "le processeur travaille seul."
    ),
    "gpu.note.autre": "Non exploitée.",
    "npu.note": (
        "Détecté, non exploité. Un NPU vise surtout l'autonomie sur batterie, la "
        "transcription tourne sur le processeur."
    ),
    "npu.note.intel": (
        "Exploitable à titre expérimental par le moteur OpenVINO (option). Rien n'est "
        "promis : le banc d'essai dit s'il tient sur cette machine."
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
    # -- moteur OpenVINO (app/moteur_openvino.py) ---------------------------
    "ov.peripherique.cpu": "processeur",
    "ov.peripherique.gpu": "puce graphique Intel",
    "ov.peripherique.npu": "NPU Intel",
    "ov.modele_absent.titre": "Modèle sans version OpenVINO",
    "ov.modele_absent.msg": (
        "Le modèle {modele} n'existe pas au format d'OpenVINO. Choisissez un modèle du "
        "catalogue, ou revenez au moteur habituel (réglages, Vitesse de cette machine)."
    ),
    "ov.chargement": "Chargement du modèle {modele} sur {peripherique} (OpenVINO)...",
    "ov.repli": (
        "OpenVINO n'a pas pu travailler sur {peripherique} : la transcription continue "
        "avec le moteur habituel, sur le processeur. Le détail est dans le journal."
    ),
    "ov.rejeu": "Raté sur {peripherique} : modèle rouvert, reprise à {position}.",
    "ov.rejeu_ouverture": "Ouverture sur {peripherique} réussie au second essai.",

    # -- banc d'essai (app/banc.py) --------------------------------------
    "banc.titre": "Banc d'essai {nom} {version}, {date}",
    "banc.section.materiel": "Matériel",
    "banc.processeur": "Processeur",
    "banc.topologie": "{p} cœurs performants, {e} efficaces, {lp} basse consommation, {fils} fils",
    "banc.coeurs": "{coeurs} cœurs, {fils} fils",
    "banc.fils_auto": "Fils de calcul choisis d'office : {n}",
    "banc.memoire": "Mémoire vive",
    "banc.graphique": "Graphique",
    "banc.pilote": "pilote",
    "banc.alimentation": "Alimentation",
    "banc.secteur": "sur secteur (batterie {pct} %)",
    "banc.batterie": "SUR BATTERIE ({pct} %), chiffres moins représentatifs",
    "banc.secteur_sans_batterie": "sur secteur",
    "banc.mode_alimentation": "mode {mode}",
    "banc.systeme": "Système",
    "banc.non_installe": "non installé",
    "banc.section.essais": "Essais (extrait de {duree} s, texte comparé à la référence)",
    "banc.libelle_ct2": "CTranslate2, {modele}, {fils} fils, {lots}",
    "banc.libelle_ov": "OpenVINO {peripherique}, {modele}",
    "banc.lots": "lots de {n}",
    "banc.un_a_un": "un à un",
    "banc.affinite": "cœurs basse consommation écartés",
    "banc.ligne": (
        "{reglage} : {calcul} s de calcul, facteur {facteur}, WER {wer} %, "
        "chargement {chargement} s, mémoire {memoire} Go"
    ),
    "banc.etat.erreur": "échec",
    "banc.etat.annule": "annulé",
    "banc.etat.delai": "abandonné, délai dépassé",
    "banc.etat.modele_absent": "modèle absent, non téléchargé",
    "banc.section.conseil": "Réglage conseillé",
    "banc.aucun_conseil": "aucun essai n'a abouti, pas de conseil possible.",
    "banc.conseil_openvino": "moteur OpenVINO sur {peripherique}",
    "banc.conseil_ct2": "moteur CTranslate2, {fils} fils, lots de {lot} (0 = un à un)",
    "banc.pour_une_heure": "{preset} : environ {duree} pour une heure d'audio (facteur {facteur})",
    "banc.derive": "premier essai refait à la fin : écart de {ecart} % (chauffe ou charge de la machine)",
    "banc.duree_totale": "Durée du banc : {duree}.",
    "banc.remarque": (
        "Ce rapport ne contient ni nom d'utilisateur, ni nom de machine, ni chemin. "
        "Le facteur est la durée de calcul divisée par la durée de l'audio."
    ),
    "banc.extrait_absent.titre": "Extrait du banc introuvable",
    "banc.extrait_absent.msg": (
        "L'extrait audio du banc d'essai manque à l'installation. Réinstallez "
        "l'application."
    ),
    "banc.etape.telechargement": "Téléchargement du modèle {modele} ({taille})...",
    "banc.etape.telechargement_echoue": "Modèle {modele} non téléchargé : {detail}",
    "banc.etape.essai": "Essai {numero} sur {total} environ : {reglage}",
    "banc.etape.fini": "Banc terminé.",
    "banc.cli.fichier": "Rapport enregistré : {fichier}",
    "banc.cli.applique": "Réglage conseillé appliqué.",
    "banc.cli.appliquer": (
        "Pour appliquer le réglage conseillé : bouton « Appliquer » dans les réglages, "
        "ou relancer avec --appliquer."
    ),

    # -- comparaison des moteurs (app/comparaison.py) ---------------------
    "comp.moteur.ct2": "CTranslate2 (moteur actuel)",
    "comp.moteur.openvino": "OpenVINO ({peripherique})",
    "comp.oui": "oui",
    "comp.non": "non",
    "comp.un_a_un": "un à un",
    "comp.openvino_absent.titre": "OpenVINO n'est pas installé",
    "comp.openvino_absent.msg": (
        "La comparaison a besoin des deux moteurs. Installez OpenVINO depuis les "
        "réglages (Vitesse de cette machine) ou avec --installer-openvino, puis relancez."
    ),
    "comp.etape.telechargement": "Téléchargement du modèle {modele} ({taille})...",
    "comp.etape.decodage": "Lecture de l'extrait...",
    "comp.etape.moteur": "Transcription par {moteur} ({duree} d'audio)...",
    "comp.etape.analyse": "Comparaison des deux textes...",
    "comp.etape.fini": "Comparaison terminée.",
    "comp.cli.usage": (
        "Usage : --comparer FICHIER [--debut 00:05:00] [--duree 600] [--reference TRANSCRIPTION] "
        "[--sortie DOSSIER] [--peripherique GPU|CPU|NPU] [--preset qualite|rapide] "
        "[--faisceau-openvino N] [--faisceau-ctranslate2 N] [--glossaire FICHIER] [--sans-glossaire] "
        "[--sans-corrections] "
        "[--ouvrir]"
    ),
    "comp.cli.fichiers": (
        "Rapport de chiffres (transmissible) : {rapport}\n"
        "Page côte à côte (contient le texte, reste sur ce poste) : {page}"
    ),
    "comp.page.titre": "Comparaison des moteurs",
    "comp.page.reference": "Référence relue",
    "comp.page.confidentiel": "contient la transcription : ce fichier reste sur ce poste.",
    "comp.page.seulement": "Seulement les lignes qui diffèrent",
    "comp.page.legende": (
        "Surligné : les deux moteurs divergent. Pointillé : mot incertain pour CTranslate2 "
        "(survoler pour la probabilité). Cliquer sur une heure réécoute le passage."
    ),
    "comp.page.legende_ref": "Ondulé rouge : mot d'un moteur qui diffère de la référence ; dans la colonne de référence, mot manqué par les deux moteurs.",
    "comp.rapport.titre": "Comparaison des moteurs, {nom} {version}, {date}",
    "comp.rapport.section.extrait": "Extrait",
    "comp.rapport.extrait": "{duree} min d'audio, à partir de {debut} (bords ramenés sur des pauses)",
    "comp.rapport.reglages": (
        "langue {langue}, preset {preset}, glossaire {glossaire}, corrections {corrections}"
    ),
    "comp.rapport.machine": "{processeur}, {memoire} Go, {alimentation}",
    "comp.rapport.section.vitesse": "Vitesse",
    "comp.rapport.echec": "{moteur} : échec ({etat}) {detail}",
    "comp.rapport.vitesse": (
        "{moteur}, {modele} : {calcul} s de calcul (facteur {facteur}), chargement {chargement} s, "
        "mémoire {memoire} Go"
    ),
    "comp.rapport.detail_ct2": "faisceau {faisceau}, lots {lots}, {fils} fils, calcul {type_calcul}",
    "comp.rapport.detail_ov": (
        "faisceau {faisceau}, calcul {type_calcul}, fenêtres de 30 s décodées en deux passes (la seconde sans glossaire) : {plafond}"
    ),
    "comp.rapport.amorce": (
        "glossaire : {termes} termes dans l'amorce ({jetons} jetons), {remplacements} corrections appliquées"
    ),
    "comp.rapport.rapport_vitesse": "OpenVINO calcule {rapport} fois plus vite que CTranslate2 sur cet extrait",
    "comp.rapport.section.accord": "Accord entre les deux moteurs",
    "comp.rapport.mots": "mots (après normalisation) : CTranslate2 {a}, OpenVINO {b}",
    "comp.rapport.desaccord": (
        "désaccord : {a} % rapporté au texte de CTranslate2, {b} % rapporté à celui d'OpenVINO "
        "({sub} mots remplacés, {sup} absents chez OpenVINO, {ins} en plus chez OpenVINO)"
    ),
    "comp.rapport.passages": "{n} passages où les textes diffèrent",
    "comp.rapport.repartition": (
        "un seul mot : {un} ; plusieurs mots : {plusieurs} ; passage d'au moins {mots} mots "
        "présent seulement chez CTranslate2 : {seul_a}, seulement chez OpenVINO : {seul_b}"
    ),
    "comp.rapport.horodatage": (
        "horodatage : {n} mots identiques sur {egaux} placés à plus de {seuil} s l'un de l'autre, "
        "en {zones} zones"
    ),
    "comp.rapport.segments": (
        "segments (base de la séparation des locuteurs) : CTranslate2 {na}, médiane {ma} s, "
        "le plus long {xa} s ; OpenVINO {nb}, médiane {mb} s, le plus long {xb} s"
    ),
    "comp.rapport.glossaire": (
        "glossaire ({total} termes) : CTranslate2 en retrouve {ta} ({oa} occurrences), "
        "OpenVINO {tb} ({ob} occurrences)"
    ),
    "comp.rapport.anglais": (
        "mots anglais courants écrits en anglais (liste de {liste} mots) : CTranslate2 {a}, OpenVINO {b}"
    ),
    "comp.rapport.incertains": (
        "CTranslate2 signale {n} mots incertains (probabilité sous {seuil}) ; {div} tombent dans un "
        "passage où les moteurs divergent, soit {pct} %, contre {base} % de l'ensemble de ses mots"
    ),
    "comp.rapport.confiance_ov": "OpenVINO ne donne pas la probabilité des mots : pas de décompte de son côté.",
    "comp.rapport.section.reference": "Référence relue",
    "comp.rapport.sans_reference": (
        "aucune : les chiffres ci-dessus disent où les moteurs divergent, pas lequel a raison."
    ),
    "comp.rapport.ref_fenetre": (
        "{couvert} min de référence sur {duree} min d'extrait, {mots} mots (format {format})"
    ),
    "comp.rapport.ref_wer": (
        "{moteur} : taux d'erreur {wer} % ({sub} remplacés, {sup} manquants, {ins} en trop)"
    ),
    "comp.rapport.ref_glossaire": "termes du glossaire de la référence retrouvés : {retrouves} sur {attendus}",
    "comp.rapport.ref_anglais": "mots anglais courants : {n} (référence : {ref})",
    "comp.rapport.ref_biais": (
        "Attention : une référence produite par Scribouille (moteur CTranslate2) puis peu corrigée "
        "favorise CTranslate2, dont elle garde les tournures et les erreurs non relues."
    ),
    "comp.ref.vide": "référence vide ou illisible : pas de taux d'erreur.",
    "comp.ref.illisible": "référence illisible : pas de taux d'erreur.",
    "comp.ref.sans_horodatage": (
        "la référence n'a pas d'horodatage : on ne peut pas savoir quelle partie correspond à "
        "l'extrait. Comparaison à la référence possible seulement sur le fichier entier "
        "(sans --debut ni --duree)."
    ),
    "comp.ref.hors_extrait": (
        "aucune réplique de la référence ne tombe entièrement dans l'extrait : vérifier "
        "--debut et --duree, ou les horodatages de la référence."
    ),
    "comp.rapport.lecture": (
        "Lecture : le désaccord n'est pas une erreur de l'un ou de l'autre, il montre où "
        "réécouter. Normalisation : minuscules, sans ponctuation, nombres en lettres, élisions "
        "séparées, hésitations retirées."
    ),
    "comp.rapport.remarque": (
        "Ce rapport ne contient aucun mot de la transcription, ni nom d'utilisateur, ni nom "
        "de machine, ni chemin."
    ),

    "moteur.hors_ligne": (
        "Sans accès à Hugging Face (réseau filtré), une voie hors ligne existe : sur "
        "un poste où Scribouille a déjà téléchargé ce modèle, copiez le dossier "
        "« {dossier_cache} » de son dossier des modèles, puis collez-le tel quel dans "
        "{dossier}. Il sera reconnu sans aucun appel réseau. Dépôt d'origine : "
        "https://huggingface.co/{depot}"
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
        "pyannote/speaker-diarization-community-1 et acceptez ses conditions "
        "d'utilisation (licence CC-BY-4.0 ; le formulaire demande une organisation et "
        "un usage, et pyannote peut vous écrire de temps en temps)."
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
    "ext.lot.openvino": "le moteur OpenVINO",
    "ov.installe": "Moteur OpenVINO installé. Lancez le banc d'essai pour savoir s'il va plus vite ici.",
    "ov.installation_echec": (
        "L'installation d'OpenVINO a échoué : le réseau bloque peut-être PyPI. Voie hors "
        "ligne : sur un poste qui y a accès, lancez « pip download --no-deps "
        "openvino==2026.4.1 openvino-tokenizers==2026.4.1.0 openvino-genai==2026.4.1.0 "
        "--python-version 3.12 --only-binary=:all: --platform win_amd64 -d roues », puis "
        "copiez les trois fichiers .whl dans {dossier} et relancez l'installation."
    ),
    "ov.retrait_sources": (
        "Depuis les sources, OpenVINO vit dans l'environnement « .venv » : retirez-le avec "
        "pip uninstall openvino-genai openvino-tokenizers openvino."
    ),
    "ov.retrait_echec": (
        "Le dossier d'OpenVINO n'a pas pu être effacé, sans doute parce qu'il sert encore. "
        "Fermez Scribouille, rouvrez-le, puis recommencez."
    ),
    "app.banc.en_cours": "Un banc d'essai ou une comparaison des moteurs tourne : attendez sa fin ou arrêtez-le.",
    "app.banc.file_occupee": "Une transcription est en cours : le banc attendra qu'elle soit finie.",
    "vitesse.automatique": "réglage automatique ({fils} fils de calcul, moteur habituel)",
    "vitesse.reglage_ov": "moteur OpenVINO sur {peripherique}",
    "vitesse.reglage_ct2": "moteur habituel, {fils} fils, {lots}",
    "vitesse.aucun_conseil": "Aucun conseil à appliquer : lancez d'abord le banc d'essai.",
    "vitesse.applique": "Réglage appliqué : {reglage}.",
    "vitesse.retour_auto": "Retour au réglage automatique.",
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
    "app.comp.dialogue_reference": "Transcriptions (*.txt;*.srt;*.vtt;*.json)",
    "app.comp.fichier_absent": "Choisissez d'abord l'enregistrement à comparer.",
    "app.comp.debut_illisible": "Début illisible : écrivez-le sous la forme 00:05:00.",
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
    "app.arret": (
        "Arrêt demandé : la transcription s'interrompt à la fin du lot de passages en "
        "cours, ce qui peut prendre plus d'une minute sur processeur. Avec la "
        "sauvegarde progressive, le texte déjà produit est conservé."
    ),
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
    # -- Campagne de mesure (app/campagne.py) ----------------------------------
    "camp.libelle_ov": "OpenVINO {peripherique}, {modele}, faisceau {faisceau}",
    "camp.libelle_ct2": "CTranslate2 processeur, {modele}, faisceau {faisceau}",
    "camp.rapport.titre": "Campagne de mesure des réglages, {nom} {version}, {date}",
    "camp.rapport.machine": "Machine : {processeur}, {memoire} Go, {alimentation}",
    "camp.rapport.openvino": "OpenVINO {version}, périphériques vus : {peripheriques}",
    "camp.rapport.vitesse": (
        "vitesse : {facteur} fois la durée de l'audio (une heure de réunion : {heure}), "
        "chargement {chargement} s, mémoire {memoire} Go ; passé de {debut} à {fin}"
    ),
    "camp.rapport.section.corpus": "Corpus public avec référence",
    "camp.rapport.corpus": (
        "{extraits} extraits de {reunions} réunions, {minutes} min d'audio, {mots} mots de "
        "référence, dont {chev} % prononcés pendant qu'une autre personne parle ; "
        "{anglais} mots anglais courants"
    ),
    "camp.rapport.armes_egales": (
        "à armes égales : mêmes extraits, même normalisation (minuscules, ponctuation et "
        "hésitations retirées, nombres en lettres), glossaire et corrections éteints, langue fr"
    ),
    "camp.rapport.source": "source : {attribution}",
    "camp.rapport.section.reglages": "Réglages mesurés",
    "camp.rapport.preset_actuel": "(réglage actuel « {preset} »)",
    "camp.rapport.echec": "échec ({etat}) {detail}",
    "camp.rapport.non_pris_en_charge": (
        "non pris en charge sur ce périphérique (OpenVINO ne décode pas en faisceau sur la "
        "puce graphique ni sur le NPU), pas compté comme une panne"
    ),
    "camp.rapport.wer": (
        "taux d'erreur de mots : {wer} % (intervalle à 95 % : {bas} à {haut}) ; "
        "{sub} substitutions, {sup} omissions, {ins} insertions sur {mots} mots"
    ),
    "camp.rapport.chevauchement": (
        "mots de la référence perdus : {chev} % quand deux personnes parlent en même temps, "
        "{hors} % sinon"
    ),
    "camp.rapport.inventions": (
        "insertions longues ({seuil} mots ou plus absents de la référence) : {n}, {mots} mots ; "
        "segments de plus de {duree} s : {longs} % de {segments}"
    ),
    "camp.rapport.temoin": "témoin de parole lue (FLEURS, 44 s) : {wer} % d'erreur",
    "camp.rapport.section.verdict": "Verdict",
    "camp.rapport.regle": (
        "règle : écarter tout réglage plus lent que la réunion ; garder ceux dont le taux "
        "d'erreur ne se distingue pas du meilleur (moins de {ecart} point d'écart, ou écart "
        "apparié dont l'intervalle à 95 % contient zéro et qui reste sous {plafond} points) ; "
        "parmi eux, le plus rapide"
    ),
    "camp.rapport.aucun_verdict": "aucun réglage n'a abouti : pas de verdict.",
    "camp.rapport.retenu": "réglage retenu : {code}, {reglage}",
    "camp.rapport.motif.equivalent_plus_rapide": (
        "le plus rapide des réglages aussi justes que le meilleur ({meilleur})"
    ),
    "camp.rapport.motif.plus_juste_admissible": (
        "aucun réglage assez rapide n'égale le meilleur ({meilleur}) : le plus juste des "
        "réglages plus rapides que la réunion"
    ),
    "camp.rapport.equivalent": "équivalent",
    "camp.rapport.distinct": "moins juste",
    "camp.rapport.trop_lent": "plus lent que la réunion",
    "camp.rapport.ecart": (
        "{code} : {ecart} points d'écart au meilleur (intervalle apparié {bas} à {haut}), {etat}"
    ),
    "camp.rapport.contre_qualite": (
        "par rapport au preset « Qualité maximale » actuel : {ecart} points de taux d'erreur, "
        "{rapport} fois plus rapide"
    ),
    "camp.rapport.cout_ov": (
        "ce qu'il coûte : OpenVINO ne donne pas la probabilité des mots, la vue de relecture "
        "ne souligne donc aucun mot douteux ; segments plus courts ; en cas de panne de la "
        "puce graphique, l'application repasse d'elle-même sur CTranslate2"
    ),
    "camp.rapport.cout_ct2": (
        "ce qu'il coûte : calcul sur le processeur seul, la puce graphique reste inutilisée ; "
        "les mots incertains restent soulignés dans la vue de relecture"
    ),
    "camp.rapport.pour_une_heure": "durée attendue pour une heure de réunion : {duree}",
    "camp.rapport.section.doutes": "Mots douteux",
    "camp.rapport.doute_ct2": (
        "{code}, probabilité sous {seuil} : {part} % des mots signalés, qui couvrent {rappel} % "
        "des mots faux ; {precision} % des mots signalés sont faux"
    ),
    "camp.rapport.doute_seconde": (
        "{code} contrôlé par une seconde passe {second} (mots écrits autrement) : {part} % des "
        "mots signalés, qui couvrent {rappel} % des mots faux ; {precision} % des mots signalés "
        "sont faux ; coût : {cout} % de calcul en plus"
    ),
    "camp.rapport.doute_aucun": "pas assez de réglages réussis pour mesurer un signalement.",
    "camp.rapport.section.glossaire": "Glossaire",
    "camp.rapport.glossaire_public": "corpus public : glossaire éteint pour tous les réglages",
    "camp.rapport.glossaire_poste": (
        "glossaire de ce poste : {termes} termes chargés, dont {exemples} exemples livrés "
        "actifs par les anciennes versions (noms fictifs)"
    ),
    "camp.rapport.glossaire_exemples": (
        "le glossaire de ce poste n'est que l'exemple d'origine : aucun de ses termes ne peut "
        "être retrouvé dans une vraie réunion. Remplacer son contenu par les noms propres et "
        "sigles de l'équipe (Réglages, Glossaire)."
    ),
    "camp.rapport.duree": "Durée de la campagne : {duree}",
    "camp.rapport.appliquer": (
        "Pour appliquer ce verdict, dans le dossier du programme : "
        "scribouille-verifier.exe --campagne --appliquer (rien n'est recalculé)"
    ),
    "camp.rapport.remarque": (
        "Ce rapport ne contient que des nombres : aucun mot transcrit, aucun nom, aucun chemin."
    ),
    "camp.etape.deja": "{code} : déjà mesuré, repris tel quel",
    "camp.etape.non_pris_en_charge": "{code} : non pris en charge sur {peripherique}, passé",
    "camp.etape.reglage": "Réglage {numero} sur {total} : {reglage} ({code})",
    "camp.etape.progres": "{code} : extrait {n} sur {total}",
    "camp.etape.modele": "Téléchargement du modèle {modele}",
    "camp.etape.corpus": "Préparation du corpus public (au plus {mo} Mo à télécharger sans paquet préparé)",
    "camp.etape.paquet": "Corpus pris dans le paquet préparé",
    "camp.etape.reseau": "Corpus : extrait {rang} téléchargé et mélangé",
    "camp.corpus_absent.titre": "Corpus public indisponible",
    "camp.corpus_absent.msg": (
        "Le corpus n'a pu être ni lu dans un paquet préparé ({paquet}), ni téléchargé. "
        "Déposez le paquet à côté du programme ou désignez-le avec --corpus. Détail : {detail}"
    ),
    "camp.reglage_inconnu.titre": "Réglage inconnu",
    "camp.reglage_inconnu.msg": "Réglage inconnu : {cles}. Réglages possibles : {connues}.",
    "camp.reunion.titre": "Campagne, réunion réelle (sans référence), {nom} {version}, {date}",
    "camp.reunion.extrait": "Extrait : {minutes} min (bords ramenés sur des pauses)",
    "camp.reunion.ancre": "Réglage de comparaison : {code} ({source})",
    "camp.reunion.ancre.verdict": "retenu par la campagne publique",
    "camp.reunion.ancre.qualite": "preset « Qualité maximale », pas de verdict public",
    "camp.reunion.ancre.verdict_echec": (
        "preset « Qualité maximale » : le réglage retenu par la campagne publique, {retenu}, "
        "a échoué sur cette réunion"
    ),
    "camp.reunion.ancre.premier": "premier réglage réussi",
    "camp.reunion.glossaire": (
        "Glossaire et corrections du poste appliqués : {termes} termes chargés, dont "
        "{exemples} exemples livrés actifs par les anciennes versions"
    ),
    "camp.reunion.accord": (
        "désaccord avec {ancre} : {desaccord} % ({mots} mots contre {mots_ancre}) ; passages "
        "d'au moins {mots_seg} mots en plus : {en_plus}, en moins : {en_moins}"
    ),
    "camp.reunion.segments": (
        "segments : {n}, durée médiane {mediane} s, plus de {duree} s : {longs} %"
    ),
    "camp.reunion.termes": "termes du glossaire retrouvés : {trouves} sur {termes}",
    "camp.reunion.remarque": (
        "Sans référence, un désaccord dit où les réglages divergent, pas lequel a raison. "
        "Ce rapport ne contient que des nombres : aucun mot transcrit, aucun nom, aucun chemin."
    ),
    "camp.cli.usage": (
        "Usage : --campagne [--appliquer] [--recommencer] [--reglages CLE,CLE] "
        "[--limite-extraits N] [--corpus PAQUET.zip] [--peripherique GPU|CPU] [--telecharger]\n"
        "        --campagne --reunion FICHIER [--debut 00:05:00] [--duree 600] [--reglages CLE,CLE]"
    ),
    "camp.cli.fichier": "Rapport : {fichier}",
    "camp.cli.applique": "Réglage {code} appliqué : il sert dès la prochaine transcription.",
    "camp.cli.rien_a_appliquer": "Aucun verdict : rien n'est appliqué.",

    # Épreuve d'endurance (app/endurance.py)
    "end.rapport.titre": "{nom} {version} : épreuve d'endurance ({date})",
    "end.rapport.reglage": "Réglage éprouvé : {code} ({reglage})",
    "end.rapport.plan": (
        "Passages : {n}, de {minutes} min en moyenne, pris dans le corpus public (SUMM-RE ASRU) ; "
        "un seul processus, pipeline ouvert puis libéré à chaque passage, comme dans l'application"
    ),
    "end.rapport.plan_pression": (
        "Pression mémoire, un passage sur deux : CTranslate2 large-v3 chargé et passé sur {secondes} s "
        "(réglages « Qualité maximale »), puis mémoire libre ramenée vers {cible} Go ; le tout reste en "
        "place pendant l'ouverture et le passage d'OpenVINO"
    ),
    "end.rapport.section.resultat": "Résultat",
    "end.rapport.panne_avant": (
        "Passages avec au moins une erreur du moteur (avant rejeu) : {k} sur {n} ({pct} %, "
        "borne haute à 95 % : {borne} %)"
    ),
    "end.rapport.panne_apres": (
        "Passages que le rejeu n'a pas sauvés (repli sur CTranslate2 ou échec) : {k} sur {n} ({pct} %, "
        "borne haute à 95 % : {borne} %)"
    ),
    "end.rapport.issues": (
        "Rejeux réussis : {rejeux} ; replis sur CTranslate2 : {replis} ; échecs non rattrapés : {erreurs} ; "
        "processus tombés ou bloqués : {plantages}"
    ),
    "end.rapport.pression_ratee": "Passages sans mesure, la mise sous pression ayant échoué : {n}",
    "end.rapport.repetitions": (
        "Fenêtres qui bouclaient : {fenetres}, refaites {reprises} fois ; reprises en échec : {echecs}"
    ),
    "end.rapport.vitesse": (
        "Vitesse : facteur médian {mediane} (de {min} à {max}) ; ouverture du modèle : médiane {ouv} s, "
        "au plus {ouv_max} s"
    ),
    "end.rapport.memoire": (
        "Mémoire libre du poste avant l'ouverture : au plus bas {min} Go, médiane {med} Go ; "
        "avant le passage : au plus bas {min2} Go"
    ),
    "end.rapport.par_mode": (
        "{mode} : passages {n}, avec erreur {k}, non sauvés {perdus} ; mémoire libre avant "
        "l'ouverture : médiane {med} Go, au plus bas {min} Go"
    ),
    "end.mode.normal": "normal",
    "end.mode.pression": "sous pression",
    "end.mode.diagnostic": "diagnostic",
    "end.rapport.section.erreurs": "Erreurs relevées, texte exact",
    "end.rapport.aucune_erreur": "aucune",
    "end.rapport.erreur": "{id} ({phase}, {issue}) : {erreur}",
    "end.phase.ouverture": "ouverture du pipeline",
    "end.phase.transcription": "transcription",
    "end.phase.garde": "reprise d'une fenêtre qui bouclait",
    "end.phase.passage": "passage",
    "end.issue.rejeu": "rejoué",
    "end.issue.rejeu_reussi": "rejeu réussi",
    "end.issue.repli": "repli sur CTranslate2",
    "end.issue.premiere_version_gardee": "première version gardée",
    "end.rapport.section.diagnostic": "Diagnostic de l'échec du 12/11",
    "end.rapport.diag_journal_aucun": "Journal du processus tombé : introuvable (purgé ou effacé).",
    "end.rapport.diag_journal": (
        "Journal {date} : erreur levée dans moteur_openvino.py, ligne {lignes} ({lieu}) ; "
        "fenêtre qui bouclait juste avant : {repetitive} ; pipeline ouvert : {ouvert} ; "
        "fenêtres prévues : {fenetres}"
    ),
    "end.lieu.glouton": "décodage glouton d'une fenêtre",
    "end.lieu.garde_faisceau": "garde-fou des répétitions, faisceau de 5",
    "end.lieu.ouverture": "ouverture du pipeline",
    "end.lieu.inconnu": "autre endroit",
    "end.oui": "oui",
    "end.non": "non",
    "end.rapport.diag_ancien": (
        "Réunion {reunion}, ancien garde-fou (faisceau de 5) : {etat} ; fenêtres qui bouclaient : {fenetres} ; "
        "reprises en échec : {echecs} ; facteur {facteur}"
    ),
    "end.rapport.diag_nouveau": (
        "Réunion {reunion}, nouveau garde-fou (température) : {etat} ; fenêtres qui bouclaient : {fenetres} ; "
        "reprises en échec : {echecs} ; facteur {facteur}"
    ),
    "end.rapport.diag_conclusion_oui": (
        "L'ancien garde-fou reproduit l'erreur du 12/11 sur cette réunion et le nouveau la passe : "
        "cause confirmée."
    ),
    "end.rapport.diag_conclusion_non": (
        "L'ancien garde-fou ne reproduit pas l'erreur sur cette réunion, ou le nouveau ne la passe "
        "pas : cause non confirmée."
    ),
    "end.rapport.section.detail": "Détail par passage",
    "end.rapport.ligne": (
        "{id} {mode} : {etat} ; libre {libre_ouv} Go avant l'ouverture, {libre_pass} Go avant le passage ; "
        "ouverture {ouv} s ; facteur {facteur} ; fenêtres qui bouclaient {boucles}"
    ),
    "end.etat.ok": "réussi",
    "end.etat.rejeu_reussi": "réussi après rejeu",
    "end.etat.repli": "repli sur CTranslate2",
    "end.etat.erreur": "échec",
    "end.etat.plantage": "processus tombé",
    "end.etat.bloque": "bloqué, arrêté",
    "end.etat.pression_ratee": "mise sous pression impossible",
    "end.rapport.remarque": "Rapport de chiffres : aucun mot transcrit, aucun nom, aucun chemin.",
    "end.rapport.duree": "Durée de l'épreuve : {duree}",
    "end.refuse.titre": "Épreuve d'endurance impossible",
    "end.refuse.absent": "Le réglage {code} demande OpenVINO, qui n'est pas installé sur ce poste.",
    "end.refuse.faisceau": "Le réglage {code} n'est pas pris en charge sur {peripherique} (faisceau).",
    "end.refuse.modele": (
        "Un modèle manque pour le réglage {code} (ou pour la pression mémoire, CTranslate2 large-v3) : "
        "lancer d'abord la campagne, qui les télécharge."
    ),
    "end.etape.plan": "{code} : {n} passages prévus, {faits} déjà faits",
    "end.etape.passage": "{id} ({n} sur {total}) : {etat}, facteur {facteur}, ouverture {ouv} s, {libre} Go libres",
    "end.etape.relance": "nouveau processus pour les {n} passages restants",
    "end.etape.abandon": "le processus s'arrête sans rien faire ({issue}) : épreuve arrêtée",
    "end.erreur.bloque": "aucun signe de vie pendant {s} s, processus arrêté",
    "end.erreur.plantage": "processus terminé sans résultat (code {code})",
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
    "reco.processeur_lent": (
        "Low-power processor: one hour of meeting would take about {qualite} with "
        "\"Highest quality\", against {rapide} with \"Fast\". The benchmark (settings, "
        "Speed of this machine section) measures the real figures in a few minutes."
    ),
    "reco.openvino": (
        "Intel chip used through OpenVINO: one hour of meeting would take about "
        "{qualite} with \"Highest quality\", {rapide} with \"Fast\"."
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
        "{carte} detected but not used: only the CPU works on non NVIDIA cards."
    ),

    "mat.cpu_inconnu": "Unknown processor",
    "mat.fils": "{n} threads",
    "mat.coeurs_fils": "{coeurs} cores / {fils} threads",
    "mat.hybride_trois": (
        "{p} performance, {e} efficient and {lp} low-power cores / {fils} threads"
    ),
    "mat.hybride_deux": "{p} performance and {e} efficient cores / {fils} threads",
    "mat.memoire": "{go} GB of memory",
    "mat.gpu_accelere": "{nom} (accelerated)",
    "mat.gpu_non_accelere": "{nom} (not used)",
    "mat.sans_gpu": "no dedicated graphics card",
    "mat.npu_non_exploite": "{nom} (not used)",
    "gpu.note.cuda_active": "CUDA acceleration active.",
    "gpu.note.cuda_absente": (
        "NVIDIA card detected, but the CUDA libraries used by CTranslate2 are not "
        "answering. Run the installer again to put them in place."
    ),
    "gpu.note.amd": (
        "Not used: transcription runs on the CPU. The engine can compute on recent AMD "
        "cards (ROCm), but the application does not ship it yet."
    ),
    "gpu.note.intel": (
        "Integrated graphics. The OpenVINO engine, an optional install (settings, Speed "
        "of this machine section), can transcribe on it; without it, the CPU works alone."
    ),
    "gpu.note.autre": "Not used.",
    "npu.note": (
        "Detected, not used. An NPU mainly targets battery life; transcription runs "
        "on the CPU."
    ),
    "npu.note.intel": (
        "Usable on an experimental basis by the OpenVINO engine (option). Nothing is "
        "promised: the benchmark tells whether it holds up on this machine."
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
    # -- OpenVINO engine (app/moteur_openvino.py) ---------------------------
    "ov.peripherique.cpu": "CPU",
    "ov.peripherique.gpu": "Intel graphics",
    "ov.peripherique.npu": "Intel NPU",
    "ov.modele_absent.titre": "Model without an OpenVINO version",
    "ov.modele_absent.msg": (
        "Model {modele} does not exist in OpenVINO format. Pick a model from the "
        "catalogue, or go back to the usual engine (settings, Speed of this machine)."
    ),
    "ov.chargement": "Loading model {modele} on {peripherique} (OpenVINO)...",
    "ov.repli": (
        "OpenVINO could not run on {peripherique}: transcription carries on with the "
        "usual engine, on the CPU. Details are in the log."
    ),
    "ov.rejeu": "Glitch on {peripherique}: model reopened, resuming at {position}.",
    "ov.rejeu_ouverture": "Opening on {peripherique} succeeded on the second try.",

    # -- benchmark (app/banc.py) -------------------------------------------
    "banc.titre": "{nom} {version} benchmark, {date}",
    "banc.section.materiel": "Hardware",
    "banc.processeur": "Processor",
    "banc.topologie": "{p} performance, {e} efficient, {lp} low-power cores, {fils} threads",
    "banc.coeurs": "{coeurs} cores, {fils} threads",
    "banc.fils_auto": "Compute threads chosen by default: {n}",
    "banc.memoire": "Memory",
    "banc.graphique": "Graphics",
    "banc.pilote": "driver",
    "banc.alimentation": "Power",
    "banc.secteur": "plugged in (battery {pct}%)",
    "banc.batterie": "ON BATTERY ({pct}%), figures less representative",
    "banc.secteur_sans_batterie": "plugged in",
    "banc.mode_alimentation": "{mode} plan",
    "banc.systeme": "System",
    "banc.non_installe": "not installed",
    "banc.section.essais": "Runs ({duree} s clip, text compared with the reference)",
    "banc.libelle_ct2": "CTranslate2, {modele}, {fils} threads, {lots}",
    "banc.libelle_ov": "OpenVINO {peripherique}, {modele}",
    "banc.lots": "batches of {n}",
    "banc.un_a_un": "one by one",
    "banc.affinite": "low-power cores left out",
    "banc.ligne": (
        "{reglage}: {calcul} s of compute, factor {facteur}, WER {wer}%, "
        "loading {chargement} s, memory {memoire} GB"
    ),
    "banc.etat.erreur": "failed",
    "banc.etat.annule": "cancelled",
    "banc.etat.delai": "given up, time limit exceeded",
    "banc.etat.modele_absent": "model missing, not downloaded",
    "banc.section.conseil": "Recommended setting",
    "banc.aucun_conseil": "no run succeeded, no recommendation possible.",
    "banc.conseil_openvino": "OpenVINO engine on {peripherique}",
    "banc.conseil_ct2": "CTranslate2 engine, {fils} threads, batches of {lot} (0 = one by one)",
    "banc.pour_une_heure": "{preset}: about {duree} for one hour of audio (factor {facteur})",
    "banc.derive": "first run repeated at the end: {ecart}% difference (heat or machine load)",
    "banc.duree_totale": "Benchmark duration: {duree}.",
    "banc.remarque": (
        "This report contains no user name, machine name or path. The factor is the "
        "compute time divided by the audio duration."
    ),
    "banc.extrait_absent.titre": "Benchmark clip not found",
    "banc.extrait_absent.msg": (
        "The benchmark audio clip is missing from the installation. Reinstall the "
        "application."
    ),
    "banc.etape.telechargement": "Downloading model {modele} ({taille})...",
    "banc.etape.telechargement_echoue": "Model {modele} not downloaded: {detail}",
    "banc.etape.essai": "Run {numero} of about {total}: {reglage}",
    "banc.etape.fini": "Benchmark finished.",
    "banc.cli.fichier": "Report saved: {fichier}",
    "banc.cli.applique": "Recommended setting applied.",
    "banc.cli.appliquer": (
        "To apply the recommended setting: \"Apply\" button in the settings, or run "
        "again with --appliquer."
    ),

    # -- engine comparison (app/comparaison.py) ---------------------------
    "comp.moteur.ct2": "CTranslate2 (current engine)",
    "comp.moteur.openvino": "OpenVINO ({peripherique})",
    "comp.oui": "yes",
    "comp.non": "no",
    "comp.un_a_un": "one by one",
    "comp.openvino_absent.titre": "OpenVINO is not installed",
    "comp.openvino_absent.msg": (
        "The comparison needs both engines. Install OpenVINO from the settings (Speed of "
        "this computer) or with --installer-openvino, then run it again."
    ),
    "comp.etape.telechargement": "Downloading the {modele} model ({taille})...",
    "comp.etape.decodage": "Reading the excerpt...",
    "comp.etape.moteur": "Transcribing with {moteur} ({duree} of audio)...",
    "comp.etape.analyse": "Comparing both texts...",
    "comp.etape.fini": "Comparison finished.",
    "comp.cli.usage": (
        "Usage: --comparer FILE [--debut 00:05:00] [--duree 600] [--reference TRANSCRIPT] "
        "[--sortie FOLDER] [--peripherique GPU|CPU|NPU] [--preset qualite|rapide] "
        "[--faisceau-openvino N] [--faisceau-ctranslate2 N] [--glossaire FILE] [--sans-glossaire] "
        "[--sans-corrections] "
        "[--ouvrir]"
    ),
    "comp.cli.fichiers": (
        "Figures report (shareable): {rapport}\n"
        "Side-by-side page (contains the text, stays on this computer): {page}"
    ),
    "comp.page.titre": "Engine comparison",
    "comp.page.reference": "Reviewed reference",
    "comp.page.confidentiel": "contains the transcript: this file stays on this computer.",
    "comp.page.seulement": "Only lines that differ",
    "comp.page.legende": (
        "Highlighted: the engines disagree. Dotted: word CTranslate2 is unsure of (hover for "
        "the probability). Clicking a time plays the passage again."
    ),
    "comp.page.legende_ref": "Red wavy line: an engine word that differs from the reference; in the reference column, a word both engines missed.",
    "comp.rapport.titre": "Engine comparison, {nom} {version}, {date}",
    "comp.rapport.section.extrait": "Excerpt",
    "comp.rapport.extrait": "{duree} min of audio, starting at {debut} (edges moved to pauses)",
    "comp.rapport.reglages": (
        "language {langue}, preset {preset}, glossary {glossaire}, corrections {corrections}"
    ),
    "comp.rapport.machine": "{processeur}, {memoire} GB, {alimentation}",
    "comp.rapport.section.vitesse": "Speed",
    "comp.rapport.echec": "{moteur}: failed ({etat}) {detail}",
    "comp.rapport.vitesse": (
        "{moteur}, {modele}: {calcul} s of computing (factor {facteur}), loading {chargement} s, "
        "memory {memoire} GB"
    ),
    "comp.rapport.detail_ct2": "beam {faisceau}, batches {lots}, {fils} threads, compute {type_calcul}",
    "comp.rapport.detail_ov": (
        "beam {faisceau}, compute {type_calcul}, 30 s windows decoded in two passes (the second without glossary): {plafond}"
    ),
    "comp.rapport.amorce": (
        "glossary: {termes} terms in the prompt ({jetons} tokens), {remplacements} corrections applied"
    ),
    "comp.rapport.rapport_vitesse": "OpenVINO computes {rapport} times faster than CTranslate2 on this excerpt",
    "comp.rapport.section.accord": "Agreement between the engines",
    "comp.rapport.mots": "words (after normalisation): CTranslate2 {a}, OpenVINO {b}",
    "comp.rapport.desaccord": (
        "disagreement: {a} % relative to the CTranslate2 text, {b} % relative to the OpenVINO "
        "text ({sub} words replaced, {sup} missing in OpenVINO, {ins} extra in OpenVINO)"
    ),
    "comp.rapport.passages": "{n} passages where the texts differ",
    "comp.rapport.repartition": (
        "single word: {un}; several words: {plusieurs}; passage of at least {mots} words "
        "only in CTranslate2: {seul_a}, only in OpenVINO: {seul_b}"
    ),
    "comp.rapport.horodatage": (
        "timing: {n} identical words out of {egaux} placed more than {seuil} s apart, "
        "in {zones} areas"
    ),
    "comp.rapport.segments": (
        "segments (basis of speaker separation): CTranslate2 {na}, median {ma} s, longest {xa} s; "
        "OpenVINO {nb}, median {mb} s, longest {xb} s"
    ),
    "comp.rapport.glossaire": (
        "glossary ({total} terms): CTranslate2 finds {ta} ({oa} occurrences), "
        "OpenVINO {tb} ({ob} occurrences)"
    ),
    "comp.rapport.anglais": (
        "common English words written in English (list of {liste} words): CTranslate2 {a}, OpenVINO {b}"
    ),
    "comp.rapport.incertains": (
        "CTranslate2 flags {n} uncertain words (probability below {seuil}); {div} fall in a "
        "passage where the engines disagree, that is {pct} %, against {base} % of all its words"
    ),
    "comp.rapport.confiance_ov": "OpenVINO gives no word probability: no count on its side.",
    "comp.rapport.section.reference": "Reviewed reference",
    "comp.rapport.sans_reference": (
        "none: the figures above show where the engines disagree, not which one is right."
    ),
    "comp.rapport.ref_fenetre": (
        "{couvert} min of reference out of {duree} min of excerpt, {mots} words (format {format})"
    ),
    "comp.rapport.ref_wer": (
        "{moteur}: error rate {wer} % ({sub} replaced, {sup} missing, {ins} extra)"
    ),
    "comp.rapport.ref_glossaire": "glossary terms of the reference found: {retrouves} out of {attendus}",
    "comp.rapport.ref_anglais": "common English words: {n} (reference: {ref})",
    "comp.rapport.ref_biais": (
        "Caution: a reference produced by Scribouille (CTranslate2 engine) and lightly corrected "
        "favours CTranslate2, whose wording and unreviewed errors it keeps."
    ),
    "comp.ref.vide": "empty or unreadable reference: no error rate.",
    "comp.ref.illisible": "unreadable reference: no error rate.",
    "comp.ref.sans_horodatage": (
        "the reference has no timestamps: there is no way to tell which part matches the "
        "excerpt. Comparing with the reference is only possible on the whole file "
        "(without --debut or --duree)."
    ),
    "comp.ref.hors_extrait": (
        "no line of the reference falls entirely within the excerpt: check --debut and "
        "--duree, or the timestamps of the reference."
    ),
    "comp.rapport.lecture": (
        "Reading: a disagreement is not an error of one engine or the other, it shows where "
        "to listen again. Normalisation: lower case, no punctuation, numbers in words, split "
        "elisions, hesitations removed."
    ),
    "comp.rapport.remarque": (
        "This report contains no word of the transcript, no user name, no computer name and "
        "no path."
    ),

    "moteur.hors_ligne": (
        "Without access to Hugging Face (filtered network), there is an offline route: "
        "on a computer where Scribouille has already downloaded this model, copy the "
        "“{dossier_cache}” folder from its models folder, then paste it as is into "
        "{dossier}. It will be recognised without any network call. Original "
        "repository: https://huggingface.co/{depot}"
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
        "pyannote/speaker-diarization-community-1 model and accept its terms of use "
        "(CC-BY-4.0 licence; the form asks for an organisation and a use case, and "
        "pyannote may email you now and then)."
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
    "ext.lot.openvino": "the OpenVINO engine",
    "ov.installe": "OpenVINO engine installed. Run the benchmark to find out whether it is faster here.",
    "ov.installation_echec": (
        "OpenVINO installation failed: the network may be blocking PyPI. Offline route: "
        "on a computer with access, run \"pip download --no-deps openvino==2026.4.1 "
        "openvino-tokenizers==2026.4.1.0 openvino-genai==2026.4.1.0 --python-version 3.12 "
        "--only-binary=:all: --platform win_amd64 -d wheels\", then copy the three .whl "
        "files into {dossier} and start the installation again."
    ),
    "ov.retrait_sources": (
        "From source, OpenVINO lives in the \".venv\" environment: remove it with "
        "pip uninstall openvino-genai openvino-tokenizers openvino."
    ),
    "ov.retrait_echec": (
        "The OpenVINO folder could not be deleted, probably because it is still in use. "
        "Close Scribouille, open it again, then retry."
    ),
    "app.banc.en_cours": "A benchmark or an engine comparison is running: wait for it to finish or stop it.",
    "app.banc.file_occupee": "A transcription is running: the benchmark will wait until it is done.",
    "vitesse.automatique": "automatic setting ({fils} compute threads, usual engine)",
    "vitesse.reglage_ov": "OpenVINO engine on {peripherique}",
    "vitesse.reglage_ct2": "usual engine, {fils} threads, {lots}",
    "vitesse.aucun_conseil": "No recommendation to apply: run the benchmark first.",
    "vitesse.applique": "Setting applied: {reglage}.",
    "vitesse.retour_auto": "Back to the automatic setting.",
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
    "app.comp.dialogue_reference": "Transcripts (*.txt;*.srt;*.vtt;*.json)",
    "app.comp.fichier_absent": "First choose the recording to compare.",
    "app.comp.debut_illisible": "Unreadable start: write it as 00:05:00.",
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
    "app.arret": (
        "Stop requested: the transcription stops at the end of the current batch of "
        "passages, which can take more than a minute on a CPU. With progressive "
        "saving, text already produced is kept."
    ),
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
    # -- Measurement campaign (app/campagne.py) --------------------------------
    "camp.libelle_ov": "OpenVINO {peripherique}, {modele}, beam {faisceau}",
    "camp.libelle_ct2": "CTranslate2 processor, {modele}, beam {faisceau}",
    "camp.rapport.titre": "Settings measurement campaign, {nom} {version}, {date}",
    "camp.rapport.machine": "Machine: {processeur}, {memoire} GB, {alimentation}",
    "camp.rapport.openvino": "OpenVINO {version}, devices seen: {peripheriques}",
    "camp.rapport.vitesse": (
        "speed: {facteur} times the audio duration (one hour of meeting: {heure}), "
        "loading {chargement} s, memory {memoire} GB; ran from {debut} to {fin}"
    ),
    "camp.rapport.section.corpus": "Public corpus with reference",
    "camp.rapport.corpus": (
        "{extraits} excerpts from {reunions} meetings, {minutes} min of audio, {mots} reference "
        "words, {chev} % of them spoken while someone else is talking; "
        "{anglais} common English words"
    ),
    "camp.rapport.armes_egales": (
        "like for like: same excerpts, same normalisation (lower case, punctuation and "
        "hesitations removed, numbers in words), glossary and corrections off, language fr"
    ),
    "camp.rapport.source": "source: {attribution}",
    "camp.rapport.section.reglages": "Measured settings",
    "camp.rapport.preset_actuel": "(current \"{preset}\" setting)",
    "camp.rapport.echec": "failed ({etat}) {detail}",
    "camp.rapport.non_pris_en_charge": (
        "not supported on this device (OpenVINO does not run beam search on the "
        "integrated graphics or the NPU), not counted as a failure"
    ),
    "camp.rapport.wer": (
        "word error rate: {wer} % (95 % interval: {bas} to {haut}); "
        "{sub} substitutions, {sup} deletions, {ins} insertions over {mots} words"
    ),
    "camp.rapport.chevauchement": (
        "reference words lost: {chev} % when two people speak at once, {hors} % otherwise"
    ),
    "camp.rapport.inventions": (
        "long insertions ({seuil} or more words absent from the reference): {n}, {mots} words; "
        "segments longer than {duree} s: {longs} % of {segments}"
    ),
    "camp.rapport.temoin": "read speech control (FLEURS, 44 s): {wer} % errors",
    "camp.rapport.section.verdict": "Verdict",
    "camp.rapport.regle": (
        "rule: drop any setting slower than the meeting; keep those whose error rate cannot be "
        "told apart from the best (less than {ecart} point apart, or paired difference whose "
        "95 % interval contains zero and which stays under {plafond} points); among them, the fastest"
    ),
    "camp.rapport.aucun_verdict": "no setting completed: no verdict.",
    "camp.rapport.retenu": "chosen setting: {code}, {reglage}",
    "camp.rapport.motif.equivalent_plus_rapide": (
        "the fastest of the settings as accurate as the best ({meilleur})"
    ),
    "camp.rapport.motif.plus_juste_admissible": (
        "no fast enough setting matches the best ({meilleur}): the most accurate of the "
        "settings faster than the meeting"
    ),
    "camp.rapport.equivalent": "equivalent",
    "camp.rapport.distinct": "less accurate",
    "camp.rapport.trop_lent": "slower than the meeting",
    "camp.rapport.ecart": (
        "{code}: {ecart} points from the best (paired interval {bas} to {haut}), {etat}"
    ),
    "camp.rapport.contre_qualite": (
        "compared with the current \"Maximum quality\" preset: {ecart} points of error rate, "
        "{rapport} times faster"
    ),
    "camp.rapport.cout_ov": (
        "what it costs: OpenVINO gives no word probability, so the review view underlines no "
        "doubtful word; shorter segments; if the graphics chip fails, the application falls "
        "back to CTranslate2 on its own"
    ),
    "camp.rapport.cout_ct2": (
        "what it costs: processor only, the graphics chip stays idle; uncertain words stay "
        "underlined in the review view"
    ),
    "camp.rapport.pour_une_heure": "expected time for one hour of meeting: {duree}",
    "camp.rapport.section.doutes": "Doubtful words",
    "camp.rapport.doute_ct2": (
        "{code}, probability below {seuil}: {part} % of words flagged, covering {rappel} % of "
        "wrong words; {precision} % of flagged words are wrong"
    ),
    "camp.rapport.doute_seconde": (
        "{code} checked by a second {second} pass (words written differently): {part} % of words "
        "flagged, covering {rappel} % of wrong words; {precision} % of flagged words are wrong; "
        "cost: {cout} % more computing"
    ),
    "camp.rapport.doute_aucun": "not enough successful settings to measure flagging.",
    "camp.rapport.section.glossaire": "Glossary",
    "camp.rapport.glossaire_public": "public corpus: glossary off for every setting",
    "camp.rapport.glossaire_poste": (
        "this computer's glossary: {termes} terms loaded, {exemples} of them examples shipped "
        "active by older versions (fictitious names)"
    ),
    "camp.rapport.glossaire_exemples": (
        "this computer's glossary is only the original example: none of its terms can be found "
        "in a real meeting. Replace its content with the team's proper names and acronyms "
        "(Settings, Glossary)."
    ),
    "camp.rapport.duree": "Campaign duration: {duree}",
    "camp.rapport.appliquer": (
        "To apply this verdict, in the program folder: "
        "scribouille-verifier.exe --campagne --appliquer (nothing is computed again)"
    ),
    "camp.rapport.remarque": (
        "This report holds numbers only: no transcribed word, no name, no path."
    ),
    "camp.etape.deja": "{code}: already measured, reused as is",
    "camp.etape.non_pris_en_charge": "{code}: not supported on {peripherique}, skipped",
    "camp.etape.reglage": "Setting {numero} of {total}: {reglage} ({code})",
    "camp.etape.progres": "{code}: excerpt {n} of {total}",
    "camp.etape.modele": "Downloading model {modele}",
    "camp.etape.corpus": "Preparing the public corpus (at most {mo} MB to download without a prepared pack)",
    "camp.etape.paquet": "Corpus taken from the prepared pack",
    "camp.etape.reseau": "Corpus: excerpt {rang} downloaded and mixed",
    "camp.corpus_absent.titre": "Public corpus unavailable",
    "camp.corpus_absent.msg": (
        "The corpus could neither be read from a prepared pack ({paquet}) nor downloaded. "
        "Put the pack next to the program or point to it with --corpus. Detail: {detail}"
    ),
    "camp.reglage_inconnu.titre": "Unknown setting",
    "camp.reglage_inconnu.msg": "Unknown setting: {cles}. Possible settings: {connues}.",
    "camp.reunion.titre": "Campaign, real meeting (no reference), {nom} {version}, {date}",
    "camp.reunion.extrait": "Excerpt: {minutes} min (edges moved to pauses)",
    "camp.reunion.ancre": "Comparison setting: {code} ({source})",
    "camp.reunion.ancre.verdict": "chosen by the public campaign",
    "camp.reunion.ancre.qualite": "\"Maximum quality\" preset, no public verdict",
    "camp.reunion.ancre.verdict_echec": (
        "\"Maximum quality\" preset: the setting chosen by the public campaign, {retenu}, "
        "failed on this meeting"
    ),
    "camp.reunion.ancre.premier": "first successful setting",
    "camp.reunion.glossaire": (
        "This computer's glossary and corrections applied: {termes} terms loaded, "
        "{exemples} of them examples shipped active by older versions"
    ),
    "camp.reunion.accord": (
        "disagreement with {ancre}: {desaccord} % ({mots} words against {mots_ancre}); passages "
        "of at least {mots_seg} extra words: {en_plus}, missing: {en_moins}"
    ),
    "camp.reunion.segments": (
        "segments: {n}, median duration {mediane} s, longer than {duree} s: {longs} %"
    ),
    "camp.reunion.termes": "glossary terms found: {trouves} of {termes}",
    "camp.reunion.remarque": (
        "Without a reference, a disagreement says where settings diverge, not which is right. "
        "This report holds numbers only: no transcribed word, no name, no path."
    ),
    "camp.cli.usage": (
        "Usage: --campagne [--appliquer] [--recommencer] [--reglages KEY,KEY] "
        "[--limite-extraits N] [--corpus PACK.zip] [--peripherique GPU|CPU] [--telecharger]\n"
        "       --campagne --reunion FILE [--debut 00:05:00] [--duree 600] [--reglages KEY,KEY]"
    ),
    "camp.cli.fichier": "Report: {fichier}",
    "camp.cli.applique": "Setting {code} applied: it is used from the next transcription.",
    "camp.cli.rien_a_appliquer": "No verdict: nothing applied.",

    # Endurance test (app/endurance.py)
    "end.rapport.titre": "{nom} {version}: endurance test ({date})",
    "end.rapport.reglage": "Setting under test: {code} ({reglage})",
    "end.rapport.plan": (
        "Runs: {n}, {minutes} min long on average, taken from the public corpus (SUMM-RE ASRU); "
        "a single process, pipeline opened then released for each run, as in the app"
    ),
    "end.rapport.plan_pression": (
        "Memory pressure, every other run: CTranslate2 large-v3 loaded and run on {secondes} s "
        "(\"Maximum quality\" settings), then free memory brought down to about {cible} GB; all of it stays "
        "in place while OpenVINO opens and runs"
    ),
    "end.rapport.section.resultat": "Result",
    "end.rapport.panne_avant": (
        "Runs with at least one engine error (before replay): {k} of {n} ({pct} %, "
        "95 % upper bound: {borne} %)"
    ),
    "end.rapport.panne_apres": (
        "Runs the replay did not save (fallback to CTranslate2 or failure): {k} of {n} ({pct} %, "
        "95 % upper bound: {borne} %)"
    ),
    "end.rapport.issues": (
        "Successful replays: {rejeux}; fallbacks to CTranslate2: {replis}; uncaught failures: {erreurs}; "
        "crashed or stuck processes: {plantages}"
    ),
    "end.rapport.pression_ratee": "Runs not measured because memory pressure could not be set up: {n}",
    "end.rapport.repetitions": (
        "Looping windows: {fenetres}, redone {reprises} times; failed redos: {echecs}"
    ),
    "end.rapport.vitesse": (
        "Speed: median factor {mediane} (from {min} to {max}); model opening: median {ouv} s, "
        "at most {ouv_max} s"
    ),
    "end.rapport.memoire": (
        "Free memory before opening: lowest {min} GB, median {med} GB; "
        "before the run: lowest {min2} GB"
    ),
    "end.rapport.par_mode": (
        "{mode}: runs {n}, with an error {k}, not saved {perdus}; free memory before "
        "opening: median {med} GB, lowest {min} GB"
    ),
    "end.mode.normal": "normal",
    "end.mode.pression": "under pressure",
    "end.mode.diagnostic": "diagnostic",
    "end.rapport.section.erreurs": "Errors seen, exact text",
    "end.rapport.aucune_erreur": "none",
    "end.rapport.erreur": "{id} ({phase}, {issue}): {erreur}",
    "end.phase.ouverture": "pipeline opening",
    "end.phase.transcription": "transcription",
    "end.phase.garde": "redo of a looping window",
    "end.phase.passage": "run",
    "end.issue.rejeu": "replayed",
    "end.issue.rejeu_reussi": "replay succeeded",
    "end.issue.repli": "fallback to CTranslate2",
    "end.issue.premiere_version_gardee": "first version kept",
    "end.rapport.section.diagnostic": "Diagnosis of the 12/11 failure",
    "end.rapport.diag_journal_aucun": "Log of the crashed process: not found (purged or deleted).",
    "end.rapport.diag_journal": (
        "Log {date}: error raised in moteur_openvino.py, line {lignes} ({lieu}); "
        "looping window just before: {repetitive}; pipeline opened: {ouvert}; "
        "planned windows: {fenetres}"
    ),
    "end.lieu.glouton": "greedy decoding of a window",
    "end.lieu.garde_faisceau": "repetition guard, beam of 5",
    "end.lieu.ouverture": "pipeline opening",
    "end.lieu.inconnu": "elsewhere",
    "end.oui": "yes",
    "end.non": "no",
    "end.rapport.diag_ancien": (
        "Meeting {reunion}, old guard (beam of 5): {etat}; looping windows: {fenetres}; "
        "failed redos: {echecs}; factor {facteur}"
    ),
    "end.rapport.diag_nouveau": (
        "Meeting {reunion}, new guard (temperature): {etat}; looping windows: {fenetres}; "
        "failed redos: {echecs}; factor {facteur}"
    ),
    "end.rapport.diag_conclusion_oui": (
        "The old guard reproduces the 12/11 error on this meeting and the new one gets through: "
        "cause confirmed."
    ),
    "end.rapport.diag_conclusion_non": (
        "The old guard does not reproduce the error on this meeting, or the new one does not get "
        "through: cause not confirmed."
    ),
    "end.rapport.section.detail": "Run by run",
    "end.rapport.ligne": (
        "{id} {mode}: {etat}; {libre_ouv} GB free before opening, {libre_pass} GB before the run; "
        "opening {ouv} s; factor {facteur}; looping windows {boucles}"
    ),
    "end.etat.ok": "succeeded",
    "end.etat.rejeu_reussi": "succeeded after replay",
    "end.etat.repli": "fallback to CTranslate2",
    "end.etat.erreur": "failed",
    "end.etat.plantage": "process crashed",
    "end.etat.bloque": "stuck, stopped",
    "end.etat.pression_ratee": "memory pressure not possible",
    "end.rapport.remarque": "Report of figures only: no transcribed word, no name, no path.",
    "end.rapport.duree": "Test duration: {duree}",
    "end.refuse.titre": "Endurance test not possible",
    "end.refuse.absent": "Setting {code} needs OpenVINO, which is not installed on this computer.",
    "end.refuse.faisceau": "Setting {code} is not supported on {peripherique} (beam search).",
    "end.refuse.modele": (
        "A model is missing for setting {code} (or for memory pressure, CTranslate2 large-v3): "
        "run the campaign first, it downloads them."
    ),
    "end.etape.plan": "{code}: {n} runs planned, {faits} already done",
    "end.etape.passage": "{id} ({n} of {total}): {etat}, factor {facteur}, opening {ouv} s, {libre} GB free",
    "end.etape.relance": "new process for the {n} remaining runs",
    "end.etape.abandon": "the process stops without doing anything ({issue}): test stopped",
    "end.erreur.bloque": "no sign of life for {s} s, process stopped",
    "end.erreur.plantage": "process ended without a result (code {code})",
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
