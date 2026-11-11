"""
Detection du materiel et recommandation.

Objectif : afficher honnetement ce que la machine sait faire, et rien de plus.
CTranslate2 (le moteur de faster-whisper) n'accelere que sur NVIDIA. Les cartes
AMD et Intel sont donc detectees et affichees, mais annoncees comme non
accelerees en v1.

Aucune dependance obligatoire : psutil est utilise s'il est present, sinon on
retombe sur la bibliotheque standard et sur l'API Windows via ctypes.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
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
    #: Cle de traduction de la note, resolue a l'affichage. Le materiel est
    #: detecte une fois pour toutes, la langue peut changer ensuite.
    note_cle: str = ""


@dataclass
class Accelerateur:
    """Circuit d'accélération detecte mais non exploite en v1 (NPU par exemple)."""

    nom: str
    genre: str = "npu"
    note_cle: str = ""


@dataclass
class Materiel:
    cpu_nom: str = ""
    coeurs_physiques: int = 0
    coeurs_logiques: int = 0
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
    def fils_calcul(self) -> int:
        """Laisse deux coeurs au systeme pour que la machine reste utilisable."""
        total = self.coeurs_logiques or os.cpu_count() or 4
        return max(1, total - 2)

    def en_dict(self) -> dict:
        donnees = asdict(self)
        # Les notes sont traduites ici, pas à la détection : une bascule de
        # langue doit les changer sans relancer l'inspection du matériel.
        for carte in donnees.get("gpus") or []:
            carte["note"] = langues.t(carte["note_cle"]) if carte.get("note_cle") else ""
        for circuit in donnees.get("npus") or []:
            circuit["note"] = langues.t(circuit["note_cle"]) if circuit.get("note_cle") else ""
        donnees["peripherique"] = self.peripherique
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
        if self.coeurs_logiques:
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
        "Select-Object Name,AdapterCompatibility,AdapterRAM | ConvertTo-Json -Compress",
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
                cartes.append(Gpu(nom=nom, vendeur=_vendeur(nom, fabricant), memoire_mo=memoire_mo))
    except Exception as exc:  # pragma: no cover - depend du poste
        journal.debug("Detection GPU impossible : %s", exc)

    cartes.sort(key=_rang_carte)
    return cartes


def _accelerateurs_neuronaux() -> list[Accelerateur]:
    """
    Repere un NPU (Intel AI Boost sur Meteor Lake, AMD XDNA, Qualcomm Hexagon).

    Purement informatif : aucun de ces circuits n'est exploite en v1. On les
    affiche pour que l'utilisateur sache ce que sa machine possede.
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
            trouves.append(Accelerateur(nom=nom, genre="npu", note_cle="npu.note"))
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

    _CACHE = Materiel(
        cpu_nom=_nom_cpu(),
        coeurs_physiques=physiques,
        coeurs_logiques=logiques,
        ram_go=total,
        ram_libre_go=libre,
        gpus=cartes,
        npus=neuronaux,
        a_nvidia=nvidia,
        cuda_disponible=cuda,
        systeme=f"{platform.system()} {platform.release()}",
    )

    journal.info("Matériel : %s", _CACHE.resume())
    journal.info(
        "Profil retenu : périphérique=%s, type de calcul=%s, fils=%s",
        _CACHE.peripherique, _CACHE.type_calcul, _CACHE.fils_calcul,
    )
    return _CACHE
