"""
Lecture audio : mesure de durée, décodage.

On décode nous-mêmes une seule fois, en mono 16 kHz float32, pour trois raisons :
  - c'est exactement ce qu'attendent Whisper et pyannote, donc pas de double
    décodage entre les deux étapes ;
  - cela permet d'appliquer au passage les filtres « audio de salle » ;
  - cela évite de dépendre du backend audio de torchaudio, source du fameux
    avertissement torchcodec au démarrage.

Le décodage passe par PyAV, c'est-à-dire les bibliothèques de FFmpeg que
faster-whisper livre déjà : une seule FFmpeg dans le paquet, aucun sous-processus,
et le signal est écrit au fil du décodage dans un tableau réservé d'avance (le
pic de mémoire d'une réunion de 1 h 30 passe d'environ deux copies à une).
Le chemin est le même que celui de la ligne de commande `ffmpeg` utilisée
jusqu'en 2.4 : mêmes filtres, même conversion (`aformat`, donc `aresample` avec
ses réglages par défaut), même découpe d'un extrait.

numpy et PyAV ne sont importés qu'au premier décodage : la fenêtre démarre
sans eux.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import TYPE_CHECKING

from . import journal, langues
from .journal import ErreurLisible

if TYPE_CHECKING:
    import numpy as np

EXTENSIONS_AUDIO = {
    ".m4a", ".mp3", ".wav", ".ogg", ".oga", ".flac", ".webm", ".wma",
    ".aac", ".opus", ".mp4", ".mkv", ".mov", ".amr", ".aiff", ".3gp",
}

FREQUENCE = 16000

# Filtres appliqués en option pour les enregistrements de salle :
# coupe sous 100 Hz (ronflement, bruit de table), coupe au-dessus de 8 kHz
# (hors bande de la voix), puis normalisation de niveau EBU R128.
FILTRES_SALLE = "highpass=f=100,lowpass=f=8000,loudnorm=I=-18:TP=-2:LRA=11"

#: Conversion finale, celle que `-f f32le -ac 1 -ar 16000` demandait à FFmpeg.
_FORMAT_SORTIE = f"sample_fmts=flt:sample_rates={FREQUENCE}:channel_layouts=mono"


def decodeur_present() -> bool:
    """PyAV (les bibliothèques de FFmpeg) est-il là ? Test léger, sans import."""
    return importlib.util.find_spec("av") is not None


def ffmpeg_present() -> bool:
    """Ancien nom, gardé : le décodeur, c'est FFmpeg par PyAV."""
    return decodeur_present()


def version_decodeur() -> str:
    """Versions de PyAV et de FFmpeg (libavcodec), pour le bilan `--verifier`."""
    import av  # type: ignore

    avcodec = av.library_versions.get("libavcodec") or ()
    return f"PyAV {av.__version__}, libavcodec {'.'.join(str(n) for n in avcodec)}"


def est_audio(chemin: str | Path) -> bool:
    return Path(chemin).suffix.lower() in EXTENSIONS_AUDIO


def lister_dossier(dossier: str | Path) -> tuple[list[str], int]:
    """
    Fichiers audio d'un dossier, premier niveau seulement.

    Volontairement non récursif : déposer un dossier de projet entier ne doit
    pas déclencher trente heures de calcul par surprise. Renvoie les chemins
    retenus, triés, et le nombre d'entrées écartées.
    """
    cible = Path(str(dossier or "")).expanduser()
    if not cible.is_dir():
        return [], 0
    retenus: list[str] = []
    ignores = 0
    try:
        entrees = sorted(cible.iterdir())
    except OSError:
        return [], 0
    for entree in entrees:
        try:
            if entree.is_file() and est_audio(entree):
                retenus.append(str(entree))
            else:
                ignores += 1
        except OSError:
            ignores += 1
    return retenus, ignores


def _duree_conteneur(conteneur, flux) -> float:
    """Durée annoncée par le conteneur (la ligne « Duration » de FFmpeg), sinon par le flux."""
    if conteneur.duration:
        return conteneur.duration / 1_000_000
    if flux is not None and flux.duration and flux.time_base:
        return float(flux.duration * flux.time_base)
    return 0.0


def duree(chemin: str | Path) -> float:
    """
    Durée du fichier en secondes, 0 si elle n'a pas pu être lue. Lit l'en-tête
    seulement. Pour un WAV, la durée que son en-tête annonce compte aussi :
    FFmpeg mesure un WAV tronqué à ce qui reste, et la troncature passerait
    inaperçue.
    """
    mesuree = 0.0
    try:
        import av  # type: ignore

        with av.open(str(chemin)) as conteneur:
            flux = next((s for s in conteneur.streams if s.type == "audio"), None)
            mesuree = _duree_conteneur(conteneur, flux)
    except Exception as exc:
        journal.debug("Mesure de durée impossible pour %s : %s", chemin, exc)
    return max(mesuree, _duree_entete_wav(chemin)) if mesuree else mesuree


