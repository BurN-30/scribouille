"""
Banc d'essai de vitesse : quelle façon de transcrire va le plus vite ICI ?

Les réglages par défaut viennent de mesures faites sur d'autres machines. Sur un
portable à processeur hybride de 15 W, rien ne garantit qu'ils soient les bons :
le nombre de fils, la taille des lots, le moteur (CTranslate2 ou OpenVINO) et le
périphérique (processeur, puce graphique Intel, NPU) changent la durée du tout
au tout. Le banc transcrit un extrait court livré avec l'application
(`banc/extrait_fr.ogg`, 43,6 s, phrases du jeu FLEURS sous licence CC-BY-4.0)
sous plusieurs réglages, chronomètre chaque essai, compare le texte obtenu à la
référence, puis conseille un réglage. Il n'applique rien de lui-même.

Chaque essai tourne dans un processus séparé (`--banc-essai`) :
  - la mémoire est rendue à la fin de chaque essai, quoi qu'il arrive ;
  - un périphérique qui se bloque (le NPU l'a fait avec large-v3-turbo sur un
    Core Ultra 7 265U, ticket TalkTrack n° 131) est arrêté au bout du délai,
    sans emporter l'application ;
  - l'affinité du processus (cœurs basse consommation écartés) se pose sans
    toucher à la fenêtre.

Le chronomètre ne compte que la transcription : décodage de l'extrait et
chargement du modèle sont mesurés à part. Le premier essai est refait à la fin :
l'écart dit si la machine a chauffé ou changé de régime en cours de route.

Le rapport ne contient ni nom d'utilisateur, ni nom de machine, ni chemin : il
est fait pour être envoyé tel quel. Une dernière passe le vérifie et masque ce
qui aurait pu passer.

Ligne de commande (sans fenêtre) :

    transcriber.pyw --banc [--telecharger] [--npu] [--appliquer]
    Scribouille.exe --banc ...          (version installée, voir le guide)
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import VERSION, NOM_APPLICATION, calibration, chemins, journal, langues, materiel, moteur
from . import presets

MARQUE = "SCRIBOUILLE-BANC|"
DOSSIER_EXTRAIT = chemins.DOSSIER_RESSOURCES / "banc"
EXTRAIT = DOSSIER_EXTRAIT / "extrait_fr.ogg"
REFERENCE = DOSSIER_EXTRAIT / "extrait_fr.txt"
DOSSIER_RAPPORTS = chemins.RACINE / "rapports-banc"

#: Délai accordé à un essai, chargement compris. Une compilation pour le NPU
#: prend jusqu'à deux minutes la première fois ; large-v3 sur un processeur
#: de 15 W, une minute ou deux sur l'extrait.
DELAI_ESSAI_S = 420

#: Écart de justesse toléré, en points de WER, pour qu'un réglage plus rapide
#: soit retenu. L'extrait compte 95 mots : un mot vaut environ 1,05 point.
#: Au-delà de quatre mots d'écart, le réglage le plus rapide est tenu pour
#: moins fiable et écarté du conseil.
TOLERANCE_WER = 4.5


# ---------------------------------------------------------------------------
# Taux d'erreur sur les mots
# ---------------------------------------------------------------------------

def _mots(texte: str) -> list[str]:
    texte = unicodedata.normalize("NFC", texte.lower())
    texte = texte.replace("’", "'").replace("œ", "oe")
    texte = re.sub(r"[^\w' ]+", " ", texte).replace("'", " ")
    return texte.split()


def taux_erreur_mots(reference: str, hypothese: str) -> float:
    """WER en pourcentage, après minuscules et retrait de la ponctuation."""
    ref, hyp = _mots(reference), _mots(hypothese)
    precedent = list(range(len(hyp) + 1))
    for i, mot in enumerate(ref, 1):
        courant = [i]
        for j, autre in enumerate(hyp, 1):
            courant.append(min(precedent[j] + 1, courant[j - 1] + 1,
                               precedent[j - 1] + (mot != autre)))
        precedent = courant
    return round(100.0 * precedent[-1] / max(1, len(ref)), 2)


# ---------------------------------------------------------------------------
# Un essai, dans son propre processus
# ---------------------------------------------------------------------------

@dataclass
class Essai:
    etiquette: str
    moteur: str = "ctranslate2"          # ou « openvino »
    modele: str = presets.MODELE_TURBO
    peripherique: str = "cpu"            # CTranslate2 : cpu ; OpenVINO : CPU, GPU, NPU
    fils: int = 0
    lot: int = 8
    faisceau: int = 5
    affinite: bool = False
    #: Banc des rythmes (`--modes`) : rythme appliqué dans le processus, nombre
    #: de passages de l'extrait mis bout à bout, propriétés d'OpenVINO en plus.
    rythme: str = ""
    repetitions: int = 1
    proprietes: dict = field(default_factory=dict)
    resultat: dict = field(default_factory=dict)

    def parametres(self) -> dict:
        donnees = {
            "etiquette": self.etiquette, "moteur": self.moteur, "modele": self.modele,
            "peripherique": self.peripherique, "fils": self.fils, "lot": self.lot,
            "faisceau": self.faisceau, "affinite": self.affinite,
        }
        if self.rythme:
            donnees.update(rythme=self.rythme, repetitions=self.repetitions,
                           proprietes=self.proprietes)
        return donnees

    @property
    def reussi(self) -> bool:
        return self.resultat.get("etat") == "ok"


def _emettre(donnees: dict) -> None:
    try:
        sys.__stdout__.write(MARQUE + json.dumps(donnees, ensure_ascii=False) + "\n")
        sys.__stdout__.flush()
    except Exception:
        pass


def executer_essai(parametres: dict) -> dict:
    """Corps d'un essai. Tourne dans le processus travailleur."""
    from . import audio, energie

    resultat: dict = {"etiquette": parametres.get("etiquette", ""), "etat": "erreur"}
    try:
        import psutil  # type: ignore

        processus = psutil.Process()
        if os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE"):
            processus.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        processus = None

    mat = materiel.detecter()
    if parametres.get("affinite") and processus is not None:
        logiques = mat.topologie.logiques_principaux
        if logiques:
            try:
                processus.cpu_affinity(logiques)
            except Exception as exc:
                resultat["note"] = f"affinité refusée : {type(exc).__name__}"

    # Banc des rythmes : les bornes du rythme sont posées dans ce processus,
    # comme la file de l'application les pose dans le sien.
    from . import rythme as rythme_module

    nom_rythme = str(parametres.get("rythme") or "")
    bornes = rythme_module.bornes(nom_rythme, mat) if nom_rythme else None
    if bornes is None or bornes.rythme == "vitesse":
        energie.desactiver_bridage()
    if bornes is not None:
        rythme_module.Leviers().appliquer(_plafonner(bornes), avec_affinite=True)
        resultat["priorite"] = _plafonner(bornes).priorite

    modele = parametres.get("modele") or presets.MODELE_TURBO
    moteur_voulu = parametres.get("moteur") or "ctranslate2"
    sur_puce = False
    if moteur_voulu == "openvino":
        from . import moteur_openvino

        depot = presets.depot_openvino(modele)
        if moteur.etat_modele(depot)["etat"] != "complet":
            resultat["etat"] = "modele_absent"
            return resultat
        peripherique_ov = str(parametres.get("peripherique") or "CPU")
        instance = moteur_openvino.MoteurOpenVINO(mat, peripherique_ov)
        sur_puce = peripherique_ov.upper() != "CPU"
        proprietes = dict(parametres.get("proprietes") or {})
        if bornes is not None:
            proprietes = {**(bornes.ov_puce if sur_puce else bornes.ov_processeur), **proprietes}
        instance.proprietes = proprietes
    else:
        if moteur.etat_modele(modele)["etat"] != "complet":
            resultat["etat"] = "modele_absent"
            return resultat
        mat.fils_imposes = int(parametres.get("fils") or 0)
        instance = moteur.MoteurTranscription(mat)
        if bornes is not None:
            instance.fils = bornes.fils
        moteur.limiter_parallelisme(instance.fils_effectifs)

    signal = audio.decoder(EXTRAIT)
    repetitions = max(1, int(parametres.get("repetitions") or 1))
    if repetitions > 1:
        import numpy as np

        signal = np.concatenate([signal] * repetitions)
    duree = signal.size / audio.FREQUENCE

    debut = time.perf_counter()
    instance.charger(modele)
    chargement = time.perf_counter() - debut

    reglages = {
        "beam_size": int(parametres.get("faisceau") or 5),
        "best_of": int(parametres.get("faisceau") or 5),
        "vad": True,
        "lot": int(parametres.get("lot") or 0),
        "faisceau_openvino": int(parametres.get("faisceau") or 1),
    }
    if bornes is not None:
        if bornes.lot_max is not None and reglages["lot"]:
            reglages["lot"] = min(reglages["lot"], bornes.lot_max)
        regulateur = rythme_module.Regulateur(mat, bornes.rythme, False)
        regulateur.sur_puce = sur_puce
        reglages["frein"] = rythme_module.Frein(regulateur)
        fils_ov = (getattr(instance, "proprietes", {}) or {}).get("INFERENCE_NUM_THREADS") if not sur_puce else 0
        resultat.update({"lot": reglages["lot"],
                         "fils_rythme": getattr(instance, "fils_effectifs", 0) or fils_ov or "auto"})
    temps_cpu = sum(processus.cpu_times()[:2]) if processus is not None else 0.0
    debut = time.perf_counter()
    segments, _ = instance.transcrire(signal, duree, "fr", reglages)
    calcul = time.perf_counter() - debut
    if processus is not None:
        temps_cpu = sum(processus.cpu_times()[:2]) - temps_cpu
    instance.liberer()

    texte = " ".join(s.texte for s in segments)
    reference = REFERENCE.read_text(encoding="utf-8")
    if repetitions > 1:
        reference = " ".join([reference] * repetitions)
    pic = 0.0
    if processus is not None:
        pic = getattr(processus.memory_info(), "peak_wset", 0) / 1024 ** 3
    resultat.update({
        "etat": "ok",
        "duree_audio": round(duree, 1),
        "chargement_s": round(chargement, 1),
        "calcul_s": round(calcul, 2),
        "facteur": round(calcul / duree, 3) if duree else 0.0,
        "wer": taux_erreur_mots(reference, texte),
        "fils": mat.fils_calcul if moteur_voulu == "ctranslate2" else 0,
        "processeur_s": round(temps_cpu, 1),
        "memoire_go": round(pic, 2),
        "texte": texte,
    })
    return resultat


