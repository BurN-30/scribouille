"""
Comparaison des deux moteurs sur un vrai enregistrement.

Pourquoi
--------
Le banc d'essai (`app/banc.py`) dit quel moteur va le plus vite, sur 44 s de
phrases lues d'une seule voix. Il ne dit rien de la justesse sur une vraie
réunion : plusieurs voix, des phrases coupées, des mots avalés, des mots
anglais au milieu du français, le vocabulaire propre à l'équipe. Seul
l'utilisateur a ces enregistrements, et ils ne quittent pas son poste.

Cette commande transcrit le MÊME extrait d'un fichier avec CTranslate2 et avec
OpenVINO, chacun dans son réglage Qualité, avec la langue, le glossaire et les
corrections de l'utilisateur, puis écrit dans un dossier local :

  - `cote-a-cote.html` : les deux textes horodatés face à face, les passages
    où ils divergent surlignés, les mots incertains de CTranslate2 soulignés,
    et la référence en troisième colonne si l'utilisateur en fournit une. Ce
    fichier contient la transcription : il reste sur le poste, comme
    `textes-ctranslate2.json` et `textes-openvino.json`, les segments bruts ;
  - `rapport-chiffres.txt` : des nombres seulement, sans un mot de la
    transcription, sans nom ni chemin. C'est lui qu'on peut transmettre.

Le désaccord entre les deux moteurs n'est pas une erreur de l'un ou de l'autre :
il dit OÙ regarder. La page permet de trancher en réécoutant ; une référence
relue permet de compter.

Ligne de commande (sans fenêtre) :

    scribouille-verifier.exe --comparer FICHIER [--debut 00:05:00] [--duree 600]
        [--reference TRANSCRIPTION] [--sortie DOSSIER] [--peripherique GPU|CPU|NPU]
        [--preset qualite|rapide] [--faisceau-openvino N]
        [--faisceau-ctranslate2 N] [--glossaire FICHIER] [--sans-glossaire]
        [--sans-corrections] [--ouvrir]

Chaque moteur tourne dans son propre processus (`--comparer-essai`), comme les
essais du banc : la mémoire est rendue entre les deux, un périphérique qui se
bloque est arrêté au bout du délai, et le chronomètre de l'un ne subit pas le
modèle encore chargé de l'autre.
"""

from __future__ import annotations

import html
import json
import os
import re
import statistics
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

import numpy as np

from . import NOM_APPLICATION, VERSION, chemins, journal, langues, materiel, moteur, presets

MARQUE = "SCRIBOUILLE-COMPARAISON|"
DOSSIER_COMPARAISONS = chemins.RACINE / "comparaisons"

#: Probabilité sous laquelle un mot est signalé incertain dans la vue de
#: relecture (même seuil que `compagnon.SEUIL_FAIBLE`).
SEUIL_INCERTAIN = 0.50

#: Écart d'horodatage, en secondes, au-delà duquel deux mots identiques sont
#: tenus pour mal placés l'un par rapport à l'autre. Une seconde suffit à
#: changer l'attribution d'un locuteur sur une réplique courte.
ECART_HORODATAGE_S = 1.0

#: Un passage où un moteur a au moins ce nombre de mots de plus que l'autre
#: compte comme « segment manquant ou en trop », pas comme quelques mots perdus.
MOTS_SEGMENT = 4

#: Au-delà de ce nombre de cellules, l'alignement mot à mot exact coûterait trop
#: de mémoire (fichier entier d'une heure contre sa référence) : on ancre
#: d'abord les longues portions identiques, puis l'alignement exact ne travaille
#: que dans les trous. Le résultat peut alors dépasser d'un cheveu le minimum.
CELLULES_MAX = 25_000_000


# ---------------------------------------------------------------------------
# Normalisation : ce qui compte comme « le même mot »
# ---------------------------------------------------------------------------

#: Hésitations retirées des deux côtés : un transcripteur humain les note, le
#: modèle rarement, et elles ne portent aucun sens.
HESITATIONS = frozenset({
    "euh", "euhm", "heu", "hum", "hm", "hmm", "mh", "mhm", "mm", "mmh", "uh", "um",
})

#: Formes ramenées à une seule graphie avant comparaison.
EQUIVALENCES = {
    "okay": "ok", "oké": "ok", "okey": "ok", "vingts": "vingt", "cents": "cent",
}

#: Annotations courantes des transcriptions faites à la main, retirées quand
#: elles sont entre parenthèses : « (rires) », « (inaudible) ».
ANNOTATIONS = frozenset({
    "rires", "rire", "inaudible", "incompréhensible", "silence", "pause", "bruit",
    "toux", "applaudissements", "musique", "brouhaha", "inaudibles", "laughter",
    "laughs", "crosstalk", "noise", "music",
})

_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
           "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _moins_de_cent(n: int) -> str:
    if n <= 16:
        return _UNITES[n]
    if n < 20:
        return "dix " + _UNITES[n - 10]
    dizaine, unite = divmod(n, 10)
    if dizaine in (7, 9):
        base = "soixante" if dizaine == 7 else "quatre vingt"
        reste = 10 + unite
        liaison = " et " if (dizaine == 7 and unite == 1) else " "
        return base + liaison + _moins_de_cent(reste)
    if dizaine == 8:
        return "quatre vingt" + ("" if unite == 0 else " " + _UNITES[unite])
    base = _DIZAINES[dizaine]
    if unite == 0:
        return base
    if unite == 1:
        return base + " et un"
    return base + " " + _UNITES[unite]


def _moins_de_mille(n: int) -> str:
    centaines, reste = divmod(n, 100)
    morceaux = []
    if centaines:
        morceaux.append("cent" if centaines == 1 else _UNITES[centaines] + " cent")
    if reste or not centaines:
        morceaux.append(_moins_de_cent(reste))
    return " ".join(morceaux)


def nombre_en_lettres(n: int) -> str:
    """Un entier en toutes lettres, mots séparés par des espaces (« quatre vingt dix »)."""
    if n < 0:
        return "moins " + nombre_en_lettres(-n)
    if n >= 10 ** 12:
        return " ".join(_UNITES[int(c)] for c in str(n))
    morceaux = []
    for valeur, nom in ((10 ** 9, "milliard"), (10 ** 6, "million")):
        quantite, n = divmod(n, valeur)
        if quantite:
            morceaux.append(_moins_de_mille(quantite) + " " + nom + ("s" if quantite > 1 else ""))
    milliers, n = divmod(n, 1000)
    if milliers:
        morceaux.append("mille" if milliers == 1 else _moins_de_mille(milliers) + " mille")
    if n or not morceaux:
        morceaux.append(_moins_de_mille(n))
    return " ".join(morceaux)


def ordinal_en_lettres(n: int, feminin: bool = False) -> str:
    if n == 1:
        return "première" if feminin else "premier"
    mots = nombre_en_lettres(n).split()
    dernier = mots[-1]
    if dernier == "un":
        dernier = "unième"
    elif dernier == "cinq":
        dernier = "cinquième"
    elif dernier == "neuf":
        dernier = "neuvième"
    elif dernier.endswith("e"):
        dernier = dernier[:-1] + "ième"
    elif dernier.endswith("s") and dernier not in ("trois",):
        dernier = dernier[:-1] + "ième"
    else:
        dernier = dernier + "ième"
    return " ".join(mots[:-1] + [dernier])


_ESPACES_MILLIERS = re.compile(r"(?<![\d,.])(\d{1,3})(?:[   ](\d{3}))+(?![\d])")
_ORDINAL = re.compile(r"\b(\d+)\s?(er|re|ère|ères|ers|eme|ème|èmes|emes|e|es|è)\b", re.IGNORECASE)
_POURCENT = re.compile(r"(\d+(?:[,.]\d+)?)\s?%")
_HEURE = re.compile(r"\b(\d{1,2})\s?h\s?(\d{2})?\b", re.IGNORECASE)
_DECIMAL = re.compile(r"\b(\d+)[,.](\d+)\b")
_ENTIER = re.compile(r"\d+")


def _nombres_en_lettres(texte: str) -> str:
    texte = _ESPACES_MILLIERS.sub(lambda m: m.group(0).replace(" ", "").replace(
        " ", "").replace(" ", ""), texte)
    texte = _POURCENT.sub(lambda m: m.group(1) + " pour cent", texte)
    texte = _ORDINAL.sub(lambda m: " " + ordinal_en_lettres(
        int(m.group(1)), feminin=m.group(2).lower().startswith("r")
        or m.group(2).lower() == "ère") + " ", texte)
    texte = _HEURE.sub(lambda m: " " + nombre_en_lettres(int(m.group(1))) + " heures"
                       + (" " + nombre_en_lettres(int(m.group(2))) if m.group(2)
                          and int(m.group(2)) else "") + " ", texte)
    texte = _DECIMAL.sub(lambda m: " " + nombre_en_lettres(int(m.group(1))) + " virgule "
                         + " ".join(nombre_en_lettres(int(m.group(2))).split()) + " ", texte)
    texte = texte.replace("€", " euros ").replace("$", " dollars ")
    return _ENTIER.sub(lambda m: " " + nombre_en_lettres(int(m.group(0))) + " ", texte)


