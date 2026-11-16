"""
Sauvegarde progressive et reprise d'une transcription interrompue.

Le problème : une réunion de deux heures représente deux heures de calcul, et
une coupure de courant, une fermeture de fenêtre ou un plantage à la
quatre-vingt-dixième minute ne laissait jusqu'ici strictement rien.

Le remède est volontairement modeste. Le moteur produit déjà les segments un par
un ; on se contente d'écrire chacun à la volée dans un fichier de reprise, plus
un petit état à côté. Rien n'est mis en tampon, aucun calcul n'est refait, aucun
processus supplémentaire n'est lancé.

Trois fichiers par transcription en cours, dans « reprises/ » sous les données de
l'utilisateur, jamais dans le dossier de sortie :

  - `<clé>.jsonl` : un segment par ligne, JSON compact, ajouté en fin de fichier.
    C'est le texte partiel, avec ses horodatages et la confiance des mots.
  - `<clé>.etat`  : l'état (JSON), réécrit après chaque segment. Il tient en
    quelques centaines d'octets et porte la position atteinte dans l'audio
    ainsi que le TEMPS DÉJÀ ÉCOULÉ, pour que le compteur reparte là où il
    s'était arrêté. Jusqu'au 15/11 il s'appelait `<clé>.json` : ces états-là
    sont toujours lus, et renommés à la première reprise (ou, dossier partagé
    avec une 2.x, à l'ouverture de la fenêtre). Le nouveau nom ne finit pas
    par `.json` : une WhiScribe 2.3.3 qui partage le dossier ne les voit donc
    pas (elle ne liste ni ne purge que `*.json`).
  - `<clé>.depart` : la demande de départ (source, modèle, sortie, réglages),
    écrite une fois à l'ouverture, vidée sur le disque puis renommée. Un état
    perdu ou abîmé par une coupure de courant (réécrit à chaque segment, il
    n'est pas vidé sur le disque) se reconstruit avec elle et les segments
    gardés : la reprise reste proposée, au segment près.

La clé identifie le couple fichier source / modèle : reprendre une transcription
avec un autre modèle n'aurait aucun sens, et deux fichiers homonymes rangés dans
deux dossiers différents ne se mélangent pas.

La sauvegarde est ouverte dès qu'un fichier est pris en charge, avant la
lecture de l'audio et le chargement du modèle : une transcription coupée avant
son premier segment reste reprenable, elle repart alors du début avec toute la
demande de départ.

Lecture tolérante : les segments sont relus ligne par ligne ; une ligne
abîmée (octet invalide, coupure au milieu d'une écriture) est écartée et
notée au journal, les autres sont gardées. Avant d'ajouter à la suite, une
dernière ligne incomplète est retirée (ou complétée si elle est entière). Une
erreur de lecture du disque ne tronque jamais rien : la reprise échoue, dit
pourquoi, et reste en place.

À la reprise, seule la fin du signal est repassée au décodeur, à partir du
dernier segment enregistré. Les fichiers sont effacés dès qu'une transcription
se termine normalement. Ce qui ne peut plus être repris est « orphelin » :
`orphelines()` le liste avec sa raison, `scribouille etat` le montre,
`scribouille etat --nettoyer` l'efface, et la fenêtre en purge une partie à
son démarrage (`purger`), en journalisant chaque fichier retiré. La purge
n'efface jamais sur une absence qui peut être passagère : source sur un
lecteur injoignable, état momentanément illisible ; une source absente
(dossier joignable, fichier introuvable) n'est effacée qu'après
`DELAI_ABSENCE_JOURS` jours de constats ; des segments valides sans état
lisible restent jusqu'à la rétention.

Dossier partagé avec une WhiScribe 2.x installée (même `reprises\\`, même
format) : seuls les fichiers de Scribouille 3.x sont lus, proposés ou
effacés. Un état est à nous s'il porte `auteur` (`AUTEUR`), ou la demande de
départ que seule la 3.x enregistre ; ses segments vont avec lui. Les verrous
(`.en-cours`), les états `.etat`, les écritures provisoires
(`.json.scribouille-tmp`) et les constats d'absence (`.absente`) n'ont pas
d'équivalent en 2.x. La clé d'une transcription de la 3.x ne peut pas non
plus tomber sur celle d'une 2.x (`cle`). Le reste n'est jamais touché ; une
fois la 2.x désinstallée, tout le dossier redevient le nôtre.
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

#: Source introuvable (dossier joignable, fichier absent) : effacée par la
#: purge du démarrage seulement après autant de jours de constats.
DELAI_ABSENCE_JOURS = 7

#: Ce que la demande de départ prévoyait et qu'une reprise rétablit : formats,
#: langue, vocabulaire, voix et leurs noms, rythme, modèle, moteur. Le dossier
#: de sortie est gardé à part (« sortie »).
CLES_DEMANDE = ("formats", "compagnon_confiance", "langue", "preset", "utiliser_glossaire",
                "appliquer_corrections", "vocabulaires_partages", "rapprochement_vocabulaire", "diarisation",
                "nb_locuteurs", "noms_locuteurs", "motif_sortie", "filtres_salle", "rythme", "rythme_auto",
                "mode_avance", "modele_avance", "beam_size", "condition_on_previous_text", "forcer_processeur",
                "reglage_machine")

#: Parmi elles, celles qui valent fichier par fichier : une reprise remise
#: dans la file de la fenêtre les retrouve, quels que soient les réglages du
#: moment (le modèle, lui, est gardé par la clé de reprise).
CLES_PAR_FICHIER = ("formats", "compagnon_confiance", "langue", "utiliser_glossaire", "appliquer_corrections",
                    "vocabulaires_partages", "rapprochement_vocabulaire", "diarisation", "nb_locuteurs",
                    "noms_locuteurs", "motif_sortie")


#: Marque des états écrits par Scribouille 3.x.
AUTEUR = "scribouille-3"
#: Écriture provisoire d'un état (renommée aussitôt écrite).
SUFFIXE_PROVISOIRE = ".json.scribouille-tmp"
#: État d'une reprise de la 3.x. Avant le 15/11 : `.json` (`SUFFIXE_ETAT_ANCIEN`).
SUFFIXE_ETAT = ".etat"
SUFFIXE_ETAT_ANCIEN = ".json"
#: Premier constat d'une source introuvable (date ISO), pour `DELAI_ABSENCE_JOURS`.
SUFFIXE_ABSENCE = ".absente"
#: Demande de départ (source, modèle, sortie, réglages), écrite une fois à
#: l'ouverture, vidée sur le disque (`fsync`) puis renommée : si l'état
#: `.etat` est perdu ou abîmé par une coupure de courant, la reprise se
#: reconstruit avec elle et les segments gardés (`_reconstruire`).
SUFFIXE_DEPART = ".depart"


class RepriseIllisible(OSError):
    """Les segments d'une reprise ne se lisent pas pour l'instant (disque, accès) : rien n'est touché."""


