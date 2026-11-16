"""
Emplacements de fichiers de l'application. Aucun chemin personnel en dur.

Deux modes de fonctionnement, volontairement distincts :

  - exécution depuis les sources (double-clic sur transcriber.pyw, lancer.bat) :
    tout vit à côté du script, comme avant. Le dossier est celui de l'utilisateur
    qui a cloné le dépôt, il est donc accessible en écriture.

  - exécution de la version installée ou portable (exe gelé par PyInstaller) :
    le programme est posé dans un dossier qu'il ne faut pas polluer, et qui
    peut être en lecture seule. La configuration, les journaux et les modèles
    vont alors dans l'espace utilisateur, sous %LOCALAPPDATA%\\Scribouille
    (%LOCALAPPDATA%\\WhiScribe jusqu'à la 2.4, repris au premier lancement,
    voir `app/migration.py`).

Le dossier des modèles se choisit à part : ils pèsent de 1,6 à 3,1 Go et l'on
veut pouvoir les ranger sur un autre disque. Il est donc noté dans un fichier
d'une seule ligne, écrit aussi bien par le programme d'installation que par
l'application, et relu par le désinstallateur pour savoir quoi proposer
d'effacer. Trois sources, dans cet ordre :

  1. « dossier-modeles.txt » dans les données de l'utilisateur ;
  2. « emplacement-modeles.txt » à côté du programme, posé par l'installation ;
  3. le dossier « modeles » sous la racine de données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

#: Nom du dossier de données, sous %LOCALAPPDATA%. Jusqu'à la 2.4, il portait
#: l'ancien nom de l'application, « WhiScribe », que partage un projet tiers
#: homonyme (ses modèles vont dans le même dossier sous Windows). Depuis la 3.0,
#: le dossier est à notre nom ; ce que Scribouille reconnaît comme sien dans
#: l'ancien y est déplacé au premier lancement, sans rien perdre ni
#: retélécharger (`app/migration.py`). Le programme d'installation lit les
#: mêmes chemins (packaging/setup.iss) ; son identifiant Inno ne bouge pas.
NOM_DOSSIER_UTILISATEUR = "Scribouille"
NOM_DOSSIER_ANCIEN = "WhiScribe"

#: Bilan de la reprise de l'ancien dossier, au démarrage (journalisé ensuite).
MIGRATION: dict = {}

#: Écrit par le programme d'installation, à côté de l'exécutable.
NOM_FICHIER_AMORCAGE = "emplacement-modeles.txt"

#: Écrit par l'application et par le programme d'installation, dans les données
#: de l'utilisateur. C'est lui qui fait foi, et c'est lui que lit le désinstallateur.
NOM_FICHIER_CHOIX_MODELES = "dossier-modeles.txt"

#: Vrai quand l'application tourne depuis l'exécutable produit par PyInstaller.
EST_GELE = bool(getattr(sys, "frozen", False))

#: Exécutable console de la version gelée : la ligne de commande, le moteur et
#: les travailleurs de fond. Windows le préfère à « Scribouille.exe » quand on
#: tape « scribouille » (le .com passe avant le .exe). Avant la 3.0, il
#: s'appelait « scribouille-verifier.exe » : ce nom est encore cherché.
NOM_EXE_CONSOLE = "scribouille.com"
ANCIEN_EXE_CONSOLE = "scribouille-verifier.exe"


def _dossier_ressources() -> Path:
    """Dossier des fichiers livrés avec le programme, jamais écrit par l'application."""
    if EST_GELE:
        # onedir : PyInstaller expose ses ressources via _MEIPASS (le sous-dossier
        # « _internal » à côté de l'exécutable).
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _dossier_programme() -> Path:
    """Dossier d'installation (celui de l'exécutable), ou la racine des sources."""
    if EST_GELE:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


#: Identifiant Inno de l'installation (packaging/setup.iss, AppId). Il n'a
#: jamais changé depuis la 2.x : la même clé de désinstallation porte la 2.x
#: ou la 3.x, selon `DisplayVersion`.
APP_ID = "{4E1B7C86-8F2A-4B5D-9C31-6D0A4F7E2B93}"
CLE_DESINSTALLATION = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}_is1"

