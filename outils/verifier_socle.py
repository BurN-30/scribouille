"""
Vérification du socle allégé de la version 3.0, sans fenêtre ni modèle.

Décodage par PyAV (une seule FFmpeg), démarrage sans détection bloquante,
modèle gardé d'un fichier à l'autre, garde-fou des répétitions, dossier de
données à notre nom. Tout se passe dans un dossier temporaire : la
configuration et les données de l'utilisateur ne sont jamais touchées.

    .venv\\Scripts\\python outils\\verifier_socle.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
# Aucun processus lancé par les vérifications n'ouvre de console visible.
SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import langues  # noqa: E402

langues.definir("fr")

_reussites = 0
_echecs: list[str] = []


def verifier(condition: bool, libelle: str, detail: str = "") -> None:
    global _reussites
    if condition:
        _reussites += 1
        print(f"  OK    {libelle}")
    else:
        _echecs.append(libelle)
        print(f"  ECHEC {libelle}" + (f" : {detail}" if detail else ""))


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * len(texte))


# ---------------------------------------------------------------------------
# 1. Décodage : une seule FFmpeg, celle de PyAV
# ---------------------------------------------------------------------------

def essai_decodage(base: Path) -> None:
    titre("1. Décodage par PyAV")
    import wave

    import numpy as np

    from app import audio

    # WAV tronqué : l'en-tête annonce 78 s, 26 s restent. La durée annoncée
    # est celle de l'en-tête : la troncature est vue (« audio lu en partie »).
    import struct

    tronque = base / "tronque.wav"
    donnees_pcm = (np.sin(np.arange(16000 * 26) / 10.0) * 8000).astype("<i2").tobytes()
    annonce = 16000 * 2 * 78
    entete = (b"RIFF" + struct.pack("<I", 36 + annonce) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16)
              + b"data" + struct.pack("<I", annonce))
    tronque.write_bytes(entete + donnees_pcm)
    annoncee, lue = audio.duree(tronque), audio.decoder(tronque).size / audio.FREQUENCE
    verifier(abs(annoncee - 78) < 0.5 and abs(lue - 26) < 0.5 and lue < 0.9 * annoncee and annoncee > 60,
             "WAV tronqué : 78 s annoncées par l'en-tête, 26 s lues, l'écart sera dit", f"{annoncee:.1f} / {lue:.1f}")
    from app.journal import ErreurLisible

    extrait = RACINE / "banc" / "extrait_fr.ogg"
    signal = audio.decoder(extrait)
    verifier(signal.dtype == np.float32 and signal.ndim == 1 and signal.size == 697280,
             "extrait du banc : mono 16 kHz flottant, longueur de la ligne de commande FFmpeg d'avant",
             f"{signal.dtype} {signal.shape}")
    verifier(float(np.max(np.abs(signal))) <= 1.0, "signal borné à 1")
    morceau = audio.decoder(extrait, debut=7.25, duree=12.5)
    verifier(morceau.size == 200000, "extrait demandé (début, durée) : longueur exacte", str(morceau.size))
    decalage = int(7.25 * audio.FREQUENCE)
    verifier(float(np.max(np.abs(morceau[1000:-1000] - signal[decalage + 1000:decalage + 199000]))) < 1e-3,
             "extrait demandé : mêmes échantillons que le fichier entier au même endroit")
    salle = audio.decoder(extrait, filtres_salle=True)
    verifier(salle.size == signal.size and not np.array_equal(salle, signal), "filtres de salle appliqués")
    verifier(abs(audio.duree(extrait) - 43.58) < 0.05, "durée lue dans l'en-tête", str(audio.duree(extrait)))

    # WAV stéréo 44,1 kHz fabriqué ici : mélange et rééchantillonnage.
    stereo = base / "stereo.wav"
    t = np.arange(44100 * 3) / 44100
    gauche = (0.4 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(stereo), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(np.column_stack([gauche, gauche]).tobytes())
    decode = audio.decoder(stereo)
    # Mélange de FFmpeg par défaut : chaque voie à -3 dB, 0,4 x 2 x 0,707.
    verifier(decode.size == 48000 and abs(float(np.max(np.abs(decode))) - 0.566) < 0.01,
             "WAV stéréo 44,1 kHz : 3 s à 16 kHz, mélange de FFmpeg", f"{decode.size} {np.max(np.abs(decode)):.3f}")
    verifier(audio.reechantillonner(np.zeros(44100, dtype=np.float32), 44100).size == 16000,
             "rééchantillonnage d'un signal en mémoire (corpus)")

    vide = base / "vide.m4a"
    vide.write_bytes(b"pas un fichier audio")
    try:
        audio.decoder(vide)
        verifier(False, "fichier illisible : erreur lisible")
    except ErreurLisible:
        verifier(True, "fichier illisible : erreur lisible")
    try:
        audio.decoder(base / "absent.mp3")
        verifier(False, "fichier absent : erreur lisible")
    except ErreurLisible:
        verifier(True, "fichier absent : erreur lisible")
    verifier(audio.ffmpeg_present() and audio.decodeur_present(), "décodeur présent")


# ---------------------------------------------------------------------------
# 2. Démarrage : rien de lourd avant la fenêtre, matériel gardé sur disque
# ---------------------------------------------------------------------------

#: Modules qui ne doivent pas être chargés tant qu'aucune file ne tourne.
LOURDS = ("numpy", "ctranslate2", "faster_whisper", "av", "tokenizers", "huggingface_hub",
          "onnxruntime", "openvino", "openvino_genai", "torch")

_SONDE_IMPORTS = """
import json, sys
sys.path.insert(0, sys.argv[1])
from app import adaptation, audio, banc, campagne, diarisation, lecture, materiel  # noqa
from app import moteur, moteur_openvino, presets, reprise, traitement, vocabulaire  # noqa
moteur.identifiant_depot("large-v3"); moteur.identifiant_depot("Systran/faster-whisper-large-v3")
campagne.dossier_publique(); campagne.dernier_verdict()
print(json.dumps(sorted(m for m in {lourds} if m in sys.modules)))
"""


def essai_demarrage(base: Path) -> None:
    titre("2. Démarrage sans détection bloquante ni import lourd")
    import json
    import subprocess

    from app import chemins, materiel, moteur, moteur_openvino

    sortie = subprocess.run([sys.executable, "-c", _SONDE_IMPORTS.replace("{lourds}", repr(LOURDS)), str(RACINE)],
                            capture_output=True, text=True, timeout=120, creationflags=SANS_FENETRE)
    charges = json.loads((sortie.stdout or "[]").strip().splitlines()[-1] if sortie.stdout else "[]")
    verifier(sortie.returncode == 0 and charges == [],
             "modules de la fenêtre importés sans numpy, CTranslate2, PyAV ni OpenVINO",
             f"{charges} {sortie.stderr[-300:]}")
    verifier(moteur.identifiant_depot("turbo") == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
             and moteur.identifiant_depot("deepdml/x") == "deepdml/x", "noms de dépôts sans faster-whisper")

    ancienne_racine = chemins.RACINE
    ancien = (moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, materiel._CACHE)
    try:
        chemins.RACINE = base / "donnees"
        mat, provisoire = materiel.detecter_au_demarrage()
        verifier(provisoire and not mat.gpus and mat.coeurs_logiques > 0 and mat.ram_go > 0,
                 "premier lancement : processeur et mémoire lus, cartes en attente (provisoire)")
        if moteur_openvino.installe():
            deja_charge = "openvino" in sys.modules
            verifier(not moteur_openvino.peripheriques_confirmes()
                     and moteur_openvino.peripheriques_disponibles() == list(moteur_openvino.PERIPHERIQUES)
                     and moteur_openvino.version() == "" and ("openvino" in sys.modules) == deja_charge,
                     "premier lancement avec OpenVINO : périphériques supposés, OpenVINO non chargé")
        lent = {"gpus": [{"nom": "Intel(R) Graphics", "vendeur": "intel", "memoire_mo": 0, "accelere": False,
                          "pilote": "32.0.101.8801", "note_cle": "gpu.note.intel"}],
                "npus": [{"nom": "Intel(R) AI Boost", "genre": "npu", "note_cle": "npu.note.intel"}],
                "a_nvidia": False, "cuda_disponible": False,
                "openvino": {"installe": moteur_openvino.installe(), "version": "2099.1",
                             "peripheriques": ["CPU", "GPU", "XYZ"]}}
        materiel.ecrire_cache(lent)
        mat, provisoire = materiel.detecter_au_demarrage()
        verifier(not provisoire and mat.a_graphique_intel() and mat.npus and mat.npus[0].nom == "Intel(R) AI Boost",
                 "lancement suivant : cartes et NPU repris de materiel.json")
        verifier(moteur_openvino.peripheriques_disponibles() == ["CPU", "GPU"]
                 and moteur_openvino.version() == "2099.1",
                 "périphériques et version d'OpenVINO repris sans charger OpenVINO",
                 str(moteur_openvino.peripheriques_disponibles()))
        verifier(materiel.signature(lent) == materiel.signature(materiel.lire_cache())
                 and materiel.signature({**lent, "a_nvidia": True}) != materiel.signature(lent),
                 "signature : un changement de matériel se voit")
        (base / "donnees" / materiel.NOM_CACHE_DISQUE).write_text("{abîmé", encoding="utf-8")
        verifier(materiel.lire_cache() is None and materiel.detecter_au_demarrage()[1],
                 "cache illisible : ignoré, matériel provisoire")
        commande, _dossier = materiel._commande_detection()
        verifier(commande[-1] == "--detecter-materiel", "détection lente : processus de fond dédié", str(commande))
    finally:
        chemins.RACINE = ancienne_racine
        moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, materiel._CACHE = ancien

    noms = materiel._noms_peripheriques_presents() if sys.platform == "win32" else ["x"]
    verifier(len(noms) > 5 and all(isinstance(n, str) for n in noms),
             "SetupAPI : périphériques présents lus sans PowerShell", str(len(noms)))
    verifier(materiel._MOTIF_NPU.search("Intel(R) AI Boost") and not materiel._MOTIF_NPU.search("USB Input Device"),
             "motif des NPU : « Input » n'est pas un NPU")


# ---------------------------------------------------------------------------
# 3. File : le modèle gardé d'un fichier à l'autre
# ---------------------------------------------------------------------------

class _MoteurCompte:
    """Moteur sans modèle qui compte les vrais chargements (même règle que le vrai)."""

    tokeniseur = None
    fils = 0
    proprietes: dict = {}

    def __init__(self, echouer_sur: int = 0):
        self.charge = ""
        self.chargements = 0
        self.liberations = 0
        self.appels = 0
        self.echouer_sur = echouer_sur

    def charger(self, modele: str, signaler) -> None:
        if self.charge == modele:
            return
        self.chargements += 1
        self.charge = modele

    def liberer(self) -> None:
        if self.charge:
            self.liberations += 1
        self.charge = ""

    def transcrire(self, signal, duree, langue, reglages, amorce="", progression=None,
                   interrompu=None, decalage=0.0, sur_segment=None, origine=None):
        from app.moteur import Segment

        self.appels += 1
        if self.appels == self.echouer_sur:
            raise RuntimeError("panne simulée du moteur")
        segments = [Segment(0.0, 2.0, "Bonjour à tous."), Segment(2.5, 4.0, "On commence.")]
        for s in segments:
            if sur_segment:
                sur_segment(s)
        return segments, {"duree": duree, "langue": langue, "peripherique": "cpu", "type_calcul": "int8"}


def _file_de_trois(base: Path, nom: str, moteur_compte: _MoteurCompte, memoire_go: float) -> dict:
    import copy
    import threading

    import numpy as np

    from app import audio as audio_module, config as config_module, materiel, traitement

    dossier = base / nom
    dossier.mkdir()
    file = traitement.FileTraitement(materiel.detecter_au_demarrage()[0])
    for rang in range(3):
        (dossier / f"reunion-{rang}.wav").write_bytes(b"\0" * 64)
    file.ajouter([str(dossier / f"reunion-{rang}.wav") for rang in range(3)])
    config = copy.deepcopy(config_module.DEFAUTS)
    config.update({"dossier_sortie": str(dossier / "sorties"), "sauvegarde_progressive": False,
                   "utiliser_glossaire": False, "appliquer_corrections": False, "diarisation": False})
    fini, bilan = threading.Event(), {}
    rappels = traitement.Rappels(etat=lambda *a: None, progression=lambda *a: None, termine=lambda *a: None,
                                 journal_ui=lambda *a: None, file_terminee=lambda d: (bilan.update(d), fini.set()))
    anciens = (traitement.fabriquer_moteur, audio_module.decoder, traitement.memoire_libre_go)
    traitement.fabriquer_moteur = lambda *_: moteur_compte
    audio_module.decoder = lambda *_a, **_k: np.zeros(5 * audio_module.FREQUENCE, dtype=np.float32)
    traitement.memoire_libre_go = lambda: memoire_go
    try:
        file.demarrer(config, rappels)
        fini.wait(120)
    finally:
        traitement.fabriquer_moteur, audio_module.decoder, traitement.memoire_libre_go = anciens
    return bilan


def essai_modele_garde(base: Path) -> None:
    titre("3. File : le modèle gardé d'un fichier à l'autre")
    from app import diarisation, traitement

    m = _MoteurCompte()
    bilan = _file_de_trois(base, "garde", m, memoire_go=16.0)
    verifier(bilan.get("reussis") == 3 and m.chargements == 1 and m.liberations == 1,
             "trois fichiers, même réglage : un seul chargement, libéré à la fin de la file",
             f"{bilan} chargements={m.chargements} libérations={m.liberations}")
    m = _MoteurCompte()
    _file_de_trois(base, "memoire", m, memoire_go=0.8)
    verifier(m.chargements == 3, "mémoire libre basse : rendu entre deux fichiers", str(m.chargements))
    m = _MoteurCompte(echouer_sur=2)
    bilan = _file_de_trois(base, "panne", m, memoire_go=16.0)
    verifier(bilan.get("reussis") == 2 and bilan.get("echecs") == 1 and m.chargements == 2,
             "après un échec, le fichier suivant repart d'un moteur propre", f"{bilan} {m.chargements}")
    ancien = diarisation.effective
    try:
        diarisation.effective = lambda demandee: True
        garder, raison = traitement.garder_le_modele({"diarisation": True}, False)
        verifier(not garder and "séparation" in raison, "séparation des voix : le modèle cède sa mémoire")
    finally:
        diarisation.effective = ancien


# ---------------------------------------------------------------------------
# 4. Réglage proposé : les phrases suivent les durées du poste
# ---------------------------------------------------------------------------

def essai_reglage_propose() -> None:
    titre("4. Réglage proposé : jamais une vitesse que les durées du poste contredisent")
    from app import adaptation, materiel, presets

    P = adaptation.Profil
    mat = materiel.Materiel(cpu_nom="Processeur de bureau", coeurs_physiques=8, coeurs_logiques=16, ram_go=32.0)
    present = lambda depot: "complet"  # noqa: E731
    vrai = presets.estimer_annonce

    def annonces(ov: float, habituel: float):
        def estimer(duree, cle_preset, m, rythme_choisi="vitesse", *a, **k):
            return ov if m.cle_calcul.startswith("openvino") else habituel
        return estimer

    try:
        presets.estimer_annonce = annonces(ov=540.0, habituel=1200.0)
        p = adaptation.proposer(mat, P(logiques=16, ram_go=32, openvino_installe=True), None, None, present)
        verifier(p["regle"] == "processeur_openvino" and "20 min" in p["phrase"] and "pas annoncé" not in p["phrase"],
                 "moteur Intel annoncé plus rapide ici : la phrase donne la durée du moteur habituel", p["phrase"])
        presets.estimer_annonce = annonces(ov=1151.0, habituel=820.0)
        p = adaptation.proposer(mat, P(logiques=16, ram_go=32, openvino_installe=True), None, None, present)
        verifier("sans gain de vitesse" in p["phrase"] and "deux fois" not in p["phrase"],
                 "moteur habituel mesuré plus rapide ici : la phrase ne prétend pas le contraire", p["phrase"])
        muette = P(logiques=14, ram_go=32, puce_intel=True, openvino_installe=True, openvino_puce=False)
        p = adaptation.proposer(mat, muette, None, None, present)
        verifier(p["regle"] == "puce_muette" and "sans gain de vitesse" in p["phrase"],
                 "puce muette, moteur habituel plus rapide ici : dit tel quel", p["phrase"])
    finally:
        presets.estimer_annonce = vrai
    p = adaptation.proposer(mat, P(logiques=16, ram_go=32), None, None, present)
    verifier(p["action"] == "installer_openvino" and p["moteur"] == "ctranslate2"
             and any("2 points" in n for n in p["notes"]),
             "processeur sans moteur Intel : son installation est proposée (un clic, jamais d'office)")
    p = adaptation.proposer(mat, P(logiques=16, ram_go=32, cuda=True), None, None, present)
    verifier(p["action"] == "" and p["moteur"] == "ctranslate2", "carte NVIDIA : rien à installer")
    verifier(presets.PRESET_DEFAUT == "qualite",
             "installation neuve sans moteur Intel : « Qualité maximale » reste le défaut")


# ---------------------------------------------------------------------------
# 5. Garde-fou des répétitions
# ---------------------------------------------------------------------------

def essai_repetitions() -> None:
    titre("5. Garde-fou des répétitions : boucles de mots, reprise, autre moteur, coupe")
    from types import SimpleNamespace

    import numpy as np

    from app import materiel, moteur, moteur_openvino as mo, repetitions
    from app.moteur import Segment

    naturels = ["oui oui oui oui", "non non non non non non", "c'est ça, c'est ça, c'est ça, c'est ça",
                "un, deux, trois, quatre, cinq, six, sept, huit, neuf, dix, onze, douze, treize, quatorze",
                "Merci. Merci. Merci. Merci. Merci. Merci.", "on y va, on y va, on y va",
                "Très très très bien, vraiment très très bien."]
    verifier(not any(repetitions.boucle_repetee(t) for t in naturels),
             "parole normalement répétitive : rien de signalé",
             str([t for t in naturels if repetitions.boucle_repetee(t)]))
    # Le cas de la réunion réelle : une fenêtre de 30 s ordinaire, avec au
    # milieu trois mots répétés huit fois. Le taux de compression reste sous 2,4.
    debut = ("Bon, pour la suite du projet, il faudrait que chacun regarde les retours du client avant jeudi, "
             "parce que la livraison de la deuxième version dépend surtout des tests sur les postes du service "
             "comptable, et que personne n'a encore validé la procédure de sauvegarde. ")
    fin = (" Ensuite nous reprendrons le planning de décembre avec la direction, puis le budget des licences, "
           "et enfin la formation des nouveaux arrivants prévue au printemps.")
    boucle = debut + "on va voir " * 8 + fin
    trouve = repetitions.boucle_repetee(boucle)
    verifier(trouve and (trouve["n"], trouve["fois"]) == (3, 8) and mo._taux_compression(boucle) < mo.SEUIL_COMPRESSION,
             "boucle de trois mots répétés huit fois, sous le seuil de compression : repérée par les mots",
             f"{trouve} {mo._taux_compression(boucle):.2f}")
    coupe, nombre = repetitions.couper_boucles(boucle)
    verifier(nombre == 1 and coupe == debut + "on va voir " + fin,
             "coupe : la suite gardée une fois, le reste du texte intact", coupe)

    class Tube:
        """Pipeline d'OpenVINO simulé : rend les textes donnés, dans l'ordre."""

        def __init__(self, textes):
            self.textes, self.configs = list(textes), []

        def get_generation_config(self):
            return SimpleNamespace()

        def generate(self, morceau, config, streamer=None):
            self.configs.append(dict(vars(config)))
            texte = self.textes.pop(0) if len(self.textes) > 1 else self.textes[0]
            return SimpleNamespace(texts=[texte], words=[], languages=["<|fr|>"], perf_metrics=None,
                                   chunks=[SimpleNamespace(start_ts=0.0, end_ts=2.0, text=texte)])

    decouper, etat_modele, transcription = mo.decouper, moteur.etat_modele, moteur.MoteurTranscription
    mo.decouper = lambda signal: [[{"start": 0, "end": 32000}]]
    # OpenVINO est une extension : absent (service de vérification de GitHub),
    # le moteur simulé n'en demande que l'état du flux, prêté ici.
    import importlib.util

    simule = importlib.util.find_spec("openvino_genai") is None
    if simule:
        sys.modules["openvino_genai"] = SimpleNamespace(
            __version__="simulé", StreamingStatus=SimpleNamespace(RUNNING=0, CANCEL=1))
    signal = np.zeros(32000, dtype=np.float32)
    mat = materiel.detecter_au_demarrage()[0]

    def sur(peripherique, tube, modele="turbo"):
        instance = mo.MoteurOpenVINO(mat, peripherique)
        instance._pipeline, instance._mots, instance._nom_modele = tube, False, modele
        return instance

    propre = "Bonjour à tous, on commence la réunion."
    try:
        tube = Tube([boucle, propre])
        segments, details = sur("GPU", tube).transcrire(signal, 2.0, "fr", {"faisceau_openvino": 1})
        verifier(details["boucles_mots"] == 1 and details["reprises"] == 1 and tube.configs[1].get("do_sample")
                 and segments[0].texte == propre,
                 "puce graphique : la boucle de mots est refaite par échantillonnage, la version propre gardée")
        tube = Tube([boucle, propre])
        segments, details = sur("CPU", tube).transcrire(signal, 2.0, "fr", {"faisceau_openvino": 5})
        verifier(tube.configs[1].get("do_sample") and details["reprises"] == 1 and segments[0].texte == propre,
                 "déjà en faisceau de 5 : la reprise passe directement à l'échantillonnage")

        class AutreMoteur:
            charges: list[str] = []

            def __init__(self, _mat):
                pass

            def charger(self, depot, _signaler):
                AutreMoteur.charges.append(depot)

            def transcrire(self, morceau, duree, langue, reglages, amorce=""):
                return [Segment(0.5, 1.5, "Texte repris par l'autre moteur.")], {}

            def liberer(self):
                pass

        moteur.MoteurTranscription = AutreMoteur
        moteur.etat_modele = lambda depot: {"etat": "complet"}
        segments, details = sur("GPU", Tube([boucle]), "OpenVINO/whisper-large-v3-turbo-int8-ov").transcrire(
            signal, 2.0, "fr", {"faisceau_openvino": 1})
        verifier(details["fenetres_autre_moteur"] == 1 and AutreMoteur.charges == [mo.presets.MODELE_TURBO]
                 and [s.texte for s in segments] == ["Texte repris par l'autre moteur."] and segments[0].debut == 0.5,
                 "boucle tenace : la fenêtre est refaite par CTranslate2, même modèle déjà sur le disque",
                 str(details))
        moteur.etat_modele = lambda depot: {"etat": "absent"}
        segments, details = sur("GPU", Tube([boucle]), "OpenVINO/whisper-large-v3-turbo-int8-ov").transcrire(
            signal, 2.0, "fr", {"faisceau_openvino": 1})
        verifier(details["fenetres_autre_moteur"] == 0 and details["boucles_coupees"] == 1
                 and segments[0].texte == (debut + "on va voir " + fin).strip(),
                 "autre moteur absent du disque : jamais téléchargé, la boucle est coupée et comptée")
    finally:
        mo.decouper, moteur.etat_modele, moteur.MoteurTranscription = decouper, etat_modele, transcription
        if simule:
            sys.modules.pop("openvino_genai", None)


# ---------------------------------------------------------------------------
# 6. Dossier de données : de « WhiScribe » à « Scribouille »
# ---------------------------------------------------------------------------

def essai_migration(base: Path) -> None:
    titre("6. Dossier de données : WhiScribe repris dans Scribouille, rien de perdu")
    import json
    import os

    from app import migration

    racine = base / "localappdata"
    ancien, nouveau, programme = racine / "WhiScribe", racine / "Scribouille", base / "programme"
    for dossier in (ancien / "modeles" / "models--Systran--faster-whisper-large-v3" / "blobs",
                    ancien / "logs", ancien / "extensions-openvino" / "openvino", ancien / "models", programme):
        dossier.mkdir(parents=True, exist_ok=True)
    poids = ancien / "modeles" / "models--Systran--faster-whisper-large-v3" / "blobs" / "model.bin"
    poids.write_bytes(b"\1" * 4096)
    (ancien / "config.json").write_text('{"preset": "qualite"}', encoding="utf-8")
    (ancien / "vocabulaire.toml").write_text('format = "scribouille-vocabulaire"\n', encoding="utf-8")
    (ancien / "corrections-format1-sauvegarde.txt").write_text("a => b\n", encoding="utf-8")
    (ancien / "logs" / "2026-11-01.log").write_text("journal", encoding="utf-8")
    (ancien / "dossier-modeles.txt").write_text(str(ancien / "modeles") + "\n", encoding="utf-8")
    (programme / "emplacement-modeles.txt").write_text(str(ancien / "modeles") + "\n", encoding="utf-8")
    # Ce qui n'est pas à nous : le « models » du projet homonyme, un fichier inconnu.
    (ancien / "models" / "ggml-large-v3-turbo.bin").write_bytes(b"\2" * 1024)
    (ancien / "reglages-tiers.ini").write_text("x=1", encoding="utf-8")
    inode = os.stat(poids).st_ino

    # Une entrée verrouillée (fichier ouvert ailleurs) : la migration s'arrête
    # là pour elle, et reprend au lancement suivant.
    verrou = open(ancien / "logs" / "2026-11-01.log", "rb")  # noqa: SIM115
    try:
        premier = migration.migrer(ancien, nouveau, programme)
    finally:
        verrou.close()
    reprise = migration.migrer(ancien, nouveau, programme)
    verifier(sys.platform != "win32" or (premier["etat"] == "en_cours" and premier["restes"]),
             "entrée verrouillée : migration laissée en cours, rien de perdu", str(premier.get("restes")))
    verifier(reprise["etat"] == "terminee" and (nouveau / "logs" / "2026-11-01.log").is_file(),
             "lancement suivant : la migration reprend et se termine", str(reprise.get("restes")))
    deplace = nouveau / "modeles" / "models--Systran--faster-whisper-large-v3" / "blobs" / "model.bin"
    verifier(deplace.is_file() and os.stat(deplace).st_ino == inode,
             "modèles déplacés par renommage, sans copie (même fichier sur le disque) : rien à retélécharger")
    verifier(all((nouveau / n).is_file() for n in ("config.json", "vocabulaire.toml",
                                                    "corrections-format1-sauvegarde.txt"))
             and (nouveau / "extensions-openvino" / "openvino").is_dir(),
             "réglages, vocabulaire, sauvegardes et moteur Intel repris")
    verifier((ancien / "models" / "ggml-large-v3-turbo.bin").is_file() and (ancien / "reglages-tiers.ini").is_file()
             and not (nouveau / "models").exists() and sorted(os.listdir(ancien)) == ["models", "reglages-tiers.ini"],
             "ce qui n'est pas à Scribouille reste dans l'ancien dossier, intact")
    verifier((nouveau / "dossier-modeles.txt").read_text(encoding="utf-8").strip() == str(nouveau / "modeles")
             and (programme / "emplacement-modeles.txt").read_text(encoding="utf-8").strip() == str(nouveau / "modeles"),
             "emplacements des modèles notés dans l'ancien dossier : réécrits vers le nouveau")
    journal = json.loads((nouveau / migration.NOM_JOURNAL).read_text(encoding="utf-8"))
    verifier(journal["etat"] == "terminee" and "modeles" in journal["deplaces"] and len(journal["reecrits"]) == 2,
             "journal de la migration tenu")
    verifier(migration.migrer(ancien, nouveau, programme)["etat"] == "rien", "relancée : rien à refaire")

    # Doublon : une entrée déjà présente des deux côtés n'écrase rien.
    (ancien / "calibration.json").write_text("ancien", encoding="utf-8")
    (nouveau / "calibration.json").write_text("nouveau", encoding="utf-8")
    migration.migrer(ancien, nouveau, programme)
    verifier((nouveau / "calibration.json").read_text(encoding="utf-8") == "nouveau"
             and (nouveau / migration.NOM_CONFLITS / "calibration.json").read_text(encoding="utf-8") == "ancien",
             "doublon : le nouveau gardé, l'ancien rangé à part, aucun des deux perdu")

    # Retour arrière, pour une ancienne version.
    bilan = migration.revenir(ancien, nouveau, programme)
    verifier(not bilan["restes"] and (ancien / "config.json").is_file() and (ancien / "modeles").is_dir()
             and (ancien / "dossier-modeles.txt").read_text(encoding="utf-8").strip() == str(ancien / "modeles")
             and (programme / "emplacement-modeles.txt").read_text(encoding="utf-8").strip() == str(ancien / "modeles")
             and (ancien / "models" / "ggml-large-v3-turbo.bin").is_file(),
             "retour arrière : tout revient dans WhiScribe, emplacements des modèles d'origine", str(bilan))
    verifier(migration.est_a_nous("vocabulaire-propositions-20261112-1000.toml", False)
             and not migration.est_a_nous("models", True) and not migration.est_a_nous("settings.json", False),
             "inventaire : seuls les noms de Scribouille sont reconnus")
    verifier(migration.est_a_nous("historique-relecture", True) and migration.est_a_nous("relecture-positions.json", False)
             and migration.est_a_nous("webview", True),
             "relecture (historique, positions) et profil d'affichage reconnus et migrés")


def essai_instances(base: Path) -> None:
    """Deux Scribouille en même temps : un fichier n'est transcrit que par un seul."""
    import os
    import subprocess

    from app import chemins, instance

    titre("Plusieurs instances : verrou d'un fichier en cours")
    racine = chemins.RACINE
    chemins.RACINE = base / "instances"
    try:
        source = base / "reunion.wav"
        source.write_bytes(b"x")
        verifier(instance.prendre_fichier(source) == 0, "le premier processus prend le fichier")
        verifier(instance.prendre_fichier(source) == 0, "le même processus peut le reprendre (reprise après plantage)")
        verrou = instance._fichier_verrou(source)
        autre = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=SANS_FENETRE)
        try:
            verrou.write_text(str(autre.pid), encoding="ascii")
            verifier(instance.prendre_fichier(source) == autre.pid,
                     "un autre processus vivant le tient : refusé, son PID est rendu")
        finally:
            autre.kill()
            autre.wait()
        verifier(instance.prendre_fichier(source) == 0
                 and verrou.read_text(encoding="ascii").split()[0] == str(os.getpid()),
                 "le verrou d'un processus disparu est repris")
        instance.rendre_fichier(source)
        verifier(not verrou.exists(), "le verrou est rendu en fin de fichier")
        from app import reprise

        session = reprise.Session("essai-sortie", active=True)
        session.ouvrir(source, "tiny", 60.0, sortie=str(base / "ailleurs"))
        session.fermer()
        verifier(reprise.lire_etat("essai-sortie").get("sortie") == str(base / "ailleurs"),
                 "une reprise garde le dossier de sortie demandé (scribouille reprendre y écrit)")
        session.effacer()
        from app import config as config_module

        from app import langues as langues_module

        fichier_config = chemins.FICHIER_CONFIG
        chemins.FICHIER_CONFIG = base / "config-langue.json"   # jamais celui de l'utilisateur
        try:
            config_module.sauver({**config_module.DEFAUTS, "langue_interface": "fr"})
            langues_module.definir("en")
            config_module.charger(definir_langue=False)
            garde = langues_module.courante()
            config_module.charger(definir_langue=True)
        finally:
            chemins.FICHIER_CONFIG = fichier_config
        passerelle = (RACINE / "transcriber.pyw").read_text(encoding="utf-8")
        verifier(garde == "en" and langues_module.courante() == "fr"
                 and "disque = config_module.charger(definir_langue=False)" in passerelle,
                 "changer de langue : la fenêtre qui relit le disque ne remet pas l'ancienne langue",
                 f"{garde} {langues_module.courante()}")

        # Langue choisie contre langue du système (échec du service de
        # vérification, poste en anglais) : lire une configuration sans langue
        # enregistrée ne doit pas imposer celle du système au processus.
        variable = os.environ.get("SCRIBOUILLE_LANGUE_SYSTEME")
        chemins.FICHIER_CONFIG = base / "config-sans-langue.json"
        vus = []
        try:
            for systeme, choisie in (("en", "fr"), ("fr", "en")):
                os.environ["SCRIBOUILLE_LANGUE_SYSTEME"] = systeme
                chemins.FICHIER_CONFIG.unlink(missing_ok=True)
                langues_module.definir(choisie)
                lue = config_module.charger()
                vus.append((langues_module.detecter_systeme(), langues_module.courante(), lue["langue_interface"]))
                chemins.FICHIER_CONFIG.unlink(missing_ok=True)
                config_module.charger(definir_langue=True)
                vus.append(langues_module.courante())
        finally:
            chemins.FICHIER_CONFIG = fichier_config
            if variable is None:
                os.environ.pop("SCRIBOUILLE_LANGUE_SYSTEME", None)
            else:
                os.environ["SCRIBOUILLE_LANGUE_SYSTEME"] = variable
            langues_module.definir("fr")
        verifier(vus == [("en", "fr", "en"), "en", ("fr", "en", "fr"), "fr"],
                 "langue choisie : lire la configuration ne la remplace pas par celle du système ; "
                 "le premier lancement, lui, suit le système", str(vus))
        from app import processus as processus_module

        tampon = bytearray(64 * 1024 * 1024)  # 64 Mo occupés pour de bon
        releve = processus_module.Sonde().releve() or {}
        verifier(0 < releve.get("propre_octets", 0) <= releve.get("prive_octets", 0)
                 and releve["propre_octets"] > 60 * 1024 * 1024,
                 "mémoire montrée : celle que le processus occupe seul (USS), pas la mémoire engagée",
                 str({k: releve.get(k) for k in ("propre_octets", "prive_octets", "memoire_octets")}))
        del tampon
        from app import cli, langues

        langues.definir("fr")
        verifier(cli._noms("Alice,Bob") == {"Locuteur 1": "Alice", "Locuteur 2": "Bob"}
                 and cli._noms("Locuteur 3=Chloé") == {"Locuteur 3": "Chloé"},
                 "--noms : « Alice,Bob » ou « Locuteur 3=Chloé »")
    finally:
        chemins.RACINE = racine


