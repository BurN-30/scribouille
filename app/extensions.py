"""
Extensions installables après coup : aujourd'hui la séparation des locuteurs.

Le problème posé
----------------
La séparation des locuteurs repose sur PyTorch et pyannote.audio, soit 3,55 Go
de fichiers une fois posés, mesurés. Les embarquer dans le programme
d'installation ferait passer celui-ci de 200 Mo à plusieurs gigaoctets, pour une
fonction que tout le monde n'utilise pas. Les laisser à la seule version source
revient à demander à un utilisateur normal d'installer Python, de cloner un
dépôt et de lancer un script : ce n'est pas raisonnable.

La réponse retenue
------------------
Un bouton dans l'application, qui fait le travail dans les deux modes.

  - **Depuis les sources**, l'environnement isolé « .venv » existe déjà et il a
    son propre pip : on y installe les paquets, exactement comme le ferait
    « installer.bat --locuteurs ».

  - **Depuis la version installée**, il n'y a ni Python ni pip sur le poste.
    pip est donc embarqué dans le gel (voir `packaging/scribouille.spec`) et les
    paquets sont posés dans un **dossier d'extensions** propre à l'utilisateur,
    `%LOCALAPPDATA%\\WhiScribe\\extensions`, par « pip install --target ». Ce
    dossier est ajouté à `sys.path` au démarrage, avant tout import de torch ou
    de pyannote : les paquets s'y trouvent alors comme s'ils avaient toujours
    été là.

Points d'attention, tous appris à la construction et vérifiés sur le gel réel :

  1. **pip doit être collecté en fichiers .py sur le disque**, pas dans l'archive
     PyInstaller. `pip._vendor.distlib` cherche un « finder » de ressources et
     échoue avec le chargeur gelé, sur un « Unable to locate finder for
     'pip._vendor.distlib' ». Le mode de collecte `{"pip": "py"}` du fichier
     .spec règle cela, tout en laissant l'analyse statique ramasser les modules
     de la bibliothèque standard dont pip a besoin.

  2. **L'installation se fait dans un processus séparé.** pip n'est pas prévu
     pour être appelé plusieurs fois dans un même interpréteur, et il refusera
     bientôt qu'on importe un paquet fraîchement posé dans le processus qui
     vient de l'installer. Un processus par installation, un autre pour la
     vérification : l'application, elle, reste utilisable pendant tout le
     téléchargement, et l'annulation se réduit à terminer ce processus.

  3. **La progression vient de « pip --progress-bar raw »**, qui écrit des
     lignes « Progress 262144 of 12787999 » au lieu d'une barre à retours
     chariot. C'est lisible par un programme, et cela donne un pourcentage réel
     par paquet téléchargé.

  4. **La reprise est confiée au cache HTTP de pip**, rangé sous les données de
     l'utilisateur. Relancer après une coupure réseau ou une annulation ne
     retélécharge rien de ce qui est déjà arrivé : le réseau ne resert que pour
     ce qui manque. En revanche, les fichiers sont bel et bien reposés, parce
     que « --upgrade » est indispensable pour que « --target » accepte d'écrire
     par dessus un dossier existant. Une relance coûte donc quelques minutes de
     disque, jamais un second téléchargement. C'est le prix d'une reprise sûre :
     sans « --upgrade », pip se contenterait d'un avertissement et laisserait en
     place les fichiers tronqués de la tentative interrompue.

     Aucun nettoyage automatique n'est fait : effacer 3,5 Go parce qu'un octet
     manque serait hostile. Le bouton « Retirer » est là pour repartir de zéro
     quand on le veut vraiment.

Limite connue, dite ici plutôt que découverte plus tard
------------------------------------------------------
torchcodec, tiré par pyannote.audio, cherche au chargement les bibliothèques
partagées de FFmpeg, « avcodec-61.dll » et compagnie. Scribouille n'en pose
aucune : il embarque un exécutable FFmpeg entier, ce qui n'est pas la même
chose. torchcodec écrit donc quelques lignes d'avertissement à l'import, et ses
décodeurs restent inertes.

Sans conséquence ici : la diarisation reçoit un signal déjà décodé, sous forme
de tableau numpy passé en mémoire (voir `app/diarisation.py`), et ne demande
jamais à torchcodec d'ouvrir un fichier. Les avertissements sont bruyants, pas
graves. Il faudra y revenir le jour où pyannote se mettra à décoder lui-même.

Le dossier d'extensions ne part JAMAIS dans l'export des données personnelles
(`app/donnees.py` travaille sur une liste blanche de fichiers), et il entre dans
le périmètre de la question « supprimer vos données » de la désinstallation
(voir `packaging/setup.iss`).

Ligne de commande, utilisée par l'application et par la recette :

    Scribouille.exe --installer-locuteurs [--cible DOSSIER] [--cpu|--cuda]
                                          [--paquets a==1,b==2] [--index-url URL]
    Scribouille.exe --verifier-locuteurs  [--cible DOSSIER]
    Scribouille.exe --retirer-locuteurs   [--cible DOSSIER]

Depuis les sources, le même point d'entrée existe :

    .venv\\Scripts\\python.exe -m app.extensions --verifier-locuteurs
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable

from . import chemins

#: Dossier où atterrissent les paquets de la version installée.
DOSSIER = chemins.RACINE / "extensions"

#: Cache HTTP de pip. Séparé du dossier d'extensions pour que « Retirer » puisse
#: effacer les paquets sans jeter ce qui a été téléchargé.
DOSSIER_CACHE = chemins.RACINE / "cache-pip"

#: Marqueur écrit à la fin d'une installation réussie : il porte la variante
#: (processeur ou NVIDIA) et les versions posées, ce que l'interface affiche.
NOM_MARQUEUR = "locuteurs.txt"

TORCH = "torch==2.8.0"
TORCHAUDIO = "torchaudio==2.8.0"
PYANNOTE = "pyannote.audio==4.0.4"

#: torchcodec est une extension native compilée contre une version précise de
#: PyTorch. pyannote.audio se contente d'exiger « torchcodec>=0.7.0 », et pip
#: prend alors la dernière, bâtie pour un torch bien plus récent. La
#: bibliothèque se charge, mais l'un de ses symboles manque : « WinError 127,
#: la procédure spécifiée est introuvable ». Constaté sur une installation
#: réelle, et reproduit hors du gel : ce n'est pas un problème d'application,
#: c'est une version à figer. 0,7 est celle qui accompagne torch 2.8.
TORCHCODEC = "torchcodec==0.7.0"

INDEX_CPU = "https://download.pytorch.org/whl/cpu"
INDEX_CUDA = "https://download.pytorch.org/whl/cu124"

#: Volumes annoncés à l'utilisateur AVANT de lancer quoi que ce soit, en gigaoctets.
#:
#: Chiffres **mesurés**, pas estimés, sur une installation réelle depuis la
#: version gelée, en variante processeur : 0,71 Go de roues dans le cache et
#: 3,55 Go de fichiers posés. Le rapport surprend, mais les roues de PyTorch
#: sont très compressées et les bibliothèques natives décompressent beaucoup.
#:
#: La marge de l'espace requis n'est pas de la coquetterie : pendant
#: l'installation, une roue existe deux fois, sous forme compressée dans le
#: cache et décompressée dans le dossier cible.
#:
#: La variante CUDA n'a pas été mesurée sur ce poste, faute de carte NVIDIA :
#: les chiffres viennent de la taille publiée des roues « cu124 », qui pèsent
#: environ trois fois celles du processeur. Ils sont volontairement larges.
TELECHARGEMENT_GO = {"cpu": 0.8, "cuda": 3.0}
ESPACE_REQUIS_GO = {"cpu": 6.0, "cuda": 14.0}

#: Ce que l'extension occupe une fois posée. Sert aux textes de présentation ;
#: la taille réelle est relue dans le marqueur une fois l'installation faite.
TAILLE_ATTENDUE_GO = {"cpu": 3.6, "cuda": 9.0}

#: Modules dont la présence, et surtout l'import réel, décident que l'extension
#: est utilisable. `importlib.util.find_spec` ne suffit pas : un paquet à demi
#: téléchargé se voit, mais ne s'importe pas.
MODULES_ATTENDUS = ("torch", "pyannote.audio")

_active = False


# ---------------------------------------------------------------------------
# Chargement au démarrage
# ---------------------------------------------------------------------------

def activer(dossier: str | Path | None = None) -> bool:
    """
    Rend les paquets du dossier d'extensions importables.

    À appeler le plus tôt possible, et de toute façon avant le premier import de
    torch ou de pyannote. L'appel est idempotent et sans effet quand le dossier
    n'existe pas : c'est le cas courant, celui d'une application qui n'a jamais
    eu besoin de la séparation des locuteurs.
    """
    global _active
    cible = Path(str(dossier)) if dossier else DOSSIER
    if not cible.is_dir():
        return False

    texte = str(cible)
    if texte not in sys.path:
        # Devant : les paquets de l'extension priment sur d'éventuels homonymes.
        # Les modules déjà gelés dans l'exécutable gardent malgré tout la main,
        # PyInstaller les servant avant toute recherche de chemin.
        sys.path.insert(0, texte)
        importlib.invalidate_caches()

    _declarer_dossiers_dll(cible)
    _active = True
    return True


def _declarer_dossiers_dll(cible: Path) -> None:
    """
    Déclare à Windows les dossiers de DLL de l'extension.

    Depuis Python 3.8, un dossier de bibliothèques natives n'est plus cherché
    parce qu'il se trouve à côté du module : il faut le nommer. Une roue
    installée par pip s'attend pourtant à ce que ses DLL voisines se
    retrouvent entre elles.

    Sans cette déclaration, l'import passe mais laisse des trous. Constaté sur
    le gel réel : « Failed to load dynlib/dll libtorchcodec_image.dll », alors
    que le fichier était bien là, faute de pouvoir charger les siennes.

    Le balayage se limite au premier niveau, plus « torch/lib » qui est le gros
    morceau. C'est une poignée d'accès disque, et seulement quand l'extension
    existe.
    """
    if not hasattr(os, "add_dll_directory"):
        return

    candidats = [cible, cible / "torch" / "lib"]
    try:
        candidats += [entree for entree in cible.iterdir() if entree.is_dir()]
    except OSError:
        pass

    vus: set[str] = set()
    for dossier in candidats:
        texte = str(dossier)
        if texte in vus or not dossier.is_dir():
            continue
        vus.add(texte)
        try:
            if next(dossier.glob("*.dll"), None) is None:
                continue
            os.add_dll_directory(texte)
        except OSError:
            continue


def dossier_actif() -> Path:
    return DOSSIER


# ---------------------------------------------------------------------------
# État
# ---------------------------------------------------------------------------

def _lit_marqueur(cible: Path) -> dict:
    try:
        lignes = (cible / NOM_MARQUEUR).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    donnees = {}
    for ligne in lignes:
        if "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            donnees[cle.strip()] = valeur.strip()
    return donnees


def _ecrit_marqueur(cible: Path, variante: str, paquets: Iterable[str]) -> None:
    # La taille est mesurée ici, une seule fois, et relue ensuite. Parcourir
    # 3 Go et quelques dizaines de milliers de fichiers coûte plusieurs
    # secondes sur un disque froid : hors de question de le faire à chaque
    # ouverture de la fenêtre pour afficher un chiffre sur un bouton.
    contenu = [
        f"variante={variante}",
        "paquets=" + " ".join(paquets),
        f"taille_go={chemins.taille_dossier_go(cible):.2f}",
    ]
    try:
        cible.mkdir(parents=True, exist_ok=True)
        (cible / NOM_MARQUEUR).write_text("\n".join(contenu) + "\n", encoding="utf-8")
    except OSError:
        pass


def modules_importables(dossier: str | Path | None = None) -> tuple[bool, str]:
    """
    Importe pour de vrai les modules attendus. Renvoie (réussi, détail).

    C'est la seule vérification qui vaille : elle attrape les téléchargements
    interrompus, les DLL manquantes et les incompatibilités de version, là où un
    simple test de présence de dossier dirait que tout va bien.
    """
    activer(dossier)
    for module in MODULES_ATTENDUS:
        try:
            __import__(module)
        except Exception as exc:
            return False, f"{module} : {type(exc).__name__}: {exc}"
    # Les versions vues à l'exécution, pas celles demandées à pip. La ligne
    # « numpy » n'est pas décorative : dans la version installée, le numpy gelé
    # dans l'exécutable prime sur celui du dossier d'extensions, PyInstaller
    # servant ses modules avant toute recherche de chemin. C'est le point de
    # friction le plus probable d'une future montée de version, autant qu'il
    # soit lisible dans le bilan.
    details = []
    for module, etiquette in (("torch", "torch"), ("numpy", "numpy")):
        try:
            details.append(f"{etiquette} {__import__(module).__version__}")
        except Exception:
            pass
    return True, ", ".join(details)


def presente(dossier: str | Path | None = None) -> bool:
    """
    Test rapide, sans import : l'extension a-t-elle l'air posée ?

    Sert à l'affichage, et rien d'autre. L'import réel, seul verdict qui vaille,
    est fait dans un processus séparé, par « --verifier-locuteurs ».
    """
    if not chemins.EST_GELE:
        return all(
            importlib.util.find_spec(m.split(".")[0]) is not None for m in MODULES_ATTENDUS
        )
    cible = Path(str(dossier)) if dossier else DOSSIER
    if not cible.is_dir():
        return False
    return (cible / "torch").is_dir() and (cible / "pyannote").is_dir()


def variante_materielle() -> str:
    """
    « cuda » si le pilote NVIDIA répond, « cpu » sinon.

    On ne peut pas interroger torch pour le savoir : c'est justement ce qu'il
    s'agit d'installer. La présence de « nvidia-smi », livré avec le pilote, est
    le signal fiable, et c'est déjà celui qu'utilise `installer.py`.
    """
    if shutil.which("nvidia-smi") is None:
        return "cpu"
    try:
        sortie = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=20,
            creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
        )
        return "cuda" if sortie.returncode == 0 else "cpu"
    except Exception:
        return "cpu"


def taille_go(dossier: str | Path | None = None, mesurer: bool = False) -> float:
    """
    Taille de l'extension. Par défaut, celle notée à l'installation.

    Le parcours réel n'est fait que sur demande, ou faute de marqueur : il
    coûte plusieurs secondes sur un dossier de cette taille, et l'interface
    n'affiche qu'un ordre de grandeur sur un bouton.
    """
    cible = Path(str(dossier)) if dossier else DOSSIER
    if not mesurer:
        notee = _lit_marqueur(cible).get("taille_go", "")
        try:
            if notee and float(notee) > 0:
                return float(notee)
        except ValueError:
            pass
    return chemins.taille_dossier_go(cible)


def taille_cache_go() -> float:
    return chemins.taille_dossier_go(DOSSIER_CACHE)


def etat(dossier: str | Path | None = None) -> dict:
    """État complet, tel que l'interface l'affiche."""
    cible = Path(str(dossier)) if dossier else DOSSIER
    variante = variante_materielle()
    marqueur = _lit_marqueur(cible)
    installee = presente(cible)
    return {
        "installee": installee,
        "mode_installe": chemins.EST_GELE,
        "dossier": str(cible),
        "variante": marqueur.get("variante") or variante,
        "variante_materielle": variante,
        "paquets": marqueur.get("paquets", ""),
        # Taille relue dans le marqueur, jamais recalculée ici : cet état est
        # demandé à l'ouverture de la fenêtre. Le cache de téléchargement n'y
        # figure pas pour la même raison, il n'est chiffré qu'au retrait.
        "taille_go": round(taille_go(cible), 2) if installee else 0.0,
        "telechargement_go": TELECHARGEMENT_GO[variante],
        "espace_requis_go": ESPACE_REQUIS_GO[variante],
        "taille_attendue_go": TAILLE_ATTENDUE_GO[variante],
        "espace_libre_go": round(chemins.espace_libre_go(chemins.RACINE), 1),
    }


def espace_suffisant(variante: str | None = None) -> tuple[bool, float, float]:
    """Renvoie (assez de place, libre en Go, requis en Go)."""
    variante = variante or variante_materielle()
    libre = chemins.espace_libre_go(chemins.RACINE)
    requis = ESPACE_REQUIS_GO.get(variante, ESPACE_REQUIS_GO["cpu"])
    return libre >= requis, libre, requis


# ---------------------------------------------------------------------------
# Construction des commandes pip
# ---------------------------------------------------------------------------

#: Index public, réclamé en second quand l'index PyTorch est en premier : ce
#: dernier ne sert que les paquets de PyTorch, tout le reste vient de là.
INDEX_PYPI = "https://pypi.org/simple"


def lots(variante: str, paquets: list[str] | None = None,
         index: str = "") -> list[tuple[str, list[str], str, str]]:
    """
    Découpe l'installation en lots : (nom, paquets, index principal, index d'appoint).

    **Un seul lot, et ce n'est pas une simplification paresseuse.** Les deux
    autres découpages ont été essayés, sur de vraies installations, et écartés :

      - *PyTorch d'abord, pyannote ensuite, sans contrainte.* pyannote.audio
        demande « torch>=2.8.0 » et « torchcodec>=0.7.0 ». Laissé libre, pip va
        chercher sur PyPI les dernières versions, qui embarquent CUDA, et
        écrase la version processeur à peine posée : un gigaoctet téléchargé
        pour rien, deux « dist-info » de torch côte à côte, et un torchcodec
        compilé contre un autre PyTorch, qui refuse ensuite de se charger sur
        « WinError 127 ».

      - *La même chose en répétant les versions au second lot.* La résolution
        redevient juste, mais « --upgrade », indispensable pour que « --target »
        accepte d'écrire par dessus un dossier existant, force la repose des
        paquets nommés. PyTorch, ses trois gigaoctets, était effacé puis
        recopié une seconde fois. Plusieurs minutes de disque pour rien.

    Tout demander d'un coup laisse pip résoudre l'ensemble une fois, avec les
    versions figées, et ne copier chaque fichier qu'une fois. L'index de PyTorch
    passe en premier, PyPI en appoint pour tout le reste.

    Un lot nommé quand la recette impose une liste de paquets : cela sert à
    prouver le mécanisme sans télécharger plusieurs gigaoctets.
    """
    if paquets:
        return [("paquets", list(paquets), index, "")]
    index_torch = index or (INDEX_CUDA if variante == "cuda" else INDEX_CPU)
    return [
        ("locuteurs", [TORCH, TORCHAUDIO, TORCHCODEC, PYANNOTE], index_torch, INDEX_PYPI),
    ]


def arguments_pip(paquets: list[str], index: str, extra: str,
                  cible: Path | None) -> list[str]:
    """
    Arguments d'un « pip install », identiques dans les deux modes à la cible près.

    `--target` n'apparaît que pour la version installée : depuis les sources,
    les paquets vont dans le « .venv », là où le reste de l'application vit déjà.
    """
    arguments = [
        "install",
        "--no-input",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--progress-bar", "raw",
        "--prefer-binary",
        "--cache-dir", str(DOSSIER_CACHE),
    ]
    if cible is not None:
        # « --upgrade » avec « --target » : sans lui, pip refuse d'écrire par
        # dessus un dossier déjà présent et se contente d'un avertissement, ce
        # qui laisse une installation à moitié faite après une reprise.
        # « only-if-needed » évite en même temps de tout remonter de version
        # à chaque passage.
        arguments += ["--target", str(cible), "--upgrade", "--upgrade-strategy", "only-if-needed"]
    if index:
        arguments += ["--index-url", index]
    if extra:
        arguments += ["--extra-index-url", extra]
    return arguments + list(paquets)


# ---------------------------------------------------------------------------
# Analyse de la sortie de pip, pour une progression lisible
# ---------------------------------------------------------------------------

def analyser_ligne(ligne: str) -> dict | None:
    """
    Transforme une ligne de pip en événement, ou renvoie None si elle n'apprend rien.

    Sortie normalisée, volontairement pauvre : l'interface ne doit jamais avoir
    à comprendre pip. Types produits :

      {"type": "paquet",      "nom": "torch"}          un paquet commence
      {"type": "octets",      "recu": .., "total": ..} progression d'un téléchargement
      {"type": "pose",        "texte": "..."}          installation des roues
      {"type": "fini",        "texte": "..."}          bilan de pip
      {"type": "erreur",      "texte": "..."}          ligne d'erreur de pip
    """
    ligne = (ligne or "").rstrip()
    if not ligne:
        return None
    nu = ligne.strip()

    if nu.startswith("Progress "):
        morceaux = nu.split()
        if len(morceaux) >= 4:
            try:
                return {"type": "octets", "recu": int(morceaux[1]), "total": int(morceaux[3])}
            except ValueError:
                return None
        return None

    # « Collecting torch==2.8.0 » : une exigence, le tiret peut faire partie du
    # nom (« typing-extensions »). On ne coupe que sur un opérateur de version.
    for prefixe in ("Collecting ", "Obtaining "):
        if nu.startswith(prefixe):
            reste = nu[len(prefixe):].strip()
            nom = reste.split()[0] if reste else ""
            for coupure in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";"):
                if coupure in nom:
                    nom = nom.split(coupure)[0]
                    break
            return {"type": "paquet", "nom": nom.strip() or reste}

    # « Downloading torch-2.8.0-cp312-...whl (216.1 MB) » : un nom de fichier,
    # où le premier tiret suivi d'un chiffre ouvre le numéro de version.
    for prefixe in ("Downloading ", "Using cached "):
        if nu.startswith(prefixe):
            reste = nu[len(prefixe):].strip()
            fichier = (reste.split()[0] if reste else "").split("/")[-1]
            nom = fichier
            for position, caractere in enumerate(fichier):
                if caractere == "-" and position + 1 < len(fichier) \
                        and fichier[position + 1].isdigit():
                    nom = fichier[:position]
                    break
            return {"type": "paquet", "nom": nom.replace("_", "-") or reste}

    if nu.startswith("Installing collected packages"):
        return {"type": "pose", "texte": nu}
    if nu.startswith("Successfully installed"):
        return {"type": "fini", "texte": nu}
    if nu.startswith("ERROR") or nu.startswith("error:"):
        return {"type": "erreur", "texte": nu}
    return None


# ---------------------------------------------------------------------------
# Exécution de pip
# ---------------------------------------------------------------------------

def _python_du_venv() -> Path:
    """Interpréteur de l'environnement isolé, en mode source."""
    racine = Path(__file__).resolve().parent.parent
    if os.name == "nt":
        return racine / ".venv" / "Scripts" / "python.exe"
    return racine / ".venv" / "bin" / "python"


