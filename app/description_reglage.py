"""
Ce que change un réglage, en lignes courtes et exactes.

La fiche « ce que ça change » de la fenêtre (bouton d'information à côté de la
qualité, du rythme, de l'adaptation automatique, du moteur) et la commande
`scribouille reglages decrire` lisent toutes deux `decrire`. Il n'y a pas
d'autre texte : un preset, un rythme ou un réglage du poste qui change change
la fiche avec lui.

Une seule source
----------------
`plan` refait, sur une COPIE de la configuration et du matériel, les décisions
de `traitement.FileTraitement.ouvrir_file` avec les mêmes fonctions : réglage
du poste (`reglage_machine.appliquer_au_materiel`), réglages du preset
(`config.reglages_effectifs`), lots (`presets.taille_lot`, `lot_impose`, borne
du rythme), faisceau (`faisceau_impose`, `moteur_openvino.faisceau_effectif`),
rythme (`rythme.retenu`, `bornes_chargement`, `bornes`, `pause`), moteur
(celui que `traitement.fabriquer_moteur` créerait), puis la garde de la
mémoire de `traiter_element` (`rythme.garde_memoire`, `besoin_memoire_go`) et
la durée annoncée partout (`presets.estimer_annonce`). La file n'en dépend
pas : ce module ne fait que lire, et `outils/verifier_fiches.py` compare la
fiche à ce que la vraie `ouvrir_file` pose, cas par cas.

Les chiffres de justesse ne viennent que des mesures que le dépôt possède
(`MESURES`), chacune avec ce sur quoi elle a été prise ; aucune mesure, aucune
ligne. Le vérificateur contrôle que chacune figure bien dans sa source (journal
des versions, en-têtes du code) et que la durée du corpus des réunions est
celle de son manifeste.

Rien n'est écrit, rien n'est appliqué, aucun modèle n'est chargé, aucun
téléchargement : la fiche se demande pendant une transcription sans la gêner.
Les lignes que le réglage du poste note d'habitude au journal en l'appliquant
ne sont pas notées pour une fiche (filtre propre au fil appelant).
"""

from __future__ import annotations

import copy
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass

from . import calibration, langues, presets, reglage_machine, rythme
from .materiel import Materiel

#: Clés de la configuration qu'une hypothèse peut changer.
CLES_CONFIG = ("preset", "rythme", "rythme_auto", "mode_avance", "modele_avance", "beam_size",
               "condition_on_previous_text", "forcer_processeur")

#: Processeur laissé libre en vitesse maximale quand la puce graphique Intel
#: calcule : seule mesure, sur un Core Ultra 5 225U (essai du PC du travail,
#: novembre 2026 ; voir `app/rythme.py` et le journal des versions).
LIBRE_PUCE_225U_PCT = 92


# ---------------------------------------------------------------------------
# Mesures de justesse que le dépôt possède
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Mesure:
    """Un taux d'erreur de mots mesuré, et ce sur quoi il l'a été."""

    #: Corpus : « extraits » (journal des versions 2.4.0 et 2.4.1), « reunions »
    #: (campagne de mesure), « openvino » (mise au point du moteur Intel).
    corpus: str
    moteur: str          # « ctranslate2 » ou « openvino »
    modele: str          # clé du catalogue
    faisceau: int
    lots: bool
    #: Taux d'erreur de mots en pour cent, par langue de l'extrait.
    valeurs: tuple[tuple[str, float], ...]
    #: Fichier du dépôt où le chiffre est écrit (contrôlé par le vérificateur).
    source: str


#: Toutes processeur : la carte NVIDIA et la puce graphique Intel n'ont aucune
#: mesure de justesse dans le dépôt (la machine de mesure n'en a pas).
MESURES: tuple[Mesure, ...] = (
    # Journal des versions, 2.4.0 et 2.4.1 : Ryzen 7 7800X3D, mêmes extraits.
    Mesure("extraits", "ctranslate2", "large-v3", 5, True, (("fr", 7.3), ("en", 8.9)), "CHANGELOG.md"),
    Mesure("extraits", "ctranslate2", "large-v3", 8, False, (("fr", 7.5), ("en", 9.2)), "CHANGELOG.md"),
    Mesure("extraits", "ctranslate2", presets.MODELE_TURBO, 5, True, (("fr", 8.3), ("en", 12.9)), "CHANGELOG.md"),
    Mesure("extraits", "ctranslate2", presets.MODELE_TURBO, 5, False, (("fr", 10.2), ("en", 11.4)), "CHANGELOG.md"),
    Mesure("extraits", "openvino", "large-v3", 1, False, (("fr", 8.5), ("en", 8.1)), "CHANGELOG.md"),
    Mesure("extraits", "openvino", presets.MODELE_TURBO, 1, False, (("fr", 8.3), ("en", 10.7)), "CHANGELOG.md"),
    # Campagne sur réunions publiques (app/adaptation.py, en-tête de la table).
    Mesure("reunions", "ctranslate2", "large-v3", 5, True, (("fr", 35.1),), "app/adaptation.py"),
    Mesure("reunions", "ctranslate2", presets.MODELE_TURBO, 5, True, (("fr", 35.2),), "app/adaptation.py"),
    Mesure("reunions", "openvino", presets.MODELE_TURBO, 1, False, (("fr", 33.1),), "app/adaptation.py"),
    # Mise au point d'OpenVINO (en-tête de app/moteur_openvino.py).
    Mesure("openvino", "openvino", "large-v3", 1, False, (("", 8.03),), "app/moteur_openvino.py"),
    Mesure("openvino", "openvino", "large-v3", 5, False, (("", 8.27),), "app/moteur_openvino.py"),
)

#: Corpus des réunions : extraits et réunions du manifeste, durée en minutes
#: (contrôlés contre `app/corpus_manifeste.py`).
REUNIONS = {"extraits": 20, "reunions": 10, "minutes": 22.8}

#: Ce que vaut un mot d'écart sur les extraits (journal des versions, 2.4.1).
POINT_PAR_MOT = {"fr": 0.25, "en": 0.37}


