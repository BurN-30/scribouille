"""
Recalibration à chaud des estimations de durée.

Le problème mesuré le 21 août 2026 : le preset « Qualité maximale » annonçait
un facteur de 1,35 fois la durée de l'audio, et en demandait 2,07 sur un Ryzen
7800X3D. Une réunion de vingt-trois minutes annoncée pour une demi-heure en
prenait trois quarts. Les facteurs statiques de `app/presets.py` viennent de
mesures publiques faites sur une autre machine que celle de l'utilisateur : ils
ne peuvent pas être justes ailleurs que là où ils ont été relevés.

Le remède tient en une phrase : après chaque transcription menée à son terme,
on écrit le facteur réellement observé, et c'est lui qui sert aux annonces
suivantes. La machine se mesure elle-même, personne n'a rien à régler.

Ce qui est retenu, et pourquoi
------------------------------
Une mesure porte sur la TRANSCRIPTION seule : ni le décodage du fichier, ni le
chargement du modèle, ni la séparation des locuteurs. C'est exactement ce que
les facteurs de `presets.py` prétendent décrire, et le surcoût des locuteurs a
son propre terme. Une transcription reprise après coupure n'est pas mesurée :
son temps de calcul est réparti sur deux exécutions.

Les mesures sont rangées par MODÈLE, par PÉRIPHÉRIQUE et par LARGEUR DE
FAISCEAU, parce que ces trois-là changent le coût du tout au tout : le preset
« Rapide » va environ quatre fois plus vite que « Qualité maximale », et un
beam 8 coûte bien plus qu'un beam 5 avec le même modèle.

Le fichier porte une signature de machine. Un dossier de données recopié sur un
autre poste, ou un processeur changé, repart donc d'une page blanche plutôt que
d'annoncer les durées d'une autre machine.

Lissage
-------
Une seule mesure ne fait pas une vérité : une réunion peut tomber pendant une
sauvegarde du système, une autre sur une machine au repos. On garde donc les
cinq dernières et l'on en fait une moyenne pondérée, où pèsent :

  - la RÉCENCE, parce qu'une machine change (mise à jour de pilote, portable
    branché ou sur batterie) : la mesure la plus fraîche compte le plus ;
  - la DURÉE de l'enregistrement mesuré, parce qu'un extrait de deux minutes
    renseigne moins qu'une réunion d'une heure.

Enfin, les enregistrements trop courts et les valeurs aberrantes sont écartés
d'entrée : sur trente secondes d'audio, la mise en route pèse plus que le
calcul, et la mesure dirait n'importe quoi.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import chemins, journal
from .materiel import Materiel

#: Version du contenu du fichier. Un fichier écrit par une version future est
#: ignoré plutôt que mal relu : perdre des mesures ne coûte qu'une transcription.
VERSION_FICHIER = 1

#: En dessous, la mise en route du moteur pèse trop lourd dans le chronomètre.
DUREE_MINIMALE = 60.0

#: Garde-fous : au-delà, la mesure vient d'autre chose que d'une transcription
#: (machine mise en veille, disque saturé, horloge qui saute).
FACTEUR_MINIMAL = 0.01
FACTEUR_MAXIMAL = 60.0

#: Nombre de mesures conservées par situation.
MESURES_RETENUES = 5

#: Poids de récence : la mesure la plus fraîche compte pour 1, la précédente
#: pour 0,7, et ainsi de suite. Un facteur mesuré il y a cinq réunions pèse
#: encore, mais ne décide plus.
DECROISSANCE = 0.7


def fichier() -> Path:
    """Emplacement du fichier de mesures, dans les données de l'utilisateur."""
    return chemins.RACINE / "calibration.json"


def signature_machine(mat: Materiel) -> str:
    """
    Ce qui, dans la machine, change le temps de calcul.

    Le nom du processeur et le nombre de fils suffisent : c'est ce qui décide de
    la vitesse en calcul processeur, et le périphérique retenu figure déjà dans
    la clé de chaque mesure.
    """
    return " / ".join([
        (mat.cpu_nom or "processeur inconnu").strip(),
        f"{mat.coeurs_logiques or 0} fils",
    ])


def cle_mesure(modele: str, peripherique: str, beam: int) -> str:
    """Identifiant d'une situation de calcul : modèle, périphérique, faisceau."""
    return f"{modele}|{peripherique or 'cpu'}|beam{max(1, int(beam or 1))}"


# ---------------------------------------------------------------------------
# Lecture et écriture du fichier
# ---------------------------------------------------------------------------

def _vide(signature: str = "") -> dict:
    return {"version": VERSION_FICHIER, "machine": signature, "mesures": {}}


