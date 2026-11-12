"""
Campagne de mesure : quel réglage transcrire, mesuré sur ce poste, avec référence.

Pourquoi
--------
Le banc d'essai dit ce qui va vite ; la comparaison des moteurs dit où deux
moteurs divergent sur une vraie réunion, sans pouvoir dire lequel a raison.
La campagne tranche : elle transcrit, sous chaque réglage candidat, des
réunions publiques transcrites à la main (`app/corpus.py`, SUMM-RE ASRU, CC
BY-SA 4.0), compte les erreurs mot à mot, et rend un verdict.

Réglages candidats, à armes égales (même extraits, même normalisation,
glossaire et corrections éteints sur le corpus public) : CTranslate2 large-v3
faisceau 5 (le preset « Qualité maximale ») et faisceau 1 ; OpenVINO large-v3
faisceau 1 (réglage actuel d'OpenVINO) et faisceau 5 ; OpenVINO large-v3-turbo
faisceau 1 et 5 ; CTranslate2 large-v3-turbo faisceau 5 (le preset « Rapide »).
OpenVINO tourne sur la puce graphique Intel si elle est vue, sinon sur le
processeur.

Mesures par réglage : taux d'erreur de mots (WER) avec intervalle de confiance
à 95 % par rééchantillonnage des extraits (bootstrap), décomposé en
substitutions, omissions et insertions ; part des mots de la référence perdus
quand deux personnes parlent en même temps, et en dehors ; insertions longues
(au moins quatre mots consécutifs absents de la référence : indice
d'invention) ; vitesse rapportée à la durée de l'audio, chargement, mémoire ;
part des segments de plus de 15 s. Un témoin de parole lue (l'extrait FLEURS du
banc) est mesuré à part.

Verdict, la fiabilité d'abord : on écarte tout réglage plus lent que le temps
réel ; on garde ceux dont le taux d'erreur ne se distingue pas du meilleur
(moins d'un point d'écart, ou écart apparié dont l'intervalle à 95 % contient
zéro et qui reste sous deux points) ; parmi eux, le plus rapide. Rien n'est appliqué sans `--appliquer`.

Le rapport de chiffres ne contient aucun mot transcrit, aucun nom, aucun
chemin. Les transcriptions du corpus public restent dans le dossier de la
campagne ; celles d'une réunion réelle (`--reunion`) aussi, et rien d'elles
n'entre dans le rapport que des nombres.

La campagne reprend où elle s'est arrêtée : chaque réglage terminé est
enregistré aussitôt, et une relance ne recalcule que ce qui manque. Pendant le
calcul, le poste ne se met pas en veille (`energie.sans_veille`).

Ligne de commande :

    scribouille-verifier.exe --campagne [--appliquer] [--recommencer]
        [--reglages CLE,CLE] [--limite-extraits N] [--corpus PAQUET.zip]
        [--peripherique GPU|CPU] [--telecharger]
        [--peripherique HETERO:GPU,CPU] [--proprietes-ov CLE=VALEUR,...]   (essais du faisceau
        sur la puce graphique : dossier à part, jamais le verdict public du poste)
    scribouille-verifier.exe --campagne --reunion FICHIER [--debut 00:05:00]
        [--duree 600] [--reglages CLE,CLE]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from . import NOM_APPLICATION, VERSION, chemins, journal, langues, materiel, moteur, presets

MARQUE = "SCRIBOUILLE-CAMPAGNE|"
DOSSIER_CAMPAGNES = chemins.RACINE / "campagnes"

#: Écart de taux d'erreur, en points, sous lequel deux réglages sont tenus
#: pour équivalents quoi que dise l'intervalle.
ECART_EQUIVALENT = 1.0
#: Écart au-delà duquel deux réglages ne sont jamais tenus pour équivalents,
#: même quand l'intervalle apparié contient zéro (peu d'extraits, extraits très
#: inégaux) : la fiabilité passe avant la vitesse.
ECART_MAX = 2.0
#: Facteur temps réel au-delà duquel un réglage est écarté (plus lent que la réunion).
FACTEUR_MAX = 1.0
#: Tirages du bootstrap. 2000 suffisent pour des bornes à 95 % stables au dixième.
TIRAGES = 2000
#: Insertion « longue » : au moins ce nombre de mots consécutifs absents de la référence.
MOTS_INSERTION_LONGUE = 4
#: Segment « long », en secondes : illisible en sous-titre, mauvais pour les locuteurs.
SEGMENT_LONG_S = 15.0
#: Seuil des mots incertains de CTranslate2 (même valeur que la vue de relecture).
SEUIL_INCERTAIN = 0.50


# ---------------------------------------------------------------------------
# Réglages candidats
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Reglage:
    cle: str
    moteur: str          # « ctranslate2 » ou « openvino »
    modele: str          # « large-v3 » ou presets.MODELE_TURBO
    faisceau: int
    actuel: str = ""     # preset dont c'est le réglage par défaut, s'il y en a un

    @property
    def preset(self) -> str:
        return "qualite" if self.modele == "large-v3" else "rapide"


#: Ordre de passage : les réglages les plus utiles au verdict d'abord, pour qu'une
#: campagne interrompue ait déjà de quoi trancher.
CANDIDATS = (
    Reglage("ov-v3-f1", "openvino", "large-v3", 1, "openvino"),
    Reglage("ct2-v3-f5", "ctranslate2", "large-v3", 5, "qualite"),
    Reglage("ov-turbo-f1", "openvino", presets.MODELE_TURBO, 1),
    Reglage("ov-v3-f5", "openvino", "large-v3", 5),
    Reglage("ov-turbo-f5", "openvino", presets.MODELE_TURBO, 5),
    Reglage("ct2-turbo-f5", "ctranslate2", presets.MODELE_TURBO, 5, "rapide"),
    Reglage("ct2-v3-f1", "ctranslate2", "large-v3", 1),
)
PAR_CLE = {r.cle: r for r in CANDIDATS}


def libelle(reglage: Reglage, peripherique: str = "") -> str:
    nom = "large-v3-turbo" if reglage.modele == presets.MODELE_TURBO else reglage.modele
    if reglage.moteur == "openvino":
        return langues.t("camp.libelle_ov", modele=nom, faisceau=reglage.faisceau,
                         peripherique=peripherique or "?")
    return langues.t("camp.libelle_ct2", modele=nom, faisceau=reglage.faisceau)


#: État d'un réglage que le périphérique ne sait pas faire (faisceau d'OpenVINO
#: sur la puce graphique) : ni lancé, ni compté comme une panne.
NON_PRIS_EN_CHARGE = "non_pris_en_charge"


def pris_en_charge(reglage: Reglage, peripherique: str) -> bool:
    """Ce réglage peut-il tourner sur ce périphérique ? (faux : OpenVINO GPU en faisceau)"""
    if reglage.moteur != "openvino":
        return True
    from . import moteur_openvino

    return moteur_openvino.faisceau_pris_en_charge(peripherique or "CPU", reglage.faisceau)


def depot_du(reglage: Reglage) -> str:
    return presets.depot_openvino(reglage.modele) if reglage.moteur == "openvino" else reglage.modele


# ---------------------------------------------------------------------------
# Un réglage, dans son propre processus
# ---------------------------------------------------------------------------

def _emettre(donnees: dict) -> None:
    try:
        sys.__stdout__.write(MARQUE + json.dumps(donnees, ensure_ascii=False) + "\n")
        sys.__stdout__.flush()
    except Exception:
        pass


def _lire_signal(entree: dict) -> np.ndarray:
    if entree.get("npy"):
        return np.load(entree["npy"])
    from .corpus import lire_wav16

    return lire_wav16(Path(entree["wav"]))


def executer_reglage(parametres: dict) -> dict:
    """
    Corps d'un passage : charge un moteur une fois, transcrit chaque extrait,
    écrit les segments dans un fichier local. Tourne dans le processus travailleur.
    """
    from . import config as config_module, energie, reglage_machine, vocabulaire

    resultat: dict = {"cle": parametres.get("cle"), "etat": "erreur"}
    try:
        import psutil  # type: ignore

        processus = psutil.Process()
        if os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE"):
            processus.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        processus = None

    config = config_module.charger()
    mat = materiel.detecter()
    reglage_machine.appliquer_au_materiel(config, mat)
    energie.desactiver_bridage()

    reglage = PAR_CLE[parametres["cle"]]
    reglages = config_module.reglages_effectifs({**config, "preset": reglage.preset, "mode_avance": False})
    langue = str(parametres.get("langue") or "fr")
    if reglage.moteur == "openvino":
        from . import moteur_openvino

        if not moteur_openvino.installe():
            resultat["etat"] = "openvino_absent"
            return resultat
        if moteur.etat_modele(depot_du(reglage))["etat"] != "complet":
            resultat["etat"] = "modele_absent"
            return resultat
        peripherique = str(parametres.get("peripherique") or "CPU").upper()
        instance = moteur_openvino.MoteurOpenVINO(mat, peripherique)
        # Voie d'essai (`--proprietes-ov`), jamais posée par l'application.
        instance.proprietes = dict(parametres.get("proprietes_ov") or {})
        reglages["faisceau_openvino"] = reglage.faisceau
        resultat["peripherique"] = peripherique
    else:
        if moteur.etat_modele(reglage.modele)["etat"] != "complet":
            resultat["etat"] = "modele_absent"
            return resultat
        moteur.limiter_parallelisme(mat.fils_calcul)
        instance = moteur.MoteurTranscription(mat)
        reglages["beam_size"] = reglages["best_of"] = reglage.faisceau
        reglages["lot"] = presets.taille_lot("qualite", mat)
        impose = reglage_machine.lot_impose(config, mat)
        if impose is not None and reglages["lot"]:
            reglages["lot"] = impose
        resultat.update({"peripherique": instance.peripherique, "lot": int(reglages["lot"] or 0),
                         "fils": mat.fils_calcul})

    debut = time.perf_counter()
    instance.charger(reglage.modele, lambda niveau, texte: journal.info("campagne : %s", texte))
    resultat["chargement_s"] = round(time.perf_counter() - debut, 1)

    amorce = {"amorce": "", "nb_retenus": 0, "jetons": 0}
    if parametres.get("glossaire"):
        amorce = vocabulaire.construire_amorce(None, tokeniseur=instance.tokeniseur, langue=langue)
    if parametres.get("vocabulaire"):
        # Mesure du vocabulaire (app/mesure_vocabulaire.py) : amorce choisie
        # dans un fichier du format 2, refaite fenêtre par fenêtre s'il déborde.
        from . import vocabulaire_usage, vocabulaire_v2

        voc = vocabulaire_v2.lire(parametres["vocabulaire"])[0]
        dynamique = vocabulaire_usage.amorce(voc, instance.tokeniseur, langue,
                                             str(parametres.get("contexte") or ""))
        amorce = {"amorce": dynamique, "nb_retenus": dynamique.info["nb_retenus"],
                  "jetons": dynamique.info["jetons"]}
    regles = vocabulaire.analyser_corrections()[0] if parametres.get("corrections") else []

    sorties: dict[str, dict] = {}
    calcul_total, audio_total, remplacements = 0.0, 0.0, 0
    repetitions = {"fenetres_repetitives": 0, "reprises": 0, "echecs_garde": 0}
    temps_cpu = sum(processus.cpu_times()[:2]) if processus is not None else 0.0
    for rang, entree in enumerate(parametres["extraits"], 1):
        signal = _lire_signal(entree)
        duree = signal.size / 16000
        debut = time.perf_counter()
        segments, details = instance.transcrire(signal, duree, langue, dict(reglages),
                                                amorce=amorce["amorce"])
        calcul = time.perf_counter() - debut
        for segment in segments:
            segment.texte, nombre = vocabulaire.appliquer(segment.texte, regles)
            remplacements += nombre
        sorties[entree["id"]] = {
            "calcul_s": round(calcul, 3), "duree_s": round(duree, 3),
            "segments": [{"d": round(s.debut, 3), "f": round(s.fin, 3), "t": s.texte,
                          "m": [[m.texte, round(m.debut, 3), round(m.fin, 3), round(m.probabilite, 4)]
                                for m in s.mots]} for s in segments]}
        calcul_total += calcul
        audio_total += duree
        resultat["type_calcul"] = details.get("type_calcul", "")
        for cle in repetitions:
            repetitions[cle] += int(details.get(cle) or 0)
        _emettre({"progres": rang, "total": len(parametres["extraits"])})
    instance.liberer()
    if processus is not None:
        temps_cpu = sum(processus.cpu_times()[:2]) - temps_cpu

    Path(parametres["sortie"]).write_text(json.dumps(sorties, ensure_ascii=False), encoding="utf-8")
    pic = getattr(processus.memory_info(), "peak_wset", 0) / 1024 ** 3 if processus else 0.0
    resultat.update({
        "etat": "ok", "calcul_s": round(calcul_total, 2), "duree_audio_s": round(audio_total, 2),
        "facteur": round(calcul_total / audio_total, 4) if audio_total else 0.0,
        "processeur_s": round(temps_cpu, 1), "memoire_go": round(pic, 2),
        "termes_amorce": int(amorce.get("nb_retenus") or 0), "jetons_amorce": int(amorce.get("jetons") or 0),
        "remplacements": remplacements, **repetitions,
    })
    return resultat


def principal_essai(argument: str) -> int:
    try:
        parametres = json.loads(argument)
    except (TypeError, ValueError):
        _emettre({"etat": "erreur", "erreur": "paramètres illisibles"})
        return 2
    try:
        _emettre(executer_reglage(parametres))
        return 0
    except Exception as exc:
        journal.exception("Campagne : réglage en échec", exc)
        _emettre({"cle": parametres.get("cle"), "etat": "erreur",
                  "erreur": f"{type(exc).__name__}: {exc}"[:300]})
        return 1


def commande_essai(parametres: dict) -> tuple[list[str], str]:
    charge = json.dumps(parametres, ensure_ascii=False)
    if chemins.EST_GELE:
        dossier = Path(sys.executable).resolve().parent
        console = dossier / "scribouille-verifier.exe"
        exe = console if console.is_file() else Path(sys.executable)
        return [str(exe), "--campagne-essai", charge], str(dossier)
    racine = Path(__file__).resolve().parent.parent
    python = racine / ".venv" / "Scripts" / "python.exe"
    interprete = str(python) if python.exists() else sys.executable
    return [interprete, "-m", "app.campagne", "--campagne-essai", charge], str(racine)


def lancer_reglage(parametres: dict, inactivite_max: float,
                   rappel: Callable[[dict], None] | None = None,
                   interrompu: Callable[[], bool] | None = None) -> dict:
    """
    Lance un réglage dans un processus séparé et attend son résultat.

    Le délai porte sur l'INACTIVITÉ : il repart à chaque extrait terminé, si
    bien qu'un réglage lent mais vivant n'est jamais coupé, et qu'un
    périphérique bloqué l'est au bout de `inactivite_max` secondes.
    """
    import queue
    import threading

    from .banc import _arreter

    commande, dossier = commande_essai(parametres)
    try:
        processus = subprocess.Popen(
            commande, cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
    except OSError as exc:
        return {"cle": parametres.get("cle"), "etat": "erreur", "erreur": str(exc)}
    lignes: "queue.Queue[str | None]" = queue.Queue()

    def lire() -> None:
        for ligne in processus.stdout or []:
            lignes.put(ligne)
        lignes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    resultat: dict = {}
    dernier_signe = time.time()
    while True:
        if interrompu is not None and interrompu():
            _arreter(processus)
            return {"cle": parametres.get("cle"), "etat": "annule"}
        if time.time() - dernier_signe > inactivite_max:
            _arreter(processus)
            return {"cle": parametres.get("cle"), "etat": "delai",
                    "erreur": f"aucun signe depuis {int(inactivite_max)} s"}
        try:
            ligne = lignes.get(timeout=0.5)
        except Exception:
            continue
        if ligne is None:
            break
        if ligne.startswith(MARQUE):
            try:
                donnees = json.loads(ligne[len(MARQUE):])
            except ValueError:
                continue
            if "progres" in donnees:
                dernier_signe = time.time()
                if rappel:
                    rappel(donnees)
            else:
                resultat = donnees
        elif ligne.strip():
            journal.debug("campagne : %s", ligne.rstrip()[:300])
    processus.wait()
    if not resultat:
        resultat = {"cle": parametres.get("cle"), "etat": "erreur",
                    "erreur": f"processus terminé sans résultat (code {processus.returncode})"}
    return resultat


# ---------------------------------------------------------------------------
# Mesures (sans un mot du texte en sortie)
# ---------------------------------------------------------------------------

def mots_reference(reference: dict) -> tuple[list[str], list[bool]]:
    """Mots normalisés de la référence, et pour chacun : en chevauchement ?"""
    from .comparaison import normaliser

    mots, chev = [], []
    for texte, _d, _f, _loc, chevauche in reference["mots"]:
        for forme in normaliser(texte):
            mots.append(forme)
            chev.append(bool(chevauche))
    return mots, chev


def mesurer_extrait(reference: dict, segments: list[dict]) -> dict:
    """Erreurs d'une transcription contre la référence d'un extrait."""
    from .comparaison import aligner, construire_texte

    ref, chev = mots_reference(reference)
    texte = construire_texte(segments)
    hyp = [j.mot for j in texte.jetons]
    bilan = aligner(ref, hyp)
    chev_total = sum(chev)
    chev_perdus = hors_perdus = 0
    erreurs_hyp: set[int] = set()
    longues, mots_longs, suite = 0, 0, 0
    for op, i1, _i2, j1, _j2 in bilan.operations:
        if op in ("sub", "sup"):
            if chev[i1]:
                chev_perdus += 1
            else:
                hors_perdus += 1
        if op in ("sub", "ins"):
            erreurs_hyp.add(j1)
        if op == "ins":
            suite += 1
        else:
            if suite >= MOTS_INSERTION_LONGUE:
                longues += 1
                mots_longs += suite
            suite = 0
    if suite >= MOTS_INSERTION_LONGUE:
        longues += 1
        mots_longs += suite
    incertains = {k for k, j in enumerate(texte.jetons)
                  if j.probabilite is not None and j.probabilite < SEUIL_INCERTAIN}
    durees = [max(0.0, float(s.get("f", 0)) - float(s.get("d", 0))) for s in segments]
    return {
        "mots_ref": len(ref), "mots_hyp": len(hyp),
        "sub": bilan.substitutions, "sup": bilan.suppressions, "ins": bilan.insertions,
        "erreurs": bilan.editions,
        "chev_total": chev_total, "chev_perdus": chev_perdus,
        "hors_total": len(ref) - chev_total, "hors_perdus": hors_perdus,
        "insertions_longues": longues, "mots_insertions_longues": mots_longs,
        "segments": len(durees), "segments_longs": sum(1 for d in durees if d > SEGMENT_LONG_S),
        "avec_probabilite": sum(1 for j in texte.jetons if j.probabilite is not None),
        "incertains": len(incertains), "incertains_errones": len(incertains & erreurs_hyp),
        "hyp_erronees": len(erreurs_hyp),
    }


def _tirages(n: int, tirages: int = TIRAGES, graine: int = 20261112) -> np.ndarray:
    """Indices de rééchantillonnage, les MÊMES pour tous les réglages (comparaison appariée)."""
    return np.random.default_rng(graine).integers(0, n, size=(tirages, n))


def intervalle(erreurs: list[int], mots: list[int], indices: np.ndarray | None = None) -> tuple[float, float]:
    """Intervalle à 95 % du taux d'erreur global, par tirage des extraits avec remise."""
    e, m = np.asarray(erreurs, dtype=float), np.asarray(mots, dtype=float)
    if e.size == 0:
        return 0.0, 0.0
    if indices is None:
        indices = _tirages(e.size)
    taux = 100.0 * e[indices].sum(axis=1) / np.maximum(1.0, m[indices].sum(axis=1))
    return round(float(np.percentile(taux, 2.5)), 2), round(float(np.percentile(taux, 97.5)), 2)


