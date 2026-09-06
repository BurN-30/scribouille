"""
Emplacements de fichiers de l'application. Aucun chemin personnel en dur.

Deux modes de fonctionnement, volontairement distincts :

  - exécution depuis les sources (double-clic sur transcriber.pyw, lancer.bat) :
    tout vit à côté du script, comme avant. Le dossier est celui de l'utilisateur
    qui a cloné le dépôt, il est donc accessible en écriture.

  - exécution de la version installée (exe gelé par PyInstaller) : le programme
    est posé dans un dossier qu'il ne faut pas polluer, et qui peut être en
    lecture seule. La configuration, les journaux et les modèles vont alors dans
    l'espace utilisateur, sous %LOCALAPPDATA%\\WhiScribe.

Le dossier des modèles se choisit à part : ils pèsent de 1,6 à 3,1 Go et l'on
veut pouvoir les ranger sur un autre disque. Il est donc noté dans un fichier
d'une seule ligne, écrit aussi bien par le programme d'installation que par
l'application, et relu par le désinstallateur pour savoir quoi proposer
d'effacer. Trois sources, dans cet ordre :

  1. « dossier-modeles.txt » dans les données de l'utilisateur ;
  2. « emplacement-modeles.txt » à côté du programme, posé par l'installation ;
  3. le dossier « modeles » sous la racine de données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Nom du dossier de données, sous %LOCALAPPDATA%. Il porte encore l'ancien nom
#: de l'application, et c'est VOULU : le renommer en 2.4.0 aurait abandonné sur
#: place la configuration, le glossaire, les corrections et les modèles déjà
#: téléchargés de toutes les installations existantes. Le programme
#: d'installation lit le même chemin en dur (packaging/setup.iss), et son
#: identifiant Inno ne bouge pas non plus.
NOM_DOSSIER_UTILISATEUR = "WhiScribe"

#: Écrit par le programme d'installation, à côté de l'exécutable.
NOM_FICHIER_AMORCAGE = "emplacement-modeles.txt"

#: Écrit par l'application et par le programme d'installation, dans les données
#: de l'utilisateur. C'est lui qui fait foi, et c'est lui que lit le désinstallateur.
NOM_FICHIER_CHOIX_MODELES = "dossier-modeles.txt"

#: Vrai quand l'application tourne depuis l'exécutable produit par PyInstaller.
EST_GELE = bool(getattr(sys, "frozen", False))


def _dossier_ressources() -> Path:
    """Dossier des fichiers livrés avec le programme, jamais écrit par l'application."""
    if EST_GELE:
        # onedir : PyInstaller expose ses ressources via _MEIPASS (le sous-dossier
        # « _internal » à côté de l'exécutable).
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _dossier_programme() -> Path:
    """Dossier d'installation (celui de l'exécutable), ou la racine des sources."""
    if EST_GELE:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _dossier_donnees() -> Path:
    """Racine où l'application écrit : à côté des sources, ou dans l'espace utilisateur."""
    if not EST_GELE:
        return Path(__file__).resolve().parent.parent
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / NOM_DOSSIER_UTILISATEUR
    return Path.home() / f".{NOM_DOSSIER_UTILISATEUR.lower()}"


DOSSIER_RESSOURCES = _dossier_ressources()
DOSSIER_PROGRAMME = _dossier_programme()

#: Racine des données de l'utilisateur : configuration, journaux, modèles par défaut.
RACINE = _dossier_donnees()

DOSSIER_WEB = DOSSIER_RESSOURCES / "web"
DOSSIER_LOGS = RACINE / "logs"

FICHIER_CONFIG = RACINE / "config.json"
FICHIER_CONFIG_EXEMPLE = DOSSIER_RESSOURCES / "config.example.json"
FICHIER_VOCABULAIRE = RACINE / "vocabulaire.txt"
FICHIER_CORRECTIONS = RACINE / "corrections.txt"
FICHIER_JETON_HF = RACINE / "jeton_hf.txt"

#: Gabarit d'instructions pour un assistant IA, créé au premier usage du bouton
#: « Copier pour l'IA ». Voir `app/gabarit.py`.
FICHIER_GABARIT_IA = RACINE / "gabarit-ia.txt"

#: Modèles d'exemple livrés avec le programme, recopiés au premier lancement.
MODELES_FICHIERS_EXEMPLE = {
    FICHIER_VOCABULAIRE: DOSSIER_RESSOURCES / "vocabulaire.txt",
    FICHIER_CORRECTIONS: DOSSIER_RESSOURCES / "corrections.txt",
}


# ---------------------------------------------------------------------------
# Dossier des modèles : configurable, parce qu'il pèse plusieurs gigaoctets
# ---------------------------------------------------------------------------

FICHIER_CHOIX_MODELES = RACINE / NOM_FICHIER_CHOIX_MODELES


