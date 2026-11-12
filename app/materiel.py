"""
Détection du matériel et recommandation.

Objectif : afficher honnêtement ce que la machine sait faire, et rien de plus.
CTranslate2 (le moteur de faster-whisper) n'accélère que sur NVIDIA. Les puces
graphiques et les NPU d'Intel peuvent servir par le moteur OpenVINO, en option
(voir `app/moteur_openvino.py`) ; les cartes AMD restent affichées sans être
exploitées.

Processeurs hybrides
--------------------
Depuis la 12e génération, les processeurs Intel mêlent des cœurs performants et
des cœurs efficaces, et les puces mobiles récentes (Core Ultra série U) ajoutent
des cœurs « basse consommation » placés hors du cache L3 commun. Windows décrit
tout cela par `GetLogicalProcessorInformationEx` : la classe d'efficacité de
chaque cœur et les processeurs logiques que partage chaque cache. On en tire le
décompte des trois familles (`Topologie`), qui sert au nombre de fils de calcul
et au banc d'essai.

Aucune dependance obligatoire : psutil est utilise s'il est present, sinon on
retombe sur la bibliotheque standard et sur l'API Windows via ctypes.

Démarrage
---------
Ce qui se lit en quelques millisecondes (processeur, cœurs, mémoire, batterie)
est relu à chaque lancement. Le reste (cartes graphiques, NPU, CUDA,
périphériques d'OpenVINO) coûtait une à deux secondes avant d'ouvrir la
fenêtre : il est gardé dans `materiel.json`, servi tel quel au lancement, et
rafraîchi après l'affichage par un processus de fond (`--detecter-materiel`),
qui charge OpenVINO à la place de la fenêtre. Les cartes se lisent par WMI dans
le processus (module `_wmi` de Python), les NPU par SetupAPI : plus de
PowerShell, ni sa minute d'analyse antivirus sur un poste d'entreprise.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import chemins, journal, langues

_CACHE: "Materiel | None" = None

#: Ce que la détection lente a trouvé, gardé d'un lancement à l'autre.
NOM_CACHE_DISQUE = "materiel.json"
VERSION_CACHE = 1

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Seuils de mémoire vive, en gigaoctets.
# 16 Go tient pour large-v3 en int8 plus la diarisation, à condition de séquencer
# les deux étapes (voir moteur.py). En dessous de 10 Go on déconseille large-v3.
SEUIL_MEMOIRE_CONFORTABLE = 20.0
SEUIL_MEMOIRE_CRITIQUE = 10.0


@dataclass
class Gpu:
    nom: str
    vendeur: str  # "nvidia" | "amd" | "intel" | "autre"
    memoire_mo: int = 0
    accelere: bool = False
    #: Version du pilote, telle que Windows la déclare (« 32.0.101.8801 »).
    pilote: str = ""
    #: Cle de traduction de la note, resolue a l'affichage. Le materiel est
    #: detecte une fois pour toutes, la langue peut changer ensuite.
    note_cle: str = ""


@dataclass
class Accelerateur:
    """Circuit d'accélération détecté (NPU), exploitable seulement par OpenVINO."""

    nom: str
    genre: str = "npu"
    note_cle: str = ""


@dataclass
class Topologie:
    """
    Décompte des cœurs par famille, tel que Windows le décrit.

    `performants` : cœurs de la classe d'efficacité la plus haute (P-cores).
    `efficaces` : autres cœurs qui partagent le cache L3 (E-cores).
    `basse_consommation` : cœurs hors de tout cache L3 (LP E-cores des Core Ultra
    série U), nettement plus lents. Sur un processeur homogène, tout est compté
    en `performants` et `hybride` reste faux.
    """

    performants: int = 0
    efficaces: int = 0
    basse_consommation: int = 0
    hybride: bool = False
    #: Processeurs logiques des cœurs performants et efficaces : de quoi borner
    #: l'affinité du calcul pour écarter les cœurs basse consommation.
    logiques_principaux: list[int] = field(default_factory=list)
    #: Processeurs logiques des seuls cœurs performants, puis des seuls cœurs
    #: efficaces : le mode « discret » range le calcul sur les seconds et laisse
    #: les premiers à l'utilisateur (voir `app/rythme.py`).
    logiques_performants: list[int] = field(default_factory=list)
    logiques_efficaces: list[int] = field(default_factory=list)

    @property
    def coeurs_principaux(self) -> int:
        return self.performants + self.efficaces


