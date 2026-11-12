"""
Apprendre un vocabulaire à partir de transcriptions relues et de comptes rendus.

Entrées, par réunion : la transcription brute de Scribouille, la même relue et
corrigée à la main, et, en option, le compte rendu rédigé. D'autres documents
propres peuvent s'ajouter sans transcription en face (`--documents`).

Ce que l'outil en tire, uniquement des PROPOSITIONS (état « propose ») :

1. Remplacements systématiques : la transcription brute et la relue sont
   alignées mot à mot (même alignement que la comparaison et la campagne).
   Chaque passage où elles divergent, court et qui SONNE pareil (clé
   phonétique voisine : une erreur d'oreille, pas une reformulation), donne
   une faute « ce que le modèle a écrit » vers « ce qui était dit », avec le
   nombre d'occurrences et de réunions. Une faute faite de mots courants
   reçoit les voisins qui l'accompagnent le plus souvent (portée en
   contexte) ; sans voisin récurrent, elle est écartée. Une faute que le
   modèle écrit aussi souvent À BON DROIT qu'à tort est écartée.

2. Termes des documents propres : noms propres (majuscule en milieu de
   phrase), sigles, formes à chiffres ou à capitales internes, mots absents du
   lexique du français courant, répétés. Ceux que le modèle n'a jamais écrits
   ainsi passent devant.

Rien n'est appris sans validation : la sortie est un fichier de vocabulaire
dont toutes les entrées sont « proposées ». Il se relit dans l'application
(accepter, refuser, modifier, par lots) ou à la main. Le rapport qui
l'accompagne ne contient que des nombres : il peut sortir du poste, le fichier
de propositions non.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import NOM_APPLICATION, VERSION, chemins, documents, journal, lexique
from .vocabulaire_v2 import Entree, Faute, Vocabulaire, cle

#: Longueur maximale, en mots, d'une forme fautive et de sa correction.
MOTS_MAX_FAUTE = 5
MOTS_MAX_TERME = 4
#: Occurrences minimales d'un remplacement pour être proposé (sauf forme rare
#: phonétiquement très proche du terme : une seule suffit).
OCCURRENCES_MIN = 2
#: Occurrences minimales d'un terme repéré dans les documents propres.
OCCURRENCES_TERME_MIN = 2
CIVILITES = lexique.CIVILITES
INDICES_SOCIETE = {"société", "societe", "groupe", "entreprise", "chez", "client", "fournisseur", "cabinet",
                   "agence", "prestataire", "partenaire", "filiale"}


# ---------------------------------------------------------------------------
# Mots repérés dans un texte : forme comparable, forme écrite, contexte
# ---------------------------------------------------------------------------

@dataclass
class Mot:
    comparable: str
    ecrit: str
    debut_phrase: bool
    debut: int
    fin: int


def mots_reperes(texte: str) -> list[Mot]:
    resultat: list[Mot] = []
    precedent_fin = 0
    for comparable, d, f in lexique.decouper(texte):
        avant = texte[precedent_fin:d]
        debut_phrase = not resultat or bool(re.search(r"[.!?…:\n]\s*$", avant)) or "\n" in avant
        resultat.append(Mot(comparable, texte[d:f], debut_phrase, d, f))
        precedent_fin = f
    return resultat


def _remarquable(mot: Mot) -> bool:
    """Un mot qui a l'allure d'un nom propre, d'un sigle ou d'un terme rare."""
    ecrit = mot.ecrit
    if len(ecrit) < 2 or ecrit.isdigit():
        return False
    if lexique.est_sigle(ecrit):
        return True
    if any(c.isdigit() for c in ecrit) and any(c.isalpha() for c in ecrit):
        return True
    if re.search(r"[a-zà-ÿ][A-ZÀ-Ý]", ecrit):
        return True   # capitale interne : « GitLab », « iPhone »
    if ecrit[:1].isupper() and not mot.debut_phrase:
        return True
    return len(ecrit) >= 4 and not lexique.est_courant(ecrit)


def _texte_entre(texte: str, mots: list[Mot], i: int, j: int) -> str:
    return " ".join(texte[mots[i].debut:mots[j - 1].fin].split())


# ---------------------------------------------------------------------------
# Réunion d'apprentissage
# ---------------------------------------------------------------------------

@dataclass
class Reunion:
    ident: str
    brut: str = ""
    propre: str = ""
    autres: list[str] = field(default_factory=list)   # comptes rendus, documents


@dataclass
class _Constat:
    """Un remplacement vu : forme écrite par le modèle vers forme juste."""

    faute: str
    juste: str
    occurrences: int = 0
    reunions: set = field(default_factory=set)
    voisins: Counter = field(default_factory=Counter)


def _aligner(propre: list[Mot], brut: list[Mot]):
    from .comparaison import aligner

    return aligner([m.comparable for m in propre], [m.comparable for m in brut])


def _proche(juste: str, faute: str) -> bool:
    """La faute SONNE-t-elle comme la forme juste ? (sigles : aussi épelés)"""
    kb = lexique.cle_phonetique(faute)
    if not kb:
        return False
    formes = [juste] + ([lexique.epeler(juste)] if lexique.est_sigle(juste) else [])
    for forme in formes:
        ka = lexique.cle_phonetique(forme)
        if not ka:
            continue
        plafond = max(1, max(len(ka), len(kb)) // 3)
        if lexique.distance(ka, kb, plafond) <= plafond:
            return True
    return False


def apprendre(reunions: list[Reunion], existant: Vocabulaire | None = None,
              occurrences_min: int = OCCURRENCES_MIN) -> tuple[Vocabulaire, dict]:
    """
    Propositions tirées des réunions. Renvoie le vocabulaire proposé et un
    bilan chiffré (aucun mot dedans).
    """
    existant = existant or Vocabulaire()
    constats: dict[tuple[str, str], _Constat] = {}
    justes_brut: Counter = Counter()        # n-grammes écrits par le modèle et justes
    vus_dans_brut: Counter = Counter()      # tout n-gramme du brut (comparable)
    termes_propres: dict[str, dict] = {}
    bilan = Counter()

    for reunion in reunions:
        propre = mots_reperes(reunion.propre) if reunion.propre else []
        brut = mots_reperes(reunion.brut) if reunion.brut else []
        bilan["reunions"] += 1
        bilan["mots_propres"] += len(propre)
        bilan["mots_bruts"] += len(brut)
        comparables_brut = [m.comparable for m in brut]
        for n in range(1, MOTS_MAX_TERME + 1):
            for i in range(len(comparables_brut) - n + 1):
                vus_dans_brut[" ".join(comparables_brut[i:i + n])] += 1

        if propre and brut:
            bilan["paires"] += 1
            resultat = _aligner(propre, brut)
            egaux = [False] * len(brut)
            for op, i1, i2, j1, j2 in resultat.operations:
                if op == "egal":
                    egaux[j1] = True
            # Ce que le modèle écrit juste : utile pour écarter les fautes qui
            # sont aussi des mots dits.
            for n in range(1, MOTS_MAX_FAUTE + 1):
                for j in range(len(brut) - n + 1):
                    if all(egaux[j:j + n]):
                        justes_brut[" ".join(comparables_brut[j:j + n])] += 1
            for i1, i2, j1, j2 in resultat.passages():
                if not (1 <= i2 - i1 <= MOTS_MAX_TERME and 1 <= j2 - j1 <= MOTS_MAX_FAUTE):
                    continue
                juste = _texte_entre(reunion.propre, propre, i1, i2)
                faute = " ".join(m.comparable for m in brut[j1:j2])
                if cle(juste) == faute or not _proche(juste, faute):
                    bilan["passages_ecartes"] += 1
                    continue
                if not any(_remarquable(m) for m in propre[i1:i2]) and lexique.tous_courants(
                        lexique.mots_de(juste)):
                    bilan["passages_ecartes"] += 1
                    continue
                constat = constats.setdefault((faute, juste), _Constat(faute, juste))
                constat.occurrences += 1
                constat.reunions.add(reunion.ident)
                for k in list(range(max(0, j1 - 6), j1)) + list(range(j2, min(len(brut), j2 + 6))):
                    voisin = brut[k].comparable
                    if len(voisin) >= 3:
                        constat.voisins[voisin] += 1

        # Termes des documents propres (relue, compte rendu, autres).
        for document in [reunion.propre] + list(reunion.autres):
            if not document:
                continue
            mots = mots_reperes(document)
            bilan["mots_documents"] += len(mots)
            i = 0
            while i < len(mots):
                if not _remarquable(mots[i]) or mots[i].comparable in CIVILITES:
                    i += 1
                    continue
                j = i + 1
                while j < len(mots) and j - i < MOTS_MAX_TERME and _remarquable(mots[j]) \
                        and not mots[j].debut_phrase and mots[j].debut - mots[j - 1].fin <= 1:
                    j += 1
                forme = _texte_entre(document, mots, i, j)
                k = cle(forme)
                info = termes_propres.setdefault(k, {"formes": Counter(), "occurrences": 0, "reunions": set(),
                                                     "civilite": 0, "societe": 0})
                info["formes"][forme] += 1
                info["occurrences"] += 1
                info["reunions"].add(reunion.ident)
                precedent = mots[i - 1].comparable if i else ""
                if precedent in CIVILITES:
                    info["civilite"] += 1
                if precedent in INDICES_SOCIETE:
                    info["societe"] += 1
                i = j

    propositions = Vocabulaire(nom="Propositions apprises", portee="personnel")
    date = datetime.now().strftime("%Y-%m-%d")

    def entree_pour(forme: str) -> Entree:
        trouvee = propositions.chercher(forme, etat=None)
        if trouvee is None:
            trouvee = Entree(forme, _categorie(forme, termes_propres.get(cle(forme))), origine="apprentissage",
                             etat="propose", ajoute=date)
            propositions.entrees.append(trouvee)
        return trouvee

    # 1. Remplacements systématiques.
    for constat in sorted(constats.values(), key=lambda c: -c.occurrences):
        bilan["remplacements_vus"] += 1
        mots_faute = constat.faute.split()
        rare = not lexique.tous_courants(mots_faute)
        cle_faute = lexique.cle_phonetique(constat.faute)
        formes_justes = [constat.juste] + ([lexique.epeler(constat.juste)]
                                           if lexique.est_sigle(constat.juste) else [])
        tres_proche = any(lexique.distance(cle_faute, lexique.cle_phonetique(f), 1) <= 1 for f in formes_justes)
        if constat.occurrences < occurrences_min and not (rare and tres_proche):
            bilan["remplacements_rares"] += 1
            continue
        if justes_brut[constat.faute] >= constat.occurrences:
            # Le modèle écrit cette forme à bon droit au moins aussi souvent :
            # la remplacer ferait plus de mal que de bien.
            bilan["remplacements_faux_amis"] += 1
            continue
        faute = Faute(constat.faute, vu=constat.occurrences, reunions=len(constat.reunions))
        if not rare:
            # Voisins récurrents : civilités et indices de société d'abord
            # (« monsieur », « société »), puis mots rares, puis mots longs
            # présents au moins une fois sur deux.
            frequents = [(v, n) for v, n in constat.voisins.most_common(12) if n >= 2]
            recurrents = [v for v, _n in frequents if v in CIVILITES]
            recurrents = recurrents or [v for v, _n in frequents if v in INDICES_SOCIETE]
            recurrents = recurrents or [v for v, _n in frequents if not lexique.est_courant(v)]
            recurrents = recurrents or [v for v, n in frequents
                                        if n >= max(2, constat.occurrences // 2) and len(v) >= 4]
            if not recurrents:
                bilan["remplacements_sans_contexte"] += 1
                continue
            faute.voisins = recurrents[:3]
        entree = entree_pour(constat.juste)
        entree.ajouter_faute(faute)
        entree.vu = max(entree.vu, constat.occurrences)
        entree.reunions = max(entree.reunions, len(constat.reunions))
        bilan["fautes_proposees"] += 1

    # 2. Termes repérés dans les documents propres.
    for k, info in termes_propres.items():
        if info["occurrences"] < OCCURRENCES_TERME_MIN and len(info["reunions"]) < 2:
            continue
        forme = info["formes"].most_common(1)[0][0]
        if lexique.tous_courants(lexique.mots_de(forme)) and not lexique.est_sigle(forme) \
                and not re.search(r"[a-zà-ÿ][A-ZÀ-Ý]|\d", forme):
            # Majuscule de titre ou de début de liste sur un mot courant.
            if info["civilite"] == 0 and info["societe"] == 0:
                continue
        jamais_ecrit = vus_dans_brut[k] == 0 and bilan["paires"] > 0
        entree = propositions.chercher(forme, etat=None)
        if entree is None:
            entree = Entree(forme, _categorie(forme, info), origine="compte_rendu", etat="propose", ajoute=date)
            propositions.entrees.append(entree)
            bilan["termes_proposes"] += 1
        elif entree.categorie == "autre":
            entree.categorie = _categorie(forme, info)
        entree.vu = max(entree.vu, info["occurrences"])
        entree.reunions = max(entree.reunions, len(info["reunions"]))
        if jamais_ecrit:
            entree.note = "jamais écrit ainsi par le modèle"

    # Poids : fréquence dans les documents, sur 1 à 5 ; jamais écrit : +1.
    for entree in propositions.entrees:
        base = 1 + min(3, int(entree.vu >= 3) + int(entree.vu >= 8) + int(entree.reunions >= 3))
        entree.poids = min(5, base + int(entree.note.startswith("jamais")))

    # Ce qui est déjà actif ou refusé n'est pas reproposé.
    filtre = Vocabulaire(nom=propositions.nom, portee="personnel")
    for entree in propositions.entrees:
        actif = existant.chercher(entree.forme, etat="actif")
        if existant.chercher(entree.forme, etat="refuse") is not None:
            bilan["deja_refuses"] += 1
            continue
        if actif is not None:
            nouvelles = [f for f in entree.fautes if actif.faute(f.forme) is None]
            if not nouvelles:
                bilan["deja_connus"] += 1
                continue
            entree.fautes = nouvelles
        filtre.entrees.append(entree)
    filtre.entrees.sort(key=lambda e: (-e.poids, -e.vu, e.forme.lower()))
    bilan["propositions"] = len(filtre.entrees)
    bilan["termes_jamais_ecrits"] = sum(1 for e in filtre.entrees if e.note.startswith("jamais"))
    bilan["fautes_total"] = sum(len(e.fautes) for e in filtre.entrees)
    bilan["fautes_en_contexte"] = sum(1 for e in filtre.entrees for f in e.fautes if f.voisins)
    par_categorie = Counter(e.categorie for e in filtre.entrees)
    return filtre, {**bilan, "categories": dict(par_categorie)}


def _categorie(forme: str, info: dict | None) -> str:
    if lexique.est_sigle(forme):
        return "sigle"
    if info and info.get("civilite"):
        return "personne"
    if info and info.get("societe"):
        return "societe"
    if re.search(r"\d|[a-zà-ÿ][A-ZÀ-Ý]", forme):
        return "produit"
    if forme[:1].islower():
        return "anglicisme" if _anglais(forme) else "metier"
    return "autre"


def _anglais(forme: str) -> bool:
    from .comparaison import MOTS_ANGLAIS

    return any(m in MOTS_ANGLAIS for m in lexique.mots_de(forme))


# ---------------------------------------------------------------------------
# Rapport (chiffres seulement)
# ---------------------------------------------------------------------------

def rediger_rapport(bilan: dict, illisibles: int) -> str:
    from .vocabulaire_v2 import CATEGORIES

    lignes = [f"{NOM_APPLICATION} {VERSION} : apprentissage du vocabulaire, {datetime.now():%Y-%m-%d %H:%M}",
              "",
              f"Réunions lues : {bilan.get('reunions', 0)} (dont {bilan.get('paires', 0)} avec transcription "
              f"brute et relue), documents illisibles : {illisibles}",
              f"Mots : {bilan.get('mots_bruts', 0)} bruts, {bilan.get('mots_propres', 0)} relus, "
              f"{bilan.get('mots_documents', 0)} dans les documents propres",
              "",
              f"Remplacements vus : {bilan.get('remplacements_vus', 0)} formes distinctes",
              f"  proposés comme fautes : {bilan.get('fautes_proposees', 0)}",
              f"  écartés, trop rares : {bilan.get('remplacements_rares', 0)}",
              f"  écartés, le modèle les écrit aussi à bon droit : {bilan.get('remplacements_faux_amis', 0)}",
              f"  écartés, mots courants sans voisin récurrent : {bilan.get('remplacements_sans_contexte', 0)}",
              f"  passages divergents non retenus (reformulation, mot courant) : {bilan.get('passages_ecartes', 0)}",
              f"Termes repérés dans les documents propres (sans faute en face) : {bilan.get('termes_proposes', 0)}",
              f"Déjà dans le vocabulaire : {bilan.get('deja_connus', 0)} ; déjà refusés : {bilan.get('deja_refuses', 0)}",
              "",
              f"Propositions : {bilan.get('propositions', 0)}, dont jamais écrites ainsi par le modèle : "
              f"{bilan.get('termes_jamais_ecrits', 0)}",
              f"  fautes associées : {bilan.get('fautes_total', 0)}, dont en contexte (voisins) : "
              f"{bilan.get('fautes_en_contexte', 0)}"]
    categories = bilan.get("categories") or {}
    lignes.append("  par catégorie : " + ", ".join(f"{c} {categories.get(c, 0)}" for c in CATEGORIES))
    lignes += ["", "Ce rapport ne contient que des nombres. Le fichier de propositions, lui, contient des",
               "termes : il reste sur le poste."]
    return "\n".join(lignes) + "\n"


# ---------------------------------------------------------------------------
# Ligne de commande
# ---------------------------------------------------------------------------

USAGE = """Usage :
  scribouille.com --apprendre-vocabulaire
      --brut BRUT.txt --propre RELUE.docx [--cr CR.docx] [--brut ... --propre ... --cr ...]
      [--manifeste LISTE.txt] [--documents DOC1 DOC2 ...] [--sortie PROPOSITIONS.toml]
      [--rapport CHIFFRES.txt] [--importer] [--occurrences-min 2]
  scribouille.com --apprendre-vocabulaire --importer-propositions PROPOSITIONS.toml

  LISTE.txt : une réunion par ligne, « brut | relue | compte rendu » (le compte rendu est facultatif).
  --importer : verse les propositions dans le vocabulaire personnel, à l'état « propose »,
               pour les relire dans l'application. Rien ne devient actif sans validation."""


