"""
Vérification du processus moteur, de la ligne de commande et de l'inventaire,
sans modèle ni fenêtre (moteur factice, `app/moteur_factice.py`).

Protocole, file de trois fichiers avec un seul chargement, aucune bibliothèque
de calcul dans le processus parent, annulation en moins d'une seconde (pendant
un chargement et pendant le calcul), reprise au segment près, plantage simulé
avec reprise automatique et repli hors de la puce graphique, double plantage,
aucun orphelin quand le parent est tué, retour de veille, moteur bloqué, rythme
appliqué au seul moteur, ligne de commande sur un bureau sans affichage ni
console, codes de retour, lecture paginée, réglages, inventaire et effacement
sur des arborescences factices avec des fichiers étrangers.

Tout se passe dans un dossier temporaire : rien de l'utilisateur n'est lu ni
écrit.

    .venv\\Scripts\\python outils\\verifier_moteur.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TEMPORAIRE = Path(tempfile.mkdtemp(prefix="scribouille-moteur-"))
os.environ["SCRIBOUILLE_DONNEES"] = str(TEMPORAIRE / "donnees")
os.environ["LOCALAPPDATA"] = str(TEMPORAIRE / "localappdata")
(TEMPORAIRE / "localappdata").mkdir()
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import chemins, langues  # noqa: E402

langues.definir("fr")
EXTRAIT = RACINE / "banc" / "extrait_fr.ogg"
PYTHON = sys.executable

_reussites = 0
_echecs: list[str] = []


def verifier(condition: bool, libelle: str, detail: str = "") -> None:
    global _reussites
    if condition:
        _reussites += 1
        print(f"  OK    {libelle}")
    else:
        _echecs.append(libelle)
        print(f"  ECHEC {libelle}" + (f" : {detail}" if detail else ""))


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * len(texte))


def attendre(condition, delai: float = 30.0, pas: float = 0.02) -> bool:
    limite = time.monotonic() + delai
    while time.monotonic() < limite:
        if condition():
            return True
        time.sleep(pas)
    return False


def vivant(pid: int | None) -> bool:
    import psutil

    try:
        return bool(pid) and psutil.Process(pid).is_running() and psutil.Process(pid).status() != "zombie"
    except psutil.Error:
        return False


# ---------------------------------------------------------------------------
# Une file dans le processus moteur, moteur factice
# ---------------------------------------------------------------------------

class File:
    """Une file distante, ses rappels relevés, et son bilan."""

    def __init__(self, nom: str, essai: dict, fichiers: int = 1, config_en_plus: dict | None = None):
        from app import config as config_module, materiel, superviseur, traitement

        os.environ["SCRIBOUILLE_MOTEUR_ESSAI"] = json.dumps(essai)
        self.dossier = TEMPORAIRE / nom
        self.dossier.mkdir()
        self.sorties = self.dossier / "sorties"
        self.sup = superviseur.Superviseur()
        self.file = traitement.FileTraitement(materiel.detecter_au_demarrage()[0], distant=self.sup)
        self.sources = []
        for rang in range(fichiers):
            copie = self.dossier / f"reunion-{rang + 1}.ogg"
            copie.write_bytes(EXTRAIT.read_bytes())
            self.sources.append(copie)
        self.file.ajouter([str(s) for s in self.sources])
        self.config = copy.deepcopy(config_module.DEFAUTS)
        self.config.update({"dossier_sortie": str(self.sorties), "diarisation": False, "utiliser_glossaire": False,
                            "appliquer_corrections": False, "sauvegarde_progressive": True, "langue": "fr",
                            "langue_interface": "fr", "preset": "rapide", **(config_en_plus or {})})
        self.recus: list[tuple] = []
        self.bilan: dict = {}
        self.fini = threading.Event()
        self.rappels = traitement.Rappels(
            etat=lambda i, e, m: self.recus.append(("etat", i, e, m, time.perf_counter())),
            progression=lambda i, d: self.recus.append(("progression", i, dict(d), time.perf_counter())),
            termine=lambda i, d: self.recus.append(("termine", i, dict(d), time.perf_counter())),
            journal_ui=lambda n, t: self.recus.append(("journal", n, t, time.perf_counter())),
            file_terminee=lambda d: (self.bilan.update(d), self.fini.set()),
        )

    def demarrer(self) -> None:
        self.file.demarrer(self.config, self.rappels)

    def attendre(self, delai: float = 120) -> bool:
        return self.fini.wait(delai)

    def journal(self) -> list[str]:
        return [r[2] for r in self.recus if r[0] == "journal"]

    def progressions(self) -> int:
        return sum(1 for r in self.recus if r[0] == "progression")

    def segments(self, rang: int = 0) -> list[str]:
        """Textes des segments du compagnon écrit pour la source `rang`."""
        for f in sorted(self.sorties.glob("*.json")):
            donnees = json.loads(f.read_text(encoding="utf-8"))
            if Path(donnees["source"]["chemin"]).name == self.sources[rang].name:
                return [s["t"] for s in donnees["segments"]]
        return []


def attendu(n: int) -> list[str]:
    return [f"Segment numéro {k + 1} de la réunion." for k in range(n)]


# ---------------------------------------------------------------------------
# 1. Protocole
# ---------------------------------------------------------------------------

def essai_protocole() -> None:
    titre("1. Protocole")
    from app import protocole

    ligne = protocole.encoder({"type": "progression", "id": "a", "donnees": {"pct": 12, "phase": "Écriture"}})
    verifier(ligne.endswith(b"\n") and ligne.count(b"\n") == 1, "un message, une ligne terminée par \\n")
    verifier(protocole.decoder(ligne) == {"type": "progression", "id": "a", "donnees": {"pct": 12, "phase": "Écriture"}},
             "aller-retour sans perte, accents compris")
    verifier(protocole.decoder(b"pas du json") is None and protocole.decoder(b"[1,2]") is None
             and protocole.decoder(b'{"sans":"type"}') is None and protocole.decoder(b"   ") is None,
             "ligne illisible, tableau, objet sans type, ligne vide : ignorés")
    verifier(protocole.VERSION == 1 and set(protocole.ORDRES) == {"ouvrir", "traiter", "fermer", "durees", "quitter"},
             "version 1, cinq ordres")
    # Le moteur lui-même : pret, ordre inconnu, ligne illisible, quitter.
    commande = [PYTHON, str(RACINE / "transcriber.pyw"), "--moteur"]
    p = subprocess.run(commande, input=b'pas du json\n{"type":"inconnu","n":7}\n{"type":"quitter","n":8}\n',
                       capture_output=True, timeout=60, cwd=str(RACINE))
    messages = [protocole.decoder(x) for x in p.stdout.splitlines()]
    verifier(messages and messages[0]["type"] == "pret" and messages[0]["protocole"] == 1
             and isinstance(messages[0]["pid"], int), "premier message : pret, version du protocole, PID", str(messages[:1]))
    verifier(any(m and m["type"] == "erreur" and m.get("n") == 7 for m in messages)
             and any(m and m["type"] == "erreur" and m.get("n") is None for m in messages),
             "ordre inconnu et ligne illisible : erreur, le moteur continue")
    verifier(p.returncode == 0, "« quitter » : sortie propre, code 0", str(p.returncode))
    verifier(all(m is not None for m in messages), "la sortie standard ne porte que le protocole",
             str([x for x in p.stdout.splitlines() if protocole.decoder(x) is None][:2]))


# ---------------------------------------------------------------------------
# 2. File de trois fichiers, un seul chargement, fenêtre sans calcul
# ---------------------------------------------------------------------------

_SONDE_PARENT = r"""
import json, os, sys, threading, copy
sys.path.insert(0, sys.argv[1])
from app import config as config_module, materiel, superviseur, traitement
sup = superviseur.Superviseur()
file = traitement.FileTraitement(materiel.detecter_au_demarrage()[0], distant=sup)
file.ajouter([sys.argv[2]])
config = copy.deepcopy(config_module.DEFAUTS)
config.update({"dossier_sortie": sys.argv[3], "diarisation": False, "utiliser_glossaire": False,
               "appliquer_corrections": False})
