"""
Pleine vitesse pendant le calcul, même fenêtre réduite.

Sur un processeur hybride, Windows 11 classe d'office en « EcoQoS » un
processus dont la fenêtre est réduite ou masquée : il baisse alors la fréquence
et range le travail sur les cœurs efficaces. C'est voulu pour un navigateur en
arrière-plan, pas pour une transcription d'une heure que l'on laisse tourner
en réduisant la fenêtre.

La documentation de `SetProcessInformation` (Microsoft Learn, classe
`ProcessPowerThrottling`) décrit le remède : déclarer `ControlMask =
PROCESS_POWER_THROTTLING_EXECUTION_SPEED` avec `StateMask = 0` fait passer le
processus en « HighQoS », bridage de vitesse désactivé. On le pose le temps de
la file de traitement, puis on rend la main au système (`ControlMask = 0`),
qui reprend ses propres heuristiques.

Sans effet sur un processeur homogène, et sans conséquence si l'appel échoue
(Windows 10 ancien, autre système) : la transcription continue, simplement
au rythme que le système choisit.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

from . import journal

_CLASSE_BRIDAGE = 4                 # ProcessPowerThrottling
_VERSION_BRIDAGE = 1                # PROCESS_POWER_THROTTLING_CURRENT_VERSION
_VITESSE_EXECUTION = 0x1            # PROCESS_POWER_THROTTLING_EXECUTION_SPEED


def _poser(controle: int, etat: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class _Etat(ctypes.Structure):
            _fields_ = [
                ("Version", wintypes.ULONG),
                ("ControlMask", wintypes.ULONG),
                ("StateMask", wintypes.ULONG),
            ]

        noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        fonction = noyau.SetProcessInformation
        fonction.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        fonction.restype = wintypes.BOOL
        noyau.GetCurrentProcess.restype = wintypes.HANDLE
        valeur = _Etat(_VERSION_BRIDAGE, controle, etat)
        return bool(fonction(noyau.GetCurrentProcess(), _CLASSE_BRIDAGE,
                             ctypes.byref(valeur), ctypes.sizeof(valeur)))
    except Exception as exc:  # pragma: no cover - dépend du système
        journal.debug("Qualité de service non modifiée : %s", exc)
        return False


def desactiver_bridage() -> bool:
    """HighQoS : ni baisse de fréquence ni relégation sur les cœurs efficaces."""
    return _poser(_VITESSE_EXECUTION, 0)


def activer_bridage() -> bool:
    """
    EcoQoS : le « mode efficacité » de Windows, voulu pour le mode discret.

    Microsoft Learn (SetProcessInformation, ProcessPowerThrottling) : le
    système baisse la fréquence ou range le travail sur les cœurs efficaces,
    « when the work is not contributing to the foreground user experience ».
    Le gestionnaire des tâches pose la même chose, plus la priorité basse,
    quand on clique sur « Mode efficacité ».
    """
    return _poser(_VITESSE_EXECUTION, _VITESSE_EXECUTION)


# ---------------------------------------------------------------------------
# Priorité, entrées-sorties et affinité du processus (mode « je travaille en
# même temps », voir `app/rythme.py`). Par psutil, déjà requis : sans lui, ou
# hors de Windows, chaque appel renvoie faux et rien ne change.
# ---------------------------------------------------------------------------

#: Classes de priorité Windows (SetPriorityClass), par nom de l'application.
PRIORITES = {"normale": 0x20, "inferieure": 0x4000, "basse": 0x40}


def poser_priorite(nom: str) -> bool:
    try:
        import psutil  # type: ignore

        psutil.Process().nice(PRIORITES.get(nom, PRIORITES["normale"]))
        return True
    except Exception as exc:  # pragma: no cover - dépend du système
        journal.debug("Priorité non modifiée : %s", exc)
        return False


def poser_priorite_es(nom: str) -> bool:
    """Priorité des lectures et écritures : « normale » ou « basse »."""
    try:
        import psutil  # type: ignore

        valeur = psutil.IOPRIO_LOW if nom == "basse" else psutil.IOPRIO_NORMAL
        psutil.Process().ionice(valeur)
        return True
    except Exception as exc:  # pragma: no cover - dépend du système
        journal.debug("Priorité des entrées-sorties non modifiée : %s", exc)
        return False


def poser_affinite(logiques: list[int] | None) -> bool:
    """Processeurs logiques permis ; liste vide ou None : tous."""
    try:
        import psutil  # type: ignore

        processus = psutil.Process()
        tous = list(range(psutil.cpu_count(logical=True) or 1))
        voulus = [n for n in (logiques or []) if n in tous] or tous
        processus.cpu_affinity(voulus)
        return True
    except Exception as exc:  # pragma: no cover - dépend du système
        journal.debug("Affinité non modifiée : %s", exc)
        return False


def poser_qos(nom: str) -> bool:
    """« haute » (HighQoS), « eco » (EcoQoS) ou « systeme » (heuristiques de Windows)."""
    if nom == "haute":
        return desactiver_bridage()
    if nom == "eco":
        return activer_bridage()
    return rendre_au_systeme()


def alimentation() -> dict:
    """{"batterie": présente, "secteur": branché, "pct": charge} ; secteur vrai sans batterie."""
    try:
        import psutil  # type: ignore

        batterie = psutil.sensors_battery()
    except Exception:
        batterie = None
    if batterie is None:
        return {"batterie": False, "secteur": True, "pct": 100}
    return {"batterie": True, "secteur": bool(batterie.power_plugged),
            "pct": int(batterie.percent or 0)}


#: Mode d'alimentation de Windows 10 et 11 (curseur « Mode d'alimentation »),
#: lu par PowerGetEffectiveOverlayScheme (powrprof.dll). Lecture seule :
#: l'application ne change aucun réglage du système, elle peut le signaler.
MODES_ALIMENTATION = {
    "961cc777-2547-4f9d-8174-7d86181b8a7a": "efficacite",
    "00000000-0000-0000-0000-000000000000": "equilibre",
    "3af9b8d9-7c97-431d-ad78-34a8bfea439f": "performances",
    "ded574b5-45a0-4f42-8737-46345c09c238": "performances_max",
}


def mode_alimentation() -> str:
    """« efficacite », « equilibre », « performances », « performances_max », vide si illisible."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        import uuid

        tampon = (ctypes.c_ubyte * 16)()
        fonction = ctypes.WinDLL("powrprof").PowerGetEffectiveOverlayScheme
        if fonction(ctypes.byref(tampon)) != 0:
            return ""
        return MODES_ALIMENTATION.get(str(uuid.UUID(bytes_le=bytes(tampon))), "")
    except Exception:
        return ""


