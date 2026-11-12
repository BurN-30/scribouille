"""
Vue de lecture : relire une transcription dans l'application.

Jusqu'ici l'application écrivait des fichiers et les listait. Pour relire le
résultat il fallait sortir, ouvrir le Bloc-notes, chercher. C'est pourtant à la
relecture que tout se joue : vérifier un nom propre, retrouver une décision,
préparer un compte rendu.

Ce module prépare tout ce que la vue affiche, et fait le travail que le
JavaScript n'a pas à faire :

  - situer chaque segment du compagnon JSON dans le fichier texte, à la
    lettre : les paragraphes affichés sont ceux du fichier, jamais une
    reconstruction ;
  - y joindre la confiance mot à mot ;
  - se rabattre sur le fichier texte seul quand le compagnon manque ou ne
    décrit plus ce fichier ;
  - écrire une modification (correction, passage réécrit ou supprimé,
    locuteur renommé) dans le fichier texte, le compagnon et les sous-titres
    d'un seul geste, sans jamais toucher à l'en-tête du fichier.

Règle d'or : le texte affiché, le `.txt`, le compagnon et les exports disent
la même chose. Une écriture qui la romprait est annulée et dite : chaque
modification est contrôlée après coup, en relisant les fichiers écrits.
"""

from __future__ import annotations

import copy
import json
import os
import re
from collections import namedtuple
from datetime import datetime
from pathlib import Path

from . import chemins, compagnon, gabarit, journal, langues, sorties, vocabulaire

#: Taille au-delà de laquelle un fichier texte n'est pas chargé en entier.
#: Cent mille caractères représentent déjà plusieurs heures de réunion.
LIMITE_CARACTERES = 400_000

#: Ligne de séparation de l'en-tête écrit par `app/sorties.py`.
_BARRE = "=" * 68

#: Les deux libellés produits par l'application, plus un nom propre quelconque.
#: « Speaker » comme « Locuteur » sont reconnus quelle que soit la langue de
#: l'interface : une transcription écrite en français se relit en anglais.
_MOTIF_LOCUTEUR = re.compile(
    r"((?:Locuteur|Speaker)\s+\d+|[A-ZÉÈÀÂÎÔÛÇ][\w'’\- ]{0,28})\s:\s"
)
#: Heure en tête de paragraphe, telle que `app/sorties.py` l'écrit.
_MOTIF_HEURE = re.compile(r"\[\d{2}:\d{2}:\d{2}\] ")
_MOTIF_HORODATAGE = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})\][ \t]*")
#: Ce qui sépare deux paragraphes : au moins une ligne vide.
_MOTIF_ENTRE_PARAGRAPHES = re.compile(r"[ \t]*\n[ \t]*\n\s*")


# ---------------------------------------------------------------------------
# Découpe de l'en-tête
# ---------------------------------------------------------------------------

def separer_entete(contenu: str) -> tuple[str, str]:
    """Sépare l'en-tête encadré du corps du texte. Sans en-tête, tout est corps."""
    if not contenu.startswith(_BARRE):
        return "", contenu
    position = contenu.rfind("\n" + _BARRE)
    if position < 0:
        return "", contenu
    fin = position + 1 + len(_BARRE)
    return contenu[:fin], contenu[fin:].lstrip("\n")


def _valeur_entete(entete: str, cle: str) -> str:
    """
    Valeur d'une ligne « Étiquette   : valeur » de l'en-tête.

    L'étiquette doit occuper toute la partie gauche, deux points compris : sans
    cela « Compute » attraperait la ligne « Compute time », et l'ordre des
    lignes ferait la loi.
    """
    motif = re.compile(rf"^{re.escape(cle)}\s*:\s*(.*)$")
    for ligne in entete.splitlines():
        trouve = motif.match(ligne)
        if trouve:
            return trouve.group(1).strip()
    return ""


def _valeur_entete_traduite(entete: str, cle_texte: str) -> str:
    """
    Valeur d'une ligne d'en-tête, quelle que soit la langue du fichier.

    Un `.txt` produit en français doit rester lisible après une bascule en
    anglais : on essaie donc les libellés de TOUTES les langues connues, pas
    seulement ceux de la langue courante.
    """
    etiquettes = dict.fromkeys(
        [langues.t(cle_texte)]
        + [langues.TEXTES[code][cle_texte] for code in langues.LANGUES]
    )
    for etiquette in etiquettes:
        valeur = _valeur_entete(entete, etiquette)
        if valeur:
            return valeur
    return ""


# ---------------------------------------------------------------------------
# Le compagnon situé dans le fichier
# ---------------------------------------------------------------------------

def situer(corps: str, segments: list) -> list[dict] | None:
    """
    Situe chaque segment du compagnon dans le corps du fichier, à la lettre.

    Le corps est fait de paragraphes séparés par une ligne vide ; chacun porte
    éventuellement une heure et un locuteur en tête, puis les textes de ses
    segments joints par une espace (`app/sorties.py`, `corps_texte`). Les
    coupures de paragraphe sont LUES dans le fichier, pas recalculées : une
    correction qui retire un point ne déplace donc aucun paragraphe.

    Renvoie un plan, un élément par paragraphe : « tete » (début de l'heure ou
    du locuteur), « debut » et « fin » du texte, « locuteur », et pour chaque
    segment son rang et ses bornes. None si le compagnon ne décrit pas
    exactement ce corps : modifié hors de l'application, ou d'une autre
    transcription.
    """
    plan: list[dict] = []
    courant: dict | None = None
    position = 0
    for rang, segment in enumerate(segments or []):
        if not isinstance(segment, dict):
            continue
        texte = str(segment.get("t") or "").strip()
        if not texte:
            continue
        if courant is not None and corps.startswith(" " + texte, position):
            debut = position + 1
        else:
            if courant is not None:
                separation = _MOTIF_ENTRE_PARAGRAPHES.match(corps, position)
                if not separation:
                    return None
                position = separation.end()
            tete = position
            heure = _MOTIF_HEURE.match(corps, position)
            if heure:
                position = heure.end()
            locuteur = str(segment.get("l") or "")
            if locuteur and corps.startswith(locuteur + " : ", position):
                position += len(locuteur) + 3
            else:
                locuteur = ""
            if not corps.startswith(texte, position):
                return None
            debut = position
            courant = {"tete": tete, "debut": debut, "fin": debut, "locuteur": locuteur,
                       "nom": debut - len(locuteur) - 3 if locuteur else None, "segments": []}
            plan.append(courant)
        fin = debut + len(texte)
        courant["segments"].append((rang, debut, fin))
        courant["fin"] = fin
        position = fin
    if not plan or corps[position:].strip():
        return None
    return plan


def _plan_du_texte(corps: str, avec_locuteurs: bool = True) -> list[dict]:
    """
    Plan d'un corps sans compagnon : les paragraphes sont les blocs séparés par
    une ligne vide, heure et locuteur lus en tête. Le texte de chaque
    paragraphe est pris tel quel, sans rien recoller ni recouper.
    """
    debuts = [0] + [m.end() for m in _MOTIF_ENTRE_PARAGRAPHES.finditer(corps)]
    fins = [m.start() for m in _MOTIF_ENTRE_PARAGRAPHES.finditer(corps)] + [len(corps)]
    plan: list[dict] = []
    for a, b in zip(debuts, fins):
        bloc = corps[a:b]
        tete = a + len(bloc) - len(bloc.lstrip())
        fin = a + len(bloc.rstrip())
        if fin <= tete:
            continue
        position = tete
        secondes = None
        heure = _MOTIF_HORODATAGE.match(corps, position)
        if heure and heure.end() < fin:
            h, m, s = (int(x) for x in heure.groups())
            secondes = float(h * 3600 + m * 60 + s)
            position = heure.end()
        locuteur = ""
        nom = _MOTIF_LOCUTEUR.match(corps, position) if avec_locuteurs else None
        if nom and nom.end() < fin:
            locuteur = nom.group(1)
            position = nom.end()
        plan.append({"tete": tete, "debut": position, "fin": fin, "locuteur": locuteur,
                     "nom": nom.start() if locuteur else None, "segments": None, "heure": secondes})
    return plan


def _paragraphes_du_texte(corps: str, plan: list[dict] | None = None) -> list[dict]:
    """Paragraphes affichés sans compagnon : chaque mot garde ce qui le précède dans le fichier."""
    paragraphes: list[dict] = []
    for p in plan if plan is not None else _plan_du_texte(corps):
        texte = corps[p["debut"]:p["fin"]]
        heure = p.get("heure")
        mots = []
        position = 0
        for trouve in re.finditer(r"\S+", texte):
            mots.append({"t": trouve.group(0), "e": texte[position:trouve.start()], "p": -1.0,
                         "d": heure or 0.0})
            position = trouve.end()
        # « debut » vaut None quand le fichier ne dit pas l'heure : la vue
        # n'affiche alors aucune heure, plutôt qu'un « 0:00 » inventé.
        paragraphes.append({"debut": heure, "fin": heure, "locuteur": p["locuteur"], "texte": texte,
                            "mots": mots, "o": p["debut"]})
    return paragraphes