def _pip_en_place(arguments: list[str], ecrire: Callable[[str], None]) -> int:
    """
    Appelle pip dans CE processus. Réservé au processus travailleur.

    L'appelant est soit l'exécutable gelé lancé avec « --installer-locuteurs »,
    soit `python -m app.extensions`. Dans les deux cas, ce processus ne fait que
    cela puis se termine : pip n'aime pas être rappelé, et il refusera bientôt
    qu'on importe dans la foulée un paquet qu'il vient de poser.
    """
    if chemins.EST_GELE:
        # pip est livré en fichiers .py à côté des ressources : il faut que le
        # dossier soit sur le chemin d'import pour que ses ressources vendues
        # se retrouvent (voir la note 1 en tête de module).
        base = str(chemins.DOSSIER_RESSOURCES)
        if base not in sys.path:
            sys.path.insert(0, base)
    try:
        from pip._internal.cli.main import main as pip_principal
    except Exception as exc:
        ecrire(f"ERROR: pip indisponible : {type(exc).__name__}: {exc}")
        return 2
    try:
        return int(pip_principal(arguments) or 0)
    except SystemExit as sortie:
        return int(sortie.code or 0)
    except Exception as exc:
        ecrire(f"ERROR: {type(exc).__name__}: {exc}")
        return 2