#: Vérifications seulement : clés de désinstallation simulées (JSON), à la
#: place du vrai registre, voir `_cles_desinstallation`. Prise en compte
#: seulement quand LOCALAPPDATA est détourné vers un dossier d'essai : une
#: variable posée par erreur ne peut jamais lever la protection d'une vraie
#: 2.x sur le vrai dossier de données.
VARIABLE_ESSAI_REGISTRE = "SCRIBOUILLE_ESSAI_REGISTRE"


def _localappdata_reel() -> str:
    """
    Le vrai %LOCALAPPDATA% de la session, sans rien tirer de l'environnement
    du processus (qu'un essai détourne, `USERPROFILE` compris) : la valeur que
    l'Explorateur tient dans le registre (`Shell Folders`), sinon le dossier
    du profil donné par le jeton de la session, plus `AppData\\Local`.
    Vide si rien ne se lit (la simulation du registre n'est alors jamais lue).
    """
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as cle:
            valeur = str(winreg.QueryValueEx(cle, "Local AppData")[0] or "")
        if valeur and "%" not in valeur:
            return valeur
    except OSError:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32")
        userenv = ctypes.WinDLL("userenv")
        kernel32 = ctypes.WinDLL("kernel32")
        jeton = wintypes.HANDLE()
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(jeton)):
            return ""
        try:
            taille = wintypes.DWORD(1024)
            tampon = ctypes.create_unicode_buffer(1024)
            if not userenv.GetUserProfileDirectoryW(jeton, tampon, ctypes.byref(taille)):
                return ""
            return str(Path(tampon.value) / "AppData" / "Local") if tampon.value else ""
        finally:
            kernel32.CloseHandle(jeton)
    except Exception:
        return ""


def _essai_registre_permis() -> bool:
    """LOCALAPPDATA détourné vers un dossier d'essai (vérifications) : la simulation du registre est lue."""
    base = os.environ.get("LOCALAPPDATA", "")
    reel = _localappdata_reel()
    if not base or not reel:
        return False
    if os.path.normcase(os.path.abspath(base)).rstrip("\\/") == os.path.normcase(os.path.abspath(reel)).rstrip("\\/"):
        return False
    # Un autre nom du même dossier (nom court 8.3, jonction, lecteur `subst`)
    # n'est pas un dossier d'essai ; dans le doute (erreur), non plus.
    try:
        return not os.path.samefile(base, reel)
    except FileNotFoundError:
        return not Path(base).exists()
    except OSError:
        return False


