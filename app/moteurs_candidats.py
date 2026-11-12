"""
Moteurs de mesure des modèles candidats, hors de l'application.

Pourquoi
--------
La campagne (`app/campagne.py`) compare des réglages de l'application :
CTranslate2 et OpenVINO, large-v3 et turbo. Pour savoir si un modèle plus
récent vaut d'être intégré, il faut le passer sur le même corpus, avec la même
normalisation et le même calcul d'erreurs, AVANT d'écrire la moindre ligne
d'intégration. Ce module fournit deux moteurs minimalistes à cet effet :

  - « onnx-asr » : ONNX Runtime par la bibliothèque onnx-asr (MIT), pour les
    modèles NVIDIA Parakeet TDT 0.6B v3 et Canary 1B v2 exportés en ONNX ;
  - « transformers » : PyTorch par transformers, pour Cohere Transcribe.

Ils n'entrent pas dans l'application : ni l'interface, ni la file, ni
`--appliquer` ne les connaissent. Leurs paquets ne sont pas dans
`requirements.txt` : la campagne les lance avec l'interprète désigné par la
variable d'environnement SCRIBOUILLE_PYTHON_CANDIDATS (un environnement à part
où sont installés torch, transformers 5.5, onnx-asr et onnxruntime, en plus des
dépendances du socle).

Découpage, le même pour les deux : le détecteur de parole de faster-whisper
(Silero, celui que le traitement par lots de CTranslate2 utilise déjà) repère
les passages de parole ; les passages voisins sont regroupés en fenêtres d'au
plus 30 s, silences intermédiaires compris, et chaque fenêtre est transcrite
d'un bloc. Un segment par fenêtre, sans mots horodatés : la campagne ne mesure
que le texte.
"""

from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Callable

import numpy as np

from . import journal
from .moteur import Segment

FREQUENCE = 16000
#: Durée maximale d'une fenêtre transcrite d'un bloc, en secondes.
FENETRE_MAX_S = 30.0
#: Silence minimal entre deux passages de parole, comme dans le moteur CTranslate2.
SILENCE_MIN_MS = 500