fini = threading.Event()
duree = []
file.mesurer_durees(lambda i, s, t: duree.append(s))
file.demarrer(config, traitement.Rappels(file_terminee=lambda d: fini.set()))
fini.wait(120)
lourds = ("numpy", "ctranslate2", "faster_whisper", "av", "openvino", "openvino_genai", "onnxruntime", "torch",
          "tokenizers", "webview")
print(json.dumps({"charges": sorted(m for m in lourds if m in sys.modules), "duree": duree}))
"""


def essai_file_de_trois() -> None:
    titre("2. File de trois fichiers dans le moteur")
    f = File("trois", {"segments": 8, "pause_s": 0.01, "chargement_s": 0.3}, fichiers=3)
    f.demarrer()
    verifier(f.attendre(), "la file se termine")
    verifier(f.bilan.get("reussis") == 3 and f.bilan.get("echecs") == 0, "trois réussis", str(f.bilan))
    verifier(f.sup.chargements == 1 and f.sup.lancements == 1,
             "un seul processus et un seul chargement du modèle pour la file",
             f"chargements={f.sup.chargements} lancements={f.sup.lancements}")
    verifier(attendre(lambda: not f.sup.vivant(), 15), "fin de file : le moteur s'arrête (mémoire rendue)")
    verifier(all(f.segments(k) == attendu(8) for k in range(3)), "trois compagnons complets, dans l'ordre")
    etats = [e.etat for e in f.file.elements]
    verifier(etats == ["termine"] * 3, "états de la fenêtre tenus à jour par le moteur", str(etats))
    phases = [r[2] for r in f.recus if r[0] == "etat" and r[1] == f.file.elements[0].identifiant]
    verifier(phases == ["decodage", "transcription", "ecriture", "termine"], "phases relayées dans l'ordre", str(phases))
    verifier(f.sup.etat_public()["etat"] == "arrete", "moteur_etat : arrêté après la file")

    sortie = subprocess.run([PYTHON, "-c", _SONDE_PARENT, str(RACINE), str(EXTRAIT), str(TEMPORAIRE / "sonde")],
                            capture_output=True, text=True, timeout=180, env=dict(os.environ))
    try:
        sonde = json.loads(sortie.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        sonde = {"charges": ["?"], "duree": []}
    verifier(sonde["charges"] == [], "processus parent : ni numpy, ni CTranslate2, ni PyAV, ni OpenVINO chargés",
             f"{sonde} {sortie.stderr[-300:]}")
    verifier(sonde["duree"] and abs(sonde["duree"][0] - 43.6) < 0.2, "durée mesurée par le moteur",
             str(sonde["duree"]))


# ---------------------------------------------------------------------------
# 3. Annulation
# ---------------------------------------------------------------------------

def essai_annulation() -> None:
    titre("3. Annulation en moins d'une seconde")
    f = File("annule-chargement", {"segments": 10, "chargement_s": 120})
    f.demarrer()
    verifier(attendre(lambda: f.sup.etat == "chargement", 30), "moteur en chargement du modèle")
    pid = f.sup.pid
    depart = time.perf_counter()
    f.file.arreter()
    f.attendre(10)
    annule = next((r[4] for r in f.recus if r[0] == "etat" and r[2] == "annule"), None)
    delai = (annule - depart) if annule else 99
    verifier(annule is not None and delai < 1.0, "pendant un chargement : arrêté en moins d'une seconde",
             f"{delai * 1000:.0f} ms")
    print(f"        délai mesuré : {delai * 1000:.0f} ms")
    verifier(attendre(lambda: not vivant(pid), 3), "le processus moteur n'existe plus")
    verifier(f.file.elements[0].etat == "annule" and f.bilan.get("annules") == 1, "fichier « arrêté », bilan juste")

    f = File("annule-calcul", {"segments": 40, "pause_s": 0.15})
    f.demarrer()
    verifier(attendre(lambda: f.progressions() >= 8, 30), "transcription en cours")
    depart = time.perf_counter()
    f.file.arreter()
    f.attendre(10)
    annule = next((r[4] for r in f.recus if r[0] == "etat" and r[2] == "annule"), None)
    delai = (annule - depart) if annule else 99
    verifier(annule is not None and delai < 1.0, "pendant le calcul : arrêté en moins d'une seconde",
             f"{delai * 1000:.0f} ms")
    print(f"        délai mesuré : {delai * 1000:.0f} ms")
    from app import reprise

    cle = f.file.elements[0].reprise
    etat = reprise.lire_etat(cle) if cle else None
    lignes = (chemins.RACINE / "reprises" / f"{cle}.jsonl").read_text(encoding="utf-8").splitlines() if cle else []
    verifier(bool(etat) and etat["nb_segments"] >= 5 and len(lignes) == etat["nb_segments"],
             "état de reprise intact : segments écrits et état d'accord", f"{etat} lignes={len(lignes)}")
    # Reprise : le fichier repart de sa sauvegarde, au segment près.
    remis = f.file.ajouter_pour_reprise(str(f.sources[0]), cle)
    f.fini.clear()
    f.demarrer()
    f.attendre(60)
    verifier(bool(remis) and f.segments() == attendu(40),
             "reprise : tous les segments, une seule fois, dans l'ordre", str(len(f.segments())))
    verifier(not reprise.lire_etat(cle), "reprise menée au bout : sauvegarde effacée")


# ---------------------------------------------------------------------------
# 4. Plantages
# ---------------------------------------------------------------------------

def essai_plantage() -> None:
    titre("4. Plantage du moteur : la fenêtre reste, reprise au segment près")
    temoin_essai = TEMPORAIRE / "plantage-une-fois.txt"
    temoin_puce = chemins.RACINE / "openvino-chargement-en-cours.txt"
    temoin_puce.unlink(missing_ok=True)
    f = File("plantage", {"segments": 20, "pause_s": 0.02, "plantage_segment": 7, "temoin": str(temoin_essai),
                          "puce": True})
    f.demarrer()
    verifier(f.attendre(60), "la file se termine malgré le plantage")
    verifier(temoin_essai.exists(), "le moteur s'est bien arrêté net une fois (simulation)")
    verifier(f.bilan.get("reussis") == 1, "fichier réussi après reprise automatique", str(f.bilan))
    verifier(f.segments() == attendu(20), "texte complet : ni perte ni doublon au point de reprise",
             str(f.segments()[:9]))
    textes = " | ".join(f.journal())
    verifier("s'est arrêté brutalement" in textes and "Reprise automatique" in textes,
             "le plantage et la reprise sont dits", textes[:300])
    verifier(temoin_puce.is_file() and "GPU" in temoin_puce.read_text(encoding="utf-8"),
             "puce graphique écartée pour la suite (témoin d'OpenVINO posé)")
    verifier(f.sup.lancements == 2 and (f.sup.derniere_panne or {}).get("code") == 3,
             "un seul relancement, panne notée avec son code", f"{f.sup.lancements} {f.sup.derniere_panne}")
    temoin_puce.unlink(missing_ok=True)

    f = File("double-plantage", {"segments": 20, "pause_s": 0.02, "plantage_segment": 4})
    f.demarrer()
    verifier(f.attendre(60), "double plantage : la file se termine quand même")
    element = f.file.elements[0]
    from app import reprise

    etat = reprise.lire_etat(element.reprise) if element.reprise else None
    verifier(element.etat == "erreur" and f.bilan.get("echecs") == 1, "deux plantages : fichier en erreur",
             f"{element.etat} {f.bilan}")
    verifier(bool(etat) and float(etat.get("position") or 0) > 0, "la reprise reste possible (segments gardés)")
    termine = next((r[2] for r in f.recus if r[0] == "termine"), {})
    verifier(termine.get("plantage_moteur") is True and termine.get("reprise") == element.reprise,
             "la ligne du fichier sait que c'est le moteur, et garde la clé de reprise", str(termine))


# ---------------------------------------------------------------------------
# 5. Aucun orphelin
# ---------------------------------------------------------------------------

_PARENT = r"""
import os, sys, json, threading, copy, time
sys.path.insert(0, sys.argv[1])
from app import config as config_module, materiel, superviseur, traitement
sup = superviseur.Superviseur()
file = traitement.FileTraitement(materiel.detecter_au_demarrage()[0], distant=sup)
file.ajouter([sys.argv[2]])
config = copy.deepcopy(config_module.DEFAUTS)
config.update({"dossier_sortie": sys.argv[3], "diarisation": False})
file.demarrer(config, traitement.Rappels())
while sup.etat != "chargement":
    time.sleep(0.05)