def _pip_en_sous_processus(arguments: list[str], ecrire: Callable[[str], None]) -> int:
    """Appelle le pip du « .venv ». Mode source uniquement."""
    python = _python_du_venv()
    if not python.exists():
        ecrire(f"ERROR: environnement isolé introuvable : {python}")
        return 2
    processus = subprocess.Popen(
        [str(python), "-m", "pip", *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0),
    )
    assert processus.stdout is not None
    for ligne in processus.stdout:
        ecrire(ligne.rstrip())
    return processus.wait()


class _SortieInterceptee:
    """
    Remplace `sys.stdout` le temps d'un appel à pip, pour lire ses lignes.

    pip construit son gestionnaire de journalisation sur le `sys.stdout` du
    moment : il suffit donc de le remplacer avant l'appel. Les lignes sont
    accumulées jusqu'au saut de ligne, la progression brute arrivant par
    morceaux.
    """

    def __init__(self, sur_ligne: Callable[[str], None]):
        self._sur_ligne = sur_ligne
        self._tampon = ""

    def write(self, texte: str) -> int:
        self._tampon += texte
        while "\n" in self._tampon:
            ligne, _, self._tampon = self._tampon.partition("\n")
            self._sur_ligne(ligne)
        return len(texte)

    def flush(self) -> None:
        if self._tampon:
            self._sur_ligne(self._tampon)
            self._tampon = ""

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:
        return "utf-8"