@dataclass
class Materiel:
    cpu_nom: str = ""
    coeurs_physiques: int = 0
    coeurs_logiques: int = 0
    topologie: Topologie = field(default_factory=Topologie)
    #: Processeur mobile basse consommation (suffixe U ou V), 15 W environ.
    basse_consommation: bool = False
    #: Portable : une batterie est présente.
    portable: bool = False
    #: Nombre de fils imposé par un réglage mesuré sur ce poste (banc d'essai),
    #: 0 pour le choix automatique.
    fils_imposes: int = 0
    #: Moteur retenu pour ce poste : « ctranslate2 » (défaut) ou « openvino »,
    #: et périphérique d'OpenVINO (« CPU », « GPU », « NPU »). Posés par le
    #: réglage machine (`app/reglage_machine.py`), jamais devinés.
    moteur: str = "ctranslate2"
    peripherique_openvino: str = ""
    ram_go: float = 0.0
    ram_libre_go: float = 0.0
    gpus: list[Gpu] = field(default_factory=list)
    npus: list[Accelerateur] = field(default_factory=list)
    a_nvidia: bool = False
    cuda_disponible: bool = False
    systeme: str = ""

    @property
    def peripherique(self) -> str:
        return "cuda" if self.cuda_disponible else "cpu"

    @property
    def type_calcul(self) -> str:
        return "float16" if self.cuda_disponible else "int8"

    @property
    def cle_calcul(self) -> str:
        """
        Situation de calcul, telle que les mesures de durée la rangent.

        « cpu » ou « cuda » avec CTranslate2, « openvino-gpu » et consorts avec
        OpenVINO : les vitesses n'ont rien de commun d'un moteur à l'autre.
        """
        if self.moteur == "openvino" and self.peripherique_openvino:
            return "openvino-" + self.peripherique_openvino.lower()
        return self.peripherique

    @property
    def fils_calcul(self) -> int:
        """
        Un fil de calcul par coeur PHYSIQUE quand le processeur double ses coeurs.

        CTranslate2 le recommande dans son guide de performance : ne pas depasser
        le nombre de coeurs physiques. Mesure sur un 8 coeurs / 16 fils occupe
        par d'autres programmes : 8 fils transcrivent aussi vite que 14, voire
        plus, en laissant la moitie du processeur au reste de la machine. Sans
        hyperthreading, on laisse deux coeurs au systeme, comme avant.

        Processeur hybride à trois familles (Core Ultra série U : 2 performants,
        8 efficaces, 2 basse consommation) : un fil par cœur performant ou
        efficace, les cœurs basse consommation à part. Ils plafonnent à 2,4 GHz
        et n'ont pas de cache L3 ; CTranslate2 partage le travail à parts égales
        entre ses fils, et le plus lent fixe la cadence. C'est un choix par
        défaut raisonné, pas une mesure : le banc d'essai (`app/banc.py`) le
        vérifie sur la machine et peut en imposer un autre (`fils_imposes`).
        """
        total = self.coeurs_logiques or os.cpu_count() or 4
        if self.fils_imposes > 0:
            return max(1, min(self.fils_imposes, total))
        topo = self.topologie
        if topo.hybride and topo.basse_consommation and topo.coeurs_principaux:
            return max(1, min(total, topo.coeurs_principaux))
        if 0 < self.coeurs_physiques < total:
            return self.coeurs_physiques
        return max(1, total - 2)

    @property
    def fils_automatiques(self) -> int:
        """Nombre de fils hors de tout réglage imposé."""
        impose, self.fils_imposes = self.fils_imposes, 0
        try:
            return self.fils_calcul
        finally:
            self.fils_imposes = impose

    def en_dict(self) -> dict:
        donnees = asdict(self)
        # Les notes sont traduites ici, pas à la détection : une bascule de
        # langue doit les changer sans relancer l'inspection du matériel.
        for carte in donnees.get("gpus") or []:
            carte["note"] = langues.t(carte["note_cle"]) if carte.get("note_cle") else ""
        for circuit in donnees.get("npus") or []:
            circuit["note"] = langues.t(circuit["note_cle"]) if circuit.get("note_cle") else ""
        donnees["peripherique"] = self.peripherique
        donnees["cle_calcul"] = self.cle_calcul
        donnees["fils_automatiques"] = self.fils_automatiques
        donnees["type_calcul"] = self.type_calcul
        donnees["fils_calcul"] = self.fils_calcul
        donnees["resume"] = self.resume()
        donnees["memoire_serree"] = self.memoire_serree
        donnees["memoire_tres_serree"] = self.memoire_tres_serree
        return donnees

    @property
    def memoire_serree(self) -> bool:
        """Sous 20 Go, large-v3 plus diarisation demande de la prudence."""
        return 0 < self.ram_go < SEUIL_MEMOIRE_CONFORTABLE

    @property
    def memoire_tres_serree(self) -> bool:
        """Sous 10 Go, large-v3 n'est pas raisonnable."""
        return 0 < self.ram_go < SEUIL_MEMOIRE_CRITIQUE

    def resume(self) -> str:
        morceaux = [self.cpu_nom or langues.t("mat.cpu_inconnu")]
        topo = self.topologie
        if topo.hybride and self.coeurs_logiques:
            cle = "mat.hybride_trois" if topo.basse_consommation else "mat.hybride_deux"
            morceaux.append(langues.t(
                cle, p=topo.performants, e=topo.efficaces, lp=topo.basse_consommation,
                fils=self.coeurs_logiques,
            ))
        elif self.coeurs_logiques:
            if self.coeurs_physiques and self.coeurs_physiques != self.coeurs_logiques:
                morceaux.append(langues.t(
                    "mat.coeurs_fils",
                    coeurs=self.coeurs_physiques, fils=self.coeurs_logiques,
                ))
            else:
                morceaux.append(langues.t("mat.fils", n=self.coeurs_logiques))
        if self.ram_go:
            morceaux.append(langues.t("mat.memoire", go=f"{self.ram_go:.0f}"))
        if self.cuda_disponible:
            nvidia = next((g for g in self.gpus if g.vendeur == "nvidia"), None)
            morceaux.append(langues.t(
                "mat.gpu_accelere", nom=nvidia.nom if nvidia else "GPU NVIDIA"))
        elif self.gpus:
            morceaux.append(langues.t("mat.gpu_non_accelere", nom=self.gpus[0].nom))
        else:
            morceaux.append(langues.t("mat.sans_gpu"))
        if self.npus:
            morceaux.append(langues.t("mat.npu_non_exploite", nom=self.npus[0].nom))
        return ", ".join(morceaux)

    def a_graphique_intel(self) -> bool:
        """Puce ou carte graphique Intel présente, cible du plugin GPU d'OpenVINO."""
        return any(g.vendeur == "intel" for g in self.gpus)


