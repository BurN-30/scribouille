"""
Paquet portable et empreintes, à partir de ce que PyInstaller a construit.

    python packaging/empaqueter.py [--source dist/Scribouille] [--sortie packaging/sortie]

- `Scribouille-<version>-portable.zip` : le dossier `dist/Scribouille` tel
  quel, sous un dossier racine « Scribouille », sans modèle ni corpus (refusé
  s'il en trouve) ; Deflate niveau 6, fichiers dans l'ordre alphabétique ;
- `SHA256SUMS.txt` : l'empreinte SHA-256 de ce paquet et du programme
  d'installation de la même version s'il est déjà dans le dossier de sortie,
  au format de `sha256sum` (vérifiable par `sha256sum -c` ou, sous Windows,
  `Get-FileHash`).

La version est celle de `app/__init__.py`, seule source de vérité.
Même procédé que les paquets portables essayés avant la 3.0.0.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
#: Ce qui n'a rien à faire dans un paquet : modèles de transcription, corpus de mesure.
INTERDITS = ("corpus-campagne", "models--", "modeles")


def version() -> str:
    texte = (RACINE / "app" / "__init__.py").read_text(encoding="utf-8")
    trouve = re.search(r'^VERSION\s*=\s*"([^"]+)"', texte, re.MULTILINE)
    if not trouve:
        sys.exit("VERSION introuvable dans app/__init__.py")
    return trouve.group(1)


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def main() -> int:
    # Console d'un exécuteur ou d'un poste en page de code 1252 : rien ne doit casser à l'affichage.
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    analyse = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    analyse.add_argument("--source", default=str(RACINE / "dist" / "Scribouille"))
    analyse.add_argument("--sortie", default=str(RACINE / "packaging" / "sortie"))
    options = analyse.parse_args()
    v = version()
    source, sortie = Path(options.source).resolve(), Path(options.sortie).resolve()
    if not (source / "scribouille.com").is_file() or not (source / "Scribouille.exe").is_file():
        sys.exit(f"Pas de programme construit dans {source}")
    fichiers = sorted(p for p in source.rglob("*") if p.is_file())
    refuses = [p for p in fichiers if any(x in str(p.relative_to(source)).lower() for x in INTERDITS)]
    if refuses:
        sys.exit(f"Modèle ou corpus dans le paquet : {refuses[0].relative_to(source)}")
    sortie.mkdir(parents=True, exist_ok=True)
    paquet = sortie / f"Scribouille-{v}-portable.zip"
    with zipfile.ZipFile(paquet, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in fichiers:
            z.write(p, Path("Scribouille") / p.relative_to(source))
    print(f"{paquet.name} : {paquet.stat().st_size} octets, {len(fichiers)} fichiers, "
          f"{sum(p.stat().st_size for p in fichiers)} octets décompressés")
    lignes = []
    for nom in (f"Scribouille-Setup-{v}.exe", paquet.name):
        chemin = sortie / nom
        if chemin.is_file():
            lignes.append(f"{empreinte(chemin)}  {nom}")
    (sortie / "SHA256SUMS.txt").write_text("\n".join(lignes) + "\n", encoding="ascii", newline="\n")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
