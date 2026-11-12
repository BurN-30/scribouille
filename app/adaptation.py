"""
Choix automatique du réglage selon le poste.

Au premier lancement, et sur demande (bouton « Reconnaître ce poste » des
réglages, ou `scribouille-verifier --reconnaitre`), l'application regarde le
poste et PROPOSE un réglage, expliqué en une phrase. Rien n'est appliqué, rien
n'est téléchargé ni installé sans un clic sur « Appliquer » (ou l'option
`--appliquer`) ; si le modèle proposé manque, la phrase donne sa taille, et le
téléchargement n'a lieu qu'au premier lancement d'une transcription, comme
pour tout premier usage.

Ordre des sources, de la plus sûre à la plus générale :

  1. le verdict d'une campagne de mesure menée sur ce poste (`app/campagne.py`),
     s'il est encore applicable (le périphérique retenu est toujours là) ;
  2. le conseil du dernier banc d'essai (`app/banc.py`), aux mêmes conditions ;
  3. la table de décision ci-dessous, lue de haut en bas, première règle qui
     s'applique.

Si le matériel a changé (puce graphique absente, pilote en panne, OpenVINO
retiré), la source mesurée est écartée, la table reprend la main, et la
proposition le dit.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable

from . import journal, langues, presets
from .materiel import Materiel

#: Version minimale du pilote graphique Intel sous Windows pour le greffon GPU
#: d'OpenVINO, d'après sa documentation (« Configurations for Intel Processor
#: Graphics (GPU) with OpenVINO », docs.openvino.ai, version 2026).
PILOTE_INTEL_MIN = (30, 0, 100, 9955)

#: Rythme que la proposition pose, avec l'adaptation automatique.
RYTHME_PROPOSE = "equilibre"


@dataclass
class Profil:
    """Ce que la table regarde du poste. Rempli par `profil`, ou à la main pour les vérifications."""

    processeur: str = ""
    logiques: int = 0
    hybride: bool = False
    basse_consommation: bool = False
    ram_go: float = 0.0
    cuda: bool = False
    puce_intel: bool = False
    pilote_intel: str = ""
    openvino_installe: bool = False
    openvino_puce: bool = False
    npu: bool = False
    portable: bool = False
    secteur: bool = True
    mode_alimentation: str = ""


def pilote_ancien(version: str) -> bool:
    """Pilote Intel antérieur au minimum documenté ; faux si la version est illisible."""
    try:
        morceaux = tuple(int(x) for x in str(version or "").split("."))
    except ValueError:
        return False
    if len(morceaux) != 4:
        return False
    return morceaux < PILOTE_INTEL_MIN


@dataclass(frozen=True)
class Regle:
    cle: str
    quand: Callable[[Profil], bool]
    moteur: str          # « ctranslate2 » ou « openvino »
    peripherique: str    # OpenVINO : « GPU » ou « CPU » ; vide pour CTranslate2
    preset: str          # « qualite » (large-v3) ou « rapide » (large-v3-turbo)


#: Table de décision. La première règle vraie l'emporte. Les mesures qui la
#: fondent :
#:  - carte NVIDIA : CTranslate2 en float16 sur la carte, large-v3 en dix fois
#:    moins de temps que l'audio ; aucune raison d'alléger le modèle ;
#:  - puce graphique Intel vue par OpenVINO : large-v3-turbo sur la puce, une
#:    heure en 7 minutes avec 2,2 Go, aussi juste que CTranslate2 large-v3
#:    faisceau 5 (51 minutes, 4 à 7,6 Go) d'après la campagne du PC du
#:    travail (Core Ultra 5 225U, novembre 2026) ;
#:  - puce Intel présente mais muette (pilote, OpenVINO retiré entre-temps) :
#:    OpenVINO sur le processeur, plus rapide que CTranslate2 à justesse égale
#:    (campagne sur processeur : turbo glouton 33,1 % à 0,09 fois l'audio,
#:    CTranslate2 turbo faisceau 5 35,2 % à 0,17) ;
#:  - moins de 10 Go de mémoire : large-v3 n'y tient pas avec le reste ;
#:  - processeur seul : OpenVINO s'il est installé (même raison), sinon
#:    « Rapide » sur un processeur modeste (moins de 12 fils ou série U/V,
#:    où « Qualité » dépasse la durée de la réunion), « Qualité » sur un
#:    processeur de bureau.
TABLE: tuple[Regle, ...] = (
    Regle("nvidia", lambda p: p.cuda, "ctranslate2", "", "qualite"),
    Regle("puce_intel", lambda p: p.openvino_puce, "openvino", "GPU", "rapide"),
    Regle("puce_muette", lambda p: p.puce_intel and p.openvino_installe, "openvino", "CPU", "rapide"),
    Regle("memoire_juste", lambda p: 0 < p.ram_go < 10, "ctranslate2", "", "rapide"),
    Regle("processeur_openvino", lambda p: p.openvino_installe, "openvino", "CPU", "rapide"),
    Regle("processeur_modeste", lambda p: p.basse_consommation or p.logiques < 12,
          "ctranslate2", "", "rapide"),
    Regle("processeur_puissant", lambda p: True, "ctranslate2", "", "qualite"),
)


def regle(p: Profil) -> Regle:
    return next(r for r in TABLE if r.quand(p))


def profil(mat: Materiel, ov_installe: bool | None = None,
           ov_peripheriques: list[str] | None = None) -> Profil:
    """Profil réel du poste. Aucun téléchargement, aucune installation."""
    from . import energie, moteur_openvino

    if ov_installe is None:
        ov_installe = moteur_openvino.installe()
    if ov_peripheriques is None:
        ov_peripheriques = moteur_openvino.peripheriques_disponibles() if ov_installe else []
    intel = next((g for g in mat.gpus if g.vendeur == "intel"), None)
    courant = energie.alimentation()
    return Profil(
        processeur=mat.cpu_nom, logiques=mat.coeurs_logiques, hybride=mat.topologie.hybride,
        basse_consommation=mat.basse_consommation, ram_go=mat.ram_go,
        cuda=mat.cuda_disponible, puce_intel=intel is not None,
        pilote_intel=intel.pilote if intel else "",
        openvino_installe=bool(ov_installe), openvino_puce="GPU" in (ov_peripheriques or []),
        npu=bool(mat.npus), portable=bool(courant["batterie"]), secteur=bool(courant["secteur"]),
        mode_alimentation=energie.mode_alimentation())


# ---------------------------------------------------------------------------
# Proposition
# ---------------------------------------------------------------------------

def _applicable(source: dict, p: Profil) -> bool:
    """Un réglage mesuré tient-il encore sur le matériel d'aujourd'hui ?"""
    if not source or not source.get("moteur"):
        return False
    if source["moteur"] != "openvino":
        return True
    if not p.openvino_installe:
        return False
    peripherique = str(source.get("peripherique") or "CPU").upper()
    return peripherique == "CPU" or (peripherique == "GPU" and p.openvino_puce)


def _preset_du_verdict(verdict: dict) -> str:
    return str(verdict.get("preset") or ("qualite" if verdict.get("modele") == "large-v3" else "rapide"))


def proposer(mat: Materiel, p: Profil, verdict: dict | None = None, conseil: dict | None = None,
             etat_modele: Callable[[str], str] | None = None) -> dict:
    """
    Réglage proposé pour ce poste, et pourquoi. Fonction pure si `etat_modele`
    est fourni (les vérifications le simulent) ; sinon l'état réel du disque.
    """
    from . import moteur

    notes: list[str] = []
    regle_table = regle(p)
    choix = {"moteur": regle_table.moteur, "peripherique": regle_table.peripherique,
             "preset": regle_table.preset, "faisceau": 0, "source": "table", "regle": regle_table.cle}
    if verdict and _applicable(verdict, p):
        choix.update(moteur=verdict["moteur"], peripherique=str(verdict.get("peripherique") or ""),
                     preset=_preset_du_verdict(verdict), faisceau=int(verdict.get("faisceau") or 0),
                     source="campagne", regle="campagne")
    elif conseil and _applicable(conseil, p):
        choix.update(moteur=conseil["moteur"], peripherique=str(conseil.get("peripherique") or ""),
                     source="banc", regle="banc")
        if conseil["moteur"] == "openvino":
            choix["preset"] = "rapide"
    else:
        if verdict:
            notes.append(langues.t("adapt.note.mesure_caduque", source=langues.t("adapt.source.campagne")))
        elif conseil:
            notes.append(langues.t("adapt.note.mesure_caduque", source=langues.t("adapt.source.banc")))
    if choix["moteur"] != "openvino":
        choix["peripherique"] = ""

    # Ce que le moteur proposé retire, dit avant d'appliquer : OpenVINO ne
    # donne pas la probabilité des mots, la relecture n'en surligne plus aucun.
    if choix["moteur"] == "openvino":
        notes.append(langues.t("adapt.note.sans_confiance"))
    if p.puce_intel and not p.openvino_installe:
        notes.append(langues.t("adapt.note.installer_openvino"))
    if p.puce_intel and pilote_ancien(p.pilote_intel):
        notes.append(langues.t("adapt.note.pilote_ancien", version=p.pilote_intel,
                               minimum=".".join(str(n) for n in PILOTE_INTEL_MIN)))
    if p.portable and not p.secteur:
        notes.append(langues.t("adapt.note.batterie"))
    elif p.mode_alimentation == "efficacite":
        notes.append(langues.t("adapt.note.mode_efficacite"))

    modele = presets.modele_du_preset(choix["preset"])
    depot = presets.depot_openvino(modele) if choix["moteur"] == "openvino" else modele
    lire_etat = etat_modele or (lambda d: moteur.etat_modele(d)["etat"])
    try:
        manque = lire_etat(depot) != "complet"
    except Exception:
        manque = True
    telechargement = moteur.taille_annoncee(depot) if manque else ""

    essai = copy.copy(mat)
    essai.moteur = choix["moteur"]
    essai.peripherique_openvino = choix["peripherique"] if choix["moteur"] == "openvino" else ""
    # Le même calcul que partout ailleurs, rythme proposé compris : une fois
    # appliquée, la proposition annonce ce que diront les cartes des presets.
    une_heure = presets.pour_une_heure(choix["preset"], essai, RYTHME_PROPOSE)

    if choix["moteur"] == "openvino":
        from . import moteur_openvino

        moteur_lisible = langues.t("adapt.moteur_ov", peripherique=moteur_openvino.nom_peripherique(
            choix["peripherique"] or "CPU"))
    else:
        moteur_lisible = langues.t("adapt.moteur_cuda" if p.cuda else "adapt.moteur_ct2")
    raison = langues.t(f"adapt.raison.{choix['regle']}")
    phrase = langues.t("adapt.phrase", preset=presets.nom_preset(choix["preset"]),
                       moteur=moteur_lisible, duree=une_heure, raison=raison)
    if telechargement:
        phrase += " " + langues.t("adapt.telechargement", taille=telechargement)
    return {**choix, "modele": moteur.nom_court(depot), "telechargement": telechargement,
            "une_heure": une_heure, "phrase": phrase, "notes": notes,
            "resume": langues.t("adapt.resume", preset=presets.nom_preset(choix["preset"]),
                                moteur=moteur_lisible),
            "rythme": RYTHME_PROPOSE, "rythme_auto": True,
            "action": "installer_openvino" if (p.puce_intel and not p.openvino_installe) else ""}


def deja_en_place(proposition: dict, config: dict, mat: Materiel) -> bool:
    """La proposition est-elle déjà le réglage en service ?"""
    from . import reglage_machine

    actuel = reglage_machine.lire(config, mat)
    moteur_actuel = actuel.get("moteur") or "ctranslate2"
    peripherique = str(actuel.get("peripherique") or "").upper() if moteur_actuel == "openvino" else ""
    return (moteur_actuel == proposition["moteur"]
            and peripherique == str(proposition.get("peripherique") or "").upper()
            and config.get("preset") == proposition["preset"]
            and config.get("rythme", "vitesse") == proposition["rythme"]
            and bool(config.get("rythme_auto")) == bool(proposition["rythme_auto"]))


def appliquer(config: dict, mat: Materiel, proposition: dict) -> dict:
    """Écrit la proposition (en mémoire) : réglage du poste, preset, rythme."""
    from . import reglage_machine

    actuel = reglage_machine.lire(config, mat)
    nouveau = {k: v for k, v in actuel.items() if k in ("fils", "lot")}
    nouveau.update({"moteur": proposition["moteur"], "source": proposition.get("source") or "table"})
    if proposition["moteur"] == "openvino":
        nouveau["peripherique"] = proposition.get("peripherique") or "CPU"
    if int(proposition.get("faisceau") or 0) > 0:
        nouveau["faisceau"] = int(proposition["faisceau"])
    propre = reglage_machine.enregistrer(config, mat, nouveau)
    config["preset"] = proposition["preset"]
    config["rythme"] = proposition.get("rythme") or "vitesse"
    config["rythme_auto"] = bool(proposition.get("rythme_auto"))
    journal.info("Proposition du poste appliquée : %s (%s)", proposition.get("regle"), proposition.get("source"))
    return propre


def proposition_du_poste(mat: Materiel) -> dict:
    """Proposition réelle : verdict de campagne et conseil du banc lus sur ce poste."""
    from . import banc, campagne

    return proposer(mat, profil(mat), campagne.dernier_verdict(), banc.dernier_conseil())


def decrire(p: Profil) -> list[str]:
    """Le poste, en quelques lignes, pour la ligne de commande."""
    t = langues.t
    lignes = [t("adapt.cli.processeur", nom=p.processeur or "?", fils=p.logiques,
                hybride=t("adapt.cli.hybride") if p.hybride else ""),
              t("adapt.cli.memoire", go=f"{p.ram_go:.0f}")]
    lignes.append(t("adapt.cli.graphique",
                    etat=t("adapt.cli.nvidia") if p.cuda else (
                        t("adapt.cli.intel_vue") if p.openvino_puce else (
                            t("adapt.cli.intel_muette") if p.puce_intel else t("adapt.cli.aucune")))))
    lignes.append(t("adapt.cli.openvino", etat=t("adapt.cli.oui") if p.openvino_installe else t("adapt.cli.non")))
    if p.npu:
        lignes.append(t("adapt.cli.npu"))
    lignes.append(t("adapt.cli.alimentation",
                    etat=t("adapt.cli.secteur") if p.secteur else t("adapt.cli.batterie"),
                    mode=t(f"adapt.mode.{p.mode_alimentation}") if p.mode_alimentation else "?"))
    return lignes


def principal_cli(arguments: list[str]) -> int:
    """`--reconnaitre [--appliquer]` : le poste, la règle, la proposition."""
    from . import config as config_module, materiel

    for flux in (__import__("sys").stdout,):
        try:
            flux.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass
    config = config_module.charger()
    mat = materiel.detecter()
    p = profil(mat)
    proposition = proposition_du_poste(mat)
    print(langues.t("adapt.cli.titre"))
    for ligne in decrire(p):
        print("  - " + ligne)
    print()
    print(langues.t("adapt.cli.source", source=langues.t(f"adapt.source.{proposition['source']}"),
                    regle=proposition["regle"]))
    print("  " + proposition["phrase"])
    print("  " + langues.t("adapt.cli.rythme", rythme=langues.t(f"rythme.nom.{proposition['rythme']}")))
    for note in proposition["notes"]:
        print("  " + note)
    print()
    if deja_en_place(proposition, config, mat):
        print(langues.t("adapt.cli.deja"))
    elif "--appliquer" in arguments:
        appliquer(config, mat, proposition)
        config_module.sauver(config)
        print(langues.t("adapt.cli.applique"))
    else:
        print(langues.t("adapt.cli.pour_appliquer"))
    return 0


def options_reconnues(arguments: list[str]) -> bool:
    return "--reconnaitre" in arguments