def ecart_apparie(erreurs_a: list[int], erreurs_b: list[int], mots: list[int],
                  indices: np.ndarray | None = None) -> tuple[float, float, float]:
    """Écart de taux d'erreur a moins b, en points, et son intervalle à 95 % apparié."""
    a, b, m = (np.asarray(x, dtype=float) for x in (erreurs_a, erreurs_b, mots))
    if a.size == 0:
        return 0.0, 0.0, 0.0
    if indices is None:
        indices = _tirages(a.size)
    total = np.maximum(1.0, m[indices].sum(axis=1))
    ecarts = 100.0 * (a[indices].sum(axis=1) - b[indices].sum(axis=1)) / total
    observe = 100.0 * (a.sum() - b.sum()) / max(1.0, m.sum())
    return (round(float(observe), 2), round(float(np.percentile(ecarts, 2.5)), 2),
            round(float(np.percentile(ecarts, 97.5)), 2))


def agreger(par_extrait: dict[str, dict], ordre: list[str], indices: np.ndarray | None = None) -> dict:
    """Totaux d'un réglage sur les extraits, dans l'ordre donné, avec son intervalle."""
    lignes = [par_extrait[i] for i in ordre if i in par_extrait]
    total = {cle: sum(l[cle] for l in lignes) for cle in (
        "mots_ref", "mots_hyp", "sub", "sup", "ins", "erreurs", "chev_total", "chev_perdus",
        "hors_total", "hors_perdus", "insertions_longues", "mots_insertions_longues",
        "segments", "segments_longs", "avec_probabilite", "incertains", "incertains_errones",
        "hyp_erronees")}
    total["wer"] = round(100.0 * total["erreurs"] / max(1, total["mots_ref"]), 2)
    total["ic"] = intervalle([l["erreurs"] for l in lignes], [l["mots_ref"] for l in lignes],
                             indices if indices is not None and len(lignes) == indices.shape[1] else None)
    total["extraits"] = len(lignes)
    return total


