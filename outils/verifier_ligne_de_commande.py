"""
Vérification de la ligne de commande sans modèle ni fenêtre : analyse des
arguments, aide, erreurs d'usage, et ce que l'exécutable console décide de
lancer.

Une commande inconnue, une faute de frappe, une option inconnue ou une valeur
manquante rendent un message clair sur la sortie d'erreur et le code 2, en
quelques secondes, sans jamais ouvrir de fenêtre (y compris sans bureau ni
console, comme une tâche planifiée). L'aide se demande de quatre façons et
rend le code 0. Toute option documentée existe, toute option existante est
documentée (`docs/ligne-de-commande.md`).

Tout se passe dans un dossier temporaire : rien de l'utilisateur n'est lu ni
écrit.

    .venv\\Scripts\\python outils\\verifier_ligne_de_commande.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TEMPORAIRE = Path(tempfile.mkdtemp(prefix="scribouille-cli-"))
for nom in ("donnees", "maison", "localappdata", "appdata"):
    (TEMPORAIRE / nom).mkdir()
os.environ["SCRIBOUILLE_DONNEES"] = str(TEMPORAIRE / "donnees")
os.environ["USERPROFILE"] = os.environ["HOME"] = str(TEMPORAIRE / "maison")
os.environ["LOCALAPPDATA"] = str(TEMPORAIRE / "localappdata")
os.environ["APPDATA"] = str(TEMPORAIRE / "appdata")
# Aucune clé de désinstallation : une WhiScribe 2.x réellement installée sur
# le poste ne change rien aux essais (simulation lue seulement quand
# LOCALAPPDATA est détourné, comme ici ; voir `chemins.etat_version_2x`).
os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = "[]"
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import cli, langues  # noqa: E402

langues.definir("fr")
PYTHON = sys.executable
# Aucun processus lancé par les vérifications n'ouvre de console visible.
SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_reussites = 0
_echecs: list[str] = []


def interprete_sans_lanceur() -> tuple[str, dict]:
    """
    Le vrai python.exe, et les paquets de l'environnement virtuel en
    PYTHONPATH. Le lanceur d'un venv (`.venv\\Scripts\\python.exe`) relance
    l'interpréteur dans un processus fils : lancé sans console (tâche
    planifiée simulée), ce fils en ouvrirait une, visible à l'écran.
    """
    base = getattr(sys, "_base_executable", sys.executable) or sys.executable
    if os.path.normcase(os.path.abspath(base)) == os.path.normcase(os.path.abspath(sys.executable)):
        return sys.executable, {}
    paquets = os.pathsep.join(p for p in sys.path if p.lower().endswith("site-packages"))
    return base, {"PYTHONPATH": paquets}


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


def lancer(*arguments: str, delai: float = 30.0) -> tuple[int, str, str, list[str], float]:
    """Code, sortie standard, sortie d'erreur, modules d'interface chargés, durée."""
    audit = TEMPORAIRE / f"audit-{time.monotonic_ns()}.json"
    t0 = time.monotonic()
    try:
        p = subprocess.run([PYTHON, "-c", _AUDIT, str(audit), str(RACINE / "transcriber.pyw"), *arguments],
                           capture_output=True, timeout=delai, cwd=str(TEMPORAIRE),
                           env={**os.environ, "PYTHONIOENCODING": "cp1252"}, creationflags=SANS_FENETRE)
    except subprocess.TimeoutExpired:
        return -1, "", "délai dépassé : processus encore vivant", ["?"], delai
    charges = json.loads(audit.read_text(encoding="utf-8")) if audit.exists() else ["?"]
    return (p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace"), charges,
            time.monotonic() - t0)


# ---------------------------------------------------------------------------
# 1. Aiguillage : l'exécutable console ne lance jamais la fenêtre
# ---------------------------------------------------------------------------

def essai_aiguillage() -> None:
    titre("1. Aiguillage : scribouille.com ne lance jamais la fenêtre")
    for arguments in (["transcrir", "x.wav"], ["commande_inconnue"], ["--aide"], ["-V"], [], ["--json"],
                      ["--verifierr"], ["x.wav"]):
        verifier(cli.pour_ce_module(arguments, console=True),
                 f"exécutable console, {' '.join(arguments) or '(rien)'} : ligne de commande")
    for arguments in (["--verifier"], ["--banc", "--modes"], ["--campagne"], ["--detecter-materiel"]):
        verifier(not cli.pour_ce_module(arguments, console=True),
                 f"ancienne forme {arguments[0]} : traitée par le point d'entrée, comme avant")
    verifier(not cli.pour_ce_module([], console=False) and not cli.pour_ce_module(["x.wav"], console=False)
             and cli.pour_ce_module(["transcrire", "x.wav"], console=False),
             "exécutable fenêtré : seule une commande connue va à la ligne de commande")


# ---------------------------------------------------------------------------
# 2. Erreurs d'usage : message, code 2, rien d'autre
# ---------------------------------------------------------------------------

ERREURS = [
    (["transcrir", "x.wav"], "commande inconnue", "transcrire"),
    (["commande_inconnue"], "commande inconnue", ""),
    (["-V"], "option inconnue", ""),
    (["--verifierr"], "option inconnue", ""),
    (["transcrire"], "obligatoire", "FICHIER"),
    (["transcrire", "x.wav", "--preset", "turbo"], "turbo", "qualite"),
    (["transcrire", "x.wav", "--option-inconnue"], "inconnu", "--option-inconnue"),
    (["transcrire", "x.wav", "--sort", "D"], "inconnu", "--sort"),
    (["transcrire", "x.wav", "--sortie"], "valeur manquante", "--sortie"),
    (["transcrire", "x.wav", "--formats", "txt,pdf"], "format inconnu", "pdf"),
    (["transcrire", "x.wav", "--formats", ""], "au moins un format", ""),
    (["transcrire", "x.wav", "--langue", "xx"], "langue", "xx"),
    (["transcrire", "x.wav", "--sans-vocabulaire", "--vocabulaire", "v.toml"], "ne vont pas ensemble", ""),
    (["transcrire", "x.wav", "--moteur", "ctranslate2", "--peripherique", "GPU"], "OpenVINO", ""),
    (["transcrire", "x.wav", "--locuteurs", "beaucoup"], "--locuteurs", "beaucoup"),
    (["transcrire", "x.wav", "--locuteurs", "non", "--noms", "Alice"], "--noms", ""),
    (["lire"], "obligatoire", ""),
    (["lire", "s.json", "--limite", "0"], "--limite", ""),
    (["lire", "s.json", "--limite", "beaucoup"], "nombre", "beaucoup"),
    (["lire", "s.json", "--depuis", "20", "--jusqua", "10"], "--depuis", ""),
    (["lire", "s.json", "--texte", "--json"], "--texte", ""),
    (["exporter", "s.txt", "--remplacer", "--nouveau"], "ne vont pas ensemble", ""),
    (["reglages", "lire"], "une seule clé", ""),
    (["reglages", "liste", "theme"], "liste", ""),
    (["reglages", "effacer"], "effacer", "liste"),
    (["effacer", "--complet", "--liberable"], "--complet", ""),
    (["effacer", "journaux", "--liberable"], "--liberable", ""),
    (["effacer", "--avec-transcriptions"], "--complet", ""),
    (["effacer", "--complet", "--apercu", "--oui"], "--apercu", ""),
    (["vocabulaire", "etat", "x.toml"], "fichier", ""),
    (["vocabulaire", "importer"], "fichier manquant", ""),
    (["vocabulaire", "exporter", "v.toml", "--brut", "b.txt"], "--brut", ""),
    (["agent", "afficher", "--cible", "codex"], "installer", ""),
    (["agent", "installer", "--cible", "copilot"], "copilot", "claude"),
    (["materiel", "detecter", "--appliquer"], "proposer", ""),
    (["mesurer", "campagne", "--option-inconnue"], "--option-inconnue", ""),
    (["mesurer", "fusee"], "fusee", "campagne"),
    (["donnees"], "obligatoire", ""),
    (["aide", "transcrir"], "commande inconnue", ""),
    (["version", "--complet"], "inconnu", ""),
]


def essai_erreurs() -> None:
    titre("2. Erreurs d'usage : message en français sur la sortie d'erreur, code 2")
    lentes = []
    for arguments, attendu, aussi in ERREURS:
        code, sortie, erreur, charges, duree = lancer(*arguments)
        lentes.append(duree)
        verifier(code == 2 and attendu in erreur and aussi in erreur and erreur.startswith("Erreur : ")
                 and (not sortie.strip() or "--json" in arguments) and charges == [],
                 f"{' '.join(arguments)} : code 2, « {attendu} »",
                 f"code {code}, sortie {sortie[:120]!r}, erreur {erreur[:200]!r}, chargés {charges}")
    verifier(not any(m in "".join(lancer(*a)[2] for a, _, _ in ERREURS[:8])
                     for m in ("usage:", "error:", "invalid choice", "the following", "unrecognized")),
             "aucun message d'argparse en anglais")
    verifier(max(lentes) < 20, "chaque erreur d'usage rend la main en moins de 20 s", f"{max(lentes):.1f} s")
    code, sortie, erreur, _, _ = lancer("--json", "transcrir", "x.wav")
    lignes = [json.loads(x) for x in sortie.splitlines() if x.startswith("{")]
    verifier(code == 2 and len(lignes) == 1 and lignes[0]["erreur"]["code_retour"] == 2
             and "transcrir" in lignes[0]["erreur"]["message"] and "transcrir" in erreur,
             "--json : une enveloppe d'erreur qui dit quel argument, et le message en clair",
             f"{code} {sortie[:200]} {erreur[:100]}")
    code, sortie, _, _, _ = lancer("transcrire", "x.wav", "--preset", "turbo", "--json")
    lignes = [json.loads(x) for x in sortie.splitlines() if x.startswith("{")]
    verifier(code == 2 and lignes and lignes[0]["commande"] == "transcrire" and "turbo" in lignes[0]["erreur"]["message"]
             and "transcrire --aide" in lignes[0]["erreur"]["suggestion"],
             "--json : la commande nommée, la valeur refusée, l'aide suggérée", sortie[:200])


# ---------------------------------------------------------------------------
# 3. Aide : quatre façons de la demander, code 0
# ---------------------------------------------------------------------------

def essai_aide() -> None:
    titre("3. Aide : -h, --help, --aide, « aide », code 0")
    # Sans argument, depuis les sources, c'est la fenêtre : l'aide sans
    # argument est propre à scribouille.com (aiguillage, section 1).
    for arguments in (["--aide"], ["-h"], ["--help"], ["aide"], ["--json", "--aide"]):
        code, sortie, erreur, charges, _ = lancer(*arguments)
        verifier(code == 0 and all(c in sortie for c in cli.COMMANDES) and charges == [],
                 f"{' '.join(arguments) or '(rien)'} : aide générale, toutes les commandes", f"{code} {erreur[:100]}")
    for commande in cli.COMMANDES:
        for forme in (("--aide",), ("-h",), ("--help",)):
            code, sortie, erreur, _, _ = lancer(commande, *forme)
            options = cli.options_de(commande)
            manquantes = [o for o in options if o not in sortie]
            verifier(code == 0 and sortie.startswith(f"scribouille {commande}") and not manquantes,
                     f"{commande} {forme[0]} : son aide, toutes ses options", f"{code} {manquantes} {erreur[:120]}")
            if forme[0] != "--aide":
                continue
            code2, sortie2, _, _, _ = lancer("aide", commande)
            verifier(code2 == 0 and sortie2 == sortie, f"aide {commande} : la même")
    code, sortie, _, _, _ = lancer("transcrire", "--aide", "--json")
    donnees = json.loads(sortie.splitlines()[0])["donnees"] if sortie.startswith("{") else {}
    verifier(code == 0 and "--sortie" in donnees.get("options", []) and donnees.get("aide"),
             "aide en JSON : texte et liste des options")
    code, sortie, _, _, _ = lancer("transcrire", "--aide")
    verifier(code == 0 and "é" in sortie and "�" not in sortie, "accents intacts, même en tube (UTF-8)")


# ---------------------------------------------------------------------------
# 4. Sans bureau ni console : jamais suspendu
# ---------------------------------------------------------------------------

def _lancer_sans_bureau(commande: list[str], sortie: Path, delai_s: float) -> tuple[int, bool]:
    """Sur un bureau Windows à part, invisible, sans console. Renvoie (code, encore vivant au délai)."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    u32 = ctypes.WinDLL("user32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32.CreateDesktopW.restype = wintypes.HANDLE
    u32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
                                   wintypes.DWORD, ctypes.c_void_p]
    nom = f"scribouille-cli-{os.getpid()}"
    bureau = u32.CreateDesktopW(nom, None, None, 0, 0x10000000, None)

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

    flux = open(sortie, "wb")
    poignee = msvcrt.get_osfhandle(flux.fileno())
    os.set_handle_inheritable(poignee, True)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    si.lpDesktop = f"WinSta0\\{nom}"
    si.dwFlags = 0x100
    si.hStdOutput = si.hStdError = poignee
    pi = PROCESS_INFORMATION()
    interprete, en_plus = interprete_sans_lanceur()
    commande = [interprete if c == PYTHON else c for c in commande]
    bloc = "".join(f"{k}={v}\0" for k, v in {**os.environ, **en_plus}.items()) + "\0"
    k32.CreateProcessW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
                                   wintypes.BOOL, wintypes.DWORD, ctypes.c_wchar_p, wintypes.LPCWSTR,
                                   ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]
    ok = k32.CreateProcessW(None, ctypes.create_unicode_buffer(subprocess.list2cmdline(commande)), None, None, True,
                            0x00000008 | 0x00000400, bloc, str(TEMPORAIRE), ctypes.byref(si), ctypes.byref(pi))
    if not ok:
        flux.close()
        return -2, False
    vivant = k32.WaitForSingleObject(pi.hProcess, int(delai_s * 1000)) != 0
    if vivant:
        k32.TerminateProcess(pi.hProcess, 99)
        k32.WaitForSingleObject(pi.hProcess, 5000)
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(code))
    k32.CloseHandle(pi.hProcess)
    k32.CloseHandle(pi.hThread)
    flux.close()
    u32.CloseDesktop(bureau)
    return int(code.value), vivant


