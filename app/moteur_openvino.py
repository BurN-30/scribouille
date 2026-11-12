"""
Moteur OpenVINO (Intel), en option : processeur, puce graphique, NPU.

Pourquoi un second moteur
-------------------------
CTranslate2 ne calcule que sur processeur et sur carte NVIDIA. Sur un portable
Intel sans carte dédiée, la puce graphique intégrée et le NPU restent inertes
pendant que le processeur, bridé à 15 W, met parfois plus longtemps à
transcrire que la réunion n'a duré. OpenVINO GenAI (Intel, licence Apache-2.0)
fait tourner Whisper sur ces trois circuits, avec des modèles déjà convertis et
compressés en int8 par Intel (organisation « OpenVINO » de Hugging Face).

Mesures publiées, aucune sur la machine de développement (processeur AMD) :
large-v3-turbo à 0,12 fois la durée de l'audio sur la puce graphique d'un Core
Ultra 7 265U, contre 1,04 sur son processeur avec faster-whisper, texte
identique mot pour mot sur l'extrait comparé ; le NPU de la même machine a
bloqué avec turbo (ticket TalkTrack n° 131, octobre 2026). Sur processeur,
mesuré ici : 1,1 à 1,6 fois plus rapide que CTranslate2 par lots, à justesse
comparable (voir le CHANGELOG de la 2.4.0).

Ce que l'application garde, et comment
--------------------------------------
Le pipeline d'OpenVINO n'a pas de détection d'activité vocale, et Whisper
invente du texte sur le silence. On reprend donc le découpage de faster-whisper
(Silero VAD, livré avec lui) : les passages de parole sont réunis en fenêtres
de 30 s au plus, sans les silences, et chaque fenêtre est transcrite à part.
Cela donne tout le reste :

  - **segments horodatés** : les horodatages rendus par OpenVINO dans la
    fenêtre sont ramenés au temps de l'enregistrement d'origine ;
  - **horodatage des mots**, demandé au pipeline (`word_timestamps`), pour la
    séparation des locuteurs et la vue de relecture. OpenVINO ne donne pas la
    probabilité de chaque mot : la confiance est marquée inconnue (-1), et la
    vue de relecture n'en souligne aucun ;
  - **glossaire** : l'amorce est passée à chaque fenêtre (`initial_prompt`),
    comme le fait le traitement par lots de faster-whisper ;
  - **sauvegarde progressive et reprise** : chaque segment part dès la fin de
    sa fenêtre, le décalage de reprise s'applique comme avec l'autre moteur ;
  - **annulation** : vérifiée entre deux fenêtres, et pendant une fenêtre par
    le rappel de flux d'OpenVINO, qui interrompt la génération.

Décodage glouton par défaut : le faisceau de 5 coûtait 1,7 fois plus cher sans
gagner un mot sur les extraits de test (large-v3 : 8,03 % de WER en glouton,
8,27 % avec faisceau). Garde-fou des boucles de répétition, à la manière de
faster-whisper : une fenêtre dont le texte se compresse trop (taux > 2,4) est
refaite, avec un faisceau de 5 sur le processeur, et par échantillonnage à
température croissante (0,2, 0,4, 0,6) sur la puce graphique et le NPU.

Pas de faisceau sur la puce graphique ni sur le NPU
---------------------------------------------------
OpenVINO GenAI 2026.4 ne sait pas décoder Whisper en faisceau sur la puce
graphique : l'encodeur y rend un tenseur resté dans la mémoire du circuit
(`init_model`, whisper/pipeline.cpp), et le décodeur en faisceau le recopie
côté processeur pour chaque branche (`_set_encoder_hidden_states_tensor`,
whisper/models/decoder.cpp), ce qu'un tenseur distant refuse : « tensor.cpp:125
... iremote_tensor.hpp:32 Not Implemented », à chaque fois, dès la deuxième
étape du décodage. Ticket public n° 2746 d'openvino.genai ; corrigé sur la
branche principale le 22/09/2026 (PR 4498), pas dans la 2026.4, et la
correction laisse un défaut de justesse du faisceau sur la puce graphique en
précision par défaut (CVS-195124). Le NPU passe par un pipeline statique sans
faisceau. Le faisceau y est donc ramené à 1, quoi que demande le réglage, et le
garde-fou des répétitions n'y utilise jamais le faisceau : c'est lui qui, avant
la 2.4.1, faisait tomber une transcription en glouton sur la puce graphique
quand une fenêtre bouclait.

Le compilé pour la puce graphique ou le NPU est mis en cache sous les données
de l'utilisateur (`cache-openvino`) : la première ouverture coûte de quelques
dizaines de secondes à deux minutes, les suivantes quelques secondes.
"""