def executer_pip(arguments: list[str], sur_ligne: Callable[[str], None]) -> int:
    """Lance pip par le chemin adapté au mode, en retransmettant chaque ligne."""
    if chemins.EST_GELE:
        ancien = sys.stdout
        sys.stdout = _SortieInterceptee(sur_ligne)  # type: ignore[assignment]
        try:
            return _pip_en_place(arguments, sur_ligne)
        finally:
            try:
                sys.stdout.flush()
            except Exception:
                pass
            sys.stdout = ancien
    return _pip_en_sous_processus(arguments, sur_ligne)


# ---------------------------------------------------------------------------
# Point d'entrée en ligne de commande, exécuté dans le processus travailleur
# ---------------------------------------------------------------------------

#: Préfixe des lignes destinées à l'application. Tout le reste est du bruit de
#: pip, conservé dans le journal mais jamais montré tel quel.
MARQUE = "SCRIBOUILLE|"


def _emettre(evenement: str, detail: str = "") -> None:
    try:
        sys.__stdout__.write(f"{MARQUE}{evenement}|{detail}\n")  # type: ignore[union-attr]
        sys.__stdout__.flush()  # type: ignore[union-attr]
    except Exception:
        pass


def _installer(cible: Path | None, variante: str, paquets: list[str] | None,
               index: str) -> int:
    liste = lots(variante, paquets, index)
    _emettre("debut", f"{len(liste)}|{variante}")

    for numero, (nom_lot, contenu, index_lot, extra_lot) in enumerate(liste, start=1):
        _emettre("lot", f"{numero}|{len(liste)}|{nom_lot}")
        courant = {"paquet": ""}

        def sur_ligne(ligne: str, courant=courant) -> None:
            evenement = analyser_ligne(ligne)
            if evenement is None:
                return
            if evenement["type"] == "paquet":
                courant["paquet"] = evenement["nom"]
                _emettre("paquet", evenement["nom"])
            elif evenement["type"] == "octets":
                total = evenement["total"] or 0
                pct = int(evenement["recu"] * 100 / total) if total else 0
                _emettre("octets", f"{courant['paquet']}|{pct}|{evenement['recu']}|{total}")
            elif evenement["type"] == "pose":
                _emettre("pose", "")
            elif evenement["type"] == "erreur":
                _emettre("detail", evenement["texte"][:400])

        code = executer_pip(arguments_pip(contenu, index_lot, extra_lot, cible), sur_ligne)
        if code != 0:
            _emettre("echec", f"{nom_lot}|{code}")
            return code

    if cible is not None:
        _ecrit_marqueur(cible, variante, sorted({
            paquet for _, contenu, _, _ in liste for paquet in contenu
        }))
    _emettre("succes", "")
    return 0