def essai_sans_bureau() -> None:
    titre("4. Sans bureau ni console (tâche planifiée, SSH) : jamais suspendu")
    for rang, arguments in enumerate((["transcrir", "x.wav"], ["--aide"], ["commande_inconnue"])):
        sortie = TEMPORAIRE / f"sans-bureau-{rang}.txt"
        code, vivant = _lancer_sans_bureau([PYTHON, str(RACINE / "transcriber.pyw"), *arguments], sortie, 30)
        texte = sortie.read_text(encoding="utf-8", errors="replace") if sortie.exists() else ""
        attendu = 0 if arguments == ["--aide"] else 2
        verifier(not vivant and code == attendu and texte.strip(),
                 f"{' '.join(arguments)} : rend la main, code {attendu}, un message",
                 f"code {code}, vivant {vivant}, {texte[:120]!r}")


# ---------------------------------------------------------------------------
# 5. Chaque option agit, ou échoue en le disant
# ---------------------------------------------------------------------------

def _json(sortie: str) -> list[dict]:
    lignes = []
    for x in sortie.splitlines():
        try:
            lignes.append(json.loads(x))
        except ValueError:
            pass
    return lignes


def essai_options_honorees() -> None:
    titre("5. Une option demandée et impossible : dite, avec son code, jamais ignorée")
    from app import diarisation, moteur_openvino

    source = TEMPORAIRE / "point.ogg"
    source.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    if not diarisation.disponible():
        code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--locuteurs", "2", "--json")
        fin = (_json(sortie) or [{}])[-1].get("erreur", {})
        verifier(code == 3 and fin.get("code") == "locuteurs_absents" and "non installée" in erreur,
                 "--locuteurs 2 sans l'extension : code 3, dit", f"{code} {fin} {erreur[:160]}")
        code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--locuteurs", "auto", "--noms", "Alice,Bob")
        verifier(code == 3 and "non installée" in erreur, "--locuteurs auto --noms sans l'extension : code 3",
                 f"{code} {erreur[:160]}")
    code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--noms", "Alice,Bob", "--json")
    fin = (_json(sortie) or [{}])[-1].get("erreur", {})
    verifier(code == 2 and "--noms" in fin.get("message", "") and "--locuteurs" in fin.get("message", ""),
             "--noms sans voix séparées : code 2, dit comment faire", f"{code} {fin}")
    absent = "NPU" if "NPU" not in (moteur_openvino.peripheriques_disponibles() if moteur_openvino.installe() else []) \
        else "GPU"
    code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--peripherique", absent, "--json")
    fin = (_json(sortie) or [{}])[-1].get("erreur", {})
    verifier(code == 3 and fin.get("code") == "moteur_absent" and absent in fin.get("message", ""),
             f"--peripherique {absent} absent : code 3, la raison dite", f"{code} {fin}")
    if not moteur_openvino.installe():
        code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--moteur", "openvino", "--json")
        fin = (_json(sortie) or [{}])[-1].get("erreur", {})
        verifier(code == 3 and "non installé" in fin.get("message", ""), "--moteur openvino non installé : code 3",
                 f"{code} {fin}")
    abime = TEMPORAIRE / "abime.toml"
    abime.write_text("format = [[[ oups\n", encoding="utf-8")
    code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--vocabulaire", str(abime))
    verifier(code == 2 and "illisible" in erreur, "--vocabulaire illisible : code 2", f"{code} {erreur[:160]}")

    # La même demande venue des réglages : dite, puis contournée.
    if not diarisation.disponible():
        lancer("reglages", "definir", "diarisation=oui")
        code, sortie, erreur, _, _ = lancer("transcrire", str(source), "--json")
        avis = [x for x in _json(sortie) if x.get("evenement") == "journal" and x.get("niveau") == "attention"]
        verifier(any("non installée" in x.get("texte", "") for x in avis) and "non installée" in erreur,
                 "voix cochées dans les réglages, extension absente : dit en JSON et sur la sortie d'erreur",
                 f"{code} {avis} {erreur[:120]}")
        lancer("reglages", "defaut", "diarisation")

    # --noms appliqués au fichier produit (file simulée, voix séparées).
    from app import cli as module_cli, sorties, superviseur, traitement
    from app.moteur import Mot, Segment

    dossier = TEMPORAIRE / "noms"
    dossier.mkdir()
    segments = [Segment(0.0, 2.0, "Bonjour à tous.", "Locuteur 1", [Mot("Bonjour", 0.0, 0.5, 0.9)]),
                Segment(2.5, 4.0, "On commence.", "Locuteur 2", [Mot("On", 2.5, 3.0, 0.9)])]
    produits = sorties.ecrire_tout(dossier, source, segments, {"duree": 4.0, "modele": "tiny", "langue": "fr",
                                                                "nb_locuteurs": 2}, {"txt": True}, avec_compagnon=True)
    chemins_produits = [p["chemin"] for p in produits]

    class FauxSuperviseur:
        def __init__(self, *a, **k):
            pass

    class FausseFile:
        def __init__(self, mat, distant=None):
            self.elements = []

        def demarrer(self, config, rappels):
            for e in self.elements:
                rappels.termine(e.identifiant, {"ok": True, "sorties": [{"chemin": c} for c in chemins_produits],
                                                "locuteurs": 2, "duree": "4 s"})
            rappels.file_terminee({"reussis": len(self.elements), "echecs": 0, "annules": 0})
            return True

        def arreter(self):
            pass

    anciens = superviseur.Superviseur, traitement.FileTraitement
    superviseur.Superviseur, traitement.FileTraitement = FauxSuperviseur, FausseFile
    try:
        element = traitement.Element(identifiant="c1", chemin=str(source), nom=source.name, taille=1,
                                     sortie=str(dossier))
        execution = module_cli._executer_file(module_cli.Sortie("transcrire", True), [element], {}, False,
                                              module_cli._noms("Alice,Bob,Chloé"))
    finally:
        superviseur.Superviseur, traitement.FileTraitement = anciens
    texte = Path(chemins_produits[0]).read_text(encoding="utf-8")
    resultat = execution["resultats"][0]
    verifier("Alice : Bonjour" in texte and "Bob : On commence" in texte
             and sorted(resultat.get("renommes") or []) == ["Locuteur 1 -> Alice", "Locuteur 2 -> Bob"],
             "--noms Alice,Bob : les voix sont renommées dans le fichier", f"{resultat} {texte[-80:]!r}")