def _empreinte_arbre(dossier: Path) -> dict:
    import hashlib

    return {p.relative_to(dossier).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(dossier.rglob("*")) if p.is_file()}


def essai_version_2x(base: Path) -> None:
    """Revue du 15/11 (S1) : une 2.x installée n'est jamais privée de ses données, où qu'elle soit."""
    import json
    import os

    from app import chemins, inventaire

    titre("WhiScribe 2.x installée : détectée par le registre, jamais déplacée ni effacée")
    local = base / "registre-local"
    ancien, nouveau = local / "WhiScribe", local / "Scribouille"
    reels = {k: os.environ.get(k) for k in ("LOCALAPPDATA", "SCRIBOUILLE_ESSAI_REGISTRE", "SCRIBOUILLE_DONNEES")}
    gele, migration_reelle = chemins.EST_GELE, dict(chemins.MIGRATION)
    racine, imposees = chemins.RACINE, chemins.DONNEES_IMPOSEES

    def preparer(avec_nouveau: bool) -> None:
        import shutil

        shutil.rmtree(local, ignore_errors=True)
        (ancien / "modeles" / "models--Systran--faster-whisper-large-v3").mkdir(parents=True)
        (ancien / "modeles" / "models--Systran--faster-whisper-large-v3" / "poids").write_bytes(b"p" * 64)
        (ancien / "config.json").write_text('{"preset": "rapide"}', encoding="utf-8")
        (ancien / "dossier-modeles.txt").write_text(str(ancien / "modeles") + "\n", encoding="utf-8")
        (ancien / "logs").mkdir()
        (ancien / "logs" / "2026-11-12_1.log").write_text("2.x\n", encoding="utf-8")
        if avec_nouveau:
            nouveau.mkdir(parents=True)
            (nouveau / "config.json").write_text("{}", encoding="utf-8")

    def registre(valeur) -> None:
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = valeur if isinstance(valeur, str) else json.dumps(valeur)

    try:
        os.environ["LOCALAPPDATA"] = str(local)
        os.environ.pop("SCRIBOUILLE_DONNEES", None)
        chemins.EST_GELE = True
        ailleurs = {"ruche": "HKCU", "version": "2.3.3", "dossier": str(base / "D" / "Outils" / "WhiScribe")}
        registre([ailleurs])
        etat = chemins.etat_version_2x()
        verifier(etat["presente"] and etat["sure"] and etat["par"] == "registre"
                 and chemins.ancienne_version_installee() == Path(ailleurs["dossier"]) / "WhiScribe.exe",
                 "2.3.3 installée ailleurs que dans Programs\\WhiScribe : vue par sa clé de désinstallation", str(etat))
        registre([{"ruche": "HKCU", "version": "3.0.0", "dossier": str(local / "Programs" / "WhiScribe")}])
        verifier(not chemins.etat_version_2x()["presente"],
                 "clé de la 3.x installée par-dessus (même identifiant) : plus de 2.x")
        registre("erreur")
        etat = chemins.etat_version_2x()
        verifier(etat["presente"] and not etat["sure"], "registre illisible : tenue pour présente", str(etat))
        registre([{"ruche": "HKLM", "version": "", "dossier": ""}])
        verifier(chemins.etat_version_2x()["presente"], "clé sans version lisible : tenue pour présente")

        for cas, valeur, avec_nouveau, attendu_racine, attendu_etat in (
                ("2.x ailleurs, Scribouille déjà en service (3.0 antérieure)", [ailleurs], True, nouveau, "bloquee"),
                ("2.x ailleurs, jamais ouverte par la 3.x", [ailleurs], False, ancien, "partage"),
                ("registre illisible", "erreur", True, nouveau, "bloquee")):
            preparer(avec_nouveau)
            registre(valeur)
            avant = _empreinte_arbre(ancien)
            chemins.MIGRATION.clear()
            obtenue = chemins._dossier_donnees()
            verifier(obtenue == attendu_racine and chemins.MIGRATION.get("etat") == attendu_etat
                     and _empreinte_arbre(ancien) == avant and not (nouveau / "migration-whiscribe.json").exists(),
                     f"{cas} : rien de WhiScribe déplacé ni réécrit (dossier {attendu_etat})",
                     f"{obtenue} {chemins.MIGRATION} {sorted(set(avant) ^ set(_empreinte_arbre(ancien)))}")
        # Effacement complet : WhiScribe hors de tout poste quand la 2.x est là.
        preparer(True)
        registre([ailleurs])
        chemins.RACINE, chemins.DONNEES_IMPOSEES = nouveau, False
        reglages = {"dossier_sortie": str(base / "sorties-2x")}   # jamais les vraies Transcriptions
        postes = {p.cle for p in inventaire.postes(reglages, mesurer=False)[0]}
        apercu = inventaire.apercu_effacement(True, reglages, avec_programme=False)
        verifier("ancien_dossier" not in postes and str(ancien) in apercu["partages"]
                 and not any(str(c).lower().startswith(str(ancien).lower())
                             for p in apercu["postes"] for c in p["chemins"]),
                 "effacer --complet : WhiScribe montré à part, jamais dans ce qui s'efface", str(sorted(postes)))
        registre([])
        preparer(False)
        chemins.MIGRATION.clear()
        chemins.RACINE = chemins._dossier_donnees()
        verifier(chemins.RACINE == nouveau and (nouveau / "config.json").is_file() and not (ancien / "config.json").exists(),
                 "sans 2.x : la reprise de l'ancien dossier se fait comme avant", str(chemins.MIGRATION))
        # La simulation n'est lue que sur un LOCALAPPDATA d'essai.
        os.environ["LOCALAPPDATA"] = chemins._localappdata_reel() or str(local)
        verifier(not chemins._essai_registre_permis() or not chemins._localappdata_reel(),
                 "vrai LOCALAPPDATA : la simulation du registre est ignorée (vrai registre lu)")
    finally:
        chemins.EST_GELE, chemins.RACINE, chemins.DONNEES_IMPOSEES = gele, racine, imposees
        chemins.MIGRATION.clear()
        chemins.MIGRATION.update(migration_reelle)
        for cle, valeur in reels.items():
            if valeur is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = valeur


