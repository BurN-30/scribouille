"""
Passage du dossier de données de `%LOCALAPPDATA%\\WhiScribe` à `%LOCALAPPDATA%\\Scribouille`.

Pourquoi : le dossier portait l'ancien nom de l'application (2.0.0 à 2.3.3).
Un projet tiers homonyme range ses modèles dans `%LOCALAPPDATA%\\Whiscribe\\models`,
le même dossier sous Windows : nos données ne doivent plus s'y mêler, et un
effacement ne doit jamais toucher ce qui n'est pas à nous.

Comment, pour que rien ne se perde :
  - seules les entrées que Scribouille sait avoir écrites sont déplacées
    (`FICHIERS`, `MOTIFS`, `DOSSIERS`) ; tout le reste, dont le `models` du
    projet tiers, reste à sa place ;
  - un déplacement est un renommage, sur le même disque : instantané, même
    pour plusieurs gigaoctets de modèles, qui ne sont donc pas retéléchargés ;
  - une entrée déjà présente des deux côtés n'écrase rien : l'ancienne est
    rangée dans `ancien-whiscribe\\` du nouveau dossier ; un dossier présent des
    deux côtés est fusionné entrée par entrée, avec la même règle ;
  - les fichiers qui notent l'emplacement des modèles (`dossier-modeles.txt`,
    et `emplacement-modeles.txt` à côté du programme) sont réécrits s'ils
    pointaient dans l'ancien dossier, leur contenu d'origine gardé au journal ;
  - tout est noté dans `migration-whiscribe.json` : une migration interrompue
    (fichier ouvert ailleurs, coupure) reprend au lancement suivant, là où elle
    s'était arrêtée ;
  - `--revenir-whiscribe` remet tout en place pour une ancienne version.

Version portable et version installée : même comportement, les deux rangent
leurs données dans le même dossier de l'utilisateur.
"""

from __future__ import annotations

import fnmatch
import json
import os
from datetime import datetime
from pathlib import Path

NOM_ANCIEN = "WhiScribe"
NOM_NOUVEAU = "Scribouille"
NOM_JOURNAL = "migration-whiscribe.json"
NOM_CONFLITS = "ancien-whiscribe"
NOM_CHOIX_MODELES = "dossier-modeles.txt"
NOM_AMORCAGE = "emplacement-modeles.txt"

#: Fichiers que Scribouille écrit dans son dossier de données.
FICHIERS = (
    "config.json", "vocabulaire.txt", "corrections.txt", "jeton_hf.txt", "gabarit-ia.txt",
    NOM_CHOIX_MODELES, "calibration.json", "maj-etat.json", "surveillance-vus.json",
    "vocabulaire.toml", "materiel.json", "openvino-chargement-en-cours.txt",
)
#: Fichiers datés ou dérivés, reconnus à leur nom.
MOTIFS = (
    "*-format1-sauvegarde.txt", "vocabulaire-propositions-*.toml", "vocabulaire-propositions-*.txt",
    "scribouille-donnees-avant-import-*.zip", "whiscribe-donnees-avant-import-*.zip",
)
#: Dossiers que Scribouille crée dans son dossier de données.
DOSSIERS = (
    "logs", "modeles", "reprises", "extensions", "cache-pip", "extensions-openvino", "cache-openvino",
    "paquets-hors-ligne", "rapports-banc", "comparaisons", "campagnes", "corpus-campagne",
    # Profil du composant d'affichage (WebView2), depuis la 2.6.
    "webview",
)


def est_a_nous(nom: str, dossier: bool) -> bool:
    if dossier:
        return nom in DOSSIERS
    return nom in FICHIERS or any(fnmatch.fnmatchcase(nom, m) for m in MOTIFS)


def entrees_a_nous(racine: Path) -> list[Path]:
    """Ce que Scribouille reconnaît comme sien dans un dossier, rien d'autre."""
    try:
        return sorted(e for e in racine.iterdir() if est_a_nous(e.name, e.is_dir()))
    except OSError:
        return []


