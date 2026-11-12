"""
Épreuve d'endurance : le réglage retenu, passé de nombreuses fois d'affilée.

Pourquoi
--------
La campagne de mesure dit quel réglage est juste et rapide ; elle ne dit pas
s'il tient. Le 12/11, sur le poste du travail, OpenVINO sur la puce graphique a
échoué une fois sur vingt-trois passages. Avant d'en faire le réglage de tous
les jours, il faut un taux de panne mesuré, et savoir si le filet de
l'application (rejeu sur la puce graphique, puis repli sur CTranslate2, voir
`moteur_openvino.MoteurAvecRepli`) le rattrape.

Ce que fait l'épreuve
---------------------
- N passages (30 par défaut) d'environ 2 min, chacun fait de deux extraits de
  réunions différentes du corpus public de la campagne (SUMM-RE ASRU) ;
- comme dans l'application : un seul processus pour toute la file, le moteur
  de la file (`MoteurAvecRepli` pour OpenVINO), pipeline ouvert puis libéré à
  chaque passage, langue fr, glossaire éteint ;
- avec `--pression`, un passage sur deux recrée la situation du 12/11 :
  CTranslate2 large-v3 chargé et passé sur 60 s avec les réglages de la
  « Qualité maximale » (le pic de mémoire de ct2-v3-f5), puis la mémoire libre
  du poste ramenée vers 4 Go par un lest ; le tout reste en place pendant
  l'ouverture du pipeline OpenVINO et pendant le passage ;
- pour chaque passage : réussi ou non, erreur exacte, phase (ouverture ou
  transcription), rejeu réussi ou non, repli, mémoire libre du poste juste
  avant l'ouverture du pipeline et juste avant le passage, vitesse ;
- diagnostic de l'échec du 12/11, si ses traces sont encore sur le poste : le
  journal du processus tombé (numéros de ligne seulement), et la réunion
  elle-même rejouée deux fois, avec l'ancien garde-fou des répétitions puis
  avec le nouveau.

Le rapport ne contient que des nombres et les messages d'erreur d'OpenVINO :
aucun mot transcrit, aucun nom, aucun chemin. Le poste ne se met pas en veille
pendant l'épreuve, et une relance reprend au passage suivant le dernier
enregistré. Un processus qui tombe est noté (« processus tombé ») et la file
repart dans un nouveau processus au passage suivant.

Ligne de commande :

    scribouille.com --endurance [--passages 30] [--reglage CLE]
        [--pression] [--memoire-libre 4] [--sans-diagnostic] [--recommencer]
        [--corpus PAQUET.zip] [--peripherique GPU|CPU]
"""

from __future__ import annotations

import gc
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from . import chemins, journal, langues, materiel, moteur, presets
from . import campagne as cp

MARQUE = "SCRIBOUILLE-ENDURANCE|"
DOSSIER = cp.DOSSIER_CAMPAGNES / "endurance"

PASSAGES = 30
#: Durée visée d'un passage : deux extraits du corpus, de 55 à 80 s chacun.
DUREE_PASSAGE_S = 120.0
#: Mémoire libre visée pendant un passage sous pression (constaté le 12/11 : 4,0 Go).
MEMOIRE_LIBRE_GO = 4.0
#: Audio passé à CTranslate2 large-v3 avant chaque passage sous pression.
PRESSION_CT2_S = 60.0
#: Lest au plus, en Go : jamais plus de 60 % de la mémoire du poste non plus.
LEST_MAX_GO = 20.0
#: Un passage sans signe de vie pendant ce temps est tenu pour bloqué.
INACTIVITE_MAX_S = 900.0
#: Réunions dont l'échec est rejoué en diagnostic, au plus.
DIAGNOSTICS_MAX = 2

#: Issues d'un incident du moteur (voir `MoteurAvecRepli.incidents`).
ISSUES = ("rejeu", "rejeu_reussi", "repli", "premiere_version_gardee")

#: Lignes de `app/moteur_openvino.py` dans la version de la campagne du 12/11
#: (commit de4302c), pour lire le journal du processus tombé.
LIGNES_12_11 = {400: "glouton", 401: "glouton", 414: "garde_faisceau", 415: "garde_faisceau",
                315: "ouverture", 316: "ouverture", 324: "ouverture", 325: "ouverture"}


# ---------------------------------------------------------------------------
# Plan des passages
# ---------------------------------------------------------------------------

