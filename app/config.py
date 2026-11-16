"""
Configuration de l'application.

`config.json` est propre à chaque poste, il n'est pas versionné.
`config.example.json` en donne un exemplaire neutre, sans aucun chemin réel.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy

from . import chemins, journal, langues
from .presets import PRESET_DEFAUT

DEFAUTS: dict = {
    "preset": PRESET_DEFAUT,
    "langue": "fr",                 # langue PARLÉE, pour le moteur
    "langue_interface": "",         # langue de l'INTERFACE, vide = à détecter
    "dossier_sortie": "",
    "diarisation": False,
    "nb_locuteurs": 0,              # 0 = détection automatique
    # Heure en tête de chaque paragraphe du .txt, par défaut : depuis un compte
    # rendu, on retrouve le passage dans l'enregistrement.
    "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": True},
    "appliquer_corrections": True,
    "utiliser_glossaire": True,
    "compagnon_confiance": True,    # fichier .json de confiance à côté des sorties
    "corrections_apprises": True,   # proposer de mémoriser une correction relue
    "rapprochement_vocabulaire": True,  # vocabulaire : rapprochement phonétique borné, voir app/vocabulaire_usage.py
    "vocabulaires_partages": [],    # fichiers de vocabulaire d'équipe ou de projet, lus en plus du personnel
    "sauvegarde_progressive": True, # écrire au fil des segments, reprise possible
    "motif_sortie": "",             # vide = nommage historique, « {date}-{nom} »
    "dossier_surveille": "",        # dossier scruté quand la surveillance est active
    "surveillance": False,          # opt-in, voir app/surveillance.py
    "maj_verifier": False,          # opt-in, SEUL appel réseau hors modèles
    "barre_taches": True,
    "prevenir_fin": True,           # fin de file : clignotement, titre, notification sans son           # progression dans la barre des tâches Windows
    "filtres_salle": False,
    "mode_avance": False,
    "modele_avance": "",            # vide = modèle du preset
    "beam_size": 0,                 # 0 = valeur du preset
    "condition_on_previous_text": True,
    "forcer_processeur": False,
    "reglage_machine": {},          # réglage mesuré par le banc d'essai, voir app/reglage_machine.py
    # vitesse | equilibre | discret ; vide : selon le moteur (vitesse maximale
    # quand la puce ou la carte graphique calcule, équilibré sur le processeur),
    # voir `rythme.retenu`.
    "rythme": "",
    "rythme_auto": False,           # s'adapter tout seul à l'usage du poste
    "proposition_ecartee": "",      # signature du poste dont la proposition a été écartée
    # Exemples fictifs des anciennes versions dans vocabulaire.txt et
    # corrections.txt (voir `vocabulaire.retirer_exemples_anciens`) : vide,
    # « retires » (fait, à annoncer), « vus » (annoncé), « gardes » (remis ou
    # gardés par l'utilisateur : plus rien n'est proposé).
    "exemples_anciens": "",
    # Séparation des voix cochée mais non installée : déjà dite une fois par
    # la ligne de commande (remis à faux quand le réglage change).
    "avis_locuteurs": False,
    "theme": "auto",                # auto | clair | sombre
    "zoom": 1.0,
    "journal_ouvert": False,
}


def _fusionner(base: dict, ajout: dict) -> dict:
    resultat = deepcopy(base)
    for cle, valeur in (ajout or {}).items():
        if cle not in resultat:
            continue
        if isinstance(resultat[cle], dict) and isinstance(valeur, dict):
            resultat[cle] = {**resultat[cle], **valeur}
        else:
            resultat[cle] = valeur
    return resultat


#: Réglages propres à Scribouille 3.x quand une WhiScribe 2.x installée lit le
#: même dossier de données (`chemins.donnees_partagees_ancienne_version`) : son
#: `config.json` n'est alors jamais réécrit (la 2.x retire à sa prochaine
#: sauvegarde les clés qu'elle ne connaît pas, et la 3.0 retirait les siennes).
#: On n'y garde que ce qui diffère du `config.json` de la 2.x ; une fois la 2.x
#: partie, la première sauvegarde le reverse dans `config.json` et l'efface.
NOM_FICHIER_PROPRE = "config-scribouille.json"


def fichier_propre():
    return chemins.RACINE / NOM_FICHIER_PROPRE


def partage_ancienne_version() -> bool:
    """Une WhiScribe 2.x installée lit aussi `config.json` : on ne le touche pas."""
    return chemins.donnees_partagees_ancienne_version() is not None


#: Résultat de la dernière lecture de chaque fichier de réglages, par chemin :
#: « ok », « absent », « acces » (ne se lit pas pour l'instant : verrou d'un
#: antivirus, remplacement en cours ailleurs) ou « abime » (contenu illisible).
#: `sauver` s'en sert pour ne jamais écrire des valeurs par défaut par-dessus
#: des réglages qu'il n'a pas pu lire.
_LECTURES: dict[str, str] = {}

#: Lecture refusée par le système : nouvel essai après une courte pause.
ESSAIS_LECTURE = 3
PAUSE_LECTURE_S = 0.2


def _lire_detail(chemin) -> tuple[dict, str]:
    """(contenu, statut) ; voir `_LECTURES`. Ne lève jamais."""
    import time

    texte = None
    for essai in range(ESSAIS_LECTURE):
        try:
            texte = chemin.read_bytes()
            break
        except FileNotFoundError:
            return {}, "absent"
        except OSError as exc:
            if essai == ESSAIS_LECTURE - 1:
                journal.attention("%s illisible pour l'instant, valeurs par défaut en mémoire, rien n'est écrit "
                                  "par-dessus : %s", chemin.name, exc)
                return {}, "acces"
            time.sleep(PAUSE_LECTURE_S)
    try:
        donnees = json.loads(texte.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        journal.attention("%s illisible, valeurs par défaut utilisées ; il sera gardé de côté avant toute "
                          "sauvegarde : %s", chemin.name, exc)
        return {}, "abime"
    if not isinstance(donnees, dict):
        return {}, "abime"
    return donnees, "ok"


def _lire_json(chemin) -> dict:
    donnees, statut = _lire_detail(chemin)
    _LECTURES[str(chemin)] = statut
    return donnees


class SauvegardeRefusee(OSError):
    """Les réglages du disque n'ont pas pu être lus : rien n'est écrit par-dessus."""


def _mettre_de_cote(chemin) -> None:
    """Un fichier de réglages abîmé est gardé sous un autre nom avant d'être remplacé, et c'est dit."""
    from datetime import datetime

    cible = chemin.with_name(f"{chemin.name}.illisible-{datetime.now():%Y%m%d-%H%M%S}")
    os.replace(chemin, cible)
    journal.attention("%s illisible, gardé de côté sous %s ; nouveaux réglages écrits", chemin.name, cible.name)


def _verifier_avant_ecriture(chemin) -> dict:
    """
    Relit `chemin` juste avant d'écrire : contenu à garder. Lecture refusée
    (maintenant, ou à la dernière lecture qui a servi à bâtir les réglages) :
    `SauvegardeRefusee`. Contenu abîmé : mis de côté, sous un autre nom.
    """
    donnees, statut = _lire_detail(chemin)
    if statut == "acces" or _LECTURES.get(str(chemin)) == "acces":
        raise SauvegardeRefusee(f"{chemin.name} illisible pour l'instant : réglages non enregistrés, "
                                "le fichier n'est pas écrasé")
    if statut == "abime":
        _mettre_de_cote(chemin)
    return donnees


def charger(definir_langue: bool = False) -> dict:
    """
    La configuration du disque, défauts compris. Ne réécrit JAMAIS rien :
    une commande de lecture (`diagnostic`, `verifier`...) laisse le dossier
    de données tel quel, octet pour octet.

    Lire la configuration ne change pas la langue de l'interface du processus :
    seuls les points d'entrée (fenêtre, ligne de commande, moteur, import de
    données) la posent, avec `definir_langue=True`. Avant, toute lecture la
    reposait : une langue choisie par le processus (par un essai, ou par la
    fenêtre qui venait d'en changer) cédait à celle du disque, et, sur un
    dossier sans langue enregistrée, à celle du système.
    """
    config = _fusionner(_fusionner(DEFAUTS, _lire_json(chemins.FICHIER_CONFIG)), _lire_json(fichier_propre()))

    if not config["dossier_sortie"]:
        config["dossier_sortie"] = str(chemins.dossier_sortie_defaut())

    # Langue de l'interface. Tant que l'utilisateur n'en a pas choisi une,
    # elle suit la langue du système (elle s'enregistre avec la première
    # sauvegarde des réglages, jamais à la lecture). Elle est SANS RAPPORT
    # avec « langue », qui désigne la langue parlée dans les enregistrements.
    if not langues.normaliser(config.get("langue_interface")):
        config["langue_interface"] = langues.detecter_systeme()
    if definir_langue:
        langues.definir(config["langue_interface"])

    # Le dossier des modèles n'est pas rangé ici : il est partagé avec le
    # programme d'installation et le désinstallateur, voir `app/chemins.py`.
    return config


def _ecrire(chemin, contenu: dict) -> None:
    # Nom provisoire propre à ce processus et à cette écriture : une fenêtre
    # et une commande qui écrivent en même temps ne se mélangent pas.
    import secrets

    texte = json.dumps(contenu, indent=2, ensure_ascii=False) + "\n"
    if chemins.contenu_identique(chemin, texte):
        # Rien ne change : le fichier n'est ni réécrit ni redaté.
        return
    temporaire = chemin.with_name(f"{chemin.name}.{os.getpid()}-{secrets.token_hex(3)}.tmp")
    try:
        temporaire.write_text(texte, encoding="utf-8")
        os.replace(temporaire, chemin)
    finally:
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass


def _retirer_propre(config: dict) -> None:
    """
    La 2.x partie, nos réglages à part (`config-scribouille.json`) sont dans
    `config.json` : le fichier à part s'en va. S'il n'a pas été lu, ou pas
    entièrement repris, il est gardé de côté plutôt qu'effacé.
    """
    propre = fichier_propre()
    if not propre.exists():
        return
    statut = _LECTURES.get(str(propre))
    if statut == "acces":
        return
    donnees, lu = _lire_detail(propre)
    repris = statut == "ok" or all(config.get(cle) == valeur for cle, valeur in donnees.items() if cle in DEFAUTS)
    if lu == "ok" and repris:
        propre.unlink(missing_ok=True)
    elif lu in ("ok", "abime"):
        _mettre_de_cote(propre)


def sauver(config: dict) -> bool:
    """
    Écrit les réglages. Dossier partagé avec une WhiScribe 2.x : dans notre
    fichier à nous, seulement ce qui diffère de son `config.json`, qui reste
    tel quel. Sinon dans `config.json`, en gardant les clés qu'on ne connaît
    pas (celles d'une autre version) au lieu de les effacer.

    Un fichier qui n'a pas pu être lu (à la lecture qui a bâti ces réglages,
    ou juste avant d'écrire) n'est jamais écrasé : rien n'est écrit, c'est
    dit au journal. Un fichier abîmé est gardé de côté sous un autre nom
    (`<nom>.illisible-<date>`) avant d'être remplacé. Vrai si c'est écrit.
    """
    try:
        if partage_ancienne_version():
            base_lue = _lire_json(chemins.FICHIER_CONFIG)
            if _LECTURES.get(str(chemins.FICHIER_CONFIG)) == "acces":
                raise SauvegardeRefusee(f"{chemins.FICHIER_CONFIG.name} illisible pour l'instant : "
                                        "réglages non enregistrés")
            base = _fusionner(DEFAUTS, base_lue)
            propre = {cle: valeur for cle, valeur in config.items()
                      if cle in DEFAUTS and base.get(cle) != valeur}
            _verifier_avant_ecriture(fichier_propre())
            _ecrire(fichier_propre(), propre)
            _LECTURES[str(fichier_propre())] = "ok"
            return True
        existant = _verifier_avant_ecriture(chemins.FICHIER_CONFIG)
        etrangers = {cle: valeur for cle, valeur in existant.items() if cle not in DEFAUTS}
        _ecrire(chemins.FICHIER_CONFIG, {**etrangers, **config})
        _LECTURES[str(chemins.FICHIER_CONFIG)] = "ok"
        _retirer_propre(config)
        return True
    except OSError as exc:
        journal.attention("Sauvegarde de la configuration impossible : %s", exc)
        return False


def reglages_effectifs(config: dict) -> dict:
    """
    Traduit la configuration de l'interface en paramètres du moteur.

    Le mode avancé n'écrase que ce que l'utilisateur a explicitement changé :
    tout le reste continue de venir du preset.
    """
    from .presets import preset as lire_preset

    p = lire_preset(config.get("preset", PRESET_DEFAUT))
    avance = bool(config.get("mode_avance"))
    modele = (config.get("modele_avance") or p["modele"]) if avance else p["modele"]
    beam = (config.get("beam_size") or p["beam_size"]) if avance else p["beam_size"]
    personnalise = avance and (modele != p["modele"] or beam != p["beam_size"])

    from .presets import nom_preset

    return {
        "preset": p["cle"],
        "preset_nom": (
            langues.t("preset.personnalise", nom=nom_preset(p["cle"]))
            if personnalise else nom_preset(p["cle"])
        ),
        "modele": modele,
        "beam_size": beam,
        "best_of": p["best_of"],
        "vad": p["vad"],
        "condition_on_previous_text": (
            bool(config.get("condition_on_previous_text", True)) if avance else True
        ),
        "filtres_salle": bool(config.get("filtres_salle")),
        "forcer_processeur": bool(config.get("forcer_processeur")) if avance else False,
    }