def _plafonner(bornes):
    """
    Plafond de priorité du banc (`SCRIBOUILLE_BANC_PRIORITE_BASSE`) : quand
    d'autres calculs tournent sur le poste, aucun essai ne passe au-dessus de
    « inférieure à la normale ». Le rapport le dit : la gêne de la vitesse
    maximale y est alors sous-estimée.
    """
    import dataclasses

    if os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE") and bornes.priorite == "normale":
        return dataclasses.replace(bornes, priorite="inferieure")
    return bornes


def principal_essai(argument: str) -> int:
    """Point d'entrée du processus travailleur : un essai, une ligne de résultat."""
    try:
        parametres = json.loads(argument)
    except (TypeError, ValueError):
        _emettre({"etat": "erreur", "erreur": "paramètres illisibles"})
        return 2
    try:
        _emettre(executer_essai(parametres))
        return 0
    except Exception as exc:
        journal.exception("Essai du banc en échec", exc)
        _emettre({"etiquette": parametres.get("etiquette", ""), "etat": "erreur",
                  "erreur": f"{type(exc).__name__}: {exc}"[:300]})
        return 1


def commande_essai(parametres: dict) -> tuple[list[str], str]:
    """Commande du processus travailleur, et son dossier de travail."""
    charge = json.dumps(parametres, ensure_ascii=False)
    if chemins.EST_GELE:
        dossier = Path(sys.executable).resolve().parent
        console = dossier / "scribouille-verifier.exe"
        exe = console if console.is_file() else Path(sys.executable)
        return [str(exe), "--banc-essai", charge], str(dossier)
    racine = Path(__file__).resolve().parent.parent
    python = racine / ".venv" / "Scripts" / "python.exe"
    interprete = str(python) if python.exists() else sys.executable
    return [interprete, "-m", "app.banc", "--banc-essai", charge], str(racine)


