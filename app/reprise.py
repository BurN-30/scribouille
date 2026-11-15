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

La sauvegarde est ouverte dès qu'un fichier est pris en charge, avant la
lecture de l'audio et le chargement du modèle : une transcription coupée avant
son premier segment reste reprenable, elle repart alors du début avec toute la
demande de départ.

À la reprise, seule la fin du signal est repassée au décodeur, à partir du
dernier segment enregistré. Les fichiers sont effacés dès qu'une transcription
se termine normalement. Ce qui ne peut plus être repris (source disparue, état
illisible, segments sans état, plus de trente jours) est « orphelin » :
`orphelines()` le liste avec sa raison, `scribouille etat` le montre,
`scribouille etat --nettoyer` l'efface, et la fenêtre le purge à son démarrage
en journalisant chaque fichier retiré.

Dossier partagé avec une WhiScribe 2.x installée (même `reprises\\`, même
format) : seuls les fichiers de Scribouille 3.x sont lus, proposés ou
effacés. Un état est à nous s'il porte `auteur` (`AUTEUR`), ou la demande de
départ que seule la 3.x enregistre ; ses segments vont avec lui. Les verrous
(`.en-cours`) et les écritures provisoires (`.json.scribouille-tmp`) n'ont
pas d'équivalent en 2.x. La clé d'une transcription de la 3.x ne peut pas
non plus tomber sur celle d'une 2.x (`cle`). Le reste n'est jamais touché ;
une fois la 2.x désinstallée, tout le dossier redevient le nôtre.
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
        #: Moteur et modèle réellement utilisés (`noter_calcul`).
        self._calcul: dict = {}
        self._ecoule = 0.0
        self._flux = None
        #: Appelée une fois si l'écriture échoue (disque plein, clé retirée) :
        #: l'interface le dit, au lieu de laisser croire que tout est protégé.
        self.alerte = None

    # -- cycle de vie ------------------------------------------------------

    def ouvrir(self, source: Path, modele: str, duree_audio: float,
               position: float = 0.0, nb_segments: int = 0, ecoule: float = 0.0,
               sortie: str = "", demande: dict | None = None, nouvelle: bool = False) -> None:
        """
        `nouvelle` : rien n'est repris, le fichier des segments repart vide.
        Sans cela, une nouvelle transcription d'un fichier qui avait laissé une
        reprise ajoutait ses segments après les anciens, et une seconde coupure
        donnait un texte en double à la reprise.
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
        try:
            self._flux = _fichier_segments(self.identifiant).open("w" if nouvelle else "a", encoding="utf-8")
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
        provisoire = cible.with_name(cible.stem + SUFFIXE_PROVISOIRE)
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
    for fichier in sorted(dossier().glob("*.json")):
        identifiant = fichier.stem
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
    trouves: list[Path] = sorted(racine.glob("*.en-cours")) + sorted(racine.glob("*" + SUFFIXE_PROVISOIRE))
    for fichier in sorted(racine.glob("*.json")):
        if etat_a_nous(lire_etat(fichier.stem), True):
            trouves.append(fichier)
            if _fichier_segments(fichier.stem).exists():
                trouves.append(_fichier_segments(fichier.stem))
    return trouves


def orphelines(jours: int = RETENTION_JOURS) -> list[dict]:
    """
    Ce qui, dans `reprises/`, ne peut plus être repris, avec la raison :
    `source_absente` (fichier déplacé ou effacé), `etat_illisible`,
    `segments_sans_etat`, `trop_vieille` (plus de `jours` jours), `verrou_mort`
    (verrou d'un processus disparu), `provisoire` (écriture coupée net).

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
    limite = time.time() - jours * 86400
    trouvees: list[dict] = []

    def noter(fichiers: list[Path], raison: str, nom: str = "", cle_: str = "") -> None:
        presents = [f for f in fichiers if f.exists()]
        if presents:
            trouvees.append({"cle": cle_, "nom": nom, "raison": raison,
                             "fichiers": [str(f) for f in presents],
                             "octets": sum(f.stat().st_size for f in presents)})

    reprenables = _verrous_des_reprenables()
    for verrou in sorted(dossier().glob("*.en-cours")):
        if verrou.name.lower() in reprenables:
            continue
        try:
            pid = int(verrou.read_text(encoding="ascii").strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if not instance._vivant(pid):
            noter([verrou], "verrou_mort")

    def recent(f: Path) -> bool:
        # Peut-être une transcription qui démarre dans un autre processus.
        try:
            return time.time() - f.stat().st_mtime < 60
        except OSError:
            return True

    provisoires = sorted(dossier().glob("*" + SUFFIXE_PROVISOIRE))
    if not commun:
        provisoires += sorted(dossier().glob("*.json.tmp"))
    for provisoire in provisoires:
        if not recent(provisoire):
            noter([provisoire], "provisoire")
    etats = {f.stem for f in dossier().glob("*.json")}
    if not commun:
        for segments in sorted(dossier().glob("*.jsonl")):
            if segments.stem not in etats and not recent(segments):
                noter([segments], "segments_sans_etat", cle_=segments.stem)
    for fichier in sorted(dossier().glob("*.json")):
        identifiant = fichier.stem
        paire = [fichier, _fichier_segments(identifiant)]
        etat = lire_etat(identifiant)
        if not etat_a_nous(etat, commun):
            continue
        if not etat:
            noter(paire, "etat_illisible", cle_=identifiant)
            continue
        nom = str(etat.get("nom") or Path(str(etat.get("source", ""))).name)
        if not Path(etat.get("source", "")).is_file():
            noter(paire, "source_absente", nom, identifiant)
            continue
        try:
            vieille = fichier.stat().st_mtime < limite
        except OSError:
            vieille = False
        if vieille:
            noter(paire, "trop_vieille", nom, identifiant)
    return trouvees


def nettoyer(trouvees: list[dict] | None = None) -> list[dict]:
    """Efface les orphelines (celles données, ou toutes) ; renvoie ce qui l'a été."""
    faites = []
    for orpheline in (orphelines() if trouvees is None else trouvees):
        reste = []
        for nom in orpheline["fichiers"]:
            try:
                Path(nom).unlink(missing_ok=True)
            except OSError:
                reste.append(nom)
        faites.append({**orpheline, "restes": reste})
    return faites


def purger(jours: int = RETENTION_JOURS) -> int:
    """Au démarrage de la fenêtre : efface les orphelines, chacune notée au
    journal avec sa raison (rien ne disparaît sans trace)."""
    faites = nettoyer(orphelines(jours))
    for f in faites:
        journal.info("Reprise orpheline effacée (%s) : %s %s", f["raison"], f["nom"] or f["cle"] or "",
                     ", ".join(Path(x).name for x in f["fichiers"]))
    return len(faites)


def oublier(identifiant: str) -> None:
    """Abandon d'une reprise : seulement une des nôtres (jamais celle d'une 2.x qui partage le dossier)."""
    if _fichier_etat(identifiant).exists() and not etat_a_nous(lire_etat(identifiant)):
        journal.attention("Reprise %s laissée : elle n'est pas de Scribouille 3.x", identifiant)
        return
    Session(identifiant, active=True).effacer()
