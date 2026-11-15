"""
Dossier surveillé : ce qui arrive dans un dossier part en transcription.

Fonction volontairement modeste, et coupée par défaut. Elle sert un cas précis :
un dictaphone, un téléphone ou un enregistreur de réunion qui dépose ses
fichiers toujours au même endroit. Plutôt que d'aller les chercher, on désigne
le dossier une fois.

Trois choix d'implémentation, tous dictés par la sobriété :

  - **Aucune dépendance nouvelle.** Pas de watchdog, pas de service, pas de
    notification du système de fichiers : une scrutation toutes les dix
    secondes, uniquement quand l'option est active. Sur un dossier normal, cela
    coûte un `iterdir` et quelques `stat`, c'est-à-dire rien.
  - **Un fichier doit être stable pour être pris.** Une copie de 300 Mo en
    cours d'écriture apparaît immédiatement dans le dossier, et la transcrire
    à cet instant produirait un échec ou un texte tronqué. Un fichier n'est
    donc retenu que si sa taille n'a pas bougé entre deux passages, soit dix
    secondes de calme.
  - **La mémoire des fichiers déjà pris est persistante.** Sans elle, tout
    serait retranscrit à chaque démarrage. La clé retenue est le triplet
    chemin, taille, date de modification : un enregistrement refait sous le
    même nom est bien un fichier nouveau, et il repart en transcription. Un
    fichier n'y entre qu'une fois sa transcription finie (réussie ou en
    échec) : ceux qui attendaient en file lors d'une coupure repartent au
    démarrage suivant. Elle est écrite à côté puis renommée.

Un dossier supprimé, débranché ou devenu illisible ne casse rien : la
surveillance passe en défaut, le dit une fois dans l'interface, et repart toute
seule si le dossier réapparaît.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from . import audio, chemins, journal, langues

#: Intervalle entre deux passages. Dix secondes, c'est court pour un humain et
#: long pour un disque.
INTERVALLE_SECONDES = 10.0

#: Nombre d'empreintes conservées. Largement de quoi tenir des années d'usage,
#: et une borne pour que le fichier ne grossisse pas indéfiniment.
MEMOIRE_MAX = 3000

FICHIER_MEMOIRE = "surveillance-vus.json"


def fichier_memoire() -> Path:
    return chemins.RACINE / FICHIER_MEMOIRE


def empreinte(fichier: Path) -> str:
    """Identifie une version précise d'un fichier : chemin, taille, date."""
    try:
        etat = fichier.stat()
        return f"{str(fichier).lower()}|{etat.st_size}|{int(etat.st_mtime)}"
    except OSError:
        return str(fichier).lower()


# ---------------------------------------------------------------------------
# Mémoire persistante
# ---------------------------------------------------------------------------

def charger_memoire() -> dict:
    try:
        donnees = json.loads(fichier_memoire().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return donnees if isinstance(donnees, dict) else {}


def ecrire_memoire(memoire: dict) -> None:
    if len(memoire) > MEMOIRE_MAX:
        anciennes = sorted(memoire.items(), key=lambda couple: couple[1])
        memoire = dict(anciennes[-MEMOIRE_MAX:])
    # Écrite à côté (nom propre à ce processus) puis renommée : tronquée par
    # une coupure, elle remettait tout le dossier surveillé en file.
    cible = fichier_memoire()
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}.tmp")
    try:
        chemins.RACINE.mkdir(parents=True, exist_ok=True)
        provisoire.write_text(json.dumps(memoire, ensure_ascii=False), encoding="utf-8")
        os.replace(provisoire, cible)
    except OSError as exc:
        journal.attention("Mémoire du dossier surveillé non enregistrée : %s", exc)
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Un passage de scrutation
# ---------------------------------------------------------------------------

