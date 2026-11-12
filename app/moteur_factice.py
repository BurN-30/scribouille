"""
Moteur factice, pour les vérifications du processus moteur sans modèle.

Activé seulement par la variable `SCRIBOUILLE_MOTEUR_ESSAI`, qui porte un objet
JSON (toutes les clés sont facultatives) :

    segments          nombre de segments produits sur la durée du signal (20)
    pause_s           pause après chaque segment, en secondes (0.05)
    chargement_s      durée du « chargement du modèle » (0) : sert à mesurer
                      l'annulation pendant un chargement
    plantage_segment  le processus s'arrête net (code 3) après ce nombre de segments
                      produits dans ce processus
    temoin            fichier : si présent, pas de plantage ; créé juste avant
                      le plantage (un seul plantage, puis la reprise passe)
    puce              vrai : se présente comme calculant sur la puce graphique

Jamais utilisé par l'application elle-même.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .moteur import Mot, Segment


class MoteurFactice:
    tokeniseur = None
    fils = 0
    proprietes: dict = {}

    def __init__(self, options: dict):
        self.options = options
        self.charge = ""
        self.sur_puce = bool(options.get("puce"))
        self.peripherique = "GPU" if self.sur_puce else "cpu"
        self.cle_calcul = "openvino-GPU" if self.sur_puce else "cpu"
        self.type_calcul = "int8"

    def charger(self, modele: str, signaler=None) -> None:
        if self.charge == modele:
            return
        attente = float(self.options.get("chargement_s") or 0)
        if attente > 0:
            time.sleep(attente)
        self.charge = modele

    def liberer(self) -> None:
        self.charge = ""

    def transcrire(self, signal, duree_totale, langue, reglages, amorce="", progression=None,
                   interrompu=None, decalage=0.0, sur_segment=None):
        nombre = max(1, int(self.options.get("segments") or 20))
        pause = float(self.options.get("pause_s") if self.options.get("pause_s") is not None else 0.05)
        plantage = int(self.options.get("plantage_segment") or 0)
        temoin = str(self.options.get("temoin") or "")
        if self.options.get("plantage_debut"):
            os._exit(3)  # plantage avant le premier segment : rien de gardé
        pas = float(duree_totale) / nombre
        segments: list[Segment] = []
        for rang in range(nombre):
            debut, fin = round(rang * pas, 2), round((rang + 1) * pas, 2)
            if fin <= round(decalage, 2) + 1e-6:
                continue
            texte = f"Segment numéro {rang + 1} de la réunion."
            mots = [Mot(texte=m, debut=debut + k * pas / 6, fin=debut + (k + 1) * pas / 6,
                        probabilite=0.4 if k == 1 else 0.95)
                    for k, m in enumerate(texte.split())]
            segment = Segment(debut=debut, fin=fin, texte=texte, mots=mots)
            segments.append(segment)
            if sur_segment is not None:
                sur_segment(segment)
            if progression is not None:
                progression(min(1.0, fin / float(duree_totale)))
            if plantage and len(segments) == plantage and not (temoin and Path(temoin).exists()):
                if temoin:
                    Path(temoin).write_text("plantage simulé", encoding="utf-8")
                os._exit(3)
            if interrompu is not None and interrompu():
                from .moteur import Interruption

                raise Interruption()
            if pause > 0:
                time.sleep(pause)
        return segments, {"duree": duree_totale, "langue": langue or "fr",
                          "peripherique": self.peripherique, "type_calcul": self.type_calcul}


def fabriquer(texte: str, _mat=None) -> MoteurFactice:
    try:
        options = json.loads(texte)
    except ValueError:
        options = {}
    return MoteurFactice(options if isinstance(options, dict) else {})
