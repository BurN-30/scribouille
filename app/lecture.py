"""
Vue de lecture : relire une transcription dans l'application.

Jusqu'ici l'application écrivait des fichiers et les listait. Pour relire le
résultat il fallait sortir, ouvrir le Bloc-notes, chercher. C'est pourtant à la
relecture que tout se joue : vérifier un nom propre, retrouver une décision,
préparer un compte rendu.

Ce module prépare tout ce que la vue affiche, et fait le travail que le
JavaScript n'a pas à faire :

  - assembler des paragraphes lisibles, regroupés par locuteur, exactement
    comme le fichier texte ;
  - y joindre la confiance mot à mot quand le compagnon JSON est là ;
  - se rabattre proprement sur le fichier texte quand il n'y est pas, ce qui
    est le cas de toutes les transcriptions antérieures ;
  - appliquer une correction apprise au texte affiché, au fichier `.txt` et au
    compagnon, d'un seul geste et sans jamais toucher à l'en-tête du fichier.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import compagnon, gabarit, journal, langues, vocabulaire

#: Taille au-delà de laquelle un fichier texte n'est pas chargé en entier.
#: Cent mille caractères représentent déjà plusieurs heures de réunion.
LIMITE_CARACTERES = 400_000

#: Ligne de séparation de l'en-tête écrit par `app/sorties.py`.
_BARRE = "=" * 68

#: Les deux libellés produits par l'application, plus un nom propre quelconque.
#: « Speaker » comme « Locuteur » sont reconnus quelle que soit la langue de
#: l'interface : une transcription écrite en français se relit en anglais.
_MOTIF_LOCUTEUR = re.compile(
    r"^((?:Locuteur|Speaker)\s+\d+|[A-ZÉÈÀÂÎÔÛÇ][\w'’\- ]{0,28})\s:\s"
)
_MOTIF_HORODATAGE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s*")


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
# Paragraphes
# ---------------------------------------------------------------------------

#: Un paragraphe se ferme à la première fin de phrase passé ce seuil, et de
#: force au second. Sans cela, une heure de réunion sans locuteurs séparés
#: s'afficherait d'un seul bloc, illisible à l'écran.
LONGUEUR_CONFORTABLE = 450
LONGUEUR_MAXIMALE = 900

#: Un silence de cette durée entre deux segments marque un changement de sujet.
SILENCE_PARAGRAPHE = 1.5

_FINS_DE_PHRASE = (".", "!", "?", "…", ":")


def _doit_couper(courant: dict, segment: dict) -> bool:
    """Faut-il ouvrir un nouveau paragraphe avant ce segment ?"""
    longueur = len(courant["texte"])
    if longueur >= LONGUEUR_MAXIMALE:
        return True
    if longueur < LONGUEUR_CONFORTABLE:
        return False
    if not courant["texte"].rstrip().endswith(_FINS_DE_PHRASE):
        return False
    silence = float(segment.get("d", 0) or 0) - courant["fin"]
    return silence >= SILENCE_PARAGRAPHE or longueur >= LONGUEUR_CONFORTABLE


def _paragraphes_du_compagnon(donnees: dict) -> list[dict]:
    """
    Regroupe les segments en paragraphes lisibles.

    Les répliques consécutives d'un même locuteur sont réunies, et un long
    monologue est coupé sur une fin de phrase : on lit un compte rendu, pas une
    liste de sous-titres, et pas davantage un mur de texte.
    """
    paragraphes: list[dict] = []
    courant: dict | None = None

    for segment in donnees.get("segments") or []:
        if not isinstance(segment, dict) or not segment.get("t"):
            continue
        locuteur = str(segment.get("l") or "")
        if courant is None or locuteur != courant["locuteur"] or _doit_couper(courant, segment):
            courant = {
                "debut": float(segment.get("d", 0) or 0),
                "fin": float(segment.get("f", 0) or 0),
                "locuteur": locuteur,
                "mots": [],
                "texte": "",
            }
            paragraphes.append(courant)
        courant["fin"] = float(segment.get("f", courant["fin"]) or courant["fin"])
        texte = str(segment.get("t", "")).strip()
        courant["texte"] = (courant["texte"] + " " + texte).strip()

        mots = segment.get("m") or []
        if mots:
            for mot in mots:
                if not isinstance(mot, dict) or not mot.get("t"):
                    continue
                courant["mots"].append({
                    "t": str(mot["t"]),
                    "p": round(float(mot.get("p", 1) or 0), 3),
                    "d": round(float(mot.get("d", 0) or 0), 2),
                })
        else:
            # Segment sans mots : le paragraphe reste lisible, simplement sans
            # confiance affichée pour cette portion.
            for morceau in texte.split():
                courant["mots"].append({"t": morceau, "p": -1.0, "d": courant["debut"]})

    return paragraphes


def _couper_long(texte: str) -> list[str]:
    """Découpe un bloc trop long sur les fins de phrase, pour qu'il reste lisible."""
    if len(texte) <= LONGUEUR_MAXIMALE:
        return [texte]
    morceaux: list[str] = []
    courant = ""
    for phrase in re.split(r"(?<=[.!?…])\s+", texte):
        courant = (courant + " " + phrase).strip() if courant else phrase
        if len(courant) >= LONGUEUR_CONFORTABLE:
            morceaux.append(courant)
            courant = ""
    if courant:
        morceaux.append(courant)
    return morceaux or [texte]


