"""
Relecture plein cadre : gestes qui demandent d'écrire dans une transcription.

`app/lecture.py` situe le compagnon dans le fichier et sait écrire une
modification sous la règle d'or (texte affiché, `.txt`, compagnon et
sous-titres égaux, contrôlés après chaque écriture). Ce module ajoute ce que la
relecture plein cadre demande en plus :

  - corriger seulement les endroits choisis : celui que l'on vient de
    sélectionner, situé par sa position exacte à l'écran (même au milieu d'un
    mot, même à partir d'une apostrophe), ou plusieurs cochés dans l'aperçu ;
  - renommer un locuteur (« Locuteur 1 » devient un prénom) dans toute la
    transcription ;
  - enregistrer un export (Markdown) à côté du fichier.

Chaque écriture garde l'état d'avant : « Annuler » (Ctrl+Z) la défait.

Les refus sont rendus sous forme de codes (« code ») que l'interface formule :
aucune phrase n'est ajoutée au catalogue Python.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from . import journal, lecture, sorties

#: Endroits détaillés au plus dans un aperçu : au-delà, « tout corriger » reste
#: possible, mais la liste ne sert plus à choisir.
EXTRAITS_MAX = 300
CONTEXTE = 48

#: Un nom de locuteur doit pouvoir être relu depuis le seul fichier texte : même
#: forme que celle que `app/lecture.py` reconnaît en tête de paragraphe.
_MOTIF_NOM = re.compile(r"[A-ZÉÈÀÂÎÔÛÇ][\w'’\- ]{0,28}")

#: Contexte qui doit concorder, de chaque côté, pour qu'un endroit soit tenu
#: pour celui de la sélection quand la vue n'a pas donné sa position.
_CONCORDANCE = 20


def _normaliser(texte: str) -> str:
    return " ".join((texte or "").split())


def _suffixe_commun(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _prefixe_commun(a: str, b: str) -> int:
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def _position(etat: dict, position, source: str) -> tuple[int, int, int] | None:
    """
    Endroit exact de la sélection, d'après sa position à l'écran : rang du
    paragraphe, début et fin dans son texte. Rien si la position ne désigne
    plus ce texte (fichier changé depuis).
    """
    if not isinstance(position, dict):
        return None
    try:
        k, debut, fin = int(position.get("k", -1)), int(position.get("debut", -1)), int(position.get("fin", -1))
    except (TypeError, ValueError):
        return None
    plan = etat["plan"]
    if not (0 <= k < len(plan)):
        return None
    a, b = plan[k]["debut"] + debut, plan[k]["debut"] + fin
    if not (plan[k]["debut"] <= a < b <= plan[k]["fin"]):
        return None
    if _normaliser(etat["corps"][a:b]) != _normaliser(source):
        return None
    return a, b, k


def _endroits(chemin, source: str, cible: str, avant: str, apres: str, position):
    """
    Endroits qu'une correction peut toucher, et celui de la sélection.

    Les endroits sont les occurrences de la forme (mot entier) ; la sélection,
    quand la vue donne sa position, est située exactement : si elle ne
    coïncide avec aucune occurrence (un morceau de mot, une sélection qui part
    d'une apostrophe), elle devient un endroit de plus, le seul coché. Sans
    position, un endroit n'est « ici » que si le texte qui l'entoure concorde.
    """
    prepa = lecture._preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa, None, [], -1
    etat = lecture._etat(prepa["fichier"], prepa["contenu"])
    trouves = lecture.trouver(etat, prepa["regles"][0])
    exact = _position(etat, position, prepa["source"])
    choisie = -1
    if exact:
        choisie = next((r for r, t in enumerate(trouves) if t[:2] == exact[:2]), -1)
        if choisie < 0:
            trouves = trouves + [exact]
            choisie = len(trouves) - 1
    elif avant or apres:
        avant_n, apres_n = _normaliser(avant)[-CONTEXTE:].rstrip(), _normaliser(apres)[:CONTEXTE].lstrip()
        corps = etat["corps"]
        for rang, (debut, fin, _) in enumerate(trouves):
            accord_avant = _suffixe_commun(_normaliser(corps[max(0, debut - 200):debut]), avant_n)
            accord_apres = _prefixe_commun(_normaliser(corps[fin:fin + 200]), apres_n)
            if accord_avant >= min(len(avant_n), _CONCORDANCE) and accord_apres >= min(len(apres_n), _CONCORDANCE):
                choisie = rang
                break
    return prepa, etat, trouves, choisie


def occurrences(chemin: str | Path, source: str, cible: str, avant: str = "", apres: str = "",
                position=None) -> dict:
    """
    Tous les endroits qu'une correction toucherait, avec leur contexte, et
    celui de la sélection dans « choisie » (-1 s'il n'est pas retrouvé).
    """
    prepa, etat, trouves, choisie = _endroits(chemin, source, cible, avant, apres, position)
    if not prepa["ok"]:
        return prepa
    if not trouves:
        return {"ok": False, "nombre": 0, "message": lecture._rien_a_changer(prepa, etat["corps"])}
    ordre = sorted(range(len(trouves)), key=lambda r: trouves[r][0])
    extraits = []
    for rang in ordre[:EXTRAITS_MAX]:
        debut, fin, k = trouves[rang]
        extraits.append({"rang": rang, **lecture.extrait(etat, debut, fin, k, CONTEXTE)})
    if choisie >= 0 and all(x["rang"] != choisie for x in extraits):
        debut, fin, k = trouves[choisie]
        extraits.insert(0, {"rang": choisie, **lecture.extrait(etat, debut, fin, k, CONTEXTE)})
    return {"ok": True, "nombre": len(trouves), "extraits": extraits, "choisie": choisie}


def corriger(chemin: str | Path, source: str, cible: str, rangs, ajouter_regle: bool = False,
             position=None, empreinte: str = "") -> dict:
    """
    Corrige les endroits choisis (rangs de `occurrences`), ou tous avec
    `rangs == "tous"`. Le fichier, le compagnon et les sous-titres changent
    ensemble, contrôlés après écriture ; un écart fait tout remettre.
    """
    prepa, etat, trouves, _ = _endroits(chemin, source, cible, "", "", position)
    if not prepa["ok"]:
        return prepa
    if not trouves:
        return {"ok": False, "message": lecture._rien_a_changer(prepa, etat["corps"])}
    if rangs == "tous":
        choisis = list(range(len(trouves)))
    else:
        choisis = sorted({int(r) for r in (rangs or []) if 0 <= int(r) < len(trouves)})
    if not choisis:
        return {"ok": False, "code": "aucun_endroit"}
    fichier, source, cible = prepa["fichier"], prepa["source"], prepa["cible"]
    plages = [(trouves[r][0], trouves[r][1], cible) for r in choisis]
    retour = lecture.corriger_plages(fichier, plages, source, cible, ajouter_regle, empreinte)
    if not retour["ok"]:
        return retour
    retour.pop("message_regle", None)
    retour["nombre"] = len(trouves)
    journal.info("Correction dans %s : « %s » vers « %s », %s endroits sur %s",
                 fichier.name, source, cible, len(choisis), len(trouves))
    return retour


def renommer_locuteur(chemin: str | Path, ancien: str, nouveau: str, empreinte: str = "") -> dict:
    """
    Donne un nom à un locuteur dans toute la transcription : tête des
    paragraphes du fichier texte, et étiquette des segments du compagnon. Un nom
    déjà porté par un autre locuteur les réunit ; leurs paragraphes restent
    distincts, à l'écran comme dans le fichier. Annulable comme une correction.
    """
    ancien = " ".join((ancien or "").split())
    nouveau = " ".join((nouveau or "").split())
    if nouveau:
        nouveau = nouveau[0].upper() + nouveau[1:]
    if not ancien:
        return {"ok": False, "code": "locuteur_inconnu"}
    if not nouveau or not _MOTIF_NOM.fullmatch(nouveau):
        return {"ok": False, "code": "nom_invalide"}
    if nouveau == ancien:
        return {"ok": False, "code": "nom_identique"}
    if not Path(chemin or "").is_file():
        return {"ok": False, "code": "absent"}
    compte = {"paragraphes": 0, "segments": 0}

    def calcul(etat: dict):
        corps, plan = etat["corps"], etat["plan"]
        prefixes = {k: corps[p["tete"]:p["nom"]] + nouveau + " : "
                    for k, p in enumerate(plan) if p["locuteur"] == ancien and p.get("nom") is not None}
        donnees = None
        if etat["situe"]:
            donnees = copy.deepcopy(etat["donnees"])
            for segment in donnees.get("segments") or []:
                if isinstance(segment, dict) and segment.get("l") == ancien:
                    segment["l"] = nouveau
                    compte["segments"] += 1
        compte["paragraphes"] = len(prefixes)
        if not prefixes and not compte["segments"]:
            raise lecture.Refus("locuteur_inconnu")
        nouveau_corps = lecture._reconstruire(corps, plan, {}, prefixes)
        if donnees is not None and lecture.situer(nouveau_corps, donnees["segments"]) is None:
            raise lecture.Refus("ecart")
        return nouveau_corps, donnees

    retour = lecture.modifier(chemin, calcul, empreinte)
    if not retour["ok"]:
        retour.pop("message", None)
        return retour
    retour.pop("ecrit", None)
    journal.info("Locuteur renommé dans %s : %s paragraphes, %s segments",
                 Path(chemin).name, compte["paragraphes"], compte["segments"])
    return {"ok": True, "paragraphes": compte["paragraphes"], "segments": compte["segments"],
            "nom": nouveau, "annulable": True}


EXTENSIONS_EXPORT = (".md",)


def enregistrer_export(chemin: str | Path, extension: str, contenu: str) -> dict:
    """Écrit un export à côté de la transcription, sans jamais écraser un fichier."""
    fichier = Path(chemin or "")
    extension = str(extension or "").lower()
    if extension not in EXTENSIONS_EXPORT:
        return {"ok": False, "code": "format_refuse"}
    if not fichier.parent.is_dir():
        return {"ok": False, "code": "absent"}
    cible = sorties.chemin_libre(fichier.parent, fichier.stem, extension)
    try:
        cible.write_text(contenu or "", encoding="utf-8")
    except OSError as exc:
        journal.attention("Export non écrit (%s) : %s", cible, exc)
        return {"ok": False, "code": "non_reecrit"}
    journal.info("Export écrit : %s", cible)
    return {"ok": True, "chemin": str(cible), "nom": cible.name}
