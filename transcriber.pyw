"""
Scribouille : point d'entrée.

Fenêtre pywebview, interface web dans `web/`, moteur faster-whisper.
Tout se passe sur la machine : aucun envoi vers un service en ligne.

Lancement : double-clic sur ce fichier, ou « lancer.bat ».

Option de diagnostic, utilisée par la chaîne de publication :

    transcriber.pyw --verifier

vérifie les imports, le décodeur audio et l'écriture des dossiers de
travail, affiche un bilan, et sort avec le code 0 si tout va bien.

Options d'extension, sans fenêtre elles non plus. C'est par elles que
l'application s'installe à elle-même la séparation des locuteurs, en se
relançant dans un processus de fond : voir `app/extensions.py`.

    transcriber.pyw --installer-locuteurs [--cible DOSSIER] [--cpu|--cuda]
    transcriber.pyw --verifier-locuteurs  [--cible DOSSIER]
    transcriber.pyw --retirer-locuteurs   [--cible DOSSIER]

Comparaison des deux moteurs sur un vrai enregistrement (voir `app/comparaison.py`) :

    transcriber.pyw --comparer FICHIER [--debut 00:05:00] [--duree 600] [--reference FICHIER]

Campagne de mesure des réglages sur un corpus public avec référence (voir `app/campagne.py`) :

    transcriber.pyw --campagne [--appliquer] [--reunion FICHIER --debut 00:05:00 --duree 600]

Épreuve d'endurance du réglage retenu (voir `app/endurance.py`) :

    transcriber.pyw --endurance [--passages 30] [--pression] [--reglage CLE]

Réglage proposé pour ce poste (voir `app/adaptation.py`), et banc des rythmes
« je travaille en même temps » (voir `app/banc_rythmes.py`) :

    transcriber.pyw --reconnaitre [--appliquer]
    transcriber.pyw --banc --modes [--rythmes vitesse,equilibre,discret] [--peripherique GPU]

Vocabulaire (format 2) : apprentissage à partir de transcriptions relues, et
mesure de chaque étage (voir `app/apprentissage.py`, `app/mesure_vocabulaire.py`) :

    transcriber.pyw --apprendre-vocabulaire --brut BRUT --propre RELUE [--cr CR] [--importer]
    transcriber.pyw --mesurer-vocabulaire --vocabulaire V.toml --reunion AUDIO --reference RELUE
    transcriber.pyw --mesurer-vocabulaire --corpus
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

if not getattr(sys, "frozen", False):
    RACINE = Path(__file__).resolve().parent
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))

from app import VERSION, NOM_APPLICATION, chemins, extensions, journal, langues  # noqa: E402

# Le dossier d'extensions rejoint le chemin d'import AVANT tout le reste : c'est
# là que vivent torch et pyannote quand l'utilisateur a demandé la séparation
# des locuteurs depuis la version installée. Sans objet, et sans effet, quand le
# dossier n'existe pas.
extensions.activer()

# Modes de fond liés aux extensions. Ils précèdent la journalisation : ces
# processus sont lancés par l'application elle-même, ils ne doivent pas écrire
# dans le même fichier de journal que la fenêtre qui les a lancés.
if extensions.options_reconnues(sys.argv[1:]):
    sys.exit(extensions.principal_cli(sys.argv[1:]))

# Retour arrière du dossier de données vers « WhiScribe », pour une ancienne
# version (voir app/migration.py) : « scribouille-verifier.exe --revenir-whiscribe ».
if "--revenir-whiscribe" in sys.argv[1:]:
    from app import migration as _migration

    sys.exit(_migration.principal_cli())

# Détection lente du matériel (cartes, NPU, CUDA, périphériques d'OpenVINO),
# lancée par la fenêtre après son affichage : résultat dans « materiel.json ».
if "--detecter-materiel" in sys.argv[1:]:
    from app import materiel as _materiel

    sys.exit(_materiel.principal_detection())

# Banc d'essai de vitesse, en ligne de commande. « --banc-essai » est le
# processus travailleur d'un essai, lancé par le banc lui-même : comme pour les
# extensions, il n'écrit pas dans le journal de la fenêtre. Dans la version
# installée, c'est « scribouille-verifier.exe --banc » qu'il faut lancer : il a
# une console, l'exécutable fenêtré n'en a pas.
if "--banc" in sys.argv[1:] or "--banc-essai" in sys.argv[1:]:
    from app import banc as _banc

    if "--banc" in sys.argv[1:]:
        journal.demarrer()
    sys.exit(_banc.principal_cli(sys.argv[1:]))

# Campagne de mesure (voir `app/campagne.py`) : chaque réglage candidat sur un
# corpus public avec référence, puis verdict. « --campagne-essai » est le
# processus d'un réglage. Version installée : « scribouille-verifier.exe --campagne ».
if "--campagne" in sys.argv[1:] or "--campagne-essai" in sys.argv[1:]:
    from app import campagne as _campagne

    if "--campagne" in sys.argv[1:]:
        journal.demarrer()
    journal.silence_bibliotheques()
    sys.exit(_campagne.principal_cli(sys.argv[1:]))

# Épreuve d'endurance (voir `app/endurance.py`) : le réglage retenu, passé de
# nombreuses fois d'affilée. « --endurance-essai » est le processus qui enchaîne
# les passages. Version installée : « scribouille-verifier.exe --endurance ».
if "--endurance" in sys.argv[1:] or "--endurance-essai" in sys.argv[1:]:
    from app import endurance as _endurance

    if "--endurance" in sys.argv[1:]:
        journal.demarrer()
    journal.silence_bibliotheques()
    sys.exit(_endurance.principal_cli(sys.argv[1:]))

# Comparaison des deux moteurs sur un vrai fichier, en ligne de commande, même
# organisation que le banc : « --comparer-essai » est le processus d'un moteur.
# Version installée : « scribouille-verifier.exe --comparer FICHIER ».
if "--comparer" in sys.argv[1:] or "--comparer-essai" in sys.argv[1:]:
    from app import comparaison as _comparaison

    if "--comparer" in sys.argv[1:]:
        journal.demarrer()
    journal.silence_bibliotheques()
    sys.exit(_comparaison.principal_cli(sys.argv[1:]))

# Choix du réglage selon le poste (voir `app/adaptation.py`) : décrit le poste
# et propose un réglage ; « --appliquer » l'enregistre. Rien n'est téléchargé
# ni installé. Version installée : « scribouille-verifier.exe --reconnaitre ».
if "--reconnaitre" in sys.argv[1:]:
    from app import adaptation as _adaptation

    journal.demarrer()
    journal.silence_bibliotheques()
    sys.exit(_adaptation.principal_cli(sys.argv[1:]))

# Vocabulaire, format 2 (voir `app/apprentissage.py` et `app/mesure_vocabulaire.py`) :
# apprendre des propositions à partir de transcriptions relues, et mesurer ce
# que chaque étage gagne. Version installée : « scribouille-verifier.exe ... ».
if "--apprendre-vocabulaire" in sys.argv[1:]:
    from app import apprentissage as _apprentissage

    journal.demarrer()
    sys.exit(_apprentissage.principal_cli(sys.argv[1:]))

if "--mesurer-vocabulaire" in sys.argv[1:]:
    from app import mesure_vocabulaire as _mesure_vocabulaire

    journal.demarrer()
    journal.silence_bibliotheques()
    sys.exit(_mesure_vocabulaire.principal_cli(sys.argv[1:]))

journal.demarrer()
journal.purger()
journal.silence_bibliotheques()
if chemins.MIGRATION.get("etat") not in (None, "rien"):
    _m = chemins.MIGRATION
    journal.info("Données reprises de %s : %s entrée(s) déplacée(s), %s doublon(s) rangé(s) à part, état %s%s",
                 chemins.NOM_DOSSIER_ANCIEN, len(_m.get("deplaces") or []), len(_m.get("conflits") or []),
                 _m.get("etat"), (" : " + "; ".join(_m.get("restes") or [])) if _m.get("restes") else "")
    if _m.get("erreur"):
        journal.attention("Reprise des données de %s en échec : %s", chemins.NOM_DOSSIER_ANCIEN, _m["erreur"])


# ---------------------------------------------------------------------------
# Mode « --verifier » : bilan en ligne de commande, sans ouvrir de fenêtre
# ---------------------------------------------------------------------------

def verification() -> int:
    """
    Contrôle que l'installation est complète et utilisable.

    Sert à valider une version installée sans aucune interaction : imports,
    binaire FFmpeg, interface web présente, et écriture réelle dans les dossiers
    de travail. Renvoie 0 si tout est en ordre, 1 sinon.
    """
    lignes: list[str] = []
    tout_va_bien = True

    def resultat(reussi: bool, etiquette: str, detail: str = "") -> None:
        nonlocal tout_va_bien
        if not reussi:
            tout_va_bien = False
        marque = "OK   " if reussi else "ECHEC"
        lignes.append(f"  {marque}  {etiquette}" + (f" : {detail}" if detail else ""))

    lignes.append(f"{NOM_APPLICATION} v{VERSION}")
    lignes.append(f"  Mode          : {'version installée' if chemins.EST_GELE else 'sources'}")
    lignes.append(f"  Ressources    : {chemins.DOSSIER_RESSOURCES}")
    lignes.append(f"  Données       : {chemins.RACINE}")
    lignes.append(f"  Modèles       : {chemins.DOSSIER_MODELES}")
    lignes.append("")

    for module, etiquette in (
        ("webview", "interface de fenêtre (pywebview)"),
        ("faster_whisper", "moteur de transcription (faster-whisper)"),
        ("ctranslate2", "calcul (CTranslate2)"),
        ("numpy", "calcul numérique (numpy)"),
        ("tokenizers", "tokeniseur (tokenizers)"),
        ("huggingface_hub", "téléchargement des modèles (huggingface_hub)"),
        ("psutil", "détection du matériel (psutil)"),
    ):
        try:
            __import__(module)
            resultat(True, etiquette)
        except Exception as exc:
            resultat(False, etiquette, f"{type(exc).__name__}: {exc}")

    # Interface web : sans elle la fenêtre s'ouvrirait vide.
    page = chemins.DOSSIER_WEB / "index.html"
    resultat(page.is_file(), "interface web (web/index.html)", "" if page.is_file() else str(page))

    # Lexique du français courant : sans lui, le vocabulaire se replie sur les
    # seules fautes listées (garde-fou des corrections automatiques).
    try:
        from app import lexique as lexique_verif

        nombre = len(lexique_verif.mots_courants())
        resultat(nombre >= 30000, "lexique du français (vocabulaire)", f"{nombre} mots")
    except Exception as exc:
        resultat(False, "lexique du français (vocabulaire)", f"{type(exc).__name__}: {exc}")

    # Décodeur (FFmpeg par PyAV) : décodage réel de l'extrait livré.
    try:
        from app import audio as audio_verif, banc as banc_verif

        signal = audio_verif.decoder(banc_verif.EXTRAIT)
        resultat(signal.size > audio_verif.FREQUENCE, "décodeur audio (FFmpeg par PyAV)",
                 f"{audio_verif.version_decodeur()}, extrait de {signal.size / audio_verif.FREQUENCE:.1f} s")
    except Exception as exc:
        resultat(False, "décodeur audio (FFmpeg par PyAV)", f"{type(exc).__name__}: {exc}")

    # Écriture des dossiers de travail : c'est le point qui casse quand une
    # version installée essaie encore d'écrire dans son dossier de programme.
    try:
        chemins.assurer_dossiers()
        temoin = chemins.DOSSIER_LOGS / "verification.tmp"
        temoin.write_text("ok", encoding="utf-8")
        temoin.unlink(missing_ok=True)
        resultat(True, "écriture des journaux", str(chemins.DOSSIER_LOGS))
    except Exception as exc:
        resultat(False, "écriture des journaux", f"{type(exc).__name__}: {exc}")

    message = chemins.dossier_modeles_inscriptible(chemins.DOSSIER_MODELES)
    resultat(not message, "écriture du dossier des modèles", message or str(chemins.DOSSIER_MODELES))

    try:
        config_verif = __import__("app.config", fromlist=["charger"])
        config_verif.charger()
        config_verif.sauver(config_verif.charger())
        resultat(True, "lecture et écriture de la configuration", str(chemins.FICHIER_CONFIG))
    except Exception as exc:
        resultat(False, "configuration", f"{type(exc).__name__}: {exc}")

    # Détection matérielle et presets : ce sont les premiers appels de l'interface.
    try:
        from app import materiel as materiel_verif
        from app import presets as presets_verif

        mat = materiel_verif.detecter()
        presets_verif.recommandation(mat)
        resultat(True, "détection du matériel", f"{mat.fils_calcul} fils, {mat.ram_go:.0f} Go")
    except Exception as exc:
        resultat(False, "détection du matériel", f"{type(exc).__name__}: {exc}")

    # Séparation des locuteurs : facultative, elle ne fait donc jamais échouer le
    # bilan. La ligne dit ce qui est vraiment importable, pas ce qui a l'air posé :
    # un téléchargement interrompu laisse des dossiers qui ne s'importent pas.
    try:
        posee, detail = extensions.modules_importables()
    except Exception as exc:
        posee, detail = False, f"{type(exc).__name__}: {exc}"
    lignes.append(
        "  INFO   séparation des locuteurs : "
        + ("installée" if posee else "non installée")
        + (f" ({detail})" if detail else "")
        + (f" [{extensions.DOSSIER}]" if chemins.EST_GELE else "")
    )

    lignes.append("")
    lignes.append("  Bilan : tout est en place." if tout_va_bien
                  else "  Bilan : installation incomplète, voir les lignes ECHEC.")
    lignes.append("")

    texte = "\n".join(lignes)
    try:
        print(texte)
    except Exception:
        pass
    journal.info("Vérification :\n%s", texte)
    # Toujours un double du bilan sur disque : sous pythonw.exe, il n'y a pas de console.
    try:
        (chemins.DOSSIER_LOGS / "verification.txt").write_text(texte + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if tout_va_bien else 1


# L'exécutable « scribouille-verifier.exe » produit par PyInstaller n'a pas d'autre
# raison d'être : il déclenche la vérification même sans argument.
_NOM_EXECUTABLE = Path(sys.argv[0] if sys.argv else "").stem.lower()
if "--verifier" in sys.argv or _NOM_EXECUTABLE.endswith("verifier"):
    sys.exit(verification())


# ---------------------------------------------------------------------------
# Vérification des dépendances : message clair plutôt qu'un traceback
# ---------------------------------------------------------------------------

def _dependances_manquantes() -> list[str]:
    import importlib.util

    requis = {
        "webview": "pywebview",
        "faster_whisper": "faster-whisper",
        "numpy": "numpy",
    }
    return [
        paquet for module, paquet in requis.items()
        if importlib.util.find_spec(module) is None
    ]


def _abandonner(titre: str, message: str) -> None:
    journal.erreur("%s : %s", titre, message)
    try:
        import tkinter as tk
        from tkinter import messagebox

        racine = tk.Tk()
        racine.withdraw()
        messagebox.showerror(titre, message)
        racine.destroy()
    except Exception:
        print(f"{titre}\n\n{message}", file=sys.stdout)
    sys.exit(1)


_manquants = _dependances_manquantes()
if _manquants:
    _abandonner(
        NOM_APPLICATION,
        langues.t("app.dependances.titre")
        + "\n\n  "
        + "\n  ".join(_manquants)
        + "\n\n"
        + (
            langues.t("app.dependances.installee") if chemins.EST_GELE else
            langues.t("app.dependances.sources")
            + "\n\n  pip install " + " ".join(_manquants)
        ),
    )

import webview  # noqa: E402
from webview.dom import DOMEventHandler  # noqa: E402

from app import audio as audio_module  # noqa: E402
from app import config as config_module  # noqa: E402
from app import barre_taches, diarisation, donnees, ecoute, gabarit, lecture, maj  # noqa: E402
from app import banc, materiel, nommage, presets, reglage_machine, reprise, rythme, stockage  # noqa: E402
from app import surveillance, traitement, vocabulaire, vocabulaire_interface  # noqa: E402

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _json(valeur) -> str:
    return json.dumps(valeur, ensure_ascii=False)


class Passerelle:
    """Objet exposé à l'interface web sous le nom `pywebview.api`."""

    def __init__(self):
        self._fenetre = None
        #: Premier lancement : pas encore de configuration. La fenêtre propose
        #: alors un réglage pour ce poste (voir `app/adaptation.py`).
        self._premier_lancement = not chemins.FICHIER_CONFIG.exists()
        self.config = config_module.charger()
        # Rythme équilibré ou discret : les fils de CTranslate2 attendent sans
        # tourner à vide (OpenMP lit cette variable une fois, au premier calcul,
        # d'où sa place ici, avant tout chargement ; voir app/rythme.py).
        if rythme.normaliser(self.config.get("rythme")) != "vitesse":
            os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
        self._proposition: dict = {}
        #: Serveur local de l'audio pour la relecture (voir app/ecoute.py) :
        #: un seul fichier servi à la fois, démarré au premier besoin.
        self._ecoute = ecoute.Ecoute()
        # Glossaire et corrections d'une installation ancienne restés tels que
        # livrés, exemples fictifs actifs : remplacés par les modèles actuels.
        # Seulement à l'ouverture de la fenêtre, jamais depuis la ligne de
        # commande (banc, comparaison, campagne ne modifient rien).
        vocabulaire.retirer_exemples_anciens()
        # Matériel gardé du lancement précédent : la fenêtre s'ouvre sans
        # attendre les pilotes. La détection lente est relancée en arrière-plan
        # une fois la page chargée (`rafraichir_materiel_en_fond`).
        self.materiel, self._materiel_provisoire = materiel.detecter_au_demarrage()
        # Réglage de vitesse mesuré par le banc d'essai et accepté sur ce poste.
        self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
        self.file = traitement.FileTraitement(self.materiel)
        self._rappels = traitement.Rappels(
            etat=self._sur_etat,
            progression=self._sur_progression,
            termine=self._sur_fichier_termine,
            journal_ui=self._sur_journal,
            file_terminee=self._sur_file_terminee,
        )
        #: Processus d'installation de l'extension « locuteurs », ou None.
        #: Un seul à la fois, et l'interface le sait par `etat_locuteurs`.
        self._installation_locuteurs = None
        self._installation_annulee = False
        #: Installation du moteur OpenVINO, même mécanique, processus à part.
        self._installation_openvino = None
        self._installation_ov_annulee = False
        #: Banc d'essai en cours (un fil), et sa demande d'arrêt.
        self._banc = None
        self._arret_banc = threading.Event()
        self._comparaison = None
        self._arret_comparaison = threading.Event()
        #: Dossier surveillé. Le fil ne démarre que si l'option est active.
        self.surveillant = surveillance.Surveillant(
            sur_nouveaux=self._sur_fichiers_surveilles,
            signaler=self._sur_etat_surveillance,
        )

    # -- utilitaires -------------------------------------------------------

    def _js(self, appel: str) -> None:
        try:
            if self._fenetre is not None:
                self._fenetre.evaluate_js(appel)
        except Exception as exc:
            journal.debug("Appel JavaScript ignoré : %s", exc)

    def _fond(self, fonction) -> None:
        threading.Thread(target=fonction, daemon=True).start()

    # -- rappels de la file ------------------------------------------------

    def _sur_etat(self, identifiant: str, etat: str, message: str) -> None:
        self._js(f"onEtat({_json(identifiant)}, {_json(etat)}, {_json(message)})")

    def _sur_progression(self, identifiant: str, donnees: dict) -> None:
        self._js(f"onProgression({_json(identifiant)}, {_json(donnees)})")
        if self.config.get("barre_taches", True):
            barre_taches.progression(int(donnees.get("pct") or 0))

    def _sur_fichier_termine(self, identifiant: str, donnees: dict) -> None:
        self._js(f"onFichierTermine({_json(identifiant)}, {_json(donnees)})")
        if donnees.get("ok"):
            self.charger_historique()

    def _sur_journal(self, niveau: str, texte: str) -> None:
        self._js(f"onJournal({_json(niveau)}, {_json(texte)})")

    def _sur_file_terminee(self, donnees: dict) -> None:
        self._js(f"onFileTerminee({_json(donnees)})")
        self._clore_barre_taches(bool(donnees.get("echecs")))
        self._signaler_fin(donnees)

    def _signaler_fin(self, donnees: dict) -> None:
        """
        Fin de file, quand on regarde ailleurs : le titre de la fenêtre le dit
        et son bouton clignote dans la barre des tâches (rien de plus : une
        notification Windows demanderait d'enregistrer l'application auprès du
        système). Le titre revient à la normale au retour sur la fenêtre.
        """
        reussis = int(donnees.get("reussis") or 0)
        if not reussis or self._fenetre is None:
            return
        try:
            self._fenetre.set_title(langues.tn("app.titre_fin", reussis, nom=NOM_APPLICATION))
        except Exception as exc:
            journal.debug("Titre de fin non posé : %s", exc)
        barre_taches.clignoter()

    def titre_normal(self) -> None:
        """Appelé par l'interface quand la fenêtre reprend la main."""
        try:
            if self._fenetre is not None and self._fenetre.title != NOM_APPLICATION:
                self._fenetre.set_title(NOM_APPLICATION)
        except Exception as exc:
            journal.debug("Titre non rétabli : %s", exc)

    def _clore_barre_taches(self, en_echec: bool) -> None:
        """
        Fin de file : la barre disparaît. Un échec la laisse rouge quelques
        secondes, le temps d'être vue, puis elle s'efface comme le reste.
        """
        if not self.config.get("barre_taches", True):
            return
        if not en_echec:
            barre_taches.effacer()
            return
        barre_taches.erreur()
        threading.Timer(4.0, barre_taches.effacer).start()

    def _sur_etat_surveillance(self, niveau: str, texte: str) -> None:
        """
        Le dossier surveillé change d'état : dit dans le journal, et reflété
        par l'indicateur discret de l'en-tête.
        """
        self._sur_journal(niveau, texte)
        self._js(f"onSurveillance({_json(self.surveillant.etat())})")

    def _sur_fichiers_surveilles(self, chemins_trouves: list[str]) -> None:
        """Fichiers apparus dans le dossier surveillé, ajoutés à la file."""
        ajoutes = self.file.ajouter(list(chemins_trouves))
        if not ajoutes:
            return
        self._js(f"onFichiersAjoutes({_json(ajoutes)})")
        self._sur_journal("info", langues.tn("app.veille.ajoutes", len(ajoutes)))
        self.file.mesurer_durees(
            lambda identifiant, secondes, texte:
            self._js(f"onDuree({_json(identifiant)}, {secondes}, {_json(texte)})")
        )

    # -- état initial ------------------------------------------------------

    def etat_initial(self) -> dict:
        chemins.assurer_dossiers()
        glossaire = vocabulaire.resume_glossaire(self.config.get("langue", "fr"))
        manque_diarisation = diarisation.indisponibilite()
        # Une seule décision pour tout l'écran : la proposition du poste pilote
        # la pastille « conseillé ici », la fiche du matériel et l'encart, et
        # toutes les durées tiennent compte du rythme choisi, une seule fois.
        rythme_choisi = rythme.normaliser(self.config.get("rythme"))
        proposition = self._proposition_du_poste()

        return {
            "version": VERSION,
            "nom": NOM_APPLICATION,
            "config": self.config,
            "materiel": self.materiel.en_dict(),
            "recommandation": presets.recommandation(self.materiel, proposition, rythme_choisi),
            "presets": self._presets_affiches(rythme_choisi),
            "modeles_avances": presets.modeles_avances(),
            "langues_interface": langues.liste_langues(),
            "glossaire": {
                "contenu": vocabulaire.lire_glossaire(),
                "resume": glossaire,
            },
            "corrections": {
                "contenu": vocabulaire.lire_corrections(),
                "nb": glossaire.get("nb_corrections", 0),
                "erreurs": glossaire.get("erreurs_corrections", []),
            },
            "diarisation": {
                "disponible": not manque_diarisation,
                "indisponibilite": manque_diarisation,
                "jeton_present": diarisation.jeton_present(),
                "guide": diarisation.guide(),
                # Tout ce qu'il faut au panneau pour proposer l'installation :
                # taille annoncée, place disponible, état du dossier.
                "extension": self.etat_locuteurs(),
            },
            "reprises": self._reprises(),
            "surveillance": self.surveillant.etat(),
            "nommage": {
                "defaut": nommage.MOTIF_DEFAUT,
                "variables": [{"cle": c, "role": r} for c, r in nommage.VARIABLES],
            },
            "ffmpeg": audio_module.ffmpeg_present(),
            "journal": journal.nom_fichier(),
            "modeles": self.infos_modeles(),
            "version_installee": chemins.EST_GELE,
            "avertissements": self._avertissements(),
            "vitesse": self.etat_vitesse(),
            "rythme": self.etat_rythme(),
            "proposition": self._proposition_au_demarrage(proposition),
        }

    # -- durées du démarrage, notées au journal -----------------------------

    def _depuis_le_lancement(self) -> float:
        """Secondes écoulées depuis la création du processus (horloge du système)."""
        import time

        try:
            import psutil  # type: ignore

            return time.time() - psutil.Process().create_time()
        except Exception:
            return -1.0

    def fenetre_affichee(self) -> None:
        journal.info("Démarrage : fenêtre affichée à %.2f s du lancement", self._depuis_le_lancement())

    def interface_prete(self) -> None:
        """Appelé par l'interface une fois l'état initial dessiné : la fenêtre est utilisable."""
        journal.info("Démarrage : interface prête à %.2f s du lancement", self._depuis_le_lancement())

    # -- matériel rafraîchi après l'affichage --------------------------------

    def _etat_materiel(self) -> dict:
        """Ce qui, à l'écran, dépend du matériel : renvoyé quand il change."""
        rythme_choisi = rythme.normaliser(self.config.get("rythme"))
        proposition = self._proposition_du_poste()
        return {
            "materiel": self.materiel.en_dict(),
            "recommandation": presets.recommandation(self.materiel, proposition, rythme_choisi),
            "presets": self._presets_affiches(rythme_choisi),
            "avertissements": self._avertissements(),
            "vitesse": self.etat_vitesse(),
            "rythme": self.etat_rythme(),
            "proposition": self._proposition_au_demarrage(proposition),
        }

    def rafraichir_materiel_en_fond(self) -> None:
        """
        Détection lente dans un processus de fond, après l'affichage. Si elle
        trouve autre chose que ce qui était gardé (premier lancement, station
        d'accueil, pilote changé), l'écran est mis à jour ; pendant une
        transcription, le matériel en cours n'est pas remplacé (le résultat
        servira au lancement suivant).
        """
        def travail() -> None:
            try:
                rafraichir()
            except Exception as exc:
                journal.exception("Matériel non relu en arrière-plan", exc)

        def rafraichir() -> None:
            avant = materiel.signature(materiel.lire_cache())
            lent = materiel.rafraichir()
            if lent is None:
                return
            if materiel.signature(lent) == avant and not self._materiel_provisoire:
                return
            if self.file.occupee:
                journal.info("Matériel changé : pris en compte au prochain lancement")
                return
            from app import moteur_openvino

            ov = lent.get("openvino") or {}
            if bool(ov.get("installe")) == moteur_openvino.installe():
                moteur_openvino.amorcer(str(ov.get("version") or ""), list(ov.get("peripheriques") or []))
            self.materiel, self._materiel_provisoire = materiel.detecter_au_demarrage()
            self.file.materiel = self.materiel
            self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
            journal.info("Matériel relu en arrière-plan : %s", self.materiel.resume())
            self._js(f"onMateriel({_json(self._etat_materiel())})")

        self._fond(travail)

    def _presets_affiches(self, rythme_choisi: str) -> list[dict]:
        return [
            {
                "cle": p["cle"],
                "nom": presets.nom_preset(p["cle"]),
                "resume": presets.resume_preset(p["cle"]),
                "modele": moteur_nom_court(p["modele"]),
                "telechargement": langues.octets(p["telechargement_go"] * 1024 ** 3),
                "facteur": presets.facteur_temps_reel(p["cle"], self.materiel),
                "pour_une_heure": presets.pour_une_heure(p["cle"], self.materiel, rythme_choisi),
            }
            for p in presets.PRESETS.values()
        ]

    # -- rythme et réglage proposé pour le poste ----------------------------

    def etat_rythme(self) -> dict:
        """Rythme choisi, adaptation, et durée pour une heure dans chaque rythme."""
        choisi = rythme.normaliser(self.config.get("rythme"))
        preset_choisi = self.config.get("preset", "qualite")
        courant = __import__("app.energie", fromlist=["alimentation"]).alimentation()
        return {
            "choisi": choisi,
            "auto": bool(self.config.get("rythme_auto")),
            "batterie": bool(courant["batterie"] and not courant["secteur"]),
            "pour_une_heure": {
                nom: presets.pour_une_heure(preset_choisi, self.materiel, nom)
                for nom in rythme.RYTHMES},
        }

    def _proposition_du_poste(self) -> dict | None:
        """La proposition du poste, seule source du conseil affiché ; None si elle échoue."""
        try:
            from app import adaptation

            proposition = adaptation.proposition_du_poste(self.materiel)
            proposition["deja"] = adaptation.deja_en_place(proposition, self.config, self.materiel)
            return proposition
        except Exception as exc:
            journal.exception("Proposition du poste impossible", exc)
            return None

    def _proposition_au_demarrage(self, proposition: dict | None) -> dict | None:
        """
        La proposition ne s'affiche d'elle-même qu'au tout premier lancement, et
        tant qu'elle n'a été ni appliquée ni écartée ; sinon, sur demande. Tant
        que le matériel est provisoire (cartes pas encore lues), elle attend :
        elle arrive avec le matériel, quelques secondes plus tard.
        """
        if not self._premier_lancement or self._proposition.get("_vue") or self._materiel_provisoire:
            return None
        if not proposition or proposition.get("deja"):
            return None
        self._proposition = {**proposition, "_vue": True}
        return proposition

    def proposer_reglage(self) -> dict:
        """Bouton « Reconnaître ce poste » : la proposition, jamais appliquée d'office."""
        from app import adaptation

        if not self.file.occupee:
            # Le matériel a pu changer depuis l'ouverture (station d'accueil,
            # pilote réinstallé) : il est relu, sauf pendant une transcription,
            # par le processus de fond (OpenVINO compris), pas dans la fenêtre.
            try:
                lent = materiel.rafraichir()
                if lent is not None:
                    from app import moteur_openvino

                    ov = lent.get("openvino") or {}
                    if bool(ov.get("installe")) == moteur_openvino.installe():
                        moteur_openvino.amorcer(str(ov.get("version") or ""),
                                                list(ov.get("peripheriques") or []))
                    self.materiel, self._materiel_provisoire = materiel.detecter_au_demarrage()
                    self.file.materiel = self.materiel
            except Exception as exc:
                journal.exception("Nouvelle détection du matériel impossible", exc)
            self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
        proposition = adaptation.proposition_du_poste(self.materiel)
        proposition["deja"] = adaptation.deja_en_place(proposition, self.config, self.materiel)
        self._proposition = {**proposition, "_vue": True}
        journal.info("Proposition du poste : %s (%s)", proposition["regle"], proposition["source"])
        return proposition

    def appliquer_proposition(self) -> dict:
        from app import adaptation

        if self.file.occupee:
            return {"ok": False, "message": langues.t("app.banc.file_occupee")}
        proposition = self._proposition or adaptation.proposition_du_poste(self.materiel)
        adaptation.appliquer(self.config, self.materiel, proposition)
        config_module.sauver(self.config)
        self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
        return {"ok": True, "message": langues.t("adapt.applique", phrase=proposition["phrase"])}

    def ecarter_proposition(self) -> dict:
        self.config["proposition_ecartee"] = __import__(
            "app.calibration", fromlist=["signature_machine"]).signature_machine(self.materiel)
        config_module.sauver(self.config)
        return {"ok": True}

    def _avertissements(self) -> list[str]:
        """Garde-fous matériels, plus l'annonce du téléchargement à venir."""
        messages = presets.avertissements(
            self.config.get("preset", "qualite"), self.materiel,
            bool(self.config.get("diarisation")),
            self.config.get("modele_avance", "") if self.config.get("mode_avance") else "",
        )
        annonce = self._annonce_telechargement()
        if annonce:
            messages.insert(0, annonce)
        # Dit AVANT de lancer, là où l'on regarde les réglages, et pas seulement
        # dans le journal une fois la file partie.
        if self.config.get("diarisation") and not diarisation.effective(True):
            messages.append(langues.t("app.diar.non_installee"))
        return messages

    def _modele_courant(self) -> str:
        """
        Modèle que la prochaine file va charger : celui du preset, ou son
        équivalent au format d'OpenVINO quand ce moteur est retenu sur le poste.
        """
        avance = self.config.get("modele_avance", "") if self.config.get("mode_avance") else ""
        modele = presets.modele_du_preset(self.config.get("preset", "qualite"), avance)
        forcer = bool(self.config.get("forcer_processeur")) and bool(self.config.get("mode_avance"))
        if self.materiel.moteur == "openvino" and not forcer and presets.depot_openvino(modele):
            return presets.depot_openvino(modele)
        return modele

    def _annonce_telechargement(self) -> str:
        """
        Phrase affichée quand le modèle choisi n'est pas encore utilisable.

        C'est le seul moment où l'application a besoin d'Internet : il faut le
        dire avant, avec la taille, et pas au milieu d'une transcription. Un
        modèle laissé incomplet par une coupure a sa propre phrase : ce n'est
        pas un premier usage, et l'utilisateur n'a rien à faire de particulier.
        """
        from app import moteur

        modele = self._modele_courant()
        try:
            etat = moteur.etat_modele(modele)["etat"]
        except Exception:
            return ""
        if etat == "complet":
            return ""
        cle = ("app.telechargement_reparation" if etat == "incomplet"
               else "app.telechargement_annonce")
        return langues.t(
            cle,
            modele=moteur.nom_court(modele),
            taille=moteur.taille_annoncee(modele),
            dossier=chemins.DOSSIER_MODELES,
        )

    # -- dossier des modèles ------------------------------------------------

    def infos_modeles(self) -> dict:
        """État du dossier des modèles, pour le panneau des réglages."""
        dossier = chemins.DOSSIER_MODELES
        from app import moteur

        etat_presets = []
        incomplets = []
        for p in presets.PRESETS.values():
            try:
                etat = moteur.etat_modele(p["modele"])["etat"]
            except Exception:
                etat = "absent"
            nom_modele = moteur.nom_court(p["modele"])
            if etat == "incomplet":
                incomplets.append(nom_modele)
            etat_presets.append({
                "cle": p["cle"],
                "nom": presets.nom_preset(p["cle"]),
                "modele": nom_modele,
                "taille": langues.octets(p["telechargement_go"] * 1024 ** 3),
                # Un modèle incomplet n'est pas « présent » : le compter comme
                # tel ferait croire à l'utilisateur qu'il est prêt à servir.
                "present": etat == "complet",
                "etat": etat,
            })

        return {
            "incomplets": incomplets,
            "dossier": str(dossier),
            "defaut": str(chemins.dossier_modeles_defaut()),
            "personnalise": chemins.FICHIER_CHOIX_MODELES.exists(),
            "occupe": langues.octets(chemins.taille_dossier_go(dossier) * 1024 ** 3),
            "libre": langues.octets(chemins.espace_libre_go(dossier) * 1024 ** 3),
            "presets": etat_presets,
        }

    def choisir_dossier_modeles(self) -> None:
        self._fond(self._dialogue_dossier_modeles)

    def _dialogue_dossier_modeles(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.FOLDER_DIALOG, directory=str(chemins.DOSSIER_MODELES),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onDossierModeles({_json(self.definir_dossier_modeles(str(chemin)))})")

    def definir_dossier_modeles(self, chemin: str) -> dict:
        """
        Change l'emplacement des modèles. Les modèles déjà téléchargés ne sont
        pas déplacés : ils seront simplement retéléchargés au besoin, et l'ancien
        dossier reste sur le disque, à l'utilisateur de le vider s'il le souhaite.
        """
        texte = (chemin or "").strip()
        ancien = str(chemins.DOSSIER_MODELES)

        if texte:
            probleme = chemins.dossier_modeles_inscriptible(texte)
            if probleme:
                return {"ok": False, "message": probleme, "modeles": self.infos_modeles()}

        nouveau = chemins.definir_dossier_modeles(texte, memoriser=True)
        chemins.assurer_dossiers()
        journal.info("Dossier des modèles : %s (était %s)", nouveau, ancien)

        message = langues.t("app.modeles.range", dossier=nouveau)
        if str(nouveau) != ancien and chemins.taille_dossier_go(ancien) > 0.05:
            message += langues.t("app.modeles.ancien", ancien=ancien)
        return {
            "ok": True,
            "message": message,
            "modeles": self.infos_modeles(),
            "avertissements": self._avertissements(),
        }

    def ouvrir_dossier_modeles(self) -> None:
        chemins.assurer_dossiers()
        self.ouvrir(str(chemins.DOSSIER_MODELES))

    # -- espace occupé ------------------------------------------------------

    def mesurer_stockage(self) -> None:
        """
        Mesure l'espace occupé en tâche de fond.

        Un dossier de modèles de trois gigaoctets se parcourt en centaines de
        milliers d'appels système : le faire dans le fil de l'interface figerait
        la fenêtre. Le résultat arrive par `onStockage`.
        """
        def travail() -> None:
            try:
                mesure = stockage.mesurer()
            except Exception as exc:
                journal.exception("Mesure de l'espace occupé en échec", exc)
                mesure = {"postes": [], "total_texte": "--", "erreur": True}
            self._js(f"onStockage({_json(mesure)})")

        self._fond(travail)

    # -- nom des fichiers produits -----------------------------------------

    def apercu_motif(self, motif: str) -> dict:
        """Aperçu en direct sous le champ des réglages."""
        return nommage.apercu(motif or "")

    def enregistrer_motif(self, motif: str) -> dict:
        """
        Enregistre le motif de nommage après validation.

        Un motif refusé n'est pas écrit : l'ancien réglage reste en place, et le
        message dit pourquoi.
        """
        texte = (motif or "").strip()
        probleme = nommage.valider(texte)
        if probleme:
            return {"ok": False, "message": probleme, "motif": self.config.get("motif_sortie", "")}
        self.config["motif_sortie"] = texte
        config_module.sauver(self.config)
        journal.info("Nom des fichiers produits : %s", texte or nommage.MOTIF_DEFAUT)
        return {
            "ok": True,
            "motif": texte,
            "apercu": nommage.apercu(texte),
            "message": langues.t(
                "app.motif.defaut" if not texte else "app.motif.enregistre"),
        }

    # -- dossier surveillé --------------------------------------------------

    def configurer_surveillance(self, dossier: str, actif: bool) -> dict:
        """Applique le réglage du dossier surveillé et l'enregistre."""
        chemin = (dossier or "").strip()
        actif = bool(actif)
        if actif and not chemin:
            return {
                **self.surveillant.etat(),
                "ok": False,
                "message": langues.t("app.veille.choisir"),
            }
        if actif and not Path(chemin).expanduser().is_dir():
            return {
                **self.surveillant.etat(),
                "ok": False,
                "message": langues.t("app.veille.pas_accessible", chemin=chemin),
            }

        self.config["dossier_surveille"] = chemin
        self.config["surveillance"] = actif
        config_module.sauver(self.config)
        etat = self.surveillant.configurer(chemin, actif)
        journal.info("Surveillance %s : %s", "active" if actif else "coupée", chemin or "--")
        return {
            **etat,
            "ok": True,
            "message": (
                langues.t("app.veille.active", chemin=chemin) if actif
                else langues.t("app.veille.coupee")
            ),
        }

    def choisir_dossier_surveille(self) -> None:
        self._fond(self._dialogue_dossier_surveille)

    def _dialogue_dossier_surveille(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.config.get("dossier_surveille", "") or str(Path.home()),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            resultat = None
        if not resultat:
            # Sélection annulée : l'interface doit le savoir pour ne pas laisser
            # une bascule allumée sur un dossier qui n'existe pas.
            self._js('onDossierSurveille("")')
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onDossierSurveille({_json(str(chemin))})")

    def oublier_fichiers_surveilles(self) -> dict:
        """Vide la mémoire : tout le contenu du dossier repartira en file."""
        etat = self.surveillant.oublier_tout()
        journal.info("Mémoire du dossier surveillé vidée.")
        return {
            **etat,
            "ok": True,
            "message": langues.t("app.veille.memoire_videe"),
        }

    def ouvrir_dossier_surveille(self) -> None:
        self.ouvrir(self.config.get("dossier_surveille", ""))

    # -- vérification de mise à jour ---------------------------------------

    def verifier_maj(self, forcer: bool = False) -> None:
        """
        Interroge les Releases du dépôt, uniquement si l'option est active.

        C'est ici, et nulle part ailleurs, que se garantit la promesse : option
        coupée, aucun appel réseau sortant n'est émis par l'application.
        """
        if not self.config.get("maj_verifier"):
            return

        def travail() -> None:
            try:
                resultat = maj.verifier(VERSION, forcer=bool(forcer))
            except Exception as exc:
                journal.exception("Vérification de mise à jour en échec", exc)
                return
            if resultat.get("disponible"):
                self._js(f"onMiseAJour({_json(resultat)})")

        self._fond(travail)

    def verifier_maj_manuel(self) -> dict:
        """
        Vérification demandée à la main depuis la fenêtre d'aide.

        Deux différences avec `verifier_maj`, toutes deux voulues :

        - elle ne consulte **pas** le réglage d'opt-in. Celui-ci ne gouverne que
          la vérification passive du démarrage ; ici l'utilisateur clique, il
          demande donc explicitement cet unique appel à GitHub, et la fenêtre
          d'aide le lui dit noir sur blanc juste sous le bouton ;
        - elle ignore la garde des 24 heures (`forcer=True`), sans quoi un clic
          répondrait « repassez demain », ce qui n'aurait aucun sens.

        Elle renvoie son résultat directement, l'interface l'attend. Si une
        version plus récente sort de là, le bandeau du haut est levé au passage.
        """
        try:
            resultat = maj.verifier(VERSION, forcer=True)
        except Exception as exc:
            journal.exception("Vérification de mise à jour en échec", exc)
            resultat = {"disponible": False, "raison": "reseau"}
        if resultat.get("disponible"):
            self._js(f"onMiseAJour({_json(resultat)})")
        return {**resultat, "version_installee": VERSION}

    # -- réglages ----------------------------------------------------------

    def sauver_config(self, partiel: dict) -> dict:
        for cle, valeur in (partiel or {}).items():
            if cle not in config_module.DEFAUTS:
                continue
            if isinstance(self.config.get(cle), dict) and isinstance(valeur, dict):
                self.config[cle].update(valeur)
            else:
                self.config[cle] = valeur
        # La langue d'interface prend effet tout de suite, y compris pour les
        # textes que Python fabrique : l'interface redemande son état juste après.
        if "langue_interface" in (partiel or {}):
            retenue = langues.definir(self.config.get("langue_interface"))
            self.config["langue_interface"] = retenue
            journal.info("Langue d'interface : %s", retenue)
        config_module.sauver(self.config)
        return {
            "config": self.config,
            "avertissements": self._avertissements(),
        }

    def sauver_glossaire(self, contenu: str) -> dict:
        vocabulaire.ecrire_glossaire(contenu or "")
        resume = vocabulaire.construire_amorce(
            contenu or "", langue=self.config.get("langue", "fr"))
        journal.info("Glossaire enregistré : %s termes", resume["nb_termes"])
        return resume

    def sauver_corrections(self, contenu: str) -> dict:
        vocabulaire.ecrire_corrections(contenu or "")
        regles, erreurs = vocabulaire.analyser_corrections(contenu or "")
        journal.info("Corrections enregistrées : %s règles, %s erreurs", len(regles), len(erreurs))
        return {"nb": len(regles), "erreurs": erreurs}

    def enregistrer_jeton(self, valeur: str) -> dict:
        valeur = (valeur or "").strip()
        if valeur and not valeur.startswith("hf_"):
            return {"ok": False, "message": langues.t("app.jeton.prefixe")}
        diarisation.enregistrer_jeton(valeur)
        if not valeur:
            return {"ok": True, "message": langues.t("app.jeton.efface")}
        return {"ok": True, "message": langues.t("app.jeton.enregistre")}

    # -- extension « séparation des locuteurs » ----------------------------
    #
    # Toute la logique vit dans `app/extensions.py`. Ici, on ne fait que lancer
    # le processus de fond, lire ses lignes et les retransmettre à l'interface,
    # traduites. L'application reste utilisable pendant le téléchargement :
    # rien de ce qui suit ne bloque le fil de la fenêtre.

    def etat_locuteurs(self) -> dict:
        etat = extensions.etat()
        etat["en_cours"] = self._installation_locuteurs is not None
        etat["diarisation_prete"] = diarisation.disponible()
        etat["jeton_present"] = diarisation.jeton_present()
        return etat

    def installer_locuteurs(self) -> dict:
        """
        Lance l'installation. La confirmation et l'annonce de la taille ont
        déjà eu lieu côté interface : ici, on revérifie tout de même la place
        disponible, parce qu'un disque se remplit entre deux clics.
        """
        if self._installation_locuteurs is not None:
            return {"ok": False, "message": langues.t("ext.deja_en_cours")}

        assez, libre, requis = extensions.espace_suffisant()
        if not assez:
            return {
                "ok": False,
                "message": langues.t(
                    "ext.espace_insuffisant",
                    libre=langues.nombre(libre, 1), requis=langues.nombre(requis, 1),
                ),
            }

        commande, dossier = extensions.commande_travailleur(["--installer-locuteurs"])
        journal.info("Installation de la séparation des locuteurs : %s", " ".join(commande))
        try:
            processus = subprocess.Popen(
                commande, cwd=dossier,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=_SANS_FENETRE,
            )
        except OSError as exc:
            journal.exception("Processus d'installation impossible à lancer", exc)
            return {"ok": False, "message": langues.t("ext.lancement_impossible")}

        self._installation_locuteurs = processus
        self._installation_annulee = False
        self._fond(lambda: self._suivre_installation(processus))
        return {"ok": True}

    def annuler_installation_locuteurs(self) -> dict:
        processus = self._installation_locuteurs
        if processus is None:
            return {"ok": False}
        self._installation_annulee = True
        try:
            if sys.platform == "win32":
                # Toute la descendance, pas seulement le processus lancé :
                # depuis les sources, le travailleur lance lui-même un pip.
                # « terminate » seul le laisserait orphelin, à télécharger
                # dans le vide.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(processus.pid)],
                    capture_output=True, creationflags=_SANS_FENETRE, timeout=30,
                )
            else:
                processus.terminate()
        except Exception as exc:
            journal.debug("Arrêt du processus d'installation : %s", exc)
        journal.info("Installation de la séparation des locuteurs annulée")
        return {"ok": True}

    # -- vitesse de cette machine : OpenVINO et banc d'essai ----------------
    #
    # Le moteur OpenVINO s'installe comme la séparation des locuteurs (même
    # processus de fond, même protocole de lignes), dans son propre dossier.
    # Le banc d'essai tourne dans un fil, chaque essai dans un processus.

    def etat_vitesse(self) -> dict:
        from app import extensions as ext_module, moteur_openvino

        ov = ext_module.etat_openvino()
        ov["en_cours"] = self._installation_openvino is not None
        ov["version"] = moteur_openvino.version() if ov["installee"] else ""
        # Rien d'affiché tant que la détection de fond ne les a pas confirmés.
        ov["peripheriques"] = (moteur_openvino.peripheriques_disponibles()
                               if ov["installee"] and moteur_openvino.peripheriques_confirmes() else [])
        ov["utile"] = bool(self.materiel.a_graphique_intel()
                           or any("intel" in n.nom.lower() for n in self.materiel.npus)
                           or "intel" in (self.materiel.cpu_nom or "").lower()
                           or ov["installee"])
        reglage = reglage_machine.lire(self.config, self.materiel)
        conseil = banc.dernier_conseil()
        return {
            "openvino": ov,
            "reglage": reglage,
            "effet": {k: v for k, v in (self._effet_reglage or {}).items()
                      if k in ("indisponible", "plantage")},
            "resume_reglage": self._resume_reglage(reglage),
            "banc_en_cours": self._banc is not None,
            "conseil": conseil,
            "resume_conseil": self._resume_reglage(conseil) if conseil else "",
            "rapport": banc.dernier_rapport() if conseil else "",
            "manquants": [
                {"modele": moteur_nom_court(m), "taille": langues.octets(o)}
                for m, o in banc.modeles_manquants()
            ],
            "npu": any(True for _ in self.materiel.npus),
        }

    def _resume_reglage(self, reglage: dict) -> str:
        if not reglage:
            return langues.t("vitesse.automatique", fils=self.materiel.fils_automatiques)
        if reglage.get("moteur") == "openvino":
            from app import moteur_openvino

            return langues.t("vitesse.reglage_ov", peripherique=moteur_openvino.nom_peripherique(
                str(reglage.get("peripherique") or "CPU")))
        lot = int(reglage.get("lot") or 0)
        return langues.t("vitesse.reglage_ct2", fils=reglage.get("fils") or self.materiel.fils_automatiques,
                         lots=langues.t("banc.lots", n=lot) if lot else langues.t("banc.un_a_un"))

    def installer_openvino(self) -> dict:
        from app import extensions as ext_module

        if self._installation_openvino is not None:
            return {"ok": False, "message": langues.t("ext.deja_en_cours")}
        libre = chemins.espace_libre_go(chemins.RACINE)
        if libre and libre < ext_module.ESPACE_REQUIS_OPENVINO_GO:
            return {"ok": False, "message": langues.t(
                "ext.espace_insuffisant", libre=langues.nombre(libre, 1),
                requis=langues.nombre(ext_module.ESPACE_REQUIS_OPENVINO_GO, 1))}
        commande, dossier = ext_module.commande_travailleur(["--installer-openvino"])
        journal.info("Installation d'OpenVINO : %s", " ".join(commande))
        try:
            processus = subprocess.Popen(
                commande, cwd=dossier, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=_SANS_FENETRE,
            )
        except OSError as exc:
            journal.exception("Processus d'installation impossible à lancer", exc)
            return {"ok": False, "message": langues.t("ext.lancement_impossible")}
        self._installation_openvino = processus
        self._installation_ov_annulee = False
        self._fond(lambda: self._suivre_installation(processus, "openvino"))
        return {"ok": True}

    def annuler_installation_openvino(self) -> dict:
        processus = self._installation_openvino
        if processus is None:
            return {"ok": False}
        self._installation_ov_annulee = True
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(processus.pid)],
                           capture_output=True, creationflags=_SANS_FENETRE, timeout=30)
        except Exception as exc:
            journal.debug("Arrêt du processus d'installation : %s", exc)
        return {"ok": True}

    def _terminer_installation_openvino(self, code: int) -> None:
        from app import extensions as ext_module, moteur_openvino

        def conclure(charge: dict) -> None:
            charge["vitesse"] = self.etat_vitesse()
            self._js("onFinExtensionOpenvino(" + _json(charge) + ")")

        if self._installation_ov_annulee:
            conclure({"etat": "annulee", "message": langues.t("ext.annulee")})
            return
        if code != 0:
            journal.erreur("Installation d'OpenVINO en échec (code %s)", code)
            conclure({"etat": "echec", "message": langues.t("ov.installation_echec", dossier=str(
                ext_module.DOSSIER_HORS_LIGNE))})
            return
        commande, dossier = ext_module.commande_travailleur(["--verifier-openvino"])
        try:
            sortie = subprocess.run(commande, cwd=dossier, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=300,
                                    creationflags=_SANS_FENETRE)
            reussi = sortie.returncode == 0
            detail = (sortie.stdout or "").strip().splitlines()[-1:] or [""]
        except Exception as exc:
            reussi, detail = False, [f"{type(exc).__name__}: {exc}"]
        if not reussi:
            journal.erreur("OpenVINO posé mais inutilisable : %s", detail[0])
            conclure({"etat": "echec", "message": langues.t("ext.verification_ko")})
            return
        ext_module.activer()
        import importlib

        importlib.invalidate_caches()
        moteur_openvino.peripheriques_disponibles(forcer=True)
        self.rafraichir_materiel_en_fond()
        journal.info("OpenVINO installé : %s", detail[0])
        conclure({"etat": "installee", "message": langues.t("ov.installe")})

    def retirer_openvino(self) -> dict:
        from app import extensions as ext_module

        if self._installation_openvino is not None:
            return {"ok": False, "message": langues.t("ext.deja_en_cours")}
        if not chemins.EST_GELE:
            return {"ok": False, "message": langues.t("ov.retrait_sources")}
        if self.materiel.moteur == "openvino":
            reglage_machine.oublier(self.config, self.materiel)
            config_module.sauver(self.config)
        resultat = ext_module.retirer(ext_module.DOSSIER_OPENVINO, vider_cache=False)
        if not resultat["ok"]:
            # Les DLL d'OpenVINO déjà chargées par ce processus restent
            # verrouillées jusqu'à la fermeture : on le dit.
            journal.erreur("Retrait d'OpenVINO en échec : %s", resultat["message_technique"])
            return {"ok": False, "message": langues.t("ov.retrait_echec")}
        return {"ok": True, "message": langues.t(
            "ext.retiree", taille=langues.nombre(resultat["libere_go"], 2)),
            "vitesse": self.etat_vitesse()}

    def lancer_banc(self, telecharger: bool = False, npu: bool = False) -> dict:
        if self._banc is not None or self._comparaison is not None:
            return {"ok": False, "message": langues.t("app.banc.en_cours")}
        if self.file.occupee:
            return {"ok": False, "message": langues.t("app.banc.file_occupee")}
        self._arret_banc.clear()

        def travail() -> None:
            try:
                resultat = banc.executer(
                    telecharger=bool(telecharger), npu=bool(npu),
                    rappel=lambda etape: self._js(f"onBanc({_json(etape)})"),
                    interrompu=self._arret_banc.is_set)
                charge = {"ok": True, "rapport": resultat["rapport"],
                          "fichier": resultat["fichier"], "annule": resultat["annule"],
                          "conseil": resultat["reglage"]}
            except Exception as exc:
                incident = journal.formater_incident(exc, "banc d'essai")
                charge = {"ok": False, "message": incident["titre"]}
            self._banc = None
            charge["vitesse"] = self.etat_vitesse()
            self._js(f"onFinBanc({_json(charge)})")

        self._banc = threading.Thread(target=travail, daemon=True)
        self._banc.start()
        return {"ok": True}

    def arreter_banc(self) -> dict:
        self._arret_banc.set()
        return {"ok": True}

    # -- comparaison des deux moteurs sur un enregistrement -----------------
    #
    # Même organisation que le banc : un fil, chaque moteur dans son processus.
    # La page côte à côte contient le texte et reste sur le poste ; le rapport
    # de chiffres, lui, peut être transmis.

    def choisir_fichier_comparaison(self, nature: str = "audio") -> None:
        self._fond(lambda: self._dialogue_comparaison(nature))

    def _dialogue_comparaison(self, nature: str) -> None:
        if nature == "reference":
            types = (langues.t("app.comp.dialogue_reference"), langues.t("arch.tous_fichiers"))
        else:
            extensions = ";".join(f"*{e}" for e in sorted(audio_module.EXTENSIONS_AUDIO))
            types = (langues.t("app.dialogue.audio", extensions=extensions),
                     langues.t("arch.tous_fichiers"))
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.OPEN_DIALOG, directory=self._dossier_de_depart(), file_types=types)
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        charge = {"nature": nature, "chemin": str(chemin), "nom": Path(str(chemin)).name}
        self._js(f"onFichierComparaison({_json(charge)})")

    def lancer_comparaison(self, fichier: str, reference: str = "", debut: str = "",
                           duree_minutes: float = 10) -> dict:
        from app import comparaison

        if self._banc is not None or self._comparaison is not None:
            return {"ok": False, "message": langues.t("app.banc.en_cours")}
        if self.file.occupee:
            return {"ok": False, "message": langues.t("app.banc.file_occupee")}
        if not fichier or not Path(fichier).is_file():
            return {"ok": False, "message": langues.t("app.comp.fichier_absent")}
        try:
            debut_s = comparaison.lire_duree(debut or "0")
            duree_s = max(0.0, float(duree_minutes or 0) * 60)
        except ValueError:
            return {"ok": False, "message": langues.t("app.comp.debut_illisible")}
        self._arret_comparaison.clear()

        def travail() -> None:
            try:
                resultat = comparaison.executer(
                    fichier, debut=debut_s, duree=duree_s, reference=reference or "",
                    rappel=lambda etape: self._js(f"onComparaison({_json(etape)})"),
                    interrompu=self._arret_comparaison.is_set)
                charge = {"ok": resultat["ok"], "rapport": resultat["rapport"],
                          "page": resultat["page"], "fichier": resultat["rapport_fichier"],
                          "annule": self._arret_comparaison.is_set()}
            except Exception as exc:
                incident = journal.formater_incident(exc, "comparaison des moteurs")
                charge = {"ok": False, "message": incident["titre"]}
            self._comparaison = None
            self._js(f"onFinComparaison({_json(charge)})")

        self._comparaison = threading.Thread(target=travail, daemon=True)
        self._comparaison.start()
        return {"ok": True}

    def arreter_comparaison(self) -> dict:
        self._arret_comparaison.set()
        return {"ok": True}

    def appliquer_conseil_banc(self) -> dict:
        conseil = banc.dernier_conseil()
        if not conseil:
            return {"ok": False, "message": langues.t("vitesse.aucun_conseil")}
        reglage_machine.enregistrer(self.config, self.materiel, conseil)
        banc.enregistrer_mesures(self.materiel, conseil)
        config_module.sauver(self.config)
        self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
        journal.info("Réglage du banc appliqué : %s", self._resume_reglage(conseil))
        return {"ok": True, "message": langues.t("vitesse.applique",
                                                 reglage=self._resume_reglage(conseil))}

    def revenir_reglage_automatique(self) -> dict:
        reglage_machine.oublier(self.config, self.materiel)
        config_module.sauver(self.config)
        self._effet_reglage = {}
        journal.info("Réglage de vitesse : retour au choix automatique")
        return {"ok": True, "message": langues.t("vitesse.retour_auto")}

    def _suivre_installation(self, processus, extension: str = "locuteurs") -> None:
        """
        Lit les lignes du processus de fond et les traduit pour l'interface.

        Le protocole est celui de `app/extensions.py` : des lignes préfixées,
        volontairement pauvres. Tout le reste est de la sortie brute de pip,
        qui part au journal et nulle part ailleurs.
        """
        try:
            for ligne in processus.stdout or []:
                ligne = ligne.rstrip()
                if not ligne.startswith(extensions.MARQUE):
                    if ligne:
                        journal.debug("pip : %s", ligne)
                    continue
                _, _, reste = ligne.partition(extensions.MARQUE)
                evenement, _, detail = reste.partition("|")
                rappel = "onExtensionOpenvino" if extension == "openvino" else "onExtensionLocuteurs"
                self._js(f"{rappel}({_json(self._traduire_etape(evenement, detail))})")
        except Exception as exc:
            journal.exception("Lecture du processus d'installation interrompue", exc)

        code = processus.wait()
        if extension == "openvino":
            self._installation_openvino = None
            self._terminer_installation_openvino(code)
            return
        self._installation_locuteurs = None
        self._terminer_installation(code)

    def _traduire_etape(self, evenement: str, detail: str) -> dict:
        """Fabrique le message affiché, dans la langue de l'interface."""
        morceaux = detail.split("|")
        if evenement == "debut":
            return {"phase": "debut", "message": langues.t("ext.etape.preparation"), "pct": 0}
        if evenement == "lot":
            numero = morceaux[0] if morceaux else "1"
            total = morceaux[1] if len(morceaux) > 1 else "1"
            nom = morceaux[2] if len(morceaux) > 2 else ""
            cle = {"locuteurs": "ext.lot.locuteurs",
                   "openvino": "ext.lot.openvino"}.get(nom, "ext.lot.paquets")
            # « Etape 1 sur 1 » ne dirait rien a personne : quand il n'y a
            # qu'un lot, on annonce simplement ce qui s'installe.
            if total == "1":
                message = langues.t("ext.etape.installation", nom=langues.t(cle))
            else:
                message = langues.t("ext.etape.lot", numero=numero, total=total,
                                    nom=langues.t(cle))
            return {"phase": "lot", "lot": numero, "lots": total, "message": message}
        if evenement == "paquet":
            return {"phase": "paquet", "paquet": detail,
                    "message": langues.t("ext.etape.paquet", paquet=detail)}
        if evenement == "octets":
            paquet = morceaux[0] if morceaux else ""
            pct = int(morceaux[1]) if len(morceaux) > 1 and morceaux[1].isdigit() else 0
            recu = int(morceaux[2]) if len(morceaux) > 2 and morceaux[2].isdigit() else 0
            total = int(morceaux[3]) if len(morceaux) > 3 and morceaux[3].isdigit() else 0
            return {
                "phase": "octets", "pct": pct, "paquet": paquet,
                "message": langues.t(
                    "ext.etape.telechargement", paquet=paquet,
                    recu=langues.octets(recu), total=langues.octets(total),
                ),
            }
        if evenement == "pose":
            return {"phase": "pose", "message": langues.t("ext.etape.pose")}
        if evenement == "detail":
            journal.attention("Installation des locuteurs : %s", detail)
            return {"phase": "detail", "message": detail}
        if evenement == "echec":
            return {"phase": "detail", "message": langues.t("ext.etape.echec_lot")}
        return {"phase": evenement, "message": ""}

    def _terminer_installation(self, code: int) -> None:
        """
        Conclut : vérification réelle de l'import, puis activation à chaud.

        La vérification tourne dans un processus neuf, et pas ici. pip n'aime
        pas qu'on importe dans la foulée ce qu'il vient de poser, et un torch
        chargé dans le processus de la fenêtre ne se déchargerait plus.
        """
        def conclure(charge: dict) -> None:
            self._js("onFinExtensionLocuteurs(" + _json(charge) + ")")

        if self._installation_annulee:
            conclure({"etat": "annulee", "message": langues.t("ext.annulee")})
            return

        if code != 0:
            journal.erreur("Installation de la séparation des locuteurs en échec (code %s)", code)
            conclure({"etat": "echec", "message": langues.t("ext.echec")})
            return

        reussi, detail = self._verifier_locuteurs_hors_processus()
        if not reussi:
            journal.erreur("Extension posée mais inutilisable : %s", detail)
            conclure({"etat": "echec", "message": langues.t("ext.verification_ko")})
            return

        # Activation à chaud : le dossier rejoint le chemin d'import, et
        # `diarisation.disponible()` le voit immédiatement. Rien n'a encore
        # importé torch dans ce processus, c'est ce qui rend la chose possible.
        extensions.activer()
        import importlib

        importlib.invalidate_caches()
        chaud = diarisation.disponible()
        journal.info("Séparation des locuteurs installée (%s), activation à chaud : %s",
                     detail or "sans détail", "oui" if chaud else "non")
        conclure({
            "etat": "installee",
            "chaud": chaud,
            "message": langues.t("ext.installee" if chaud else "ext.installee_redemarrer"),
            "extension": self.etat_locuteurs(),
        })

    def _verifier_locuteurs_hors_processus(self) -> tuple[bool, str]:
        commande, dossier = extensions.commande_travailleur(["--verifier-locuteurs"])
        try:
            sortie = subprocess.run(
                commande, cwd=dossier, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=600,
                creationflags=_SANS_FENETRE,
            )
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        detail = ""
        for ligne in (sortie.stdout or "").splitlines():
            if ligne.startswith(extensions.MARQUE):
                _, _, reste = ligne.partition(extensions.MARQUE)
                _, _, charge = reste.partition("|")
                etat, _, detail = charge.partition("|")
                return etat == "ok", detail
        return sortie.returncode == 0, detail

    def retirer_locuteurs(self) -> dict:
        """Efface le dossier d'extensions et le cache de téléchargement."""
        if self._installation_locuteurs is not None:
            return {"ok": False, "message": langues.t("ext.deja_en_cours")}
        resultat = extensions.retirer()
        if not resultat["ok"]:
            journal.erreur("Retrait de l'extension en échec : %s",
                           resultat["message_technique"])
            return {"ok": False, "message": langues.t("ext.retrait_echec")}
        journal.info("Extension des locuteurs retirée, %.2f Go libérés", resultat["libere_go"])
        return {
            "ok": True,
            "message": langues.t("ext.retiree",
                                 taille=langues.nombre(resultat["libere_go"], 2)),
            "extension": self.etat_locuteurs(),
        }

    # -- import et export des données personnelles -------------------------

    def _dossier_de_depart(self) -> str:
        """Dossier proposé dans les boîtes de dialogue d'import et d'export."""
        candidat = Path(self.config.get("dossier_sortie") or "")
        if candidat.is_dir():
            return str(candidat)
        documents = Path.home() / "Documents"
        return str(documents if documents.is_dir() else Path.home())

    def exporter_donnees(self) -> None:
        self._fond(self._dialogue_export)

    def _dialogue_export(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.SAVE_DIALOG,
                directory=self._dossier_de_depart(),
                save_filename=donnees.nom_export_propose(),
                file_types=(langues.t("arch.type"),),
            )
        except Exception as exc:
            journal.exception("Ouverture de la boîte d'enregistrement impossible", exc)
            refus = {"ok": False, "message": langues.t("app.export.fenetre")}
            self._js(f"onExportDonnees({_json(refus)})")
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onExportDonnees({_json(donnees.exporter(str(chemin)))})")

    def choisir_import(self) -> None:
        self._fond(self._dialogue_import)

    def _dialogue_import(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=self._dossier_de_depart(),
                file_types=(langues.t("arch.type"), langues.t("arch.tous_fichiers")),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if not resultat:
            return
        chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
        self._js(f"onApercuImport({_json(donnees.analyser(str(chemin)))})")

    def appliquer_import(self, chemin: str) -> dict:
        """Écrit réellement les données importées, après confirmation de l'utilisateur."""
        retour = donnees.importer(chemin)
        if retour.get("ok"):
            # L'objet de configuration en mémoire est périmé dès cet instant.
            self.config = config_module.charger()
            retour["config"] = self.config
            retour["avertissements"] = self._avertissements()
            retour["modeles"] = self.infos_modeles()
        return retour

    def estimation(self, duree_secs: float, cle_preset: str, diarisation_active: bool,
                   modele_avance: str = "") -> str:
        # La largeur de faisceau change le coût du simple au double : elle entre
        # dans la clé des mesures relevées sur le poste, elle doit donc être dite.
        beam = int(self.config.get("beam_size") or 0) \
            if self.config.get("mode_avance") else 0
        # Rythme équilibré ou discret : plus long, et l'annonce le dit (en
        # adaptation automatique, la durée du rythme choisi, la plus longue).
        # La séparation des locuteurs ne compte que si elle tournera vraiment :
        # cochée par défaut, elle ajoutait son coût sans être installée.
        return presets.formater_duree(presets.estimer_annonce(
            duree_secs, cle_preset, self.materiel, self.config.get("rythme"),
            diarisation.effective(diarisation_active), modele_avance or "", beam=beam))

    # -- fichiers ----------------------------------------------------------

    def ajouter_fichiers(self) -> None:
        self._fond(self._dialogue_fichiers)

    def _dialogue_fichiers(self) -> None:
        # Séparateur ; imposé par pywebview : « Nom (*.ext1;*.ext2) ». Avec des
        # espaces, parse_file_type refuse le filtre et le sélecteur ne s'ouvre
        # jamais (bug constaté le 18/08 : clic sur la zone de dépôt sans effet).
        extensions = ";".join(f"*{e}" for e in sorted(audio_module.EXTENSIONS_AUDIO))
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=True,
                file_types=(langues.t("app.dialogue.audio", extensions=extensions),
                            langues.t("arch.tous_fichiers")),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de fichiers impossible", exc)
            return
        if resultat:
            self._enregistrer_fichiers(list(resultat))

    def _enregistrer_depot(self, liste: list[str]) -> None:
        """
        Trie ce qui vient d'être déposé sur la fenêtre.

        Trois cas, dans cet ordre : une archive d'export Scribouille seule propose
        l'import, un dossier livre ses fichiers audio de premier niveau, et tout
        le reste part dans la file comme avant.
        """
        chemins_deposes = [str(c) for c in liste if c]
        if not chemins_deposes:
            return

        if len(chemins_deposes) == 1 and chemins_deposes[0].lower().endswith(".zip"):
            self._js(f"onApercuImport({_json(donnees.analyser(chemins_deposes[0]))})")
            return

        fichiers: list[str] = []
        ignores = 0
        for brut in chemins_deposes:
            cible = Path(brut)
            if cible.is_dir():
                retenus, ecartes = audio_module.lister_dossier(cible)
                fichiers += retenus
                ignores += ecartes
                self._sur_journal(
                    "info" if retenus else "attention",
                    langues.t("app.depot.dossier", nom=cible.name, retenus=len(retenus))
                    + (langues.t("app.depot.ignores", n=ecartes) if ecartes else "")
                    + langues.t("app.depot.sous_dossiers"),
                )
            else:
                fichiers.append(brut)

        self._enregistrer_fichiers(fichiers)

    def _enregistrer_fichiers(self, liste: list[str]) -> None:
        ajoutes = self.file.ajouter(liste)
        if not ajoutes:
            doublons = self.file.derniers_doublons
            self._sur_journal("attention", langues.tn("app.depot.deja", doublons) if doublons
                              else langues.t("app.depot.aucun"))
            return
        self._js(f"onFichiersAjoutes({_json(ajoutes)})")
        self._sur_journal("info", langues.tn("app.ajoutes", len(ajoutes)))
        self.file.mesurer_durees(
            lambda identifiant, secondes, texte:
            self._js(f"onDuree({_json(identifiant)}, {secondes}, {_json(texte)})")
        )

    def retirer(self, identifiant: str) -> None:
        self.file.retirer(identifiant)

    def relancer(self, identifiant: str) -> dict:
        """
        Remet en attente un fichier arrêté, en échec ou terminé. Un fichier
        arrêté en route reprend où il en était, grâce à sa sauvegarde.
        """
        element = next((e for e in self.file.elements if e.identifiant == identifiant), None)
        if element is None:
            return {"ok": False, "message": langues.t("app.reprise.introuvable")}
        cle = next((r["cle"] for r in reprise.lister()
                    if Path(r["chemin"]).resolve() == Path(element.chemin).resolve()), "")
        remis = self.file.relancer(identifiant, cle)
        if not remis:
            return {"ok": False, "message": langues.t("app.reprise.introuvable")}
        self._sur_journal("info", langues.t("app.relance", nom=remis["nom"]))
        return {"ok": True, "element": remis, "reprises": self._reprises()}

    def vider_file(self) -> None:
        self.file.vider()

    def choisir_dossier_sortie(self) -> None:
        self._fond(self._dialogue_dossier)

    def _dialogue_dossier(self) -> None:
        try:
            resultat = self._fenetre.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.config.get("dossier_sortie", "") or str(Path.home()),
            )
        except Exception as exc:
            journal.exception("Ouverture du sélecteur de dossier impossible", exc)
            return
        if resultat:
            chemin = resultat[0] if isinstance(resultat, (list, tuple)) else resultat
            self.config["dossier_sortie"] = str(chemin)
            config_module.sauver(self.config)
            self._js(f"onDossierSortie({_json(str(chemin))})")
            self.charger_historique()

    # -- exécution ---------------------------------------------------------

    def demarrer(self) -> dict:
        if self.file.occupee:
            return {"ok": False, "message": langues.t("app.demarrer.en_cours")}
        if self._banc is not None or self._comparaison is not None:
            return {"ok": False, "message": langues.t("app.banc.en_cours")}
        self._effet_reglage = reglage_machine.appliquer_au_materiel(self.config, self.materiel)
        if self._effet_reglage.get("indisponible"):
            # Puce graphique absente, pilote en panne, OpenVINO retiré : le
            # repli sur le moteur habituel est dit au moment où il joue.
            self._sur_journal("attention", langues.t(
                "app.repli_materiel_plantage" if self._effet_reglage.get("plantage")
                else "app.repli_materiel"))
        if not audio_module.ffmpeg_present():
            return {
                "ok": False,
                "message": langues.t(
                    "app.demarrer.ffmpeg_installee" if chemins.EST_GELE
                    else "app.demarrer.ffmpeg_sources"),
            }
        dossier = Path(self.config.get("dossier_sortie") or "")
        try:
            dossier.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "ok": False,
                "message": langues.t("app.demarrer.sortie", erreur=exc.strerror),
            }

        refus = self._verifier_modele_disponible()
        if refus:
            return refus

        if self.config.get("diarisation"):
            manque = diarisation.indisponibilite()
            if manque:
                self._sur_journal(
                    "attention", langues.t("app.diar.ignoree", raison=manque))
            elif not diarisation.jeton_present():
                self._sur_journal("attention", langues.t("app.diar.sans_jeton"))

        self.titre_normal()
        lancee = self.file.demarrer(self.config, self._rappels)
        if not lancee:
            return {"ok": False, "message": langues.t("app.demarrer.file_vide")}
        self._sur_journal("info", langues.t("app.demarrer.lancee"))
        return {"ok": True}

    def _verifier_modele_disponible(self) -> dict | None:
        """
        Contrôles préalables au premier téléchargement d'un modèle.

        Renvoie un refus expliqué si le modèle manque et que rien ne permet de
        l'obtenir (pas de réseau, pas de place), sinon None. Quand le modèle
        manque mais que tout est réuni, on se contente d'annoncer la taille.

        Un modèle incomplet suit exactement le même chemin : il sera complété au
        chargement, ce sont donc les mêmes contrôles de place et de réseau qui
        valent, avec d'autres mots.
        """
        from app import moteur

        modele = self._modele_courant()
        try:
            etat = moteur.etat_modele(modele)["etat"]
        except Exception:
            return None
        if etat == "complet":
            return None
        incomplet = etat == "incomplet"

        taille = moteur.taille_annoncee(modele)
        dossier = chemins.DOSSIER_MODELES

        probleme = chemins.dossier_modeles_inscriptible(dossier)
        if probleme:
            return {
                "ok": False,
                "message": langues.t(
                    "app.modele.dossier_inutilisable",
                    dossier=dossier, probleme=probleme),
            }

        # Le besoin est celui que retiendra le moteur au téléchargement : les
        # deux contrôles doivent dire la même chose, y compris pour les modèles
        # du mode avancé, que l'ancien calcul laissait passer sans rien vérifier.
        libre = chemins.espace_libre_go(dossier)
        requis = moteur.poids_attendu_octets(modele) * moteur.MARGE_DISQUE / 1024 ** 3
        if libre and requis and libre < requis:
            return {
                "ok": False,
                "message": langues.t(
                    "app.modele.place", taille=taille,
                    libre=presets.nombre_fr(libre), dossier=dossier),
            }

        if not moteur.connexion_disponible():
            return {
                "ok": False,
                "message": langues.t(
                    "app.modele.incomplet_hors_ligne" if incomplet
                    else "app.modele.hors_ligne",
                    taille=taille) + " " + moteur.voie_hors_ligne(modele),
            }

        self._sur_journal("attention", langues.t(
            "app.modele.incomplet" if incomplet else "app.modele.premier_usage",
            taille=taille, dossier=dossier))
        return None

    def arreter(self) -> None:
        self.file.arreter()
        self._sur_journal("attention", langues.t("app.arret"))

    # -- historique et ouverture -------------------------------------------

    def charger_historique(self) -> None:
        self._fond(self._lire_historique)

    def _lire_historique(self) -> None:
        from app import sorties

        # Une entrée par transcription (texte et sous-titres ensemble), et plus
        # de coupure à 40 fichiers.
        elements = sorties.historique(Path(self.config.get("dossier_sortie") or ""))
        for element in elements:
            element["taille"] = audio_module.formater_taille(element["taille"])
        self._js(f"onHistorique({_json(elements)})")

    def lire_texte(self, chemin: str) -> str:
        try:
            texte = Path(chemin).read_text(encoding="utf-8")
            return texte[:200000]
        except OSError as exc:
            journal.attention("Lecture impossible de %s : %s", chemin, exc)
            return ""

    # -- vue de lecture ----------------------------------------------------

    def lire_transcription(self, chemin: str) -> dict:
        """Contenu structuré d'une transcription, pour la vue de lecture."""
        # Un fichier retouché dans un éditeur est relu tel quel, et son
        # compagnon recalé dessus une fois pour toutes.
        retour = lecture.charger(chemin, persister=True)
        retour["lecture_audio"] = bool(self.config.get("lecture_audio"))
        retour["niveaux"] = lecture.niveaux_annulables(chemin)
        retour["annulable"] = retour["niveaux"] > 0
        retour["original"] = lecture.original_disponible(chemin)
        # L'audio passe par le serveur local, jamais par un « file:// » que le
        # navigateur intégré refuse depuis une page servie en http.
        meta = retour.get("meta") or {}
        if retour["lecture_audio"] and meta.get("source_presente"):
            retour["audio_url"] = self._ecoute.adresse_pour(meta.get("source_chemin", ""))
        return retour

    def empreinte_transcription(self, chemin: str) -> str:
        """Date et taille du texte et du compagnon : la relecture voit ainsi une retouche faite ailleurs."""
        return lecture.empreinte(chemin)

    def copier_pour_ia(self, chemin: str) -> dict:
        """
        Met dans le presse-papiers le gabarit d'instructions suivi du texte.

        La copie passe par l'API Windows quand le presse-papiers du navigateur
        intégré refuse un texte de cette taille.
        """
        retour = lecture.texte_pour_ia(chemin)
        if not retour.get("ok"):
            return retour
        texte = retour["texte"]
        self.copier(texte)
        journal.info("Texte préparé pour un assistant IA : %s caractères", len(texte))
        return {
            "ok": True,
            "taille": len(texte),
            "message": langues.t("app.copie_ia", n=len(texte)),
        }

    def apercu_correction(self, chemin: str, source: str, cible: str) -> dict:
        """Endroits que la correction toucherait, avant de l'appliquer."""
        return lecture.apercu_correction(chemin, source, cible)

    def corriger_transcription(self, chemin: str, source: str, cible: str,
                               ajouter_regle: bool = False) -> dict:
        """Applique une correction relue au fichier, au compagnon et aux règles."""
        if not self.config.get("corrections_apprises", True):
            ajouter_regle = False
        retour = lecture.appliquer_correction(chemin, source, cible, ajouter_regle)
        if retour.get("regle_ajoutee"):
            regles, _ = vocabulaire.analyser_corrections()
            retour["nb_corrections"] = len(regles)
        return retour

    def annuler_correction(self, chemin: str) -> dict:
        """Défait la dernière correction de ce fichier, règle ajoutée comprise."""
        retour = lecture.annuler_correction(chemin)
        if retour.get("regle_retiree"):
            regles, _ = vocabulaire.analyser_corrections()
            retour["nb_corrections"] = len(regles)
        return retour

    def revenir_original(self, chemin: str) -> dict:
        """Remet la transcription dans son état d'avant toute modification (annulable)."""
        return lecture.revenir_original(chemin)

    def annuler_remplacement(self, chemin: str, rang: int) -> dict:
        """Défait un remplacement du vocabulaire dans une transcription relue."""
        return lecture.annuler_remplacement(chemin, int(rang))

    # -- relecture plein cadre (voir app/relecture.py) ----------------------
    # Ajouts de la refonte d'interface : aucune méthode existante n'est changée.

    def accueil(self) -> dict:
        """Premier lancement : l'interface montre l'accueil et le réglage proposé."""
        return {"premier_lancement": bool(self._premier_lancement)}

    def audio_relecture(self, chemin: str) -> dict:
        """
        Adresse locale de l'enregistrement d'une transcription. L'écoute fait
        partie de la relecture : elle ne dépend plus d'une option.
        """
        from app import compagnon

        fichier = Path(chemin or "")
        donnees = compagnon.lire(fichier) if fichier.is_file() else None
        if donnees:
            source = str((donnees.get("source") or {}).get("chemin") or "")
        else:
            try:
                entete = lecture.separer_entete(fichier.read_text(encoding="utf-8", errors="replace"))[0]
            except OSError:
                entete = ""
            source = lecture._meta_de_lentete(entete, fichier).get("source_chemin", "")
        if not source or not Path(source).is_file():
            return {"ok": False, "code": "audio_absent" if source else "audio_inconnu"}
        url = self._ecoute.adresse_pour(source)
        return {"ok": bool(url), "url": url, "code": "" if url else "audio_illisible"}

    def occurrences_correction(self, chemin: str, source: str, cible: str,
                               avant: str = "", apres: str = "", position=None) -> dict:
        """Endroits d'une correction ; `position` situe la sélection à l'écran (paragraphe, début, fin)."""
        from app import relecture

        return relecture.occurrences(chemin, source, cible, avant, apres, position)

    def corriger_occurrences(self, chemin: str, source: str, cible: str, rangs,
                             ajouter_regle: bool = False, position=None, empreinte: str = "") -> dict:
        from app import relecture

        if not self.config.get("corrections_apprises", True):
            ajouter_regle = False
        retour = relecture.corriger(chemin, source, cible, rangs, bool(ajouter_regle), position,
                                    str(empreinte or ""))
        if retour.get("regle_ajoutee"):
            regles, _ = vocabulaire.analyser_corrections()
            retour["nb_corrections"] = len(regles)
        return retour

    def renommer_locuteur(self, chemin: str, ancien: str, nouveau: str, empreinte: str = "") -> dict:
        from app import relecture

        return relecture.renommer_locuteur(chemin, ancien, nouveau, str(empreinte or ""))

    def enregistrer_export(self, chemin: str, extension: str, contenu: str) -> dict:
        from app import relecture

        return relecture.enregistrer_export(chemin, extension, contenu)

    def ouvrir_dossier_de(self, chemin: str) -> None:
        """Ouvre le dossier qui contient ce fichier."""
        self.ouvrir(str(Path(chemin or "").parent))

    # -- vocabulaire, format 2 (voir app/vocabulaire_interface.py) ----------

    def vocabulaire_etat(self) -> dict:
        return vocabulaire_interface.etat(self.config, self.config.get("langue", "fr"))

    def vocabulaire_decider(self, formes: list, decision: str) -> dict:
        return vocabulaire_interface.decider(list(formes or []), str(decision))

    def vocabulaire_modifier(self, forme: str, etat: str, modification: dict) -> dict:
        return vocabulaire_interface.modifier(forme, etat, dict(modification or {}))

    def vocabulaire_ajouter(self, donnees_entree: dict) -> dict:
        return vocabulaire_interface.ajouter(dict(donnees_entree or {}))

    def vocabulaire_supprimer(self, forme: str, etat: str) -> dict:
        return vocabulaire_interface.supprimer(forme, etat)

    def vocabulaire_convertir(self) -> dict:
        return vocabulaire_interface.convertir()

    def vocabulaire_importer(self) -> None:
        self._fond(lambda: self._dialogue_vocabulaire("importer"))

    def vocabulaire_exporter(self) -> None:
        self._fond(lambda: self._dialogue_vocabulaire("exporter"))

    def vocabulaire_ajouter_partage(self) -> None:
        self._fond(lambda: self._dialogue_vocabulaire("partager"))

    def vocabulaire_retirer_partage(self, chemin: str) -> dict:
        partages = [p for p in self.config.get("vocabulaires_partages") or [] if p != chemin]
        return self.sauver_config({"vocabulaires_partages": partages})

    def _dialogue_vocabulaire(self, geste: str) -> None:
        types = (langues.t("voc2.type_fichier"), langues.t("arch.tous_fichiers"))
        try:
            if geste == "exporter":
                resultat = self._fenetre.create_file_dialog(
                    webview.SAVE_DIALOG, directory=self._dossier_de_depart(),
                    save_filename="vocabulaire-equipe.toml", file_types=types)
            else:
                resultat = self._fenetre.create_file_dialog(
                    webview.OPEN_DIALOG, directory=self._dossier_de_depart(), file_types=types)
        except Exception as exc:
            journal.exception("Ouverture de la boîte de fichiers impossible", exc)
            return
        if not resultat:
            return
        chemin = str(resultat[0] if isinstance(resultat, (list, tuple)) else resultat)
        if geste == "exporter":
            retour = vocabulaire_interface.exporter(chemin, self.config)
        elif geste == "importer":
            retour = vocabulaire_interface.importer(chemin)
        else:
            partages = list(self.config.get("vocabulaires_partages") or [])
            if chemin not in partages:
                partages.append(chemin)
            self.sauver_config({"vocabulaires_partages": partages})
            retour = {"ok": True, "message": langues.t("voc2.partage_ajoute", nom=Path(chemin).name)}
        self._js(f"onVocabulaire({_json(retour)})")

    def lire_gabarit(self) -> dict:
        return {"contenu": gabarit.lire(), "chemin": str(gabarit.fichier())}

    def sauver_gabarit(self, contenu: str) -> dict:
        gabarit.ecrire(contenu or "")
        journal.info("Gabarit d'instructions enregistré.")
        return {"ok": True, "message": langues.t("app.gabarit_enregistre")}

    # -- reprise d'une transcription interrompue ---------------------------

    def _reprises(self) -> list[dict]:
        elements = []
        for item in reprise.lister():
            elements.append({
                **item,
                "position_texte": presets.formater_duree(item["position"]),
                "duree_texte": presets.formater_duree(item["duree_audio"]),
                "ecoule_texte": presets.formater_duree(item["ecoule"]),
            })
        return elements

    def liste_reprises(self) -> list[dict]:
        return self._reprises()

    def reprendre(self, cle: str) -> dict:
        """Remet en file un fichier interrompu, à l'endroit où il s'était arrêté."""
        etat = reprise.lire_etat(cle or "")
        if not etat:
            return {"ok": False, "message": langues.t("app.reprise.indisponible")}
        ajoute = self.file.ajouter_pour_reprise(etat.get("source", ""), cle)
        if not ajoute:
            return {"ok": False, "message": langues.t("app.reprise.introuvable")}
        self._js(f"onFichiersAjoutes({_json([ajoute])})")
        self._sur_journal("info", langues.t(
            "app.reprise.remise", nom=ajoute["nom"],
            position=presets.formater_duree(float(etat.get("position", 0) or 0)),
        ))
        return {"ok": True, "reprises": self._reprises()}

    def oublier_reprise(self, cle: str) -> dict:
        reprise.oublier(cle or "")
        return {"ok": True, "reprises": self._reprises()}

    def ouvrir(self, chemin: str) -> None:
        cible = Path(chemin or "")
        if not cible.exists():
            self._sur_journal("attention", langues.t("app.fichier_disparu"))
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(cible))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(cible)])
            else:
                subprocess.Popen(["xdg-open", str(cible)])
        except Exception as exc:
            journal.exception("Ouverture impossible", exc)

    def ouvrir_dossier_sortie(self) -> None:
        self.ouvrir(self.config.get("dossier_sortie", ""))

    def ouvrir_journal(self) -> None:
        self.ouvrir(str(journal.fichier()))

    def ouvrir_dossier_application(self) -> None:
        self.ouvrir(str(chemins.RACINE))

    def ouvrir_lien(self, url: str) -> None:
        if str(url).startswith(("http://", "https://")):
            webbrowser.open(url)

    def copier(self, texte: str) -> None:
        """Copie via l'API Windows, plus fiable que le presse-papiers du navigateur intégré."""
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["clip"], input=(texte or "").encode("utf-16-le"),
                    creationflags=_SANS_FENETRE, check=False,
                )
        except Exception as exc:
            journal.debug("Copie impossible : %s", exc)