def partage() -> bool:
    """Une WhiScribe 2.x installée lit-elle le même dossier de reprises ?"""
    return chemins.donnees_partagees_ancienne_version() is not None


def etat_a_nous(etat: dict | None, partage_: bool | None = None) -> bool:
    """Cet état de reprise est-il de Scribouille 3.x ? Toujours vrai hors partage avec une 2.x."""
    if not (partage() if partage_ is None else partage_):
        return True
    return isinstance(etat, dict) and (etat.get("auteur") == AUTEUR or "demande" in etat or "sortie" in etat)


def demande_de(config: dict) -> dict:
    """La part de la configuration qu'une reprise doit retrouver."""
    return {cle: json.loads(json.dumps(config[cle])) for cle in CLES_DEMANDE if cle in config}


def dossier() -> Path:
    cible = chemins.RACINE / "reprises"
    try:
        cible.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return cible


def cle(source: str | Path, modele: str) -> str:
    """
    Identifiant stable d'un couple fichier source / modèle. Préfixé pour la
    3.x : une WhiScribe 2.x qui partage le dossier calcule la sienne sans, et
    une transcription de la 3.x n'écrit donc jamais par-dessus une des siennes.
    """
    fichier = Path(source)
    empreinte = [AUTEUR, str(fichier.resolve() if fichier.exists() else fichier), modele]
    try:
        etat = fichier.stat()
        empreinte += [str(etat.st_size), str(int(etat.st_mtime))]
    except OSError:
        pass
    return hashlib.sha1("|".join(empreinte).encode("utf-8")).hexdigest()[:16]


def _fichier_etat(identifiant: str) -> Path:
    return dossier() / f"{identifiant}{SUFFIXE_ETAT}"


def _fichier_etat_ancien(identifiant: str) -> Path:
    return dossier() / f"{identifiant}{SUFFIXE_ETAT_ANCIEN}"


def _fichier_segments(identifiant: str) -> Path:
    return dossier() / f"{identifiant}.jsonl"


def _fichier_absence(identifiant: str) -> Path:
    return dossier() / f"{identifiant}{SUFFIXE_ABSENCE}"


def _fichier_depart(identifiant: str) -> Path:
    return dossier() / f"{identifiant}{SUFFIXE_DEPART}"


def _fichiers_de(identifiant: str) -> list[Path]:
    """Tous les fichiers d'une reprise : état (deux noms), segments, constat d'absence, demande de départ."""
    return [_fichier_etat(identifiant), _fichier_etat_ancien(identifiant), _fichier_segments(identifiant),
            _fichier_absence(identifiant), _fichier_depart(identifiant)]