from __future__ import annotations

import gc
import importlib.util
import time
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable

from . import chemins, journal, langues, moteur, presets
from .journal import ErreurLisible
from .materiel import Materiel
from .moteur import Interruption, Mot, Segment

if TYPE_CHECKING:
    import numpy as np

FREQUENCE = 16000

#: Durée maximale d'une fenêtre, celle que Whisper sait lire d'un trait.
FENETRE_S = 30.0

#: Réglages du découpage, ceux de l'application en traitement par lots.
SILENCE_MIN_MS = 500

#: Taux de compression au-delà duquel une fenêtre est tenue pour une boucle de
#: répétition, comme `compression_ratio_threshold` dans faster-whisper.
SEUIL_COMPRESSION = 2.4

#: Jetons générés au plus par fenêtre : borne les boucles qui survivraient.
JETONS_MAX = 224

PERIPHERIQUES = ("GPU", "NPU", "CPU")

#: Périphériques où OpenVINO ne décode Whisper qu'en glouton (voir plus haut).
SANS_FAISCEAU = ("GPU", "NPU")

#: Températures du garde-fou des répétitions là où le faisceau manque, dans
#: l'ordre ; on s'arrête à la première fenêtre qui ne boucle plus.
TEMPERATURES_REPRISE = (0.2, 0.4, 0.6)

#: Graine de l'échantillonnage : la même fenêtre donne le même texte d'un
#: passage à l'autre.
GRAINE = 20261112


def faisceau_pris_en_charge(peripherique: str, faisceau: int) -> bool:
    """OpenVINO sait-il décoder avec ce faisceau sur ce périphérique ?"""
    return int(faisceau or 1) <= 1 or (peripherique or "CPU").upper() not in SANS_FAISCEAU


def faisceau_effectif(peripherique: str, faisceau: int) -> int:
    """Faisceau réellement appliqué : ramené à 1 là où il n'est pas pris en charge."""
    faisceau = max(1, int(faisceau or 1))
    return faisceau if faisceau_pris_en_charge(peripherique, faisceau) else 1

#: Témoin posé pendant l'ouverture d'un modèle sur la puce graphique ou le NPU,
#: effacé dès qu'elle a réussi ou échoué proprement. Une compilation qui échoue
#: peut faire tomber tout le processus au lieu de lever une exception (constaté :
#: violation d'accès dans le greffon GPU quand un cache de compilation est
#: demandé et que la compilation échoue). Un témoin resté en place au
#: démarrage suivant dit que c'est arrivé : le réglage OpenVINO est alors
#: suspendu (voir `reglage_machine`), au lieu de refaire tomber l'application.
TEMOIN_CHARGEMENT = chemins.RACINE / "openvino-chargement-en-cours.txt"


def chargement_interrompu() -> str:
    """Périphérique dont la dernière ouverture a fait tomber l'application, sinon vide."""
    try:
        return TEMOIN_CHARGEMENT.read_text(encoding="utf-8").strip() or "?"
    except OSError:
        return ""


def effacer_temoin() -> None:
    try:
        TEMOIN_CHARGEMENT.unlink(missing_ok=True)
    except OSError:
        pass

_peripheriques_vus: list[str] | None = None
#: Version gardée par la détection de fond (`materiel.json`), pour que la
#: fenêtre n'ait pas à importer OpenVINO pour l'afficher.
_version_vue: str | None = None
#: Premier lancement avec OpenVINO posé, rien de gardé : les périphériques sont
#: supposés tous présents le temps que la détection de fond les confirme (une
#: à deux secondes). Un réglage OpenVINO reste ainsi en place sans que la
#: fenêtre charge OpenVINO ; s'il n'est pas tenable, le rafraîchissement le
#: retire, et le repli vers CTranslate2 couvre une file lancée entre-temps.
_supposes = False


def amorcer(version_gardee: str, peripheriques: list[str]) -> None:
    """
    Reprend la version et les périphériques vus au lancement précédent (voir
    `materiel.detecter_au_demarrage`). Une détection forcée les remplace.
    """
    global _peripheriques_vus, _version_vue, _supposes
    _peripheriques_vus = [str(p).upper() for p in peripheriques if str(p).upper() in PERIPHERIQUES]
    _version_vue = version_gardee or None
    _supposes = False