def moteur_nom_court(modele: str) -> str:
    from app.moteur import nom_court

    return nom_court(modele)


# ---------------------------------------------------------------------------
# Glisser-déposer
# ---------------------------------------------------------------------------

def _installer_depot(passerelle: Passerelle, fenetre) -> None:
    """
    Branche le dépôt de fichiers sur la zone prévue.

    pywebview complète chaque fichier déposé avec `pywebviewFullPath`, seul moyen
    d'obtenir le chemin réel : un navigateur ne le donne jamais au JavaScript.
    """
    def sur_depot(evenement):
        try:
            fichiers = (evenement.get("dataTransfer") or {}).get("files") or []
            chemins_deposes = [
                f.get("pywebviewFullPath") for f in fichiers if f.get("pywebviewFullPath")
            ]
            if chemins_deposes:
                passerelle._enregistrer_depot(chemins_deposes)
            else:
                passerelle._sur_journal(
                    "attention", langues.t("app.depot.chemin_illisible"))
        except Exception as exc:
            journal.exception("Dépôt de fichiers en échec", exc)
        finally:
            passerelle._js("finDepot()")

    try:
        # Sur le corps entier : déposer n'importe où dans la fenêtre fonctionne.
        zone = fenetre.dom.body or fenetre.dom.get_element("#zone-depot")
        zone.events.drop += DOMEventHandler(sur_depot, prevent_default=True, stop_propagation=True)
        journal.info("Glisser-déposer actif")
    except Exception as exc:
        journal.exception("Activation du glisser-déposer impossible", exc)