def essai_sortie_par_defaut() -> None:
    titre("6. Dossier de données imposé : la sortie par défaut y reste")
    (TEMPORAIRE / "maison" / "Documents").mkdir(exist_ok=True)
    code, sortie, _, _, _ = lancer("reglages", "lire", "dossier_sortie", "--json")
    valeur = (_json(sortie) or [{}])[-1].get("donnees", {}).get("valeur", "")
    attendu = str(TEMPORAIRE / "donnees" / "Transcriptions")
    verifier(code == 0 and Path(valeur) == Path(attendu),
             "SCRIBOUILLE_DONNEES posé : sortie par défaut dans ce dossier, jamais Documents", f"{code} {valeur}")
    Path(attendu).mkdir(parents=True, exist_ok=True)
    code, sortie, _, _, _ = lancer("espace", "--json")
    donnees = (_json(sortie) or [{}])[-1].get("donnees", {})
    verifier(code == 0 and not any("Transcriptions" in x for x in donnees.get("non_reconnus", []))
             and Path(donnees.get("transcriptions", {}).get("dossier", "")) == Path(attendu),
             "espace : ce dossier est celui des transcriptions, pas un inconnu", str(donnees.get("non_reconnus")))
    verifier(not any((TEMPORAIRE / "maison" / "Documents").iterdir()), "rien n'est écrit dans Documents")


def essai_json_partout() -> None:
    titre("7. --json tenu par toutes les commandes : rien d'autre que du JSON sur la sortie standard")
    brut, propre = TEMPORAIRE / "brut.txt", TEMPORAIRE / "propre.txt"
    brut.write_text("On déploie sur cube air nettesse demain. Le cube air nettesse tourne.\n" * 3, encoding="utf-8")
    propre.write_text("On déploie sur Kubernetes demain. Le Kubernetes tourne.\n" * 3, encoding="utf-8")
    commandes = [("version",), ("aide",), ("etat",), ("espace",), ("reglages",), ("reglages", "lire", "rythme"),
                 ("diagnostic",), ("agent", "afficher"), ("vocabulaire", "etat"), ("materiel", "proposer"),
                 ("vocabulaire", "apprendre", "--brut", str(brut), "--propre", str(propre),
                  "--sortie", str(TEMPORAIRE / "propositions.toml")),
                 ("mesurer", "comparer"), ("effacer", "--liberable", "--apercu"), ("transcrire", "--aide")]
    for commande in commandes:
        code, sortie, erreur, _, _ = lancer(*commande, "--json")
        lignes = sortie.splitlines()
        valides = []
        for x in lignes:
            try:
                valides.append(json.loads(x))
            except ValueError:
                pass
        verifier(lignes and len(valides) == len(lignes) and all(v.get("schema") == "scribouille.cli/1" for v in valides)
                 and all(v.get("commande") == commande[0] or commande[-1] == "--aide" for v in valides),
                 f"{' '.join(commande)} --json : {len(lignes)} ligne(s), toutes JSON (code {code})",
                 f"{lignes[:2]} {erreur[-160:]}")
    code, sortie, erreur, _, _ = lancer("mesurer", "comparer", "--json")
    fin = (_json(sortie) or [{}])[-1].get("donnees", {})
    verifier(code == 2 and fin.get("code_retour") == 2 and erreur.strip(),
             "mesurer --json : le texte de l'outil sur la sortie d'erreur, son code dans l'enveloppe", str(fin))
    code, sortie, _, _, _ = lancer("verifier", "--json", delai=120)
    bilan = "\n".join((_json(sortie) or [{}])[-1].get("donnees", {}).get("bilan", []))
    verifier("Données" in bilan and "�" not in bilan and "Mode          : sources" in bilan,
             "verifier : accents intacts à travers le tube, mode juste", bilan[:200])
    code, sortie, _, _, _ = lancer("--verifier", delai=120)
    verifier("Données" in sortie and "�" not in sortie,
             "--verifier vers un tube, page de code imposée (comme un programme gelé) : UTF-8, accents intacts",
             sortie[:120])
    code, sortie, _, _, _ = lancer("vocabulaire", "etat")
    verifier(code == 0 and "{" not in sortie and "actifs" in sortie, "vocabulaire etat : un texte lisible, pas un "
             "dictionnaire brut", sortie[:160])


# ---------------------------------------------------------------------------
# 8. Documentation et comportement accordés
# ---------------------------------------------------------------------------

def _sections_commandes(texte: str) -> dict[str, str]:
    """Sections « ### commande » (ou « ### a, b ») du guide de la ligne de commande."""
    import re

    sections: dict[str, str] = {}
    morceaux = re.split(r"(?m)^### (.+)$", texte)
    for titre_section, corps in zip(morceaux[1::2], morceaux[2::2]):
        corps = corps.split("\n## ")[0]
        for nom in (n.strip() for n in titre_section.split(",")):
            sections[nom] = corps
    return sections


