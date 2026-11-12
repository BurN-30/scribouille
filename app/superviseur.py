"""
Superviseur du processus moteur, côté fenêtre et ligne de commande.

Un seul propriétaire du processus fils. Il le lance au premier besoin (une
file, ou la mesure des durées des fichiers ajoutés), lui passe les ordres du
protocole (`app/protocole.py`), relaie ses événements aux rappels de la file,
et l'arrête à la fin de la file : la mémoire du modèle est rendue au système
en même temps que le processus.

Ce qu'il garantit :
  - **annulation** : `arreter()` termine le processus, en moins d'une seconde
    quelle que soit la phase (chargement, compilation pour la puce graphique,
    calcul) ; ce qui est transcrit est déjà sur le disque (`app/reprise.py`) ;
  - **plantage** : un moteur qui meurt (pilote graphique, mémoire) ne touche
    pas la fenêtre. Le fichier en cours est repris une fois, automatiquement,
    au segment près, sans la puce graphique si elle était en jeu (le témoin
    d'OpenVINO est posé : `reglage_machine` replie sur CTranslate2). Un second
    plantage sur le même fichier le laisse « en erreur », reprenable ;
  - **aucun orphelin** : le processus est rangé dans un objet de travail
    Windows (`app/processus.py`), surveille son parent, et sort à la fin de
    son entrée standard ;
  - **veille** : un retour de veille ne passe pas pour un blocage ; un moteur
    muet pendant `DELAI_BLOCAGE_S` hors veille est arrêté et traité comme un
    plantage.

Motif repris de Handy (`engine_supervisor`, MIT, Copyright (c) 2025 CJ Pais).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from . import chemins, journal, langues, processus, protocole

_SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

#: Attente du premier message du moteur. Un exécutable gelé, au premier
#: lancement sous un antivirus d'entreprise, peut mettre plusieurs secondes.
DELAI_DEMARRAGE_S = 120.0
#: Silence du moteur (hors veille) au-delà duquel il est tenu pour bloqué. Il
#: envoie une preuve de vie toutes les 5 s ; une compilation pour la puce
#: graphique dure de 40 s à 2 min.
DELAI_BLOCAGE_S = 15 * 60.0
#: Saut d'horloge entre deux tours de garde qui signale une sortie de veille.
SAUT_VEILLE_S = 30.0
#: Un moteur lancé pour mesurer des durées, sans file, s'arrête après ce délai.
DELAI_INACTIVITE_S = 30.0


class ErreurMoteur(Exception):
    """Le moteur n'a pas pu démarrer, ou a refusé un ordre hors fichier."""


class _MoteurMort(Exception):
    """Le processus moteur s'est terminé pendant une attente."""

    def __init__(self, code: int | None, voulu: bool):
        super().__init__(f"code {code}")
        self.code = code
        self.voulu = voulu


def commande_moteur(options: list[str]) -> tuple[list[str], str]:
    """Commande du processus moteur : l'exécutable console gelé, ou Python sur les sources."""
    if chemins.EST_GELE:
        console = chemins.executable_console()
        exe = console or Path(sys.executable)
        return [str(exe), "--moteur", *options], str(chemins.DOSSIER_PROGRAMME)
    racine = Path(__file__).resolve().parent.parent
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe" and (python.parent / "python.exe").is_file():
        python = python.parent / "python.exe"
    return [str(python), str(racine / "transcriber.pyw"), "--moteur", *options], str(racine)


