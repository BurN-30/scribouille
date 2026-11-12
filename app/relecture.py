"""
Relecture plein cadre : gestes qui demandent d'écrire dans une transcription.

`app/lecture.py` prépare la vue et corrige une forme partout. Ce module ajoute
ce que la relecture plein cadre demande en plus, sans rien changer à l'existant :

  - corriger seulement les endroits choisis (celui que l'on vient de
    sélectionner, ou plusieurs cochés dans l'aperçu), dans le texte et dans le
    compagnon, de façon que la vue reste égale au fichier ;
  - renommer un locuteur (« Locuteur 1 » devient un prénom) dans toute la
    transcription ;
  - enregistrer un export (Markdown) à côté du fichier.

Chaque écriture garde l'état d'avant dans la mémoire d'annulation de
`app/lecture.py` : « Annuler » (Ctrl+Z) défait la dernière, quelle qu'elle soit.

Les refus sont rendus sous forme de codes (« code ») que l'interface formule :
aucune phrase n'est ajoutée au catalogue Python.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import compagnon, journal, lecture, sorties, vocabulaire

#: Endroits détaillés au plus dans un aperçu : au-delà, « tout corriger » reste
#: possible, mais la liste ne sert plus à choisir.
EXTRAITS_MAX = 300
CONTEXTE = 48

#: Un nom de locuteur doit pouvoir être relu depuis le seul fichier texte : même
#: forme que celle que `app/lecture.py` reconnaît en tête de paragraphe.
_MOTIF_NOM = re.compile(r"[A-ZÉÈÀÂÎÔÛÇ][\w'’\- ]{0,28}")


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


def _corps(contenu: str) -> tuple[str, str, str]:
    """En-tête, séparation exacte et corps, pour réécrire sans rien déplacer."""
    entete, corps = lecture.separer_entete(contenu)
    separation = contenu[len(entete):len(contenu) - len(corps)]
    return entete, separation, corps


def occurrences(chemin: str | Path, source: str, cible: str, avant: str = "", apres: str = "") -> dict:
    """
    Tous les endroits qu'une correction toucherait, avec leur contexte, et
    celui qui correspond à la sélection (le texte qui l'entoure à l'écran,
    `avant` et `apres`), rendu dans « choisie » (-1 s'il n'est pas retrouvé).
    """
    prepa = lecture._preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    corps = lecture.separer_entete(prepa["contenu"])[1]
    trouves = vocabulaire.occurrences(prepa["regles"][0], corps)
    if not trouves:
        return {"ok": False, "nombre": 0, "message": lecture._rien_a_changer(prepa, corps)}

    avant_n, apres_n = _normaliser(avant)[-CONTEXTE:], _normaliser(apres)[:CONTEXTE]
    choisie, meilleur = -1, 0
    extraits = []
    for rang, trouve in enumerate(trouves):
        brut_avant = corps[max(0, trouve.start() - 200):trouve.start()]
        brut_apres = corps[trouve.end():trouve.end() + 200]
        if avant_n or apres_n:
            score = _suffixe_commun(_normaliser(brut_avant), avant_n.rstrip()) \
                + _prefixe_commun(_normaliser(brut_apres), apres_n.lstrip())
            if score > meilleur:
                choisie, meilleur = rang, score
        if rang < EXTRAITS_MAX:
            court_avant = brut_avant[-CONTEXTE:]
            court_apres = brut_apres[:CONTEXTE]
            extraits.append({
                "rang": rang,
                "avant": " ".join(court_avant.split()) + (" " if court_avant[-1:].isspace() else ""),
                "forme": trouve.group(0),
                "apres": (" " if court_apres[:1].isspace() else "") + " ".join(court_apres.split()),
                "debut_coupe": trouve.start() > CONTEXTE,
                "fin_coupee": trouve.end() + CONTEXTE < len(corps),
            })
    # Une sélection d'un seul endroit possible n'a pas besoin de contexte.
    if choisie < 0 and len(trouves) == 1:
        choisie = 0
    return {"ok": True, "nombre": len(trouves), "extraits": extraits, "choisie": choisie}


def _segments_situes(corps: str, segments: list) -> list[tuple[int, int, int]]:
    """Position de chaque segment du compagnon dans le corps du fichier, dans l'ordre."""
    situes = []
    curseur = 0
    for rang, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        texte = str(segment.get("t") or "").strip()
        if not texte:
            continue
        position = corps.find(texte, curseur)
        if position < 0:
            continue
        situes.append((position, position + len(texte), rang))
        curseur = position + len(texte)
    return situes


