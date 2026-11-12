"""
Vérification du socle allégé de la version 2.5, sans fenêtre ni modèle.

Décodage par PyAV (une seule FFmpeg), démarrage sans détection bloquante,
modèle gardé d'un fichier à l'autre, garde-fou des répétitions, dossier de
données à notre nom. Tout se passe dans un dossier temporaire : la
configuration et les données de l'utilisateur ne sont jamais touchées.

    .venv\\Scripts\\python outils\\verifier_socle.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
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
                            capture_output=True, text=True, timeout=120)
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


def principal() -> int:
    print(f"Vérification du socle de Scribouille\n{'=' * 40}")
    with tempfile.TemporaryDirectory(prefix="scribouille-socle-") as brut:
        base = Path(brut)
        essai_decodage(base)
        essai_demarrage(base)
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