def signalements(reference: dict, principal: list[dict], second: list[dict]) -> dict:
    """
    Substitut aux probabilités d'OpenVINO : les mots du réglage principal que
    la seconde passe n'écrit pas pareil. Combien d'erreurs réelles ils couvrent
    (rappel), et combien des mots signalés sont faux (précision).
    """
    from .comparaison import aligner, construire_texte

    ref, _chev = mots_reference(reference)
    a = [j.mot for j in construire_texte(principal).jetons]
    b = [j.mot for j in construire_texte(second).jetons]
    erreurs = {o[3] for o in aligner(ref, a).operations if o[0] in ("sub", "ins")}
    signales = aligner(a, b).divergents_a()
    return {"mots": len(a), "signales": len(signales), "erreurs": len(erreurs),
            "signales_errones": len(signales & erreurs)}


def verdict(resultats: dict[str, dict], ordre_extraits: list[str],
            par_extrait: dict[str, dict[str, dict]]) -> dict:
    """
    Règle de décision, la fiabilité d'abord.

    1. Écarter tout réglage en échec ou plus lent que le temps réel.
    2. Meilleur : le plus petit taux d'erreur parmi les réglages réussis.
    3. Équivalents : écart au meilleur inférieur à un point, ou écart apparié
       dont l'intervalle à 95 % contient zéro, à condition qu'il reste sous
       deux points.
    4. Retenu : le plus rapide des équivalents admissibles ; à défaut, le plus
       juste des admissibles.
    """
    reussis = {c: r for c, r in resultats.items() if r.get("etat") == "ok" and c in par_extrait}
    if not reussis:
        return {}
    indices = _tirages(len(ordre_extraits)) if ordre_extraits else None
    meilleur = min(reussis, key=lambda c: (reussis[c]["wer"], reussis[c]["facteur"]))
    mots = [par_extrait[meilleur][i]["mots_ref"] for i in ordre_extraits]
    ref_err = [par_extrait[meilleur][i]["erreurs"] for i in ordre_extraits]
    lignes: dict[str, dict] = {}
    for cle, r in reussis.items():
        err = [par_extrait[cle][i]["erreurs"] for i in ordre_extraits]
        ecart, bas, haut = ecart_apparie(err, ref_err, mots, indices)
        equivalent = cle == meilleur or ecart < ECART_EQUIVALENT or (bas <= 0.0 and ecart < ECART_MAX)
        lignes[cle] = {"ecart": ecart, "ecart_ic": (bas, haut), "equivalent": equivalent,
                       "admissible": float(r["facteur"]) < FACTEUR_MAX}
    candidats = [c for c, l in lignes.items() if l["equivalent"] and l["admissible"]]
    if candidats:
        retenu = min(candidats, key=lambda c: reussis[c]["facteur"])
        motif = "equivalent_plus_rapide"
    else:
        admissibles = [c for c, l in lignes.items() if l["admissible"]]
        if not admissibles:
            return {"meilleur": meilleur, "lignes": lignes, "retenu": "", "motif": "aucun_admissible"}
        retenu = min(admissibles, key=lambda c: (reussis[c]["wer"], reussis[c]["facteur"]))
        motif = "plus_juste_admissible"
    return {"meilleur": meilleur, "retenu": retenu, "motif": motif, "lignes": lignes,
            "equivalents": sorted(candidats, key=lambda c: reussis[c]["facteur"])}


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def _n(valeur: float, decimales: int = 1) -> str:
    return langues.nombre(valeur, decimales)


