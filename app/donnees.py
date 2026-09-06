"""
Import et export des données personnelles, par fichier zip.

Le besoin : emporter son glossaire professionnel d'un poste à l'autre, ou le
sauvegarder, sans passer par un dépôt Git. Un dépôt privé rendrait le service,
mais il faut un compte, un client, une convention de branches, et surtout le
glossaire d'une entreprise n'a rien à faire en ligne. Un fichier suffit.

Ce qui part dans l'archive :

  - `vocabulaire.txt`  : le glossaire ;
  - `corrections.txt`  : la table de corrections ;
  - `gabarit-ia.txt`   : le gabarit d'instructions pour l'IA, s'il existe ;
  - `config.json`      : les réglages ;
  - `manifeste.json`   : version de l'application, date, liste des fichiers.

Ce qui n'y va JAMAIS :

  - `jeton_hf.txt`, le jeton Hugging Face. C'est un secret personnel, il ne
    doit pas se promener dans une pièce jointe ni dans un partage réseau ;
  - les modèles, plusieurs gigaoctets qui se retéléchargent tout seuls ;
  - le dossier « extensions », où vit la séparation des locuteurs. Plusieurs
    gigaoctets de bibliothèques compilées pour un processeur donné : les
    transporter d'un poste à l'autre n'aurait aucun sens, et l'application sait
    les reposer d'un bouton ;
  - les journaux, qui ne décrivent que la machine où ils ont été écrits.

L'archive se construit sur une liste blanche de membres, pas sur une liste
d'exclusions : ce qui n'est pas nommé ici ne peut pas y entrer, quoi qu'on ajoute
un jour dans les données de l'utilisateur.

À l'import, rien n'est écrit avant que l'utilisateur ait vu l'aperçu et
confirmé, et l'état courant est systématiquement sauvegardé d'abord.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from . import VERSION, NOM_APPLICATION, chemins, journal, langues, vocabulaire

NOM_MANIFESTE = "manifeste.json"

#: Noms d'application acceptés dans le manifeste d'une archive. Le second est
#: celui d'avant le renommage de la 2.4.0 : une archive exportée par une version
#: antérieure doit continuer de se réimporter, sans quoi le changement de nom
#: rendrait toutes les sauvegardes déjà faites inutilisables.
NOMS_APPLICATION_LUS = (NOM_APPLICATION.lower(), "whiscribe")

#: Version du format d'archive. Un export produit par une version future de
#: l'application sera refusé plutôt que mal interprété.
#:
#: Format 1 : glossaire, corrections, réglages. Format 2 : le gabarit
#: d'instructions pour l'IA en plus, et seulement s'il existe sur le poste de
#: départ. Les deux se relisent. Une archive de format 1 n'efface donc jamais
#: le gabarit en place ici : ce qu'elle ne transporte pas, elle ne le remplace
#: pas.
FORMAT_ARCHIVE = 2

#: Les seuls membres acceptés dans une archive. Tout le reste la fait rejeter.
FICHIER_GABARIT = "gabarit-ia.txt"
FICHIERS_TEXTE = ("vocabulaire.txt", "corrections.txt", FICHIER_GABARIT)
FICHIER_CONFIG = "config.json"
MEMBRES_AUTORISES = (NOM_MANIFESTE, FICHIER_CONFIG, *FICHIERS_TEXTE)

#: Bornes de sécurité. Ces fichiers pèsent quelques kilooctets : au-delà de ces
#: seuils, on a affaire à autre chose qu'un export Scribouille.
TAILLE_MAX_ARCHIVE = 8 * 1024 * 1024
TAILLE_MAX_MEMBRE = 2 * 1024 * 1024
TAILLE_MAX_TOTALE = 8 * 1024 * 1024

#: Réglages dont l'aperçu ne parle pas : ils changent à chaque clic et ne
#: renseignent personne sur ce qu'un import va vraiment modifier.
REGLAGES_DISCRETS = ("zoom", "journal_ouvert")


def libelle_reglage(cle: str) -> str:
    """
    Libellé d'un réglage dans l'aperçu d'import, langue de l'interface.

    La langue de l'interface est un réglage comme un autre : elle voyage dans
    l'export et l'aperçu la nomme, au même titre que le thème ou le preset.
    """
    traduit = langues.t("reglage." + cle)
    return cle if traduit == "reglage." + cle else traduit


# ---------------------------------------------------------------------------
# Petits utilitaires
# ---------------------------------------------------------------------------

class ErreurArchive(Exception):
    """Refus d'une archive, déjà formulé en français."""


