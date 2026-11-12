"""
Protocole entre la fenêtre (ou la ligne de commande) et le processus moteur.

Transport : une ligne JSON par message (UTF-8, `\\n`), ordres sur l'entrée
standard du moteur, réponses et événements sur sa sortie standard. Pas de port
réseau (rien à ouvrir dans un pare-feu, rien à protéger par un jeton), pas de
fichier partagé : le canal vit et meurt avec le processus, et une fin de flux
dit au moteur que son parent est parti. La sortie standard du moteur est
réservée au protocole : au démarrage, le descripteur 1 est redirigé vers
l'erreur standard, pour qu'une bibliothèque C qui écrit sur stdout ne puisse
pas casser une ligne.

Chaque message est un objet `{"type": ..., ...}`. Le moteur annonce la version
du protocole dans son premier message (`pret`) ; le parent refuse une version
qu'il ne connaît pas. Une nouvelle clé dans un message ne change pas la
version ; une clé retirée ou un sens changé, si.

Ordres (parent vers moteur), chacun avec un numéro `n` repris dans la réponse :

    ouvrir   {config}            prépare une file : réglages, rythme, moteur de calcul
                                 (le modèle se charge au premier fichier)
    traiter  {element}           un fichier, jusqu'au bout ; réponse `fini`
                                 element : id, chemin, nom, taille, duree, duree_annoncee,
                                 reprise (clé, vide sinon), sortie (dossier, vide : réglages)
    fermer   {}                  fin de file : modèle rendu, rythme rendu ; réponse `ferme`
    durees   {elements}          durées annoncées par les en-têtes ; réponse `durees`
    quitter  {}                  le moteur sort (code 0)

Événements (moteur vers parent) :

    pret         {protocole, version, pid}        premier message, une fois prêt à lire
    vie          {}                               toutes les 5 s, preuve de vie
    moteur       {etat, modele, peripherique, sur_puce}
                 etat : chargement | pret | transcription | libere
    etat         {id, etat, message}              phase d'un fichier (attente, decodage, ...)
    progression  {id, donnees}                    pourcentage, phase, écoulé, reste
    journal      {niveau, texte}                  ligne pour l'utilisateur (déjà traduite)
    reprise      {id, cle}                        sauvegarde progressive ouverte pour ce fichier
    termine      {id, donnees}                    fin d'un fichier, comme le rappel historique
    ouvert / ferme / fini / durees                réponses, avec le `n` de l'ordre
    erreur       {n, message}                     ordre illisible ou incident hors fichier

L'annulation n'est pas un ordre : le parent arrête le processus (moins d'une
seconde quelle que soit la phase, chargement ou compilation comprise). Ce qui a
été transcrit est déjà sur le disque, segment par segment (`app/reprise.py`).

Le motif (un seul propriétaire du processus fils, délais de garde, nouvel
essai sans la puce graphique après une panne) est repris de Handy
(`src-tauri/src/engine_supervisor`, MIT, Copyright (c) 2025 CJ Pais), recodé
en Python.
"""

from __future__ import annotations

import json

#: Version du protocole. À changer seulement si un message perd une clé ou change de sens.
VERSION = 1

ORDRES = ("ouvrir", "traiter", "fermer", "durees", "quitter")
EVENEMENTS = ("pret", "vie", "moteur", "etat", "progression", "journal", "reprise", "termine",
              "ouvert", "ferme", "fini", "durees", "erreur")

#: Intervalle des preuves de vie du moteur, en secondes.
INTERVALLE_VIE_S = 5.0


def encoder(message: dict) -> bytes:
    """Une ligne JSON terminée par un saut de ligne, en UTF-8."""
    return (json.dumps(message, ensure_ascii=False, separators=(",", ":"), default=str) + "\n").encode("utf-8")


def decoder(ligne: bytes | str) -> dict | None:
    """Le message d'une ligne, ou None si elle n'est pas un objet JSON avec un type."""
    if isinstance(ligne, bytes):
        ligne = ligne.decode("utf-8", "replace")
    ligne = ligne.strip()
    if not ligne:
        return None
    try:
        message = json.loads(ligne)
    except ValueError:
        return None
    if not isinstance(message, dict) or not isinstance(message.get("type"), str):
        return None
    return message