def _verifier(cible: Path | None) -> int:
    reussi, detail = modules_importables(cible)
    _emettre("verification", f"{'ok' if reussi else 'ko'}|{detail}")
    print(("  OK    " if reussi else "  ECHEC ")
          + "séparation des locuteurs : "
          + ("installée" if reussi else "non installée")
          + (f" ({detail})" if detail else ""))
    return 0 if reussi else 1


def retirer(dossier: str | Path | None = None, vider_cache: bool = True) -> dict:
    """
    Efface le dossier d'extensions, et par défaut le cache de téléchargement.

    Renvoie {ok, message_technique, libere_go}. L'appelant traduit.
    """
    cible = Path(str(dossier)) if dossier else DOSSIER
    # Mesure réelle cette fois : c'est un geste ponctuel, et le chiffre annoncé
    # à l'utilisateur doit être celui de ce qui part vraiment.
    libere = taille_go(cible, mesurer=True) + (taille_cache_go() if vider_cache else 0.0)
    erreurs = []
    for chemin in [cible] + ([DOSSIER_CACHE] if vider_cache else []):
        if not chemin.is_dir():
            continue
        try:
            shutil.rmtree(chemin)
        except OSError as exc:
            erreurs.append(f"{chemin} : {exc.strerror or exc}")
    return {
        "ok": not erreurs,
        "message_technique": " ; ".join(erreurs),
        "libere_go": round(libere, 2),
    }