# ---------------------------------------------------------------------------
# Collecte
# ---------------------------------------------------------------------------

def _nom_cpu() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            cle = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            valeur, _ = winreg.QueryValueEx(cle, "ProcessorNameString")
            winreg.CloseKey(cle)
            nom = " ".join(str(valeur).split())
            if nom:
                return nom
        except OSError:
            pass
    # Chaîne vide plutôt qu'un libellé figé : `Materiel.resume` traduit le repli
    # au moment de l'affichage, dans la langue de l'interface du moment.
    return platform.processor() or platform.machine() or ""


def _coeurs() -> tuple[int, int]:
    logiques = os.cpu_count() or 0
    physiques = 0
    try:
        import psutil  # type: ignore

        physiques = psutil.cpu_count(logical=False) or 0
        logiques = psutil.cpu_count(logical=True) or logiques
    except Exception:
        pass
    return physiques, logiques


# ---------------------------------------------------------------------------
# Topologie du processeur (GetLogicalProcessorInformationEx)
#
# Disposition des structures, d'après la documentation de winnt.h :
#   SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX : Relationship (DWORD), Size (DWORD),
#     puis l'union, à l'octet 8.
#   PROCESSOR_RELATIONSHIP : Flags (BYTE), EfficiencyClass (BYTE) à l'octet 9,
#     RelativePerformance et RelativeEfficiency (WORD), Reserved[16],
#     GroupCount (WORD) à l'octet 30, GroupMask[] à l'octet 32.
#   CACHE_RELATIONSHIP : Level (BYTE) à l'octet 8, ..., GroupCount (WORD) à
#     l'octet 38 (zéro sur les systèmes antérieurs, qui n'ont qu'un masque),
#     GroupMask[] à l'octet 40.
#   GROUP_AFFINITY : Mask (8 octets), Group (WORD), Reserved[3] : 16 octets.
# ---------------------------------------------------------------------------

_RELATION_COEUR = 0
_RELATION_CACHE = 2
_RELATION_TOUT = 0xFFFF