#: Écart maximal, en caractères, entre deux mots consécutifs rattachés au
#: texte : au-delà, le mot cherché est tenu pour absent du texte plutôt que
#: rattaché à une occurrence lointaine.
_ECART_MAXIMAL = 80

#: Un écart entre deux mots placés : blancs et ponctuation de tête, partie
#: écrite, ponctuation et blancs de queue.
_MOTIF_ECART = re.compile(r"^([\s\W]*)(.*?\w)([\W]*)$", re.DOTALL)


def _chercher_mot(texte: str, jeton: str, depart: int) -> int:
    """Position du jeton dans le texte à partir de `depart`, entre deux frontières de mot."""
    position = texte.find(jeton, depart)
    while 0 <= position <= depart + _ECART_MAXIMAL:
        avant = texte[position - 1] if position > 0 else ""
        apres = texte[position + len(jeton):position + len(jeton) + 1]
        colle_avant = jeton[:1].isalnum() and avant.isalnum()
        colle_apres = jeton[-1:].isalnum() and apres.isalnum()
        if not colle_avant and not colle_apres:
            return position
        position = texte.find(jeton, position + 1)
    return -1


def _ecart_marque(ecart: str, debut: float) -> tuple[list[dict], str]:
    """
    Un écart qui contient des lettres, dans un segment changé par le
    vocabulaire, est un mot corrigé : il devient un mot marqué (« c »), sans
    confiance. Renvoie ce mot (ou rien) et ce qui doit précéder le mot suivant.
    Le texte rendu est inchangé : seule la découpe change.
    """
    trouve = _MOTIF_ECART.match(ecart)
    if not trouve:
        return [], ecart
    tete, ecrit, queue = trouve.groups()
    return [{"t": ecrit, "e": tete, "p": -1.0, "c": 1, "d": debut}], queue


def _placer_mots(texte: str, mots: list[dict], marquer: bool = False) -> tuple[list[dict], str]:
    """
    Rattache chaque mot à sa place dans le texte du segment.

    Le texte du segment fait foi : c'est lui que le fichier contient. Chaque mot
    reçoit dans « e » ce qui le précède exactement dans ce texte (rien devant
    l'apostrophe de « l'Amazon » ni devant le trait d'union de « peut-être »,
    une espace ailleurs, ou un mot que le moteur n'a pas détaillé). Un mot qui
    n'est plus dans le texte, après une correction par exemple, n'est pas
    affiché : sa confiance portait sur une forme qui n'existe plus. Avec
    `marquer` (segment changé par le vocabulaire), le texte qui ne vient
    d'aucun mot du moteur est rendu comme un mot corrigé. Renvoie les mots
    placés et le texte restant après le dernier.
    """
    places: list[dict] = []
    position = 0
    for mot in mots:
        trouve = _chercher_mot(texte, mot["t"], position)
        if trouve < 0:
            continue
        ecart = texte[position:trouve]
        if marquer:
            corriges, ecart = _ecart_marque(ecart, mot["d"])
            places.extend(corriges)
        places.append({**mot, "e": ecart})
        position = trouve + len(mot["t"])
    reste = texte[position:]
    if marquer and reste:
        dernier = places[-1]["d"] if places else (mots[0]["d"] if mots else 0.0)
        corriges, reste = _ecart_marque(reste, dernier)
        places.extend(corriges)
    return places, reste


def _paragraphes_situes(donnees: dict, corps: str, plan: list[dict]) -> list[dict]:
    """
    Paragraphes affichés, d'après le plan : texte pris dans le fichier,
    confiance prise dans le compagnon. Un segment sans mots reste lisible,
    simplement sans confiance ; un segment corrigé après coup par le
    vocabulaire montre les mots changés.
    """
    segments = donnees.get("segments") or []
    corriges = {
        int(r.get("s", -1))
        for r in ((donnees.get("vocabulaire") or {}).get("remplacements") or [])
        if isinstance(r, dict) and not r.get("annule")
    }
    paragraphes: list[dict] = []
    for situe in plan:
        mots: list[dict] = []
        for n, (rang, debut, fin) in enumerate(situe["segments"]):
            segment = segments[rang]
            texte = corps[debut:fin]
            separateur = " " if n else ""
            liste = [
                {
                    "t": str(mot["t"]),
                    "p": round(float(mot.get("p", 1) or 0), 3),
                    "d": round(float(mot.get("d", 0) or 0), 2),
                    **({"c": 1} if mot.get("c") else {}),
                }
                for mot in segment.get("m") or []
                if isinstance(mot, dict) and mot.get("t")
            ]
            places, reste = _placer_mots(texte, liste, marquer=rang in corriges)
            if places:
                places[0]["e"] = separateur + places[0]["e"]
            else:
                reste = separateur + reste
            mots.extend(places)
            if reste:
                mots.append({"t": "", "e": reste, "p": -1.0,
                             "d": round(float(segment.get("d", 0) or 0), 2)})
        premier = segments[situe["segments"][0][0]]
        dernier = segments[situe["segments"][-1][0]]
        paragraphes.append({
            "debut": float(premier.get("d", 0) or 0),
            "fin": float(dernier.get("f", 0) or 0),
            "locuteur": situe["locuteur"],
            "texte": corps[situe["debut"]:situe["fin"]],
            "mots": mots,
            "o": situe["debut"],
        })
    return paragraphes


def _reunir_elisions(mots: list[dict]) -> list[dict]:
    """
    Un mot collé au précédent (« d » puis « 'emploi », « peut » puis « -être »)
    ne fait qu'un à l'écran : surligné, lu ou visé en entier, pas à moitié. La
    confiance retenue est la plus basse des deux. Le texte rendu est inchangé.
    """
    reunis: list[dict] = []
    for mot in mots:
        precedent = reunis[-1] if reunis else None
        if precedent and mot["t"] and precedent["t"] and not mot.get("e"):
            precedent = dict(precedent)
            precedent["t"] += mot["t"]
            if precedent["p"] < 0 or (0 <= mot["p"] < precedent["p"]):
                precedent["p"] = mot["p"]
            if mot.get("c"):
                precedent["c"] = 1
            reunis[-1] = precedent
            continue
        reunis.append(mot)
    return reunis


# ---------------------------------------------------------------------------
# État d'une transcription
# ---------------------------------------------------------------------------

