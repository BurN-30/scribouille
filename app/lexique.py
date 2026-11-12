"""
Outils de langue du vocabulaire : mots courants, clé phonétique, découpage.

Trois besoins, sans dépendance lourde :

1. Savoir si un mot est un mot COURANT du français. C'est le garde-fou des
   corrections automatiques : une suite de mots courants (« mon entreprise »,
   « pierre ») n'est jamais remplacée sans un contexte qui le justifie. La liste
   vient de FrequencyWords (sous-titres OpenSubtitles 2018, CC BY-SA 4.0) : les
   40 000 formes les plus fréquentes, dans `lexique/fr-courant.txt`. Elle
   contient aussi des prénoms et des noms de séries : un nom propre qui y figure
   est simplement traité avec plus de prudence.

2. Rapprocher ce que le modèle a écrit de ce qui a été dit : une clé
   phonétique simplifiée du français (« Siminov » et « Siminoff », « qui
   bernetes » et « Kubernetes » ont des clés voisines), comparée par distance
   d'édition bornée.

3. Découper un texte en mots repérés par leur position, pour remplacer une
   forme sans toucher à la ponctuation ni à la mise en forme qui l'entourent.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import chemins

FICHIER_LEXIQUE = "fr-courant.txt"

# ---------------------------------------------------------------------------
# Mots courants
# ---------------------------------------------------------------------------

_courants: frozenset[str] | None = None


def _chemin_lexique() -> Path:
    for base in (chemins.DOSSIER_RESSOURCES, Path(__file__).resolve().parent.parent):
        chemin = base / "lexique" / FICHIER_LEXIQUE
        if chemin.is_file():
            return chemin
    return chemins.DOSSIER_RESSOURCES / "lexique" / FICHIER_LEXIQUE


def mots_courants() -> frozenset[str]:
    """Ensemble des mots courants, chargé une fois. Vide si le fichier manque."""
    global _courants
    if _courants is None:
        try:
            lignes = _chemin_lexique().read_text(encoding="utf-8").splitlines()
        except OSError:
            lignes = []
        _courants = frozenset(l.strip() for l in lignes if l.strip() and not l.startswith("#"))
    return _courants


def lexique_disponible() -> bool:
    return bool(mots_courants())


def est_courant(mot: str) -> bool:
    """Le mot (une forme, sans espace) est-il un mot courant du français ?"""
    forme = forme_comparable(mot)
    if not forme:
        return True
    if forme.isdigit():
        return True
    courants = mots_courants()
    if not courants:
        # Sans lexique, la prudence : tout est réputé courant, seules les
        # formes fautives explicites s'appliquent.
        return True
    if forme in courants:
        return True
    # « l'équipe », « peut-être » : chaque morceau compte.
    morceaux = [m for m in re.split(r"['’-]", forme) if m]
    return len(morceaux) > 1 and all(m in courants or len(m) <= 2 for m in morceaux)


#: Civilités : un mot courant qui les suit est un nom (« madame Vallée »).
CIVILITES = frozenset({"m", "mme", "mlle", "monsieur", "madame", "mademoiselle", "dr", "docteur",
                       "maître", "me"})


def tous_courants(mots: list[str]) -> bool:
    return bool(mots) and all(est_courant(m) for m in mots)


# ---------------------------------------------------------------------------
# Formes comparables et découpage
# ---------------------------------------------------------------------------

def forme_comparable(texte: str) -> str:
    """Minuscules, NFC, ligatures dépliées, apostrophe droite, espaces réduits."""
    texte = unicodedata.normalize("NFC", str(texte or "")).lower()
    texte = texte.replace("’", "'").replace("œ", "oe").replace("æ", "ae")
    return " ".join(texte.split())


def sans_accents(texte: str) -> str:
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


_MOT = re.compile(r"\w+", re.UNICODE)


def decouper(texte: str) -> list[tuple[str, int, int]]:
    """Mots d'un texte : (forme comparable, début, fin) en positions de caractères.

    L'apostrophe et le trait d'union séparent les mots, comme la normalisation
    de la comparaison : « l'API » donne « l » et « api ».
    """
    return [(forme_comparable(m.group(0)), m.start(), m.end()) for m in _MOT.finditer(texte or "")]


def mots_de(texte: str) -> list[str]:
    return [m for m, _d, _f in decouper(texte)]


# ---------------------------------------------------------------------------
# Sigles épelés
# ---------------------------------------------------------------------------

_LETTRES = {
    "a": "a", "b": "bé", "c": "cé", "d": "dé", "e": "e", "f": "èf", "g": "gé", "h": "ach",
    "i": "i", "j": "ji", "k": "ka", "l": "èl", "m": "èm", "n": "èn", "o": "o", "p": "pé",
    "q": "ku", "r": "èr", "s": "ès", "t": "té", "u": "u", "v": "vé", "w": "doublevé",
    "x": "ix", "y": "igrec", "z": "zèd",
}


def est_sigle(forme: str) -> bool:
    """« RGPD », « API », « SI2A » : deux à huit lettres capitales, chiffres permis."""
    compact = forme.replace(".", "").replace("-", "")
    return 2 <= len(compact) <= 8 and compact.isupper() and any(c.isalpha() for c in compact)


def epeler(sigle: str) -> str:
    """Le sigle lu lettre à lettre : « RGPD » donne « èr gé pé dé »."""
    return " ".join(_LETTRES.get(c, c) for c in sigle.lower() if c.isalnum())


# ---------------------------------------------------------------------------
# Clé phonétique simplifiée du français
# ---------------------------------------------------------------------------

#: Règles appliquées dans l'ordre, sur un mot en minuscules. Les voyelles sont
#: rangées par classes (A, E, I, O, U, W pour « ou », et les nasales N1 à N3),
#: les consonnes qui se confondent à l'oreille partagent une lettre. Ce n'est
#: pas une transcription phonétique : seulement de quoi dire que deux graphies
#: SONNENT pareil, assez finement pour ne pas tout confondre.
_REGLES = [
    (r"ph", "f"), (r"th", "t"), (r"sch", "C"), (r"sh", "C"), (r"ch(?=[rl])", "k"), (r"ch", "C"),
    (r"ck", "k"), (r"qu", "k"), (r"q", "k"), (r"gn", "N"), (r"gu(?=[eiy])", "g"),
    (r"g(?=[eiyéèê])", "j"), (r"c(?=[eiyéèê])", "s"), (r"ç", "s"), (r"c", "k"),
    (r"x", "ks"), (r"w", "v"), (r"h", ""),
    (r"eau", "O"), (r"au", "O"), (r"ou", "W"), (r"oo", "W"),
    (r"(?:ain|ein|aim|eim)(?![aeiouyéèêAEIOUW]|n|m)", "3"),
    (r"(?:ai|ei|è|ê|ë|é)", "E"), (r"(?:er|ez|et)$", "E"),
    (r"(?:an|am|en|em)(?![aeiouyéèêAEIOUW]|n|m)", "1"),
    (r"(?:on|om)(?![aeiouyéèêAEIOUW]|n|m)", "2"),
    (r"(?:ain|ein|in|im|un|um|yn|ym)(?![aeiouyéèêAEIOUW]|n|m)", "3"),
    (r"y", "i"), (r"[àâä]", "a"), (r"[îï]", "i"), (r"[ôö]", "o"), (r"[ùûü]", "u"),
    (r"(?<=[aeiouAEIOUW123])s(?=[aeiouAEIOUW])", "z"),
    (r"z", "s"),
]
_REGLES_COMPILEES = [(re.compile(motif), remplacement) for motif, remplacement in _REGLES]


@lru_cache(maxsize=65536)
def _cle_mot(mot: str) -> str:
    mot = forme_comparable(mot).replace("'", "")
    mot = re.sub(r"[^a-zàâäçéèêëîïôöùûüÿ]", "", mot)
    if not mot:
        return ""
    # Consonnes finales muettes, puis e muet final.
    mot = re.sub(r"(?<=[a-zéèêëîïôöùûü])(?:ent|es|s|t|d|x|p)$", "", mot) if len(mot) > 3 else mot
    mot = re.sub(r"(?<=.)e$", "", mot) if len(mot) > 2 else mot
    for motif, remplacement in _REGLES_COMPILEES:
        mot = motif.sub(remplacement, mot)
    mot = mot.upper()
    # Lettres doublées réduites.
    return re.sub(r"(.)\1+", r"\1", mot)


def cle_phonetique(texte: str) -> str:
    """Clé phonétique d'un mot ou d'une suite de mots (les espaces disparaissent)."""
    return "".join(_cle_mot(m) for m in mots_de(texte))


def distance(a: str, b: str, plafond: int | None = None) -> int:
    """Distance d'édition (Levenshtein). Au-delà de `plafond`, renvoie plafond + 1."""
    if a == b:
        return 0
    if plafond is not None and abs(len(a) - len(b)) > plafond:
        return plafond + 1
    precedent = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courant = [i]
        minimum = i
        for j, cb in enumerate(b, 1):
            valeur = min(precedent[j] + 1, courant[j - 1] + 1, precedent[j - 1] + (ca != cb))
            courant.append(valeur)
            minimum = min(minimum, valeur)
        if plafond is not None and minimum > plafond:
            return plafond + 1
        precedent = courant
    return precedent[-1]


#: Sous cette longueur de clé, aucun rapprochement : trop de mots sonnent pareil.
CLE_MIN_RAPPROCHEMENT = 4


def tolerance(cle: str) -> int:
    """Écart de clé toléré : -1 (jamais) sous 4 signes, 1 de 4 à 7, puis un quart.

    Le rapprochement ne vise que des formes qui ne sont pas des mots courants
    (voir `vocabulaire_usage`) : un écart d'un son sur quatre reste sûr là où il
    ne le serait pas sur des mots ordinaires."""
    if len(cle) < CLE_MIN_RAPPROCHEMENT:
        return -1
    if len(cle) < 8:
        return 1
    return max(2, len(cle) // 4)
