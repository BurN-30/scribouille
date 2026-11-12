"""
Processus fils : lien de vie avec le parent, mesure, arrêt.

Trois garanties, empilées pour qu'aucune ne soit seule à tenir :

  1. **Objet de travail Windows** (`TacheLiee`) : le parent y range ses fils
     avec `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Quand le parent disparaît, même
     tué par le gestionnaire des tâches, Windows ferme la poignée de l'objet et
     tue tout ce qui y est rangé, petits-enfants compris. Seuls les fils voulus y
     entrent : un document ouvert par l'utilisateur (Bloc-notes, navigateur)
     n'est jamais tué à la fermeture de Scribouille.
  2. **Surveillance du parent** côté fils (`surveiller_parent`) : un fil attend
     la fin du processus parent et sort aussitôt (idée reprise de vibe-server,
     `--exit-with-parent`, MIT, Copyright (c) 2024 thewh1teagle).
  3. **Fin de l'entrée standard** : le moteur lit ses ordres sur stdin ; une
     fin de flux veut dire que le parent n'est plus là.

Hors Windows, seules les garanties 2 (par sondage du PID) et 3 jouent.
"""

from __future__ import annotations

import os
import sys
import threading
import time

_WINDOWS = sys.platform == "win32"


class TacheLiee:
    """Objet de travail Windows qui tue ses processus quand le parent s'en va."""

    def __init__(self):
        self._poignee = None
        if not _WINDOWS:
            return
        try:
            self._poignee = _creer_objet_travail()
        except Exception:  # pragma: no cover - dépend du système
            self._poignee = None

    @property
    def active(self) -> bool:
        return self._poignee is not None

    def rattacher(self, processus) -> bool:
        """Range un `subprocess.Popen` (ou un PID) dans l'objet de travail."""
        if self._poignee is None:
            return False
        try:
            return _assigner(self._poignee, processus)
        except Exception:  # pragma: no cover - dépend du système
            return False


_tache_commune: TacheLiee | None = None
_verrou_tache = threading.Lock()


def tache_commune() -> TacheLiee:
    """Un seul objet de travail par processus parent, créé au premier besoin."""
    global _tache_commune
    with _verrou_tache:
        if _tache_commune is None:
            _tache_commune = TacheLiee()
        return _tache_commune


def rattacher(processus) -> bool:
    """Raccourci : range le processus dans l'objet de travail commun."""
    return tache_commune().rattacher(processus)


# ---------------------------------------------------------------------------
# Windows : objet de travail par ctypes
# ---------------------------------------------------------------------------

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JobObjectExtendedLimitInformation = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _kernel32():
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def _creer_objet_travail():
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = _kernel32()
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    poignee = k32.CreateJobObjectW(None, None)
    if not poignee:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(poignee, _JobObjectExtendedLimitInformation,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
    # La poignée n'est jamais fermée volontairement : elle vit autant que le
    # parent, et c'est sa fermeture par le système qui tue les fils.
    return poignee


def _assigner(poignee, processus) -> bool:
    import ctypes
    from ctypes import wintypes

    k32 = _kernel32()
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    poignee_processus = getattr(processus, "_handle", None)
    fermer = False
    if poignee_processus is None:
        pid = int(getattr(processus, "pid", processus))
        poignee_processus = k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
        fermer = True
        if not poignee_processus:
            return False
    try:
        return bool(k32.AssignProcessToJobObject(poignee, int(poignee_processus)))
    finally:
        if fermer:
            k32.CloseHandle(poignee_processus)


# ---------------------------------------------------------------------------
# Côté fils : sortir quand le parent disparaît
# ---------------------------------------------------------------------------

def surveiller_parent(pid: int, sortir=None) -> bool:
    """
    Lance un fil qui attend la fin du processus `pid`, puis appelle `sortir`
    (par défaut `os._exit(0)` : rien ne doit retenir un moteur orphelin).
    Renvoie False si le parent est introuvable (déjà parti : on sort tout de suite).
    """
    if not pid or pid <= 0:
        return False
    sortie = sortir or (lambda: os._exit(0))

    if _WINDOWS:
        import ctypes
        from ctypes import wintypes

        k32 = _kernel32()
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        poignee = k32.OpenProcess(_SYNCHRONIZE, False, int(pid))
        if not poignee:
            sortie()
            return False

        def attendre() -> None:
            k32.WaitForSingleObject(poignee, 0xFFFFFFFF)
            sortie()
    else:
        def attendre() -> None:
            while True:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(1.0)
            sortie()

    threading.Thread(target=attendre, name="surveillance-parent", daemon=True).start()
    return True


# ---------------------------------------------------------------------------
# Mesure : mémoire et processeur d'un processus
# ---------------------------------------------------------------------------

class Sonde:
    """
    Mémoire et processeur d'un processus, relevés à la demande.

    `processeur_pct` est la part d'UN cœur depuis le relevé précédent (100 % =
    un cœur plein), comme le Gestionnaire des tâches en vue détaillée la
    multiplie par le nombre de cœurs ; `processeur_poste_pct` la ramène au
    poste entier.
    """

    def __init__(self, pid: int | None = None):
        self.pid = int(pid or os.getpid())
        self._processus = None
        self._dernier: tuple[float, float] | None = None

    def releve(self) -> dict | None:
        try:
            import psutil  # type: ignore
        except Exception:
            return None
        try:
            if self._processus is None or self._processus.pid != self.pid:
                self._processus = psutil.Process(self.pid)
            p = self._processus
            with p.oneshot():
                memoire = p.memory_info()
                temps = p.cpu_times()
            propre = memoire_propre(p)
            maintenant = time.monotonic()
            cumul = float(temps.user + temps.system)
            pct = None
            if self._dernier is not None and maintenant > self._dernier[0]:
                pct = max(0.0, (cumul - self._dernier[1]) / (maintenant - self._dernier[0]) * 100.0)
            self._dernier = (maintenant, cumul)
            coeurs = psutil.cpu_count() or 1
            return {
                "pid": self.pid,
                # Ensemble de travail : ce que le Gestionnaire des tâches appelle « mémoire ».
                "memoire_octets": int(memoire.rss),
                # Mémoire privée engagée (Windows) : ce que le processus a réservé pour lui.
                "prive_octets": int(getattr(memoire, "private", 0) or getattr(memoire, "vms", 0)),
                # Mémoire qu'il occupe vraiment, à lui seul (USS) : ce que l'écran
                # montre. La mémoire engagée la dépasse de loin (590 Mo engagés
                # pour 79 Mo occupés, relevé de la recette du 12/11).
                "propre_octets": propre,
                "processeur_pct": None if pct is None else round(pct, 1),
                "processeur_poste_pct": None if pct is None else round(pct / coeurs, 1),
            }
        except Exception:
            return None


def memoire_propre(processus) -> int:
    """Mémoire occupée par ce processus seul (USS), 0 si Windows la refuse."""
    try:
        return int(processus.memory_full_info().uss)
    except Exception:
        return 0


def vivant(pid: int) -> bool:
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).status() != "zombie"
    except Exception:
        return False


def enfants(pid: int | None = None) -> list[int]:
    """PID des descendants d'un processus (vide si psutil manque)."""
    try:
        import psutil  # type: ignore

        return [p.pid for p in psutil.Process(int(pid or os.getpid())).children(recursive=True)]
    except Exception:
        return []
