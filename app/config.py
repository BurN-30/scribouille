"""
Configuration de l'application.

`config.json` est propre à chaque poste, il n'est pas versionné.
`config.example.json` en donne un exemplaire neutre, sans aucun chemin réel.
"""

from __future__ import annotations

import json
from copy import deepcopy

from . import chemins, journal, langues
from .presets import PRESET_DEFAUT

DEFAUTS: dict = {
    "preset": PRESET_DEFAUT,
    "langue": "fr",                 # langue PARLÉE, pour le moteur
    "langue_interface": "",         # langue de l'INTERFACE, vide = à détecter
    "dossier_sortie": "",
    "diarisation": True,
    "nb_locuteurs": 0,              # 0 = détection automatique
    "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
    "appliquer_corrections": True,
    "utiliser_glossaire": True,
    "compagnon_confiance": True,    # fichier .json de confiance à côté des sorties
    "corrections_apprises": True,   # proposer de mémoriser une correction relue
    "rapprochement_vocabulaire": True,  # vocabulaire : rapprochement phonétique borné, voir app/vocabulaire_usage.py
    "vocabulaires_partages": [],    # fichiers de vocabulaire d'équipe ou de projet, lus en plus du personnel
    "sauvegarde_progressive": True, # écrire au fil des segments, reprise possible
    "lecture_audio": False,         # écouter l'extrait depuis la vue de lecture
    "motif_sortie": "",             # vide = nommage historique, « {date}-{nom} »
    "dossier_surveille": "",        # dossier scruté quand la surveillance est active
    "surveillance": False,          # opt-in, voir app/surveillance.py
    "maj_verifier": False,          # opt-in, SEUL appel réseau hors modèles
    "barre_taches": True,           # progression dans la barre des tâches Windows
    "filtres_salle": False,
    "mode_avance": False,
    "modele_avance": "",            # vide = modèle du preset
    "beam_size": 0,                 # 0 = valeur du preset
    "condition_on_previous_text": True,
    "forcer_processeur": False,
    "reglage_machine": {},          # réglage mesuré par le banc d'essai, voir app/reglage_machine.py
    "rythme": "vitesse",            # vitesse | equilibre | discret, voir app/rythme.py
    "rythme_auto": False,           # s'adapter tout seul à l'usage du poste
    "proposition_ecartee": "",      # signature du poste dont la proposition a été écartée
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


def charger() -> dict:
    donnees: dict = {}
    if chemins.FICHIER_CONFIG.exists():
        try:
            donnees = json.loads(chemins.FICHIER_CONFIG.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            journal.attention("config.json illisible, valeurs par défaut utilisées : %s", exc)
            donnees = {}

    config = _fusionner(DEFAUTS, donnees)

    if not config["dossier_sortie"]:
        config["dossier_sortie"] = str(chemins.dossier_sortie_defaut())

    # Langue de l'interface. Au tout premier lancement elle suit la langue du
    # système, puis elle est écrite dans la configuration et ne bouge plus que
    # si l'utilisateur la change. Elle est SANS RAPPORT avec « langue », qui
    # désigne la langue parlée dans les enregistrements.
    if not langues.normaliser(config.get("langue_interface")):
        config["langue_interface"] = langues.detecter_systeme()
        journal.info("Langue d'interface détectée : %s", config["langue_interface"])
        sauver(config)
    langues.definir(config["langue_interface"])

    # Le dossier des modèles n'est pas rangé ici : il est partagé avec le
    # programme d'installation et le désinstallateur, voir `app/chemins.py`.
    return config


def sauver(config: dict) -> None:
    try:
        chemins.FICHIER_CONFIG.write_text(
            json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        journal.attention("Sauvegarde de config.json impossible : %s", exc)


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
