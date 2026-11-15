"""
Plusieurs Scribouille en même temps : qui a la main sur quoi.

- **Une seule fenêtre par dossier de données.** Une seconde fenêtre ouverte sur
  les mêmes données ramène la première au premier plan et se ferme : deux
  fenêtres auraient chacune leur file, et enregistreraient chacune leurs
  réglages par-dessus ceux de l'autre.
- **La ligne de commande reste libre** pendant que la fenêtre est ouverte (une
  tâche planifiée, un agent, une session SSH). Les deux partagent réglages,
  vocabulaire et reprises ; la fenêtre relit les réglages du disque avant
  d'écrire les siens (`Passerelle._enregistrer_config`), elle n'efface donc
  pas un réglage posé entre-temps en ligne de commande.
- **Un fichier n'est transcrit que par un seul processus à la fois** : un
  verrou à son nom, dans `reprises\\`, porte le PID du moteur qui le traite et
  l'heure de création de ce processus. Un second lancement sur le même
  enregistrement s'arrête net, avec un message, au lieu de se disputer la
  même sauvegarde progressive. Un verrou dont le processus est mort
  (plantage, coupure de courant) est repris, même si son PID a été réattribué
  depuis à un autre programme : l'heure de création ne correspond plus (comme
  pour le témoin de la puce, `temoin_puce._vivant`). Un verrou d'avant ce
  format (PID seul) posé avant le dernier démarrage du système est mort.
  Le verrou naît complet (écrit à côté, puis lié sous son nom) : un
  concurrent ne le lit jamais vide ; un verrou vide (support sans liens) est
  tenu pour vivant quelques secondes.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

from . import chemins, journal

#: Poignée du mutex de la fenêtre, gardée ouverte jusqu'à la fin du processus.
_MUTEX = None


def _empreinte(texte: str) -> str:
    return hashlib.sha1(texte.lower().encode("utf-8", "replace")).hexdigest()[:16]


def prendre_fenetre() -> bool:
    """
    Réserve la fenêtre pour ce dossier de données. Faux si une autre fenêtre
    de Scribouille l'a déjà (Windows ; ailleurs, toujours vrai).
    """
    global _MUTEX
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        noyau = ctypes.windll.kernel32
        noyau.CreateMutexW.restype = ctypes.c_void_p
        nom = f"Local\\Scribouille-fenetre-{_empreinte(str(chemins.RACINE))}"
        poignee = noyau.CreateMutexW(None, False, nom)
        deja = noyau.GetLastError() == 183  # ERROR_ALREADY_EXISTS
        if not poignee:
            return True
        if deja:
            noyau.CloseHandle(ctypes.c_void_p(poignee))
            return False
        _MUTEX = poignee
        return True
    except Exception as exc:  # jamais bloquant
        journal.debug("Mutex de la fenêtre indisponible : %s", exc)
        return True


def montrer_fenetre_existante(titre: str) -> bool:
    """Ramène au premier plan la fenêtre déjà ouverte (retrouvée par son titre)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, titre)
        if not hwnd:
            return False
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Verrou d'un fichier en cours de transcription
# ---------------------------------------------------------------------------

def _fichier_verrou(source: str | Path) -> Path:
    try:
        cle = str(Path(source).resolve())
    except OSError:
        cle = str(source)
    return chemins.RACINE / "reprises" / f"{_empreinte(cle)}.en-cours"


#: Un verrou vide (pas encore écrit) plus jeune que cela est tenu pour vivant.
VERROU_VIDE_S = 10.0


def _creation(pid: int) -> float:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(int(pid)).create_time())
    except Exception:
        return 0.0


def _demarrage_systeme() -> float:
    try:
        import psutil  # type: ignore

        return float(psutil.boot_time())
    except Exception:
        return 0.0