def _lire_journal(nouveau: Path) -> dict:
    try:
        return json.loads((nouveau / NOM_JOURNAL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _ecrire_journal(nouveau: Path, journal: dict) -> None:
    cible = nouveau / NOM_JOURNAL
    provisoire = cible.with_name(cible.name + ".tmp")
    provisoire.write_text(json.dumps(journal, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(provisoire, cible)


def _deplacer(source: Path, cible: Path, rangement_doublons: Path, journal: dict, relatif: str) -> None:
    """
    Renomme `source` en `cible`. En cas de doublon, un dossier est fusionné
    entrée par entrée, un fichier est rangé dans `rangement_doublons` : la
    version déjà à destination est gardée, l'autre n'est jamais écrasée.
    """
    if not cible.exists():
        os.replace(source, cible)
        journal["deplaces"].append(relatif)
        return
    if source.is_dir() and cible.is_dir():
        for enfant in sorted(source.iterdir()):
            _deplacer(enfant, cible / enfant.name, rangement_doublons, journal, f"{relatif}/{enfant.name}")
        try:
            source.rmdir()
        except OSError:
            pass
        return
    rangement = rangement_doublons / relatif
    rangement.parent.mkdir(parents=True, exist_ok=True)
    if rangement.exists():
        rangement = rangement.with_name(f"{rangement.name}.{datetime.now():%Y%m%d%H%M%S}")
    os.replace(source, rangement)
    journal["conflits"].append(relatif)


def _remplacer_prefixe(valeur: str, ancien: Path, nouveau: Path) -> str | None:
    """Le chemin réécrit s'il est dans `ancien`, None sinon (comparaison sans casse)."""
    texte = valeur.strip()
    base = str(ancien).rstrip("\\/")
    if texte.lower() == base.lower() or texte.lower().startswith(base.lower() + os.sep) \
            or texte.lower().startswith(base.lower() + "/"):
        return str(nouveau) + texte[len(base):]
    return None


def _reecrire_choix(fichier: Path, ancien: Path, nouveau: Path, journal: dict) -> None:
    try:
        contenu = fichier.read_text(encoding="utf-8")
    except OSError:
        return
    lignes = contenu.splitlines()
    if not lignes:
        return
    reecrit = _remplacer_prefixe(lignes[0], ancien, nouveau)
    if reecrit is None:
        return
    fichier.write_text(reecrit + "\n", encoding="utf-8")
    journal["reecrits"].append({"fichier": str(fichier), "avant": contenu})


def migrer(ancien: Path, nouveau: Path, programme: Path | None = None) -> dict:
    """
    Déplace les données de Scribouille de `ancien` vers `nouveau`. Sans effet
    si `ancien` n'a rien de Scribouille. Reprend une migration interrompue.
    Ne lève jamais : une entrée qui résiste (fichier ouvert ailleurs) reste en
    place, et sera reprise au lancement suivant. Renvoie le bilan.
    """
    a_deplacer = entrees_a_nous(ancien) if ancien.is_dir() else []
    journal = _lire_journal(nouveau) if nouveau.is_dir() else {}
    if not a_deplacer and journal.get("etat") != "en_cours":
        return {"etat": "rien"}
    nouveau.mkdir(parents=True, exist_ok=True)
    if journal.get("etat") != "en_cours":
        # Une nouvelle passe garde la trace des précédentes.
        journal = {"version": 1, "depuis": str(ancien), "vers": str(nouveau), "etat": "en_cours",
                   "debut": datetime.now().isoformat(timespec="seconds"),
                   "deplaces": list(journal.get("deplaces") or []), "conflits": list(journal.get("conflits") or []),
                   "reecrits": list(journal.get("reecrits") or []), "restes": []}
    _ecrire_journal(nouveau, journal)
    restes: list[str] = []
    for entree in a_deplacer:
        try:
            _deplacer(entree, nouveau / entree.name, nouveau / NOM_CONFLITS, journal, entree.name)
        except OSError as exc:
            restes.append(f"{entree.name} : {exc.strerror or exc}")
        _ecrire_journal(nouveau, journal)
    # Les emplacements de modèles notés qui pointaient dans l'ancien dossier.
    for fichier in (nouveau / NOM_CHOIX_MODELES, (programme / NOM_AMORCAGE) if programme else None):
        if fichier is not None and fichier.is_file():
            try:
                _reecrire_choix(fichier, ancien, nouveau, journal)
            except OSError as exc:
                restes.append(f"{fichier.name} : {exc.strerror or exc}")
    journal["restes"] = restes
    journal["etat"] = "en_cours" if restes else "terminee"
    if not restes:
        journal["fin"] = datetime.now().isoformat(timespec="seconds")
        # L'ancien dossier n'est retiré que s'il est vide : ce qui n'est pas à
        # nous (le « models » du projet homonyme, par exemple) y reste.
        try:
            ancien.rmdir()
            journal["ancien_retire"] = True
        except OSError:
            journal["ancien_retire"] = False
            journal["ancien_garde"] = sorted(e.name for e in ancien.iterdir()) if ancien.is_dir() else []
    _ecrire_journal(nouveau, journal)
    return journal


def revenir(ancien: Path, nouveau: Path, programme: Path | None = None) -> dict:
    """
    Retour arrière, pour une ancienne version qui lit encore `WhiScribe` :
    tout ce qui est à nous dans `nouveau` y retourne (les rangements
    `ancien-whiscribe` compris), les emplacements de modèles réécrits
    sont remis vers l'ancien dossier. Rien n'est supprimé.
    """
    ancien.mkdir(parents=True, exist_ok=True)
    bilan = {"etat": "revenu", "deplaces": [], "conflits": [], "restes": []}
    trace = {"deplaces": bilan["deplaces"], "conflits": bilan["conflits"]}
    for entree in entrees_a_nous(nouveau):
        try:
            _deplacer(entree, ancien / entree.name, ancien / "doublons-scribouille", trace, entree.name)
        except OSError as exc:
            bilan["restes"].append(f"{entree.name} : {exc.strerror or exc}")
    rangement = nouveau / NOM_CONFLITS
    if rangement.is_dir():
        try:
            _deplacer(rangement, ancien / NOM_CONFLITS, ancien / "doublons-scribouille", trace, NOM_CONFLITS)
        except OSError as exc:
            bilan["restes"].append(f"{NOM_CONFLITS} : {exc.strerror or exc}")
    # Les emplacements de modèles qui pointent dans le nouveau dossier
    # reviennent vers l'ancien, comme les modèles eux-mêmes.
    retour = {"reecrits": []}
    for fichier in (ancien / NOM_CHOIX_MODELES, (programme / NOM_AMORCAGE) if programme else None):
        if fichier is not None and fichier.is_file():
            try:
                _reecrire_choix(fichier, nouveau, ancien, retour)
            except OSError as exc:
                bilan["restes"].append(f"{fichier.name} : {exc.strerror or exc}")
    try:
        (nouveau / NOM_JOURNAL).unlink(missing_ok=True)
        nouveau.rmdir()
    except OSError:
        pass
    return bilan


def principal_cli() -> int:
    """`--revenir-whiscribe` : remet les données dans `%LOCALAPPDATA%\\WhiScribe`."""
    from . import chemins

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        print("LOCALAPPDATA introuvable : rien n'a été déplacé.")
        return 1
    bilan = revenir(Path(base) / NOM_ANCIEN, Path(base) / NOM_NOUVEAU, chemins.DOSSIER_PROGRAMME)
    print(f"Retour vers {Path(base) / NOM_ANCIEN} : {len(bilan['deplaces'])} entrée(s) remise(s), "
          f"{len(bilan['conflits'])} doublon(s) rangé(s) à part.")
    for reste in bilan["restes"]:
        print(f"  non déplacé : {reste}")
    return 1 if bilan["restes"] else 0