def principal_cli(arguments: list[str]) -> int:
    """
    Traite les options de ligne de commande liées aux extensions.

    Renvoie le code de sortie du processus. L'appelant ne doit y venir que si
    `options_reconnues` a dit oui : sans aucune de ces options, il n'y a rien à
    faire et le code renvoyé est 0.
    """
    import argparse

    analyseur = argparse.ArgumentParser(add_help=False)
    analyseur.add_argument("--installer-locuteurs", dest="installer", action="store_true")
    analyseur.add_argument("--verifier-locuteurs", dest="verifier", action="store_true")
    analyseur.add_argument("--retirer-locuteurs", dest="retirer", action="store_true")
    analyseur.add_argument("--cible", default="")
    analyseur.add_argument("--paquets", default="")
    analyseur.add_argument("--index-url", dest="index", default="")
    analyseur.add_argument("--cpu", action="store_true")
    analyseur.add_argument("--cuda", action="store_true")
    options, _ = analyseur.parse_known_args(arguments)

    cible: Path | None
    if options.cible:
        cible = Path(options.cible).expanduser()
    elif chemins.EST_GELE:
        cible = DOSSIER
    else:
        cible = None  # mode source : on installe dans le « .venv »

    variante = "cuda" if options.cuda else ("cpu" if options.cpu else variante_materielle())
    paquets = [p.strip() for p in options.paquets.split(",") if p.strip()]

    if options.retirer:
        resultat = retirer(cible)
        print(f"  {'OK   ' if resultat['ok'] else 'ECHEC'}  retrait, "
              f"{resultat['libere_go']:.2f} Go libérés {resultat['message_technique']}")
        return 0 if resultat["ok"] else 1

    if options.verifier:
        return _verifier(cible)

    if options.installer:
        if cible is not None:
            try:
                cible.mkdir(parents=True, exist_ok=True)
                DOSSIER_CACHE.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                _emettre("echec", f"dossier|{exc}")
                return 2
        return _installer(cible, variante, paquets, options.index)

    return 0


def commande_travailleur(options: list[str]) -> tuple[list[str], str]:
    """
    Commande à lancer pour faire le travail dans un processus séparé, et son
    dossier de travail.

    Version installée : l'exécutable lui-même. On préfère « scribouille-verifier.exe »
    quand il est là : construit avec une console, il a des flux standard francs,
    là où un exécutable fenêtré n'en a que par la grâce de son parent. Il est
    lancé sans fenêtre visible.

    Depuis les sources : l'interpréteur du « .venv », sur ce module.
    """
    if chemins.EST_GELE:
        dossier = Path(sys.executable).resolve().parent
        console = dossier / "scribouille-verifier.exe"
        exe = console if console.is_file() else Path(sys.executable)
        return [str(exe), *options], str(dossier)
    racine = Path(__file__).resolve().parent.parent
    python = _python_du_venv()
    interprete = str(python) if python.exists() else sys.executable
    return [interprete, "-m", "app.extensions", *options], str(racine)


def options_reconnues(arguments: list[str]) -> bool:
    return any(
        argument in ("--installer-locuteurs", "--verifier-locuteurs", "--retirer-locuteurs")
        for argument in arguments
    )


if __name__ == "__main__":
    sys.exit(principal_cli(sys.argv[1:]))