def _vivant(pid: int, cree: float = 0.0) -> bool:
    """Le processus `pid` vit-il, et est-ce bien celui créé à `cree` (à 1 s près, si donné) ?"""
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        p = psutil.Process(int(pid))
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        return not cree or abs(float(p.create_time()) - float(cree)) < 1.0
    except Exception:
        return False


def _contenu() -> str:
    return f"{os.getpid()} {_creation(os.getpid()):.3f}"


def lire_verrou(verrou: Path) -> tuple[int, float, float]:
    """(pid, heure de création du processus, date du verrou) ; OSError ou ValueError s'il ne se lit pas."""
    texte = verrou.read_text(encoding="ascii").strip()
    date = verrou.stat().st_mtime
    if not texte:
        return 0, 0.0, date
    morceaux = texte.split()
    return int(morceaux[0]), float(morceaux[1]) if len(morceaux) > 1 else 0.0, date


def verrou_tenu(verrou: Path) -> int:
    """
    PID du processus vivant qui tient ce verrou (le nôtre compris), -1 si le
    verrou est trop récent pour être jugé (vide, en cours d'écriture) ou ne se
    lit pas pour l'instant, 0 s'il est mort.
    """
    try:
        pid, cree, date = lire_verrou(verrou)
    except FileNotFoundError:
        return 0
    except (OSError, ValueError):
        try:
            return -1 if time.time() - verrou.stat().st_mtime < VERROU_VIDE_S else 0
        except OSError:
            return 0
    if pid <= 0:
        return -1 if time.time() - date < VERROU_VIDE_S else 0
    if not cree:
        # Ancien format (PID seul) : posé avant le dernier démarrage, il est mort.
        demarrage = _demarrage_systeme()
        if demarrage and date < demarrage:
            return 0
    return pid if _vivant(pid, cree) else 0


def occupant(source: str | Path) -> int:
    """PID du processus vivant qui transcrit ce fichier, sinon 0."""
    pid = verrou_tenu(_fichier_verrou(source))
    return pid if pid > 0 and pid != os.getpid() else 0


def _creer(verrou: Path) -> bool:
    """
    Crée le verrou complet d'un coup : écrit à côté puis lié sous son nom
    (échoue s'il existe). Support sans liens : création exclusive puis
    écriture (un verrou vide est tenu pour vivant quelques secondes).
    Vrai si créé, faux s'il existait déjà.
    """
    provisoire = verrou.with_name(f"{verrou.name}.{os.getpid()}.tmp")
    try:
        provisoire.write_text(_contenu(), encoding="ascii")
        try:
            os.link(provisoire, verrou)
            return True
        except FileExistsError:
            return False
        except (OSError, NotImplementedError, AttributeError):
            pass
    finally:
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        descripteur = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(descripteur, "w", encoding="ascii") as flux:
        flux.write(_contenu())
    return True


def prendre_fichier(source: str | Path) -> int:
    """
    Pose le verrou du fichier pour ce processus. Renvoie 0 si c'est fait, ou
    le PID du processus qui le transcrit déjà (-1 : verrou trop récent pour
    être jugé, ou qui résiste).
    """
    verrou = _fichier_verrou(source)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        if _creer(verrou):
            return 0
        tenu = verrou_tenu(verrou)
        if tenu == os.getpid():
            # Le nôtre (reprise après plantage dans ce processus) : refait à neuf.
            pass
        elif tenu:
            return tenu
        try:
            avant = verrou.read_bytes()
        except FileNotFoundError:
            continue
        except OSError:
            return -1
        try:
            # Verrou mort : retiré, sauf s'il a changé entre-temps (un autre
            # processus vient de le reprendre).
            if verrou.read_bytes() == avant:
                verrou.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return -1
    return -1


def rendre_fichier(source: str | Path) -> None:
    verrou = _fichier_verrou(source)
    try:
        pid, _cree, _date = lire_verrou(verrou)
        if pid == os.getpid():
            verrou.unlink()
    except (OSError, ValueError):
        pass
