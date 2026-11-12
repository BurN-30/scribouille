"""
Écran « Vocabulaire » : ce que l'interface affiche et les gestes qu'elle permet.

Trois sources sont montrées ensemble, chacune marquée :

  - le vocabulaire personnel (`vocabulaire.toml`), seul modifiable ici ;
  - le glossaire et les corrections du format 1, tant qu'ils ne sont pas
    convertis (bouton « Convertir », sans rien perdre) ;
  - les fichiers partagés (équipe, projet), en lecture : on les modifie là où
    ils vivent, ou on les importe.

Gestes : accepter, refuser, modifier, ajouter, supprimer, par lots pour les
deux premiers. Rien n'est actif sans un geste de l'utilisateur.
"""

from __future__ import annotations

from pathlib import Path

from . import journal, langues, lexique
from . import vocabulaire as v1
from . import vocabulaire_v2 as v2


def _faute_en_dict(f: v2.Faute) -> dict:
    return {"forme": f.forme, "voisins": list(f.voisins), "forcer": f.forcer, "vu": f.vu,
            "reunions": f.reunions, "risquee": v2.faute_risquee(f)}


def entree_en_dict(e: v2.Entree, source: str, modifiable: bool) -> dict:
    return {"forme": e.forme, "categorie": e.categorie, "fautes": [_faute_en_dict(f) for f in e.fautes],
            "prononciation": e.prononciation, "poids": e.poids, "origine": e.origine, "etat": e.etat,
            "amorce": e.amorce, "vu": e.vu, "reunions": e.reunions, "note": e.note, "source": source,
            "modifiable": modifiable}


def etat(config: dict, langue: str | None = None) -> dict:
    """Tout ce que l'écran affiche, sans charger de modèle."""
    lignes: list[dict] = []
    problemes: list[str] = []
    glossaire, corrections = v1.lire_glossaire(), v1.lire_corrections()
    avec_v1 = v2.v1_a_du_contenu(glossaire, corrections)
    if avec_v1:
        for e in v2.depuis_v1(glossaire, corrections).entrees:
            lignes.append(entree_en_dict(e, "format1", False))
    partages = []
    for chemin in v2.fichiers_partages(config):
        info = {"chemin": str(chemin), "nom": chemin.name, "ok": True, "termes": 0}
        try:
            voc = v2.lire(chemin)[0]
            info["termes"] = len(voc.actives())
            for e in voc.entrees:
                lignes.append(entree_en_dict(e, "partage:" + chemin.name, False))
        except (OSError, v2.ErreurFormat) as exc:
            info["ok"] = False
            problemes.append(f"{chemin.name} : {exc}")
        partages.append(info)
    try:
        personnel = v2.charger_personnel()
        for e in personnel.entrees:
            lignes.append(entree_en_dict(e, "personnel", True))
    except (OSError, v2.ErreurFormat) as exc:
        problemes.append(f"{v2.NOM_FICHIER} : {exc}")
    effectif, autres = v2.effectif(config)
    problemes += [p for p in autres if p not in problemes]
    from .vocabulaire_usage import selectionner

    amorce = selectionner(effectif, langue=langue)
    return {
        "entrees": lignes,
        "resume": v2.resume(effectif),
        "format1": avec_v1,
        "partages": partages,
        "problemes": problemes,
        "amorce": {"message": amorce["message"], "retenus": amorce["nb_retenus"], "total": amorce["nb_termes"],
                   "jetons": amorce["jetons"], "tronque": amorce["tronque"]},
        "fichier": str(v2.FICHIER_PERSONNEL),
        "rapprochement": bool(config.get("rapprochement_vocabulaire", True)),
        "lexique": lexique.lexique_disponible(),
        "categories": list(v2.CATEGORIES),
    }


def _personnel() -> v2.Vocabulaire:
    return v2.charger_personnel()


def decider(formes: list[str], decision: str) -> dict:
    """Accepter ou refuser des propositions, par lots."""
    voc = _personnel()
    faites = 0
    for forme in formes or []:
        if decision == "accepter":
            faites += int(v2.accepter(voc, forme))
        elif decision == "refuser":
            faites += int(v2.refuser(voc, forme))
    if faites:
        v2.ecrire(voc)
        journal.info("Vocabulaire : %s proposition(s), décision « %s »", faites, decision)
    cle = "voc2.acceptees" if decision == "accepter" else "voc2.refusees"
    return {"ok": True, "n": faites, "message": langues.tn(cle, faites)}


def modifier(forme: str, etat_entree: str, modification: dict) -> dict:
    voc = _personnel()
    entree = voc.chercher(forme, etat=etat_entree)
    if entree is None:
        return {"ok": False, "message": langues.t("voc2.introuvable")}
    nouvelle_forme = v2._texte(modification.get("forme", entree.forme))
    if v2.cle(nouvelle_forme) != entree.cle and voc.chercher(nouvelle_forme, etat=etat_entree) is not None:
        return {"ok": False, "message": langues.t("voc2.doublon", forme=nouvelle_forme)}
    refus = v2.appliquer_modification(entree, modification)
    if refus:
        return {"ok": False, "message": langues.t("voc2.forme_vide")}
    if modification.get("accepter") and entree.etat == "propose":
        v2.accepter(voc, entree.forme)
    v2.ecrire(voc)
    return {"ok": True, "message": langues.t("voc2.enregistre", forme=entree.forme)}