def _au_demarrage(passerelle: Passerelle, fenetre) -> None:
    _installer_depot(passerelle, fenetre)
    passerelle.charger_historique()
    # Détection lente du matériel, après l'affichage et hors de la fenêtre.
    passerelle.rafraichir_materiel_en_fond()
    # Traces de reprise devenues sans objet : fichier source disparu, ou plus
    # vieilles que la rétention. Rien de visible, juste du ménage.
    passerelle._fond(reprise.purger)

    # Barre de progression de l'icône : la fenêtre existe maintenant, elle se
    # retrouve par son titre. Sans elle, le module reste simplement inerte.
    if passerelle.config.get("barre_taches", True):
        passerelle._fond(lambda: barre_taches.definir_fenetre(NOM_APPLICATION))

    # Dossier surveillé : le fil ne démarre que si l'utilisateur l'a demandé.
    if passerelle.config.get("surveillance") and passerelle.config.get("dossier_surveille"):
        # Sans adoption : ce qui est arrivé pendant que l'application était
        # fermée est bien nouveau, et la mémoire persistante empêche de
        # reprendre ce qui a déjà été transcrit.
        passerelle.surveillant.configurer(
            str(passerelle.config.get("dossier_surveille") or ""), True, adopter=False
        )

    # Vérification de mise à jour : seul appel réseau sortant possible, et
    # seulement si l'utilisateur l'a activée. La méthode le revérifie.
    passerelle.verifier_maj()


