"""
Espace occupé par l'application, ses données et ses modèles.

Trois postes, trois emplacements, et l'application est la seule à savoir où ils
sont réellement : les modèles se choisissent à l'installation, les données
changent de place selon que l'on tourne depuis les sources ou depuis la version
installée. Autant l'afficher.

Deux règles fermes :

  - **jamais d'élévation de droits.** Un dossier illisible est annoncé comme
    tel, on ne demande rien à personne. L'installation étant par utilisateur,
    le dossier du programme est de toute façon lisible par son propriétaire ;
  - **jamais dans le fil de l'interface.** Un dossier de modèles de trois
    gigaoctets se parcourt en centaines de milliers d'appels système : la
    mesure part dans un fil de fond, l'appelant reçoit le résultat quand il est
    prêt.
"""

from __future__ import annotations

from pathlib import Path

from . import chemins, langues

#: Dossiers que l'on ne compte jamais dans la taille du programme : ce sont des
#: dépendances de développement, pas le programme.
EXCLUS_SOURCE = (".venv", ".git", "build", "dist", "__pycache__")


def formater_octets(octets: float) -> str:
    """« 3,1 Go », « 348 Mo », « 12 Ko », « 0 octet », dans la langue courante."""
    return langues.octets(octets)


def taille(chemin: str | Path, exclus: tuple[str, ...] = ()) -> tuple[int, int]:
    """
    Somme des fichiers d'un dossier, en octets, et leur nombre.

    Les erreurs de lecture sont ignorées fichier par fichier : un verrou, un
    lien mort ou un droit refusé ne doit pas faire échouer toute la mesure.
    """
    cible = Path(str(chemin or "")).expanduser()
    if cible.is_file():
        try:
            return cible.stat().st_size, 1
        except OSError:
            return 0, 0
    if not cible.is_dir():
        return 0, 0

    total = 0
    nombre = 0
    piles = [cible]
    while piles:
        dossier = piles.pop()
        try:
            entrees = list(dossier.iterdir())
        except OSError:
            continue
        for entree in entrees:
            try:
                if entree.is_dir():
                    if entree.name in exclus:
                        continue
                    piles.append(entree)
                elif entree.is_file():
                    total += entree.stat().st_size
                    nombre += 1
            except OSError:
                continue
    return total, nombre


def _poste(cle: str, libelle: str, chemin: Path, octets: int,
           detail: str, nombre: int = 0) -> dict:
    return {
        "cle": cle,
        "libelle": libelle,
        "chemin": str(chemin),
        "existe": Path(chemin).exists(),
        "octets": int(octets),
        "taille": formater_octets(octets),
        "nombre": nombre,
        "detail": detail,
    }


def _taille_donnees() -> tuple[int, int]:
    """
    Données de l'application : configuration, glossaire, corrections, gabarit,
    journaux et fichiers de reprise.

    Elles sont énumérées une par une plutôt que mesurées en bloc : depuis les
    sources, la racine des données est aussi celle du projet et des modèles,
    et compter le dossier entier donnerait un chiffre faux.
    """
    total = 0
    nombre = 0
    fichiers = [
        chemins.FICHIER_CONFIG, chemins.FICHIER_VOCABULAIRE,
        chemins.FICHIER_CORRECTIONS, chemins.FICHIER_GABARIT_IA,
        chemins.FICHIER_JETON_HF, chemins.FICHIER_CHOIX_MODELES,
        chemins.RACINE / "maj-etat.json",
        chemins.RACINE / "surveillance-vus.json",
        chemins.RACINE / "calibration.json",
    ]
    for fichier in fichiers:
        octets, compte = taille(fichier)
        total += octets
        nombre += compte
    for dossier in (chemins.DOSSIER_LOGS, chemins.RACINE / "reprises"):
        octets, compte = taille(dossier)
        total += octets
        nombre += compte
    return total, nombre


def mesurer() -> dict:
    """
    Photo de l'espace occupé. Appel bloquant, à lancer dans un fil de fond.
    """
    postes: list[dict] = []

    octets_modeles, nb_modeles = taille(chemins.DOSSIER_MODELES)
    postes.append(_poste(
        "modeles", langues.t("stock.modeles.libelle"), chemins.DOSSIER_MODELES,
        octets_modeles, langues.t("stock.modeles.detail"), nb_modeles,
    ))

    octets_donnees, nb_donnees = _taille_donnees()
    postes.append(_poste(
        "donnees", langues.t("stock.donnees.libelle"), chemins.RACINE, octets_donnees,
        langues.t("stock.donnees.detail"), nb_donnees,
    ))

    if chemins.EST_GELE:
        octets_programme, nb_programme = taille(chemins.DOSSIER_PROGRAMME)
        detail_programme = langues.t("stock.programme.detail_installee")
    else:
        octets_programme, nb_programme = taille(
            chemins.DOSSIER_PROGRAMME, exclus=EXCLUS_SOURCE
        )
        detail_programme = langues.t("stock.programme.detail_sources")
    postes.append(_poste(
        "programme", langues.t("stock.programme.libelle"), chemins.DOSSIER_PROGRAMME,
        octets_programme, detail_programme, nb_programme,
    ))

    total = sum(p["octets"] for p in postes)
    return {
        "postes": postes,
        "total": total,
        "total_texte": formater_octets(total),
        "libre": formater_octets(_octets_libres(chemins.DOSSIER_MODELES)),
        "source": not chemins.EST_GELE,
    }


def _octets_libres(chemin: str | Path) -> int:
    import shutil

    cible = Path(str(chemin)).expanduser()
    for candidat in [cible, *cible.parents]:
        if candidat.exists():
            try:
                return shutil.disk_usage(str(candidat)).free
            except OSError:
                return 0
    return 0
