"""
Cache de compilation d'OpenVINO (`cache-openvino`) : ce qui le remplit, ce qui le borne.

Ce qu'OpenVINO y écrit
----------------------
Le moteur OpenVINO ouvre `WhisperPipeline` avec `CACHE_DIR` (`app/moteur_openvino.py`,
sur la puce graphique, le NPU et le processeur). OpenVINO compile alors chaque
modèle du pipeline (encodeur, décodeur) pour le périphérique et range le
résultat à plat sous un nom opaque : une empreinte décimale de 17 à 20
chiffres, plus `.blob`. Cette empreinte couvre le modèle, le périphérique, les
propriétés de compilation et la version d'OpenVINO. Le greffon de la puce
graphique y range aussi ses noyaux compilés (`<empreinte>.cl_cache`), y compris
pendant la transcription, quand le décodeur rencontre une forme nouvelle.

Rien ne borne ce dossier : OpenVINO n'efface jamais une entrée qu'il ne relit
plus. Chaque combinaison nouvelle ajoute ses compilés : les propriétés du
rythme (priorité de la puce, fils du processeur), chaque réglage d'une
campagne ou d'un banc, le passage d'un modèle à l'autre, une autre version
d'OpenVINO. Relevé sur un portable Core Ultra (11 au 15/11/2026, quatre
paquets d'essai, une campagne de 7 réglages, des essais de propriétés) :
6 088 Mo, dont 10 `.blob` (5 993 Mo, de 165 à 1 280 Mo chacun) et 537
`.cl_cache` (95 Mo) ; aucun `.blob` écrit le dernier jour, les lancements
ordinaires relisant l'existant.

Ce que la 3.x y ajoute
----------------------
Un index (`scribouille-index.json`, dans le dossier) : chaque ouverture d'un
modèle par OpenVINO note les entrées créées entre son début et la libération
du modèle, et la date d'usage de sa clé (modèle, périphérique, propriétés
appliquées, version d'OpenVINO, pilote de la puce). Une entrée de l'index est
reconnue comme écrite par la 3.x. Les entrées trouvées sans index (écrites
avant lui, ou par un processus arrêté net) sont notées à leur premier constat
(`anterieures`). Elles ne sont reconnues comme écrites par la 3.x que si
aucune 2.x capable d'écrire ce cache ne partage le dossier (`adoption_permise`) :
la 2.3.3 et les précédentes n'ont pas de moteur OpenVINO, la 2.4.0 si.

Purge (`purger`), au démarrage de la fenêtre et d'une commande qui transcrit,
jamais pendant un calcul (un processus qui ouvre ou calcule avec ce cache y
tient une marque d'usage « PID heure-de-création », `poser_usage`), jamais une
entrée modifiée depuis moins d'un jour, jamais ce qui n'est pas reconnu :
  - une clé de l'index inutilisée depuis `DELAI_JOURS` jours : ses entrées ;
  - une entrée antérieure reconnue, vue pour la première fois il y a plus de
    `DELAI_JOURS` jours (sa date d'usage n'est pas connaissable : la date de
    dernier accès ne vaut rien, un simple relevé la remet à jour) ;
  - au-delà de `PLAFOND_OCTETS` reconnus : les antérieures d'abord (la plus
    ancienne d'abord), puis les clés les moins récemment utilisées, jamais
    la plus récente.
Ce n'est qu'un cache : une entrée effacée à tort est refaite au chargement
suivant (40 s à 2 min sur la puce graphique), rien d'autre n'est perdu.
Libération à la demande : `scribouille effacer cache_openvino`, et l'écran
« Espace disque » de la fenêtre.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from . import chemins, journal

NOM_DOSSIER = "cache-openvino"
NOM_INDEX = "scribouille-index.json"
NOM_VERROU = "scribouille-index.verrou"
AUTEUR = "scribouille-3"

#: Nom d'une entrée écrite par OpenVINO : empreinte décimale, extension connue.
MOTIF_ENTREE = re.compile(r"^\d{6,24}\.(blob|cl_cache)$", re.IGNORECASE)

#: Clé inutilisée, ou entrée antérieure vue pour la première fois, depuis plus
#: de tant de jours : effacée.
DELAI_JOURS = 30
#: Au-delà, les entrées reconnues les moins utiles partent jusqu'à repasser dessous.
#: Un réglage en service sur la puce graphique en prend de 0,8 à 2 Go
#: (turbo, large-v3) : deux modèles tiennent.
PLAFOND_OCTETS = 4 * 1024 ** 3
#: Jamais touchée : une entrée modifiée depuis moins longtemps (écriture en cours ailleurs).
RECENTE_S = 24 * 3600
#: Verrou de l'index plus vieux que cela : laissé par un processus tombé.
VERROU_PERIME_S = 120


def dossier() -> Path:
    return chemins.RACINE / NOM_DOSSIER


def est_entree(nom: str) -> bool:
    return bool(MOTIF_ENTREE.match(nom or ""))


def instantane(racine: Path | None = None) -> dict[str, tuple[int, int]]:
    """Entrées d'OpenVINO présentes : nom -> (octets, date d'écriture en ns). Erreurs ignorées une à une."""
    trouvees: dict[str, tuple[int, int]] = {}
    try:
        entrees = list(os.scandir(racine or dossier()))
    except OSError:
        return trouvees
    for e in entrees:
        if not est_entree(e.name):
            continue
        try:
            if e.is_file(follow_symlinks=False):
                etat = e.stat(follow_symlinks=False)
                trouvees[e.name] = (int(etat.st_size), int(etat.st_mtime_ns))
        except OSError:
            continue
    return trouvees


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _index_vide() -> dict:
    return {"format": 1, "auteur": AUTEUR, "cles": {}, "entrees": {}, "anterieures": {}}


def lire_index() -> dict:
    """L'index, ou un index vide (absent, illisible, ou pas de nous)."""
    try:
        donnees = json.loads((dossier() / NOM_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _index_vide()
    if not isinstance(donnees, dict) or donnees.get("auteur") != AUTEUR:
        return _index_vide()
    index = _index_vide()
    for cle in ("cles", "entrees", "anterieures"):
        if isinstance(donnees.get(cle), dict):
            index[cle] = {k: v for k, v in donnees[cle].items() if isinstance(v, dict)}
    return index


def _ecrire_index(index: dict) -> bool:
    cible = dossier() / NOM_INDEX
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}-{secrets.token_hex(3)}.tmp")
    try:
        provisoire.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(provisoire, cible)
        return True
    except OSError as exc:
        journal.debug("Index du cache OpenVINO non écrit : %s", exc)
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass
        return False


@contextmanager
def _verrou(attente_s: float = 3.0):
    """Verrou de l'index entre processus (création exclusive). Rend vrai s'il est tenu."""
    fichier = dossier() / NOM_VERROU
    tenu = False
    fin = time.monotonic() + attente_s
    while True:
        try:
            descripteur = os.open(fichier, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descripteur, "w", encoding="ascii") as flux:
                flux.write(str(os.getpid()))
            tenu = True
            break
        except FileExistsError:
            try:
                age = time.time() - fichier.stat().st_mtime
                if age > VERROU_PERIME_S:
                    fichier.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
        except OSError:
            break
        if time.monotonic() >= fin:
            break
        time.sleep(0.05)
    try:
        yield tenu
    finally:
        if tenu:
            try:
                fichier.unlink(missing_ok=True)
            except OSError:
                pass


def cle_reglage(depot: str, peripherique: str, proprietes: dict | None, version_openvino: str,
                pilote: str = "", mots: bool = True) -> tuple[str, dict]:
    """Clé d'un réglage de compilation, et sa description lisible (sans rien de personnel)."""
    infos = {"modele": str(depot or ""), "peripherique": str(peripherique or "").upper(),
             "proprietes": {str(k): str(v) for k, v in sorted((proprietes or {}).items()) if k != "CACHE_DIR"},
             "openvino": str(version_openvino or ""), "pilote": str(pilote or ""), "mots": bool(mots)}
    empreinte = hashlib.sha1(json.dumps(infos, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return empreinte, infos


def noter_usage(cle: str, infos: dict, avant: dict[str, tuple[int, int]]) -> int:
    """
    Note un usage de `cle` : les entrées apparues ou réécrites depuis `avant`
    (instantané pris juste avant l'ouverture) lui sont rattachées. Rend leur
    nombre. Jamais depuis une commande de lecture ; sans effet si le dossier
    n'existe pas ou si l'index est tenu ailleurs trop longtemps.
    """
    if chemins.LECTURE_SEULE or not dossier().is_dir():
        return 0
    with _verrou() as tenu:
        if not tenu:
            journal.debug("Index du cache OpenVINO occupé : usage de %s non noté", cle)
            return 0
        index = lire_index()
        maintenant = time.time()
        apres = instantane()
        nouvelles = [n for n, v in apres.items() if avant.get(n) != v]
        for nom in nouvelles:
            octets, ecrit = apres[nom]
            index["entrees"][nom] = {"cle": cle, "octets": octets, "ecrit": ecrit / 1e9}
            index["anterieures"].pop(nom, None)
        fiche = index["cles"].setdefault(cle, {**infos, "premier_usage": maintenant})
        fiche.update(infos)
        fiche["dernier_usage"] = maintenant
        _ecrire_index(index)
    if nouvelles:
        journal.info("Cache OpenVINO : %s entrée(s) écrite(s) pour %s sur %s (%s)", len(nouvelles),
                     infos.get("modele"), infos.get("peripherique"), _octets(sum(apres[n][0] for n in nouvelles)))
    return len(nouvelles)


def _octets(n: int) -> str:
    from . import langues

    return langues.octets(n)


# ---------------------------------------------------------------------------
# Qui a écrit quoi
# ---------------------------------------------------------------------------

def adoption_permise() -> bool:
    """
    Les entrées sans index peuvent-elles être tenues pour écrites par la 3.x ?
    Oui si aucune 2.x ne partage le dossier de données, ou si celle qui le
    partage est sûrement antérieure à la 2.4 (pas de moteur OpenVINO). Dans
    le doute (2.4, version illisible, registre en échec) : non.
    """
    try:
        if chemins.donnees_partagees_ancienne_version() is None:
            return True
        return chemins.version_2x_sans_openvino()
    except Exception:
        return False


def fichiers_a_nous() -> list[Path]:
    """Les entrées reconnues comme écrites par la 3.x (index, et antérieures si `adoption_permise`)."""
    presentes = instantane()
    if adoption_permise():
        noms = set(presentes)
    else:
        noms = set(lire_index()["entrees"]) & set(presentes)
    return [dossier() / n for n in sorted(noms)]


def resume() -> dict:
    """Ce que `diagnostic` montre : tailles, nombre d'entrées, reconnues, bornes. Ne fait que lire."""
    presentes = instantane()
    index = lire_index()
    adopter = adoption_permise()
    indexees = {n for n in index["entrees"] if n in presentes}
    reconnues = set(presentes) if adopter else indexees
    total = sum(o for o, _ in presentes.values())
    blobs = [n for n in presentes if n.lower().endswith(".blob")]
    dernier = max((float(f.get("dernier_usage") or 0) for f in index["cles"].values()), default=0.0)
    return {
        "dossier": str(dossier()),
        "existe": dossier().is_dir(),
        "octets": total,
        "nombre": len(presentes),
        "compiles": len(blobs),
        "noyaux": len(presentes) - len(blobs),
        "indexees": len(indexees),
        "reconnues": len(reconnues),
        "reconnues_octets": sum(presentes[n][0] for n in reconnues),
        "non_reconnues_octets": sum(o for n, (o, _) in presentes.items() if n not in reconnues),
        "reglages": len(index["cles"]),
        "dernier_usage": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(dernier)) if dernier else "",
        "adoption": adopter,
        "delai_jours": DELAI_JOURS,
        "plafond_octets": PLAFOND_OCTETS,
    }


PREFIXE_USAGE = "scribouille-usage-"
SUFFIXE_USAGE = ".marque"


def _marque_usage(pid: int | None = None) -> Path:
    return dossier() / f"{PREFIXE_USAGE}{os.getpid() if pid is None else pid}{SUFFIXE_USAGE}"


def poser_usage() -> None:
    """
    Ce processus ouvre un modèle avec ce cache, puis calcule avec : marque
    « PID heure-de-création » (comme le verrou d'un fichier en cours, voir
    `instance`), posée avant la compilation, retirée à la libération du
    modèle. Tant qu'elle vit, ni la purge ni la libération ne touchent au cache.
    """
    if chemins.LECTURE_SEULE:
        return
    from . import instance

    try:
        dossier().mkdir(parents=True, exist_ok=True)
        _marque_usage().write_text(instance._contenu(), encoding="ascii")
    except OSError as exc:
        journal.debug("Marque d'usage du cache OpenVINO non posée : %s", exc)


def lever_usage() -> None:
    try:
        _marque_usage().unlink(missing_ok=True)
    except OSError:
        pass


def usages_vivants(nettoyer: bool = True) -> list[int]:
    """
    PID des autres processus qui calculent avec ce cache (marque vivante). Une
    marque qui ne se juge pas encore (vide, illisible pour l'instant) compte
    comme vivante ; une marque morte est retirée (sauf en lecture seule).
    """
    from . import instance

    vivants: list[int] = []
    try:
        marques = sorted(dossier().glob(f"{PREFIXE_USAGE}*{SUFFIXE_USAGE}"))
    except OSError:
        return vivants
    for marque in marques:
        tenu = instance.verrou_tenu(marque)
        if tenu == os.getpid():
            continue
        if tenu:
            vivants.append(tenu)
        elif nettoyer and not chemins.LECTURE_SEULE:
            try:
                marque.unlink(missing_ok=True)
            except OSError:
                pass
    return vivants


def moteurs_vivants() -> list[int]:
    """Autres processus en train de calculer avec ce cache (voir `usages_vivants`)."""
    return usages_vivants()


# ---------------------------------------------------------------------------
# Purge et libération
# ---------------------------------------------------------------------------

def _supprimer(nom: str) -> int:
    chemin = dossier() / nom
    try:
        octets = chemin.stat().st_size
        chemin.unlink()
        return octets
    except FileNotFoundError:
        return 0
    except OSError as exc:
        journal.debug("Cache OpenVINO : %s laissé (%s)", nom, exc)
        return -1


def purger(maintenant: float | None = None, plafond: int = PLAFOND_OCTETS, delai_jours: int = DELAI_JOURS,
           verifier_calcul: bool = True) -> dict:
    """
    Borne le cache (règles en tête du module). Ne lève jamais. Rend le bilan :
    {fait, raison, effacees, octets, restes, reconnues_octets}.
    """
    bilan = {"fait": False, "raison": "", "effacees": [], "octets": 0, "restes": 0, "reconnues_octets": 0}
    try:
        if chemins.LECTURE_SEULE:
            bilan["raison"] = "lecture_seule"
            return bilan
        if not dossier().is_dir():
            bilan["raison"] = "absent"
            return bilan
        if verifier_calcul and moteurs_vivants():
            bilan["raison"] = "calcul_en_cours"
            return bilan
        with _verrou() as tenu:
            if not tenu:
                bilan["raison"] = "index_occupe"
                return bilan
            return _purger(bilan, time.time() if maintenant is None else maintenant, plafond, delai_jours)
    except Exception as exc:  # jamais bloquant : c'est un cache
        journal.debug("Purge du cache OpenVINO interrompue : %s", exc)
        bilan["raison"] = "erreur"
        return bilan


def _purger(bilan: dict, maintenant: float, plafond: int, delai_jours: int) -> dict:
    index = lire_index()
    presentes = instantane()
    # Index remis d'aplomb : entrées disparues oubliées, nouvelles inconnues datées.
    for nom in list(index["entrees"]):
        if nom not in presentes:
            index["entrees"].pop(nom)
    for nom in list(index["anterieures"]):
        if nom not in presentes or nom in index["entrees"]:
            index["anterieures"].pop(nom)
    for nom, (octets, _) in presentes.items():
        if nom not in index["entrees"] and nom not in index["anterieures"]:
            index["anterieures"][nom] = {"vue": maintenant, "octets": octets}
    adopter = adoption_permise()
    limite = maintenant - delai_jours * 86400

    def recente(nom: str) -> bool:
        return maintenant - presentes[nom][1] / 1e9 < RECENTE_S

    usage = {c: float(f.get("dernier_usage") or 0) for c, f in index["cles"].items()}
    plus_recente = max(usage, key=usage.get) if usage else ""
    a_effacer: list[tuple[str, str]] = []
    for nom, fiche in index["entrees"].items():
        if not recente(nom) and usage.get(fiche.get("cle"), 0) < limite:
            a_effacer.append((nom, "inutilisee"))
    if adopter:
        for nom, fiche in index["anterieures"].items():
            if not recente(nom) and float(fiche.get("vue") or maintenant) < limite:
                a_effacer.append((nom, "anterieure"))
    retenues = {n for n, _ in a_effacer}
    reconnues = set(index["entrees"]) | (set(index["anterieures"]) if adopter else set())
    reste = sum(presentes[n][0] for n in reconnues if n not in retenues)
    if reste > plafond:
        candidates = []
        if adopter:
            candidates += sorted((n for n in index["anterieures"] if n not in retenues and not recente(n)),
                                 key=lambda n: presentes[n][1])
        candidates += sorted((n for n, f in index["entrees"].items()
                              if n not in retenues and not recente(n) and f.get("cle") != plus_recente),
                             key=lambda n: (usage.get(index["entrees"][n].get("cle"), 0), presentes[n][1]))
        for nom in candidates:
            if reste <= plafond:
                break
            a_effacer.append((nom, "plafond"))
            reste -= presentes[nom][0]
    for nom, raison in a_effacer:
        octets = _supprimer(nom)
        if octets < 0:
            bilan["restes"] += 1
            continue
        bilan["effacees"].append({"nom": nom, "raison": raison, "octets": octets})
        bilan["octets"] += octets
        index["entrees"].pop(nom, None)
        index["anterieures"].pop(nom, None)
    # Clés sans plus aucune entrée et inutilisées depuis le délai : oubliées.
    vivantes = {f.get("cle") for f in index["entrees"].values()}
    for cle in list(index["cles"]):
        if cle not in vivantes and usage.get(cle, 0) < limite:
            index["cles"].pop(cle)
    _ecrire_index(index)
    bilan["fait"] = True
    bilan["reconnues_octets"] = reste
    if bilan["effacees"]:
        par_raison: dict[str, int] = {}
        for e in bilan["effacees"]:
            par_raison[e["raison"]] = par_raison.get(e["raison"], 0) + 1
        journal.info("Cache OpenVINO borné : %s entrée(s) effacée(s), %s (%s) ; reste %s reconnu(s) comme de la 3.x",
                     len(bilan["effacees"]), _octets(bilan["octets"]),
                     ", ".join(f"{k} {v}" for k, v in sorted(par_raison.items())), _octets(reste))
    return bilan


def liberer() -> tuple[int, list[str]]:
    """
    À la demande : efface toutes les entrées reconnues comme écrites par la
    3.x (et l'index si plus rien de reconnu ne reste), jamais pendant un
    calcul ni ce qui n'est pas reconnu. Rend (octets, restes).
    """
    if moteurs_vivants():
        return 0, [f"{dossier()} : une transcription est en cours, cache laissé"]
    octets, restes = 0, []
    with _verrou() as tenu:
        if not tenu:
            return 0, [f"{dossier()} : index occupé, cache laissé"]
        for chemin in fichiers_a_nous():
            libere = _supprimer(chemin.name)
            if libere < 0:
                restes.append(f"{chemin} : en cours d'utilisation")
            else:
                octets += libere
        index = lire_index()
        presentes = instantane()
        index["entrees"] = {n: f for n, f in index["entrees"].items() if n in presentes}
        index["anterieures"] = {n: f for n, f in index["anterieures"].items() if n in presentes}
        _ecrire_index(index)
    return octets, restes