def _avant_fermeture(passerelle: Passerelle, fenetre):
    """
    Fermer la fenêtre pendant une transcription : on demande d'abord.

    Le travail déjà fait n'est pas perdu (sauvegarde progressive, reprise
    proposée au lancement suivant), mais une fermeture par mégarde coûte le
    calcul en cours. Toute erreur ici laisse fermer : la fenêtre ne doit jamais
    rester bloquée ouverte.
    """
    try:
        if not passerelle.file.occupee:
            return None
        if fenetre.create_confirmation_dialog(
                NOM_APPLICATION, langues.t("app.fermer_pendant_transcription")):
            passerelle.file.arreter()
            journal.info("Fenêtre fermée pendant une transcription, reprise possible au lancement suivant")
            return None
        return False
    except Exception as exc:
        journal.debug("Confirmation de fermeture impossible : %s", exc)
        return None


def principal() -> None:
    journal.info("%s v%s", NOM_APPLICATION, VERSION)
    passerelle = Passerelle()

    fenetre = webview.create_window(
        f"{NOM_APPLICATION}",
        url=str(chemins.DOSSIER_WEB / "index.html"),
        js_api=passerelle,
        width=1180, height=780, min_size=(720, 540),
        background_color="#12151b",
        text_select=True,
    )
    passerelle._fenetre = fenetre
    fenetre.events.shown += passerelle.fenetre_affichee
    fenetre.events.loaded += lambda: _au_demarrage(passerelle, fenetre)
    fenetre.events.closing += lambda: _avant_fermeture(passerelle, fenetre)

    try:
        webview.start(debug=bool(os.environ.get("TRANSCRIPTEUR_DEBUG")))
    except Exception as exc:
        journal.exception("La fenêtre n'a pas pu s'ouvrir", exc)
        _abandonner(
            NOM_APPLICATION,
            langues.t("app.fenetre_impossible", journal=journal.nom_fichier()),
        )


if __name__ == "__main__":
    principal()