def lancer_essai(essai: Essai, interrompu: Callable[[], bool] | None = None,
                 delai: float = DELAI_ESSAI_S, env_ajout: dict | None = None) -> dict:
    """Lance un essai dans un processus séparé et attend sa ligne de résultat."""
    commande, dossier = commande_essai(essai.parametres())
    debut = time.time()
    env = {**os.environ, **env_ajout} if env_ajout else None
    try:
        processus = subprocess.Popen(
            commande, cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
    except OSError as exc:
        return {"etiquette": essai.etiquette, "etat": "erreur", "erreur": str(exc)}

    import queue
    import threading

    lignes: "queue.Queue[str | None]" = queue.Queue()

    def lire() -> None:
        for ligne in processus.stdout or []:
            lignes.put(ligne)
        lignes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    resultat: dict = {}
    while True:
        if interrompu is not None and interrompu():
            _arreter(processus)
            return {"etiquette": essai.etiquette, "etat": "annule"}
        if time.time() - debut > delai:
            _arreter(processus)
            return {"etiquette": essai.etiquette, "etat": "delai",
                    "erreur": f"plus de {int(delai)} s"}
        try:
            ligne = lignes.get(timeout=0.5)
        except Exception:
            continue
        if ligne is None:
            break
        if ligne.startswith(MARQUE):
            try:
                resultat = json.loads(ligne[len(MARQUE):])
            except ValueError:
                pass
        elif ligne.strip():
            journal.debug("banc : %s", ligne.rstrip()[:300])
    processus.wait()
    if not resultat:
        resultat = {"etiquette": essai.etiquette, "etat": "erreur",
                    "erreur": f"processus terminé sans résultat (code {processus.returncode})"}
    return resultat


def _arreter(processus) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(processus.pid)],
                           capture_output=True, timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            processus.kill()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Le plan d'essais