def ajouter(donnees: dict) -> dict:
    voc = _personnel()
    forme = v2._texte(donnees.get("forme", ""))
    if not forme:
        return {"ok": False, "message": langues.t("voc2.forme_vide")}
    if voc.chercher(forme, etat="actif") is not None:
        return {"ok": False, "message": langues.t("voc2.doublon", forme=forme)}
    entree = v2.Entree(forme, origine="saisi", etat="actif", ajoute=v2.aujourdhui())
    v2.appliquer_modification(entree, donnees)
    voc.entrees.append(entree)
    v2.ecrire(voc)
    return {"ok": True, "message": langues.t("voc2.ajoute", forme=forme)}


def supprimer(forme: str, etat_entree: str) -> dict:
    voc = _personnel()
    entree = voc.chercher(forme, etat=etat_entree)
    if entree is None:
        return {"ok": False, "message": langues.t("voc2.introuvable")}
    voc.entrees.remove(entree)
    v2.ecrire(voc)
    return {"ok": True, "message": langues.t("voc2.supprime", forme=forme)}


def importer(chemin: str) -> dict:
    """Verse un fichier (propositions apprises, vocabulaire d'équipe) dans le
    vocabulaire personnel, à l'état « propose » : à relire avant de servir."""
    try:
        autre, remarques = v2.lire(chemin)
    except (OSError, v2.ErreurFormat) as exc:
        return {"ok": False, "message": langues.t("voc2.import_illisible", detail=str(exc))}
    voc = _personnel()
    retour = v2.importer_propositions(voc, autre)
    v2.ecrire(voc)
    return {"ok": True, "message": langues.t("voc2.importe", ajoutees=retour["ajoutees"],
                                            ignorees=retour["ignorees"]), "remarques": remarques[:10]}


def exporter(chemin: str, config: dict) -> dict:
    """Exporte le vocabulaire effectif (toutes sources fusionnées), actifs seulement."""
    effectif, _problemes = v2.effectif(config)
    sortie = v2.Vocabulaire(nom=Path(chemin).stem, portee="equipe",
                            entrees=[e.copie() for e in effectif.actives()])
    for e in sortie.entrees:
        e.source = ""
    v2.ecrire(sortie, chemin)
    return {"ok": True, "message": langues.tn("voc2.exporte", len(sortie.entrees))}


def convertir() -> dict:
    retour = v2.convertir_v1_sur_disque()
    return {"ok": True, "message": langues.t("voc2.converti", n=retour.get("convertis", 0))}


def proposer_depuis_correction(source: str, cible: str) -> bool:
    """Une correction faite dans la vue de relecture, sans règle mémorisée,
    devient une proposition : vue une fois de plus, à relire plus tard."""
    source, cible = " ".join((source or "").split()), " ".join((cible or "").split())
    if not source or not cible or v2.cle(source) == v2.cle(cible):
        return False
    try:
        voc = _personnel()
    except (OSError, v2.ErreurFormat):
        return False
    actif = voc.chercher(cible, etat="actif")
    if actif is not None and actif.faute(source) is not None:
        return False
    if voc.chercher(cible, etat="refuse") is not None:
        return False
    proposition = voc.chercher(cible, etat="propose")
    if proposition is None:
        proposition = v2.Entree(cible, "sigle" if lexique.est_sigle(cible) else "autre", origine="correction",
                                etat="propose", ajoute=v2.aujourdhui())
        voc.entrees.append(proposition)
    faute = proposition.faute(source)
    if faute is None:
        faute = v2.Faute(source)
        proposition.fautes.append(faute)
    faute.vu += 1
    proposition.vu = max(proposition.vu, faute.vu)
    v2.ecrire(voc)
    return True


def memoriser_depuis_correction(source: str, cible: str) -> dict:
    """
    « Mémoriser la règle » dans le vocabulaire personnel (format 2) : la forme
    entendue devient une faute active de la forme corrigée, appliquée partout
    comme l'était une règle du format 1 (forcée si elle n'est faite que de
    mots courants). Une proposition de la même forme est acceptée au passage.
    Mêmes refus que le format 1 : règle déjà là, ou forme entendue déjà
    ramenée à une autre forme.
    """
    source, cible = " ".join((source or "").split()), " ".join((cible or "").split())
    probleme = v1.verifier_regle(source, cible)
    if probleme:
        return {"ajoutee": False, "message": probleme}
    try:
        voc = _personnel()
    except (OSError, v2.ErreurFormat) as exc:
        return {"ajoutee": False, "message": langues.t("voc2.import_illisible", detail=str(exc))}
    for autre in voc.actives():
        if autre.faute(source) is not None and autre.cle != v2.cle(cible):
            return {"ajoutee": False, "message": langues.t("regle.conflit", source=source, cible=autre.forme)}
    actif = voc.chercher(cible, etat="actif")
    deja_graphie = v2.cle(source) == v2.cle(cible) and not lexique.tous_courants(lexique.mots_de(source))
    if actif is not None and (actif.faute(source) is not None or deja_graphie):
        return {"ajoutee": False, "message": langues.t("regle.deja_enregistree")}
    if voc.chercher(cible, etat="propose") is not None:
        v2.accepter(voc, cible)
        actif = voc.chercher(cible, etat="actif")
    if actif is None:
        actif = v2.Entree(cible, "sigle" if lexique.est_sigle(cible) else "autre", origine="correction",
                          etat="actif", amorce=False, ajoute=v2.aujourdhui())
        voc.entrees.append(actif)
    courant = lexique.tous_courants(lexique.mots_de(source))
    if v2.cle(source) != actif.cle or courant:
        # Une correction de casse de mots courants (« pierre » vers « Pierre »)
        # n'est pas faite d'office par la graphie : la faute forcée la garde.
        actif.ajouter_faute(v2.Faute(source, forcer=courant))
    v2.ecrire(voc)
    journal.info("Vocabulaire : règle mémorisée depuis la relecture")
    return {"ajoutee": True, "message": langues.t("voc2.regle_memorisee", source=source, cible=cible)}