def _duree_entete_wav(chemin: str | Path) -> float:
    """Durée annoncée par l'en-tête RIFF d'un WAV (taille des données / débit), 0 sinon."""
    import struct

    try:
        with open(chemin, "rb") as flux:
            tete = flux.read(4096)
    except OSError:
        return 0.0
    if tete[:4] != b"RIFF" or tete[8:12] != b"WAVE":
        return 0.0
    position, debit, taille = 12, 0, 0
    while position + 8 <= len(tete):
        nom, longueur = tete[position:position + 4], struct.unpack("<I", tete[position + 4:position + 8])[0]
        if nom == b"fmt " and position + 16 <= len(tete):
            debit = struct.unpack("<I", tete[position + 16:position + 20])[0]
        elif nom == b"data":
            taille = longueur
            break
        position += 8 + longueur + (longueur & 1)
    if not debit or not taille or taille == 0xFFFFFFFF:
        return 0.0
    return taille / debit


def _graphe(av, flux, filtres_salle: bool, debut: float, duree_extrait: float, origine: float):
    """
    Chaîne de filtres : découpe éventuelle (comme `-ss` avant `-i`, puis `-t`),
    filtres de salle, conversion en mono 16 kHz flottant.
    """
    graphe = av.filter.Graph()
    noeuds = [graphe.add_abuffer(template=flux)]
    if debut > 0 or duree_extrait > 0:
        # Les instants des trames sont ceux du flux : le début du fichier n'est
        # pas forcément à zéro (`start_time`), FFmpeg le compte aussi.
        options = [f"start={origine + max(0.0, debut):.6f}"] if debut > 0 else []
        if duree_extrait > 0:
            options.append(f"duration={duree_extrait:.6f}")
        noeuds.append(graphe.add("atrim", ":".join(options)))
        noeuds.append(graphe.add("asetpts", "PTS-STARTPTS"))
    if filtres_salle:
        for filtre in FILTRES_SALLE.split(","):
            nom, _, arguments = filtre.partition("=")
            noeuds.append(graphe.add(nom, arguments))
    noeuds.append(graphe.add("aformat", _FORMAT_SORTIE))
    noeuds.append(graphe.add("abuffersink"))
    for amont, aval in zip(noeuds, noeuds[1:]):
        amont.link_to(aval)
    graphe.configure()
    return graphe


class _Tampon:
    """Tableau réservé d'avance d'après la durée annoncée, agrandi si elle était fausse."""

    def __init__(self, np, echantillons: int):
        self.np = np
        self.donnees = np.empty(max(echantillons, FREQUENCE), dtype=np.float32)
        self.taille = 0

    def ajouter(self, morceau) -> None:
        fin = self.taille + morceau.size
        if fin > self.donnees.size:
            nouveau = self.np.empty(max(fin, int(self.donnees.size * 1.25)), dtype=self.np.float32)
            nouveau[:self.taille] = self.donnees[:self.taille]
            self.donnees = nouveau
        self.donnees[self.taille:fin] = morceau
        self.taille = fin

    def resultat(self):
        if self.taille == self.donnees.size:
            return self.donnees
        # Copie seulement si la réserve dépasse nettement : quelques secondes
        # de marge ne valent pas une copie de tout le signal.
        if self.donnees.size - self.taille > 60 * FREQUENCE:
            return self.donnees[:self.taille].copy()
        return self.donnees[:self.taille]


