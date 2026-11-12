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

COMMANDES = ("transcrire", "reprendre", "etat", "lire", "exporter", "reglages", "diagnostic", "agent", "espace",
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
    "motif_sortie": "Nom des fichiers produits ; vide : {date}-{nom}.",
    "dossier_surveille": "Dossier scruté par la surveillance.",
    "surveillance": "Transcrire ce qui arrive dans le dossier surveillé.",
    "maj_verifier": "Vérifier les mises à jour (seul appel réseau hors modèles).",
    "barre_taches": "Progression sur l'icône de la barre des tâches.",
    "prevenir_fin": "Fin de file, fenêtre en arrière-plan : clignotement, titre, notification Windows sans son.",
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
        """L'erreur en clair sur la sortie d'erreur, toujours ; en JSON sur la sortie standard en plus."""
        if self.json:
            self._ecrire({"schema": SCHEMA, "commande": self.commande, "erreur": {
                "code": echec.code, "message": echec.message, "code_retour": echec.code_retour,
                "suggestion": echec.suggestion}})
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

#: Demandes d'aide, acceptées seules ou après une commande.
AIDES = ("-h", "--help", "--aide")

#: Anciennes formes (avant la 3.0) et processus de fond lancés par
#: l'application : `transcriber.pyw` les traite lui-même, après ce module.
ANCIENNES_FORMES = ("--verifier", "--banc", "--banc-essai", "--campagne", "--campagne-essai", "--endurance",
                    "--endurance-essai", "--comparer", "--comparer-essai", "--reconnaitre", "--detecter-materiel",
                    "--revenir-whiscribe", "--apprendre-vocabulaire", "--mesurer-vocabulaire")


class ErreurUsage(Exception):
    """Arguments refusés : message en français, code 2, jamais de fenêtre."""

    def __init__(self, message: str, suggestion: str = ""):
        super().__init__(message)
        self.message, self.suggestion = message, suggestion


def _traduire(message: str) -> str:
    """Les messages d'argparse (anglais), en français."""
    import re

    regles = (
        (r"the following arguments are required: (.+)", "argument obligatoire manquant : {0}"),
        (r"unrecognized arguments: (.+)", "option ou argument inconnu : {0}"),
        (r"argument (.+?): invalid choice: '?([^']*?)'? \(choose from (.+)\)",
         "{0} : « {1} » n'est pas une valeur possible (valeurs : {2})"),
        (r"argument (.+?): expected one argument", "{0} : valeur manquante"),
        (r"argument (.+?): expected at least one argument", "{0} : valeur manquante"),
        (r"argument (.+?): not allowed with argument (.+)", "{0} et {1} ne vont pas ensemble"),
        (r"argument (.+?): invalid (\w+) value: '?([^']*?)'?$", "{0} : « {2} » n'est pas un nombre valable"),
        (r"argument (.+?): ignored explicit argument '?([^']*?)'?$", "{0} ne prend pas de valeur (« {1} »)"),
        (r"one of the arguments (.+) is required", "il faut l'un de : {0}"),
        (r"ambiguous option: (.+?) could match (.+)", "option ambiguë : {0} ({1})"),
    )
    for motif, gabarit in regles:
        trouve = re.fullmatch(motif, message.strip())
        if trouve:
            morceaux = [g.replace("'", "").replace("/", " ou ") for g in trouve.groups()]
            return gabarit.format(*morceaux)
    return message


class _Analyseur(argparse.ArgumentParser):
    """Analyseur qui lève `ErreurUsage` au lieu d'écrire en anglais et de quitter."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("add_help", False)
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):  # type: ignore[override]
        raise ErreurUsage(_traduire(message))

    def exit(self, status=0, message=None):  # type: ignore[override]
        raise ErreurUsage(_traduire(message or "arguments invalides"))


def reconnue(arguments: list[str]) -> bool:
    """Ces arguments sont-ils une commande de ce module ?"""
    reste = [a for a in arguments if a != "--json"]
    if not reste:
        return False
    return reste[0] in COMMANDES or reste[0] in (*AIDES, "--version")


def pour_ce_module(arguments: list[str], console: bool) -> bool:
    """
    Ces arguments vont-ils à la ligne de commande plutôt qu'à la fenêtre ?
    Depuis l'exécutable console (`scribouille.com`) ou depuis les sources avec
    des arguments, TOUJOURS, hors anciennes formes : une faute de frappe rend
    un message et le code 2, jamais une fenêtre (qui, sans bureau, resterait
    suspendue). L'exécutable fenêtré ne bascule que sur une commande connue.
    """
    if reconnue(arguments):
        return True
    if any(a in ANCIENNES_FORMES for a in arguments):
        return False
    return console


def _sous_commandes(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in p._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _ajouter(parseur: argparse.ArgumentParser, *noms: str, aide: str = "", **kwargs) -> None:
    parseur.add_argument(*noms, help=aide, **kwargs)


def _analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="scribouille")
    p.add_argument("--json", action="store_true")
    p.add_argument("--version", action="store_true")
    s = p.add_subparsers(dest="commande", parser_class=_Analyseur)

    def commande(nom: str, usage: str, resume: str, description: str = "") -> argparse.ArgumentParser:
        x = s.add_parser(nom, prog=f"scribouille {nom}", usage=usage, description=description or resume)
        x.resume = resume  # type: ignore[attr-defined]
        return x

    rythmes = ("vitesse", "equilibre", "discret", "auto")
    t = commande("transcrire", "FICHIER|DOSSIER... [options]", "transcrire des enregistrements",
                 "Transcrit des fichiers audio ou vidéo, ou les enregistrements d'un dossier. Les options valent "
                 "pour cette commande seule : les réglages ne changent pas.")
    _ajouter(t, "chemins", nargs="+", metavar="FICHIER|DOSSIER", aide="Fichiers ou dossiers à transcrire.")
    _ajouter(t, "--sortie", default="", metavar="DOSSIER", aide="Dossier des sorties ; défaut : à côté de chaque source.")
    _ajouter(t, "--formats", default="txt,json", metavar="LISTE",
             aide="txt, json, srt, vtt, horodatage, séparés par des virgules ; défaut : txt,json.")
    _ajouter(t, "--langue", default="", metavar="CODE", aide="Langue parlée (fr, en...) ou auto ; défaut : le réglage.")
    _ajouter(t, "--preset", choices=("qualite", "rapide"), metavar="qualite|rapide",
             aide="large-v3 ou turbo ; défaut : le réglage.")
    _ajouter(t, "--moteur", choices=("auto", "openvino", "ctranslate2"), default="auto",
             metavar="auto|openvino|ctranslate2", aide="Moteur imposé ; défaut : le réglage du poste.")
    _ajouter(t, "--peripherique", choices=("CPU", "GPU", "NPU", "cpu", "gpu", "npu"), metavar="CPU|GPU|NPU",
             aide="Périphérique d'OpenVINO (implique --moteur openvino).")
    _ajouter(t, "--rythme", choices=rythmes, metavar="|".join(rythmes), aide="Part du poste laissée à l'utilisateur.")
    _ajouter(t, "--locuteurs", default="", metavar="auto|non|N",
             aide="Séparer les voix (extension installée), N : nombre attendu.")
    _ajouter(t, "--noms", default="", metavar="Alice,Bob", aide="Noms des voix séparées, dans l'ordre, ou « Locuteur 2=Bob ».")
    _ajouter(t, "--vocabulaire", action="append", default=[], metavar="F.toml",
             aide="Vocabulaire d'équipe en plus du personnel ; répétable.")
    _ajouter(t, "--sans-vocabulaire", action="store_true", aide="Ni amorce ni corrections du vocabulaire.")
    _ajouter(t, "--recursif", action="store_true", aide="Sous-dossiers compris.")
    _ajouter(t, "--telecharger", action="store_true", aide="Permet de télécharger un modèle absent.")
    _ajouter(t, "--ecraser", action="store_true", aide="Refait un fichier déjà transcrit.")
    t.add_argument("--json", action="store_true")

    r = commande("reprendre", "[CLE|FICHIER] [options]", "reprendre une transcription interrompue",
                 "Reprend une transcription interrompue au segment près, avec tout ce que la demande de départ "
                 "prévoyait (formats, dossier de sortie, langue, vocabulaire, voix, noms, rythme).")
    _ajouter(r, "cible", nargs="?", default="", metavar="CLE|FICHIER", aide="Défaut : la plus récente (scribouille etat).")
    _ajouter(r, "--sortie", default="", metavar="DOSSIER", aide="Autre dossier de sortie que celui de départ.")
    _ajouter(r, "--formats", default="", metavar="LISTE", aide="Autres formats que ceux de départ.")
    _ajouter(r, "--rythme", choices=rythmes, metavar="|".join(rythmes), aide="Autre rythme que celui de départ.")
    _ajouter(r, "--telecharger", action="store_true", aide="Permet de télécharger le modèle de départ s'il manque.")
    r.add_argument("--json", action="store_true")

    e = commande("etat", "", "transcriptions en cours et reprenables, moteurs actifs")
    e.add_argument("--json", action="store_true")

    lire = commande("lire", "SORTIE.json|SORTIE.txt [options]", "lire une transcription par pages",
                    "Lecture bornée d'un compagnon .json : au plus --limite mots à partir du segment --decalage.")
    _ajouter(lire, "fichier", metavar="SORTIE.json|SORTIE.txt", aide="Transcription à lire.")
    _ajouter(lire, "--depuis", type=float, default=None, metavar="S", aide="Segments qui finissent après S secondes.")
    _ajouter(lire, "--jusqua", type=float, default=None, metavar="S", aide="Segments qui commencent avant S secondes.")
    _ajouter(lire, "--limite", type=int, default=2000, metavar="N", aide="Mots au plus par page ; défaut : 2000.")
    _ajouter(lire, "--decalage", type=int, default=0, metavar="N", aide="Premier segment de la page ; défaut : 0.")
    _ajouter(lire, "--douteux", action="store_true", aide="Seulement les segments qui ont des mots sous le seuil.")
    _ajouter(lire, "--texte", action="store_true", aide="Texte lisible horodaté au lieu du JSON (sans --json).")
    lire.add_argument("--json", action="store_true")

    x = commande("exporter", "SORTIE.txt [--format md] [--remplacer|--nouveau]", "exporter en Markdown",
                 "Export Markdown à côté de la transcription ; un export retouché n'est jamais écrasé.")
    _ajouter(x, "fichier", metavar="SORTIE.txt", aide="Transcription à exporter.")
    _ajouter(x, "--format", default="md", choices=("md",), metavar="md", aide="Format de l'export ; défaut : md.")
    choix = x.add_mutually_exclusive_group()
    choix.add_argument("--remplacer", action="store_true", help="Remplace l'export existant, même retouché.")
    choix.add_argument("--nouveau", action="store_true", help="Écrit toujours une variante numérotée (-2.md).")
    x.add_argument("--json", action="store_true")

    g = commande("reglages", "[liste|lire CLE|definir CLE=VALEUR...|defaut CLE...]", "lire et changer les réglages",
                 "Chaque réglage, sa valeur par défaut et son effet : docs/reglages.md.")
    _ajouter(g, "action", nargs="?", default="liste", choices=("liste", "lire", "definir", "defaut"),
             metavar="liste|lire|definir|defaut", aide="Défaut : liste.")
    _ajouter(g, "valeurs", nargs="*", metavar="CLE|CLE=VALEUR", aide="Clés, ou paires pour definir.")
    g.add_argument("--json", action="store_true")

    d = commande("diagnostic", "[--materiel]", "prêt ou non, et pourquoi")
    _ajouter(d, "--materiel", action="store_true", aide="Relance d'abord la détection lente du matériel.")
    d.add_argument("--json", action="store_true")

    a = commande("agent", "[afficher|installer [--cible claude|codex] [--dossier D] [--ecraser]]",
                 "fiche d'usage pour Claude Code ou Codex")
    _ajouter(a, "action", nargs="?", default="afficher", choices=("afficher", "installer"),
             metavar="afficher|installer", aide="Défaut : afficher.")
    _ajouter(a, "--cible", choices=("claude", "codex"), default=None, metavar="claude|codex",
             aide="installer : outil visé ; défaut : claude.")
    _ajouter(a, "--dossier", default="", metavar="D", aide="installer : dossier personnel ; défaut : celui de Windows.")
    _ajouter(a, "--ecraser", action="store_true", aide="installer : remplace une fiche retouchée.")
    a.add_argument("--json", action="store_true")

    es = commande("espace", "", "ce que Scribouille occupe, par poste")
    es.add_argument("--json", action="store_true")

    ef = commande("effacer", "CLE...|--liberable|--complet [options]", "libérer de la place, ou tout effacer",
                  "Liste et tailles d'abord ; rien n'est effacé sans --oui ou « oui » tapé dans un terminal.")
    _ajouter(ef, "cles", nargs="*", metavar="CLE", aide="Postes de « scribouille espace ».")
    _ajouter(ef, "--liberable", action="store_true", aide="Tout ce qui se libère sans rien perdre.")
    _ajouter(ef, "--complet", action="store_true", aide="Tout ce que Scribouille a écrit, sauf les transcriptions.")
    _ajouter(ef, "--avec-transcriptions", action="store_true", aide="--complet : les transcriptions aussi.")
    _ajouter(ef, "--garder-programme", action="store_true", aide="--complet : sans désinstaller le programme.")
    _ajouter(ef, "--resume", default="", metavar="F", aide="--complet : résumé pour le désinstalleur.")
    _ajouter(ef, "--apercu", action="store_true", aide="Montre seulement.")
    _ajouter(ef, "--oui", action="store_true", aide="Confirme sans question.")
    ef.add_argument("--json", action="store_true")

    v = commande("vocabulaire", "[etat|appliquer F|importer F|exporter F|apprendre ...] [options]",
                 "vocabulaire personnel et d'équipe")
    _ajouter(v, "action", nargs="?", default="etat", choices=("etat", "appliquer", "importer", "exporter", "apprendre"),
             metavar="etat|appliquer|importer|exporter|apprendre", aide="Défaut : etat.")
    _ajouter(v, "fichier", nargs="?", default="", metavar="F", aide="Fichier lu ou écrit.")
    _ajouter(v, "--sortie", default="", metavar="F", aide="appliquer, apprendre : fichier écrit.")
    _ajouter(v, "--ecraser", action="store_true", aide="appliquer, exporter : remplace un fichier existant.")
    _ajouter(v, "--brut", action="append", default=[], metavar="B.txt", aide="apprendre : transcription brute.")
    _ajouter(v, "--propre", action="append", default=[], metavar="RELUE.txt", aide="apprendre : la même, relue.")
    _ajouter(v, "--cr", action="append", default=[], metavar="CR", aide="apprendre : compte rendu, facultatif.")
    _ajouter(v, "--importer", action="store_true", aide="apprendre : verse les propositions, à relire.")
    v.add_argument("--json", action="store_true")

    m = commande("mesurer", "campagne|banc|rythmes|endurance|comparer|vocabulaire [options d'origine]",
                 "outils de mesure")
    _ajouter(m, "quoi", choices=MESURES, metavar="|".join(MESURES), aide="Outil de mesure.")
    m.add_argument("reste", nargs=argparse.REMAINDER)

    ma = commande("materiel", "[detecter|proposer [--appliquer]]", "matériel détecté, réglage proposé")
    _ajouter(ma, "action", nargs="?", default="detecter", choices=("detecter", "proposer"),
             metavar="detecter|proposer", aide="Défaut : detecter.")
    _ajouter(ma, "--appliquer", action="store_true", aide="proposer : enregistre le réglage proposé.")
    ma.add_argument("--json", action="store_true")

    do = commande("donnees", "revenir-whiscribe", "revenir à l'ancien dossier de données")
    _ajouter(do, "action", choices=("revenir-whiscribe",), metavar="revenir-whiscribe",
             aide="Remet les données dans WhiScribe, pour une version antérieure à la 2.4.")
    do.add_argument("--json", action="store_true")

    for nom, resume in (("verifier", "bilan de l'installation"), ("version", "numéro de version"),
                        ("aide", "cette aide, ou celle d'une commande")):
        x = commande(nom, "[COMMANDE]" if nom == "aide" else "", resume)
        if nom == "aide":
            _ajouter(x, "sujet", nargs="?", default="", metavar="COMMANDE", aide="Commande à décrire.")
        x.add_argument("--json", action="store_true")
    return p


#: Outils de `mesurer`, et les options de chacun (celles de leur forme d'origine).
MESURES = ("campagne", "banc", "rythmes", "endurance", "comparer", "vocabulaire")
OPTIONS_MESURES = {
    "campagne": ("--appliquer", "--corpus", "--debut", "--duree", "--limite-extraits", "--peripherique",
                 "--proprietes-ov", "--recommencer", "--reglages", "--reunion", "--sans-temoin", "--telecharger"),
    "banc": ("--appliquer", "--npu", "--telecharger"),
    "rythmes": ("--moteur", "--peripherique", "--repetitions", "--rythmes", "--sans-enregistrer",
                "--sans-temoin-passif", "--variantes-ov"),
    "endurance": ("--corpus", "--memoire-libre", "--passages", "--peripherique", "--pression", "--recommencer",
                  "--reglage", "--sans-diagnostic"),
    "comparer": ("--debut", "--duree", "--faisceau-ctranslate2", "--faisceau-openvino", "--glossaire", "--ouvrir",
                 "--peripherique", "--preset", "--reference", "--sans-corrections", "--sans-glossaire", "--sortie"),
    "vocabulaire": ("--corpus", "--corpus-paquet", "--peripherique", "--recommencer", "--reference", "--reglage",
                    "--reunion", "--vocabulaire"),
}


def options_de(nom: str) -> list[str]:
    """Options d'une commande telles que l'analyseur les accepte (sans --json)."""
    if nom == "mesurer":
        return sorted({o for liste in OPTIONS_MESURES.values() for o in liste})
    parseur = _sous_commandes(_analyseur()).get(nom)
    if parseur is None:
        return []
    return sorted(o for action in parseur._actions for o in action.option_strings if o != "--json")


def aide_commande(nom: str) -> str:
    """Aide d'une commande, générée depuis son analyseur : usage, effet, chaque option."""
    import textwrap

    parseur = _sous_commandes(_analyseur())[nom]
    lignes = [f"scribouille {nom} {parseur.usage or ''}".rstrip(), "",
              textwrap.fill(parseur.description or "", 100), "", "Arguments et options :"]
    options = []
    for action in parseur._actions:
        if action.dest in ("json", "reste") or not (action.help or action.option_strings):
            continue
        if action.option_strings:
            gauche = ", ".join(action.option_strings)
            if action.nargs != 0:
                gauche += f" {action.metavar or action.dest.upper()}"
        else:
            gauche = str(action.metavar or action.dest)
        options.append((gauche, action.help or ""))
    if nom == "mesurer":
        for quoi, liste in OPTIONS_MESURES.items():
            options.append((quoi, ", ".join(liste)))
    options += [("--json", "Sortie structurée (docs/ligne-de-commande.md)."), (", ".join(AIDES), "Cette aide.")]
    largeur = min(30, max(len(g) for g, _ in options) + 2)
    for gauche, texte in options:
        lignes.append(f"  {gauche:<{largeur}}{texte}" if len(gauche) < largeur else f"  {gauche}\n  {'':<{largeur}}{texte}")
    return "\n".join(lignes).replace("\n\n\n", "\n\n").rstrip() + "\n"


def aide_generale() -> str:
    """Résumé de toutes les commandes, généré depuis les analyseurs."""
    lignes = [f"Scribouille {VERSION}, transcription locale, sans fenêtre.", ""]
    for nom, parseur in _sous_commandes(_analyseur()).items():
        lignes.append(f"  scribouille {nom} {parseur.usage or ''}".rstrip())
        lignes.append(f"      {parseur.resume}")  # type: ignore[attr-defined]
    lignes += ["", "  scribouille COMMANDE --aide : les options d'une commande (aussi -h, --help, « aide COMMANDE »).",
               "  --json sur toute commande : sortie structurée (docs/ligne-de-commande.md).",
               "  Codes de retour : 0 fait, 1 échec partiel, 2 arguments, 3 pas prêt, 4 sortie existante,",
               "  5 interrompu (reprenable), 6 disque ou mémoire.", ""]
    return "\n".join(lignes)


def _commande_vue(arguments: list[str]) -> str:
    """Premier mot qui n'est pas une option : la commande demandée (« » s'il n'y en a pas)."""
    return next((a for a in arguments if not a.startswith("-")), "")


def _usage(sortie_commande: str, en_json: bool, message: str, suggestion: str = "") -> int:
    sortie = Sortie(sortie_commande or "?", en_json)
    sortie.erreur(Echec("arguments", message, ARGUMENTS, suggestion))
    return ARGUMENTS


def principal(arguments: list[str]) -> int:
    import difflib

    _flux_en_utf8()
    en_json = "--json" in arguments
    vue = _commande_vue(arguments)
    aide = any(a in AIDES for a in arguments)
    if not vue:
        if aide or not [a for a in arguments if a != "--json"]:
            Sortie("aide", en_json).donnees({"commandes": list(COMMANDES), "aide": aide_generale()}, aide_generale())
            return OK
        if arguments and all(a in ("--json", "--version") for a in arguments):
            Sortie("version", en_json).donnees({"version": VERSION, "schema": SCHEMA}, f"Scribouille {VERSION}")
            return OK
        inconnues = [a for a in arguments if a not in ("--json", "--version")]
        return _usage("", en_json, f"option inconnue : {' '.join(inconnues)}", "scribouille aide")
    if vue not in COMMANDES:
        proches = difflib.get_close_matches(vue, COMMANDES, n=1)
        return _usage("", en_json, f"commande inconnue : « {vue} »"
                      + (f" ; vouliez-vous dire « {proches[0]} » ?" if proches else ""),
                      "commandes : " + ", ".join(COMMANDES) + " (scribouille aide)")
    if vue == "aide" or aide:
        sujet = vue
        if vue == "aide":
            suite = [a for a in arguments[arguments.index("aide") + 1:] if not a.startswith("-")]
            sujet = suite[0] if suite else ("aide" if aide else "")
            if sujet and sujet not in COMMANDES:
                return _usage("aide", en_json, f"commande inconnue : « {sujet} »", "scribouille aide")
        texte = aide_commande(sujet) if sujet else aide_generale()
        Sortie("aide", en_json).donnees({"commande": sujet, "aide": texte, "options": options_de(sujet) if sujet else [],
                                         "commandes": list(COMMANDES)}, texte)
        return OK
    try:
        options = _analyseur().parse_args(arguments)
    except ErreurUsage as erreur:
        return _usage(vue, en_json, erreur.message, f"scribouille {vue} --aide")
    options.json = en_json
    commande = options.commande
    sortie = Sortie(commande, en_json)
    if commande == "version":
        sortie.donnees({"version": VERSION, "schema": SCHEMA}, f"Scribouille {VERSION}")
        return OK
    from . import journal

    try:
        _controler_options(commande, options)
    except ErreurUsage as erreur:
        return _usage(commande, en_json, erreur.message, erreur.suggestion or f"scribouille {commande} --aide")
    _interruption_comme_ctrl_c()
    if commande in SANS_ECRITURE:
        journal.sans_fichier()
    else:
        journal.demarrer()
    journal.silence_bibliotheques()
    config_cli(commande)  # pose la langue de l'interface
    try:
        return _COMMANDES[commande](options, sortie)
    except ErreurUsage as erreur:
        return _usage(commande, en_json, erreur.message, erreur.suggestion or f"scribouille {commande} --aide")
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


def _interruption_comme_ctrl_c() -> None:
    """
    Ctrl+Pause (et l'arrêt d'une tâche ou d'une session qui l'envoie) vaut
    Ctrl+C : le travail fait est gardé, code 5, `reprendre` le poursuit. Sans
    cela, Windows tue le processus sur-le-champ, code quelconque.
    """
    import signal

    def interrompre(_signal, _cadre):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGBREAK, interrompre)  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass


def _flux_en_utf8() -> None:
    """Sorties en UTF-8, que la console, un tube ou un fichier les reçoive."""
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


#: Langues de Whisper (faster_whisper.tokenizer._LANGUAGE_CODES), recopiées :
#: les lire chargerait la bibliothèque de calcul dans ce processus.
LANGUES_PAROLE = tuple(
    "af am ar as az ba be bg bn bo br bs ca cs cy da de el en es et eu fa fi fo fr gl gu ha haw he hi hr ht hu hy "
    "id is it ja jw ka kk km kn ko la lb ln lo lt lv mg mi mk ml mn mr ms mt my ne nl nn no oc pa pl ps pt ro ru sa "
    "sd si sk sl sn so sq sr su sv sw ta te tg th tk tl tr tt uk ur uz vi yi yo zh yue".split())


def _instant(texte: str, option: str) -> float | None:
    """« 90 », « 1:30 », « 00:01:30 » ou « 90.5 » en secondes ; None si vide."""
    texte = str(texte or "").strip().replace(",", ".")
    if not texte:
        return None
    try:
        morceaux = [float(x) for x in texte.split(":")]
    except ValueError:
        raise ErreurUsage(f"{option} : « {texte} » n'est pas un instant (HH:MM:SS ou secondes)") from None
    if len(morceaux) > 3 or any(x < 0 for x in morceaux):
        raise ErreurUsage(f"{option} : « {texte} » n'est pas un instant (HH:MM:SS ou secondes)")
    secondes = 0.0
    for x in morceaux:
        secondes = secondes * 60 + x
    return secondes