def essai_reprise_tolerante(base: Path) -> None:
    """Revue du 15/11 (S2 à S5, M4) : une reprise ne se perd ni à la lecture, ni à la suite, ni à la purge."""
    import json
    from datetime import datetime, timedelta

    from app import chemins, lecture, reprise
    from app.moteur import Segment

    titre("Reprises : lecture ligne par ligne, suite propre, purge prudente, à l'abri de la 2.3.3")
    racine = chemins.RACINE
    chemins.RACINE = base / "reprises-tolerantes"
    try:
        source = base / "reunion-tolerante.ogg"
        source.write_bytes(b"audio")

        def ligne(k: int) -> bytes:
            return json.dumps({"d": k, "f": k + 1, "t": f"Segment {k}", "m": []}).encode("utf-8") + b"\n"

        s = reprise.Session("tolerante01", active=True)
        s.ouvrir(source, "tiny", 60.0, nouvelle=True)
        s.fermer()
        fichier = chemins.RACINE / "reprises" / "tolerante01.jsonl"
        # Une ligne au milieu avec un octet UTF-8 invalide, une dernière ligne coupée net.
        fichier.write_bytes(ligne(0) + ligne(1) + b'{"d": 2, "f": 3, "t": "caf\xe9"}\n' + ligne(3)
                            + b'{"d": 4, "f": 5, "t": "Segm')
        lus = [x.texte for x in reprise.lire_segments("tolerante01")]
        verifier(lus == ["Segment 0", "Segment 1", "Segment 3"],
                 "octet invalide et dernière ligne tronquée : seules ces lignes-là sont écartées", str(lus))
        s = reprise.Session("tolerante01", active=True)
        s.ouvrir(source, "tiny", 60.0, position=4.0, nb_segments=3)
        s.ajouter(Segment(debut=4.0, fin=5.0, texte="Segment 4", mots=[]), 1.0)
        s.fermer()
        lus = [x.texte for x in reprise.lire_segments("tolerante01")]
        verifier(lus == ["Segment 0", "Segment 1", "Segment 3", "Segment 4"] and fichier.read_bytes().endswith(b"\n")
                 and b"Segm\n" not in fichier.read_bytes() and b"Segm{" not in fichier.read_bytes(),
                 "à la suite : la ligne coupée est retirée, le segment suivant n'y est pas collé", str(lus))
        # Dernière ligne entière mais sans fin de ligne : gardée et complétée.
        fichier.write_bytes(ligne(0) + ligne(1).rstrip(b"\n"))
        s = reprise.Session("tolerante01", active=True)
        s.ouvrir(source, "tiny", 60.0, position=2.0, nb_segments=2)
        s.ajouter(Segment(debut=2.0, fin=3.0, texte="Segment 2", mots=[]), 1.0)
        s.fermer()
        verifier([x.texte for x in reprise.lire_segments("tolerante01")] == ["Segment 0", "Segment 1", "Segment 2"],
                 "dernière ligne entière sans fin de ligne : gardée, la suite va à la ligne")
        # Lecture refusée par le disque : erreur dite, rien de tronqué.
        illisible = chemins.RACINE / "reprises" / "tolerante02.jsonl"
        illisible.mkdir()
        try:
            reprise.lire_segments("tolerante02")
            leve = False
        except reprise.RepriseIllisible:
            leve = True
        verifier(leve and illisible.is_dir() and reprise.a_garder("tolerante02"),
                 "segments illisibles pour l'instant : erreur dite, reprise gardée, rien d'écrit")
        illisible.rmdir()
        # À l'abri de la 2.3.3 : elle ne liste et ne purge que « *.json ».
        verifier(not list((chemins.RACINE / "reprises").glob("*.json"))
                 and (chemins.RACINE / "reprises" / "tolerante01.etat").is_file(),
                 "l'état d'une reprise de la 3.x ne finit plus par .json (invisible pour la 2.3.3)")
        reprise.oublier("tolerante01")
        ancienne =chemins.RACINE / "reprises" / "tolerante03.json"
        ancienne.write_text(json.dumps({"auteur": reprise.AUTEUR, "source": str(source), "nom": source.name,
                                        "modele": "tiny", "position": 1.0, "nb_segments": 1}), encoding="utf-8")
        (chemins.RACINE / "reprises" / "tolerante03.jsonl").write_bytes(ligne(0))
        cles = {r["cle"] for r in reprise.lister()}
        s = reprise.Session("tolerante03", active=True)
        s.ouvrir(source, "tiny", 60.0, position=1.0, nb_segments=1)
        s.fermer()
        verifier("tolerante03" in cles and not ancienne.exists()
                 and (chemins.RACINE / "reprises" / "tolerante03.etat").is_file()
                 and len(reprise.lire_segments("tolerante03")) == 1,
                 "reprise de la 3.x d'avant (état en .json) : lue, puis renommée à la reprise, segments gardés")
        reprise.oublier("tolerante03")
        # Redéposer ou relancer : la reprise est gardée (a_garder) et retrouvée par fichier.
        cle = reprise.cle(source, "tiny")
        s = reprise.Session(cle, active=True)
        s.ouvrir(source, "tiny", 60.0, nouvelle=True)
        s.ajouter(Segment(debut=0.0, fin=1.0, texte="Gardé", mots=[]), 1.0)
        s.fermer()
        trouvee = reprise.reprise_du_fichier(source)
        verifier(reprise.a_garder(cle) and trouvee and trouvee["cle"] == cle,
                 "un fichier redéposé retrouve sa reprise (au moins un segment gardé)")
        reprise.oublier(cle)

        # Purge du démarrage : jamais sur une absence passagère.
        def etat_vers(identifiant: str, chemin_source: str) -> None:
            (chemins.RACINE / "reprises" / f"{identifiant}.etat").write_text(json.dumps(
                {"auteur": reprise.AUTEUR, "source": chemin_source, "nom": Path(chemin_source).name, "modele": "tiny",
                 "position": 1.0, "nb_segments": 1}), encoding="utf-8")
            (chemins.RACINE / "reprises" / f"{identifiant}.jsonl").write_bytes(ligne(0))

        etat_vers("injoignable01", str(base / "lecteur-debranche" / "sous-dossier" / "r.ogg"))
        etat_vers("absente00001", str(base / "r-disparue.ogg"))
        (chemins.RACINE / "reprises" / "illisible0001.etat").write_text("", encoding="utf-8")
        (chemins.RACINE / "reprises" / "illisible0001.jsonl").write_bytes(ligne(0))
        reprise.purger()
        rep = chemins.RACINE / "reprises"
        verifier((rep / "injoignable01.jsonl").is_file() and (rep / "absente00001.jsonl").is_file()
                 and (rep / "absente00001.absente").is_file() and (rep / "illisible0001.jsonl").is_file(),
                 "purge : source injoignable gardée, source absente datée et gardée, état vide aux segments valides gardé")
        raisons = {o["cle"]: o for o in reprise.orphelines()}
        verifier(raisons["injoignable01"]["raison"] == "source_injoignable"
                 and not raisons["injoignable01"]["effacable"],
                 "source injoignable : même « etat --nettoyer » la garde", str(raisons.get("injoignable01")))
        reprise.nettoyer(reprise.orphelines())
        verifier((rep / "injoignable01.jsonl").is_file() and not (rep / "absente00001.jsonl").exists(),
                 "etat --nettoyer : la source absente (dossier joignable) s'efface sur demande, l'injoignable reste")
        etat_vers("absente00002", str(base / "r-disparue-2.ogg"))
        reprise.purger()
        vieux = (datetime.now() - timedelta(days=reprise.DELAI_ABSENCE_JOURS + 1)).isoformat(timespec="seconds")
        (rep / "absente00002.absente").write_text(vieux, encoding="ascii")
        reprise.purger()
        verifier(not (rep / "absente00002.jsonl").exists() and not (rep / "absente00002.absente").exists(),
                 f"source absente depuis plus de {reprise.DELAI_ABSENCE_JOURS} jours : effacée par la purge")
        # État qui ne se lit pas pour l'instant (verrou d'un antivirus, simulé
        # par un verrou d'octets) : ni listé, ni effacé.
        if sys.platform == "win32":
            import msvcrt

            etat_vers("verrouille01", str(base / "r-disparue-3.ogg"))
            (rep / "verrouille01.etat").write_text("{ abîmé", encoding="utf-8")
            with open(rep / "verrouille01.etat", "rb") as flux:
                msvcrt.locking(flux.fileno(), msvcrt.LK_NBLCK, 8)
                try:
                    statut = reprise.lire_etat_detail("verrouille01")[1]
                    reprise.purger()
                    vues = {o["cle"] for o in reprise.orphelines()}
                finally:
                    flux.seek(0)
                    msvcrt.locking(flux.fileno(), msvcrt.LK_UNLCK, 8)
            verifier(statut == "acces" and (rep / "verrouille01.jsonl").is_file() and "verrouille01" not in vues,
                     "état illisible pour l'instant (accès refusé) : pas pris pour un état abîmé, rien d'effacé",
                     f"{statut} {sorted(vues)}")

        # Historique de relecture : l'original n'est retiré que sur une absence durable.
        historique_reel = lecture.DOSSIER_HISTORIQUE
        lecture.DOSSIER_HISTORIQUE = base / "historique"
        try:
            for nom, chemin in (("injoignable", base / "cle-usb" / "dossier" / "t.txt"), ("absente", base / "t-ab.txt")):
                d = lecture.DOSSIER_HISTORIQUE / nom
                d.mkdir(parents=True)
                lecture._ecrire_gz(d / "index.json.gz", {"chemin": str(chemin), "pile": [1], "suivant": 2})
                (d / "original.json.gz").write_bytes(b"original")
            lecture._elaguer_historique()
            garde = (lecture.DOSSIER_HISTORIQUE / "injoignable" / "original.json.gz").is_file() \
                and (lecture.DOSSIER_HISTORIQUE / "absente" / "original.json.gz").is_file()
            (lecture.DOSSIER_HISTORIQUE / "absente" / lecture.NOM_ABSENCE).write_text(vieux, encoding="ascii")
            lecture._elaguer_historique()
            verifier(garde and not (lecture.DOSSIER_HISTORIQUE / "absente").exists()
                     and (lecture.DOSSIER_HISTORIQUE / "injoignable" / "original.json.gz").is_file(),
                     "historique de relecture : gardé sur un lecteur injoignable, retiré après une absence durable")
        finally:
            lecture.DOSSIER_HISTORIQUE = historique_reel
    finally:
        chemins.RACINE = racine