def decoder(chemin: str | Path, filtres_salle: bool = False,
            debut: float = 0.0, duree: float = 0.0) -> "np.ndarray":
    """
    Décode le fichier en tableau float32 mono 16 kHz, normalisé entre -1 et 1.

    `debut` et `duree`, en secondes, ne décodent qu'un extrait (comparaison des
    moteurs) : le décodage se place directement près du début voulu, sans
    décoder ce qui précède. Zéro pour l'un ou l'autre : depuis le début,
    jusqu'à la fin.

    Lève une ErreurLisible si le fichier est illisible ou ne contient pas d'audio.
    """
    import numpy as np

    fichier = Path(chemin)
    if not fichier.exists():
        raise ErreurLisible(
            langues.t("audio.introuvable.titre"),
            langues.t("audio.introuvable.msg", nom=fichier.name),
        )
    try:
        import av  # type: ignore
    except Exception as exc:
        raise ErreurLisible(
            langues.t("audio.ffmpeg.titre"),
            langues.t("audio.ffmpeg.msg_installee"),
            exc,
        ) from exc

    debut = max(0.0, float(debut or 0.0))
    duree_extrait = max(0.0, float(duree or 0.0))
    try:
        with av.open(str(fichier)) as conteneur:
            flux = next((s for s in conteneur.streams if s.type == "audio"), None)
            if flux is None:
                raise ErreurLisible(
                    langues.t("audio.muet.titre"),
                    langues.t("audio.muet.msg", nom=fichier.name),
                )
            origine = float(conteneur.start_time or 0) / 1_000_000
            total = _duree_conteneur(conteneur, flux)
            attendu = duree_extrait if duree_extrait > 0 else max(0.0, total - debut)
            tampon = _Tampon(np, int(math.ceil(attendu * FREQUENCE)) + FREQUENCE)
            graphe = _graphe(av, flux, filtres_salle, debut, duree_extrait, origine)
            if debut > 0:
                # Recherche vers l'arrière jusqu'à l'image clé précédente ; la
                # découpe exacte est faite par « atrim », comme FFmpeg le fait
                # après un « -ss » placé devant l'entrée.
                conteneur.seek(int((origine + debut) * 1_000_000), backward=True, any_frame=False)

            def tirer() -> None:
                while True:
                    try:
                        trame = graphe.pull()
                    except (av.error.BlockingIOError, av.error.EOFError):
                        return
                    tampon.ajouter(trame.to_ndarray().reshape(-1))

            ferme = False
            for trame in conteneur.decode(flux):
                try:
                    graphe.push(trame)
                except av.error.EOFError:
                    # « atrim » a reçu tout l'extrait : la chaîne est close.
                    ferme = True
                    break
                tirer()
            if not ferme:
                try:
                    graphe.push(None)
                except av.error.EOFError:
                    pass
            tirer()
    except ErreurLisible:
        raise
    except Exception as exc:
        journal.erreur("Décodage en échec sur %s : %s", fichier.name, f"{type(exc).__name__}: {exc}"[:2000])
        raise ErreurLisible(
            langues.t("audio.illisible.titre"),
            langues.t("audio.illisible.msg",
                      nom=fichier.name, journal=journal.nom_fichier()),
            exc,
        ) from exc

    signal = tampon.resultat()
    if signal.size == 0:
        raise ErreurLisible(
            langues.t("audio.muet.titre"),
            langues.t("audio.muet.msg", nom=fichier.name),
        )

    # Crête sans tableau intermédiaire (np.abs en ferait une copie entière).
    maximum = max(float(signal.max()), -float(signal.min()))
    if maximum > 1.0:
        signal /= maximum

    journal.info(
        "Audio décodé : %s, %.1f s%s",
        fichier.name, signal.size / FREQUENCE,
        " (filtres de salle appliqués)" if filtres_salle else "",
    )
    return signal


def reechantillonner(signal: "np.ndarray", frequence: int) -> "np.ndarray":
    """Un signal mono flottant vers 16 kHz, par le même rééchantillonneur que le décodage."""
    import numpy as np

    if frequence == FREQUENCE:
        return np.asarray(signal, dtype=np.float32)
    import av  # type: ignore

    graphe = av.filter.Graph()
    from fractions import Fraction

    base = Fraction(1, int(frequence))
    source = graphe.add_abuffer(format="flt", sample_rate=int(frequence), layout="mono", time_base=base)
    conversion = graphe.add("aformat", _FORMAT_SORTIE)
    sortie = graphe.add("abuffersink")
    source.link_to(conversion)
    conversion.link_to(sortie)
    graphe.configure()
    tampon = _Tampon(np, int(signal.size * FREQUENCE / frequence) + FREQUENCE)
    donnees = np.ascontiguousarray(signal, dtype=np.float32)
    pas = 65536
    for depart in range(0, donnees.size, pas):
        trame = av.AudioFrame.from_ndarray(donnees[depart:depart + pas].reshape(1, -1), format="flt",
                                           layout="mono")
        trame.sample_rate = int(frequence)
        trame.pts = depart
        trame.time_base = base
        graphe.push(trame)
        while True:
            try:
                tampon.ajouter(graphe.pull().to_ndarray().reshape(-1))
            except (av.error.BlockingIOError, av.error.EOFError):
                break
    graphe.push(None)
    while True:
        try:
            tampon.ajouter(graphe.pull().to_ndarray().reshape(-1))
        except (av.error.BlockingIOError, av.error.EOFError):
            break
    return np.array(tampon.resultat(), dtype=np.float32)


def formater_taille(octets: int) -> str:
    """Taille d'un fichier, unités et séparateur décimal de la langue courante."""
    return langues.octets(octets)