def lire_manifeste(chemin: Path) -> list[tuple[str, str, str]]:
    triplets = []
    for ligne in chemin.read_text(encoding="utf-8-sig").splitlines():
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        morceaux = [m.strip().strip('"') for m in re.split(r"\s*[|\t]\s*", ligne.strip())]
        while len(morceaux) < 3:
            morceaux.append("")
        triplets.append((morceaux[0], morceaux[1], morceaux[2]))
    return triplets


def _triplets_arguments(arguments: list[str]) -> tuple[list[tuple[str, str, str]], list[str]]:
    triplets: list[list[str]] = []
    documents_seuls: list[str] = []
    i = 0
    while i < len(arguments):
        option = arguments[i]
        valeur = arguments[i + 1] if i + 1 < len(arguments) else ""
        if option == "--brut":
            triplets.append([valeur, "", ""])
            i += 2
        elif option in ("--propre", "--cr"):
            if not triplets or (option == "--propre" and triplets[-1][1]) or (option == "--cr" and triplets[-1][2]):
                triplets.append(["", "", ""])
            triplets[-1][1 if option == "--propre" else 2] = valeur
            i += 2
        elif option == "--documents":
            i += 1
            while i < len(arguments) and not arguments[i].startswith("--"):
                documents_seuls.append(arguments[i])
                i += 1
        else:
            i += 1
    return [tuple(t) for t in triplets], documents_seuls