# ---------------------------------------------------------------------------

def _present(modele: str) -> bool:
    try:
        return moteur.etat_modele(modele)["etat"] == "complet"
    except Exception:
        return False


def modeles_manquants(npu: bool = False) -> list[tuple[str, int]]:
    """Modèles qu'il faudrait télécharger pour un banc complet : (dépôt, octets)."""
    from . import moteur_openvino

    voulus = [presets.MODELE_TURBO, "large-v3"]
    if moteur_openvino.installe() and peripheriques_openvino(npu):
        voulus += [presets.depot_openvino(m) for m in (presets.MODELE_TURBO, "large-v3")]
    return [(m, moteur.poids_attendu_octets(m)) for m in voulus if not _present(m)]


def peripheriques_openvino(npu: bool = False) -> list[str]:
    from . import moteur_openvino

    if not moteur_openvino.installe():
        return []
    vus = moteur_openvino.peripheriques_disponibles()
    ordre = ["GPU", "CPU"] + (["NPU"] if npu else [])
    return [p for p in ordre if p in vus]


def candidats_fils(mat: materiel.Materiel) -> list[tuple[int, bool]]:
    """(fils, affinité) à comparer, du réglage automatique aux variantes."""
    auto = mat.fils_automatiques
    total = mat.coeurs_logiques or auto
    candidats: list[tuple[int, bool]] = [(auto, False)]
    for valeur in (mat.coeurs_physiques, total):
        if valeur and (valeur, False) not in candidats:
            candidats.append((valeur, False))
    topo = mat.topologie
    if topo.hybride and topo.basse_consommation and topo.logiques_principaux:
        candidats.append((auto, True))
    return candidats


def modele_banc() -> str:
    """
    Modèle sur lequel se comparent les réglages : large-v3-turbo s'il est là.

    C'est le plus rapide, le banc tient alors en quelques minutes. À défaut,
    large-v3 sert de modèle de comparaison, et le banc est plus long.
    """
    for modele in (presets.MODELE_TURBO, "large-v3"):
        if _present(modele):
            return modele
    return ""


def _court(modele: str) -> str:
    return "turbo" if modele == presets.MODELE_TURBO else moteur.nom_court(modele)


def plan(mat: materiel.Materiel, npu: bool = False) -> list[Essai]:
    """
    Essais prévus d'entrée, dans l'ordre où ils tournent : les variantes de
    fils de CTranslate2, puis chaque périphérique d'OpenVINO. Les lots et
    large-v3 suivent, avec le meilleur réglage trouvé (`completer_plan`).
    """
    essais: list[Essai] = []
    modele = modele_banc()
    if modele:
        for fils, affinite in candidats_fils(mat):
            etiquette = f"ct2-{_court(modele)}-{fils}f-l8" + ("-aff" if affinite else "")
            essais.append(Essai(etiquette, modele=modele, fils=fils, lot=8, affinite=affinite))
    modele_ov = modele or presets.MODELE_TURBO
    if not _present(presets.depot_openvino(modele_ov)):
        modele_ov = next((m for m in (presets.MODELE_TURBO, "large-v3")
                          if _present(presets.depot_openvino(m))), "")
    if modele_ov:
        for peripherique in peripheriques_openvino(npu):
            essais.append(Essai(f"ov-{_court(modele_ov)}-{peripherique.lower()}",
                                moteur="openvino", modele=modele_ov,
                                peripherique=peripherique, faisceau=1, lot=0))
    return essais


