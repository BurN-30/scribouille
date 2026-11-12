"""
Ligne de commande de Scribouille, sans fenêtre : utilisable par SSH, en tâche
planifiée, et par un agent de code.

    scribouille COMMANDE [options] [--json]

Version installée : `scribouille.com` (Windows le choisit avant `Scribouille.exe`
quand on tape `scribouille`). Depuis les sources : `python transcriber.pyw COMMANDE`.
Guide complet : `docs/ligne-de-commande.md`.

Ce module n'importe rien de l'interface (ni pywebview, ni WebView2) : la
transcription passe par le processus moteur (`app/superviseur.py`).

Enveloppe JSON (une par réponse ; `transcrire` et `reprendre` écrivent une
ligne par événement, la dernière est `fin`) :
    {"schema": "scribouille.cli/1", "commande": "...", "donnees": {...}}
    {"schema": "scribouille.cli/1", "commande": "...", "erreur":
        {"code": "...", "message": "...", "code_retour": N, "suggestion": "..."}}

Codes de retour : 0 fait ; 1 au moins un fichier en échec ; 2 arguments
invalides ou confirmation manquante ; 3 pas prêt (modèle ou moteur absent) ;
4 sortie déjà là sans --ecraser ; 5 interrompu, reprenable ; 6 ressource
manquante (disque, mémoire).

Anciennes formes gardées telles quelles (`--verifier`, `--banc`, `--campagne`,
`--endurance`, `--comparer`, `--reconnaitre`, `--detecter-materiel`,
`--revenir-whiscribe`, `--apprendre-vocabulaire`, `--mesurer-vocabulaire`) :
elles restent traitées par `transcriber.pyw` avant ce module.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import threading
import time
from pathlib import Path

from . import VERSION, chemins, langues

SCHEMA = "scribouille.cli/1"

OK, ECHEC_PARTIEL, ARGUMENTS, PAS_PRET, SORTIE_EXISTANTE, INTERROMPU, RESSOURCE = 0, 1, 2, 3, 4, 5, 6

COMMANDES = ("transcrire", "reprendre", "etat", "lire", "reglages", "diagnostic", "agent", "espace",
             "effacer", "vocabulaire", "mesurer", "materiel", "donnees", "verifier", "aide", "version")

#: Réglages accessibles par `reglages`, avec leur effet. Les clés absentes
#: d'ici sont internes (thème, zoom, état de l'interface).
REGLAGES: dict[str, str] = {
    "preset": "qualite (large-v3, faisceau 5) ou rapide (turbo).",
    "langue": "Langue parlée : code ISO (fr, en...) ou auto.",
    "langue_interface": "Langue de l'interface et des en-têtes : fr ou en (vide : celle de Windows).",
    "dossier_sortie": "Dossier des transcriptions de la fenêtre.",
    "diarisation": "Séparer les locuteurs (extension à installer).",
    "nb_locuteurs": "Nombre de locuteurs attendu, 0 : détection automatique.",
    "formats": "Formats écrits : txt, srt, vtt, horodatage (horodatage dans le .txt).",
    "appliquer_corrections": "Appliquer les corrections du vocabulaire après la transcription.",
    "utiliser_glossaire": "Passer le vocabulaire au modèle comme amorce.",
    "compagnon_confiance": "Écrire le .json compagnon (mots, horodatages, probabilités).",
    "corrections_apprises": "Proposer de mémoriser une correction faite en relecture.",
    "rapprochement_vocabulaire": "Corrections par rapprochement phonétique borné.",
    "vocabulaires_partages": "Fichiers de vocabulaire d'équipe lus en plus du personnel.",
    "sauvegarde_progressive": "Écrire chaque segment au fil de l'eau (reprise après coupure).",
    "lecture_audio": "Écouter l'extrait depuis la vue de lecture.",
    "motif_sortie": "Nom des fichiers produits ; vide : {date}-{nom}.",
    "dossier_surveille": "Dossier scruté par la surveillance.",
    "surveillance": "Transcrire ce qui arrive dans le dossier surveillé.",
    "maj_verifier": "Vérifier les mises à jour (seul appel réseau hors modèles).",
    "barre_taches": "Progression sur l'icône de la barre des tâches.",
    "filtres_salle": "Filtres de salle avant transcription (passe-haut, passe-bas, niveau).",
    "mode_avance": "Active modele_avance, beam_size, condition_on_previous_text, forcer_processeur.",
    "modele_avance": "Modèle imposé (mode avancé) ; vide : celui du preset.",
    "beam_size": "Largeur du faisceau (mode avancé) ; 0 : celle du preset.",
    "condition_on_previous_text": "Le modèle tient compte du texte précédent (mode avancé).",
    "forcer_processeur": "CTranslate2 sur processeur, quoi que dise le réglage du poste (mode avancé).",
    "rythme": "vitesse, equilibre ou discret : part du poste laissée à l'utilisateur.",
    "rythme_auto": "Passer seul en vitesse maximale quand le poste est inoccupé.",
    "moteur": "Réglage du poste : auto, ctranslate2 ou openvino (pseudo-clé de reglage_machine).",
    "peripherique": "Périphérique d'OpenVINO : CPU, GPU ou NPU (pseudo-clé de reglage_machine).",
    "dossier_modeles": "Dossier des modèles (pseudo-clé ; vide : celui par défaut).",
}

PSEUDO_CLES = ("moteur", "peripherique", "dossier_modeles")

#: Commandes qui n'écrivent rien dans le dossier de données, ni journal ni
#: réglages : regarder l'espace occupé, ou l'effacer, ne recrée rien.
SANS_ECRITURE = ("espace", "effacer", "etat", "lire", "agent")


def config_cli(commande: str = "") -> dict:
    """
    La configuration, et la langue de l'interface posée. Pour les commandes
    sans écriture, lue telle quelle : rien n'est enregistré, même au premier
    lancement.
    """
    from . import config as config_module

    if commande not in SANS_ECRITURE:
        return config_module.charger()
    try:
        donnees = json.loads(chemins.FICHIER_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        donnees = {}
    config = config_module._fusionner(config_module.DEFAUTS, donnees if isinstance(donnees, dict) else {})
    if not config.get("dossier_sortie"):
        config["dossier_sortie"] = str(chemins.dossier_sortie_defaut())
    langues.definir(config.get("langue_interface") or langues.detecter_systeme())
    return config


class Echec(Exception):
    def __init__(self, code: str, message: str, code_retour: int, suggestion: str = ""):
        super().__init__(message)
        self.code, self.message, self.code_retour, self.suggestion = code, message, code_retour, suggestion


class Sortie:
    """Écrit le texte humain ou l'enveloppe JSON, selon `--json`."""

    def __init__(self, commande: str, en_json: bool):
        self.commande, self.json = commande, en_json
        self._verrou = threading.Lock()
        for flux in (sys.stdout, sys.stderr):
            try:
                flux.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
            except Exception:
                pass

    def _ecrire(self, objet: dict) -> None:
        with self._verrou:
            try:
                sys.stdout.write(json.dumps(objet, ensure_ascii=False, default=str) + "\n")
                sys.stdout.flush()
            except Exception:
                pass

    def donnees(self, donnees: dict, texte: str = "") -> None:
        if self.json:
            self._ecrire({"schema": SCHEMA, "commande": self.commande, "donnees": donnees})
        elif texte:
            self.dire(texte)

    def evenement(self, nom: str, **champs) -> None:
        if self.json:
            self._ecrire({"schema": SCHEMA, "commande": self.commande, "evenement": nom, **champs})

    def erreur(self, echec: Echec) -> None:
        if self.json:
            self._ecrire({"schema": SCHEMA, "commande": self.commande, "erreur": {
                "code": echec.code, "message": echec.message, "code_retour": echec.code_retour,
                "suggestion": echec.suggestion}})
        else:
            self.dire(f"Erreur : {echec.message}" + (f"\n  {echec.suggestion}" if echec.suggestion else ""),
                      erreur=True)

    def dire(self, texte: str, erreur: bool = False) -> None:
        if self.json and not erreur:
            return
        flux = sys.stderr if erreur else sys.stdout
        with self._verrou:
            try:
                flux.write(texte.rstrip("\n") + "\n")
                flux.flush()
            except Exception:
                pass

    def progression(self, texte: str) -> None:
        """Une ligne d'avancement sur l'erreur standard (le terminal), jamais en JSON."""
        if self.json:
            return
        with self._verrou:
            try:
                if sys.stderr.isatty():
                    sys.stderr.write("\r" + texte[:118].ljust(118))
                else:
                    sys.stderr.write(texte + "\n")
                sys.stderr.flush()
            except Exception:
                pass

    def fin_progression(self) -> None:
        if not self.json:
            try:
                if sys.stderr.isatty():
                    sys.stderr.write("\n")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Analyse des arguments