print(sup.pid, flush=True)
if sys.argv[4] == "sortir":
    os._exit(0)
time.sleep(600)
"""


def essai_orphelins() -> None:
    titre("5. Aucun processus orphelin")
    import psutil

    os.environ["SCRIBOUILLE_MOTEUR_ESSAI"] = json.dumps({"chargement_s": 600})
    for mode, libelle in (("tuer", "parent tué (TerminateProcess)"), ("sortir", "parent sorti sans rien fermer")):
        parent = subprocess.Popen([PYTHON, "-c", _PARENT, str(RACINE), str(EXTRAIT), str(TEMPORAIRE / "orph"), mode],
                                  stdout=subprocess.PIPE, text=True, env=dict(os.environ))
        ligne = parent.stdout.readline().strip()
        pid = int(ligne) if ligne.isdigit() else 0
        verifier(vivant(pid), f"{libelle} : moteur en marche avant", ligne)
        if mode == "tuer":
            psutil.Process(parent.pid).kill()
        parent.wait(10)
        verifier(attendre(lambda: not vivant(pid), 5), f"{libelle} : le moteur disparaît avec lui")


# ---------------------------------------------------------------------------
# 6. Veille, blocage, rythme
# ---------------------------------------------------------------------------

def essai_veille_et_blocage() -> None:
    titre("6. Retour de veille, moteur bloqué, rythme du seul moteur")
    from app import superviseur

    f = File("veille", {"segments": 30, "pause_s": 0.1})
    decalage = [0.0]
    f.sup.horloge_mur = lambda: time.time() + decalage[0]
    f.demarrer()
    attendre(lambda: f.progressions() >= 3, 30)
    decalage[0] = 3600.0  # l'horloge saute d'une heure : retour de veille
    verifier(f.attendre(60), "la file finit après un saut d'horloge")
    verifier(f.bilan.get("reussis") == 1 and f.sup.lancements == 1,
             "retour de veille : rien d'arrêté ni de relancé", f"{f.bilan} lancements={f.sup.lancements}")
    verifier(any("Retour de veille" in t for t in f.journal()), "le retour de veille est dit")

    ancien = superviseur.DELAI_BLOCAGE_S
    superviseur.DELAI_BLOCAGE_S = 3.0
    try:
        import psutil

        f = File("bloque", {"segments": 20, "pause_s": 0.15})
        f.demarrer()
        attendre(lambda: f.progressions() >= 4, 30)
        pid = f.sup.pid
        psutil.Process(pid).suspend()  # plus rien ne sort du moteur
        verifier(f.attendre(90), "moteur figé : la file ne reste pas bloquée")
        verifier(not vivant(pid) and f.sup.lancements == 2 and f.bilan.get("reussis") == 1,
                 "moteur figé : arrêté, relancé, fichier repris et terminé", f"{f.bilan} {f.sup.lancements}")
        verifier(f.segments() == attendu(20), "texte complet après le blocage")
    finally:
        superviseur.DELAI_BLOCAGE_S = ancien

    import psutil

    f = File("rythme", {"segments": 30, "pause_s": 0.1}, config_en_plus={"rythme": "discret"})
    f.demarrer()
    attendre(lambda: f.progressions() >= 3, 30)
    pid = f.sup.pid
    try:
        priorite_moteur = psutil.Process(pid).nice()
    except psutil.Error:
        priorite_moteur = None
    priorite_parent = psutil.Process().nice()
    f.attendre(60)
    verifier(priorite_moteur == psutil.IDLE_PRIORITY_CLASS, "rythme discret : moteur en priorité basse",
             str(priorite_moteur))
    verifier(priorite_parent == psutil.NORMAL_PRIORITY_CLASS, "la fenêtre garde sa priorité normale",
             str(priorite_parent))


# ---------------------------------------------------------------------------
# 7. Ligne de commande
# ---------------------------------------------------------------------------

def cli(*arguments, essai: dict | None = None, env_en_plus: dict | None = None) -> tuple[int, list[dict], str]:
    env = dict(os.environ)
    env.pop("SCRIBOUILLE_MOTEUR_ESSAI", None)
    if essai is not None:
        env["SCRIBOUILLE_MOTEUR_ESSAI"] = json.dumps(essai)
    env.update(env_en_plus or {})
    p = subprocess.run([PYTHON, str(RACINE / "transcriber.pyw"), *arguments], capture_output=True, timeout=300,
                       env=env, cwd=str(TEMPORAIRE))
    lignes = []
    for x in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            lignes.append(json.loads(x))
        except ValueError:
            pass
    return p.returncode, lignes, p.stderr.decode("utf-8", "replace")


_AUDIT = r"""
import atexit, json, runpy, sys
fichier_audit = sys.argv[1]
def audit():
    noms = ("webview", "clr", "pythonnet", "clr_loader", "System", "tkinter")
    with open(fichier_audit, "w", encoding="utf-8") as f:
        json.dump(sorted(m for m in noms if m in sys.modules), f)