def _pct(partie: float, total: float) -> float:
    return 100.0 * partie / total if total else 0.0


def _entete(mat, titre_cle: str) -> list[str]:
    from . import moteur_openvino
    from .banc import _alimentation

    t = langues.t
    lignes = [t(titre_cle, nom=NOM_APPLICATION, version=VERSION, date=datetime.now().strftime("%Y-%m-%d")), ""]
    ov = moteur_openvino.version() if moteur_openvino.installe() else ""
    lignes.append(t("camp.rapport.machine", processeur=mat.cpu_nom or "?", memoire=f"{mat.ram_go:.0f}",
                    alimentation=_alimentation()))
    lignes.append(t("camp.rapport.openvino", version=ov or "-",
                    peripheriques=", ".join(moteur_openvino.peripheriques_disponibles()) if ov else "-"))
    return lignes


def _ligne_vitesse(r: dict) -> str:
    return langues.t("camp.rapport.vitesse", facteur=_n(r.get("facteur", 0), 2),
                     heure=presets.formater_duree(float(r.get("facteur", 0)) * 3600),
                     chargement=_n(r.get("chargement_s", 0), 0), memoire=_n(r.get("memoire_go", 0), 1),
                     debut=r.get("heure_debut", "?"), fin=r.get("heure_fin", "?"))


def rediger_rapport(mat, corpus_info: dict, resultats: dict[str, dict], agregats: dict[str, dict],
                    decision: dict, temoins: dict[str, float], doutes: dict, glossaire: dict,
                    peripherique: str, duree_totale: float) -> str:
    """Rapport de la partie publique : des nombres seulement."""
    from .banc import _masquer
    from .corpus import ATTRIBUTION

    t = langues.t
    lignes = _entete(mat, "camp.rapport.titre")
    lignes += ["", t("camp.rapport.section.corpus")]
    lignes.append("  - " + t("camp.rapport.corpus", extraits=corpus_info["extraits"],
                             reunions=corpus_info["reunions"], minutes=_n(corpus_info["duree_s"] / 60, 1),
                             mots=corpus_info["mots"], chev=_n(_pct(corpus_info["chev"], corpus_info["mots"]), 0),
                             anglais=corpus_info["anglais"]))
    lignes.append("  - " + t("camp.rapport.armes_egales"))
    lignes.append("  - " + t("camp.rapport.source", attribution=ATTRIBUTION))

    lignes += ["", t("camp.rapport.section.reglages")]
    for reglage in CANDIDATS:
        r = resultats.get(reglage.cle)
        if r is None:
            continue
        nom = libelle(reglage, r.get("peripherique") or peripherique)
        if reglage.actuel in ("qualite", "rapide"):
            nom += " " + t("camp.rapport.preset_actuel", preset=presets.nom_preset(reglage.actuel))
        if r.get("etat") == NON_PRIS_EN_CHARGE:
            lignes.append(f"  - {reglage.cle} : {nom} : " + t("camp.rapport.non_pris_en_charge"))
            continue
        if r.get("etat") != "ok" or reglage.cle not in agregats:
            lignes.append(f"  - {reglage.cle} : {nom} : " + t("camp.rapport.echec", etat=r.get("etat", "?"),
                                                              detail=r.get("erreur", "")))
            continue
        a = agregats[reglage.cle]
        lignes.append(f"  - {reglage.cle} : {nom}")
        lignes.append("      " + t("camp.rapport.wer", wer=_n(a["wer"], 1), bas=_n(a["ic"][0], 1),
                                   haut=_n(a["ic"][1], 1), sub=a["sub"], sup=a["sup"], ins=a["ins"],
                                   mots=a["mots_ref"]))
        lignes.append("      " + t("camp.rapport.chevauchement",
                                   chev=_n(_pct(a["chev_perdus"], a["chev_total"]), 0),
                                   hors=_n(_pct(a["hors_perdus"], a["hors_total"]), 0)))
        lignes.append("      " + t("camp.rapport.inventions", n=a["insertions_longues"],
                                   mots=a["mots_insertions_longues"], seuil=MOTS_INSERTION_LONGUE,
                                   longs=_n(_pct(a["segments_longs"], a["segments"]), 1),
                                   segments=a["segments"], duree=_n(SEGMENT_LONG_S, 0)))
        lignes.append("      " + _ligne_vitesse(r))
        if reglage.cle in temoins:
            lignes.append("      " + t("camp.rapport.temoin", wer=_n(temoins[reglage.cle], 1)))

    lignes += ["", t("camp.rapport.section.verdict")]
    lignes.append("  - " + t("camp.rapport.regle", ecart=_n(ECART_EQUIVALENT, 0), plafond=_n(ECART_MAX, 0)))
    if not decision or not decision.get("retenu"):
        lignes.append("  - " + t("camp.rapport.aucun_verdict"))
    else:
        retenu = PAR_CLE[decision["retenu"]]
        r = resultats[retenu.cle]
        a = agregats[retenu.cle]
        lignes.append("  - " + t("camp.rapport.retenu", code=retenu.cle,
                                 reglage=libelle(retenu, r.get("peripherique") or peripherique)))
        lignes.append("      " + t(f"camp.rapport.motif.{decision['motif']}",
                                   meilleur=decision["meilleur"]))
        for cle, l in sorted(decision["lignes"].items(), key=lambda x: resultats[x[0]]["facteur"]):
            etat = t("camp.rapport.equivalent") if l["equivalent"] else t("camp.rapport.distinct")
            if not l["admissible"]:
                etat += ", " + t("camp.rapport.trop_lent")
            lignes.append("      " + t("camp.rapport.ecart", code=cle, ecart=_n(l["ecart"], 1),
                                       bas=_n(l["ecart_ic"][0], 1), haut=_n(l["ecart_ic"][1], 1), etat=etat))
        actuel = resultats.get("ct2-v3-f5")
        if actuel and actuel.get("etat") == "ok" and retenu.cle != "ct2-v3-f5" and "ct2-v3-f5" in agregats:
            lignes.append("  - " + t("camp.rapport.contre_qualite", ecart=_n(a["wer"] - agregats["ct2-v3-f5"]["wer"], 1),
                                     rapport=_n(float(actuel["facteur"]) / max(1e-9, float(r["facteur"])), 1)))
        lignes.append("  - " + t("camp.rapport.cout_" + ("ov" if retenu.moteur == "openvino" else "ct2")))
        lignes.append("  - " + t("camp.rapport.pour_une_heure",
                                 duree=presets.formater_duree(float(r["facteur"]) * 3600)))

    lignes += ["", t("camp.rapport.section.doutes")]
    if doutes.get("ct2"):
        d = doutes["ct2"]
        lignes.append("  - " + t("camp.rapport.doute_ct2", code=d["cle"], seuil=_n(SEUIL_INCERTAIN, 2),
                                 part=_n(_pct(d["incertains"], d["mots"]), 0),
                                 rappel=_n(_pct(d["incertains_errones"], d["erreurs"]), 0),
                                 precision=_n(_pct(d["incertains_errones"], d["incertains"]), 0)))
    if doutes.get("seconde"):
        d = doutes["seconde"]
        lignes.append("  - " + t("camp.rapport.doute_seconde", code=d["cle"], second=d["second"],
                                 part=_n(_pct(d["signales"], d["mots"]), 0),
                                 rappel=_n(_pct(d["signales_errones"], d["erreurs"]), 0),
                                 precision=_n(_pct(d["signales_errones"], d["signales"]), 0),
                                 cout=_n(d["cout"], 0)))
    if not doutes:
        lignes.append("  - " + t("camp.rapport.doute_aucun"))

    lignes += ["", t("camp.rapport.section.glossaire")]
    lignes.append("  - " + t("camp.rapport.glossaire_public"))
    lignes.append("  - " + t("camp.rapport.glossaire_poste", termes=glossaire["termes"],
                             exemples=glossaire["exemples"]))
    if glossaire["exemples"] and glossaire["exemples"] == glossaire["termes"]:
        lignes.append("      " + t("camp.rapport.glossaire_exemples"))

    lignes += ["", t("camp.rapport.duree", duree=presets.formater_duree(duree_totale))]
    if decision and decision.get("retenu"):
        lignes.append(t("camp.rapport.appliquer"))
    lignes.append(t("camp.rapport.remarque"))
    return _masquer("\n".join(lignes)) + "\n"


