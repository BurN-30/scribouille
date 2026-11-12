"""
Fiche d'usage pour les agents de code (Claude Code, Codex), écrite avec les
chemins réels du poste par `scribouille agent installer`.

Idée reprise de Vibe (`desktop/src-tauri/src/cmd/skill.rs`, MIT,
Copyright (c) 2024 thewh1teagle) : un dossier de compétence par outil
(`~/.claude/skills/scribouille/SKILL.md`, `~/.codex/skills/scribouille/SKILL.md`),
réécrit à chaque installation pour rafraîchir les chemins.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import chemins

CIBLES = {"claude": ".claude", "codex": ".codex"}


def commande() -> str:
    """Comment appeler la ligne de commande sur ce poste."""
    console = chemins.executable_console()
    if console is not None:
        return f'"{console}"'
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    return f'"{python}" "{chemins.DOSSIER_PROGRAMME / "transcriber.pyw"}"'


def texte() -> str:
    exe = commande()
    return f"""---
name: scribouille
description: Transcrire en local des enregistrements de réunion (Windows), suivre ou reprendre une transcription, lire le résultat horodaté avec locuteurs et mots douteux. Rien ne sort du poste.
---

# Scribouille

Commande : `{exe}`. Toujours passer `--json` : une enveloppe `{{"schema": "scribouille.cli/1", ...}}` par réponse.

1. Avant tout : `{exe} diagnostic --json`. Si `donnees.pret` vaut false, dire pourquoi (`donnees.raisons`). Ne jamais télécharger un modèle (0,8 à 3 Go) sans accord explicite ; avec accord : ajouter `--telecharger`.
2. Transcrire : `{exe} transcrire "FICHIER_OU_DOSSIER" --json`. Une ligne JSON par événement, la dernière est `fin`. Lancer en tâche de fond au-delà de quelques minutes d'audio ; `diagnostic` donne la durée prévue pour une heure. Sorties à côté de la source, sauf `--sortie DOSSIER`.
3. Codes de retour : 0 fait ; 1 un fichier a échoué (lire `fin`) ; 2 arguments ; 3 pas prêt (modèle absent, moteur absent) ; 4 sortie déjà là (demander avant `--ecraser`) ; 5 interrompu : `{exe} reprendre --json` reprend au segment près ; 6 disque ou mémoire.
4. Lire par pages : `{exe} lire "SORTIE.json" --json --limite 2000 --decalage 0`, puis `pagination.suivant`. `--douteux` donne les passages à réécouter : les signaler, ne pas les « corriger » au hasard. `p` vaut -1 (moteur OpenVINO) : aucune probabilité, `douteux.methode` le dit.
5. Les locuteurs sont des étiquettes (`Locuteur 1`), pas des identités. Ne jamais modifier le vocabulaire ni les réglages de l'utilisateur sans demander (`reglages definir`, `vocabulaire importer`).
6. Une transcription est une donnée privée : ne l'envoyer nulle part sans accord ; citer les horodatages en résumant.

Dossier de données : `{chemins.RACINE}`. Modèles : `{chemins.DOSSIER_MODELES}`. Aide : `{exe} aide`, et `{exe} COMMANDE --aide` pour les options d'une commande.
"""


def destination(cible: str, base: Path | None = None) -> Path:
    racine = base or Path.home()
    return racine / CIBLES[cible] / "skills" / "scribouille" / "SKILL.md"