def _valeur(arguments: list[str], option: str, defaut: str = "") -> str:
    if option in arguments:
        rang = arguments.index(option)
        if rang + 1 < len(arguments):
            return arguments[rang + 1]
    return defaut


def charger_reunions(triplets, documents_seuls) -> tuple[list[Reunion], int]:
    reunions: list[Reunion] = []
    illisibles = 0

    def lire(chemin: str) -> str:
        nonlocal illisibles
        if not chemin:
            return ""
        try:
            return documents.lire_texte(chemin)
        except documents.DocumentIllisible as exc:
            illisibles += 1
            journal.attention("Apprentissage : document illisible (%s)", exc.motif)
            return ""

    for rang, (brut, propre, cr) in enumerate(triplets, 1):
        reunions.append(Reunion(f"r{rang}", lire(brut), lire(propre), [t for t in [lire(cr)] if t]))
    if documents_seuls:
        reunions.append(Reunion("documents", "", "", [t for t in (lire(d) for d in documents_seuls) if t]))
    return reunions, illisibles


def principal_cli(arguments: list[str]) -> int:
    from . import vocabulaire_v2

    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass
    a_importer = _valeur(arguments, "--importer-propositions")
    if a_importer:
        # Propositions déjà relues (et éventuellement corrigées à la main) :
        # versées dans le vocabulaire personnel, à valider dans l'application.
        try:
            relues, _remarques = vocabulaire_v2.lire(a_importer)
        except (OSError, vocabulaire_v2.ErreurFormat) as exc:
            print(f"Fichier illisible : {exc}")
            return 1
        personnel = vocabulaire_v2.charger_personnel()
        retour = vocabulaire_v2.importer_propositions(personnel, relues)
        vocabulaire_v2.ecrire(personnel)
        print(f"Versées dans le vocabulaire personnel, à valider dans l'application : {retour['ajoutees']} "
              f"(déjà connues ou refusées : {retour['ignorees']} ; écartées gardées comme refusées : "
              f"{len(relues.par_etat('refuse'))})")
        return 0
    triplets, documents_seuls = _triplets_arguments(arguments)
    manifeste = _valeur(arguments, "--manifeste")
    if manifeste:
        triplets += lire_manifeste(Path(manifeste))
    if not triplets and not documents_seuls:
        print(USAGE)
        return 2
    occurrences_min = int(_valeur(arguments, "--occurrences-min", str(OCCURRENCES_MIN)) or OCCURRENCES_MIN)
    resultat = executer(triplets, documents_seuls, sortie=_valeur(arguments, "--sortie"),
                        rapport=_valeur(arguments, "--rapport"), importer="--importer" in arguments,
                        occurrences_min=occurrences_min)
    print(resultat["rapport"])
    print(f"Propositions : {resultat['propositions']}")
    print(f"Rapport      : {resultat['chiffres']}")
    if resultat.get("importees"):
        print(f"Versées dans le vocabulaire personnel, à relire : {resultat['importees']['ajoutees']} "
              f"(déjà connues ou refusées : {resultat['importees']['ignorees']})")
    return 0