def _etats_presents() -> dict[str, Path]:
    """
    Identifiant -> fichier d'état (le nouveau nom passe avant l'ancien, la
    demande de départ seule vient en dernier : état perdu par une coupure).
    """
    trouves: dict[str, Path] = {}
    racine = chemins.RACINE / "reprises"
    if not racine.is_dir():
        return trouves
    for suffixe in (SUFFIXE_DEPART, SUFFIXE_ETAT_ANCIEN, SUFFIXE_ETAT):
        for fichier in sorted(racine.glob("*" + suffixe)):
            if fichier.name.endswith(suffixe) and fichier.is_file():
                trouves[fichier.name[: -len(suffixe)]] = fichier
    return trouves


# ---------------------------------------------------------------------------
# Lecture tolérante des segments
# ---------------------------------------------------------------------------

def _segment_de(brut) -> Segment | None:
    if not isinstance(brut, dict) or not brut.get("t"):
        return None
    try:
        return Segment(
            debut=float(brut.get("d", 0) or 0),
            fin=float(brut.get("f", 0) or 0),
            texte=str(brut.get("t", "")),
            mots=[
                Mot(texte=str(m.get("t", "")), debut=float(m.get("d", 0) or 0),
                    fin=float(m.get("f", 0) or 0), probabilite=float(m.get("p", 0) or 0))
                for m in (brut.get("m") or []) if isinstance(m, dict) and m.get("t")
            ],
        )
    except (TypeError, ValueError):
        return None


def _ligne(octets: bytes) -> tuple[Segment | None, bool]:
    """(segment, vide) : une ligne du fichier, décodée strictement ; (None, False) si elle est abîmée."""
    propre = octets.strip(b" \t\r\n\x00")
    if not propre:
        return None, True
    try:
        return _segment_de(json.loads(propre.decode("utf-8"))), False
    except (UnicodeDecodeError, ValueError):
        return None, False


def lire_segments(identifiant: str, strict: bool = True) -> list[Segment]:
    """
    Relit les segments déjà transcrits, ligne par ligne. Une ligne abîmée (octet
    invalide, écriture coupée net, zéros laissés par une coupure de courant)
    est écartée et notée au journal ; toutes les autres sont gardées.

    Fichier absent : liste vide. Fichier qui ne se lit pas pour l'instant
    (verrou d'un antivirus, disque débranché) : `RepriseIllisible` avec
    `strict`, liste vide sinon. Jamais rien d'écrit.
    """
    fichier = _fichier_segments(identifiant)
    try:
        contenu = fichier.read_bytes()
    except FileNotFoundError:
        return []
    except OSError as exc:
        if strict:
            raise RepriseIllisible(f"segments de la reprise {identifiant} illisibles : {exc}") from exc
        return []
    segments: list[Segment] = []
    ecartees = 0
    for brute in contenu.split(b"\n"):
        segment, vide = _ligne(brute)
        if segment is not None:
            segments.append(segment)
        elif not vide:
            ecartees += 1
    if ecartees:
        journal.attention("Reprise %s : %s ligne(s) abîmée(s) écartée(s), %s segment(s) gardé(s)",
                          identifiant, ecartees, len(segments))
    return segments


def compter_segments(identifiant: str) -> int:
    """Segments valides gardés pour cette reprise (0 si rien, ou illisible pour l'instant)."""
    return len(lire_segments(identifiant, strict=False))


