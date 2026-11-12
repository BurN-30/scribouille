"""
Vérification du parcours de l'utilisateur, sans fenêtre et sans transcription.

Ce que l'on fait d'une transcription une fois écrite, et ce que l'écran en dit :
relecture, corrections, fichiers produits, file d'attente, annonces de durée.
Chaque essai fabrique ses propres segments, comme le moteur les rend, dans un
dossier temporaire effacé à la fin : aucun modèle n'est chargé, le glossaire et
les corrections de l'utilisateur ne sont jamais touchés.

    .venv\\Scripts\\python outils\\verifier_parcours.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import chemins, langues, lecture, sorties  # noqa: E402
from app.moteur import Mot, Segment  # noqa: E402

# Les contrôles comparent des chaînes produites par l'application.
langues.definir("fr")

_reussites = 0
_echecs: list[str] = []


def verifier(condition: bool, libelle: str, detail: str = "") -> None:
    global _reussites
    if condition:
        _reussites += 1
        print(f"  OK    {libelle}")
    else:
        _echecs.append(libelle)
        print(f"  ECHEC {libelle}" + (f" : {detail}" if detail else ""))


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * len(texte))


def segment(debut: float, fin: float, jetons: list[tuple[str, float]], locuteur: str = "") -> Segment:
    """
    Un segment tel que faster-whisper le rend : le texte du segment, et ses mots
    avec l'espace qui les précède (« L », « 'Amazon »), ici retirée comme le
    fait le moteur de l'application.
    """
    texte = "".join(j for j, _ in jetons).strip()
    pas = (fin - debut) / max(1, len(jetons))
    mots = [Mot(j.strip(), debut + i * pas, debut + (i + 1) * pas, p)
            for i, (j, p) in enumerate(jetons) if j.strip()]
    return Segment(debut, fin, texte, locuteur, mots)


def jetons(phrase: str, p: float = 0.9) -> list[tuple[str, float]]:
    """Découpe une phrase comme le fait Whisper : élisions et traits d'union à part."""
    import re

    morceaux = re.findall(r" ?[\w…]+|[-'’][\w]+|[.,!?…:;]+| ?\S", phrase)
    return [(m, p) for m in morceaux]


def ecrire(dossier: Path, segments: list[Segment], formats: dict | None = None,
           details: dict | None = None) -> Path:
    source = dossier / "reunion equipe.m4a"
    source.write_bytes(b"\0" * 64)
    produits = sorties.ecrire_tout(
        dossier / "sorties", source, segments,
        {"duree": 120.0, "modele": "large-v3", "langue": "fr", "temps_calcul": 30.0,
         **(details or {})},
        formats or {"txt": True}, avec_compagnon=True)
    return Path(produits[0]["chemin"])


# ---------------------------------------------------------------------------
# Corrections depuis la relecture
# ---------------------------------------------------------------------------

def essai_entete_apres_correction(base: Path) -> None:
    titre("Une correction ne touche que le mot corrigé, pas l'en-tête")
    dossier = base / "entete"
    dossier.mkdir()
    txt = ecrire(dossier, [segment(0.0, 4.0, jetons("Bonjour à tous, voici le projet Garfam."))])
    avant = txt.read_text(encoding="utf-8")
    retour = lecture.appliquer_correction(txt, "Garfam", "GAFAM", ajouter_regle=False)
    apres = txt.read_text(encoding="utf-8")
    verifier(retour.get("ok") is True, "correction appliquée", str(retour))
    verifier(apres == avant.replace("Garfam", "GAFAM"),
             "le fichier ne diffère que du mot corrigé, saut de ligne après l'en-tête compris",
             repr(apres[apres.rfind("=" * 20) - 5:][:120]))


def principal() -> int:
    print(f"Vérification du parcours de l'utilisateur\n{'=' * 42}")
    with tempfile.TemporaryDirectory(prefix="scribouille-parcours-") as brut:
        base = Path(brut)
        # Les règles apprises vont dans un fichier jetable, jamais dans celui
        # de l'utilisateur.
        chemins.FICHIER_CORRECTIONS = base / "corrections.txt"
        essai_entete_apres_correction(base)

    print(f"\n{'=' * 42}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
