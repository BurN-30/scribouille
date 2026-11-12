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

#: Les seuils de découpe sont ceux du fichier texte (`app/sorties.py`) : la
#: vue coupe ses paragraphes exactement où le fichier les coupe.
LONGUEUR_CONFORTABLE = sorties.LONGUEUR_CONFORTABLE
LONGUEUR_MAXIMALE = sorties.LONGUEUR_MAXIMALE
SILENCE_PARAGRAPHE = sorties.SILENCE_PARAGRAPHE


def _doit_couper(courant: dict, segment: dict) -> bool:
    """Faut-il ouvrir un nouveau paragraphe avant ce segment ? Même règle que le fichier."""
    return sorties.doit_couper(courant["texte"], courant["fin"], float(segment.get("d", 0) or 0))


def _paragraphes_du_compagnon(donnees: dict) -> list[dict]:
    """
    Regroupe les segments en paragraphes lisibles.

    Les répliques consécutives d'un même locuteur sont réunies, et un long
    monologue est coupé sur une fin de phrase : on lit un compte rendu, pas une
    liste de sous-titres, et pas davantage un mur de texte.
    """
    paragraphes: list[dict] = []
    courant: dict | None = None
    # Segments que le vocabulaire a changés (remplacements non annulés).
    corriges = {
        int(r.get("s", -1))
        for r in ((donnees.get("vocabulaire") or {}).get("remplacements") or [])
        if isinstance(r, dict) and not r.get("annule")
    }

    for rang, segment in enumerate(donnees.get("segments") or []):
        if not isinstance(segment, dict) or not str(segment.get("t") or "").strip():
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
        separateur = " " if courant["texte"] else ""
        courant["texte"] = courant["texte"] + separateur + texte

        mots = [
            {
                "t": str(mot["t"]),
                "p": round(float(mot.get("p", 1) or 0), 3),
                "d": round(float(mot.get("d", 0) or 0), 2),
            }
            for mot in segment.get("m") or []
            if isinstance(mot, dict) and mot.get("t")
        ]
        # Segment sans mots : le paragraphe reste lisible, simplement sans
        # confiance affichée pour cette portion. Segment corrigé après coup par
        # le vocabulaire : le texte corrigé fait foi, les mots changés sont
        # marqués.
        places, reste = _placer_mots(texte, mots, marquer=rang in corriges)
        if places:
            places[0]["e"] = separateur + places[0]["e"]
        else:
            reste = separateur + reste
        courant["mots"].extend(places)
        if reste:
            debut = float(segment.get("d", 0) or 0)
            courant["mots"].append({"t": "", "e": reste, "p": -1.0, "d": round(debut, 2)})

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
            "mots": [{"t": mot, "e": " " if rang else "", "p": -1.0, "d": debut}
                     for rang, mot in enumerate(texte.split())],
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
    remplacements = []
    if donnees and not tronque:
        for rang, r in enumerate(((donnees.get("vocabulaire") or {}).get("remplacements")) or []):
            if isinstance(r, dict) and not r.get("annule"):
                remplacements.append({"rang": rang, "avant": str(r.get("a", "")), "apres": str(r.get("b", "")),
                                      "regle": str(r.get("regle", "")), "debut": float(r.get("d", 0) or 0)})
    return {
        "ok": True,
        "remplacements": remplacements,
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
        # Texte du fichier, en-tête retiré : c'est lui que « Copier le texte »
        # met dans le presse-papiers, jamais une reconstruction.
        "corps": corps.strip(),
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
# Corrections apprises depuis la vue de lecture
# ---------------------------------------------------------------------------

#: Dernière correction de chaque fichier, de quoi la défaire : contenus du
#: texte, du compagnon et des règles avant et après. En mémoire seulement, le
#: temps de la session : annuler vaut pour une erreur que l'on vient de faire.
_DERNIERES: dict[str, dict] = {}

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


def apercu_correction(chemin: str | Path, source: str, cible: str) -> dict:
    """
    Ce qu'une correction changerait, avant de l'appliquer : le nombre
    d'endroits du fichier touchés, et chacun avec un peu de contexte.
    """
    prepa = _preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    corps = separer_entete(prepa["contenu"])[1]
    trouves = vocabulaire.occurrences(prepa["regles"][0], corps)
    if not trouves:
        return {"ok": False, "nombre": 0, "message": _rien_a_changer(prepa, corps)}
    extraits = []
    for trouve in trouves[:_EXTRAITS_APERCU]:
        avant = corps[max(0, trouve.start() - _CONTEXTE_APERCU):trouve.start()]
        apres = corps[trouve.end():trouve.end() + _CONTEXTE_APERCU]
        extraits.append({
            "avant": " ".join(avant.split()) + (" " if avant[-1:].isspace() else ""),
            "forme": trouve.group(0),
            "apres": (" " if apres[:1].isspace() else "") + " ".join(apres.split()),
            "debut_coupe": trouve.start() > _CONTEXTE_APERCU,
            "fin_coupee": trouve.end() + _CONTEXTE_APERCU < len(corps),
        })
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


def _lire_ou_rien(chemin: Path) -> str | None:
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError:
        return None


def appliquer_correction(chemin: str | Path, source: str, cible: str,
                         ajouter_regle: bool = False) -> dict:
    """
    Corrige une forme dans une transcription déjà écrite.

    Trois écritures, dans cet ordre, chacune indépendante de la suivante :
    le fichier texte (corps seulement, l'en-tête décrit la production et ne
    doit pas bouger), le compagnon JSON s'il existe, et enfin `corrections.txt`
    quand l'utilisateur demande que la règle vaille pour les transcriptions
    suivantes. L'état d'avant est gardé : `annuler_correction` le remet.
    """
    prepa = _preparer_correction(chemin, source, cible)
    if not prepa["ok"]:
        return prepa
    fichier, source, cible = prepa["fichier"], prepa["source"], prepa["cible"]
    regles, contenu = prepa["regles"], prepa["contenu"]
    json_avant = _lire_ou_rien(compagnon.chemin_pour(fichier))

    entete, corps = separer_entete(contenu)
    # `separer_entete` retire les sauts de ligne entre l'en-tête et le corps :
    # ils sont remis tels quels, sans quoi la barre de fin d'en-tête et la
    # première phrase se retrouvaient sur la même ligne.
    separation = contenu[len(entete):len(contenu) - len(corps)]
    corps_corrige, remplacements = vocabulaire.appliquer(corps, regles)
    if not remplacements:
        return {"ok": False, "message": _rien_a_changer(prepa, corps)}

    nouveau = entete + separation + corps_corrige
    try:
        fichier.write_text(nouveau, encoding="utf-8")
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

    # Les fichiers de règles sont photographiés avant et après : l'annulation
    # remet la règle mémorisée, ou la proposition ajoutée, telle qu'avant.
    regles_avant = _instantane_regles()
    regle_ajoutee = False
    message_regle = ""
    if ajouter_regle:
        retour = _memoriser_regle(source, cible)
        regle_ajoutee = bool(retour.get("ajoutee"))
        message_regle = retour.get("message", "")
    else:
        # Sans règle mémorisée, la correction devient une proposition du
        # vocabulaire (format 2), à relire plus tard : rien ne sert sans accord.
        from . import vocabulaire_interface

        if vocabulaire_interface.proposer_depuis_correction(source, cible):
            message_regle = langues.t("voc2.propose_depuis_lecture")
    regles_apres = _instantane_regles()

    _DERNIERES[str(fichier.resolve())] = {
        "txt_avant": contenu, "txt_apres": nouveau,
        "json_avant": json_avant, "json_apres": _lire_ou_rien(compagnon.chemin_pour(fichier)),
        "regles_avant": regles_avant, "regles_apres": regles_apres, "regle_ajoutee": regle_ajoutee,
    }

    journal.info(
        "Correction appliquée dans %s : « %s » vers « %s », %s remplacement(s)%s",
        fichier.name, source, cible, remplacements,
        ", règle mémorisée" if regle_ajoutee else "",
    )
    return {
        "ok": True,
        "remplacements": remplacements,
        "regle_ajoutee": regle_ajoutee,
        "annulable": True,
        "message": (
            langues.tn("lect.remplacements", remplacements)
            + (" " + message_regle if message_regle else "")
        ),
    }


def correction_annulable(chemin: str | Path) -> bool:
    return str(Path(chemin or "").resolve()) in _DERNIERES


def annuler_correction(chemin: str | Path) -> dict:
    """
    Défait la dernière correction appliquée à ce fichier : texte, compagnon et,
    si elle avait été ajoutée, la règle. Rien n'est touché si le fichier a été
    modifié entre-temps, par un éditeur par exemple : on écraserait ce travail.
    """
    fichier = Path(chemin or "")
    cle = str(fichier.resolve())
    derniere = _DERNIERES.get(cle)
    if not derniere:
        return {"ok": False, "message": langues.t("lect.annulation.aucune")}
    if _lire_ou_rien(fichier) != derniere["txt_apres"]:
        _DERNIERES.pop(cle, None)
        return {"ok": False, "message": langues.t("lect.annulation.modifie")}
    try:
        fichier.write_text(derniere["txt_avant"], encoding="utf-8")
        cible_json = compagnon.chemin_pour(fichier)
        if derniere["json_avant"] is not None and _lire_ou_rien(cible_json) == derniere["json_apres"]:
            cible_json.write_text(derniere["json_avant"], encoding="utf-8")
    except OSError as exc:
        journal.attention("Correction non annulée dans %s : %s", fichier, exc)
        return {"ok": False, "message": langues.t("lect.non_reecrit")}
    _DERNIERES.pop(cle, None)

    message = langues.t("lect.annulation.faite")
    remis = _remettre_regles(derniere["regles_avant"], derniere["regles_apres"])
    regle_retiree = bool(remis and derniere["regle_ajoutee"])
    if regle_retiree:
        message += " " + langues.t("lect.annulation.regle")
    elif remis:
        message += " " + langues.t("lect.annulation.proposition")
    journal.info("Correction annulée dans %s%s", fichier.name, ", règle retirée" if regle_retiree else "")
    return {"ok": True, "message": message, "regle_retiree": regle_retiree}


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
    Défait un remplacement fait par le vocabulaire (étage b) : dans le texte
    du segment du compagnon, puis dans le fichier texte (même segment, corps
    seulement). Le remplacement est marqué annulé, jamais effacé : on sait
    ce qui a été fait, et ce qui a été défait.
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
    segments = donnees.get("segments") or []
    rang_segment = int(remplacement.get("s", -1))
    if not (0 <= rang_segment < len(segments)):
        return {"ok": False, "message": langues.t("lect.annulation_introuvable")}
    segment = segments[rang_segment]
    ancien_texte = str(segment.get("t", ""))
    nouveau_texte = vocabulaire_usage.annuler(ancien_texte, remplacement)
    if nouveau_texte is None:
        return {"ok": False, "message": langues.t("lect.annulation_introuvable")}
    try:
        contenu = fichier.read_text(encoding="utf-8")
        entete, corps = separer_entete(contenu)
        # Même précaution que pour une correction : la séparation entre
        # l'en-tête et le corps est remise telle quelle.
        separation = contenu[len(entete):len(contenu) - len(corps)]
        if ancien_texte and ancien_texte in corps:
            fichier.write_text(entete + separation + corps.replace(ancien_texte, nouveau_texte, 1),
                               encoding="utf-8")
    except OSError as exc:
        journal.attention("Annulation non écrite dans %s : %s", fichier, exc)
        return {"ok": False, "message": langues.t("lect.non_reecrit")}
    segment["t"] = nouveau_texte
    remplacement["annule"] = True
    transcription = donnees.get("transcription") or {}
    if isinstance(transcription.get("corrections_appliquees"), int):
        transcription["corrections_appliquees"] = max(0, transcription["corrections_appliquees"] - 1)
    compagnon.enregistrer_tel_quel(fichier, donnees)
    journal.info("Remplacement du vocabulaire annulé dans %s (segment %s)", fichier.name, rang_segment)
    return {"ok": True, "message": langues.t("lect.annulation_faite", avant=remplacement.get("a", ""),
                                            apres=remplacement.get("b", ""))}
