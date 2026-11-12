"""
Banc des rythmes : ce que coûte et ce que gêne chaque position du réglage
« je travaille en même temps » (voir `app/rythme.py`).

Pour chaque rythme, l'extrait du banc d'essai (43,6 s de parole lue, FLEURS,
CC-BY-4.0) est transcrit plusieurs fois bout à bout dans un processus à part,
avec les bornes du rythme posées dans ce processus comme la file de
l'application les pose dans le sien. Pendant ce temps, une TÂCHE TÉMOIN tourne
dans le processus du banc, en priorité normale : toutes les 100 ms, elle
demande à dormir 20 ms puis fait un petit calcul fixe. Elle joue le rôle d'une
application de l'utilisateur. On relève :

  - la vitesse (durée de calcul sur durée de l'audio, pauses comprises) et ce
    qu'elle donnerait pour une heure de réunion ;
  - la mémoire au pic du processus de transcription ;
  - le processeur laissé libre : 100 % moins la part du processeur entier
    prise par la transcription en moyenne ;
  - la gêne : durée du calcul témoin rapportée à sa durée sur un poste au repos
    (médiane et 95e centile), et retard du réveil du témoin (95e centile, ms) ;
  - le taux d'erreur sur l'extrait, pour vérifier qu'aucun rythme ne change le
    texte (les rythmes ne touchent ni au modèle ni au décodage).

Ligne de commande :

    scribouille-verifier.exe --banc --modes [--rythmes vitesse,equilibre,discret]
        [--moteur ctranslate2|openvino] [--peripherique GPU|CPU] [--repetitions 3]
        [--variantes-ov] [--sans-temoin-passif]

Sans plafond de priorité (variable `SCRIBOUILLE_BANC_PRIORITE_BASSE` absente),
les rapports de durée par rapport à la vitesse maximale sont rangés dans
`rapports-banc/modes.json` : ils remplacent les coefficients de repli des
estimations de durée (`rythme.coefficient`). Rien d'autre n'est modifié.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
from datetime import datetime
from typing import Callable

from . import VERSION, NOM_APPLICATION, journal, langues, materiel, moteur, presets, rythme
from .banc import DOSSIER_RAPPORTS, Essai, _masquer, lancer_essai, _alimentation

#: Calcul fixe de la tâche témoin (additions en Python, environ 1 à 2 ms au repos).
TRAVAIL_TEMOIN = 20000
SOMMEIL_TEMOIN_S = 0.020
CADENCE_TEMOIN_S = 0.100

#: Variantes de compilation d'OpenVINO mesurées à la demande (`--variantes-ov`),
#: en vitesse maximale. Documentation du greffon GPU d'OpenVINO 2026 : indice de
#: performance LATENCY (une requête à la fois, ce que fait Whisper) ou
#: THROUGHPUT ; chemin d'attention optimisé (SDPA) coupé, contournement publié
#: pour la justesse du faisceau sur la puce (ticket openvino.genai n° 2746).
VARIANTES_OV = (
    ("vitesse-latence", {"PERFORMANCE_HINT": "LATENCY"}, ("CPU", "GPU")),
    ("vitesse-debit", {"PERFORMANCE_HINT": "THROUGHPUT"}, ("CPU", "GPU")),
    ("vitesse-sans-sdpa", {"GPU_ENABLE_SDPA_OPTIMIZATION": False}, ("GPU",)),
)


class Temoin:
    """La petite application de l'utilisateur, simulée dans un fil."""

    def __init__(self):
        self.travaux: list[float] = []
        self.reveils: list[float] = []
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None

    def demarrer(self) -> "Temoin":
        self._arret.clear()
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()
        return self

    def _boucle(self) -> None:
        while not self._arret.is_set():
            debut = time.perf_counter()
            time.sleep(SOMMEIL_TEMOIN_S)
            self.reveils.append(max(0.0, time.perf_counter() - debut - SOMMEIL_TEMOIN_S))
            debut = time.perf_counter()
            somme = 0
            for valeur in range(TRAVAIL_TEMOIN):
                somme += valeur
            self.travaux.append(time.perf_counter() - debut)
            self._arret.wait(CADENCE_TEMOIN_S)

    def arreter(self) -> dict:
        self._arret.set()
        if self._fil is not None:
            self._fil.join(timeout=2)
        return resumer(self.travaux, self.reveils)