def _horodatage_jour() -> str:
    return f"{datetime.now():%Y-%m-%d}"


def _horodatage_seconde() -> str:
    return f"{datetime.now():%Y-%m-%d-%H%M%S}"


def nom_export_propose() -> str:
    """Nom de fichier proposé dans la boîte d'enregistrement."""
    return f"scribouille-donnees-{_horodatage_jour()}.zip"


def nom_sauvegarde_avant_import() -> str:
    return f"scribouille-donnees-avant-import-{_horodatage_seconde()}.zip"


def _lire_texte(fichier: Path) -> str:
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError) as exc:
        journal.attention("Lecture impossible de %s : %s", fichier, exc)
        return ""


def _ecrire_atomique(fichier: Path, contenu: str) -> None:
    """
    Écrit par un fichier temporaire puis remplace.

    Une coupure de courant au mauvais moment laisserait sinon un glossaire
    tronqué, c'est-à-dire pire que pas de glossaire du tout.
    """
    fichier.parent.mkdir(parents=True, exist_ok=True)
    provisoire = fichier.with_suffix(fichier.suffix + ".tmp-import")
    provisoire.write_text(contenu, encoding="utf-8")
    os.replace(str(provisoire), str(fichier))


def _config_courante() -> dict:
    from . import config as config_module

    return config_module.charger()


def _cles_config() -> tuple[str, ...]:
    from . import config as config_module

    return tuple(config_module.DEFAUTS.keys())


def _formater_valeur(cle: str, valeur) -> str:
    if isinstance(valeur, bool):
        return langues.t("val.oui" if valeur else "val.non")
    if cle == "formats" and isinstance(valeur, dict):
        actifs = [nom for nom, actif in valeur.items() if actif]
        return ", ".join(actifs) if actifs else langues.t("val.aucun")
    if cle == "nb_locuteurs" and not valeur:
        return langues.t("val.auto")
    if cle in ("beam_size", "modele_avance") and not valeur:
        return langues.t("val.preset")
    if cle == "langue_interface":
        return langues.t("langue." + str(valeur)) if valeur else langues.t("val.vide")
    if isinstance(valeur, float):
        return langues.nombre(valeur, 2)
    texte = str(valeur)
    return texte if texte else langues.t("val.vide")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def _contenu_a_exporter() -> tuple[dict, dict]:
    """
    Renvoie (fichiers du zip, manifeste) pour l'état courant.

    Le gabarit d'instructions n'est joint que s'il existe déjà : l'export ne
    doit rien créer sur le poste de départ, et une archive sans gabarit reste
    parfaitement valide.
    """
    fichiers = {
        "vocabulaire.txt": _lire_texte(chemins.FICHIER_VOCABULAIRE),
        "corrections.txt": _lire_texte(chemins.FICHIER_CORRECTIONS),
        FICHIER_CONFIG: json.dumps(_config_courante(), indent=2, ensure_ascii=False) + "\n",
    }
    if chemins.FICHIER_GABARIT_IA.is_file():
        gabarit_courant = _lire_texte(chemins.FICHIER_GABARIT_IA)
        if gabarit_courant.strip():
            fichiers[FICHIER_GABARIT] = gabarit_courant
    manifeste = {
        "application": NOM_APPLICATION,
        "format": FORMAT_ARCHIVE,
        "version": VERSION,
        "date": datetime.now().isoformat(timespec="seconds"),
        "fichiers": sorted(fichiers.keys()),
        # Informatif : le dossier des modèles ne vit pas dans config.json, il est
        # partagé avec le programme d'installation. Il n'est repris à l'import
        # que s'il existe sur le poste d'arrivée.
        "dossier_modeles": str(chemins.DOSSIER_MODELES),
        "exclus": ["jeton_hf.txt", "logs", "modeles", "extensions", "cache-pip"],
    }
    return fichiers, manifeste