def _simuler_2x(local: Path, valeur) -> None:
    import json

    os.environ["LOCALAPPDATA"] = str(local)
    os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = valeur if isinstance(valeur, str) else json.dumps(valeur)


def _environnement_garde():
    return {k: os.environ.get(k) for k in ("LOCALAPPDATA", "SCRIBOUILLE_ESSAI_REGISTRE", "SCRIBOUILLE_DONNEES")}


def _rendre_environnement(reels: dict) -> None:
    for cle, valeur in reels.items():
        if valeur is None:
            os.environ.pop(cle, None)
        else:
            os.environ[cle] = valeur


def essai_classement_2x(base: Path) -> None:
    """16/11 (point 2, M7) : ce que seule une 2.4 écrit n'est plus tenu pour la 2.3.3, et reste protégé dans le doute."""
    from app import cache_openvino, chemins, inventaire, migration

    titre("Dossier partagé : ce que la 2.3.3 n'écrit pas n'est plus rangé parmi ses fichiers")
    local = base / "classement-local"
    donnees = local / "WhiScribe"
    (donnees / "cache-openvino").mkdir(parents=True)
    (donnees / "config.json").write_text("{}", encoding="utf-8")
    (donnees / "calibration.json").write_text("{}", encoding="utf-8")
    (donnees / "cache-openvino" / "1234567890123456789.blob").write_bytes(b"b" * 1000)
    (donnees / "cache-openvino" / "1234567890123456780.cl_cache").write_bytes(b"c" * 10)
    reels = _environnement_garde()
    racine, imposees = chemins.RACINE, chemins.DONNEES_IMPOSEES
    reglages = {"dossier_sortie": str(base / "sorties-classement")}
    deux33 = {"ruche": "HKCU", "version": "2.3.3", "dossier": str(local / "Programs" / "WhiScribe")}
    try:
        chemins.RACINE, chemins.DONNEES_IMPOSEES = donnees, False
        _simuler_2x(local, [deux33])
        verifier(chemins.version_2x_sans_openvino() and not migration.etendu_2x(),
                 "2.3.3 lue dans le registre : sûrement sans OpenVINO")
        noms = {Path(c).name for c in inventaire.partages(reglages)}
        postes = {p.cle: p for p in inventaire.postes(reglages)[0]}
        verifier("config.json" in noms and "cache-openvino" not in noms and "calibration.json" not in noms,
                 "2.3.3 : réglages toujours à la 2.x ; cache OpenVINO et mesures de durée à la 3.x seule", str(sorted(noms)))
        verifier("cache_openvino" in postes and postes["cache_openvino"].liberable
                 and postes["cache_openvino"].octets == 1010,
                 "2.3.3 : le cache OpenVINO est un poste à nous, avec sa taille, libérable",
                 str({k: (p.octets, p.liberable) for k, p in postes.items()}))
        for cas, valeur in (("2.4.0 installée", [{**deux33, "version": "2.4.0"}]),
                            ("registre illisible", "erreur"),
                            ("version 2.3.10 inconnue", [{**deux33, "version": "2.3.10"}]),
                            ("clé sans version", [{**deux33, "version": ""}])):
            _simuler_2x(local, valeur)
            noms = {Path(c).name for c in inventaire.partages(reglages)}
            verifier(migration.etendu_2x() and {"cache-openvino", "calibration.json", "config.json"} <= noms,
                     f"{cas} : cache OpenVINO et mesures tenus pour la 2.x aussi (dans le doute)", str(sorted(noms)))
        _simuler_2x(local, [deux33])
        (local / "Programs" / "WhiScribe").mkdir(parents=True)
        (local / "Programs" / "WhiScribe" / "Scribouille.exe").write_bytes(b"MZ")
        verifier(migration.etendu_2x(), "2.3.3 dans le registre mais Scribouille.exe à côté (une 2.4 ?) : dans le doute")
        (local / "Programs" / "WhiScribe" / "Scribouille.exe").unlink()
        # Dans le doute (2.4 possible), seules les entrées de notre index sont à nous.
        _simuler_2x(local, [{**deux33, "version": "2.4.0"}])
        verifier(cache_openvino.fichiers_a_nous() == [] and not cache_openvino.adoption_permise(),
                 "2.4 possible : aucune entrée sans index n'est prise pour la nôtre")
        index = cache_openvino._index_vide()
        index["entrees"]["1234567890123456780.cl_cache"] = {"cle": "k", "octets": 10, "ecrit": 0}
        cache_openvino._ecrire_index(index)
        postes = {p.cle: p for p in inventaire.postes(reglages)[0]}
        verifier([c.name for c in postes.get("cache_openvino", inventaire.Poste("x")).chemins]
                 == ["1234567890123456780.cl_cache"],
                 "2.4 possible : le poste « cache OpenVINO » ne tient que les entrées de notre index",
                 str(postes.get("cache_openvino")))
    finally:
        chemins.RACINE, chemins.DONNEES_IMPOSEES = racine, imposees
        _rendre_environnement(reels)


def essai_cache_openvino(base: Path) -> None:
    """16/11 (point 2) : le cache de compilation d'OpenVINO est indexé, borné, jamais touché pendant un calcul."""
    import json
    import time
    import types

    from app import cache_openvino, chemins, inventaire, moteur, moteur_openvino, presets

    titre("Cache OpenVINO : index, délai, plafond, marque d'usage, jamais ce qui n'est pas à nous")
    racine, imposees = chemins.RACINE, chemins.DONNEES_IMPOSEES
    reels = _environnement_garde()
    chemins.RACINE, chemins.DONNEES_IMPOSEES = base / "cache-ov", True
    cache = chemins.RACINE / "cache-openvino"
    cache.mkdir(parents=True)
    sauves = (moteur.etat_modele, moteur.assurer_modele_telecharge, sys.modules.get("openvino_genai"))
    vus_ov = (moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, moteur_openvino._supposes)
    modeles_ov = base / "modele-ov-factice"
    modeles_ov.mkdir()
    jour = 86400

    class Pipeline:
        """WhisperPipeline factice : « compile » encodeur et décodeur dans CACHE_DIR, en lecture seule, comme OpenVINO."""

        def __init__(self, dossier, peripherique, **proprietes):
            empreinte = abs(hash((peripherique, json.dumps(proprietes, sort_keys=True)))) % 10 ** 17
            for rang, taille in ((1, 3000), (2, 2000)):
                blob = Path(proprietes["CACHE_DIR"]) / f"{rang * 10 ** 17 + empreinte}.blob"
                if blob.exists():
                    os.chmod(blob, 0o600)
                blob.write_bytes(b"x" * taille)
                os.chmod(blob, 0o400)

    try:
        os.environ["LOCALAPPDATA"] = str(base / "cache-ov-local")
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = "[]"
        moteur.etat_modele = lambda depot: {"etat": "complet", "snapshot": str(modeles_ov)}
        moteur.assurer_modele_telecharge = lambda depot, etat, signaler=None: {"snapshot": str(modeles_ov)}
        sys.modules["openvino_genai"] = types.SimpleNamespace(WhisperPipeline=Pipeline)
        moteur_openvino.amorcer("2026.4.1", ["CPU", "GPU"])
        depot = presets.depot_openvino(presets.MODELE_TURBO) or "OpenVINO/whisper-large-v3-turbo-int8-ov"
        ov = moteur_openvino.MoteurOpenVINO(None, "CPU")
        ov.proprietes = {"INFERENCE_NUM_THREADS": 4}
        ov.charger(presets.MODELE_TURBO)
        marques = list(cache.glob("scribouille-usage-*.marque"))
        index = cache_openvino.lire_index()
        verifier(len(index["entrees"]) == 2 and len(index["cles"]) == 1 and len(marques) == 1,
                 "ouverture : les compilés écrits sont rattachés à leur réglage, marque d'usage posée",
                 json.dumps(index)[:300])
        (cache / "999999999999999999.cl_cache").write_bytes(b"k" * 50)   # noyau compilé pendant le calcul
        ov.liberer()
        index = cache_openvino.lire_index()
        cle = next(iter(index["cles"]))
        verifier(index["entrees"].get("999999999999999999.cl_cache", {}).get("cle") == cle
                 and not list(cache.glob("scribouille-usage-*.marque"))
                 and index["cles"][cle]["proprietes"] == {"INFERENCE_NUM_THREADS": "4"}
                 and index["cles"][cle]["modele"] == depot,
                 "libération : les noyaux écrits pendant le calcul vont avec ce réglage, marque levée",
                 json.dumps(index)[:400])

        # Un autre réglage (campagne), une entrée d'avant l'index, un fichier inconnu.
        ov.proprietes = {"PERFORMANCE_HINT": "LATENCY"}
        ov.charger(presets.MODELE_TURBO)
        ov.liberer()
        (cache / "555555555555555555.blob").write_bytes(b"a" * 3000)    # sans index : d'une version d'avant
        (cache / "inconnu.bin").write_bytes(b"?")
        maintenant = time.time()
        bilan = cache_openvino.purger(maintenant=maintenant)
        verifier(bilan["fait"] and not bilan["effacees"]
                 and "555555555555555555.blob" in cache_openvino.lire_index()["anterieures"],
                 "purge du jour : rien d'effacé, l'entrée sans index est datée à son premier constat", str(bilan))
        # Le réglage de campagne n'a plus servi depuis 31 jours ; l'autre, si.
        index = cache_openvino.lire_index()
        campagne = next(c for c, f in index["cles"].items() if "PERFORMANCE_HINT" in f["proprietes"])
        index["cles"][campagne]["dernier_usage"] = maintenant - 31 * jour
        cle_service = next(c for c in index["cles"] if c != campagne)
        index["cles"][cle_service]["dernier_usage"] = maintenant + 30 * jour
        index["anterieures"]["555555555555555555.blob"]["vue"] = maintenant - 31 * jour
        cache_openvino._ecrire_index(index)
        vieux = maintenant - 2 * jour
        for f in cache.iterdir():
            os.utime(f, (vieux, vieux))
        (cache / "777777777777777777.blob").write_bytes(b"r" * 10)    # écrite à l'instant, sans index
        fichiers_campagne = [n for n, f in index["entrees"].items() if f["cle"] == campagne]
        bilan = cache_openvino.purger(maintenant=maintenant)
        effacees = {e["nom"] for e in bilan["effacees"]}
        verifier(effacees == set(fichiers_campagne) | {"555555555555555555.blob"},
                 f"purge : réglage inutilisé depuis {cache_openvino.DELAI_JOURS} jours et entrée d'avant vue il y a "
                 "plus longtemps effacés", str(sorted(effacees)))
        verifier((cache / "inconnu.bin").is_file() and (cache / "777777777777777777.blob").is_file()
                 and (cache / "999999999999999999.cl_cache").is_file(),
                 "purge : fichier inconnu, entrée toute récente et réglage en service jamais touchés")
        # Plafond : au-delà, le moins utile part, jamais le réglage le plus récent.
        for k in range(3):
            (cache / f"88888888888888888{k}.blob").write_bytes(b"p" * 4000)
            os.utime(cache / f"88888888888888888{k}.blob", (vieux - k, vieux - k))
        cache_openvino.purger(maintenant=maintenant)   # premier constat
        bilan = cache_openvino.purger(maintenant=maintenant, plafond=9000)
        restants = {f.name for f in cache.iterdir()}
        service = {n for n, f in cache_openvino.lire_index()["entrees"].items() if f["cle"] == cle_service}
        verifier(bilan["reconnues_octets"] <= 9000 and service <= restants and "inconnu.bin" in restants
                 and all(e["raison"] == "plafond" for e in bilan["effacees"]) and bilan["effacees"],
                 "plafond : les plus anciennes partent d'abord, le réglage en service reste", str(bilan)[:300])

        # Jamais pendant un calcul : marque d'usage d'un autre processus vivant.
        enfant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], creationflags=SANS_FENETRE)
        try:
            from app import instance

            createur = instance._creation(enfant.pid)
            (cache / f"scribouille-usage-{enfant.pid}.marque").write_text(f"{enfant.pid} {createur:.3f}",
                                                                          encoding="ascii")
            avant = sorted(f.name for f in cache.iterdir())
            bilan = cache_openvino.purger(maintenant=maintenant + 400 * jour)
            libere = inventaire.liberer(["cache_openvino"], {"dossier_sortie": str(base / "sorties-cache")})
            verifier(bilan["raison"] == "calcul_en_cours" and sorted(f.name for f in cache.iterdir()) == avant
                     and libere["octets"] == 0 and libere["restes"],
                     "un autre processus calcule avec ce cache : ni purge, ni libération", str(bilan) + str(libere))
        finally:
            enfant.kill()
            enfant.wait(10)
        bilan = cache_openvino.purger(maintenant=maintenant + 400 * jour)
        verifier(bilan["fait"] and not list(cache.glob("scribouille-usage-*.marque")),
                 "processus mort : sa marque est retirée, la purge reprend", str(bilan)[:200])
        verifier((cache / "inconnu.bin").is_file(), "même après un an : le fichier inconnu est toujours là")

        # Dossier partagé avec une 2.x qui peut être une 2.4 : les entrées sans index restent.
        local = base / "cache-ov-partage"
        donnees = local / "WhiScribe"
        (donnees / "cache-openvino").mkdir(parents=True)
        chemins.RACINE = donnees
        os.environ["LOCALAPPDATA"] = str(local)
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = json.dumps([{"ruche": "HKCU", "version": "2.4.0", "dossier": ""}])
        (donnees / "cache-openvino" / "444444444444444444.blob").write_bytes(b"z" * 100)
        cache_openvino.purger(maintenant=maintenant)
        bilan = cache_openvino.purger(maintenant=maintenant + 400 * jour, plafond=0)
        verifier((donnees / "cache-openvino" / "444444444444444444.blob").is_file() and not bilan["effacees"],
                 "2.4 possible sur le dossier partagé : une entrée sans index n'est jamais effacée")
        # Commande de lecture : rien d'écrit, rien d'effacé.
        chemins.LECTURE_SEULE = True
        try:
            bilan = cache_openvino.purger(maintenant=maintenant + 400 * jour)
            resume = cache_openvino.resume()
        finally:
            chemins.LECTURE_SEULE = False
        verifier(bilan["raison"] == "lecture_seule" and resume["octets"] == 100 and resume["reconnues"] == 0
                 and resume["non_reconnues_octets"] == 100,
                 "lecture seule : purge refusée ; le résumé dit la taille et ce qui n'est pas reconnu", str(resume))
    finally:
        moteur.etat_modele, moteur.assurer_modele_telecharge = sauves[0], sauves[1]
        if sauves[2] is None:
            sys.modules.pop("openvino_genai", None)
        else:
            sys.modules["openvino_genai"] = sauves[2]
        moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, moteur_openvino._supposes = vus_ov
        chemins.RACINE, chemins.DONNEES_IMPOSEES = racine, imposees
        _rendre_environnement(reels)