def amorcer_provisoire() -> None:
    """Rien de gardé : périphériques supposés, en attendant la détection de fond."""
    global _peripheriques_vus, _version_vue, _supposes
    _peripheriques_vus, _version_vue, _supposes = None, None, True


def peripheriques_confirmes() -> bool:
    return not _supposes


def installe() -> bool:
    """Les paquets d'OpenVINO sont-ils importables ? Test léger, sans import."""
    return importlib.util.find_spec("openvino_genai") is not None


def version() -> str:
    if _version_vue:
        return _version_vue
    if _supposes:
        return ""
    try:
        import openvino_genai as ov_genai  # type: ignore

        return str(ov_genai.__version__).split("-")[0]
    except Exception:
        return ""


def peripheriques_disponibles(forcer: bool = False) -> list[str]:
    """
    Périphériques qu'OpenVINO voit sur ce poste : « CPU », « GPU », « NPU ».

    Liste vide si OpenVINO n'est pas installé. Le résultat est gardé : la
    question coûte une seconde ou deux à la première ouverture des pilotes.
    """
    global _peripheriques_vus, _supposes
    if _peripheriques_vus is not None and not forcer:
        return list(_peripheriques_vus)
    if _supposes and not forcer:
        return list(PERIPHERIQUES)
    _supposes = False
    trouves: list[str] = []
    if installe():
        try:
            import openvino as ov  # type: ignore

            coeur = ov.Core()
            for nom in coeur.available_devices:
                famille = str(nom).split(".")[0].upper()
                if famille not in PERIPHERIQUES or famille in trouves:
                    continue
                if famille == "GPU":
                    # Le greffon GPU énumère tous les circuits OpenCL, y compris
                    # ceux d'AMD, sur lesquels ses noyaux ne compilent pas
                    # (CL_BUILD_PROGRAM_FAILURE, constaté sur une Radeon) : on ne
                    # garde que les puces Intel, les seules qu'il prenne en charge.
                    try:
                        description = str(coeur.get_property(nom, "FULL_DEVICE_NAME"))
                    except Exception:
                        description = ""
                    if "intel" not in description.lower():
                        continue
                trouves.append(famille)
        except Exception as exc:
            journal.attention("OpenVINO ne liste aucun périphérique : %s", exc)
    _peripheriques_vus = trouves
    return list(trouves)


def nom_peripherique(peripherique: str) -> str:
    """Nom lisible du périphérique, dans la langue de l'interface."""
    return langues.t(f"ov.peripherique.{(peripherique or 'CPU').lower()}")


def _passes_encodeur(resultat) -> int:
    """Nombre de passages de l'encodeur pour une fenêtre (1 en temps normal)."""
    try:
        return len(resultat.perf_metrics.whisper_raw_metrics.encode_inference_durations)
    except Exception:
        return 1


def _taux_compression(texte: str) -> float:
    octets = texte.encode("utf-8")
    if not octets:
        return 0.0
    return len(octets) / len(zlib.compress(octets))


# ---------------------------------------------------------------------------
# Découpage en fenêtres
# ---------------------------------------------------------------------------

def decouper(signal: np.ndarray) -> list[list[dict]]:
    """
    Passages de parole regroupés en fenêtres de 30 s au plus.

    Chaque fenêtre est une liste de passages {"start", "end"} en échantillons,
    dans le temps du signal reçu. Un signal sans parole donne une liste vide.
    """
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    passages = get_speech_timestamps(
        signal, VadOptions(max_speech_duration_s=FENETRE_S,
                           min_silence_duration_ms=SILENCE_MIN_MS),
        sampling_rate=FREQUENCE)
    fenetres: list[list[dict]] = []
    courante: list[dict] = []
    duree = 0
    limite = int(FENETRE_S * FREQUENCE)
    for passage in passages:
        longueur = passage["end"] - passage["start"]
        if courante and duree + longueur > limite:
            fenetres.append(courante)
            courante, duree = [], 0
        courante.append(passage)
        duree += longueur
    if courante:
        fenetres.append(courante)
    return fenetres


class Correspondance:
    """Ramène un temps de la fenêtre (silences retirés) au temps du signal."""

    def __init__(self, passages: list[dict]):
        self.debuts: list[float] = []
        self.cumuls: list[float] = []
        self.longueurs: list[float] = []
        cumul = 0.0
        for passage in passages:
            longueur = (passage["end"] - passage["start"]) / FREQUENCE
            self.debuts.append(passage["start"] / FREQUENCE)
            self.cumuls.append(cumul)
            self.longueurs.append(longueur)
            cumul += longueur
        self.duree = cumul

    def index(self, temps: float) -> int:
        for rang in range(len(self.cumuls) - 1, -1, -1):
            if temps >= self.cumuls[rang]:
                return rang
        return 0

    def origine(self, temps: float, rang: int | None = None) -> float:
        if not self.debuts:
            return 0.0
        temps = min(max(0.0, temps), self.duree)
        if rang is None:
            rang = self.index(temps)
        local = min(max(0.0, temps - self.cumuls[rang]), self.longueurs[rang])
        return self.debuts[rang] + local