def _masques(tampon: bytes, debut: int, fin: int, nombre: int) -> set[int]:
    logiques: set[int] = set()
    for rang in range(max(1, nombre)):
        position = debut + 16 * rang
        if position + 10 > fin:
            break
        masque, groupe = struct.unpack_from("<QH", tampon, position)
        logiques |= {groupe * 64 + bit for bit in range(64) if masque >> bit & 1}
    return logiques


def analyser_topologie(tampon: bytes) -> Topologie:
    """
    Décompte des familles de cœurs à partir du tampon brut de Windows.

    Fonction pure, sans appel système : la vérification la nourrit d'un tampon
    fabriqué pour un Core Ultra 5 225U, qu'aucun poste de test n'a sous la main.
    """
    coeurs: list[tuple[int, set[int]]] = []
    caches_l3: list[set[int]] = []
    position = 0
    while position + 8 <= len(tampon):
        relation, taille = struct.unpack_from("<II", tampon, position)
        if taille < 8 or position + taille > len(tampon):
            break
        fin = position + taille
        if relation == _RELATION_COEUR and taille >= 48:
            classe = tampon[position + 9]
            nombre = struct.unpack_from("<H", tampon, position + 30)[0]
            coeurs.append((classe, _masques(tampon, position + 32, fin, nombre)))
        elif relation == _RELATION_CACHE and taille >= 56 and tampon[position + 8] == 3:
            nombre = struct.unpack_from("<H", tampon, position + 38)[0]
            caches_l3.append(_masques(tampon, position + 40, fin, nombre))
        position = fin

    topo = Topologie()
    if not coeurs:
        return topo
    classes = {classe for classe, _ in coeurs}
    haute = max(classes)
    couverts = set().union(*caches_l3) if caches_l3 else set()
    hybride = len(classes) > 1
    principaux: list[int] = []
    performants: list[int] = []
    efficaces: list[int] = []
    for classe, logiques in coeurs:
        if hybride and classe != haute and couverts and not (logiques & couverts):
            topo.basse_consommation += 1
            continue
        if hybride and classe != haute:
            topo.efficaces += 1
            efficaces += sorted(logiques)
        else:
            topo.performants += 1
            performants += sorted(logiques)
        principaux += sorted(logiques)
    if hybride and topo.basse_consommation and not topo.efficaces:
        # Deux familles seulement, dont l'une hors du L3 (Lunar Lake : ses cœurs
        # efficaces ont leur propre cache). Ce ne sont pas des cœurs d'appoint :
        # ils comptent comme efficaces.
        topo.efficaces, topo.basse_consommation = topo.basse_consommation, 0
        principaux = sorted(set().union(*(logiques for _, logiques in coeurs)))
        efficaces = sorted(set(principaux) - set(performants))
    topo.hybride = hybride
    topo.logiques_principaux = sorted(principaux)
    if hybride:
        topo.logiques_performants = sorted(performants)
        topo.logiques_efficaces = sorted(efficaces)
    return topo


def _topologie() -> Topologie:
    if sys.platform != "win32":
        return Topologie()
    try:
        import ctypes
        from ctypes import wintypes

        noyau = ctypes.WinDLL("kernel32", use_last_error=True)
        fonction = noyau.GetLogicalProcessorInformationEx
        fonction.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        fonction.restype = wintypes.BOOL
        taille = wintypes.DWORD(0)
        fonction(_RELATION_TOUT, None, ctypes.byref(taille))
        if not taille.value:
            return Topologie()
        tampon = ctypes.create_string_buffer(taille.value)
        if not fonction(_RELATION_TOUT, tampon, ctypes.byref(taille)):
            return Topologie()
        return analyser_topologie(tampon.raw[: taille.value])
    except Exception as exc:  # pragma: no cover - dépend du poste
        journal.debug("Topologie du processeur illisible : %s", exc)
        return Topologie()


#: Processeurs mobiles basse consommation : suffixe U ou V (Intel « 1255U »,
#: « 225U », « 258V » ; AMD « 7530U »). Autour de 15 W de puissance de base,
#: contre 65 à 120 W pour un processeur de bureau.
_BASSE_CONSOMMATION = re.compile(r"\b\d{3,5}[UV]\b")


def est_basse_consommation(nom_cpu: str) -> bool:
    return bool(_BASSE_CONSOMMATION.search(nom_cpu or ""))


def _portable() -> bool:
    try:
        import psutil  # type: ignore

        return psutil.sensors_battery() is not None
    except Exception:
        return False