def _recaler(corps: str, donnees: dict) -> dict | None:
    """
    Recale le compagnon sur un fichier texte retouché hors de l'application.

    Les mots des segments et ceux du fichier sont alignés (début et fin
    communs écartés d'abord, puis comparaison mot à mot du milieu) ; chaque
    mot du fichier revient au segment dont il vient, un mot ajouté au segment
    voisin. Les segments reprennent ainsi le texte du fichier en gardant leurs
    heures et la confiance des mots restés identiques. Un segment coupé en
    deux par une ligne vide ajoutée donne deux segments. Renvoie le compagnon
    recalé, ou None si le fichier ne se laisse pas décrire ainsi.
    """
    import difflib

    segments = donnees.get("segments") or []
    avec_locuteurs = any(isinstance(s, dict) and s.get("l") for s in segments)
    plan = _plan_du_texte(corps, avec_locuteurs)
    anciens = [(mot, rang) for rang, s in enumerate(segments) if isinstance(s, dict)
               for mot in str(s.get("t") or "").split()]
    nouveaux = [(m.group(0), k, p["debut"] + m.start(), p["debut"] + m.end())
                for k, p in enumerate(plan) for m in re.finditer(r"\S+", corps[p["debut"]:p["fin"]])]
    if not anciens or not nouveaux:
        return None
    proprietaire: list[int | None] = [None] * len(nouveaux)
    tete = 0
    while tete < min(len(anciens), len(nouveaux)) and anciens[tete][0] == nouveaux[tete][0]:
        proprietaire[tete] = anciens[tete][1]
        tete += 1
    queue = 0
    while (queue < min(len(anciens), len(nouveaux)) - tete
           and anciens[-1 - queue][0] == nouveaux[-1 - queue][0]):
        proprietaire[len(nouveaux) - 1 - queue] = anciens[-1 - queue][1]
        queue += 1
    milieu_a = anciens[tete:len(anciens) - queue]
    milieu_n = nouveaux[tete:len(nouveaux) - queue]
    if milieu_a and milieu_n:
        comparaison = difflib.SequenceMatcher(None, [m for m, _ in milieu_a], [m[0] for m in milieu_n],
                                              autojunk=False)
        for etiquette, i1, i2, j1, j2 in comparaison.get_opcodes():
            if etiquette == "equal":
                for d in range(j2 - j1):
                    proprietaire[tete + j1 + d] = milieu_a[i1 + d][1]
            elif etiquette == "replace":
                for j in range(j1, j2):
                    proprietaire[tete + j] = milieu_a[i1 + (j - j1) * (i2 - i1) // (j2 - j1)][1]
    # Mots ajoutés : au segment du mot qui précède, sinon de celui qui suit.
    for j in range(1, len(nouveaux)):
        if proprietaire[j] is None:
            proprietaire[j] = proprietaire[j - 1]
    for j in range(len(nouveaux) - 2, -1, -1):
        if proprietaire[j] is None:
            proprietaire[j] = proprietaire[j + 1]
    if proprietaire[0] is None:
        return None
    for j in range(1, len(nouveaux)):
        proprietaire[j] = max(proprietaire[j], proprietaire[j - 1])

    groupes: list[list] = []
    for j, (_, k, debut, fin) in enumerate(nouveaux):
        dernier = groupes[-1] if groupes else None
        if dernier and dernier[1] == k and (dernier[0] == proprietaire[j] or corps[dernier[3]:debut] != " "):
            dernier[3] = fin
        else:
            groupes.append([proprietaire[j], k, debut, fin])
    par_rang: dict[int, list] = {}
    for groupe in groupes:
        par_rang.setdefault(groupe[0], []).append(groupe)

    recales: list = []
    correspondance: dict[int, int] = {}
    for rang, segment in enumerate(segments):
        correspondance[rang] = len(recales)
        origine = segment if isinstance(segment, dict) else {}
        liste = par_rang.get(rang) or []
        if not liste:
            vide = copy.deepcopy(origine)
            vide["t"] = ""
            recales.append(vide)
            continue
        for n, (_, k, debut, fin) in enumerate(liste):
            nouveau = copy.deepcopy(origine) if n == 0 else {"d": origine.get("f", 0), "f": origine.get("f", 0)}
            nouveau["t"] = corps[debut:fin]
            if plan[k]["locuteur"]:
                nouveau["l"] = plan[k]["locuteur"]
            else:
                nouveau.pop("l", None)
            recales.append(nouveau)
    if situer(corps, recales) is None:
        return None
    resultat = copy.deepcopy(donnees)
    resultat["segments"] = recales
    for remplacement in (resultat.get("vocabulaire") or {}).get("remplacements") or []:
        if isinstance(remplacement, dict) and int(remplacement.get("s", -1)) in correspondance:
            remplacement["s"] = correspondance[int(remplacement["s"])]
    return resultat


def _etat(fichier: Path, contenu: str | None = None, recaler: bool = True) -> dict:
    """
    Ce que l'on sait d'une transcription : le fichier, son compagnon, et où se
    trouve chaque paragraphe. Avec un compagnon qui décrit ce fichier, le plan
    vient de `situer` ; avec un compagnon qui ne le décrit plus (fichier
    retouché dans un éditeur), le compagnon est recalé en mémoire sur le
    fichier ; sinon, le plan vient du fichier seul. « recale » le signale.
    """
    if contenu is None:
        contenu = fichier.read_text(encoding="utf-8")
    entete, corps = separer_entete(contenu)
    separation = contenu[len(entete):len(contenu) - len(corps)]
    donnees = compagnon.lire(fichier)
    plan = None
    recale = False
    if donnees and len(contenu) <= LIMITE_CARACTERES:
        plan = situer(corps, donnees.get("segments") or [])
        if plan is None and recaler and _compagnon_parlant(donnees):
            recalees = _recaler(corps, donnees)
            if recalees is not None:
                donnees, plan, recale = recalees, situer(corps, recalees["segments"]), True
    if plan is None:
        avec_locuteurs = not donnees or any(
            isinstance(s, dict) and s.get("l") for s in donnees.get("segments") or [])
        plan_texte = _plan_du_texte(corps, avec_locuteurs)
    else:
        plan_texte = None
    return {
        "fichier": fichier, "contenu": contenu, "entete": entete, "separation": separation,
        "corps": corps, "donnees": donnees, "situe": plan is not None, "recale": recale,
        "plan": plan if plan is not None else plan_texte,
    }


def _compagnon_parlant(donnees: dict | None) -> bool:
    """Un compagnon qui contient au moins un segment de texte."""
    return bool(donnees) and any(
        isinstance(s, dict) and str(s.get("t") or "").strip() for s in donnees.get("segments") or [])


def _paragraphes(etat: dict) -> list[dict]:
    """Paragraphes affichés pour cet état, avant réunion des élisions."""
    if etat["situe"]:
        return _paragraphes_situes(etat["donnees"], etat["corps"], etat["plan"])
    return _paragraphes_du_texte(etat["corps"], etat["plan"])


def _empreinte(fichier: Path) -> str:
    """Date et taille du texte et du compagnon : de quoi voir qu'ils ont changé."""
    parties = []
    for chemin in (fichier, compagnon.chemin_pour(fichier)):
        try:
            infos = chemin.stat()
            parties.append(f"{infos.st_mtime_ns}:{infos.st_size}")
        except OSError:
            parties.append("-")
    return "/".join(parties)


def empreinte(chemin: str | Path) -> str:
    return _empreinte(Path(chemin or ""))


# ---------------------------------------------------------------------------
# Chargement d'une transcription
# ---------------------------------------------------------------------------

def charger(chemin: str | Path, persister: bool = False) -> dict:
    """
    Tout ce dont la vue de lecture a besoin pour un fichier de sortie.

    Le compagnon JSON n'est jamais obligatoire : sans lui, le texte s'affiche
    quand même, sans surlignage, avec une phrase qui l'explique. Le texte
    affiché est toujours celui du fichier : retouché dans un éditeur, il est
    relu tel quel et le compagnon est recalé dessus (écrit sur le disque avec
    `persister`, annulable comme une correction).
    """
    fichier = Path(chemin or "")
    if not fichier.is_file():
        return {"ok": False, "message": langues.t("lect.absent")}

    try:
        contenu = fichier.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        journal.attention("Lecture impossible de %s : %s", fichier, exc)
        return {"ok": False, "message": langues.t("lect.illisible")}

    tronque = len(contenu) > LIMITE_CARACTERES
    if tronque:
        contenu = contenu[:LIMITE_CARACTERES]

    etat = _etat(fichier, contenu)
    donnees = etat["donnees"] if etat["situe"] else None
    paragraphes = _paragraphes(etat)
    if etat["recale"] and persister and not tronque:
        ecrit = _ecrire(etat, etat["corps"], donnees)
        if ecrit["ok"]:
            regles = _instantane_regles()
            _memoriser_annulation(fichier, ecrit, regles, regles, False)
            journal.info("Compagnon recalé sur %s, retouché hors de l'application", fichier.name)
    if donnees:
        meta = _meta_du_compagnon(donnees, fichier, paragraphes)
        message = langues.t("lect.recale") if etat["recale"] else ""
    else:
        meta = _meta_de_lentete(etat["entete"], fichier)
        if tronque:
            message = langues.t("lect.tronque")
        elif _compagnon_parlant(etat["donnees"]):
            message = langues.t("lect.compagnon_desaccorde")
        else:
            message = langues.t("lect.sans_compagnon")

    seuils = (donnees or {}).get("seuils") or {}
    remplacements = []
    if donnees:
        for rang, r in enumerate(((donnees.get("vocabulaire") or {}).get("remplacements")) or []):
            if isinstance(r, dict) and not r.get("annule"):
                remplacements.append({"rang": rang, "avant": str(r.get("a", "")), "apres": str(r.get("b", "")),
                                      "regle": str(r.get("regle", "")), "debut": float(r.get("d", 0) or 0)})
    statistiques = _statistiques(paragraphes, seuils)
    for paragraphe in paragraphes:
        paragraphe["mots"] = _reunir_elisions(paragraphe["mots"])
    return {
        "ok": True,
        "remplacements": remplacements,
        "chemin": str(fichier),
        "nom": fichier.name,
        "compagnon": bool(donnees),
        "message": message,
        "meta": meta,
        "seuils": {
            "faible": float(seuils.get("faible", compagnon.SEUIL_FAIBLE)),
            "tres_faible": float(seuils.get("tres_faible", compagnon.SEUIL_TRES_FAIBLE)),
        },
        "paragraphes": paragraphes,
        "entete": etat["entete"],
        # Texte du fichier, en-tête retiré : c'est lui que « Copier le texte »
        # met dans le presse-papiers, jamais une reconstruction.
        "corps": etat["corps"].strip(),
        "statistiques": statistiques,
        "empreinte": _empreinte(fichier),
        "heures": any(p.get("debut") is not None for p in paragraphes),
    }


def _duree_lisible(secondes: float) -> str:
    secondes = int(secondes or 0)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return langues.t("duree_longue.heures", h=heures, m=f"{minutes:02d}")
    if not minutes:
        return f"{sec} s"  # « 43 s », pas « 0 min 43 s »
    return langues.t("duree_longue.minutes", m=minutes, s=f"{sec:02d}")


def _meta_du_compagnon(donnees: dict, fichier: Path, paragraphes: list[dict] | None = None) -> dict:
    source = donnees.get("source") or {}
    infos = donnees.get("transcription") or {}
    chemin_source = str(source.get("chemin", ""))
    date = str(infos.get("date", ""))
    try:
        date_lisible = datetime.fromisoformat(date).strftime(langues.t("format.date_heure"))
    except ValueError:
        date_lisible = date
    nb = int(infos.get("nb_locuteurs", 0) or 0)
    if nb and paragraphes is not None:
        # Après un renommage qui réunit deux voix, le nombre affiché suit le
        # fichier, pas le décompte du calcul.
        nb = len({p["locuteur"] for p in paragraphes if p.get("locuteur")}) or nb
    return {
        "fichier": str(source.get("nom", "")) or fichier.stem,
        "source_chemin": chemin_source,
        "source_presente": bool(chemin_source) and Path(chemin_source).is_file(),
        "duree": _duree_lisible(source.get("duree", 0)),
        "duree_secs": float(source.get("duree", 0) or 0),
        "date": date_lisible,
        "modele": str(infos.get("modele", "")),
        "langue": str(infos.get("langue", "")),
        "locuteurs": nb,
        "locuteurs_texte": (
            langues.tn("lect.locuteurs", nb) if nb
            else langues.t("lect.non_separes")
        ),
    }


def _meta_de_lentete(entete: str, fichier: Path) -> dict:
    """Ce que l'on sait d'une transcription sans compagnon : son en-tête."""
    source = _valeur_entete_traduite(entete, "ent.source")
    return {
        "fichier": Path(source).name if source else fichier.stem,
        "source_chemin": source,
        "source_presente": bool(source) and Path(source).is_file(),
        "duree": _valeur_entete_traduite(entete, "ent.duree"),
        "duree_secs": 0.0,
        "date": _valeur_entete_traduite(entete, "ent.transcrit_le"),
        "modele": _valeur_entete_traduite(entete, "ent.modele"),
        "langue": _valeur_entete_traduite(entete, "ent.langue"),
        "locuteurs": 0,
        "locuteurs_texte": (
            _valeur_entete_traduite(entete, "ent.locuteurs")
            or langues.t("lect.non_separes")
        ),
    }


def _statistiques(paragraphes: list[dict], seuils: dict) -> dict:
    """
    Mots dont la confiance est connue, et ceux qui sont signalés. `sans_confiance`
    compte les mots du moteur sans probabilité (OpenVINO n'en donne pas) : la
    vue doit alors dire qu'elle ne peut rien surligner, pas laisser croire que
    tout est sûr.
    """
    faible = float(seuils.get("faible", compagnon.SEUIL_FAIBLE))
    total = 0
    signales = 0
    sans_confiance = 0
    for paragraphe in paragraphes:
        for mot in paragraphe["mots"]:
            if mot["p"] < 0:
                if mot["t"]:
                    sans_confiance += 1
                continue
            total += 1
            if mot["p"] < faible:
                signales += 1
    return {"mots": total, "signales": signales, "sans_confiance": sans_confiance}


def texte_complet(paragraphes: list[dict]) -> str:
    """Le texte lisible, tel qu'il est affiché, locuteurs compris."""
    blocs = []
    for paragraphe in paragraphes:
        prefixe = f"{paragraphe['locuteur']} : " if paragraphe.get("locuteur") else ""
        blocs.append(prefixe + paragraphe["texte"])
    return "\n\n".join(blocs)


# ---------------------------------------------------------------------------
# Copier pour l'IA
# ---------------------------------------------------------------------------

def texte_pour_ia(chemin: str | Path) -> dict:
    """Assemble gabarit, métadonnées et texte, prêts pour le presse-papiers."""
    charge = charger(chemin)
    if not charge.get("ok"):
        return charge
    meta = charge["meta"]
    valeurs = {
        "texte": texte_complet(charge["paragraphes"]),
        "fichier": meta.get("fichier", ""),
        "date": meta.get("date", ""),
        "duree": meta.get("duree", ""),
        "locuteurs": meta.get("locuteurs_texte", ""),
        "modele": meta.get("modele", ""),
    }
    return {"ok": True, "texte": gabarit.appliquer(valeurs)}


# ---------------------------------------------------------------------------
# Écrire une modification : plages du corps, segments, contrôle
# ---------------------------------------------------------------------------

class Refus(Exception):
    """Modification refusée avant toute écriture ; `code` dit pourquoi."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _raccorder(gauche: str, remplacement: str, droite: str) -> str:
    """
    Texte d'un paragraphe après remplacement d'une plage. Le remplacement tient
    sur une ligne ; une suppression ne laisse ni double espace ni espace en
    bord de paragraphe.
    """
    # Le remplacement arrive déjà sur une ligne (`calculer_plages`), et peut
    # commencer ou finir par l'espace qui sépare deux mots : il est pris tel quel.
    remplacement = str(remplacement or "")
    if not remplacement and gauche.endswith(" ") and droite.startswith(" "):
        droite = droite[1:]
    return (gauche + remplacement + droite).strip(" ")


def _commun(a: str, b: str) -> tuple[int, int]:
    """Longueurs du début et de la fin communs à deux textes, sans se recouvrir."""
    limite = min(len(a), len(b))
    debut = 0
    while debut < limite and a[debut] == b[debut]:
        debut += 1
    fin = 0
    while fin < limite - debut and a[-1 - fin] == b[-1 - fin]:
        fin += 1
    return debut, fin


def _redistribuer(segments: list, situe: dict, ancien: str, nouveau: str) -> None:
    """
    Répartit le nouveau texte d'un paragraphe entre ses segments.

    Seules les séparations (l'espace entre deux segments) situées hors de la
    partie changée sont gardées ; les segments dont la séparation tombe dans
    la partie changée sont réunis au premier d'entre eux, qui prend leurs mots
    et leur fin. C'est ce qui rend juste une correction à cheval sur deux
    segments : le texte change là où il doit, et les segments joints par une
    espace redonnent exactement le paragraphe.
    """
    rangs = [rang for rang, _, _ in situe["segments"]]
    if not nouveau:
        for rang in rangs:
            segments[rang]["t"] = ""
        return
    base = situe["debut"]
    separations = [fin - base for _, _, fin in situe["segments"][:-1]]
    tete, queue = _commun(ancien, nouveau)
    ecart = len(nouveau) - len(ancien)
    gardees: list[tuple[int, int]] = []
    for indice, position in enumerate(separations):
        if position < tete:
            gardees.append((indice, position))
        elif position >= len(ancien) - queue:
            gardees.append((indice, position + ecart))
    bornes = [-1] + [p for _, p in gardees] + [len(nouveau)]
    morceaux = [nouveau[bornes[n] + 1:bornes[n + 1]] for n in range(len(bornes) - 1)]
    if any(not m or m != m.strip() for m in morceaux):
        # Garde-fou : tout le paragraphe dans son premier segment, toujours juste.
        gardees, morceaux = [], [nouveau]
    debut_groupe = 0
    for (indice, _), morceau in zip(gardees + [(len(rangs) - 1, 0)], morceaux):
        groupe = rangs[debut_groupe:indice + 1]
        premier = segments[groupe[0]]
        premier["t"] = morceau
        if len(groupe) > 1:
            mots = []
            for rang in groupe:
                mots.extend(m for m in segments[rang].get("m") or [] if isinstance(m, dict))
            if mots:
                premier["m"] = mots
            premier["f"] = segments[groupe[-1]].get("f", premier.get("f", 0))
            for rang in groupe[1:]:
                segments[rang]["t"] = ""
                segments[rang].pop("m", None)
        debut_groupe = indice + 1


def _reconstruire(corps: str, plan: list[dict], textes: dict[int, str],
                  prefixes: dict[int, str] | None = None) -> str:
    """
    Corps du fichier, paragraphe par paragraphe, avec les textes et préfixes
    changés. Tout le reste (séparations, heures, fin de fichier) est repris à
    la lettre. Un paragraphe vidé disparaît avec ce qui le séparait du
    précédent.
    """
    prefixes = prefixes or {}
    gardes = [k for k in range(len(plan)) if textes.get(k, None) != ""]
    if not gardes:
        raise Refus("vide")
    morceaux = [corps[:plan[0]["tete"]]]
    for n, k in enumerate(gardes):
        p = plan[k]
        if n:
            # La séparation qui précédait ce paragraphe : un paragraphe vidé
            # juste avant disparaît ainsi avec la sienne.
            morceaux.append(corps[plan[k - 1]["fin"]:p["tete"]])
        morceaux.append(prefixes.get(k, corps[p["tete"]:p["debut"]]))
        morceaux.append(textes.get(k, corps[p["debut"]:p["fin"]]))
    morceaux.append(corps[plan[-1]["fin"]:])
    return "".join(morceaux)


def _mots_situes(segments: list, situe: dict, corps: str) -> list[tuple[dict, int, int]]:
    """Chaque mot du compagnon de ce paragraphe, avec sa place dans le texte du paragraphe."""
    places = []
    for rang, debut, fin in situe["segments"]:
        texte, position = corps[debut:fin], 0
        for mot in segments[rang].get("m") or []:
            if not isinstance(mot, dict) or not mot.get("t"):
                continue
            trouve = _chercher_mot(texte, str(mot["t"]), position)
            if trouve < 0:
                continue
            decalage = debut - situe["debut"]
            places.append((mot, decalage + trouve, decalage + trouve + len(str(mot["t"]))))
            position = trouve + len(str(mot["t"]))
    return places


def _etendre_au_mot(texte: str, debut: int, fin: int) -> tuple[int, int]:
    """Une plage élargie aux mots qu'elle entame : « gitl » dans « gitlab » devient « gitlab »."""
    dans_mot = lambda c: c.isalnum() or c in "'’-_"  # noqa: E731
    while debut > 0 and dans_mot(texte[debut - 1]):
        debut -= 1
    while fin < len(texte) and dans_mot(texte[fin]):
        fin += 1
    return debut, fin


def _corriger_mots(mots: list, avant: str, apres: str, debut: int, fin: int) -> None:
    """
    Les mots du compagnon touchés par un remplacement prennent le texte
    nouveau : le premier le porte, avec son heure (l'écoute s'y place
    toujours), les suivants sont retirés. Une suppression les retire tous.
    """
    a, b = _etendre_au_mot(avant, debut, fin)
    nouveau = apres[a:len(apres) - (len(avant) - b)].strip()
    touches = [entree for entree in mots if entree[1] < b and entree[2] > a]
    for n, (mot, _, _) in enumerate(touches):
        # Réécrit à la main : ce n'est plus le vocabulaire qui l'a écrit.
        mot.pop("c", None)
        if n == 0 and nouveau:
            mot["t"] = nouveau
        else:
            mot["t"] = ""


def _nettoyer_mots(segments: list, situe: dict) -> None:
    for rang, _, _ in situe["segments"]:
        mots = segments[rang].get("m")
        if isinstance(mots, list):
            segments[rang]["m"] = [m for m in mots if not isinstance(m, dict) or m.get("t")]


def calculer_plages(etat: dict, plages: list[tuple[int, int, str]]) -> tuple[str, dict | None]:
    """
    Nouveau corps et nouveau compagnon après remplacement de plages du corps
    (début, fin, texte). Chaque plage tient dans le texte d'un seul paragraphe
    (jamais dans une heure ou un nom de locuteur) ; deux plages ne se
    chevauchent pas. Rien n'est écrit ici.
    """
    corps, plan = etat["corps"], etat["plan"]
    par_paragraphe: dict[int, list[tuple[int, int, str]]] = {}
    for debut, fin, texte in plages:
        debut, fin = int(debut), int(fin)
        k = next((i for i, p in enumerate(plan) if p["debut"] <= debut <= fin <= p["fin"]), None)
        if k is None:
            raise Refus("hors_paragraphe")
        # La plage est réduite à ce qui change vraiment : un paragraphe
        # réécrit dont seul un mot bouge ne touche que ce mot, et les autres
        # gardent leur heure et leur confiance.
        remplacement = " ".join(str(texte or "").split())
        tete, queue = _commun(corps[debut:fin], remplacement)
        debut, fin = debut + tete, fin - queue
        remplacement = remplacement[tete:len(remplacement) - queue]
        par_paragraphe.setdefault(k, []).append((debut - plan[k]["debut"], fin - plan[k]["debut"], remplacement))
    textes: dict[int, str] = {}
    donnees = copy.deepcopy(etat["donnees"]) if etat["situe"] else None
    for k, liste in par_paragraphe.items():
        liste.sort()
        if any(liste[n][0] < liste[n - 1][1] for n in range(1, len(liste))):
            raise Refus("chevauchement")
        texte = corps[plan[k]["debut"]:plan[k]["fin"]]
        mots = _mots_situes(donnees["segments"], plan[k], corps) if donnees else []
        # De la fin vers le début : les positions des plages et des mots qui
        # précèdent restent celles du texte d'origine.
        for debut, fin, remplacement in reversed(liste):
            avant = texte
            texte = _raccorder(texte[:debut], remplacement, texte[fin:])
            if mots:
                _corriger_mots(mots, avant, texte, debut, fin)
        textes[k] = texte
        if mots:
            _nettoyer_mots(donnees["segments"], plan[k])
    nouveau_corps = _reconstruire(corps, plan, textes)
    if donnees is not None:
        segments = donnees["segments"]
        for k, texte in textes.items():
            _redistribuer(segments, plan[k], corps[plan[k]["debut"]:plan[k]["fin"]], texte)
        verifie = situer(nouveau_corps, segments)
        attendus = [t for k, t in sorted({**{k: corps[p["debut"]:p["fin"]] for k, p in enumerate(plan)},
                                           **textes}.items()) if t]
        if verifie is None or [nouveau_corps[p["debut"]:p["fin"]] for p in verifie] != attendus:
            journal.attention("Modification refusée : le compagnon ne suivrait pas le texte.")
            raise Refus("ecart")
    return nouveau_corps, donnees


# -- écriture, contrôle et retour en arrière ---------------------------------

#: Fichiers d'une transcription qu'une modification réécrit.
_SUFFIXES = (".txt", ".json", ".srt", ".vtt")

_SousTitre = namedtuple("_SousTitre", "debut fin texte locuteur")


def _lire_ou_rien(chemin: Path) -> str | None:
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError:
        return None


def _photo(fichier: Path) -> dict[str, str | None]:
    """Contenu de chaque fichier de la transcription, ou None s'il n'existe pas."""
    return {suffixe: _lire_ou_rien(fichier.with_suffix(suffixe)) for suffixe in _SUFFIXES}


def _ecrire_atomique(chemin: Path, texte: str) -> None:
    """Écrit à côté puis remplace : une coupure ne laisse jamais un fichier à moitié écrit."""
    provisoire = chemin.with_name(chemin.name + ".scribouille-tmp")
    provisoire.write_text(texte, encoding="utf-8")
    os.replace(provisoire, chemin)


def _remettre(fichier: Path, photo: dict[str, str | None]) -> None:
    """Remet les fichiers d'une photo, compagnon d'abord. Ceux qui n'existaient pas sont laissés."""
    for suffixe in (".json", ".txt", ".srt", ".vtt"):
        contenu = photo.get(suffixe)
        if contenu is not None:
            _ecrire_atomique(fichier.with_suffix(suffixe), contenu)


def _segments_sous_titres(donnees: dict) -> tuple[list, bool]:
    liste = [
        _SousTitre(float(s.get("d", 0) or 0), float(s.get("f", 0) or 0), str(s.get("t") or "").strip(),
                   str(s.get("l") or ""))
        for s in donnees.get("segments") or []
        if isinstance(s, dict) and str(s.get("t") or "").strip()
    ]
    return liste, any(s.locuteur for s in liste)


def _sous_titres_attendus(fichier: Path, donnees: dict, suffixe: str) -> str:
    """Contenu des sous-titres que décrit le compagnon, écrit comme `app/sorties.py` l'écrit."""
    provisoire = fichier.with_name(fichier.stem + ".scribouille-st" + suffixe)
    liste, avec_locuteurs = _segments_sous_titres(donnees)
    ecrire = sorties.ecrire_srt if suffixe == ".srt" else sorties.ecrire_vtt
    try:
        ecrire(provisoire, liste, avec_locuteurs)
        return provisoire.read_text(encoding="utf-8")
    finally:
        try:
            provisoire.unlink()
        except OSError:
            pass


def controler(fichier: str | Path, mots: bool = True) -> str:
    """
    Vérifie la règle d'or sur les fichiers tels qu'ils sont sur le disque :
    texte affiché, `.txt`, compagnon (segments ET mots) et sous-titres disent
    la même chose. Renvoie une description de l'écart, ou une chaîne vide.
    `mots=False` : seulement pour remettre un état d'origine écrit par une
    version qui ne tenait pas encore les mots.
    """
    fichier = Path(fichier)
    try:
        etat = _etat(fichier, recaler=False)
    except (OSError, UnicodeDecodeError) as exc:
        return f"illisible : {exc}"
    if _compagnon_parlant(etat["donnees"]) and not etat["situe"]:
        return "le compagnon ne décrit plus le fichier"
    corps, plan = etat["corps"], etat["plan"]
    if plan and _reconstruire(corps, plan, {}) != corps:
        return "paragraphes"
    if mots and etat["situe"]:
        ecart = compagnon.ecart_mots(etat["donnees"])
        if ecart:
            return ecart
    for k, paragraphe in enumerate(_paragraphes(etat)):
        rendu = "".join(m.get("e", "") + m["t"] for m in _reunir_elisions(paragraphe["mots"]))
        if rendu != paragraphe["texte"] or paragraphe["texte"] != corps[plan[k]["debut"]:plan[k]["fin"]]:
            return f"paragraphe {k + 1}"
    if etat["situe"]:
        for suffixe in (".srt", ".vtt"):
            actuel = _lire_ou_rien(fichier.with_suffix(suffixe))
            if actuel is not None and actuel != _sous_titres_attendus(fichier, etat["donnees"], suffixe):
                return f"sous-titres {suffixe}"
    return ""


def _ecrire(etat: dict, nouveau_corps: str, donnees: dict | None) -> dict:
    """
    Écrit une modification : compagnon, texte, puis sous-titres existants
    régénérés depuis le compagnon. Contrôle ensuite la règle d'or sur les
    fichiers relus ; en cas d'écart, tout est remis comme avant et la
    modification est refusée. Renvoie les photos d'avant et d'après.
    """
    fichier = etat["fichier"]
    avant = _photo(fichier)
    if avant[".txt"] != etat["contenu"]:
        return {"ok": False, "code": "modifie_dehors"}
    if donnees is not None:
        # Les mots redisent le texte de chaque segment, avant toute écriture.
        compagnon.aligner_segments(donnees)
    try:
        if donnees is not None:
            _ecrire_atomique(compagnon.chemin_pour(fichier), json.dumps(donnees, ensure_ascii=False))
        _ecrire_atomique(fichier, etat["entete"] + etat["separation"] + nouveau_corps)
        if donnees is not None:
            for suffixe in (".srt", ".vtt"):
                if avant[suffixe] is not None:
                    _ecrire_atomique(fichier.with_suffix(suffixe), _sous_titres_attendus(fichier, donnees, suffixe))
    except OSError as exc:
        journal.attention("Modification non écrite dans %s : %s", fichier, exc)
        try:
            _remettre(fichier, avant)
        except OSError:
            pass
        return {"ok": False, "code": "non_reecrit"}
    ecart = controler(fichier)
    if ecart:
        journal.attention("Modification annulée dans %s, écart après écriture : %s", fichier.name, ecart)
        try:
            _remettre(fichier, avant)
        except OSError as exc:
            journal.attention("Retour en arrière impossible dans %s : %s", fichier, exc)
        return {"ok": False, "code": "ecart"}
    return {"ok": True, "avant": avant, "apres": _photo(fichier)}


# -- historique des modifications, sur le disque ---------------------------

#: Une pile par transcription, dans le dossier de données : chaque
#: modification y garde les fichiers d'avant (texte, compagnon, sous-titres)
#: et les règles d'avant, compressés. Elle survit à la fermeture de
#: l'application ; l'état d'origine, photographié à la première modification,
#: est gardé à part et n'est jamais retiré.
DOSSIER_HISTORIQUE = chemins.RACINE / "historique-relecture"
PROFONDEUR_HISTORIQUE = 50


def _dossier_historique(fichier: Path) -> Path:
    import hashlib

    cle = hashlib.sha1(str(fichier.resolve()).lower().encode("utf-8")).hexdigest()[:16]
    return DOSSIER_HISTORIQUE / cle


def _ecrire_gz(chemin: Path, objet) -> None:
    import gzip

    provisoire = chemin.with_name(chemin.name + ".tmp")
    with gzip.open(provisoire, "wt", encoding="utf-8") as flux:
        json.dump(objet, flux, ensure_ascii=False)
    os.replace(provisoire, chemin)


def _lire_gz(chemin: Path):
    import gzip

    try:
        with gzip.open(chemin, "rt", encoding="utf-8") as flux:
            return json.load(flux)
    except (OSError, ValueError, EOFError):
        return None


def _index_historique(dossier: Path) -> dict:
    index = _lire_gz(dossier / "index.json.gz")
    return index if isinstance(index, dict) and isinstance(index.get("pile"), list) else {}


def _signature(photo: dict) -> dict:
    import hashlib

    return {s: (hashlib.sha256(c.encode("utf-8")).hexdigest() if c is not None else None)
            for s, c in photo.items()}


def _elaguer_historique() -> None:
    """Retire les historiques des transcriptions qui n'existent plus."""
    import shutil

    try:
        dossiers = list(DOSSIER_HISTORIQUE.iterdir())
    except OSError:
        return
    for dossier in dossiers:
        chemin = _index_historique(dossier).get("chemin")
        if chemin and not Path(chemin).exists():
            shutil.rmtree(dossier, ignore_errors=True)


def _memoriser_annulation(fichier: Path, ecrit: dict, regles_avant: dict, regles_apres: dict,
                          regle_ajoutee: bool) -> None:
    """Empile une modification ; la plus ancienne sort au-delà de la profondeur."""
    dossier = _dossier_historique(fichier)
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        index = _index_historique(dossier) or {"chemin": str(fichier.resolve()), "pile": [], "suivant": 1}
        if not (dossier / "original.json.gz").exists():
            _ecrire_gz(dossier / "original.json.gz", ecrit["avant"])
        numero = int(index.get("suivant", 1))
        _ecrire_gz(dossier / f"{numero}.json.gz", {
            "avant": ecrit["avant"], "apres": _signature(ecrit["apres"]),
            "regles_avant": regles_avant, "regles_apres": regles_apres, "regle_ajoutee": regle_ajoutee,
            "date": datetime.now().isoformat(timespec="seconds"),
        })
        index["pile"].append(numero)
        index["suivant"] = numero + 1
        while len(index["pile"]) > PROFONDEUR_HISTORIQUE:
            ancien = index["pile"].pop(0)
            (dossier / f"{ancien}.json.gz").unlink(missing_ok=True)
        _ecrire_gz(dossier / "index.json.gz", index)
    except OSError as exc:
        journal.attention("Historique de relecture non écrit pour %s : %s", fichier.name, exc)
        return
    _elaguer_historique()


def modifier(chemin: str | Path, calcul, empreinte_attendue: str = "", memoriser: bool = True) -> dict:
    """
    Applique une modification calculée par `calcul(etat) -> (corps, donnees)`
    et la rend annulable (sauf `memoriser=False` : l'appelant l'empile
    lui-même, avec les règles qu'il touche). `empreinte_attendue`, quand elle
    est donnée, est celle que la vue a lue : si le fichier a changé depuis,
    rien n'est écrit.
    """
    fichier = Path(chemin or "")
    if not fichier.is_file():
        return {"ok": False, "code": "absent", "message": langues.t("lect.absent")}
    if empreinte_attendue and empreinte_attendue != _empreinte(fichier):
        return {"ok": False, "code": "modifie_dehors", "message": langues.t("lect.modifie_pendant")}
    try:
        etat = _etat(fichier)
    except (OSError, UnicodeDecodeError):
        return {"ok": False, "code": "illisible", "message": langues.t("lect.illisible")}
    try:
        nouveau_corps, donnees = calcul(etat)
    except Refus as refus:
        return {"ok": False, "code": refus.code, "message": langues.t("lect.refus." + refus.code)}
    ecrit = _ecrire(etat, nouveau_corps, donnees)
    if not ecrit["ok"]:
        ecrit["message"] = langues.t("lect.refus." + ecrit["code"])
        return ecrit
    if memoriser:
        regles = _instantane_regles()
        _memoriser_annulation(fichier, ecrit, regles, regles, False)
    return {"ok": True, "annulable": True, "ecrit": ecrit}


# ---------------------------------------------------------------------------
# Corrections apprises depuis la vue de lecture
# ---------------------------------------------------------------------------

#: Contexte affiché autour de chaque endroit touché, et nombre d'endroits montrés.
_CONTEXTE_APERCU = 40
_EXTRAITS_APERCU = 6


def _preparer_correction(chemin: str | Path, source: str, cible: str) -> dict:
    """Contrôles communs à l'aperçu et à l'application d'une correction."""
    fichier = Path(chemin or "")
    source = " ".join((source or "").split())
    cible = " ".join((cible or "").split())

    probleme = vocabulaire.verifier_regle(source, cible)
    if probleme:
        return {"ok": False, "message": probleme}
    if not fichier.is_file():
        return {"ok": False, "message": langues.t("lect.absent")}

    regles, _ = vocabulaire.analyser_corrections(f"{source} => {cible}")
    if not regles:
        return {"ok": False, "message": langues.t("lect.non_interpretee")}

    try:
        contenu = fichier.read_text(encoding="utf-8")
    except OSError:
        return {"ok": False, "message": langues.t("lect.illisible")}
    return {"ok": True, "fichier": fichier, "source": source, "cible": cible,
            "regles": regles, "contenu": contenu}


def trouver(etat: dict, regle) -> list[tuple[int, int, int]]:
    """
    Endroits qu'une règle changerait : (début, fin, paragraphe), en positions
    du corps. La recherche se fait paragraphe par paragraphe, dans le texte
    seul : jamais dans une heure ou un nom de locuteur, jamais à cheval sur
    deux paragraphes.
    """
    corps = etat["corps"]
    trouves = []
    for k, p in enumerate(etat["plan"]):
        texte = corps[p["debut"]:p["fin"]]
        for occurrence in vocabulaire.occurrences(regle, texte):
            trouves.append((p["debut"] + occurrence.start(), p["debut"] + occurrence.end(), k))
    return trouves


def extrait(etat: dict, debut: int, fin: int, k: int, contexte: int) -> dict:
    """Un endroit et ce qui l'entoure dans son paragraphe, coupé sur des mots."""
    corps, p = etat["corps"], etat["plan"][k]
    a, b = max(p["debut"], debut - contexte), min(p["fin"], fin + contexte)
    avant, apres = corps[a:debut], corps[fin:b]
    coupe_avant, coupe_apres = a > p["debut"], b < p["fin"]
    # Pas de demi-mot en bord d'extrait.
    if coupe_avant and not corps[a - 1].isspace() and " " in avant:
        avant = avant[avant.index(" ") + 1:]
    if coupe_apres and not corps[b].isspace() and " " in apres:
        apres = apres[:apres.rindex(" ")]
    return {
        "avant": " ".join(avant.split()) + (" " if avant[-1:].isspace() else ""),
        "forme": corps[debut:fin],
        "apres": (" " if apres[:1].isspace() else "") + " ".join(apres.split()),
        "debut_coupe": coupe_avant,
        "fin_coupee": coupe_apres,
    }


def apercu_correction(chemin: str | Path, source: str, cible: str) -> dict:
    """
    Ce qu'une correction changerait, avant de l'appliquer : le nombre
    d'endroits du fichier touchés, et chacun avec un peu de contexte.
    """
    prepa = _preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    etat = _etat(prepa["fichier"], prepa["contenu"])
    trouves = trouver(etat, prepa["regles"][0])
    if not trouves:
        return {"ok": False, "nombre": 0, "message": _rien_a_changer(prepa, etat["corps"])}
    extraits = [extrait(etat, a, b, k, _CONTEXTE_APERCU) for a, b, k in trouves[:_EXTRAITS_APERCU]]
    return {
        "ok": True,
        "nombre": len(trouves),
        "extraits": extraits,
        "message": langues.tn("lect.apercu", len(trouves)),
    }


def _rien_a_changer(prepa: dict, corps: str) -> str:
    """Forme absente, ou déjà écrite comme on la veut partout : ce n'est pas pareil."""
    if prepa["regles"][0].motif.search(corps):
        return langues.t("lect.deja_corrige", cible=prepa["cible"])
    return langues.t("lect.non_retrouve", source=prepa["source"])


def corriger_plages(chemin: str | Path, plages: list[tuple[int, int, str]], source: str, cible: str,
                    ajouter_regle: bool = False, empreinte_attendue: str = "") -> dict:
    """
    Écrit une correction aux endroits donnés (positions du corps), puis
    mémorise la règle si on le demande. Annulable d'un geste, règle comprise.
    """
    fichier = Path(chemin or "")
    regles_avant = _instantane_regles()
    retour = modifier(fichier, lambda etat: calculer_plages(etat, plages), empreinte_attendue, memoriser=False)
    if not retour["ok"]:
        return retour
    regle_ajoutee = False
    message_regle = ""
    # Le vocabulaire n'apprend que sur demande (« Mémoriser ») : une correction
    # ordinaire ne dépose aucune proposition à relire.
    if ajouter_regle:
        memoire = _memoriser_regle(source, cible)
        regle_ajoutee = bool(memoire.get("ajoutee"))
        message_regle = memoire.get("message", "")
    ecrit = retour.pop("ecrit")
    _memoriser_annulation(fichier, ecrit, regles_avant, _instantane_regles(), regle_ajoutee)
    retour.update({"remplacements": len(plages), "regle_ajoutee": regle_ajoutee,
                   "message_regle": message_regle})
    return retour


def appliquer_correction(chemin: str | Path, source: str, cible: str,
                         ajouter_regle: bool = False) -> dict:
    """
    Corrige une forme partout dans une transcription déjà écrite : texte (corps
    seulement, l'en-tête décrit la production et ne doit pas bouger),
    compagnon et sous-titres, puis `corrections.txt` quand l'utilisateur
    demande que la règle vaille pour les transcriptions suivantes. L'état
    d'avant est gardé : `annuler_correction` le remet.
    """
    prepa = _preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    fichier, source, cible = prepa["fichier"], prepa["source"], prepa["cible"]
    etat = _etat(fichier, prepa["contenu"])
    trouves = trouver(etat, prepa["regles"][0])
    if not trouves:
        return {"ok": False, "message": _rien_a_changer(prepa, etat["corps"])}
    retour = corriger_plages(fichier, [(a, b, cible) for a, b, _ in trouves], source, cible, ajouter_regle)
    if not retour["ok"]:
        return retour
    journal.info(
        "Correction appliquée dans %s : « %s » vers « %s », %s remplacements%s",
        fichier.name, source, cible, retour["remplacements"],
        ", règle mémorisée" if retour["regle_ajoutee"] else "",
    )
    message_regle = retour.pop("message_regle", "")
    retour["message"] = (langues.tn("lect.remplacements", retour["remplacements"])
                         + (" " + message_regle if message_regle else ""))
    return retour


# -- position de relecture ----------------------------------------------------

#: Dernière position de chaque transcription relue (instant d'écoute,
#: défilement), pour reprendre là où l'on s'était arrêté.
FICHIER_POSITIONS = chemins.RACINE / "relecture-positions.json"
_POSITIONS_MAX = 300


def _lire_positions() -> dict:
    try:
        positions = json.loads(FICHIER_POSITIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return positions if isinstance(positions, dict) else {}


def memoriser_position(chemin: str | Path, temps: float, haut: int) -> bool:
    fichier = Path(chemin or "")
    if not fichier.name:
        return False
    positions = _lire_positions()
    positions[str(fichier.resolve()).lower()] = {
        "t": round(max(0.0, float(temps or 0)), 1), "haut": max(0, int(haut or 0)),
        "date": datetime.now().isoformat(timespec="seconds"),
    }
    if len(positions) > _POSITIONS_MAX:
        recentes = sorted(positions.items(), key=lambda e: str(e[1].get("date", "")), reverse=True)
        positions = dict(recentes[:_POSITIONS_MAX])
    try:
        FICHIER_POSITIONS.parent.mkdir(parents=True, exist_ok=True)
        _ecrire_atomique(FICHIER_POSITIONS, json.dumps(positions, ensure_ascii=False))
        return True
    except OSError:
        return False


def position(chemin: str | Path) -> dict | None:
    fichier = Path(chemin or "")
    if not fichier.name:
        return None
    trouvee = _lire_positions().get(str(fichier.resolve()).lower())
    return trouvee if isinstance(trouvee, dict) else None


def editer_passage(chemin: str | Path, k: int, debut: int, fin: int, attendu: str, texte: str,
                   empreinte_attendue: str = "") -> dict:
    """
    Réécrit librement un passage d'un paragraphe, ou le supprime (`texte`
    vide) : positions dans le texte du paragraphe, et le texte qu'on y lisait
    à l'écran, pour ne jamais écrire ailleurs. Un paragraphe vidé disparaît.
    Même règle d'or qu'une correction, même annulation.
    """
    def calcul(etat: dict):
        plan = etat["plan"]
        try:
            rang, a, b = int(k), int(debut), int(fin)
        except (TypeError, ValueError):
            raise Refus("introuvable")
        if not (0 <= rang < len(plan)):
            raise Refus("introuvable")
        p = plan[rang]
        a, b = p["debut"] + a, p["debut"] + b
        if not (p["debut"] <= a <= b <= p["fin"]) or etat["corps"][a:b] != str(attendu or ""):
            raise Refus("introuvable")
        return calculer_plages(etat, [(a, b, str(texte or ""))])

    retour = modifier(chemin, calcul, empreinte_attendue)
    if retour.get("ok"):
        retour.pop("ecrit", None)
        journal.info("Passage %s dans %s", "supprimé" if not " ".join(str(texte or "").split()) else "réécrit",
                     Path(chemin).name)
    return retour


def correction_annulable(chemin: str | Path) -> bool:
    return niveaux_annulables(chemin) > 0


def niveaux_annulables(chemin: str | Path) -> int:
    fichier = Path(chemin or "")
    return len(_index_historique(_dossier_historique(fichier)).get("pile") or []) if fichier.name else 0


def annuler_correction(chemin: str | Path) -> dict:
    """
    Défait la dernière modification de ce fichier : texte, compagnon,
    sous-titres et, si elle avait été ajoutée, la règle. Chaque appel remonte
    d'un cran. Rien n'est touché si le fichier a été modifié entre-temps, par
    un éditeur par exemple : on écraserait ce travail.
    """
    fichier = Path(chemin or "")
    dossier = _dossier_historique(fichier)
    index = _index_historique(dossier)
    if not index.get("pile"):
        return {"ok": False, "message": langues.t("lect.annulation.aucune")}
    numero = index["pile"][-1]
    derniere = _lire_gz(dossier / f"{numero}.json.gz")
    if not isinstance(derniere, dict) or _signature(_photo(fichier)) != derniere.get("apres"):
        # Modifié ailleurs depuis : aucun cran de la pile ne s'applique plus.
        # L'original, lui, reste disponible.
        for ancien in index["pile"]:
            (dossier / f"{ancien}.json.gz").unlink(missing_ok=True)
        index["pile"] = []
        _ecrire_gz(dossier / "index.json.gz", index)
        return {"ok": False, "message": langues.t("lect.annulation.modifie")}
    try:
        _remettre(fichier, derniere["avant"])
    except OSError as exc:
        journal.attention("Correction non annulée dans %s : %s", fichier, exc)
        return {"ok": False, "message": langues.t("lect.non_reecrit")}
    index["pile"].pop()
    _ecrire_gz(dossier / "index.json.gz", index)
    (dossier / f"{numero}.json.gz").unlink(missing_ok=True)

    message = langues.t("lect.annulation.faite")
    remis = _remettre_regles(derniere["regles_avant"], derniere["regles_apres"])
    regle_retiree = bool(remis and derniere["regle_ajoutee"])
    if regle_retiree:
        message += " " + langues.t("lect.annulation.regle")
    elif remis:
        message += " " + langues.t("lect.annulation.proposition")
    journal.info("Correction annulée dans %s%s", fichier.name, ", règle retirée" if regle_retiree else "")
    return {"ok": True, "message": message, "regle_retiree": regle_retiree}


def original_disponible(chemin: str | Path) -> bool:
    """L'état d'avant la première modification est gardé, et diffère de l'état actuel."""
    fichier = Path(chemin or "")
    original = _lire_gz(_dossier_historique(fichier) / "original.json.gz") if fichier.name else None
    return isinstance(original, dict) and original.get(".txt") is not None and original != _photo(fichier)


def revenir_original(chemin: str | Path) -> dict:
    """
    Remet la transcription telle qu'elle était avant toute modification :
    texte, compagnon et sous-titres d'origine. C'est une modification comme
    une autre : contrôlée, et annulable.
    """
    fichier = Path(chemin or "")
    original = _lire_gz(_dossier_historique(fichier) / "original.json.gz") if fichier.name else None
    if not isinstance(original, dict) or original.get(".txt") is None:
        return {"ok": False, "code": "sans_original", "message": langues.t("lect.original.absent")}
    avant = _photo(fichier)
    if original == avant:
        return {"ok": False, "code": "deja_original", "message": langues.t("lect.original.deja")}
    try:
        _remettre(fichier, original)
    except OSError as exc:
        journal.attention("Original non remis dans %s : %s", fichier, exc)
        return {"ok": False, "code": "non_reecrit", "message": langues.t("lect.non_reecrit")}
    # L'original est remis à l'octet : ses mots sont ceux qu'il avait, même
    # écrits par une version antérieure qui ne les tenait pas encore.
    try:
        tenus = not compagnon.ecart_mots(json.loads(original.get(".json") or "null"))
    except ValueError:
        tenus = False
    ecart = controler(fichier, mots=tenus)
    if ecart:
        _remettre(fichier, avant)
        return {"ok": False, "code": "ecart", "message": langues.t("lect.refus.ecart")}
    regles = _instantane_regles()
    _memoriser_annulation(fichier, {"avant": avant, "apres": _photo(fichier)}, regles, regles, False)
    journal.info("Transcription remise dans son état d'origine : %s", fichier.name)
    return {"ok": True, "annulable": True, "message": langues.t("lect.original.remis")}


def _fichiers_de_regles() -> list[Path]:
    from . import vocabulaire_v2

    return [chemins.FICHIER_CORRECTIONS, vocabulaire_v2.FICHIER_PERSONNEL]


def _instantane_regles() -> dict[str, str | None]:
    """Contenu des fichiers qu'une correction peut toucher (règles, vocabulaire)."""
    return {str(chemin): _lire_ou_rien(chemin) for chemin in _fichiers_de_regles()}


def _remettre_regles(avant: dict, apres: dict) -> bool:
    """
    Remet chaque fichier de règles changé par la correction dans son état
    d'avant, s'il n'a pas bougé depuis. Renvoie vrai si l'un d'eux a été remis.
    """
    remis = False
    for chemin, contenu_avant in (avant or {}).items():
        contenu_apres = (apres or {}).get(chemin)
        if contenu_avant == contenu_apres:
            continue
        fichier = Path(chemin)
        if _lire_ou_rien(fichier) != contenu_apres:
            continue
        try:
            if contenu_avant is None:
                fichier.unlink()
            else:
                fichier.write_text(contenu_avant, encoding="utf-8")
            remis = True
        except OSError as exc:
            journal.attention("Règle non remise dans %s : %s", fichier.name, exc)
    return remis


def _memoriser_regle(source: str, cible: str) -> dict:
    """
    « Mémoriser la règle » : tant que le format 1 a du contenu, la règle va
    dans `corrections.txt` comme avant ; une fois le vocabulaire converti (ou
    jamais commencé), elle devient une faute active du vocabulaire personnel.
    """
    from . import vocabulaire_interface, vocabulaire_v2

    if vocabulaire_v2.v1_a_du_contenu(vocabulaire.lire_glossaire(), vocabulaire.lire_corrections()):
        return vocabulaire.ajouter_correction_apprise(source, cible)
    return vocabulaire_interface.memoriser_depuis_correction(source, cible)


# ---------------------------------------------------------------------------
# Remplacements du vocabulaire : montrés, et annulables un à un
# ---------------------------------------------------------------------------

def annuler_remplacement(chemin: str | Path, rang: int) -> dict:
    """
    Défait un remplacement fait par le vocabulaire (étage b), dans le segment
    du compagnon et au même endroit du fichier texte. Le remplacement est
    marqué annulé, jamais effacé : on sait ce qui a été fait, et ce qui a été
    défait.
    """
    from . import vocabulaire_usage

    fichier = Path(chemin or "")
    donnees = compagnon.lire(fichier)
    if not donnees:
        return {"ok": False, "message": langues.t("lect.absent")}
    liste = (donnees.get("vocabulaire") or {}).get("remplacements") or []
    if not (0 <= int(rang) < len(liste)) or not isinstance(liste[int(rang)], dict):
        return {"ok": False, "message": langues.t("lect.annulation_introuvable")}
    remplacement = liste[int(rang)]
    if remplacement.get("annule"):
        return {"ok": False, "message": langues.t("lect.annulation_deja")}

    def calcul(etat: dict):
        if not etat["situe"]:
            raise Refus("introuvable")
        rang_segment = int(remplacement.get("s", -1))
        place = next(((debut, fin) for p in etat["plan"] for r, debut, fin in p["segments"]
                      if r == rang_segment), None)
        if place is None:
            raise Refus("introuvable")
        segment = etat["donnees"]["segments"][rang_segment]
        nouveau = vocabulaire_usage.annuler(str(segment.get("t", "")), remplacement)
        if nouveau is None:
            raise Refus("introuvable")
        corps, donnees_nouvelles = calculer_plages(etat, [(place[0], place[1], nouveau.strip())])
        cible = donnees_nouvelles["vocabulaire"]["remplacements"][int(rang)]
        cible["annule"] = True
        transcription = donnees_nouvelles.get("transcription") or {}
        if isinstance(transcription.get("corrections_appliquees"), int):
            transcription["corrections_appliquees"] = max(0, transcription["corrections_appliquees"] - 1)
        return corps, donnees_nouvelles

    retour = modifier(fichier, calcul)
    if not retour["ok"]:
        if retour.get("code") == "introuvable":
            retour["message"] = langues.t("lect.annulation_introuvable")
        return retour
    retour.pop("ecrit", None)
    journal.info("Remplacement du vocabulaire annulé dans %s", fichier.name)
    return {"ok": True, "message": langues.t("lect.annulation_faite", avant=remplacement.get("a", ""),
                                            apres=remplacement.get("b", ""))}