class Superviseur:
    """Lance, pilote, surveille et arrête le processus moteur."""

    def __init__(self, telecharger: bool = True, journal_parent: str | None = None):
        #: Téléchargement des modèles permis au moteur (la ligne de commande le
        #: coupe sans `--telecharger`).
        self.telecharger = telecharger
        self._journal = journal_parent
        self._processus: subprocess.Popen | None = None
        self._verrou = threading.RLock()
        self._verrou_envoi = threading.Lock()
        self._attentes: dict[int, dict] = {}
        self._numero = 0
        self._rappels = None
        self._element = None
        self._cles_reprise: dict[str, str] = {}
        self._config: dict | None = None
        self._arret_voulu = False
        self._dernier_message = time.monotonic()
        self._fin_lecture = threading.Event()
        self._mort = _MoteurMort(None, False)
        self._minuterie: threading.Timer | None = None
        self._sonde: processus.Sonde | None = None
        #: État public (`moteur_etat`).
        self.etat = "arrete"
        self.modele = ""
        self.peripherique = ""
        self.sur_puce = False
        self.depuis = time.time()
        self.derniere_panne: dict | None = None
        self.version_protocole: int | None = None
        #: Chargements de modèle et lancements du moteur depuis la création.
        self.chargements = 0
        self.lancements = 0
        #: Horloges de la garde (remplaçables par les vérifications).
        self.horloge_mur: Callable[[], float] = time.time
        self.horloge_mono: Callable[[], float] = time.monotonic

    # -- cycle de vie --------------------------------------------------------

    @property
    def pid(self) -> int | None:
        """PID du moteur (celui qui calcule), None s'il ne tourne pas."""
        p = self._processus
        if p is None or p.poll() is not None:
            return None
        return getattr(self, "_pid_moteur", None) or p.pid

    def vivant(self) -> bool:
        return self.pid is not None

    def _changer_etat(self, etat: str) -> None:
        if etat != self.etat:
            self.etat = etat
            self.depuis = time.time()

    def demarrer(self) -> None:
        """Lance le moteur s'il ne tourne pas, et attend son premier message."""
        with self._verrou:
            if self.vivant():
                return
            self._annuler_minuterie()
            self._arret_voulu = False
            options = ["--parent", str(os.getpid())]
            fichier_journal = self._journal or str(journal.fichier())
            if fichier_journal:
                options += ["--journal", fichier_journal]
            commande, dossier = commande_moteur(options)
            environnement = dict(os.environ)
            # Même dossier de données que le parent, sans nouvelle reprise de l'ancien.
            environnement["SCRIBOUILLE_DONNEES"] = str(chemins.RACINE)
            environnement.setdefault("PYTHONUTF8", "1")
            self._changer_etat("demarrage")
            try:
                p = subprocess.Popen(
                    commande, cwd=dossier, env=environnement,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=_SANS_FENETRE, bufsize=0)
            except OSError as exc:
                self._changer_etat("panne")
                raise ErreurMoteur(langues.t("superviseur.demarrage_impossible", detail=str(exc))) from exc
            processus.rattacher(p)
            self._processus = p
            self._sonde = processus.Sonde(p.pid)
            self._dernier_message = time.monotonic()
            self._fin_lecture = threading.Event()
            pret = threading.Event()
            self._attentes[0] = {"evenement": pret, "reponse": None}
            threading.Thread(target=self._lire_sortie, args=(p, self._fin_lecture), name="moteur-sortie",
                             daemon=True).start()
            threading.Thread(target=self._lire_erreurs, args=(p,), name="moteur-erreurs", daemon=True).start()
            threading.Thread(target=self._garde, args=(p,), name="moteur-garde", daemon=True).start()
            self.lancements += 1
            journal.info("Moteur lancé : PID %s", p.pid)
        limite = time.monotonic() + DELAI_DEMARRAGE_S
        while not pret.wait(0.1):
            if p.poll() is not None or time.monotonic() > limite:
                self._tuer(p)
                self._changer_etat("panne")
                raise ErreurMoteur(langues.t("superviseur.demarrage_impossible",
                                             detail=f"code {p.poll()}"))
        reponse = self._attentes.pop(0, {}).get("reponse") or {}
        if reponse.get("protocole") != protocole.VERSION:
            self._tuer(p)
            self._changer_etat("panne")
            detail = f"protocole {reponse.get('protocole')}" if reponse else f"code {p.poll()}"
            raise ErreurMoteur(langues.t("superviseur.demarrage_impossible", detail=detail))
        self.version_protocole = reponse.get("protocole")
        # PID du moteur lui-même (depuis les sources, l'interpréteur d'un
        # environnement virtuel est un lanceur qui a son propre fils).
        self._pid_moteur = int(reponse.get("pid") or p.pid)
        self._sonde = processus.Sonde(self._pid_moteur)
        self._changer_etat("repos")

    def _tuer(self, p: subprocess.Popen) -> None:
        """Arrêt immédiat (TerminateProcess) du moteur et de ses descendants."""
        for pid in processus.enfants(p.pid):
            try:
                import psutil  # type: ignore

                psutil.Process(pid).kill()
            except Exception:
                pass
        try:
            p.kill()
        except OSError:
            pass

    def arreter(self) -> None:
        """Annulation : le moteur est arrêté sur-le-champ, quelle que soit sa phase."""
        with self._verrou:
            p = self._processus
            if p is None or p.poll() is not None:
                return
            self._arret_voulu = True
        depart = time.perf_counter()
        self._tuer(p)
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            pass
        journal.info("Moteur arrêté à la demande en %.0f ms", (time.perf_counter() - depart) * 1000)

    def quitter(self, delai: float = 10.0) -> None:
        """Fin propre : le moteur sort de lui-même, ou il est arrêté."""
        with self._verrou:
            p = self._processus
            if p is None or p.poll() is not None:
                # Un moteur mort de lui-même reste « en panne » à l'écran jusqu'au
                # prochain lancement : la fin de la file ne l'efface pas.
                if self.etat != "panne":
                    self._changer_etat("arrete")
                return
            self._arret_voulu = True
        try:
            self._envoyer("quitter")
            p.wait(timeout=delai)
        except Exception:
            self._tuer(p)
        self._changer_etat("arrete")
        self.modele = ""

    # -- lecture ---------------------------------------------------------------

    def _lire_sortie(self, p: subprocess.Popen, fin: threading.Event) -> None:
        flux = p.stdout
        try:
            for brut in iter(flux.readline, b""):
                self._dernier_message = time.monotonic()
                message = protocole.decoder(brut)
                if message is not None:
                    try:
                        self._recevoir(message)
                    except Exception as exc:  # pragma: no cover - un rappel fautif
                        journal.exception("Message du moteur mal relayé", exc)
        except (OSError, ValueError):
            pass
        code = p.wait()
        voulu = self._arret_voulu
        if not voulu:
            self.derniere_panne = {"code": code, "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "etat": self.etat, "peripherique": self.peripherique,
                                   "sur_puce": self.sur_puce}
            journal.attention("Moteur terminé sans qu'on le demande : code %s (état %s, %s)",
                              code, self.etat, self.peripherique or "--")
            self._changer_etat("panne")
        else:
            self._changer_etat("arrete")
        self._mort = _MoteurMort(code, voulu)
        fin.set()
        for numero, attente in list(self._attentes.items()):
            attente["mort"] = self._mort
            attente["evenement"].set()

    def _lire_erreurs(self, p: subprocess.Popen) -> None:
        """L'erreur standard du moteur (bibliothèques C, avertissements) part au journal."""
        try:
            for brut in iter(p.stderr.readline, b""):
                texte = brut.decode("utf-8", "replace").rstrip()
                if texte:
                    journal.debug("[moteur, sortie technique] %s", texte[:500])
        except (OSError, ValueError):
            pass

    def _recevoir(self, message: dict) -> None:
        genre = message.get("type")
        if genre == "pret":
            attente = self._attentes.get(0)
            if attente is not None:
                attente["reponse"] = message
                attente["evenement"].set()
            return
        if genre == "vie":
            return
        if genre == "moteur":
            etat = str(message.get("etat") or "")
            if etat == "chargement":
                self.chargements += 1
            self.modele = str(message.get("modele") or "") if etat != "libere" else ""
            self.peripherique = str(message.get("peripherique") or "")
            self.sur_puce = bool(message.get("sur_puce"))
            self._changer_etat({"pret": "repos", "libere": "repos"}.get(etat, etat))
            return
        numero = message.get("n")
        if genre in ("ouvert", "ferme", "fini", "durees") or (genre == "erreur" and numero is not None):
            attente = self._attentes.get(int(numero or 0))
            if attente is not None:
                attente["reponse"] = message
                attente["evenement"].set()
            return
        rappels, element = self._rappels, self._element
        if genre == "reprise":
            self._cles_reprise[str(message.get("id"))] = str(message.get("cle") or "")
            if element is not None and element.identifiant == message.get("id"):
                element.reprise = str(message.get("cle") or "")
        if rappels is None:
            if genre == "journal" or genre == "erreur":
                journal.info("Moteur : %s", message.get("texte") or message.get("message"))
            return
        if genre == "etat":
            if element is not None and element.identifiant == message.get("id"):
                element.etat = str(message.get("etat") or element.etat)
            rappels.etat(message.get("id"), message.get("etat"), message.get("message") or "")
        elif genre == "progression":
            rappels.progression(message.get("id"), message.get("donnees") or {})
        elif genre == "termine":
            rappels.termine(message.get("id"), message.get("donnees") or {})
        elif genre == "journal":
            rappels.journal_ui(message.get("niveau") or "info", message.get("texte") or "")
        elif genre == "erreur":
            rappels.journal_ui("erreur", message.get("message") or "")

    # -- garde : veille et blocage --------------------------------------------

    def _garde(self, p: subprocess.Popen) -> None:
        mur, mono = self.horloge_mur(), self.horloge_mono()
        while p.poll() is None:
            time.sleep(1.0)
            maintenant_mur, maintenant_mono = self.horloge_mur(), self.horloge_mono()
            saut = max(maintenant_mur - mur, maintenant_mono - mono) - 1.0
            mur, mono = maintenant_mur, maintenant_mono
            if saut > SAUT_VEILLE_S:
                # Sortie de veille : le silence du moteur n'est pas un blocage. Si
                # le pilote graphique n'a pas survécu, le moteur le dira (repli
                # d'OpenVINO) ou mourra (plantage, reprise au segment près).
                journal.info("Retour de veille (%.0f s) : garde du moteur remise à zéro", saut)
                self._dernier_message = time.monotonic()
                if self._rappels is not None:
                    self._rappels.journal_ui("info", langues.t("superviseur.veille"))
                continue
            if self._config is not None and time.monotonic() - self._dernier_message > DELAI_BLOCAGE_S:
                journal.erreur("Moteur muet depuis %.0f s : arrêté", time.monotonic() - self._dernier_message)
                if self._rappels is not None:
                    self._rappels.journal_ui("erreur", langues.t(
                        "superviseur.bloque", minutes=int(DELAI_BLOCAGE_S // 60)))
                self._tuer(p)
                return

    # -- envoi et attente -----------------------------------------------------

    def _envoyer(self, genre: str, **champs) -> int:
        with self._verrou_envoi:
            self._numero += 1
            numero = self._numero
            p = self._processus
            if p is None or p.poll() is not None or p.stdin is None:
                raise _MoteurMort(p.poll() if p else None, self._arret_voulu)
            if genre != "quitter":
                self._attentes[numero] = {"evenement": threading.Event(), "reponse": None}
            try:
                p.stdin.write(protocole.encoder({"type": genre, "n": numero, **champs}))
                p.stdin.flush()
            except OSError as exc:
                self._attentes.pop(numero, None)
                raise _MoteurMort(p.poll(), self._arret_voulu) from exc
        return numero

    def _attendre(self, numero: int, delai: float | None = None) -> dict:
        attente = self._attentes.get(numero)
        if attente is None:
            raise ErreurMoteur(f"ordre {numero} inconnu")
        limite = None if delai is None else time.monotonic() + delai
        fin = self._fin_lecture
        try:
            while not attente["evenement"].wait(0.2):
                if fin.is_set() and not attente["evenement"].is_set():
                    # Le moteur est mort entre l'envoi et l'enregistrement de l'attente.
                    attente["mort"] = self._mort
                    break
                if limite is not None and time.monotonic() > limite:
                    raise ErreurMoteur(f"pas de réponse à l'ordre {numero}")
        finally:
            self._attentes.pop(numero, None)
        if "mort" in attente and attente.get("reponse") is None:
            raise attente["mort"]
        return attente["reponse"] or {}

    # -- la file ----------------------------------------------------------------

    def ouvrir_file(self, config: dict, rappels) -> None:
        """Prépare une file dans le moteur (lancé au besoin)."""
        with self._verrou:
            self._annuler_minuterie()
            self._rappels = rappels
            self._config = dict(config)
            self._cles_reprise.clear()
        self._ouvrir()

    def _ouvrir(self) -> None:
        self.demarrer()
        reponse = self._attendre(self._envoyer("ouvrir", config=self._config,
                                               options={"telecharger": self.telecharger}))
        if reponse.get("type") == "erreur":
            raise ErreurMoteur(str(reponse.get("message") or "ouverture de la file"))
        self.peripherique = str(reponse.get("peripherique") or "")

    def traiter(self, element, rappels, interrompu: Callable[[], bool] | None = None) -> str:
        """
        Un fichier, jusqu'au bout, plantages compris. Renvoie le statut de
        `traitement.traiter_element` : reussi, sans_voix, annule ou erreur.
        """
        from . import reprise as reprise_module

        self._rappels = rappels
        plantages = 0
        while True:
            self._element = element
            try:
                numero = self._envoyer("traiter", element={
                    "id": element.identifiant, "chemin": element.chemin, "nom": element.nom,
                    "taille": element.taille, "duree": element.duree, "reprise": element.reprise,
                    "duree_annoncee": element.duree_annoncee,
                    "sortie": getattr(element, "sortie", "")})
                reponse = self._attendre(numero)
            except _MoteurMort as mort:
                if mort.voulu or (interrompu is not None and interrompu()):
                    element.etat = "annule"
                    cle = self._cles_reprise.get(element.identifiant)
                    if cle:
                        element.reprise = cle
                    rappels.etat(element.identifiant, "annule", langues.t("etat.arrete"))
                    rappels.termine(element.identifiant, {"ok": False, "annule": True})
                    return "annule"
                plantages += 1
                sur_puce, peripherique = self.sur_puce, self.peripherique
                cause = f"code {mort.code}"
                rappels.journal_ui("erreur", langues.t("superviseur.plantage", cause=cause))
                if sur_puce:
                    self._poser_temoin_puce(peripherique)
                    rappels.journal_ui("attention", langues.t("superviseur.repli_puce"))
                cle = self._cles_reprise.get(element.identifiant) or element.reprise
                if plantages >= 2:
                    return self._echec_definitif(element, rappels, cle, cause)
                etat = reprise_module.lire_etat(cle) if cle else None
                if etat and float(etat.get("position") or 0) > 0:
                    element.reprise = cle
                    rappels.journal_ui("info", langues.t(
                        "superviseur.reprise_auto", nom=element.nom,
                        position=_minutes(float(etat.get("position") or 0))))
                try:
                    self._ouvrir()
                except Exception as exc:
                    journal.exception("Relance du moteur après plantage impossible", exc)
                    return self._echec_definitif(element, rappels, cle, cause)
                continue
            finally:
                self._element = None
            if reponse.get("type") == "erreur":
                element.etat = "erreur"
                rappels.etat(element.identifiant, "erreur", str(reponse.get("message") or ""))
                rappels.termine(element.identifiant, {"ok": False, "titre": str(reponse.get("message") or "")})
                return "erreur"
            infos = reponse.get("element") or {}
            element.etat = str(infos.get("etat") or element.etat)
            element.duree = float(infos.get("duree") or element.duree or 0)
            element.reprise = str(infos.get("reprise") or "")
            return str(reponse.get("statut") or "erreur")

    def _echec_definitif(self, element, rappels, cle: str, cause: str) -> str:
        element.etat = "erreur"
        from . import reprise as reprise_module

        # « Reprenable » seulement si un segment au moins est gardé : sinon,
        # rien à reprendre, la ligne propose « Relancer » (comme `etat`).
        etat = reprise_module.lire_etat(cle) if cle else None
        if not (etat and float(etat.get("position") or 0) > 0):
            cle = ""
        element.reprise = cle
        titre = langues.t("superviseur.echec_definitif" if cle else "superviseur.echec_definitif_vide",
                          nom=element.nom)
        journal.erreur("Fichier %s abandonné après plantage du moteur (%s)", element.nom, cause)
        rappels.etat(element.identifiant, "erreur", titre)
        rappels.journal_ui("erreur", titre)
        rappels.termine(element.identifiant, {"ok": False, "titre": titre, "message": cause,
                                              "plantage_moteur": True, "reprise": cle or ""})
        return "erreur"

    @staticmethod
    def _poser_temoin_puce(peripherique: str) -> None:
        """Le moteur suivant ne retournera pas sur la puce graphique (voir `reglage_machine`)."""
        try:
            temoin = chemins.RACINE / "openvino-chargement-en-cours.txt"
            temoin.write_text((peripherique or "GPU").upper() + "\n", encoding="utf-8")
        except OSError as exc:
            journal.debug("Témoin de la puce graphique non posé : %s", exc)

    def fermer_file(self, rappels=None) -> None:
        """Fin de file : modèle et rythme rendus, puis le moteur sort (mémoire rendue)."""
        self._rappels = rappels or self._rappels
        try:
            if self.vivant():
                self._attendre(self._envoyer("fermer"), delai=120)
        except Exception as exc:
            journal.debug("Fermeture de la file : %s", exc)
        finally:
            self._config = None
            self._rappels = None
            self.quitter()

    # -- durées ---------------------------------------------------------------

    def durees(self, elements: list[dict], rappel: Callable[[str, float, str], None]) -> None:
        """Durées annoncées par les en-têtes, mesurées par le moteur, en tâche de fond."""
        def travail() -> None:
            try:
                self.demarrer()
                reponse = self._attendre(self._envoyer("durees", elements=elements), delai=300)
                for r in reponse.get("resultats") or []:
                    rappel(str(r.get("id")), float(r.get("secondes") or 0), str(r.get("texte") or ""))
            except Exception as exc:
                journal.attention("Durées des fichiers non mesurées : %s", exc)
            finally:
                if self._config is None:
                    self._programmer_arret()

        threading.Thread(target=travail, name="moteur-durees", daemon=True).start()

    def _programmer_arret(self) -> None:
        self._annuler_minuterie()

        def arret() -> None:
            with self._verrou:
                if self._config is None:
                    self.quitter()

        self._minuterie = threading.Timer(DELAI_INACTIVITE_S, arret)
        self._minuterie.daemon = True
        self._minuterie.start()

    def _annuler_minuterie(self) -> None:
        if self._minuterie is not None:
            self._minuterie.cancel()
            self._minuterie = None

    # -- état public ------------------------------------------------------------

    def etat_public(self) -> dict:
        """État du processus moteur, pour `moteur_etat()` et `scribouille etat`."""
        releve = self._sonde.releve() if (self._sonde is not None and self.vivant()) else None
        etat = self.etat
        if not self.vivant() and etat not in ("panne", "demarrage"):
            etat = "arrete"
        return {
            "etat": etat,
            "pid": self.pid,
            "modele": self.modele if self.vivant() else "",
            "peripherique": self.peripherique if self.vivant() else "",
            "sur_puce": bool(self.sur_puce and self.vivant()),
            "memoire_octets": (releve or {}).get("memoire_octets"),
            "prive_octets": (releve or {}).get("prive_octets"),
            "depuis": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.depuis)),
            "file_ouverte": self._config is not None,
            "chargements": self.chargements,
            "protocole": protocole.VERSION,
            "derniere_panne": self.derniere_panne,
        }

    def usage(self) -> dict | None:
        """Mémoire et processeur du moteur, ou None s'il ne tourne pas."""
        if self._sonde is None or not self.vivant():
            return None
        return self._sonde.releve()


def _minutes(secondes: float) -> str:
    from . import presets

    return presets.formater_duree(secondes)
