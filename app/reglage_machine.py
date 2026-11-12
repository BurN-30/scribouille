"""
Réglage de vitesse propre à ce poste : moteur, périphérique, fils, lots.

Le banc d'essai (`app/banc.py`) mesure plusieurs façons de transcrire sur la
machine et en conseille une. Rien n'est appliqué sans l'accord de
l'utilisateur : le bouton « Appliquer » de l'interface écrit le réglage ici,
dans `config.json`, avec la signature de la machine. Recopié sur un autre poste,
ou après un changement de processeur, il est ignoré : les choix automatiques
reprennent la main.

Clés du réglage, toutes facultatives :
    moteur          « ctranslate2 » ou « openvino »
    peripherique    « CPU », « GPU » ou « NPU » (OpenVINO seulement)
    fils            nombre de fils de calcul de CTranslate2, 0 = automatique
    lot             taille des lots de CTranslate2, 0 = un à un, absent = preset
    faisceau        largeur du faisceau du moteur retenu, absent = valeur du
                    moteur (5 pour CTranslate2, 1 pour OpenVINO) ; posé par la
                    campagne de mesure (`app/campagne.py`)
"""

from __future__ import annotations

from datetime import date

from . import calibration, journal
from .materiel import Materiel

CLE = "reglage_machine"
MOTEURS = ("ctranslate2", "openvino")


def lire(config: dict, mat: Materiel) -> dict:
    """Réglage enregistré pour CE poste, dictionnaire vide sinon."""
    reglage = config.get(CLE) or {}
    if not isinstance(reglage, dict) or not reglage:
        return {}
    if reglage.get("signature") != calibration.signature_machine(mat):
        return {}
    return reglage


def appliquer_au_materiel(config: dict, mat: Materiel) -> dict:
    """
    Pose le réglage sur la description du matériel, que tout le reste consulte.

    OpenVINO demandé mais absent (extension retirée, pilote changé) : le
    réglage est gardé, mais l'application retombe sur CTranslate2, et la clé
    « indisponible » le dit à l'interface.
    """
    reglage = lire(config, mat)
    mat.fils_imposes = max(0, int(reglage.get("fils") or 0))
    mat.moteur, mat.peripherique_openvino = "ctranslate2", ""
    effet = dict(reglage)
    if reglage.get("moteur") == "openvino":
        from . import moteur_openvino

        peripherique = str(reglage.get("peripherique") or "CPU").upper()
        plantage = moteur_openvino.chargement_interrompu()
        if plantage and peripherique != "CPU":
            # La dernière ouverture sur ce périphérique a fait tomber
            # l'application : on ne recommence pas d'office.
            effet["indisponible"] = True
            effet["plantage"] = plantage
            journal.attention("OpenVINO suspendu : la dernière ouverture sur %s n'a pas abouti",
                              plantage)
        elif moteur_openvino.installe() and peripherique in moteur_openvino.peripheriques_disponibles():
            mat.moteur, mat.peripherique_openvino = "openvino", peripherique
        else:
            effet["indisponible"] = True
            journal.attention("Réglage OpenVINO (%s) inapplicable sur ce poste, "
                              "CTranslate2 garde la main", peripherique)
    return effet


def lot_impose(config: dict, mat: Materiel) -> int | None:
    """Taille de lots imposée par le réglage, None pour suivre le preset."""
    reglage = lire(config, mat)
    if "lot" not in reglage:
        return None
    try:
        return max(0, int(reglage["lot"]))
    except (TypeError, ValueError):
        return None


def faisceau_impose(config: dict, mat: Materiel) -> int | None:
    """
    Largeur de faisceau imposée par le réglage, None pour garder celle du moteur.

    OpenVINO sur la puce graphique ou le NPU ne décode qu'en glouton (voir
    `moteur_openvino.SANS_FAISCEAU`) : un faisceau plus large n'y est jamais
    appliqué, même écrit à la main dans la configuration.
    """
    reglage = lire(config, mat)
    try:
        valeur = int(reglage.get("faisceau") or 0)
    except (TypeError, ValueError):
        return None
    if valeur < 1:
        return None
    if reglage.get("moteur") == "openvino":
        from . import moteur_openvino

        valeur = moteur_openvino.faisceau_effectif(str(reglage.get("peripherique") or "CPU"), valeur)
    return valeur


def enregistrer(config: dict, mat: Materiel, reglage: dict) -> dict:
    """Écrit le réglage dans la configuration (en mémoire), signé pour ce poste."""
    propre = {
        cle: reglage[cle] for cle in ("moteur", "peripherique", "fils", "lot", "faisceau")
        if cle in reglage and reglage[cle] is not None
    }
    if propre.get("moteur") not in MOTEURS:
        propre["moteur"] = "ctranslate2"
    if propre["moteur"] == "openvino" and "faisceau" in propre:
        from . import moteur_openvino

        propre["faisceau"] = moteur_openvino.faisceau_effectif(
            str(propre.get("peripherique") or "CPU"), int(propre["faisceau"] or 1))
    propre["signature"] = calibration.signature_machine(mat)
    propre["date"] = date.today().isoformat()
    propre["source"] = str(reglage.get("source") or "banc")
    config[CLE] = propre
    if propre["moteur"] == "openvino":
        # Accepter de nouveau OpenVINO, c'est lever la suspension posée après
        # un plantage : l'utilisateur a refait le banc ou choisi en connaissance.
        from . import moteur_openvino

        moteur_openvino.effacer_temoin()
    appliquer_au_materiel(config, mat)
    return propre


def oublier(config: dict, mat: Materiel) -> None:
    config[CLE] = {}
    appliquer_au_materiel(config, mat)