# ---------------------------------------------------------------------------
# Orchestration de la partie publique
# ---------------------------------------------------------------------------

def _heure() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _temoin(dossier: Path) -> dict | None:
    """Extrait de parole lue du banc (FLEURS), converti au format du corpus."""
    from . import audio, banc
    from .corpus import ecrire_wav16

    if not banc.EXTRAIT.is_file() or not banc.REFERENCE.is_file():
        return None
    cible = dossier / "temoin-fleurs.wav"
    if not cible.is_file():
        signal = audio.decoder(banc.EXTRAIT)
        ecrire_wav16(cible, np.clip(np.round(signal * 32767.0), -32768, 32767).astype("<i2"))
    texte = banc.REFERENCE.read_text(encoding="utf-8")
    return {"id": "temoin-fleurs", "wav": str(cible),
            "reference": {"mots": [[m, 0, 0, 0, False] for m in texte.split()]}}


def _peripherique_ov(force: str = "") -> str:
    from . import moteur_openvino

    if force:
        return force.upper()
    if not moteur_openvino.installe():
        return ""
    return "GPU" if "GPU" in moteur_openvino.peripheriques_disponibles() else "CPU"


def _glossaire_du_poste() -> dict:
    from . import vocabulaire

    termes = vocabulaire.termes()
    return {"termes": len(termes), "exemples": vocabulaire.nombre_exemples_anciens(termes)}


def _choisir(reglages: str) -> list[Reglage]:
    if not reglages:
        return list(CANDIDATS)
    voulus = [c.strip() for c in reglages.split(",") if c.strip()]
    inconnus = [c for c in voulus if c not in PAR_CLE]
    if inconnus:
        raise journal.ErreurLisible(langues.t("camp.reglage_inconnu.titre"),
                                    langues.t("camp.reglage_inconnu.msg", cles=", ".join(inconnus),
                                              connues=", ".join(PAR_CLE)))
    return [PAR_CLE[c] for c in voulus]


def _jouer(reglages: list[Reglage], extraits: list[dict], dossier: Path, peripherique: str,
           parametres_communs: dict, dire: Callable[[str], None],
           interrompu: Callable[[], bool] | None) -> dict[str, dict]:
    """Passe chaque réglage pas encore fait ; chaque résultat est écrit aussitôt."""
    (dossier / "reglages").mkdir(parents=True, exist_ok=True)
    ids = [e["id"] for e in extraits]
    resultats: dict[str, dict] = {}
    duree_max = max((float(e.get("duree_s") or 120.0) for e in extraits), default=120.0)
    for rang, reglage in enumerate(reglages, 1):
        if interrompu and interrompu():
            break
        fichier_resultat = dossier / "reglages" / f"{reglage.cle}.json"
        fichier_textes = dossier / "reglages" / f"{reglage.cle}-textes.json"
        if fichier_resultat.is_file() and fichier_textes.is_file():
            try:
                deja = json.loads(fichier_resultat.read_text(encoding="utf-8"))
                if deja.get("etat") == "ok" and deja.get("extraits") == ids:
                    resultats[reglage.cle] = deja
                    dire(langues.t("camp.etape.deja", code=reglage.cle))
                    continue
            except (OSError, ValueError):
                pass
        if reglage.moteur == "openvino" and not peripherique:
            resultats[reglage.cle] = {"cle": reglage.cle, "etat": "openvino_absent"}
            continue
        if reglage.moteur == "openvino" and not pris_en_charge(reglage, peripherique):
            # Limite connue d'OpenVINO, pas une panne : rien n'est lancé, et le
            # verdict ne voit pas ce réglage (seuls les « ok » y entrent).
            resultats[reglage.cle] = {"cle": reglage.cle, "etat": NON_PRIS_EN_CHARGE,
                                      "peripherique": peripherique}
            dire(langues.t("camp.etape.non_pris_en_charge", code=reglage.cle, peripherique=peripherique))
            continue
        dire(langues.t("camp.etape.reglage", numero=rang, total=len(reglages),
                       reglage=libelle(reglage, peripherique), code=reglage.cle))
        parametres = {**parametres_communs, "cle": reglage.cle, "peripherique": peripherique,
                      "extraits": [{k: e[k] for k in ("id", "wav", "npy") if k in e} for e in extraits],
                      "sortie": str(fichier_textes)}
        debut = _heure()
        resultat = lancer_reglage(
            parametres, inactivite_max=900.0 + 4.0 * duree_max,
            rappel=lambda p: dire(langues.t("camp.etape.progres", code=reglage.cle,
                                            n=p["progres"], total=p["total"])),
            interrompu=interrompu)
        resultat.update({"heure_debut": debut, "heure_fin": _heure(), "extraits": ids})
        resultats[reglage.cle] = resultat
        fichier_resultat.write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultats


