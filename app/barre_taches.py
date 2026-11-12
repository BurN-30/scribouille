"""
Progression dans la barre des tâches de Windows.

Pendant une transcription d'une heure, la fenêtre est le plus souvent réduite.
La barre de progression native de l'icône, celle que montrent les navigateurs
pendant un téléchargement, dit l'avancement d'un coup d'œil sans rien afficher :
pas de notification, pas de clignotement, pas de fenêtre au premier plan.

Implémentation : `ITaskbarList3`, en **ctypes pur**. `comtypes` n'est pas une
dépendance du projet et il n'est pas question d'en ajouter une pour ceci. Les
appels COM se font donc à la main, par index dans la table virtuelle :

    IUnknown        0 QueryInterface, 1 AddRef, 2 Release
    ITaskbarList    3 HrInit, 4 AddTab, 5 DeleteTab, 6 ActivateTab, 7 SetActiveAlt
    ITaskbarList2   8 MarkFullscreenWindow
    ITaskbarList3   9 SetProgressValue, 10 SetProgressState

L'interface COM est liée à l'appartement du fil qui l'a créée : chaque fil qui
appelle ce module obtient donc son propre pointeur, rangé dans un
`threading.local`. C'est la manière correcte, pas une précaution.

Rien ici n'a le droit d'interrompre quoi que ce soit. Toute erreur, à
n'importe quelle étape, met le module hors service en silence pour le reste de
la session : au pire, la barre des tâches ne bouge pas.

La fenêtre est retrouvée par son titre, seul point d'accroche disponible :
pywebview n'expose pas le HWND de sa fenêtre. Sans fenêtre trouvée, le module
ne fait rien du tout.
"""

from __future__ import annotations

import ctypes
import sys
import threading

from . import journal

#: États acceptés par SetProgressState.
ETAT_AUCUN = 0x0
ETAT_INDETERMINE = 0x1
ETAT_NORMAL = 0x2
ETAT_ERREUR = 0x4
ETAT_PAUSE = 0x8

_CLSID_TASKBARLIST = "{56FDF344-FD6D-11D0-958A-006097C9A090}"
_IID_ITASKBARLIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"

_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2

_local = threading.local()
_hors_service = not sys.platform.startswith("win")
_hwnd = 0
_verrou = threading.Lock()


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _guid(texte: str) -> _GUID:
    identifiant = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(texte), ctypes.byref(identifiant))
    return identifiant


def _appeler(pointeur, index: int, *types_et_valeurs) -> int:
    """Appelle la méthode `index` de la table virtuelle de l'objet COM."""
    table = ctypes.cast(pointeur, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    fonction = ctypes.WINFUNCTYPE(
        ctypes.c_long, ctypes.c_void_p, *[t for t, _ in types_et_valeurs]
    )(table[0][index])
    return fonction(pointeur, *[v for _, v in types_et_valeurs])


def _objet():
    """Pointeur ITaskbarList3 du fil courant, créé au premier besoin."""
    global _hors_service
    if _hors_service:
        return None
    pointeur = getattr(_local, "taskbar", None)
    if pointeur is not None:
        return pointeur or None

    try:
        # S_FALSE (déjà initialisé) est un succès, oledll ne lève que sur échec.
        try:
            ctypes.oledll.ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        except OSError:
            pass
        brut = ctypes.c_void_p()
        ctypes.oledll.ole32.CoCreateInstance(
            ctypes.byref(_guid(_CLSID_TASKBARLIST)), None, _CLSCTX_INPROC_SERVER,
            ctypes.byref(_guid(_IID_ITASKBARLIST3)), ctypes.byref(brut),
        )
        if _appeler(brut, 3) != 0:          # HrInit
            raise OSError("HrInit a échoué")
        _local.taskbar = brut
        return brut
    except Exception as exc:
        journal.debug("Barre de progression Windows indisponible : %s", exc)
        _local.taskbar = 0
        _hors_service = True
        return None


def definir_fenetre(titre: str) -> int:
    """
    Retrouve la fenêtre de l'application par son titre et la mémorise.

    pywebview ne donne pas le HWND de ses fenêtres ; `FindWindowW` est le seul
    accès raisonnable, et il ne coûte rien. Renvoie 0 si rien n'est trouvé,
    auquel cas le module reste inerte.
    """
    global _hwnd
    if _hors_service:
        return 0
    try:
        _hwnd = int(ctypes.windll.user32.FindWindowW(None, ctypes.c_wchar_p(titre)) or 0)
    except Exception as exc:
        journal.debug("Fenêtre introuvable pour la barre de progression : %s", exc)
        _hwnd = 0
    return _hwnd


def disponible() -> bool:
    return bool(not _hors_service and _hwnd)


def _etat(valeur: int) -> None:
    if not disponible():
        return
    pointeur = _objet()
    if not pointeur:
        return
    with _verrou:
        try:
            _appeler(pointeur, 10,
                     (ctypes.c_void_p, ctypes.c_void_p(_hwnd)),
                     (ctypes.c_int, ctypes.c_int(valeur)))
        except Exception as exc:
            journal.debug("Barre de progression : état non appliqué (%s)", exc)


def progression(pourcent: int) -> None:
    """Avancement normal, de 0 à 100."""
    if not disponible():
        return
    pointeur = _objet()
    if not pointeur:
        return
    borne = max(0, min(100, int(pourcent or 0)))
    with _verrou:
        try:
            _appeler(pointeur, 10,
                     (ctypes.c_void_p, ctypes.c_void_p(_hwnd)),
                     (ctypes.c_int, ctypes.c_int(ETAT_NORMAL)))
            _appeler(pointeur, 9,
                     (ctypes.c_void_p, ctypes.c_void_p(_hwnd)),
                     (ctypes.c_ulonglong, ctypes.c_ulonglong(borne)),
                     (ctypes.c_ulonglong, ctypes.c_ulonglong(100)))
        except Exception as exc:
            journal.debug("Barre de progression : valeur non appliquée (%s)", exc)


def erreur() -> None:
    """
    Barre rouge, brièvement, quand un fichier a échoué.

    La barre est d'abord remplie : un état d'erreur sur une valeur nulle ne
    dessine rien, et ne se verrait donc pas.
    """
    if not disponible():
        return
    pointeur = _objet()
    if not pointeur:
        return
    with _verrou:
        try:
            _appeler(pointeur, 9,
                     (ctypes.c_void_p, ctypes.c_void_p(_hwnd)),
                     (ctypes.c_ulonglong, ctypes.c_ulonglong(100)),
                     (ctypes.c_ulonglong, ctypes.c_ulonglong(100)))
            _appeler(pointeur, 10,
                     (ctypes.c_void_p, ctypes.c_void_p(_hwnd)),
                     (ctypes.c_int, ctypes.c_int(ETAT_ERREUR)))
        except Exception as exc:
            journal.debug("Barre de progression : erreur non affichée (%s)", exc)


def effacer() -> None:
    """Retour à une icône ordinaire."""
    _etat(ETAT_AUCUN)


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hwnd", ctypes.c_void_p), ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint), ("dwTimeout", ctypes.c_uint)]


#: FLASHW_ALL | FLASHW_TIMERNOFG : la fenêtre et son bouton clignotent jusqu'à
#: ce que l'utilisateur revienne sur la fenêtre, et pas du tout s'il y est déjà.
_CLIGNOTEMENT = 0x3 | 0xC


def clignoter() -> bool:
    """
    Signal discret de fin : le bouton de la barre des tâches clignote, comme
    pour une conversation qui attend une réponse. User32 seulement, aucune
    dépendance, rien d'affiché si la fenêtre est déjà au premier plan.
    """
    if _hors_service or not _hwnd or sys.platform != "win32":
        return False
    try:
        info = _FLASHWINFO(ctypes.sizeof(_FLASHWINFO), ctypes.c_void_p(_hwnd), _CLIGNOTEMENT, 0, 0)
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
        return True
    except Exception as exc:
        journal.debug("Clignotement de la barre des tâches impossible : %s", exc)
        return False


def au_premier_plan() -> bool:
    """La fenêtre de Scribouille est-elle celle que l'on regarde ?"""
    if _hors_service or not _hwnd or sys.platform != "win32":
        return False
    try:
        return int(ctypes.windll.user32.GetForegroundWindow() or 0) == _hwnd
    except Exception:
        return False


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("hWnd", ctypes.c_void_p), ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint), ("uCallbackMessage", ctypes.c_uint), ("hIcon", ctypes.c_void_p),
                ("szTip", ctypes.c_wchar * 128), ("dwState", ctypes.c_uint), ("dwStateMask", ctypes.c_uint),
                ("szInfo", ctypes.c_wchar * 256), ("uVersion", ctypes.c_uint),
                ("szInfoTitle", ctypes.c_wchar * 64), ("dwInfoFlags", ctypes.c_uint),
                ("guidItem", _GUID), ("hBalloonIcon", ctypes.c_void_p)]