# ---------------------------------------------------------------------------
# Hypothèse : la configuration telle qu'un choix la laisserait
# ---------------------------------------------------------------------------

def reglage_ecrit(mat: Materiel, reglage: dict) -> dict:
    """
    Le réglage du poste tel que `reglage_machine.enregistrer` l'écrirait, sans
    rien écrire ni lever (le vérificateur compare les deux).
    """
    propre = {cle: reglage[cle] for cle in ("moteur", "peripherique", "fils", "lot", "faisceau")
              if cle in reglage and reglage[cle] is not None}
    if propre.get("moteur") not in reglage_machine.MOTEURS:
        propre["moteur"] = "ctranslate2"
    if propre["moteur"] == "openvino" and "faisceau" in propre:
        from . import moteur_openvino

        propre["faisceau"] = moteur_openvino.faisceau_effectif(
            str(propre.get("peripherique") or "CPU"), int(propre["faisceau"] or 1))
    propre["signature"] = calibration.signature_machine(mat)
    return propre


def choix_proposition(config: dict, mat: Materiel, proposition: dict) -> dict:
    """Le choix que « Appliquer » poserait pour une proposition (`adaptation.appliquer`)."""
    actuel = reglage_machine.lire(config, mat)
    nouveau = {k: v for k, v in actuel.items() if k in ("fils", "lot")}
    nouveau["moteur"] = proposition["moteur"]
    if proposition["moteur"] == "openvino":
        nouveau["peripherique"] = proposition.get("peripherique") or "CPU"
    if int(proposition.get("faisceau") or 0) > 0:
        nouveau["faisceau"] = int(proposition["faisceau"])
    return {"preset": proposition["preset"], "rythme": proposition.get("rythme") or "vitesse",
            "rythme_auto": bool(proposition.get("rythme_auto")), "reglage": nouveau}


def hypothese(config: dict, mat: Materiel, choix: dict | None = None) -> dict:
    """
    Copie de la configuration avec le choix posé. `choix["reglage"]` : None (ou
    absent) garde le réglage du poste, {} revient à l'automatique, un dict est
    écrit comme `reglage_machine.enregistrer` le ferait.
    """
    conf = copy.deepcopy(config or {})
    choix = choix or {}
    for cle in CLES_CONFIG:
        if cle in choix:
            conf[cle] = choix[cle]
    machine = choix.get("reglage")
    if machine is not None:
        conf[reglage_machine.CLE] = reglage_ecrit(mat, machine) if machine else {}
    return conf


# ---------------------------------------------------------------------------
# Le plan : ce que la file appliquerait
# ---------------------------------------------------------------------------

class _SansJournal(logging.Filter):
    """Écarte du journal les lignes du seul fil qui décrit (les autres passent)."""

    def __init__(self):
        super().__init__()
        self.fil = threading.get_ident()

    def filter(self, record: logging.LogRecord) -> bool:
        return threading.get_ident() != self.fil


@contextmanager
def _muet():
    journal = logging.getLogger("transcripteur")
    filtre = _SansJournal()
    journal.addFilter(filtre)
    reessai = reglage_machine.REESSAI_EN_COURS
    try:
        yield
    finally:
        journal.removeFilter(filtre)
        reglage_machine.REESSAI_EN_COURS = reessai


def _origine_fils(mat: Materiel) -> str:
    """Pourquoi ce nombre de fils en vitesse maximale (voir `Materiel.fils_calcul`)."""
    if mat.fils_imposes > 0:
        return "banc"
    topo = mat.topologie
    if topo.hybride and topo.basse_consommation and topo.coeurs_principaux:
        return "hybride"
    total = mat.coeurs_logiques or 0
    if 0 < mat.coeurs_physiques < total:
        return "physiques"
    return "moins_deux"