def corriger(chemin: str | Path, source: str, cible: str, rangs, ajouter_regle: bool = False) -> dict:
    """
    Corrige les endroits choisis (rangs de `occurrences`), ou tous avec
    `rangs == "tous"`. Le fichier et le compagnon changent ensemble : un endroit
    que l'on ne sait pas situer dans le compagnon fait refuser la correction,
    plutôt que de laisser la vue différer du fichier.
    """
    prepa = lecture._preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    fichier, source, cible = prepa["fichier"], prepa["source"], prepa["cible"]
    regle = prepa["regles"][0]
    contenu = prepa["contenu"]
    entete, separation, corps = _corps(contenu)
    trouves = vocabulaire.occurrences(regle, corps)
    if not trouves:
        return {"ok": False, "message": lecture._rien_a_changer(prepa, corps)}

    if rangs == "tous":
        choisis = list(range(len(trouves)))
    else:
        choisis = sorted({int(r) for r in (rangs or []) if 0 <= int(r) < len(trouves)})
    if not choisis:
        return {"ok": False, "code": "aucun_endroit"}
    if len(choisis) == len(trouves):
        # Tous les endroits : le chemin existant fait exactement cela.
        retour = lecture.appliquer_correction(fichier, source, cible, ajouter_regle)
        retour["nombre"] = len(trouves)
        return retour

    json_avant = lecture._lire_ou_rien(compagnon.chemin_pour(fichier))
    donnees = compagnon.lire(fichier)
    a_changer = [trouves[r] for r in choisis]

    # Compagnon d'abord, en mémoire : chaque endroit doit tomber dans un segment.
    par_segment: dict[int, list[tuple[int, int]]] = {}
    if donnees:
        segments = donnees.get("segments") or []
        situes = _segments_situes(corps, segments)
        for trouve in a_changer:
            hote = next((s for s in situes if s[0] <= trouve.start() and trouve.end() <= s[1]), None)
            if hote is None:
                return {"ok": False, "code": "non_localise"}
            par_segment.setdefault(hote[2], []).append((trouve.start() - hote[0], trouve.end() - hote[0]))
        for rang_segment, places in par_segment.items():
            segment = segments[rang_segment]
            texte = str(segment.get("t") or "")
            decalage = len(texte) - len(texte.lstrip())
            # Rang de chaque endroit parmi les occurrences du segment, pour viser le bon mot.
            internes = [(t.start(), t.end()) for t in vocabulaire.occurrences(regle, texte)]
            visees = set()
            for debut, fin in sorted(places, reverse=True):
                debut += decalage
                fin += decalage
                texte = texte[:debut] + cible + texte[fin:]
                if (debut, fin) in internes:
                    visees.add(internes.index((debut, fin)))
            segment["t"] = texte
            mots = [m for m in segment.get("m") or [] if isinstance(m, dict) and m.get("t")]
            entiers = [m for m in mots if regle.motif.fullmatch(str(m["t"]))]
            for k in visees:
                if k < len(entiers):
                    entiers[k]["t"] = cible

    morceaux, position = [], 0
    for trouve in a_changer:
        morceaux.append(corps[position:trouve.start()])
        morceaux.append(cible)
        position = trouve.end()
    morceaux.append(corps[position:])
    nouveau = entete + separation + "".join(morceaux)
    try:
        fichier.write_text(nouveau, encoding="utf-8")
    except OSError as exc:
        journal.attention("Correction non écrite dans %s : %s", fichier, exc)
        return {"ok": False, "code": "non_reecrit"}
    if donnees:
        compagnon.enregistrer_tel_quel(fichier, donnees)

    regles_avant = lecture._instantane_regles()
    regle_ajoutee = False
    if ajouter_regle:
        regle_ajoutee = bool(lecture._memoriser_regle(source, cible).get("ajoutee"))
    else:
        from . import vocabulaire_interface

        vocabulaire_interface.proposer_depuis_correction(source, cible)
    regles_apres = lecture._instantane_regles()

    lecture._DERNIERES[str(fichier.resolve())] = {
        "txt_avant": contenu, "txt_apres": nouveau,
        "json_avant": json_avant, "json_apres": lecture._lire_ou_rien(compagnon.chemin_pour(fichier)),
        "regles_avant": regles_avant, "regles_apres": regles_apres, "regle_ajoutee": regle_ajoutee,
    }
    journal.info("Correction ciblée dans %s : « %s » vers « %s », %s endroit(s) sur %s",
                 fichier.name, source, cible, len(choisis), len(trouves))
    return {"ok": True, "remplacements": len(choisis), "nombre": len(trouves),
            "regle_ajoutee": regle_ajoutee, "annulable": True}


