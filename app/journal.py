"""
Journalisation.

Deux niveaux volontairement separes :
  - l'interface recoit des messages courts et lisibles, DANS LA LANGUE DE
    L'INTERFACE : `expliquer()` traduit chaque incident via `app/langues.py` ;
  - le fichier de log horodate recoit tout le detail technique, tracebacks
    compris, ET RESTE EN FRANCAIS. Choix assume : ce journal s'adresse au
    mainteneur, pas a l'utilisateur, et sert au diagnostic des incidents
    rapportes au depot. Le traduire n'aiderait personne et rendrait les traces
    d'un poste a l'autre incomparables.

Le nom du fichier de log est toujours cite dans le message d'erreur affiche,
pour que le diagnostic tienne en un clic.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

from . import chemins

_logger: logging.Logger | None = None
_fichier_courant: Path | None = None


def demarrer(niveau: int = logging.INFO) -> Path:
    """Ouvre un fichier de log horodate pour la session et renvoie son chemin."""
    global _logger, _fichier_courant

    if _logger is not None and _fichier_courant is not None:
        return _fichier_courant

    chemins.assurer_dossiers()
    _fichier_courant = chemins.DOSSIER_LOGS / f"{datetime.now():%Y-%m-%d_%H%M%S}.log"

    logger = logging.getLogger("transcripteur")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for ancien in list(logger.handlers):
        logger.removeHandler(ancien)

    handler = logging.FileHandler(_fichier_courant, encoding="utf-8")
    handler.setLevel(niveau)
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", "%H:%M:%S")
    )
    logger.addHandler(handler)

    _logger = logger
    logger.info("Session ouverte, journal : %s", _fichier_courant)
    return _fichier_courant


def sans_fichier() -> None:
    """
    Journal sans fichier, pour les commandes qui ne doivent rien écrire
    (regarder l'espace occupé, effacer) : les lignes sont perdues.
    """
    global _logger, _fichier_courant

    logger = logging.getLogger("transcripteur")
    logger.propagate = False
    for ancien in list(logger.handlers):
        logger.removeHandler(ancien)
    logger.addHandler(logging.NullHandler())
    _logger = logger
    _fichier_courant = Path("aucun-journal.log")


def fichier() -> Path:
    if _fichier_courant is None:
        return demarrer()
    return _fichier_courant


def nom_fichier() -> str:
    return fichier().name


def info(message: str, *args) -> None:
    _ecrire(logging.INFO, message, args)


def attention(message: str, *args) -> None:
    _ecrire(logging.WARNING, message, args)


def erreur(message: str, *args) -> None:
    _ecrire(logging.ERROR, message, args)


def debug(message: str, *args) -> None:
    _ecrire(logging.DEBUG, message, args)


def exception(message: str, exc: BaseException | None = None) -> None:
    """Trace un incident avec son traceback complet dans le fichier."""
    if _logger is None:
        demarrer()
    assert _logger is not None
    detail = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    ) if exc is not None else traceback.format_exc()
    _logger.error("%s\n%s", message, detail)


def _ecrire(niveau: int, message: str, args: tuple) -> None:
    if _logger is None:
        demarrer()
    assert _logger is not None
    _logger.log(niveau, message, *args)


def purger(nb_a_garder: int = 30) -> None:
    """Ne conserve que les N derniers fichiers de log."""
    try:
        fichiers = sorted(
            chemins.DOSSIER_LOGS.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True
        )
        for vieux in fichiers[nb_a_garder:]:
            vieux.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Traduction des incidents techniques en messages lisibles
# ---------------------------------------------------------------------------

class ErreurLisible(Exception):
    """Incident deja formule en francais pour l'utilisateur."""

    def __init__(self, titre: str, message: str, cause: BaseException | None = None):
        super().__init__(f"{titre} : {message}")
        self.titre = titre
        self.message = message
        self.cause = cause


def espace_disque_libre(dossier: str | Path) -> int:
    try:
        return shutil.disk_usage(str(dossier)).free
    except OSError:
        return -1


def expliquer(exc: BaseException, contexte: str = "") -> tuple[str, str]:
    """
    Convertit une exception en couple (titre, message) comprehensible.

    On reste factuel et on indique toujours l'action a mener.
    """
    from . import langues

    if isinstance(exc, ErreurLisible):
        return exc.titre, exc.message

    texte = f"{type(exc).__name__}: {exc}".lower()

    def couple(prefixe: str) -> tuple[str, str]:
        return langues.t(prefixe + ".titre"), langues.t(prefixe + ".msg")

    if isinstance(exc, MemoryError) or "cannot allocate" in texte or "bad_alloc" in texte:
        return couple("err.memoire")

    if "no space left" in texte or "espace insuffisant" in texte or isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return couple("err.disque")

    if "401" in texte or "gated" in texte or "unauthorized" in texte or "authentication" in texte:
        return couple("err.jeton")

    if "connection" in texte or "timed out" in texte or "getaddrinfo" in texte or "max retries" in texte:
        return couple("err.reseau")

    # Poids absents ou tronques : l'application repare d'elle-meme avant d'en
    # arriver la (voir app/moteur.py). Si le message remonte quand meme, c'est
    # que la reparation n'a pas pu se faire, et il faut le dire en francais.
    if "model.bin" in texte or "unable to open file" in texte:
        return couple("err.modele")

    if "cudnn" in texte or "cublas" in texte or "cuda" in texte:
        return couple("err.cuda")

    if isinstance(exc, FileNotFoundError):
        return couple("err.fichier")

    if isinstance(exc, PermissionError):
        return couple("err.acces")

    titre = (
        langues.t("err.inattendu.titre_contexte", contexte=contexte) if contexte
        else langues.t("err.inattendu.titre")
    )
    return titre, langues.t("err.inattendu.msg", journal=nom_fichier())


def formater_incident(exc: BaseException, contexte: str = "") -> dict:
    """Prepare le dictionnaire envoye a l'interface pour un incident."""
    exception(f"Incident ({contexte or 'general'})", exc)
    titre, message = expliquer(exc, contexte)
    return {
        "titre": titre,
        "message": message,
        "log": nom_fichier(),
        # Un incident déjà rédigé pour l'utilisateur n'expose pas de nom interne.
        "detail": (message if isinstance(exc, ErreurLisible) else f"{type(exc).__name__}: {exc}")[:400],
    }


def silence_bibliotheques() -> None:
    """
    Fait taire le bruit connu des dependances au demarrage.

    Cible principale : l'avertissement torchcodec / FFmpeg emis par torchaudio et
    pyannote, plus les avertissements de depreciation de speechbrain et lightning.
    Ces messages n'apportent rien a l'utilisateur et polluaient la console.
    """
    import warnings

    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("SPEECHBRAIN_QUIET", "1")

    for motif in (
        r".*torchcodec.*",
        r".*TorchCodec.*",
        r".*torchaudio.*(deprecat|backend).*",
        r".*FFmpeg.*not found.*",
        r".*was not found.*libtorchcodec.*",
        r".*std\(\): degrees of freedom.*",
        r".*does not have many workers.*",
        r".*`torchaudio.*",
    ):
        warnings.filterwarnings("ignore", message=motif)

    for categorie in (UserWarning, FutureWarning, DeprecationWarning):
        warnings.filterwarnings("ignore", category=categorie, module=r"(torch|torchaudio|pyannote|speechbrain|lightning|pytorch_lightning|huggingface_hub).*")

    for nom in (
        "torio",
        "torchaudio",
        "speechbrain",
        "pyannote",
        "pytorch_lightning",
        "lightning",
        "lightning_fabric",
        "huggingface_hub",
        "faster_whisper",
        "matplotlib",
    ):
        logging.getLogger(nom).setLevel(logging.ERROR)


class SortieMuette:
    """
    Redirige temporairement stderr vers le fichier de log.

    Certaines dependances ecrivent directement sur stderr, hors du systeme de
    warnings : sous pythonw.exe stderr est invalide, ce qui peut lever une
    exception. On capture donc tout et on le range dans le journal.
    """

    def __init__(self, etiquette: str = ""):
        self.etiquette = etiquette
        self._ancien = None
        self._tampon = None

    def __enter__(self):
        import io

        self._ancien = sys.stderr
        self._tampon = io.StringIO()
        sys.stderr = self._tampon
        return self

    def __exit__(self, *_):
        sys.stderr = self._ancien
        contenu = (self._tampon.getvalue() if self._tampon else "").strip()
        if contenu:
            debug("Sortie technique %s :\n%s", self.etiquette, contenu)
        return False
