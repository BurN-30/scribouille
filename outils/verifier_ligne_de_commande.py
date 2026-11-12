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