def renommer_locuteur(chemin: str | Path, ancien: str, nouveau: str) -> dict:
    """
    Donne un nom à un locuteur dans toute la transcription : tête des
    paragraphes du fichier texte, et étiquette des segments du compagnon. Un nom
    déjà porté par un autre locuteur les réunit. Annulable comme une correction.
    """
    fichier = Path(chemin or "")
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
    if not fichier.is_file():
        return {"ok": False, "code": "absent"}
    try:
        contenu = fichier.read_text(encoding="utf-8")
    except OSError:
        return {"ok": False, "code": "illisible"}

    entete, separation, corps = _corps(contenu)
    motif = re.compile(rf"^(\[\d{{2}}:\d{{2}}:\d{{2}}\] )?{re.escape(ancien)} : ", re.MULTILINE)
    corps_nouveau, nombre = motif.subn(lambda m: (m.group(1) or "") + nouveau + " : ", corps)

    json_avant = lecture._lire_ou_rien(compagnon.chemin_pour(fichier))
    donnees = compagnon.lire(fichier)
    segments_changes = 0
    if donnees:
        for segment in donnees.get("segments") or []:
            if isinstance(segment, dict) and segment.get("l") == ancien:
                segment["l"] = nouveau
                segments_changes += 1
    if not nombre and not segments_changes:
        return {"ok": False, "code": "locuteur_inconnu"}

    nouveau_contenu = entete + separation + corps_nouveau
    try:
        fichier.write_text(nouveau_contenu, encoding="utf-8")
    except OSError as exc:
        journal.attention("Renommage non écrit dans %s : %s", fichier, exc)
        return {"ok": False, "code": "non_reecrit"}
    if donnees and segments_changes:
        compagnon.enregistrer_tel_quel(fichier, donnees)
    regles = lecture._instantane_regles()
    lecture._DERNIERES[str(fichier.resolve())] = {
        "txt_avant": contenu, "txt_apres": nouveau_contenu,
        "json_avant": json_avant, "json_apres": lecture._lire_ou_rien(compagnon.chemin_pour(fichier)),
        "regles_avant": regles, "regles_apres": regles, "regle_ajoutee": False,
    }
    journal.info("Locuteur renommé dans %s : %s paragraphe(s), %s segment(s)",
                 fichier.name, nombre, segments_changes)
    return {"ok": True, "paragraphes": nombre, "segments": segments_changes, "annulable": True}


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