# ---------------------------------------------------------------------------
# Le moteur
# ---------------------------------------------------------------------------

class MoteurOpenVINO:
    """Même contrat que `moteur.MoteurTranscription`, sur OpenVINO GenAI."""

    def __init__(self, mat: Materiel, peripherique: str = "GPU"):
        self.materiel = mat
        self.peripherique_ov = (peripherique or "CPU").upper()
        self._pipeline = None
        self._tokeniseur = None
        self._nom_modele = ""
        self._mots = True
        #: Témoin d'ouverture : posé par l'application, pas par le banc d'essai,
        #: dont chaque essai tourne déjà dans un processus à part.
        self.temoin = False
        #: Propriétés de compilation ajoutées par le rythme (priorité de file
        #: de la puce graphique, fils du processeur : voir `app/rythme.py`).
        #: Refusées par le pilote, elles sont abandonnées et le journal le dit.
        self.proprietes: dict = {}

    @property
    def peripherique(self) -> str:
        return "openvino-" + self.peripherique_ov.lower()

    cle_calcul = peripherique

    @property
    def type_calcul(self) -> str:
        return "int8"

    @property
    def tokeniseur(self):
        return self._tokeniseur

    def charger(self, modele: str, signaler: Callable[[str, str], None] | None = None) -> None:
        if self._pipeline is not None and self._nom_modele == modele:
            return
        self.liberer()
        depot = presets.depot_openvino(modele) or (modele if moteur.est_modele_openvino(modele) else "")
        if not depot:
            raise ErreurLisible(langues.t("ov.modele_absent.titre"),
                                langues.t("ov.modele_absent.msg", modele=moteur.nom_court(modele)))
        chemins.assurer_dossiers()
        etat = moteur.assurer_modele_telecharge(depot, moteur.etat_modele(depot), signaler)
        dossier = etat.get("snapshot") or etat.get("dossier")

        import openvino_genai as ov_genai  # type: ignore

        cache = chemins.RACINE / "cache-openvino"
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if signaler:
            signaler("info", langues.t(
                "ov.chargement", modele=moteur.nom_court(modele),
                peripherique=nom_peripherique(self.peripherique_ov)))
        journal.info("Chargement OpenVINO %s sur %s (%s)", depot, self.peripherique_ov, dossier)
        base = {"CACHE_DIR": str(cache)}
        temoin = self.temoin and self.peripherique_ov != "CPU"
        if temoin:
            try:
                TEMOIN_CHARGEMENT.write_text(self.peripherique_ov, encoding="utf-8")
            except OSError:
                temoin = False
        essais = [{**base, **self.proprietes}, base] if self.proprietes else [base]
        try:
            for rang, proprietes in enumerate(essais):
                try:
                    self._ouvrir(ov_genai, str(dossier), proprietes)
                    if self.proprietes:
                        journal.info("OpenVINO : propriétés du rythme %s",
                                     "appliquées" if rang == 0 else "refusées, ouverture sans elles")
                    break
                except Exception as exc:
                    if rang == len(essais) - 1:
                        raise
                    journal.attention("OpenVINO refuse les propriétés du rythme (%s) : %s",
                                      ", ".join(sorted(self.proprietes)), exc)
        finally:
            if temoin:
                effacer_temoin()
        try:
            from tokenizers import Tokenizer

            self._tokeniseur = Tokenizer.from_file(str(Path(dossier) / "tokenizer.json"))
        except Exception as exc:
            journal.debug("Tokeniseur du glossaire indisponible : %s", exc)
            self._tokeniseur = None
        self._nom_modele = modele

    def _ouvrir(self, ov_genai, dossier: str, proprietes: dict) -> None:
        try:
            self._pipeline = ov_genai.WhisperPipeline(
                dossier, self.peripherique_ov, word_timestamps=True, **proprietes)
            self._mots = True
        except Exception as exc:
            # Les horodatages de mots demandent une décomposition de
            # l'attention que certains périphériques refusent : on retente
            # sans, plutôt que de renoncer au périphérique.
            journal.attention("OpenVINO sans horodatage des mots sur %s : %s",
                              self.peripherique_ov, exc)
            self._pipeline = ov_genai.WhisperPipeline(dossier, self.peripherique_ov, **proprietes)
            self._mots = False

    def liberer(self) -> None:
        if self._pipeline is None:
            return
        journal.info("Libération du modèle OpenVINO %s", self._nom_modele)
        self._pipeline = None
        self._tokeniseur = None
        self._nom_modele = ""
        gc.collect()

    def _config(self, langue: str | None, faisceau: int, amorce: str, temperature: float = 0.0):
        config = self._pipeline.get_generation_config()
        config.task = "transcribe"
        config.language = f"<|{langue}|>" if langue else None
        config.return_timestamps = True
        config.word_timestamps = self._mots
        config.num_beams = max(1, int(faisceau))
        config.max_new_tokens = JETONS_MAX
        if temperature > 0:
            # Échantillonnage sur une seule séquence : aucune recopie de l'état
            # de l'encodeur, donc permis sur la puce graphique (vérifié sur
            # processeur : accepté avec l'horodatage des mots).
            config.num_beams = 1
            config.do_sample = True
            config.temperature = float(temperature)
            config.top_p = 1.0
            config.top_k = 0
            config.rng_seed = GRAINE
        if amorce:
            config.initial_prompt = amorce
        return config

    def _garde_repetition(self, morceau, resultat, texte: str, langue: str | None, amorce: str,
                          flux, mode: str, bilan: dict):
        """
        Refait une fenêtre qui boucle ; garde la version qui se compresse le moins.

        `mode` : « faisceau » ou « temperature », « auto » choisit selon le
        périphérique. Un échec de la reprise n'emporte pas la transcription :
        la première version est gardée, et l'échec est compté.
        """
        bilan["fenetres_repetitives"] += 1
        if mode == "auto":
            mode = "faisceau" if faisceau_pris_en_charge(self.peripherique_ov, 5) else "temperature"
        taux = _taux_compression(texte)
        essais = [(5, 0.0)] if mode == "faisceau" else [(1, t) for t in TEMPERATURES_REPRISE]
        journal.attention("Fenêtre répétitive (taux %.2f), refaite (%s)", taux,
                          "faisceau de 5" if mode == "faisceau" else "température")
        meilleur, meilleur_taux = resultat, taux
        try:
            for faisceau, temperature in essais:
                second = self._pipeline.generate(
                    morceau, self._config(langue, faisceau, amorce, temperature), streamer=flux)
                bilan["reprises"] += 1
                taux_second = _taux_compression((second.texts[0] if second.texts else "") or "")
                if taux_second < meilleur_taux:
                    meilleur, meilleur_taux = second, taux_second
                if meilleur_taux <= SEUIL_COMPRESSION:
                    break
        except Exception as exc:
            bilan["echecs_garde"] += 1
            bilan["erreur_garde"] = f"{type(exc).__name__}: {exc}"[:300]
            journal.exception("Reprise d'une fenêtre répétitive impossible, première version gardée", exc)
        return meilleur

    def transcrire(
        self,
        signal: np.ndarray,
        duree_totale: float,
        langue: str,
        reglages: dict,
        amorce: str = "",
        progression: Callable[[float], None] | None = None,
        interrompu: Callable[[], bool] | None = None,
        decalage: float = 0.0,
        sur_segment: Callable[[Segment], None] | None = None,
    ) -> tuple[list[Segment], dict]:
        if self._pipeline is None:
            raise ErreurLisible(langues.t("moteur.non_charge.titre"),
                                langues.t("moteur.non_charge.msg"))
        import openvino_genai as ov_genai  # type: ignore

        import numpy as np

        signal = np.ascontiguousarray(signal, dtype=np.float32)
        demande = int(reglages.get("faisceau_openvino") or 1)
        faisceau = faisceau_effectif(self.peripherique_ov, demande)
        if faisceau != demande:
            journal.attention("Faisceau de %s non pris en charge par OpenVINO sur %s : décodage glouton",
                              demande, self.peripherique_ov)
        # « auto » en temps normal ; l'épreuve d'endurance force l'ancien
        # comportement pour le diagnostic (voir `app/endurance.py`).
        mode_garde = str(reglages.get("garde_repetition") or "auto")
        bilan = {"fenetres_repetitives": 0, "reprises": 0, "echecs_garde": 0, "erreur_garde": ""}
        langue_fixee = None if (not langue or langue == "auto") else langue
        fenetres = decouper(signal) if signal.size else []
        journal.info(
            "Transcription OpenVINO : %s, langue=%s, faisceau=%s, %s fenêtre(s), amorce=%s caractères",
            self.peripherique_ov, langue or "auto", faisceau, len(fenetres), len(amorce))

        def arret() -> bool:
            return bool(interrompu is not None and interrompu())

        def flux(_morceau) -> "ov_genai.StreamingStatus":
            return ov_genai.StreamingStatus.CANCEL if arret() else ov_genai.StreamingStatus.RUNNING

        segments: list[Segment] = []
        langue_detectee = langue_fixee or ""
        plafond = 0
        # Rythme « je travaille en même temps » : pause après chaque fenêtre,
        # à proportion de son calcul (voir app/rythme.py). Seul levier qui se
        # change à chaud sur la puce graphique.
        frein = reglages.get("frein")
        if frein is not None:
            frein.depart()
        # Amorce du vocabulaire refaite fenêtre par fenêtre quand il déborde du
        # budget : les termes que la fenêtre précédente évoque passent devant
        # (voir app/vocabulaire_usage.py). Une chaîne simple reste fixe.
        texte_precedent = ""
        for fenetre in fenetres:
            if arret():
                journal.attention("Transcription interrompue à la demande de l'utilisateur")
                raise Interruption()
            correspondance = Correspondance(fenetre)
            morceau = np.concatenate([signal[p["start"]:p["end"]] for p in fenetre])
            amorce_fenetre = (amorce.pour_fenetre(texte_precedent) if hasattr(amorce, "pour_fenetre")
                              else amorce)
            resultat = self._pipeline.generate(
                morceau, self._config(langue_fixee, faisceau, amorce_fenetre), streamer=flux)
            if arret():
                journal.attention("Transcription interrompue à la demande de l'utilisateur")
                raise Interruption()
            texte = (resultat.texts[0] if resultat.texts else "") or ""
            if _passes_encodeur(resultat) > 1:
                # OpenVINO a repris le décodage au dernier horodatage complet,
                # sans l'amorce du glossaire : plafond de jetons atteint, ou
                # dernière phrase annoncée comme continuant au-delà de la fenêtre.
                plafond += 1
            if faisceau == 1 and _taux_compression(texte) > SEUIL_COMPRESSION:
                resultat = self._garde_repetition(morceau, resultat, texte, langue_fixee, amorce_fenetre,
                                                  flux, mode_garde, bilan)
                if arret():
                    journal.attention("Transcription interrompue à la demande de l'utilisateur")
                    raise Interruption()
            if not langue_fixee:
                # Langue détectée sur la première fenêtre, puis gardée : une
                # réunion ne change pas de langue d'une fenêtre à l'autre, et
                # Whisper hésite sur les fenêtres courtes.
                # Les résultats d'OpenVINO GenAI 2026 portent une liste
                # « languages » (une par texte) ; « language » n'existe pas.
                detectees = list(getattr(resultat, "languages", None) or [])
                brute = detectees[0] if detectees else getattr(resultat, "language", "")
                langue_fixee = str(brute or "").strip("<|>") or None
                langue_detectee = langue_fixee or ""
            texte_precedent = ""
            for segment in self._segments(resultat, correspondance, decalage):
                segments.append(segment)
                texte_precedent += " " + segment.texte
                if sur_segment is not None:
                    sur_segment(segment)
            if progression and duree_totale > 0:
                fin_fenetre = fenetre[-1]["end"] / FREQUENCE + decalage
                progression(min(0.99, fin_fenetre / duree_totale))
            if frein is not None:
                frein()

        if progression:
            progression(1.0)
        details = {
            "langue": langue_detectee or langue,
            "probabilite_langue": 0.0,
            "duree": float(duree_totale),
            "modele": self._nom_modele,
            "peripherique": self.peripherique,
            "type_calcul": self.type_calcul,
            "moteur": "openvino",
            "fenetres_plafond": plafond,
            "faisceau": faisceau,
            **bilan,
        }
        journal.info("Transcription OpenVINO terminée : %s segments", len(segments))
        return segments, details

    def _segments(self, resultat, correspondance: Correspondance,
                  decalage: float) -> list[Segment]:
        """Segments de la fenêtre, horodatages ramenés au temps d'origine."""
        morceaux = list(getattr(resultat, "chunks", None) or [])
        mots_bruts = list(getattr(resultat, "words", None) or []) if self._mots else []
        if not morceaux:
            texte = (resultat.texts[0] if resultat.texts else "").strip()
            if not texte:
                return []
            morceaux = [SimpleNamespace(start_ts=0.0, end_ts=correspondance.duree, text=texte)]

        mots: list[tuple[float, Mot]] = []
        for brut in mots_bruts:
            texte = (getattr(brut, "word", "") or "").strip()
            if not texte:
                continue
            debut, fin = float(brut.start_ts), float(brut.end_ts)
            rang = correspondance.index((debut + fin) / 2)
            mots.append(((debut + fin) / 2, Mot(
                texte=texte,
                debut=correspondance.origine(debut, rang) + decalage,
                fin=correspondance.origine(fin, rang) + decalage,
                probabilite=-1.0,
            )))

        segments: list[Segment] = []
        for numero, morceau in enumerate(morceaux):
            texte = (morceau.text or "").strip()
            if not texte:
                continue
            debut = float(morceau.start_ts)
            fin = float(morceau.end_ts)
            if fin < 0 or fin < debut:
                fin = correspondance.duree
            # Les mots d'un segment : ceux dont le milieu tombe dans ses bornes.
            # Le dernier segment ramasse ce qui dépasse.
            dernier = numero == len(morceaux) - 1
            propres = [m for milieu, m in mots
                       if debut - 0.05 <= milieu < fin + 0.05 or (dernier and milieu >= debut)]
            pris = {id(m) for m in propres}
            mots = [(milieu, m) for milieu, m in mots if id(m) not in pris]
            if propres:
                origine_debut, origine_fin = propres[0].debut, propres[-1].fin
            else:
                origine_debut = correspondance.origine(debut) + decalage
                origine_fin = correspondance.origine(fin, correspondance.index(max(debut, fin - 0.01))) + decalage
            segments.append(Segment(
                debut=origine_debut, fin=max(origine_debut, origine_fin),
                texte=texte, mots=propres))
        return segments


