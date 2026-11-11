"""
Corpus public de la campagne de mesure : réunions françaises avec référence.

Pourquoi
--------
Comparer deux réglages sur une vraie réunion ne dit pas lequel a raison : il
faut une transcription relue, mot à mot. Les réunions de l'utilisateur n'en ont
pas, et elles ne quittent pas son poste. La campagne (`app/campagne.py`) mesure
donc d'abord chaque réglage sur des réunions PUBLIQUES transcrites à la main.

Le corpus retenu
----------------
SUMM-RE ASRU (sous-ensemble « SUMM-RE-sm ») : dix réunions simulées de vingt
minutes, en français, trois ou quatre participants chacune, un micro par
participant, transcription orthographique corrigée à la main et alignée au mot
près. Licence Creative Commons BY-SA 4.0. Publié sur ORTOLANG
(https://doi.org/10.82270/summ-re-asru) et recopié à l'identique sur Hugging
Face (« datasets-CNRS/summ-re-asru »). Créateurs : Laboratoire Parole et
Langage (UMR 7309, Aix-Marseille Université) et LINAGORA, projet ANR SUMM-RE
(ANR-20-CE23-0017).

Rien de ce corpus n'est dans le dépôt : il ne contient que la liste des
extraits retenus, leurs octets dans les fichiers d'origine et leurs empreintes
(`corpus_manifeste.py`). Sur le poste, l'outil :

  1. prend un paquet déjà préparé s'il en trouve un (`corpus-campagne-v1.zip`
     à côté du programme, ou passé par `--corpus`), contrôlé fichier par
     fichier par son empreinte ;
  2. sinon télécharge, par requêtes partielles (en-tête HTTP Range), les seules
     secondes utiles de chaque piste depuis Hugging Face, puis ORTOLANG en
     repli, chaque morceau contrôlé par son empreinte ;
  3. mélange les pistes d'un extrait en un seul signal, comme un enregistreur
     posé sur la table : les voix qui se chevauchent se chevauchent aussi dans
     le signal, et la transcription au mot près dit lesquels de leurs mots
     tombent dans un chevauchement.

Ce que la licence impose, et comment c'est respecté : citer les auteurs et la
source, donner la licence, signaler les modifications (le rapport de la
campagne et le LISEZMOI du paquet le font), et diffuser toute œuvre dérivée
sous la même licence (le paquet préparé, qui contient des extraits mélangés et
une transcription nettoyée, est diffusé sous CC BY-SA 4.0 ; le code, qui ne
contient aucun extrait, n'est pas une œuvre dérivée).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import wave
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import chemins, journal
from .corpus_manifeste import MANIFESTE

FREQUENCE = 16000
VERSION_CORPUS = int(MANIFESTE["version"])
NOM_PAQUET = f"corpus-campagne-v{VERSION_CORPUS}.zip"
DOSSIER = chemins.RACINE / "corpus-campagne" / f"v{VERSION_CORPUS}"

#: Sources, dans l'ordre d'essai. Hugging Face d'abord : c'est d'où viennent
#: déjà les modèles, il est donc joignable partout où l'application fonctionne.
#: La révision est figée : les octets attendus ne bougeront pas.
SOURCES = (
    f"https://huggingface.co/datasets/{MANIFESTE['depot_hf']}/resolve/{MANIFESTE['revision_hf']}",
    MANIFESTE["base_ortolang"],
)

ATTRIBUTION = (
    "SUMM-RE ASRU, Laboratoire Parole et Langage (UMR 7309) et LINAGORA, projet ANR "
    "SUMM-RE (ANR-20-CE23-0017), ORTOLANG, https://doi.org/10.82270/summ-re-asru, "
    "licence CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). "
    "Modifications : extraits, pistes mélangées, ré-échantillonnage à 16 kHz, "
    "annotations de transcription retirées."
)

DELAI_RESEAU_S = 60
AGENT = "Scribouille-campagne"


class ErreurCorpus(Exception):
    """Le corpus ne peut pas être préparé : réseau refusé, empreinte fausse."""

    def __init__(self, motif: str, detail: str = ""):
        super().__init__(f"{motif}: {detail}")
        self.motif = motif
        self.detail = detail


@dataclass
class Extrait:
    ident: str
    reunion: str
    duree: float
    wav: Path
    reference: dict

    def signal(self) -> np.ndarray:
        return lire_wav16(self.wav)


# ---------------------------------------------------------------------------
# Fichiers WAV 16 bits, 16 kHz
# ---------------------------------------------------------------------------

def ecrire_wav16(chemin: Path, echantillons: np.ndarray) -> None:
    with wave.open(str(chemin), "wb") as sortie:
        sortie.setnchannels(1)
        sortie.setsampwidth(2)
        sortie.setframerate(FREQUENCE)
        sortie.writeframes(np.asarray(echantillons, dtype="<i2").tobytes())


def lire_wav16(chemin: Path) -> np.ndarray:
    with wave.open(str(chemin), "rb") as entree:
        if entree.getframerate() != FREQUENCE or entree.getsampwidth() != 2 or entree.getnchannels() != 1:
            raise ValueError("format inattendu")
        brut = entree.readframes(entree.getnframes())
    return np.frombuffer(brut, dtype="<i2").astype(np.float32) / 32768.0


def empreinte(donnees: bytes) -> str:
    return hashlib.sha256(donnees).hexdigest()


def empreinte_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Téléchargement partiel
# ---------------------------------------------------------------------------

def _lire_url(url: str, debut: int | None = None, fin: int | None = None) -> bytes:
    requete = urllib.request.Request(url, headers={"User-Agent": AGENT})
    if debut is not None:
        requete.add_header("Range", f"bytes={debut}-{fin}")
    with urllib.request.urlopen(requete, timeout=DELAI_RESEAU_S) as reponse:
        if debut is not None and getattr(reponse, "status", 206) != 206:
            raise ErreurCorpus("plage_refusee", "le serveur renvoie le fichier entier")
        return reponse.read()


def telecharger(relatif: str, sha256: str, debut: int | None = None,
                fin: int | None = None) -> bytes:
    """
    Octets d'un fichier du corpus (ou d'une plage, bornes incluses), contrôlés.

    Chaque source est essayée à son tour ; une empreinte fausse compte comme un
    échec de la source, jamais comme une donnée acceptable.
    """
    echecs: list[str] = []
    for base in SOURCES:
        try:
            donnees = _lire_url(f"{base}/{relatif}", debut, fin)
        except (urllib.error.URLError, OSError, TimeoutError, ErreurCorpus, ValueError) as exc:
            echecs.append(f"{base.split('/')[2]} : {type(exc).__name__}")
            continue
        if empreinte(donnees) != sha256:
            echecs.append(f"{base.split('/')[2]} : empreinte")
            continue
        return donnees
    raise ErreurCorpus("reseau", " ; ".join(echecs))


# ---------------------------------------------------------------------------
# Transcriptions de référence (conventions SPPAS)
# ---------------------------------------------------------------------------

_LOCUTEUR_ANONYME = re.compile(r"SPEAKER_?\d+")


def nettoyer_jeton(jeton: str) -> str:
    """
    Mot de la transcription manuelle débarrassé des annotations SPPAS.

    Silences « # », pauses « + », bruits « * », rires « @ », mots tronqués
    (« ex- ») et noms anonymisés (« SPEAKER_n ») disparaissent ; les
    prononciations « [mot,prononciation] » et variantes « <a,b> » gardent leur
    première forme, les liaisons « =n= » et les marques de nom propre « $ »
    s'effacent, les élisions « p(eu)t-être » sont rétablies.
    """
    j = jeton.strip()
    if j in ("#", "+", "*", "@", "dummy", "") or _LOCUTEUR_ANONYME.fullmatch(j):
        return ""
    j = re.sub(r"\[([^,\]]*),[^\]]*\]", r"\1", j)
    j = re.sub(r"<([^,>]*),[^>]*>", r"\1", j)
    j = re.sub(r"=\w*=", "", j)
    j = j.replace("$", "")
    j = re.sub(r"\(([^()]*)\)", r"\1", j)
    j = re.sub(r"\{[^}]*\}", "", j)
    if j.endswith("-"):
        return ""
    return j.replace("_", " ").strip()


def lire_jetons(contenu: bytes) -> list[tuple[float, float, str]]:
    """Jetons alignés d'une piste : (début, fin, jeton brut), tier « TokensAlign »."""
    resultat = []
    lecteur = csv.reader(io.StringIO(contenu.decode("utf-8-sig")))
    for ligne in lecteur:
        if len(ligne) < 4 or ligne[0] != "TokensAlign":
            continue
        try:
            resultat.append((float(ligne[1]), float(ligne[2]), ligne[3]))
        except ValueError:
            continue
    return resultat