def charger(signature: str = "") -> dict:
    """
    Relit les mesures du poste. Renvoie une structure vide en cas de doute.

    Le doute couvre tout : fichier absent, illisible, écrit par une version
    future, ou relevé sur une autre machine. Aucune de ces situations n'est une
    erreur : on repart des facteurs statiques, et la première transcription
    réussie recommence à mesurer.
    """
    cible = fichier()
    try:
        donnees = json.loads(cible.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _vide(signature)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        journal.attention("Mesures de durée illisibles, valeurs de repli : %s", exc)
        return _vide(signature)

    if not isinstance(donnees, dict) or donnees.get("version") != VERSION_FICHIER:
        return _vide(signature)
    if not isinstance(donnees.get("mesures"), dict):
        return _vide(signature)
    if signature and str(donnees.get("machine", "")) != signature:
        journal.info("Mesures de durée relevées sur une autre machine, remises à zéro.")
        return _vide(signature)
    return donnees


def _ecrire(donnees: dict) -> None:
    try:
        chemins.RACINE.mkdir(parents=True, exist_ok=True)
        fichier().write_text(
            json.dumps(donnees, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        journal.attention("Mesures de durée non enregistrées : %s", exc)


def oublier() -> None:
    """Efface les mesures. Les annonces repartent des facteurs statiques."""
    try:
        fichier().unlink(missing_ok=True)
    except OSError as exc:
        journal.attention("Mesures de durée non effacées : %s", exc)


# ---------------------------------------------------------------------------
# Calcul
# ---------------------------------------------------------------------------

def moyenne_lissee(historique: list) -> float:
    """
    Facteur retenu à partir des mesures gardées, de la plus récente à la plus
    ancienne. Renvoie 0 si aucune mesure n'est exploitable.
    """
    total = 0.0
    poids_total = 0.0
    for rang, entree in enumerate(historique[:MESURES_RETENUES]):
        try:
            duree = float(entree.get("duree", 0))
            facteur = float(entree.get("facteur", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        if duree <= 0 or not FACTEUR_MINIMAL <= facteur <= FACTEUR_MAXIMAL:
            continue
        poids = duree * (DECROISSANCE ** rang)
        total += facteur * poids
        poids_total += poids
    return round(total / poids_total, 3) if poids_total else 0.0


def facteur_mesure(modele: str, peripherique: str, beam: int,
                   mat: Materiel | None = None) -> float:
    """
    Facteur observé sur cette machine dans cette situation, 0 s'il n'y en a pas.

    Un 0 n'est pas un échec : c'est le cas normal tant qu'aucune transcription
    n'a été menée à son terme avec ce modèle, et l'appelant se rabat alors sur
    le facteur statique du preset.
    """
    donnees = charger(signature_machine(mat) if mat else "")
    entree = donnees["mesures"].get(cle_mesure(modele, peripherique, beam))
    if not isinstance(entree, dict):
        return 0.0
    historique = entree.get("historique")
    return moyenne_lissee(historique) if isinstance(historique, list) else 0.0


def enregistrer(modele: str, peripherique: str, beam: int, duree_audio: float,
                temps_calcul: float, mat: Materiel | None = None) -> float:
    """
    Retient le facteur d'une transcription réussie et renvoie le facteur lissé.

    Renvoie 0 quand la mesure est écartée : enregistrement trop court, ou
    valeur hors des bornes du plausible.
    """
    try:
        duree_audio = float(duree_audio)
        temps_calcul = float(temps_calcul)
    except (TypeError, ValueError):
        return 0.0
    if duree_audio < DUREE_MINIMALE or temps_calcul <= 0:
        return 0.0

    facteur = round(temps_calcul / duree_audio, 3)
    if not FACTEUR_MINIMAL <= facteur <= FACTEUR_MAXIMAL:
        journal.attention(
            "Facteur de temps réel écarté, hors des bornes plausibles : %.3f", facteur)
        return 0.0

    signature = signature_machine(mat) if mat else ""
    donnees = charger(signature)
    donnees["machine"] = signature or donnees.get("machine", "")

    cle = cle_mesure(modele, peripherique, beam)
    entree = donnees["mesures"].get(cle)
    historique = entree.get("historique", []) if isinstance(entree, dict) else []
    if not isinstance(historique, list):
        historique = []

    historique.insert(0, {
        "facteur": facteur,
        "duree": round(duree_audio, 1),
        "date": datetime.now().isoformat(timespec="seconds"),
    })
    del historique[MESURES_RETENUES:]

    lisse = moyenne_lissee(historique)
    donnees["mesures"][cle] = {"facteur": lisse, "historique": historique}
    _ecrire(donnees)

    journal.info(
        "Facteur de temps réel mesuré pour %s : %.2f (retenu après lissage : %.2f)",
        cle, facteur, lisse)
    return lisse