def completer_plan(mat: materiel.Materiel, faits: list[Essai]) -> list[Essai]:
    """Lots de 4 et un à un, avec le meilleur nombre de fils trouvé."""
    suite: list[Essai] = []
    ct2 = [e for e in faits if e.moteur == "ctranslate2" and e.reussi]
    if ct2:
        meilleur = min(ct2, key=lambda e: e.resultat["facteur"])
        for lot in (4, 0):
            suite.append(Essai(f"ct2-{_court(meilleur.modele)}-{meilleur.fils}f-l{lot}"
                               + ("-aff" if meilleur.affinite else ""),
                               modele=meilleur.modele, fils=meilleur.fils, lot=lot,
                               affinite=meilleur.affinite))
    return suite


def essais_qualite(faits: list[Essai]) -> list[Essai]:
    """large-v3 avec le meilleur réglage de chaque moteur."""
    suite: list[Essai] = []
    ct2 = [e for e in faits if e.moteur == "ctranslate2" and e.reussi
           and e.modele == presets.MODELE_TURBO]
    if ct2 and _present("large-v3"):
        m = min(ct2, key=lambda e: e.resultat["facteur"])
        suite.append(Essai(f"ct2-large-v3-{m.fils}f-l{m.lot}", modele="large-v3",
                           fils=m.fils, lot=m.lot, affinite=m.affinite))
    ov = [e for e in faits if e.moteur == "openvino" and e.reussi
          and e.modele == presets.MODELE_TURBO]
    if ov and _present(presets.depot_openvino("large-v3")):
        m = min(ov, key=lambda e: e.resultat["facteur"])
        suite.append(Essai(f"ov-large-v3-{m.peripherique.lower()}", moteur="openvino",
                           modele="large-v3", peripherique=m.peripherique, faisceau=1, lot=0))
    return suite


# ---------------------------------------------------------------------------
# Conseil
# ---------------------------------------------------------------------------

def _plus_rapide_fiable(essais: list[Essai]) -> Essai | None:
    valides = [e for e in essais if e.reussi]
    if not valides:
        return None
    meilleur_wer = min(e.resultat["wer"] for e in valides)
    fiables = [e for e in valides if e.resultat["wer"] <= meilleur_wer + TOLERANCE_WER]
    return min(fiables, key=lambda e: e.resultat["facteur"])


def conseiller(mat: materiel.Materiel, essais: list[Essai]) -> dict:
    """
    Réglage conseillé, à partir des essais réussis.

    Le moteur et le périphérique viennent des essais de large-v3-turbo : le plus
    rapide dont le texte reste aussi juste que le meilleur, à 4,5 points près.
    Les fils et les lots viennent des essais de CTranslate2 ; ils restent dans le
    réglage même quand OpenVINO l'emporte, pour le cas où il faudrait y revenir.
    """
    # Le moteur se choisit sur le modèle de comparaison, celui des premiers
    # essais (turbo en général), où tous les réglages se mesurent à égalité.
    reference = next((e.modele for e in essais if e.reussi), "")
    turbo = [e for e in essais if e.modele == reference and not e.etiquette.endswith("-bis")]
    gagnant = _plus_rapide_fiable(turbo)
    if gagnant is None:
        return {}
    ct2 = [e for e in turbo if e.moteur == "ctranslate2" and e.reussi]
    meilleur_ct2 = min(ct2, key=lambda e: e.resultat["facteur"]) if ct2 else None
    reglage: dict = {"moteur": gagnant.moteur, "source": "banc"}
    if gagnant.moteur == "openvino":
        reglage["peripherique"] = gagnant.peripherique
    if meilleur_ct2 is not None:
        reglage["fils"] = int(meilleur_ct2.resultat.get("fils") or meilleur_ct2.fils)
        reglage["lot"] = int(meilleur_ct2.lot)

    def facteur(modele: str) -> float:
        for e in essais:
            if not e.reussi or e.modele != modele or e.etiquette.endswith("-bis"):
                continue
            if e.moteur != gagnant.moteur:
                continue
            if e.moteur == "openvino" and e.peripherique != gagnant.peripherique:
                continue
            if e.moteur == "ctranslate2" and meilleur_ct2 is not None and (
                    e.fils != meilleur_ct2.fils or e.lot != meilleur_ct2.lot
                    or e.affinite != meilleur_ct2.affinite):
                continue
            return float(e.resultat["facteur"])
        return 0.0

    reglage["facteurs"] = {"rapide": facteur(presets.MODELE_TURBO),
                           "qualite": facteur("large-v3")}
    reglage["duree_audio"] = float(gagnant.resultat.get("duree_audio") or 0)
    if meilleur_ct2 is not None and meilleur_ct2.affinite:
        reglage["note_affinite"] = True
    return reglage


