"""
Sauvegarde progressive et reprise d'une transcription interrompue.

Le problème : une réunion de deux heures représente deux heures de calcul, et
une coupure de courant, une fermeture de fenêtre ou un plantage à la
quatre-vingt-dixième minute ne laissait jusqu'ici strictement rien.

Le remède est volontairement modeste. Le moteur produit déjà les segments un par
un ; on se contente d'écrire chacun à la volée dans un fichier de reprise, plus
un petit état à côté. Rien n'est mis en tampon, aucun calcul n'est refait, aucun
processus supplémentaire n'est lancé.

Deux fichiers par transcription en cours, dans « reprises/ » sous les données de
l'utilisateur, jamais dans le dossier de sortie :

  - `<clé>.jsonl` : un segment par ligne, JSON compact, ajouté en fin de fichier.
    C'est le texte partiel, avec ses horodatages et la confiance des mots.
  - `<clé>.json`  : l'état, réécrit après chaque segment. Il tient en quelques
    centaines d'octets et porte la position atteinte dans l'audio ainsi que le
    TEMPS DÉJÀ ÉCOULÉ, pour que le compteur reparte là où il s'était arrêté.

La clé identifie le couple fichier source / modèle : reprendre une transcription
avec un autre modèle n'aurait aucun sens, et deux fichiers homonymes rangés dans
deux dossiers différents ne se mélangent pas.

À la reprise, seule la fin du signal est repassée au décodeur, à partir du
dernier segment enregistré. Les fichiers sont effacés dès qu'une transcription
se termine normalement, et les traces de plus de trente jours sont purgées au
démarrage.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

from . import chemins, journal
from .moteur import Mot, Segment

#: Au-delà, une reprise ne présente plus d'intérêt et l'audio a souvent bougé.
RETENTION_JOURS = 30


def dossier() -> Path:
    cible = chemins.RACINE / "reprises"
    try:
        cible.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return cible


def cle(source: str | Path, modele: str) -> str:
    """Identifiant stable d'un couple fichier source / modèle."""
    fichier = Path(source)
    empreinte = [str(fichier.resolve() if fichier.exists() else fichier), modele]
    try:
        etat = fichier.stat()
        empreinte += [str(etat.st_size), str(int(etat.st_mtime))]
    except OSError:
        pass
    return hashlib.sha1("|".join(empreinte).encode("utf-8")).hexdigest()[:16]


def _fichier_etat(identifiant: str) -> Path:
    return dossier() / f"{identifiant}.json"


def _fichier_segments(identifiant: str) -> Path:
    return dossier() / f"{identifiant}.jsonl"


# ---------------------------------------------------------------------------
# Écriture au fil des segments
# ---------------------------------------------------------------------------

class Session:
    """
    Sauvegarde progressive d'une transcription en cours.

    Une session inactive (option coupée) ne fait rien du tout : toutes ses
    méthodes deviennent des passe-plats, l'appelant n'a pas à s'en soucier.
    """

    def __init__(self, identifiant: str = "", active: bool = False):
        self.identifiant = identifiant
        self.active = bool(active and identifiant)
        self.nb_segments = 0
        self.position = 0.0
        self._infos: dict = {}
        self._flux = None
        #: Appelée une fois si l'écriture échoue (disque plein, clé retirée) :
        #: l'interface le dit, au lieu de laisser croire que tout est protégé.
        self.alerte = None

    # -- cycle de vie ------------------------------------------------------

    def ouvrir(self, source: Path, modele: str, duree_audio: float,
               position: float = 0.0, nb_segments: int = 0, ecoule: float = 0.0,
               sortie: str = "") -> None:
        if not self.active:
            return
        self.position = position
        self.nb_segments = nb_segments
        self._infos = {
            "version": 1,
            "source": str(source),
            "nom": source.name,
            "modele": modele,
            "duree_audio": round(float(duree_audio or 0), 2),
            "debut": datetime.now().isoformat(timespec="seconds"),
        }
        # Dossier de sortie demandé : « scribouille reprendre » y écrit aussi.
        if sortie:
            self._infos["sortie"] = str(sortie)
        try:
            self._flux = _fichier_segments(self.identifiant).open("a", encoding="utf-8")
        except OSError as exc:
            journal.attention("Sauvegarde progressive désactivée pour ce fichier : %s", exc)
            self.active = False
            return
        self.ecrire_etat(ecoule)

    def fermer(self) -> None:
        if self._flux is not None:
            try:
                self._flux.close()
            except OSError:
                pass
            self._flux = None

    def effacer(self) -> None:
        """Fin normale d'une transcription : plus rien à reprendre."""
        self.fermer()
        if not self.identifiant:
            return
        for fichier in (_fichier_segments(self.identifiant), _fichier_etat(self.identifiant)):
            try:
                fichier.unlink(missing_ok=True)
            except OSError:
                pass

    # -- écriture ----------------------------------------------------------

    def ajouter(self, segment: Segment, ecoule: float) -> None:
        """Enregistre un segment qui vient de sortir du décodeur."""
        if not self.active or self._flux is None:
            return
        ligne = {
            "d": round(segment.debut, 2),
            "f": round(segment.fin, 2),
            "t": segment.texte,
            "m": [
                {"t": m.texte, "d": round(m.debut, 2), "f": round(m.fin, 2),
                 "p": round(m.probabilite, 3)}
                for m in segment.mots
            ],
        }
        try:
            self._flux.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            self._flux.flush()
        except OSError as exc:
            journal.attention("Écriture de reprise impossible, sauvegarde coupée : %s", exc)
            self.active = False
            if self.alerte is not None:
                try:
                    self.alerte(str(exc))
                except Exception:
                    pass
            return
        self.nb_segments += 1
        self.position = segment.fin
        self.ecrire_etat(ecoule)

    def ecrire_etat(self, ecoule: float) -> None:
        if not self.active:
            return
        etat = dict(self._infos)
        etat.update({
            "position": round(float(self.position), 2),
            "nb_segments": self.nb_segments,
            "ecoule": round(float(ecoule), 1),
            "maj": datetime.now().isoformat(timespec="seconds"),
        })
        # Écrit à côté puis renommé : une fenêtre fermée ou un courant coupé
        # pendant l'écriture laisse l'ancien état, jamais un état à moitié écrit
        # qui rendrait la reprise impossible.
        cible = _fichier_etat(self.identifiant)
        provisoire = cible.with_name(cible.name + ".tmp")
        try:
            provisoire.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
            os.replace(provisoire, cible)
        except OSError:
            pass


