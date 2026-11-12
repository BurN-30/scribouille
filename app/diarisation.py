"""
Séparation des locuteurs (diarisation) via pyannote.audio.

Toujours exécutée APRÈS la transcription, une fois le modèle Whisper libéré :
les deux pics de mémoire se suivent au lieu de s'additionner, ce qui permet de
tenir dans 16 Go avec large-v3.

pyannote est optionnel. Sans torch installé, sans jeton Hugging Face, ou si les
conditions du modèle n'ont pas été acceptées, la transcription se termine
normalement, simplement sans étiquettes de locuteur.
"""

from __future__ import annotations

import gc
import inspect
import os
from typing import TYPE_CHECKING, Callable

from . import URL_PROJET as _URL_DEPOT
from . import chemins, journal, langues
from .journal import ErreurLisible

if TYPE_CHECKING:
    import numpy as np

# Dépôts essayés dans l'ordre. « community-1 » (pyannote.audio 4, licence
# CC-BY-4.0, septembre 2025) passe en tête : sa fiche le donne meilleur que 3.1
# sur presque tous les jeux de test (AMI IHM : 17,0 % d'erreur de diarisation
# contre 18,8 % ; AliMeeting : 20,3 contre 24,5), il tient en un seul dépôt et
# fournit la sortie « exclusive » faite pour l'alignement avec une transcription.
# 3.1 reste en second, pour qui n'a accepté que ses conditions.
DEPOTS = (
    "pyannote/speaker-diarization-community-1",
    "pyannote/speaker-diarization-3.1",
)

URL_CONDITIONS = "https://huggingface.co/pyannote/speaker-diarization-community-1"
URL_JETON = "https://huggingface.co/settings/tokens"

# Le dépôt du projet, cité quand la fonction n'est pas incluse dans la version
# installée. L'ancre pointe sur la section du README qui décrit la voie source.
URL_PROJET = (
    f"{_URL_DEPOT}#installation-depuis-les-sources-"
    "développeurs-et-séparation-des-locuteurs"
)


def torch_present() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("torch") is not None
    except Exception:
        return False


def pyannote_present() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("pyannote.audio") is not None
    except Exception:
        return False


def disponible() -> bool:
    return torch_present() and pyannote_present()


def effective(demandee: bool) -> bool:
    """
    La séparation tournera-t-elle vraiment ? Demandée (cochée par défaut) ET
    installée. C'est ce qui compte pour les annonces de durée et la
    progression : une option cochée mais absente ne coûte rien.
    """
    return bool(demandee) and disponible()


def indisponibilite() -> str:
    """Phrase expliquant pourquoi la diarisation ne peut pas tourner, ou chaîne vide."""
    if disponible():
        return ""

    if chemins.EST_GELE:
        # La version installée ne contient pas PyTorch : il pèse à lui seul
        # plusieurs gigaoctets, ce qui ferait passer le programme d'installation
        # de 200 Mo à bien davantage pour une fonction facultative. Depuis la
        # version 2.3.0, l'application sait l'installer elle-même : voir
        # app/extensions.py, et le bouton du panneau « Locuteurs ».
        return langues.t("diar.indispo.installee")

    if not torch_present():
        return langues.t("diar.indispo.torch")
    return langues.t("diar.indispo.pyannote")


def jeton() -> str:
    """
    Jeton Hugging Face, cherché dans l'ordre : variable d'environnement, fichier local.

    Le fichier `jeton_hf.txt` est ignoré par Git : aucun secret ne part dans le dépôt.
    """
    for variable in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_TOKEN"):
        valeur = (os.environ.get(variable) or "").strip()
        if valeur:
            return valeur
    try:
        return chemins.FICHIER_JETON_HF.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def enregistrer_jeton(valeur: str) -> None:
    valeur = (valeur or "").strip()
    if not valeur:
        chemins.FICHIER_JETON_HF.unlink(missing_ok=True)
        journal.info("Jeton Hugging Face effacé")
        return
    chemins.FICHIER_JETON_HF.write_text(valeur + "\n", encoding="utf-8")
    journal.info("Jeton Hugging Face enregistré (%s caractères)", len(valeur))


def jeton_present() -> bool:
    return bool(jeton())


def _charger_pipeline(cle: str, signaler: Callable[[str, str], None] | None):
    from pyannote.audio import Pipeline

    # pyannote 4.x attend `token`, les versions 3.x attendaient `use_auth_token`.
    parametres = inspect.signature(Pipeline.from_pretrained).parameters
    nom_argument = "token" if "token" in parametres else "use_auth_token"

    dernier: Exception | None = None
    for depot in DEPOTS:
        try:
            if signaler:
                signaler("info", langues.t(
                    "diar.chargement", depot=depot.split("/")[-1]))
            with journal.SortieMuette("chargement pyannote"):
                pipeline = Pipeline.from_pretrained(
                    depot,
                    cache_dir=str(chemins.DOSSIER_MODELES),
                    **{nom_argument: cle},
                )
            if pipeline is not None:
                journal.info("Diarisation : dépôt %s chargé", depot)
                return pipeline
            dernier = ErreurLisible(
                langues.t("diar.inaccessible.titre"),
                langues.t("diar.inaccessible.depot", depot=depot),
            )
        except Exception as exc:
            journal.attention("Dépôt %s indisponible : %s", depot, exc)
            dernier = exc

    if dernier is not None:
        raise dernier
    raise ErreurLisible(
        langues.t("diar.inaccessible.titre"),
        langues.t("diar.inaccessible.aucun"),
    )