def essai_cache_plafond_tenu(base: Path) -> None:
    """
    16/11 (tour 7) : le plafond du cache est tenu sur le dossier réel. Scénario
    du portable, à l'échelle (1 Go = 1 000 octets) : dix compilés d'avant
    l'index, en lecture seule comme OpenVINO les écrit, dont les quatre des
    deux réglages en service (les plus anciens), un fichier tenu ouvert par un
    autre programme ; deux lancements suffisent, sans recompilation.
    """
    import json
    import stat
    import time
    import types

    from app import cache_openvino, chemins, cli, instance, inventaire, journal, moteur, moteur_openvino, presets

    titre("Cache OpenVINO : plafond tenu sur le dossier réel, compilés en service jamais effacés")
    racine, imposees = chemins.RACINE, chemins.DONNEES_IMPOSEES
    reels = _environnement_garde()
    plafond_reel = cache_openvino.PLAFOND_OCTETS
    chemins.RACINE, chemins.DONNEES_IMPOSEES = base / "plafond-ov", True
    cache = chemins.RACINE / "cache-openvino"
    cache.mkdir(parents=True)
    sauves = (moteur.etat_modele, moteur.assurer_modele_telecharge, sys.modules.get("openvino_genai"))
    vus_ov = (moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, moteur_openvino._supposes)
    maintenant = time.time()
    heure = 3600
    turbo = presets.depot_openvino(presets.MODELE_TURBO) or "OpenVINO/whisper-large-v3-turbo-int8-ov"
    large = "OpenVINO/whisper-large-v3-int8-ov"
    # Réglage -> (encodeur, décodeur) : noms et tailles des compilés qu'OpenVINO relit.
    compiles = {"turbo": (("11111111111111111101.blob", 633), ("11111111111111111102.blob", 234)),
                "large": (("22222222222222222201.blob", 1280), ("22222222222222222202.blob", 689))}
    inutiles = {"33333333333333333301.blob": 622, "33333333333333333302.blob": 622,
                "33333333333333333303.blob": 233, "33333333333333333304.blob": 165,
                "33333333333333333305.blob": 944, "33333333333333333306.blob": 600}
    tenu_ailleurs = "33333333333333333305.blob"
    compilations: list[str] = []

    def poser(nom: str, taille: int, ecrit: float, accede: float) -> None:
        chemin = cache / nom
        chemin.write_bytes(b"o" * taille)
        os.utime(chemin, (accede, ecrit))
        os.chmod(chemin, stat.S_IREAD)    # OpenVINO écrit ses compilés en lecture seule

    class Pipeline:
        """WhisperPipeline factice : relit ses compilés s'ils sont là (encodeur tenu, dernier accès du
        décodeur avancé, comme sur processeur et sur la puce), sinon « compile »."""
        signal = True

        def __init__(self, dossier, peripherique, **proprietes):
            reglage = Path(dossier).name
            self.tenus = []
            for rang, (nom, taille) in enumerate(compiles[reglage]):
                chemin = Path(proprietes["CACHE_DIR"]) / nom
                if not chemin.exists():
                    compilations.append(nom)
                    chemin.write_bytes(b"c" * taille)
                    os.chmod(chemin, stat.S_IREAD)
                elif Pipeline.signal and rang == 0:
                    self.tenus.append(open(chemin, "rb"))    # projeté tant que le modèle est ouvert
                elif Pipeline.signal:
                    os.utime(chemin, ns=(time.time_ns(), chemin.stat().st_mtime_ns))    # relu

    tenant = None
    messages: list[str] = []
    info_reelle = journal.info

    def noter_info(message, *args, **kwargs):
        messages.append(message % args if args else message)
        return info_reelle(message, *args, **kwargs)

    journal.info = noter_info
    try:
        os.environ["LOCALAPPDATA"] = str(base / "plafond-ov-local")
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = "[]"
        dossiers = {turbo: base / "plafond-modeles" / "turbo", large: base / "plafond-modeles" / "large"}
        for d in dossiers.values():
            d.mkdir(parents=True)
        moteur.etat_modele = lambda depot: {"etat": "complet", "snapshot": str(dossiers[depot])}
        moteur.assurer_modele_telecharge = lambda depot, etat, signaler=None: {"snapshot": str(dossiers[depot])}
        sys.modules["openvino_genai"] = types.SimpleNamespace(WhisperPipeline=Pipeline)
        moteur_openvino.amorcer("2026.4.1", ["CPU", "GPU"])
        presets_ov = {turbo: presets.MODELE_TURBO, large: large}
        cache_openvino.PLAFOND_OCTETS = 4000

        # Le portable : compilés des 11 et 12/11 (ceux en service sont les plus
        # anciens), dernier accès de la sauvegarde de nuit pour les inutiles,
        # du passage du jour pour ceux en service ; noyaux de la puce ; index
        # de la 3.x d'avant ce tour : deux clés, des noyaux, aucun compilé.
        for reglage, paires in compiles.items():
            for nom, taille in paires:
                poser(nom, taille, maintenant - 5 * 86400, maintenant - 2 * heure)
        for k, (nom, taille) in enumerate(inutiles.items()):
            poser(nom, taille, maintenant - 4 * 86400 + k * 60, maintenant - 10 * heure + k)
        index = cache_openvino._index_vide()
        cles = {}
        for reglage, depot in (("turbo", turbo), ("large", large)):
            cle, infos = cache_openvino.cle_reglage(depot, "CPU", {}, moteur_openvino.version(), "", True)
            cles[reglage] = cle
            index["cles"][cle] = {**infos, "premier_usage": maintenant - 4 * heure, "dernier_usage": maintenant - 3 * heure}
        for k in range(20):
            nom = f"9{k:017d}.cl_cache"
            (cache / nom).write_bytes(b"k" * 5)
            os.utime(cache / nom, (maintenant - 3 * 86400, maintenant - 3 * 86400))
            if k < 4:
                index["entrees"][nom] = {"cle": cles["turbo" if k % 2 else "large"], "octets": 5, "ecrit": 0}
        cache_openvino._ecrire_index(index)
        en_service = {nom for paires in compiles.values() for nom, _ in paires}
        total_depart = sum(f.stat().st_size for f in cache.iterdir() if cache_openvino.est_entree(f.name))
        # Un autre programme (sauvegarde, antivirus) tient un inutile ouvert, sans partage d'effacement.
        tenant = subprocess.Popen([sys.executable, "-c",
                                   f"import time; f = open(r'{cache / tenu_ailleurs}', 'rb'); print('ok', flush=True); "
                                   "time.sleep(120)"], stdout=subprocess.PIPE, creationflags=SANS_FENETRE)
        tenant.stdout.readline()

        # Ouverture de la fenêtre (ou début de transcrire) : rien ne dit encore
        # quels compilés servent, aucun antérieur ne part au plafond.
        bilan = cache_openvino.purger()
        res = cache_openvino.resume()
        verifier(not bilan["effacees"] and sorted(bilan["attente"]) == sorted(cles.values())
                 and res["octets"] == total_depart and res["attente"]
                 and "gardés jusqu'au prochain chargement" in cache_openvino.phrase_etat(res),
                 "premier lancement : au-delà du plafond, les compilés d'avant l'index attendent que chaque "
                 "réglage en service soit reconnu (aucun effacé), et diagnostic le dit",
                 str(bilan)[:300] + cache_openvino.phrase_etat(res))

        # Lancement 1 : une transcription avec turbo. Ses compilés relus et tenus sont rattachés.
        ov = moteur_openvino.MoteurOpenVINO(None, "CPU")
        ov.temoin = True
        ov.charger(presets_ov[turbo])
        index = cache_openvino.lire_index()
        rattaches = {n for n, f in index["entrees"].items() if f["cle"] == cles["turbo"] and n.endswith(".blob")}
        verifier(rattaches == {n for n, _ in compiles["turbo"]} and not compilations
                 and en_service <= {f.name for f in cache.iterdir()},
                 "lancement 1 : les compilés de turbo, relus (dernier accès) et tenus (projetés), sont rattachés "
                 "à son réglage ; rien n'est recompilé ni effacé de ce qui sert", str(sorted(rattaches)))
        ov.liberer()

        # Lancement 2 : large-v3. Les deux réglages en service sont reconnus,
        # le plafond s'applique sur le dossier réel ; l'entrée tenue ailleurs
        # n'est pas décomptée, la purge passe aux suivantes.
        ov.charger(presets_ov[large])
        presentes = {f.name: f.stat().st_size for f in cache.iterdir() if cache_openvino.est_entree(f.name)}
        index = cache_openvino.lire_index()
        reconnues = sum(presentes.values())
        verifier(en_service <= set(presentes) and not compilations,
                 "lancement 2 : les quatre compilés en service sont toujours là, aucune recompilation",
                 str(sorted(presentes)))
        verifier(reconnues <= 4000 and tenu_ailleurs in presentes,
                 "lancement 2 : le dossier réel repasse sous le plafond malgré l'entrée tenue ailleurs "
                 f"({reconnues} octets pour 4 000)", str(presentes))
        verifier(index["echecs"].get(tenu_ailleurs, {}).get("erreur") == "ouvert_ailleurs"
                 and not os.access(cache / tenu_ailleurs, os.W_OK),
                 "échec d'effacement noté avec sa cause, et l'attribut lecture seule remis",
                 json.dumps(index["echecs"]))
        ov.liberer()
        res = cache_openvino.resume()
        phrase = cache_openvino.phrase_etat(res)
        ligne = cli._ligne_cache(res)
        poste = {p.cle: p for p in inventaire.postes({"dossier_sortie": str(base / "plafond-sorties")})[0]}
        verifier(res["echecs"] == 1 and "n'a pas pu être effacé" in phrase and phrase in ligne
                 and phrase in poste["cache_openvino"].description and not res["attente"],
                 "diagnostic et espace disent en une phrase ce qui n'a pas pu être effacé", ligne)
        lignes_echec = [m for m in messages if "non effacée(s)" in m]
        lignes_borne = [m for m in messages if m.startswith("Cache OpenVINO borné")]
        verifier(len(lignes_echec) == 1 and "ouvert_ailleurs 1" in lignes_echec[0]
                 and not [m for m in messages if "laissé (" in m],
                 "journal : les échecs sont dits en une ligne groupée (nombre, taille, cause), pas un par fichier",
                 str(lignes_echec))
        verifier(lignes_borne and f"reste {langues.octets(reconnues)}" in lignes_borne[-1],
                 "journal : le reste annoncé est celui du dossier réel après effacement", str(lignes_borne))

        # L'autre programme lâche le fichier : la purge suivante n'a plus d'échec à dire.
        tenant.kill()
        tenant.wait(10)
        tenant = None
        bilan = cache_openvino.purger()
        verifier(bilan["fait"] and not bilan["echecs"] and not cache_openvino.phrase_etat()
                 and bilan["reconnues_octets"] == sum(f.stat().st_size for f in cache.iterdir()
                                                      if cache_openvino.est_entree(f.name)),
                 "fichier relâché : plus d'échec dit, le reste annoncé est le dossier réel", str(bilan)[:300])

        # « effacer cache_openvino » : compilés en lecture seule effacés aussi,
        # dossier entier (à nous) comme entrée par entrée (dossier partagé
        # avec une 2.4 possible : seules nos entrées indexées).
        sorties_liberer = {"dossier_sortie": str(base / "plafond-sorties")}
        libere = inventaire.liberer(["cache_openvino"], sorties_liberer)
        verifier((not cache.exists() or not [f for f in cache.iterdir() if cache_openvino.est_entree(f.name)])
                 and libere["octets"] > 0
                 and not libere["restes"],
                 "effacer cache_openvino : compilés en lecture seule effacés (dossier à nous)", str(libere)[:300])
        cache.mkdir(parents=True, exist_ok=True)
        local = base / "plafond-partage"
        donnees_2x = local / "WhiScribe"
        (donnees_2x / "cache-openvino").mkdir(parents=True)
        _simuler_2x(local, [{"ruche": "HKCU", "version": "2.4.0", "dossier": ""}])
        chemins.RACINE = donnees_2x
        index = cache_openvino._index_vide()
        for nom, taille in (("44444444444444444401.blob", 70), ("44444444444444444402.blob", 30)):
            poser(nom, taille, maintenant - 5 * 86400, maintenant - 5 * 86400)
            os.replace(cache / nom, donnees_2x / "cache-openvino" / nom)
            index["entrees"][nom] = {"cle": "k", "octets": taille, "ecrit": 0}
        (donnees_2x / "cache-openvino" / "55555555555555555501.blob").write_bytes(b"2" * 40)
        cache = donnees_2x / "cache-openvino"
        cache_openvino._ecrire_index(index)
        libere = inventaire.liberer(["cache_openvino"], sorties_liberer)
        verifier(sorted(f.name for f in cache.iterdir() if cache_openvino.est_entree(f.name))
                 == ["55555555555555555501.blob"] and libere["octets"] == 100 and not libere["restes"],
                 "dossier partagé (2.4 possible) : nos entrées en lecture seule effacées une à une, l'autre laissée",
                 str(libere)[:300])
        chemins.RACINE = base / "plafond-ov"
        cache = chemins.RACINE / "cache-openvino"
        _simuler_2x(base / "plafond-ov-local", "[]")
        # Marques d'usage laissées par un arrêt forcé : processus mort, PID
        # réutilisé (vivant, autre heure de création), notre propre PID d'un
        # lancement d'avant. Retirées, elles ne bloquent pas la purge.
        enfant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], creationflags=SANS_FENETRE)
        try:
            (cache / "scribouille-usage-999999.marque").write_text("999999 1000.000", encoding="ascii")
            (cache / f"scribouille-usage-{enfant.pid}.marque").write_text(
                f"{enfant.pid} {instance._creation(enfant.pid) - 500:.3f}", encoding="ascii")
            (cache / f"scribouille-usage-{os.getpid()}.marque").write_text(
                f"{os.getpid()} {instance._creation(os.getpid()) - 900:.3f}", encoding="ascii")
            vieux = time.time() - 600
            for m in cache.glob("scribouille-usage-*.marque"):
                os.utime(m, (vieux, vieux))
            bilan = cache_openvino.purger()
            restantes = [m.name for m in cache.glob("scribouille-usage-*.marque")]
            verifier(bilan["fait"] and restantes in ([], [f"scribouille-usage-{os.getpid()}.marque"]),
                     "marques d'un arrêt forcé (processus mort, PID réutilisé) : la purge se fait quand même",
                     str(bilan)[:200] + str(restantes))
            verifier(not [n for n in restantes if n != f"scribouille-usage-{os.getpid()}.marque"],
                     "marques mortes retirées au lancement suivant", str(restantes))
        finally:
            enfant.kill()
            enfant.wait(10)
            for m in cache.glob("scribouille-usage-*.marque"):
                m.unlink(missing_ok=True)

        # Sans signal (dernier accès non tenu, compilé relu puis refermé) :
        # rien d'antérieur ne part au plafond tant que le réglage n'est pas
        # reconnu ; seule la règle des 30 jours finit par s'appliquer.
        muet = base / "plafond-ov-muet"
        chemins.RACINE = muet
        cache = muet / "cache-openvino"
        cache.mkdir(parents=True)
        for nom, taille in compiles["turbo"]:
            poser(nom, taille, maintenant - 5 * 86400, maintenant - 5 * 86400)
        for nom, taille in list(inutiles.items())[:4]:
            poser(nom, taille, maintenant - 4 * 86400, maintenant - 4 * 86400)
        Pipeline.signal = False
        cache_openvino.PLAFOND_OCTETS = 1000
        ov = moteur_openvino.MoteurOpenVINO(None, "CPU")
        ov.temoin = True
        avant = {f.name for f in cache.iterdir()}
        bilan = cache_openvino.purger()
        ov.charger(presets_ov[turbo])
        ov.liberer()
        bilan_apres = cache_openvino.purger()
        verifier(avant <= {f.name for f in cache.iterdir()} and bilan["attente"] == [cache_openvino.AUCUN_CHARGEMENT]
                 and bilan_apres["attente"] and not compilations,
                 "sans signal au chargement : aucun antérieur effacé au plafond (ni avant le premier chargement, "
                 "ni après un chargement qui n'a rien reconnu)", str(bilan_apres)[:300])
        bilan = cache_openvino.purger(maintenant=maintenant + 31 * 86400)
        verifier(not [f for f in cache.iterdir() if f.suffix == ".blob"]
                 and {e["raison"] for e in bilan["effacees"]} == {"anterieure"},
                 f"sans signal : la règle des {cache_openvino.DELAI_JOURS} jours s'applique quand même (plafond tenu)",
                 str(bilan)[:300])
    finally:
        journal.info = info_reelle
        cache_openvino.PLAFOND_OCTETS = plafond_reel
        if tenant is not None:
            tenant.kill()
            tenant.wait(10)
        moteur.etat_modele, moteur.assurer_modele_telecharge = sauves[0], sauves[1]
        if sauves[2] is None:
            sys.modules.pop("openvino_genai", None)
        else:
            sys.modules["openvino_genai"] = sauves[2]
        moteur_openvino._peripheriques_vus, moteur_openvino._version_vue, moteur_openvino._supposes = vus_ov
        chemins.RACINE, chemins.DONNEES_IMPOSEES = racine, imposees
        _rendre_environnement(reels)