def rendre_au_systeme() -> bool:
    """Le système reprend ses heuristiques habituelles."""
    return _poser(0, 0)


#: Drapeaux de `SetThreadExecutionState` (Microsoft Learn, winbase.h).
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _etat_execution(drapeaux: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        fonction = noyau.SetThreadExecutionState
        fonction.argtypes = [ctypes.c_uint32]
        fonction.restype = ctypes.c_uint32
        return fonction(drapeaux) != 0
    except Exception as exc:  # pragma: no cover - dépend du système
        journal.debug("Mise en veille non retenue : %s", exc)
        return False


@contextmanager
def sans_veille():
    """
    Le système ne se met pas en veille pendant le bloc (calcul de plusieurs heures).

    `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` est une demande
    propre au processus : aucun réglage d'alimentation n'est modifié, l'écran
    peut s'éteindre, et la demande tombe d'elle-même si le processus s'arrête.
    Elle est relâchée à la sortie du bloc, erreur comprise. À appeler depuis le
    fil qui reste vivant pendant tout le calcul.
    """
    pose = _etat_execution(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if pose:
        journal.info("Mise en veille du système suspendue le temps du calcul")
    try:
        yield pose
    finally:
        if pose:
            _etat_execution(ES_CONTINUOUS)


@contextmanager
def pleine_vitesse():
    """Bloc exécuté sans bridage d'énergie, quoi qu'il arrive à la fenêtre."""
    pose = desactiver_bridage()
    if pose:
        journal.info("Bridage d'énergie de Windows désactivé le temps du calcul")
    try:
        yield pose
    finally:
        if pose:
            rendre_au_systeme()