def session_inactive() -> Session:
    return Session()


# ---------------------------------------------------------------------------
# Relecture
# ---------------------------------------------------------------------------

def lire_etat(identifiant: str) -> dict | None:
    try:
        etat = json.loads(_fichier_etat(identifiant).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return etat if isinstance(etat, dict) else None


def lire_segments(identifiant: str) -> list[Segment]:
    """
    Relit les segments déjà transcrits.

    Une dernière ligne tronquée par une coupure brutale est simplement ignorée :
    c'est exactement le cas que ce format une-ligne-un-segment doit encaisser.
    """
    fichier = _fichier_segments(identifiant)
    segments: list[Segment] = []
    try:
        contenu = fichier.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return segments

    for ligne in contenu.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            brut = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if not isinstance(brut, dict) or not brut.get("t"):
            continue
        segments.append(Segment(
            debut=float(brut.get("d", 0) or 0),
            fin=float(brut.get("f", 0) or 0),
            texte=str(brut.get("t", "")),
            mots=[
                Mot(texte=str(m.get("t", "")), debut=float(m.get("d", 0) or 0),
                    fin=float(m.get("f", 0) or 0), probabilite=float(m.get("p", 0) or 0))
                for m in (brut.get("m") or []) if isinstance(m, dict) and m.get("t")
            ],
        ))
    return segments


def lister() -> list[dict]:
    """
    Transcriptions interrompues que l'on peut proposer de reprendre.

    Une reprise dont le fichier source a disparu ou n'a pas avancé d'une seule
    seconde n'est pas proposée : elle serait une fausse promesse.
    """
    resultat: list[dict] = []
    if not (chemins.RACINE / "reprises").is_dir():
        return resultat
    for fichier in sorted(dossier().glob("*.json")):
        identifiant = fichier.stem
        etat = lire_etat(identifiant)
        if not etat:
            continue
        source = Path(etat.get("source", ""))
        if not source.is_file() or float(etat.get("position", 0) or 0) <= 0:
            continue
        duree = float(etat.get("duree_audio", 0) or 0)
        position = float(etat.get("position", 0) or 0)
        resultat.append({
            "cle": identifiant,
            "nom": etat.get("nom", source.name),
            "chemin": str(source),
            "modele": etat.get("modele", ""),
            "position": position,
            "duree_audio": duree,
            "pct": int(min(99, position / duree * 100)) if duree else 0,
            "nb_segments": int(etat.get("nb_segments", 0) or 0),
            "ecoule": float(etat.get("ecoule", 0) or 0),
            "date": etat.get("maj", etat.get("debut", "")),
        })
    return resultat


def purger(jours: int = RETENTION_JOURS) -> int:
    """Retire les reprises trop vieilles ou dont la source a disparu."""
    limite = time.time() - jours * 86400
    retires = 0
    for fichier in list(dossier().glob("*.json")):
        etat = lire_etat(fichier.stem)
        trop_vieux = False
        try:
            trop_vieux = fichier.stat().st_mtime < limite
        except OSError:
            trop_vieux = True
        source_absente = not etat or not Path(etat.get("source", "")).is_file()
        if trop_vieux or source_absente:
            Session(fichier.stem, active=True).effacer()
            retires += 1
    if retires:
        journal.info("Reprises purgées : %s", retires)
    return retires


def oublier(identifiant: str) -> None:
    Session(identifiant, active=True).effacer()
