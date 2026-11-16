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

Rattacher les entrées qu'un réglage relit
-----------------------------------------
Un chargement qui trouve ses compilés dans le cache ne réécrit rien (puce
graphique) ou seulement une partie (processeur : le décodeur est réécrit,
l'encodeur relu). Juste après l'ouverture, dans le processus qui charge, sont
donc aussi rattachées à la clé du réglage :
  - les entrées que ce processus tient ouvertes ou projetées en mémoire
    (`entrees_tenues` ; relevé sur processeur, OpenVINO 2026.4 : l'encodeur
    reste projeté tant que le modèle est ouvert) ;
  - les entrées dont la date de dernier accès a avancé pendant l'ouverture
    (`acces`). Signal utile mais pas une preuve : Windows peut ne pas tenir
    cette date (réglage `DisableLastAccess`, ou mise à jour au plus une fois
    par heure), et une sauvegarde ou un antivirus qui lit le fichier pendant
    l'ouverture la fait avancer aussi (l'entrée est alors gardée à tort, ce
    qui est le sens sûr). Jamais à la libération : sur une longue
    transcription, une sauvegarde de nuit ferait tout rattacher.
Un réglage dont au moins `COMPILES_PAR_REGLAGE` compilés (`.blob` :
l'encodeur et le décodeur) sont rattachés est « reconnu ».

OpenVINO écrit ses `.blob` en lecture seule (attribut Windows, relevé sur
processeur avec la 2026.4 et sur le portable) : l'attribut est levé juste
avant d'effacer, et remis si l'effacement échoue.

Purge (`purger`), au démarrage de la fenêtre, au début d'une commande qui
transcrit (`transcrire`, `reprendre`) et juste après chaque ouverture d'un
modèle par l'application (une fois les entrées relues rattachées), jamais
pendant le calcul d'un autre processus (un processus qui ouvre ou calcule
avec ce cache y tient une marque d'usage « PID heure-de-création »,
`poser_usage`), jamais une entrée modifiée depuis moins d'un jour, jamais ce
qui n'est pas reconnu :
  - une clé de l'index inutilisée depuis `DELAI_JOURS` jours : ses entrées ;
  - une entrée antérieure reconnue, vue pour la première fois il y a plus de
    `DELAI_JOURS` jours ;
  - au-delà de `PLAFOND_OCTETS` reconnus, mesurés sur le dossier réel après
    chaque effacement (un échec n'est pas décompté, la purge passe à la
    suivante) : les antérieures d'abord, du dernier accès le plus ancien au
    plus récent, mais seulement quand chaque réglage chargé avec succès
    depuis moins de `DELAI_JOURS` jours est reconnu (sinon ses compilés sont
    peut-être parmi elles : elles attendent son prochain chargement, au plus
    `DELAI_JOURS` jours) ; puis les clés les moins récemment utilisées,
    jamais la plus récente.
Ce n'est qu'un cache : une entrée effacée à tort est refaite au chargement
suivant (40 s à 2 min sur la puce graphique), rien d'autre n'est perdu.
Les échecs d'effacement sont notés dans l'index (nombre, taille, cause) pour
que `diagnostic` et `espace` le disent ; ils sont retentés à chaque purge.
Libération à la demande : `scribouille effacer cache_openvino`, et l'écran
« Espace disque » de la fenêtre.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
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
#: Compilés (`.blob`) d'un réglage de Whisper : l'encodeur et le décodeur
#: (relevé sur processeur, OpenVINO GenAI 2026.4). Un réglage dont l'index
#: en tient au moins autant est « reconnu » (voir `_reglages_non_reconnus`).
COMPILES_PAR_REGLAGE = 2
#: Marque de `_reglages_non_reconnus` : aucun chargement réussi noté depuis le délai.
AUCUN_CHARGEMENT = "*"


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
                # Relu sur le fichier : sous Windows, l'entrée du dossier peut
                # retarder sur la taille et la date d'un fichier encore ouvert.
                etat = os.stat(e.path, follow_symlinks=False)
                trouvees[e.name] = (int(etat.st_size), int(etat.st_mtime_ns))
        except OSError:
            continue
    return trouvees