def construire_reference(pistes: dict[str, list[tuple[float, float, str]]],
                         debut: float, fin: float) -> dict:
    """
    Référence d'un extrait : mots rangés par prise de parole.

    Une prise de parole (unité inter-pausale) est la suite des mots d'un
    locuteur entre deux silences « # ». Les prises de parole sont rangées par
    instant de début, chacune d'un seul tenant, comme un transcripteur les
    écrirait. Un mot est « en chevauchement » quand un autre locuteur prononce
    un mot pendant qu'il est prononcé. Seuls les mots entièrement compris dans
    l'extrait sont gardés (ses bornes tombent sur des silences communs).
    """
    noms = sorted(pistes)
    mots_par_piste: dict[str, list[tuple[float, float]]] = {}
    unites: list[tuple[float, int, list[tuple[str, float, float]]]] = []
    for rang, nom in enumerate(noms):
        intervalles = []
        courante: list[tuple[str, float, float]] = []
        for d, f, jeton in pistes[nom]:
            if jeton.strip() == "#":
                if courante:
                    unites.append((courante[0][1], rang, courante))
                    courante = []
                continue
            if d < debut - 0.01 or f > fin + 0.01:
                continue
            propre = nettoyer_jeton(jeton)
            if not propre:
                continue
            courante.append((propre, d - debut, f - debut))
            intervalles.append((d - debut, f - debut))
        if courante:
            unites.append((courante[0][1], rang, courante))
        mots_par_piste[nom] = intervalles

    def chevauche(rang: int, d: float, f: float) -> bool:
        for autre_rang, autre in enumerate(noms):
            if autre_rang == rang:
                continue
            for d2, f2 in mots_par_piste[autre]:
                if d2 < f and f2 > d:
                    return True
        return False

    unites.sort(key=lambda u: (u[0], u[1]))
    mots = []
    for _debut, rang, contenu in unites:
        for texte, d, f in contenu:
            mots.append([texte, round(d, 3), round(f, 3), rang, chevauche(rang, d, f)])
    return {"duree": round(fin - debut, 3), "locuteurs": len(noms), "mots": mots}