def essai_ecritures_identiques(base: Path) -> None:
    """16/11 (tour 7, point 2) : un fichier d'état n'est jamais réécrit (ni redaté) quand rien n'y change."""
    import json
    import time

    from app import cache_openvino, calibration, chemins, config as config_module, surveillance

    titre("Fichiers d'état : rien de réécrit quand le contenu serait identique à l'octet")
    racine, imposees = chemins.RACINE, chemins.DONNEES_IMPOSEES
    choix_modeles, dossier_modeles = chemins.FICHIER_CHOIX_MODELES, chemins.DOSSIER_MODELES
    fichier_config = chemins.FICHIER_CONFIG
    reels = _environnement_garde()
    vieux = time.time() - 3 * 86400

    def date(chemin: Path) -> int:
        return chemin.stat().st_mtime_ns

    def vieillir(chemin: Path) -> int:
        os.utime(chemin, (vieux, vieux))
        return date(chemin)

    try:
        # Dossier à nous : config.json.
        chemins.RACINE, chemins.DONNEES_IMPOSEES = base / "identique-propre", True
        chemins.RACINE.mkdir(parents=True)
        chemins.FICHIER_CONFIG = chemins.RACINE / "config.json"
        os.environ["LOCALAPPDATA"] = str(base / "identique-local-vide")
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = "[]"
        config_module._LECTURES.clear()
        reglages = config_module.charger()
        verifier(config_module.sauver(reglages) and chemins.FICHIER_CONFIG.is_file(), "réglages : première écriture")
        avant = vieillir(chemins.FICHIER_CONFIG)
        config_module.sauver(config_module.charger())
        verifier(date(chemins.FICHIER_CONFIG) == avant, "config.json : resauvé sans changement, ni réécrit ni redaté")
        reglages = config_module.charger()
        reglages["preset"] = "rapide" if reglages.get("preset") != "rapide" else "qualite"
        config_module.sauver(reglages)
        verifier(date(chemins.FICHIER_CONFIG) != avant
                 and json.loads(chemins.FICHIER_CONFIG.read_text(encoding="utf-8"))["preset"] == reglages["preset"],
                 "config.json : un vrai changement est bien écrit")

        # Dossier partagé avec une 2.3.3 : config-scribouille.json (le fichier du portable).
        local = base / "identique-partage"
        donnees = local / "WhiScribe"
        donnees.mkdir(parents=True)
        (local / "Programs" / "WhiScribe").mkdir(parents=True)
        (local / "Programs" / "WhiScribe" / "WhiScribe.exe").write_bytes(b"MZ")
        (donnees / "config.json").write_text(json.dumps({"preset": "rapide", "langue_interface": "fr"}), encoding="utf-8")
        _simuler_2x(local, [{"ruche": "HKCU", "version": "2.3.3", "dossier": str(local / "Programs" / "WhiScribe")}])
        chemins.RACINE = donnees
        chemins.FICHIER_CONFIG = donnees / "config.json"
        config_module._LECTURES.clear()
        reglages = config_module.charger()
        reglages["preset"] = "qualite"
        config_module.sauver(reglages)
        propre = config_module.fichier_propre()
        verifier(config_module.partage_ancienne_version() and propre.is_file(),
                 "dossier partagé : nos réglages à part dans config-scribouille.json", str(propre))
        avant, avant_2x = vieillir(propre), vieillir(donnees / "config.json")
        for _ in range(3):
            config_module.sauver(config_module.charger())
        verifier(date(propre) == avant and date(donnees / "config.json") == avant_2x,
                 "config-scribouille.json : trois sauvegardes sans changement, ni réécrit ni redaté (celui de la 2.x non plus)")

        # Index du cache OpenVINO : purgé à chaque lancement, réécrit seulement s'il change.
        (donnees / "cache-openvino").mkdir()
        (donnees / "cache-openvino" / "123456789012345678.blob").write_bytes(b"b" * 10)
        cache_openvino.purger()
        index = donnees / "cache-openvino" / cache_openvino.NOM_INDEX
        avant = vieillir(index)
        cache_openvino.purger()
        cache_openvino.purger()
        verifier(date(index) == avant, "index du cache OpenVINO : purges sans changement, ni réécrit ni redaté")

        # Mesures de durée, mémoire du dossier surveillé, choix du dossier des modèles.
        calibration._ecrire({"format": 1, "mesures": {}})
        avant = vieillir(calibration.fichier())
        calibration._ecrire(json.loads(calibration.fichier().read_text(encoding="utf-8")))
        verifier(date(calibration.fichier()) == avant, "mesures de durée : réécrites à l'identique, fichier inchangé")
        surveillance.ecrire_memoire({})
        avant = vieillir(surveillance.fichier_memoire())
        surveillance.ecrire_memoire({})
        verifier(date(surveillance.fichier_memoire()) == avant, "mémoire du dossier surveillé : même contenu, fichier inchangé")
        chemins.FICHIER_CHOIX_MODELES = donnees / "dossier-modeles.txt"
        chemins.definir_dossier_modeles(str(base / "identique-modeles"), memoriser=True)
        avant = vieillir(chemins.FICHIER_CHOIX_MODELES)
        chemins.definir_dossier_modeles(str(base / "identique-modeles"), memoriser=True)
        verifier(date(chemins.FICHIER_CHOIX_MODELES) == avant, "choix du dossier des modèles : même chemin, fichier inchangé")
    finally:
        chemins.RACINE, chemins.DONNEES_IMPOSEES = racine, imposees
        chemins.FICHIER_CHOIX_MODELES, chemins.FICHIER_CONFIG = choix_modeles, fichier_config
        chemins.definir_dossier_modeles(str(dossier_modeles))
        config_module._LECTURES.clear()
        _rendre_environnement(reels)


