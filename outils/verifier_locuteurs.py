"""
Essai de bout en bout de la séparation des locuteurs, avec un vrai jeton.

Transcrit l'extrait du banc d'essai (cinq phrases lues par des voix différentes,
jeu FLEURS), puis sépare les locuteurs avec pyannote, comme le fait la file de
traitement : modèle de transcription libéré d'abord, tours de parole ensuite,
attribution aux segments. Dit quel dépôt pyannote a servi, combien de voix ont
été trouvées, et combien de segments ont reçu une étiquette.

Le jeton est lu dans un FICHIER désigné en argument, jamais affiché ni écrit
ailleurs : il ne passe que par la variable d'environnement de ce processus.

    .venv\\Scripts\\python outils\\verifier_locuteurs.py --jeton-fichier CHEMIN [--modele small]

Prérequis : la séparation des locuteurs installée (bouton de l'application, ou
« .venv\\Scripts\\python -m app.extensions --installer-locuteurs »), et les
conditions de pyannote/speaker-diarization-community-1 acceptées sur Hugging
Face avec le compte du jeton. Premier passage : environ 30 Mo de modèles pyannote
téléchargés. Sort avec 0 si au moins deux voix sont trouvées et attribuées.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import extensions  # noqa: E402

extensions.activer()

from app import audio, banc, diarisation, journal, langues, materiel, moteur  # noqa: E402


def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    analyseur.add_argument("--jeton-fichier", required=True,
                           help="fichier texte contenant le jeton Hugging Face (hf_...)")
    analyseur.add_argument("--modele", default="small",
                           help="modèle de transcription, small par défaut pour aller vite")
    options = analyseur.parse_args()
    langues.definir("fr")
    journal.demarrer()

    fichier = Path(options.jeton_fichier).expanduser()
    try:
        valeur = fichier.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"ECHEC  jeton illisible ({fichier}) : {exc.strerror or exc}")
        return 2
    if not valeur.startswith("hf_"):
        print("ECHEC  le fichier ne contient pas de jeton Hugging Face (il doit commencer par hf_)")
        return 2
    os.environ["HF_TOKEN"] = valeur
    print("OK     jeton lu (non affiché)")

    manque = diarisation.indisponibilite()
    if manque:
        print(f"ECHEC  séparation des locuteurs non installée : {manque}")
        return 2

    signal = audio.decoder(banc.EXTRAIT)
    duree = signal.size / audio.FREQUENCE
    instance = moteur.MoteurTranscription(materiel.detecter())
    instance.charger(options.modele)
    segments, _ = instance.transcrire(signal, duree, "fr", {"beam_size": 5, "lot": 0, "vad": True})
    instance.liberer()
    print(f"OK     transcription : {len(segments)} segments ({options.modele})")

    messages: list[str] = []
    debut = time.time()
    try:
        tours = diarisation.diariser(signal, audio.FREQUENCE,
                                     signaler=lambda niveau, texte: messages.append(texte))
    except Exception as exc:
        print(f"ECHEC  diarisation : {type(exc).__name__}: {getattr(exc, 'message', exc)}")
        for message in messages:
            print(f"       {message}")
        return 1
    voix = diarisation.attribuer(segments, tours)
    etiquetes = sum(1 for s in segments if s.locuteur)
    # Les dépôts sont essayés dans l'ordre : le dernier annoncé est celui qui a servi.
    depot = next((m for m in reversed(messages) if "speaker-diarization" in m), "")
    print(f"OK     diarisation en {time.time() - debut:.0f} s, {len(tours)} tours de parole"
          + (f" ({depot})" if depot else ""))
    print(f"{'OK   ' if voix >= 2 else 'ECHEC'}  {voix} voix trouvées, "
          f"{etiquetes} segments sur {len(segments)} étiquetés")
    for segment in segments:
        print(f"       [{segment.debut:5.1f} s] {segment.locuteur or '?':<12} {segment.texte[:60]}")
    return 0 if voix >= 2 and etiquetes else 1


if __name__ == "__main__":
    sys.exit(principal())