def enregistrer_mesures(mat: materiel.Materiel, reglage: dict) -> None:
    """
    Verse les facteurs du banc dans les mesures de durée du poste.

    L'extrait ne dure que 43 s : la mesure entre avec ce poids, et les vraies
    transcriptions, plus longues, prendront vite le dessus dans le lissage.
    """
    cle = ("openvino-" + str(reglage.get("peripherique", "cpu")).lower()
           if reglage.get("moteur") == "openvino" else mat.peripherique)
    lot = 0 if reglage.get("moteur") == "openvino" else int(reglage.get("lot") or 0)
    faisceau = 1 if reglage.get("moteur") == "openvino" else 5
    duree = float(reglage.get("duree_audio") or 0)
    for cle_preset, modele in (("rapide", presets.MODELE_TURBO), ("qualite", "large-v3")):
        facteur = float((reglage.get("facteurs") or {}).get(cle_preset) or 0)
        if facteur > 0 and duree > 0:
            calibration.enregistrer(modele, cle, faisceau, duree, facteur * duree, mat, lot=lot,
                                    duree_minimale=20.0)


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def _alimentation() -> str:
    try:
        import psutil  # type: ignore

        batterie = psutil.sensors_battery()
    except Exception:
        batterie = None
    if batterie is None:
        source = langues.t("banc.secteur_sans_batterie")
    elif batterie.power_plugged:
        source = langues.t("banc.secteur", pct=int(batterie.percent))
    else:
        source = langues.t("banc.batterie", pct=int(batterie.percent))
    mode = ""
    if sys.platform == "win32":
        try:
            sortie = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True,
                                    text=True, errors="replace", timeout=10,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            trouve = re.search(r"\(([^()]+)\)\s*$", (sortie.stdout or "").strip())
            mode = trouve.group(1).strip() if trouve else ""
        except Exception:
            mode = ""
    return source + (f", {langues.t('banc.mode_alimentation', mode=mode)}" if mode else "")


def _masquer(texte: str) -> str:
    """Dernière garde : rien d'identifiant ne sort dans le rapport."""
    sensibles = set()
    for variable in ("USERNAME", "USER", "COMPUTERNAME", "USERDOMAIN", "LOGONSERVER"):
        valeur = (os.environ.get(variable) or "").strip("\\ ")
        if len(valeur) >= 3:
            sensibles.add(valeur)
    try:
        sensibles.add(platform.node())
    except Exception:
        pass
    for chemin in (Path.home(), chemins.RACINE, chemins.DOSSIER_MODELES, chemins.DOSSIER_RESSOURCES):
        sensibles.add(str(chemin))
    for valeur in sorted((v for v in sensibles if v and len(v) >= 3), key=len, reverse=True):
        texte = re.sub(re.escape(valeur), "[masqué]", texte, flags=re.IGNORECASE)
    return texte


def libelle(essai: Essai) -> str:
    """Le réglage d'un essai, en clair."""
    if essai.moteur == "openvino":
        return langues.t("banc.libelle_ov", peripherique=essai.peripherique,
                         modele=moteur.nom_court(essai.modele))
    return langues.t(
        "banc.libelle_ct2", modele=moteur.nom_court(essai.modele), fils=essai.fils,
        lots=(langues.t("banc.lots", n=essai.lot) if essai.lot else langues.t("banc.un_a_un"))
        + (", " + langues.t("banc.affinite") if essai.affinite else ""))


def _ligne_essai(essai: Essai) -> str:
    r = essai.resultat
    reglage = libelle(essai)
    if r.get("etat") != "ok":
        motif = langues.t(f"banc.etat.{r.get('etat', 'erreur')}")
        detail = f" ({r['erreur']})" if r.get("erreur") else ""
        return f"  - {reglage} : {motif}{detail}"
    return "  - " + langues.t(
        "banc.ligne", reglage=reglage, calcul=langues.nombre(r.get("calcul_s", 0), 1),
        facteur=langues.nombre(r.get("facteur", 0), 2), wer=langues.nombre(r.get("wer", 0), 1),
        chargement=langues.nombre(r.get("chargement_s", 0), 1),
        memoire=langues.nombre(r.get("memoire_go", 0), 1))