def exporter(destination: str | Path) -> dict:
    """
    Écrit l'archive d'export à l'emplacement demandé.

    Renvoie un dictionnaire `{ok, message, chemin, fichiers}`. Aucun écrasement
    n'a lieu ici sans que la boîte d'enregistrement de Windows n'ait déjà posé
    la question : c'est elle qui gère la confirmation de remplacement.
    """
    cible = Path(str(destination or "")).expanduser()
    if not cible.name:
        return {"ok": False, "message": langues.t("arch.aucun_emplacement")}
    if cible.suffix.lower() != ".zip":
        cible = cible.with_suffix(".zip")

    fichiers, manifeste = _contenu_a_exporter()
    provisoire = cible.with_name(cible.name + ".tmp-export")

    try:
        cible.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(provisoire, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                NOM_MANIFESTE, json.dumps(manifeste, indent=2, ensure_ascii=False) + "\n"
            )
            for nom, contenu in fichiers.items():
                archive.writestr(nom, contenu)
        os.replace(str(provisoire), str(cible))
    except OSError as exc:
        try:
            provisoire.unlink(missing_ok=True)
        except OSError:
            pass
        titre, message = journal.expliquer(exc, langues.t("contexte.export"))
        journal.exception("Export des données en échec", exc)
        return {
            "ok": False,
            "message": langues.t("format.titre_message", titre=titre, message=message),
        }

    resume = vocabulaire.termes(fichiers["vocabulaire.txt"])
    regles, _ = vocabulaire.analyser_corrections(fichiers["corrections.txt"])
    journal.info(
        "Export des données vers %s (%s termes, %s règles)", cible, len(resume), len(regles)
    )
    return {
        "ok": True,
        "chemin": str(cible),
        "fichiers": manifeste["fichiers"],
        "message": langues.t(
            "arch.export_message",
            termes=len(resume), regles=len(regles), chemin=cible,
        ),
    }


# ---------------------------------------------------------------------------
# Lecture et validation d'une archive
# ---------------------------------------------------------------------------

def _verifier_nom_membre(nom: str) -> None:
    """Refuse tout ce qui ressemble à une sortie de l'archive."""
    if nom not in MEMBRES_AUTORISES:
        raise ErreurArchive(langues.t("arch.membre_inattendu", nom=nom))
    if nom.endswith("/") or "\\" in nom or ".." in Path(nom).parts or Path(nom).is_absolute():
        raise ErreurArchive(langues.t("arch.chemin_invalide"))