def _memoire() -> tuple[float, float]:
    """Renvoie (total, libre) en Go."""
    try:
        import psutil  # type: ignore

        memoire = psutil.virtual_memory()
        return memoire.total / 1024 ** 3, memoire.available / 1024 ** 3
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes

            class _Statut(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            statut = _Statut()
            statut.dwLength = ctypes.sizeof(_Statut)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(statut))
            return statut.ullTotalPhys / 1024 ** 3, statut.ullAvailPhys / 1024 ** 3
        except Exception:
            pass

    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        taille = os.sysconf("SC_PAGE_SIZE")
        total = pages * taille / 1024 ** 3
        return total, total
    except (ValueError, AttributeError, OSError):
        return 0.0, 0.0


def _vendeur(nom: str, fabricant: str = "") -> str:
    texte = f"{nom} {fabricant}".lower()
    if "nvidia" in texte or "geforce" in texte or "quadro" in texte or "rtx" in texte:
        return "nvidia"
    if "advanced micro" in texte or "amd" in texte or "radeon" in texte:
        return "amd"
    if "intel" in texte or "arc(" in texte or "uhd graphics" in texte or "iris" in texte:
        return "intel"
    return "autre"


#: Adaptateurs d'affichage qui ne sont pas des cartes : écrans virtuels posés par
#: les logiciels de bureau à distance ou de diffusion (Parsec, Sunshine et ses
#: dérivés), pilote d'affichage de base de Windows. Les montrer comme « carte
#: graphique » trompe l'utilisateur, et c'est le premier de la liste que le
#: résumé du matériel affiche.
_ADAPTATEURS_VIRTUELS = re.compile(
    r"virtual|basic (display|render)|remote display|mirror|indirect display|dummy",
    re.IGNORECASE,
)

#: AdapterRAM est un entier 32 bits côté WMI : toute carte de 4 Go ou plus y
#: plafonne à 4095 Mo. La vraie valeur est dans le registre du pilote.
_PLAFOND_ADAPTER_RAM_MO = 4095

_CLE_CLASSE_AFFICHAGE = (
    r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
)


def _memoires_registre() -> dict[str, int]:
    """Mémoire dédiée par nom de carte, en Mo, lue dans la clé du pilote."""
    trouves: dict[str, int] = {}
    if sys.platform != "win32":
        return trouves
    try:
        import winreg

        classe = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CLE_CLASSE_AFFICHAGE)
    except OSError:
        return trouves
    try:
        index = 0
        while True:
            try:
                nom_sous_cle = winreg.EnumKey(classe, index)
            except OSError:
                break
            index += 1
            try:
                with winreg.OpenKey(classe, nom_sous_cle) as cle:
                    description, _ = winreg.QueryValueEx(cle, "DriverDesc")
                    taille, _ = winreg.QueryValueEx(cle, "HardwareInformation.qwMemorySize")
            except OSError:
                continue
            try:
                if isinstance(taille, bytes):
                    taille = int.from_bytes(taille[:8], "little")
                trouves[str(description).strip()] = int(taille) // (1024 * 1024)
            except (TypeError, ValueError):
                continue
    finally:
        winreg.CloseKey(classe)
    return trouves


def _rang_carte(carte: Gpu) -> tuple:
    """Ordre d'affichage : carte dédiée d'abord, la plus dotée en mémoire en tête."""
    priorite = {"nvidia": 0, "amd": 1, "intel": 2}.get(carte.vendeur, 3)
    return (priorite, -carte.memoire_mo)


def _requete_wmi(requete: str) -> list[dict]:
    """
    Requête WMI dans le processus (module `_wmi` de CPython 3.12), sans
    PowerShell. Lève une exception si le module manque : on se rabat alors sur
    PowerShell.
    """
    import _wmi  # type: ignore

    lignes = []
    for bloc in _wmi.exec_query(requete).split("\0\0"):
        ligne = {}
        for champ in bloc.split("\0"):
            cle, egal, valeur = champ.partition("=")
            if egal:
                ligne[cle] = valeur
        if ligne:
            lignes.append(ligne)
    return lignes


def _cartes_wmi() -> list[dict]:
    try:
        return _requete_wmi(
            "SELECT Name,AdapterCompatibility,AdapterRAM,DriverVersion FROM Win32_VideoController")
    except Exception as exc:
        journal.debug("WMI indisponible pour les cartes graphiques (%s), repli sur PowerShell", exc)
    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterCompatibility,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress",
    ]
    resultat = subprocess.run(
        commande, capture_output=True, text=True, timeout=20,
        creationflags=_SANS_FENETRE,
    )
    sortie = (resultat.stdout or "").strip()
    if not sortie:
        return []
    import json

    donnees = json.loads(sortie)
    return [donnees] if isinstance(donnees, dict) else list(donnees)