def essai_documentation() -> None:
    import re

    from app import config as config_module

    titre("8. Documentation et comportement accordés (aide générée, guides, réglages)")
    guide = (RACINE / "docs" / "ligne-de-commande.md").read_text(encoding="utf-8")
    sections = _sections_commandes(guide)
    for commande in cli.COMMANDES:
        corps = sections.get(commande)
        if corps is None:
            verifier(False, f"{commande} : une section dans docs/ligne-de-commande.md")
            continue
        documentees = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", corps)) - {"--json"}
        if commande == "mesurer":
            documentees -= {"--modes"}  # forme d'origine citée en regard
        existantes = set(cli.options_de(commande))
        verifier(documentees == existantes,
                 f"{commande} : options documentées = options de l'analyseur",
                 f"documentées en trop {sorted(documentees - existantes)}, absentes du guide {sorted(existantes - documentees)}")
        parseur = cli._sous_commandes(cli._analyseur())[commande]
        manquants = [f"{a.option_strings or a.dest}:{c}" for a in parseur._actions if a.choices and a.dest != "commande"
                     for c in a.choices if not c.islower() or c == c.lower() if f"{c}" not in corps]
        manquants = [m for m in manquants if not m.endswith((":cpu", ":gpu", ":npu"))]
        verifier(not manquants, f"{commande} : chaque valeur possible est dans le guide", str(manquants))

    # Toute option citée dans les guides, la fiche pour agents et les README existe.
    citees = []
    for fichier in [RACINE / "AGENTS.md", RACINE / "README.md", RACINE / "README.fr.md",
                    *sorted((RACINE / "docs").glob("*.md"))]:
        texte = fichier.read_text(encoding="utf-8")
        for trouve in re.finditer(r"scribouille(?:\.com)? ([a-z][a-z-]*)([^`\n]*)", texte):
            commande, reste = trouve.group(1), trouve.group(2)
            if commande not in cli.COMMANDES:
                continue
            for option in re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", reste):
                if option not in (*cli.options_de(commande), "--json", "--aide", "--help"):
                    citees.append(f"{fichier.name} : scribouille {commande} {option}")
    verifier(not citees, "toute option citée dans les guides, AGENTS.md et les README existe", "; ".join(citees[:8]))

    # Réglages : chaque clé documentée existe, chaque clé existante est documentée.
    reglages = (RACINE / "docs" / "reglages.md").read_text(encoding="utf-8")
    documentees = set()
    for ligne in reglages.splitlines():
        if ligne.startswith("| `") and not ligne.startswith("| `SCRIBOUILLE") and not ligne.startswith("| `TRANSCRIPTEUR"):
            documentees |= set(re.findall(r"`([a-z_]+)`", ligne.split("|")[1]))
    internes = set()
    for ligne in reglages.splitlines():
        if ligne.startswith("Clés internes"):
            internes = set(re.findall(r"`([a-z_]+)`", ligne.split(":")[0] + ":" + ligne))
    internes &= set(cli.INTERNES) | {"moteur", "peripherique"}
    attendues = (set(config_module.DEFAUTS) | set(cli.PSEUDO_CLES)) - set(cli.INTERNES)
    verifier(documentees == attendues, "reglages.md : une ligne par réglage, ni plus ni moins",
             f"en trop {sorted(documentees - attendues)}, absentes {sorted(attendues - documentees)}")
    verifier(set(cli.REGLAGES) == attendues, "chaque réglage documenté est accessible par « reglages »",
             f"{sorted(attendues ^ set(cli.REGLAGES))}")
    verifier(set(cli.INTERNES) <= internes, "les clés internes sont nommées comme telles", str(sorted(internes)))
    ecarts = []
    for ligne in reglages.splitlines():
        cellules = [c.strip() for c in ligne.split("|")]
        if len(cellules) < 4 or not cellules[1].startswith("`"):
            continue
        cles = re.findall(r"`([a-z_]+)`", cellules[1])
        if not cles:
            continue
        defaut = config_module.DEFAUTS.get(cles[0])
        cle = cles[0]
        if isinstance(defaut, bool) and cellules[2] != f"`{str(defaut).lower()}`":
            ecarts.append(f"{cle} : {cellules[2]} au lieu de {str(defaut).lower()}")
        elif isinstance(defaut, int) and not isinstance(defaut, bool) and cellules[2] != f"`{defaut}`":
            ecarts.append(f"{cle} : {cellules[2]} au lieu de {defaut}")
        elif isinstance(defaut, str) and defaut and cellules[2] != f"`{defaut}`":
            ecarts.append(f"{cle} : {cellules[2]} au lieu de {defaut}")
    verifier(not ecarts, "reglages.md : chaque valeur par défaut est la vraie", "; ".join(ecarts))
    code, sortie, _, _, _ = lancer("reglages", "--json")
    liste = {r["cle"]: r for r in (_json(sortie) or [{}])[-1].get("donnees", {}).get("reglages", [])}
    verifier(code == 0 and liste.get("peripherique", {}).get("defaut") == "CPU"
             and liste.get("dossier_sortie", {}).get("defaut") and liste.get("theme"),
             "reglages : défauts de peripherique et dossier_sortie affichés comme documentés, theme présent",
             str({k: liste.get(k, {}).get("defaut") for k in ("peripherique", "dossier_sortie", "theme")}))
    code, sortie, _, _, _ = lancer("reglages", "definir", "formats=txt,srt")
    verifier(code == 0 and '"horodatage": false' in sortie and '"srt": true' in sortie,
             "definir formats=txt,srt : la sortie montre horodatage coupé", sortie[-200:])
    code, _, erreur, _, _ = lancer("reglages", "lire", "zoom")
    verifier(code == 2 and "fenêtre" in erreur, "clé interne : refusée, et dite comme telle", erreur[:120])
    lancer("reglages", "defaut", "formats")

    # Les textes, l'aide et les guides donnent la syntaxe d'aujourd'hui (PC du
    # travail, 15/11 : « scribouille.com --reconnaitre --appliquer » après
    # `materiel proposer`). Les anciennes formes ne restent que dans leur table.
    ancienne = re.compile(r"(scribouille(\.com)?|transcriber\.pyw|Scribouille\.exe) --(banc|campagne|endurance|"
                          r"comparer|reconnaitre|mesurer-vocabulaire|apprendre-vocabulaire|detecter-materiel)\b"
                          r"|--reconnaitre --appliquer")
    trouves = []
    for relatif in ("app/langues.py", "web/langues.js", "web/app.js", "web/index.html", "docs/guide.fr.md",
                    "docs/guide.md", "docs/reglages.md", "README.md", "README.fr.md", "AGENTS.md"):
        texte = (RACINE / relatif).read_text(encoding="utf-8")
        trouves += [f"{relatif}:{n}" for n, ligne in enumerate(texte.splitlines(), 1) if ancienne.search(ligne)]
    hors_table = [ligne for ligne in guide.split("### Anciennes formes")[0].splitlines() if ancienne.search(ligne)]
    textes_aide = cli._analyseur().format_help() + "".join(p.format_help() for p in cli._sous_commandes(
        cli._analyseur()).values())
    verifier(not trouves and not hors_table and not ancienne.search(textes_aide),
             "textes, aide et guides : aucune syntaxe d'avant la 3.0 (hors de la table des anciennes formes)",
             str(trouves[:6] + hors_table[:3]))


# ---------------------------------------------------------------------------
# 9. Aucune fenêtre de console, jamais
# ---------------------------------------------------------------------------

_LANCEMENTS = ("Popen", "run", "call", "check_call", "check_output")


def lancements_sans_drapeau() -> list[str]:
    """Chaque lancement de processus du dépôt qui n'interdit pas la console (CREATE_NO_WINDOW)."""
    import ast

    fautifs = []
    fichiers = [*sorted((RACINE / "app").glob("*.py")), RACINE / "transcriber.pyw",
                *sorted((RACINE / "outils").glob("*.py"))]
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not (isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Attribute)
                    and noeud.func.attr in _LANCEMENTS and isinstance(noeud.func.value, ast.Name)
                    and noeud.func.value.id == "subprocess"):
                continue
            premier = noeud.args[0] if noeud.args else None
            if isinstance(premier, ast.List) and premier.elts and isinstance(premier.elts[0], ast.Constant) \
                    and premier.elts[0].value in ("open", "xdg-open"):
                continue  # macOS et Linux seulement
            if not any(k.arg == "creationflags" for k in noeud.keywords):
                fautifs.append(f"{fichier.name}:{noeud.lineno}")
    return fautifs


