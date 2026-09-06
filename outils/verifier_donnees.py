"""
Vérification de l'import et de l'export des données personnelles.

Le panneau « Mes données » écrit par-dessus le glossaire, les corrections, le
gabarit d'instructions et les réglages de l'utilisateur. C'est l'endroit du
programme où une erreur se paye le plus cher : ce contrôle éprouve donc le
chemin complet, export puis relecture puis import, sans interface ni réseau.

Huit contrôles :

  1. EXPORT : l'archive contient le glossaire, les corrections, les réglages,
     et le gabarit quand il existe. Le manifeste annonce le format 2.
  2. EXPORT SANS GABARIT : le membre est simplement absent, l'archive reste
     valide et le manifeste ne l'annonce pas.
  3. APERÇU : une archive porteuse d'un gabarit le signale avant toute
     écriture, une archive qui n'en porte pas n'en parle pas.
  4. IMPORT COMPLET : glossaire, corrections et gabarit sont remplacés, et
     l'import le dit dans ses notes.
  5. ARCHIVE DE FORMAT 1 : elle s'importe toujours, et laisse en place le
     gabarit de ce poste. Ce qu'une archive ne transporte pas, elle ne le
     remplace pas.
  6. ARCHIVE DE FORMAT 2 SANS GABARIT : même règle.
  7. FORMAT TROP RÉCENT : une archive de format 3 est refusée, avec le message
     prévu pour cela.
  8. FILET : la sauvegarde automatique écrite avant un import emporte bien le
     gabarit courant, sans quoi le retour en arrière serait incomplet.

Rien n'est touché en dehors d'un dossier temporaire : les fichiers personnels
du poste qui exécute ce contrôle ne sont ni lus ni écrits.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python outils\\verifier_donnees.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import NOM_APPLICATION, VERSION, chemins, donnees, langues  # noqa: E402

_echecs: list[str] = []
_reussites = 0


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


# ---------------------------------------------------------------------------
# Bac à sable
# ---------------------------------------------------------------------------

GLOSSAIRE = "Valenciennes\nCTranslate2\nScribouille\n"
CORRECTIONS = "valencienne => Valenciennes\n"
GABARIT = "# gabarit de contrôle\nCompte rendu de {fichier} :\n\n{texte}\n"


def installer_bac(bac: Path) -> None:
    """Déplace tous les fichiers de données vers le dossier temporaire."""
    chemins.RACINE = bac
    chemins.FICHIER_CONFIG = bac / "config.json"
    chemins.FICHIER_VOCABULAIRE = bac / "vocabulaire.txt"
    chemins.FICHIER_CORRECTIONS = bac / "corrections.txt"
    chemins.FICHIER_GABARIT_IA = bac / "gabarit-ia.txt"
    # Les messages comparés sont ceux du catalogue français : la langue de
    # Windows sur le poste qui exécute ce contrôle ne doit pas les changer.
    langues.definir("fr")


def poser_donnees(gabarit: str | None = GABARIT) -> None:
    chemins.FICHIER_VOCABULAIRE.write_text(GLOSSAIRE, encoding="utf-8")
    chemins.FICHIER_CORRECTIONS.write_text(CORRECTIONS, encoding="utf-8")
    chemins.FICHIER_GABARIT_IA.unlink(missing_ok=True)
    if gabarit is not None:
        chemins.FICHIER_GABARIT_IA.write_text(gabarit, encoding="utf-8")


def membres(archive: Path) -> list[str]:
    with zipfile.ZipFile(str(archive)) as zip_ouvert:
        return sorted(zip_ouvert.namelist())


def manifeste_de(archive: Path) -> dict:
    with zipfile.ZipFile(str(archive)) as zip_ouvert:
        return json.loads(zip_ouvert.read(donnees.NOM_MANIFESTE).decode("utf-8"))


def fabriquer_archive(cible: Path, format_archive: int, contenus: dict,
                      application: str = NOM_APPLICATION) -> Path:
    """
    Écrit une archive à la main, pour éprouver la relecture d'un autre format.

    Une archive de format 1 est ce que produit la version 2.1.0 : elle ne
    connaît pas le gabarit. On la reconstitue plutôt que de la simuler.
    """
    manifeste = {
        "application": application,
        "format": format_archive,
        "version": "2.1.0" if format_archive == 1 else VERSION,
        "date": "2026-08-18T09:00:00",
        "fichiers": sorted(contenus.keys()),
        "exclus": ["jeton_hf.txt", "logs", "modeles"],
    }
    with zipfile.ZipFile(str(cible), "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            donnees.NOM_MANIFESTE, json.dumps(manifeste, indent=2, ensure_ascii=False) + "\n"
        )
        for nom, contenu in contenus.items():
            archive.writestr(nom, contenu)
    return cible


# ---------------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------------

def essai_export(bac: Path) -> Path:
    titre("[1] Export d'un poste qui a un gabarit")

    poser_donnees()
    cible = bac / "export-avec-gabarit.zip"
    resultat = donnees.exporter(cible)
    verifier(resultat.get("ok") is True, "export réussi", str(resultat.get("message")))
    verifier(cible.is_file(), "archive écrite", cible.name)

    dedans = membres(cible)
    verifier(donnees.FICHIER_GABARIT in dedans, "gabarit-ia.txt joint à l'archive",
             ", ".join(dedans))
    verifier(
        {"vocabulaire.txt", "corrections.txt", "config.json", donnees.NOM_MANIFESTE}
        <= set(dedans),
        "glossaire, corrections, réglages et manifeste toujours joints",
    )

    manifeste = manifeste_de(cible)
    verifier(manifeste.get("format") == 2, "manifeste en format 2",
             str(manifeste.get("format")))
    verifier(donnees.FICHIER_GABARIT in manifeste.get("fichiers", []),
             "gabarit déclaré dans le manifeste")
    verifier("jeton_hf.txt" not in dedans, "le jeton Hugging Face reste hors de l'archive")
    return cible


def essai_export_sans_gabarit(bac: Path) -> Path:
    titre("[2] Export d'un poste qui n'a pas de gabarit")

    poser_donnees(gabarit=None)
    cible = bac / "export-sans-gabarit.zip"
    resultat = donnees.exporter(cible)
    verifier(resultat.get("ok") is True, "export réussi", str(resultat.get("message")))

    dedans = membres(cible)
    verifier(donnees.FICHIER_GABARIT not in dedans, "aucun gabarit joint",
             ", ".join(dedans))
    manifeste = manifeste_de(cible)
    verifier(manifeste.get("format") == 2, "manifeste en format 2 malgré tout")
    verifier(donnees.FICHIER_GABARIT not in manifeste.get("fichiers", []),
             "gabarit absent du manifeste")

    apercu = donnees.analyser(cible)
    verifier(apercu.get("ok") is True, "archive sans gabarit acceptée",
             str(apercu.get("message")))
    return cible


def essai_apercu(avec: Path, sans: Path) -> None:
    titre("[3] Aperçu avant écriture")

    apercu = donnees.analyser(avec)
    verifier(apercu.get("ok") is True, "archive lue", str(apercu.get("message")))
    gabarit_apercu = apercu.get("gabarit") or {}
    verifier(gabarit_apercu.get("present") is True, "gabarit signalé dans l'aperçu")
    verifier("gabarit personnalisé" in str(gabarit_apercu.get("message", "")).lower(),
             "l'aperçu nomme le gabarit personnalisé",
             str(gabarit_apercu.get("message")))

    muet = (donnees.analyser(sans).get("gabarit") or {})
    verifier(muet.get("present") is False, "aucun gabarit annoncé quand il n'y en a pas")
    verifier(not muet.get("message"), "et rien à afficher")


def essai_import_complet(bac: Path, archive: Path) -> None:
    titre("[4] Import d'une archive de format 2 avec gabarit")

    poser_donnees(gabarit="Gabarit de ce poste, à remplacer.\n")
    chemins.FICHIER_VOCABULAIRE.write_text("Terme local\n", encoding="utf-8")

    resultat = donnees.importer(archive)
    verifier(resultat.get("ok") is True, "import appliqué", str(resultat.get("message")))
    verifier("Valenciennes" in chemins.FICHIER_VOCABULAIRE.read_text(encoding="utf-8"),
             "glossaire remplacé")
    verifier("valencienne =>" in chemins.FICHIER_CORRECTIONS.read_text(encoding="utf-8"),
             "corrections remplacées")
    gabarit_final = chemins.FICHIER_GABARIT_IA.read_text(encoding="utf-8")
    verifier("Compte rendu de {fichier}" in gabarit_final, "gabarit remplacé", gabarit_final[:60])
    verifier(any("abarit" in note for note in resultat.get("notes", [])),
             "l'import signale le gabarit repris", " | ".join(resultat.get("notes", [])))
    verifier(Path(resultat.get("sauvegarde", "")).is_file(), "sauvegarde préalable écrite")


def essai_format_1(bac: Path) -> None:
    titre("[5] Archive de format 1, produite par la version 2.1.0")

    poser_donnees(gabarit="Gabarit de ce poste, à conserver.\n")
    archive = fabriquer_archive(bac / "format-1.zip", 1, {
        "vocabulaire.txt": "Terme venu du format 1\n",
        "corrections.txt": "faute => correction\n",
        "config.json": json.dumps({"theme": "sombre"}, ensure_ascii=False),
    })

    apercu = donnees.analyser(archive)
    verifier(apercu.get("ok") is True, "archive de format 1 acceptée",
             str(apercu.get("message")))
    verifier((apercu.get("gabarit") or {}).get("present") is False,
             "aucun gabarit annoncé pour un format 1")

    resultat = donnees.importer(archive)
    verifier(resultat.get("ok") is True, "import de format 1 appliqué",
             str(resultat.get("message")))
    verifier("Terme venu du format 1" in chemins.FICHIER_VOCABULAIRE.read_text(encoding="utf-8"),
             "glossaire du format 1 repris")
    verifier(chemins.FICHIER_GABARIT_IA.read_text(encoding="utf-8")
             == "Gabarit de ce poste, à conserver.\n",
             "le gabarit de ce poste n'est pas effacé")


def essai_format_2_sans_gabarit(bac: Path) -> None:
    titre("[6] Archive de format 2 sans gabarit")

    poser_donnees(gabarit="Gabarit de ce poste, à conserver aussi.\n")
    archive = fabriquer_archive(bac / "format-2-nu.zip", 2, {
        "vocabulaire.txt": "Terme venu du format 2\n",
        "corrections.txt": "erreur => correction\n",
    })

    resultat = donnees.importer(archive)
    verifier(resultat.get("ok") is True, "import appliqué", str(resultat.get("message")))
    verifier(chemins.FICHIER_GABARIT_IA.read_text(encoding="utf-8")
             == "Gabarit de ce poste, à conserver aussi.\n",
             "gabarit intact, le membre était absent")


def essai_archive_ancien_nom(bac: Path) -> None:
    """
    Une archive exportée avant le renommage de la 2.4.0 se réimporte.

    Son manifeste annonce « WhiScribe ». Le refuser rendrait inutilisables
    toutes les sauvegardes déjà faites, ce qui est exactement ce qu'un export
    de données sert à éviter.
    """
    titre("[7] Archive exportée sous l'ancien nom de l'application")

    poser_donnees()
    archive = fabriquer_archive(bac / "ancien-nom.zip", 2, {
        "vocabulaire.txt": "Terme venu de WhiScribe\n",
        "corrections.txt": "faute => correction\n",
        "config.json": json.dumps({"theme": "clair"}, ensure_ascii=False),
    }, application="WhiScribe")

    apercu = donnees.analyser(archive)
    verifier(apercu.get("ok") is True, "archive au nom « WhiScribe » acceptée",
             str(apercu.get("message")))

    resultat = donnees.importer(archive)
    verifier(resultat.get("ok") is True, "import de l'archive ancienne appliqué",
             str(resultat.get("message")))
    verifier("Terme venu de WhiScribe" in chemins.FICHIER_VOCABULAIRE.read_text(encoding="utf-8"),
             "glossaire de l'archive ancienne repris")

    # La garde ne tombe pas pour autant : un export d'un autre logiciel reste refusé.
    etrangere = fabriquer_archive(bac / "etrangere.zip", 2, {
        "vocabulaire.txt": "peu importe\n",
    }, application="UnAutreLogiciel")
    refus = donnees.analyser(etrangere)
    verifier(refus.get("ok") is False, "une archive d'un autre logiciel reste refusée")


def essai_format_trop_recent(bac: Path) -> None:
    titre("[8] Archive de format 3, refusée")

    archive = fabriquer_archive(bac / "format-3.zip", 3, {
        "vocabulaire.txt": "Terme venu du futur\n",
    })
    resultat = donnees.analyser(archive)
    verifier(resultat.get("ok") is False, "archive de format 3 refusée")
    attendu = langues.t("arch.format_recent", application=NOM_APPLICATION, format=3,
                        lu=donnees.FORMAT_ARCHIVE)
    verifier(resultat.get("message") == attendu, "message de refus inchangé",
             str(resultat.get("message")))

    intrus = bac / "intrus.zip"
    fabriquer_archive(intrus, 2, {"vocabulaire.txt": "Terme\n"})
    with zipfile.ZipFile(str(intrus), "a") as archive_ouverte:
        archive_ouverte.writestr("jeton_hf.txt", "hf_secret")
    refus = donnees.analyser(intrus)
    verifier(refus.get("ok") is False, "membre inattendu toujours refusé",
             str(refus.get("message")))


def essai_filet(bac: Path) -> None:
    titre("[9] Sauvegarde automatique avant import")

    poser_donnees(gabarit="Gabarit à sauvegarder avant tout.\n")
    archive = fabriquer_archive(bac / "pour-le-filet.zip", 2, {
        "vocabulaire.txt": "Autre terme\n",
    })
    resultat = donnees.importer(archive)
    verifier(resultat.get("ok") is True, "import appliqué", str(resultat.get("message")))

    sauvegarde = Path(resultat.get("sauvegarde", ""))
    verifier(sauvegarde.is_file(), "sauvegarde écrite", sauvegarde.name)
    dedans = membres(sauvegarde)
    verifier(donnees.FICHIER_GABARIT in dedans,
             "le gabarit d'avant l'import est dans la sauvegarde", ", ".join(dedans))
    with zipfile.ZipFile(str(sauvegarde)) as zip_ouvert:
        garde = zip_ouvert.read(donnees.FICHIER_GABARIT).decode("utf-8")
    verifier(garde.strip() == "Gabarit à sauvegarder avant tout.",
             "et c'est bien le gabarit d'avant", garde[:60])

    # Le retour en arrière remet ce gabarit en place.
    donnees.importer(sauvegarde)
    verifier(chemins.FICHIER_GABARIT_IA.read_text(encoding="utf-8").strip()
             == "Gabarit à sauvegarder avant tout.",
             "la sauvegarde se réimporte et restitue le gabarit")


# ---------------------------------------------------------------------------

def principal() -> int:
    print(f"Vérification de l'import et de l'export des données\n{'=' * 50}")

    with tempfile.TemporaryDirectory(prefix="scribouille-donnees-") as temporaire:
        bac = Path(temporaire)
        installer_bac(bac)

        avec = essai_export(bac)
        sans = essai_export_sans_gabarit(bac)
        essai_apercu(avec, sans)
        essai_import_complet(bac, avec)
        essai_format_1(bac)
        essai_format_2_sans_gabarit(bac)
        essai_archive_ancien_nom(bac)
        essai_format_trop_recent(bac)
        essai_filet(bac)

    print(f"\n{'=' * 50}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