def plan(config: dict, mat: Materiel, choix: dict | None = None) -> dict:
    """
    Ce que `ouvrir_file` (puis `traiter_element`) appliquerait avec ce choix,
    sur ce poste. Rien n'est modifié : ni la configuration, ni le matériel.
    """
    conf = hypothese(config, mat, choix)
    choix = choix or {}
    m = copy.copy(mat)
    from . import config as config_module

    with _muet():
        effet = reglage_machine.appliquer_au_materiel(conf, m)
        if effet.get("plantage") and choix.get("leve_suspension"):
            # « Appliquer » une proposition ou un conseil d'OpenVINO lève la
            # suspension (`reglage_machine.enregistrer` efface le témoin) : la
            # file ouvrirait alors la puce, si elle est là.
            from . import moteur_openvino

            peripherique = str(effet["plantage"]).upper()
            if (not reglage_machine.PUCE_ECARTEE and moteur_openvino.installe()
                    and peripherique in moteur_openvino.peripheriques_disponibles()):
                m.moteur, m.peripherique_openvino = "openvino", peripherique
                effet = {k: v for k, v in effet.items() if k not in ("indisponible", "plantage", "puce")}
                effet["suspension_levee"] = True
        reglages = config_module.reglages_effectifs(conf)
        lot_preset = presets.taille_lot(reglages["preset"], m)
        lot = lot_preset
        impose = reglage_machine.lot_impose(conf, m)
        if impose is not None and lot:
            lot = impose
        faisceau_poste = reglage_machine.faisceau_impose(conf, m)
    beam = int(reglages["beam_size"] or 0)
    faisceau_ov = 1
    if faisceau_poste is not None:
        if m.moteur == "openvino":
            faisceau_ov = faisceau_poste
        else:
            beam = faisceau_poste
    choisi = rythme.retenu(conf, m)
    auto_demande = bool(conf.get("rythme_auto"))
    auto = auto_demande and choisi != "vitesse"
    charge = rythme.bornes_chargement(choisi, auto_demande, m)
    lot_avant_rythme = lot
    if charge.lot_max is not None and lot:
        lot = min(int(lot), charge.lot_max)

    modele = reglages["modele"]
    forcer = bool(reglages["forcer_processeur"])
    sur_openvino = m.moteur == "openvino" and not forcer
    depot = ""
    sans_equivalent = False
    if sur_openvino:
        from . import moteur

        depot = presets.depot_openvino(modele) or (modele if moteur.est_modele_openvino(modele) else "")
        sans_equivalent = not depot
    if sur_openvino and depot:
        from . import moteur_openvino

        peripherique = (m.peripherique_openvino or "CPU").upper()
        moteur_calcul, calcule = "openvino", depot
        faisceau = moteur_openvino.faisceau_effectif(peripherique, faisceau_ov)
        faisceau_demande = max(1, int(faisceau_ov or 1))
        precision = "int8"
        lots = 0
        sur_puce = peripherique != "CPU"
    else:
        # CTranslate2 : forcé, réglé, ou repli d'OpenVINO pour un modèle sans
        # version OpenVINO (`MoteurAvecRepli` ouvre alors son CTranslate2).
        peripherique = "cpu" if forcer else m.peripherique
        moteur_calcul, calcule = "ctranslate2", modele
        faisceau = faisceau_demande = max(1, beam or 5)
        precision = "float16" if peripherique == "cuda" else "int8"
        lots = int(lot or 0)
        sur_puce = False
    par_lots = moteur_calcul == "ctranslate2" and lots > 1 and bool(reglages["vad"])

    proprietes: dict = {}
    if (charge.rythme != "vitesse" or auto) and m.moteur == "openvino":
        proprietes = dict(charge.ov_puce if (m.peripherique_openvino or "CPU").upper() != "CPU"
                          else charge.ov_processeur)
    if moteur_calcul != "openvino":
        proprietes = {}
    occupe = rythme.bornes(choisi, m)

    # Garde de la mémoire, au départ de chaque fichier (`traiter_element`).
    garde = None
    if choisi != "vitesse":
        nom_moteur = "openvino" if m.moteur == "openvino" else "ctranslate2"
        garde = {"moteur": nom_moteur, "marge_go": rythme.MARGE_MEMOIRE_GO,
                 "lots_sous_go": (round(rythme.besoin_memoire_go(nom_moteur, modele, lots)
                                        + rythme.MARGE_MEMOIRE_GO, 1) if lots > 1 else None),
                 "modele_sous_go": (round(rythme.besoin_memoire_go(nom_moteur, modele, 0)
                                          + rythme.MARGE_MEMOIRE_GO, 1)
                                    if modele in ("large-v3", "large-v2") else None),
                 "modele_leger": presets.MODELE_TURBO if not conf.get("mode_avance") else ""}

    # Durée annoncée : la même que les cartes des presets et le bandeau
    # (`pour_une_heure`), sur la copie du matériel ; mode avancé : celle de la
    # file (`traiter_element`). Forcer le processeur : la durée du processeur.
    m_duree = m
    if forcer and m.cle_calcul != "cpu":
        m_duree = copy.copy(m)
        m_duree.moteur, m_duree.peripherique_openvino, m_duree.cuda_disponible = "ctranslate2", "", False
    avance = bool(conf.get("mode_avance")) and (
        modele != presets.preset(reglages["preset"])["modele"]
        or int(reglages["beam_size"] or 0) != presets.preset(reglages["preset"])["beam_size"])
    modele_avance = modele if avance else ""
    beam_annonce = int(reglages["beam_size"] or 0) if avance else 0
    secondes = presets.estimer_annonce(3600, reglages["preset"], m_duree, choisi,
                                       modele_avance=modele_avance, beam=beam_annonce)
    vitesse_s = presets.estimer_annonce(3600, reglages["preset"], m_duree, "vitesse",
                                        modele_avance=modele_avance, beam=beam_annonce)
    duree = _source_duree(reglages["preset"], m_duree, modele_avance, beam_annonce)
    coefficient = rythme.coefficient(choisi, m_duree.cle_calcul)
    famille = "puce" if m_duree.cle_calcul in ("openvino-gpu", "openvino-npu", "cuda") else "processeur"
    try:
        mesure_rythme = float(((rythme._mesures().get(famille) or {}).get(choisi) or 0))
    except (TypeError, ValueError, AttributeError):
        mesure_rythme = 0.0

    memoire = None
    if peripherique != "cuda":
        famille_modele = ("large-v3" if modele in ("large-v3", "large-v2")
                          else "turbo" if modele == presets.MODELE_TURBO else "")
        if famille_modele:
            memoire = {"go": rythme.besoin_memoire_go(moteur_calcul, modele, lots),
                       "famille": famille_modele, "lots": lots > 1,
                       "valeur_de": "large-v3" if modele == "large-v2" else ""}

    return {
        "choix": {k: choix.get(k) for k in ("preset", "rythme", "rythme_auto", "reglage") if k in choix},
        "preset": reglages["preset"],
        "preset_nom": reglages["preset_nom"],
        "modele": modele,
        "modele_calcule": calcule,
        "moteur": moteur_calcul,
        "moteur_poste": m.moteur,
        "peripherique": peripherique,
        "sur_puce": sur_puce,
        "precision": precision,
        "faisceau": faisceau,
        "faisceau_demande": faisceau_demande,
        "faisceau_poste": faisceau_poste,
        "lots": lots,
        "lots_preset": int(presets.preset(reglages["preset"]).get("lot") or 0),
        "lots_memoire_vive": lot_preset == 0 and int(presets.preset(reglages["preset"]).get("lot") or 0) > 1,
        "lots_banc": impose if (impose is not None and lot_preset) else None,
        "lots_avant_rythme": int(lot_avant_rythme or 0),
        "lots_rythme": charge.lot_max if (charge.lot_max is not None and lot_avant_rythme
                                          and lots < int(lot_avant_rythme)) else None,
        "par_lots": par_lots,
        "vad": bool(reglages["vad"]),
        "texte_precedent": (False if par_lots or moteur_calcul == "openvino"
                     else bool(reglages["condition_on_previous_text"])),
        "repli_temperature": moteur_calcul == "ctranslate2" and not par_lots,
        "confiance_mots": moteur_calcul == "ctranslate2",
        "forcer_processeur": forcer,
        "sans_equivalent_openvino": sans_equivalent,
        "effet": {k: v for k, v in effet.items()
                  if k in ("indisponible", "plantage", "ecartee", "reessai", "suspension_levee")},
        "mode_avance": bool(conf.get("mode_avance")),
        "rythme": {
            "choisi": choisi,
            "selon_moteur": conf.get("rythme") not in rythme.RYTHMES,
            "auto": auto,
            "auto_demande": auto_demande,
            "fils": charge.fils,
            "fils_vitesse": rythme.bornes("vitesse", m).fils,
            "fils_origine": _origine_fils(m),
            "logiques": m.coeurs_logiques or 0,
            "priorite": occupe.priorite,
            "qos": occupe.qos,
            "priorite_es": occupe.priorite_es,
            "affinite": list(occupe.affinite) if not auto else [],
            "proprietes_openvino": proprietes,
            "pause": rythme.pause(choisi, sur_puce, auto),
            "attente_passive": choisi != "vitesse" and moteur_calcul == "ctranslate2",
            "lot_max": charge.lot_max,
            "leger": not auto and choisi == "vitesse",
        },
        "garde_memoire": garde,
        "cout": {
            "secondes": round(secondes, 1),
            "pour_une_heure": presets.formater_duree(secondes),
            "vitesse_secondes": round(vitesse_s, 1),
            "vitesse_pour_une_heure": presets.formater_duree(vitesse_s),
            **duree,
            "coefficient_rythme": round(coefficient, 3),
            "coefficient_mesure": choisi != "vitesse" and mesure_rythme >= 1.0,
            "memoire": memoire,
            "libre_puce_pct": (LIBRE_PUCE_225U_PCT if sur_puce and peripherique == "GPU"
                               and choisi == "vitesse" and not auto else None),
        },
    }