def _fenetres_pendant(commande: list[str], delai_s: float) -> tuple[int, list[str]]:
    """
    Lance `commande` sans console (DETACHED_PROCESS, comme une tâche
    planifiée ou un service) et relève toute fenêtre qui paraît pendant
    l'exécution : fenêtre d'un processus de son arbre, ou console nouvelle
    où qu'elle soit (Windows Terminal héberge les consoles hors de l'arbre).
    Il ne doit y en avoir aucune.
    """
    import ctypes
    from ctypes import wintypes

    import psutil

    u32 = ctypes.WinDLL("user32", use_last_error=True)
    RAPPEL = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    consoles = ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow")

    def fenetres() -> dict:
        trouvees = {}

        def noter(hwnd, _):
            pid = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            classe = ctypes.create_unicode_buffer(128)
            u32.GetClassNameW(hwnd, classe, 128)
            trouvees[hwnd] = (pid.value, classe.value, bool(u32.IsWindowVisible(hwnd)))
            return True

        u32.EnumWindows(RAPPEL(noter), 0)
        return trouvees

    avant = set(fenetres())
    interprete, en_plus = interprete_sans_lanceur()
    commande = [interprete if c == PYTHON else c for c in commande]
    p = subprocess.Popen(commande, cwd=str(TEMPORAIRE), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=0x00000008, env={**os.environ, **en_plus})
    arbre: set[int] = {p.pid}
    vues: list[str] = []
    limite = time.monotonic() + delai_s
    while p.poll() is None and time.monotonic() < limite:
        try:
            arbre |= {c.pid for c in psutil.Process(p.pid).children(recursive=True)}
        except psutil.Error:
            pass
        for hwnd, (pid, classe, visible) in fenetres().items():
            if hwnd in avant:
                continue
            if (pid in arbre and (visible or classe in consoles)) or classe in consoles[:2]:
                if classe not in vues:
                    vues.append(classe)
        time.sleep(0.01)
    if p.poll() is None:
        p.kill()
        vues.append("(délai dépassé)")
    return p.wait(), vues


def essai_aucune_console() -> None:
    titre("9. Aucune fenêtre de console : ni la ligne de commande, ni le moteur, ni la détection")
    fautifs = lancements_sans_drapeau()
    verifier(not fautifs, "chaque lancement de processus du dépôt interdit la console (CREATE_NO_WINDOW)",
             ", ".join(fautifs))
    # La détection de fond, lancée à chaque ouverture de la fenêtre, ne passe
    # plus par un programme console (qui a toujours son conhost.exe caché).
    from app import chemins, materiel

    gele, programme = chemins.EST_GELE, chemins.DOSSIER_PROGRAMME
    faux = TEMPORAIRE / "programme-gele"
    faux.mkdir(exist_ok=True)
    for nom in ("Scribouille.exe", "scribouille.com"):
        (faux / nom).write_bytes(b"MZ")
    chemins.EST_GELE, chemins.DOSSIER_PROGRAMME = True, faux
    try:
        commande_gelee = materiel._commande_detection()[0]
    finally:
        chemins.EST_GELE, chemins.DOSSIER_PROGRAMME = gele, programme
    commande_sources = materiel._commande_detection()[0]
    verifier(Path(commande_gelee[0]).name == "Scribouille.exe" and commande_gelee[1:] == ["--detecter-materiel"]
             and Path(commande_sources[0]).name.lower() in ("pythonw.exe", "python.exe"),
             "détection du matériel : exécutable fenêtré (gelé) ou pythonw.exe (sources), jamais un programme console",
             f"{commande_gelee} {commande_sources}")
    source = TEMPORAIRE / "console.ogg"
    source.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    os.environ["SCRIBOUILLE_MOTEUR_ESSAI"] = json.dumps({"segments": 6, "pause_s": 0.05})
    try:
        for arguments, libelle in (
                (["transcrire", str(source), "--json", "--telecharger", "--sortie", str(TEMPORAIRE / "console")],
                 "transcription (processus moteur)"),
                (["verifier", "--json"], "verifier (bilan dans un processus fils)"),
                (["materiel", "--json"], "détection lente du matériel (processus de fond, PowerShell)")):
            code, vues = _fenetres_pendant([PYTHON, str(RACINE / "transcriber.pyw"), *arguments], 180)
            verifier(code in (0, 1, 3) and not vues, f"{libelle}, lancée sans console : aucune fenêtre ne paraît",
                     f"code {code}, fenêtres {vues}")
    finally:
        os.environ.pop("SCRIBOUILLE_MOTEUR_ESSAI", None)


# ---------------------------------------------------------------------------
# 10. Commandes de lecture : rien n'est écrit, dossier partagé avec une 2.x
# ---------------------------------------------------------------------------

#: `config.json` tel qu'une WhiScribe 2.3.3 l'écrit (ses clés, dont
#: `lecture_audio` que la 3.0 ne connaît pas, et la séparation des voix cochée
#: par défaut), recopié du dépôt à la révision v2.3.3.
CONFIG_2X = {"preset": "qualite", "langue": "fr", "langue_interface": "fr", "dossier_sortie": "",
             "diarisation": True, "nb_locuteurs": 0,
             "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
             "appliquer_corrections": True, "utiliser_glossaire": True, "compagnon_confiance": True,
             "corrections_apprises": True, "sauvegarde_progressive": True, "lecture_audio": False,
             "motif_sortie": "", "dossier_surveille": "", "surveillance": False, "maj_verifier": False,
             "barre_taches": True, "filtres_salle": False, "mode_avance": False, "modele_avance": "",
             "beam_size": 0, "condition_on_previous_text": True, "forcer_processeur": False, "theme": "auto",
             "zoom": 1.0, "journal_ouvert": False}


