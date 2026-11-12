"""
Processus moteur : `Scribouille --moteur` (ou `transcriber.pyw --moteur`).

Il lit ses ordres sur l'entrée standard, calcule, et répond sur la sortie
standard, selon `app/protocole.py`. Tout ce qui charge une bibliothèque de
calcul (décodeur, CTranslate2, OpenVINO, séparation des locuteurs) vit ici,
jamais dans la fenêtre. Le code d'une file est celui de `app/traitement.py`,
inchangé : seul le lieu d'exécution change.

Options :
    --parent PID      sortir dès que ce processus disparaît
    --journal CHEMIN  écrire dans le journal de la session du parent

Hors du protocole, pour les vérifications seulement : la variable
`SCRIBOUILLE_MOTEUR_ESSAI` (JSON) remplace le moteur de calcul par un moteur
factice (`app/moteur_factice.py`), qui sait aussi simuler un plantage.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
from pathlib import Path

from . import journal, protocole


class Canal:
    """Sortie du protocole : une ligne par message, protégée par un verrou."""

    def __init__(self, descripteur: int):
        self._descripteur = descripteur
        self._verrou = threading.Lock()
        self.ferme = False

    def envoyer(self, type_message: str, **champs) -> None:
        if self.ferme:
            return
        donnees = protocole.encoder({"type": type_message, **champs})
        with self._verrou:
            try:
                os.write(self._descripteur, donnees)
            except OSError:
                # Le parent ne lit plus : il est parti. Rien ne doit survivre.
                self.ferme = True
                os._exit(0)


def _reserver_sortie() -> int:
    """
    Garde la vraie sortie standard pour le protocole, et envoie tout le reste
    (prints, bibliothèques C) vers l'erreur standard.
    """
    try:
        sys.stdout.flush()
    except Exception:
        pass
    descripteur = os.dup(1)
    os.dup2(2, 1)
    try:
        sys.stdout = sys.stderr
    except Exception:
        pass
    return descripteur


def lignes_entree():
    """
    Lignes de l'entrée standard, sans jamais laisser une lecture en attente
    sous Windows.

    Une lecture synchrone en suspens sur le tube de l'entrée standard bloque,
    dans les autres fils, le chargement de toute DLL qui initialise sa
    bibliothèque C (elle interroge les poignées standard avec `GetFileType`) :
    l'import de numpy attendait le prochain ordre. On regarde donc ce qui est
    arrivé (`PeekNamedPipe`) et on ne lit que cela. Ailleurs, ou si l'entrée
    n'est pas un tube, lecture ordinaire.
    """
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.PeekNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k32.GetFileType.argtypes = [wintypes.HANDLE]
        try:
            poignee = msvcrt.get_osfhandle(sys.stdin.fileno())
        except (OSError, ValueError, AttributeError):
            poignee = None
        if poignee is not None and k32.GetFileType(poignee) == 3:  # FILE_TYPE_PIPE
            tampon = b""
            disponible = wintypes.DWORD()
            descripteur = sys.stdin.fileno()
            while True:
                if not k32.PeekNamedPipe(poignee, None, 0, None, ctypes.byref(disponible), None):
                    break  # tube fermé : le parent est parti
                if disponible.value == 0:
                    time.sleep(0.03)
                    continue
                morceau = os.read(descripteur, disponible.value)
                if not morceau:
                    break
                tampon += morceau
                while b"\n" in tampon:
                    ligne, tampon = tampon.split(b"\n", 1)
                    yield ligne
            if tampon:
                yield tampon
            return
    yield from sys.stdin.buffer


def _ouvrir_journal(chemin: str) -> None:
    """Les lignes du moteur rejoignent le journal du parent, marquées « moteur »."""
    import logging

    if not chemin:
        journal.demarrer()
        return
    logger = logging.getLogger("transcripteur")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for ancien in list(logger.handlers):
        logger.removeHandler(ancien)
    handler = logging.FileHandler(chemin, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  [moteur] %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    journal._logger = logger
    journal._fichier_courant = Path(chemin)


class InstanceSurveillee:
    """
    Le moteur de calcul de la file, qui dit ce qu'il fait : chargement,
    modèle prêt, libération. Tout le reste passe tel quel.
    """

    def __init__(self, instance, canal: Canal):
        object.__setattr__(self, "_instance", instance)
        object.__setattr__(self, "_canal", canal)
        object.__setattr__(self, "_modele", "")
        object.__setattr__(self, "_charge", False)

    def __getattr__(self, nom):
        return getattr(self._instance, nom)

    def __setattr__(self, nom, valeur):
        setattr(self._instance, nom, valeur)

    def _annoncer(self, etat: str) -> None:
        self._canal.envoyer("moteur", etat=etat, modele=self._modele,
                            peripherique=str(getattr(self._instance, "peripherique", "") or ""),
                            sur_puce=bool(getattr(self._instance, "sur_puce", False)))

    def charger(self, modele, signaler=None):
        if self._charge and self._modele == str(modele):
            # Modèle gardé d'un fichier à l'autre : rien à annoncer.
            self._instance.charger(modele, signaler)
            return
        object.__setattr__(self, "_modele", str(modele))
        object.__setattr__(self, "_charge", False)
        self._annoncer("chargement")
        self._instance.charger(modele, signaler)
        object.__setattr__(self, "_charge", True)
        self._annoncer("pret")

    def transcrire(self, *args, **kwargs):
        self._annoncer("transcription")
        try:
            return self._instance.transcrire(*args, **kwargs)
        finally:
            self._annoncer("pret")

    def liberer(self):
        self._instance.liberer()
        if self._charge:
            object.__setattr__(self, "_charge", False)
            self._annoncer("libere")


class Moteur:
    """Le moteur côté processus fils : une file à la fois, un fichier à la fois."""

    def __init__(self, canal: Canal):
        self.canal = canal
        self.file = None
        self.contexte: dict | None = None
        self.config: dict = {}

    # -- rappels de la file, transformés en messages ------------------------

    def _rappels(self):
        from . import traitement

        envoyer = self.canal.envoyer
        return traitement.Rappels(
            etat=lambda i, e, m: envoyer("etat", id=i, etat=e, message=m),
            progression=lambda i, d: envoyer("progression", id=i, donnees=d),
            termine=lambda i, d: envoyer("termine", id=i, donnees=d),
            journal_ui=lambda n, t: envoyer("journal", niveau=n, texte=t),
            file_terminee=lambda d: None,
            reprise=lambda i, c: envoyer("reprise", id=i, cle=c),
        )

    # -- ordres -------------------------------------------------------------

    def ouvrir(self, n: int, config: dict, options: dict) -> None:
        from . import langues, materiel, moteur, rythme, traitement

        self.config = dict(config or {})
        langues.definir(self.config.get("langue_interface") or langues.detecter_systeme())
        # Rythme équilibré ou discret : les fils de CTranslate2 attendent sans
        # tourner à vide. OpenMP lit la variable une seule fois, au premier
        # calcul : le moteur est un processus neuf pour chaque file.
        if rythme.normaliser(self.config.get("rythme")) != "vitesse":
            os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")
        moteur.TELECHARGEMENT_PERMIS = bool(options.get("telecharger", True))
        mat, _provisoire = materiel.detecter_au_demarrage()
        self.file = traitement.FileTraitement(mat)
        self.contexte = self.file.ouvrir_file(self.config)
        self.contexte["instance"] = InstanceSurveillee(self.contexte["instance"], self.canal)
        self.canal.envoyer("ouvert", n=n, moteur=mat.moteur,
                           peripherique=mat.peripherique_openvino or mat.peripherique)

    def traiter(self, n: int, donnees: dict) -> None:
        from . import traitement

        if self.file is None or self.contexte is None:
            self.canal.envoyer("erreur", n=n, message="file non ouverte")
            return
        element = traitement.Element(
            identifiant=str(donnees.get("id") or ""), chemin=str(donnees.get("chemin") or ""),
            nom=str(donnees.get("nom") or Path(str(donnees.get("chemin") or "")).name),
            taille=int(donnees.get("taille") or 0), duree=float(donnees.get("duree") or 0.0),
            etat="attente", reprise=str(donnees.get("reprise") or ""),
            duree_annoncee=float(donnees.get("duree_annoncee") or 0.0),
            sortie=str(donnees.get("sortie") or ""))
        statut = self.file.traiter_element(element, self.config, self.contexte, self._rappels())
        self.canal.envoyer("fini", n=n, id=element.identifiant, statut=statut,
                           element={"etat": element.etat, "duree": element.duree,
                                    "reprise": element.reprise})

    def fermer(self, n: int) -> None:
        bilan = {}
        if self.file is not None and self.contexte is not None:
            bilan = self.file.fermer_file(self.contexte, self._rappels())
        self.file, self.contexte = None, None
        self.canal.envoyer("ferme", n=n, bilan=bilan)

    def durees(self, n: int, elements: list) -> None:
        from . import audio as audio_module, presets

        resultats = []
        for element in elements or []:
            try:
                secondes = float(audio_module.duree(str(element.get("chemin") or "")))
            except Exception:
                secondes = 0.0
            resultats.append({"id": element.get("id"), "secondes": round(secondes, 1),
                              "texte": presets.formater_duree(secondes)})
        self.canal.envoyer("durees", n=n, resultats=resultats)


def principal(arguments: list[str]) -> int:
    def valeur(option: str) -> str:
        if option in arguments:
            rang = arguments.index(option)
            if rang + 1 < len(arguments):
                return arguments[rang + 1]
        return ""

    canal = Canal(_reserver_sortie())
    _ouvrir_journal(valeur("--journal"))
    journal.silence_bibliotheques()
    from . import processus

    parent = int(valeur("--parent") or 0)
    if parent:
        processus.surveiller_parent(parent)

    moteur = Moteur(canal)
    ordres: queue.Queue = queue.Queue()

    def lire() -> None:
        """Lit l'entrée standard ; les durées passent devant, en parallèle de la file."""
        for brut in lignes_entree():
            message = protocole.decoder(brut)
            if message is None:
                canal.envoyer("erreur", n=None, message="ligne illisible")
                continue
            if message["type"] == "durees":
                threading.Thread(target=_sans_faute, args=(
                    moteur.durees, message.get("n"), message.get("elements") or []), daemon=True).start()
                continue
            ordres.put(message)
        ordres.put({"type": "quitter"})

    def vie() -> None:
        while not canal.ferme:
            time.sleep(protocole.INTERVALLE_VIE_S)
            canal.envoyer("vie")

    threading.Thread(target=lire, name="lecture-ordres", daemon=True).start()
    threading.Thread(target=vie, name="preuve-de-vie", daemon=True).start()

    from . import VERSION

    canal.envoyer("pret", protocole=protocole.VERSION, version=VERSION, pid=os.getpid())
    journal.info("Moteur prêt (protocole %s, PID %s)", protocole.VERSION, os.getpid())

    # Les ordres de la file s'exécutent dans CE fil, du début à la fin : la
    # demande « pas de mise en veille » est propre au fil qui l'a posée.
    while True:
        message = ordres.get()
        genre, n = message.get("type"), message.get("n")
        if genre == "quitter":
            break
        try:
            if genre == "ouvrir":
                moteur.ouvrir(n, message.get("config") or {}, message.get("options") or {})
            elif genre == "traiter":
                moteur.traiter(n, message.get("element") or {})
            elif genre == "fermer":
                moteur.fermer(n)
            else:
                canal.envoyer("erreur", n=n, message=f"ordre inconnu : {genre}")
        except Exception as exc:
            journal.exception(f"Ordre « {genre} » en échec", exc)
            incident = journal.formater_incident(exc, "moteur")
            canal.envoyer("erreur", n=n, message=incident["titre"], detail=incident.get("detail", ""))
    journal.info("Moteur arrêté à la demande")
    # Sortie immédiate : le fil de lecture peut être dans une lecture que
    # l'arrêt normal de Python attendrait (et ferait planter à la finalisation).
    import logging

    logging.shutdown()
    os._exit(0)


def _sans_faute(fonction, *args) -> None:
    try:
        fonction(*args)
    except Exception as exc:  # pragma: no cover
        journal.exception("Mesure des durées en échec", exc)
