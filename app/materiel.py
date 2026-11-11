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

from . import journal, langues

_CACHE: "Materiel | None" = None

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
    for classe, logiques in coeurs:
        if hybride and classe != haute and couverts and not (logiques & couverts):
            topo.basse_consommation += 1
            continue
        if hybride and classe != haute:
            topo.efficaces += 1
        else:
            topo.performants += 1
        principaux += sorted(logiques)
    if hybride and topo.basse_consommation and not topo.efficaces:
        # Deux familles seulement, dont l'une hors du L3 (Lunar Lake : ses cœurs
        # efficaces ont leur propre cache). Ce ne sont pas des cœurs d'appoint :
        # ils comptent comme efficaces.
        topo.efficaces, topo.basse_consommation = topo.basse_consommation, 0
        principaux = sorted(set().union(*(logiques for _, logiques in coeurs)))
    topo.hybride = hybride
    topo.logiques_principaux = sorted(principaux)
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


def _cartes_graphiques() -> list[Gpu]:
    cartes: list[Gpu] = []
    if sys.platform != "win32":
        return cartes

    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterCompatibility,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress",
    ]
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=20,
            creationflags=_SANS_FENETRE,
        )
        sortie = (resultat.stdout or "").strip()
        if sortie:
            import json

            donnees = json.loads(sortie)
            if isinstance(donnees, dict):
                donnees = [donnees]
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
                    memoire_mo = max(0, int(ram) // (1024 * 1024))
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


def _accelerateurs_neuronaux() -> list[Accelerateur]:
    """
    Repère un NPU (Intel AI Boost des Core Ultra, AMD XDNA, Qualcomm Hexagon).

    Seul celui d'Intel peut servir, par le moteur OpenVINO et à titre
    expérimental. Les autres sont affichés pour information.
    """
    trouves: list[Accelerateur] = []
    if sys.platform != "win32":
        return trouves

    commande = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_PnPEntity | "
        # Motif volontairement strict : un « NPU » non délimité attrape « Input ».
        "Where-Object { $_.Name -match 'AI Boost|Neural Processor|\\bNPU\\b|XDNA|Hexagon NPU' } | "
        "Select-Object -ExpandProperty Name -Unique",
    ]
    try:
        resultat = subprocess.run(
            commande, capture_output=True, text=True, timeout=25,
            creationflags=_SANS_FENETRE,
        )
        for ligne in (resultat.stdout or "").splitlines():
            nom = ligne.strip()
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


def detecter(forcer: bool = False) -> Materiel:
    global _CACHE
    if _CACHE is not None and not forcer:
        return _CACHE

    physiques, logiques = _coeurs()
    topologie = _topologie()
    total, libre = _memoire()
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

    nom_cpu = _nom_cpu()
    _CACHE = Materiel(
        cpu_nom=nom_cpu,
        coeurs_physiques=physiques,
        coeurs_logiques=logiques,
        topologie=topologie,
        basse_consommation=est_basse_consommation(nom_cpu),
        portable=_portable(),
        ram_go=total,
        ram_libre_go=libre,
        gpus=cartes,
        npus=neuronaux,
        a_nvidia=nvidia,
        cuda_disponible=cuda,
        systeme=f"{platform.system()} {platform.release()}",
    )

    journal.info("Matériel : %s", _CACHE.resume())
    if topologie.hybride:
        journal.info(
            "Processeur hybride : %s performants, %s efficaces, %s basse consommation",
            topologie.performants, topologie.efficaces, topologie.basse_consommation)
    journal.info(
        "Profil retenu : périphérique=%s, type de calcul=%s, fils=%s",
        _CACHE.peripherique, _CACHE.type_calcul, _CACHE.fils_calcul,
    )
    return _CACHE
