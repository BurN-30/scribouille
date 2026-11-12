"""
File de traitement séquentielle.

Un seul fichier à la fois, volontairement : la transcription sature déjà le
processeur, et le séquencement est ce qui garantit la tenue en mémoire.

Déroulé d'un fichier :
    décodage → transcription → libération du modèle → diarisation → corrections → écriture

Chaque étape informe l'interface via des rappels, et tout le détail technique
part dans le fichier de log.
"""

from __future__ import annotations

import gc
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import audio as audio_module
from . import calibration
from . import config as config_module
from . import diarisation, energie, journal, langues, moteur, presets, reprise as reprise_module
from . import reglage_machine, rythme, sorties, vocabulaire, vocabulaire_usage, vocabulaire_v2
from .journal import ErreurLisible
from .materiel import Materiel

ETATS = ("attente", "decodage", "transcription", "locuteurs", "ecriture", "termine", "erreur", "annule")


@dataclass
class Element:
    identifiant: str
    chemin: str
    nom: str
    taille: int = 0
    duree: float = 0.0
    etat: str = "attente"
    #: Clé de reprise quand ce fichier a été remis en file après une interruption.
    reprise: str = ""
    #: Durée annoncée par l'en-tête du fichier, mesurée à l'ajout (0 : inconnue).
    duree_annoncee: float = 0.0

    def en_dict(self) -> dict:
        return {
            "id": self.identifiant,
            "chemin": self.chemin,
            "nom": self.nom,
            "taille": audio_module.formater_taille(self.taille) if self.taille else "",
            "duree_secs": round(self.duree, 1),
            "duree": presets.formater_duree(self.duree) if self.duree else "--",
            "etat": self.etat,
            "reprise": bool(self.reprise),
        }


@dataclass
class Rappels:
    """Fonctions d'information vers l'interface. Toutes optionnelles."""

    etat: Callable[[str, str, str], None] = lambda i, e, m: None
    progression: Callable[[str, dict], None] = lambda i, d: None
    termine: Callable[[str, dict], None] = lambda i, d: None
    journal_ui: Callable[[str, str], None] = lambda n, t: None
    file_terminee: Callable[[dict], None] = lambda d: None


def fabriquer_moteur(mat: Materiel, reglages: dict):
    """
    Moteur de la file : OpenVINO si le réglage du poste le demande, sinon
    CTranslate2. « Forcer le processeur » (mode avancé) ramène toujours au
    chemin historique, CTranslate2 sur processeur.
    """
    if mat.moteur == "openvino" and not reglages.get("forcer_processeur"):
        from . import moteur_openvino

        return moteur_openvino.MoteurAvecRepli(mat, mat.peripherique_openvino or "CPU")
    return moteur.MoteurTranscription(mat, forcer_processeur=bool(reglages.get("forcer_processeur")))


