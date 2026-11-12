"""
Inventaire de ce que Scribouille écrit sur le disque, libération et effacement.

Une seule liste fait foi : celle des noms que l'application écrit dans son
dossier de données (`app/migration.py` : `FICHIERS`, `MOTIFS`, `DOSSIERS`),
plus les modèles (dossier choisi par l'utilisateur), le programme, et pour la
version installée ses raccourcis et sa clé de désinstallation. Tout ce qui
n'est pas reconnu est montré à part et jamais touché : l'ancien dossier
`WhiScribe` est partagé avec un projet tiers homonyme, et un dossier de modèles
choisi à la main peut contenir les fichiers d'autres outils.

Les transcriptions vivent dans le dossier de sortie : elles sont comptées à
part (`transcriptions_octets`) et ne sont effacées qu'avec un drapeau explicite.

Postes (clé : contenu) :
    programme            le programme (version installée ou portable, ou les sources)
    modele:<dépôt>       un modèle de transcription ; libérable s'il ne sert pas au réglage
    openvino             moteur optionnel pour la puce Intel (extensions-openvino)
    locuteurs            séparation des locuteurs (extensions)
    cache_openvino       modèles compilés par OpenVINO, refaits au besoin
    cache_pip            téléchargements de l'installation des extensions
    paquets_hors_ligne   paquets déposés pour une installation sans réseau
    affichage            profil du composant d'affichage (WebView2)
    journaux             journaux des sessions
    reprises             transcriptions interrompues, reprenables
    mesures              banc d'essai, comparaisons, campagnes, corpus, durées apprises
    vocabulaire          glossaire, corrections, vocabulaire personnel et propositions
    relecture            historique des corrections (annulations, originaux) et positions de lecture
    reglages             réglages et petits fichiers d'état
    sauvegardes          sauvegardes avant import, doublons de l'ancien dossier
    ancien_dossier       ce qui reste de Scribouille dans %LOCALAPPDATA%\\WhiScribe
    installation         raccourcis et entrée de désinstallation (version installée)
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import chemins, langues, migration

#: Dossiers jamais comptés dans le programme depuis les sources.
EXCLUS_SOURCE = (".venv", ".git", "build", "dist", "__pycache__", ".github")

#: Noms écrits par la bibliothèque de Hugging Face dans un dossier de modèles.
NOMS_HUB = ("CACHEDIR.TAG", ".locks", ".ecriture-test")

#: Fichiers produits pour une transcription (même nom de base).
EXTENSIONS_SORTIES = (".txt", ".json", ".srt", ".vtt")

#: Identifiant de l'installation (packaging/setup.iss, AppId).
APP_ID = "{4E1B7C86-8F2A-4B5D-9C31-6D0A4F7E2B93}"

#: Durée de validité d'un aperçu d'effacement.
VALIDITE_APERCU_S = 15 * 60

_GROUPES = {
    "reglages": ("config.json", "dossier-modeles.txt", "jeton_hf.txt", "gabarit-ia.txt", "maj-etat.json",
                 "surveillance-vus.json", "materiel.json", "materiel.json.tmp", migration.NOM_JOURNAL,
                 "openvino-chargement-en-cours.txt", "config.json.tmp"),
    "vocabulaire": ("vocabulaire.txt", "corrections.txt", "vocabulaire.toml", "vocabulaire.toml.tmp",
                    "*-format1-sauvegarde.txt", "vocabulaire-propositions-*.toml", "vocabulaire-propositions-*.txt"),
    "mesures": ("calibration.json", "rapports-banc", "comparaisons", "campagnes", "corpus-campagne"),
    "sauvegardes": ("scribouille-donnees-avant-import-*.zip", "whiscribe-donnees-avant-import-*.zip",
                    migration.NOM_CONFLITS),
    "journaux": ("logs",),
    "reprises": ("reprises",),
    "openvino": ("extensions-openvino",),
    "locuteurs": ("extensions",),
    "cache_openvino": ("cache-openvino",),
    "cache_pip": ("cache-pip",),
    "paquets_hors_ligne": ("paquets-hors-ligne",),
    "affichage": ("webview",),
    # Pile d'annulation de la relecture (avec l'original de chaque texte
    # corrigé) et dernière position de lecture par transcription.
    "relecture": ("historique-relecture", "relecture-positions.json", "relecture-positions.json.scribouille-tmp",
                  "exports.json"),
}

#: Postes libérables sans rien perdre : refaits ou retéléchargés au besoin.
LIBERABLES = {"cache_openvino", "cache_pip", "affichage", "journaux"}

#: Ordre d'affichage.
ORDRE = ("programme", "modele", "openvino", "locuteurs", "cache_openvino", "cache_pip", "paquets_hors_ligne",
         "affichage", "journaux", "reprises", "mesures", "vocabulaire", "relecture", "reglages", "sauvegardes",
         "ancien_dossier", "installation")


@dataclass
class Poste:
    cle: str
    chemins: list[Path] = field(default_factory=list)
    liberable: bool = False
    libelle: str = ""
    description: str = ""
    octets: int = 0
    nombre: int = 0
    #: Entrées de registre (version installée), effacées par le désinstalleur.
    registre: list[str] = field(default_factory=list)

    def en_dict(self) -> dict:
        return {"cle": self.cle, "libelle": self.libelle, "octets": self.octets,
                "taille": langues.octets(self.octets), "liberable": self.liberable,
                "description": self.description, "chemins": [str(c) for c in self.chemins],
                "nombre": self.nombre, **({"registre": self.registre} if self.registre else {})}


# ---------------------------------------------------------------------------
# Mesure
# ---------------------------------------------------------------------------

def taille(chemin: Path, exclus: tuple[str, ...] = ()) -> tuple[int, int]:
    """Octets et nombre de fichiers ; les erreurs de lecture sont ignorées une à une."""
    try:
        if chemin.is_symlink():
            return 0, 0
        if chemin.is_file():
            return chemin.stat().st_size, 1
    except OSError:
        return 0, 0
    total = nombre = 0
    pile = [chemin]
    while pile:
        dossier = pile.pop()
        try:
            entrees = list(os.scandir(dossier))
        except OSError:
            continue
        for e in entrees:
            try:
                if e.is_symlink() or (hasattr(e, "is_junction") and e.is_junction()):
                    continue
                if e.is_dir(follow_symlinks=False):
                    if e.name not in exclus:
                        pile.append(Path(e.path))
                elif e.is_file(follow_symlinks=False):
                    total += e.stat(follow_symlinks=False).st_size
                    nombre += 1
            except OSError:
                continue
    return total, nombre


# ---------------------------------------------------------------------------
# Reconnaissance
# ---------------------------------------------------------------------------

def _groupe_de(nom: str, dossier: bool) -> str:
    for cle, motifs in _GROUPES.items():
        for motif in motifs:
            if fnmatch.fnmatchcase(nom, motif) or fnmatch.fnmatchcase(nom.lower(), motif.lower()):
                return cle
    if migration.est_a_nous(nom, dossier):
        return "reglages" if not dossier else "mesures"
    return ""


def depots_connus() -> set[str]:
    """Dépôts de modèles que Scribouille sait télécharger (catalogue, OpenVINO, campagne)."""
    from . import moteur, presets

    depots = set(moteur._DEPOTS_CONNUS.values()) | set(presets.DEPOTS_OPENVINO.values())
    for p in presets.PRESETS.values():
        depots.add(moteur.identifiant_depot(p["modele"]))
    try:
        from . import campagne

        for reglage in campagne.TOUS:
            if "/" in reglage.modele:
                depots.add(reglage.modele)
            else:
                depots.add(moteur.identifiant_depot(reglage.modele))
    except Exception:
        pass
    return {d for d in depots if d}


def _depot_du_dossier(nom: str) -> str:
    """« models--OpenVINO--whisper-large-v3-int8-ov » vers « OpenVINO/whisper-large-v3-int8-ov »."""
    if not nom.startswith("models--"):
        return ""
    return nom[len("models--"):].replace("--", "/", 1)


def _modeles_du_reglage(config: dict | None) -> set[str]:
    """Dépôts que le réglage en cours charge (le modèle du preset et son équivalent OpenVINO)."""
    from . import moteur, presets

    config = config or {}
    avance = config.get("modele_avance", "") if config.get("mode_avance") else ""
    modele = presets.modele_du_preset(config.get("preset", presets.PRESET_DEFAUT), avance)
    servis = {moteur.identifiant_depot(modele)}
    if presets.depot_openvino(modele):
        servis.add(presets.depot_openvino(modele))
    return servis


def _dans(chemin: Path, parent: Path) -> bool:
    try:
        chemin.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _ancien_dossier() -> Path | None:
    # Dossier de données imposé (SCRIBOUILLE_DONNEES) : il n'a rien repris de
    # l'ancien dossier, qui appartient à l'installation habituelle du poste.
    if chemins.DONNEES_IMPOSEES:
        return None
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        return None
    ancien = Path(base) / chemins.NOM_DOSSIER_ANCIEN
    if not ancien.is_dir():
        return None
    try:
        if ancien.resolve() == chemins.RACINE.resolve():
            return None
    except OSError:
        return None
    return ancien


def _dossier_installation() -> Path | None:
    """Dossier de la version installée (désinstalleur Inno présent), sinon None."""
    if not chemins.EST_GELE:
        return None
    if any(chemins.DOSSIER_PROGRAMME.glob("unins*.exe")):
        return chemins.DOSSIER_PROGRAMME
    return None


def desinstalleur() -> Path | None:
    dossier = _dossier_installation()
    if dossier is None:
        return None
    candidats = sorted(dossier.glob("unins*.exe"))
    return candidats[-1] if candidats else None


def _raccourcis() -> list[Path]:
    """Raccourcis posés par l'installation (menu Démarrer, bureau), s'ils existent."""
    trouves: list[Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        groupe = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Scribouille"
        if groupe.is_dir():
            trouves.append(groupe)
    bureau = Path.home() / "Desktop" / "Scribouille.lnk"
    if bureau.is_file():
        trouves.append(bureau)
    return trouves


def _cle_registre() -> list[str]:
    if sys.platform != "win32":
        return []
    chemin = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin):
            return [rf"HKCU\{chemin}"]
    except OSError:
        return []


# ---------------------------------------------------------------------------
# Inventaire
# ---------------------------------------------------------------------------

def _libeller(poste: Poste, modele: str = "") -> None:
    base = poste.cle.split(":", 1)[0]
    poste.libelle = langues.t(f"inv.{base}.libelle", modele=modele)
    poste.description = langues.t(f"inv.{base}.description" + (".libre" if base == "modele" and poste.liberable
                                                              else ""), modele=modele)


def postes(config: dict | None = None, mesurer: bool = True) -> tuple[list[Poste], list[Path]]:
    """
    Les postes de Scribouille sur ce poste, et les entrées non reconnues
    trouvées dans ses dossiers (montrées, jamais touchées).
    """
    racine = chemins.RACINE
    # Depuis les sources sans dossier imposé, données et sources se mêlent :
    # seuls les noms de données sont pris, jamais un fichier livré.
    sources = not chemins.EST_GELE and _dans(racine, chemins.DOSSIER_PROGRAMME)
    livres = {str(f.resolve()).lower() for f in chemins.MODELES_FICHIERS_EXEMPLE.values()}
    par_cle: dict[str, Poste] = {}
    inconnus: list[Path] = []

    def ajouter(cle: str, chemin: Path, liberable: bool = False) -> None:
        poste = par_cle.setdefault(cle, Poste(cle=cle, liberable=liberable))
        poste.chemins.append(chemin)

    # Programme
    if chemins.EST_GELE or (chemins.DOSSIER_PROGRAMME / "transcriber.pyw").is_file():
        ajouter("programme", chemins.DOSSIER_PROGRAMME)

    # Dossier de données : entrée par entrée. Le dossier de sortie, s'il y
    # est (dossier de données imposé), est compté à part, comme ailleurs.
    modeles = Path(chemins.DOSSIER_MODELES)
    sortie = str(Path((config or {}).get("dossier_sortie") or chemins.dossier_sortie_defaut()).resolve()).lower()
    if racine.is_dir():
        for entree in sorted(racine.iterdir()):
            dossier = entree.is_dir()
            if dossier and str(entree.resolve()).lower() == sortie:
                continue
            if sources and entree.name in ("app", "web", "lexique", "banc", "packaging", "outils", "docs") \
                    or sources and entree.name in EXCLUS_SOURCE:
                continue
            if entree.name == "modeles" and dossier:
                continue  # compté modèle par modèle plus bas
            if str(entree.resolve()).lower() in livres:
                continue  # exemple livré avec les sources (glossaire, corrections)
            groupe = _groupe_de(entree.name, dossier)
            if groupe:
                ajouter(groupe, entree, groupe in LIBERABLES)
            elif not sources:
                inconnus.append(entree)

    # Modèles : un poste par modèle. Dans le dossier par défaut, tout est à
    # nous ; dans un dossier choisi à la main, seulement les dépôts connus.
    if modeles.is_dir():
        a_nous = _dans(modeles, racine) and modeles.name == "modeles"
        connus = depots_connus()
        servis = _modeles_du_reglage(config)
        for entree in sorted(modeles.iterdir()):
            if entree.name in NOMS_HUB:
                continue
            if entree.name == "convertis" and entree.is_dir():
                for converti in sorted(entree.iterdir()):
                    if converti.is_dir():
                        cle = f"modele:convertis/{converti.name}"
                        ajouter(cle, converti, liberable=True)
                continue
            depot = _depot_du_dossier(entree.name)
            if entree.is_dir() and depot and (a_nous or depot in connus):
                ajouter(f"modele:{depot}", entree, liberable=depot not in servis)
                verrous = modeles / ".locks" / entree.name
                if verrous.is_dir():
                    par_cle[f"modele:{depot}"].chemins.append(verrous)
            elif a_nous:
                ajouter("reglages", entree)
            else:
                inconnus.append(entree)

    # Ancien dossier : seulement ce qui est à nous.
    ancien = _ancien_dossier()
    if ancien is not None:
        for entree in migration.entrees_a_nous(ancien):
            ajouter("ancien_dossier", entree)

    # Version installée : raccourcis et clé de désinstallation.
    if _dossier_installation() is not None:
        installation = Poste(cle="installation", chemins=_raccourcis(), registre=_cle_registre())
        par_cle["installation"] = installation

    resultat: list[Poste] = []
    for poste in par_cle.values():
        if poste.cle.startswith("modele:"):
            _libeller(poste, poste.cle.split(":", 1)[1])
        else:
            _libeller(poste)
        if mesurer:
            exclus = EXCLUS_SOURCE if poste.cle == "programme" else ()
            for chemin in poste.chemins:
                if poste.cle == "programme" and sources:
                    octets, nombre = _taille_sources(chemin)
                else:
                    octets, nombre = taille(chemin, exclus)
                poste.octets += octets
                poste.nombre += nombre
        resultat.append(poste)
    resultat.sort(key=lambda p: (ORDRE.index(p.cle.split(":", 1)[0]) if p.cle.split(":", 1)[0] in ORDRE else 99,
                                 -p.octets, p.cle))
    return resultat, inconnus


def _taille_sources(racine: Path) -> tuple[int, int]:
    """Les sources seules : sans environnement Python, ni données, ni modèles."""
    total = nombre = 0
    for entree in racine.iterdir():
        if entree.name in EXCLUS_SOURCE or _groupe_de(entree.name, entree.is_dir()) or entree.name == "modeles":
            continue
        octets, n = taille(entree, EXCLUS_SOURCE)
        total += octets
        nombre += n
    return total, nombre


def transcriptions(config: dict | None = None) -> dict:
    """
    Transcriptions produites par Scribouille dans le dossier de sortie : un
    groupe de fichiers de même nom dont le compagnon `.json` est à nous, ou dont
    le `.txt` porte l'en-tête de Scribouille. Rien d'autre n'est compté.
    """
    from . import compagnon

    config = config or {}
    dossier = Path(config.get("dossier_sortie") or chemins.dossier_sortie_defaut())
    fichiers: list[Path] = []
    if dossier.is_dir():
        groupes: dict[str, list[Path]] = {}
        for f in dossier.iterdir():
            if f.is_file() and f.suffix.lower() in EXTENSIONS_SORTIES:
                groupes.setdefault(f.stem.lower(), []).append(f)
        for membres in groupes.values():
            if any(_est_transcription(f, compagnon) for f in membres):
                fichiers += membres
    octets = sum(f.stat().st_size for f in fichiers if f.exists())
    return {"dossier": str(dossier), "octets": octets, "nombre": len(fichiers),
            "fichiers": [str(f) for f in fichiers]}


def _est_transcription(fichier: Path, compagnon) -> bool:
    try:
        if fichier.suffix.lower() == ".json":
            import json

            donnees = json.loads(fichier.read_text(encoding="utf-8"))
            return isinstance(donnees, dict) and donnees.get("format") in compagnon.FORMATS_LUS
        if fichier.suffix.lower() == ".txt":
            with fichier.open(encoding="utf-8", errors="replace") as flux:
                tete = "".join(flux.readline() for _ in range(25))
            if not tete.startswith("=" * 68):
                return False
            # En-tête court (3.0) : titre « Transcription : » ; avant, la
            # mention « Produit localement » fermait un en-tête de dix lignes.
            lignes = tete.splitlines()
            titre = lignes[1] if len(lignes) > 1 else ""
            return titre.startswith(("Transcription : ", "Transcript: ")) or any(
                m in tete for m in ("Produit localement", "Produced locally"))
    except (OSError, ValueError):
        return False
    return False


def inventaire(config: dict | None = None) -> dict:
    """Le contrat `espace_inventaire()` : postes, total, transcriptions à part."""
    liste, inconnus = postes(config)
    trans = transcriptions(config)
    total = sum(p.octets for p in liste)
    return {
        "postes": [p.en_dict() for p in liste],
        "total_octets": total,
        "total": langues.octets(total),
        "liberable_octets": sum(p.octets for p in liste if p.liberable),
        "transcriptions_octets": trans["octets"],
        "transcriptions": {k: v for k, v in trans.items() if k != "fichiers"},
        "non_reconnus": [str(c) for c in inconnus],
        "donnees": str(chemins.RACINE),
        "modeles": str(chemins.DOSSIER_MODELES),
        "installee": _dossier_installation() is not None,
    }


# ---------------------------------------------------------------------------
# Suppression : jamais hors des dossiers de Scribouille
# ---------------------------------------------------------------------------

def _racines_permises(config: dict | None) -> list[Path]:
    racines = [chemins.RACINE, Path(chemins.DOSSIER_MODELES)]
    ancien = _ancien_dossier()
    if ancien is not None:
        racines.append(ancien)
    appdata = os.environ.get("APPDATA")
    if appdata:
        racines.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Scribouille")
    racines.append(Path.home() / "Desktop" / "Scribouille.lnk")
    if config is not None:
        racines.append(Path(config.get("dossier_sortie") or chemins.dossier_sortie_defaut()))
    return racines


def _supprimer(chemin: Path, permises: list[Path]) -> tuple[int, str]:
    """Supprime un fichier ou un dossier de Scribouille ; renvoie (octets, erreur)."""
    if not any(_dans(chemin, r) or chemin == r for r in permises):
        return 0, f"{chemin} : hors des dossiers de Scribouille, laissé"
    if chemin.anchor and chemin.resolve() == Path(chemin.anchor):
        return 0, f"{chemin} : racine d'un disque, laissée"
    octets, _ = taille(chemin)
    erreurs: list[str] = []

    def surmonter(fonction, cible, _infos) -> None:
        try:
            os.chmod(cible, 0o700)
            fonction(cible)
        except OSError as exc:
            erreurs.append(f"{cible} : {exc.strerror or exc}")

    try:
        if chemin.is_symlink() or chemin.is_file():
            chemin.unlink()
        elif chemin.is_dir():
            shutil.rmtree(chemin, onerror=surmonter)
        else:
            return 0, ""
    except OSError as exc:
        erreurs.append(f"{chemin} : {exc.strerror or exc}")
    reste, _ = taille(chemin) if chemin.exists() else (0, 0)
    return max(0, octets - reste), "; ".join(erreurs[:3])


def liberer(cles: list[str], config: dict | None = None) -> dict:
    """Supprime les postes demandés (sauf programme et installation). Renvoie le bilan."""
    liste, _ = postes(config, mesurer=False)
    par_cle = {p.cle: p for p in liste}
    permises = _racines_permises(None)
    bilan = {"liberes": [], "octets": 0, "restes": [], "inconnus": []}
    for cle in cles:
        if cle in ("programme", "installation"):
            bilan["restes"].append(f"{cle} : retiré par le désinstalleur, pas ici")
            continue
        poste = par_cle.get(cle)
        if poste is None:
            bilan["inconnus"].append(cle)
            continue
        octets = 0
        for chemin in _a_liberer(poste):
            liberes, erreur = _supprimer(chemin, permises)
            octets += liberes
            if erreur:
                bilan["restes"].append(erreur)
        bilan["liberes"].append({"cle": cle, "octets": octets})
        bilan["octets"] += octets
    _ranger_dossiers_vides()
    return bilan


def _a_liberer(poste: Poste) -> list[Path]:
    """
    Ce que « libérer » supprime d'un poste. Les journaux : tous sauf celui de
    la session en cours, que ce processus tient ouvert (le supprimer échouait
    et l'écran annonçait un élément « non supprimé »).
    """
    if poste.cle != "journaux":
        return list(poste.chemins)
    from . import journal

    try:
        courant = journal.fichier().resolve()
    except Exception:
        courant = None
    fichiers: list[Path] = []
    for dossier in poste.chemins:
        if dossier.is_dir():
            fichiers += [f for f in dossier.iterdir() if courant is None or f.resolve() != courant]
        else:
            fichiers.append(dossier)
    return fichiers


def _ranger_dossiers_vides(complet: bool = False) -> None:
    """
    Un dossier de modèles vidé de nos modèles part s'il ne reste que les
    fichiers du hub : toujours pour un dossier choisi à la main, et aussi pour
    celui des données lors d'un effacement complet.
    """
    modeles = Path(chemins.DOSSIER_MODELES)
    if not modeles.is_dir():
        return
    try:
        restes = [e for e in modeles.iterdir() if e.name not in NOMS_HUB]
        if restes:
            return
        verrous = modeles / ".locks"
        if verrous.is_dir() and any(verrous.iterdir()):
            return
        for nom in NOMS_HUB:
            cible = modeles / nom
            if cible.is_dir():
                cible.rmdir()
            elif cible.exists():
                cible.unlink()
        if complet or not _dans(modeles, chemins.RACINE):
            modeles.rmdir()
    except OSError:
        pass


_APERCUS: dict[str, dict] = {}


def apercu_effacement(garder_transcriptions: bool = True, config: dict | None = None,
                      avec_programme: bool = True) -> dict:
    """
    Ce que l'effacement complet supprimerait, avec les tailles, et un jeton à
    rendre à `executer_effacement`. Rien n'est supprimé ici.
    """
    liste, inconnus = postes(config)
    retenus = [p for p in liste if avec_programme or p.cle not in ("programme", "installation")]
    trans = transcriptions(config)
    total = sum(p.octets for p in retenus)
    if not garder_transcriptions:
        total += trans["octets"]
    empreinte = hashlib.sha256(repr((sorted(str(c) for p in retenus for c in p.chemins),
                                     garder_transcriptions, time.time(), os.getpid())).encode()).hexdigest()[:24]
    _APERCUS[empreinte] = {"postes": retenus, "transcriptions": [] if garder_transcriptions else trans["fichiers"],
                           "date": time.time(), "config": dict(config or {}), "programme": avec_programme}
    desinst = desinstalleur()
    return {
        "jeton": empreinte,
        "postes": [p.en_dict() for p in retenus],
        "total_octets": total,
        "total": langues.octets(total),
        "garder_transcriptions": bool(garder_transcriptions),
        "transcriptions_octets": trans["octets"],
        "transcriptions": {k: v for k, v in trans.items() if k != "fichiers"},
        "non_reconnus": [str(c) for c in inconnus],
        "desinstalleur": str(desinst) if (desinst and avec_programme) else "",
        "valide_s": VALIDITE_APERCU_S,
    }


def executer_effacement(jeton: str) -> dict:
    """
    Efface exactement ce que l'aperçu `jeton` a montré. Le programme et
    l'installation (raccourcis, registre) sont laissés au désinstalleur, dont
    le chemin est rendu : l'appelant le lance une fois sorti.
    """
    apercu = _APERCUS.pop(str(jeton or ""), None)
    if apercu is None or time.time() - apercu["date"] > VALIDITE_APERCU_S:
        return {"ok": False, "message": langues.t("inv.apercu_perime")}
    config = apercu["config"]
    permises = _racines_permises(config if apercu["transcriptions"] else None)
    bilan = {"ok": True, "liberes": [], "octets": 0, "restes": []}
    for poste in apercu["postes"]:
        if poste.cle in ("programme", "installation"):
            continue
        octets = 0
        for chemin in poste.chemins:
            liberes, erreur = _supprimer(chemin, permises)
            octets += liberes
            if erreur:
                bilan["restes"].append(erreur)
        bilan["liberes"].append({"cle": poste.cle, "octets": octets})
        bilan["octets"] += octets
    if apercu["transcriptions"]:
        octets = 0
        for fichier in apercu["transcriptions"]:
            liberes, erreur = _supprimer(Path(fichier), permises)
            octets += liberes
            if erreur:
                bilan["restes"].append(erreur)
        bilan["liberes"].append({"cle": "transcriptions", "octets": octets})
        bilan["octets"] += octets
        sortie = Path(config.get("dossier_sortie") or chemins.dossier_sortie_defaut())
        try:
            sortie.rmdir()  # seulement s'il est vide
        except OSError:
            pass
    _ranger_dossiers_vides(complet=True)
    for dossier in (chemins.RACINE, _ancien_dossier()):
        if dossier is None or _dans(dossier, chemins.DOSSIER_PROGRAMME):
            continue  # depuis les sources, les données vivent dans le dépôt
        try:
            dossier.rmdir()  # seulement s'il est vide : ce qui n'est pas à nous y reste
        except OSError:
            pass
    desinst = desinstalleur()
    bilan["desinstalleur"] = str(desinst) if (desinst and apercu["programme"]) else ""
    bilan["restes"] = bilan["restes"][:50]
    return bilan


def nettoyer_apres(pid: int, desinstalleur_chemin: str = "") -> bool:
    """
    Une fois le processus `pid` terminé (la fenêtre, qui tenait encore son
    journal et son profil d'affichage ouverts), refait un effacement complet
    par la ligne de commande pour ces restes, puis lance le désinstalleur en
    silence s'il y en a un (programme, raccourcis, clé de registre). Le
    lanceur est détaché : il survit à la fermeture de Scribouille.
    """
    if sys.platform != "win32":
        return False
    import subprocess

    console = chemins.executable_console()
    if console is not None:
        ligne = f'"{console}"'
    else:
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        ligne = f'"{python}" "{chemins.DOSSIER_PROGRAMME / "transcriber.pyw"}"'
    etapes = [f"{ligne} effacer --complet --garder-programme --oui"]
    if desinstalleur_chemin and Path(desinstalleur_chemin).is_file():
        etapes.append(f'"{desinstalleur_chemin}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART')
    # Attente de la fin du PID (au plus une minute), puis les étapes dans l'ordre.
    commande = (f'cmd /d /c "for /l %i in (1,1,60) do @(tasklist /fi "PID eq {int(pid)}" 2>nul | '
                f'find "{int(pid)}" >nul && ping -n 2 127.0.0.1 >nul) & ' + " & ".join(etapes) + '"')
    try:
        # Nouveau groupe, sans fenêtre, hors de l'objet de travail : il survit à Scribouille.
        subprocess.Popen(commande, creationflags=0x00000200 | 0x08000000, close_fds=True)
        return True
    except OSError:
        return False
