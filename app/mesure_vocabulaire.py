"""
Mesure du vocabulaire : ce que gagne chaque étage, sur des réunions avec référence.

Conditions, pour chaque réunion (le réglage est celui de la campagne, par
défaut `ov-turbo-f1`) :

  - sans vocabulaire ;
  - correction seule (étage b, sur la transcription sans amorce : sans
    transcription de plus) ;
  - amorce seule (étage a : une seconde transcription) ;
  - amorce et correction (a puis b).

Mesures : taux d'erreur de mots (même normalisation que la campagne), et sur
les TERMES du vocabulaire : rappel (occurrences dites que la transcription
écrit juste) et précision (occurrences écrites qui sont justes), par
catégorie. Chaque remplacement de l'étage b est classé : utile (faux devenu
juste), fausse correction (juste devenu faux), sans effet (faux resté faux),
indifférent (juste resté juste, une majuscule par exemple).

Protocole honnête : le vocabulaire est appris sur des réunions et mesuré sur
D'AUTRES. Le mode public (`--corpus`) le fait par plis sur le corpus de la
campagne (SUMM-RE, CC BY-SA 4.0) ; il ajoute une borne haute (vocabulaire tiré
des références mêmes, dit « oracle », jamais présenté comme un gain réel) et le
témoin FLEURS du banc avec un vocabulaire de démonstration.

Le rapport ne contient que des nombres : ni terme, ni nom, ni phrase, ni
chemin. Les transcriptions restent dans le dossier de mesure, sur le poste.

    scribouille-verifier.exe --mesurer-vocabulaire --vocabulaire VOCABULAIRE.toml
        --reunion AUDIO --reference RELUE [--reunion AUDIO --reference RELUE ...]
        [--reglage ov-turbo-f1] [--peripherique GPU|CPU] [--recommencer]
    scribouille-verifier.exe --mesurer-vocabulaire --corpus [--reglage ov-turbo-f1]
        [--peripherique CPU] [--corpus-paquet PAQUET.zip]
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import NOM_APPLICATION, VERSION, chemins, journal, lexique
from .vocabulaire_v2 import CATEGORIES, Entree, Faute, Vocabulaire

DOSSIER = chemins.RACINE / "campagnes" / "vocabulaire"
CONDITIONS = ("sans", "correction", "amorce", "amorce_correction")


# ---------------------------------------------------------------------------
# Jetons d'une transcription, avec leur place dans les segments
# ---------------------------------------------------------------------------

def jetons_segments(segments: list[dict]) -> tuple[list[str], list[tuple[int, int, int]]]:
    """Mots normalisés (comme la campagne) et, pour chacun : segment, début, fin (caractères)."""
    from .comparaison import normaliser

    mots: list[str] = []
    places: list[tuple[int, int, int]] = []
    for rang, segment in enumerate(segments):
        texte = str(segment.get("t", ""))
        for trouve in re.finditer(r"\S+", texte):
            for forme in normaliser(trouve.group(0)):
                mots.append(forme)
                places.append((rang, trouve.start(), trouve.end()))
    return mots, places


def _egaux(operations, cote: str, taille: int) -> list[bool]:
    egal = [False] * taille
    for op, i1, _i2, j1, _j2 in operations:
        if op == "egal":
            egal[j1 if cote == "hyp" else i1] = True
    return egal


def _occurrences(mots: list[str], terme: list[str]) -> list[int]:
    n = len(terme)
    return [i for i in range(len(mots) - n + 1) if mots[i:i + n] == terme] if n else []


def termes_normalises(voc: Vocabulaire) -> list[tuple[list[str], str]]:
    from .comparaison import normaliser

    resultat = []
    vus = set()
    for e in voc.actives():
        forme = normaliser(e.forme)
        if forme and tuple(forme) not in vus:
            vus.add(tuple(forme))
            resultat.append((forme, e.categorie))
    return resultat


def mesurer_termes(ref: list[str], hyp: list[str], operations, termes) -> dict[str, Counter]:
    """Par catégorie : occurrences dites, retrouvées ; écrites, justes."""
    egal_ref = _egaux(operations, "ref", len(ref))
    egal_hyp = _egaux(operations, "hyp", len(hyp))
    par_categorie: dict[str, Counter] = {}
    for forme, categorie in termes:
        c = par_categorie.setdefault(categorie, Counter())
        n = len(forme)
        for i in _occurrences(ref, forme):
            c["dits"] += 1
            c["retrouves"] += int(all(egal_ref[i:i + n]))
        for j in _occurrences(hyp, forme):
            c["ecrits"] += 1
            c["justes"] += int(all(egal_hyp[j:j + n]))
    return par_categorie


def classer_remplacements(ref: list[str], avant: list[dict], apres: list[dict], remplacements: list[dict]) -> Counter:
    """Utile, fausse correction, sans effet, indifférent : chaque remplacement jugé contre la référence."""
    from .comparaison import aligner

    mots_avant, places_avant = jetons_segments(avant)
    mots_apres, places_apres = jetons_segments(apres)
    egal_avant = _egaux(aligner(ref, mots_avant).operations, "hyp", len(mots_avant))
    egal_apres = _egaux(aligner(ref, mots_apres).operations, "hyp", len(mots_apres))
    decalage: Counter = Counter()
    bilan: Counter = Counter()
    for r in remplacements:
        s, o = int(r["s"]), int(r["o"])
        avant_debut = o - decalage[s]
        decalage[s] += len(r["b"]) - len(r["a"])

        def juste(places, egal, d, f) -> bool | None:
            indices = [k for k, (rang, c1, c2) in enumerate(places) if rang == s and c1 < f and c2 > d]
            return all(egal[k] for k in indices) if indices else None

        etait = juste(places_avant, egal_avant, avant_debut, avant_debut + len(r["a"]))
        est = juste(places_apres, egal_apres, o, o + len(r["b"]))
        if etait and est:
            bilan["indifferent"] += 1
        elif etait and not est:
            bilan["fausse"] += 1
        elif not etait and est:
            bilan["utile"] += 1
        else:
            bilan["sans_effet"] += 1
        bilan[f"regle_{r.get('regle', '?')}"] += 1
    return bilan


def evaluer(ref_mots: list[str], segments: list[dict], termes) -> dict:
    from .comparaison import aligner

    mots, _places = jetons_segments(segments)
    bilan = aligner(ref_mots, mots)
    return {"mots_ref": len(ref_mots), "erreurs": bilan.editions, "sub": bilan.substitutions,
            "sup": bilan.suppressions, "ins": bilan.insertions,
            "termes": {k: dict(v) for k, v in mesurer_termes(ref_mots, mots, bilan.operations, termes).items()}}


def evaluer_conditions(ref_mots: list[str], sans: list[dict], avec_amorce: list[dict] | None,
                       voc: Vocabulaire) -> dict:
    """Les quatre conditions sur une réunion (ou un extrait)."""
    from .vocabulaire_usage import Correcteur

    termes = termes_normalises(voc)
    correcteur = Correcteur(voc)
    resultats: dict[str, dict] = {"sans": evaluer(ref_mots, sans, termes)}
    corrige = copy.deepcopy(sans)
    remplacements = correcteur.corriger_segments(corrige)
    resultats["correction"] = evaluer(ref_mots, corrige, termes)
    resultats["correction"]["remplacements"] = dict(classer_remplacements(ref_mots, sans, corrige, remplacements))
    if avec_amorce is not None:
        resultats["amorce"] = evaluer(ref_mots, avec_amorce, termes)
        corrige = copy.deepcopy(avec_amorce)
        remplacements = correcteur.corriger_segments(corrige)
        resultats["amorce_correction"] = evaluer(ref_mots, corrige, termes)
        resultats["amorce_correction"]["remplacements"] = dict(
            classer_remplacements(ref_mots, avec_amorce, corrige, remplacements))
    return resultats


def cumuler(liste: list[dict]) -> dict:
    """Additionne les résultats de plusieurs réunions, condition par condition."""
    total: dict[str, dict] = {}
    for resultats in liste:
        for condition, r in resultats.items():
            t = total.setdefault(condition, {"mots_ref": 0, "erreurs": 0, "sub": 0, "sup": 0, "ins": 0,
                                             "termes": {}, "remplacements": Counter()})
            for k in ("mots_ref", "erreurs", "sub", "sup", "ins"):
                t[k] += r[k]
            for categorie, c in r["termes"].items():
                t["termes"].setdefault(categorie, Counter()).update(c)
            t["remplacements"].update(r.get("remplacements") or {})
    return total


# ---------------------------------------------------------------------------
# Rapport (chiffres seulement)
# ---------------------------------------------------------------------------

def _pct(a: float, b: float) -> str:
    return f"{100.0 * a / b:.1f} %".replace(".", ",") if b else "-"


NOMS_CONDITIONS = {"sans": "sans vocabulaire", "correction": "correction seule",
                   "amorce": "amorce seule", "amorce_correction": "amorce et correction"}


def lignes_conditions(total: dict) -> list[str]:
    lignes = []
    for condition in CONDITIONS:
        if condition not in total:
            continue
        t = total[condition]
        tous = Counter()
        for c in t["termes"].values():
            tous.update(c)
        lignes.append(f"  - {NOMS_CONDITIONS[condition]} : taux d'erreur {_pct(t['erreurs'], t['mots_ref'])} "
                      f"({t['sub']} sub, {t['sup']} omissions, {t['ins']} ins, {t['mots_ref']} mots) ; "
                      f"termes : rappel {_pct(tous['retrouves'], tous['dits'])} "
                      f"({tous['retrouves']} sur {tous['dits']}), précision {_pct(tous['justes'], tous['ecrits'])} "
                      f"({tous['justes']} sur {tous['ecrits']})")
        for categorie in CATEGORIES:
            c = t["termes"].get(categorie)
            if not c or not (c["dits"] or c["ecrits"]):
                continue
            lignes.append(f"      {categorie} : rappel {c['retrouves']} sur {c['dits']}, "
                          f"précision {c['justes']} sur {c['ecrits']}")
        r = t["remplacements"]
        if condition in ("correction", "amorce_correction"):
            total_r = sum(r[k] for k in ("utile", "fausse", "sans_effet", "indifferent"))
            lignes.append(f"      remplacements : {total_r} (utiles {r['utile']}, fausses corrections {r['fausse']}, "
                          f"sans effet {r['sans_effet']}, indifférents {r['indifferent']}) ; par règle : "
                          f"fautes {r['regle_faute']}, contexte {r['regle_contexte']}, graphie {r['regle_graphie']}, "
                          f"rapprochement {r['regle_rapprochement']}")
    return lignes


def lignes_vocabulaire(voc: Vocabulaire, nom: str) -> list[str]:
    from .vocabulaire_v2 import resume

    r = resume(voc)
    categories = ", ".join(f"{c} {r['categories'].get(c, 0)}" for c in CATEGORIES)
    return [f"  - {nom} : {r['actifs']} termes actifs ({categories}), {r['fautes']} fautes listées, "
            f"dont {r['fautes_risquees']} écartées par le garde-fou des mots courants"]


def masquer(texte: str) -> str:
    from .banc import _masquer

    return _masquer(texte)


# ---------------------------------------------------------------------------
# Transcriptions (processus séparé, comme la campagne)
# ---------------------------------------------------------------------------

def _transcrire(cle_reglage: str, entrees: list[dict], sortie: Path, peripherique: str,
                vocabulaire: str = "", contexte: str = "", dire: Callable[[str], None] = print) -> dict:
    """Une passe d'un réglage sur des extraits ; reprise si déjà faite."""
    from .campagne import lancer_reglage

    resultat_fichier = sortie.with_suffix(".resultat.json")
    if sortie.is_file() and resultat_fichier.is_file():
        try:
            deja = json.loads(resultat_fichier.read_text(encoding="utf-8"))
            if deja.get("etat") == "ok" and deja.get("extraits") == [e["id"] for e in entrees]:
                return deja
        except (OSError, ValueError):
            pass
    parametres = {"cle": cle_reglage, "peripherique": peripherique, "langue": "fr", "glossaire": False,
                  "corrections": False, "vocabulaire": vocabulaire, "contexte": contexte,
                  "extraits": [{k: e[k] for k in ("id", "wav", "npy") if k in e} for e in entrees],
                  "sortie": str(sortie)}
    duree = max((float(e.get("duree_s") or 120.0) for e in entrees), default=120.0)
    resultat = lancer_reglage(parametres, inactivite_max=900.0 + 4.0 * duree,
                              rappel=lambda p: dire(f"{sortie.stem} : {p['progres']} sur {p['total']}"))
    resultat["extraits"] = [e["id"] for e in entrees]
    resultat_fichier.write_text(json.dumps(resultat, ensure_ascii=False), encoding="utf-8")
    return resultat