def _controler_options(commande: str, o) -> None:
    """Combinaisons contradictoires et valeurs impossibles, avant tout travail."""
    def refuser(message: str) -> None:
        raise ErreurUsage(message)

    if commande == "transcrire":
        formats = [f.strip().lower() for f in (o.formats or "").split(",") if f.strip()]
        inconnus = sorted(set(formats) - {"txt", "json", "srt", "vtt", "horodatage"})
        if not formats:
            refuser("--formats : au moins un format (txt, json, srt, vtt, horodatage)")
        if inconnus:
            refuser(f"--formats : format inconnu : {', '.join(inconnus)} (txt, json, srt, vtt, horodatage)")
        if o.langue and o.langue.lower() not in (*LANGUES_PAROLE, "auto"):
            refuser(f"--langue : « {o.langue} » n'est pas une langue connue (fr, en, de... ou auto)")
        if o.sans_vocabulaire and o.vocabulaire:
            refuser("--sans-vocabulaire et --vocabulaire ne vont pas ensemble")
        if o.moteur == "ctranslate2" and o.peripherique:
            refuser("--peripherique vaut pour OpenVINO : il ne va pas avec --moteur ctranslate2")
        locuteurs = str(o.locuteurs or "").strip().lower()
        if locuteurs and locuteurs not in ("auto", "non", "0") and not locuteurs.isdigit():
            refuser(f"--locuteurs : auto, non ou un nombre (pas « {o.locuteurs} »)")
        if o.noms and locuteurs in ("non", "0"):
            refuser("--noms demande des voix séparées : il ne va pas avec --locuteurs non")
    elif commande == "reprendre":
        if o.formats:
            formats = [f.strip().lower() for f in o.formats.split(",") if f.strip()]
            inconnus = sorted(set(formats) - {"txt", "json", "srt", "vtt", "horodatage"})
            if not formats or inconnus:
                refuser("--formats : txt, json, srt, vtt, horodatage")
    elif commande == "lire":
        if o.limite < 1:
            refuser("--limite : un nombre de mots supérieur à 0")
        if o.decalage < 0:
            refuser("--decalage : un rang de segment, 0 ou plus")
        if o.depuis is not None and o.jusqua is not None and o.depuis > o.jusqua:
            refuser("--depuis est après --jusqua")
        if o.texte and o.json:
            refuser("--texte et --json ne vont pas ensemble : l'un ou l'autre")
    elif commande == "reglages":
        if o.action == "liste" and o.valeurs:
            refuser(f"reglages liste ne prend pas d'argument (« {' '.join(o.valeurs)} »)")
        if o.action == "lire" and len(o.valeurs) != 1:
            refuser("reglages lire CLE : une seule clé")
        if o.action in ("lire", "defaut") and any("=" in v for v in o.valeurs):
            refuser(f"reglages {o.action} CLE : la clé seule, sans « = »")
    elif commande == "effacer":
        if o.complet and (o.cles or o.liberable):
            refuser("--complet ne va ni avec --liberable ni avec des clés")
        if o.liberable and o.cles:
            refuser("--liberable ne va pas avec des clés : l'un ou l'autre")
        sans_complet = [n for n, v in (("--avec-transcriptions", o.avec_transcriptions),
                                       ("--garder-programme", o.garder_programme), ("--resume", o.resume)) if v]
        if sans_complet and not o.complet:
            refuser(f"{', '.join(sans_complet)} : seulement avec --complet")
        if o.apercu and o.oui:
            refuser("--apercu et --oui ne vont pas ensemble : regarder, ou effacer")
    elif commande == "vocabulaire":
        par_action = {"etat": (), "importer": (), "exporter": ("ecraser",), "appliquer": ("sortie", "ecraser"),
                      "apprendre": ("sortie", "brut", "propre", "cr", "importer")}
        en_trop = [n for n in ("sortie", "ecraser", "brut", "propre", "cr", "importer")
                   if getattr(o, n) and n not in par_action[o.action]]
        if en_trop:
            refuser(f"vocabulaire {o.action} : " + ", ".join("--" + n for n in en_trop) + " sans objet ici")
        if o.action in ("etat", "apprendre") and o.fichier:
            refuser(f"vocabulaire {o.action} ne prend pas de fichier (« {o.fichier} »)")
        if o.action in ("importer", "exporter", "appliquer") and not o.fichier:
            refuser(f"vocabulaire {o.action} FICHIER : fichier manquant")
    elif commande == "agent":
        en_trop = [n for n, v in (("--cible", o.cible), ("--dossier", o.dossier), ("--ecraser", o.ecraser)) if v]
        if o.action == "afficher" and en_trop:
            refuser(f"{', '.join(en_trop)} : seulement avec « agent installer »")
        o.cible = o.cible or "claude"
    elif commande == "materiel":
        if o.appliquer and o.action != "proposer":
            refuser("--appliquer : seulement avec « materiel proposer »")
    elif commande == "mesurer":
        reste = [a for a in (o.reste or []) if a != "--json"]
        connues = OPTIONS_MESURES[o.quoi]
        inconnues = [a for a in reste if a.startswith("--") and a.split("=")[0] not in connues]
        if inconnues:
            raise ErreurUsage(f"mesurer {o.quoi} : option inconnue : {', '.join(inconnues)}",
                              f"options : {', '.join(connues)}")
        o.reste = reste


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