def _centile(valeurs: list[float], part: float) -> float:
    if not valeurs:
        return 0.0
    rangees = sorted(valeurs)
    return rangees[min(len(rangees) - 1, int(round(part * (len(rangees) - 1))))]


def resumer(travaux: list[float], reveils: list[float]) -> dict:
    return {"n": len(travaux),
            "travail_median_ms": round(1000 * statistics.median(travaux), 3) if travaux else 0.0,
            "travail_p95_ms": round(1000 * _centile(travaux, 0.95), 3),
            "reveil_p95_ms": round(1000 * _centile(reveils, 0.95), 2)}


def gene(temoin: dict, repos: dict) -> dict:
    """Rapports au poste au repos : 1,0 = aucune gêne mesurable."""
    base_med = float(repos.get("travail_median_ms") or 0)
    base_p95 = float(repos.get("travail_p95_ms") or 0)
    return {"median": round(temoin["travail_median_ms"] / base_med, 2) if base_med else 0.0,
            "p95": round(temoin["travail_p95_ms"] / base_p95, 2) if base_p95 else 0.0,
            "reveil_p95_ms": temoin["reveil_p95_ms"]}


def libre_pct(processeur_s: float, calcul_s: float, logiques: int) -> float:
    """Part du processeur entier laissée aux autres, en moyenne pendant le calcul."""
    if calcul_s <= 0 or logiques <= 0:
        return 0.0
    pris = processeur_s / calcul_s / logiques * 100.0
    return round(max(0.0, 100.0 - pris), 1)


def coefficients(resultats: list[dict]) -> dict[str, float]:
    """Durée de chaque rythme rapportée à la vitesse maximale (essais réussis seulement)."""
    par = {r["rythme"]: r for r in resultats if r.get("etat") == "ok" and r.get("variante") == r.get("rythme")}
    base = float((par.get("vitesse") or {}).get("facteur") or 0)
    if base <= 0:
        return {}
    return {nom: round(float(r["facteur"]) / base, 3) for nom, r in par.items() if nom != "vitesse"}


