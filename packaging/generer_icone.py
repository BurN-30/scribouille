"""
Génère l'icône Windows de Scribouille, sans aucune dépendance.

L'icône reprend l'identité de l'application : le fond sombre de la fenêtre
(#12151b) et les cinq barres de l'onde sonore dans le bleu d'accentuation
(#2f5fe0, éclairci pour rester lisible sur fond sombre à 16 pixels).

Le fichier produit, « packaging/scribouille.ico », est versionné : ce script ne
sert qu'à le régénérer si l'identité visuelle change.

    python packaging/generer_icone.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

DESTINATION = Path(__file__).resolve().parent / "scribouille.ico"

TAILLES = (16, 24, 32, 48, 64, 128, 256)

FOND = (18, 21, 27)          # #12151b, le fond de la fenêtre
BARRE = (127, 157, 255)      # #7f9dff, l'accent de la variante sombre

# Hauteurs relatives des cinq barres, calquées sur l'icône « i-onde » de l'interface.
HAUTEURS = (0.16, 0.52, 0.84, 0.44, 0.16)


def _rayon_du_coin(taille: int) -> float:
    return taille * 0.22


def _dans_le_fond(x: float, y: float, taille: int) -> bool:
    """Carré aux coins arrondis, testé au centre du pixel."""
    r = _rayon_du_coin(taille)
    gauche, haut, droite, bas = 0.0, 0.0, float(taille), float(taille)
    dx = max(gauche + r - x, 0.0, x - (droite - r))
    dy = max(haut + r - y, 0.0, y - (bas - r))
    return dx * dx + dy * dy <= r * r


def _dans_une_barre(x: float, y: float, taille: int) -> bool:
    """
    Cinq barres verticales à bouts arrondis, centrées.

    Une barre est le lieu des points situés à moins d'un demi-trait d'un segment
    vertical : c'est exactement le rendu d'un trait à extrémités rondes.
    """
    marge = taille * 0.2
    utile = taille - 2 * marge
    largeur = utile / 11.0           # 5 traits, 4 espaces d'une fois et demie
    rayon = largeur / 2
    pas = largeur * 2.5

    for index, hauteur in enumerate(HAUTEURS):
        cx = marge + rayon + pas * index
        demi_h = max(hauteur * utile / 2, rayon)
        y0 = taille / 2 - demi_h + rayon
        y1 = taille / 2 + demi_h - rayon
        dy = max(y0 - y, 0.0, y - y1)
        dx = x - cx
        if dx * dx + dy * dy <= rayon * rayon:
            return True
    return False


def _pixels(taille: int) -> bytes:
    """
    Image RGBA, anticrénelée par échantillonnage 3 x 3.

    Pas de bibliothèque graphique : trois boucles suffisent, et l'icône reste
    reproductible partout, y compris sur un runner d'intégration continue.
    """
    lignes = bytearray()
    echantillons = 3
    pas = 1.0 / (echantillons + 1)

    for y in range(taille):
        lignes.append(0)  # filtre PNG « None » en tête de ligne
        for x in range(taille):
            couvert_fond = 0
            couvert_barre = 0
            for sy in range(1, echantillons + 1):
                for sx in range(1, echantillons + 1):
                    px, py = x + sx * pas, y + sy * pas
                    if _dans_le_fond(px, py, taille):
                        couvert_fond += 1
                        if _dans_une_barre(px, py, taille):
                            couvert_barre += 1
            total = echantillons * echantillons
            if not couvert_fond:
                lignes += bytes((0, 0, 0, 0))
                continue
            part_barre = couvert_barre / couvert_fond
            couleur = tuple(
                round(FOND[c] * (1 - part_barre) + BARRE[c] * part_barre) for c in range(3)
            )
            alpha = round(255 * couvert_fond / total)
            lignes += bytes((*couleur, alpha))
    return bytes(lignes)


def _morceau(nom: bytes, donnees: bytes) -> bytes:
    corps = nom + donnees
    return struct.pack(">I", len(donnees)) + corps + struct.pack(">I", zlib.crc32(corps))


def _png(taille: int) -> bytes:
    entete = struct.pack(">2I5B", taille, taille, 8, 6, 0, 0, 0)  # RGBA 8 bits
    return (
        b"\x89PNG\r\n\x1a\n"
        + _morceau(b"IHDR", entete)
        + _morceau(b"IDAT", zlib.compress(_pixels(taille), 9))
        + _morceau(b"IEND", b"")
    )


def ecrire_icone(destination: Path = DESTINATION) -> Path:
    """
    Assemble un fichier .ico contenant une image PNG par taille.

    Windows accepte les images PNG dans un .ico depuis Vista, ce qui évite
    d'écrire un encodeur BMP et un masque de transparence à la main.
    """
    images = [_png(t) for t in TAILLES]
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = len(entete) + 16 * len(images)

    repertoire = bytearray()
    for taille, image in zip(TAILLES, images):
        repertoire += struct.pack(
            "<BBBBHHII",
            0 if taille >= 256 else taille,   # 0 signifie 256
            0 if taille >= 256 else taille,
            0, 0, 1, 32, len(image), decalage,
        )
        decalage += len(image)

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(entete) + bytes(repertoire) + b"".join(images))
    return destination


if __name__ == "__main__":
    chemin = ecrire_icone()
    print(f"Icône écrite : {chemin} ({chemin.stat().st_size} octets)")