def fenetres(signal: np.ndarray) -> list[tuple[int, int]]:
    """Fenêtres (début, fin) en échantillons, d'au plus FENETRE_MAX_S, calées sur la parole."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    passages = get_speech_timestamps(
        signal, VadOptions(min_silence_duration_ms=SILENCE_MIN_MS, max_speech_duration_s=FENETRE_MAX_S))
    groupes: list[tuple[int, int]] = []
    limite = int(FENETRE_MAX_S * FREQUENCE)
    for passage in passages:
        debut, fin = int(passage["start"]), int(passage["end"])
        if groupes and fin - groupes[-1][0] <= limite:
            groupes[-1] = (groupes[-1][0], fin)
        else:
            groupes.append((debut, fin))
    return groupes


class _MoteurParFenetres:
    """Socle commun : découpage, segments, détails, libération."""

    type_calcul = ""

    def __init__(self, fils: int = 0):
        self.fils = int(fils or 0)
        self.peripherique = "cpu"
        self._modele = None
        self._nom_modele = ""

    @property
    def tokeniseur(self):
        return None

    def liberer(self) -> None:
        if self._modele is None:
            return
        journal.info("Libération du modèle candidat %s", self._nom_modele)
        self._modele = None
        self._nom_modele = ""
        gc.collect()

    def _reconnaitre(self, morceaux: list[np.ndarray], langue: str) -> list[str]:
        raise NotImplementedError

    def transcrire(self, signal: np.ndarray, duree_totale: float, langue: str, reglages: dict,
                   amorce: str = "", progression: Callable[[float], None] | None = None,
                   **_inutile) -> tuple[list[Segment], dict]:
        if self._modele is None:
            raise RuntimeError("modèle candidat non chargé")
        signal = np.ascontiguousarray(signal, dtype=np.float32)
        decoupage = fenetres(signal)
        lot = max(1, int(reglages.get("lot_candidat") or 4))
        segments: list[Segment] = []
        for rang in range(0, len(decoupage), lot):
            paquet = decoupage[rang:rang + lot]
            textes = self._reconnaitre([signal[a:b] for a, b in paquet], langue or "fr")
            for (a, b), texte in zip(paquet, textes):
                texte = " ".join(str(texte or "").split())
                if texte:
                    segments.append(Segment(debut=a / FREQUENCE, fin=b / FREQUENCE, texte=texte))
            if progression and duree_totale > 0:
                progression(min(0.99, paquet[-1][1] / FREQUENCE / duree_totale))
        return segments, {"langue": langue, "duree": duree_totale, "modele": self._nom_modele,
                          "peripherique": self.peripherique, "type_calcul": self.type_calcul,
                          "fenetres": len(decoupage)}


class MoteurOnnxAsr(_MoteurParFenetres):
    """Parakeet TDT v3 ou Canary v2 exportés en ONNX, poids int8, ONNX Runtime sur le processeur."""

    type_calcul = "int8"

    def __init__(self, fils: int = 0, nom_onnx_asr: str = ""):
        super().__init__(fils)
        self.nom_onnx_asr = nom_onnx_asr

    def charger(self, modele: str, signaler=None) -> None:
        import onnx_asr  # type: ignore
        import onnxruntime as rt  # type: ignore

        options = rt.SessionOptions()
        if self.fils:
            options.intra_op_num_threads = self.fils
        debut = time.perf_counter()
        self._modele = onnx_asr.load_model(self.nom_onnx_asr, str(modele), quantization="int8",
                                           sess_options=options, providers=["CPUExecutionProvider"])
        self._nom_modele = Path(str(modele)).name
        journal.info("Candidat onnx-asr %s chargé en %.1f s", self.nom_onnx_asr, time.perf_counter() - debut)

    def _reconnaitre(self, morceaux: list[np.ndarray], langue: str) -> list[str]:
        options = {"language": langue} if self.nom_onnx_asr.startswith("nemo-canary") else {}
        return list(self._modele.recognize(morceaux, sample_rate=FREQUENCE, **options))


class MoteurTransformers(_MoteurParFenetres):
    """
    Modèles servis nativement par transformers, en float32 sur le processeur :
    Cohere Transcribe (transformers ≥ 5.4) et Qwen3-ASR (≥ 5.13). La famille se
    lit dans la configuration du modèle. Qwen3-ASR reçoit le glossaire en
    contexte (`prompt`) ; Cohere n'a pas d'équivalent.
    """

    type_calcul = "float32"

    def charger(self, modele: str, signaler=None) -> None:
        import json

        import torch  # type: ignore
        import transformers  # type: ignore

        if self.fils:
            torch.set_num_threads(self.fils)
        self._torch = torch
        config = json.loads((Path(str(modele)) / "config.json").read_text(encoding="utf-8"))
        self.famille = str(config.get("model_type") or "")
        self._processeur = transformers.AutoProcessor.from_pretrained(str(modele))
        if self.famille == "qwen3_asr":
            classe = transformers.AutoModelForMultimodalLM
        else:
            classe = transformers.CohereAsrForConditionalGeneration
        self._modele = classe.from_pretrained(str(modele), dtype=torch.float32).eval()
        self._nom_modele = Path(str(modele)).name

    def transcrire(self, signal, duree_totale, langue, reglages, amorce="", progression=None, **_inutile):
        self._amorce = amorce
        return super().transcrire(signal, duree_totale, langue, reglages, amorce, progression)

    def _reconnaitre(self, morceaux: list[np.ndarray], langue: str) -> list[str]:
        with self._torch.inference_mode():
            if self.famille == "qwen3_asr":
                options = {"prompt": self._amorce} if getattr(self, "_amorce", "") else {}
                entrees = self._processeur.apply_transcription_request(
                    audio=list(morceaux), language=[langue] * len(morceaux), **options)
                longueur = entrees["input_ids"].shape[1]
                sorties = self._modele.generate(**entrees, max_new_tokens=448)
                return list(self._processeur.decode(sorties[:, longueur:], return_format="transcription_only"))
            entrees = self._processeur(morceaux, sampling_rate=FREQUENCE, return_tensors="pt", language=langue)
            index = entrees.get("audio_chunk_index")
            sorties = self._modele.generate(**entrees, max_new_tokens=256)
            textes = self._processeur.decode(sorties, skip_special_tokens=True, audio_chunk_index=index,
                                             language=langue)
        return [textes] if isinstance(textes, str) else list(textes)

    def liberer(self) -> None:
        self._processeur = None
        super().liberer()


def creer(moteur: str, fils: int = 0, nom_onnx_asr: str = ""):
    if moteur == "onnx-asr":
        return MoteurOnnxAsr(fils, nom_onnx_asr)
    if moteur == "transformers":
        return MoteurTransformers(fils)
    raise ValueError(f"moteur candidat inconnu : {moteur}")