def essai_reprise_fenetres(base: Path) -> None:
    """
    16/11 (tour 7, point 4) : une reprise sur OpenVINO retrouve les fenêtres du
    passage complet (même texte), sans segment perdu ni doublé à la jointure.
    """
    import hashlib
    from types import SimpleNamespace

    import numpy as np

    from app import materiel, moteur_openvino as mo

    titre("Reprise sur OpenVINO : fenêtres du passage complet, jointure sans perte ni doublon")
    F = mo.FREQUENCE
    # 4 min de « parole » : salves de 3 à 9 s séparées de 0,6 à 1,6 s de silence,
    # chacune reconnaissable à son contenu. VAD simulé : les salves non nulles.
    graine = np.random.default_rng(7)
    morceaux, t = [], 0
    while t < 240 * F:
        salve = int(graine.uniform(3, 9) * F)
        silence = int(graine.uniform(0.6, 1.6) * F)
        morceaux += [graine.uniform(0.2, 0.9, salve).astype(np.float32), np.zeros(silence, dtype=np.float32)]
        t += salve + silence
    signal = np.concatenate(morceaux)

    marge = int(0.2 * F)

    def vad(sig, _options=None, sampling_rate=16000, **_k):
        # Comme Silero : rien sous une trame (512 échantillons), passages
        # élargis d'une marge de silence de chaque côté, fondus s'ils se touchent.
        actif = np.flatnonzero(np.diff(np.concatenate([[0], (sig != 0).astype(np.int8), [0]])))
        passages: list[dict] = []
        for a, b in zip(actif[::2], actif[1::2]):
            if b - a < 512:
                continue
            a, b = max(0, int(a) - marge), min(sig.size, int(b) + marge)
            if passages and a <= passages[-1]["end"]:
                passages[-1]["end"] = b
            else:
                passages.append({"start": a, "end": b})
        return passages

    class Tube:
        """Pipeline simulé : le texte d'une fenêtre ne dépend que de son audio ; une panne sur demande."""

        def __init__(self, panne_a=None):
            self.appels, self.panne_a = 0, panne_a

        def get_generation_config(self):
            return SimpleNamespace()

        def generate(self, morceau, config, streamer=None):
            self.appels += 1
            if self.panne_a is not None and self.appels == self.panne_a:
                self.panne_a = None
                raise RuntimeError("panne simulée du pilote")
            texte = "fenêtre " + hashlib.sha1(np.ascontiguousarray(morceau).tobytes()).hexdigest()[:10]
            # Le dernier horodatage tombe à la fin de la parole, avant la marge
            # de silence du passage : la jointure d'une reprise est à cheval.
            return SimpleNamespace(texts=[texte], words=[], languages=["<|fr|>"], perf_metrics=None,
                                   chunks=[SimpleNamespace(start_ts=0.0, end_ts=morceau.size / F - 0.2, text=texte)])

    import faster_whisper.vad as fw_vad

    vrai_vad = fw_vad.get_speech_timestamps
    simule = "openvino_genai" not in sys.modules and __import__("importlib").util.find_spec("openvino_genai") is None
    if simule:
        sys.modules["openvino_genai"] = SimpleNamespace(
            __version__="simulé", StreamingStatus=SimpleNamespace(RUNNING=0, CANCEL=1))
    fw_vad.get_speech_timestamps = vad
    try:
        mat = materiel.detecter_au_demarrage()[0]

        def instance(tube):
            ov = mo.MoteurOpenVINO(mat, "CPU")
            ov._pipeline, ov._mots, ov._nom_modele = tube, False, "turbo"
            return ov

        duree = signal.size / F
        reglages = {"faisceau_openvino": 1}
        complet, _d = instance(Tube()).transcrire(signal, duree, "fr", reglages)
        verifier(len(complet) >= 8, f"passage complet : {len(complet)} fenêtres de 30 s au plus")

        def reprendre(deja):
            decalage = deja[-1].fin
            debut = int(decalage * F)
            suite, _d = instance(Tube()).transcrire(signal[debut:], duree, "fr", reglages, decalage=decalage,
                                                    origine=signal)
            return deja + suite, suite

        k = len(complet) * 43 // 100
        total, _s = reprendre(complet[:k])
        verifier([s.texte for s in total] == [s.texte for s in complet]
                 and [(round(s.debut, 3), round(s.fin, 3)) for s in total]
                 == [(round(s.debut, 3), round(s.fin, 3)) for s in complet],
                 "coupure entre deux fenêtres (jointure à la fin de la parole, avant la marge de silence) : la "
                 "reprise donne exactement le passage complet, texte et heures")
        # Coupure au milieu d'une fenêtre (segments d'une fenêtre écrits en partie) :
        # la jointure est n'importe où, chaque échantillon d'après repasse une fois.
        for position in (k * 3 + 0.37, duree * 0.43, duree * 0.71 + 0.11):
            debut = int(position * F)
            fenetres = mo.fenetres_reprise(signal, debut)
            couverts = np.zeros(signal.size, dtype=np.int8)
            for fenetre in fenetres:
                for p in fenetre:
                    couverts[p["start"] + debut:p["end"] + debut] += 1
            parole = signal != 0
            verifier(not couverts[:debut].any() and (couverts[debut:] <= 1).all()
                     and (couverts[debut + 512:][parole[debut + 512:]] == 1).all(),
                     f"jointure à {position:.2f} s : rien d'avant rejoué, toute la parole d'après une fois")
            entieres = [f for f in mo.decouper(signal) if f[0]["start"] >= debut]
            verifier(entieres and [[(p["start"] + debut, p["end"] + debut) for p in f] for f in fenetres[-len(entieres):]]
                     == [[(p["start"], p["end"]) for p in f] for f in entieres],
                     f"jointure à {position:.2f} s : les fenêtres suivantes sont celles du passage complet")
        # Signal qui n'est pas la fin de l'entier (incohérence) : découpage d'avant, rien de faux.
        autre = np.ascontiguousarray(signal[1000:][::-1])
        segs, _d = instance(Tube()).transcrire(autre, duree, "fr", reglages, decalage=1.0, origine=signal)
        verifier(len(segs) >= 1, "signal qui n'est pas la fin de l'entier : découpé seul, comme avant")
        # Rejeu après une panne en cours de route (moteur avec repli) : même texte que sans panne.
        repli = mo.MoteurAvecRepli(mat, "CPU")
        repli._ov = repli._actif = instance(Tube(panne_a=k + 1))
        repli._rouvrir = lambda: None
        repli.PAUSE_RECREATION_S = 0
        vus = []
        segs, details = repli.transcrire(signal, duree, "fr", reglages, sur_segment=vus.append)
        verifier(details.get("rejeux_openvino") == 1 and [s.texte for s in segs] == [s.texte for s in complet]
                 and len(vus) == len(complet),
                 "panne d'OpenVINO en cours de route : le rejeu retrouve les mêmes fenêtres, même texte, "
                 "chaque segment sauvegardé une fois", str(details.get("rejeux_openvino")))
        # Reprise passée par le moteur avec repli (chemin de l'application).
        repli = mo.MoteurAvecRepli(mat, "CPU")
        repli._ov = repli._actif = instance(Tube())
        deja = complet[:k]
        suite, _d = repli.transcrire(signal[int(deja[-1].fin * F):], duree, "fr", reglages,
                                     decalage=deja[-1].fin, origine=signal)
        verifier([s.texte for s in deja + suite] == [s.texte for s in complet],
                 "reprise par le moteur avec repli : même texte que le passage complet")
    finally:
        fw_vad.get_speech_timestamps = vrai_vad
        if simule:
            sys.modules.pop("openvino_genai", None)


def essai_reprise_reconstruite(base: Path) -> None:
    """16/11 (point 3) : un état vidé par une coupure ne fait plus perdre la reprise."""
    import json

    from app import chemins, reprise
    from app.moteur import Segment

    titre("Reprise : état perdu par une coupure, reconstruit avec la demande de départ")
    racine = chemins.RACINE
    chemins.RACINE = base / "reprises-reconstruites"
    try:
        source = base / "reunion-coupee.ogg"
        source.write_bytes(b"audio")
        rep = chemins.RACINE / "reprises"
        resultats = {}
        for cas, abimer in (("état vidé (0 octet)", lambda f: f.write_bytes(b"")),
                            ("état rempli de zéros", lambda f: f.write_bytes(b"\x00" * 300)),
                            ("état disparu", lambda f: f.unlink())):
            s = reprise.Session("coupure0000001", active=True)
            s.ouvrir(source, "tiny", 60.0, sortie=str(base / "sorties-coupure"),
                     demande={"formats": {"txt": True, "srt": True}, "langue": "fr"}, nouvelle=True)
            s.ajouter(Segment(debut=0.0, fin=4.0, texte="Un.", mots=[]), 1.0)
            s.ajouter(Segment(debut=4.0, fin=9.5, texte="Deux.", mots=[]), 2.0)
            s.fermer()
            abimer(rep / "coupure0000001.etat")
            trouvees = {r["cle"]: r for r in reprise.lister()}
            etat = reprise.lire_etat("coupure0000001") or {}
            orphelines = [o for o in reprise.orphelines() if o.get("cle") == "coupure0000001"]
            resultats[cas] = (trouvees.get("coupure0000001", {}).get("nb_segments"),
                              trouvees.get("coupure0000001", {}).get("position"),
                              etat.get("demande", {}).get("formats", {}).get("srt"), etat.get("sortie"), orphelines)
            verifier(resultats[cas][:3] == (2, 9.5, True) and resultats[cas][3] and not orphelines,
                     f"{cas} : la reprise est toujours proposée, au segment près, avec toute sa demande",
                     str(resultats[cas]))
            reprise.oublier("coupure0000001")
        verifier(not list(rep.glob("coupure0000001*")), "fin ou abandon : la demande de départ part avec le reste",
                 str(sorted(f.name for f in rep.glob("coupure0000001*"))))
        # Écrite durablement : à côté, vidée sur le disque, puis renommée.
        appels = []
        fsync_reel = os.fsync
        os.fsync = lambda d: (appels.append(d), fsync_reel(d))[1]
        try:
            s = reprise.Session("coupure0000002", active=True)
            s.ouvrir(source, "tiny", 60.0, nouvelle=True)
            s.fermer()
        finally:
            os.fsync = fsync_reel
        verifier(appels and (rep / "coupure0000002.depart").is_file() and not list(rep.glob("*.tmp")),
                 "demande de départ vidée sur le disque (fsync) avant d'être renommée")
        reprise.oublier("coupure0000002")
        # Une reprise d'avant (sans demande de départ) dont l'état est perdu : signalée, rien d'effacé d'office.
        (rep / "ancienne000001.etat").write_bytes(b"")
        (rep / "ancienne000001.jsonl").write_text(json.dumps({"d": 0, "f": 1, "t": "Texte", "m": []}) + "\n",
                                                  encoding="utf-8")
        trouvee = next((o for o in reprise.orphelines() if o.get("cle") == "ancienne000001"), {})
        verifier(trouvee.get("raison") == "etat_illisible" and trouvee.get("segments") == 1
                 and trouvee.get("segments_fichier", "").endswith("ancienne000001.jsonl") and not trouvee.get("purgeable"),
                 "sans demande de départ : segments signalés avec leur fichier, gardés par la purge", str(trouvee))
        reprise.purger()
        verifier((rep / "ancienne000001.jsonl").is_file(), "purge : les segments gardés restent")
    finally:
        chemins.RACINE = racine


def essai_migration_provisoire(base: Path) -> None:
    """Revue du 15/11 (M8) : le journal de migration s'écrit sous un nom provisoire propre à chaque écriture."""
    from app import inventaire, migration

    titre("Migration : nom provisoire unique pour son journal")
    dossier = base / "migration-provisoire"
    dossier.mkdir()
    vus = []
    remplacer = os.replace

    def noter(source, cible):
        vus.append(Path(source).name)
        return remplacer(source, cible)

    os.replace = noter
    try:
        migration._ecrire_journal(dossier, {"etat": "en_cours"})
        migration._ecrire_journal(dossier, {"etat": "terminee"})
    finally:
        os.replace = remplacer
    verifier(len(set(vus)) == 2 and all(str(os.getpid()) in n and n.endswith(".tmp") for n in vus)
             and (dossier / migration.NOM_JOURNAL).is_file() and not list(dossier.glob("*.tmp")),
             "deux écritures, deux noms provisoires (PID et hasard), rien de laissé", str(vus))
    verifier(inventaire._groupe_de(vus[0], False) == "reglages",
             "un provisoire laissé par une coupure est reconnu par l'inventaire")


def essai_relecture_8b5eae8(base: Path) -> None:
    """16/11 (point 6) : régressions et cas limites relevés à la relecture des correctifs du 15/11."""
    import json
    import types

    from app import chemins, cli, reprise, sorties, superviseur, traitement
    from app.moteur import Segment

    titre("Relecture des correctifs du 15/11 : reprises d'un autre modèle, états en retard, noms provisoires")
    racine = chemins.RACINE
    chemins.RACINE = base / "relecture-15-11"
    reels = _environnement_garde()
    try:
        source = base / "relecture.ogg"
        source.write_bytes(b"audio")
        rep = chemins.RACINE / "reprises"

        def reprise_de(modele: str, segments: int = 1) -> str:
            cle = reprise.cle(source, modele)
            s = reprise.Session(cle, active=True)
            s.ouvrir(source, modele, 60.0, nouvelle=True)
            for k in range(segments):
                s.ajouter(Segment(debut=float(k), fin=k + 1.0, texte=f"S{k}", mots=[]), 1.0)
            s.fermer()
            return cle

        muet = types.SimpleNamespace(evenement=lambda *a, **k: None, dire=lambda *a, **k: None,
                                     journal_ui=lambda *a, **k: None)
        # --recommencer : jamais la reprise d'un autre modèle, jamais avant le verrou.
        autre = reprise_de("modele-b")
        trouvee = {"cle": autre, "modele_demande": "modele-b", "modele": "modele-b"}
        element = traitement.Element(identifiant="c1", chemin=str(source), nom=source.name, taille=5)
        cli._reprise_de_transcrire(muet, element, source, "modele-a", trouvee, True)
        meme = reprise_de("modele-a")
        element2 = traitement.Element(identifiant="c2", chemin=str(source), nom=source.name, taille=5)
        cli._reprise_de_transcrire(muet, element2, source, "modele-a", None, True)
        verifier(reprise.a_garder(autre) and reprise.a_garder(meme) and element.recommencer and element2.recommencer,
                 "--recommencer : la reprise d'un autre modèle reste ; la sienne n'est remplacée qu'au départ")
        # File sur le modèle A, reprise rattachée faite avec B : pas poursuivie avec A.
        element3 = traitement.Element(identifiant="c3", chemin=str(source), nom=source.name, taille=5, reprise=autre)
        fausse = types.SimpleNamespace()
        traitement.FileTraitement._rattacher(fausse, element3, {"sauvegarde_progressive": True},
                                             {"reglages": {"modele": "modele-a"}}, muet)
        verifier(element3.reprise == meme and reprise.a_garder(autre),
                 "reprise d'un autre modèle rattachée : laissée telle quelle, celle du modèle de la file poursuivie",
                 element3.reprise)
        reprise.oublier(meme)
        # Plantages répétés, état en retard sur ses segments : rien d'effacé.
        retard = reprise_de("modele-c", segments=2)
        etat = json.loads((rep / f"{retard}.etat").read_text(encoding="utf-8"))
        etat.update({"position": 0.0, "nb_segments": 0})
        (rep / f"{retard}.etat").write_text(json.dumps(etat), encoding="utf-8")
        element4 = traitement.Element(identifiant="c4", chemin=str(source), nom=source.name, taille=5)
        rappels = types.SimpleNamespace(etat=lambda *a, **k: None, journal_ui=lambda *a, **k: None,
                                        termine=lambda *a, **k: None)
        superviseur.Superviseur._echec_definitif(None, element4, rappels, retard, "essai")
        verifier((rep / f"{retard}.jsonl").is_file() and element4.reprise == retard,
                 "deux plantages, état en retard sur 2 segments valides : reprise gardée et proposée",
                 str(sorted(f.name for f in rep.glob(f"{retard}*"))))
        # Nom provisoire des sorties : court, quel que soit le nom final.
        vus = []
        remplacer = os.replace
        os.replace = lambda a, b: (vus.append(Path(a).name), remplacer(a, b))[1]
        try:
            (base / "sorties-longues").mkdir()
            sorties.ecrire_sur_disque(base / "sorties-longues" / ("x" * 150 + ".txt"), "texte")
        finally:
            os.replace = remplacer
        verifier(vus and len(vus[0]) <= 24, "sortie au nom long : nom provisoire court (limite des 260 caractères)",
                 str(vus))
        # Le dossier à notre nom qui a déjà des données sans réglages : il sert.
        nouveau = base / "en-service" / "Scribouille"
        (nouveau / "reprises").mkdir(parents=True)
        verifier(chemins._nouveau_deja_en_service(nouveau),
                 "Scribouille avec nos données mais sans config.json : tenu pour en service")
        # Dossier partagé : nos états .json d'avant le 15/11 mis à l'abri de la purge de la 2.x.
        local = base / "abri-local"
        donnees = local / "WhiScribe"
        (donnees / "reprises").mkdir(parents=True)
        chemins.RACINE = donnees
        os.environ["LOCALAPPDATA"] = str(local)
        os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = json.dumps([{"ruche": "HKCU", "version": "2.3.3",
                                                                 "dossier": str(local / "P" / "WhiScribe")}])
        (donnees / "reprises" / "1111111111111111.json").write_text(json.dumps(
            {"auteur": reprise.AUTEUR, "source": str(source), "modele": "tiny", "nb_segments": 1}), encoding="utf-8")
        (donnees / "reprises" / "2222222222222222.json").write_text(json.dumps(
            {"source": str(source), "modele": "tiny", "nb_segments": 1}), encoding="utf-8")
        faits = reprise._abriter_anciens_etats()
        verifier(faits == 1 and (donnees / "reprises" / "1111111111111111.etat").is_file()
                 and (donnees / "reprises" / "2222222222222222.json").is_file(),
                 "dossier partagé : nos états .json renommés en .etat, ceux de la 2.x jamais touchés")
        # Simulation du registre : jamais sur un autre nom du « vrai » LOCALAPPDATA
        # (ici un dossier d'essai tenu pour le vrai ; le vrai n'est jamais visé).
        faux_reel = base / "faux-reel-local"
        faux_reel.mkdir()
        alias = base / "alias-local"
        lire_reel = chemins._localappdata_reel
        try:
            chemins._localappdata_reel = lambda: str(faux_reel)
            if sys.platform == "win32":
                subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(faux_reel)], capture_output=True,
                               creationflags=SANS_FENETRE)
            if alias.is_dir():
                os.environ["LOCALAPPDATA"] = str(alias)
                permis = chemins._essai_registre_permis()
                os.environ["LOCALAPPDATA"] = str(local)
                verifier(not permis and chemins._essai_registre_permis(),
                         "LOCALAPPDATA par une jonction vers le vrai : simulation du registre refusée")
            else:
                print("  (jonction impossible ici : contrôle de l'alias sauté)")
        finally:
            chemins._localappdata_reel = lire_reel
            if alias.is_dir():
                os.rmdir(alias)   # la jonction seule
    finally:
        chemins.RACINE = racine
        _rendre_environnement(reels)