def _noms(valeur: str) -> dict[str, str]:
    """
    « Alice,Bob » (Locuteur 1, Locuteur 2...) ou « Locuteur 2=Bob,Locuteur 1=Alice ».
    """
    noms: dict[str, str] = {}
    for rang, morceau in enumerate([m.strip() for m in (valeur or "").split(",") if m.strip()], start=1):
        ancien, egal, nouveau = morceau.partition("=")
        if egal:
            noms[ancien.strip()] = nouveau.strip()
        else:
            noms[langues.t("diar.locuteur", n=rang)] = morceau
    return noms


def _renommer(produits: list[str], noms: dict[str, str]) -> list[str]:
    """Renomme les locuteurs dans les .txt produits ; rend les renommages faits."""
    from . import relecture

    faits = []
    for chemin in produits:
        if not chemin.lower().endswith(".txt"):
            continue
        for ancien, nouveau in noms.items():
            if relecture.renommer_locuteur(chemin, ancien, nouveau).get("ok"):
                faits.append(f"{ancien} -> {nouveau}")
    return faits


def _executer_file(sortie: Sortie, elements: list, config: dict, telecharger: bool,
                   noms: dict[str, str] | None = None) -> dict:
    """Une file de fichiers dans le processus moteur, avec progression et Ctrl+C."""
    from . import presets, superviseur, traitement
    from .materiel import detecter_au_demarrage

    mat, _ = detecter_au_demarrage()
    distant = superviseur.Superviseur(telecharger=telecharger)
    file = traitement.FileTraitement(mat, distant=distant)
    file.elements = list(elements)
    resultats: dict[str, dict] = {e.identifiant: {"fichier": e.chemin, "ok": False} for e in elements}
    noms_fichiers = {e.identifiant: e.nom for e in elements}
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
        sortie.progression(f"[{rang[identifiant]}/{len(elements)}] {noms_fichiers[identifiant]} : {phase} {pct} %"
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
            if noms:
                r["renommes"] = _renommer(produits, noms) if donnees.get("locuteurs") else []
                faits = {x.split(" -> ")[0] for x in r["renommes"]}
                oublies = [f"{a} ({b})" for a, b in noms.items() if a not in faits]
                if oublies:
                    journal_ui("attention", f"{noms_fichiers[identifiant]} : noms non appliqués, voix absentes : "
                                            + ", ".join(oublies))
            sortie.fin_progression()
            sortie.evenement("fichier_fini", id=identifiant, **r)
            sortie.dire(f"[{rang[identifiant]}/{len(elements)}] {noms_fichiers[identifiant]} : fait en {r['duree']}"
                        + "".join(f"\n    {c}" for c in r["sorties"]))
        else:
            r.update({"annule": bool(donnees.get("annule")), "erreur": donnees.get("titre") or donnees.get("message") or "",
                      "detail": donnees.get("detail") or donnees.get("message") or ""})
            sortie.fin_progression()
            sortie.evenement("fichier_echec", id=identifiant, **r)
            sortie.dire(f"[{rang[identifiant]}/{len(elements)}] {noms_fichiers[identifiant]} : "
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


def _avertir(sortie: Sortie, texte: str) -> None:
    """Une demande des réglages qui ne sera pas suivie : dite, en JSON et sur la sortie d'erreur."""
    sortie.evenement("journal", niveau="attention", texte=texte)
    sortie.dire(f"  {texte}", erreur=True)


def _raison_openvino(effet: dict, peripherique: str) -> str:
    from . import moteur_openvino

    if effet.get("plantage"):
        return (f"OpenVINO suspendu sur {peripherique} : la dernière ouverture n'a pas abouti "
                f"({effet['plantage']})")
    if not moteur_openvino.installe():
        return "moteur OpenVINO non installé"
    vus = moteur_openvino.peripheriques_disponibles()
    return f"périphérique {peripherique} non vu par OpenVINO (vus : {', '.join(vus) or 'aucun'})"


def _options_satisfaites(options, config: dict, mat, sortie: Sortie) -> None:
    """
    Une option demandée qu'on ne peut pas honorer est dite et rend son code,
    jamais ignorée en silence : voix séparées sans l'extension (code 3), noms
    sans voix séparées (code 2), moteur ou périphérique absents (code 3). Les
    mêmes demandes venues des réglages, elles, sont dites et contournées.
    """
    from . import diarisation, reglage_machine, vocabulaire_v2

    locuteurs = str(options.locuteurs or "").strip().lower()
    voix_demandees = locuteurs == "auto" or (locuteurs.isdigit() and int(locuteurs) > 0)
    if config.get("diarisation") and not diarisation.disponible():
        if voix_demandees or options.noms:
            raise Echec("locuteurs_absents", "séparation des voix demandée ("
                        + ("--locuteurs" if voix_demandees else "--noms") + ") mais non installée : "
                        + diarisation.indisponibilite(), PAS_PRET,
                        "l'installer (fenêtre, écran Réglages, ou installer.bat --locuteurs), ou --locuteurs non")
        _avertir(sortie, "Séparation des voix cochée dans les réglages mais non installée : texte sans voix "
                         "(--locuteurs non pour ne plus le voir).")
    if options.noms and not config.get("diarisation"):
        raise Echec("arguments", "--noms demande des voix séparées : ajouter --locuteurs auto (ou leur nombre)",
                    ARGUMENTS)
    import copy as copie

    from . import materiel as materiel_module, moteur_openvino

    explicite = options.moteur == "openvino" or bool(options.peripherique)
    if explicite and moteur_openvino.installe() and not moteur_openvino.peripheriques_confirmes():
        # Rien de gardé du lancement précédent : périphériques seulement
        # supposés. Une demande explicite se vérifie (détection lente, dans
        # un processus à part, comme `diagnostic --materiel`).
        materiel_module.rafraichir()
        mat = materiel_module.detecter_au_demarrage()[0]
    essai_config, essai_mat = copie.deepcopy(config), copie.deepcopy(mat)
    effet = reglage_machine.appliquer_au_materiel(essai_config, essai_mat)
    if effet.get("indisponible"):
        peripherique = str(effet.get("peripherique") or "CPU").upper()
        raison = _raison_openvino(effet, peripherique)
        if options.moteur == "openvino" or options.peripherique:
            raise Echec("moteur_absent", f"--moteur openvino ({peripherique}) : {raison}", PAS_PRET,
                        "scribouille diagnostic --materiel ; ou --moteur ctranslate2")
        _avertir(sortie, f"Réglage du poste : {raison} ; CTranslate2 prend la main.")
    for fichier in options.vocabulaire or []:
        try:
            vocabulaire_v2.lire(fichier)
        except (OSError, ValueError, vocabulaire_v2.ErreurFormat) as exc:
            raise Echec("arguments", f"--vocabulaire {fichier} : illisible ({exc})", ARGUMENTS) from None


def cmd_transcrire(options, sortie: Sortie) -> int:
    from . import moteur, traitement
    from .materiel import detecter_au_demarrage

    fichiers, refuses = _fichiers(options.chemins, options.recursif)
    if not fichiers:
        raise Echec("aucun_fichier", "aucun fichier audio trouvé"
                    + (f" ({', '.join(refuses[:5])})" if refuses else ""), ARGUMENTS)
    mat, _ = detecter_au_demarrage()
    config = _config_de_commande(options, mat)
    _options_satisfaites(options, config, mat, sortie)
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
    config["noms_locuteurs"] = _noms(options.noms)
    execution = _executer_file(sortie, elements, config, options.telecharger, config["noms_locuteurs"])
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
    etat = reprise.lire_etat(choisie["cle"]) or {}
    demande = etat.get("demande") or {}
    from . import config as config_module

    # Tout ce que la demande de départ prévoyait (formats, langue, vocabulaire,
    # voix, noms, rythme, moteur), puis les seules options données ici.
    config = copy.deepcopy(config_module.charger())
    config.update(copy.deepcopy(demande))
    if options.formats:
        formats = {f.strip().lower() for f in options.formats.split(",") if f.strip()}
        config["formats"] = {"txt": True, "srt": "srt" in formats, "vtt": "vtt" in formats,
                             "horodatage": "horodatage" in formats}
        config["compagnon_confiance"] = "json" in formats
    if options.rythme:
        if options.rythme == "auto":
            config["rythme_auto"] = True
        else:
            config["rythme"], config["rythme_auto"] = options.rythme, False
    if not demande:
        sortie.evenement("journal", niveau="attention",
                         texte="Reprise d'une version antérieure : la demande de départ n'est pas connue, "
                               "réglages actuels et --formats " + (options.formats or "txt,json"))
        sortie.dire("  Demande de départ inconnue (version antérieure) : réglages actuels.", erreur=True)
        if not options.formats:
            config["formats"] = {"txt": True, "srt": False, "vtt": False, "horodatage": False}
            config["compagnon_confiance"] = True
    # Une reprise garde son modèle : le texte ne mêle jamais deux modèles.
    if presets.modele_du_preset(config.get("preset", "qualite"), "") != choisie["modele"]:
        cles = [c for c, p in presets.PRESETS.items() if p["modele"] == choisie["modele"]]
        if cles:
            config["preset"] = cles[0]
        else:
            config["mode_avance"], config["modele_avance"] = True, choisie["modele"]
    source = Path(choisie["chemin"])
    # Sans --sortie : le dossier que la transcription interrompue visait.
    ancien = str(etat.get("sortie") or "")
    dossier = (Path(options.sortie).expanduser().resolve() if options.sortie
               else Path(ancien) if ancien and Path(ancien).is_dir() else source.parent)
    dossier.mkdir(parents=True, exist_ok=True)
    element = traitement.Element(identifiant="r1", chemin=str(source), nom=source.name, taille=source.stat().st_size,
                                 reprise=choisie["cle"], sortie=str(dossier))
    sortie.dire(f"Reprise de {source.name} à {presets.formater_duree(choisie['position'])} "
                f"sur {presets.formater_duree(choisie['duree_audio'])}.")
    execution = _executer_file(sortie, [element], config, options.telecharger,
                               dict(config.get("noms_locuteurs") or {}))
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
    # « en_cours » : un moteur tourne et la sauvegarde a bougé dans la minute.
    moteurs = _moteurs_actifs()
    for r in reprise.lister():
        try:
            maj = time.mktime(time.strptime(str(r.get("date") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            maj = 0.0
        taches.append({**r, "etat": "en_cours" if moteurs and maintenant - maj < 60 else "interrompue",
                       "reprendre": f"scribouille reprendre {r['cle']}"})
    lignes = [f"Moteurs actifs : {len(moteurs)}"] + [f"  PID {m['pid']}, {langues.octets(m['memoire_octets'])}"
                                                      for m in moteurs]
    lignes.append(f"Transcriptions reprenables : {len(taches)}")
    for t in taches:
        lignes.append(f"  {t['nom']} : {t['pct']} % ({presets.formater_duree(t['position'])} sur "
                      f"{presets.formater_duree(t['duree_audio'])}), {t['etat']}, clé {t['cle']}")
    sortie.donnees({"moteurs": moteurs, "taches": taches}, "\n".join(lignes))
    return OK


def cmd_exporter(options, sortie: Sortie) -> int:
    from . import relecture

    fichier = Path(options.fichier).expanduser()
    if fichier.suffix.lower() == ".json":
        fichier = fichier.with_suffix(".txt")
    if not fichier.is_file():
        raise Echec("introuvable", f"transcription introuvable : {fichier}", ARGUMENTS)
    forcer = True if options.remplacer else False if options.nouveau else None
    resultat = relecture.enregistrer_export(fichier, "." + options.format, relecture.markdown(fichier), forcer)
    if not resultat.get("ok"):
        raise Echec(str(resultat.get("code") or "echec"), f"export non écrit : {resultat.get('code')}", ECHEC_PARTIEL)
    texte = f"Export écrit : {resultat['chemin']}"
    if resultat.get("variante"):
        texte += " (l'export précédent a été modifié ou n'est pas de Scribouille : gardé tel quel)"
    elif resultat.get("remplace"):
        texte += " (remplace l'export précédent, intact)"
    sortie.donnees(resultat, texte)
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
        cle = "" if p["cle"].startswith("modele:") else f"  [{p['cle']}]"
        lignes.append(f"  {p['libelle'][:64]:<64} {p['taille']:>10}{cle}{marque}")
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
    "exporter": cmd_exporter,
    "reglages": cmd_reglages, "diagnostic": cmd_diagnostic, "agent": cmd_agent, "espace": cmd_espace,
    "effacer": cmd_effacer, "vocabulaire": cmd_vocabulaire, "mesurer": cmd_mesurer, "materiel": cmd_materiel,
    "donnees": cmd_donnees, "verifier": cmd_verifier,
}