def rediger(mat: materiel.Materiel, essais: list[Essai], reglage: dict,
            duree_totale: float) -> str:
    """Rapport texte, sans rien d'identifiant."""
    from . import moteur_openvino

    t = langues.t
    lignes = [
        t("banc.titre", nom=NOM_APPLICATION, version=VERSION,
          date=datetime.now().strftime("%Y-%m-%d")),
        "",
        t("banc.section.materiel"),
        f"  - {t('banc.processeur')} : {mat.cpu_nom or '?'}",
    ]
    topo = mat.topologie
    if topo.hybride:
        lignes.append("  - " + t("banc.topologie", p=topo.performants, e=topo.efficaces,
                                 lp=topo.basse_consommation, fils=mat.coeurs_logiques))
    else:
        lignes.append("  - " + t("banc.coeurs", coeurs=mat.coeurs_physiques,
                                 fils=mat.coeurs_logiques))
    lignes.append("  - " + t("banc.fils_auto", n=mat.fils_automatiques))
    lignes.append(f"  - {t('banc.memoire')} : {mat.ram_go:.0f} Go")
    for carte in mat.gpus:
        pilote = f", {t('banc.pilote')} {carte.pilote}" if carte.pilote else ""
        lignes.append(f"  - {t('banc.graphique')} : {carte.nom}{pilote}")
    for circuit in mat.npus:
        lignes.append(f"  - NPU : {circuit.nom}")
    lignes.append(f"  - {t('banc.alimentation')} : {_alimentation()}")
    lignes.append(f"  - {t('banc.systeme')} : {platform.system()} {platform.release()} "
                  f"({platform.version()})")
    try:
        import ctranslate2  # type: ignore

        version_ct2 = ctranslate2.__version__
    except Exception:
        version_ct2 = "?"
    ov = moteur_openvino.version() if moteur_openvino.installe() else ""
    lignes.append(f"  - CTranslate2 {version_ct2}, OpenVINO "
                  + (f"{ov} ({', '.join(moteur_openvino.peripheriques_disponibles()) or '-'})"
                     if ov else t("banc.non_installe")))
    lignes += ["", t("banc.section.essais", duree=langues.nombre(
        float(next((e.resultat.get("duree_audio") for e in essais if e.reussi), 43.6)), 1))]
    lignes += [_ligne_essai(e) for e in essais]

    lignes += ["", t("banc.section.conseil")]
    if not reglage:
        lignes.append("  - " + t("banc.aucun_conseil"))
    else:
        if reglage.get("moteur") == "openvino":
            lignes.append("  - " + t("banc.conseil_openvino", peripherique=reglage.get("peripherique")))
        else:
            lignes.append("  - " + t("banc.conseil_ct2", fils=reglage.get("fils", "?"),
                                     lot=reglage.get("lot", "?")))
        for cle in ("rapide", "qualite"):
            facteur = float((reglage.get("facteurs") or {}).get(cle) or 0)
            if facteur:
                lignes.append("  - " + t("banc.pour_une_heure", preset=presets.nom_preset(cle),
                                         duree=presets.formater_duree(facteur * 3600),
                                         facteur=langues.nombre(facteur, 2)))
    bis = next((e for e in essais if e.etiquette.endswith("-bis") and e.reussi), None)
    premier = next((e for e in essais if e.reussi and not e.etiquette.endswith("-bis")), None)
    if bis and premier and premier.resultat.get("facteur"):
        ecart = 100.0 * (bis.resultat["facteur"] / premier.resultat["facteur"] - 1)
        lignes.append("  - " + t("banc.derive", ecart=langues.nombre(ecart, 0)))
    lignes += ["", t("banc.duree_totale", duree=presets.formater_duree(duree_totale)),
               t("banc.remarque")]
    return _masquer("\n".join(lignes)) + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def executer(telecharger: bool = False, npu: bool = False,
             rappel: Callable[[dict], None] | None = None,
             interrompu: Callable[[], bool] | None = None) -> dict:
    """
    Mène le banc complet et renvoie {rapport, reglage, fichier, essais}.

    `rappel` reçoit des étapes {"message", "pct"} pour l'interface.
    """
    def dire(message: str, pct: int) -> None:
        journal.info("Banc : %s", message)
        if rappel:
            rappel({"message": message, "pct": max(0, min(100, pct))})

    depart = time.time()
    mat = materiel.detecter()
    if not EXTRAIT.is_file() or not REFERENCE.is_file():
        raise journal.ErreurLisible(langues.t("banc.extrait_absent.titre"),
                                    langues.t("banc.extrait_absent.msg"))

    if telecharger:
        for depot, octets in modeles_manquants(npu):
            if interrompu and interrompu():
                break
            dire(langues.t("banc.etape.telechargement", modele=moteur.nom_court(depot),
                           taille=langues.octets(octets)), 2)
            try:
                moteur.assurer_modele_telecharge(depot, None, None, annoncer=False)
            except Exception as exc:
                dire(langues.t("banc.etape.telechargement_echoue", modele=moteur.nom_court(depot),
                               detail=getattr(exc, "message", str(exc))[:200]), 2)

    essais = plan(mat, npu)
    total_prevu = len(essais) + 4
    faits: list[Essai] = []

    def jouer(liste: list[Essai]) -> None:
        for essai in liste:
            if interrompu and interrompu():
                return
            dire(langues.t("banc.etape.essai", numero=len(faits) + 1, total=total_prevu,
                           reglage=libelle(essai)),
                 int(5 + 90 * len(faits) / max(1, total_prevu)))
            essai.resultat = lancer_essai(essai, interrompu)
            faits.append(essai)

    jouer(essais)
    jouer(completer_plan(mat, faits))
    jouer(essais_qualite(faits))
    premier = next((e for e in faits if e.reussi), None)
    if premier is not None and not (interrompu and interrompu()):
        bis = Essai(premier.etiquette + "-bis", premier.moteur, premier.modele,
                    premier.peripherique, premier.fils, premier.lot, premier.faisceau,
                    premier.affinite)
        jouer([bis])

    reglage = conseiller(mat, faits)
    rapport = rediger(mat, faits, reglage, time.time() - depart)
    fichier = ""
    try:
        DOSSIER_RAPPORTS.mkdir(parents=True, exist_ok=True)
        cible = DOSSIER_RAPPORTS / f"rapport-banc-{datetime.now():%Y%m%d-%H%M}.txt"
        cible.write_text(rapport, encoding="utf-8")
        (DOSSIER_RAPPORTS / "dernier-banc.json").write_text(json.dumps(
            {"reglage": reglage, "rapport": cible.name,
             "essais": [{**e.parametres(), **{k: v for k, v in e.resultat.items() if k != "texte"}}
                        for e in faits]},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fichier = str(cible)
    except OSError as exc:
        journal.attention("Rapport du banc non écrit : %s", exc)
    dire(langues.t("banc.etape.fini"), 100)
    return {"rapport": rapport, "reglage": reglage, "fichier": fichier,
            "annule": bool(interrompu and interrompu()),
            "essais": [e.parametres() | {"resultat": e.resultat} for e in faits]}


def dernier_conseil() -> dict:
    """Réglage conseillé par le dernier banc mené sur ce poste, s'il existe."""
    try:
        donnees = json.loads((DOSSIER_RAPPORTS / "dernier-banc.json").read_text(encoding="utf-8"))
        return donnees.get("reglage") or {}
    except (OSError, ValueError):
        return {}


def dernier_rapport() -> str:
    """Texte du rapport du dernier banc mené sur ce poste, vide s'il n'y en a pas."""
    try:
        donnees = json.loads((DOSSIER_RAPPORTS / "dernier-banc.json").read_text(encoding="utf-8"))
        nom = Path(str(donnees.get("rapport") or "")).name
        return (DOSSIER_RAPPORTS / nom).read_text(encoding="utf-8") if nom else ""
    except (OSError, ValueError):
        return ""


def principal_cli(arguments: list[str]) -> int:
    """`--banc` : le banc complet en ligne de commande, rapport sur la sortie."""
    if "--banc-essai" in arguments:
        rang = arguments.index("--banc-essai")
        return principal_essai(arguments[rang + 1] if rang + 1 < len(arguments) else "")
    if "--modes" in arguments:
        from . import banc_rythmes

        return banc_rythmes.principal_cli(arguments)
    from . import config as config_module, reglage_machine

    config = config_module.charger()
    resultat = executer(telecharger="--telecharger" in arguments, npu="--npu" in arguments,
                        rappel=lambda etape: print("  " + etape["message"], flush=True))
    print()
    print(resultat["rapport"])
    if resultat["fichier"]:
        print(langues.t("banc.cli.fichier", fichier=resultat["fichier"]))
    if "--appliquer" in arguments and resultat["reglage"]:
        mat = materiel.detecter()
        reglage_machine.enregistrer(config, mat, resultat["reglage"])
        enregistrer_mesures(mat, resultat["reglage"])
        config_module.sauver(config)
        print(langues.t("banc.cli.applique"))
    elif resultat["reglage"]:
        print(langues.t("banc.cli.appliquer"))
    return 0


def options_reconnues(arguments: list[str]) -> bool:
    return "--banc" in arguments or "--banc-essai" in arguments


if __name__ == "__main__":
    sys.exit(principal_cli(sys.argv[1:]))
