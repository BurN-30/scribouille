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
  verrou à son nom, dans `reprises\\`, porte le PID du moteur qui le traite.
  Un second lancement sur le même enregistrement s'arrête net, avec un
  message, au lieu de se disputer la même sauvegarde progressive. Un verrou
  dont le processus est mort (plantage) est repris.
"""

from __future__ import annotations

import hashlib
import os
import sys
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


def _vivant(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except Exception:
        return False


def prendre_fichier(source: str | Path) -> int:
    """
    Pose le verrou du fichier pour ce processus. Renvoie 0 si c'est fait, ou
    le PID du processus qui le transcrit déjà.
    """
    verrou = _fichier_verrou(source)
    verrou.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descripteur = os.open(verrou, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(verrou.read_text(encoding="ascii").strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and pid != os.getpid() and _vivant(pid):
                return pid
            try:
                verrou.unlink()  # verrou d'un processus disparu
            except OSError:
                return pid or -1
            continue
        with os.fdopen(descripteur, "w", encoding="ascii") as flux:
            flux.write(str(os.getpid()))
        return 0
    return -1


def rendre_fichier(source: str | Path) -> None:
    verrou = _fichier_verrou(source)
    try:
        if int(verrou.read_text(encoding="ascii").strip() or 0) == os.getpid():
            verrou.unlink()
    except (OSError, ValueError):
        pass