def _preparer_ajout(fichier: Path) -> bool:
    """
    Avant d'écrire à la suite : une dernière ligne sans fin de ligne est
    retirée si elle est incomplète (coupure au milieu d'une écriture), ou
    complétée si elle est entière. Renvoie vrai s'il faut commencer par un
    saut de ligne (ligne entière à compléter, ou fin du fichier illisible :
    rien n'est tronqué sur une erreur de lecture).
    """
    try:
        taille = fichier.stat().st_size
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if taille == 0:
        return False
    fenetre = min(taille, 4 * 1024 * 1024)
    try:
        with fichier.open("rb") as flux:
            flux.seek(taille - fenetre)
            queue = flux.read(fenetre)
    except OSError:
        return True
    if queue.endswith(b"\n"):
        return False
    dernier = queue.rfind(b"\n")
    if dernier < 0 and fenetre < taille:
        return True  # ligne démesurée : on n'y touche pas
    reste = queue[dernier + 1:]
    segment, vide = _ligne(reste)
    if segment is not None or vide:
        return True
    try:
        with fichier.open("r+b") as flux:
            flux.truncate(taille - len(reste))
    except OSError:
        return True
    journal.attention("Reprise %s : dernière ligne incomplète (%s octets) retirée avant de continuer",
                      fichier.stem, len(reste))
    return False


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
        #: Moteur et modèle réellement utilisés (`noter_calcul`).
        self._calcul: dict = {}
        self._ecoule = 0.0
        self._flux = None
        self._ancien_retire = False
        #: Appelée une fois si l'écriture échoue (disque plein, clé retirée) :
        #: l'interface le dit, au lieu de laisser croire que tout est protégé.
        self.alerte = None

    # -- cycle de vie ------------------------------------------------------

    def ouvrir(self, source: Path, modele: str, duree_audio: float,
               position: float = 0.0, nb_segments: int = 0, ecoule: float = 0.0,
               sortie: str = "", demande: dict | None = None, nouvelle: bool = False) -> None:
        """
        `nouvelle` : rien n'est repris, le fichier des segments repart vide
        (nouvelle transcription, ou « recommencer » demandé explicitement).
        Sans cela, les segments s'ajoutent à la suite, après remise en ordre
        d'une dernière ligne coupée (`_preparer_ajout`).
        """
        if not self.active:
            return
        self.position = position
        self.nb_segments = nb_segments
        self._infos = {
            "version": 1,
            "auteur": AUTEUR,
            "source": str(source),
            "nom": source.name,
            "modele": modele,
            "duree_audio": round(float(duree_audio or 0), 2),
            "debut": datetime.now().isoformat(timespec="seconds"),
        }
        # Dossier de sortie demandé : « scribouille reprendre » y écrit aussi.
        if sortie:
            self._infos["sortie"] = str(sortie)
        # Toute la demande de départ (formats, langue, vocabulaire, voix...).
        if demande:
            self._infos["demande"] = demande
        self._infos.update(self._calcul)
        # La demande de départ, d'abord, durablement : c'est elle qui permet de
        # reprendre si l'état réécrit à chaque segment est perdu.
        _ecrire_depart(self.identifiant, self._infos)
        fichier = _fichier_segments(self.identifiant)
        saut = False if nouvelle else _preparer_ajout(fichier)
        try:
            self._flux = fichier.open("w" if nouvelle else "a", encoding="utf-8")
            if saut:
                self._flux.write("\n")
                self._flux.flush()
        except OSError as exc:
            journal.attention("Sauvegarde progressive désactivée pour ce fichier : %s", exc)
            self.active = False
            return
        self.ecrire_etat(ecoule)

    def noter_calcul(self, cle_calcul: str, modele_reel: str) -> None:
        """
        Situation de calcul (« openvino-GPU », « cpu »...) et modèle réellement
        chargé (le dépôt OpenVINO sur la puce, pas le modèle du catalogue) :
        ce que `scribouille etat` annonce. L'état est réécrit s'il change.
        """
        calcul = {"calcul": str(cle_calcul or ""), "modele_reel": str(modele_reel or "")}
        if calcul == self._calcul:
            return
        self._calcul = calcul
        if self.active and self._infos:
            self._infos.update(calcul)
            self.ecrire_etat(self._ecoule)

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
        # La demande de départ en dernier : tant qu'il reste des segments,
        # elle permet encore de reprendre.
        for fichier in (_fichier_segments(self.identifiant), _fichier_etat(self.identifiant),
                        _fichier_etat_ancien(self.identifiant), _fichier_absence(self.identifiant),
                        _fichier_depart(self.identifiant)):
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
        self._ecoule = float(ecoule or 0)
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
        provisoire = cible.with_name(self.identifiant + SUFFIXE_PROVISOIRE)
        try:
            provisoire.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
            os.replace(provisoire, cible)
        except OSError:
            return
        if not self._ancien_retire:
            # État d'avant le 15/11 (`<clé>.json`) : remplacé par le nouveau.
            self._ancien_retire = True
            try:
                _fichier_etat_ancien(self.identifiant).unlink(missing_ok=True)
            except OSError:
                pass


def session_inactive() -> Session:
    return Session()


