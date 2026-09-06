"""
Harnais de mesure : combien coûte la sauvegarde progressive ?

La sauvegarde progressive écrit chaque segment dès qu'il sort du décodeur, pour
qu'une coupure ne fasse pas perdre le calcul déjà fait. La question posée avant
de l'intégrer était chiffrée : si le surcoût dépasse 10 % du temps de
transcription, ou s'il consomme beaucoup de disque ou de mémoire, on n'intègre
pas.

Ce script y répond en passant le MÊME audio dans la VRAIE file de traitement,
plusieurs fois, alternativement avec et sans l'option, et compare les temps
mesurés. L'alternance A/B/A/B est là pour que la montée en température du
processeur ou une tâche de fond ne se retrouve pas comptée d'un seul côté.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python outils\\mesure_sauvegarde_progressive.py ^
        --audio chemin\\vers\\un.wav --passes 3 --modele tiny

Le fichier audio peut être n'importe quel enregistrement court. Aucun réseau
n'est utilisé si le modèle demandé est déjà téléchargé.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import chemins, config as config_module, materiel, reprise, traitement  # noqa: E402


# Chronométrage à la source : on mesure le temps réellement passé DANS la
# sauvegarde pendant une vraie transcription. C'est le seul chiffre insensible
# au bruit d'une machine de bureau, où deux passes identiques varient déjà de
# plusieurs pour cent selon la fréquence du processeur.
_CHRONO = {"total": 0.0, "appels": 0}
_AJOUTER_ORIGINE = reprise.Session.ajouter


def _ajouter_chronometre(self, segment, ecoule):
    depart = time.perf_counter()
    try:
        return _AJOUTER_ORIGINE(self, segment, ecoule)
    finally:
        _CHRONO["total"] += time.perf_counter() - depart
        _CHRONO["appels"] += 1


reprise.Session.ajouter = _ajouter_chronometre


def _config(dossier_sortie: Path, modele: str, sauvegarde: bool) -> dict:
    config = config_module.charger()
    config.update({
        "dossier_sortie": str(dossier_sortie),
        "diarisation": False,
        "utiliser_glossaire": False,
        "appliquer_corrections": False,
        "mode_avance": True,
        "modele_avance": modele,
        "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
        "sauvegarde_progressive": sauvegarde,
        "compagnon_confiance": True,
    })
    return config


def _taille_reprises() -> int:
    return sum(f.stat().st_size for f in reprise.dossier().glob("*") if f.is_file())


def une_passe(audio: Path, modele: str, sauvegarde: bool, mat) -> dict:
    """Transcrit une fois, renvoie le temps mesuré et la place occupée."""
    _CHRONO["total"], _CHRONO["appels"] = 0.0, 0
    with tempfile.TemporaryDirectory(prefix="scribouille-mesure-") as temporaire:
        dossier = Path(temporaire)
        file = traitement.FileTraitement(mat)
        file.ajouter([str(audio)])

        fini = threading.Event()
        maximum_reprise = {"octets": 0, "fichiers": 0}
        arret_veille = threading.Event()

        def veiller() -> None:
            # La place occupée par la reprise est un maximum instantané : les
            # fichiers sont effacés à la fin, il faut les regarder pendant.
            while not arret_veille.is_set():
                fichiers = [f for f in reprise.dossier().glob("*") if f.is_file()]
                octets = sum(f.stat().st_size for f in fichiers)
                if octets > maximum_reprise["octets"]:
                    maximum_reprise["octets"] = octets
                    maximum_reprise["fichiers"] = len(fichiers)
                arret_veille.wait(0.2)

        memoire = {"pic": 0}

        def veiller_memoire() -> None:
            try:
                import psutil

                processus = psutil.Process()
            except Exception:
                return
            while not arret_veille.is_set():
                try:
                    memoire["pic"] = max(memoire["pic"], processus.memory_info().rss)
                except Exception:
                    return
                arret_veille.wait(0.2)

        threading.Thread(target=veiller_memoire, daemon=True).start()
        veille = threading.Thread(target=veiller, daemon=True)
        veille.start()

        rappels = traitement.Rappels(file_terminee=lambda d: fini.set())
        depart = time.perf_counter()
        file.demarrer(_config(dossier, modele, sauvegarde), rappels)
        fini.wait(timeout=3600)
        duree = time.perf_counter() - depart
        arret_veille.set()
        veille.join(timeout=2)

        produits = sorted(dossier.glob("*"))
        return {
            "duree": duree,
            "reprise_octets": maximum_reprise["octets"],
            "reprise_fichiers": maximum_reprise["fichiers"],
            "chrono": _CHRONO["total"],
            "segments": _CHRONO["appels"],
            "memoire": memoire["pic"],
            "sorties": [(f.name, f.stat().st_size) for f in produits],
        }


def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--audio", required=True)
    analyseur.add_argument("--passes", type=int, default=3)
    analyseur.add_argument("--modele", default="tiny")
    arguments = analyseur.parse_args()

    audio = Path(arguments.audio)
    if not audio.is_file():
        print(f"Fichier introuvable : {audio}")
        return 1

    chemins.assurer_dossiers()
    mat = materiel.detecter()
    print(f"Matériel  : {mat.resume()}")
    print(f"Audio     : {audio.name}")
    print(f"Modèle    : {arguments.modele}, {arguments.passes} passes par mode")
    print(f"Reprises  : {reprise.dossier()}")
    print("")

    resultats: dict[bool, list[dict]] = {False: [], True: []}
    numero = 0
    for tour in range(arguments.passes):
        for sauvegarde in ((True, False) if tour % 2 else (False, True)):
            numero += 1
            mesure = une_passe(audio, arguments.modele, sauvegarde, mat)
            resultats[sauvegarde].append(mesure)
            print(
                f"  passe {numero:>2}  sauvegarde={'oui' if sauvegarde else 'non'}  "
                f"{mesure['duree']:8.2f} s  "
                f"reprise {mesure['reprise_octets'] / 1024:7.1f} Ko "
                f"({mesure['reprise_fichiers']} fichiers)"
            )

    print("")
    sans = [m["duree"] for m in resultats[False]]
    avec = [m["duree"] for m in resultats[True]]
    moyenne_sans, moyenne_avec = statistics.mean(sans), statistics.mean(avec)
    mediane_sans, mediane_avec = statistics.median(sans), statistics.median(avec)
    surcout = (moyenne_avec - moyenne_sans) / moyenne_sans * 100 if moyenne_sans else 0.0
    surcout_median = (mediane_avec - mediane_sans) / mediane_sans * 100 if mediane_sans else 0.0
    octets = max((m["reprise_octets"] for m in resultats[True]), default=0)

    chrono = sum(m["chrono"] for m in resultats[True])
    segments = sum(m["segments"] for m in resultats[True])
    part_chrono = chrono / sum(avec) * 100 if sum(avec) else 0.0
    memoire_sans = max((m["memoire"] for m in resultats[False]), default=0)
    memoire_avec = max((m["memoire"] for m in resultats[True]), default=0)

    print(f"Sans sauvegarde : moyenne {moyenne_sans:.2f} s, médiane {mediane_sans:.2f} s, "
          f"min {min(sans):.2f} s, max {max(sans):.2f} s")
    print(f"Avec sauvegarde : moyenne {moyenne_avec:.2f} s, médiane {mediane_avec:.2f} s, "
          f"min {min(avec):.2f} s, max {max(avec):.2f} s")
    print(f"Écart mesuré    : {surcout:+.2f} % en moyenne, {surcout_median:+.2f} % en médiane, "
          f"{(min(avec) - min(sans)) / min(sans) * 100:+.2f} % sur les meilleures passes")
    print(f"Dispersion      : {(max(sans) - min(sans)) / min(sans) * 100:.1f} % entre la meilleure "
          "et la pire passe SANS l'option, bruit de la machine")
    print("")
    print(f"Coût direct     : {chrono * 1000:.1f} ms passés dans la sauvegarde pour "
          f"{segments} segments écrits, soit {chrono / max(1, segments) * 1000:.2f} ms par segment")
    print(f"                  {part_chrono:.3f} % du temps de transcription")
    print(f"Disque          : {octets / 1024:.1f} Ko de fichiers de reprise au maximum, "
          "effacés à la fin de la transcription")
    print(f"Mémoire         : pic {memoire_sans / 1024 ** 2:.0f} Mo sans, "
          f"{memoire_avec / 1024 ** 2:.0f} Mo avec")
    print(f"Verdict         : {'sous' if part_chrono < 10 else 'AU-DESSUS de'} la limite de 10 % "
          "(le coût direct fait foi, l'écart de bout en bout est noyé dans le bruit)")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