def acces(racine: Path | None = None) -> dict[str, int]:
    """Entrées d'OpenVINO présentes : nom -> date de dernier accès en ns (voir l'en-tête : un signal, pas une preuve)."""
    trouvees: dict[str, int] = {}
    try:
        entrees = list(os.scandir(racine or dossier()))
    except OSError:
        return trouvees
    for e in entrees:
        if est_entree(e.name):
            try:
                if e.is_file(follow_symlinks=False):
                    # scandir garde sous Windows les dates lues avec le dossier :
                    # stat() relu sur le fichier lui-même, pour la date du moment.
                    trouvees[e.name] = int(os.stat(e.path, follow_symlinks=False).st_atime_ns)
            except OSError:
                continue
    return trouvees


def entrees_tenues() -> set[str]:
    """
    Entrées du cache que ce processus tient ouvertes ou projetées en mémoire
    (OpenVINO sur processeur projette l'encodeur tant que le modèle est
    ouvert). Vide si rien ne se relève ; ne lève jamais.
    """
    noms: set[str] = set()
    try:
        import psutil  # type: ignore

        moi = psutil.Process()
        base = os.path.normcase(os.path.realpath(dossier()))
    except Exception:
        return noms
    for relever in (moi.memory_maps, moi.open_files):
        try:
            chemins_vus = [str(m.path) for m in relever()]
        except Exception:
            continue
        for chemin in chemins_vus:
            try:
                parent, nom = os.path.split(chemin)
                if est_entree(nom) and os.path.normcase(os.path.realpath(parent)) == base:
                    noms.add(nom)
            except (OSError, ValueError):
                continue
    return noms


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

def _index_vide() -> dict:
    return {"format": 1, "auteur": AUTEUR, "cles": {}, "entrees": {}, "anterieures": {}, "echecs": {}}