class FileTraitement:
    def __init__(self, mat: Materiel):
        self.materiel = mat
        self.elements: list[Element] = []
        self._verrou = threading.Lock()
        self._arret = threading.Event()
        self._fil: threading.Thread | None = None
        self._en_cours = False
        #: Sauvegarde progressive du fichier en cours, fermée quoi qu'il arrive.
        self._session = reprise_module.session_inactive()
        #: Rythme de la file en cours : choisi, adaptation, régulateur.
        self._rythme: dict = {}
        #: Fichiers du dernier ajout ignorés parce qu'ils attendent déjà ou
        #: sont en cours : l'interface le dit au lieu de se taire.
        self.derniers_doublons = 0

    # -- gestion de la file -------------------------------------------------

    @property
    def occupee(self) -> bool:
        return self._en_cours

    #: États d'un fichier déjà listé que l'on peut remettre en attente : il a
    #: été arrêté, a échoué, ou est terminé et l'on veut le refaire.
    ETATS_RELANCABLES = ("annule", "erreur", "termine")

    def _remettre_en_attente(self, element: Element, cle_reprise: str = "") -> dict:
        element.etat = "attente"
        element.reprise = cle_reprise
        return element.en_dict()

    def ajouter(self, chemins_fichiers: list[str]) -> list[dict]:
        """
        Ajoute des fichiers, ignore les formats non audio.

        Un fichier déjà listé mais arrêté, en échec ou terminé repasse en
        attente au lieu d'être ignoré ; un fichier qui attend déjà ou qui est
        en cours n'est pas ajouté une seconde fois, et il est compté dans
        `derniers_doublons` pour que l'interface puisse le dire.
        """
        ajoutes: list[dict] = []
        self.derniers_doublons = 0
        with self._verrou:
            deja = {e.chemin.lower(): e for e in self.elements}
            for brut in chemins_fichiers:
                if not brut:
                    continue
                fichier = Path(brut)
                if not fichier.is_file():
                    continue
                if not audio_module.est_audio(fichier):
                    journal.attention("Format ignoré : %s", fichier.name)
                    continue
                present = deja.get(str(fichier).lower())
                if present is not None:
                    if present.etat in self.ETATS_RELANCABLES:
                        ajoutes.append(self._remettre_en_attente(present))
                    else:
                        self.derniers_doublons += 1
                    continue
                element = Element(
                    identifiant=f"f{int(time.time() * 1000)}{len(self.elements)}",
                    chemin=str(fichier),
                    nom=fichier.name,
                    taille=fichier.stat().st_size,
                )
                self.elements.append(element)
                deja[str(fichier).lower()] = element
                ajoutes.append(element.en_dict())
        return ajoutes

    def relancer(self, identifiant: str, cle_reprise: str = "") -> dict | None:
        """Remet en attente un fichier arrêté, en échec ou terminé, depuis sa ligne."""
        with self._verrou:
            for element in self.elements:
                if element.identifiant == identifiant and element.etat in self.ETATS_RELANCABLES:
                    return self._remettre_en_attente(element, cle_reprise)
        return None

    def ajouter_pour_reprise(self, chemin: str, cle_reprise: str) -> dict | None:
        """
        Remet en file un fichier dont la transcription avait été interrompue.

        Le fichier peut déjà être dans la file : il repasse alors en attente avec
        sa reprise (c'est le cas juste après « Arrêter »), plutôt que de créer
        un doublon. Seul un fichier en cours de calcul est refusé.
        """
        fichier = Path(chemin or "")
        if not fichier.is_file():
            return None
        with self._verrou:
            for element in self.elements:
                if element.chemin.lower() == str(fichier).lower():
                    if element.etat == "attente" or element.etat in self.ETATS_RELANCABLES:
                        return self._remettre_en_attente(element, cle_reprise)
                    return None
        ajoutes = self.ajouter([str(fichier)])
        if not ajoutes:
            return None
        with self._verrou:
            for element in self.elements:
                if element.identifiant == ajoutes[0]["id"]:
                    element.reprise = cle_reprise
                    return element.en_dict()
        return None

    def retirer(self, identifiant: str) -> None:
        with self._verrou:
            self.elements = [
                e for e in self.elements
                if e.identifiant != identifiant or e.etat not in ("attente", "termine", "erreur", "annule")
            ]

    def vider(self) -> None:
        with self._verrou:
            self.elements = [e for e in self.elements if e.etat not in
                             ("attente", "termine", "erreur", "annule")]

    def mesurer_durees(self, rappel: Callable[[str, float, str], None]) -> None:
        """Mesure les durées en tâche de fond, sans bloquer l'interface."""
        def travail():
            for element in list(self.elements):
                if element.duree:
                    continue
                valeur = audio_module.duree(element.chemin)
                element.duree = valeur
                element.duree_annoncee = valeur
                rappel(element.identifiant, round(valeur, 1), presets.formater_duree(valeur))

        threading.Thread(target=travail, daemon=True).start()

    # -- exécution ----------------------------------------------------------

    def demarrer(self, config: dict, rappels: Rappels) -> bool:
        if self._en_cours:
            return False
        attente = [e for e in self.elements if e.etat == "attente"]
        if not attente:
            return False
        self._arret.clear()
        self._en_cours = True
        self._fil = threading.Thread(
            target=self._boucle, args=(config, rappels), daemon=True
        )
        self._fil.start()
        return True

    def arreter(self) -> None:
        self._arret.set()

    def _interrompu(self) -> bool:
        return self._arret.is_set()

    def _boucle(self, config: dict, rappels: Rappels) -> None:
        reglages = config_module.reglages_effectifs(config)
        # Réglage mesuré sur ce poste par le banc d'essai, s'il a été accepté :
        # moteur, périphérique, fils. Relu à chaque file, il suit les boutons
        # « Appliquer » et « Revenir à l'automatique » sans redémarrage.
        reglage_machine.appliquer_au_materiel(config, self.materiel)
        # Traitement par lots selon la mémoire de CE poste : la configuration
        # ne connaît pas le matériel, la file si.
        reglages["lot"] = presets.taille_lot(reglages["preset"], self.materiel)
        impose = reglage_machine.lot_impose(config, self.materiel)
        if impose is not None and reglages["lot"]:
            # Le banc a mesuré mieux sur ce poste ; la garde mémoire, elle,
            # reste prioritaire (un lot de 0 venu d'elle n'est jamais relevé).
            reglages["lot"] = impose
        # Faisceau mesuré par la campagne et accepté (« --appliquer ») : il vaut
        # pour le moteur retenu. Sans réglage, rien ne change.
        faisceau = reglage_machine.faisceau_impose(config, self.materiel)
        if faisceau is not None:
            if self.materiel.moteur == "openvino":
                reglages["faisceau_openvino"] = faisceau
            else:
                reglages["beam_size"] = reglages["best_of"] = faisceau
        # Rythme « je travaille en même temps » (voir app/rythme.py). En vitesse
        # maximale sans adaptation, la file se comporte exactement comme avant.
        choisi = rythme.normaliser(config.get("rythme"))
        regulateur = rythme.Regulateur(
            self.materiel, choisi, bool(config.get("rythme_auto")),
            sur_bascule=lambda nouveau, raison: journal.info(
                "Rythme effectif : %s (%s)", nouveau, raison))
        charge = regulateur.chargement
        if charge.lot_max is not None and reglages["lot"]:
            reglages["lot"] = min(int(reglages["lot"]), charge.lot_max)
        moteur.limiter_parallelisme(charge.fils)
        self._rythme = {"choisi": choisi, "auto": regulateur.auto, "regulateur": regulateur}

        instance = fabriquer_moteur(self.materiel, reglages)
        if charge.rythme != "vitesse" or regulateur.auto:
            instance.fils = charge.fils
            if self.materiel.moteur == "openvino":
                sur_puce = (self.materiel.peripherique_openvino or "CPU").upper() != "CPU"
                instance.proprietes = charge.ov_puce if sur_puce else charge.ov_processeur
            reglages["frein"] = rythme.Frein(regulateur, self._interrompu)
        regulateur.sur_puce = lambda: bool(getattr(instance, "sur_puce", False))
        if not regulateur.leger:
            journal.info("Rythme %s%s : %s fils, lots %s, priorité %s, qualité de service %s",
                         choisi, " (adaptation automatique)" if regulateur.auto else "",
                         charge.fils, reglages["lot"], charge.priorite, charge.qos)

        reussis, echoues, annules, sans_voix = 0, 0, 0, 0
        # Une transcription d'une heure et demie ne doit pas s'arrêter parce que
        # le portable se met en veille faute d'activité (le capot fermé, lui,
        # garde son effet : c'est un geste explicite).
        sans_veille = energie.sans_veille()
        sans_veille.__enter__()
        regulateur.demarrer(self._interrompu)
        try:
            for element in list(self.elements):
                if element.etat != "attente":
                    continue
                if self._interrompu():
                    # Arrêter interrompt le fichier en cours ; ceux qui n'ont
                    # pas commencé restent en attente, prêts pour le prochain
                    # lancement, au lieu de finir « annulés » sans issue.
                    break
                try:
                    if self._traiter(element, config, reglages, instance, rappels):
                        sans_voix += 1
                    reussis += 1
                except moteur.Interruption:
                    element.etat = "annule"
                    annules += 1
                    rappels.etat(element.identifiant, "annule", langues.t("etat.arrete"))
                    rappels.termine(element.identifiant, {"ok": False, "annule": True})
                except Exception as exc:
                    echoues += 1
                    element.etat = "erreur"
                    incident = journal.formater_incident(exc, element.nom)
                    rappels.etat(element.identifiant, "erreur", incident["titre"])
                    rappels.journal_ui("erreur", f"{element.nom} : {incident['titre']}")
                    rappels.termine(element.identifiant, {"ok": False, **incident})
                finally:
                    # Un fichier interrompu garde sa reprise, seul un succès
                    # l'efface : c'est tout l'intérêt de la sauvegarde.
                    self._session.fermer()
                    instance.liberer()
                    gc.collect()
        finally:
            instance.liberer()
            gc.collect()
            bilan_rythme = regulateur.arreter()
            sans_veille.__exit__(None, None, None)
            if regulateur.auto and bilan_rythme["bascules"]:
                durees = bilan_rythme["durees"]
                rappels.journal_ui("info", langues.t(
                    "rythme.bilan", rapide=presets.formater_duree(durees.get("vitesse", 0)),
                    discret=presets.formater_duree(sum(v for k, v in durees.items() if k != "vitesse")),
                    rythme=langues.t(f"rythme.nom.{choisi}")))
            self._en_cours = False
            rappels.file_terminee({
                "total": reussis + echoues + annules,
                "reussis": reussis,
                "echecs": echoues,
                "annules": annules,
                # Transcriptions réussies dont les voix n'ont pas été séparées
                # alors que c'était demandé.
                "voix_non_separees": sans_voix,
            })

    # -- traitement d'un fichier -------------------------------------------

    def _traiter(self, element: Element, config: dict, reglages: dict,
                 instance: moteur.MoteurTranscription, rappels: Rappels) -> bool:
        """Mène un fichier à son terme ; vrai si les voix demandées n'ont pas été séparées."""
        depart = time.time()
        source = Path(element.chemin)
        journal.info("=" * 60)
        journal.info("Fichier : %s", source)

        def signaler(niveau: str, texte: str) -> None:
            rappels.journal_ui(niveau, texte)

        # 1. Décodage
        element.etat = "decodage"
        rappels.etat(element.identifiant, "decodage", langues.t("etat.lecture"))
        signal = audio_module.decoder(source, filtres_salle=reglages["filtres_salle"])
        duree_audio = signal.size / audio_module.FREQUENCE
        element.duree = duree_audio
        signaler("info", langues.t(
            "trait.duree_audio", nom=element.nom,
            duree=presets.formater_duree(duree_audio)))

        # Fichier abîmé : FFmpeg lit ce qu'il peut et rend la main sans erreur.
        # La durée annoncée par le conteneur, mesurée à l'ajout, dit s'il manque
        # un morceau notable ; on le signale au lieu de le taire.
        annoncee = float(element.duree_annoncee or 0) or audio_module.duree(source)
        if annoncee > 60 and duree_audio < 0.90 * annoncee:
            journal.attention("Audio lu en partie : %.1f s sur %.1f s annoncées", duree_audio, annoncee)
            signaler("attention", langues.t(
                "trait.audio_partiel", nom=element.nom, lu=presets.formater_duree(duree_audio),
                annonce=presets.formater_duree(annoncee)))

        if self._interrompu():
            raise moteur.Interruption()

        # Mémoire libre du moment, en rythme équilibré ou discret : lots, puis
        # modèle plus léger si même un passage à la fois ne tient plus. Une
        # reprise garde son modèle, pour ne pas mêler deux modèles dans un texte.
        reglages = dict(reglages)
        choisi = (self._rythme or {}).get("choisi", "vitesse")
        if choisi != "vitesse":
            from . import materiel as materiel_module

            libre = materiel_module._memoire()[1]
            nom_moteur = "openvino" if self.materiel.moteur == "openvino" else "ctranslate2"
            # Le modèle léger n'est proposé que s'il est déjà sur le disque :
            # jamais de téléchargement que l'utilisateur n'a pas demandé.
            leger = presets.MODELE_TURBO
            depot_leger = presets.depot_openvino(leger) if nom_moteur == "openvino" else leger
            if element.reprise or bool(config.get("mode_avance")) or not moteur.modele_deja_telecharge(depot_leger):
                leger = ""
            modele, lot, raison = rythme.garde_memoire(
                choisi, nom_moteur, reglages["modele"], int(reglages.get("lot") or 0), libre, leger)
            if raison:
                journal.attention("Mémoire libre %.1f Go : %s", libre, raison)
                signaler("attention", langues.t(
                    f"rythme.memoire_{raison}", libre=langues.nombre(libre, 1),
                    modele=moteur.nom_court(modele)))
                reglages["modele"], reglages["lot"] = modele, lot

        # 1 bis. Sauvegarde progressive et reprise éventuelle.
        #
        # Le moteur livre déjà les segments un par un : les écrire au fil de
        # l'eau ne coûte qu'une ligne de texte par segment. En contrepartie, une
        # coupure ne fait plus perdre le calcul déjà fait, et le temps écoulé
        # est conservé pour que le compteur reparte où il s'était arrêté.
        session = self._session = reprise_module.session_inactive()
        deja_transcrits: list[moteur.Segment] = []
        decalage = 0.0
        ecoule_anterieur = 0.0
        # Seule la fin du signal repasse au modèle après une reprise. Le signal
        # COMPLET, lui, reste entier pour la séparation des locuteurs : ses tours
        # de parole doivent couvrir tout l'enregistrement et partir de zéro,
        # comme les horodatages des segments. Une vue numpy, aucune copie.
        a_transcrire = signal

        if element.reprise:
            etat_reprise = reprise_module.lire_etat(element.reprise) or {}
            deja_transcrits = reprise_module.lire_segments(element.reprise)
            if deja_transcrits:
                decalage = deja_transcrits[-1].fin
                ecoule_anterieur = float(etat_reprise.get("ecoule", 0) or 0)
                depart -= ecoule_anterieur
                a_transcrire = signal[int(decalage * audio_module.FREQUENCE):]
                signaler("info", langues.t(
                    "trait.reprise", nom=element.nom,
                    position=presets.formater_duree(decalage),
                    segments=len(deja_transcrits),
                    ecoule=presets.formater_duree(ecoule_anterieur),
                ))

        if config.get("sauvegarde_progressive", True):
            identifiant = element.reprise or reprise_module.cle(source, reglages["modele"])
            session = self._session = reprise_module.Session(identifiant, active=True)
            session.alerte = lambda _detail: signaler("attention", langues.t("trait.reprise_coupee"))
            session.ouvrir(
                source, reglages["modele"], duree_audio,
                position=decalage, nb_segments=len(deja_transcrits),
                ecoule=ecoule_anterieur,
            )
        elif element.reprise:
            # Reprise demandée mais sauvegarde coupée depuis : le travail déjà
            # fait est réutilisé, simplement plus rien de nouveau n'est protégé.
            signaler("attention", langues.t("trait.sauvegarde_coupee"))

        # 2. Transcription
        element.etat = "transcription"
        # Rythme équilibré ou discret : l'estimation de départ en tient compte
        # (adaptation automatique : celle du rythme choisi, la plus longue).
        # C'est la même fonction que pour les annonces de l'écran.
        estimation = presets.estimer_annonce(
            duree_audio,
            reglages["preset"],
            self.materiel,
            choisi,
            diarisation=diarisation.effective(config.get("diarisation")),
            modele_avance=reglages["modele"] if (
                config.get("mode_avance")
                or reglages["modele"] != presets.preset(reglages["preset"])["modele"]) else "",
            beam=int(reglages["beam_size"] or 0),
            lot=int(reglages.get("lot") or 0),
        )
        regulateur = (self._rythme or {}).get("regulateur")
        durees_avant = regulateur.releve_durees() if regulateur is not None else {}
        rappels.etat(element.identifiant, "transcription", langues.t("etat.transcription"))

        # Phase à part : le chargement prend de 20 à 45 s sur processeur. La
        # ligne le dit (barre indéterminée, horloge qui tourne côté interface)
        # au lieu d'afficher « Transcription » à 0 % sans signe de vie.
        rappels.progression(element.identifiant, {
            "pct": 0, "phase": langues.t("phase.chargement"), "indetermine": True,
            "ecoule": presets.formater_duree(time.time() - depart),
            "ecoule_s": round(time.time() - depart, 1), "restant": "", "restant_s": None,
        })
        debut_chargement = time.time()
        instance.charger(reglages["modele"], signaler)
        # Le pied de page montre la dernière ligne du journal : sans celle-ci,
        # il affichait « Chargement du modèle... » pendant toute la transcription.
        signaler("info", langues.t(
            "trait.modele_charge", duree=presets.formater_duree(time.time() - debut_chargement)))
        # Le calcul commence : la phase change tout de suite. Par lots, le
        # premier avancement n'arrive qu'à la fin du premier lot, parfois une
        # minute plus tard ; d'ici là, le reste à faire part de l'estimation.
        rappels.progression(element.identifiant, {
            "pct": 0, "phase": langues.t("phase.transcription"), "indetermine": True,
            "ecoule": presets.formater_duree(time.time() - depart),
            "ecoule_s": round(time.time() - depart, 1), "restant": "",
            "restant_s": round(estimation * (1.0 - decalage / duree_audio) if duree_audio else estimation, 1),
        })

        # Vocabulaire effectif : glossaire et corrections du format 1 encore en
        # place, fichiers partagés, puis vocabulaire personnel (format 2).
        voc, problemes_voc = vocabulaire_v2.effectif(config)
        for probleme in problemes_voc:
            signaler("attention", langues.t("trait.vocabulaire_probleme", detail=probleme))

        amorce_info = {"amorce": "", "nb_retenus": 0, "message": ""}
        amorce = ""
        if config.get("utiliser_glossaire", True):
            # L'en-tête de l'amorce suit la langue parlée : elle est lue par le
            # décodeur comme un début de texte, pas comme une consigne. Le nom
            # du fichier sert d'indice : les termes qu'il évoque passent devant.
            amorce = vocabulaire_usage.amorce(voc, tokeniseur=instance.tokeniseur,
                                              langue=config.get("langue", "fr"), contexte=source.stem)
            amorce_info = amorce.info
            if amorce_info["amorce"]:
                signaler("info", amorce_info["message"])
                if amorce_info["tronque"]:
                    signaler("attention", langues.t("trait.glossaire_tronque"))

        # Reste à faire : estimation de départ, puis cadence observée depuis le
        # début du calcul (le chargement du modèle n'y entre plus), le tout
        # lissé : l'heure de fin prévue bouge doucement au lieu de sauter de
        # dix minutes à deux en vingt secondes. Une reprise ne compte que ce
        # qui reste à transcrire.
        estimation_reste = estimation * (1.0 - decalage / duree_audio) if duree_audio else estimation
        lisseur = rythme.LisseurRestant()
        debut_transcription = time.time()
        # Point de départ du lissage : l'estimation annoncée à l'écran.
        lisseur(estimation_reste, debut_transcription)

        def progression(part: float) -> None:
            maintenant = time.time()
            ecoule = maintenant - depart
            part_transcription = 0.85 if diarisation.effective(config.get("diarisation")) else 1.0
            pourcent = int(part * part_transcription * 100)
            # Estimation au départ, puis cadence observée : elle suit d'elle-même
            # les bascules du rythme automatique.
            restant = lisseur(rythme.restant_s(
                estimation_reste, maintenant - debut_transcription, part), maintenant)
            effectif = getattr(regulateur, "effectif", "vitesse")
            rappels.progression(element.identifiant, {
                "pct": min(99, pourcent),
                "phase": (langues.t("phase.transcription") if effectif == "vitesse"
                          else langues.t("phase.transcription_rythme",
                                         rythme=langues.t(f"rythme.nom.{effectif}"))),
                "ecoule": presets.formater_duree(ecoule),
                "ecoule_s": round(ecoule, 1),
                "restant": (
                    presets.formater_duree(restant) if restant > 5
                    else langues.t("phase.bientot")
                ),
                "restant_s": round(restant, 1),
            })

        debut_transcription = time.time()
        segments, details = instance.transcrire(
            a_transcrire, duree_audio, config.get("langue", "fr"), reglages,
            amorce=amorce, progression=progression,
            interrompu=self._interrompu, decalage=decalage,
            sur_segment=lambda seg: session.ajouter(seg, time.time() - depart),
        )
        temps_transcription = time.time() - debut_transcription
        segments = deja_transcrits + segments
        session.fermer()

        # 2 bis. Recalibration à chaud des annonces de durée.
        #
        # On vient de mesurer, sur cette machine et sur un vrai fichier, ce que
        # coûte ce modèle : c'est infiniment plus juste que le facteur statique du
        # preset, relevé ailleurs. La mesure porte sur la transcription SEULE, le
        # décodage, le chargement du modèle et la séparation des locuteurs restant
        # dehors. Une reprise après coupure ne compte pas : son temps de calcul
        # est réparti sur deux exécutions.
        #
        # La mesure est rangée ramenée à la vitesse maximale : en rythme
        # équilibré ou discret, le calcul a duré plus longtemps à dessein, et
        # les annonces appliquent déjà le coefficient du rythme. Sans cette
        # division, il était compté deux fois (une transcription en « discret »
        # faisait annoncer « Rapide » plus lent que « Qualité maximale »).
        if not deja_transcrits:
            cle_calcul = getattr(instance, "cle_calcul", self.materiel.cle_calcul)
            sur_openvino = cle_calcul.startswith("openvino")
            ralenti = rythme.coefficient_effectif(
                durees_avant, regulateur.releve_durees() if regulateur is not None else {},
                choisi, cle_calcul)
            calibration.enregistrer(
                reglages["modele"], cle_calcul,
                1 if sur_openvino else int(reglages["beam_size"] or 0),
                duree_audio, temps_transcription / ralenti, self.materiel,
                lot=0 if sur_openvino else int(reglages.get("lot") or 0),
            )

        # 3. Libération AVANT la diarisation : c'est ce qui tient les 16 Go.
        instance.liberer()

        # 4. Diarisation, optionnelle et jamais bloquante
        nb_locuteurs = 0
        # Demandée mais pas installée : rien à tenter (c'est dit au lancement et
        # dans l'état final), et ni phase « séparation » ni barre bloquée à 85 %.
        if diarisation.effective(config.get("diarisation")) and segments:
            element.etat = "locuteurs"
            rappels.etat(element.identifiant, "locuteurs", langues.t("etat.locuteurs"))
            rappels.progression(element.identifiant, {
                "pct": 88, "phase": langues.t("etat.locuteurs"), "indetermine": True,
                "ecoule": presets.formater_duree(time.time() - depart),
                "ecoule_s": round(time.time() - depart, 1), "restant": "", "restant_s": None,
            })
            try:
                tours = diarisation.diariser(
                    signal, audio_module.FREQUENCE,
                    nb_locuteurs=int(config.get("nb_locuteurs") or 0),
                    signaler=signaler, interrompu=self._interrompu,
                )
                nb_locuteurs = diarisation.attribuer(segments, tours)
                signaler("ok", langues.t("trait.locuteurs_identifies", n=nb_locuteurs))
            except ErreurLisible as exc:
                journal.attention("Diarisation abandonnée : %s", exc.message)
                signaler("attention", langues.t(
                    "trait.diar_abandonnee", titre=exc.titre, message=exc.message))
            except Exception as exc:
                incident = journal.formater_incident(exc, "diarisation")
                signaler("attention", langues.t(
                    "trait.diar_incident", titre=incident["titre"]))

        del signal, a_transcrire
        gc.collect()

        # 5. Corrections post-transcription
        # Étage b du vocabulaire : fautes listées, graphie, rapprochement
        # phonétique borné. Chaque remplacement est noté dans le compagnon, pour
        # être montré et annulé dans la vue de relecture.
        remplacements = 0
        journal_remplacements: list[dict] = []
        if config.get("appliquer_corrections", True):
            _regles, erreurs = vocabulaire.analyser_corrections()
            for message in erreurs:
                signaler("attention", langues.t("trait.corrections_fichier", message=message))
            correcteur = vocabulaire_usage.Correcteur(
                voc, rapprochement=bool(config.get("rapprochement_vocabulaire", True)))
            journal_remplacements = correcteur.corriger_segments(segments)
            remplacements = len(journal_remplacements)
            if remplacements:
                signaler("ok", langues.t(
                    "trait.corrections_appliquees", n=remplacements))

        if self._interrompu():
            raise moteur.Interruption()

        # 6. Écriture
        element.etat = "ecriture"
        rappels.etat(element.identifiant, "ecriture", langues.t("etat.ecriture"))
        rappels.progression(element.identifiant, {
            "pct": 99, "phase": langues.t("etat.ecriture"),
            "ecoule": presets.formater_duree(time.time() - depart),
            "ecoule_s": round(time.time() - depart, 1), "restant": "", "restant_s": None,
        })
        temps_calcul = time.time() - depart
        details.update({
            "modele_lisible": moteur.nom_court(reglages["modele"]),
            "preset_nom": reglages["preset_nom"],
            "nb_locuteurs": nb_locuteurs,
            "diarisation_demandee": bool(config.get("diarisation")),
            "diarisation_absente": bool(config.get("diarisation"))
            and not diarisation.effective(True),
            "corrections_appliquees": remplacements,
            "remplacements_vocabulaire": journal_remplacements,
            "termes_amorce": amorce_info["nb_retenus"],
            "temps_calcul": temps_calcul,
            "facteur_reel": temps_calcul / duree_audio if duree_audio else 0,
        })

        dossier = Path(config.get("dossier_sortie") or ".")
        libre = journal.espace_disque_libre(dossier if dossier.exists() else dossier.parent)
        if 0 <= libre < 50 * 1024 * 1024:
            raise ErreurLisible(
                langues.t("err.disque.titre"),
                langues.t("trait.disque_plein.msg"),
            )

        produits = sorties.ecrire_tout(
            dossier, source, segments, details, config.get("formats", {"txt": True}),
            avec_compagnon=bool(config.get("compagnon_confiance", True)),
            motif=str(config.get("motif_sortie") or ""),
        )

        # Le fichier est écrit : la reprise n'a plus lieu d'être.
        session.effacer()
        element.reprise = ""

        element.etat = "termine"
        rappels.progression(element.identifiant, {
            "pct": 100, "phase": langues.t("phase.termine"),
            "ecoule": presets.formater_duree(temps_calcul),
            "ecoule_s": round(temps_calcul, 1), "restant": "", "restant_s": None,
        })
        rappels.etat(element.identifiant, "termine", langues.t("etat.termine"))
        rappels.journal_ui("ok", langues.t(
            "trait.termine", nom=element.nom,
            duree=presets.formater_duree(temps_calcul),
            facteur=langues.nombre(details["facteur_reel"], 2),
        ))
        rappels.termine(element.identifiant, {
            "ok": True,
            "sorties": produits,
            "duree": presets.formater_duree(temps_calcul),
            "facteur": round(details["facteur_reel"], 2),
            "locuteurs": nb_locuteurs,
            # Voix demandées mais non séparées (non installée, ou échec) : la
            # ligne et l'état final le disent, au lieu d'un « Terminé » tout vert.
            "voix_non_separees": bool(config.get("diarisation")) and not nb_locuteurs,
            "corrections": remplacements,
        })
        return bool(config.get("diarisation")) and not nb_locuteurs