atexit.register(audit)
programme = sys.argv[2]
sys.argv = [programme] + sys.argv[3:]
runpy.run_path(programme, run_name="__main__")
"""


def _lancer_sans_bureau(commande: list[str], env: dict, sortie: Path) -> int:
    """Lance `commande` sur un bureau Windows à part, invisible, sans console : comme un service."""
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32.CreateDesktopW.restype = wintypes.HANDLE
    u32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p]
    nom = f"scribouille-essai-{os.getpid()}"
    bureau = u32.CreateDesktopW(nom, None, None, 0, 0x10000000, None)  # GENERIC_ALL
    if not bureau:
        return -1

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                    ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                    ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]

    import msvcrt

    flux = open(sortie, "wb")
    poignee = msvcrt.get_osfhandle(flux.fileno())
    os.set_handle_inheritable(poignee, True)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    si.lpDesktop = f"WinSta0\\{nom}"
    si.dwFlags = 0x100  # STARTF_USESTDHANDLES
    si.hStdOutput = si.hStdError = poignee
    pi = PROCESS_INFORMATION()
    bloc = "".join(f"{k}={v}\0" for k, v in env.items()) + "\0"
    ligne = subprocess.list2cmdline(commande)
    k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.BOOL, wintypes.DWORD, ctypes.c_wchar_p, wintypes.LPCWSTR,
                                   ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]
    ok = k32.CreateProcessW(None, ctypes.create_unicode_buffer(ligne), None, None, True,
                            0x00000008 | 0x00000400,  # DETACHED_PROCESS (pas de console), environnement Unicode
                            bloc, str(TEMPORAIRE), ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        flux.close()
        return -2
    k32.WaitForSingleObject(pi.hProcess, 300_000)
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.CloseHandle(pi.hProcess)
    k32.CloseHandle(pi.hThread)
    flux.close()
    u32.CloseDesktop(bureau)
    return int(code.value)


def essai_ligne_de_commande() -> None:
    titre("7. Ligne de commande")
    dossier = TEMPORAIRE / "cli"
    dossier.mkdir()
    source = dossier / "point hebdo.ogg"
    source.write_bytes(EXTRAIT.read_bytes())
    essai = {"segments": 12, "pause_s": 0.01}

    code, lignes, err = cli("transcrire", str(source), "--json")
    verifier(code == 3 and lignes and lignes[-1]["erreur"]["code"] == "modele_absent"
             and "--telecharger" in lignes[-1]["erreur"]["suggestion"],
             "modèle absent sans --telecharger : code 3, rien de téléchargé", f"{code} {lignes[-1:]} {err[-200:]}")

    code, lignes, err = cli("transcrire", str(source), "--json", "--telecharger", essai=essai)
    evenements = [x.get("evenement") for x in lignes]
    fin = lignes[-1] if lignes else {}
    verifier(code == 0 and evenements[0] == "debut" and evenements[-1] == "fin" and fin.get("reussis") == 1,
             "transcrire : code 0, NDJSON de « debut » à « fin »", f"{code} {evenements[:3]} {err[-300:]}")
    verifier(all(x.get("schema") == "scribouille.cli/1" for x in lignes), "chaque ligne porte le schéma versionné")
    fichier = (fin.get("fichiers") or [{}])[0]
    compagnon = Path(fichier.get("json") or "")
    verifier(compagnon.is_file() and compagnon.parent == dossier, "sorties à côté de la source, .json compris",
             str(fichier))
    verifier("progres" in evenements and "fichier_fini" in evenements, "progression et fin de fichier en JSON")

    code, lignes, _ = cli("transcrire", str(source), "--json", "--telecharger", essai=essai)
    verifier(code == 4 and any(x.get("evenement") == "fichier_ignore" for x in lignes),
             "déjà transcrit : code 4, rien d'écrasé")
    avant = sorted(p.name for p in dossier.iterdir())
    code, lignes, _ = cli("transcrire", str(source), "--json", "--telecharger", "--ecraser", "--moteur", "ctranslate2",
                          "--rythme", "equilibre", "--locuteurs", "non", "--formats", "txt,json", essai=essai)
    verifier(code == 0 and sorted(p.name for p in dossier.iterdir()) == avant,
             "--ecraser : refait, mêmes fichiers (les anciens remplacés, pas de « -2 »)")

    code, lignes, _ = cli("transcrire", str(dossier / "absent.ogg"), "--json")
    verifier(code == 2 and lignes[-1]["erreur"]["code"] == "aucun_fichier", "fichier absent : code 2")
    code, lignes, _ = cli("transcrire", "--json")
    verifier(code == 2 and "erreur" in lignes[-1], "arguments invalides : code 2, erreur en JSON")

    code, lignes, _ = cli("lire", str(compagnon), "--json", "--limite", "20")
    page = lignes[-1]["donnees"] if lignes else {}
    verifier(code == 0 and len(page["segments"]) == 3 and page["pagination"]["suivant"] == 3
             and page["pagination"]["total"] == 12, "lire : pages bornées en mots, « suivant » donné",
             str(page.get("pagination")))
    code, lignes, _ = cli("lire", str(compagnon), "--json", "--douteux")
    page = lignes[-1]["donnees"] if lignes else {}
    verifier(page["douteux"]["methode"] == "probabilite<0.5" and page["douteux"]["nombre"] == 12
             and all(s["douteux"] == ["numéro"] for s in page["segments"]),
             "lire --douteux : les mots sous le seuil, la méthode dite", str(page.get("douteux")))
    code, lignes, _ = cli("lire", str(compagnon), "--json", "--depuis", "20", "--jusqua", "25")
    page = lignes[-1]["donnees"] if lignes else {}
    verifier(page["segments"] and all(s["f"] >= 20 and s["d"] <= 25 for s in page["segments"]),
             "lire --depuis --jusqua : fenêtre de temps")

    code, lignes, _ = cli("reglages", "definir", "rythme=discret", "preset=rapide", "--json")
    code2, lignes2, _ = cli("reglages", "lire", "rythme", "--json")
    verifier(code == 0 and code2 == 0 and lignes2[-1]["donnees"]["valeur"] == "discret",
             "reglages definir puis lire")
    code, lignes, _ = cli("reglages", "definir", "rythme=fusee", "--json")
    verifier(code == 2, "valeur hors liste : refusée, code 2")
    code, lignes, _ = cli("reglages", "defaut", "rythme", "--json")
    _code, lignes2, _ = cli("reglages", "lire", "rythme", "--json")
    verifier(code == 0 and lignes2[-1]["donnees"]["valeur"] == "vitesse", "reglages defaut")
    code, lignes, _ = cli("reglages", "--json")
    cles = {r["cle"] for r in lignes[-1]["donnees"]["reglages"]}
    verifier({"preset", "rythme", "moteur", "dossier_modeles", "formats"} <= cles, "reglages : liste complète")

    code, lignes, _ = cli("diagnostic", "--json")
    verifier(code == 3 and lignes[-1]["donnees"]["pret"] is False and lignes[-1]["donnees"]["raisons"],
             "diagnostic sans modèle : pas prêt, raisons données, code 3")
    code, lignes, _ = cli("etat", "--json")
    verifier(code == 0 and "taches" in lignes[-1]["donnees"], "etat : tâches et moteurs actifs")
    code, lignes, _ = cli("agent", "installer", "--cible", "claude", "--dossier", str(TEMPORAIRE / "maison"), "--json")
    fiche = TEMPORAIRE / "maison" / ".claude" / "skills" / "scribouille" / "SKILL.md"
    verifier(code == 0 and fiche.is_file() and "name: scribouille" in fiche.read_text(encoding="utf-8"),
             "agent installer : fiche écrite avec ses chemins")
    fiche.write_text("modifiée", encoding="utf-8")
    code, _, _ = cli("agent", "installer", "--cible", "claude", "--dossier", str(TEMPORAIRE / "maison"), "--json")
    verifier(code == 4, "fiche modifiée à la main : pas écrasée sans --ecraser")

    # Ctrl+C : interrompu, reprenable (code 5), puis « reprendre ».
    longue = dossier / "longue.ogg"
    longue.write_bytes(EXTRAIT.read_bytes())
    env = dict(os.environ, SCRIBOUILLE_MOTEUR_ESSAI=json.dumps({"segments": 60, "pause_s": 0.1}))
    p = subprocess.Popen([PYTHON, str(RACINE / "transcriber.pyw"), "transcrire", str(longue), "--json", "--telecharger"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=str(TEMPORAIRE),
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    vus = 0
    for x in p.stdout:
        if b'"progres"' in x:
            vus += 1
            if vus >= 6:
                break
    import signal

    p.send_signal(signal.CTRL_BREAK_EVENT)
    try:
        p.wait(30)
    except subprocess.TimeoutExpired:
        p.kill()
    code, lignes, _ = cli("etat", "--json")
    taches = lignes[-1]["donnees"]["taches"] if lignes else []
    verifier(any(Path(t["chemin"]).name == "longue.ogg" for t in taches),
             "interruption brutale de la commande : la transcription est reprenable", str(taches)[:200])
    code, lignes, err = cli("reprendre", "--json", essai={"segments": 60, "pause_s": 0.0})
    compagnons = sorted(dossier.glob("*longue*.json"))
    textes = [s["t"] for s in json.loads(compagnons[-1].read_text(encoding="utf-8"))["segments"]] if compagnons else []
    verifier(code == 0 and textes == attendu(60), "reprendre : terminé au segment près, sans doublon",
             f"{code} {len(textes)} {err[-200:]}")
    code, lignes, _ = cli("reprendre", "cle-qui-n-existe-pas", "--json")
    verifier(code == 2 and lignes[-1]["erreur"]["code"] == "introuvable", "reprendre une clé inconnue : code 2")

    # Sans bureau ni console, comme un service, une tâche planifiée ou SSH.
    sortie = TEMPORAIRE / "sans-bureau.ndjson"
    audit = TEMPORAIRE / "modules-cli.json"
    seconde = dossier / "sans bureau.ogg"
    seconde.write_bytes(EXTRAIT.read_bytes())
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("SCRIBOUILLE_MOTEUR_ESSAI",)}
    env["SCRIBOUILLE_MOTEUR_ESSAI"] = json.dumps(essai)
    code = _lancer_sans_bureau([PYTHON, "-c", _AUDIT, str(audit), str(RACINE / "transcriber.pyw"), "transcrire",
                                str(seconde), "--json", "--telecharger"], env, sortie)
    contenu = sortie.read_text(encoding="utf-8", errors="replace") if sortie.exists() else ""
    fin = [json.loads(x) for x in contenu.splitlines() if x.startswith("{") and '"fin"' in x]
    verifier(code == 0 and fin and fin[-1].get("reussis") == 1,
             "sur un bureau invisible, sans console : transcription faite, code 0", f"{code} {contenu[-300:]}")
    charges = json.loads(audit.read_text(encoding="utf-8")) if audit.exists() else ["?"]
    verifier(charges == [], "chemin de la ligne de commande : ni pywebview, ni WebView2 (.NET), ni Tk", str(charges))


# ---------------------------------------------------------------------------
# 8. Inventaire et effacement, arborescences factices
# ---------------------------------------------------------------------------

def _ecrire(chemin: Path, octets: int = 100, texte: str | None = None) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if texte is not None:
        chemin.write_text(texte, encoding="utf-8")
    else:
        chemin.write_bytes(b"x" * octets)
    return chemin


def essai_inventaire() -> None:
    titre("8. Inventaire et effacement")
    from app import inventaire

    base = TEMPORAIRE / "arbre"
    racine = base / "Scribouille"
    ancien = base / "WhiScribe"
    sortie = base / "Transcriptions"
    anciens = (chemins.RACINE, chemins.DOSSIER_MODELES, os.environ.get("LOCALAPPDATA"))
    chemins.RACINE = racine
    chemins.DOSSIER_MODELES = racine / "modeles"
    os.environ["LOCALAPPDATA"] = str(base)
    try:
        _ecrire(racine / "config.json", texte="{}")
        _ecrire(racine / "vocabulaire.toml", 300)
        _ecrire(racine / "logs" / "2026-11-12.log", 2000)
        _ecrire(racine / "cache-openvino" / "a.blob", 50_000)
        _ecrire(racine / "cache-pip" / "b.whl", 7000)
        _ecrire(racine / "extensions-openvino" / "openvino.dll", 90_000)
        _ecrire(racine / "reprises" / "k.jsonl", 400)
        _ecrire(racine / "campagnes" / "rapport.txt", 500)
        _ecrire(racine / "webview" / "EBWebView" / "x", 800)
        _ecrire(racine / "inconnu-d-un-autre.txt", 123)
        m = racine / "modeles"
        _ecrire(m / "models--Systran--faster-whisper-large-v3" / "blobs" / "poids", 300_000)
        _ecrire(m / "models--OpenVINO--whisper-large-v3-turbo-int8-ov" / "blobs" / "poids", 200_000)
        _ecrire(m / "convertis" / "distil-fr-ov" / "openvino_encoder_model.bin", 100_000)
        _ecrire(m / ".locks" / "models--Systran--faster-whisper-large-v3" / "v.lock", 0)
        _ecrire(ancien / "models" / "ggml-large-v3-turbo.bin", 60_000)   # projet tiers homonyme
        _ecrire(ancien / "reglages-tiers.ini", 50)
        _ecrire(ancien / "config.json", texte="{}")                          # reste de chez nous
        _ecrire(sortie / "2026-11-12-reunion.txt", texte="=" * 68 + "\nTranscription : reunion.ogg\n" + "=" * 68
                + "\nProduit localement, aucune donnée n'a quitté cette machine.\n\nBonjour.\n")
        _ecrire(sortie / "2026-11-12-reunion.json", texte=json.dumps({"format": "scribouille-transcription",
                                                                      "source": {"chemin": "x"}, "segments": []}))
        _ecrire(sortie / "notes-personnelles.txt", texte="mes notes")
        config = {"preset": "qualite", "dossier_sortie": str(sortie)}

        inv = inventaire.inventaire(config)
        par_cle = {p["cle"]: p for p in inv["postes"]}
        verifier({"cache_openvino", "cache_pip", "openvino", "journaux", "reprises", "mesures", "vocabulaire",
                  "reglages", "affichage", "ancien_dossier", "modele:Systran/faster-whisper-large-v3",
                  "modele:OpenVINO/whisper-large-v3-turbo-int8-ov", "modele:convertis/distil-fr-ov"} <= set(par_cle),
                 "inventaire : un poste par usage et par modèle", str(sorted(par_cle)))
        verifier(par_cle["cache_openvino"]["octets"] == 50_000 and par_cle["cache_openvino"]["liberable"],
                 "cache d'OpenVINO : taille juste, libérable")
        verifier(not par_cle["modele:Systran/faster-whisper-large-v3"]["liberable"]
                 and par_cle["modele:OpenVINO/whisper-large-v3-turbo-int8-ov"]["liberable"],
                 "modèle du réglage en cours non libérable, modèle inutilisé libérable")
        verifier(par_cle["ancien_dossier"]["chemins"] == [str(ancien / "config.json")],
                 "ancien dossier : seulement ce qui est à nous")
        verifier(inv["transcriptions_octets"] > 0 and inv["transcriptions"]["nombre"] == 2
                 and inv["total_octets"] == sum(p["octets"] for p in inv["postes"]),
                 "transcriptions comptées à part (2 fichiers), hors du total", str(inv["transcriptions"]))
        verifier(str(racine / "inconnu-d-un-autre.txt") in inv["non_reconnus"],
                 "fichier inconnu montré comme non reconnu")
        for cle in ("libelle", "octets", "liberable", "description", "chemins"):
            verifier(all(cle in p for p in inv["postes"]), f"contrat : chaque poste a « {cle} »")

        bilan = inventaire.liberer(["cache_openvino", "modele:OpenVINO/whisper-large-v3-turbo-int8-ov"], config)
        verifier(bilan["octets"] == 250_000 and not (racine / "cache-openvino").exists()
                 and not (m / "models--OpenVINO--whisper-large-v3-turbo-int8-ov").exists()
                 and (m / "models--Systran--faster-whisper-large-v3").exists(),
                 "libération ciblée : exactement les postes demandés", str(bilan))
        verifier(inventaire.liberer(["programme"], config)["restes"], "le programme ne se libère pas ici")

        apercu = inventaire.apercu_effacement(True, config, avec_programme=False)
        verifier(apercu["jeton"] and apercu["garder_transcriptions"] and apercu["total_octets"] > 0
                 and all(p["cle"] != "programme" for p in apercu["postes"]),
                 "aperçu : liste, tailles, jeton ; rien d'effacé", str(apercu["total"]))
        verifier((racine / "config.json").exists(), "l'aperçu ne touche à rien")
        verifier(not inventaire.executer_effacement("jeton-inconnu")["ok"], "jeton inconnu : refusé")
        bilan = inventaire.executer_effacement(apercu["jeton"])
        restants = sorted(str(p.relative_to(base)) for p in base.rglob("*") if p.is_file())
        verifier(bilan["ok"] and restants == sorted([
            str(Path("Scribouille") / "inconnu-d-un-autre.txt"),
            str(Path("Transcriptions") / "2026-11-12-reunion.json"),
            str(Path("Transcriptions") / "2026-11-12-reunion.txt"),
            str(Path("Transcriptions") / "notes-personnelles.txt"),
            str(Path("WhiScribe") / "models" / "ggml-large-v3-turbo.bin"),
            str(Path("WhiScribe") / "reglages-tiers.ini")]),
            "effacement complet : tout ce qui est à nous, rien d'autre, transcriptions gardées", str(restants))
        verifier(not inventaire.executer_effacement(apercu["jeton"])["ok"], "un jeton ne sert qu'une fois")

        apercu = inventaire.apercu_effacement(False, config, avec_programme=False)
        verifier(apercu["transcriptions_octets"] > 0 and not apercu["garder_transcriptions"],
                 "aperçu avec transcriptions : leur poids est annoncé")
        inventaire.executer_effacement(apercu["jeton"])
        verifier(not (sortie / "2026-11-12-reunion.txt").exists() and (sortie / "notes-personnelles.txt").exists(),
                 "transcriptions effacées sur demande explicite, notes étrangères gardées")

        # Dossier de modèles choisi à la main : seuls les dépôts connus.
        perso = base / "MesModeles"
        _ecrire(perso / "models--Systran--faster-whisper-small" / "blobs" / "p", 1000)
        _ecrire(perso / "models--quelquun--autre-modele" / "blobs" / "p", 1000)
        _ecrire(perso / "CACHEDIR.TAG", 10)
        chemins.DOSSIER_MODELES = perso
        inv = inventaire.inventaire(config)
        cles = {p["cle"] for p in inv["postes"]}
        verifier("modele:Systran/faster-whisper-small" in cles and "modele:quelquun/autre-modele" not in cles
                 and str(perso / "models--quelquun--autre-modele") in inv["non_reconnus"],
                 "dossier de modèles personnel : modèle d'un autre outil non reconnu", str(cles))
        inventaire.liberer(["modele:Systran/faster-whisper-small"], config)
        verifier((perso / "models--quelquun--autre-modele").exists() and perso.exists(),
                 "modèle d'un autre outil et dossier gardés")
    finally:
        chemins.RACINE, chemins.DOSSIER_MODELES = anciens[0], anciens[1]
        os.environ["LOCALAPPDATA"] = anciens[2] or ""

    # Ligne de commande : jamais sans confirmation.
    code, lignes, _ = cli("effacer", "--complet", "--json")
    verifier(code == 2 and lignes[-1]["erreur"]["code"] == "confirmation", "effacer sans --oui : code 2, rien effacé")
    code, lignes, _ = cli("effacer", "--complet", "--apercu", "--json")
    verifier(code == 0 and lignes[-1]["donnees"]["fait"] is False and lignes[-1]["donnees"]["apercu"]["postes"],
             "effacer --apercu : la liste et les tailles, rien de fait")
    code, lignes, _ = cli("espace", "--json")
    verifier(code == 0 and "postes" in lignes[-1]["donnees"], "espace : inventaire en JSON")

    # Regarder ou prévisualiser ne recrée rien ; effacer pour de bon, si.
    neuf = TEMPORAIRE / "jamais-cree"
    for commande in (("espace", "--json"), ("effacer", "--complet", "--apercu", "--json"), ("etat", "--json")):
        cli(*commande, env_en_plus={"SCRIBOUILLE_DONNEES": str(neuf)})
    verifier(not neuf.exists(), "espace, aperçu et etat n'écrivent rien (ni journal, ni réglages)")
    bac = TEMPORAIRE / "bac" / "donnees"
    _ecrire(bac / "config.json", texte="{}")
    _ecrire(bac / "logs" / "s.log", 10)
    _ecrire(bac / "cache-openvino" / "c", 10)
    _ecrire(bac / "modeles" / "models--Systran--faster-whisper-tiny" / "p", 10)
    _ecrire(bac / "a-quelqu-un.txt", 10)
    code, lignes, _ = cli("effacer", "--complet", "--garder-programme", "--oui", "--json",
                          env_en_plus={"SCRIBOUILLE_DONNEES": str(bac)})
    restants = sorted(p.name for p in bac.rglob("*"))
    verifier(code == 0 and restants == ["a-quelqu-un.txt"],
             "effacer --complet --oui : tout ce qui est à nous, le fichier étranger reste", f"{code} {restants}")
    (bac / "a-quelqu-un.txt").unlink()
    cli("effacer", "--complet", "--garder-programme", "--oui", "--json", env_en_plus={"SCRIBOUILLE_DONNEES": str(bac)})
    verifier(not bac.exists(), "dossier de données vide après effacement : retiré")


def principal() -> int:
    print(f"Vérification du processus moteur\n{'=' * 40}\n(dossier temporaire : {TEMPORAIRE})")
    try:
        essai_protocole()
        essai_file_de_trois()
        essai_annulation()
        essai_plantage()
        essai_orphelins()
        essai_veille_et_blocage()
        essai_ligne_de_commande()
        essai_inventaire()
    finally:
        import shutil

        shutil.rmtree(TEMPORAIRE, ignore_errors=True)
    print(f"\n{'=' * 40}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