# ---------------------------------------------------------------------------
# Audio : en-tête, conversion, mélange
# ---------------------------------------------------------------------------

def lire_entete(octets: bytes) -> tuple[int, int, int, int, int]:
    """(format, canaux, fréquence, bits, décalage des données) d'un WAV."""
    if octets[:4] != b"RIFF" or octets[8:12] != b"WAVE":
        raise ValueError("pas un fichier WAV")
    i, fmt = 12, None
    while i <= len(octets) - 8:
        bloc, taille = octets[i:i + 4], struct.unpack("<I", octets[i + 4:i + 8])[0]
        if bloc == b"fmt ":
            format_, canaux, frequence, _debit, _align, bits = struct.unpack(
                "<HHIIHH", octets[i + 8:i + 24])
            fmt = (format_, canaux, frequence, bits)
        if bloc == b"data":
            if fmt is None:
                raise ValueError("bloc fmt absent")
            return (*fmt, i + 8)
        i += 8 + taille + (taille & 1)
    raise ValueError("bloc data absent")


def en_flottants(octets: bytes, format_: int, bits: int) -> np.ndarray:
    if format_ == 3 and bits == 32:
        return np.frombuffer(octets, dtype="<f4").astype(np.float32)
    if format_ == 1 and bits == 16:
        return np.frombuffer(octets, dtype="<i2").astype(np.float32) / 32768.0
    if format_ == 1 and bits == 24:
        brut = np.frombuffer(octets, dtype=np.uint8).reshape(-1, 3)
        valeurs = (brut[:, 0].astype(np.int32) | (brut[:, 1].astype(np.int32) << 8)
                   | (brut[:, 2].astype(np.int32) << 16))
        valeurs = np.where(valeurs >= 1 << 23, valeurs - (1 << 24), valeurs)
        return valeurs.astype(np.float32) / float(1 << 23)
    raise ValueError(f"format WAV non pris en charge ({format_}, {bits} bits)")