def scruter(dossier: str | Path, memoire: dict, tailles_precedentes: dict) -> dict:
    """
    Un passage sur le dossier. N'écrit rien, ne décide rien d'autre.

    Renvoie `{nouveaux, tailles, probleme}` :

      - `nouveaux` : les fichiers audio stables et jamais pris jusqu'ici ;
      - `tailles`  : la photo des tailles, à repasser au tour suivant, c'est
        elle qui donne la stabilité ;
      - `probleme` : message en français si le dossier est injoignable, sinon
        chaîne vide.

    Fonction pure au sens utile du terme : elle ne touche ni à la mémoire
    persistante ni au reste de l'application, ce qui la rend vérifiable en
    ligne de commande.
    """
    cible = Path(str(dossier or "")).expanduser()
    if not str(dossier or "").strip():
        return {"nouveaux": [], "tailles": {}, "probleme": ""}

    if not cible.exists():
        return {
            "nouveaux": [], "tailles": {},
            "probleme": langues.t("veille.introuvable", chemin=cible),
        }
    if not cible.is_dir():
        return {
            "nouveaux": [], "tailles": {},
            "probleme": langues.t("veille.pas_dossier", chemin=cible),
        }

    try:
        entrees = list(cible.iterdir())
    except OSError as exc:
        return {
            "nouveaux": [], "tailles": {},
            "probleme": langues.t(
                "veille.illisible", chemin=cible, erreur=exc.strerror or exc),
        }

    tailles: dict[str, int] = {}
    nouveaux: list[str] = []

    for entree in sorted(entrees):
        try:
            if not entree.is_file() or not audio.est_audio(entree):
                continue
            taille = entree.stat().st_size
        except OSError:
            continue
        if taille <= 0:
            continue

        cle = str(entree).lower()
        tailles[cle] = taille

        if empreinte(entree) in memoire:
            continue
        # Stabilité : vu au passage précédent, avec exactement la même taille.
        if tailles_precedentes.get(cle) != taille:
            continue
        nouveaux.append(str(entree))

    return {"nouveaux": nouveaux, "tailles": tailles, "probleme": ""}


# ---------------------------------------------------------------------------
# Boucle de fond
# ---------------------------------------------------------------------------

