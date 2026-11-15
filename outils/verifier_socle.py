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
                   interrompu=None, decalage=0.0, sur_segment=None):
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
                 and not list((chemins.RACINE / "sorties").glob("*scribouille-tmp")),
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
        for essai in (essai_version_2x, essai_reprise_tolerante, essai_verrou_et_ecritures):
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