def reechantillonner(signal: np.ndarray, frequence: int) -> np.ndarray:
    """Vers 16 kHz, par le FFmpeg livré avec l'application."""
    if frequence == FREQUENCE:
        return signal.astype(np.float32)
    from . import audio

    resultat = subprocess.run(
        [audio.binaire_ffmpeg(), "-nostdin", "-hide_banner", "-loglevel", "error",
         "-f", "f32le", "-ar", str(frequence), "-ac", "1", "-i", "pipe:0",
         "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(FREQUENCE), "-ac", "1", "-"],
        input=np.ascontiguousarray(signal, dtype="<f4").tobytes(), capture_output=True,
        creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
    if resultat.returncode != 0:
        raise ErreurCorpus("reechantillonnage", (resultat.stderr or b"").decode("utf-8", "replace")[:200])
    return np.frombuffer(resultat.stdout, dtype="<f4").astype(np.float32)


def melanger(signaux: list[np.ndarray], paroles: list[list[tuple[float, float]]]) -> np.ndarray:
    """
    Somme des pistes, chacune ramenée au même niveau de parole.

    Chaque participant avait son micro, réglé à sa façon : on égalise le niveau
    moyen de chacun mesuré pendant qu'il parle (une salle bien équilibrée), puis
    on additionne et on ramène la crête à 0,9. Renvoie des entiers 16 bits.
    """
    n = min(s.size for s in signaux)
    total = np.zeros(n, dtype=np.float64)
    for signal, intervalles in zip(signaux, paroles):
        s = signal[:n].astype(np.float64)
        masque = np.zeros(n, dtype=bool)
        for d, f in intervalles:
            masque[max(0, int(d * FREQUENCE)):min(n, int(f * FREQUENCE))] = True
        actif = s[masque] if masque.any() else s
        niveau = float(np.sqrt(np.mean(actif ** 2))) if actif.size else 0.0
        if niveau > 1e-5:
            s = s * (0.1 / niveau)
        total += s
    crete = float(np.max(np.abs(total))) if total.size else 0.0
    if crete > 0:
        total *= 0.9 / crete
    return np.clip(np.round(total * 32767.0), -32768, 32767).astype("<i2")


# ---------------------------------------------------------------------------
# Préparation sur le poste
# ---------------------------------------------------------------------------

def _chemins(ident: str, dossier: Path) -> tuple[Path, Path]:
    return dossier / f"{ident}.wav", dossier / f"{ident}.ref.json"


def _extrait_pret(entree: dict, dossier: Path, strict: bool) -> bool:
    wav, ref = _chemins(entree["id"], dossier)
    if not (wav.is_file() and ref.is_file()):
        return False
    if not strict:
        return True
    return (empreinte_fichier(wav) == entree["sha256_wav"]
            and empreinte_fichier(ref) == entree["sha256_ref"])


def _depuis_paquet(paquet: Path, dossier: Path) -> int:
    """Extrait du paquet les fichiers dont l'empreinte correspond. Renvoie leur nombre."""
    poses = 0
    with zipfile.ZipFile(paquet) as archive:
        noms = {Path(n).name: n for n in archive.namelist()}
        for entree in MANIFESTE["extraits"]:
            for suffixe, cle in ((".wav", "sha256_wav"), (".ref.json", "sha256_ref")):
                nom = entree["id"] + suffixe
                if nom not in noms:
                    continue
                donnees = archive.read(noms[nom])
                if empreinte(donnees) != entree[cle]:
                    journal.attention("Paquet du corpus : empreinte fausse pour %s", nom)
                    continue
                (dossier / nom).write_bytes(donnees)
                poses += 1
    return poses


def paquets_candidats() -> list[Path]:
    """Paquets préparés que l'on cherche sans qu'on les désigne."""
    lieux = [Path(sys.executable).resolve().parent, chemins.RACINE, chemins.RACINE / "corpus-campagne"]
    if not chemins.EST_GELE:
        lieux.insert(0, Path(__file__).resolve().parent.parent)
    return [lieu / NOM_PAQUET for lieu in lieux if (lieu / NOM_PAQUET).is_file()]


def _construire_depuis_sources(entree: dict, dossier: Path, csv_cache: dict[str, bytes]) -> None:
    signaux, paroles, jetons = [], [], {}
    for piste in entree["pistes"]:
        nom = piste["nom"]
        if nom not in csv_cache:
            csv_cache[nom] = telecharger(f"gold_transcriptions/csv/{nom}_anon.csv",
                                         MANIFESTE["csv"][nom])
        jetons[nom] = lire_jetons(csv_cache[nom])
        brut = telecharger(f"audio_anonymized/{nom}_anon.wav", piste["sha256"],
                           piste["octet_debut"], piste["octet_fin"])
        signal = reechantillonner(en_flottants(brut, piste["format"], piste["bits"]),
                                  piste["frequence"])
        signaux.append(signal)
        paroles.append([(d - entree["debut"], f - entree["debut"]) for d, f, j in jetons[nom]
                        if nettoyer_jeton(j) and d >= entree["debut"] and f <= entree["fin"]])
    wav, ref = _chemins(entree["id"], dossier)
    ecrire_wav16(wav, melanger(signaux, paroles))
    reference = construire_reference(jetons, entree["debut"], entree["fin"])
    ref.write_text(json.dumps(reference, ensure_ascii=False), encoding="utf-8")


def preparer(rappel: Callable[[str], None] | None = None, paquet: str | Path | None = None,
             limite: int = 0, interrompu: Callable[[], bool] | None = None,
             dossier: Path | None = None) -> list[Extrait]:
    """
    Extraits prêts à transcrire, préparés au besoin (paquet, sinon réseau).

    `limite` ne garde que les N premiers extraits (essais rapides). Lève
    ErreurCorpus si un extrait manque et ne peut être obtenu.
    """
    dossier = dossier or DOSSIER
    dossier.mkdir(parents=True, exist_ok=True)
    voulus = MANIFESTE["extraits"][:limite] if limite else list(MANIFESTE["extraits"])

    manquants = [e for e in voulus if not _extrait_pret(e, dossier, strict=False)]
    if manquants:
        paquets = [Path(paquet)] if paquet else paquets_candidats()
        for candidat in paquets:
            if candidat.is_file():
                poses = _depuis_paquet(candidat, dossier)
                journal.info("Corpus : %s fichiers pris dans le paquet préparé", poses)
                if rappel:
                    rappel(f"paquet:{poses}")
                break
        manquants = [e for e in voulus if not _extrait_pret(e, dossier, strict=False)]

    csv_cache: dict[str, bytes] = {}
    for rang, entree in enumerate(manquants, 1):
        if interrompu and interrompu():
            break
        if rappel:
            rappel(f"reseau:{rang}/{len(manquants)}")
        _construire_depuis_sources(entree, dossier, csv_cache)

    extraits = []
    for entree in voulus:
        wav, ref = _chemins(entree["id"], dossier)
        if not (wav.is_file() and ref.is_file()):
            raise ErreurCorpus("incomplet", entree["id"])
        extraits.append(Extrait(entree["id"], entree["reunion"], entree["fin"] - entree["debut"],
                                wav, json.loads(ref.read_text(encoding="utf-8"))))
    return extraits


def octets_a_telecharger(limite: int = 0) -> int:
    voulus = MANIFESTE["extraits"][:limite] if limite else MANIFESTE["extraits"]
    return sum(p["octet_fin"] - p["octet_debut"] + 1 for e in voulus for p in e["pistes"])


LISEZMOI_PAQUET = """Corpus de la campagne de mesure de Scribouille, version {version}
=================================================================

{n} extraits de réunions en français, {duree} minutes au total, chacun en deux
fichiers : <extrait>.wav (mono, 16 kHz, 16 bits) et <extrait>.ref.json (mots de
la transcription manuelle, horodatés, avec le locuteur et un indicateur de
chevauchement de parole).

Source : SUMM-RE ASRU (sous-ensemble SUMM-RE-sm), Laboratoire Parole et Langage
(UMR 7309, Aix-Marseille Université) et LINAGORA, projet ANR SUMM-RE
(ANR-20-CE23-0017). ORTOLANG, https://doi.org/10.82270/summ-re-asru ; copie
Hugging Face : https://huggingface.co/datasets/datasets-CNRS/summ-re-asru

Référence : Hiroyoshi Yamasaki, Jérôme Louradour, Julie Hunter, Laurent Prévot
(2023), « Transcribing And Aligning Conversational Speech: A Hybrid Pipeline
Applied To French Conversations », ASRU 2023.

Licence : Creative Commons Attribution, Partage dans les mêmes conditions 4.0
International (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/deed.fr
Ce paquet est une œuvre dérivée, diffusée sous la même licence.

Modifications apportées : découpe d'extraits bornés sur des silences communs à
tous les participants ; pistes individuelles mélangées en un seul signal après
égalisation du niveau de parole de chacune ; ré-échantillonnage à 16 kHz et
quantification sur 16 bits ; transcription débarrassée des annotations SPPAS
(pauses, bruits, rires, mots tronqués, noms anonymisés, prononciations,
liaisons) et rangée par prise de parole.
"""


def fabriquer_paquet(sortie: Path, dossier: Path | None = None) -> Path:
    """Zip des extraits préparés, avec leur LISEZMOI de licence (préparation du portable)."""
    dossier = dossier or DOSSIER
    extraits = MANIFESTE["extraits"]
    duree = sum(e["fin"] - e["debut"] for e in extraits) / 60
    with zipfile.ZipFile(sortie, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("LISEZMOI.txt", LISEZMOI_PAQUET.format(
            version=VERSION_CORPUS, n=len(extraits), duree=f"{duree:.1f}".replace(".", ",")))
        for entree in extraits:
            wav, ref = _chemins(entree["id"], dossier)
            if empreinte_fichier(wav) != entree["sha256_wav"] or empreinte_fichier(ref) != entree["sha256_ref"]:
                raise ErreurCorpus("empreinte", entree["id"])
            archive.write(wav, wav.name)
            archive.write(ref, ref.name)
    return sortie
