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
                           env={**os.environ, "PYTHONIOENCODING": "cp1252"})
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
    bloc = "".join(f"{k}={v}\0" for k, v in os.environ.items()) + "\0"
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


def principal() -> int:
    print(f"Vérification de la ligne de commande\n{'=' * 40}\n(dossier temporaire : {TEMPORAIRE})")
    try:
        essai_aiguillage()
        essai_erreurs()
        essai_aide()
        essai_sans_bureau()
        essai_options_honorees()
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
