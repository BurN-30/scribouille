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
        verifier(instance.prendre_fichier(source) == 0 and verrou.read_text(encoding="ascii") == str(os.getpid()),
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
            config_module.charger()
        finally:
            chemins.FICHIER_CONFIG = fichier_config
        passerelle = (RACINE / "transcriber.pyw").read_text(encoding="utf-8")
        verifier(garde == "en" and langues_module.courante() == "fr"
                 and "disque = config_module.charger(definir_langue=False)" in passerelle,
                 "changer de langue : la fenêtre qui relit le disque ne remet pas l'ancienne langue",
                 f"{garde} {langues_module.courante()}")
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
