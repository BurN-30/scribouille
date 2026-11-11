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


def rendre_au_systeme() -> bool:
    """Le système reprend ses heuristiques habituelles."""
    return _poser(0, 0)


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