def executer(rythmes: list[str] | None = None, moteur_voulu: str = "", peripherique: str = "",
             repetitions: int = 3, variantes_ov: bool = False, passif_vitesse: bool = True,
             rappel: Callable[[str], None] | None = None) -> dict:
    from . import config as config_module, reglage_machine

    def dire(message: str) -> None:
        journal.info("Banc des rythmes : %s", message)
        if rappel:
            rappel(message)

    depart = time.time()
    config = config_module.charger()
    mat = materiel.detecter()
    reglage_machine.appliquer_au_materiel(config, mat)
    moteur_voulu = moteur_voulu or mat.moteur
    peripherique = (peripherique or mat.peripherique_openvino or "CPU").upper() \
        if moteur_voulu == "openvino" else "cpu"
    modele = presets.MODELE_TURBO
    depot = presets.depot_openvino(modele) if moteur_voulu == "openvino" else modele
    if moteur.etat_modele(depot)["etat"] != "complet":
        raise journal.ErreurLisible(langues.t("rbanc.modele_absent.titre"),
                                    langues.t("rbanc.modele_absent.msg", modele=moteur.nom_court(depot)))
    plafond = bool(os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE"))

    dire(langues.t("rbanc.etape.repos"))
    temoin = Temoin().demarrer()
    time.sleep(6.0)
    repos = temoin.arreter()

    plan: list[tuple[str, str, dict, dict]] = []
    for nom in (rythmes or list(rythme.RYTHMES)):
        nom = rythme.normaliser(nom)
        b = rythme.bornes(nom, mat)
        env = {"OMP_WAIT_POLICY": "PASSIVE"} if (b.attente_passive and moteur_voulu == "ctranslate2") else {}
        plan.append((nom, nom, {}, env))
    if passif_vitesse and moteur_voulu == "ctranslate2" and "vitesse" in [p[0] for p in plan]:
        plan.append(("vitesse-passive", "vitesse", {}, {"OMP_WAIT_POLICY": "PASSIVE"}))
    if variantes_ov and moteur_voulu == "openvino":
        for nom, proprietes, familles in VARIANTES_OV:
            if ("GPU" if peripherique != "CPU" else "CPU") in familles:
                plan.append((nom, "vitesse", proprietes, {}))

    resultats: list[dict] = []
    for rang, (variante, nom, proprietes, env) in enumerate(plan, 1):
        essai = Essai(variante, moteur=moteur_voulu, modele=modele,
                      peripherique=peripherique if moteur_voulu == "openvino" else "cpu",
                      fils=mat.fils_imposes, lot=presets.taille_lot("rapide", mat) if moteur_voulu == "ctranslate2" else 0,
                      faisceau=5 if moteur_voulu == "ctranslate2" else 1,
                      rythme=nom, repetitions=repetitions, proprietes=proprietes)
        dire(langues.t("rbanc.etape.essai", numero=rang, total=len(plan), variante=variante))
        temoin = Temoin().demarrer()
        resultat = lancer_essai(essai, env_ajout=env)
        mesure = temoin.arreter()
        resultat.update({"variante": variante, "rythme": nom, "temoin": mesure,
                         "gene": gene(mesure, repos), "passif": bool(env),
                         "proprietes": proprietes})
        if resultat.get("etat") == "ok":
            resultat["libre_pct"] = libre_pct(float(resultat.get("processeur_s") or 0),
                                              float(resultat.get("calcul_s") or 0),
                                              mat.coeurs_logiques or os.cpu_count() or 1)
        resultat.pop("texte", None)
        resultats.append(resultat)

    famille = "puce" if (moteur_voulu == "openvino" and peripherique != "CPU") or mat.cuda_disponible \
        else "processeur"
    coef = coefficients(resultats)
    if coef and not plafond:
        try:
            DOSSIER_RAPPORTS.mkdir(parents=True, exist_ok=True)
            chemin = DOSSIER_RAPPORTS / rythme.FICHIER_MESURES
            try:
                deja = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                deja = {}
            deja[famille] = coef
            chemin.write_text(json.dumps(deja, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        except OSError as exc:
            journal.attention("Coefficients des rythmes non écrits : %s", exc)
    rapport = rediger(mat, moteur_voulu, peripherique, repos, resultats, coef, plafond,
                      time.time() - depart, repetitions)
    fichier = ""
    try:
        DOSSIER_RAPPORTS.mkdir(parents=True, exist_ok=True)
        cible = DOSSIER_RAPPORTS / f"rapport-rythmes-{datetime.now():%Y%m%d-%H%M}.txt"
        cible.write_text(rapport, encoding="utf-8")
        fichier = str(cible)
    except OSError as exc:
        journal.attention("Rapport des rythmes non écrit : %s", exc)
    return {"rapport": rapport, "fichier": fichier, "resultats": resultats, "repos": repos,
            "coefficients": coef}


def rediger(mat, moteur_voulu: str, peripherique: str, repos: dict, resultats: list[dict],
            coef: dict, plafond: bool, duree_totale: float, repetitions: int) -> str:
    t = langues.t
    n = langues.nombre
    lignes = [t("rbanc.titre", nom=NOM_APPLICATION, version=VERSION,
                date=datetime.now().strftime("%Y-%m-%d")), ""]
    topo = mat.topologie
    lignes.append("  - " + t("banc.processeur") + f" : {mat.cpu_nom or '?'}")
    if topo.hybride:
        lignes.append("  - " + t("banc.topologie", p=topo.performants, e=topo.efficaces,
                                 lp=topo.basse_consommation, fils=mat.coeurs_logiques))
    else:
        lignes.append("  - " + t("banc.coeurs", coeurs=mat.coeurs_physiques, fils=mat.coeurs_logiques))
    lignes.append(f"  - {t('banc.memoire')} : {mat.ram_go:.0f} Go")
    for carte in mat.gpus:
        pilote = f", {t('banc.pilote')} {carte.pilote}" if carte.pilote else ""
        lignes.append(f"  - {t('banc.graphique')} : {carte.nom}{pilote}")
    lignes.append(f"  - {t('banc.alimentation')} : {_alimentation()}")
    lignes.append("  - " + t("rbanc.moteur", moteur=moteur_voulu,
                             peripherique=peripherique, repetitions=repetitions,
                             duree=n(43.6 * repetitions, 1)))
    lignes.append("  - " + t("rbanc.repos", med=n(repos["travail_median_ms"], 2),
                             p95=n(repos["travail_p95_ms"], 2), reveil=n(repos["reveil_p95_ms"], 1)))
    if plafond:
        lignes.append("  - " + t("rbanc.plafond"))
    lignes += ["", t("rbanc.section.essais")]
    for r in resultats:
        if r.get("etat") != "ok":
            lignes.append("  - " + t("rbanc.echec", variante=r["variante"], etat=r.get("etat", "?"),
                                     erreur=str(r.get("erreur") or "")[:200]))
            continue
        g = r["gene"]
        lignes.append("  - " + t(
            "rbanc.ligne", variante=r["variante"], facteur=n(r.get("facteur", 0), 3),
            heure=presets.formater_duree(float(r.get("facteur", 0)) * 3600),
            memoire=n(r.get("memoire_go", 0), 1), libre=n(r.get("libre_pct", 0), 0),
            med=n(g["median"], 2), p95=n(g["p95"], 2), reveil=n(g["reveil_p95_ms"], 1),
            wer=n(r.get("wer", 0), 1), fils=r.get("fils_rythme") or r.get("fils") or "-",
            lot=r.get("lot", "-"), priorite=r.get("priorite", "?")))
    if coef:
        lignes += ["", t("rbanc.section.coefficients")]
        for nom, valeur in coef.items():
            lignes.append("  - " + t("rbanc.coefficient", rythme=t(f"rythme.nom.{nom}"), valeur=n(valeur, 2)))
        lignes.append("  - " + (t("rbanc.coefficients_non_ecrits") if plafond else t("rbanc.coefficients_ecrits")))
    lignes += ["", t("banc.duree_totale", duree=presets.formater_duree(duree_totale)), t("rbanc.lecture")]
    return _masquer("\n".join(lignes)) + "\n"


def principal_cli(arguments: list[str]) -> int:
    def valeur(option: str, defaut: str = "") -> str:
        if option in arguments:
            rang = arguments.index(option)
            if rang + 1 < len(arguments):
                return arguments[rang + 1]
        return defaut

    try:
        resultat = executer(
            rythmes=[r for r in valeur("--rythmes").split(",") if r.strip()] or None,
            moteur_voulu=valeur("--moteur"), peripherique=valeur("--peripherique"),
            repetitions=int(valeur("--repetitions", "3") or 3),
            variantes_ov="--variantes-ov" in arguments,
            passif_vitesse="--sans-temoin-passif" not in arguments,
            rappel=lambda message: print("  " + message, flush=True))
    except journal.ErreurLisible as exc:
        print(f"{exc.titre}\n{exc.message}")
        return 1
    print()
    print(resultat["rapport"])
    if resultat["fichier"]:
        print(langues.t("banc.cli.fichier", fichier=resultat["fichier"]))
    return 0