def annotation_de(sortie):
    """
    Tours de parole tirés de ce que rend le pipeline, quelle que soit sa version.

    pyannote.audio 3.x rend directement une `Annotation`. La 4.x rend un objet
    `DiarizeOutput` (sauf en mode « legacy », qu'aucun des deux dépôts n'active),
    sans méthode `itertracks` : l'appel échouait, l'incident était rattrapé, et
    la transcription se terminait sans le moindre locuteur. On prend alors la
    version EXCLUSIVE, sans chevauchement, que pyannote recommande précisément
    pour la rapprocher des horodatages d'une transcription.
    """
    for attribut in ("exclusive_speaker_diarization", "speaker_diarization"):
        annotation = getattr(sortie, attribut, None)
        if annotation is not None:
            return annotation
    return sortie


def diariser(
    signal: np.ndarray,
    frequence: int,
    nb_locuteurs: int = 0,
    signaler: Callable[[str, str], None] | None = None,
    interrompu: Callable[[], bool] | None = None,
) -> list[dict]:
    """
    Renvoie une liste de tours de parole : [{debut, fin, locuteur}].

    Lève une ErreurLisible si la diarisation ne peut pas se faire. L'appelant
    décide alors de poursuivre sans étiquettes, ce qui est le comportement retenu.
    """
    manque = indisponibilite()
    if manque:
        raise ErreurLisible(langues.t("diar.indisponible.titre"), manque)

    cle = jeton()
    if not cle:
        raise ErreurLisible(
            langues.t("diar.jeton_manquant.titre"),
            langues.t("diar.jeton_manquant.msg"),
        )

    import torch

    pipeline = _charger_pipeline(cle, signaler)

    try:
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
            journal.info("Diarisation sur GPU NVIDIA")
    except Exception as exc:
        journal.debug("Bascule GPU impossible pour la diarisation : %s", exc)

    import numpy as np

    forme_onde = torch.from_numpy(np.ascontiguousarray(signal, dtype=np.float32)).unsqueeze(0)
    entree = {"waveform": forme_onde, "sample_rate": frequence}

    arguments: dict = {}
    if nb_locuteurs and nb_locuteurs > 0:
        arguments["num_speakers"] = int(nb_locuteurs)

    if signaler:
        signaler("info", langues.t("diar.analyse"))

    try:
        with journal.SortieMuette("diarisation"):
            sortie = pipeline(entree, **arguments)
    finally:
        del forme_onde, entree
        try:
            del pipeline
        except Exception:
            pass
        gc.collect()

    annotation = annotation_de(sortie)
    tours: list[dict] = []
    etiquettes: dict[str, int] = {}
    for periode, _, etiquette in annotation.itertracks(yield_label=True):
        if etiquette not in etiquettes:
            etiquettes[etiquette] = len(etiquettes) + 1
        tours.append({
            "debut": float(periode.start),
            "fin": float(periode.end),
            "locuteur": langues.t("diar.locuteur", n=etiquettes[etiquette]),
        })

    tours.sort(key=lambda t: t["debut"])
    journal.info("Diarisation terminée : %s tours, %s locuteurs", len(tours), len(etiquettes))
    return tours


def attribuer(segments, tours: list[dict]) -> int:
    """
    Attribue un locuteur à chaque segment, par recouvrement temporel majoritaire.

    Renvoie le nombre de locuteurs distincts effectivement posés. Les segments
    sans recouvrement gardent une étiquette vide plutôt qu'une étiquette fausse.
    """
    if not tours:
        return 0

    poses: set[str] = set()
    for segment in segments:
        meilleur, duree_max = "", 0.0
        for tour in tours:
            if tour["fin"] <= segment.debut:
                continue
            if tour["debut"] >= segment.fin:
                break
            recouvrement = min(segment.fin, tour["fin"]) - max(segment.debut, tour["debut"])
            if recouvrement > duree_max:
                duree_max, meilleur = recouvrement, tour["locuteur"]
        if meilleur:
            segment.locuteur = meilleur
            poses.add(meilleur)

    return len(poses)


def guide() -> dict:
    """Contenu du guide affiché dans l'interface quand le jeton manque."""
    return {
        "url_conditions": URL_CONDITIONS,
        "url_jeton": URL_JETON,
        "url_projet": URL_PROJET,
        "version_installee": chemins.EST_GELE,
        "fichier_jeton": str(chemins.FICHIER_JETON_HF),
        "etapes": [
            langues.t("diar.guide.etape1"),
            langues.t("diar.guide.etape2"),
            langues.t("diar.guide.etape3"),
        ],
    }