def normaliser(texte: str) -> list[str]:
    """
    Mots comparables d'un texte : minuscules, sans ponctuation, nombres en
    lettres, élisions et traits d'union séparés (« l'équipe » donne « l »,
    « équipe »), hésitations retirées. Les deux moteurs et la référence passent
    par la même fonction : ce qui reste comme différence est une différence de
    mots, pas de mise en forme.
    """
    if not texte:
        return []
    texte = unicodedata.normalize("NFC", texte)
    texte = re.sub(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>", " ", texte)
    # Élision notée dans le mot, « p(eu)t-être » : on garde le mot entier.
    texte = re.sub(r"(?<=\w)\(([^()\s]*)\)|\(([^()\s]*)\)(?=\w)",
                   lambda m: m.group(1) or m.group(2) or "", texte)
    texte = re.sub(r"\(([^()]*)\)",
                   lambda m: " " if m.group(1).strip().lower() in ANNOTATIONS else " " + m.group(1) + " ",
                   texte)
    texte = re.sub(r"\b[oO]\.\s?[kK]\.?", " ok ", texte)
    texte = _nombres_en_lettres(texte)
    texte = texte.lower().replace("’", "'").replace("œ", "oe").replace("æ", "ae")
    texte = re.sub(r"[^\w]+|_", " ", texte)
    mots = []
    for mot in texte.split():
        mot = EQUIVALENCES.get(mot, mot)
        if mot in HESITATIONS:
            continue
        mots.append(mot)
    return mots


# ---------------------------------------------------------------------------
# Mots anglais : un indicateur, pas un décompte exhaustif
# ---------------------------------------------------------------------------

#: Mots anglais fréquents dans une réunion française (outils, informatique,
#: gestion de projet, mots-outils de l'anglais), choisis pour NE PAS être des
#: mots français : « on », « but », « test », « planning » ou « manager » en
#: sont exclus. Compter ceux qu'un moteur écrit en anglais dit s'il garde le mot
#: anglais prononcé ou le francise (« mitingue », « réunion »). Liste
#: volontairement courte : un vrai dictionnaire pèserait des mégaoctets.
MOTS_ANGLAIS = frozenset("""
the and of to is are was were be been being this that these those with from what which
who whom whose how why when where there their they them we you your our my his her its
do does did done can could would should will shall just not yes yeah please thanks thank
sorry well all some any more most about into over after before because if then than also
only really very here now get got gets make made take took know think thought need needs
want wants going gonna wanna let see look said say says tell told give gave work works
working worked good great nice cool awesome fine right left new old next last first
meeting meetings call calls deadline deadlines feature features release releases roadmap
sprint sprints backlog review reviews feedback workflow workflows update updates upgrade
deploy deployed deployment build builds building branch branches merge merged commit
commits push pushed pull request requests issue issues ticket tickets bug bugs fix fixed
hotfix debug check checked checklist team teams business startup timing slide slides
board dashboard dashboards framework frontend backend database databases server servers
cloud container containers cluster staging user users admin login logout password
website download downloads upload uploads online offline stream streaming chat link
links share shared screen deal benchmark brainstorming briefing workshop kickoff
onboarding scope follow asap meetup call conf call daily weekly standup stand retro
retrospective product owner scrum agile lead leader leads customer customers client
store stores api apis endpoint endpoint endpoints token tokens cache key keys keyboard
mouse laptop desktop browser chrome firefox device devices driver drivers patch patches
legacy refactor refactoring code coding coder developer developers dev devs ops devops
design designer designers mockup mockups wireframe wireframes layout template templates
""".split())


def nombre_mots_anglais(mots: list[str]) -> int:
    return sum(1 for mot in mots if mot in MOTS_ANGLAIS)


# ---------------------------------------------------------------------------
# Jetons : un mot normalisé, son horodatage, sa confiance, son mot affiché
# ---------------------------------------------------------------------------

@dataclass
class Jeton:
    mot: str                  # forme normalisée
    debut: float              # secondes, temps de l'extrait
    fin: float
    probabilite: float | None  # None : inconnue (OpenVINO, mot corrigé, référence)
    affiche: int              # rang du mot affiché auquel il appartient
    segment: int              # rang du segment


@dataclass
class Texte:
    """Un texte prêt à comparer : jetons, mots affichés, segments."""

    jetons: list[Jeton] = field(default_factory=list)
    affiches: list[str] = field(default_factory=list)
    segments: list[tuple[float, float]] = field(default_factory=list)


def _aligner_simple(a: list[str], b: list[str]) -> list[int | None]:
    """Pour chaque élément de a, l'indice de b qui lui correspond (ou None)."""
    correspondance: list[int | None] = [None] * len(a)
    for op, i1, i2, j1, j2 in _operations(a, b):
        if op in ("egal", "sub"):
            for k in range(i2 - i1):
                correspondance[i1 + k] = j1 + k
    return correspondance


def construire_texte(segments: list[dict]) -> Texte:
    """
    Jetons d'une transcription à partir de ses segments.

    Le texte du segment est celui que l'utilisateur lit, corrections appliquées.
    Les mots horodatés, eux, sortent du moteur AVANT les corrections : on aligne
    les deux pour donner à chaque jeton du texte l'horodatage et la confiance du
    mot entendu. Un jeton qu'une correction a changé garde l'horodatage de son
    voisin, et sa confiance devient inconnue.
    """
    texte = Texte()
    for rang_segment, segment in enumerate(segments):
        debut_s, fin_s = float(segment.get("d", 0.0)), float(segment.get("f", 0.0))
        texte.segments.append((debut_s, fin_s))
        mots_moteur = segment.get("m") or []
        jetons_moteur: list[tuple[str, float, float, float | None]] = []
        for brut in mots_moteur:
            t, d, f = str(brut[0]), float(brut[1]), float(brut[2])
            p = float(brut[3]) if len(brut) > 3 and brut[3] is not None and float(brut[3]) >= 0 else None
            for forme in normaliser(t):
                jetons_moteur.append((forme, d, f, p))
        nouveaux: list[Jeton] = []
        for mot_affiche in str(segment.get("t", "")).split():
            rang_affiche = len(texte.affiches)
            texte.affiches.append(mot_affiche)
            for forme in normaliser(mot_affiche):
                nouveaux.append(Jeton(forme, debut_s, fin_s, None, rang_affiche, rang_segment))
        if jetons_moteur and nouveaux:
            correspondance = _aligner_simple([j.mot for j in nouveaux], [j[0] for j in jetons_moteur])
            for jeton, indice in zip(nouveaux, correspondance):
                if indice is not None:
                    forme, d, f, p = jetons_moteur[indice]
                    jeton.debut, jeton.fin = d, f
                    jeton.probabilite = p if forme == jeton.mot else None
            # Jetons sans correspondant : horodatage du voisin précédent.
            precedent = debut_s
            for jeton, indice in zip(nouveaux, correspondance):
                if indice is None:
                    jeton.debut = jeton.fin = precedent
                else:
                    precedent = jeton.fin
        elif nouveaux:
            # Pas de mots horodatés : répartition régulière dans le segment.
            pas = (fin_s - debut_s) / max(1, len(nouveaux))
            for k, jeton in enumerate(nouveaux):
                jeton.debut = debut_s + k * pas
                jeton.fin = jeton.debut + pas
        texte.jetons.extend(nouveaux)
    return texte


# ---------------------------------------------------------------------------
# Alignement mot à mot (distance d'édition)
# ---------------------------------------------------------------------------

def _distance_exacte(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    """
    Opérations d'édition minimales de a vers b : « egal », « sub », « sup »
    (mot de a absent de b), « ins » (mot de b absent de a), une par jeton.
    Programmation dynamique ligne par ligne, vectorisée.
    """
    n, m = len(a), len(b)
    if n == 0:
        return [("ins", 0, 0, j, j + 1) for j in range(m)]
    if m == 0:
        return [("sup", i, i + 1, 0, 0) for i in range(n)]
    vocabulaire: dict[str, int] = {}
    ca = np.array([vocabulaire.setdefault(x, len(vocabulaire)) for x in a], dtype=np.int32)
    cb = np.array([vocabulaire.setdefault(x, len(vocabulaire)) for x in b], dtype=np.int32)
    type_ = np.int16 if n + m < 30000 else np.int32
    table = np.empty((n + 1, m + 1), dtype=type_)
    table[0] = np.arange(m + 1)
    indices = np.arange(m + 1, dtype=np.int64)
    for i in range(1, n + 1):
        precedent = table[i - 1].astype(np.int64)
        candidat = np.empty(m + 1, dtype=np.int64)
        candidat[0] = i
        candidat[1:] = np.minimum(precedent[1:] + 1, precedent[:-1] + (cb != ca[i - 1]))
        ligne = np.minimum.accumulate(candidat - indices) + indices
        table[i] = ligne
    operations: list[tuple[str, int, int, int, int]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and table[i, j] == table[i - 1, j - 1] + (ca[i - 1] != cb[j - 1]):
            operations.append(("egal" if ca[i - 1] == cb[j - 1] else "sub", i - 1, i, j - 1, j))
            i, j = i - 1, j - 1
        elif i > 0 and table[i, j] == table[i - 1, j] + 1:
            operations.append(("sup", i - 1, i, j, j))
            i -= 1
        else:
            operations.append(("ins", i, i, j - 1, j))
            j -= 1
    operations.reverse()
    return operations


def _operations(a: list[str], b: list[str]) -> list[tuple[str, int, int, int, int]]:
    """Alignement exact si la taille le permet, ancré par blocs identiques sinon."""
    if (len(a) + 1) * (len(b) + 1) <= CELLULES_MAX:
        return _distance_exacte(a, b)
    operations: list[tuple[str, int, int, int, int]] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            operations += [("egal", i1 + k, i1 + k + 1, j1 + k, j1 + k + 1) for k in range(i2 - i1)]
        elif (i2 - i1 + 1) * (j2 - j1 + 1) <= CELLULES_MAX:
            for sop, si1, si2, sj1, sj2 in _distance_exacte(a[i1:i2], b[j1:j2]):
                operations.append((sop, si1 + i1, si2 + i1, sj1 + j1, sj2 + j1))
        else:
            # Trou démesuré (une heure sans un mot commun) : mot pour mot.
            commun = min(i2 - i1, j2 - j1)
            operations += [("sub", i1 + k, i1 + k + 1, j1 + k, j1 + k + 1) for k in range(commun)]
            operations += [("sup", i, i + 1, j1 + commun, j1 + commun) for i in range(i1 + commun, i2)]
            operations += [("ins", i2, i2, j, j + 1) for j in range(j1 + commun, j2)]
    return operations


@dataclass
class Bilan:
    """Résultat d'un alignement de b sur a."""

    operations: list[tuple[str, int, int, int, int]]
    n_a: int
    n_b: int

    @property
    def substitutions(self) -> int:
        return sum(1 for o in self.operations if o[0] == "sub")

    @property
    def suppressions(self) -> int:
        return sum(1 for o in self.operations if o[0] == "sup")

    @property
    def insertions(self) -> int:
        return sum(1 for o in self.operations if o[0] == "ins")

    @property
    def editions(self) -> int:
        return self.substitutions + self.suppressions + self.insertions

    def taux(self, rapporte_a: str = "a") -> float:
        """Taux d'erreur (WER) en %, rapporté au nombre de mots de a ou de b."""
        total = self.n_a if rapporte_a == "a" else self.n_b
        return round(100.0 * self.editions / max(1, total), 2)

    def passages(self) -> list[tuple[int, int, int, int]]:
        """Passages divergents : (début a, fin a, début b, fin b), bornes exclues."""
        resultat: list[tuple[int, int, int, int]] = []
        courant: list[int] | None = None
        for op, i1, i2, j1, j2 in self.operations:
            if op == "egal":
                if courant is not None:
                    resultat.append(tuple(courant))  # type: ignore[arg-type]
                    courant = None
                continue
            if courant is None:
                courant = [i1, i2, j1, j2]
            else:
                courant[1], courant[3] = i2, j2
        if courant is not None:
            resultat.append(tuple(courant))  # type: ignore[arg-type]
        return resultat

    def divergents_a(self) -> set[int]:
        return {o[1] for o in self.operations if o[0] in ("sub", "sup")}

    def divergents_b(self) -> set[int]:
        return {o[3] for o in self.operations if o[0] in ("sub", "ins")}


def aligner(a: list[str], b: list[str]) -> Bilan:
    return Bilan(_operations(a, b), len(a), len(b))


def taux_erreur(reference: str, hypothese: str) -> float:
    """WER en %, avec la normalisation de la comparaison (nombres, hésitations)."""
    return aligner(normaliser(reference), normaliser(hypothese)).taux("a")


# ---------------------------------------------------------------------------
# Référence fournie par l'utilisateur
# ---------------------------------------------------------------------------

_HEURE_SRT = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")
_HEURE_VTT_COURTE = re.compile(r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
                               r"(?:(\d{1,2}):)?(\d{2}):(\d{2})[.,](\d{3})")
_HORODATAGE_LIGNE = re.compile(r"^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d+)?)\]?\s*[-:]?\s*")
#: Ligne « Nom   0:01:23 » seule : en-tête de réplique d'une transcription
#: exportée par un outil de visioconférence (texte de Teams, par exemple).
_NOM_PUIS_HEURE = re.compile(r"^\s*\S.{0,60}?\s+((?:\d{1,2}:)?\d{1,2}:\d{2})\s*$")
_LOCUTEUR = re.compile(
    r"^\s*(?:<v\s+[^>]*>|(?:SPEAKER[_ ]?\d+|Speaker \d+|Locuteur \d+|Intervenant \d+"
    r"|[A-ZÀ-Ý][\w'.-]*(?: [A-ZÀ-Ý0-9][\w'.-]*){0,2}))\s?:\s+")


def _secondes(texte: str) -> float:
    morceaux = texte.replace(",", ".").split(":")
    total = 0.0
    for morceau in morceaux:
        total = total * 60 + float(morceau)
    return total


def lire_duree(texte: str) -> float:
    """« 00:05:00 », « 5:00 », « 300 » ou « 300s » en secondes."""
    texte = str(texte or "").strip().lower().rstrip("s")
    if not texte:
        return 0.0
    if ":" in texte:
        return _secondes(texte)
    return float(texte.replace(",", "."))


@dataclass
class Reference:
    blocs: list[tuple[float | None, float | None, str]]
    horodatee: bool
    format: str


def _sans_locuteur(ligne: str) -> str:
    return _LOCUTEUR.sub("", ligne, count=1)


def lire_reference(chemin: str | Path) -> Reference:
    """
    Lit une transcription relue : SRT, VTT, texte brut, texte exporté par
    Scribouille (en-tête, horodatages et locuteurs ignorés), ou compagnon JSON.
    Les noms de locuteurs en début de réplique (« Locuteur 1 : », « Marie : »)
    sont retirés.
    """
    fichier = Path(chemin)
    brut = fichier.read_text(encoding="utf-8-sig", errors="replace")
    extension = fichier.suffix.lower()

    if extension == ".json":
        donnees = json.loads(brut)
        blocs = [(float(s.get("d", 0)), float(s.get("f", 0)), str(s.get("t", "")))
                 for s in donnees.get("segments") or []]
        return Reference(blocs, True, "json")

    if _HEURE_SRT.search(brut) or _HEURE_VTT_COURTE.search(brut):
        blocs: list[tuple[float | None, float | None, str]] = []
        for bloc in re.split(r"\n\s*\n", brut.replace("\r\n", "\n")):
            lignes = [l for l in bloc.split("\n") if l.strip()]
            for rang, ligne in enumerate(lignes):
                trouve = _HEURE_VTT_COURTE.search(ligne)
                if not trouve:
                    continue
                g = trouve.groups()
                debut = int(g[0] or 0) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
                fin = int(g[4] or 0) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
                texte = " ".join(_sans_locuteur(l) for l in lignes[rang + 1:])
                blocs.append((debut, fin, texte))
                break
        return Reference(blocs, True, "srt")

    lignes = brut.replace("\r\n", "\n").split("\n")
    # En-tête encadré d'un export de Scribouille : deux lignes de « = » au
    # début, puis l'en-tête, puis une troisième ligne de « = ».
    cadres = [k for k, l in enumerate(lignes[:40]) if re.fullmatch(r"\s*={20,}\s*", l)]
    if len(cadres) >= 3:
        lignes = lignes[cadres[2] + 1:]
    blocs = []
    horodatee = False
    for ligne in lignes:
        if not ligne.strip():
            continue
        entete = _NOM_PUIS_HEURE.match(ligne)
        if entete:
            horodatee = True
            blocs.append((_secondes(entete.group(1)), None, ""))
            continue
        trouve = _HORODATAGE_LIGNE.match(ligne)
        if trouve and ":" in trouve.group(1):
            horodatee = True
            blocs.append((_secondes(trouve.group(1)), None, _sans_locuteur(ligne[trouve.end():])))
        elif blocs and horodatee:
            debut, fin, texte = blocs[-1]
            blocs[-1] = (debut, fin, texte + " " + _sans_locuteur(ligne))
        else:
            blocs.append((None, None, _sans_locuteur(ligne)))
    if horodatee:
        # Une ligne horodatée ne donne que son début : sa fin est le début de
        # la suivante.
        complets = []
        for rang, (debut, _fin, texte) in enumerate(blocs):
            suivant = next((b[0] for b in blocs[rang + 1:] if b[0] is not None), None)
            complets.append((debut, suivant, texte))
        blocs = complets
    return Reference(blocs, horodatee, "texte")


def reference_sur_extrait(ref: Reference, debut: float, fin: float, extrait_complet: bool,
                          tolerance: float = 0.5) -> tuple[str, float, float, str]:
    """
    Partie de la référence qui tombe dans l'extrait : (texte, début, fin, motif).

    Début et fin sont dans le temps du fichier ; le motif est vide si tout va
    bien, sinon il dit pourquoi la comparaison est impossible. Sans
    horodatages, la référence n'est utilisable que si l'extrait est le fichier
    entier. Avec, on garde les répliques entièrement comprises dans l'extrait,
    et la fenêtre de comparaison se resserre sur elles.
    """
    if not ref.blocs:
        return "", 0.0, 0.0, "vide"
    if not ref.horodatee:
        if extrait_complet:
            return " ".join(b[2] for b in ref.blocs), debut, fin, ""
        return "", 0.0, 0.0, "sans_horodatage"
    gardes = [b for b in ref.blocs
              if b[0] is not None and b[0] >= debut - tolerance
              and ((b[1] is not None and b[1] <= fin + tolerance)
                   or (b[1] is None and extrait_complet))]
    if not gardes:
        return "", 0.0, 0.0, "hors_extrait"
    d = min(float(b[0]) for b in gardes)
    f = max(float(b[1]) if b[1] is not None else fin for b in gardes)
    return " ".join(b[2] for b in gardes), max(debut, d), min(fin, f), ""


# ---------------------------------------------------------------------------
# Un moteur, dans son propre processus
# ---------------------------------------------------------------------------

def _emettre(donnees: dict) -> None:
    try:
        sys.__stdout__.write(MARQUE + json.dumps(donnees, ensure_ascii=False) + "\n")
        sys.__stdout__.flush()
    except Exception:
        pass


def executer_moteur(parametres: dict) -> dict:
    """
    Corps d'un passage : charge un moteur, transcrit l'extrait, écrit les
    segments dans un fichier local. Tourne dans le processus travailleur.
    """
    from . import config as config_module, energie, reglage_machine, vocabulaire

    resultat: dict = {"moteur": parametres.get("moteur"), "etat": "erreur"}
    try:
        import psutil  # type: ignore

        processus = psutil.Process()
        if os.environ.get("SCRIBOUILLE_BANC_PRIORITE_BASSE"):
            processus.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        processus = None

    config = config_module.charger()
    mat = materiel.detecter()
    reglage_machine.appliquer_au_materiel(config, mat)
    energie.desactiver_bridage()

    cle_preset = parametres.get("preset") or "qualite"
    reglages = config_module.reglages_effectifs({**config, "preset": cle_preset, "mode_avance": False})
    reglages["lot"] = presets.taille_lot(cle_preset, mat)
    impose = reglage_machine.lot_impose(config, mat)
    if impose is not None and reglages["lot"]:
        reglages["lot"] = impose
    modele = reglages["modele"]
    langue = str(parametres.get("langue") or config.get("langue", "fr"))

    if parametres.get("moteur") == "openvino":
        from . import moteur_openvino

        if not moteur_openvino.installe():
            resultat["etat"] = "openvino_absent"
            return resultat
        peripherique = str(parametres.get("peripherique") or "CPU").upper()
        instance = moteur_openvino.MoteurOpenVINO(mat, peripherique)
        reglages["faisceau_openvino"] = int(parametres.get("faisceau_openvino") or 1)
        modele_charge = modele
        resultat["peripherique"] = peripherique
        resultat["faisceau"] = reglages["faisceau_openvino"]
    else:
        moteur.limiter_parallelisme(mat.fils_calcul)
        instance = moteur.MoteurTranscription(mat)
        if parametres.get("faisceau_ct2"):
            reglages["beam_size"] = reglages["best_of"] = int(parametres["faisceau_ct2"])
        modele_charge = modele
        resultat["peripherique"] = instance.peripherique
        resultat["faisceau"] = int(reglages["beam_size"])
        resultat["lot"] = int(reglages["lot"] or 0)
        resultat["fils"] = mat.fils_calcul
        resultat["contexte"] = bool(reglages.get("condition_on_previous_text")) and not reglages["lot"]

    signal = np.load(parametres["extrait"])
    duree = signal.size / 16000

    debut = time.perf_counter()
    instance.charger(modele_charge,
                     lambda niveau, texte: journal.info("comparaison : %s", texte))
    chargement = time.perf_counter() - debut

    amorce = {"amorce": "", "nb_retenus": 0, "jetons": 0, "tronque": False}
    if parametres.get("glossaire", True) and (config.get("utiliser_glossaire", True)
                                              or parametres.get("fichier_glossaire")):
        contenu = None
        if parametres.get("fichier_glossaire"):
            contenu = Path(parametres["fichier_glossaire"]).read_text(encoding="utf-8-sig")
        amorce = vocabulaire.construire_amorce(contenu, tokeniseur=instance.tokeniseur, langue=langue)

    temps_cpu = sum(processus.cpu_times()[:2]) if processus is not None else 0.0
    debut = time.perf_counter()
    segments, details = instance.transcrire(signal, duree, langue, reglages, amorce=amorce["amorce"])
    calcul = time.perf_counter() - debut
    if processus is not None:
        temps_cpu = sum(processus.cpu_times()[:2]) - temps_cpu
    instance.liberer()

    remplacements = 0
    if parametres.get("corrections", True) and config.get("appliquer_corrections", True):
        regles, _erreurs = vocabulaire.analyser_corrections()
        for segment in segments:
            segment.texte, nombre = vocabulaire.appliquer(segment.texte, regles)
            remplacements += nombre

    donnees = [{"d": round(s.debut, 3), "f": round(s.fin, 3), "t": s.texte,
                "m": [[m.texte, round(m.debut, 3), round(m.fin, 3), round(m.probabilite, 4)]
                      for m in s.mots]} for s in segments]
    Path(parametres["sortie"]).write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    pic = getattr(processus.memory_info(), "peak_wset", 0) / 1024 ** 3 if processus else 0.0
    resultat.update({
        "etat": "ok",
        "modele": moteur.nom_court(modele),
        "type_calcul": details.get("type_calcul", ""),
        "langue": details.get("langue", langue),
        "duree_audio": round(duree, 2),
        "chargement_s": round(chargement, 1),
        "calcul_s": round(calcul, 2),
        "processeur_s": round(temps_cpu, 1),
        "memoire_go": round(pic, 2),
        "termes_amorce": int(amorce.get("nb_retenus") or 0),
        "jetons_amorce": int(amorce.get("jetons") or 0),
        "amorce_tronquee": bool(amorce.get("tronque")),
        "remplacements": remplacements,
        "fenetres_plafond": int(details.get("fenetres_plafond") or 0),
    })
    return resultat


def principal_moteur(argument: str) -> int:
    try:
        parametres = json.loads(argument)
    except (TypeError, ValueError):
        _emettre({"etat": "erreur", "erreur": "paramètres illisibles"})
        return 2
    try:
        _emettre(executer_moteur(parametres))
        return 0
    except Exception as exc:
        journal.exception("Comparaison : passage en échec", exc)
        _emettre({"moteur": parametres.get("moteur"), "etat": "erreur",
                  "erreur": f"{type(exc).__name__}: {exc}"[:300]})
        return 1


def commande_moteur(parametres: dict) -> tuple[list[str], str]:
    charge = json.dumps(parametres, ensure_ascii=False)
    if chemins.EST_GELE:
        dossier = Path(sys.executable).resolve().parent
        console = dossier / "scribouille-verifier.exe"
        exe = console if console.is_file() else Path(sys.executable)
        return [str(exe), "--comparer-essai", charge], str(dossier)
    racine = Path(__file__).resolve().parent.parent
    python = racine / ".venv" / "Scripts" / "python.exe"
    interprete = str(python) if python.exists() else sys.executable
    return [interprete, "-m", "app.comparaison", "--comparer-essai", charge], str(racine)


def lancer_moteur(parametres: dict, delai: float,
                  interrompu: Callable[[], bool] | None = None) -> dict:
    from .banc import _arreter

    commande, dossier = commande_moteur(parametres)
    debut = time.time()
    try:
        processus = subprocess.Popen(
            commande, cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
    except OSError as exc:
        return {"moteur": parametres.get("moteur"), "etat": "erreur", "erreur": str(exc)}
    import queue
    import threading

    lignes: "queue.Queue[str | None]" = queue.Queue()

    def lire() -> None:
        for ligne in processus.stdout or []:
            lignes.put(ligne)
        lignes.put(None)

    threading.Thread(target=lire, daemon=True).start()
    resultat: dict = {}
    while True:
        if interrompu is not None and interrompu():
            _arreter(processus)
            return {"moteur": parametres.get("moteur"), "etat": "annule"}
        if time.time() - debut > delai:
            _arreter(processus)
            return {"moteur": parametres.get("moteur"), "etat": "delai",
                    "erreur": f"plus de {int(delai)} s"}
        try:
            ligne = lignes.get(timeout=0.5)
        except Exception:
            continue
        if ligne is None:
            break
        if ligne.startswith(MARQUE):
            try:
                resultat = json.loads(ligne[len(MARQUE):])
            except ValueError:
                pass
        elif ligne.strip():
            journal.debug("comparaison : %s", ligne.rstrip()[:300])
    processus.wait()
    if not resultat:
        resultat = {"moteur": parametres.get("moteur"), "etat": "erreur",
                    "erreur": f"processus terminé sans résultat (code {processus.returncode})"}
    return resultat


# ---------------------------------------------------------------------------
# Mesures
# ---------------------------------------------------------------------------

def _pct(partie: float, total: float) -> float:
    return round(100.0 * partie / total, 1) if total else 0.0


def _occurrences(mots: list[str], terme: list[str]) -> int:
    if not terme:
        return 0
    n, total = len(terme), 0
    for k in range(len(mots) - n + 1):
        if mots[k:k + n] == terme:
            total += 1
    return total


def mesurer(a: Texte, b: Texte, termes: list[str]) -> dict:
    """Chiffres de la comparaison de deux textes, sans un mot du texte."""
    mots_a = [j.mot for j in a.jetons]
    mots_b = [j.mot for j in b.jetons]
    bilan = aligner(mots_a, mots_b)
    passages = bilan.passages()
    repartition = {"un_mot": 0, "plusieurs_mots": 0, "seulement_a": 0, "seulement_b": 0}
    for i1, i2, j1, j2 in passages:
        la, lb = i2 - i1, j2 - j1
        # Un passage où un moteur a au moins quatre mots de plus que l'autre
        # est un morceau de phrase entendu par un seul des deux.
        if max(la, lb) == 1:
            repartition["un_mot"] += 1
        elif la - lb >= MOTS_SEGMENT:
            repartition["seulement_a"] += 1
        elif lb - la >= MOTS_SEGMENT:
            repartition["seulement_b"] += 1
        else:
            repartition["plusieurs_mots"] += 1

    # Écarts d'horodatage sur les mots identiques, regroupés en zones.
    ecarts, zones, dans_zone = 0, 0, False
    for op, i1, _i2, j1, _j2 in bilan.operations:
        if op != "egal":
            continue
        loin = abs(a.jetons[i1].debut - b.jetons[j1].debut) > ECART_HORODATAGE_S
        if loin:
            ecarts += 1
            if not dans_zone:
                zones += 1
        dans_zone = loin
    egaux = sum(1 for o in bilan.operations if o[0] == "egal")

    # Mots incertains de a (CTranslate2) et passages divergents.
    divergents = bilan.divergents_a()
    affiches_divergents = {a.jetons[i].affiche for i in divergents}
    incertains: dict[int, float] = {}
    for jeton in a.jetons:
        if jeton.probabilite is not None and jeton.probabilite < SEUIL_INCERTAIN:
            incertains[jeton.affiche] = jeton.probabilite
    affiches_a = {j.affiche for j in a.jetons}
    incertains_divergents = sum(1 for k in incertains if k in affiches_divergents)
    avec_confiance_b = sum(1 for j in b.jetons if j.probabilite is not None)

    termes_norm = [(t, normaliser(t)) for t in termes]
    glossaire = {}
    for cle, mots in (("a", mots_a), ("b", mots_b)):
        trouves = [t for t, n in termes_norm if _occurrences(mots, n)]
        glossaire[cle] = {"termes": len(trouves),
                          "occurrences": sum(_occurrences(mots, n) for _t, n in termes_norm)}

    def stats_segments(texte: Texte) -> dict:
        durees = [max(0.0, f - d) for d, f in texte.segments]
        return {"nombre": len(durees),
                "mediane_s": round(statistics.median(durees), 1) if durees else 0.0,
                "max_s": round(max(durees), 1) if durees else 0.0}

    return {
        "bilan": bilan,
        "mots_a": len(mots_a), "mots_b": len(mots_b),
        "desaccord_a": bilan.taux("a"), "desaccord_b": bilan.taux("b"),
        "substitutions": bilan.substitutions, "suppressions": bilan.suppressions,
        "insertions": bilan.insertions,
        "passages": len(passages), "repartition": repartition,
        "ecarts_horodatage": ecarts, "zones_horodatage": zones, "mots_egaux": egaux,
        "incertains": len(incertains), "incertains_divergents": incertains_divergents,
        "part_divergente_a": _pct(len(affiches_divergents), len(affiches_a)),
        "confiance_b": avec_confiance_b,
        "glossaire": glossaire, "termes_glossaire": len(termes),
        "anglais_a": nombre_mots_anglais(mots_a), "anglais_b": nombre_mots_anglais(mots_b),
        "segments_a": stats_segments(a), "segments_b": stats_segments(b),
    }


def mesurer_reference(ref_mots: list[str], texte: Texte, debut: float, fin: float,
                      termes: list[str]) -> dict:
    """Taux d'erreur d'un moteur sur la fenêtre couverte par la référence."""
    mots = [j.mot for j in texte.jetons if debut - 0.3 <= (j.debut + j.fin) / 2 <= fin + 0.3]
    bilan = aligner(ref_mots, mots)
    rappel_num, rappel_den = 0, 0
    for terme in termes:
        forme = normaliser(terme)
        attendu = _occurrences(ref_mots, forme)
        if attendu:
            rappel_den += attendu
            rappel_num += min(attendu, _occurrences(mots, forme))
    return {"wer": bilan.taux("a"), "sub": bilan.substitutions, "sup": bilan.suppressions,
            "ins": bilan.insertions, "mots": len(mots), "bilan": bilan,
            "glossaire_attendus": rappel_den, "glossaire_retrouves": rappel_num,
            "anglais": nombre_mots_anglais(mots)}


# ---------------------------------------------------------------------------
# Page côte à côte (contient la transcription : reste sur le poste)
# ---------------------------------------------------------------------------

def _hms(secondes: float) -> str:
    secondes = max(0, int(secondes))
    h, reste = divmod(secondes, 3600)
    m, s = divmod(reste, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _lignes_affichage(a: Texte, b: Texte, bilan: Bilan) -> list[dict]:
    """
    Lignes du tableau : une par segment de CTranslate2, les mots d'OpenVINO
    rangés en face de ceux auxquels l'alignement les rattache.
    """
    lignes: list[dict] = []
    ligne_de_a: dict[int, int] = {}

    def nouvelle(segment: int | None) -> dict:
        lignes.append({"segment": segment, "a": [], "b": [], "ref": [], "debut": None})
        return lignes[-1]

    courante: dict | None = None
    for op, i1, _i2, j1, _j2 in bilan.operations:
        if op in ("egal", "sub", "sup"):
            seg = a.jetons[i1].segment
            if courante is None or courante["segment"] != seg:
                courante = nouvelle(seg)
            courante["a"].append(i1)
            ligne_de_a[i1] = len(lignes) - 1
            if courante["debut"] is None:
                courante["debut"] = a.jetons[i1].debut
        if op in ("egal", "sub", "ins"):
            if courante is None:
                courante = nouvelle(None)
            courante["b"].append(j1)
            if courante["debut"] is None:
                courante["debut"] = b.jetons[j1].debut
    return lignes, ligne_de_a  # type: ignore[return-value]


def _mots_html(texte: Texte, indices: list[int], divergents: set[int],
               erreurs_ref: set[int] | None, incertitude: bool) -> str:
    """Mots affichés d'une colonne, surlignés selon leurs jetons."""
    par_affiche: dict[int, list[int]] = {}
    ordre: list[int] = []
    for i in indices:
        k = texte.jetons[i].affiche
        if k not in par_affiche:
            par_affiche[k] = []
            ordre.append(k)
        par_affiche[k].append(i)
    morceaux = []
    for k in ordre:
        jetons = par_affiche[k]
        classes = []
        titre = ""
        if any(i in divergents for i in jetons):
            classes.append("diff")
        if erreurs_ref is not None and any(i in erreurs_ref for i in jetons):
            classes.append("err")
        if incertitude:
            probas = [texte.jetons[i].probabilite for i in jetons
                      if texte.jetons[i].probabilite is not None]
            if probas and min(probas) < SEUIL_INCERTAIN:
                classes.append("doute")
                titre = f' title="p = {min(probas):.2f}"'
        mot = html.escape(texte.affiches[k])
        morceaux.append(f'<span class="{" ".join(classes)}"{titre}>{mot}</span>' if classes else mot)
    return " ".join(morceaux)


def rediger_page(source: Path, debut: float, a: Texte, b: Texte, mesures: dict,
                 ref_mots: list[str] | None, ref_texte: str, ref_bilans: dict | None,
                 info_a: dict, info_b: dict) -> str:
    t = langues.t
    bilan: Bilan = mesures["bilan"]
    lignes, ligne_de_a = _lignes_affichage(a, b, bilan)
    div_a, div_b = bilan.divergents_a(), bilan.divergents_b()

    # Référence : chaque mot rangé sur la ligne du mot de CTranslate2 en face.
    ref_affiches: list[str] = []
    erreurs_a = erreurs_b = None
    if ref_mots is not None and ref_bilans:
        bil_a: Bilan = ref_bilans["a"]["bilan"]
        bil_b: Bilan = ref_bilans["b"]["bilan"]
        # Les jetons comparés à la référence sont ceux de la fenêtre : on
        # retrouve leurs rangs dans le texte entier.
        rangs_a = ref_bilans["a"]["rangs"]
        rangs_b = ref_bilans["b"]["rangs"]
        erreurs_a = {rangs_a[o[3]] for o in bil_a.operations if o[0] in ("sub", "ins")}
        erreurs_b = {rangs_b[o[3]] for o in bil_b.operations if o[0] in ("sub", "ins")}
        rate_ref = {o[1] for o in bil_a.operations if o[0] in ("sub", "sup")} & \
                   {o[1] for o in bil_b.operations if o[0] in ("sub", "sup")}
        ancre = 0
        for op, i1, _i2, j1, _j2 in bil_a.operations:
            if op in ("egal", "sub"):
                ancre = ligne_de_a.get(rangs_a[j1], ancre)
            if op in ("egal", "sub", "sup") and lignes:
                ligne = lignes[min(ancre, len(lignes) - 1)]
                classe = ' class="err"' if i1 in rate_ref else ""
                ligne["ref"].append(f"<span{classe}>{html.escape(ref_mots[i1])}</span>")
        ref_affiches = ref_mots

    lignes_html = []
    for ligne in lignes:
        a_html = _mots_html(a, ligne["a"], div_a, erreurs_a, True)
        b_html = _mots_html(b, ligne["b"], div_b, erreurs_b, False)
        differe = any(i in div_a for i in ligne["a"]) or any(j in div_b for j in ligne["b"])
        instant = debut + float(ligne["debut"] or 0.0)
        cellule_ref = f'<td class="ref">{" ".join(ligne["ref"])}</td>' if ref_affiches else ""
        lignes_html.append(
            f'<tr class="{"d" if differe else "s"}"><td class="h"><a href="#" data-t="{instant:.2f}">'
            f'{_hms(instant)}</a></td>{cellule_ref}<td>{a_html}</td><td>{b_html}</td></tr>')

    entete_ref = f"<th>{html.escape(t('comp.page.reference'))}</th>" if ref_affiches else ""
    legende = t("comp.page.legende") + (" " + t("comp.page.legende_ref") if ref_affiches else "")
    try:
        audio = Path(source).resolve().as_uri()
    except ValueError:
        audio = ""
    nom_b = t("comp.moteur.openvino", peripherique=info_b.get("peripherique", "?"))
    return f"""<!doctype html>
<html lang="{langues.courante()}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(t('comp.page.titre'))}</title>
<style>
:root {{ --fond:#fbfbf8; --texte:#1d1d1b; --doux:#6b6b66; --trait:#deded8; --diff:#ffe9a8; --err:#c0392b; --doute:#7a7a74; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fond:#1b1c1e; --texte:#e8e8e3; --doux:#9a9a94; --trait:#33353a; --diff:#5a4a12; --err:#ff7b6b; --doute:#a8a8a2; }} }}
body {{ background:var(--fond); color:var(--texte); font:15px/1.5 system-ui, sans-serif; margin:0 auto; padding:16px; max-width:1500px; }}
h1 {{ font-size:20px; margin:0 0 4px; }}
.meta {{ color:var(--doux); font-size:13px; margin-bottom:10px; }}
.barre {{ position:sticky; top:0; background:var(--fond); padding:8px 0; border-bottom:1px solid var(--trait); z-index:2; display:flex; gap:16px; flex-wrap:wrap; align-items:center; }}
audio {{ height:32px; max-width:100%; }}
table {{ border-collapse:collapse; width:100%; table-layout:fixed; }}
th, td {{ border-bottom:1px solid var(--trait); padding:6px 8px; vertical-align:top; text-align:left; }}
th {{ font-size:13px; color:var(--doux); }}
td.h, th.h {{ width:76px; font-variant-numeric:tabular-nums; }}
td.h a {{ color:var(--doux); text-decoration:none; }}
.diff {{ background:var(--diff); border-radius:3px; }}
.err {{ text-decoration:underline wavy var(--err); text-underline-offset:3px; }}
.doute {{ border-bottom:2px dotted var(--doute); }}
td.ref {{ color:var(--doux); }}
body.seulement tr.s {{ display:none; }}
.legende {{ font-size:13px; color:var(--doux); }}
</style></head><body>
<h1>{html.escape(t('comp.page.titre'))}</h1>
<div class="meta">{html.escape(Path(source).name)} · {_hms(debut)} → {_hms(debut + mesures.get('duree', 0))} ·
{html.escape(t('comp.page.confidentiel'))}</div>
<div class="barre">
<label><input type="checkbox" id="seulement"> {html.escape(t('comp.page.seulement'))}</label>
{f'<audio id="lecteur" controls preload="none" src="{html.escape(audio)}"></audio>' if audio else ''}
<span class="legende">{legende}</span>
</div>
<table><thead><tr><th class="h"></th>{entete_ref}<th>{html.escape(t('comp.moteur.ct2'))}</th><th>{html.escape(nom_b)}</th></tr></thead>
<tbody>
{chr(10).join(lignes_html)}
</tbody></table>
<script>
document.getElementById('seulement').addEventListener('change', function (e) {{
  document.body.classList.toggle('seulement', e.target.checked);
}});
document.querySelectorAll('td.h a').forEach(function (a) {{
  a.addEventListener('click', function (e) {{
    e.preventDefault();
    var l = document.getElementById('lecteur');
    if (!l) return;
    l.currentTime = Math.max(0, parseFloat(a.dataset.t) - 1);
    l.play();
  }});
}});
</script>
</body></html>
"""


# ---------------------------------------------------------------------------
# Rapport de chiffres (transmissible : aucun mot de la transcription)
# ---------------------------------------------------------------------------

def rediger_rapport(mat, duree: float, debut: float, info_a: dict, info_b: dict,
                    mesures: dict | None, ref: dict | None, options: dict) -> str:
    from .banc import _alimentation, _masquer

    t = langues.t
    n = langues.nombre
    lignes = [t("comp.rapport.titre", nom=NOM_APPLICATION, version=VERSION,
                date=datetime.now().strftime("%Y-%m-%d")), ""]
    lignes.append(t("comp.rapport.section.extrait"))
    lignes.append("  - " + t("comp.rapport.extrait", duree=n(duree / 60, 1),
                             debut=_hms(debut)))
    lignes.append("  - " + t("comp.rapport.reglages", langue=options.get("langue", "?"),
                             preset=presets.nom_preset(options.get("preset", "qualite")),
                             glossaire=t("comp.oui") if options.get("glossaire") else t("comp.non"),
                             corrections=t("comp.oui") if options.get("corrections") else t("comp.non")))
    lignes.append("  - " + t("comp.rapport.machine", processeur=mat.cpu_nom or "?",
                             memoire=f"{mat.ram_go:.0f}", alimentation=_alimentation()))
    lignes.append("")
    lignes.append(t("comp.rapport.section.vitesse"))
    for cle, info in (("ct2", info_a), ("ov", info_b)):
        nom = t("comp.moteur.ct2") if cle == "ct2" else t(
            "comp.moteur.openvino", peripherique=info.get("peripherique", "?"))
        if info.get("etat") != "ok":
            lignes.append("  - " + t("comp.rapport.echec", moteur=nom,
                                     etat=info.get("etat", "?"), detail=info.get("erreur", "")))
            continue
        lignes.append("  - " + t(
            "comp.rapport.vitesse", moteur=nom, modele=info.get("modele", "?"),
            calcul=n(info.get("calcul_s", 0), 1), facteur=n(info.get("calcul_s", 0) / max(1e-9, duree), 2),
            chargement=n(info.get("chargement_s", 0), 1), memoire=n(info.get("memoire_go", 0), 1)))
        detail = t("comp.rapport.detail_ct2", faisceau=info.get("faisceau", "?"),
                   lots=info.get("lot") or t("comp.un_a_un"), fils=info.get("fils", "?"),
                   type_calcul=info.get("type_calcul", "?")) if cle == "ct2" else t(
            "comp.rapport.detail_ov", faisceau=info.get("faisceau", "?"),
            type_calcul=info.get("type_calcul", "?"),
            plafond=info.get("fenetres_plafond", 0))
        lignes.append("      " + detail)
        lignes.append("      " + t("comp.rapport.amorce", termes=info.get("termes_amorce", 0),
                                   jetons=info.get("jetons_amorce", 0),
                                   remplacements=info.get("remplacements", 0)))
    if info_a.get("etat") == "ok" and info_b.get("etat") == "ok" and info_b.get("calcul_s"):
        lignes.append("  - " + t("comp.rapport.rapport_vitesse",
                                 rapport=n(info_a["calcul_s"] / max(1e-9, info_b["calcul_s"]), 2)))

    if mesures:
        m = mesures
        lignes += ["", t("comp.rapport.section.accord")]
        lignes.append("  - " + t("comp.rapport.mots", a=m["mots_a"], b=m["mots_b"]))
        lignes.append("  - " + t("comp.rapport.desaccord", a=n(m["desaccord_a"], 1),
                                 b=n(m["desaccord_b"], 1), sub=m["substitutions"],
                                 sup=m["suppressions"], ins=m["insertions"]))
        r = m["repartition"]
        lignes.append("  - " + t("comp.rapport.passages", n=m["passages"]))
        lignes.append("      " + t("comp.rapport.repartition", un=r["un_mot"],
                                   plusieurs=r["plusieurs_mots"], seul_a=r["seulement_a"],
                                   seul_b=r["seulement_b"], mots=MOTS_SEGMENT))
        lignes.append("  - " + t("comp.rapport.horodatage", n=m["ecarts_horodatage"],
                                 egaux=m["mots_egaux"], zones=m["zones_horodatage"],
                                 seuil=n(ECART_HORODATAGE_S, 0)))
        sa, sb = m["segments_a"], m["segments_b"]
        lignes.append("  - " + t("comp.rapport.segments", na=sa["nombre"], nb=sb["nombre"],
                                 ma=n(sa["mediane_s"], 1), mb=n(sb["mediane_s"], 1),
                                 xa=n(sa["max_s"], 1), xb=n(sb["max_s"], 1)))
        g = m["glossaire"]
        lignes.append("  - " + t("comp.rapport.glossaire", total=m["termes_glossaire"],
                                 ta=g["a"]["termes"], oa=g["a"]["occurrences"],
                                 tb=g["b"]["termes"], ob=g["b"]["occurrences"]))
        lignes.append("  - " + t("comp.rapport.anglais", a=m["anglais_a"], b=m["anglais_b"],
                                 liste=len(MOTS_ANGLAIS)))
        lignes.append("  - " + t("comp.rapport.incertains", n=m["incertains"],
                                 seuil=n(SEUIL_INCERTAIN, 2),
                                 div=m["incertains_divergents"],
                                 pct=n(_pct(m["incertains_divergents"], m["incertains"]), 0),
                                 base=n(m["part_divergente_a"], 0)))
        if not m["confiance_b"]:
            lignes.append("      " + t("comp.rapport.confiance_ov"))

    lignes += ["", t("comp.rapport.section.reference")]
    if not ref:
        lignes.append("  - " + t("comp.rapport.sans_reference"))
    elif ref.get("motif"):
        lignes.append("  - " + t(f"comp.ref.{ref['motif']}"))
    else:
        lignes.append("  - " + t("comp.rapport.ref_fenetre", couvert=n(ref["couverture_s"] / 60, 1),
                                 duree=n(duree / 60, 1), mots=ref["mots"], format=ref["format"]))
        for cle, nom in (("a", t("comp.moteur.ct2")),
                         ("b", t("comp.moteur.openvino", peripherique=info_b.get("peripherique", "?")))):
            if cle not in ref:
                continue
            r = ref[cle]
            lignes.append("  - " + t("comp.rapport.ref_wer", moteur=nom, wer=n(r["wer"], 1),
                                     sub=r["sub"], sup=r["sup"], ins=r["ins"]))
            if r["glossaire_attendus"]:
                lignes.append("      " + t("comp.rapport.ref_glossaire",
                                           retrouves=r["glossaire_retrouves"],
                                           attendus=r["glossaire_attendus"]))
            lignes.append("      " + t("comp.rapport.ref_anglais", n=r["anglais"],
                                       ref=ref["anglais"]))
        lignes.append("  - " + t("comp.rapport.ref_biais"))
    lignes += ["", t("comp.rapport.lecture"), t("comp.rapport.remarque")]
    return _masquer("\n".join(lignes)) + "\n"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

#: Recherche d'une pause aux bords d'un extrait, en secondes au plus.
CALAGE_MAX_S = 20.0


def caler_sur_pauses(signal: np.ndarray, debut_fichier: bool, fin_fichier: bool) -> tuple[int, int]:
    """
    Bornes de l'extrait ramenées sur des pauses : (premier, dernier) échantillon.

    Un extrait coupé au milieu d'une phrase n'est pas une situation réelle (un
    enregistrement commence et finit par un silence ou presque), et il trompe
    les deux moteurs : sur une phrase commencée, le faisceau de CTranslate2 a
    sauté tout le début de la première fenêtre (constaté sur un extrait de test).
    On avance donc le début jusqu'à la première pause et l'on recule la fin
    jusqu'à la dernière, dans la limite de 20 s. Les bords du fichier, eux, ne
    bougent pas.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    total = signal.size
    if total < 16000 * 3 * CALAGE_MAX_S:
        return 0, total
    passages = get_speech_timestamps(signal, VadOptions(min_silence_duration_ms=300,
                                                        speech_pad_ms=0), sampling_rate=16000)
    if not passages:
        return 0, total
    limite = int(CALAGE_MAX_S * 16000)
    premier, dernier = 0, total
    if not debut_fichier and passages[0]["start"] < 1600:
        # Parole déjà en cours à la coupure : début au milieu de la pause qui suit.
        for avant, apres in zip(passages, passages[1:]):
            if avant["end"] > limite:
                break
            premier = (avant["end"] + apres["start"]) // 2
            break
    if not fin_fichier and passages[-1]["end"] > total - 1600:
        for avant, apres in zip(reversed(passages[:-1]), reversed(passages)):
            if total - apres["start"] > limite:
                break
            dernier = (avant["end"] + apres["start"]) // 2
            break
    if dernier <= premier:
        return 0, total
    return int(premier), int(dernier)


def peripherique_openvino_conseille() -> str:
    """Puce graphique Intel si OpenVINO la voit, sinon processeur."""
    from . import moteur_openvino

    if not moteur_openvino.installe():
        return ""
    vus = moteur_openvino.peripheriques_disponibles()
    return "GPU" if "GPU" in vus else "CPU"


def executer(fichier: str, debut: float = 0.0, duree: float = 0.0, reference: str = "",
             sortie: str = "", peripherique: str = "", preset: str = "qualite",
             faisceau_openvino: int = 1, faisceau_ct2: int = 0, glossaire: bool = True,
             corrections: bool = True, fichier_glossaire: str = "",
             rappel: Callable[[dict], None] | None = None,
             interrompu: Callable[[], bool] | None = None) -> dict:
    """Mène la comparaison complète et renvoie {rapport, page, rapport_fichier, dossier}."""
    from . import energie

    # Une comparaison dure de quinze à quarante minutes : la mise en veille du
    # poste la suspendrait (constaté : lancée à 18 h 40, démarrée à 22 h 56).
    with energie.sans_veille():
        return _executer(fichier, debut, duree, reference, sortie, peripherique, preset,
                         faisceau_openvino, faisceau_ct2, glossaire, corrections,
                         fichier_glossaire, rappel, interrompu)


def _executer(fichier: str, debut: float, duree: float, reference: str, sortie: str,
              peripherique: str, preset: str, faisceau_openvino: int, faisceau_ct2: int,
              glossaire: bool, corrections: bool, fichier_glossaire: str,
              rappel: Callable[[dict], None] | None,
              interrompu: Callable[[], bool] | None) -> dict:
    from . import audio, config as config_module, moteur_openvino, vocabulaire

    def dire(message: str, pct: int) -> None:
        journal.info("Comparaison : %s", message)
        if rappel:
            rappel({"message": message, "pct": max(0, min(100, pct))})

    source = Path(fichier)
    if not source.is_file():
        raise journal.ErreurLisible(langues.t("audio.introuvable.titre"),
                                    langues.t("audio.introuvable.msg", nom=source.name))
    config = config_module.charger()
    mat = materiel.detecter()
    langue = str(config.get("langue", "fr") or "fr")
    glossaire = glossaire and (bool(config.get("utiliser_glossaire", True)) or bool(fichier_glossaire))
    contenu_glossaire = None
    if fichier_glossaire:
        contenu_glossaire = Path(fichier_glossaire).read_text(encoding="utf-8-sig")
    corrections = corrections and bool(config.get("appliquer_corrections", True))

    if not moteur_openvino.installe():
        raise journal.ErreurLisible(langues.t("comp.openvino_absent.titre"),
                                    langues.t("comp.openvino_absent.msg"))
    peripherique = (peripherique or peripherique_openvino_conseille() or "CPU").upper()

    dossier = Path(sortie) if sortie else DOSSIER_COMPARAISONS / f"comparaison-{datetime.now():%Y%m%d-%H%M%S}"
    dossier.mkdir(parents=True, exist_ok=True)

    # Modèles : ceux du preset, pour les deux moteurs.
    modele = presets.preset(preset)["modele"]
    for depot in (modele, presets.depot_openvino(modele)):
        if moteur.etat_modele(depot)["etat"] != "complet":
            dire(langues.t("comp.etape.telechargement", modele=moteur.nom_court(depot),
                           taille=langues.octets(moteur.poids_attendu_octets(depot))), 2)
            moteur.assurer_modele_telecharge(depot, None, None, annoncer=False)

    duree_fichier = audio.duree(source)
    dire(langues.t("comp.etape.decodage"), 4)
    signal = audio.decoder(source, filtres_salle=bool(config.get("filtres_salle")),
                           debut=debut, duree=duree)
    fin_fichier = not duree or not duree_fichier or debut + signal.size / audio.FREQUENCE >= duree_fichier - 1.0
    premier, dernier = caler_sur_pauses(signal, debut <= 0.5, fin_fichier)
    if (premier, dernier) != (0, signal.size):
        journal.info("Extrait calé sur des pauses : +%.2f s au début, -%.2f s à la fin",
                     premier / audio.FREQUENCE, (signal.size - dernier) / audio.FREQUENCE)
        signal = np.ascontiguousarray(signal[premier:dernier])
        debut += premier / audio.FREQUENCE
    duree_extrait = signal.size / audio.FREQUENCE
    extrait = dossier / "extrait-temporaire.npy"
    np.save(extrait, signal)
    del signal
    # Le calage ne déplace jamais les bords du fichier : le fichier entier le reste.
    extrait_complet = debut <= 0.5 and fin_fichier

    delai = max(900.0, 4.0 * duree_extrait + 600.0)
    commun = {"extrait": str(extrait), "langue": langue, "preset": preset,
              "glossaire": glossaire, "corrections": corrections,
              "fichier_glossaire": str(fichier_glossaire or "")}
    infos: dict[str, dict] = {}
    textes: dict[str, Texte] = {}
    try:
        for cle, moteur_nom, pct in (("a", "ctranslate2", 10), ("b", "openvino", 50)):
            if interrompu and interrompu():
                break
            nom = langues.t("comp.moteur.ct2") if cle == "a" else langues.t(
                "comp.moteur.openvino", peripherique=peripherique)
            dire(langues.t("comp.etape.moteur", moteur=nom,
                           duree=presets.formater_duree(duree_extrait)), pct)
            # Segments horodatés, mots compris : gardés à côté de la page, dans le
            # même dossier local (ils ne contiennent rien de plus qu'elle), pour
            # une relecture ou une analyse ultérieure.
            fichier_segments = dossier / f"textes-{moteur_nom}.json"
            parametres = {**commun, "moteur": moteur_nom, "sortie": str(fichier_segments),
                          "peripherique": peripherique, "faisceau_openvino": faisceau_openvino,
                          "faisceau_ct2": faisceau_ct2}
            infos[cle] = lancer_moteur(parametres, delai, interrompu)
            if infos[cle].get("etat") == "ok" and fichier_segments.is_file():
                textes[cle] = construire_texte(json.loads(fichier_segments.read_text(encoding="utf-8")))
    finally:
        extrait.unlink(missing_ok=True)

    dire(langues.t("comp.etape.analyse"), 92)
    termes = vocabulaire.termes(contenu_glossaire) if glossaire else []
    mesures = None
    if "a" in textes and "b" in textes:
        mesures = mesurer(textes["a"], textes["b"], termes)
        mesures["duree"] = duree_extrait

    ref_infos = None
    ref_mots = None
    ref_bilans = None
    if reference:
        ref_infos = {}
        try:
            lue = lire_reference(reference)
            texte_ref, d_ref, f_ref, motif = reference_sur_extrait(
                lue, debut, debut + duree_extrait, extrait_complet)
        except (OSError, ValueError) as exc:
            journal.attention("Référence illisible : %s", exc)
            texte_ref, d_ref, f_ref, motif, lue = "", 0.0, 0.0, "illisible", None
        if motif:
            ref_infos["motif"] = motif
        else:
            ref_mots = normaliser(texte_ref)
            ref_infos.update({"couverture_s": f_ref - d_ref, "mots": len(ref_mots),
                              "format": lue.format if lue else "?",
                              "anglais": nombre_mots_anglais(ref_mots)})
            ref_bilans = {}
            for cle, texte in textes.items():
                fenetre = mesurer_reference(ref_mots, texte, d_ref - debut, f_ref - debut, termes)
                rangs = [k for k, j in enumerate(texte.jetons)
                         if d_ref - debut - 0.3 <= (j.debut + j.fin) / 2 <= f_ref - debut + 0.3]
                fenetre["rangs"] = rangs
                ref_bilans[cle] = fenetre
                ref_infos[cle] = fenetre

    options = {"langue": langue, "preset": preset, "glossaire": glossaire,
               "corrections": corrections}
    rapport = rediger_rapport(mat, duree_extrait, debut, infos.get("a", {}), infos.get("b", {}),
                              mesures, ref_infos, options)
    fichier_rapport = dossier / "rapport-chiffres.txt"
    fichier_rapport.write_text(rapport, encoding="utf-8")
    fichier_page = ""
    if mesures:
        page = rediger_page(source, debut, textes["a"], textes["b"], mesures, ref_mots,
                            "", ref_bilans if ref_bilans and len(ref_bilans) == 2 else None,
                            infos["a"], infos["b"])
        cible = dossier / "cote-a-cote.html"
        cible.write_text(page, encoding="utf-8")
        fichier_page = str(cible)
    # Données brutes pour un usage ultérieur : chiffres seulement.
    (dossier / "mesures.json").write_text(json.dumps({
        "duree_extrait": duree_extrait, "debut": debut, "moteurs": infos,
        "comparaison": {k: v for k, v in (mesures or {}).items() if k != "bilan"},
        "reference": {k: ({kk: vv for kk, vv in v.items() if kk not in ("bilan", "rangs")}
                          if isinstance(v, dict) else v) for k, v in (ref_infos or {}).items()},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dire(langues.t("comp.etape.fini"), 100)
    return {"rapport": rapport, "page": fichier_page, "rapport_fichier": str(fichier_rapport),
            "dossier": str(dossier), "ok": bool(mesures)}


def _valeur(arguments: list[str], option: str, defaut: str = "") -> str:
    if option in arguments:
        rang = arguments.index(option)
        if rang + 1 < len(arguments):
            return arguments[rang + 1]
    return defaut


def principal_cli(arguments: list[str]) -> int:
    if "--comparer-essai" in arguments:
        return principal_moteur(_valeur(arguments, "--comparer-essai"))
    fichier = _valeur(arguments, "--comparer")
    if not fichier:
        print(langues.t("comp.cli.usage"))
        return 2
    try:
        resultat = executer(
            fichier,
            debut=lire_duree(_valeur(arguments, "--debut", "0")),
            duree=lire_duree(_valeur(arguments, "--duree", "0")),
            reference=_valeur(arguments, "--reference"),
            sortie=_valeur(arguments, "--sortie"),
            peripherique=_valeur(arguments, "--peripherique"),
            preset=_valeur(arguments, "--preset", "qualite"),
            faisceau_openvino=int(_valeur(arguments, "--faisceau-openvino", "1") or 1),
            faisceau_ct2=int(_valeur(arguments, "--faisceau-ctranslate2", "0") or 0),
            glossaire="--sans-glossaire" not in arguments,
            corrections="--sans-corrections" not in arguments,
            fichier_glossaire=_valeur(arguments, "--glossaire"),
            rappel=lambda etape: print("  " + etape["message"], flush=True))
    except journal.ErreurLisible as exc:
        print(f"{exc.titre}\n{exc.message}")
        return 1
    print()
    print(resultat["rapport"])
    print(langues.t("comp.cli.fichiers", rapport=resultat["rapport_fichier"],
                    page=resultat["page"] or "-"))
    if "--ouvrir" in arguments and resultat["page"]:
        try:
            os.startfile(resultat["page"])  # type: ignore[attr-defined]
        except Exception:
            import webbrowser

            webbrowser.open(Path(resultat["page"]).as_uri())
    return 0 if resultat["ok"] else 1


def options_reconnues(arguments: list[str]) -> bool:
    return "--comparer" in arguments or "--comparer-essai" in arguments


if __name__ == "__main__":
    sys.exit(principal_cli(sys.argv[1:]))