def _segments(sortie: Path) -> dict:
    try:
        return json.loads(sortie.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _peripherique(force: str) -> str:
    from .campagne import _peripherique_ov

    return _peripherique_ov(force)


def _entete(titre: str) -> list[str]:
    from . import materiel
    from .campagne import _entete as entete_campagne

    try:
        return entete_campagne(materiel.detecter(), titre)
    except Exception:
        return [f"{NOM_APPLICATION} {VERSION}", ""]


# ---------------------------------------------------------------------------
# Réunions réelles (poste de l'utilisateur, confidentiel)
# ---------------------------------------------------------------------------

def executer_reunions(vocabulaire: str, paires: list[tuple[str, str]], reglage: str = "ov-turbo-f1",
                      peripherique: str = "", recommencer: bool = False,
                      dire: Callable[[str], None] = print) -> dict:
    from . import audio, documents, energie
    from .comparaison import caler_sur_pauses, normaliser
    from .vocabulaire_v2 import lire

    import numpy as np

    depart = time.time()
    voc = lire(vocabulaire)[0]
    # La passe avec amorce dépend du vocabulaire : un autre vocabulaire, une
    # autre passe (la passe sans vocabulaire, elle, est reprise telle quelle).
    empreinte_voc = hashlib.sha256(Path(vocabulaire).read_bytes()).hexdigest()[:10]
    peripherique = _peripherique(peripherique)
    cle_dossier = hashlib.sha256("|".join(f"{Path(a).resolve()}" for a, _r in paires).encode()).hexdigest()[:12]
    dossier = DOSSIER / f"reunions-{cle_dossier}"
    if recommencer and dossier.exists():
        import shutil

        shutil.rmtree(dossier, ignore_errors=True)
    dossier.mkdir(parents=True, exist_ok=True)
    par_reunion = []
    echecs = Counter()
    with energie.sans_veille():
        for rang, (fichier_audio, fichier_ref) in enumerate(paires, 1):
            sous = dossier / f"r{rang}"
            sous.mkdir(exist_ok=True)
            try:
                ref_mots = normaliser(documents.lire_texte(fichier_ref))
            except documents.DocumentIllisible as exc:
                echecs[f"reference_{exc.motif}"] += 1
                continue
            extrait = sous / "extrait.npy"
            if not extrait.is_file():
                dire(f"réunion {rang} : décodage")
                signal = audio.decoder(Path(fichier_audio))
                premier, dernier = caler_sur_pauses(signal, True, True)
                np.save(extrait, np.ascontiguousarray(signal[premier:dernier]))
                del signal
            duree = float(np.load(extrait, mmap_mode="r").shape[0]) / 16000
            entree = [{"id": "reunion", "npy": str(extrait), "duree_s": duree}]
            dire(f"réunion {rang} : transcription sans vocabulaire")
            r1 = _transcrire(reglage, entree, sous / "sans.json", peripherique, dire=dire)
            dire(f"réunion {rang} : transcription avec amorce")
            fichier_amorce = sous / f"amorce-{empreinte_voc}.json"
            r2 = _transcrire(reglage, entree, fichier_amorce, peripherique, vocabulaire=vocabulaire,
                             contexte=Path(fichier_audio).stem, dire=dire)
            if r1.get("etat") != "ok":
                echecs[f"transcription_{r1.get('etat')}"] += 1
                continue
            sans = _segments(sous / "sans.json").get("reunion", {}).get("segments", [])
            avec = (_segments(fichier_amorce).get("reunion", {}).get("segments")
                    if r2.get("etat") == "ok" else None)
            resultats = evaluer_conditions(ref_mots, sans, avec, voc)
            resultats["_meta"] = {"duree": duree, "facteur_sans": r1.get("facteur"), "facteur_amorce": r2.get("facteur"),
                                  "termes_amorce": r2.get("termes_amorce"), "jetons_amorce": r2.get("jetons_amorce"),
                                  "peripherique": r1.get("peripherique") or peripherique}
            (sous / "mesures.json").write_text(json.dumps(resultats, ensure_ascii=False, default=dict), encoding="utf-8")
            par_reunion.append(resultats)
    rapport = rediger_rapport_reunions(voc, par_reunion, echecs, reglage, peripherique, time.time() - depart)
    fichier = dossier / f"rapport-vocabulaire-{datetime.now():%Y%m%d-%H%M}.txt"
    fichier.write_text(rapport, encoding="utf-8")
    return {"rapport": rapport, "fichier": str(fichier)}


def rediger_rapport_reunions(voc: Vocabulaire, par_reunion: list[dict], echecs: Counter, reglage: str,
                             peripherique: str, duree_totale: float) -> str:
    lignes = [f"{NOM_APPLICATION} {VERSION} : mesure du vocabulaire sur des réunions, {datetime.now():%Y-%m-%d %H:%M}",
              ""] + _entete("camp.rapport.titre")[2:]
    lignes += [f"Réglage : {reglage}, périphérique {peripherique or '?'}",
               f"Réunions mesurées : {len(par_reunion)}" + (f" ; écartées : {dict(echecs)}" if echecs else "")]
    lignes += lignes_vocabulaire(voc, "vocabulaire mesuré")
    for rang, r in enumerate(par_reunion, 1):
        m = r.get("_meta", {})
        lignes.append(f"  - réunion {rang} : {float(m.get('duree') or 0) / 60:.0f} min, facteur sans "
                      f"{m.get('facteur_sans')}, avec amorce {m.get('facteur_amorce')}, "
                      f"{m.get('termes_amorce')} termes dans l'amorce ({m.get('jetons_amorce')} jetons)")
    total = cumuler([{k: v for k, v in r.items() if k != "_meta"} for r in par_reunion])
    lignes += ["", "Toutes réunions confondues :"] + lignes_conditions(total)
    lignes += ["", f"Durée : {duree_totale / 60:.0f} min",
               "Ce rapport ne contient que des nombres : ni terme, ni nom, ni phrase, ni chemin."]
    return masquer("\n".join(lignes)) + "\n"


# ---------------------------------------------------------------------------
# Corpus public : protocole par plis, borne haute, témoin FLEURS
# ---------------------------------------------------------------------------

#: Vocabulaire de démonstration du témoin FLEURS (termes de son texte public).
VOCABULAIRE_TEMOIN = (("Auckland", "autre"), ("Amazone", "autre"), ("Ring", "societe"),
                      ("Jamie Siminoff", "personne"), ("PDG", "sigle"))


#: Épreuve des fausses corrections : un vocabulaire FICTIF, étranger au corpus
#: (personnes, sociétés, sigles, outils, termes d'atelier, anglicismes), dont
#: plusieurs noms sont des mots courants (Pierre, Rose, Martin, Claire...). Tout
#: remplacement qu'il provoque sur le corpus est suspect : c'est le compte qui
#: dit si les garde-fous tiennent.
VOCABULAIRE_EPREUVE = (
    [(n, "personne") for n in (
        "Bérénice Lacoste-Vidal", "Aurélien Kerbrat", "Maëlle Ducasse", "Yannick Le Goff", "Solène Marquez",
        "Thibault Vannier", "Inès Bensaïd", "Grégoire Fauvel", "Anaïs Rocheteau", "Corentin Abgrall",
        "Ludivine Sarrazin", "Matthias Kowalski", "Nadège Pellerin", "Quentin Lhermitte", "Sabrina Oukaci",
        "Valentin Desrosiers", "Pierre Lemoine", "Rose Fabre", "Martin Leblanc", "Claire Fontaine",
        "Olivier Marchal", "Aline Dumas", "Hugo Brunet", "Paul Morin", "Julie Garnier", "Kerbrat",
        "Rocheteau", "Desrosiers", "Pellerin", "Abgrall", "Pierre", "Rose", "Martin", "Claire")]
    + [(n, "societe") for n in (
        "Valtéris", "Novacime", "Hexalis", "Sopranel", "Bureautik", "Ardelys", "Logimat Services", "Cofrinor",
        "Transvalor", "Médialis", "Atelier Duroc", "Groupe Vernier", "Batiprest", "Climalys", "Datanor")]
    + [(n, "sigle") for n in (
        "SIRH", "GMAO", "ERP", "CRM", "PLM", "RGPD", "DSI", "MOA", "MOE", "KPI", "SLA", "PRA", "PCA", "CSE",
        "DUERP", "QSE", "PDCA", "ETL", "API", "VPN")]
    + [(n, "produit") for n in (
        "Kubernetes", "GitLab", "SharePoint", "Jira", "Confluence", "PowerBI", "Odoo", "Salesforce", "Teams",
        "PostgreSQL", "Grafana", "Ansible", "Nextcloud", "Zabbix", "Mattermost")]
    + [(n, "metier") for n in (
        "bordereau de livraison", "nomenclature", "ordonnancement", "gamme opératoire", "kanban", "ébavurage",
        "thermolaquage", "décolletage", "emboutissage", "cahier des charges")]
    + [(n, "anglicisme") for n in ("rollout", "go-live", "onboarding", "backlog", "sprint", "feedback",
                                   "workflow", "release")]
)


def vocabulaire_epreuve() -> Vocabulaire:
    return Vocabulaire(nom="épreuve", entrees=[Entree(f, c) for f, c in VOCABULAIRE_EPREUVE])


def _texte_reference(reference: dict) -> str:
    return " ".join(m[0] for m in reference["mots"])


def vocabulaire_oracle(ref_textes: list[str], hyp_textes: list[str]) -> Vocabulaire:
    """Borne haute : les mots rares des références que la transcription n'écrit pas.
    Tiré des réunions MESURÉES elles-mêmes : jamais un gain réel."""
    from .comparaison import normaliser

    compte = Counter()
    for ref in ref_textes:
        for mot in normaliser(ref):
            if len(mot) >= 4 and not lexique.est_courant(mot):
                compte[mot] += 1
    ecrits = Counter()
    for hyp in hyp_textes:
        ecrits.update(normaliser(hyp))
    voc = Vocabulaire(nom="oracle")
    for mot, n in compte.most_common():
        if ecrits[mot] < n:
            voc.entrees.append(Entree(mot, "autre", poids=min(5, n), origine="saisi", etat="actif"))
    return voc


def executer_corpus(reglage: str = "ov-turbo-f1", peripherique: str = "", paquet: str = "",
                    plis: int = 2, dire: Callable[[str], None] = print) -> dict:
    from . import corpus, energie
    from .apprentissage import Reunion, apprendre
    from .campagne import _temoin, mots_reference
    from .vocabulaire_v2 import ecrire

    depart = time.time()
    peripherique = _peripherique(peripherique) or "CPU"
    dossier = DOSSIER / f"corpus-{reglage}-{peripherique.lower()}"
    dossier.mkdir(parents=True, exist_ok=True)
    extraits = corpus.preparer(None, paquet or None, 0, None)
    entrees = [{"id": e.ident, "wav": str(e.wav), "duree_s": e.duree} for e in extraits]
    references = {e.ident: e.reference for e in extraits}
    reunions = sorted({e.reunion for e in extraits})
    with energie.sans_veille():
        dire("corpus : transcription sans vocabulaire")
        base = _transcrire(reglage, entrees, dossier / "sans.json", peripherique, dire=dire)
        if base.get("etat") != "ok":
            raise RuntimeError(f"transcription de référence en échec : {base.get('etat')} {base.get('erreur', '')}")
        sans = _segments(dossier / "sans.json")

        def hyp_texte(textes: dict, ident: str) -> str:
            return " ".join(s["t"] for s in textes[ident]["segments"])

        # 1. Plis : apprendre sur les autres réunions, mesurer sur celles-ci.
        par_pli = []
        vocabulaires = []
        for pli in range(plis):
            mesurees = [r for k, r in enumerate(reunions) if k % plis == pli]
            apprises = [r for r in reunions if r not in mesurees]
            couples = [Reunion(e.ident, hyp_texte(sans, e.ident), _texte_reference(references[e.ident]))
                       for e in extraits if e.reunion in apprises]
            voc, bilan = apprendre(couples, occurrences_min=1)
            for entree in voc.entrees:
                entree.etat = "actif"
            chemin_voc = dossier / f"vocabulaire-pli{pli + 1}.toml"
            ecrire(voc, chemin_voc)
            vocabulaires.append((voc, bilan))
            cibles = [e for e in entrees if any(x.ident == e["id"] and x.reunion in mesurees for x in extraits)]
            dire(f"pli {pli + 1} : transcription avec amorce ({len(voc.entrees)} termes appris)")
            r = _transcrire(reglage, cibles, dossier / f"amorce-pli{pli + 1}.json", peripherique,
                            vocabulaire=str(chemin_voc), dire=dire)
            avec = _segments(dossier / f"amorce-pli{pli + 1}.json") if r.get("etat") == "ok" else {}
            for e in cibles:
                ref_mots, _chev = mots_reference(references[e["id"]])
                par_pli.append(evaluer_conditions(ref_mots, sans[e["id"]]["segments"],
                                                  avec.get(e["id"], {}).get("segments"), voc))

        # 2. Borne haute (oracle) : vocabulaire tiré des références mesurées.
        oracle = vocabulaire_oracle([_texte_reference(references[e.ident]) for e in extraits],
                                    [hyp_texte(sans, e.ident) for e in extraits])
        chemin_oracle = dossier / "vocabulaire-oracle.toml"
        ecrire(oracle, chemin_oracle)
        dire(f"borne haute : transcription avec amorce ({len(oracle.entrees)} termes)")
        r = _transcrire(reglage, entrees, dossier / "amorce-oracle.json", peripherique,
                        vocabulaire=str(chemin_oracle), dire=dire)
        avec = _segments(dossier / "amorce-oracle.json") if r.get("etat") == "ok" else {}
        par_oracle = []
        for e in entrees:
            ref_mots, _chev = mots_reference(references[e["id"]])
            par_oracle.append(evaluer_conditions(ref_mots, sans[e["id"]]["segments"],
                                                 avec.get(e["id"], {}).get("segments"), oracle))

        # 3. Épreuve des fausses corrections : vocabulaire fictif étranger au corpus.
        epreuve = vocabulaire_epreuve()
        chemin_epreuve = dossier / "vocabulaire-epreuve.toml"
        ecrire(epreuve, chemin_epreuve)
        dire(f"épreuve : transcription avec amorce ({len(epreuve.entrees)} termes fictifs)")
        r = _transcrire(reglage, entrees, dossier / "amorce-epreuve.json", peripherique,
                        vocabulaire=str(chemin_epreuve), dire=dire)
        avec = _segments(dossier / "amorce-epreuve.json") if r.get("etat") == "ok" else {}
        par_epreuve = []
        for e in entrees:
            ref_mots, _chev = mots_reference(references[e["id"]])
            par_epreuve.append(evaluer_conditions(ref_mots, sans[e["id"]]["segments"],
                                                  avec.get(e["id"], {}).get("segments"), epreuve))

        # 4. Témoin FLEURS et vocabulaire de démonstration.
        temoin = _temoin(dossier)
        par_temoin = []
        voc_temoin = Vocabulaire(nom="témoin", entrees=[Entree(f, c) for f, c in VOCABULAIRE_TEMOIN])
        if temoin:
            chemin_temoin = dossier / "vocabulaire-temoin.toml"
            ecrire(voc_temoin, chemin_temoin)
            entree_t = [{"id": temoin["id"], "wav": temoin["wav"], "duree_s": 44.0}]
            t1 = _transcrire(reglage, entree_t, dossier / "temoin-sans.json", peripherique, dire=dire)
            t2 = _transcrire(reglage, entree_t, dossier / "temoin-amorce.json", peripherique,
                             vocabulaire=str(chemin_temoin), dire=dire)
            if t1.get("etat") == "ok":
                ref_mots, _chev = mots_reference(temoin["reference"])
                par_temoin.append(evaluer_conditions(
                    ref_mots, _segments(dossier / "temoin-sans.json")[temoin["id"]]["segments"],
                    _segments(dossier / "temoin-amorce.json").get(temoin["id"], {}).get("segments")
                    if t2.get("etat") == "ok" else None, voc_temoin))

    lignes = [f"{NOM_APPLICATION} {VERSION} : mesure du vocabulaire sur le corpus public, {datetime.now():%Y-%m-%d %H:%M}",
              "", f"Réglage : {reglage}, périphérique {peripherique} ; {len(extraits)} extraits de "
              f"{len(reunions)} réunions (SUMM-RE, CC BY-SA 4.0), références en minuscules sans ponctuation",
              "", f"1. Protocole honnête : appris sur {plis - 1} pli(s), mesuré sur l'autre, {plis} plis"]
    for rang, (voc, bilan) in enumerate(vocabulaires, 1):
        lignes += lignes_vocabulaire(voc, f"vocabulaire appris, pli {rang}")
        lignes.append(f"      appris sur {bilan.get('paires', 0)} extraits : {bilan.get('remplacements_vus', 0)} "
                      f"remplacements vus, {bilan.get('fautes_proposees', 0)} retenus")
    lignes += lignes_conditions(cumuler(par_pli))
    lignes += ["", "2. Borne haute (vocabulaire tiré des références mesurées : PAS un gain atteignable)"]
    lignes += lignes_vocabulaire(oracle, "vocabulaire oracle")
    lignes += lignes_conditions(cumuler(par_oracle))
    lignes += ["", "3. Épreuve des fausses corrections : vocabulaire fictif étranger au corpus "
                   "(tout terme écrit ou remplacement est suspect)"]
    lignes += lignes_vocabulaire(epreuve, "vocabulaire d'épreuve")
    lignes += lignes_conditions(cumuler(par_epreuve))
    if par_temoin:
        lignes += ["", "4. Témoin FLEURS (parole lue, 44 s) avec un vocabulaire de démonstration de "
                       f"{len(VOCABULAIRE_TEMOIN)} termes"]
        lignes += lignes_conditions(cumuler(par_temoin))
    lignes += ["", f"Durée : {(time.time() - depart) / 60:.0f} min"]
    rapport = masquer("\n".join(lignes)) + "\n"
    fichier = dossier / f"rapport-vocabulaire-corpus-{datetime.now():%Y%m%d-%H%M}.txt"
    fichier.write_text(rapport, encoding="utf-8")
    return {"rapport": rapport, "fichier": str(fichier)}


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------

def _valeur(arguments: list[str], option: str, defaut: str = "") -> str:
    if option in arguments:
        rang = arguments.index(option)
        if rang + 1 < len(arguments):
            return arguments[rang + 1]
    return defaut


def _paires(arguments: list[str]) -> list[tuple[str, str]]:
    paires: list[list[str]] = []
    for i, option in enumerate(arguments):
        valeur = arguments[i + 1] if i + 1 < len(arguments) else ""
        if option == "--reunion":
            paires.append([valeur, ""])
        elif option == "--reference" and paires:
            paires[-1][1] = valeur
    return [(a, r) for a, r in paires if a and r]


def principal_cli(arguments: list[str]) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass

    def dire(message: str) -> None:
        print("  " + message, flush=True)
        journal.info("Mesure du vocabulaire : %s", message)

    reglage = _valeur(arguments, "--reglage", "ov-turbo-f1")
    try:
        if "--corpus" in arguments:
            resultat = executer_corpus(reglage, _valeur(arguments, "--peripherique"),
                                       _valeur(arguments, "--corpus-paquet"), dire=dire)
        else:
            vocabulaire = _valeur(arguments, "--vocabulaire")
            paires = _paires(arguments)
            if not vocabulaire or not paires:
                print(USAGE)
                return 2
            resultat = executer_reunions(vocabulaire, paires, reglage, _valeur(arguments, "--peripherique"),
                                         "--recommencer" in arguments, dire=dire)
    except journal.ErreurLisible as exc:
        print(f"{exc.titre}\n{exc.message}")
        return 1
    print()
    print(resultat["rapport"])
    print(f"Rapport : {resultat['fichier']}")
    return 0


USAGE = """Usage :
  scribouille-verifier.exe --mesurer-vocabulaire --vocabulaire VOCABULAIRE.toml
      --reunion AUDIO --reference RELUE [--reunion AUDIO --reference RELUE ...]
      [--reglage ov-turbo-f1] [--peripherique GPU|CPU] [--recommencer]
  scribouille-verifier.exe --mesurer-vocabulaire --corpus [--reglage ov-turbo-f1] [--peripherique CPU]"""


def options_reconnues(arguments: list[str]) -> bool:
    return "--mesurer-vocabulaire" in arguments