def _cles_desinstallation() -> list[dict]:
    """
    Les clés de désinstallation Inno de Scribouille (HKCU et HKLM, vues 64 et
    32 bits), en lecture seule. Chaque élément : {ruche, version, dossier}, ou
    {ruche, erreur} si la lecture a échoué (autre chose qu'une clé absente).
    """
    essai = os.environ.get(VARIABLE_ESSAI_REGISTRE, "").strip()
    if essai and _essai_registre_permis():
        import json

        if essai.lower() == "erreur":
            return [{"ruche": "essai", "erreur": "lecture simulée en échec"}]
        try:
            donnees = json.loads(essai)
        except ValueError:
            return [{"ruche": "essai", "erreur": "simulation illisible"}]
        return [dict(c) for c in (donnees if isinstance(donnees, list) else [donnees]) if isinstance(c, dict)]
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    trouvees: list[dict] = []
    vues = []
    for ruche, nom in ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")):
        for vue in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            vues.append((ruche, nom, vue))
    vus: set[tuple[str, str]] = set()
    for ruche, nom, vue in vues:
        try:
            cle = winreg.OpenKey(ruche, CLE_DESINSTALLATION, 0, winreg.KEY_READ | vue)
        except FileNotFoundError:
            continue
        except OSError as exc:
            trouvees.append({"ruche": nom, "erreur": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        with cle:
            valeurs = {}
            for valeur in ("DisplayVersion", "InstallLocation", "Inno Setup: App Path"):
                try:
                    valeurs[valeur] = str(winreg.QueryValueEx(cle, valeur)[0] or "")
                except FileNotFoundError:
                    valeurs[valeur] = ""
                except OSError as exc:
                    valeurs[valeur] = ""
                    valeurs.setdefault("erreur", f"{valeur} : {exc}"[:200])
        dossier = valeurs.get("InstallLocation") or valeurs.get("Inno Setup: App Path") or ""
        empreinte = (valeurs.get("DisplayVersion", ""), dossier.lower().rstrip("\\/"))
        if empreinte in vus:
            continue  # même clé vue sous deux vues (HKCU n'est pas redirigée)
        vus.add(empreinte)
        entree = {"ruche": nom, "version": valeurs.get("DisplayVersion", ""), "dossier": dossier}
        if valeurs.get("erreur"):
            entree["erreur"] = valeurs["erreur"]
        trouvees.append(entree)
    return trouvees


def _majeure(version: str) -> int | None:
    try:
        return int(str(version or "").strip().split(".", 1)[0])
    except ValueError:
        return None


def etat_version_2x() -> dict:
    """
    Une WhiScribe 2.x est-elle installée sur ce poste ? Deux indices, l'un
    suffit : la clé de désinstallation Inno (HKCU ou HKLM) dont la version
    est une 2.x, où qu'elle ait été installée ; « WhiScribe.exe » sans
    « Scribouille.exe » à côté dans `Programs\\WhiScribe`. Une 3.x installée
    par-dessus réécrit la même clé (même identifiant) avec sa version.

    Une lecture du registre en échec, ou une clé dont la version ne se lit
    pas, vaut présence (`sure` faux) : dans le doute, rien n'est déplacé ni
    effacé. Rend {presente, sure, exe, par, version, detail}.
    """
    for entree in _cles_desinstallation():
        if entree.get("erreur") and not entree.get("version"):
            return {"presente": True, "sure": False, "exe": None, "par": "registre_illisible",
                    "version": "", "detail": f"{entree.get('ruche')} : {entree.get('erreur')}"}
        majeure = _majeure(entree.get("version", ""))
        if majeure is None:
            return {"presente": True, "sure": False, "exe": None, "par": "registre_version_illisible",
                    "version": str(entree.get("version") or ""), "detail": str(entree.get("ruche") or "")}
        if majeure < 3:
            dossier = str(entree.get("dossier") or "")
            exe = Path(dossier) / f"{NOM_DOSSIER_ANCIEN}.exe" if dossier else None
            return {"presente": True, "sure": True, "exe": exe, "par": "registre",
                    "version": str(entree.get("version")), "detail": str(entree.get("ruche") or "")}
    base = os.environ.get("LOCALAPPDATA")
    if base:
        dossier = Path(base) / "Programs" / NOM_DOSSIER_ANCIEN
        exe = dossier / f"{NOM_DOSSIER_ANCIEN}.exe"
        try:
            if exe.is_file() and not (dossier / f"{NOM_DOSSIER_UTILISATEUR}.exe").is_file():
                return {"presente": True, "sure": True, "exe": exe, "par": "dossier", "version": "",
                        "detail": str(dossier)}
        except OSError as exc:
            return {"presente": True, "sure": False, "exe": exe, "par": "dossier_illisible", "version": "",
                    "detail": str(exc)[:200]}
    return {"presente": False, "sure": True, "exe": None, "par": "", "version": "", "detail": ""}


#: Dernière WhiScribe publiée sans moteur OpenVINO. Vérifié dans l'historique
#: du dépôt : aucun commit ancêtre de v2.3.3 n'écrit `cache-openvino`,
#: `extensions-openvino`, `calibration.json`, le témoin de chargement, ni
#: `config.json.tmp` (ils arrivent avec la 2.4.0, qui s'appelle Scribouille).
DERNIERE_2X_SANS_OPENVINO = (2, 3, 3)


def _triplet(version: str) -> tuple[int, int, int] | None:
    morceaux = str(version or "").strip().split(".")
    try:
        nombres = [int(m) for m in morceaux[:3]]
    except ValueError:
        return None
    if not nombres or len(morceaux) > 3:
        return None
    return tuple(nombres + [0] * (3 - len(nombres)))  # type: ignore[return-value]


def version_2x_sans_openvino(etat: dict | None = None) -> bool:
    """
    La 2.x détectée est-elle SÛREMENT antérieure à la 2.4 (donc sans moteur
    OpenVINO, sans cache de compilation ni mesures de durée) ? Oui seulement
    si sa clé de désinstallation se lit, donne une version de 2.0 à 2.3.3, et
    que son dossier d'installation n'a pas de `Scribouille.exe` (nom de la
    2.4). Détection par le dossier seul, version illisible, registre en échec,
    2.4 ou plus : non (dans le doute, ses fichiers sont tenus pour les siens).
    """
    etat = etat_version_2x() if etat is None else etat
    if not etat.get("presente") or not etat.get("sure") or etat.get("par") != "registre":
        return False
    triplet = _triplet(etat.get("version", ""))
    if triplet is None or triplet[0] != 2 or triplet > DERNIERE_2X_SANS_OPENVINO:
        return False
    exe = etat.get("exe")
    if exe:
        try:
            if (Path(exe).parent / f"{NOM_DOSSIER_UTILISATEUR}.exe").exists():
                return False
        except OSError:
            return False
    return True


def ancienne_version_installee() -> Path | None:
    """
    L'exécutable d'une version 2.x installée (WhiScribe), encore là, ou None
    (voir `etat_version_2x`). Détection incertaine : l'emplacement habituel,
    même s'il n'y est pas, pour que tout se comporte comme si elle était là.
    """
    etat = etat_version_2x()
    if not etat["presente"]:
        return None
    if etat.get("exe"):
        return Path(etat["exe"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / NOM_DOSSIER_ANCIEN / f"{NOM_DOSSIER_ANCIEN}.exe"


#: Commandes de lecture : elles n'écrivent RIEN, ni réglages, ni journal, ni
#: témoin, ni reprise de l'ancien dossier (`commande_de_lecture`).
LECTURES = ("version", "aide", "diagnostic", "verifier", "lire", "espace")


def commande_de_lecture(arguments: list[str] | None = None) -> bool:
    """
    Ces arguments sont-ils une commande qui ne fait que lire ? `version`,
    `aide`, `diagnostic`, `verifier` (et `--verifier`), `lire`, `espace`,
    `etat` sans `--nettoyer`, `agent afficher`, `reglages liste|lire`,
    `vocabulaire etat`, `materiel` sans `--appliquer` ni `--lever`, toute
    demande d'aide. (`diagnostic --materiel` et `materiel detecter` relancent
    la détection : le cache du matériel n'est réécrit que s'il a changé.)
    """
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    reste = [a for a in arguments if a != "--json"]
    if "--verifier" in reste or Path(sys.argv[0] if sys.argv else "").stem.lower().endswith("verifier"):
        return True
    if not reste:
        return False
    if any(a in ("-h", "--help", "--aide", "--version") for a in reste):
        return True
    positionnels = [a for a in reste if not a.startswith("-")]
    if not positionnels or positionnels[0] != reste[0]:
        return False
    commande, action = positionnels[0], (positionnels[1] if len(positionnels) > 1 else "")
    if commande in LECTURES:
        return True
    if commande == "etat":
        return "--nettoyer" not in reste
    if commande == "agent":
        return action in ("", "afficher")
    if commande == "reglages":
        return action in ("", "liste", "lire")
    if commande == "vocabulaire":
        return action in ("", "etat")
    if commande == "materiel":
        return "--appliquer" not in reste and "--lever" not in reste
    return False


#: Ce processus ne fait que lire (voir `commande_de_lecture`).
LECTURE_SEULE = commande_de_lecture()


def _nouveau_deja_en_service(nouveau: Path) -> bool:
    """
    Le dossier à notre nom a-t-il déjà nos données (réglages, une reprise de
    l'ancien commencée, ou tout autre fichier que nous y écrivons : reprises,
    vocabulaire, journaux...) ? Illisible : oui, on y reste.
    """
    try:
        if (nouveau / "config.json").exists() or (nouveau / "migration-whiscribe.json").exists():
            return True
        if not nouveau.is_dir():
            return False
        from . import migration

        return bool(migration.entrees_a_nous(nouveau))
    except OSError:
        return True


def _garder_ancien_dossier(ancien: Path, nouveau: Path) -> bool:
    """
    Une version 2.x installée lit encore l'ancien dossier : le déplacer la
    priverait de ses réglages et de ses modèles (plusieurs gigaoctets à
    retélécharger). Tant qu'elle est là, la 3.x travaille dans l'ancien
    dossier, partagé, sauf si le dossier à notre nom sert déjà (une 3.0
    antérieure l'a créé) : elle y reste, et l'ancien n'est plus touché.
    Rien n'est déplacé tant qu'une 2.x est (ou semble) installée
    (`etat_version_2x`) ; la reprise se fera au premier lancement qui suivra
    sa désinstallation ou sa mise à jour.
    """
    if ancienne_version_installee() is None:
        return False
    if _nouveau_deja_en_service(nouveau):
        return False
    try:
        return ancien.is_dir()
    except OSError:
        return True


def _dossier_donnees() -> Path:
    """
    Racine où l'application écrit : à côté des sources, ou dans l'espace
    utilisateur. Dans la version gelée, l'ancien dossier « WhiScribe » est
    repris ici, avant que quoi que ce soit ne lise ses fichiers, sauf s'il
    sert encore à une version 2.x installée (`_garder_ancien_dossier`).
    """
    # Dossier imposé (mesures, essais côte à côte d'une autre version) : pris
    # tel quel, sans reprise de l'ancien dossier.
    impose = os.environ.get("SCRIBOUILLE_DONNEES", "").strip()
    if impose:
        # Rendu absolu : le moteur et les travailleurs, lancés depuis le
        # dossier du programme, doivent désigner le même dossier.
        return Path(os.path.abspath(Path(impose).expanduser()))
    if not EST_GELE:
        return Path(__file__).resolve().parent.parent
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        return Path.home() / f".{NOM_DOSSIER_UTILISATEUR.lower()}"
    nouveau = Path(base) / NOM_DOSSIER_UTILISATEUR
    ancien = Path(base) / NOM_DOSSIER_ANCIEN
    if "--revenir-whiscribe" not in sys.argv:
        installee = etat_version_2x()
        if installee["presente"]:
            # Une 2.x installée (ou une détection incertaine) : jamais de
            # reprise de l'ancien dossier, jamais de déplacement.
            MIGRATION.update({"ancienne": str(ancienne_version_installee()), "detection": installee["par"],
                              "sure": installee["sure"]})
            if _garder_ancien_dossier(ancien, nouveau):
                MIGRATION["etat"] = "partage"
                return ancien
            MIGRATION["etat"] = "bloquee"
            return nouveau
    if LECTURE_SEULE:
        # Une commande de lecture ne déplace rien : l'ancien dossier, pas
        # encore repris, est lu sur place ; la reprise se fera à la
        # prochaine commande qui écrit, ou à l'ouverture de la fenêtre.
        try:
            if (ancien / "config.json").is_file() and not (nouveau / "config.json").exists() \
                    and not (nouveau / "migration-whiscribe.json").exists():
                MIGRATION.update({"etat": "differee"})
                return ancien
        except OSError:
            pass
        return nouveau
    if "--revenir-whiscribe" not in sys.argv:
        try:
            from . import migration

            MIGRATION.update(migration.migrer(Path(base) / NOM_DOSSIER_ANCIEN, nouveau, _dossier_programme()))
        except Exception as exc:  # jamais bloquant : on retentera au lancement suivant
            MIGRATION.update({"etat": "erreur", "erreur": f"{type(exc).__name__}: {exc}"[:300]})
    return nouveau


#: Dossier de données imposé par SCRIBOUILLE_DONNEES (mesures, essais d'une
#: autre version) : ni reprise de l'ancien dossier, ni effacement de celui-ci.
DONNEES_IMPOSEES = bool(os.environ.get("SCRIBOUILLE_DONNEES", "").strip())

DOSSIER_RESSOURCES = _dossier_ressources()
DOSSIER_PROGRAMME = _dossier_programme()


def donnees_partagees_ancienne_version() -> Path | None:
    """
    L'exécutable de la version 2.x installée qui lit le même dossier de
    données que nous (`%LOCALAPPDATA%\\WhiScribe`, gardé tant qu'elle est là,
    ou imposé par SCRIBOUILLE_DONNEES), sinon None. Ce qu'elle lit aussi
    (glossaire, corrections) n'est alors jamais réécrit d'office.
    """
    exe = ancienne_version_installee()
    base = os.environ.get("LOCALAPPDATA")
    if exe is None or not base:
        return None
    try:
        if str(RACINE.resolve()).lower() == str((Path(base) / NOM_DOSSIER_ANCIEN).resolve()).lower():
            return exe
    except OSError:
        pass
    return None


def phrase_dossier_donnees() -> str:
    """
    Où sont les données, et pourquoi là, en une phrase : ce que `diagnostic`
    et `verifier` montrent, et ce que le journal garde (`journaliser_dossier_donnees`).
    """
    etat = MIGRATION.get("etat")
    partagee = donnees_partagees_ancienne_version()
    if etat == "partage" or partagee is not None:
        return (f"Données gardées dans {RACINE} : la version installée {MIGRATION.get('ancienne') or partagee} "
                "le lit encore ; reprise après sa désinstallation ou sa mise à jour")
    if etat == "bloquee":
        doute = "" if MIGRATION.get("sure", True) else " (détection incertaine, tenue pour présente)"
        return (f"Données dans {RACINE} ; {NOM_DOSSIER_ANCIEN} laissé tel quel à la version installée "
                f"{MIGRATION.get('ancienne')}{doute} : rien n'y est repris ni effacé tant qu'elle est là")
    if etat == "differee":
        return f"Données lues sur place dans {RACINE} : reprise à la prochaine commande qui écrit"
    if etat not in (None, "rien"):
        return (f"Données reprises de {NOM_DOSSIER_ANCIEN} dans {RACINE}"
                + (f" (reprise en cours : {'; '.join(MIGRATION.get('restes') or [])})" if MIGRATION.get("restes")
                   else ""))
    if DONNEES_IMPOSEES:
        return f"Données dans {RACINE} (imposé par SCRIBOUILLE_DONNEES)"
    return f"Données dans {RACINE}"


def journaliser_dossier_donnees() -> None:
    """
    Où sont les données et pourquoi, au journal : la même ligne pour la
    fenêtre et pour la ligne de commande (dossier partagé avec une 2.x,
    reprise de l'ancien dossier, reprise différée par une commande de lecture).
    """
    from . import journal

    etat = MIGRATION.get("etat")
    if etat in ("partage", "differee", "bloquee") or donnees_partagees_ancienne_version() is not None:
        journal.info("%s", phrase_dossier_donnees())
    elif etat not in (None, "rien"):
        journal.info("Données reprises de %s : déplacées %s, doublons rangés à part %s, état %s%s",
                     NOM_DOSSIER_ANCIEN, len(MIGRATION.get("deplaces") or []), len(MIGRATION.get("conflits") or []),
                     etat, (" : " + "; ".join(MIGRATION.get("restes") or [])) if MIGRATION.get("restes") else "")
        if MIGRATION.get("erreur"):
            journal.attention("Reprise des données de %s en échec : %s", NOM_DOSSIER_ANCIEN, MIGRATION["erreur"])
    else:
        journal.info("Données dans %s", RACINE)


def mode_programme() -> str:
    """« installee » (désinstalleur présent), « portable » (dossier décompressé) ou « sources »."""
    if not EST_GELE:
        return "sources"
    return "installee" if any(DOSSIER_PROGRAMME.glob("unins*.exe")) else "portable"


def executable_console() -> Path | None:
    """L'exécutable console à côté du programme gelé, ou None (sources, ou absent)."""
    if not EST_GELE:
        return None
    for nom in (NOM_EXE_CONSOLE, ANCIEN_EXE_CONSOLE):
        candidat = DOSSIER_PROGRAMME / nom
        if candidat.is_file():
            return candidat
    return None

#: Racine des données de l'utilisateur : configuration, journaux, modèles par défaut.
RACINE = _dossier_donnees()

DOSSIER_WEB = DOSSIER_RESSOURCES / "web"
#: Dossier des journaux, celui que partagent toutes les versions (une
#: WhiScribe 2.x y écrit les siens, et y efface tout `*.log` au-delà des 30
#: derniers).
DOSSIER_LOGS_COMMUN = RACINE / "logs"
#: Journaux de Scribouille 3.x : un sous-dossier à elle, où une 2.x ne
#: regarde pas (sa purge ne descend pas dans les sous-dossiers) et le seul où
#: la 3.x efface quoi que ce soit (`journal.purger`). Les journaux posés
#: directement dans `logs\` (2.x, ou 3.0 avant ce rangement) ne sont jamais
#: effacés d'office.
DOSSIER_LOGS = DOSSIER_LOGS_COMMUN / "scribouille"

FICHIER_CONFIG = RACINE / "config.json"
FICHIER_CONFIG_EXEMPLE = DOSSIER_RESSOURCES / "config.example.json"
FICHIER_VOCABULAIRE = RACINE / "vocabulaire.txt"
FICHIER_CORRECTIONS = RACINE / "corrections.txt"
FICHIER_JETON_HF = RACINE / "jeton_hf.txt"

#: Gabarit d'instructions pour un assistant IA, créé au premier usage du bouton
#: « Copier pour l'IA ». Voir `app/gabarit.py`.
FICHIER_GABARIT_IA = RACINE / "gabarit-ia.txt"

#: Modèles d'exemple livrés avec le programme, recopiés au premier lancement.
MODELES_FICHIERS_EXEMPLE = {
    FICHIER_VOCABULAIRE: DOSSIER_RESSOURCES / "vocabulaire.txt",
    FICHIER_CORRECTIONS: DOSSIER_RESSOURCES / "corrections.txt",
}


# ---------------------------------------------------------------------------
# Dossier des modèles : configurable, parce qu'il pèse plusieurs gigaoctets
# ---------------------------------------------------------------------------

FICHIER_CHOIX_MODELES = RACINE / NOM_FICHIER_CHOIX_MODELES


def _lire_chemin(fichier: Path) -> Path | None:
    try:
        valeur = fichier.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(valeur).expanduser() if valeur else None


def dossier_modeles_defaut() -> Path:
    """Emplacement proposé quand rien n'a été choisi : « modeles » sous la racine."""
    return RACINE / "modeles"


def dossier_modeles_retenu() -> Path:
    """Applique l'ordre de priorité décrit en tête de module."""
    return (
        _lire_chemin(FICHIER_CHOIX_MODELES)
        or _lire_chemin(DOSSIER_PROGRAMME / NOM_FICHIER_AMORCAGE)
        or dossier_modeles_defaut()
    )


#: Dossier réellement utilisé pour les modèles. Réaffecté par `definir_dossier_modeles`.
DOSSIER_MODELES = dossier_modeles_retenu()


def definir_dossier_modeles(chemin: str | Path | None, memoriser: bool = False) -> Path:
    """
    Fixe le dossier des modèles. Une valeur vide rétablit l'emplacement par défaut.

    Avec `memoriser`, le choix est écrit sur disque pour les lancements suivants,
    et le désinstallateur saura où chercher les modèles à effacer.
    """
    global DOSSIER_MODELES
    texte = str(chemin or "").strip()
    DOSSIER_MODELES = Path(texte).expanduser() if texte else dossier_modeles_retenu()

    if memoriser:
        try:
            RACINE.mkdir(parents=True, exist_ok=True)
            if texte:
                FICHIER_CHOIX_MODELES.write_text(str(DOSSIER_MODELES) + "\n", encoding="utf-8")
            else:
                FICHIER_CHOIX_MODELES.unlink(missing_ok=True)
                DOSSIER_MODELES = dossier_modeles_retenu()
        except OSError:
            pass

    confiner_cache_huggingface()
    return DOSSIER_MODELES


def dossier_modeles_inscriptible(chemin: str | Path) -> str:
    """
    Vérifie qu'un dossier de modèles est utilisable. Renvoie un message d'erreur
    en français, ou une chaîne vide si tout va bien.
    """
    from . import langues

    cible = Path(str(chemin)).expanduser()
    try:
        cible.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return langues.t("chemin.dossier_non_cree", erreur=exc.strerror or exc)
    temoin = cible / ".ecriture-test"
    try:
        temoin.write_text("ok", encoding="utf-8")
        temoin.unlink(missing_ok=True)
    except OSError:
        return langues.t("chemin.dossier_non_ecrivable")
    return ""


def dossier_ecrivable(chemin: str | Path) -> str:
    """
    Le dossier (ou, s'il n'existe pas encore, son plus proche parent) permet-il
    d'y créer des fichiers ? Message d'erreur, ou chaîne vide si oui. Ne crée
    ni n'écrit rien : sous Windows, demande d'ouverture du dossier avec le
    droit de créer des fichiers et des sous-dossiers, refusée si les droits
    manquent (sert à `--verifier`, qui ne doit rien laisser derrière lui).
    """
    from . import langues

    cible = Path(str(chemin)).expanduser()
    existant = cible
    while not existant.exists():
        if existant.parent == existant:
            return langues.t("chemin.dossier_non_ecrivable")
        existant = existant.parent
    if not existant.is_dir():
        return langues.t("chemin.dossier_non_ecrivable")
    if sys.platform != "win32":
        return "" if os.access(existant, os.W_OK) else langues.t("chemin.dossier_non_ecrivable")
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    # FILE_ADD_FILE | FILE_ADD_SUBDIRECTORY ; partage complet ; OPEN_EXISTING ;
    # FILE_FLAG_BACKUP_SEMANTICS (ouvrir un dossier).
    poignee = k32.CreateFileW(str(existant), 0x2 | 0x4, 0x1 | 0x2 | 0x4, None, 3, 0x02000000, None)
    if poignee in (None, wintypes.HANDLE(-1).value, ctypes.c_void_p(-1).value):
        return langues.t("chemin.dossier_non_ecrivable")
    k32.CloseHandle(poignee)
    return ""


def constat_presence(chemin: str | Path) -> str:
    """
    « present », « absent » (le dossier qui le contient répond, le fichier
    n'y est pas) ou « injoignable » (lecteur déconnecté, clé débranchée,
    dossier parent disparu, accès refusé, erreur passagère). Seul « absent »
    autorise à tenir un fichier pour disparu ; « injoignable » peut être
    passager et ne justifie jamais un effacement.
    """
    texte = str(chemin or "").strip()
    if not texte:
        return "injoignable"
    cible = Path(texte)
    try:
        os.stat(cible)
        return "present"
    except FileNotFoundError:
        pass
    except OSError:
        return "injoignable"
    try:
        import stat as stat_module

        return "absent" if stat_module.S_ISDIR(os.stat(cible.parent).st_mode) else "injoignable"
    except OSError:
        return "injoignable"


def espace_libre_go(chemin: str | Path) -> float:
    """Espace libre en gigaoctets sur le volume du chemin, 0 si indéterminable."""
    import shutil

    cible = Path(str(chemin)).expanduser()
    for candidat in [cible, *cible.parents]:
        if candidat.exists():
            try:
                return shutil.disk_usage(str(candidat)).free / 1024 ** 3
            except OSError:
                return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Création des dossiers et amorçage des fichiers de l'utilisateur
# ---------------------------------------------------------------------------

def dossier_sortie_defaut() -> Path:
    """
    Dossier de sortie proposé au premier lancement : Documents/Transcriptions.
    Avec un dossier de données imposé (`SCRIBOUILLE_DONNEES` : essai, agent,
    poste de démonstration), « Transcriptions » DANS ce dossier : rien n'est
    écrit dans le vrai profil de l'utilisateur sans qu'on le demande.
    """
    if os.environ.get("SCRIBOUILLE_DONNEES", "").strip():
        return RACINE / NOM_SORTIES_IMPOSEES
    documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / "Transcriptions"


#: Dossier de sortie par défaut sous un dossier de données imposé.
NOM_SORTIES_IMPOSEES = "Transcriptions"


def assurer_dossiers() -> None:
    RACINE.mkdir(parents=True, exist_ok=True)
    DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
    try:
        DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Un disque externe débranché ne doit pas empêcher l'application de démarrer :
        # l'erreur sera reformulée au moment du chargement du modèle.
        pass
    confiner_cache_huggingface()
    assurer_fichiers_utilisateur()


def confiner_cache_huggingface() -> None:
    """
    Force huggingface_hub à travailler dans notre dossier de modèles.

    faster-whisper reçoit déjà `download_root`, mais certaines bibliothèques
    appellent le hub directement. Sans cela, des poids finiraient dans le cache
    partagé de l'utilisateur, et la désinstallation ne saurait plus quoi effacer.
    Un dossier, un seul, celui que l'utilisateur a choisi.
    """
    os.environ["HF_HUB_CACHE"] = str(DOSSIER_MODELES)
    os.environ.setdefault("HF_HOME", str(DOSSIER_MODELES))


def taille_dossier_go(chemin: str | Path) -> float:
    """Taille occupée par un dossier, en gigaoctets. 0 s'il n'existe pas."""
    cible = Path(str(chemin)).expanduser()
    if not cible.is_dir():
        return 0.0
    total = 0
    try:
        for fichier in cible.rglob("*"):
            try:
                if fichier.is_file():
                    total += fichier.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total / 1024 ** 3


def assurer_fichiers_utilisateur() -> None:
    """
    Recopie une fois les exemples de glossaire et de corrections dans l'espace
    utilisateur. Un fichier déjà présent n'est jamais écrasé : une mise à jour de
    l'application ne doit rien perdre.
    """
    for cible, source in MODELES_FICHIERS_EXEMPLE.items():
        if cible.exists() or cible == source:
            continue
        try:
            cible.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