def planifier(extraits: list[dict], nombre: int, pression: bool) -> list[dict]:
    """
    Passages de deux extraits de réunions différentes, environ 2 min chacun.

    `extraits` : {"id", "wav", "reunion", "duree_s"}. Le choix est mécanique :
    le k-ième passage prend l'extrait k, puis le premier extrait d'une autre
    réunion à partir de k + 7, en tournant sur la liste.
    """
    n = len(extraits)
    passages: list[dict] = []
    if not n:
        return passages
    for k in range(nombre):
        a = extraits[k % n]
        pris = [a]
        duree = float(a.get("duree_s") or 0)
        decalage = 7
        while duree < DUREE_PASSAGE_S * 0.9 and decalage < 7 + n:
            b = extraits[(k + decalage) % n]
            decalage += 1
            if b["reunion"] == a["reunion"] or b in pris:
                continue
            pris.append(b)
            duree += float(b.get("duree_s") or 0)
        passages.append({"id": f"p{k + 1:02d}", "wavs": [e["wav"] for e in pris], "duree_s": round(duree, 1),
                         "mode": "pression" if pression and k % 2 == 1 else "normal", "garde": "auto"})
    return passages


def reunions_en_echec(cle: str) -> list[Path]:
    """Extraits de réunions de la campagne où ce réglage a échoué sur l'erreur de la puce graphique."""
    trouves = []
    for dossier in sorted(cp.DOSSIER_CAMPAGNES.glob("reunion-*")):
        try:
            resultat = json.loads((dossier / "reglages" / f"{cle}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        extrait = dossier / "extrait.npy"
        if resultat.get("etat") == "erreur" and "iremote_tensor" in str(resultat.get("erreur", "")) \
                and extrait.is_file():
            trouves.append(extrait)
    return trouves[:DIAGNOSTICS_MAX]


def diagnostics(cle: str) -> list[dict]:
    """Deux passages par réunion en échec : ancien garde-fou (faisceau 5), puis le nouveau."""
    passages = []
    for rang, extrait in enumerate(reunions_en_echec(cle), 1):
        for garde, suffixe in (("faisceau", "ancien"), ("auto", "nouveau")):
            passages.append({"id": f"r{rang}-{suffixe}", "npy": str(extrait), "mode": "diagnostic",
                             "garde": garde, "reunion": rang})
    return passages


def lire_journaux(dossier: Path | None = None) -> list[dict]:
    """
    Traces de l'échec dans les journaux des processus de la campagne.

    Seulement des numéros de ligne et des drapeaux : aucune ligne du journal
    n'est recopiée. Le journal d'un processus de réglage ne contient pas de
    texte transcrit, mais on n'en garde rien de toute façon.
    """
    dossier = dossier or chemins.DOSSIER_LOGS
    traces = []
    for fichier in sorted(dossier.glob("*.log")):
        try:
            contenu = fichier.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Seuls les journaux d'un réglage de campagne tombé sur l'erreur de la
        # puce graphique : pas ceux de l'épreuve elle-même.
        if "Campagne : réglage en échec" not in contenu or "iremote_tensor" not in contenu:
            continue
        lignes = [int(n) for n in re.findall(r'moteur_openvino\.py", line (\d+)', contenu)]
        fenetres = re.findall(r"Transcription OpenVINO : \w+, langue=\w+, faisceau=(\d+), (\d+) fen", contenu)
        traces.append({
            "date": fichier.stem[:15],
            "lignes": lignes,
            "lieu": next((LIGNES_12_11[n] for n in reversed(lignes) if n in LIGNES_12_11), "inconnu"),
            "repetitive": "Fenêtre répétitive" in contenu,
            "ouvert": bool(fenetres),
            "faisceau": int(fenetres[-1][0]) if fenetres else 0,
            "fenetres": int(fenetres[-1][1]) if fenetres else 0,
        })
    return traces


# ---------------------------------------------------------------------------
# Le processus travailleur
# ---------------------------------------------------------------------------

def _emettre(donnees: dict) -> None:
    try:
        sys.__stdout__.write(MARQUE + json.dumps(donnees, ensure_ascii=False) + "\n")
        sys.__stdout__.flush()
    except Exception:
        pass


def memoire_libre_go() -> float:
    try:
        import psutil  # type: ignore

        return round(psutil.virtual_memory().available / 1024 ** 3, 2)
    except Exception:
        return -1.0


def lester(cible_go: float) -> list[np.ndarray]:
    """Occupe de la mémoire (pages réellement écrites) jusqu'à ne laisser que `cible_go` libres."""
    try:
        import psutil  # type: ignore

        total = psutil.virtual_memory().total / 1024 ** 3
    except Exception:
        return []
    plafond = min(LEST_MAX_GO, 0.6 * total)
    blocs: list[np.ndarray] = []
    pas = 256 * 1024 ** 2
    while memoire_libre_go() > cible_go + 0.3 and len(blocs) * 0.25 < plafond:
        blocs.append(np.ones(pas, dtype=np.uint8))
    return blocs


def _signal(passage: dict) -> np.ndarray:
    if passage.get("npy"):
        return np.ascontiguousarray(np.load(passage["npy"]), dtype=np.float32)
    from .corpus import lire_wav16

    morceaux = [lire_wav16(Path(w)) for w in passage["wavs"]]
    pause = np.zeros(8000, dtype=np.float32)
    signal = [morceaux[0]]
    for m in morceaux[1:]:
        signal += [pause, m]
    return np.ascontiguousarray(np.concatenate(signal), dtype=np.float32)


def _reglages(config: dict, reglage: cp.Reglage, mat) -> dict:
    from . import config as config_module, reglage_machine

    reglages = config_module.reglages_effectifs({**config, "preset": reglage.preset, "mode_avance": False})
    reglages["lot"] = presets.taille_lot(reglage.preset, mat)
    impose = reglage_machine.lot_impose(config, mat)
    if impose is not None and reglages["lot"]:
        reglages["lot"] = impose
    if reglage.moteur == "openvino":
        reglages["faisceau_openvino"] = reglage.faisceau
    else:
        reglages["beam_size"] = reglages["best_of"] = reglage.faisceau
    return reglages


def fabriquer(reglage: cp.Reglage, mat, peripherique: str):
    """Le moteur de la file de l'application, sans son témoin de plantage."""
    if reglage.moteur == "openvino":
        from . import moteur_openvino

        instance = moteur_openvino.MoteurAvecRepli(mat, peripherique)
        # Le témoin suspend OpenVINO au démarrage suivant de l'application si
        # le processus tombe à l'ouverture : l'épreuve ne doit rien changer à
        # la configuration du poste, elle note la chute elle-même.
        instance._ov.temoin = False
        return instance
    return moteur.MoteurTranscription(mat)


def _pression(mat, config: dict, signal: np.ndarray, cible_go: float):
    """CTranslate2 large-v3 chargé et passé sur 60 s (réglages « Qualité maximale »), puis lest."""
    reglages = _reglages(config, cp.PAR_CLE["ct2-v3-f5"], mat)
    ct2 = moteur.MoteurTranscription(mat)
    ct2.charger("large-v3")
    morceau = signal[:int(PRESSION_CT2_S * 16000)]
    ct2.transcrire(morceau, morceau.size / 16000, "fr", reglages)
    return ct2, lester(cible_go)


def jouer_passage(passage: dict, reglage: cp.Reglage, mat, config: dict, peripherique: str,
                  cible_go: float) -> dict:
    """Un passage, mesuré. Ne lève jamais : l'erreur est dans la ligne rendue."""
    ligne: dict = {"id": passage["id"], "mode": passage["mode"], "garde": passage.get("garde", "auto"),
                   "etat": "erreur", "incidents": []}
    instance = ct2 = lest = None
    phase = "preparation"
    try:
        signal = _signal(passage)
        duree = signal.size / 16000
        ligne["duree_s"] = round(duree, 1)
        if passage["mode"] == "pression":
            phase = "pression"
            ligne["libre_avant_pression_go"] = memoire_libre_go()
            ct2, lest = _pression(mat, config, signal, cible_go)
            ligne["lest_go"] = round(len(lest) * 0.25, 2)
        phase = "moteur"
        reglages = _reglages(config, reglage, mat)
        reglages["garde_repetition"] = passage.get("garde", "auto")
        instance = fabriquer(reglage, mat, peripherique)
        ligne["libre_avant_ouverture_go"] = memoire_libre_go()
        debut = time.perf_counter()
        instance.charger(reglage.modele, lambda niveau, texte: journal.info("endurance : %s", texte))
        ligne["ouverture_s"] = round(time.perf_counter() - debut, 1)
        ligne["libre_avant_passage_go"] = memoire_libre_go()
        debut = time.perf_counter()
        segments, details = instance.transcrire(signal, duree, "fr", reglages)
        ligne["calcul_s"] = round(time.perf_counter() - debut, 1)
        ligne["facteur"] = round(ligne["calcul_s"] / max(1e-9, duree), 4)
        ligne["segments"] = len(segments)
        for cle in ("fenetres_repetitives", "reprises", "echecs_garde"):
            ligne[cle] = int(details.get(cle) or 0)
        if details.get("erreur_garde"):
            ligne["erreur_garde"] = details["erreur_garde"]
        incidents = list(getattr(instance, "incidents", []))
        ligne["incidents"] = incidents
        if not incidents:
            ligne["etat"] = "ok"
        elif getattr(instance, "sur_openvino", True):
            ligne["etat"] = "rejeu_reussi"
        else:
            ligne["etat"] = "repli"
    except Exception as exc:
        journal.exception("Endurance : passage en échec", exc)
        ligne["incidents"] = list(getattr(instance, "incidents", []) or [])
        ligne["erreur"] = f"{type(exc).__name__}: {exc}"[:300]
        if phase != "moteur":
            # La pression (ou la lecture de l'audio) a échoué avant que le
            # moteur éprouvé ne tourne : ce n'est pas une panne de ce moteur.
            ligne["etat"] = "pression_ratee"
    finally:
        for objet in (instance, ct2):
            try:
                if objet is not None:
                    objet.liberer()
            except Exception:
                pass
        instance = ct2 = lest = None
        gc.collect()
    return ligne


def executer_passages(fichier_parametres: str) -> int:
    """Corps du processus travailleur : les passages restants, un par un."""
    from . import config as config_module, energie, reglage_machine

    parametres = json.loads(Path(fichier_parametres).read_text(encoding="utf-8"))
    try:
        import psutil  # type: ignore

        if os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE"):
            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    config = config_module.charger()
    mat = materiel.detecter()
    reglage_machine.appliquer_au_materiel(config, mat)
    energie.desactiver_bridage()
    moteur.limiter_parallelisme(mat.fils_calcul)
    reglage = cp.PAR_CLE[parametres["cle"]]
    for passage in parametres["passages"]:
        _emettre({"debut": passage["id"]})
        _emettre({"passage": jouer_passage(passage, reglage, mat, config, parametres["peripherique"],
                                           float(parametres.get("memoire_libre") or MEMOIRE_LIBRE_GO))})
    return 0


# ---------------------------------------------------------------------------
# Chiffres
# ---------------------------------------------------------------------------

def borne_haute(pannes: int, total: int, z: float = 1.96) -> float:
    """Borne haute à 95 % d'un taux observé (intervalle de Wilson), en pour cent."""
    if total <= 0:
        return 0.0
    p = pannes / total
    centre = p + z * z / (2 * total)
    marge = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return round(100.0 * (centre + marge) / (1 + z * z / total), 1)


def bilan(lignes: list[dict]) -> dict:
    """Taux de panne avant et après rejeu, issues, vitesse, mémoire."""
    ratees = sum(1 for l in lignes if l["etat"] == "pression_ratee")
    lignes = [l for l in lignes if l["etat"] != "pression_ratee"]
    n = len(lignes)
    avant = sum(1 for l in lignes if l["etat"] != "ok")
    apres = sum(1 for l in lignes if l["etat"] not in ("ok", "rejeu_reussi"))
    compte = {e: sum(1 for l in lignes if l["etat"] == e)
              for e in ("ok", "rejeu_reussi", "repli", "erreur", "plantage", "bloque")}
    facteurs = [l["facteur"] for l in lignes if l.get("facteur")]
    ouvertures = [l["ouverture_s"] for l in lignes if l.get("ouverture_s") is not None]
    libres_ouv = [l["libre_avant_ouverture_go"] for l in lignes if l.get("libre_avant_ouverture_go", -1) >= 0]
    libres_pass = [l["libre_avant_passage_go"] for l in lignes if l.get("libre_avant_passage_go", -1) >= 0]
    return {
        "n": n, "avant": avant, "apres": apres, "pression_ratee": ratees,
        "taux_avant": round(100.0 * avant / n, 1) if n else 0.0,
        "taux_apres": round(100.0 * apres / n, 1) if n else 0.0,
        "borne_avant": borne_haute(avant, n), "borne_apres": borne_haute(apres, n),
        **compte,
        "fenetres_repetitives": sum(int(l.get("fenetres_repetitives") or 0) for l in lignes),
        "reprises": sum(int(l.get("reprises") or 0) for l in lignes),
        "echecs_garde": sum(int(l.get("echecs_garde") or 0) for l in lignes),
        "facteur_med": statistics.median(facteurs) if facteurs else 0.0,
        "facteur_min": min(facteurs, default=0.0), "facteur_max": max(facteurs, default=0.0),
        "ouverture_med": statistics.median(ouvertures) if ouvertures else 0.0,
        "ouverture_max": max(ouvertures, default=0.0),
        "libre_ouv_min": min(libres_ouv, default=-1.0),
        "libre_ouv_med": statistics.median(libres_ouv) if libres_ouv else -1.0,
        "libre_pass_min": min(libres_pass, default=-1.0),
    }


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def _n(valeur: float, decimales: int = 1) -> str:
    return langues.nombre(valeur, decimales)


def rediger_rapport(mat, cle: str, peripherique: str, lignes: list[dict], traces: list[dict] | None,
                    pression: bool, cible_go: float, duree_totale: float) -> str:
    from .banc import _masquer

    t = langues.t
    reglage = cp.PAR_CLE[cle]
    rapport = cp._entete(mat, "end.rapport.titre")
    courants = [l for l in lignes if l["mode"] != "diagnostic"]
    diag = [l for l in lignes if l["mode"] == "diagnostic"]
    rapport.append(t("end.rapport.reglage", code=cle, reglage=cp.libelle(reglage, peripherique)))
    durees = [l["duree_s"] for l in courants if l.get("duree_s")]
    rapport.append(t("end.rapport.plan", n=len(courants),
                     minutes=_n(statistics.mean(durees) / 60 if durees else 0.0, 1)))
    if pression:
        rapport.append(t("end.rapport.plan_pression", secondes=_n(PRESSION_CT2_S, 0), cible=_n(cible_go, 0)))

    b = bilan(courants)
    rapport += ["", t("end.rapport.section.resultat")]
    rapport.append("  - " + t("end.rapport.panne_avant", k=b["avant"], n=b["n"], pct=_n(b["taux_avant"], 1),
                              borne=_n(b["borne_avant"], 1)))
    rapport.append("  - " + t("end.rapport.panne_apres", k=b["apres"], n=b["n"], pct=_n(b["taux_apres"], 1),
                              borne=_n(b["borne_apres"], 1)))
    rapport.append("  - " + t("end.rapport.issues", rejeux=b["rejeu_reussi"], replis=b["repli"],
                              erreurs=b["erreur"], plantages=b["plantage"] + b["bloque"]))
    if b["pression_ratee"]:
        rapport.append("  - " + t("end.rapport.pression_ratee", n=b["pression_ratee"]))
    rapport.append("  - " + t("end.rapport.repetitions", fenetres=b["fenetres_repetitives"],
                              reprises=b["reprises"], echecs=b["echecs_garde"]))
    rapport.append("  - " + t("end.rapport.vitesse", mediane=_n(b["facteur_med"], 3), min=_n(b["facteur_min"], 3),
                              max=_n(b["facteur_max"], 3), ouv=_n(b["ouverture_med"], 1),
                              ouv_max=_n(b["ouverture_max"], 1)))
    rapport.append("  - " + t("end.rapport.memoire", min=_n(b["libre_ouv_min"], 1), med=_n(b["libre_ouv_med"], 1),
                              min2=_n(b["libre_pass_min"], 1)))
    if pression:
        for mode in ("normal", "pression"):
            sous = bilan([l for l in courants if l["mode"] == mode])
            rapport.append("      " + t("end.rapport.par_mode", mode=t(f"end.mode.{mode}"), n=sous["n"],
                                        k=sous["avant"], perdus=sous["apres"], med=_n(sous["libre_ouv_med"], 1),
                                        min=_n(sous["libre_ouv_min"], 1)))

    erreurs = [(l["id"], i) for l in lignes for i in l.get("incidents", [])]
    erreurs += [(l["id"], {"phase": "passage", "issue": l["etat"], "erreur": l["erreur"]})
                for l in lignes if l.get("erreur")]
    erreurs += [(l["id"], {"phase": "garde", "issue": "premiere_version_gardee", "erreur": l["erreur_garde"]})
                for l in lignes if l.get("erreur_garde")]
    rapport += ["", t("end.rapport.section.erreurs")]
    if not erreurs:
        rapport.append("  - " + t("end.rapport.aucune_erreur"))
    for ident, incident in erreurs:
        issue = str(incident.get("issue", ""))
        rapport.append("  - " + t("end.rapport.erreur", id=ident,
                                  phase=t(f"end.phase.{incident.get('phase', 'passage')}"),
                                  issue=t(f"end.issue.{issue}") if issue in ISSUES else t(f"end.etat.{issue}"),
                                  erreur=incident.get("erreur", "")))

    if traces is not None or diag:
        rapport += ["", t("end.rapport.section.diagnostic")]
        if traces is not None:
            if not traces:
                rapport.append("  - " + t("end.rapport.diag_journal_aucun"))
            for trace in traces:
                rapport.append("  - " + t("end.rapport.diag_journal", date=trace["date"],
                                          lignes=", ".join(str(n) for n in trace["lignes"]) or "-",
                                          lieu=t(f"end.lieu.{trace['lieu']}"),
                                          repetitive=t("end.oui" if trace["repetitive"] else "end.non"),
                                          ouvert=t("end.oui" if trace["ouvert"] else "end.non"),
                                          fenetres=trace["fenetres"]))
        for rang in sorted({l["id"].split("-")[0] for l in diag}):
            ancien = next((l for l in diag if l["id"] == f"{rang}-ancien"), None)
            nouveau = next((l for l in diag if l["id"] == f"{rang}-nouveau"), None)
            for libelle_cle, l in (("end.rapport.diag_ancien", ancien), ("end.rapport.diag_nouveau", nouveau)):
                if l is None:
                    continue
                rapport.append("  - " + t(libelle_cle, reunion=rang[1:], etat=t(f"end.etat.{l['etat']}"),
                                          fenetres=int(l.get("fenetres_repetitives") or 0),
                                          echecs=int(l.get("echecs_garde") or 0),
                                          facteur=_n(float(l.get("facteur") or 0), 3)))
            if ancien and nouveau:
                reproduit = bool(ancien.get("echecs_garde")) and "iremote_tensor" in str(ancien.get("erreur_garde"))
                passe = nouveau["etat"] == "ok" and not nouveau.get("echecs_garde")
                rapport.append("      " + t("end.rapport.diag_conclusion_oui" if reproduit and passe
                                            else "end.rapport.diag_conclusion_non"))

    rapport += ["", t("end.rapport.section.detail")]
    for l in lignes:
        rapport.append("  " + t("end.rapport.ligne", id=l["id"], mode=t(f"end.mode.{l['mode']}"),
                                etat=t(f"end.etat.{l['etat']}"),
                                libre_ouv=_n(float(l.get("libre_avant_ouverture_go", -1)), 1),
                                libre_pass=_n(float(l.get("libre_avant_passage_go", -1)), 1),
                                ouv=_n(float(l.get("ouverture_s") or 0), 1),
                                facteur=_n(float(l.get("facteur") or 0), 3),
                                boucles=int(l.get("fenetres_repetitives") or 0)))
    rapport += ["", t("end.rapport.duree", duree=presets.formater_duree(duree_totale)),
                t("end.rapport.remarque")]
    return _masquer("\n".join(rapport)) + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def commande_essai(fichier_parametres: Path) -> tuple[list[str], str]:
    if chemins.EST_GELE:
        dossier = Path(sys.executable).resolve().parent
        exe = chemins.executable_console() or Path(sys.executable)
        return [str(exe), "--endurance-essai", str(fichier_parametres)], str(dossier)
    racine = Path(__file__).resolve().parent.parent
    python = racine / ".venv" / "Scripts" / "python.exe"
    interprete = str(python) if python.exists() else sys.executable
    return [interprete, "-m", "app.endurance", "--endurance-essai", str(fichier_parametres)], str(racine)


def _lancer(fichier_parametres: Path, recevoir: Callable[[dict], None],
            interrompu: Callable[[], bool] | None) -> tuple[str, str]:
    """
    Lance un processus travailleur et relaie ce qu'il dit.

    Rend (issue, passage en cours) : « fin » quand il s'est arrêté seul,
    « bloque » s'il n'a plus donné signe de vie, « annule » sur demande.
    """
    import queue
    import threading

    from .banc import _arreter

    commande, dossier = commande_essai(fichier_parametres)
    processus = subprocess.Popen(
        commande, cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
    lignes: "queue.Queue[str | None]" = queue.Queue()

    def lire() -> None:
        for ligne in processus.stdout or []:
            lignes.put(ligne)
        lignes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    en_cours, dernier_signe = "", time.time()
    while True:
        if interrompu is not None and interrompu():
            _arreter(processus)
            return "annule", en_cours
        if time.time() - dernier_signe > INACTIVITE_MAX_S:
            _arreter(processus)
            return "bloque", en_cours
        try:
            ligne = lignes.get(timeout=0.5)
        except Exception:
            continue
        if ligne is None:
            break
        if not ligne.startswith(MARQUE):
            if ligne.strip():
                journal.debug("endurance : %s", ligne.rstrip()[:300])
            continue
        try:
            donnees = json.loads(ligne[len(MARQUE):])
        except ValueError:
            continue
        dernier_signe = time.time()
        if "debut" in donnees:
            en_cours = donnees["debut"]
        elif "passage" in donnees:
            recevoir(donnees["passage"])
            en_cours = ""
    processus.wait()
    return f"fin:{processus.returncode}", en_cours


def _lire_faits(fichier: Path) -> list[dict]:
    faits = []
    try:
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            if ligne.strip():
                faits.append(json.loads(ligne))
    except (OSError, ValueError):
        pass
    return faits


def executer(passages: int = PASSAGES, cle: str = "", pression: bool = False,
             memoire_libre: float = MEMOIRE_LIBRE_GO, diagnostic: bool = True, recommencer: bool = False,
             paquet: str = "", peripherique: str = "", rappel: Callable[[str], None] | None = None,
             interrompu: Callable[[], bool] | None = None) -> dict:
    from . import energie

    with energie.sans_veille():
        return _executer(passages, cle, pression, memoire_libre, diagnostic, recommencer, paquet,
                         peripherique, rappel, interrompu)


def _executer(passages: int, cle: str, pression: bool, memoire_libre: float, diagnostic: bool,
              recommencer: bool, paquet: str, peripherique: str, rappel: Callable[[str], None] | None,
              interrompu: Callable[[], bool] | None) -> dict:
    from . import config as config_module, corpus

    depart = time.time()
    config_module.charger()  # langue de l'interface, celle du rapport

    def dire(message: str) -> None:
        journal.info("Endurance : %s", message)
        if rappel:
            rappel(message)

    cle = cle or cp.dernier_verdict().get("cle") or "ov-turbo-f1"
    reglage = cp._choisir(cle)[0]
    peripherique = cp._peripherique_ov(peripherique) if reglage.moteur == "openvino" else ""
    if reglage.moteur == "openvino" and not peripherique:
        raise journal.ErreurLisible(langues.t("end.refuse.titre"), langues.t("end.refuse.absent", code=cle))
    if not cp.pris_en_charge(reglage, peripherique):
        raise journal.ErreurLisible(langues.t("end.refuse.titre"),
                                    langues.t("end.refuse.faisceau", code=cle, peripherique=peripherique))
    if moteur.etat_modele(cp.depot_du(reglage))["etat"] != "complet" or (
            pression and moteur.etat_modele("large-v3")["etat"] != "complet"):
        raise journal.ErreurLisible(langues.t("end.refuse.titre"), langues.t("end.refuse.modele", code=cle))

    nom = f"{cle}-{(peripherique or 'cpu').lower()}-{passages}" + ("-pression" if pression else "")
    dossier = DOSSIER / nom
    if recommencer and dossier.exists():
        shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True, exist_ok=True)
    fichier = dossier / "passages.jsonl"

    try:
        extraits = corpus.preparer(None, paquet or None, 0, interrompu)
    except corpus.ErreurCorpus as exc:
        raise journal.ErreurLisible(langues.t("camp.corpus_absent.titre"),
                                    langues.t("camp.corpus_absent.msg", paquet=corpus.NOM_PAQUET,
                                              detail=exc.detail or exc.motif)) from exc
    liste = [{"id": e.ident, "wav": str(e.wav), "reunion": e.reunion, "duree_s": e.duree} for e in extraits]
    plan = (diagnostics(cle) if diagnostic and reglage.moteur == "openvino" else []) + \
        planifier(liste, passages, pression)
    traces = lire_journaux() if diagnostic and reglage.moteur == "openvino" else None

    faits = {l["id"]: l for l in _lire_faits(fichier)}
    restants = [p for p in plan if p["id"] not in faits]
    dire(langues.t("end.etape.plan", n=len(plan), faits=len(plan) - len(restants), code=cle))

    def recevoir(ligne: dict) -> None:
        faits[ligne["id"]] = ligne
        with fichier.open("a", encoding="utf-8") as sortie:
            sortie.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        dire(langues.t("end.etape.passage", id=ligne["id"], n=len(faits), total=len(plan),
                       etat=langues.t(f"end.etat.{ligne['etat']}"),
                       facteur=_n(float(ligne.get("facteur") or 0), 3),
                       ouv=_n(float(ligne.get("ouverture_s") or 0), 0),
                       libre=_n(float(ligne.get("libre_avant_ouverture_go", -1)), 1)))

    while restants:
        if interrompu and interrompu():
            break
        parametres = dossier / "parametres.json"
        parametres.write_text(json.dumps({"cle": cle, "peripherique": peripherique or "CPU",
                                          "memoire_libre": memoire_libre, "passages": restants},
                                         ensure_ascii=False), encoding="utf-8")
        issue, en_cours = _lancer(parametres, recevoir, interrompu)
        if issue == "annule":
            break
        if en_cours and en_cours not in faits:
            passage = next(p for p in restants if p["id"] == en_cours)
            recevoir({"id": en_cours, "mode": passage["mode"], "garde": passage.get("garde", "auto"),
                      "etat": "bloque" if issue == "bloque" else "plantage", "incidents": [],
                      "erreur": langues.t("end.erreur.bloque", s=int(INACTIVITE_MAX_S)) if issue == "bloque"
                      else langues.t("end.erreur.plantage", code=issue.split(":")[-1])})
        avant = len(restants)
        restants = [p for p in restants if p["id"] not in faits]
        if restants and len(restants) == avant:
            # Le processus s'arrête sans rien faire : inutile de boucler.
            dire(langues.t("end.etape.abandon", issue=issue))
            break
        if restants:
            dire(langues.t("end.etape.relance", n=len(restants)))

    lignes = [faits[p["id"]] for p in plan if p["id"] in faits]
    mat = materiel.detecter()
    rapport = rediger_rapport(mat, cle, peripherique, lignes, traces, pression, memoire_libre,
                              time.time() - depart)
    sortie = dossier / f"rapport-endurance-{datetime.now():%Y%m%d-%H%M}.txt"
    sortie.write_text(rapport, encoding="utf-8")
    return {"rapport": rapport, "fichier": str(sortie), "bilan": bilan([l for l in lignes
                                                                         if l["mode"] != "diagnostic"]),
            "complet": len(lignes) == len(plan)}


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------

def principal_cli(arguments: list[str]) -> int:
    if "--endurance-essai" in arguments:
        try:
            return executer_passages(cp._valeur(arguments, "--endurance-essai"))
        except Exception as exc:
            journal.exception("Endurance : processus travailleur en échec", exc)
            return 1
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass

    def afficher(message: str) -> None:
        print("  " + message, flush=True)

    try:
        resultat = executer(
            passages=int(cp._valeur(arguments, "--passages", str(PASSAGES)) or PASSAGES),
            cle=cp._valeur(arguments, "--reglage"), pression="--pression" in arguments,
            memoire_libre=float(cp._valeur(arguments, "--memoire-libre", str(MEMOIRE_LIBRE_GO)).replace(",", ".")),
            diagnostic="--sans-diagnostic" not in arguments, recommencer="--recommencer" in arguments,
            paquet=cp._valeur(arguments, "--corpus"), peripherique=cp._valeur(arguments, "--peripherique"),
            rappel=afficher)
    except journal.ErreurLisible as exc:
        print(f"{exc.titre}\n{exc.message}")
        return 1
    print()
    print(resultat["rapport"])
    print(langues.t("camp.cli.fichier", fichier=resultat["fichier"]))
    return 0 if resultat["complet"] else 1


def options_reconnues(arguments: list[str]) -> bool:
    return "--endurance" in arguments or "--endurance-essai" in arguments


if __name__ == "__main__":
    sys.exit(principal_cli(sys.argv[1:]))