def _cartes_graphiques() -> list[Gpu]:
    cartes: list[Gpu] = []
    if sys.platform != "win32":
        return cartes

    try:
        donnees = _cartes_wmi()
        if donnees:
            registre = _memoires_registre()
            for entree in donnees:
                nom = (entree.get("Name") or "").strip()
                if not nom:
                    continue
                if _ADAPTATEURS_VIRTUELS.search(nom):
                    journal.debug("Adaptateur virtuel ignoré : %s", nom)
                    continue
                fabricant = (entree.get("AdapterCompatibility") or "").strip()
                ram = entree.get("AdapterRAM") or 0
                try:
                    # WMI dans le processus rend cet entier non signé de 32 bits
                    # avec son signe : on le remet tel que PowerShell le montrait.
                    octets = int(ram)
                    memoire_mo = max(0, (octets + 2 ** 32 if octets < 0 else octets) // (1024 * 1024))
                except (TypeError, ValueError):
                    memoire_mo = 0
                if registre.get(nom):
                    memoire_mo = registre[nom]
                elif memoire_mo >= _PLAFOND_ADAPTER_RAM_MO:
                    # Valeur plafonnée par WMI : mieux vaut ne rien afficher
                    # qu'annoncer 4 Go pour une carte qui en a 20.
                    memoire_mo = 0
                cartes.append(Gpu(nom=nom, vendeur=_vendeur(nom, fabricant), memoire_mo=memoire_mo,
                                  pilote=str(entree.get("DriverVersion") or "").strip()))
    except Exception as exc:  # pragma: no cover - depend du poste
        journal.debug("Detection GPU impossible : %s", exc)

    cartes.sort(key=_rang_carte)
    return cartes


#: Motif volontairement strict : un « NPU » non délimité attrape « Input ».
_MOTIF_NPU = re.compile(r"AI Boost|Neural Processor|\bNPU\b|XDNA|Hexagon NPU")


def _noms_peripheriques_presents() -> list[str]:
    """
    Noms de tous les périphériques présents, comme `Win32_PnPEntity.Name` :
    le nom convivial s'il existe, la description sinon. Lu par SetupAPI, dans
    le processus, en quelques dizaines de millisecondes.
    """
    import ctypes
    from ctypes import wintypes

    class _InfoPeripherique(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", ctypes.c_byte * 16),
                    ("DevInst", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    setupapi.SetupDiEnumDeviceInfo.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_InfoPeripherique)]
    setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(_InfoPeripherique), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    presents_toutes_classes = 0x2 | 0x4          # DIGCF_PRESENT | DIGCF_ALLCLASSES
    nom_convivial, description = 0x0C, 0x00      # SPDRP_FRIENDLYNAME, SPDRP_DEVICEDESC
    liste = setupapi.SetupDiGetClassDevsW(None, None, None, presents_toutes_classes)
    if not liste or liste == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevsW")
    noms: list[str] = []
    tampon = ctypes.create_unicode_buffer(512)
    try:
        rang = 0
        while True:
            info = _InfoPeripherique()
            info.cbSize = ctypes.sizeof(_InfoPeripherique)
            if not setupapi.SetupDiEnumDeviceInfo(liste, rang, ctypes.byref(info)):
                break
            rang += 1
            for propriete in (nom_convivial, description):
                if setupapi.SetupDiGetDeviceRegistryPropertyW(
                        liste, ctypes.byref(info), propriete, None, tampon, ctypes.sizeof(tampon), None):
                    noms.append(tampon.value.strip())
                    break
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(liste)
    return noms


def _noms_npu_powershell() -> list[str]:
    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.Name -match 'AI Boost|Neural Processor|\\bNPU\\b|XDNA|Hexagon NPU' } | "
        "Select-Object -ExpandProperty Name -Unique",
    ]
    resultat = subprocess.run(
        commande, capture_output=True, text=True, timeout=25,
        creationflags=_SANS_FENETRE,
    )
    return [ligne.strip() for ligne in (resultat.stdout or "").splitlines() if ligne.strip()]