# ---------------------------------------------------------------------------

def reconnue(arguments: list[str]) -> bool:
    """Ces arguments sont-ils une commande de ce module ?"""
    reste = [a for a in arguments if a != "--json"]
    if not reste:
        return False
    return reste[0] in COMMANDES or reste[0] in ("-h", "--help", "--version")


def _analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scribouille", add_help=False,
                                description="Scribouille, transcription locale, sans fenêtre.")
    p.add_argument("--json", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--version", action="store_true")
    s = p.add_subparsers(dest="commande")

    t = s.add_parser("transcrire", add_help=False)
    t.add_argument("chemins", nargs="+")
    t.add_argument("--sortie", default="")
    t.add_argument("--formats", default="txt,json")
    t.add_argument("--langue", default="")
    t.add_argument("--preset", choices=("qualite", "rapide"))
    t.add_argument("--moteur", choices=("auto", "openvino", "ctranslate2"), default="auto")
    t.add_argument("--peripherique", choices=("CPU", "GPU", "NPU", "cpu", "gpu", "npu"))
    t.add_argument("--vocabulaire", action="append", default=[])
    t.add_argument("--sans-vocabulaire", action="store_true")
    t.add_argument("--locuteurs", default="")
    t.add_argument("--rythme", choices=("vitesse", "equilibre", "discret", "auto"))
    t.add_argument("--recursif", action="store_true")
    t.add_argument("--telecharger", action="store_true")
    t.add_argument("--ecraser", action="store_true")
    t.add_argument("--json", action="store_true")

    r = s.add_parser("reprendre", add_help=False)
    r.add_argument("cible", nargs="?", default="")
    r.add_argument("--sortie", default="")
    r.add_argument("--formats", default="txt,json")
    r.add_argument("--rythme", choices=("vitesse", "equilibre", "discret", "auto"))
    r.add_argument("--telecharger", action="store_true")
    r.add_argument("--json", action="store_true")

    e = s.add_parser("etat", add_help=False)
    e.add_argument("--json", action="store_true")

    lire = s.add_parser("lire", add_help=False)
    lire.add_argument("fichier")
    lire.add_argument("--depuis", type=float, default=None)
    lire.add_argument("--jusqua", type=float, default=None)
    lire.add_argument("--limite", type=int, default=2000)
    lire.add_argument("--decalage", type=int, default=0)
    lire.add_argument("--douteux", action="store_true")
    lire.add_argument("--texte", action="store_true")
    lire.add_argument("--json", action="store_true")

    g = s.add_parser("reglages", add_help=False)
    g.add_argument("action", nargs="?", default="liste", choices=("liste", "lire", "definir", "defaut"))
    g.add_argument("valeurs", nargs="*")
    g.add_argument("--json", action="store_true")

    d = s.add_parser("diagnostic", add_help=False)
    d.add_argument("--materiel", action="store_true")
    d.add_argument("--json", action="store_true")

    a = s.add_parser("agent", add_help=False)
    a.add_argument("action", nargs="?", default="afficher", choices=("afficher", "installer"))
    a.add_argument("--cible", choices=("claude", "codex"), default="claude")
    a.add_argument("--dossier", default="")
    a.add_argument("--ecraser", action="store_true")
    a.add_argument("--json", action="store_true")

    es = s.add_parser("espace", add_help=False)
    es.add_argument("--json", action="store_true")

    ef = s.add_parser("effacer", add_help=False)
    ef.add_argument("cles", nargs="*")
    ef.add_argument("--liberable", action="store_true")
    ef.add_argument("--complet", action="store_true")
    ef.add_argument("--avec-transcriptions", action="store_true")
    ef.add_argument("--garder-programme", action="store_true")
    ef.add_argument("--apercu", action="store_true")
    ef.add_argument("--resume", default="")
    ef.add_argument("--oui", action="store_true")
    ef.add_argument("--json", action="store_true")

    v = s.add_parser("vocabulaire", add_help=False)
    v.add_argument("action", nargs="?", default="etat",
                   choices=("etat", "appliquer", "importer", "exporter", "apprendre"))
    v.add_argument("fichier", nargs="?", default="")
    v.add_argument("--sortie", default="")
    v.add_argument("--ecraser", action="store_true")
    v.add_argument("--brut", action="append", default=[])
    v.add_argument("--propre", action="append", default=[])
    v.add_argument("--cr", action="append", default=[])
    v.add_argument("--importer", action="store_true")
    v.add_argument("--json", action="store_true")

    m = s.add_parser("mesurer", add_help=False)
    m.add_argument("quoi", choices=("campagne", "banc", "endurance", "comparer", "vocabulaire", "rythmes"))
    m.add_argument("reste", nargs=argparse.REMAINDER)

    ma = s.add_parser("materiel", add_help=False)
    ma.add_argument("action", nargs="?", default="detecter", choices=("detecter", "proposer"))
    ma.add_argument("--appliquer", action="store_true")
    ma.add_argument("--json", action="store_true")

    do = s.add_parser("donnees", add_help=False)
    do.add_argument("action", choices=("revenir-whiscribe",))

    for nom in ("verifier", "aide", "version"):
        x = s.add_parser(nom, add_help=False)
        x.add_argument("--json", action="store_true")
    return p


AIDE = """Scribouille {version}, transcription locale, sans fenêtre.

  scribouille transcrire FICHIER|DOSSIER... [--sortie D] [--formats txt,json,srt,vtt]
                         [--langue fr] [--preset qualite|rapide] [--moteur auto|openvino|ctranslate2]
                         [--peripherique CPU|GPU|NPU] [--rythme vitesse|equilibre|discret|auto]
                         [--locuteurs auto|non|N] [--vocabulaire F.toml] [--sans-vocabulaire]
                         [--recursif] [--telecharger] [--ecraser]
  scribouille reprendre [CLE|FICHIER]          reprendre une transcription interrompue
  scribouille etat                             transcriptions en cours et reprenables, moteurs actifs
  scribouille lire SORTIE.json [--depuis S --jusqua S] [--limite N --decalage N] [--douteux] [--texte]
  scribouille reglages [liste|lire CLE|definir CLE=VALEUR...|defaut CLE]
  scribouille diagnostic [--materiel]          prêt ou non, et pourquoi
  scribouille espace                           ce que Scribouille occupe, par poste
  scribouille effacer [CLE...|--liberable|--complet [--avec-transcriptions]] [--apercu] [--oui]
  scribouille vocabulaire [etat|appliquer F|importer F|exporter F|apprendre --brut B --propre P]
  scribouille agent [afficher|installer --cible claude|codex]
  scribouille mesurer campagne|banc|endurance|comparer|vocabulaire|rythmes [options d'origine]
  scribouille materiel [detecter|proposer [--appliquer]]
  scribouille donnees revenir-whiscribe
  scribouille verifier                         bilan de l'installation

  --json sur toute commande : sortie structurée (docs/ligne-de-commande.md).
  Codes de retour : 0 fait, 1 échec partiel, 2 arguments, 3 pas prêt, 4 sortie existante,
  5 interrompu (reprenable), 6 disque ou mémoire.
"""


def principal(arguments: list[str]) -> int:
    en_json = "--json" in arguments
    try:
        options = _analyseur().parse_args(arguments)
    except SystemExit:
        sortie = Sortie("?", en_json)
        sortie.erreur(Echec("arguments", "arguments invalides (scribouille aide)", ARGUMENTS))
        return ARGUMENTS
    options.json = en_json
    commande = options.commande or ("version" if options.version else "aide")
    sortie = Sortie(commande, en_json)
    if commande == "aide" or options.help:
        sortie.donnees({"commandes": list(COMMANDES), "aide": AIDE.format(version=VERSION)},
                       AIDE.format(version=VERSION))
        return OK
    if commande == "version":
        sortie.donnees({"version": VERSION, "schema": SCHEMA}, f"Scribouille {VERSION}")
        return OK
    from . import journal

    if commande in SANS_ECRITURE:
        journal.sans_fichier()
    else:
        journal.demarrer()
    journal.silence_bibliotheques()
    config_cli(commande)  # pose la langue de l'interface
    try:
        return _COMMANDES[commande](options, sortie)
    except Echec as echec:
        sortie.erreur(echec)
        return echec.code_retour
    except KeyboardInterrupt:
        sortie.erreur(Echec("interrompu", "interrompu", INTERROMPU))
        return INTERROMPU
    except Exception as exc:
        journal.exception(f"Commande {commande} en échec", exc)
        sortie.erreur(Echec("erreur", f"{type(exc).__name__}: {exc}", ECHEC_PARTIEL))
        return ECHEC_PARTIEL


# ---------------------------------------------------------------------------
# transcrire, reprendre
# ---------------------------------------------------------------------------

def _fichiers(entrees: list[str], recursif: bool) -> tuple[list[Path], list[str]]:
    from . import audio

    trouves, refuses = [], []
    for brut in entrees:
        chemin = Path(brut).expanduser()
        if chemin.is_dir():
            motif = "**/*" if recursif else "*"
            for f in sorted(chemin.glob(motif)):
                if f.is_file() and audio.est_audio(f):
                    trouves.append(f.resolve())
        elif chemin.is_file():
            if audio.est_audio(chemin):
                trouves.append(chemin.resolve())
            else:
                refuses.append(str(chemin))
        else:
            refuses.append(str(chemin))
    vus, uniques = set(), []
    for f in trouves:
        if str(f).lower() not in vus:
            vus.add(str(f).lower())
            uniques.append(f)
    return uniques, refuses


def _transcriptions_de(source: Path, dossier: Path) -> list[Path]:
    """Sorties déjà écrites pour cette source dans ce dossier (compagnon qui la nomme)."""
    from . import compagnon

    trouvees: list[Path] = []
    if not dossier.is_dir():
        return trouvees
    cible = str(source.resolve()).lower()
    for f in dossier.glob("*.json"):
        try:
            donnees = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(donnees, dict) or donnees.get("format") not in compagnon.FORMATS_LUS:
            continue
        chemin = str((donnees.get("source") or {}).get("chemin") or "")
        if chemin and str(Path(chemin).resolve()).lower() == cible:
            trouvees += [g for g in dossier.glob(f.stem + ".*") if g.suffix.lower() in (".txt", ".json", ".srt", ".vtt")]
    return trouvees


def _config_de_commande(options, materiel_poste) -> dict:
    from . import calibration, config as config_module, reglage_machine, rythme as rythme_module

    config = copy.deepcopy(config_module.charger())
    formats = {f.strip().lower() for f in (options.formats or "").split(",") if f.strip()}
    inconnus = formats - {"txt", "json", "srt", "vtt", "horodatage"}
    if inconnus:
        raise Echec("arguments", f"format inconnu : {', '.join(sorted(inconnus))}", ARGUMENTS)
    config["formats"] = {"txt": bool(formats & {"txt", "json", "horodatage"}), "srt": "srt" in formats,
                         "vtt": "vtt" in formats, "horodatage": "horodatage" in formats}
    config["compagnon_confiance"] = "json" in formats
    if getattr(options, "langue", ""):
        config["langue"] = options.langue
    if getattr(options, "preset", None):
        config["preset"] = options.preset
    if getattr(options, "sans_vocabulaire", False):
        config["utiliser_glossaire"] = False
        config["appliquer_corrections"] = False
    for fichier in getattr(options, "vocabulaire", []) or []:
        if not Path(fichier).is_file():
            raise Echec("arguments", f"vocabulaire introuvable : {fichier}", ARGUMENTS)
        config["vocabulaires_partages"] = list(config.get("vocabulaires_partages") or []) + [str(Path(fichier).resolve())]
    locuteurs = str(getattr(options, "locuteurs", "") or "").strip().lower()
    if locuteurs in ("non", "0"):
        config["diarisation"] = False
    elif locuteurs == "auto":
        config["diarisation"], config["nb_locuteurs"] = True, 0
    elif locuteurs.isdigit():
        config["diarisation"], config["nb_locuteurs"] = True, int(locuteurs)
    elif locuteurs:
        raise Echec("arguments", f"--locuteurs : auto, non ou un nombre (pas « {locuteurs} »)", ARGUMENTS)
    if getattr(options, "rythme", None):
        if options.rythme == "auto":
            choisi = rythme_module.normaliser(config.get("rythme"))
            config["rythme"] = choisi if choisi != "vitesse" else "equilibre"
            config["rythme_auto"] = True
        else:
            config["rythme"], config["rythme_auto"] = options.rythme, False
    moteur_voulu = getattr(options, "moteur", "auto") or "auto"
    peripherique = (getattr(options, "peripherique", None) or "").upper()
    if moteur_voulu != "auto" or peripherique:
        actuel = dict(reglage_machine.lire(config, materiel_poste))
        if moteur_voulu == "ctranslate2":
            actuel = {k: v for k, v in actuel.items() if k in ("fils", "lot")} if actuel.get("moteur") != "openvino" else {}
            actuel["moteur"] = "ctranslate2"
        else:
            actuel["moteur"] = "openvino"
            actuel["peripherique"] = peripherique or str(actuel.get("peripherique") or "CPU")
        actuel["signature"] = calibration.signature_machine(materiel_poste)
        config[reglage_machine.CLE] = actuel
    return config


def _modele_attendu(config: dict, mat) -> str:
    from . import presets, reglage_machine

    essai = dict(config)
    reglage_machine.appliquer_au_materiel(essai, mat)
    avance = config.get("modele_avance", "") if config.get("mode_avance") else ""
    modele = presets.modele_du_preset(config.get("preset", presets.PRESET_DEFAUT), avance)
    forcer = bool(config.get("forcer_processeur")) and bool(config.get("mode_avance"))
    if mat.moteur == "openvino" and not forcer and presets.depot_openvino(modele):
        return presets.depot_openvino(modele)
    return modele


def _executer_file(sortie: Sortie, elements: list, config: dict, telecharger: bool) -> dict:
    """Une file de fichiers dans le processus moteur, avec progression et Ctrl+C."""
    from . import presets, superviseur, traitement
    from .materiel import detecter_au_demarrage

    mat, _ = detecter_au_demarrage()
    distant = superviseur.Superviseur(telecharger=telecharger)
    file = traitement.FileTraitement(mat, distant=distant)
    file.elements = list(elements)
    resultats: dict[str, dict] = {e.identifiant: {"fichier": e.chemin, "ok": False} for e in elements}
    noms = {e.identifiant: e.nom for e in elements}
    rang = {e.identifiant: i + 1 for i, e in enumerate(elements)}
    dernier: dict[str, tuple[float, int, str]] = {}
    fini, bilan = threading.Event(), {}

    def progression(identifiant: str, donnees: dict) -> None:
        pct, phase = int(donnees.get("pct") or 0), str(donnees.get("phase") or "")
        avant = dernier.get(identifiant)
        maintenant = time.monotonic()
        if avant and avant[1] == pct and avant[2] == phase and maintenant - avant[0] < 5:
            return
        if avant and maintenant - avant[0] < 1.0 and avant[2] == phase and pct < 100:
            return
        dernier[identifiant] = (maintenant, pct, phase)
        sortie.evenement("progres", id=identifiant, fichier=resultats[identifiant]["fichier"], pct=pct,
                         phase=phase, ecoule_s=donnees.get("ecoule_s"), reste_s=donnees.get("restant_s"))
        reste = f", reste {donnees.get('restant')}" if donnees.get("restant") else ""
        sortie.progression(f"[{rang[identifiant]}/{len(elements)}] {noms[identifiant]} : {phase} {pct} %"
                           f" ({donnees.get('ecoule') or ''}{reste})")

    def termine(identifiant: str, donnees: dict) -> None:
        r = resultats[identifiant]
        if donnees.get("ok"):
            produits = [s["chemin"] for s in donnees.get("sorties") or []]
            compagnons = [str(Path(c).with_suffix(".json")) for c in produits
                          if c.lower().endswith(".txt") and Path(c).with_suffix(".json").is_file()]
            r.update({"ok": True, "sorties": produits + compagnons, "json": compagnons[0] if compagnons else "",
                      "duree": donnees.get("duree"), "facteur": donnees.get("facteur"),
                      "locuteurs": donnees.get("locuteurs"), "corrections": donnees.get("corrections")})
            sortie.fin_progression()
            sortie.evenement("fichier_fini", id=identifiant, **r)
            sortie.dire(f"[{rang[identifiant]}/{len(elements)}] {noms[identifiant]} : fait en {r['duree']}"
                        + "".join(f"\n    {c}" for c in r["sorties"]))
        else:
            r.update({"annule": bool(donnees.get("annule")), "erreur": donnees.get("titre") or donnees.get("message") or "",
                      "detail": donnees.get("detail") or donnees.get("message") or ""})
            sortie.fin_progression()
            sortie.evenement("fichier_echec", id=identifiant, **r)
            sortie.dire(f"[{rang[identifiant]}/{len(elements)}] {noms[identifiant]} : "
                        + ("arrêté (reprenable)" if r["annule"] else f"échec : {r['erreur']}"), erreur=True)

    def journal_ui(niveau: str, texte: str) -> None:
        sortie.evenement("journal", niveau=niveau, texte=texte)
        if niveau in ("attention", "erreur"):
            sortie.fin_progression()
            sortie.dire(f"  {texte}", erreur=True)

    rappels = traitement.Rappels(
        etat=lambda i, e, m: sortie.evenement("etat", id=i, etat=e, message=m),
        progression=progression, termine=termine, journal_ui=journal_ui,
        file_terminee=lambda d: (bilan.update(d), fini.set()),
        reprise=lambda i, c: resultats[i].update({"reprise": c}))
    sortie.evenement("debut", fichiers=[e.chemin for e in elements], version=VERSION,
                     preset=config.get("preset"), rythme=config.get("rythme"),
                     pour_une_heure=presets.pour_une_heure(config.get("preset", "qualite"), mat,
                                                           config.get("rythme") or "vitesse"))
    interrompu = False
    file.demarrer(config, rappels)
    try:
        while not fini.wait(0.5):
            pass
    except KeyboardInterrupt:
        interrompu = True
        sortie.dire("Arrêt demandé : le travail fait est gardé, « scribouille reprendre » le poursuit.",
                    erreur=True)
        file.arreter()
        fini.wait(30)
    sortie.fin_progression()
    for e in elements:
        resultats[e.identifiant]["etat"] = e.etat
        if e.reprise and not resultats[e.identifiant].get("ok"):
            resultats[e.identifiant]["reprise"] = e.reprise
    return {"bilan": bilan, "resultats": list(resultats.values()), "interrompu": interrompu}


def _code_de_fin(execution: dict, ignores: int) -> int:
    bilan = execution["bilan"]
    if execution["interrompu"] or bilan.get("annules"):
        return INTERROMPU
    if bilan.get("echecs"):
        textes = " ".join(str(r.get("detail", "")) + str(r.get("erreur", "")) for r in execution["resultats"])
        if any(m in textes.lower() for m in ("disque", "disk", "mémoire", "memory", "espace")):
            return RESSOURCE
        if any(m in textes for m in ("--telecharger", "n'est pas sur ce poste", "is not on this computer")):
            return PAS_PRET
        return ECHEC_PARTIEL
    return SORTIE_EXISTANTE if ignores else OK


def cmd_transcrire(options, sortie: Sortie) -> int:
    from . import moteur, traitement
    from .materiel import detecter_au_demarrage

    fichiers, refuses = _fichiers(options.chemins, options.recursif)
    if not fichiers:
        raise Echec("aucun_fichier", "aucun fichier audio trouvé"
                    + (f" ({', '.join(refuses[:5])})" if refuses else ""), ARGUMENTS)
    mat, _ = detecter_au_demarrage()
    config = _config_de_commande(options, mat)
    modele = _modele_attendu(config, mat)
    if moteur.etat_modele(modele)["etat"] != "complet" and not options.telecharger:
        raise Echec("modele_absent", langues.t("moteur.telechargement_refuse", modele=moteur.nom_court(modele),
                                               taille=moteur.taille_annoncee(modele)), PAS_PRET,
                    "relancer avec --telecharger (accord de l'utilisateur), ou poser le modèle dans "
                    + str(chemins.DOSSIER_MODELES))
    elements, ignores = [], []
    for rang, f in enumerate(fichiers):
        dossier = Path(options.sortie).expanduser().resolve() if options.sortie else f.parent
        deja = _transcriptions_de(f, dossier)
        if deja and not options.ecraser:
            ignores.append({"fichier": str(f), "sorties": [str(d) for d in deja]})
            sortie.evenement("fichier_ignore", fichier=str(f), raison="deja_transcrit",
                             sorties=[str(d) for d in deja])
            sortie.dire(f"{f.name} : déjà transcrit ({deja[0].name}), --ecraser pour refaire", erreur=True)
            continue
        if not dossier.exists():
            dossier.mkdir(parents=True, exist_ok=True)
        for ancienne in deja:
            ancienne.unlink(missing_ok=True)
        elements.append(traitement.Element(identifiant=f"c{rang + 1}", chemin=str(f), nom=f.name,
                                           taille=f.stat().st_size, sortie=str(dossier)))
    if not elements:
        sortie.evenement("fin", reussis=0, echecs=0, annules=0, ignores=len(ignores), code_retour=SORTIE_EXISTANTE,
                         fichiers=[], ignores_detail=ignores)
        return SORTIE_EXISTANTE
    execution = _executer_file(sortie, elements, config, options.telecharger)
    code = _code_de_fin(execution, len(ignores))
    bilan = execution["bilan"]
    sortie.evenement("fin", reussis=bilan.get("reussis", 0), echecs=bilan.get("echecs", 0),
                     annules=bilan.get("annules", 0), ignores=len(ignores), code_retour=code,
                     fichiers=execution["resultats"], ignores_detail=ignores)
    if code == INTERROMPU:
        sortie.dire("Interrompu : « scribouille reprendre » poursuit au segment près.", erreur=True)
    return code


def cmd_reprendre(options, sortie: Sortie) -> int:
    from . import presets, reprise, traitement
    from .materiel import detecter_au_demarrage

    reprises = reprise.lister()
    if not reprises:
        raise Echec("rien_a_reprendre", "aucune transcription interrompue", ARGUMENTS)
    cible = options.cible
    choisie = None
    if not cible:
        choisie = sorted(reprises, key=lambda r: r.get("date") or "")[-1]
    else:
        for r in reprises:
            if r["cle"] == cible or str(Path(r["chemin"]).resolve()).lower() == str(Path(cible).expanduser().resolve()).lower():
                choisie = r
        if choisie is None:
            raise Echec("introuvable", f"aucune reprise pour « {cible} » (scribouille etat)", ARGUMENTS)
    mat, _ = detecter_au_demarrage()
    options.preset = None
    options.langue = ""
    config = _config_de_commande(options, mat)
    # Une reprise garde son modèle : le texte ne mêle jamais deux modèles.
    if presets.modele_du_preset(config.get("preset", "qualite"), "") != choisie["modele"]:
        cles = [c for c, p in presets.PRESETS.items() if p["modele"] == choisie["modele"]]
        if cles:
            config["preset"] = cles[0]
        else:
            config["mode_avance"], config["modele_avance"] = True, choisie["modele"]
    source = Path(choisie["chemin"])
    dossier = Path(options.sortie).expanduser().resolve() if options.sortie else source.parent
    dossier.mkdir(parents=True, exist_ok=True)
    element = traitement.Element(identifiant="r1", chemin=str(source), nom=source.name, taille=source.stat().st_size,
                                 reprise=choisie["cle"], sortie=str(dossier))
    sortie.dire(f"Reprise de {source.name} à {presets.formater_duree(choisie['position'])} "
                f"sur {presets.formater_duree(choisie['duree_audio'])}.")
    execution = _executer_file(sortie, [element], config, options.telecharger)
    code = _code_de_fin(execution, 0)
    bilan = execution["bilan"]
    sortie.evenement("fin", reussis=bilan.get("reussis", 0), echecs=bilan.get("echecs", 0),
                     annules=bilan.get("annules", 0), ignores=0, code_retour=code, fichiers=execution["resultats"],
                     reprise=choisie["cle"])
    return code


# ---------------------------------------------------------------------------
# etat, lire
# ---------------------------------------------------------------------------

def _moteurs_actifs() -> list[dict]:
    try:
        import psutil  # type: ignore
    except Exception:
        return []
    trouves = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            ligne = p.info.get("cmdline") or []
            if "--moteur" in ligne and any("scribouille" in str(x).lower() or "transcriber.pyw" in str(x).lower()
                                           for x in ligne):
                trouves.append({"pid": p.pid, "memoire_octets": p.memory_info().rss,
                                "depuis": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.create_time()))})
        except Exception:
            continue
    return trouves


