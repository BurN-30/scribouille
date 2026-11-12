"""
Rythme de la transcription : « je travaille en même temps ».

Trois positions, réglées par l'utilisateur dans le panneau des réglages :

  « vitesse »    Vitesse maximale. Le comportement d'avant la 3.0, à l'octet
                 près : tous les fils du réglage automatique ou du banc, lots du
                 preset, priorité normale, bridage d'énergie de Windows levé
                 (HighQoS, voir `app/energie.py`). C'est la valeur par défaut :
                 un poste déjà installé ne voit aucun changement.
  « equilibre »  Équilibré. Environ trois quarts des fils, deux processeurs
                 logiques au moins laissés libres, lots de 4 au plus, priorité
                 « inférieure à la normale », Windows décide de la fréquence.
  « discret »    Discret. La moitié des fils, rangés sur les cœurs efficaces des
                 processeurs hybrides, un passage à la fois (moins de mémoire),
                 priorité basse, « mode efficacité » de Windows (EcoQoS), lectures
                 et écritures en priorité basse ; sur la puce graphique, files
                 d'OpenVINO en priorité et cadence basses, et une pause après
                 chaque fenêtre.

Option « s'adapter tout seul » : la transcription prend le rythme choisi
pendant que le poste sert (clavier ou souris touchés depuis moins de deux
minutes, autres programmes qui occupent le processeur, plein écran ou
présentation, micro ouvert, alimentation sur batterie), et la vitesse
maximale quand il est au repos. Les fils et les lots sont fixés au chargement
du modèle et ne peuvent pas changer en route : ce sont alors ceux de la
vitesse maximale, et la bascule passe par ce qui se change à chaud (priorité,
qualité de service, pauses).

Tout ce qui décide est fait de fonctions pures (`bornes`, `rythme_effectif`,
`poste_occupe`, `garde_memoire`), vérifiées par
`outils/verifier_fonctions_peripheriques.py` avec une activité simulée. Ce qui
touche au système passe par des leviers injectables (`Leviers`), sans effet
hors de Windows.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from . import chemins, journal
from .materiel import Materiel

RYTHMES = ("vitesse", "equilibre", "discret")
DEFAUT = "vitesse"

#: Inactivité du clavier et de la souris au-delà de laquelle le poste est
#: tenu pour libre.
SEUIL_INACTIVITE_S = 120.0

#: Charge des AUTRES programmes, en pour cent du processeur entier : au-delà
#: de l'entrée, le poste est tenu pour occupé ; il ne redevient libre que sous
#: la sortie (hystérésis, pour ne pas basculer à chaque relevé).
SEUIL_CHARGE_ENTREE = 30.0
SEUIL_CHARGE_SORTIE = 15.0

#: Intervalle entre deux relevés d'activité.
INTERVALLE_S = 3.0

#: Rapport pause / calcul appliqué après chaque fenêtre ou passage. Une pause
#: de 1,0 laisse la puce graphique libre la moitié du temps. Sur processeur,
#: la pause ne sert qu'en adaptation automatique, où les fils restent ceux de
#: la vitesse maximale.
PAUSES = {
    ("vitesse", True): 0.0, ("vitesse", False): 0.0,
    ("equilibre", True): 0.25, ("equilibre", False): 0.0,
    ("discret", True): 1.0, ("discret", False): 0.0,
}
PAUSES_AUTO_PROCESSEUR = {"vitesse": 0.0, "equilibre": 0.2, "discret": 0.5}

#: Pause maximale d'une seule traite : l'annulation reste prompte.
PAUSE_MAX_S = 20.0

#: Coefficients de durée par rapport à la vitesse maximale, faute de mesure sur
#: le poste (`banc --modes` les remplace). Relevés sur un processeur de bureau
#: (Ryzen 7 7800X3D, 16 fils, novembre 2026, large-v3-turbo, autre calcul en
#: cours) : CTranslate2 1,11 et 2,35, OpenVINO sur processeur 0,90 et 1,32.
#: Prudents : le plus lent, arrondi vers le haut ; rien encore sur la puce.
COEFFICIENTS_REPLI = {"vitesse": 1.0, "equilibre": 1.3, "discret": 2.4}

#: Mémoire de calcul au pic, en Go, par moteur et modèle, traitement un à un
#: puis par lots de 8 (mesures du CHANGELOG 2.4.0 et de la campagne 2.4.1).
BESOINS_MEMOIRE_GO = {
    ("ctranslate2", "large-v3"): (3.3, 5.8),
    ("ctranslate2", "turbo"): (2.0, 3.5),
    ("openvino", "large-v3"): (3.6, 3.6),
    ("openvino", "turbo"): (2.2, 2.2),
}
#: Marge laissée au reste du poste au-dessus du besoin de calcul.
MARGE_MEMOIRE_GO = 1.5


def normaliser(rythme: str | None) -> str:
    return rythme if rythme in RYTHMES else DEFAUT


# ---------------------------------------------------------------------------
# Bornes de chaque rythme (fonction pure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Bornes:
    rythme: str
    #: Fils de calcul de CTranslate2 et d'OpenVINO sur processeur.
    fils: int
    #: Taille de lot maximale de CTranslate2 ; None : celle du preset.
    lot_max: int | None
    priorite: str           # « normale », « inferieure », « basse »
    qos: str                # « haute », « systeme », « eco »
    priorite_es: str        # « normale », « basse »
    #: Processeurs logiques permis, vide : tous.
    affinite: tuple[int, ...]
    #: Propriétés passées à OpenVINO à la compilation, par famille de circuit.
    ov_processeur: dict = field(default_factory=dict)
    ov_puce: dict = field(default_factory=dict)
    #: OpenMP en attente passive (variable lue au démarrage des processus).
    attente_passive: bool = False


def _fils_equilibre(base: int, logiques: int) -> int:
    fils = (base * 3 + 3) // 4
    if logiques > 2:
        fils = min(fils, logiques - 2)
    return max(1, min(fils, base))


def bornes(rythme: str, mat: Materiel) -> Bornes:
    """Ce que la transcription s'autorise à prendre au poste, pour ce rythme."""
    rythme = normaliser(rythme)
    base = max(1, mat.fils_calcul)
    logiques = mat.coeurs_logiques or base
    topo = mat.topologie
    if rythme == "vitesse":
        return Bornes("vitesse", base, None, "normale", "haute", "normale", ())
    if rythme == "equilibre":
        fils = _fils_equilibre(base, logiques)
        return Bornes(
            "equilibre", fils, 4, "inferieure", "systeme", "normale", (),
            ov_processeur={"INFERENCE_NUM_THREADS": fils},
            ov_puce={"GPU_QUEUE_PRIORITY": "LOW", "MODEL_PRIORITY": "LOW"},
            attente_passive=True)
    fils = max(1, base // 2)
    affinite: tuple[int, ...] = ()
    ov_processeur: dict = {"INFERENCE_NUM_THREADS": fils}
    if topo.hybride and topo.logiques_efficaces:
        fils = max(1, min(fils, len(topo.logiques_efficaces)))
        affinite = tuple(topo.logiques_efficaces)
        ov_processeur = {"INFERENCE_NUM_THREADS": fils, "SCHEDULING_CORE_TYPE": "ECORE_ONLY"}
    return Bornes(
        "discret", fils, 0, "basse", "eco", "basse", affinite,
        ov_processeur=ov_processeur,
        ov_puce={"GPU_QUEUE_PRIORITY": "LOW", "GPU_QUEUE_THROTTLE": "LOW",
                 "GPU_HOST_TASK_PRIORITY": "LOW", "MODEL_PRIORITY": "LOW"},
        attente_passive=True)


def bornes_chargement(rythme: str, auto: bool, mat: Materiel) -> Bornes:
    """
    Bornes figées au chargement du modèle (fils, lots, affinité, propriétés).

    En adaptation automatique, ce sont celles de la vitesse maximale, sauf la
    priorité de file de la puce graphique, sans effet quand rien d'autre ne la
    sollicite : la bascule se fait ensuite à chaud.
    """
    rythme = normaliser(rythme)
    if not auto or rythme == "vitesse":
        return bornes(rythme, mat)
    pleine = bornes("vitesse", mat)
    return Bornes("vitesse", pleine.fils, None, "normale", "haute", "normale", (),
                  ov_puce={"GPU_QUEUE_PRIORITY": "LOW", "MODEL_PRIORITY": "LOW"})


def pause(rythme: str, sur_puce: bool, auto: bool) -> float:
    """Rapport pause / calcul après chaque fenêtre (0 : aucune pause)."""
    rythme = normaliser(rythme)
    if auto and not sur_puce:
        return PAUSES_AUTO_PROCESSEUR[rythme]
    return PAUSES[(rythme, bool(sur_puce))]


# ---------------------------------------------------------------------------
# Activité du poste (fonction pure, puis capteurs Windows)
# ---------------------------------------------------------------------------

@dataclass
class Releve:
    inactivite_s: float = 1e9
    charge_autres: float = 0.0       # % du processeur entier pris par les autres, -1 : inconnue
    plein_ecran: bool = False        # plein écran ou présentation
    micro: bool = False              # micro ouvert (appel, visioconférence)
    batterie: bool = False           # portable débranché


def poste_occupe(releve: Releve, occupe_avant: bool = False) -> tuple[bool, str]:
    """Le poste sert-il ? (réponse, raison). L'ordre des raisons est celui du journal."""
    if releve.micro:
        return True, "micro"
    if releve.plein_ecran:
        return True, "plein_ecran"
    if releve.batterie:
        return True, "batterie"
    if releve.inactivite_s < SEUIL_INACTIVITE_S:
        return True, "clavier_souris"
    if releve.charge_autres < 0:
        # Charge pas encore mesurable (premier relevé) : on garde l'état d'avant.
        return occupe_avant, "charge_inconnue"
    seuil = SEUIL_CHARGE_SORTIE if occupe_avant else SEUIL_CHARGE_ENTREE
    if releve.charge_autres >= seuil:
        return True, "charge"
    return False, "repos"


def rythme_effectif(choisi: str, auto: bool, occupe: bool) -> str:
    """Rythme appliqué maintenant : le choisi, ou la vitesse maximale au repos en automatique."""
    choisi = normaliser(choisi)
    if not auto or choisi == "vitesse":
        return choisi
    return choisi if occupe else "vitesse"


def _inactivite_s() -> float:
    if sys.platform != "win32":
        return 1e9
    try:
        import ctypes
        from ctypes import wintypes

        class _Info(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = _Info()
        info.cbSize = ctypes.sizeof(_Info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 1e9
        maintenant = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((maintenant - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return 1e9


#: Valeurs de QUERY_USER_NOTIFICATION_STATE (shellapi.h) qui disent qu'une
#: application en plein écran, un jeu Direct3D exclusif ou une présentation
#: occupe l'écran.
_ETATS_PLEIN_ECRAN = (2, 3, 4)


def _plein_ecran() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        etat = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(etat)) != 0:
            return False
        return etat.value in _ETATS_PLEIN_ECRAN
    except Exception:
        return False


_CLE_MICRO = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"


def _micro_ouvert() -> bool:
    """
    Une application se sert-elle du micro en ce moment ? (appel, visioconférence)

    Windows note, par application, l'heure du dernier début et de la dernière
    fin d'usage du micro (registre de l'utilisateur, « ConsentStore ») : un
    début sans fin dit qu'il est ouvert. Seule la réponse oui ou non est
    gardée, jamais le nom de l'application.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    def ouvert(cle) -> bool:
        try:
            debut, _ = winreg.QueryValueEx(cle, "LastUsedTimeStart")
            fin, _ = winreg.QueryValueEx(cle, "LastUsedTimeStop")
            return bool(debut) and not fin
        except OSError:
            return False

    def parcourir(chemin: str, profondeur: int) -> bool:
        try:
            racine = winreg.OpenKey(winreg.HKEY_CURRENT_USER, chemin)
        except OSError:
            return False
        try:
            rang = 0
            while True:
                try:
                    nom = winreg.EnumKey(racine, rang)
                except OSError:
                    return False
                rang += 1
                try:
                    with winreg.OpenKey(racine, nom) as sous:
                        if ouvert(sous):
                            return True
                except OSError:
                    continue
                if nom == "NonPackaged" and profondeur and parcourir(chemin + "\\" + nom, 0):
                    return True
        finally:
            winreg.CloseKey(racine)

    return parcourir(_CLE_MICRO, 1)


class Capteur:
    """Relevés réels de l'activité du poste. Coûte quelques millisecondes."""

    def __init__(self):
        self._processus = None
        self._logiques = 1
        self._dernier = time.monotonic()
        try:
            import psutil  # type: ignore

            self._psutil = psutil
            self._processus = psutil.Process()
            self._logiques = psutil.cpu_count(logical=True) or 1
            psutil.cpu_percent(None)
            self._processus.cpu_percent(None)
        except Exception:
            self._psutil = None

    def __call__(self) -> Releve:
        charge = -1.0
        # psutil mesure la charge depuis l'appel précédent : sur une fenêtre de
        # moins d'une seconde, la valeur ne veut rien dire (100 % constaté).
        maintenant = time.monotonic()
        fenetre, self._dernier = maintenant - self._dernier, maintenant
        if self._psutil is not None and fenetre >= 1.0:
            try:
                total = self._psutil.cpu_percent(None)
                propre = self._processus.cpu_percent(None) / self._logiques
                charge = max(0.0, total - propre)
            except Exception:
                charge = -1.0
        from . import energie

        courant = energie.alimentation()
        return Releve(inactivite_s=_inactivite_s(), charge_autres=charge,
                      plein_ecran=_plein_ecran(), micro=_micro_ouvert(),
                      batterie=bool(courant["batterie"] and not courant["secteur"]))


# ---------------------------------------------------------------------------
# Mémoire (fonction pure)
# ---------------------------------------------------------------------------

def besoin_memoire_go(moteur: str, modele: str, lot: int) -> float:
    famille = "large-v3" if modele in ("large-v3", "large-v2") else "turbo"
    un_a_un, par_lots = BESOINS_MEMOIRE_GO.get((moteur, famille), (2.0, 3.5))
    return par_lots if lot > 1 else un_a_un


def garde_memoire(rythme: str, moteur: str, modele: str, lot: int,
                  libre_go: float, modele_leger: str) -> tuple[str, int, str]:
    """
    (modèle, lot, raison) adaptés à la mémoire libre du moment.

    En vitesse maximale, rien ne change (comportement d'avant). Sinon : les lots
    tombent à un passage à la fois quand la mémoire libre ne couvre plus leur
    besoin plus la marge ; puis, si même un à un ne tient pas, large-v3 cède
    la place au modèle léger (turbo), et le journal le dit. `libre_go` nul ou
    négatif (mesure impossible) ne change rien.
    """
    rythme = normaliser(rythme)
    if rythme == "vitesse" or libre_go <= 0:
        return modele, lot, ""
    raison = ""
    if lot > 1 and libre_go < besoin_memoire_go(moteur, modele, lot) + MARGE_MEMOIRE_GO:
        lot, raison = 0, "lots"
    if (modele in ("large-v3", "large-v2") and modele_leger
            and libre_go < besoin_memoire_go(moteur, modele, 0) + MARGE_MEMOIRE_GO):
        modele, raison = modele_leger, "modele"
    return modele, lot, raison


# ---------------------------------------------------------------------------
# Estimation de durée
# ---------------------------------------------------------------------------

FICHIER_MESURES = "modes.json"


def _mesures() -> dict:
    try:
        return json.loads((chemins.RACINE / "rapports-banc" / FICHIER_MESURES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def coefficient(rythme: str, cle_calcul: str = "", mesures: dict | None = None) -> float:
    """Durée relative à la vitesse maximale : mesurée par `banc --modes` si possible."""
    rythme = normaliser(rythme)
    if rythme == "vitesse":
        return 1.0
    donnees = _mesures() if mesures is None else mesures
    famille = "puce" if cle_calcul in ("openvino-gpu", "openvino-npu", "cuda") else "processeur"
    try:
        valeur = float(((donnees.get(famille) or {}).get(rythme) or 0))
    except (TypeError, ValueError):
        valeur = 0.0
    return valeur if valeur >= 1.0 else COEFFICIENTS_REPLI[rythme]


def coefficient_effectif(durees_avant: dict, durees_apres: dict, choisi: str,
                         cle_calcul: str = "") -> float:
    """
    Ralentissement moyen subi pendant un calcul, d'après le temps passé dans
    chaque rythme entre deux relevés du régulateur : ce par quoi diviser une
    durée mesurée pour la ramener à la vitesse maximale. Sans relevé exploitable,
    celui du rythme choisi.
    """
    passe = {nom: max(0.0, float(durees_apres.get(nom, 0.0)) - float(durees_avant.get(nom, 0.0)))
             for nom in RYTHMES}
    total = sum(passe.values())
    if total <= 0:
        return coefficient(choisi, cle_calcul)
    return sum(duree * coefficient(nom, cle_calcul) for nom, duree in passe.items()) / total


class LisseurRestant:
    """
    Lisse le reste à faire d'une transcription.

    Ce qui est lissé, c'est l'heure de fin prévue, pas la durée : entre deux
    relevés, le reste à faire décompte normalement, et un relevé isolé, plus
    lent ou plus rapide, ne déplace la fin que d'une fraction de l'écart.
    """

    def __init__(self, poids: float = 0.3):
        self.poids = poids
        self.fin: float | None = None

    def __call__(self, restant: float, maintenant: float) -> float:
        fin = maintenant + max(0.0, restant)
        self.fin = fin if self.fin is None else self.fin + self.poids * (fin - self.fin)
        return max(0.0, self.fin - maintenant)


def restant_s(estimation_s: float, ecoule_s: float, part: float) -> float:
    """
    Temps restant : l'estimation au départ, puis la vitesse observée.

    Au-delà de 10 % du fichier, la cadence réelle (qui suit les bascules de
    rythme) remplace peu à peu l'estimation ; à 30 %, elle seule compte.
    """
    prevu = max(0.0, estimation_s - ecoule_s)
    if part <= 0.10 or ecoule_s <= 0:
        return prevu
    observe = ecoule_s * (1.0 - part) / part
    poids = min(1.0, (part - 0.10) / 0.20)
    return max(0.0, (1.0 - poids) * prevu + poids * observe)


# ---------------------------------------------------------------------------
# Régulateur : applique les bornes et suit l'activité pendant une file
# ---------------------------------------------------------------------------

class Leviers:
    """Leviers du système ; remplaçables par des faux dans les vérifications."""

    def qos_seule(self, nom: str) -> None:
        """Vitesse maximale sans adaptation : seulement le HighQoS d'avant."""
        from . import energie

        if energie.poser_qos(nom):
            journal.info("Bridage d'énergie de Windows désactivé le temps du calcul")

    def rendre_qos(self) -> None:
        from . import energie

        energie.rendre_au_systeme()

    def appliquer(self, b: Bornes, avec_affinite: bool) -> None:
        from . import energie

        energie.poser_priorite(b.priorite)
        energie.poser_qos(b.qos)
        energie.poser_priorite_es(b.priorite_es)
        if avec_affinite:
            energie.poser_affinite(list(b.affinite))

    def rendre(self) -> None:
        from . import energie

        energie.poser_priorite("normale")
        energie.rendre_au_systeme()
        energie.poser_priorite_es("normale")
        energie.poser_affinite(None)


class Regulateur:
    """
    Le rythme d'une file de traitement.

    Sans adaptation : pose les bornes du rythme choisi au début, les rend au
    système à la fin. Avec adaptation : relève l'activité toutes les trois
    secondes dans un fil à part, et bascule priorité, qualité de service et
    pauses entre le rythme choisi (poste occupé) et la vitesse maximale (poste
    au repos). `evaluer` fait un relevé à la demande : c'est par lui que les
    vérifications simulent l'activité.
    """

    def __init__(self, mat: Materiel, choisi: str, auto: bool,
                 capteur: Callable[[], Releve] | None = None,
                 leviers: Leviers | None = None,
                 horloge: Callable[[], float] = time.monotonic,
                 sur_bascule: Callable[[str, str], None] | None = None):
        self.materiel = mat
        self.choisi = normaliser(choisi)
        self.auto = bool(auto) and self.choisi != "vitesse"
        self.capteur = capteur
        self.leviers = leviers or Leviers()
        self.horloge = horloge
        self.sur_bascule = sur_bascule
        self.sur_puce = False
        self.occupe = True
        self.raison = ""
        self.effectif = self.choisi if not self.auto else "vitesse"
        self.durees: dict[str, float] = {r: 0.0 for r in RYTHMES}
        self.bascules = 0
        self._depuis = horloge()
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._verrou = threading.Lock()

    @property
    def leger(self) -> bool:
        return not self.auto and self.choisi == "vitesse"

    @property
    def chargement(self) -> Bornes:
        return bornes_chargement(self.choisi, self.auto, self.materiel)

    def demarrer(self, interrompu: Callable[[], bool] | None = None, suivre: bool = True) -> None:
        """`suivre` à faux : pas de fil de relevés (les vérifications appellent `evaluer`)."""
        if self.auto:
            # Prudence au départ : le rythme choisi tant qu'aucun relevé n'a parlé.
            self.effectif, self.occupe = self.choisi, True
        self._depuis = self.horloge()
        if self.leger:
            # Vitesse maximale sans adaptation : exactement ce que faisait la
            # file avant la 3.0 (HighQoS), ni priorité ni affinité touchées.
            self.leviers.qos_seule("haute")
        else:
            self.leviers.appliquer(bornes(self.effectif, self.materiel) if self.auto
                                   else self.chargement, avec_affinite=not self.auto)
        if self.auto:
            if self.capteur is None:
                self.capteur = Capteur()
            self.evaluer()
            if suivre:
                self._arret.clear()
                self._fil = threading.Thread(target=self._boucle, daemon=True)
                self._fil.start()

    def _boucle(self) -> None:
        while not self._arret.wait(INTERVALLE_S):
            try:
                self.evaluer()
            except Exception as exc:  # pragma: no cover - capteur défaillant
                journal.debug("Relevé d'activité impossible : %s", exc)

    def evaluer(self, releve: Releve | None = None) -> str:
        """Un relevé, une décision ; renvoie le rythme effectif."""
        if not self.auto:
            return self.effectif
        if releve is None:
            releve = self.capteur() if self.capteur else Releve()
        occupe, raison = poste_occupe(releve, self.occupe)
        nouveau = rythme_effectif(self.choisi, True, occupe)
        with self._verrou:
            self.occupe, self.raison = occupe, raison
            if nouveau != self.effectif:
                self._compter()
                ancien, self.effectif = self.effectif, nouveau
                self.bascules += 1
                b = bornes(nouveau, self.materiel)
                self.leviers.appliquer(b, avec_affinite=False)
                journal.info("Rythme : %s vers %s (%s)", ancien, nouveau, raison)
                if self.sur_bascule:
                    self.sur_bascule(nouveau, raison)
        return self.effectif

    def _compter(self) -> None:
        maintenant = self.horloge()
        self.durees[self.effectif] += max(0.0, maintenant - self._depuis)
        self._depuis = maintenant

    def releve_durees(self) -> dict[str, float]:
        """Temps passé dans chaque rythme jusqu'à maintenant (pour la calibration)."""
        with self._verrou:
            self._compter()
            return dict(self.durees)

    def rapport_pause(self) -> float:
        # `sur_puce` peut être une fonction : après un repli d'OpenVINO sur
        # CTranslate2, le calcul quitte la puce graphique en cours de fichier.
        puce = self.sur_puce() if callable(self.sur_puce) else self.sur_puce
        return pause(self.effectif, bool(puce), self.auto)

    def frein(self, calcul_s: float, interrompu: Callable[[], bool] | None = None) -> float:
        """Pause après un morceau de calcul de `calcul_s` secondes ; renvoie la pause faite."""
        attente = min(PAUSE_MAX_S, max(0.0, calcul_s) * self.rapport_pause())
        fin = time.monotonic() + attente
        while attente > 0 and time.monotonic() < fin:
            if interrompu is not None and interrompu():
                break
            time.sleep(min(0.25, max(0.0, fin - time.monotonic())))
        return attente

    def arreter(self) -> dict:
        """Rend la main au système ; renvoie le temps passé dans chaque rythme."""
        self._arret.set()
        if self._fil is not None:
            self._fil.join(timeout=INTERVALLE_S + 1)
        with self._verrou:
            self._compter()
        if self.leger:
            self.leviers.rendre_qos()
        else:
            self.leviers.rendre()
        return {"durees": dict(self.durees), "bascules": self.bascules}


class Frein:
    """Pause entre deux morceaux de calcul, côté moteur : chronomètre puis `regulateur.frein`."""

    def __init__(self, regulateur: Regulateur | None, interrompu: Callable[[], bool] | None = None):
        self.regulateur = regulateur
        self.interrompu = interrompu
        self._depart = time.monotonic()

    def depart(self) -> None:
        self._depart = time.monotonic()

    def __call__(self) -> None:
        if self.regulateur is None:
            return
        calcul = time.monotonic() - self._depart
        self.regulateur.frein(calcul, self.interrompu)
        self._depart = time.monotonic()