def _accelerateurs_neuronaux() -> list[Accelerateur]:
    """
    Repère un NPU (Intel AI Boost des Core Ultra, AMD XDNA, Qualcomm Hexagon).

    Seul celui d'Intel peut servir, par le moteur OpenVINO et à titre
    expérimental. Les autres sont affichés pour information.
    """
    trouves: list[Accelerateur] = []
    if sys.platform != "win32":
        return trouves

    try:
        try:
            noms = [n for n in dict.fromkeys(_noms_peripheriques_presents()) if _MOTIF_NPU.search(n)]
        except Exception as exc:
            journal.debug("SetupAPI indisponible (%s), repli sur PowerShell", exc)
            noms = _noms_npu_powershell()
        for nom in noms:
            if not nom:
                continue
            intel = "intel" in nom.lower() or "ai boost" in nom.lower()
            trouves.append(Accelerateur(
                nom=nom, genre="npu", note_cle="npu.note.intel" if intel else "npu.note"))
    except Exception as exc:  # pragma: no cover - depend du poste
        journal.debug("Detection NPU impossible : %s", exc)

    return trouves


def _nvidia_present() -> bool:
    """Detection sans torch : la presence de nvidia-smi signe le pilote NVIDIA."""
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        resultat = subprocess.run(
            ["nvidia-smi"], capture_output=True, timeout=15, creationflags=_SANS_FENETRE
        )
        return resultat.returncode == 0
    except Exception:
        return False


def _cuda_utilisable() -> bool:
    """CTranslate2 voit-il vraiment un peripherique CUDA exploitable ?"""
    try:
        import ctranslate2  # type: ignore

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def detection_lente() -> dict:
    """
    Ce qui coûte : cartes graphiques, NPU, NVIDIA et CUDA. Renvoie un
    dictionnaire tel qu'il est gardé dans `materiel.json`.
    """
    cartes = _cartes_graphiques()
    neuronaux = _accelerateurs_neuronaux()
    nvidia = any(c.vendeur == "nvidia" for c in cartes) or _nvidia_present()
    cuda = nvidia and _cuda_utilisable()

    for carte in cartes:
        if carte.vendeur == "nvidia":
            carte.accelere = cuda
            carte.note_cle = "gpu.note.cuda_active" if cuda else "gpu.note.cuda_absente"
        elif carte.vendeur == "amd":
            carte.note_cle = "gpu.note.amd"
        elif carte.vendeur == "intel":
            carte.note_cle = "gpu.note.intel"
        else:
            carte.note_cle = "gpu.note.autre"
    return {"gpus": [asdict(c) for c in cartes], "npus": [asdict(n) for n in neuronaux],
            "a_nvidia": nvidia, "cuda_disponible": cuda}


def _assembler(lent: dict) -> Materiel:
    """La partie rapide, lue maintenant, plus la partie lente donnée."""
    physiques, logiques = _coeurs()
    topologie = _topologie()
    total, libre = _memoire()
    nom_cpu = _nom_cpu()
    return Materiel(
        cpu_nom=nom_cpu,
        coeurs_physiques=physiques,
        coeurs_logiques=logiques,
        topologie=topologie,
        basse_consommation=est_basse_consommation(nom_cpu),
        portable=_portable(),
        ram_go=total,
        ram_libre_go=libre,
        gpus=[Gpu(**g) for g in lent.get("gpus") or []],
        npus=[Accelerateur(**n) for n in lent.get("npus") or []],
        a_nvidia=bool(lent.get("a_nvidia")),
        cuda_disponible=bool(lent.get("cuda_disponible")),
        systeme=f"{platform.system()} {platform.release()}",
    )


def detecter(forcer: bool = False) -> Materiel:
    """Détection complète, dans ce processus (outils de mesure, ligne de commande)."""
    global _CACHE
    if _CACHE is not None and not forcer:
        return _CACHE
    _CACHE = _assembler(detection_lente())
    _journaliser(_CACHE)
    return _CACHE


def _journaliser(mat: Materiel) -> None:
    topologie = mat.topologie
    journal.info("Matériel : %s", mat.resume())
    if topologie.hybride:
        journal.info(
            "Processeur hybride : %s performants, %s efficaces, %s basse consommation",
            topologie.performants, topologie.efficaces, topologie.basse_consommation)
    journal.info(
        "Profil retenu : périphérique=%s, type de calcul=%s, fils=%s",
        mat.peripherique, mat.type_calcul, mat.fils_calcul,
    )


# ---------------------------------------------------------------------------
# Démarrage de la fenêtre : la détection lente gardée sur disque
# ---------------------------------------------------------------------------

def fichier_cache() -> Path:
    return chemins.RACINE / NOM_CACHE_DISQUE