def executer(triplets, documents_seuls, sortie: str = "", rapport: str = "", importer: bool = False,
             occurrences_min: int = OCCURRENCES_MIN) -> dict:
    """Apprend, écrit les propositions et le rapport de chiffres ; rend les chemins et le bilan."""
    from . import vocabulaire_v2

    reunions, illisibles = charger_reunions(triplets, documents_seuls)
    existant, _problemes = vocabulaire_v2.effectif()
    propositions, bilan = apprendre(reunions, existant, occurrences_min)
    cible = Path(sortie or (chemins.RACINE / f"vocabulaire-propositions-{datetime.now():%Y%m%d-%H%M}.toml"))
    vocabulaire_v2.ecrire(propositions, cible)
    texte = rediger_rapport(bilan, illisibles)
    chemin_rapport = Path(rapport or cible.with_name(cible.stem + "-chiffres.txt"))
    chemin_rapport.write_text(texte, encoding="utf-8")
    resultat = {"propositions": str(cible), "chiffres": str(chemin_rapport), "rapport": texte,
                "bilan": bilan, "illisibles": illisibles, "importees": None}
    if importer:
        personnel = vocabulaire_v2.charger_personnel()
        retour = vocabulaire_v2.importer_propositions(personnel, propositions)
        vocabulaire_v2.ecrire(personnel)
        resultat["importees"] = {"ajoutees": retour["ajoutees"], "ignorees": retour["ignorees"]}
    return resultat


def options_reconnues(arguments: list[str]) -> bool:
    return "--apprendre-vocabulaire" in arguments