def cmd_etat(options, sortie: Sortie) -> int:
    from . import presets, reprise

    maintenant = time.time()
    taches = []
    for r in reprise.lister():
        try:
            maj = time.mktime(time.strptime(str(r.get("date") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            maj = 0.0
        taches.append({**r, "etat": "en_cours" if maintenant - maj < 60 else "interrompue",
                       "reprendre": f"scribouille reprendre {r['cle']}"})
    moteurs = _moteurs_actifs()
    lignes = [f"Moteurs actifs : {len(moteurs)}"] + [f"  PID {m['pid']}, {langues.octets(m['memoire_octets'])}"
                                                      for m in moteurs]
    lignes.append(f"Transcriptions reprenables : {len(taches)}")
    for t in taches:
        lignes.append(f"  {t['nom']} : {t['pct']} % ({presets.formater_duree(t['position'])} sur "
                      f"{presets.formater_duree(t['duree_audio'])}), {t['etat']}, clé {t['cle']}")
    sortie.donnees({"moteurs": moteurs, "taches": taches}, "\n".join(lignes))
    return OK


def cmd_lire(options, sortie: Sortie) -> int:
    from . import compagnon

    fichier = Path(options.fichier).expanduser()
    if fichier.suffix.lower() != ".json":
        fichier = compagnon.chemin_pour(fichier)
    donnees = compagnon.lire(fichier) if fichier.is_file() else None
    if not donnees:
        raise Echec("introuvable", f"pas de transcription structurée : {fichier}", ARGUMENTS,
                    "le .json compagnon est écrit avec --formats txt,json")
    seuil = float((donnees.get("seuils") or {}).get("faible") or compagnon.SEUIL_FAIBLE)
    segments = donnees.get("segments") or []
    avec_p = [m.get("p") for s in segments for m in (s.get("m") or []) if isinstance(m.get("p"), (int, float))]
    probabilites = any(p >= 0 for p in avec_p)
    choisis = []
    for rang, s in enumerate(segments):
        if options.depuis is not None and float(s.get("f", 0)) < options.depuis:
            continue
        if options.jusqua is not None and float(s.get("d", 0)) > options.jusqua:
            continue
        douteux = [m for m in (s.get("m") or []) if isinstance(m.get("p"), (int, float)) and 0 <= m["p"] < seuil]
        if options.douteux and not douteux:
            continue
        entree = {"rang": rang, "d": s.get("d"), "f": s.get("f"), "t": s.get("t", "")}
        if s.get("l"):
            entree["l"] = s["l"]
        if s.get("m"):
            entree["m"] = s["m"]
        if douteux:
            entree["douteux"] = [m.get("t") for m in douteux]
        choisis.append(entree)
    debut = max(0, options.decalage)
    page, mots, rang = [], 0, debut
    while rang < len(choisis):
        nombre = len(str(choisis[rang]["t"]).split())
        if page and mots + nombre > options.limite:
            break
        page.append(choisis[rang])
        mots += nombre
        rang += 1
    suivant = rang if rang < len(choisis) else None
    total_douteux = sum(1 for p in avec_p if 0 <= p < seuil)
    resultat = {
        "fichier": str(fichier.resolve()),
        "source": donnees.get("source"),
        "transcription": donnees.get("transcription"),
        "locuteurs": sorted({s.get("l") for s in segments if s.get("l")}),
        "segments": page,
        "pagination": {"decalage": debut, "limite_mots": options.limite, "suivant": suivant,
                       "total": len(choisis)},
        "douteux": {"methode": f"probabilite<{seuil}" if probabilites else "indisponible",
                    "nombre": total_douteux if probabilites else None},
        "remplacements_vocabulaire": (donnees.get("vocabulaire") or {}).get("remplacements") or [],
    }
    if options.texte and not options.json:
        lignes = []
        for s in page:
            temps = time.strftime("%H:%M:%S", time.gmtime(float(s.get("d") or 0)))
            lignes.append(f"[{temps}] " + (f"{s['l']} : " if s.get("l") else "") + s["t"]
                          + (f"   (douteux : {', '.join(s['douteux'])})" if s.get("douteux") else ""))
        if suivant is not None:
            lignes.append(f"... suite : --decalage {suivant}")
        sortie.dire("\n".join(lignes))
        return OK
    sortie.donnees(resultat, json.dumps(resultat, ensure_ascii=False, indent=1))
    return OK


# ---------------------------------------------------------------------------
# reglages
# ---------------------------------------------------------------------------

def _convertir(cle: str, texte: str, defaut):
    texte = texte.strip()
    if isinstance(defaut, bool):
        if texte.lower() in ("oui", "vrai", "true", "1", "on", "yes"):
            return True
        if texte.lower() in ("non", "faux", "false", "0", "off", "no"):
            return False
        raise Echec("valeur", f"{cle} : oui ou non", ARGUMENTS)
    if isinstance(defaut, int):
        try:
            return int(texte)
        except ValueError:
            raise Echec("valeur", f"{cle} : nombre entier attendu", ARGUMENTS) from None
    if isinstance(defaut, float):
        try:
            return float(texte.replace(",", "."))
        except ValueError:
            raise Echec("valeur", f"{cle} : nombre attendu", ARGUMENTS) from None
    if isinstance(defaut, list):
        return [x.strip() for x in texte.split(";") if x.strip()]
    if isinstance(defaut, dict):
        choisis = {x.strip().lower() for x in texte.split(",") if x.strip()}
        if not choisis <= set(defaut):
            raise Echec("valeur", f"{cle} : parmi {', '.join(defaut)}", ARGUMENTS)
        return {k: k in choisis for k in defaut}
    return texte


def _valider(cle: str, valeur) -> None:
    from . import presets, rythme

    fermes = {"preset": tuple(presets.PRESETS), "rythme": rythme.RYTHMES,
              "langue_interface": ("", *langues.LANGUES), "theme": ("auto", "clair", "sombre")}
    if cle in fermes and valeur not in fermes[cle]:
        raise Echec("valeur", f"{cle} : parmi {', '.join(v or '(vide)' for v in fermes[cle])}", ARGUMENTS)


def cmd_reglages(options, sortie: Sortie) -> int:
    from . import config as config_module, reglage_machine
    from .materiel import detecter_au_demarrage

    config = config_module.charger()
    mat, _ = detecter_au_demarrage()

    def valeurs() -> list[dict]:
        machine = reglage_machine.lire(config, mat)
        liste = []
        for cle, effet in REGLAGES.items():
            if cle == "moteur":
                valeur, defaut = machine.get("moteur") or "auto", "auto"
            elif cle == "peripherique":
                valeur, defaut = machine.get("peripherique") or "", ""
            elif cle == "dossier_modeles":
                valeur, defaut = str(chemins.DOSSIER_MODELES), str(chemins.dossier_modeles_defaut())
            else:
                valeur, defaut = config.get(cle), config_module.DEFAUTS.get(cle)
            liste.append({"cle": cle, "valeur": valeur, "defaut": defaut, "effet": effet})
        return liste

    if options.action == "liste":
        liste = valeurs()
        sortie.donnees({"reglages": liste, "fichier": str(chemins.FICHIER_CONFIG)},
                       "\n".join(f"{r['cle']:<28} = {json.dumps(r['valeur'], ensure_ascii=False)}"
                                 f"   (défaut {json.dumps(r['defaut'], ensure_ascii=False)})" for r in liste))
        return OK
    if not options.valeurs:
        raise Echec("arguments", "préciser la clé : reglages lire|definir|defaut CLE", ARGUMENTS)
    if options.action == "lire":
        par_cle = {r["cle"]: r for r in valeurs()}
        if options.valeurs[0] not in par_cle:
            raise Echec("cle_inconnue", f"réglage inconnu : {options.valeurs[0]}", ARGUMENTS)
        r = par_cle[options.valeurs[0]]
        sortie.donnees(r, f"{r['cle']} = {json.dumps(r['valeur'], ensure_ascii=False)}\n  {r['effet']}")
        return OK
    changes: dict = {}
    for brut in options.valeurs:
        cle, egal, texte = brut.partition("=")
        cle = cle.strip()
        if options.action == "definir" and not egal:
            raise Echec("arguments", f"forme CLE=VALEUR attendue : {brut}", ARGUMENTS)
        if cle not in REGLAGES:
            raise Echec("cle_inconnue", f"réglage inconnu : {cle} (scribouille reglages)", ARGUMENTS)
        if cle in PSEUDO_CLES:
            changes[cle] = texte.strip() if options.action == "definir" else ""
            continue
        defaut = config_module.DEFAUTS[cle]
        valeur = copy.deepcopy(defaut) if options.action == "defaut" else _convertir(cle, texte, defaut)
        _valider(cle, valeur)
        changes[cle] = valeur
    for cle, valeur in changes.items():
        if cle == "dossier_modeles":
            if valeur:
                probleme = chemins.dossier_modeles_inscriptible(valeur)
                if probleme:
                    raise Echec("valeur", f"dossier_modeles : {probleme}", ARGUMENTS)
            chemins.definir_dossier_modeles(valeur, memoriser=True)
        elif cle in ("moteur", "peripherique"):
            machine = dict(reglage_machine.lire(config, mat))
            if cle == "moteur":
                if valeur in ("", "auto"):
                    reglage_machine.oublier(config, mat)
                    continue
                if valeur not in reglage_machine.MOTEURS:
                    raise Echec("valeur", "moteur : auto, ctranslate2 ou openvino", ARGUMENTS)
                machine["moteur"] = valeur
            else:
                if valeur.upper() not in ("CPU", "GPU", "NPU", ""):
                    raise Echec("valeur", "peripherique : CPU, GPU ou NPU", ARGUMENTS)
                machine["peripherique"] = valeur.upper() or "CPU"
                machine.setdefault("moteur", "openvino")
            machine["source"] = "ligne de commande"
            reglage_machine.enregistrer(config, mat, machine)
        else:
            config[cle] = valeur
    if "langue_interface" in changes:
        config["langue_interface"] = langues.definir(config.get("langue_interface"))
    config_module.sauver(config)
    sortie.donnees({"modifies": sorted(changes), "fichier": str(chemins.FICHIER_CONFIG)},
                   f"Enregistré : {', '.join(sorted(changes))}")
    return OK


# ---------------------------------------------------------------------------
# diagnostic, verifier, materiel
# ---------------------------------------------------------------------------

def cmd_diagnostic(options, sortie: Sortie) -> int:
    import importlib.util

    from . import config as config_module, diarisation, materiel, moteur, moteur_openvino, presets, reglage_machine
    from . import vocabulaire

    if options.materiel:
        materiel.rafraichir()
    config = config_module.charger()
    mat, provisoire = materiel.detecter_au_demarrage()
    effet = reglage_machine.appliquer_au_materiel(config, mat)
    modele = _modele_attendu(config, mat)
    etat_modele = moteur.etat_modele(modele)
    modeles = []
    for p in presets.PRESETS.values():
        for nom in filter(None, (p["modele"], presets.depot_openvino(p["modele"]))):
            e = moteur.etat_modele(nom)
            modeles.append({"modele": nom, "preset": p["cle"], "etat": e["etat"],
                            "taille_annoncee": moteur.taille_annoncee(nom)})
    raisons = []
    ct2 = importlib.util.find_spec("ctranslate2") is not None and importlib.util.find_spec("faster_whisper") is not None
    if not ct2:
        raisons.append("moteur CTranslate2 absent")
    if etat_modele["etat"] != "complet":
        raisons.append(f"modèle {moteur.nom_court(modele)} {etat_modele['etat']} "
                       f"({moteur.taille_annoncee(modele)}) : --telecharger pour l'obtenir")
    verdict = None
    fichier_verdict = chemins.RACINE / "campagnes" / "verdict.json"
    try:
        verdict = json.loads(fichier_verdict.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        verdict = None
    resultat = {
        "version": VERSION,
        "mode": "installee" if chemins.EST_GELE and any(chemins.DOSSIER_PROGRAMME.glob("unins*.exe"))
        else ("portable" if chemins.EST_GELE else "sources"),
        "programme": str(chemins.DOSSIER_PROGRAMME),
        "commande": str(chemins.executable_console() or ""),
        "donnees": str(chemins.RACINE),
        "modeles_dossier": str(chemins.DOSSIER_MODELES),
        "materiel": {**mat.en_dict(), "provisoire": provisoire},
        "moteurs": {
            "ctranslate2": ct2,
            "openvino": {"installe": moteur_openvino.installe(), "version": moteur_openvino.version()
                         if moteur_openvino.installe() else "",
                         "peripheriques": moteur_openvino.peripheriques_disponibles()
                         if moteur_openvino.installe() else []},
        },
        "reglage": {"preset": config.get("preset"), "moteur": mat.moteur,
                    "peripherique": mat.peripherique_openvino or mat.peripherique,
                    "modele": modele, "rythme": config.get("rythme"), "rythme_auto": bool(config.get("rythme_auto")),
                    "indisponible": bool(effet.get("indisponible")), "plantage": effet.get("plantage") or ""},
        "pour_une_heure": presets.pour_une_heure(config.get("preset", "qualite"), mat, config.get("rythme") or "vitesse"),
        "modeles": modeles,
        "locuteurs": {"demandes": bool(config.get("diarisation")), "disponibles": diarisation.disponible(),
                      "indisponibilite": diarisation.indisponibilite()},
        "vocabulaire": vocabulaire.resume_glossaire(config.get("langue", "fr")),
        "verdict_campagne": verdict,
        "pret": not raisons,
        "raisons": raisons,
    }
    lignes = [f"Scribouille {VERSION} ({resultat['mode']})",
              f"  Programme : {resultat['programme']}", f"  Données   : {resultat['donnees']}",
              f"  Modèles   : {resultat['modeles_dossier']}",
              f"  Matériel  : {mat.resume()}",
              f"  Réglage   : {config.get('preset')}, moteur {mat.moteur} ({resultat['reglage']['peripherique']}), "
              f"rythme {config.get('rythme')}{' auto' if config.get('rythme_auto') else ''}",
              f"  Modèle    : {moteur.nom_court(modele)} ({etat_modele['etat']})",
              f"  Une heure d'audio : environ {resultat['pour_une_heure']}",
              f"  Locuteurs : {'disponibles' if resultat['locuteurs']['disponibles'] else 'non installés'}",
              "  Prêt." if not raisons else "  Pas prêt : " + " ; ".join(raisons)]
    sortie.donnees(resultat, "\n".join(lignes))
    return OK if not raisons else PAS_PRET


def cmd_verifier(options, sortie: Sortie) -> int:
    import subprocess

    from . import superviseur

    commande, dossier = superviseur.commande_moteur([])
    commande = [c for c in commande if c != "--moteur"] + ["--verifier"]
    resultat = subprocess.run(commande, cwd=dossier, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
    texte = (resultat.stdout or "").strip()
    sortie.donnees({"ok": resultat.returncode == 0, "bilan": texte.splitlines()}, texte)
    return OK if resultat.returncode == 0 else PAS_PRET


def cmd_materiel(options, sortie: Sortie) -> int:
    from . import adaptation, materiel

    if options.action == "proposer":
        return adaptation.principal_cli(["--reconnaitre"] + (["--appliquer"] if options.appliquer else []))
    lent = materiel.rafraichir()
    mat, provisoire = materiel.detecter_au_demarrage()
    sortie.donnees({"materiel": mat.en_dict(), "detection": lent, "provisoire": provisoire,
                    "fichier": str(materiel.fichier_cache())}, mat.resume())
    return OK if lent is not None else ECHEC_PARTIEL


# ---------------------------------------------------------------------------
# espace, effacer
# ---------------------------------------------------------------------------

def _tableau(postes: list[dict]) -> str:
    lignes = []
    for p in postes:
        marque = "  libérable" if p.get("liberable") else ""
        lignes.append(f"  {p['libelle'][:38]:<38} {p['taille']:>10}  [{p['cle']}]{marque}")
    return "\n".join(lignes)


def cmd_espace(options, sortie: Sortie) -> int:
    from . import inventaire

    resultat = inventaire.inventaire(config_cli("espace"))
    texte = (f"Scribouille occupe {resultat['total']} ({chemins.RACINE}).\n" + _tableau(resultat["postes"])
             + f"\n  Libérable sans rien perdre : {langues.octets(resultat['liberable_octets'])}"
             + f"\n  Transcriptions (à part, jamais effacées sans demande) : "
               f"{langues.octets(resultat['transcriptions_octets'])} dans {resultat['transcriptions']['dossier']}")
    if resultat["non_reconnus"]:
        texte += "\n  Non reconnus, jamais touchés : " + ", ".join(resultat["non_reconnus"][:10])
    sortie.donnees(resultat, texte)
    return OK


def _confirmer(sortie: Sortie, question: str, oui: bool) -> bool:
    if oui:
        return True
    if sortie.json or not sys.stdin or not sys.stdin.isatty():
        raise Echec("confirmation", "confirmation requise : relancer avec --oui (ou --apercu pour voir seulement)",
                    ARGUMENTS)
    try:
        reponse = input(question + " Taper « oui » pour confirmer : ")
    except EOFError:
        return False
    return reponse.strip().lower() == "oui"


def cmd_effacer(options, sortie: Sortie) -> int:
    from . import inventaire

    config = config_cli("effacer")
    if options.complet:
        apercu = inventaire.apercu_effacement(not options.avec_transcriptions, config,
                                              avec_programme=not options.garder_programme)
        texte = (f"Effacement complet : {apercu['total']}\n" + _tableau(apercu["postes"])
                 + ("\n  Transcriptions : gardées" if apercu["garder_transcriptions"]
                    else f"\n  TRANSCRIPTIONS AUSSI : {langues.octets(apercu['transcriptions_octets'])}"
                         f" dans {apercu['transcriptions']['dossier']}")
                 + (f"\n  Puis désinstallation silencieuse : {apercu['desinstalleur']}" if apercu["desinstalleur"] else ""))
        if apercu["non_reconnus"]:
            texte += "\n  Non reconnus, laissés : " + ", ".join(apercu["non_reconnus"][:10])
        if options.resume:
            # Avec marque d'ordre : le désinstalleur (Inno Setup) la lit en UTF-8.
            Path(options.resume).write_text(_resume_desinstalleur(apercu), encoding="utf-8-sig")
        if options.apercu:
            sortie.donnees({"apercu": apercu, "fait": False}, texte)
            return OK
        sortie.dire(texte)
        question = "Tout effacer ?" if apercu["garder_transcriptions"] else "Tout effacer, TRANSCRIPTIONS COMPRISES ?"
        if not _confirmer(sortie, question, options.oui):
            sortie.donnees({"apercu": apercu, "fait": False}, "Rien n'a été effacé.")
            return ARGUMENTS
        bilan = inventaire.executer_effacement(apercu["jeton"])
        if bilan.get("desinstalleur"):
            # Programme, raccourcis et clé de registre : le désinstalleur, en
            # silence, une fois cette commande terminée.
            inventaire.nettoyer_apres(os.getpid(), bilan["desinstalleur"])
        sortie.donnees({"apercu": apercu, "fait": True, "bilan": bilan},
                       f"Effacé : {langues.octets(bilan.get('octets', 0))}"
                       + ("".join(f"\n  reste : {r}" for r in bilan.get("restes", [])[:10])))
        return OK if not bilan.get("restes") else ECHEC_PARTIEL
    resultat = inventaire.inventaire(config)
    if options.liberable:
        cles = [p["cle"] for p in resultat["postes"] if p["liberable"]]
    else:
        cles = list(options.cles)
    if not cles:
        raise Echec("arguments", "rien à effacer : CLE..., --liberable ou --complet (scribouille espace)", ARGUMENTS)
    par_cle = {p["cle"]: p for p in resultat["postes"]}
    inconnues = [c for c in cles if c not in par_cle]
    if inconnues:
        raise Echec("cle_inconnue", f"poste inconnu : {', '.join(inconnues)} (scribouille espace)", ARGUMENTS)
    choisis = [par_cle[c] for c in cles]
    total = sum(p["octets"] for p in choisis)
    texte = f"À libérer : {langues.octets(total)}\n" + _tableau(choisis)
    if options.apercu:
        sortie.donnees({"postes": choisis, "total_octets": total, "fait": False}, texte)
        return OK
    sortie.dire(texte)
    non_liberables = [p["cle"] for p in choisis if not p["liberable"]]
    question = "Libérer ?" if not non_liberables else f"Effacer, y compris {', '.join(non_liberables)} ?"
    if not _confirmer(sortie, question, options.oui):
        sortie.donnees({"fait": False}, "Rien n'a été effacé.")
        return ARGUMENTS
    bilan = inventaire.liberer(cles, config)
    sortie.donnees({"fait": True, "bilan": bilan}, f"Libéré : {langues.octets(bilan['octets'])}"
                   + "".join(f"\n  reste : {r}" for r in bilan["restes"][:10]))
    return OK if not bilan["restes"] else ECHEC_PARTIEL


def _resume_desinstalleur(apercu: dict) -> str:
    """Texte court lu par le désinstalleur (packaging/setup.iss) pour sa question."""
    lignes = [f"{p['libelle']} : {p['taille']}" for p in apercu["postes"]
              if p["cle"] not in ("programme", "installation") and p["octets"] > 0]
    lignes.append(f"TOTAL : {apercu['total']}")
    return "\r\n".join(lignes) + "\r\n"


# ---------------------------------------------------------------------------
# vocabulaire
# ---------------------------------------------------------------------------

def cmd_vocabulaire(options, sortie: Sortie) -> int:
    from . import config as config_module, vocabulaire_interface, vocabulaire_v2

    config = config_module.charger()
    if options.action == "etat":
        etat = vocabulaire_interface.etat(config, config.get("langue", "fr"))
        resume = vocabulaire_v2.resume(vocabulaire_v2.effectif(config)[0])
        sortie.donnees({"etat": etat, "resume": resume, "fichier": str(vocabulaire_v2.FICHIER_PERSONNEL)},
                       f"Vocabulaire : {json.dumps(resume, ensure_ascii=False)}\n  {vocabulaire_v2.FICHIER_PERSONNEL}")
        return OK
    if options.action in ("importer", "exporter", "appliquer") and not options.fichier:
        raise Echec("arguments", f"vocabulaire {options.action} FICHIER", ARGUMENTS)
    if options.action == "importer":
        retour = vocabulaire_interface.importer(options.fichier)
        sortie.donnees(retour, retour.get("message", ""))
        return OK if retour.get("ok") else ARGUMENTS
    if options.action == "exporter":
        if Path(options.fichier).exists() and not options.ecraser:
            raise Echec("sortie_existante", f"{options.fichier} existe déjà", SORTIE_EXISTANTE, "ajouter --ecraser")
        retour = vocabulaire_interface.exporter(options.fichier, config)
        sortie.donnees(retour, retour.get("message", ""))
        return OK
    if options.action == "appliquer":
        return _vocabulaire_appliquer(options, sortie, config)
    # apprendre : les options d'origine de « --apprendre-vocabulaire »
    from . import apprentissage

    if not options.brut or len(options.brut) != len(options.propre):
        raise Echec("arguments", "vocabulaire apprendre --brut B --propre P [--cr CR] (par paires)", ARGUMENTS)
    arguments = ["--apprendre-vocabulaire"]
    for rang, (brut, propre) in enumerate(zip(options.brut, options.propre)):
        arguments += ["--brut", brut, "--propre", propre]
        if rang < len(options.cr):
            arguments += ["--cr", options.cr[rang]]
    if options.sortie:
        arguments += ["--sortie", options.sortie]
    if options.importer:
        arguments.append("--importer")
    return apprentissage.principal_cli(arguments)


def _vocabulaire_appliquer(options, sortie: Sortie, config: dict) -> int:
    """Applique le vocabulaire effectif (corrections) à un texte existant."""
    from . import vocabulaire_usage, vocabulaire_v2
    from .moteur import Segment

    source = Path(options.fichier)
    if not source.is_file():
        raise Echec("introuvable", f"introuvable : {source}", ARGUMENTS)
    cible = Path(options.sortie) if options.sortie else None
    if cible is None and not options.ecraser:
        raise Echec("sortie_existante", "le fichier serait réécrit", SORTIE_EXISTANTE,
                    "--sortie AUTRE.txt, ou --ecraser pour réécrire le fichier")
    if cible is not None and cible.exists() and not options.ecraser:
        raise Echec("sortie_existante", f"{cible} existe déjà", SORTIE_EXISTANTE, "ajouter --ecraser")
    voc, _problemes = vocabulaire_v2.effectif(config)
    correcteur = vocabulaire_usage.Correcteur(voc, rapprochement=bool(config.get("rapprochement_vocabulaire", True)))
    lignes = source.read_text(encoding="utf-8").split("\n")
    segments = [Segment(0.0, 0.0, ligne) for ligne in lignes]
    remplacements = correcteur.corriger_segments(segments)
    (cible or source).write_text("\n".join(s.texte for s in segments), encoding="utf-8")
    sortie.donnees({"fichier": str((cible or source).resolve()), "remplacements": remplacements},
                   f"{len(remplacements)} remplacement(s) : {(cible or source)}")
    return OK


# ---------------------------------------------------------------------------
# agent, mesurer, donnees
# ---------------------------------------------------------------------------

def cmd_agent(options, sortie: Sortie) -> int:
    from . import fiche_agent

    texte = fiche_agent.texte()
    if options.action == "afficher":
        sortie.donnees({"fiche": texte}, texte)
        return OK
    cible = fiche_agent.destination(options.cible, Path(options.dossier) if options.dossier else None)
    if cible.exists() and cible.read_text(encoding="utf-8") != texte and not options.ecraser:
        raise Echec("sortie_existante", f"{cible} existe et diffère", SORTIE_EXISTANTE, "ajouter --ecraser")
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(texte, encoding="utf-8")
    sortie.donnees({"fichier": str(cible)}, f"Fiche écrite : {cible}")
    return OK


_ANCIENNES = {"campagne": "--campagne", "banc": "--banc", "endurance": "--endurance",
              "comparer": "--comparer", "vocabulaire": "--mesurer-vocabulaire", "rythmes": "--banc"}


def cmd_mesurer(options, sortie: Sortie) -> int:
    from . import journal

    reste = list(options.reste or [])
    journal.silence_bibliotheques()
    if options.quoi == "campagne":
        from . import campagne

        return campagne.principal_cli(["--campagne", *reste])
    if options.quoi in ("banc", "rythmes"):
        from . import banc

        return banc.principal_cli(["--banc", *(["--modes"] if options.quoi == "rythmes" else []), *reste])
    if options.quoi == "endurance":
        from . import endurance

        return endurance.principal_cli(["--endurance", *reste])
    if options.quoi == "comparer":
        from . import comparaison

        return comparaison.principal_cli(["--comparer", *reste])
    from . import mesure_vocabulaire

    return mesure_vocabulaire.principal_cli(["--mesurer-vocabulaire", *reste])


def cmd_donnees(options, sortie: Sortie) -> int:
    from . import migration

    return migration.principal_cli()


_COMMANDES = {
    "transcrire": cmd_transcrire, "reprendre": cmd_reprendre, "etat": cmd_etat, "lire": cmd_lire,
    "reglages": cmd_reglages, "diagnostic": cmd_diagnostic, "agent": cmd_agent, "espace": cmd_espace,
    "effacer": cmd_effacer, "vocabulaire": cmd_vocabulaire, "mesurer": cmd_mesurer, "materiel": cmd_materiel,
    "donnees": cmd_donnees, "verifier": cmd_verifier,
}