class Surveillant:
    """
    Fil de fond qui scrute le dossier et livre les fichiers retenus.

    Un seul fil pour toute la vie de l'application : il dort quand l'option est
    coupée, et ne touche jamais au disque dans ce cas.
    """

    def __init__(self, sur_nouveaux, signaler=None, intervalle: float = INTERVALLE_SECONDES):
        self._sur_nouveaux = sur_nouveaux
        self._signaler = signaler or (lambda niveau, texte: None)
        self._intervalle = float(intervalle)
        self._verrou = threading.Lock()
        self._reveil = threading.Event()
        self._fil: threading.Thread | None = None
        self._arret = threading.Event()

        self.actif = False
        self.dossier = ""
        self.probleme = ""
        self._probleme_signale = ""
        self._tailles: dict[str, int] = {}
        self._memoire = charger_memoire()
        #: Empreinte -> chemin (minuscules) des fichiers livrés à la file
        #: pendant cette session, en attendant leur transcription.
        self._livres: dict[str, str] = {}

    # -- pilotage ----------------------------------------------------------

    def demarrer(self) -> None:
        if self._fil is not None:
            return
        self._fil = threading.Thread(target=self._boucle, daemon=True)
        self._fil.start()

    def arreter(self) -> None:
        self._arret.set()
        self._reveil.set()

    def configurer(self, dossier: str, actif: bool, adopter: bool = True) -> dict:
        """
        Applique le réglage et rend l'état immédiat, sans attendre un tour.

        `adopter` distingue deux moments qui n'appellent pas la même chose. À
        l'activation depuis les réglages, le dossier désigné contient souvent
        des mois d'enregistrements : les déverser d'un coup dans la file serait
        une catastrophe, ils sont donc considérés comme déjà connus. Au
        redémarrage de l'application, au contraire, tout ce qui est arrivé
        pendant qu'elle était fermée est légitimement nouveau.
        """
        with self._verrou:
            self.dossier = str(dossier or "").strip()
            self.actif = bool(actif and self.dossier)
            self._tailles = {}
            self.probleme = ""
            self._probleme_signale = ""

        if self.actif:
            if adopter:
                self._adopter_existant()
            self.demarrer()
        self._reveil.set()
        return self.etat()

    def etat(self) -> dict:
        return {
            "actif": bool(self.actif),
            "dossier": self.dossier,
            "probleme": self.probleme,
            "intervalle": int(self._intervalle),
            "nb_connus": len(self._memoire),
        }

    def oublier_tout(self) -> dict:
        """Vide la mémoire : tout ce qui est dans le dossier repartira."""
        with self._verrou:
            self._memoire = {}
            self._tailles = {}
        ecrire_memoire({})
        return self.etat()

    # -- interne -----------------------------------------------------------

    def _adopter_existant(self) -> None:
        """Marque comme déjà connus les fichiers présents à l'activation."""
        passage = scruter(self.dossier, {}, {})
        if passage["probleme"]:
            self.probleme = passage["probleme"]
            return
        maintenant = time.time()
        with self._verrou:
            for cle in passage["tailles"]:
                self._memoire[empreinte(Path(cle))] = maintenant
            self._tailles = passage["tailles"]
        ecrire_memoire(self._memoire)

    def _boucle(self) -> None:
        while not self._arret.is_set():
            self._reveil.wait(self._intervalle)
            self._reveil.clear()
            if self._arret.is_set():
                return
            if not self.actif:
                continue
            try:
                self._passage()
            except Exception as exc:      # jamais de fil qui meurt en silence
                journal.exception("Scrutation du dossier surveillé en échec", exc)

    def _passage(self) -> None:
        with self._verrou:
            dossier, precedentes = self.dossier, dict(self._tailles)
            memoire = dict(self._memoire)

        passage = scruter(dossier, memoire, precedentes)

        with self._verrou:
            self._tailles = passage["tailles"]
            self.probleme = passage["probleme"]

        if passage["probleme"]:
            # Signalé une seule fois : un disque débranché ne doit pas remplir
            # le journal d'une ligne toutes les dix secondes.
            if passage["probleme"] != self._probleme_signale:
                self._probleme_signale = passage["probleme"]
                self._signaler(
                    "attention",
                    passage["probleme"] + langues.t("veille.reprise_auto"),
                )
            return

        if self._probleme_signale:
            self._probleme_signale = ""
            self._signaler("ok", langues.t("veille.retour"))

        if not passage["nouveaux"]:
            return

        # Livrés à la file, pas encore « vus » : ils ne le deviennent (sur le
        # disque) qu'une fois leur transcription finie (`marquer_vu`). Une
        # coupure pendant qu'ils attendaient les remet en file au démarrage
        # suivant ; d'ici là, cette session ne les relivre pas.
        nouveaux = [c for c in passage["nouveaux"] if empreinte(Path(c)) not in self._livres]
        if not nouveaux:
            return
        with self._verrou:
            for chemin in nouveaux:
                self._livres[empreinte(Path(chemin))] = str(chemin).lower()

        journal.info("Dossier surveillé : %s nouveau(x) fichier(s)", len(nouveaux))
        self._sur_nouveaux(nouveaux)

    def livre(self, chemin: str) -> bool:
        """Ce fichier a-t-il été livré à la file par le dossier surveillé, pendant cette session ?"""
        cle = str(chemin or "").lower()
        with self._verrou:
            return cle in self._livres.values()

    def marquer_vu(self, chemin: str) -> None:
        """Transcription finie (réussie ou en échec) d'un fichier livré : il est désormais connu."""
        cle = str(chemin or "").lower()
        with self._verrou:
            empreintes = [e for e, c in self._livres.items() if c == cle]
            if not empreintes:
                return
            maintenant = time.time()
            for e in empreintes:
                self._memoire[e] = maintenant
            memoire = dict(self._memoire)
        ecrire_memoire(memoire)
