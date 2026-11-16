"""
Ce qui calculera vraiment : une seule décision, que la file et toutes les
durées annoncées suivent.

Le moteur de la file (`traitement.fabriquer_moteur`) et chaque durée affichée
(cartes des presets, bandeau, ligne d'un fichier en file, décompte de départ,
fiche « ce que ça change », `transcrire`, `diagnostic`, `materiel proposer`)
passent par ici. Avant, chacun lisait `Materiel.cle_calcul`, c'est-à-dire le
réglage du poste, et non ce qui calcule :

  - « Forcer le processeur » (mode avancé) : CTranslate2 sur le processeur,
    quel que soit le réglage du poste (OpenVINO sur la puce, carte NVIDIA) ;
  - modèle sans version OpenVINO (distillation française du mode avancé) :
    `MoteurAvecRepli` ouvre d'emblée son CTranslate2 ;
  - puce suspendue après un plantage, OpenVINO retiré, puce écartée pour la
    session par le superviseur : le réglage du poste est relu
    (`reglage_machine.appliquer_au_materiel`), sur une copie, à chaque annonce ;
  - repli sur CTranslate2 à l'ouverture du modèle : la file suit le moteur
    réellement ouvert (`selon_cle`).

Ce module ne fait que décrire : il ne change ni le moteur créé, ni les
réglages, ni le matériel qu'on lui passe.
"""

from __future__ import annotations

import copy
import logging
import threading
from contextlib import contextmanager

from . import reglage_machine
from .materiel import Materiel


class _SansJournal(logging.Filter):
    """Écarte du journal les lignes du seul fil qui décrit (les autres passent)."""

    def __init__(self):
        super().__init__()
        self.fil = threading.get_ident()

    def filter(self, record: logging.LogRecord) -> bool:
        return threading.get_ident() != self.fil


@contextmanager
def muet():
    """
    Le réglage du poste relu pour une annonce : ni ligne au journal (« OpenVINO
    suspendu sur GPU... » à chaque carte), ni réessai de la puce marqué en cours.
    """
    journal = logging.getLogger("transcripteur")
    filtre = _SansJournal()
    journal.addFilter(filtre)
    reessai = reglage_machine.REESSAI_EN_COURS
    try:
        yield
    finally:
        journal.removeFilter(filtre)
        reglage_machine.REESSAI_EN_COURS = reessai


def forcer_demande(config: dict | None) -> bool:
    """« Forcer le processeur » ne vaut qu'en mode avancé (`config.reglages_effectifs`)."""
    config = config or {}
    return bool(config.get("mode_avance")) and bool(config.get("forcer_processeur"))


def a_version_openvino(modele: str) -> bool:
    """Le modèle a-t-il une version que le moteur Intel sait ouvrir (`MoteurAvecRepli.charger`) ?"""
    from . import moteur, presets

    return bool(presets.depot_openvino(modele) or moteur.est_modele_openvino(modele))


def moteur_retenu(mat: Materiel, forcer: bool) -> str:
    """
    Le moteur que la file crée : « openvino » (avec son repli) si le réglage du
    poste, posé sur `mat`, le retient et que le processeur n'est pas forcé ;
    « ctranslate2 » sinon.
    """
    return "openvino" if getattr(mat, "moteur", "") == "openvino" and not forcer else "ctranslate2"


def materiel_du_calcul(mat: Materiel, forcer: bool = False, modele: str = "") -> Materiel:
    """
    Copie de `mat` (réglage du poste déjà posé) ramenée à ce qui calculera :
    sa `cle_calcul` est celle sous laquelle la file rangera la mesure.
    """
    m = copy.copy(mat)
    if moteur_retenu(mat, forcer) == "ctranslate2":
        m.moteur, m.peripherique_openvino = "ctranslate2", ""
        if forcer:
            # `MoteurTranscription(forcer_processeur=True)` : le processeur,
            # même avec une carte NVIDIA.
            m.cuda_disponible = False
    elif modele and not a_version_openvino(modele):
        # Le CTranslate2 du repli, `MoteurTranscription(mat)` : processeur, ou
        # carte NVIDIA si le poste en a une.
        m.moteur, m.peripherique_openvino = "ctranslate2", ""
    return m


def selon_cle(mat: Materiel, cle_calcul: str) -> Materiel:
    """
    Copie de `mat` qui suit un moteur déjà ouvert (sa `cle_calcul` :
    « cpu », « cuda », « openvino-gpu »...) : repli sur CTranslate2 à
    l'ouverture, par exemple. Clé vide ou inconnue : `mat` tel quel (copié).
    """
    m = copy.copy(mat)
    cle = str(cle_calcul or "").lower()
    if cle.startswith("openvino-") and len(cle) > len("openvino-"):
        m.moteur, m.peripherique_openvino = "openvino", cle[len("openvino-"):].upper()
    elif cle in ("cpu", "cuda"):
        m.moteur, m.peripherique_openvino = "ctranslate2", ""
        m.cuda_disponible = cle == "cuda"
    return m