def _lire_chemin(fichier: Path) -> Path | None:
    try:
        valeur = fichier.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(valeur).expanduser() if valeur else None


def dossier_modeles_defaut() -> Path:
    """Emplacement proposé quand rien n'a été choisi : « modeles » sous la racine."""
    return RACINE / "modeles"


def dossier_modeles_retenu() -> Path:
    """Applique l'ordre de priorité décrit en tête de module."""
    return (
        _lire_chemin(FICHIER_CHOIX_MODELES)
        or _lire_chemin(DOSSIER_PROGRAMME / NOM_FICHIER_AMORCAGE)
        or dossier_modeles_defaut()
    )


#: Dossier réellement utilisé pour les modèles. Réaffecté par `definir_dossier_modeles`.
DOSSIER_MODELES = dossier_modeles_retenu()


def definir_dossier_modeles(chemin: str | Path | None, memoriser: bool = False) -> Path:
    """
    Fixe le dossier des modèles. Une valeur vide rétablit l'emplacement par défaut.

    Avec `memoriser`, le choix est écrit sur disque pour les lancements suivants,
    et le désinstallateur saura où chercher les modèles à effacer.
    """
    global DOSSIER_MODELES
    texte = str(chemin or "").strip()
    DOSSIER_MODELES = Path(texte).expanduser() if texte else dossier_modeles_retenu()

    if memoriser:
        try:
            RACINE.mkdir(parents=True, exist_ok=True)
            if texte:
                FICHIER_CHOIX_MODELES.write_text(str(DOSSIER_MODELES) + "\n", encoding="utf-8")
            else:
                FICHIER_CHOIX_MODELES.unlink(missing_ok=True)
                DOSSIER_MODELES = dossier_modeles_retenu()
        except OSError:
            pass

    confiner_cache_huggingface()
    return DOSSIER_MODELES


def dossier_modeles_inscriptible(chemin: str | Path) -> str:
    """
    Vérifie qu'un dossier de modèles est utilisable. Renvoie un message d'erreur
    en français, ou une chaîne vide si tout va bien.
    """
    from . import langues

    cible = Path(str(chemin)).expanduser()
    try:
        cible.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return langues.t("chemin.dossier_non_cree", erreur=exc.strerror or exc)
    temoin = cible / ".ecriture-test"
    try:
        temoin.write_text("ok", encoding="utf-8")
        temoin.unlink(missing_ok=True)
    except OSError:
        return langues.t("chemin.dossier_non_ecrivable")
    return ""


def espace_libre_go(chemin: str | Path) -> float:
    """Espace libre en gigaoctets sur le volume du chemin, 0 si indéterminable."""
    import shutil

    cible = Path(str(chemin)).expanduser()
    for candidat in [cible, *cible.parents]:
        if candidat.exists():
            try:
                return shutil.disk_usage(str(candidat)).free / 1024 ** 3
            except OSError:
                return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Création des dossiers et amorçage des fichiers de l'utilisateur
# ---------------------------------------------------------------------------

def dossier_sortie_defaut() -> Path:
    """Dossier de sortie proposé au premier lancement : Documents/Transcriptions."""
    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / "Transcriptions"


def assurer_dossiers() -> None:
    RACINE.mkdir(parents=True, exist_ok=True)
    DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
    try:
        DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Un disque externe débranché ne doit pas empêcher l'application de démarrer :
        # l'erreur sera reformulée au moment du chargement du modèle.
        pass
    confiner_cache_huggingface()
    assurer_fichiers_utilisateur()


def confiner_cache_huggingface() -> None:
    """
    Force huggingface_hub à travailler dans notre dossier de modèles.

    faster-whisper reçoit déjà `download_root`, mais certaines bibliothèques
    appellent le hub directement. Sans cela, des poids finiraient dans le cache
    partagé de l'utilisateur, et la désinstallation ne saurait plus quoi effacer.
    Un dossier, un seul, celui que l'utilisateur a choisi.
    """
    os.environ["HF_HUB_CACHE"] = str(DOSSIER_MODELES)
    os.environ.setdefault("HF_HOME", str(DOSSIER_MODELES))


def taille_dossier_go(chemin: str | Path) -> float:
    """Taille occupée par un dossier, en gigaoctets. 0 s'il n'existe pas."""
    cible = Path(str(chemin)).expanduser()
    if not cible.is_dir():
        return 0.0
    total = 0
    try:
        for fichier in cible.rglob("*"):
            try:
                if fichier.is_file():
                    total += fichier.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total / 1024 ** 3


def assurer_fichiers_utilisateur() -> None:
    """
    Recopie une fois les exemples de glossaire et de corrections dans l'espace
    utilisateur. Un fichier déjà présent n'est jamais écrasé : une mise à jour de
    l'application ne doit rien perdre.
    """
    for cible, source in MODELES_FICHIERS_EXEMPLE.items():
        if cible.exists() or cible == source:
            continue
        try:
            cible.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