def _paragraphes_du_texte(corps: str) -> list[dict]:
    """Repli sans compagnon : on découpe le fichier texte sur les lignes vides."""
    paragraphes: list[dict] = []
    blocs: list[str] = []
    for bloc in re.split(r"\n\s*\n", corps.strip()):
        blocs.extend(_couper_long(" ".join(bloc.split())))

    for texte in blocs:
        if not texte:
            continue
        debut = 0.0
        trouve = _MOTIF_HORODATAGE.match(texte)
        if trouve:
            heures, minutes, secondes = trouve.group(1).split(":")
            debut = int(heures) * 3600 + int(minutes) * 60 + int(secondes)
            texte = texte[trouve.end():]
        locuteur = ""
        trouve = _MOTIF_LOCUTEUR.match(texte)
        if trouve:
            locuteur = trouve.group(1)
            texte = texte[trouve.end():]
        paragraphes.append({
            "debut": debut, "fin": debut, "locuteur": locuteur, "texte": texte,
            "mots": [{"t": mot, "p": -1.0, "d": debut} for mot in texte.split()],
        })
    return paragraphes


# ---------------------------------------------------------------------------
# Chargement d'une transcription
# ---------------------------------------------------------------------------

def charger(chemin: str | Path) -> dict:
    """
    Tout ce dont la vue de lecture a besoin pour un fichier de sortie.

    Le compagnon JSON n'est jamais obligatoire : sans lui, le texte s'affiche
    quand même, sans surlignage, avec une phrase qui l'explique.
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

    entete, corps = separer_entete(contenu)
    donnees = compagnon.lire(fichier)

    if donnees and not tronque:
        paragraphes = _paragraphes_du_compagnon(donnees)
        meta = _meta_du_compagnon(donnees, fichier)
        message = ""
    else:
        paragraphes = _paragraphes_du_texte(corps)
        meta = _meta_de_lentete(entete, fichier)
        message = langues.t("lect.tronque" if tronque else "lect.sans_compagnon")

    seuils = (donnees or {}).get("seuils") or {}
    return {
        "ok": True,
        "chemin": str(fichier),
        "nom": fichier.name,
        "compagnon": bool(donnees) and not tronque,
        "message": message,
        "meta": meta,
        "seuils": {
            "faible": float(seuils.get("faible", compagnon.SEUIL_FAIBLE)),
            "tres_faible": float(seuils.get("tres_faible", compagnon.SEUIL_TRES_FAIBLE)),
        },
        "paragraphes": paragraphes,
        "entete": entete,
        "statistiques": _statistiques(paragraphes, seuils),
    }


def _duree_lisible(secondes: float) -> str:
    secondes = int(secondes or 0)
    heures, reste = divmod(secondes, 3600)
    minutes, sec = divmod(reste, 60)
    if heures:
        return langues.t("duree_longue.heures", h=heures, m=f"{minutes:02d}")
    return langues.t("duree_longue.minutes", m=minutes, s=f"{sec:02d}")


def _meta_du_compagnon(donnees: dict, fichier: Path) -> dict:
    source = donnees.get("source") or {}
    infos = donnees.get("transcription") or {}
    chemin_source = str(source.get("chemin", ""))
    date = str(infos.get("date", ""))
    try:
        date_lisible = datetime.fromisoformat(date).strftime(langues.t("format.date_heure"))
    except ValueError:
        date_lisible = date
    nb = int(infos.get("nb_locuteurs", 0) or 0)
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
            langues.t("lect.locuteurs_detectes", n=nb) if nb
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
    faible = float(seuils.get("faible", compagnon.SEUIL_FAIBLE))
    total = 0
    signales = 0
    for paragraphe in paragraphes:
        for mot in paragraphe["mots"]:
            if mot["p"] < 0:
                continue
            total += 1
            if mot["p"] < faible:
                signales += 1
    return {"mots": total, "signales": signales}


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
# Corrections apprises depuis la vue de lecture
# ---------------------------------------------------------------------------

def appliquer_correction(chemin: str | Path, source: str, cible: str,
                         ajouter_regle: bool = True) -> dict:
    """
    Corrige une forme dans une transcription déjà écrite.

    Trois écritures, dans cet ordre, chacune indépendante de la suivante :
    le fichier texte (corps seulement, l'en-tête décrit la production et ne
    doit pas bouger), le compagnon JSON s'il existe, et enfin `corrections.txt`
    pour que la même erreur ne revienne plus jamais.
    """
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

    entete, corps = separer_entete(contenu)
    # `separer_entete` retire les sauts de ligne entre l'en-tête et le corps :
    # ils sont remis tels quels, sans quoi la barre de fin d'en-tête et la
    # première phrase se retrouvaient sur la même ligne.
    separation = contenu[len(entete):len(contenu) - len(corps)]
    corps_corrige, remplacements = vocabulaire.appliquer(corps, regles)
    if not remplacements:
        return {"ok": False, "message": langues.t("lect.non_retrouve", source=source)}

    try:
        fichier.write_text(entete + separation + corps_corrige, encoding="utf-8")
    except OSError as exc:
        journal.attention("Correction non écrite dans %s : %s", fichier, exc)
        return {"ok": False, "message": langues.t("lect.non_reecrit")}

    donnees = compagnon.lire(fichier)
    if donnees:
        for segment in donnees.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            segment["t"], _ = vocabulaire.appliquer(str(segment.get("t", "")), regles)
            for mot in segment.get("m") or []:
                if isinstance(mot, dict) and mot.get("t"):
                    mot["t"], _ = vocabulaire.appliquer(str(mot["t"]), regles)
        compagnon.enregistrer_tel_quel(fichier, donnees)

    regle_ajoutee = False
    message_regle = ""
    if ajouter_regle:
        retour = vocabulaire.ajouter_correction_apprise(source, cible)
        regle_ajoutee = bool(retour.get("ajoutee"))
        message_regle = retour.get("message", "")

    journal.info(
        "Correction appliquée dans %s : « %s » vers « %s », %s remplacement(s)%s",
        fichier.name, source, cible, remplacements,
        ", règle mémorisée" if regle_ajoutee else "",
    )
    return {
        "ok": True,
        "remplacements": remplacements,
        "regle_ajoutee": regle_ajoutee,
        "message": (
            langues.tn("lect.remplacements", remplacements)
            + (" " + message_regle if message_regle else "")
        ),
    }