# ---------------------------------------------------------------------------
# Repli sur CTranslate2
# ---------------------------------------------------------------------------

class MoteurAvecRepli:
    """
    OpenVINO d'abord, CTranslate2 si OpenVINO lâche. Même contrat que les deux.

    Un pilote graphique trop ancien, un NPU qui ne compile pas le modèle, un
    dépôt OpenVINO que le pare-feu bloque, un périphérique perdu en cours de
    route : aucune de ces pannes ne doit coûter une transcription.

    Un raté isolé ne doit pas non plus coûter la vitesse : à la première erreur,
    à l'ouverture comme en cours de transcription, le pipeline est libéré,
    recréé après une courte pause, et le travail repris sur le même
    périphérique (en cours de transcription : à la fin du dernier segment
    sorti, donc la fenêtre en cours est rejouée, rien de ce qui est déjà
    transcrit n'est refait ni perdu). Si l'erreur revient, on bascule sur
    CTranslate2, qui reprend au même endroit, et on le dit. Un seul rejeu par
    ouverture et par fichier : une panne qui se répète n'est pas un raté.

    `incidents` garde la trace de chaque erreur, sans texte transcrit, pour
    l'épreuve d'endurance (`app/endurance.py`).
    """

    #: Pause entre la libération du pipeline et sa recréation, le temps que le
    #: pilote graphique rende la mémoire du pipeline tombé.
    PAUSE_RECREATION_S = 3.0

    def __init__(self, mat: Materiel, peripherique: str):
        self.materiel = mat
        self._ov = MoteurOpenVINO(mat, peripherique)
        self._ov.temoin = True
        self._ct2 = moteur.MoteurTranscription(mat)
        self._actif = self._ov
        self._modele = ""
        self._signaler: Callable[[str, str], None] | None = None
        self.incidents: list[dict] = []

    @property
    def peripherique(self) -> str:
        return self._actif.peripherique

    @property
    def fils(self) -> int:
        return self._ct2.fils

    @fils.setter
    def fils(self, valeur: int) -> None:
        """Fils du repli sur CTranslate2 (rythme), comme pour le moteur seul."""
        self._ct2.fils = int(valeur or 0)

    @property
    def proprietes(self) -> dict:
        return self._ov.proprietes

    @proprietes.setter
    def proprietes(self, valeur: dict) -> None:
        self._ov.proprietes = dict(valeur or {})

    @property
    def sur_puce(self) -> bool:
        return self._actif is self._ov and self._ov.peripherique_ov != "CPU"

    @property
    def cle_calcul(self) -> str:
        return self._actif.peripherique

    @property
    def type_calcul(self) -> str:
        return self._actif.type_calcul

    @property
    def tokeniseur(self):
        return self._actif.tokeniseur

    @property
    def sur_openvino(self) -> bool:
        return self._actif is self._ov

    def _noter(self, phase: str, cause: BaseException, issue: str) -> None:
        self.incidents.append({"phase": phase, "issue": issue,
                               "erreur": f"{type(cause).__name__}: {cause}"[:300]})

    def _basculer(self, cause: BaseException) -> None:
        journal.attention("Repli sur CTranslate2 : %s: %s", type(cause).__name__, cause)
        if self._signaler:
            self._signaler("attention", langues.t(
                "ov.repli", peripherique=nom_peripherique(self._ov.peripherique_ov)))
        self._ov.liberer()
        self._actif = self._ct2
        self._ct2.charger(self._modele, self._signaler)

    def _adouci(self, niveau: str, texte: str) -> None:
        # Une panne d'OpenVINO n'est pas une erreur du fichier : le rejeu, puis
        # le repli, prennent le relais juste après.
        if self._signaler:
            self._signaler("attention" if niveau == "erreur" else niveau, texte)

    def _rouvrir(self) -> None:
        """Libère le pipeline OpenVINO, laisse le pilote souffler, le recrée."""
        self._ov.liberer()
        gc.collect()
        if self.PAUSE_RECREATION_S > 0:
            time.sleep(self.PAUSE_RECREATION_S)
        self._ov.charger(self._modele, self._adouci)

    def charger(self, modele: str, signaler: Callable[[str, str], None] | None = None) -> None:
        self._modele = modele
        self._signaler = signaler
        if self._actif is self._ct2:
            self._ct2.charger(modele, signaler)
            return
        try:
            self._ov.charger(modele, self._adouci)
            return
        except Exception as exc:
            premiere = exc
        journal.exception("Ouverture OpenVINO en échec, nouvel essai après une pause", premiere)
        try:
            self._rouvrir()
        except Exception as exc:
            self._noter("ouverture", premiere, "repli")
            self._basculer(exc)
            return
        self._noter("ouverture", premiere, "rejeu_reussi")
        journal.info("Ouverture OpenVINO réussie au second essai")
        if signaler:
            signaler("info", langues.t("ov.rejeu_ouverture",
                                       peripherique=nom_peripherique(self._ov.peripherique_ov)))

    def liberer(self) -> None:
        self._ov.liberer()
        self._ct2.liberer()

    def transcrire(self, signal, duree_totale, langue, reglages, amorce="",
                   progression=None, interrompu=None, decalage=0.0, sur_segment=None):
        if self._actif is self._ct2:
            return self._ct2.transcrire(signal, duree_totale, langue, reglages, amorce,
                                        progression, interrompu, decalage, sur_segment)
        recus: list[Segment] = []

        def relais(segment: Segment) -> None:
            recus.append(segment)
            if sur_segment is not None:
                sur_segment(segment)

        rejoue = False
        position = decalage
        while True:
            debut = max(0, int(round((position - decalage) * FREQUENCE)))
            try:
                _segments, details = self._ov.transcrire(
                    signal[debut:], duree_totale, langue, reglages, amorce,
                    progression, interrompu, position, relais)
                details["rejeux_openvino"] = int(rejoue)
                if rejoue and self.incidents:
                    self.incidents[-1]["issue"] = "rejeu_reussi"
                return list(recus), details
            except Interruption:
                raise
            except Exception as exc:
                cause = exc
            journal.exception("OpenVINO a échoué en cours de transcription", cause)
            position = recus[-1].fin if recus else decalage
            if rejoue:
                self._noter("transcription", cause, "repli")
                break
            rejoue = True
            journal.attention("Pipeline OpenVINO recréé, reprise à %.1f s sur %s",
                              position, self._ov.peripherique_ov)
            if self._signaler:
                self._signaler("attention", langues.t(
                    "ov.rejeu", peripherique=nom_peripherique(self._ov.peripherique_ov),
                    position=presets.formater_duree(position)))
            try:
                self._rouvrir()
            except Exception as exc:
                self._noter("transcription", cause, "repli")
                cause = exc
                break
            self._noter("transcription", cause, "rejeu")

        self._basculer(cause)
        debut = max(0, int(round((position - decalage) * FREQUENCE)))
        suite, details = self._ct2.transcrire(
            signal[debut:], duree_totale, langue, reglages, amorce,
            progression, interrompu, position, sur_segment)
        details["rejeux_openvino"] = int(rejoue)
        details["repli_ctranslate2"] = True
        return recus + suite, details