def poste(config: dict, mat: Materiel, ecartee: bool = False) -> tuple[Materiel, dict]:
    """
    Copie de `mat` avec le réglage du poste relu à l'instant (témoin de la
    puce, OpenVINO présent ou non), comme `ouvrir_file` le posera ; `ecartee` :
    puce écartée pour la session par le superviseur de la fenêtre après une
    mort du moteur sur elle (`Superviseur.puce_ecartee`), que le processus
    moteur applique alors (`reglage_machine.PUCE_ECARTEE`).
    """
    m = copy.copy(mat)
    with muet():
        effet = reglage_machine.appliquer_au_materiel(config or {}, m)
    if ecartee and m.moteur == "openvino" and (m.peripherique_openvino or "CPU").upper() != "CPU":
        effet = {**effet, "indisponible": True, "ecartee": True}
        m.moteur, m.peripherique_openvino = "ctranslate2", ""
    return m, effet


def calcul_prevu(config: dict, mat: Materiel, ecartee: bool = False, modele: str | None = None) -> Materiel:
    """Ce qui calculera la prochaine file avec cette configuration, sur ce poste."""
    from . import config as config_module

    m, _effet = poste(config, mat, ecartee)
    if modele is None:
        modele = config_module.reglages_effectifs(config or {})["modele"]
    return materiel_du_calcul(m, forcer_demande(config), modele)


def annonce(config: dict, mat: Materiel, duree_audio: float = 3600.0, *, preset: str | None = None,
            rythme_choisi: str | None = None, diarisation: bool = False, ecartee: bool = False) -> float:
    """
    La durée annoncée pour `duree_audio` secondes avec cette configuration (ou
    ce preset à la place du sien) : modèle et faisceau du mode avancé compris,
    sur ce qui calculera vraiment, dans le rythme en service (ou `rythme_choisi`).
    Même calcul que le décompte de départ de la file (`traitement`) et que la
    fiche « ce que ça change ».
    """
    conf = dict(config or {})
    if preset is not None:
        conf["preset"] = preset
    m_poste, _effet = poste(conf, mat, ecartee)
    return annonce_sur(conf, m_poste, duree_audio, rythme_choisi=rythme_choisi, diarisation=diarisation)


def annonce_sur(conf: dict, m_poste: Materiel, duree_audio: float = 3600.0, *,
                rythme_choisi: str | None = None, diarisation: bool = False) -> float:
    """
    `annonce` sur un matériel dont le réglage du poste est déjà posé (ou
    supposé : proposition, fiche d'une hypothèse). Rien n'est relu.
    """
    from . import presets, rythme

    p = parametres(conf, m_poste)
    # Le rythme, lui, se décide sur le réglage du poste, comme `ouvrir_file`.
    choisi = rythme_choisi or rythme.retenu(conf, m_poste)
    return presets.estimer_annonce(duree_audio, p["preset"], p["materiel"], choisi, diarisation,
                                   modele_avance=p["modele_avance"], beam=p["beam"], lot=p["lot"])


def parametres(conf: dict, m_poste: Materiel) -> dict:
    """
    Ce que la file calculera, tel que l'estimation le lit : preset, matériel du
    calcul, modèle et faisceau du mode avancé, faisceau et lots imposés par le
    réglage du poste (`ouvrir_file`). La borne de lots d'un rythme n'y entre
    pas : le coefficient du rythme en tient lieu (`rythme.coefficient`). Le
    décompte de départ de la file, lui, lit les lots qui tournent, borne
    comprise (clé de mesure de ce fichier) : en Équilibré ou Discret sur le
    processeur, les deux peuvent différer d'une mesure à l'autre.
    """
    from . import config as config_module, presets

    reglages = config_module.reglages_effectifs(conf)
    prevu = materiel_du_calcul(m_poste, forcer_demande(conf), reglages["modele"])
    modele_avance, beam = avance_annonce(conf, reglages)
    faisceau = reglage_machine.faisceau_impose(conf, m_poste)
    if faisceau is not None and m_poste.moteur != "openvino":
        # Faisceau posé par la campagne (« --appliquer ») : CTranslate2 le prend.
        beam = faisceau
    lot = presets.taille_lot(reglages["preset"], m_poste)
    impose = reglage_machine.lot_impose(conf, m_poste)
    if impose is not None and lot:
        lot = impose
    return {"preset": reglages["preset"], "modele": reglages["modele"], "materiel": prevu,
            "modele_avance": modele_avance, "beam": beam, "lot": lot}


def avance_annonce(conf: dict, reglages: dict) -> tuple[str, int]:
    """Modèle et faisceau du mode avancé à passer à l'estimation, vides s'ils sont ceux du preset."""
    from . import presets

    p = presets.preset(reglages["preset"])
    beam = int(reglages["beam_size"] or 0)
    avance = bool(conf.get("mode_avance")) and (reglages["modele"] != p["modele"] or beam != p["beam_size"])
    return (reglages["modele"], beam) if avance else ("", 0)