def lire_index() -> dict:
    """L'index, ou un index vide (absent, illisible, ou pas de nous)."""
    try:
        donnees = json.loads((dossier() / NOM_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _index_vide()
    if not isinstance(donnees, dict) or donnees.get("auteur") != AUTEUR:
        return _index_vide()
    index = _index_vide()
    for cle in ("cles", "entrees", "anterieures", "echecs"):
        if isinstance(donnees.get(cle), dict):
            index[cle] = {k: v for k, v in donnees[cle].items() if isinstance(v, dict)}
    return index


def _ecrire_index(index: dict) -> bool:
    cible = dossier() / NOM_INDEX
    texte = json.dumps(index, ensure_ascii=False, indent=1)
    if chemins.contenu_identique(cible, texte):
        return True  # rien de changé : ni réécrit, ni redaté
    provisoire = cible.with_name(f"{cible.name}.{os.getpid()}-{secrets.token_hex(3)}.tmp")
    try:
        provisoire.write_text(texte, encoding="utf-8")
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


def noter_usage(cle: str, infos: dict, avant: dict[str, tuple[int, int]],
                acces_avant: dict[str, int] | None = None, tenues: set[str] | frozenset = frozenset(),
                chargement: bool = False) -> int:
    """
    Note un usage de `cle` : lui sont rattachées les entrées apparues ou
    réécrites depuis `avant` (instantané pris juste avant l'ouverture) et,
    juste après une ouverture réussie (`chargement`), celles que ce processus
    tient (`tenues`) et celles dont le dernier accès a avancé depuis
    `acces_avant`. Rend le nombre d'entrées rattachées. Jamais depuis une
    commande de lecture ; sans effet si le dossier n'existe pas ou si l'index
    est tenu ailleurs trop longtemps.
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
        nouvelles = {n for n, v in apres.items() if avant.get(n) != v}
        relues: set[str] = set()
        if acces_avant is not None:
            acces_apres = acces()
            relues = {n for n, a in acces_apres.items()
                      if n in apres and n in acces_avant and a > acces_avant[n]} - nouvelles
        tenues_ici = (set(tenues) & set(apres)) - nouvelles
        deja = {n for n in (relues | tenues_ici) if index["entrees"].get(n, {}).get("cle") != cle}
        for nom in nouvelles | relues | tenues_ici:
            octets, ecrit = apres[nom]
            index["entrees"][nom] = {"cle": cle, "octets": octets, "ecrit": ecrit / 1e9}
            index["anterieures"].pop(nom, None)
            index["echecs"].pop(nom, None)
        # Clé créée par une ouverture en échec : pas « en service » (date de
        # chargement nulle), elle ne retient pas les entrées d'avant l'index.
        fiche = index["cles"].setdefault(cle, {**infos, "premier_usage": maintenant, "dernier_chargement": 0})
        fiche.update(infos)
        fiche["dernier_usage"] = maintenant
        if chargement:
            fiche["dernier_chargement"] = maintenant
        _ecrire_index(index)
    if nouvelles:
        journal.info("Cache OpenVINO : %s entrée(s) écrite(s) pour %s sur %s (%s)", len(nouvelles),
                     infos.get("modele"), infos.get("peripherique"), _octets(sum(apres[n][0] for n in nouvelles)))
    if deja:
        journal.info("Cache OpenVINO : %s entrée(s) déjà présente(s) rattachée(s) à %s sur %s (%s ; relues %s, "
                     "tenues %s)", len(deja), infos.get("modele"), infos.get("peripherique"),
                     _octets(sum(apres[n][0] for n in deja)), len(deja & relues), len(deja & tenues_ici))
    return len(nouvelles | relues | tenues_ici)


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
    echecs = {n: f for n, f in index["echecs"].items() if n in presentes}
    causes: dict[str, int] = {}
    for f in echecs.values():
        causes[str(f.get("erreur") or "autre")] = causes.get(str(f.get("erreur") or "autre"), 0) + 1
    reconnues_octets = sum(presentes[n][0] for n in reconnues)
    anterieures = [n for n in presentes if n not in index["entrees"]] if adopter else []
    attente: list[dict] = []
    if adopter and anterieures and reconnues_octets > PLAFOND_OCTETS:
        limite = time.time() - DELAI_JOURS * 86400
        attente = [{"modele": index["cles"].get(c, {}).get("modele", ""),
                    "peripherique": index["cles"].get(c, {}).get("peripherique", "")}
                   for c in _reglages_non_reconnus(index, presentes, limite)]
    return {
        "dossier": str(dossier()),
        "existe": dossier().is_dir(),
        "octets": total,
        "nombre": len(presentes),
        "compiles": len(blobs),
        "noyaux": len(presentes) - len(blobs),
        "indexees": len(indexees),
        "reconnues": len(reconnues),
        "reconnues_octets": reconnues_octets,
        "non_reconnues_octets": sum(o for n, (o, _) in presentes.items() if n not in reconnues),
        "reglages": len(index["cles"]),
        "dernier_usage": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(dernier)) if dernier else "",
        "adoption": adopter,
        "delai_jours": DELAI_JOURS,
        "plafond_octets": PLAFOND_OCTETS,
        # Laissées par la dernière purge faute de pouvoir les effacer, encore là.
        "echecs": len(echecs),
        "echecs_octets": sum(presentes[n][0] for n in echecs),
        "echecs_causes": causes,
        # Au-delà du plafond, entrées d'avant l'index gardées : ces réglages en
        # service n'ont pas encore été reconnus (voir l'en-tête du module).
        "attente": attente,
        "anterieures_octets": sum(presentes[n][0] for n in anterieures),
    }


def phrase_etat(res: dict | None = None) -> str:
    """
    Ce que la purge n'a pas pu faire, en une ou deux phrases (vide sinon) :
    entrées qui n'ont pas pu être effacées, et entrées d'avant l'index gardées
    au-delà du plafond en attendant de reconnaître les réglages en service.
    """
    from . import langues

    res = resume() if res is None else res
    phrases = []
    if res.get("echecs"):
        causes = res.get("echecs_causes") or {}
        cause = max(causes, key=causes.get) if causes else "autre"
        cle = "cache_ov.echecs" + (".un" if res["echecs"] == 1 else "")
        phrases.append(langues.t(cle, nombre=res["echecs"], taille=langues.octets(res["echecs_octets"]),
                                 cause=langues.t(f"cache_ov.cause.{cause if cause in CAUSES else 'autre'}")))
    if res.get("attente"):
        reglages = ", ".join(sorted({f"{str(r.get('modele', '')).split('/')[-1]} ({r.get('peripherique', '')})"
                                     for r in res["attente"] if r.get("modele")})) \
            or langues.t("cache_ov.aucun_chargement")
        phrases.append(langues.t("cache_ov.attente", taille=langues.octets(res.get("anterieures_octets", 0)),
                                 reglages=reglages, jours=res.get("delai_jours", DELAI_JOURS)))
    return " ".join(phrases)


def _reglages_non_reconnus(index: dict, presentes: dict, limite: float) -> list[str]:
    """
    Clés chargées avec succès depuis `limite` dont l'index ne tient pas encore
    `COMPILES_PAR_REGLAGE` compilés présents : leurs compilés sont peut-être
    parmi les entrées d'avant l'index. Une clé notée avant ce suivi (sans date
    de chargement) compte par sa date d'usage : dans le doute, elle est en service.
    """
    compiles: dict[str, int] = {}
    for nom, fiche in index["entrees"].items():
        if nom in presentes and nom.lower().endswith(".blob"):
            compiles[fiche.get("cle")] = compiles.get(fiche.get("cle"), 0) + 1
    attente, en_service = [], 0
    for cle, fiche in index["cles"].items():
        usage = float(fiche.get("dernier_usage") or 0)
        date = min(float(fiche.get("dernier_chargement") or 0), usage) if "dernier_chargement" in fiche else usage
        if date >= limite:
            en_service += 1
            if compiles.get(cle, 0) < COMPILES_PAR_REGLAGE:
                attente.append(cle)
    # Aucun chargement réussi depuis le délai : rien ne dit encore quelles
    # entrées servent, aucune d'avant l'index ne part au plafond.
    return attente if en_service else [AUCUN_CHARGEMENT]


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

#: Causes d'échec d'un effacement, dites par `diagnostic` et `espace`.
CAUSES = ("acces_refuse", "ouvert_ailleurs", "projete", "autre")


def _cause(exc: OSError) -> str:
    code = getattr(exc, "winerror", None)
    if code == 5 or (code is None and isinstance(exc, PermissionError)):
        return "acces_refuse"
    if code in (32, 33):
        return "ouvert_ailleurs"
    if code == 1224:
        return "projete"
    return "autre"


def _supprimer(nom: str) -> tuple[int, str]:
    """
    Efface une entrée. Rend (octets libérés, cause d'échec ou ""). OpenVINO
    écrit ses `.blob` en lecture seule : l'attribut est levé juste avant
    l'effacement, et remis si celui-ci échoue (fichier tenu ailleurs).
    """
    chemin = dossier() / nom
    try:
        etat = os.stat(chemin, follow_symlinks=False)
    except FileNotFoundError:
        return 0, ""
    except OSError as exc:
        return 0, _cause(exc)
    lecture_seule = bool(getattr(etat, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_READONLY", 1)) \
        or not etat.st_mode & stat.S_IWRITE
    try:
        if lecture_seule:
            os.chmod(chemin, stat.S_IREAD | stat.S_IWRITE)
        chemin.unlink()
        return int(etat.st_size), ""
    except FileNotFoundError:
        return 0, ""
    except OSError as exc:
        if lecture_seule:
            try:
                os.chmod(chemin, stat.S_IREAD)
            except OSError:
                pass
        journal.debug("Cache OpenVINO : %s laissé (%s)", nom, exc)
        return 0, _cause(exc)


def purger(maintenant: float | None = None, plafond: int | None = None, delai_jours: int | None = None,
           verifier_calcul: bool = True) -> dict:
    """
    Borne le cache (règles en tête du module). Ne lève jamais. Rend le bilan :
    {fait, raison, effacees, octets, restes (nombre d'échecs), echecs (nom ->
    {octets, erreur}), reconnues_octets et total_octets (dossier réel après la
    purge), attente (clés en service pas encore reconnues, si le plafond
    attend à cause d'elles)}.
    """
    bilan = {"fait": False, "raison": "", "effacees": [], "octets": 0, "restes": 0, "echecs": {},
             "reconnues_octets": 0, "total_octets": 0, "attente": []}
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
            # Bornes lues à l'appel (et non figées à la définition) : un essai peut les changer.
            return _purger(bilan, time.time() if maintenant is None else maintenant,
                           PLAFOND_OCTETS if plafond is None else plafond,
                           DELAI_JOURS if delai_jours is None else delai_jours)
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

    releves = [presentes]

    def recente(nom: str) -> bool:
        # Selon chaque relevé (une entrée peut être réécrite entre deux) ;
        # inconnue des relevés (apparue entre deux) : tenue pour récente.
        dates = [r[nom][1] for r in releves if nom in r]
        return not dates or any(maintenant - d / 1e9 < RECENTE_S for d in dates)

    usage = {c: float(f.get("dernier_usage") or 0) for c, f in index["cles"].items()}
    plus_recente = max(usage, key=usage.get) if usage else ""
    echecs: dict[str, dict] = {}

    def effacer(nom: str, raison: str) -> int:
        """Efface et note ; rend les octets libérés, -1 sur un échec (alors rien n'est décompté)."""
        octets, cause = _supprimer(nom)
        if cause:
            echecs[nom] = {"octets": presentes.get(nom, (0, 0))[0], "erreur": cause}
            return -1
        bilan["effacees"].append({"nom": nom, "raison": raison, "octets": octets})
        bilan["octets"] += octets
        index["entrees"].pop(nom, None)
        index["anterieures"].pop(nom, None)
        return octets

    # 1. Délai : clés inutilisées, entrées d'avant l'index vues il y a longtemps.
    for nom, fiche in list(index["entrees"].items()):
        if not recente(nom) and usage.get(fiche.get("cle"), 0) < limite:
            effacer(nom, "inutilisee")
    if adopter:
        for nom, fiche in list(index["anterieures"].items()):
            if not recente(nom) and float(fiche.get("vue") or maintenant) < limite:
                effacer(nom, "anterieure")

    # 2. Plafond, sur ce que le dossier tient vraiment après ces effacements :
    # un échec n'est pas décompté, la boucle passe au suivant.
    reelles = instantane()
    releves.append(reelles)

    def reconnue(nom: str) -> bool:
        return nom in index["entrees"] or (adopter and nom in index["anterieures"])

    reste = sum(o for n, (o, _) in reelles.items() if reconnue(n))
    if reste > plafond:
        candidates = []
        anterieures = [n for n in index["anterieures"] if n in reelles and n not in echecs and not recente(n)] \
            if adopter else []
        attente = _reglages_non_reconnus(index, reelles, limite) if anterieures else []
        if attente:
            # Un réglage en service n'est pas encore reconnu : ses compilés
            # sont peut-être parmi les antérieures. Elles ne partent pas au
            # plafond avant son prochain chargement (la règle du délai borne
            # l'attente), ni ce que l'index tient de lui.
            bilan["attente"] = attente
        else:
            # Dernier accès le plus ancien d'abord (signal faible, mais c'est
            # l'ordre le moins risqué), puis date d'écriture.
            dates_acces = acces()
            candidates += sorted(anterieures, key=lambda n: (dates_acces.get(n, reelles[n][1]), reelles[n][1]))
        candidates += sorted((n for n, f in index["entrees"].items()
                              if n in reelles and n not in echecs and not recente(n)
                              and f.get("cle") != plus_recente and f.get("cle") not in attente),
                             key=lambda n: (usage.get(index["entrees"][n].get("cle"), 0), reelles[n][1]))
        for nom in candidates:
            if reste <= plafond:
                break
            libere = effacer(nom, "plafond")
            if libere >= 0:
                reste -= reelles[nom][0]
    # Clés sans plus aucune entrée et inutilisées depuis le délai : oubliées.
    vivantes = {f.get("cle") for f in index["entrees"].values()}
    for cle in list(index["cles"]):
        if cle not in vivantes and usage.get(cle, 0) < limite:
            index["cles"].pop(cle)
    index["echecs"] = echecs
    _ecrire_index(index)
    # Le bilan dit le dossier tel qu'il est, pas tel qu'il devrait être.
    finales = instantane()
    bilan["fait"] = True
    bilan["echecs"] = echecs
    bilan["restes"] = len(echecs)
    bilan["reconnues_octets"] = sum(o for n, (o, _) in finales.items() if reconnue(n))
    bilan["total_octets"] = sum(o for o, _ in finales.values())
    if bilan["effacees"]:
        par_raison: dict[str, int] = {}
        for e in bilan["effacees"]:
            par_raison[e["raison"]] = par_raison.get(e["raison"], 0) + 1
        journal.info("Cache OpenVINO borné : %s entrée(s) effacée(s), %s (%s) ; reste %s reconnu(s) comme de la 3.x, "
                     "%s dans le dossier", len(bilan["effacees"]), _octets(bilan["octets"]),
                     ", ".join(f"{k} {v}" for k, v in sorted(par_raison.items())),
                     _octets(bilan["reconnues_octets"]), _octets(bilan["total_octets"]))
    if echecs:
        causes: dict[str, int] = {}
        for f in echecs.values():
            causes[f["erreur"]] = causes.get(f["erreur"], 0) + 1
        journal.info("Cache OpenVINO : %s entrée(s) non effacée(s), %s (%s) ; nouvel essai à la prochaine purge",
                     len(echecs), _octets(sum(f["octets"] for f in echecs.values())),
                     ", ".join(f"{k} {v}" for k, v in sorted(causes.items())))
    if bilan["attente"] and bilan["reconnues_octets"] > plafond:
        reglages = [f"{index['cles'][c].get('modele', '')} sur {index['cles'][c].get('peripherique', '')}"
                    for c in bilan["attente"] if c in index["cles"]]
        journal.info("Cache OpenVINO au-delà du plafond (%s reconnus) : entrées d'avant l'index gardées jusqu'au "
                     "prochain chargement %s", _octets(bilan["reconnues_octets"]),
                     f"de ces réglages en service, pas encore reconnus : {', '.join(reglages)}" if reglages
                     else "d'un modèle (aucun noté depuis le suivi du cache)")
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
        from . import langues

        for chemin in fichiers_a_nous():
            libere, cause = _supprimer(chemin.name)
            if cause:
                restes.append(f"{chemin} : {langues.t('cache_ov.cause.' + cause)}")
            else:
                octets += libere
        index = lire_index()
        presentes = instantane()
        index["entrees"] = {n: f for n, f in index["entrees"].items() if n in presentes}
        index["anterieures"] = {n: f for n, f in index["anterieures"].items() if n in presentes}
        _ecrire_index(index)
    return octets, restes
