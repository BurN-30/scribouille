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


def principal() -> int:
    print(f"Vérification du socle de Scribouille\n{'=' * 40}")
    with tempfile.TemporaryDirectory(prefix="scribouille-socle-") as brut:
        base = Path(brut)
        essai_decodage(base)
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
