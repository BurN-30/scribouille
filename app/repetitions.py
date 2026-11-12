"""
Boucles de répétition : les repérer dans un texte, et les couper en dernier recours.

Whisper se met parfois à répéter la même courte suite de mots, fenêtre après
fenêtre (« on va voir on va voir on va voir ... »). Le taux de compression du
texte (seuil 2,4, celui de faster-whisper) attrape les longues boucles, pas une
boucle de trois mots répétée huit fois au milieu d'une fenêtre de 30 s
normale : c'est ce qu'a montré le modèle distillé français sur une réunion
réelle (rapport des modèles, 12/11/2026). D'où ce second détecteur, sur les
mots : une suite de n mots (n de 1 à 8) répétée à l'identique, d'affilée.

Les seuils laissent passer la parole normalement répétitive : « oui oui oui »,
« non non non non », « c'est ça, c'est ça, c'est ça », un compte à voix haute
(vérifié sur toutes les transcriptions des campagnes, voir
`outils/verifier_socle.py`). Une boucle, c'est au moins cinq répétitions d'une
suite d'au moins deux mots, et au moins quinze mots en tout (quinze fois le
même mot pour un mot seul).
"""

from __future__ import annotations

import re

#: Longueur maximale, en mots, de la suite qui se répète.
MOTS_PAR_MOTIF_MAX = 8
#: Répétitions d'affilée au moins, pour une suite de deux mots ou plus.
REPETITIONS_MIN = 5
#: Mots couverts par la boucle au moins (répétitions x longueur de la suite).
MOTS_COUVERTS_MIN = 15

_MOT = re.compile(r"\w+(?:['’-]\w+)*", re.UNICODE)


def _mots(texte: str) -> list[tuple[str, int, int]]:
    """Mots du texte, en minuscules, avec leur place : la ponctuation ne compte pas."""
    return [(m.group(0).lower().replace("’", "'"), m.start(), m.end()) for m in _MOT.finditer(texte or "")]


def boucle_repetee(texte: str) -> dict | None:
    """
    La plus longue boucle du texte, ou None. Renvoie la longueur de la suite
    (`n`), le nombre de répétitions (`fois`), la suite (`motif`) et ses places
    en caractères : début de la deuxième occurrence et fin de la dernière.
    """
    mots = _mots(texte)
    formes = [m[0] for m in mots]
    meilleure: dict | None = None
    for n in range(1, MOTS_PAR_MOTIF_MAX + 1):
        i = 0
        while i + 2 * n <= len(formes):
            motif = formes[i:i + n]
            fois = 1
            while formes[i + fois * n:i + (fois + 1) * n] == motif:
                fois += 1
            couverts = fois * n
            assez = fois >= (MOTS_COUVERTS_MIN if n == 1 else REPETITIONS_MIN) and couverts >= MOTS_COUVERTS_MIN
            if assez and (meilleure is None or couverts > meilleure["couverts"]):
                meilleure = {"n": n, "fois": fois, "motif": motif, "couverts": couverts,
                             "debut_mot": i, "coupe_debut": mots[i + n][1],
                             "coupe_fin": mots[i + couverts - 1][2]}
            i += max(1, couverts - n + 1) if fois > 1 else 1
    return meilleure


def couper_boucles(texte: str) -> tuple[str, int]:
    """
    Dernier recours, quand aucune reprise n'a fait disparaître la boucle : la
    suite répétée est gardée une fois, le reste de la boucle est retiré. Rien
    d'autre n'est touché. Renvoie le texte et le nombre de boucles coupées.
    """
    coupees = 0
    while True:
        boucle = boucle_repetee(texte)
        if boucle is None or coupees >= 10:
            return texte, coupees
        avant, apres = texte[:boucle["coupe_debut"]].rstrip(), texte[boucle["coupe_fin"]:]
        texte = avant + apres
        coupees += 1


def gravite(texte: str, taux_compression: float) -> tuple[int, float]:
    """Pour choisir entre plusieurs essais : mots pris dans une boucle, puis taux de compression."""
    boucle = boucle_repetee(texte)
    return (boucle["couverts"] if boucle else 0, taux_compression)