def _source_duree(cle_preset: str, mat: Materiel, modele_avance: str, beam: int) -> dict:
    """
    D'où vient la durée annoncée : mesure du poste (et son poids), ou facteur
    de repli. Mêmes paramètres que `presets._facteur_mesure_pondere`.
    """
    modele = presets.modele_du_preset(cle_preset, modele_avance)
    lot = presets.taille_lot(cle_preset, mat)
    faisceau = beam or presets.preset(cle_preset)["beam_size"]
    if mat.cle_calcul.startswith("openvino"):
        faisceau, lot = 1, 0
    facteur, poids = calibration.mesure_et_confiance(modele, mat.cle_calcul, faisceau, mat, lot)
    minutes, expres = 0.0, False
    if facteur:
        donnees = calibration.charger(calibration.signature_machine(mat))
        entree = calibration._entree(donnees, modele, mat.cle_calcul, faisceau, lot) or {}
        for ligne in (entree.get("historique") or [])[:calibration.MESURES_RETENUES]:
            try:
                minutes += max(0.0, float(ligne.get("duree", 0))) / 60.0
                expres = expres or bool(ligne.get("expres"))
            except (AttributeError, TypeError, ValueError):
                continue
    source = "estimation" if not facteur else ("mesure_expres" if poids >= 1.0 else "mesure")
    return {"source": source, "facteur_mesure": round(facteur, 3), "poids_mesure": round(poids, 3),
            "minutes_mesurees": round(minutes, 1), "mesure_expres": expres}


# ---------------------------------------------------------------------------
# Les lignes, dans la langue de l'interface
# ---------------------------------------------------------------------------

def _nom_rythme(nom: str) -> str:
    texte = langues.t(f"rythme.nom.{nom}")
    return texte[:1].upper() + texte[1:]


def _pct(valeur: float) -> str:
    return langues.nombre(valeur, 2 if round(valeur, 1) != valeur else 1)


def _mesures_pour(p: dict) -> list[tuple[Mesure, str]]:
    """Mesures du réglage décrit : exactes, ou voisines (autre faisceau, autres lots), dites comme telles."""
    retenues: list[tuple[Mesure, str]] = []
    for corpus in ("extraits", "reunions", "openvino"):
        candidates = [x for x in MESURES if x.corpus == corpus and x.moteur == p["moteur"]
                      and x.modele == p["modele"]]
        exacte = [x for x in candidates if x.faisceau == p["faisceau"] and x.lots == p["par_lots"]]
        if exacte:
            retenues.append((exacte[0], "exacte"))
            continue
        voisines = [x for x in candidates if x.lots == p["par_lots"]] or candidates
        if voisines:
            retenues.append((voisines[0], "voisine"))
    return retenues


def _valeurs(mesure: Mesure) -> str:
    t = langues.t
    morceaux = []
    for langue, valeur in mesure.valeurs:
        if langue:
            morceaux.append(t(f"fiche.just.langue.{langue}", pct=_pct(valeur)))
        else:
            morceaux.append(t("fiche.just.pct", pct=_pct(valeur)))
    return t("fiche.just.et").join(morceaux)


def _mesure(corpus: str, moteur: str, modele: str, faisceau: int, lots: bool) -> Mesure | None:
    return next((x for x in MESURES if (x.corpus, x.moteur, x.modele, x.faisceau, x.lots)
                 == (corpus, moteur, modele, faisceau, lots)), None)


def _court(mesure: Mesure | None) -> str:
    """« 7,3 % et 8,9 % » : les valeurs seules, dans l'ordre des langues."""
    if mesure is None:
        return "?"
    return langues.t("fiche.just.et_court").join(langues.t("fiche.just.pct_court", pct=_pct(v))
                                                 for _l, v in mesure.valeurs)


def _ligne(cle: str, libelle: str, valeur: str) -> dict:
    return {"cle": cle, "libelle": libelle, "valeur": valeur}