def lire_cache() -> dict | None:
    """Le dernier résultat de la détection lente, ou None s'il manque ou ne se lit pas."""
    import json

    try:
        donnees = json.loads(fichier_cache().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(donnees, dict) or donnees.get("version") != VERSION_CACHE:
        return None
    return donnees


def ecrire_cache(lent: dict) -> None:
    import json

    cible = fichier_cache()
    temporaire = cible.with_name(cible.name + ".tmp")
    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        temporaire.write_text(json.dumps({"version": VERSION_CACHE, **lent}, ensure_ascii=False, indent=1),
                              encoding="utf-8")
        os.replace(temporaire, cible)
    except OSError as exc:
        journal.debug("Cache du matériel non écrit : %s", exc)


def detection_complete_pour_cache() -> dict:
    """Détection lente, plus les périphériques d'OpenVINO s'il est installé."""
    lent = detection_lente()
    ov = {"installe": False, "version": "", "peripheriques": []}
    try:
        from . import moteur_openvino

        if moteur_openvino.installe():
            ov = {"installe": True, "version": moteur_openvino.version(),
                  "peripheriques": moteur_openvino.peripheriques_disponibles(forcer=True)}
    except Exception as exc:  # pragma: no cover - dépend du poste
        journal.debug("OpenVINO non interrogé : %s", exc)
    lent["openvino"] = ov
    return lent


def detecter_au_demarrage() -> tuple[Materiel, bool]:
    """
    Matériel pour ouvrir la fenêtre sans attendre : la partie rapide lue
    maintenant, la partie lente reprise du dernier lancement. Renvoie aussi
    vrai si rien n'était gardé (premier lancement) : le matériel est alors
    provisoire, sans cartes ni NPU, jusqu'au rafraîchissement de fond.

    Les périphériques d'OpenVINO gardés sont confiés au moteur, s'ils valent
    pour l'installation présente : la fenêtre n'a pas à charger OpenVINO.
    """
    global _CACHE
    lent = lire_cache()
    _CACHE = _assembler(lent or {})
    ov_connu = True
    try:
        from . import moteur_openvino

        ov = (lent or {}).get("openvino") or {}
        if lent and bool(ov.get("installe")) == moteur_openvino.installe():
            moteur_openvino.amorcer(str(ov.get("version") or ""), list(ov.get("peripheriques") or []))
        elif moteur_openvino.installe():
            moteur_openvino.amorcer_provisoire()
            ov_connu = False
    except Exception:
        pass
    _journaliser(_CACHE)
    return _CACHE, lent is None or not ov_connu


def signature(lent: dict | None) -> str:
    """Ce qui, dans la détection lente, change l'affichage ou le réglage."""
    import json

    if not lent:
        return ""
    return json.dumps({k: lent.get(k) for k in ("gpus", "npus", "a_nvidia", "cuda_disponible", "openvino")},
                      sort_keys=True, ensure_ascii=False)


def _commande_detection() -> tuple[list[str], str]:
    from .extensions import commande_travailleur

    if chemins.EST_GELE:
        return commande_travailleur(["--detecter-materiel"])
    racine = Path(__file__).resolve().parent.parent
    commande, dossier = commande_travailleur([])
    return [commande[0], "-m", "app.materiel", "--detecter-materiel"], str(racine)


def rafraichir(delai_max: float = 120.0) -> dict | None:
    """
    Détection lente dans un processus à part, en priorité basse : il charge
    OpenVINO et les pilotes à la place de la fenêtre, puis s'en va. Renvoie le
    nouveau résultat (aussi écrit dans `materiel.json`), ou None en cas d'échec.
    """
    commande, dossier = _commande_detection()
    priorite = 0x00004000 if sys.platform == "win32" else 0   # BELOW_NORMAL_PRIORITY_CLASS
    try:
        resultat = subprocess.run(commande, cwd=dossier, capture_output=True, timeout=delai_max,
                                  creationflags=_SANS_FENETRE | priorite)
    except Exception as exc:
        journal.attention("Détection du matériel en arrière-plan impossible : %s", exc)
        return None
    if resultat.returncode != 0:
        detail = (resultat.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        journal.attention("Détection du matériel en arrière-plan en échec (%s) : %s",
                          resultat.returncode, detail[0][:300])
        return None
    return lire_cache()


def principal_detection() -> int:
    """`--detecter-materiel` : détection lente, résultat dans `materiel.json`."""
    lent = detection_complete_pour_cache()
    ecrire_cache(lent)
    return 0


if __name__ == "__main__":
    if "--detecter-materiel" in sys.argv[1:]:
        sys.exit(principal_detection())