def _ouvrir_archive(chemin: str | Path) -> tuple[dict, dict]:
    """
    Ouvre, valide et lit une archive. Renvoie (membres décodés, manifeste).

    Lève `ErreurArchive` avec un message déjà rédigé pour l'utilisateur.
    """
    source = Path(str(chemin or "")).expanduser()
    if not source.is_file():
        raise ErreurArchive(langues.t("arch.fichier_absent"))

    try:
        taille = source.stat().st_size
    except OSError as exc:
        raise ErreurArchive(
            langues.t("arch.fichier_illisible", erreur=exc.strerror or exc)) from exc

    if taille == 0:
        raise ErreurArchive(langues.t("arch.vide"))
    if taille > TAILLE_MAX_ARCHIVE:
        raise ErreurArchive(langues.t(
            "arch.trop_gros", mo=langues.nombre(taille / 1024 / 1024, 1)))
    if not zipfile.is_zipfile(str(source)):
        raise ErreurArchive(langues.t("arch.pas_zip"))

    membres: dict[str, str] = {}
    try:
        with zipfile.ZipFile(str(source)) as archive:
            abime = archive.testzip()
            if abime:
                raise ErreurArchive(langues.t("arch.abimee", nom=abime))

            infos = archive.infolist()
            if not infos:
                raise ErreurArchive(langues.t("arch.archive_vide"))

            total = 0
            for info in infos:
                _verifier_nom_membre(info.filename)
                if info.file_size > TAILLE_MAX_MEMBRE:
                    raise ErreurArchive(
                        langues.t("arch.membre_trop_gros", nom=info.filename))
                total += info.file_size
            if total > TAILLE_MAX_TOTALE:
                raise ErreurArchive(langues.t("arch.contenu_volumineux"))

            for info in infos:
                brut = archive.read(info.filename)
                try:
                    membres[info.filename] = brut.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ErreurArchive(
                        langues.t("arch.membre_non_texte", nom=info.filename)) from exc
    except zipfile.BadZipFile as exc:
        raise ErreurArchive(langues.t("arch.zip_corrompue")) from exc
    except OSError as exc:
        raise ErreurArchive(
            langues.t("arch.fichier_illisible", erreur=exc.strerror or exc)) from exc

    if NOM_MANIFESTE not in membres:
        raise ErreurArchive(langues.t("arch.manifeste_absent"))

    try:
        manifeste = json.loads(membres[NOM_MANIFESTE])
    except json.JSONDecodeError as exc:
        raise ErreurArchive(langues.t("arch.manifeste_illisible")) from exc
    if not isinstance(manifeste, dict):
        raise ErreurArchive(langues.t("arch.manifeste_forme"))
    if str(manifeste.get("application", "")).strip().lower() not in NOMS_APPLICATION_LUS:
        raise ErreurArchive(langues.t(
            "arch.autre_application",
            application=manifeste.get("application")
            or langues.t("arch.application_inconnue"),
        ))

    try:
        format_archive = int(manifeste.get("format", 0))
    except (TypeError, ValueError):
        format_archive = 0
    # Tous les formats de 1 au format courant se relisent. Un membre que le
    # format d'origine ne connaissait pas est simplement absent, et ce qui est
    # absent n'est pas touché à l'import.
    if format_archive < 1:
        raise ErreurArchive(langues.t("arch.format_invalide"))
    if format_archive > FORMAT_ARCHIVE:
        raise ErreurArchive(langues.t(
            "arch.format_recent", application=NOM_APPLICATION,
            format=format_archive, lu=FORMAT_ARCHIVE,
        ))

    declares = manifeste.get("fichiers")
    if not isinstance(declares, list) or not declares:
        raise ErreurArchive(langues.t("arch.aucun_declare"))
    for nom in declares:
        if not isinstance(nom, str) or nom not in MEMBRES_AUTORISES:
            raise ErreurArchive(langues.t("arch.declare_inattendu", nom=nom))
        if nom not in membres:
            raise ErreurArchive(langues.t("arch.declare_absent", nom=nom))

    if FICHIER_CONFIG in membres:
        try:
            valeur = json.loads(membres[FICHIER_CONFIG])
        except json.JSONDecodeError as exc:
            raise ErreurArchive(langues.t("arch.config_illisible")) from exc
        if not isinstance(valeur, dict):
            raise ErreurArchive(langues.t("arch.config_forme"))

    return membres, manifeste


# ---------------------------------------------------------------------------
# Aperçu avant écriture
# ---------------------------------------------------------------------------

def analyser(chemin: str | Path) -> dict:
    """
    Valide l'archive et décrit ce qu'un import changerait. N'écrit rien.

    Renvoie `{ok: False, message}` en cas de refus, sinon `{ok: True, apercu}`.
    """
    try:
        membres, manifeste = _ouvrir_archive(chemin)
    except ErreurArchive as exc:
        journal.attention("Import refusé (%s) : %s", chemin, exc)
        return {"ok": False, "message": str(exc)}

    glossaire = membres.get("vocabulaire.txt", "")
    corrections = membres.get("corrections.txt", "")
    gabarit_present = bool(membres.get(FICHIER_GABARIT, "").strip())
    termes_import = vocabulaire.termes(glossaire)
    regles_import, erreurs_import = vocabulaire.analyser_corrections(corrections)

    termes_actuels = vocabulaire.termes(_lire_texte(chemins.FICHIER_VOCABULAIRE))
    regles_actuelles, _ = vocabulaire.analyser_corrections(
        _lire_texte(chemins.FICHIER_CORRECTIONS)
    )

    config_actuelle = _config_courante()
    config_import: dict = json.loads(membres[FICHIER_CONFIG]) if FICHIER_CONFIG in membres else {}

    changements: list[dict] = []
    for cle in _cles_config():
        if cle in REGLAGES_DISCRETS or cle not in config_import:
            continue
        avant, apres = config_actuelle.get(cle), config_import.get(cle)
        if cle == "dossier_sortie":
            continue  # traité à part, c'est un chemin propre à la machine
        if avant == apres:
            continue
        changements.append({
            "cle": cle,
            "libelle": libelle_reglage(cle),
            "avant": _formater_valeur(cle, avant),
            "apres": _formater_valeur(cle, apres),
        })

    chemins_machine = _examiner_chemins(config_import, manifeste, config_actuelle)

    return {
        "ok": True,
        "chemin": str(Path(str(chemin)).expanduser()),
        "nom": Path(str(chemin)).name,
        "manifeste": {
            "version": manifeste.get("version", "inconnue"),
            "date": _date_lisible(manifeste.get("date", "")),
            "fichiers": manifeste.get("fichiers", []),
        },
        "glossaire": {"nb": len(termes_import), "nb_actuel": len(termes_actuels)},
        "corrections": {
            "nb": len(regles_import),
            "nb_actuel": len(regles_actuelles),
            "erreurs": erreurs_import,
        },
        # Le gabarit n'est annoncé que lorsqu'il est là : une archive qui n'en
        # porte pas ne remplacera pas celui du poste, il n'y a rien à dire.
        "gabarit": {
            "present": gabarit_present,
            "message": langues.t("arch.gabarit_inclus") if gabarit_present else "",
        },
        "reglages": changements,
        "chemins": chemins_machine,
        "sauvegarde": nom_sauvegarde_avant_import(),
        "dossier_sauvegarde": str(chemins.RACINE),
    }