_NIM_ADD, _NIM_DELETE = 0, 2
_NIF_ICON, _NIF_TIP, _NIF_INFO = 0x2, 0x4, 0x10
#: NIIF_INFO | NIIF_NOSOUND : icône d'information, jamais de son.
_NIIF = 0x1 | 0x10
_ID_ICONE = 0x5C1B


def notifier(titre: str, texte: str, duree_s: float = 20.0) -> bool:
    """
    Notification Windows de fin, sans son, par l'icône de la zone de
    notification (Shell_NotifyIcon) : rien à installer ni à enregistrer
    auprès du système, aucun droit. L'icône est retirée après `duree_s` ; la
    notification reste dans le centre de notifications selon les réglages de
    Windows (et « Ne pas déranger » la fait taire).
    """
    if _hors_service or not _hwnd or sys.platform != "win32":
        return False
    try:
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        user32.SendMessageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.LoadIconW.restype = ctypes.c_void_p
        user32.LoadIconW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        # Icône de la fenêtre (WM_GETICON, petite puis grande), sinon celle de Windows.
        icone = (user32.SendMessageW(ctypes.c_void_p(_hwnd), 0x7F, ctypes.c_void_p(2), None)
                 or user32.SendMessageW(ctypes.c_void_p(_hwnd), 0x7F, ctypes.c_void_p(0), None)
                 or user32.SendMessageW(ctypes.c_void_p(_hwnd), 0x7F, ctypes.c_void_p(1), None)
                 or user32.LoadIconW(None, ctypes.c_void_p(32512)))
        donnees = _NOTIFYICONDATAW()
        donnees.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        donnees.hWnd = ctypes.c_void_p(_hwnd)
        donnees.uID = _ID_ICONE
        donnees.uFlags = _NIF_ICON | _NIF_TIP | _NIF_INFO
        donnees.hIcon = icone
        donnees.szTip = titre[:127]
        donnees.szInfoTitle = titre[:63]
        donnees.szInfo = texte[:255]
        donnees.dwInfoFlags = _NIIF
        shell32.Shell_NotifyIconW.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        if not shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(donnees)):
            return False

        def retirer() -> None:
            try:
                shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(donnees))
            except Exception:
                pass

        minuterie = threading.Timer(duree_s, retirer)
        minuterie.daemon = True
        minuterie.start()
        return True
    except Exception as exc:
        journal.debug("Notification de fin impossible : %s", exc)
        return False