def _ecrire_depart(identifiant: str, infos: dict) -> bool:
    """
    La demande de départ, écrite à côté, vidée sur le disque puis renommée :
    après une coupure, l'ancienne ou la nouvelle, jamais une moitié. Une
    écriture qui échoue laisse l'ancienne (et n'empêche pas la transcription).
    """
    cible = _fichier_depart(identifiant)
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}.tmp")
    try:
        with provisoire.open("w", encoding="utf-8") as flux:
            flux.write(json.dumps(infos, ensure_ascii=False))
            flux.flush()
            os.fsync(flux.fileno())
        os.replace(provisoire, cible)
        return True
    except OSError as exc:
        journal.attention("Demande de départ de la reprise %s non écrite : %s", identifiant, exc)
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _reconstruire(identifiant: str) -> tuple[dict | None, str]:
    """
    État perdu ou abîmé (coupure de courant pendant sa réécriture) : rebâti
    avec la demande de départ et les segments gardés. La position est la fin
    du dernier segment lisible, celle d'où la reprise repart de toute façon ;
    seul le temps déjà écoulé est perdu. (état, statut) comme `lire_etat_detail`.
    """
    try:
        texte = _fichier_depart(identifiant).read_bytes()
    except FileNotFoundError:
        return None, "absent"
    except OSError:
        return None, "acces"
    try:
        depart = json.loads(texte.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "abime"
    if not isinstance(depart, dict) or depart.get("auteur") != AUTEUR or not depart.get("source"):
        return None, "abime"
    try:
        segments = lire_segments(identifiant)
    except RepriseIllisible:
        return None, "acces"
    try:
        date = datetime.fromtimestamp(_fichier_segments(identifiant).stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        date = str(depart.get("debut") or "")
    etat = {**depart, "position": round(segments[-1].fin, 2) if segments else 0.0, "nb_segments": len(segments),
            "ecoule": 0.0, "maj": date, "reconstruit": True}
    return etat, "ok"


# ---------------------------------------------------------------------------
# Relecture
# ---------------------------------------------------------------------------

def lire_etat_detail(identifiant: str) -> tuple[dict | None, str]:
    """
    (état, statut) ; statut : « ok », « absent », « acces » (ne se lit pas
    pour l'instant : verrou, disque) ou « abime » (contenu illisible).
    État absent ou abîmé mais demande de départ lisible : l'état est
    reconstruit (`_reconstruire`, marqué `reconstruit`), statut « ok ».
    """
    for fichier in (_fichier_etat(identifiant), _fichier_etat_ancien(identifiant)):
        try:
            texte = fichier.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            return None, "acces"
        try:
            etat = json.loads(texte.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            etat = None
        if isinstance(etat, dict):
            return etat, "ok"
        reconstruit, statut = _reconstruire(identifiant)
        if reconstruit is not None or statut == "acces":
            if reconstruit is not None:
                journal.debug("Reprise %s : état abîmé, reconstruit avec la demande de départ et %s segment(s)",
                              identifiant, reconstruit["nb_segments"])
            return reconstruit, statut
        return None, "abime"
    reconstruit, statut = _reconstruire(identifiant)
    if reconstruit is not None:
        return reconstruit, "ok"
    return None, "acces" if statut == "acces" else "absent" if statut == "absent" else "abime"


def lire_etat(identifiant: str) -> dict | None:
    return lire_etat_detail(identifiant)[0]


def modele_reel(etat: dict) -> str:
    """
    Le modèle réellement chargé pour cette transcription : celui que le moteur
    a noté (`Session.noter_calcul`), sinon, pour un calcul OpenVINO, le dépôt
    OpenVINO du modèle du catalogue, sinon le modèle du catalogue.
    """
    if etat.get("modele_reel"):
        return str(etat["modele_reel"])
    modele = str(etat.get("modele") or "")
    if str(etat.get("calcul") or "").startswith("openvino"):
        from . import presets

        return presets.depot_openvino(modele) or modele
    return modele


def lister() -> list[dict]:
    """
    Transcriptions interrompues que l'on peut reprendre.

    Une transcription coupée avant son premier segment enregistré (pendant la
    lecture de l'audio ou le chargement du modèle) en fait partie : elle
    repart du début (`depuis_debut`), avec toute la demande de départ. Celle
    dont le fichier source a disparu n'est pas proposée : voir `orphelines()`.
    Dossier partagé avec une 2.x : seulement les nôtres (`etat_a_nous`).

    `modele` : le modèle réellement utilisé (`modele_reel`) ; `modele_demande` :
    celui du catalogue, d'après lequel la reprise rechoisit son réglage.
    """
    resultat: list[dict] = []
    if not (chemins.RACINE / "reprises").is_dir():
        return resultat
    commun = partage()
    for identifiant in sorted(_etats_presents()):
        etat = lire_etat(identifiant)
        if not etat or not etat_a_nous(etat, commun):
            continue
        source = Path(etat.get("source", ""))
        if not source.is_file():
            continue
        duree = float(etat.get("duree_audio", 0) or 0)
        position = float(etat.get("position", 0) or 0)
        nb_segments = int(etat.get("nb_segments", 0) or 0)
        resultat.append({
            "cle": identifiant,
            "nom": etat.get("nom", source.name),
            "chemin": str(source),
            "modele": modele_reel(etat),
            "modele_demande": etat.get("modele", ""),
            "calcul": etat.get("calcul", ""),
            "position": position,
            "duree_audio": duree,
            "pct": int(min(99, position / duree * 100)) if duree else 0,
            "nb_segments": nb_segments,
            "depuis_debut": nb_segments == 0 or position <= 0,
            "ecoule": float(etat.get("ecoule", 0) or 0),
            "date": etat.get("maj", etat.get("debut", "")),
        })
    return resultat


def _cle_chemin(chemin: str | Path) -> str:
    try:
        return str(Path(chemin).resolve()).lower()
    except OSError:
        return str(chemin).lower()


def reprises_par_fichier(avec_segments: bool = True) -> dict[str, dict]:
    """
    Chemin résolu (minuscules) -> reprise la plus récente de ce fichier
    (`lister`), quel que soit son modèle ; seulement celles qui ont gardé au
    moins un segment avec `avec_segments`. Sert à ne jamais repartir de zéro
    sans le demander (fichier redéposé, `transcrire` relancé).
    """
    retenues: dict[str, dict] = {}
    for r in sorted(lister(), key=lambda r: str(r.get("date") or "")):
        if avec_segments and not (r["nb_segments"] > 0 or compter_segments(r["cle"]) > 0):
            continue
        retenues[_cle_chemin(r["chemin"])] = r
    return retenues


def reprise_du_fichier(source: str | Path, avec_segments: bool = True) -> dict | None:
    """La reprise la plus récente de ce fichier (voir `reprises_par_fichier`), ou None."""
    return reprises_par_fichier(avec_segments).get(_cle_chemin(source))


def a_garder(identifiant: str) -> bool:
    """
    Cette clé porte-t-elle une reprise à ne pas écraser : un état à nous qui
    annonce des segments, ou des segments valides ? Dans le doute (illisible
    pour l'instant), oui.
    """
    etat, statut = lire_etat_detail(identifiant)
    if statut == "acces":
        return True
    if etat is not None and not etat_a_nous(etat):
        return False
    if etat is not None and int(etat.get("nb_segments") or 0) > 0:
        return True
    try:
        return len(lire_segments(identifiant)) > 0
    except RepriseIllisible:
        return True


def _verrous_des_reprenables() -> set[str]:
    """Noms des verrous qui appartiennent à une transcription reprenable."""
    from . import instance

    noms = set()
    for r in lister():
        try:
            noms.add(instance._fichier_verrou(r["chemin"]).name.lower())
        except OSError:
            continue
    return noms


def fichiers_a_nous() -> list[Path]:
    """
    Tout ce qui, dans `reprises\\`, est de Scribouille 3.x (le dossier entier
    hors partage avec une 2.x) : ce que l'inventaire peut libérer ou effacer.
    """
    if not (chemins.RACINE / "reprises").is_dir():
        return []
    racine = dossier()
    if not partage():
        return sorted(f for f in racine.iterdir())
    trouves: list[Path] = (sorted(racine.glob("*.en-cours")) + sorted(racine.glob("*.en-cours.*.tmp"))
                           + sorted(racine.glob("*" + SUFFIXE_PROVISOIRE))
                           + sorted(racine.glob("*" + SUFFIXE_ABSENCE))
                           + sorted(racine.glob("*" + SUFFIXE_DEPART))
                           + sorted(racine.glob("*" + SUFFIXE_DEPART + ".*.tmp")))
    for identifiant, fichier in sorted(_etats_presents().items()):
        if fichier.suffix in (SUFFIXE_ETAT, SUFFIXE_DEPART) or etat_a_nous(lire_etat(identifiant), True):
            trouves.append(fichier)
            if _fichier_segments(identifiant).exists():
                trouves.append(_fichier_segments(identifiant))
    return sorted(set(trouves))


def _date_ns(fichier: Path) -> int:
    try:
        return int(fichier.stat().st_mtime_ns)
    except OSError:
        return -1


def _absente_depuis(identifiant: str) -> float | None:
    try:
        return datetime.fromisoformat(_fichier_absence(identifiant).read_text(encoding="ascii").strip()).timestamp()
    except (OSError, ValueError):
        return None


def orphelines(jours: int = RETENTION_JOURS) -> list[dict]:
    """
    Ce qui, dans `reprises/`, ne peut plus être repris, avec la raison :
    `source_absente` (dossier joignable, fichier déplacé ou effacé),
    `source_injoignable` (lecteur ou dossier qui ne répond pas : peut-être
    passager), `etat_illisible`, `segments_sans_etat`, `trop_vieille` (plus
    de `jours` jours), `verrou_mort` (verrou d'un processus disparu),
    `provisoire` (écriture coupée net). Ne lit que : rien n'est écrit.

    Chaque entrée dit si `etat --nettoyer` l'efface (`effacable`) et si la
    purge du démarrage peut le faire seule (`purgeable`) : jamais sur une
    absence qui peut être passagère, ni quand des segments valides restent
    (sauf au-delà de la rétention), une source absente seulement après
    `DELAI_ABSENCE_JOURS` jours de constats (`absente_depuis`).

    Le verrou mort d'une transcription encore reprenable n'en est pas une : il
    va avec elle (la reprise le reprend, puis le retire). Dossier partagé
    avec une WhiScribe 2.x : seuls nos fichiers sont regardés ; un état
    illisible, des segments sans état ou une écriture provisoire de la 2.x
    (sans marque) ne sont jamais pris pour les nôtres.
    """
    from . import instance

    if not (chemins.RACINE / "reprises").is_dir():
        return []
    commun = partage()
    maintenant = time.time()
    limite = maintenant - jours * 86400
    trouvees: list[dict] = []

    def noter(fichiers: list[Path], raison: str, nom: str = "", cle_: str = "", effacable: bool = True,
              purgeable: bool = True, **autres) -> None:
        presents = [f for f in fichiers if f.exists()]
        if presents:
            octets = 0
            for f in presents:
                try:
                    octets += f.stat().st_size
                except OSError:
                    pass
            trouvees.append({"cle": cle_, "nom": nom, "raison": raison, "fichiers": [str(f) for f in presents],
                             "octets": octets, "effacable": effacable, "purgeable": purgeable,
                             # Revérifiées juste avant d'effacer (`nettoyer`) : rien
                             # de ce qui a changé entre-temps n'est effacé.
                             "dates": {str(f): _date_ns(f) for f in presents}, **autres})

    def date_de(f: Path) -> float:
        try:
            return f.stat().st_mtime
        except OSError:
            return maintenant

    reprenables = _verrous_des_reprenables()
    for verrou in sorted(dossier().glob("*.en-cours")):
        if verrou.name.lower() in reprenables:
            continue
        if not instance.verrou_tenu(verrou):
            noter([verrou], "verrou_mort")

    def recent(f: Path) -> bool:
        # Peut-être une transcription qui démarre dans un autre processus.
        try:
            return time.time() - f.stat().st_mtime < 60
        except OSError:
            return True

    provisoires = (sorted(dossier().glob("*" + SUFFIXE_PROVISOIRE)) + sorted(dossier().glob("*.en-cours.*.tmp"))
                   + sorted(dossier().glob("*" + SUFFIXE_DEPART + ".*.tmp")))
    if not commun:
        provisoires += sorted(dossier().glob("*.json.tmp"))
    for provisoire in provisoires:
        if not recent(provisoire):
            noter([provisoire], "provisoire")
    def valides_ou_none(identifiant: str) -> int | None:
        # Lecture stricte : des segments qui ne se lisent pas pour l'instant
        # (disque, antivirus) ne comptent jamais pour zéro.
        try:
            return len(lire_segments(identifiant))
        except RepriseIllisible:
            return None

    etats = _etats_presents()
    if not commun:
        for segments in sorted(dossier().glob("*.jsonl")):
            if segments.stem not in etats and not recent(segments):
                valides = valides_ou_none(segments.stem)
                if valides is None:
                    continue
                # Des segments valides se reprennent encore en redéposant le
                # même fichier avec le même modèle (même clé) : gardés.
                noter([segments], "segments_sans_etat", cle_=segments.stem, segments=valides,
                      segments_fichier=str(segments) if valides else "", effacable=valides == 0,
                      purgeable=valides == 0 or date_de(segments) < limite)
    for identifiant, fichier in sorted(etats.items()):
        paire = _fichiers_de(identifiant)
        etat, statut = lire_etat_detail(identifiant)
        if statut == "acces":
            continue  # ne se lit pas pour l'instant : rien n'en est dit ni effacé
        if not etat_a_nous(etat, commun) and not (fichier.suffix in (SUFFIXE_ETAT, SUFFIXE_DEPART) and etat is None):
            continue
        # Date du dernier signe de vie : état, segments ou demande de départ.
        derniere = max((date_de(f) for f in paire if f.exists() and f.suffix != SUFFIXE_ABSENCE),
                       default=maintenant)
        if etat is None:
            valides = valides_ou_none(identifiant)
            if valides is None:
                continue
            noter(paire, "etat_illisible", cle_=identifiant, segments=valides,
                  segments_fichier=str(_fichier_segments(identifiant)) if valides else "", effacable=valides == 0,
                  purgeable=valides == 0 or derniere < limite)
            continue
        nom = str(etat.get("nom") or Path(str(etat.get("source", ""))).name)
        vieille = derniere < limite
        source = str(etat.get("source", ""))
        presence = chemins.constat_presence(source)
        segments_gardes = int(etat.get("nb_segments") or 0)
        if presence == "absent":
            depuis = _absente_depuis(identifiant)
            noter(paire, "source_absente", nom, identifiant, absente_depuis=depuis, source=source,
                  segments=segments_gardes, modele=modele_reel(etat),
                  purgeable=vieille or (depuis is not None and maintenant - depuis >= DELAI_ABSENCE_JOURS * 86400))
            continue
        if presence == "injoignable":
            noter(paire, "source_injoignable", nom, identifiant, effacable=False, purgeable=vieille, source=source,
                  segments=segments_gardes, modele=modele_reel(etat))
            continue
        if vieille:
            noter(paire, "trop_vieille", nom, identifiant)
    return trouvees


def nettoyer(trouvees: list[dict] | None = None, purge: bool = False) -> list[dict]:
    """
    Efface les orphelines (celles données, ou toutes) qui peuvent l'être :
    `effacable` (demande explicite), ou `purgeable` avec `purge`. Renvoie ce
    qui l'a été.
    """
    from . import instance

    faites = []
    for orpheline in (orphelines() if trouvees is None else trouvees):
        if not orpheline.get("purgeable" if purge else "effacable", True):
            continue
        # Entre le constat et l'effacement (un lecteur réseau lent peut faire
        # durer l'inventaire), un fichier a pu changer ou un verrou être repris :
        # alors rien de cette orpheline n'est effacé.
        dates = orpheline.get("dates") or {}
        if any(_date_ns(Path(nom)) != date for nom, date in dates.items()):
            continue
        if orpheline.get("raison") == "verrou_mort" and any(instance.verrou_tenu(Path(nom))
                                                             for nom in orpheline["fichiers"]):
            continue
        reste = []
        for nom in orpheline["fichiers"]:
            try:
                Path(nom).unlink(missing_ok=True)
            except OSError:
                reste.append(nom)
        faites.append({**orpheline, "restes": reste})
    return faites


def _noter_absences(trouvees: list[dict]) -> None:
    """Premier constat d'une source introuvable : daté (le délai part de là). Retour de la source : oublié."""
    absentes = {o["cle"] for o in trouvees if o.get("raison") == "source_absente" and o.get("cle")}
    for identifiant in absentes:
        marque = _fichier_absence(identifiant)
        if not marque.exists():
            try:
                marque.write_text(datetime.now().isoformat(timespec="seconds"), encoding="ascii")
                journal.info("Reprise %s : source introuvable, gardée %s jours avant d'être effacée",
                             identifiant, DELAI_ABSENCE_JOURS)
            except OSError:
                pass
    etats = _etats_presents()
    for marque in dossier().glob("*" + SUFFIXE_ABSENCE):
        identifiant = marque.name[: -len(SUFFIXE_ABSENCE)]
        if identifiant in absentes:
            continue
        etat = lire_etat(identifiant) if identifiant in etats else None
        if identifiant not in etats or (etat and chemins.constat_presence(etat.get("source", "")) == "present"):
            try:
                marque.unlink(missing_ok=True)
            except OSError:
                pass


def _abriter_anciens_etats() -> int:
    """
    Dossier partagé avec une WhiScribe 2.x : nos états d'avant le 15/11
    (`<clé>.json`, marqués à nous) prennent leur nom actuel (`.etat`), que
    la purge de la 2.x ne voit pas. Sans cela, elle les effaçait (avec leurs
    segments) dès que leur source ne répondait pas, même un instant.
    Rend le nombre de renommés.
    """
    if chemins.LECTURE_SEULE or not partage():
        return 0
    faits = 0
    for identifiant, fichier in sorted(_etats_presents().items()):
        if fichier.suffix != SUFFIXE_ETAT_ANCIEN or _fichier_etat(identifiant).exists():
            continue
        etat, statut = lire_etat_detail(identifiant)
        if statut != "ok" or not isinstance(etat, dict) or not etat_a_nous(etat, True) or etat.get("reconstruit"):
            continue
        try:
            os.replace(fichier, _fichier_etat(identifiant))
            faits += 1
            journal.info("Reprise %s : état renommé en %s (à l'abri de la 2.x)", identifiant, SUFFIXE_ETAT)
        except OSError:
            continue
    return faits


def purger(jours: int = RETENTION_JOURS) -> int:
    """
    Au démarrage de la fenêtre : efface les orphelines que rien ne peut
    rendre utiles (`purgeable`), chacune notée au journal avec sa raison
    (rien ne disparaît sans trace). Une source introuvable est datée au
    premier constat et gardée `DELAI_ABSENCE_JOURS` jours.
    """
    _abriter_anciens_etats()
    trouvees = orphelines(jours)
    faites = nettoyer(trouvees, purge=True)
    for f in faites:
        journal.info("Reprise orpheline effacée (%s) : %s %s", f["raison"], f["nom"] or f["cle"] or "",
                     ", ".join(Path(x).name for x in f["fichiers"]))
    effacees = {f["cle"] for f in faites if f.get("cle") and not f.get("restes")}
    try:
        _noter_absences([o for o in trouvees if o.get("cle") not in effacees])
    except OSError:
        pass
    return len(faites)


def oublier(identifiant: str) -> None:
    """Abandon d'une reprise : seulement une des nôtres (jamais celle d'une 2.x qui partage le dossier)."""
    if _fichier_etat_ancien(identifiant).exists() and not _fichier_etat(identifiant).exists() \
            and not etat_a_nous(lire_etat(identifiant)):
        journal.attention("Reprise %s laissée : elle n'est pas de Scribouille 3.x", identifiant)
        return
    Session(identifiant, active=True).effacer()