def _date_lisible(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime(langues.t("format.date_heure"))
    except (TypeError, ValueError):
        return str(iso or "") or langues.t("val.date_inconnue")


def _examiner_chemins(config_import: dict, manifeste: dict, config_actuelle: dict) -> list[dict]:
    """
    Décide du sort des chemins propres à la machine, sans rien écrire.

    Un dossier de sortie ou un dossier de modèles venu d'un autre poste n'a
    aucune raison d'exister ici. On ne le reprend que s'il existe vraiment,
    sinon on garde la valeur locale et on le dit.
    """
    resultat: list[dict] = []

    def examiner(libelle: str, valeur, actuel: str) -> None:
        texte = str(valeur or "").strip()
        if not texte:
            return
        existe = Path(texte).expanduser().is_dir()
        if existe and texte == str(actuel or ""):
            return
        resultat.append({
            "libelle": libelle,
            "valeur": texte,
            "repris": existe,
            "actuel": str(actuel or ""),
            "message": langues.t(
                "arch.chemin_repris" if existe else "arch.chemin_absent",
                libelle=libelle, valeur=texte,
            ),
        })

    examiner(
        langues.t("arch.libelle.sortie"),
        config_import.get("dossier_sortie"),
        config_actuelle.get("dossier_sortie", ""),
    )
    examiner(
        langues.t("arch.libelle.surveille"),
        config_import.get("dossier_surveille"),
        config_actuelle.get("dossier_surveille", ""),
    )
    examiner(
        langues.t("arch.libelle.modeles"),
        manifeste.get("dossier_modeles"),
        str(chemins.DOSSIER_MODELES),
    )
    return resultat


# ---------------------------------------------------------------------------
# Sauvegarde automatique et import
# ---------------------------------------------------------------------------

def sauvegarder_etat_courant(nom: str | None = None) -> Path:
    """
    Écrit un export de l'état courant dans le dossier de données.

    Appelée juste avant tout import. Lève `ErreurArchive` si elle échoue :
    sans filet, on n'écrase rien.
    """
    cible = chemins.RACINE / (nom or nom_sauvegarde_avant_import())
    resultat = exporter(cible)
    if not resultat.get("ok"):
        raise ErreurArchive(langues.t(
            "arch.sauvegarde_echouee", detail=resultat.get("message", "")).strip())
    return cible


def importer(chemin: str | Path) -> dict:
    """
    Applique un import, après validation et sauvegarde automatique.

    L'archive est revalidée ici : l'aperçu affiché à l'utilisateur ne fait pas
    autorité, le fichier a pu changer entre-temps.
    """
    try:
        membres, manifeste = _ouvrir_archive(chemin)
    except ErreurArchive as exc:
        journal.attention("Import refusé (%s) : %s", chemin, exc)
        return {"ok": False, "message": str(exc)}

    config_actuelle = _config_courante()

    try:
        sauvegarde = sauvegarder_etat_courant()
    except ErreurArchive as exc:
        journal.erreur("Import annulé : %s", exc)
        return {"ok": False, "message": str(exc)}

    notes: list[str] = []
    try:
        if "vocabulaire.txt" in membres:
            _ecrire_atomique(
                chemins.FICHIER_VOCABULAIRE, membres["vocabulaire.txt"].rstrip() + "\n"
            )
        if "corrections.txt" in membres:
            _ecrire_atomique(
                chemins.FICHIER_CORRECTIONS, membres["corrections.txt"].rstrip() + "\n"
            )
        # Archive de format 1, ou archive de format 2 sans gabarit : le gabarit
        # déjà en place reste tel quel. Il appartient à l'utilisateur.
        if membres.get(FICHIER_GABARIT, "").strip():
            _ecrire_atomique(
                chemins.FICHIER_GABARIT_IA, membres[FICHIER_GABARIT].rstrip() + "\n"
            )
            notes.append(langues.t("arch.note.gabarit_repris"))

        config_finale = dict(config_actuelle)
        if FICHIER_CONFIG in membres:
            config_import = json.loads(membres[FICHIER_CONFIG])
            for cle in _cles_config():
                if cle not in config_import or cle in ("dossier_sortie", "dossier_surveille"):
                    continue
                valeur = config_import[cle]
                if isinstance(config_finale.get(cle), dict) and isinstance(valeur, dict):
                    config_finale[cle] = {**config_finale[cle], **valeur}
                else:
                    config_finale[cle] = valeur

            demande = str(config_import.get("dossier_sortie", "") or "").strip()
            if demande and Path(demande).expanduser().is_dir():
                config_finale["dossier_sortie"] = demande
                notes.append(langues.t("arch.note.sortie_reprise", chemin=demande))
            elif demande and demande != str(config_actuelle.get("dossier_sortie", "")):
                notes.append(langues.t(
                    "arch.note.sortie_absente", demande=demande,
                    actuel=config_actuelle.get("dossier_sortie", ""),
                ))

            # Le dossier surveillé suit la même règle : un chemin venu d'un
            # autre poste ne doit pas être scruté ici sans exister.
            surveille = str(config_import.get("dossier_surveille", "") or "").strip()
            if surveille and Path(surveille).expanduser().is_dir():
                config_finale["dossier_surveille"] = surveille
                notes.append(langues.t("arch.note.surveille_repris", chemin=surveille))
            elif surveille:
                config_finale["surveillance"] = False
                notes.append(langues.t("arch.note.surveille_absent", chemin=surveille))

        from . import config as config_module

        config_module.sauver(config_finale)

        demande_modeles = str(manifeste.get("dossier_modeles", "") or "").strip()
        if demande_modeles and demande_modeles != str(chemins.DOSSIER_MODELES):
            if Path(demande_modeles).expanduser().is_dir():
                chemins.definir_dossier_modeles(demande_modeles, memoriser=True)
                notes.append(langues.t(
                    "arch.note.modeles_repris", chemin=demande_modeles))
            else:
                notes.append(langues.t(
                    "arch.note.modeles_absents", demande=demande_modeles,
                    actuel=chemins.DOSSIER_MODELES,
                ))
    except (OSError, json.JSONDecodeError) as exc:
        titre, message = journal.expliquer(exc, langues.t("contexte.import"))
        journal.exception("Import des données en échec", exc)
        return {
            "ok": False,
            "message": langues.t(
                "arch.echec_import", titre=titre, message=message, sauvegarde=sauvegarde),
            "sauvegarde": str(sauvegarde),
        }

    termes_importes = vocabulaire.termes(membres.get("vocabulaire.txt", ""))
    regles_importees, _ = vocabulaire.analyser_corrections(membres.get("corrections.txt", ""))
    journal.info(
        "Import depuis %s : %s termes, %s règles, sauvegarde préalable %s",
        chemin, len(termes_importes), len(regles_importees), sauvegarde,
    )

    return {
        "ok": True,
        "message": langues.t(
            "arch.import_message",
            termes=len(termes_importes), regles=len(regles_importees),
        ),
        "sauvegarde": str(sauvegarde),
        "message_sauvegarde": langues.t(
            "arch.message_sauvegarde", chemin=sauvegarde),
        "notes": notes,
        "glossaire": len(termes_importes),
        "corrections": len(regles_importees),
    }