def sections(p: dict) -> list[dict]:
    """Les sections de la fiche : titre et lignes (libellé, valeur), déjà traduites."""
    t = langues.t
    r = p["rythme"]
    c = p["cout"]
    sorties: list[dict] = []

    # -- ce qui calcule ---------------------------------------------------
    calcul: list[dict] = []
    from . import moteur

    nom = moteur.nom_court(p["modele"])
    calcul.append(_ligne("modele", t("fiche.calcul.modele"),
                         nom if p["modele_calcule"] == p["modele"]
                         else t("fiche.calcul.modele_fichier", nom=nom, fichier=p["modele_calcule"])))
    if p["moteur"] == "openvino":
        calcul.append(_ligne("moteur", t("fiche.calcul.moteur"), t("fiche.moteur.openvino")))
    else:
        calcul.append(_ligne("moteur", t("fiche.calcul.moteur"), t("fiche.moteur.ctranslate2")))
    calcul.append(_ligne("peripherique", t("fiche.calcul.sur"), t(f"fiche.sur.{p['peripherique'].lower()}")))
    if p["effet"].get("indisponible"):
        calcul.append(_ligne("indisponible", t("fiche.calcul.attention"),
                             t("fiche.calcul.ov_suspendu" if p["effet"].get("plantage")
                               else "fiche.calcul.ov_ecarte" if p["effet"].get("ecartee")
                               else "fiche.calcul.ov_absent")))
    if p["effet"].get("suspension_levee"):
        calcul.append(_ligne("suspension", t("fiche.calcul.attention"), t("fiche.calcul.suspension_levee")))
    if p["sans_equivalent_openvino"]:
        calcul.append(_ligne("sans_equivalent", t("fiche.calcul.attention"), t("fiche.calcul.sans_equivalent")))
    if p["forcer_processeur"] and p["moteur_poste"] == "openvino":
        calcul.append(_ligne("force", t("fiche.calcul.attention"), t("fiche.calcul.force")))
    calcul.append(_ligne("precision", t("fiche.calcul.precision"), t(f"fiche.precision.{p['precision']}")))
    if p["faisceau"] > 1:
        valeur = t("fiche.faisceau.large", n=p["faisceau"])
    else:
        valeur = t("fiche.faisceau.glouton")
    if p["faisceau"] < p["faisceau_demande"]:
        valeur += " " + t("fiche.faisceau.ramene", n=p["faisceau_demande"])
    elif p["moteur"] == "openvino" and p["sur_puce"]:
        valeur += " " + t("fiche.faisceau.impose_puce")
    elif p["faisceau_poste"] is not None:
        valeur += " " + t("fiche.faisceau.poste")
    calcul.append(_ligne("faisceau", t("fiche.calcul.faisceau"), valeur))
    if p["moteur"] == "openvino":
        calcul.append(_ligne("lots", t("fiche.calcul.lots"), t("fiche.lots.fenetres")))
    elif p["par_lots"]:
        valeur = t("fiche.lots.n", n=p["lots"])
        if p["lots_rythme"]:
            valeur += " " + t("fiche.lots.borne_rythme", n=p["lots_rythme"], avant=p["lots_avant_rythme"],
                                  rythme=_nom_rythme(r["choisi"]))
        elif p["lots_banc"] is not None:
            valeur += " " + t("fiche.lots.banc")
        calcul.append(_ligne("lots", t("fiche.calcul.lots"), valeur))
    else:
        raison = ("fiche.lots.un_memoire" if p["lots_memoire_vive"]
                  else "fiche.lots.un_rythme" if r["lot_max"] == 0 and p["lots_preset"] > 1
                  else "fiche.lots.un_banc" if p["lots_banc"] == 0
                  else "fiche.lots.un")
        calcul.append(_ligne("lots", t("fiche.calcul.lots"),
                             t(raison, go=langues.nombre(presets.SEUIL_MEMOIRE_LOTS, 0),
                               rythme=_nom_rythme(r["choisi"]))))
    if p["vad"]:
        calcul.append(_ligne("vad", t("fiche.calcul.decoupage"), t("fiche.decoupage.vad")))
    if p["moteur"] == "openvino":
        calcul.append(_ligne("contexte", t("fiche.calcul.contexte"), t("fiche.precedent.openvino")))
        calcul.append(_ligne("garde", t("fiche.calcul.boucles"),
                             t("fiche.boucles.puce" if p["sur_puce"] else "fiche.boucles.processeur")))
        calcul.append(_ligne("repli", t("fiche.calcul.repli"), t("fiche.repli.ctranslate2")))
    elif p["par_lots"]:
        calcul.append(_ligne("contexte", t("fiche.calcul.contexte"), t("fiche.precedent.lots")))
    else:
        calcul.append(_ligne("contexte", t("fiche.calcul.contexte"),
                             t("fiche.precedent.un_a_un" if p["texte_precedent"] else "fiche.precedent.un_a_un_sans")))
    calcul.append(_ligne("confiance", t("fiche.calcul.confiance"),
                         t("fiche.confiance.oui" if p["confiance_mots"] else "fiche.confiance.non")))
    sorties.append({"cle": "calcul", "titre": t("fiche.section.calcul"), "lignes": calcul})

    # -- le rythme ----------------------------------------------------------
    lignes: list[dict] = []
    choisi = r["choisi"]
    lignes.append(_ligne("bref", t("fiche.rythme.bref"), t(f"fiche.bref.{choisi}")))
    sur_processeur = not p["sur_puce"] and p["peripherique"] != "cuda"
    if p["moteur"] == "openvino" and not p["sur_puce"] and not r["proprietes_openvino"].get("INFERENCE_NUM_THREADS"):
        fils = t("fiche.fils.openvino")
    elif p["sur_puce"]:
        fils = t("fiche.fils.puce", n=r["fils"])
    elif p["peripherique"] == "cuda":
        fils = t("fiche.fils.cuda", n=r["fils"])
    else:
        fils = t("fiche.fils.n", n=r["fils"], logiques=r["logiques"] or "?")
        if choisi == "vitesse" or r["auto"]:
            fils += " " + t(f"fiche.fils.origine.{r['fils_origine']}")
        elif choisi == "equilibre":
            fils += " " + t("fiche.fils.equilibre")
        else:
            fils += " " + t("fiche.fils.discret_efficaces" if r["affinite"] else "fiche.fils.discret")
    lignes.append(_ligne("fils", t("fiche.rythme.fils"), fils))
    if r["leger"]:
        lignes.append(_ligne("priorite", t("fiche.rythme.priorite"), t("fiche.priorite.normale")))
        lignes.append(_ligne("qos", t("fiche.rythme.qos"), t("fiche.qos.haute")))
        lignes.append(_ligne("reste", t("fiche.rythme.pauses"), t("fiche.vitesse.rien")))
        lignes.append(_ligne("poste", t("fiche.rythme.poste"),
                             t("fiche.vitesse.poste_processeur" if sur_processeur else "fiche.vitesse.poste_puce")))
    else:
        etat = "fiche.rythme.occupe" if r["auto"] else ""
        prefixe = (t(etat) + " ") if etat else ""
        lignes.append(_ligne("priorite", t("fiche.rythme.priorite"), prefixe + t(f"fiche.priorite.{r['priorite']}")))
        lignes.append(_ligne("qos", t("fiche.rythme.qos"), prefixe + t(f"fiche.qos.{r['qos']}")))
        if r["priorite_es"] == "basse":
            lignes.append(_ligne("es", t("fiche.rythme.es"), prefixe + t("fiche.es.basse")))
        if r["affinite"]:
            lignes.append(_ligne("affinite", t("fiche.rythme.affinite"),
                                 t("fiche.affinite.efficaces", n=len(r["affinite"]))))
        if r["attente_passive"]:
            lignes.append(_ligne("omp", t("fiche.rythme.attente"), t("fiche.attente.passive")))
        if r["proprietes_openvino"]:
            texte = ", ".join(f"{k}={v}" for k, v in sorted(r["proprietes_openvino"].items()))
            lignes.append(_ligne("ov", t("fiche.rythme.openvino"), t("fiche.openvino.proprietes", liste=texte)))
        if r["pause"] > 0:
            lignes.append(_ligne("pause", t("fiche.rythme.pauses"),
                                 prefixe + t("fiche.pause.puce" if p["sur_puce"] else "fiche.pause.processeur",
                                             pct=langues.nombre(r["pause"] * 100, 0))))
        elif not r["auto"]:
            lignes.append(_ligne("pause", t("fiche.rythme.pauses"), t("fiche.pause.aucune")))
        if r["auto"]:
            lignes.append(_ligne("auto", t("fiche.rythme.auto"), t("fiche.auto.quand", minutes=int(
                rythme.SEUIL_INACTIVITE_S // 60), entree=int(rythme.SEUIL_CHARGE_ENTREE),
                secondes=langues.nombre(rythme.INTERVALLE_S, 0))))
            lignes.append(_ligne("auto_libre", t("fiche.rythme.auto_libre"), t("fiche.auto.libre")))
            lignes.append(_ligne("auto_fixe", t("fiche.rythme.auto_fixe"), t(
                "fiche.auto.fixe_puce" if p["sur_puce"] else "fiche.auto.fixe", n=r["fils"])))
        g = p["garde_memoire"]
        if g:
            morceaux = []
            if g["lots_sous_go"]:
                morceaux.append(t("fiche.garde.lots", go=langues.nombre(g["lots_sous_go"], 1)))
            if g["modele_sous_go"] and g["modele_leger"]:
                morceaux.append(t("fiche.garde.modele", go=langues.nombre(g["modele_sous_go"], 1),
                                  leger=moteur.nom_court(g["modele_leger"])))
            if morceaux:
                lignes.append(_ligne("garde", t("fiche.rythme.garde"), " ; ".join(morceaux)))
    if r["auto_demande"] and choisi == "vitesse":
        lignes.append(_ligne("auto", t("fiche.rythme.auto"), t("fiche.auto.inutile")))
    sorties.append({"cle": "rythme", "titre": t("fiche.section.rythme", rythme=_nom_rythme(choisi)),
                    "lignes": lignes})

    # -- le coût sur ce poste ----------------------------------------------
    cout: list[dict] = []
    cout.append(_ligne("duree", t("fiche.cout.duree"), t("fiche.cout.duree_valeur", duree=c["pour_une_heure"])))
    if c["source"] == "estimation":
        source = t("fiche.cout.estimation")
    elif c["source"] == "mesure_expres":
        source = t("fiche.cout.mesure_expres")
    else:
        source = t("fiche.cout.mesure", minutes=langues.nombre(c["minutes_mesurees"], 0),
                   poids=langues.nombre(c["poids_mesure"] * 100, 0))
    cout.append(_ligne("source", t("fiche.cout.source"), source))
    if choisi != "vitesse":
        cout.append(_ligne("rythme", t("fiche.cout.rythme"), t(
            "fiche.cout.coef_mesure" if c["coefficient_mesure"] else "fiche.cout.coef_repli",
            coef=langues.nombre(c["coefficient_rythme"], 2), rythme=_nom_rythme(choisi))))
        if r["auto"]:
            cout.append(_ligne("libre", t("fiche.cout.libre"), t("fiche.cout.si_libre", duree=c["vitesse_pour_une_heure"])))
    mem = c["memoire"]
    if mem:
        cle = "fiche.memoire.lots" if mem["lots"] else "fiche.memoire.un"
        valeur = t(cle, go=langues.nombre(mem["go"], 1))
        if mem["valeur_de"]:
            valeur += " " + t("fiche.memoire.valeur_de")
        cout.append(_ligne("memoire", t("fiche.cout.memoire"), valeur))
    elif p["peripherique"] == "cuda":
        cout.append(_ligne("memoire", t("fiche.cout.memoire"), t("fiche.memoire.carte")))
    else:
        cout.append(_ligne("memoire", t("fiche.cout.memoire"), t("fiche.memoire.inconnue")))
    if c["libre_puce_pct"]:
        cout.append(_ligne("processeur", t("fiche.cout.processeur"),
                           t("fiche.processeur.puce_225u", pct=c["libre_puce_pct"])))
    elif sur_processeur and r["logiques"] and not (p["moteur"] == "openvino" and not r["proprietes_openvino"]):
        cout.append(_ligne("processeur", t("fiche.cout.processeur"),
                           t("fiche.processeur.fils", n=r["fils"], logiques=r["logiques"],
                             libres=max(0, r["logiques"] - r["fils"]))))
    if p["moteur"] == "openvino" and p["sur_puce"]:
        cout.append(_ligne("compilation", t("fiche.cout.premier"), t("fiche.cout.compilation")))
    sorties.append({"cle": "cout", "titre": t("fiche.section.cout"), "lignes": cout})

    # -- justesse mesurée ---------------------------------------------------
    just: list[dict] = []
    for mesure, nature in _mesures_pour(p):
        libelle = t(f"fiche.just.lib.{mesure.corpus}")
        if mesure.corpus == "reunions":
            corpus = t("fiche.just.reunions", extraits=REUNIONS["extraits"], reunions=REUNIONS["reunions"],
                       minutes=langues.nombre(REUNIONS["minutes"], 1))
        else:
            corpus = t(f"fiche.just.{mesure.corpus}")
        valeur = _valeurs(mesure)
        details = []
        if nature == "voisine":
            details.append(t("fiche.just.voisine", faisceau=mesure.faisceau,
                             lots=t("fiche.just.par_lots" if mesure.lots else "fiche.just.un_a_un")))
        if p["peripherique"] not in ("cpu", "CPU"):
            details.append(t("fiche.just.sur_processeur"))
        if details:
            valeur += " (" + ", ".join(details) + ")"
        reference = [x for x in MESURES if x.corpus == mesure.corpus and x.moteur == "ctranslate2"
                     and x.modele == "large-v3" and x.faisceau == 5 and x.lots]
        if reference and reference[0] != mesure:
            valeur += t("fiche.just.contre_qualite", valeurs=_valeurs(reference[0]))
        if mesure.corpus == "reunions":
            meilleur = min((x for x in MESURES if x.corpus == "reunions"), key=lambda x: x.valeurs[0][1])
            if meilleur != mesure and meilleur not in reference:
                valeur += t("fiche.just.meilleur_reunions", pct=_pct(meilleur.valeurs[0][1]))
        valeur += t("fiche.just.mesure_sur", corpus=corpus)
        just.append(_ligne(f"justesse_{mesure.corpus}", libelle, valeur))
    if any(m.corpus == "extraits" for m, _ in _mesures_pour(p)):
        just.append(_ligne("echelle", t("fiche.just.echelle"), t(
            "fiche.just.un_mot", fr=langues.nombre(POINT_PAR_MOT["fr"], 2), en=langues.nombre(POINT_PAR_MOT["en"], 2))))
    if not just:
        just.append(_ligne("aucune", t("fiche.just.titre_aucune"), t("fiche.just.aucune")))
    sorties.append({"cle": "justesse", "titre": t("fiche.section.justesse"), "lignes": just})

    # -- ce qui est allégé pour gagner du temps -----------------------------
    allege: list[dict] = []
    if p["moteur"] == "ctranslate2":
        if p["faisceau"] == 5 and p["par_lots"] and p["modele"] == "large-v3":
            allege.append(_ligne("allege_faisceau", t("fiche.allege.faisceau"), t("fiche.allege.faisceau_5")))
        if p["par_lots"] and p["modele"] in ("large-v3", presets.MODELE_TURBO):
            turbo = p["modele"] == presets.MODELE_TURBO
            lots = _mesure("extraits", "ctranslate2", p["modele"], 5, True)
            un = _mesure("extraits", "ctranslate2", p["modele"], 5 if turbo else 8, False)
            if lots and un:
                allege.append(_ligne("allege_lots", t("fiche.allege.lots"), t(
                    "fiche.allege.lots_turbo" if turbo else "fiche.allege.lots_mesure",
                    lots=_court(lots), un=_court(un))))
        allege.append(_ligne("allege_precision", t("fiche.allege.precision"),
                             t("fiche.allege.precision_non_mesuree", precision=p["precision"])))
    else:
        glouton = _mesure("openvino", "openvino", "large-v3", 1, False)
        faisceau = _mesure("openvino", "openvino", "large-v3", 5, False)
        if p["sur_puce"]:
            allege.append(_ligne("allege_faisceau", t("fiche.allege.faisceau"), t(
                "fiche.allege.glouton_puce", glouton=_court(glouton), faisceau=_court(faisceau))))
        elif p["faisceau"] == 1:
            allege.append(_ligne("allege_faisceau", t("fiche.allege.faisceau"), t(
                "fiche.allege.glouton_processeur", glouton=_court(glouton), faisceau=_court(faisceau))))
        allege.append(_ligne("allege_precision", t("fiche.allege.precision"), t("fiche.allege.precision_openvino")))
    if p["modele"] == presets.MODELE_TURBO:
        allege.append(_ligne("allege_modele", t("fiche.allege.modele"), t("fiche.allege.turbo")))
    if p["garde_memoire"] and p["garde_memoire"].get("modele_sous_go") and p["garde_memoire"].get("modele_leger"):
        allege.append(_ligne("allege_garde", t("fiche.allege.memoire"), t("fiche.allege.garde")))
    sorties.append({"cle": "allege", "titre": t("fiche.section.allege"), "lignes": allege})
    return sorties


def verdict(p: dict) -> str:
    """Une phrase en tête de fiche : ce que ce réglage vise."""
    t = langues.t
    if p["modele"] == "large-v3" and (p["moteur"] == "openvino" or p["faisceau"] >= 5):
        texte = t("fiche.verdict.qualite")
        if p["garde_memoire"] and p["garde_memoire"].get("modele_sous_go") and p["garde_memoire"].get("modele_leger"):
            texte += " " + t("fiche.verdict.qualite_rythme")
        return texte
    if p["modele"] == presets.MODELE_TURBO:
        return t("fiche.verdict.rapide")
    return t("fiche.verdict.autre")


def decrire(config: dict, mat: Materiel, choix: dict | None = None, sujet: str = "") -> dict:
    """
    La fiche complète : le plan (structuré) et ses sections traduites. Pour un
    rythme (ou l'adaptation), le rythme passe en tête et l'en-tête dit ce
    qu'il vise ; les mêmes lignes, dans un autre ordre.
    """
    p = plan(config, mat, choix)
    p["verdict"] = verdict(p)
    p["sections"] = sections(p)
    if sujet in ("rythme", "auto"):
        bref = next((s for s in p["sections"] if s["cle"] == "rythme"), None)
        if bref and bref["lignes"] and bref["lignes"][0]["cle"] == "bref":
            texte_bref = bref["lignes"].pop(0)["valeur"]
            p["verdict"] = texte_bref[:1].upper() + texte_bref[1:] + "."
        ordre = ("rythme", "cout", "calcul", "justesse", "allege")
        p["sections"].sort(key=lambda s: ordre.index(s["cle"]) if s["cle"] in ordre else len(ordre))
    p["titre"] = langues.t("fiche.titre", preset=p["preset_nom"], rythme=_nom_rythme(p["rythme"]["choisi"]))
    return p


SUJETS = ("actuel", "preset", "rythme", "auto", "proposition", "banc", "automatique", "forcer", "avance")


def choix_du_sujet(config: dict, mat: Materiel, sujet: str, valeur=None,
                   proposition: dict | None = None) -> tuple[dict, str, list[dict]]:
    """
    Le choix décrit par un bouton d'information de la fenêtre (ou un mot de
    `reglages decrire`), la phrase qui dit dans quel cadre, et les autres
    choix du même groupe (pour passer de l'un à l'autre dans la fiche).
    """
    t = langues.t
    preset_actuel = presets.preset(config.get("preset", presets.PRESET_DEFAUT))["cle"]
    m = copy.copy(mat)
    with _muet():
        reglage_machine.appliquer_au_materiel(config, m)
    rythme_actuel = rythme.retenu(config, m)
    groupe_presets = [{"sujet": "preset", "valeur": cle, "nom": presets.nom_preset(cle)} for cle in presets.PRESETS]
    groupe_rythmes = [{"sujet": "rythme", "valeur": nom, "nom": _nom_rythme(nom)} for nom in rythme.RYTHMES]
    groupe_rythmes.append({"sujet": "auto", "valeur": None, "nom": t("fiche.choix.auto")})
    if sujet == "preset":
        cle = valeur if valeur in presets.PRESETS else preset_actuel
        return ({"preset": cle}, t("fiche.contexte.preset", rythme=_nom_rythme(rythme_actuel)), groupe_presets)
    if sujet == "rythme":
        nom = valeur if valeur in rythme.RYTHMES else rythme_actuel
        auto = bool(config.get("rythme_auto")) and nom != "vitesse"
        return ({"rythme": nom}, t("fiche.contexte.rythme_auto" if auto else "fiche.contexte.rythme",
                                   preset=presets.nom_preset(preset_actuel)), groupe_rythmes)
    if sujet == "auto":
        nom = rythme_actuel if rythme_actuel != "vitesse" else rythme.RYTHMES[1]
        cle = "fiche.contexte.auto" if rythme_actuel != "vitesse" else "fiche.contexte.auto_vitesse"
        return ({"rythme": nom, "rythme_auto": True}, t(cle, rythme=_nom_rythme(nom),
                                                         preset=presets.nom_preset(preset_actuel)), groupe_rythmes)
    if sujet == "proposition":
        if proposition is None:
            from . import adaptation

            proposition = adaptation.proposition_du_poste(mat)
        choix = choix_proposition(config, mat, proposition)
        choix["leve_suspension"] = proposition["moteur"] == "openvino"
        return choix, t("fiche.contexte.proposition", resume=proposition.get("resume", "")), []
    if sujet == "banc":
        from . import banc

        conseil = banc.dernier_conseil()
        if not conseil:
            return {}, t("fiche.contexte.sans_banc"), []
        return ({"reglage": dict(conseil), "leve_suspension": conseil.get("moteur") == "openvino"},
                t("fiche.contexte.banc"), [])
    if sujet == "automatique":
        return {"reglage": {}}, t("fiche.contexte.automatique"), []
    if sujet == "forcer":
        return ({"mode_avance": True, "forcer_processeur": True}, t("fiche.contexte.forcer"), [])
    if sujet == "avance":
        return {"mode_avance": True}, t("fiche.contexte.avance"), []
    return {}, t("fiche.contexte.actuel"), []


def titre_sujet(sujet: str, valeur=None) -> str:
    """Le titre de la fiche dans la fenêtre : « Ce que ça change : Qualité maximale »."""
    if sujet == "preset" and valeur in presets.PRESETS:
        nom = presets.nom_preset(valeur)
    elif sujet == "rythme" and valeur in rythme.RYTHMES:
        nom = _nom_rythme(valeur)
    elif sujet == "auto":
        nom = langues.t("fiche.choix.auto")
    else:
        nom = langues.t(f"fiche.nom.{sujet if sujet in SUJETS else 'actuel'}")
    return langues.t("fiche.titre_sujet", nom=nom)


def texte(fiche: dict, entete: str = "") -> str:
    """La fiche en texte, pour la ligne de commande : les mêmes lignes que la fenêtre."""
    lignes = [entete or fiche["titre"], "  " + fiche["verdict"]]
    for section in fiche["sections"]:
        lignes += ["", section["titre"]]
        lignes += [f"  {ligne['libelle']}{langues.t('fiche.sep')}{ligne['valeur']}" for ligne in section["lignes"]]
    return "\n".join(lignes)