def essai_verrou_et_ecritures(base: Path) -> None:
    """Revue du 15/11 (S7 à S9, M1 à M3, M5, M6) : verrou, sorties, réglages, petits fichiers."""
    import json
    import os
    import subprocess
    import time

    from app import calibration, chemins, config as config_module, instance, materiel, moteur, reglage_machine
    from app import sorties, surveillance, temoin_puce
    from app.moteur import Segment

    titre("Verrou, sorties sur le disque, réglages illisibles, petits fichiers")
    racine, fichier_config = chemins.RACINE, chemins.FICHIER_CONFIG
    chemins.RACINE = base / "ecritures"
    chemins.RACINE.mkdir()
    try:
        # S7 : PID réattribué après un redémarrage.
        source = base / "verrou.wav"
        source.write_bytes(b"x")
        verrou = instance._fichier_verrou(source)
        verrou.parent.mkdir(parents=True, exist_ok=True)
        import psutil

        demarrage = psutil.boot_time()
        autre = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=SANS_FENETRE)
        try:
            # Verrou d'avant ce format (PID seul), posé avant le dernier
            # démarrage : son PID est aujourd'hui celui d'un autre programme.
            verrou.write_text(str(autre.pid), encoding="ascii")
            os.utime(verrou, (demarrage - 60, demarrage - 60))
            ancien_format = instance.prendre_fichier(source)
            instance.rendre_fichier(source)
            verrou.write_text(f"{autre.pid} 1000.000", encoding="ascii")
            repris = instance.prendre_fichier(source)
            contenu = verrou.read_text(encoding="ascii").split()
        finally:
            autre.kill()
            autre.wait()
        verifier(ancien_format == 0, "verrou d'avant ce format posé avant le démarrage du système : mort, repris",
                 str(ancien_format))
        verifier(repris == 0 and int(contenu[0]) == os.getpid() and len(contenu) == 2 and float(contenu[1]) > 0,
                 "PID réattribué (heure de création différente) : verrou mort, repris, avec l'heure de création",
                 f"{repris} {contenu}")
        instance.rendre_fichier(source)
        verrou.write_text("", encoding="ascii")
        verifier(instance.prendre_fichier(source) == -1,
                 "verrou vide tout juste créé (concurrent en train d'écrire) : tenu pour vivant")
        os.utime(verrou, (time.time() - 60, time.time() - 60))
        verifier(instance.prendre_fichier(source) == 0, "verrou vide ancien : repris")
        instance.rendre_fichier(source)
        verifier(not verrou.exists() and not list(verrou.parent.glob("*.tmp")),
                 "verrou rendu, aucun fichier provisoire laissé")

        # S8 : sorties vidées sur le disque avant d'effacer la sauvegarde.
        vides = []
        vrai_fsync = os.fsync
        os.fsync = lambda fd: (vides.append(fd), vrai_fsync(fd))
        (base / "reunion.ogg").write_bytes(b"audio")
        try:
            produits = sorties.ecrire_tout(chemins.RACINE / "sorties", base / "reunion.ogg",
                                           [Segment(debut=0.0, fin=1.0, texte="Bonjour.", mots=[])],
                                           {"modele": "tiny"}, {"txt": True, "srt": True, "vtt": True})
        finally:
            os.fsync = vrai_fsync
        verifier(len(produits) == 3 and len(vides) >= 4
                 and not list((chemins.RACINE / "sorties").glob("*scribouille-tmp"))
                 and not list((chemins.RACINE / "sorties").glob("~scb*.tmp")),
                 "sorties (texte, compagnon, sous-titres) vidées sur le disque puis renommées",
                 f"{len(produits)} sorties, {len(vides)} fsync")
        traitement_source = (RACINE / "app" / "traitement.py").read_text(encoding="utf-8")
        fin_normale = traitement_source.find("# Le fichier est écrit : la reprise n'a plus lieu d'être.")
        verifier(0 < traitement_source.find("produits = sorties.ecrire_tout(") < fin_normale
                 < traitement_source.find("session.effacer()", fin_normale),
                 "la sauvegarde progressive n'est effacée qu'après l'écriture des sorties")

        # S9 : une lecture ratée ne devient jamais une remise à zéro écrite.
        chemins.FICHIER_CONFIG = chemins.RACINE / "config.json"
        reglages = {**config_module.DEFAUTS, "preset": "rapide", "dossier_sortie": "D:\\Reunions"}
        chemins.FICHIER_CONFIG.write_text(json.dumps(reglages), encoding="utf-8")
        texte_reel = chemins.FICHIER_CONFIG.read_text(encoding="utf-8")
        chemins.FICHIER_CONFIG.rename(chemins.RACINE / "config-cache.json")
        chemins.FICHIER_CONFIG.mkdir()   # lecture refusée par le système, comme un verrou d'antivirus
        lu = config_module.charger()
        chemins.FICHIER_CONFIG.rmdir()
        (chemins.RACINE / "config-cache.json").rename(chemins.FICHIER_CONFIG)   # le verrou est levé
        ecrit = config_module.sauver({**lu, "zoom": 1.2})
        verifier(lu["dossier_sortie"] != "D:\\Reunions" and not ecrit
                 and chemins.FICHIER_CONFIG.read_text(encoding="utf-8") == texte_reel,
                 "réglages illisibles à la lecture : rien d'écrit par-dessus, même une fois lisibles")
        chemins.FICHIER_CONFIG.write_text("{ abîmé", encoding="utf-8")
        lu = config_module.charger()
        ecrit = config_module.sauver({**lu, "zoom": 1.3})
        gardes = list(chemins.RACINE.glob("config.json.illisible-*"))
        verifier(ecrit and len(gardes) == 1 and gardes[0].read_text(encoding="utf-8") == "{ abîmé"
                 and json.loads(chemins.FICHIER_CONFIG.read_text(encoding="utf-8"))["zoom"] == 1.3,
                 "réglages abîmés : gardés de côté sous un autre nom avant d'être remplacés")
        source_config = (RACINE / "app" / "config.py").read_text(encoding="utf-8")
        verifier("os.getpid()" in source_config and "secrets.token_hex" in source_config
                 and not list(chemins.RACINE.glob("config.json*.tmp")),
                 "fichier provisoire des réglages à nom unique, jamais laissé")

        # M1 : le travailleur de détection garde le dossier de données du parent.
        vus = {}

        class Fini:
            returncode, stderr = 0, b""

        vrai_run = materiel.subprocess.run
        materiel.subprocess.run = lambda *a, **k: (vus.update(k.get("env") or {}), Fini())[1]
        try:
            materiel.rafraichir(5)
        finally:
            materiel.subprocess.run = vrai_run
        verifier(vus.get("SCRIBOUILLE_DONNEES") == str(chemins.RACINE),
                 "détection du matériel en arrière-plan : même dossier de données (aucune reprise de l'ancien)")
        # M2 : SCRIBOUILLE_DONNEES relatif rendu absolu.
        p = subprocess.run([sys.executable, "-c", "from app import chemins; print(chemins.RACINE)"],
                           cwd=str(RACINE), capture_output=True, text=True, timeout=60, creationflags=SANS_FENETRE,
                           env={**os.environ, "SCRIBOUILLE_DONNEES": "donnees-relatives", "PYTHONPATH": str(RACINE)})
        verifier(p.stdout.strip() == str(RACINE / "donnees-relatives"),
                 "SCRIBOUILLE_DONNEES relatif : rendu absolu (moteur et fenêtre au même endroit)", p.stdout + p.stderr)
        # M3 : un verdict de plantage n'est pas écrasé par une ouverture.
        temoin_puce.noter_fin_moteur("GPU", 0xC0000005, "chargement")
        marque = temoin_puce.poser_chargement("GPU")
        pendant = temoin_puce.etat()["etat"]
        temoin_puce.lever_chargement(marque)
        verifier(pendant == "suspendue" and temoin_puce.etat()["etat"] == "suspendue",
                 "ouverture sur la puce pendant une suspension : le verdict de plantage reste")
        temoin_puce.lever("essai")
        # Repli après plantage : la ligne de chargement dit « sur le processeur ».
        annonce = getattr(moteur, "annonce_chargement", lambda modele: "")
        ecartee = reglage_machine.PUCE_ECARTEE
        reglage_machine.PUCE_ECARTEE = True
        try:
            ligne_repli = annonce("large-v3-turbo")
        finally:
            reglage_machine.PUCE_ECARTEE = ecartee
        verifier("processeur" in ligne_repli and "Chargement" in annonce("large-v3-turbo")
                 and "processeur" not in annonce("large-v3-turbo"),
                 "moteur relancé sans la puce : « Chargement du modèle ... sur le processeur »", ligne_repli)
        # M5 et M6 : écriture à côté puis renommage.
        remplaces = []
        vrai_replace = os.replace
        os.replace = lambda a, b: (remplaces.append(Path(b).name), vrai_replace(a, b))
        try:
            calibration._ecrire({"version": calibration.VERSION_FICHIER, "mesures": {}})
            surveillance.ecrire_memoire({"x|1|2": 1.0})
        finally:
            os.replace = vrai_replace
        verifier({"calibration.json", "surveillance-vus.json"} <= set(remplaces)
                 and not list(chemins.RACINE.glob("*.tmp")),
                 "mesures de durée et mémoire du dossier surveillé : écrites à côté puis renommées", str(remplaces))
        # M6 : un fichier surveillé n'est « vu » qu'une fois transcrit.
        guette = base / "guette"
        guette.mkdir()
        (guette / "dictaphone.mp3").write_bytes(b"x" * 100)
        surveillance.ecrire_memoire({})
        livres = []
        s = surveillance.Surveillant(sur_nouveaux=livres.extend)
        s.dossier, s.actif = str(guette), True
        s._passage()
        s._passage()
        s._passage()
        avant = surveillance.charger_memoire()
        s.marquer_vu(livres[0] if livres else "")
        verifier(len(livres) == 1 and not avant and len(surveillance.charger_memoire()) == 1,
                 "dossier surveillé : livré une fois, « vu » sur le disque seulement après la transcription",
                 f"{livres} {avant}")
    finally:
        chemins.RACINE, chemins.FICHIER_CONFIG = racine, fichier_config


def essai_documentation_livree() -> None:
    """Le paquet livre la documentation à côté de l'exécutable, et chacun de ses liens y mène."""
    import re

    titre("Documentation livrée : à côté de l'exécutable, aucun lien cassé")
    recette = (RACINE / "packaging" / "scribouille.spec").read_text(encoding="utf-8")
    a_cote = re.search(r"LIVRES_A_COTE = \(([^)]*)\)", recette)
    docs = re.search(r"DOCS_LIVRES = \(([^)]*)\)", recette)
    livres = set(re.findall(r'"([^"]+)"', a_cote.group(1))) if a_cote else set()
    livres |= {f"docs/{n}" for n in re.findall(r'"([^"]+)"', docs.group(1))} if docs else set()
    verifier({"README.md", "README.fr.md", "docs/guide.md", "docs/ligne-de-commande.md"} <= livres,
             "README et guides copiés à côté de l'exécutable", str(sorted(livres)))
    casses = []
    for nom in sorted(n for n in livres if n.endswith(".md")):
        texte = (RACINE / nom).read_text(encoding="utf-8")
        for lien in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", texte):
            if lien.startswith(("http:", "https:", "mailto:", "../../")):
                continue
            cible = (Path(nom).parent / lien).as_posix()
            cible = str(Path(cible)).replace("\\", "/")
            normal = []
            for morceau in cible.split("/"):
                if morceau == "..":
                    normal = normal[:-1]
                elif morceau not in ("", "."):
                    normal.append(morceau)
            cible = "/".join(normal)
            if cible not in livres:
                casses.append(f"{nom} -> {lien}")
    verifier(not casses, "chaque lien relatif des documents livrés mène à un document livré", "; ".join(casses))


def essai_messages() -> None:
    """Messages : pas de nom interne, pas de redite, pluriels justes."""
    from app import journal, langues as langues_module

    titre("Messages : sans nom interne ni redite, pluriels accordés")
    incident = journal.formater_incident(journal.ErreurLisible("Déjà en cours ailleurs", "Un autre processus le transcrit."))
    verifier("ErreurLisible" not in incident["detail"], "détail d'un incident rédigé : sans nom interne", incident["detail"])
    message = langues_module.t("audio.illisible.msg", nom="faux.mp3", journal="2026-11-12.log")
    titre_audio = langues_module.t("audio.illisible.titre")
    verifier("illisible" not in message.lower() and "/" not in message and "faux.mp3" in message,
             "fichier illisible : le message ne redit pas le titre, sans chemin à barres obliques",
             f"{titre_audio} / {message}")
    verifier(langues_module.tn("voc2.exporte", 1) == "1 terme actif exporté."
             and langues_module.tn("voc2.exporte", 3) == "3 termes actifs exportés.", "« 1 terme actif exporté »")


def principal() -> int:
    print(f"Vérification du socle de Scribouille\n{'=' * 40}")
    with tempfile.TemporaryDirectory(prefix="scribouille-socle-") as brut:
        base = Path(brut)
        essai_decodage(base)
        essai_demarrage(base)
        essai_modele_garde(base)
        essai_reglage_propose()
        essai_repetitions()
        essai_migration(base)
        essai_instances(base)
        for essai in (essai_version_2x, essai_reprise_tolerante, essai_verrou_et_ecritures, essai_classement_2x,
                      essai_cache_openvino, essai_cache_plafond_tenu, essai_ecritures_identiques,
                      essai_reprise_fenetres, essai_reprise_reconstruite, essai_migration_provisoire,
                      essai_relecture_8b5eae8):
            # Une section qui lève est un échec, et les suivantes passent quand même.
            try:
                essai(base)
            except Exception as exc:  # noqa: BLE001
                verifier(False, f"{essai.__name__} : levé", f"{type(exc).__name__}: {exc}")
    essai_documentation_livree()
    essai_messages()
    print(f"\n{'=' * 40}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