def poste_partage(nom: str) -> tuple[Path, Path, dict]:
    """
    Un poste comme celui du travail : WhiScribe 2.3.3 installée (exécutable
    factice) qui lit `%LOCALAPPDATA%\\WhiScribe`, la 3.0 qui y travaille aussi,
    le témoin de la puce d'avant (3 octets), une transcription à lire.
    Renvoie (maison, dossier de données, environnement).
    """
    maison = TEMPORAIRE / nom
    local = maison / "AppData" / "Local"
    donnees = local / "WhiScribe"
    (local / "Programs" / "WhiScribe").mkdir(parents=True)
    (local / "Programs" / "WhiScribe" / "WhiScribe.exe").write_bytes(b"MZ factice")
    (donnees / "logs").mkdir(parents=True)
    (donnees / "modeles").mkdir()
    (maison / "Documents").mkdir()
    config = dict(CONFIG_2X, dossier_sortie=str(maison / "Documents" / "Transcriptions"))
    (donnees / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (donnees / "vocabulaire.txt").write_text("Kubernetes\n", encoding="utf-8")
    (donnees / "corrections.txt").write_text("cube air nettesse -> Kubernetes\n", encoding="utf-8")
    (donnees / "openvino-chargement-en-cours.txt").write_text("GPU", encoding="utf-8")
    (donnees / "logs" / "whiscribe-ancien.log").write_text("journal de la 2.x\n", encoding="utf-8")
    env = {**os.environ, "SCRIBOUILLE_DONNEES": str(donnees), "LOCALAPPDATA": str(local),
           "USERPROFILE": str(maison), "HOME": str(maison), "APPDATA": str(maison / "AppData" / "Roaming")}
    env.pop("SCRIBOUILLE_MOTEUR_ESSAI", None)
    return maison, donnees, env


def empreinte(racine: Path) -> dict[str, tuple]:
    """Chaque fichier et dossier sous `racine` : taille, date de modification, contenu (SHA-256)."""
    import hashlib

    vues: dict[str, tuple] = {}
    for chemin in sorted(racine.rglob("*")):
        relatif = chemin.relative_to(racine).as_posix()
        infos = chemin.stat()
        if chemin.is_dir():
            vues[relatif + "/"] = ("dossier", infos.st_mtime_ns)
        else:
            vues[relatif] = (infos.st_size, infos.st_mtime_ns, hashlib.sha256(chemin.read_bytes()).hexdigest())
    return vues


def differences(avant: dict, apres: dict) -> list[str]:
    return sorted({*[c for c in avant if avant[c] != apres.get(c)], *[c for c in apres if c not in avant]})


def lancer_dans(env: dict, *arguments: str, delai: float = 120.0) -> tuple[int, str, str]:
    p = subprocess.run([PYTHON, str(RACINE / "transcriber.pyw"), *arguments], capture_output=True, timeout=delai,
                       cwd=str(TEMPORAIRE), env={**env, "PYTHONIOENCODING": "utf-8"}, creationflags=SANS_FENETRE)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


_DEMARRAGE_FENETRE = r"""
import runpy, sys, time
sys.argv = [sys.argv[1]]
ns = runpy.run_path(sys.argv[0], run_name="essai-demarrage")
passerelle = ns["Passerelle"]()
etat = passerelle.etat_initial()
time.sleep(1.0)  # le préchauffage de fond
print("pret", etat["vitesse"]["puce"]["etat"], flush=True)
"""


def essai_lecture_sans_ecriture() -> None:
    titre("10. Commandes de lecture : rien n'est écrit (dossier partagé avec une WhiScribe 2.x)")
    maison, donnees, env = poste_partage("poste-partage")
    from app import sorties
    from app.moteur import Mot, Segment

    lu = maison / "Documents" / "reunion"
    lu.mkdir()
    (lu / "reunion.ogg").write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    produits = sorties.ecrire_tout(lu, lu / "reunion.ogg", [Segment(0.0, 2.0, "Bonjour.", None, [
        Mot("Bonjour", 0.0, 0.5, 0.9)])], {"duree": 2.0, "modele": "tiny", "langue": "fr"}, {"txt": True},
        avec_compagnon=True)
    compagnon = next(p["chemin"] for p in produits if str(p["chemin"]).endswith(".txt"))
    lectures = [("version",), ("aide",), ("aide", "transcrire"), ("transcrire", "--aide"), ("diagnostic",),
                ("diagnostic", "--json"), ("verifier",), ("verifier", "--json"), ("--verifier",), ("etat",),
                ("etat", "--json"), ("lire", str(compagnon), "--json"), ("lire", str(compagnon), "--texte"),
                ("materiel", "proposer", "--json"), ("materiel", "puce"), ("materiel", "puce", "--json"),
                ("reglages",), ("reglages", "lire", "diarisation"), ("vocabulaire", "etat"), ("agent", "afficher"),
                ("espace", "--json")]
    for commande in lectures:
        avant = empreinte(maison)
        code, sortie, erreur = lancer_dans(env, *commande)
        changes = differences(avant, empreinte(maison))
        verifier(code in (0, 3) and not changes, f"{' '.join(commande)} : rien d'écrit ni de redaté (code {code})",
                 f"{changes[:6]} {erreur[-200:]}")
    from app import chemins

    for commande, attendu in ((["etat", "--nettoyer"], False), (["materiel", "proposer", "--appliquer"], False),
                              (["materiel", "puce", "--lever"], False), (["reglages", "definir", "theme=clair"], False),
                              (["vocabulaire", "etat"], True), (["--verifier"], True), (["lire", "x.json"], True)):
        verifier(chemins.commande_de_lecture(commande) is attendu,
                 f"{' '.join(commande)} : {'lecture' if attendu else 'écriture permise'}")

    # Le témoin d'avant (3 octets) ne suspend pas la puce ; diagnostic et etat le disent.
    code, sortie, _ = lancer_dans(env, "diagnostic", "--json")
    donnees_diag = (_json(sortie) or [{}])[-1].get("donnees", {})
    verifier(donnees_diag.get("puce", {}).get("etat") == "a_verifier"
             and any("puce graphique" in a for a in donnees_diag.get("avertissements", []))
             and any("non installée" in a for a in donnees_diag.get("avertissements", [])),
             "diagnostic : puce « à vérifier » (témoin sans auteur), voix cochées sans extension, dits",
             str({k: donnees_diag.get(k) for k in ("puce", "avertissements")})[:300])
    verifier(donnees_diag.get("donnees_partagees", "").lower().endswith("whiscribe.exe"),
             "diagnostic : le partage avec la 2.x installée est dit", donnees_diag.get("donnees_partagees", ""))
    code, sortie, _ = lancer_dans(env, "etat", "--json")
    verifier(((_json(sortie) or [{}])[-1].get("donnees", {}).get("puce") or {}).get("etat") == "a_verifier",
             "etat : l'état de la puce y est aussi")

    # Le lancement de la fenêtre (côté Python : passerelle et état initial) :
    # ni config.json de la 2.x, ni réglages, ni cache du matériel inchangé ne
    # sont réécrits. Seuls le journal de la session et le profil d'affichage
    # peuvent apparaître.
    (donnees / "materiel.json").write_text(json.dumps({"version": 1, "gpus": [], "npus": [], "a_nvidia": False,
                                                        "cuda_disponible": False, "openvino": {
                                                            "installe": False, "version": "", "peripheriques": []}},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    avant = empreinte(maison)
    p = subprocess.run([PYTHON, "-c", _DEMARRAGE_FENETRE, str(RACINE / "transcriber.pyw")], capture_output=True,
                       timeout=180, cwd=str(TEMPORAIRE), env=env, creationflags=SANS_FENETRE)
    changes = [c for c in differences(avant, empreinte(maison))
               if not c.startswith(("AppData/Local/WhiScribe/logs/", "AppData/Local/WhiScribe/webview"))
               and c != "AppData/Local/WhiScribe/logs/"]
    verifier(p.returncode == 0 and b"pret a_verifier" in p.stdout and not changes,
             "démarrage de la fenêtre sur le dossier partagé : seul le journal s'ajoute",
             f"{changes[:6]} {p.stderr.decode('utf-8', 'replace')[-300:]}")
    from app import materiel

    lent = json.loads((donnees / "materiel.json").read_text(encoding="utf-8"))
    lent.pop("version", None)
    date_avant = (donnees / "materiel.json").stat().st_mtime_ns
    contenu_avant = (donnees / "materiel.json").read_bytes()
    racine_reelle = chemins.RACINE
    chemins.RACINE = donnees
    try:
        materiel.ecrire_cache(lent)
    finally:
        chemins.RACINE = racine_reelle
    verifier((donnees / "materiel.json").stat().st_mtime_ns == date_avant
             and (donnees / "materiel.json").read_bytes() == contenu_avant,
             "détection du matériel inchangée : materiel.json ni réécrit ni redaté")

    # Une commande qui écrit, sur le dossier partagé : config.json de la 2.x
    # intact à l'octet (ni clé ajoutée, ni `lecture_audio` retirée), nos
    # réglages dans notre fichier, et relus.
    config_2x = (donnees / "config.json").read_bytes()
    code, _, erreur = lancer_dans(env, "reglages", "definir", "theme=sombre", "rythme=discret")
    propre = donnees / "config-scribouille.json"
    contenu_propre = json.loads(propre.read_text(encoding="utf-8")) if propre.is_file() else {}
    verifier(code == 0 and (donnees / "config.json").read_bytes() == config_2x
             and contenu_propre == {"theme": "sombre", "rythme": "discret"},
             "reglages definir, WhiScribe 2.x installée : config.json intact, nos réglages à part (seuls les changés)",
             f"{code} {contenu_propre} {erreur[-160:]}")
    code, sortie, _ = lancer_dans(env, "reglages", "lire", "theme", "--json")
    verifier((_json(sortie) or [{}])[-1].get("donnees", {}).get("valeur") == "sombre",
             "et relus par la 3.0")
    journaux = list((donnees / "logs" / "scribouille").glob("*.log"))
    texte = "".join(f.read_text(encoding="utf-8", errors="replace") for f in journaux)
    verifier("Données gardées dans" in texte and "WhiScribe.exe" in texte,
             "journal de la ligne de commande : « Données gardées dans … » comme celui de la fenêtre",
             f"{len(journaux)} journaux")
    source = maison / "Documents" / "point.ogg"
    source.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    avis = []
    factice = {**env, "SCRIBOUILLE_MOTEUR_ESSAI": json.dumps({"segments": 2, "pause_s": 0.01})}
    for _ in range(3):
        code, sortie, erreur = lancer_dans(factice, "transcrire", str(source), "--json", "--telecharger", "--ecraser")
        evenements = _json(sortie)
        debut = next((x for x in evenements if x.get("evenement") == "debut"), {})
        avis.append(("non installée" in erreur,
                     any(x.get("evenement") == "journal" and "non installée" in x.get("texte", "")
                         for x in evenements),
                     debut.get("locuteurs") == {"demandes": True, "disponibles": False} if debut else None))
    verifier(avis[0][:2] == (True, True) and all(a[:2] == (False, False) for a in avis[1:])
             and (donnees / "config.json").read_bytes() == config_2x,
             "voix cochées par la 2.x, extension absente : dit une fois pour de bon, plus aucun avis ensuite",
             str(avis))
    verifier(all(a[2] is True for a in avis),
             "et toujours lisible en JSON (champ « locuteurs » de l'événement « debut »)", str(avis))
    # La 2.x désinstallée : la sauvegarde suivante reverse nos réglages dans
    # config.json, garde les clés inconnues, et notre fichier s'en va.
    (maison / "AppData" / "Local" / "Programs" / "WhiScribe" / "WhiScribe.exe").unlink()
    code, _, erreur = lancer_dans(env, "reglages", "definir", "theme=clair")
    fusion = json.loads((donnees / "config.json").read_text(encoding="utf-8"))
    verifier(code == 0 and not propre.exists() and fusion.get("theme") == "clair" and fusion.get("rythme") == "discret"
             and "lecture_audio" in fusion,
             "2.x partie : nos réglages reversés dans config.json, clés de la 2.x gardées, fichier à part retiré",
             f"{code} {sorted(fusion)[:5]} {erreur[-160:]}")


# ---------------------------------------------------------------------------
# 11. Dossier partagé avec une 2.x : rien de la 2.x ne disparaît ni ne change
# ---------------------------------------------------------------------------

_FENETRE_ET_MENAGE = r"""
import runpy, sys, time
sys.argv = [sys.argv[1]]
ns = runpy.run_path(sys.argv[0], run_name="essai-demarrage")
passerelle = ns["Passerelle"]()
passerelle.etat_initial()
# Le ménage que la fenêtre fait une fois la page chargée (`_au_demarrage`).
ns["reprise"].purger()
time.sleep(1.0)
print("pret", flush=True)
"""


def _tuer_arbre(p: subprocess.Popen) -> None:
    """La commande et son moteur tués net (console fermée, courant coupé)."""
    import psutil

    arbre = []
    try:
        racine = psutil.Process(p.pid)
        arbre = racine.children(recursive=True) + [racine]
        for e in arbre:
            try:
                e.kill()
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    p.wait(30)
    psutil.wait_procs(arbre, timeout=30)


def poste_2x_complet(nom: str) -> tuple[Path, Path, dict]:
    """
    Le poste du travail, avec de vrais restes de WhiScribe 2.x de toutes
    sortes : 51 journaux (dont 11 du 12/11) et son bilan, des reprises (source
    disparue, source présente, segments sans état, écriture provisoire, état
    illisible), réglages, glossaire, jeton, sauvegarde, extensions, cache,
    modèle. Tous vieux de 60 jours, comme l'étaient ceux du 12/11.
    """
    maison, donnees, env = poste_partage(nom)
    # Témoin de la puce : protocole partagé, réécrit à dessein par une ouverture sur la puce.
    (donnees / "openvino-chargement-en-cours.txt").unlink()
    vieux = time.time() - 60 * 86400
    for k in range(51):
        jour = "2026-11-12" if k >= 40 else f"2026-10-{1 + k % 28:02d}"
        (donnees / "logs" / f"{jour}_{100000 + k}.log").write_text(f"journal de la 2.x numéro {k}\n", encoding="utf-8")
    (donnees / "logs" / "verification.txt").write_text("bilan de la 2.x\n", encoding="utf-8")
    reprises = donnees / "reprises"
    reprises.mkdir()
    presente = maison / "Documents" / "deux-x.ogg"
    presente.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())

    def etat_2x(source: Path) -> str:
        return json.dumps({"version": 1, "source": str(source), "nom": source.name, "modele": "large-v3",
                           "duree_audio": 60.0, "debut": "2026-09-15T10:00:00", "position": 10.0,
                           "nb_segments": 1, "ecoule": 5.0, "maj": "2026-09-15T10:01:00"})

    segment = json.dumps({"d": 0.0, "f": 10.0, "t": "Texte de la 2.x.", "m": []}) + "\n"
    (reprises / "aaaaaaaaaaaaaaaa.json").write_text(etat_2x(maison / "disparu.ogg"), encoding="utf-8")
    (reprises / "aaaaaaaaaaaaaaaa.jsonl").write_text(segment, encoding="utf-8")
    (reprises / "bbbbbbbbbbbbbbbb.json").write_text(etat_2x(presente), encoding="utf-8")
    (reprises / "bbbbbbbbbbbbbbbb.jsonl").write_text(segment, encoding="utf-8")
    (reprises / "cccccccccccccccc.jsonl").write_text(segment, encoding="utf-8")
    (reprises / "dddddddddddddddd.json.tmp").write_text("{", encoding="utf-8")
    (reprises / "eeeeeeeeeeeeeeee.json").write_text("illisible", encoding="utf-8")
    for nom_fichier, contenu in (("jeton_hf.txt", "hf_factice\n"), ("gabarit-ia.txt", "Résume.\n"),
                                 ("maj-etat.json", "{}"), ("surveillance-vus.json", "[]"),
                                 ("whiscribe-donnees-avant-import-20261001-1000.zip", "PK"),
                                 ("extensions/locuteurs.txt", "2.x"), ("cache-pip/paquet.whl", "roue"),
                                 ("modeles/models--Systran--faster-whisper-tiny/blobs/poids", "poids")):
        (donnees / nom_fichier).parent.mkdir(parents=True, exist_ok=True)
        (donnees / nom_fichier).write_text(contenu, encoding="utf-8")
    for f in donnees.rglob("*"):
        if f.is_file():
            os.utime(f, (vieux, vieux))
    return maison, donnees, env


def fichiers_de(racine: Path, sauf=()) -> dict[str, tuple]:
    """Empreinte des seuls fichiers (pas des dossiers, que nos propres fichiers redatent)."""
    return {c: v for c, v in empreinte(racine).items() if not c.endswith("/") and not c.startswith(tuple(sauf))}


def essai_dossier_partage_intact() -> None:
    titre("11. Dossier partagé avec une WhiScribe 2.x : rien de la 2.x ne disparaît ni ne change")
    from app import presets

    maison, donnees, env = poste_2x_complet("poste-2x-complet")
    nos_journaux = donnees / "logs" / "scribouille"
    nos_journaux.mkdir()
    maintenant = time.time()
    for k in range(70):
        f = nos_journaux / f"2026-09-{1 + k % 28:02d}_{200000 + k}.log"
        f.write_text(f"journal de la 3.x numéro {k}\n", encoding="utf-8")
        date = maintenant - (60 * 86400 if k < 60 else 86400) + k
        os.utime(f, (date, date))
    deux_x = fichiers_de(donnees)
    deux_x = {c: v for c, v in deux_x.items() if not c.startswith("logs/scribouille/")}

    def intacts(etape: str) -> None:
        apres = fichiers_de(donnees)
        changes = sorted(c for c in deux_x if apres.get(c) != deux_x[c])
        verifier(not changes, f"{etape} : les {len(deux_x)} fichiers de la 2.x sont tous là, inchangés", str(changes[:6]))

    # Ouverture de la fenêtre (côté Python), purge des journaux et des reprises comprise.
    p = subprocess.run([PYTHON, "-c", _FENETRE_ET_MENAGE, str(RACINE / "transcriber.pyw")], capture_output=True,
                       timeout=180, cwd=str(TEMPORAIRE), env=env, creationflags=SANS_FENETRE)
    verifier(p.returncode == 0 and b"pret" in p.stdout, "démarrage de la fenêtre sur le dossier partagé",
             p.stderr.decode("utf-8", "replace")[-300:])
    intacts("ouverture de la fenêtre")
    restants = sorted(nos_journaux.glob("*.log"), key=lambda f: f.stat().st_mtime)
    recents = [f for f in restants if maintenant - f.stat().st_mtime < 30 * 86400]
    verifier(len(restants) == 50 and len(recents) == 11,
             "nos journaux seulement, et doucement : plus de 30 jours et au-delà des 50 derniers",
             f"{len(restants)} restants, {len(recents)} récents")
    # Une deuxième ouverture tout de suite : rien de plus n'est effacé.
    subprocess.run([PYTHON, "-c", _FENETRE_ET_MENAGE, str(RACINE / "transcriber.pyw")], capture_output=True,
                   timeout=180, cwd=str(TEMPORAIRE), env=env, creationflags=SANS_FENETRE)
    apres = list(nos_journaux.glob("*.log"))
    verifier(len(apres) == 50 and len([f for f in apres if maintenant - f.stat().st_mtime < 30 * 86400]) == 12,
             "ouverture suivante : toujours les 50 derniers, rien de récent effacé", str(len(apres)))
    intacts("deuxième ouverture")

    # Une transcription complète (moteur factice), puis une coupée net sur la puce.
    sorties = maison / "Documents" / "sorties"
    source = maison / "Documents" / "trois-x.ogg"
    source.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    factice = {**env, "SCRIBOUILLE_MOTEUR_ESSAI": json.dumps({"segments": 4, "pause_s": 0.01})}
    code, _sortie, erreur = lancer_dans(factice, "transcrire", str(source), "--sortie", str(sorties),
                                        "--locuteurs", "non", "--telecharger", "--json")
    verifier(code == 0, "transcription complète sur le dossier partagé", erreur[-200:])
    intacts("transcription")
    coupee = maison / "Documents" / "coupee.ogg"
    coupee.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    lente = {**env, "SCRIBOUILLE_MOTEUR_ESSAI": json.dumps({"segments": 40, "pause_s": 0.3, "puce": True})}
    p = subprocess.Popen([PYTHON, str(RACINE / "transcriber.pyw"), "transcrire", str(coupee), "--sortie",
                          str(sorties), "--locuteurs", "non", "--telecharger", "--json"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(TEMPORAIRE),
                         env={**lente, "PYTHONIOENCODING": "utf-8"}, creationflags=SANS_FENETRE)

    def deux_segments() -> bool:
        for f in (donnees / "reprises").glob("*.etat"):
            try:
                etat = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if etat.get("auteur") and etat.get("nb_segments", 0) >= 2:
                return True
        return False

    limite = time.monotonic() + 90
    while time.monotonic() < limite and not deux_segments():
        time.sleep(0.1)
    _tuer_arbre(p)
    verrous = list((donnees / "reprises").glob("*.en-cours"))
    code, sortie, _ = lancer_dans(env, "etat", "--json")
    etat = (_json(sortie) or [{}])[-1].get("donnees", {})
    taches, orphelines = etat.get("taches") or [], etat.get("orphelines") or []
    attendu = presets.depot_openvino(presets.modele_du_preset("qualite"))
    verifier(len(taches) == 1 and Path(taches[0]["chemin"]).name == "coupee.ogg",
             "coupure : notre tâche reprenable, et pas celles de la 2.x", str([t.get("nom") for t in taches]))
    verifier(bool(verrous) and not [o for o in orphelines if o.get("raison") == "verrou_mort"],
             "le verrou laissé par la coupure va avec la tâche reprenable : pas d'orpheline « verrou_mort »",
             f"{len(verrous)} verrou(s) ; {orphelines}")
    verifier(not orphelines, "aucune orpheline : les restes de la 2.x ne sont pas pris pour les nôtres",
             str([(o.get('raison'), o.get('fichiers')) for o in orphelines])[:300])
    verifier(taches and taches[0].get("modele") == attendu and taches[0].get("calcul", "").lower() == "openvino-gpu"
             and taches[0].get("modele_demande") == presets.modele_du_preset("qualite"),
             "etat : le modèle réellement chargé sur la puce (OpenVINO), pas celui du catalogue",
             str({k: (taches or [{}])[0].get(k) for k in ("modele", "calcul", "modele_demande")}))
    intacts("coupure pendant la transcription")
    code, _sortie, erreur = lancer_dans(factice, "reprendre", "--json")
    verifier(code == 0, "reprise de notre tâche", erreur[-200:])
    intacts("reprise")
    code, sortie, _ = lancer_dans(env, "etat", "--nettoyer", "--json")
    etat = (_json(sortie) or [{}])[-1].get("donnees", {})
    verifier(code == 0 and not etat.get("taches") and not etat.get("nettoyees"),
             "etat --nettoyer : rien à nous à nettoyer, rien de la 2.x effacé", str(etat.get("nettoyees"))[:200])
    intacts("nettoyage des reprises")
    code, sortie, erreur = lancer_dans(env, "effacer", "--liberable", "--oui", "--json")
    verifier(code == 0 and not list(nos_journaux.glob("*.log"))[1:], "effacer --liberable : nos journaux partent",
             erreur[-200:])
    intacts("effacer --liberable")
    code, sortie, _ = lancer_dans(env, "effacer", "--complet", "--apercu", "--json")
    apercu = (_json(sortie) or [{}])[-1].get("donnees", {}).get("apercu", {})
    chemins_postes = {Path(c).name for p_ in apercu.get("postes", []) for c in p_.get("chemins", [])}
    partages = {Path(c).name for c in apercu.get("partages", [])}
    verifier({"config.json", "vocabulaire.txt", "modeles", "extensions", "reprises", "logs"} <= partages
             and not chemins_postes & {"config.json", "vocabulaire.txt", "modeles", "extensions", "reprises", "logs",
                                       "jeton_hf.txt", "cache-pip"},
             "effacer --complet : ce que la 2.x écrit aussi est montré à part, dans aucun poste effaçable",
             f"partagés {sorted(partages)} ; postes {sorted(chemins_postes)[:12]}")
    code, sortie, _ = lancer_dans(env, "diagnostic")
    verifier("Données gardées dans" in sortie and "WhiScribe.exe" in sortie,
             "diagnostic : « Données gardées dans … » (dossier partagé avec la 2.x)", sortie[-300:])
    code, sortie, _ = lancer_dans(env, "verifier")
    verifier("Données gardées dans" in sortie, "verifier : la même phrase", sortie[:400])
    code, sortie, _ = lancer_dans(env, "materiel", "proposer")
    verifier("materiel proposer --appliquer" in sortie and "--reconnaitre" not in sortie,
             "materiel proposer : la commande pour appliquer est dans la syntaxe actuelle", sortie[-200:])


_REDEPOT_FENETRE = r"""
import json, os, runpy, sys
from pathlib import Path
sys.argv = [sys.argv[1]]
ns = runpy.run_path(sys.argv[0], run_name="essai-demarrage")
from app import config as config_module, reprise as r
from app.moteur import Segment
source = Path(os.environ["ESSAI_SOURCE"])
p = ns["Passerelle"]()
modele = config_module.reglages_effectifs(p.config)["modele"]
cle = r.cle(source, modele)
s = r.Session(cle, active=True)
s.ouvrir(source, modele, 60.0, nouvelle=True)
s.ajouter(Segment(debut=0.0, fin=1.0, texte="Gardé", mots=[]), 1.0)
s.fermer()
appels = []
p._js = appels.append
p.file.mesurer_durees = lambda rappel: None   # pas de moteur à lancer ici
p._enregistrer_fichiers([str(source)])
el = p.file.elements[0]
avant = {"reprise": el.reprise, "propose": any(a.startswith("onReprisesTrouvees(") and cle in a for a in appels),
         "segments": len(r.lire_segments(cle))}
retour = getattr(p, "recommencer", lambda i: {"ok": False})(el.identifiant)
apres = {"ok": retour.get("ok"), "reprise": el.reprise, "recommencer": getattr(el, "recommencer", None),
         "garde": r.a_garder(cle)}
print("RESULTAT " + json.dumps([avant, apres, cle]), flush=True)
"""


def essai_redepot_fenetre() -> None:
    """Revue du 15/11 (S2) : redéposer un fichier interrompu ne l'efface plus, la fenêtre propose de recommencer."""
    titre("12. Fenêtre : fichier redéposé qui a une reprise")
    maison = TEMPORAIRE / "redepot"
    donnees = maison / "donnees"
    for d in (donnees, maison / "Documents", maison / "AppData" / "Local", maison / "AppData" / "Roaming"):
        d.mkdir(parents=True, exist_ok=True)
    source = maison / "Documents" / "reunion longue.ogg"
    source.write_bytes((RACINE / "banc" / "extrait_fr.ogg").read_bytes())
    (donnees / "config.json").write_text(json.dumps({"dossier_sortie": str(maison / "sorties"),
                                                     "langue_interface": "fr"}), encoding="utf-8")
    env = {**os.environ, "SCRIBOUILLE_DONNEES": str(donnees), "LOCALAPPDATA": str(maison / "AppData" / "Local"),
           "USERPROFILE": str(maison), "HOME": str(maison), "APPDATA": str(maison / "AppData" / "Roaming"),
           "ESSAI_SOURCE": str(source), "PYTHONIOENCODING": "utf-8"}
    env.pop("SCRIBOUILLE_MOTEUR_ESSAI", None)
    p = subprocess.run([PYTHON, "-c", _REDEPOT_FENETRE, str(RACINE / "transcriber.pyw")], capture_output=True,
                       timeout=180, cwd=str(TEMPORAIRE), env=env, creationflags=SANS_FENETRE)
    sortie = p.stdout.decode("utf-8", "replace")
    ligne = next((x for x in sortie.splitlines() if x.startswith("RESULTAT ")), "")
    avant, apres, cle = json.loads(ligne[len("RESULTAT "):]) if ligne else ({}, {}, "")
    verifier(avant.get("reprise") == cle and avant.get("propose") and avant.get("segments") == 1,
             "redéposé : la reprise est rattachée (rien d'effacé), la fenêtre propose de recommencer",
             f"{avant} {p.stderr.decode('utf-8', 'replace')[-300:]}")
    verifier(apres.get("ok") and apres.get("reprise") == "" and apres.get("recommencer") is True
             and apres.get("garde") is False,
             "« Recommencer du début » : la reprise est abandonnée, à la demande seulement", str(apres))
    page = (RACINE / "web" / "app.js").read_text(encoding="utf-8")
    html = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    verifier("window.onReprisesTrouvees" in page and "pywebview.api.recommencer(" in page
             and 'id="modale-reprise-trouvee"' in html and 'id="btn-recommencer-reprise"' in html,
             "la modale « Transcription interrompue » est branchée (Reprendre, Recommencer du début)")


def principal() -> int:
    print(f"Vérification de la ligne de commande\n{'=' * 40}\n(dossier temporaire : {TEMPORAIRE})")
    try:
        essai_aiguillage()
        essai_erreurs()
        essai_aide()
        essai_sans_bureau()
        essai_options_honorees()
        essai_sortie_par_defaut()
        essai_json_partout()
        essai_documentation()
        essai_aucune_console()
        essai_lecture_sans_ecriture()
        essai_dossier_partage_intact()
        essai_redepot_fenetre()
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