def _textes(dossier: Path, cle: str) -> dict:
    try:
        return json.loads((dossier / "reglages" / f"{cle}-textes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def dossier_publique() -> Path:
    from .corpus import VERSION_CORPUS

    return DOSSIER_CAMPAGNES / f"publique-v{VERSION_CORPUS}"


def lire_proprietes(texte: str) -> dict:
    """
    « CLE=VALEUR,CLE=VALEUR » en propriétés d'OpenVINO : YES/NO et TRUE/FALSE
    en booléens, entiers en entiers, le reste tel quel (« LOW », « f32 »).
    """
    proprietes: dict = {}
    for morceau in (texte or "").split(","):
        cle, _, valeur = morceau.partition("=")
        cle, valeur = cle.strip(), valeur.strip()
        if not cle or not valeur:
            continue
        if valeur.upper() in ("YES", "TRUE", "NO", "FALSE"):
            proprietes[cle] = valeur.upper() in ("YES", "TRUE")
        elif valeur.lstrip("-").isdigit():
            proprietes[cle] = int(valeur)
        else:
            proprietes[cle] = valeur
    return proprietes


def suffixe_essai(limite: int, peripherique: str, proprietes: dict) -> str:
    """
    Dossier d'une campagne réduite : le nombre d'extraits, plus le périphérique
    forcé et les propriétés d'essai, pour que deux variantes ne se mêlent pas
    (chaque réglage déjà fait est repris tel quel d'un passage à l'autre).
    """
    import re as _re

    morceaux = [f"-essai{limite}"]
    if peripherique:
        morceaux.append("-" + _re.sub(r"[^a-z0-9]+", "-", peripherique.lower()).strip("-"))
    for cle, valeur in sorted(proprietes.items()):
        morceaux.append("-" + _re.sub(r"[^a-z0-9]+", "-", f"{cle}-{valeur}".lower()).strip("-"))
    return "".join(morceaux)


def executer(reglages: str = "", limite: int = 0, paquet: str = "", peripherique: str = "",
             recommencer: bool = False, telecharger: bool = False, temoin: bool = True,
             rappel: Callable[[str], None] | None = None,
             interrompu: Callable[[], bool] | None = None, proprietes_ov: dict | None = None) -> dict:
    from . import energie

    with energie.sans_veille():
        return _executer(reglages, limite, paquet, peripherique, recommencer, telecharger,
                         temoin, rappel, interrompu, proprietes_ov or {})


def _executer(reglages: str, limite: int, paquet: str, peripherique: str, recommencer: bool,
              telecharger: bool, temoin: bool, rappel: Callable[[str], None] | None,
              interrompu: Callable[[], bool] | None, proprietes_ov: dict | None = None) -> dict:
    from . import config as config_module, corpus
    from .comparaison import nombre_mots_anglais

    depart = time.time()
    config_module.charger()  # langue de l'interface, celle du rapport

    def dire(message: str) -> None:
        journal.info("Campagne : %s", message)
        if rappel:
            rappel(message)

    choisis = _choisir(reglages)
    proprietes_ov = dict(proprietes_ov or {})
    if (proprietes_ov or ":" in (peripherique or "")) and not limite:
        # Une variante d'essai ne doit jamais écrire le verdict public du poste.
        limite = 20
    dossier = dossier_publique() if not limite else dossier_publique().with_name(
        dossier_publique().name + suffixe_essai(limite, peripherique, proprietes_ov))
    if recommencer and dossier.exists():
        shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True, exist_ok=True)
    mat = materiel.detecter()
    peripherique = _peripherique_ov(peripherique)

    if telecharger:
        for depot in dict.fromkeys(depot_du(r) for r in choisis
                                   if r.moteur == "ctranslate2" or peripherique):
            if moteur.etat_modele(depot)["etat"] != "complet":
                dire(langues.t("camp.etape.modele", modele=moteur.nom_court(depot)))
                moteur.assurer_modele_telecharge(depot, None, None, annoncer=False)

    dire(langues.t("camp.etape.corpus", mo=_n(corpus.octets_a_telecharger(limite) / 1e6, 0)))

    def rappel_corpus(etat: str) -> None:
        if etat.startswith("paquet:"):
            dire(langues.t("camp.etape.paquet"))
        elif etat.startswith("reseau:"):
            dire(langues.t("camp.etape.reseau", rang=etat.split(":", 1)[1]))

    try:
        extraits = corpus.preparer(rappel_corpus, paquet or None, limite, interrompu)
    except corpus.ErreurCorpus as exc:
        raise journal.ErreurLisible(langues.t("camp.corpus_absent.titre"),
                                    langues.t("camp.corpus_absent.msg", paquet=corpus.NOM_PAQUET,
                                              detail=exc.detail or exc.motif)) from exc
    liste = [{"id": e.ident, "wav": str(e.wav), "duree_s": e.duree} for e in extraits]
    temoin_entree = _temoin(dossier) if temoin else None
    if temoin_entree:
        liste.append({"id": temoin_entree["id"], "wav": temoin_entree["wav"], "duree_s": 44.0})

    communs = {"langue": "fr", "glossaire": False, "corrections": False}
    if proprietes_ov:
        communs["proprietes_ov"] = proprietes_ov
    resultats = _jouer(choisis, liste, dossier, peripherique, communs, dire, interrompu)

    # Mesures : partie publique (sans le témoin), témoin à part.
    ordre = [e.ident for e in extraits]
    references = {e.ident: e.reference for e in extraits}
    par_extrait: dict[str, dict[str, dict]] = {}
    temoins: dict[str, float] = {}
    textes_par_cle: dict[str, dict] = {}
    for cle, r in resultats.items():
        if r.get("etat") != "ok":
            continue
        textes = _textes(dossier, cle)
        textes_par_cle[cle] = textes
        par_extrait[cle] = {i: mesurer_extrait(references[i], textes[i]["segments"])
                            for i in ordre if i in textes}
        if temoin_entree and temoin_entree["id"] in textes:
            m = mesurer_extrait(temoin_entree["reference"], textes[temoin_entree["id"]]["segments"])
            temoins[cle] = round(100.0 * m["erreurs"] / max(1, m["mots_ref"]), 2)
        # Vitesse sur le corpus public seul, témoin exclu.
        calc = sum(textes[i]["calcul_s"] for i in ordre if i in textes)
        audio_s = sum(textes[i]["duree_s"] for i in ordre if i in textes)
        if audio_s:
            r["facteur"] = round(calc / audio_s, 4)
    indices = _tirages(len(ordre)) if ordre else None
    agregats = {cle: agreger(m, ordre, indices) for cle, m in par_extrait.items()}
    for cle in list(par_extrait):
        if agregats[cle]["extraits"] != len(ordre):
            par_extrait.pop(cle)
            agregats.pop(cle)
            resultats[cle]["etat"] = "incomplet"
    decision = verdict({c: {**resultats[c], "wer": agregats[c]["wer"]} for c in agregats}, ordre, par_extrait)

    doutes: dict = {}
    ct2 = [c for c in agregats if PAR_CLE[c].moteur == "ctranslate2" and agregats[c]["avec_probabilite"]]
    if ct2:
        cle = decision.get("retenu") if decision.get("retenu") in ct2 else min(ct2, key=lambda c: agregats[c]["wer"])
        a = agregats[cle]
        doutes["ct2"] = {"cle": cle, "mots": a["mots_hyp"], "incertains": a["incertains"],
                         "incertains_errones": a["incertains_errones"], "erreurs": a["hyp_erronees"]}
    retenu = decision.get("retenu") if decision else ""
    if retenu:
        autres = [c for c in agregats if c != retenu and PAR_CLE[c].modele != PAR_CLE[retenu].modele]
        if autres:
            second = min(autres, key=lambda c: resultats[c]["facteur"])
            cumul = {"mots": 0, "signales": 0, "erreurs": 0, "signales_errones": 0}
            for i in ordre:
                s = signalements(references[i], textes_par_cle[retenu][i]["segments"],
                                 textes_par_cle[second][i]["segments"])
                for k in cumul:
                    cumul[k] += s[k]
            doutes["seconde"] = {**cumul, "cle": retenu, "second": second,
                                 "cout": 100.0 * float(resultats[second]["facteur"])
                                 / max(1e-9, float(resultats[retenu]["facteur"]))}

    tous_mots = [mots_reference(references[i]) for i in ordre]
    corpus_info = {"extraits": len(ordre), "reunions": len({e.reunion for e in extraits}),
                   "duree_s": sum(e.duree for e in extraits),
                   "mots": sum(len(m) for m, _c in tous_mots),
                   "chev": sum(sum(c) for _m, c in tous_mots),
                   "anglais": sum(nombre_mots_anglais(m) for m, _c in tous_mots)}
    rapport = rediger_rapport(mat, corpus_info, resultats, agregats, decision, temoins, doutes,
                              _glossaire_du_poste(), peripherique, time.time() - depart)
    fichier = dossier / f"rapport-campagne-{datetime.now():%Y%m%d-%H%M}.txt"
    fichier.write_text(rapport, encoding="utf-8")
    verdict_donnees = {}
    if retenu:
        r = resultats[retenu]
        verdict_donnees = {"cle": retenu, "moteur": PAR_CLE[retenu].moteur, "modele": PAR_CLE[retenu].modele,
                           "faisceau": PAR_CLE[retenu].faisceau, "preset": PAR_CLE[retenu].preset,
                           "peripherique": r.get("peripherique", ""), "facteur": r["facteur"],
                           "lot": int(r.get("lot") or 0), "duree_audio": corpus_info["duree_s"],
                           "wer": agregats[retenu]["wer"], "date": _heure()}
    # Écrit à côté puis renommé : une lecture concurrente (campagne « réunion »
    # lancée pendant ce temps) voit l'ancien fichier ou le nouveau, jamais un
    # fichier à moitié écrit.
    provisoire = dossier / "verdict.json.tmp"
    provisoire.write_text(json.dumps({
        "verdict": verdict_donnees,
        "agregats": agregats, "decision": decision,
        "resultats": resultats}, ensure_ascii=False, indent=1, default=list), encoding="utf-8")
    os.replace(provisoire, dossier / "verdict.json")
    return {"rapport": rapport, "fichier": str(fichier), "verdict": verdict_donnees,
            "dossier": str(dossier), "decision": decision}


def appliquer(verdict_donnees: dict) -> dict:
    """Écrit le réglage retenu dans la configuration de l'application, signé pour ce poste."""
    from . import calibration, config as config_module, reglage_machine

    config = config_module.charger()
    mat = materiel.detecter()
    actuel = {k: v for k, v in reglage_machine.lire(config, mat).items()
              if k in ("fils", "lot")}
    nouveau = {**actuel, "moteur": verdict_donnees["moteur"], "faisceau": int(verdict_donnees["faisceau"]),
               "source": "campagne"}
    if verdict_donnees["moteur"] == "openvino":
        nouveau["peripherique"] = verdict_donnees.get("peripherique") or "CPU"
    propre = reglage_machine.enregistrer(config, mat, nouveau)
    config["preset"] = verdict_donnees["preset"]
    config_module.sauver(config)
    cle = ("openvino-" + str(nouveau.get("peripherique", "cpu")).lower()
           if nouveau["moteur"] == "openvino" else mat.peripherique)
    duree = float(verdict_donnees.get("duree_audio") or 0)
    if duree > 0 and float(verdict_donnees.get("facteur") or 0) > 0:
        calibration.enregistrer(verdict_donnees["modele"], cle, int(verdict_donnees["faisceau"]), duree,
                                float(verdict_donnees["facteur"]) * duree, mat,
                                lot=0 if nouveau["moteur"] == "openvino" else int(verdict_donnees.get("lot") or 0),
                                duree_minimale=20.0)
    return propre


def dernier_verdict() -> dict:
    try:
        return json.loads((dossier_publique() / "verdict.json").read_text(encoding="utf-8")).get("verdict") or {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Réunion réelle (confidentielle) : accord entre réglages, rien d'autre
# ---------------------------------------------------------------------------

def choisir_ancre(retenu: str, reussis: list[str]) -> tuple[str, str]:
    """
    Réglage auquel comparer les autres sur une réunion, et pourquoi.

    Le réglage retenu par la campagne publique s'il a réussi ici ; sinon le
    preset « Qualité maximale », en disant si c'est faute de verdict ou parce
    que le réglage retenu a échoué sur cette réunion ; sinon le premier réussi.
    """
    if retenu and retenu in reussis:
        return retenu, "verdict"
    if "ct2-v3-f5" in reussis:
        return "ct2-v3-f5", "verdict_echec" if retenu else "qualite"
    return (reussis[0] if reussis else ""), "premier"


def rediger_rapport_reunion(mat, duree: float, resultats: dict[str, dict], accords: dict[str, dict],
                            ancre: str, ancre_source: str, glossaire: dict, trouves: dict[str, int],
                            segments: dict[str, dict], peripherique: str, duree_totale: float,
                            retenu: str = "") -> str:
    from .banc import _masquer

    t = langues.t
    lignes = _entete(mat, "camp.reunion.titre")
    lignes += ["", t("camp.reunion.extrait", minutes=_n(duree / 60, 1))]
    lignes.append(t("camp.reunion.ancre", code=ancre or "-",
                    source=t(f"camp.reunion.ancre.{ancre_source}", retenu=retenu or "-")))
    lignes.append(t("camp.reunion.glossaire", termes=glossaire["termes"], exemples=glossaire["exemples"]))
    lignes.append("")
    for reglage in CANDIDATS:
        r = resultats.get(reglage.cle)
        if r is None:
            continue
        nom = libelle(reglage, r.get("peripherique") or peripherique)
        if r.get("etat") == NON_PRIS_EN_CHARGE:
            lignes.append(f"  - {reglage.cle} : {nom} : " + t("camp.rapport.non_pris_en_charge"))
            continue
        if r.get("etat") != "ok":
            lignes.append(f"  - {reglage.cle} : {nom} : " + t("camp.rapport.echec", etat=r.get("etat", "?"),
                                                              detail=r.get("erreur", "")))
            continue
        lignes.append(f"  - {reglage.cle} : {nom}")
        if reglage.cle in accords:
            a = accords[reglage.cle]
            lignes.append("      " + t("camp.reunion.accord", desaccord=_n(a["desaccord"], 1), ancre=ancre,
                                       mots=a["mots"], mots_ancre=a["mots_ancre"],
                                       en_plus=a["en_plus"], en_moins=a["en_moins"], mots_seg=4))
        s = segments.get(reglage.cle, {})
        lignes.append("      " + t("camp.reunion.segments", n=s.get("n", 0), mediane=_n(s.get("mediane", 0), 1),
                                   longs=_n(_pct(s.get("longs", 0), s.get("n", 0)), 1), duree=_n(SEGMENT_LONG_S, 0)))
        lignes.append("      " + t("camp.reunion.termes", trouves=trouves.get(reglage.cle, 0),
                                   termes=glossaire["termes"]))
        lignes.append("      " + _ligne_vitesse(r))
    lignes += ["", t("camp.rapport.duree", duree=presets.formater_duree(duree_totale)),
               t("camp.reunion.remarque")]
    return _masquer("\n".join(lignes)) + "\n"


def executer_reunion(fichier: str, debut: float = 0.0, duree: float = 600.0, reglages: str = "",
                     peripherique: str = "", rappel: Callable[[str], None] | None = None,
                     interrompu: Callable[[], bool] | None = None) -> dict:
    from . import energie

    with energie.sans_veille():
        return _executer_reunion(fichier, debut, duree, reglages, peripherique, rappel, interrompu)


def _executer_reunion(fichier: str, debut: float, duree: float, reglages: str, peripherique: str,
                      rappel: Callable[[str], None] | None,
                      interrompu: Callable[[], bool] | None) -> dict:
    import statistics

    from . import audio, config as config_module, vocabulaire
    from .comparaison import (MOTS_SEGMENT, _occurrences, aligner, caler_sur_pauses,
                              construire_texte, normaliser)

    depart = time.time()

    def dire(message: str) -> None:
        journal.info("Campagne, réunion : %s", message)
        if rappel:
            rappel(message)

    source = Path(fichier)
    if not source.is_file():
        raise journal.ErreurLisible(langues.t("audio.introuvable.titre"),
                                    langues.t("audio.introuvable.msg", nom=source.name))
    choisis = _choisir(reglages)
    config = config_module.charger()
    mat = materiel.detecter()
    peripherique = _peripherique_ov(peripherique)
    cle_dossier = hashlib.sha256(f"{source.resolve()}|{debut:.1f}|{duree:.1f}".encode("utf-8")).hexdigest()[:12]
    dossier = DOSSIER_CAMPAGNES / f"reunion-{cle_dossier}"
    dossier.mkdir(parents=True, exist_ok=True)

    extrait = dossier / "extrait.npy"
    if not extrait.is_file():
        dire(langues.t("comp.etape.decodage"))
        duree_fichier = audio.duree(source)
        signal = audio.decoder(source, filtres_salle=bool(config.get("filtres_salle")), debut=debut, duree=duree)
        fin_fichier = not duree or not duree_fichier or debut + signal.size / 16000 >= duree_fichier - 1.0
        premier, dernier = caler_sur_pauses(signal, debut <= 0.5, fin_fichier)
        np.save(extrait, np.ascontiguousarray(signal[premier:dernier]))
        del signal
    duree_extrait = float(np.load(extrait, mmap_mode="r").shape[0]) / 16000

    langue = str(config.get("langue", "fr") or "fr")
    communs = {"langue": langue, "glossaire": bool(config.get("utiliser_glossaire", True)),
               "corrections": bool(config.get("appliquer_corrections", True))}
    entree = [{"id": "reunion", "npy": str(extrait), "duree_s": duree_extrait}]
    # Verdict public lu AVANT de transcrire : celui qui vaut au lancement, et
    # non celui qu'une campagne publique écrirait pendant ce temps.
    verdict_public = dernier_verdict()
    resultats = _jouer(choisis, entree, dossier, peripherique, communs, dire, interrompu)

    textes = {c: construire_texte(_textes(dossier, c)["reunion"]["segments"])
              for c, r in resultats.items() if r.get("etat") == "ok"}
    for c in textes:
        resultats[c]["facteur"] = round(float(resultats[c]["calcul_s"]) / max(1e-9, duree_extrait), 4)
    ancre, ancre_source = choisir_ancre(verdict_public.get("cle", ""), list(textes))

    accords: dict[str, dict] = {}
    if ancre:
        mots_ancre = [j.mot for j in textes[ancre].jetons]
        for c, texte in textes.items():
            mots = [j.mot for j in texte.jetons]
            bilan = aligner(mots_ancre, mots)
            en_plus = en_moins = 0
            for i1, i2, j1, j2 in bilan.passages():
                if (j2 - j1) - (i2 - i1) >= MOTS_SEGMENT:
                    en_plus += 1
                elif (i2 - i1) - (j2 - j1) >= MOTS_SEGMENT:
                    en_moins += 1
            accords[c] = {"desaccord": bilan.taux("a"), "mots": len(mots), "mots_ancre": len(mots_ancre),
                          "en_plus": en_plus, "en_moins": en_moins}
    termes = vocabulaire.termes() if communs["glossaire"] else []
    formes = [normaliser(t) for t in termes]
    trouves = {c: sum(1 for f in formes if f and _occurrences([j.mot for j in tx.jetons], f))
               for c, tx in textes.items()}
    segments = {}
    for c in textes:
        durees = [max(0.0, s["f"] - s["d"]) for s in _textes(dossier, c)["reunion"]["segments"]]
        segments[c] = {"n": len(durees), "mediane": statistics.median(durees) if durees else 0.0,
                       "longs": sum(1 for d in durees if d > SEGMENT_LONG_S)}
    glossaire = {"termes": len(termes), "exemples": vocabulaire.nombre_exemples_anciens(termes)}
    rapport = rediger_rapport_reunion(mat, duree_extrait, resultats, accords, ancre, ancre_source,
                                      glossaire, trouves, segments, peripherique, time.time() - depart,
                                      retenu=verdict_public.get("cle", ""))
    fichier_rapport = dossier / f"rapport-reunion-{datetime.now():%Y%m%d-%H%M}.txt"
    fichier_rapport.write_text(rapport, encoding="utf-8")
    return {"rapport": rapport, "fichier": str(fichier_rapport), "dossier": str(dossier)}


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------

def _valeur(arguments: list[str], option: str, defaut: str = "") -> str:
    if option in arguments:
        rang = arguments.index(option)
        if rang + 1 < len(arguments):
            return arguments[rang + 1]
    return defaut


def principal_cli(arguments: list[str]) -> int:
    if "--campagne-essai" in arguments:
        return principal_essai(_valeur(arguments, "--campagne-essai"))
    from .comparaison import lire_duree

    # Sortie redirigée vers un fichier (lancement en tâche de fond) : un
    # caractère hors de la page de code ne doit pas arrêter la campagne.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass

    def afficher(message: str) -> None:
        print("  " + message, flush=True)

    try:
        if "--reunion" in arguments:
            fichier = _valeur(arguments, "--reunion")
            if not fichier:
                print(langues.t("camp.cli.usage"))
                return 2
            resultat = executer_reunion(
                fichier, debut=lire_duree(_valeur(arguments, "--debut", "0")),
                duree=lire_duree(_valeur(arguments, "--duree", "600")),
                reglages=_valeur(arguments, "--reglages"),
                peripherique=_valeur(arguments, "--peripherique"), rappel=afficher)
            print()
            print(resultat["rapport"])
            print(langues.t("camp.cli.fichier", fichier=resultat["fichier"]))
            return 0
        resultat = executer(
            reglages=_valeur(arguments, "--reglages"),
            limite=int(_valeur(arguments, "--limite-extraits", "0") or 0),
            paquet=_valeur(arguments, "--corpus"), peripherique=_valeur(arguments, "--peripherique"),
            recommencer="--recommencer" in arguments, telecharger="--telecharger" in arguments,
            temoin="--sans-temoin" not in arguments, rappel=afficher,
            proprietes_ov=lire_proprietes(_valeur(arguments, "--proprietes-ov")))
    except journal.ErreurLisible as exc:
        print(f"{exc.titre}\n{exc.message}")
        return 1
    print()
    print(resultat["rapport"])
    print(langues.t("camp.cli.fichier", fichier=resultat["fichier"]))
    if "--appliquer" in arguments:
        if resultat["verdict"]:
            appliquer(resultat["verdict"])
            print(langues.t("camp.cli.applique", code=resultat["verdict"]["cle"]))
        else:
            print(langues.t("camp.cli.rien_a_appliquer"))
    return 0 if resultat["verdict"] else 1


def options_reconnues(arguments: list[str]) -> bool:
    return "--campagne" in arguments or "--campagne-essai" in arguments


if __name__ == "__main__":
    sys.exit(principal_cli(sys.argv[1:]))
