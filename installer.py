"""
Installateur de Scribouille (installation depuis les sources).

Relançable autant de fois qu'on veut : il ne réinstalle que ce qui manque et
finit toujours par un bilan clair de l'état du poste.

Ce qu'il fait :
  1. vérifie la version de Python ;
  2. crée l'environnement isolé « .venv » à côté de l'application ;
  3. installe le socle (transcription seule, léger, sans PyTorch) ;
  4. pose FFmpeg via un paquet Python qui embarque le binaire, donc sans
     droits administrateur, sans winget et sans PATH à configurer ;
  5. si une carte NVIDIA est détectée, ajoute les bibliothèques CUDA au bon
     endroit pour éviter le grand classique « cublas64_12.dll introuvable » ;
  6. sur demande, installe la séparation des locuteurs (PyTorch + pyannote),
     en choisissant l'index PyTorch adapté au matériel ;
  7. vérifie que tout s'importe et affiche le bilan.

Usage :
    python installer.py                  installation standard, pose la question
    python installer.py --locuteurs      installe aussi la séparation des locuteurs
    python installer.py --sans-locuteurs installation légère, sans question
    python installer.py --verifier       ne fait que le bilan
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER_VENV = RACINE / ".venv"

PYTHON_MINIMUM = (3, 9)

TORCH_VERSION = "torch==2.8.0"
TORCHAUDIO_VERSION = "torchaudio==2.8.0"
# Figée : pyannote.audio se contente de « torchcodec>=0.7.0 », et la dernière
# version publiée est compilée contre un PyTorch bien plus récent. Elle se
# charge alors sur « WinError 127, la procédure spécifiée est introuvable ».
TORCHCODEC_VERSION = "torchcodec==0.7.0"
INDEX_TORCH_CPU = "https://download.pytorch.org/whl/cpu"
INDEX_TORCH_CUDA = "https://download.pytorch.org/whl/cu124"

LARGEUR = 68


# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------

def titre(texte: str) -> None:
    print()
    print("=" * LARGEUR)
    print(f"  {texte}")
    print("=" * LARGEUR)


def etape(numero: str, texte: str) -> None:
    print(f"\n[{numero}] {texte}")


def ok(texte: str) -> None:
    print(f"      OK    {texte}")


def info(texte: str) -> None:
    print(f"            {texte}")


def alerte(texte: str) -> None:
    print(f"      ATTN  {texte}")


def echec(texte: str) -> None:
    print(f"      ECHEC {texte}")


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def python_du_venv() -> Path:
    if os.name == "nt":
        return DOSSIER_VENV / "Scripts" / "python.exe"
    return DOSSIER_VENV / "bin" / "python"


def lancer(arguments: list[str], description: str) -> bool:
    """Lance une commande en montrant sa sortie. Renvoie True si elle réussit."""
    try:
        resultat = subprocess.run(arguments, check=False)
        if resultat.returncode == 0:
            return True
        echec(f"{description} (code {resultat.returncode})")
        return False
    except Exception as exc:
        echec(f"{description} : {exc}")
        return False


def pip(*arguments: str) -> list[str]:
    return [str(python_du_venv()), "-m", "pip", *arguments]


def carte_nvidia() -> bool:
    """
    Détecte le pilote NVIDIA AVANT toute installation.

    On ne peut pas se servir de torch.cuda pour cela : il faudrait déjà avoir
    installé la bonne version de torch. La présence de nvidia-smi, livré avec
    le pilote, est le signal fiable.
    """
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        return subprocess.run(["nvidia-smi"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def module_present(module: str) -> bool:
    code = f"import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('{module}') else 1)"
    try:
        return subprocess.run(
            [str(python_du_venv()), "-c", code], capture_output=True
        ).returncode == 0
    except Exception:
        return False


def demander_locuteurs() -> bool:
    print()
    print("  Voulez-vous la séparation des locuteurs (« Locuteur 1 », « Locuteur 2 ») ?")
    print()
    print("    Oui  : très utile pour les réunions, mais environ 2,5 Go de plus")
    print("           à installer, et un jeton Hugging Face gratuit à créer.")
    print("    Non  : installation légère. La transcription fonctionne")
    print("           parfaitement, simplement sans étiquettes de locuteur.")
    print()
    print("  Ce choix se change plus tard : relancez « installer.bat --locuteurs ».")
    print()
    try:
        reponse = input("  Installer la séparation des locuteurs ? [o/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return reponse in ("o", "oui", "y", "yes")


# ---------------------------------------------------------------------------
# Étapes
# ---------------------------------------------------------------------------

def verifier_python() -> bool:
    etape("1/6", "Version de Python")
    version = sys.version_info
    info(f"{platform.python_version()} : {sys.executable}")
    if version < PYTHON_MINIMUM:
        echec(f"Python {PYTHON_MINIMUM[0]}.{PYTHON_MINIMUM[1]} ou plus récent est nécessaire.")
        info("Téléchargez-le sur https://www.python.org/downloads/")
        return False
    ok("Version compatible")
    return True


def creer_venv() -> bool:
    etape("2/6", "Environnement isolé")
    if python_du_venv().exists():
        ok(f"Déjà présent : {DOSSIER_VENV}")
        return True
    info(f"Création de {DOSSIER_VENV} ...")
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(str(DOSSIER_VENV))
    except Exception as exc:
        echec(f"Création impossible : {exc}")
        return False
    if not python_du_venv().exists():
        echec("L'environnement a été créé mais son interpréteur est introuvable.")
        return False
    ok("Environnement prêt")
    return True


def installer_socle() -> bool:
    etape("3/6", "Composants de transcription")
    info("Mise à jour de pip ...")
    lancer(pip("install", "--upgrade", "pip", "--quiet", "--disable-pip-version-check"),
           "mise à jour de pip")

    info("Installation du socle (faster-whisper, interface, FFmpeg embarqué) ...")
    info("Comptez 250 à 400 Mo au premier passage.")
    if not lancer(
        pip("install", "-r", str(RACINE / "requirements.txt"), "--disable-pip-version-check"),
        "installation du socle",
    ):
        return False
    ok("Socle installé")
    return True


def installer_cuda(nvidia: bool) -> None:
    etape("4/6", "Accélération NVIDIA")
    if not nvidia:
        ok("Aucune carte NVIDIA détectée, transcription sur processeur.")
        info("C'est le cas le plus courant, et parfaitement utilisable :")
        info("un enregistrement d'une heure se traite en une à deux heures")
        info("en qualité maximale, et en une vingtaine de minutes en mode rapide.")
        return

    info("Carte NVIDIA détectée, pose des bibliothèques CUDA dans l'environnement ...")
    info("(elles évitent l'erreur « cublas64_12.dll introuvable »)")
    if lancer(
        pip("install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*",
            "--disable-pip-version-check"),
        "installation des bibliothèques CUDA",
    ):
        ok("Bibliothèques CUDA en place")
    else:
        alerte("Échec : l'application se rabattra sur le processeur.")


def installer_locuteurs(nvidia: bool) -> bool:
    etape("5/6", "Séparation des locuteurs")
    index = INDEX_TORCH_CUDA if nvidia else INDEX_TORCH_CPU
    info(f"Installation de PyTorch depuis {index}")
    info("Environ 2,5 Go, comptez plusieurs minutes.")
    if not lancer(
        pip("install", TORCH_VERSION, TORCHAUDIO_VERSION, TORCHCODEC_VERSION,
            "--index-url", index, "--disable-pip-version-check"),
        "installation de PyTorch",
    ):
        alerte("PyTorch n'a pas pu être installé, la séparation des locuteurs restera inactive.")
        return False

    info("Installation de pyannote.audio ...")
    # Les versions de PyTorch sont répétées ici, et ce n'est pas une redite :
    # pyannote.audio se contente de bornes basses, « torch>=2.8.0 » et
    # « torchcodec>=0.7.0 ». Sans contrainte, pip repart sur PyPI chercher les
    # dernières, qui embarquent CUDA, et écrase celles que l'on vient de poser.
    # Deux « dist-info » de torch, un gigaoctet perdu, et un torchcodec compilé
    # contre un autre PyTorch qui refuse ensuite de se charger.
    if not lancer(
        pip("install", "-r", str(RACINE / "requirements-locuteurs.txt"),
            TORCH_VERSION, TORCHAUDIO_VERSION, TORCHCODEC_VERSION,
            "--index-url", index, "--extra-index-url", "https://pypi.org/simple",
            "--disable-pip-version-check"),
        "installation de pyannote.audio",
    ):
        alerte("pyannote.audio n'a pas pu être installé.")
        return False

    ok("Séparation des locuteurs installée")
    info("Il reste à créer un jeton Hugging Face gratuit : l'application")
    info("affiche la marche à suivre dans le panneau « Locuteurs ».")
    return True


def verifier(locuteurs_demandes: bool) -> bool:
    etape("6/6", "Vérification")
    tout_va_bien = True

    for module, etiquette in (
        ("webview", "interface de fenêtre (pywebview)"),
        ("faster_whisper", "moteur de transcription (faster-whisper)"),
        ("ctranslate2", "calcul (CTranslate2)"),
        ("numpy", "calcul numérique (numpy)"),
    ):
        if module_present(module):
            ok(etiquette)
        else:
            echec(etiquette + " : manquant")
            tout_va_bien = False

    # FFmpeg embarqué
    code = "import imageio_ffmpeg,os,sys;p=imageio_ffmpeg.get_ffmpeg_exe();sys.exit(0 if os.path.exists(p) else 1)"
    if subprocess.run([str(python_du_venv()), "-c", code], capture_output=True).returncode == 0:
        ok("décodeur audio (FFmpeg embarqué)")
    else:
        echec("décodeur audio (FFmpeg) : manquant")
        tout_va_bien = False

    if module_present("psutil"):
        ok("détection du matériel (psutil)")
    else:
        alerte("psutil absent : la détection matérielle sera moins précise, sans gravité.")

    if locuteurs_demandes or module_present("torch"):
        if module_present("torch") and module_present("pyannote.audio"):
            ok("séparation des locuteurs (PyTorch + pyannote)")
        else:
            alerte("séparation des locuteurs incomplète, la transcription reste utilisable.")
    else:
        info("séparation des locuteurs : non installée (choix volontaire)")

    return tout_va_bien


def bilan(succes: bool) -> None:
    titre("Bilan")
    if succes:
        print("  Tout est en place.")
        print()
        print("  Pour démarrer : double-cliquez sur « lancer.bat ».")
        print()
        print("  Au premier lancement, le modèle de transcription se télécharge")
        print("  (1,6 Go en mode rapide, 3,1 Go en qualité maximale). C'est la")
        print("  seule fois où l'application a besoin d'Internet : ensuite, tout")
        print("  se passe sur cette machine et rien n'en sort.")
    else:
        print("  L'installation est incomplète, voir les lignes ECHEC ci-dessus.")
        print()
        print("  Causes les plus fréquentes :")
        print("    - pas de connexion Internet, ou un proxy d'entreprise qui bloque pip ;")
        print("    - un antivirus qui met en quarantaine les fichiers téléchargés ;")
        print("    - un disque plein.")
        print()
        print("  Relancez « installer.bat » : rien de ce qui est déjà posé n'est refait.")
    print()


def principal() -> int:
    analyseur = argparse.ArgumentParser(add_help=False)
    analyseur.add_argument("--locuteurs", action="store_true")
    analyseur.add_argument("--sans-locuteurs", dest="sans_locuteurs", action="store_true")
    analyseur.add_argument("--verifier", action="store_true")
    arguments, _ = analyseur.parse_known_args()

    titre("Scribouille, installation")
    print("  Transcription audio, 100 % sur votre machine.")
    print("  Rien de ce que vous transcrivez ne quitte ce poste.")

    if arguments.verifier:
        if not python_du_venv().exists():
            echec("Aucun environnement installé. Lancez « installer.bat » d'abord.")
            return 1
        reussi = verifier(module_present("torch"))
        bilan(reussi)
        return 0 if reussi else 1

    if not verifier_python():
        return 1
    if not creer_venv():
        return 1
    if not installer_socle():
        bilan(False)
        return 1

    nvidia = carte_nvidia()
    installer_cuda(nvidia)

    if arguments.locuteurs:
        voulu = True
    elif arguments.sans_locuteurs:
        voulu = False
    elif module_present("torch") and module_present("pyannote.audio"):
        etape("5/6", "Séparation des locuteurs")
        ok("Déjà installée")
        voulu = False
    else:
        voulu = demander_locuteurs()

    if voulu:
        installer_locuteurs(nvidia)
    elif not module_present("torch"):
        etape("5/6", "Séparation des locuteurs")
        info("Non installée. Pour l'ajouter plus tard : installer.bat --locuteurs")

    reussi = verifier(voulu or module_present("torch"))
    bilan(reussi)
    return 0 if reussi else 1


if __name__ == "__main__":
    try:
        sys.exit(principal())
    except KeyboardInterrupt:
        print("\n\n  Installation interrompue. Relancez quand vous voulez.\n")
        sys.exit(1)
