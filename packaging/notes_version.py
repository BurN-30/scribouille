"""
Notes de version d'une Release : la section de CHANGELOG.md qui porte le
numéro publié, suivie des empreintes SHA-256 des fichiers joints.

    python packaging/notes_version.py VERSION [--empreintes SHA256SUMS.txt]
        [--sortie notes-version.md] [--publication]

Une seule source : aucun texte recopié à la main dans la Release. La section va
du titre « ## VERSION » au titre de niveau 2 suivant ; le séparateur « --- »
qui la clôt n'est pas repris. `--publication` (chaîne de publication, sur un
tag) refuse une section absente ou encore marquée « non publiée » : mieux vaut
arrêter que publier des notes fausses. Sans lui (essais), c'est un avertissement.

Les versions installées relisent ce texte (app/maj.py) : il ne doit contenir le
marqueur [reinstallation-requise] que si la version l'exige vraiment.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def section(texte: str, version: str) -> str | None:
    lignes = texte.splitlines()
    debut = None
    fin = len(lignes)
    for i, ligne in enumerate(lignes):
        if debut is None:
            if re.fullmatch(rf"##\s+{re.escape(version)}\s*", ligne):
                debut = i + 1
        elif re.match(r"##\s", ligne):
            fin = i
            break
    if debut is None:
        return None
    corps = lignes[debut:fin]
    while corps and corps[-1].strip() in ("", "---"):
        corps.pop()
    return "\n".join(corps).strip()


def main() -> int:
    # Console d'un exécuteur ou d'un poste en page de code 1252 : rien ne doit casser à l'affichage.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    analyse = argparse.ArgumentParser(description="Notes de version tirées de CHANGELOG.md.")
    analyse.add_argument("version")
    analyse.add_argument("--changelog", default=str(RACINE / "CHANGELOG.md"))
    analyse.add_argument("--empreintes", default="")
    analyse.add_argument("--sortie", default="notes-version.md")
    analyse.add_argument("--publication", action="store_true")
    options = analyse.parse_args()

    corps = section(Path(options.changelog).read_text(encoding="utf-8"), options.version)
    problemes = []
    if corps is None:
        problemes.append(f"aucune section « ## {options.version} » dans {options.changelog}")
        corps = "Voir CHANGELOG.md."
    elif "non publiée" in corps.split("\n\n", 1)[0].lower():
        problemes.append("la section se dit encore « non publiée »")
    for probleme in problemes:
        print(("Erreur : " if options.publication else "Avertissement : ") + probleme, file=sys.stderr)
    if problemes and options.publication:
        return 1

    if options.empreintes:
        empreintes = Path(options.empreintes).read_text(encoding="ascii").strip()
        corps += ("\n\n### Empreintes SHA-256\n\n```\n" + empreintes + "\n```\n\n"
                  "Vérifier un fichier téléchargé, dans PowerShell : "
                  "`Get-FileHash .\\NOM-DU-FICHIER -Algorithm SHA256`.")
    Path(options.sortie).write_text(corps + "\n", encoding="utf-8", newline="\n")
    print(corps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
