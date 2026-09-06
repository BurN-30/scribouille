"""
Vérification en ligne de commande des fonctions périphériques.

Onze sujets, tous vérifiables sans ouvrir de fenêtre, sans transcrire quoi que
ce soit et **sans le moindre appel réseau** :

  1. la scrutation du dossier surveillé, avec de vrais fichiers déposés dans un
     dossier temporaire : détection, stabilité, mémoire persistante ;
  2. la comparaison de numéros de version, dont le cas 2.10.0 contre 2.9.0 et
     les préversions ;
  3. le motif de nommage des sorties : variables, caractères interdits, retour
     au défaut, non-régression du nom historique ;
  4. la mesure de l'espace occupé, sur une arborescence fabriquée pour
     l'occasion ;
  5. la garde des 24 heures entre deux vérifications de mise à jour : le jalon
     n'est posé qu'après une réponse effectivement reçue, un échec laisse la
     fenêtre du jour intacte, et `forcer=True`, ce qu'emploie le bouton de la
     fenêtre d'aide, passe outre la garde ;
  6. la plomberie COM en ctypes pur de la barre des tâches Windows, jusqu'à
     l'initialisation de l'objet ;
  7. l'amorce du glossaire, dont l'en-tête suit la langue parlée et non celle
     de l'interface, et son budget de jetons ;
  8. le téléchargement des poids et l'autoréparation d'un modèle laissé
     incomplet : de faux dossiers de cache sont fabriqués pour l'occasion, la
     détection les reconnaît, la suppression n'emporte que le bon dossier, un
     modèle complet ne provoque AUCUN appel réseau, un téléchargement qui rend
     un dossier sans « model.bin » lève une erreur en français au lieu d'un
     traceback, le manque de place est vu avant de commencer, et la réparation
     n'a lieu qu'une fois par modèle. Rien n'est réellement téléchargé, le
     moteur comme le réseau sont simulés.
  9. la compatibilité du renommage de la 2.4.0 : un fichier compagnon écrit
     sous l'ancien marqueur de format se relit toujours, et le dossier de
     données garde son nom d'origine.
  10. le backend « xet » de Hugging Face, coupé avant tout import du hub :
     la bibliothèque le confirme elle-même, et un choix explicite de
     l'utilisateur reste respecté.
  11. la recalibration à chaud des durées : le facteur mesuré sur le poste
     remplace celui du preset, il se lisse sur les dernières transcriptions,
     il ne déborde pas d'une situation de calcul à l'autre, et tout incident
     ramène au facteur statique.

Rien de ce que fait ce script ne touche à l'installation : tout se passe dans
un dossier temporaire, effacé à la fin.

    .venv\\Scripts\\python outils\\verifier_fonctions_peripheriques.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import (  # noqa: E402
    calibration, chemins, compagnon, langues, maj, materiel, nommage, presets,
    stockage, surveillance, vocabulaire)

# Ces contrôles comparent des chaînes produites par l'application : ils fixent
# donc la langue d'interface, sans quoi leur résultat dépendrait de la langue de
# Windows sur le poste qui les exécute. La bascule elle-même est vérifiée à part,
# dans `essai_langues`, et par `outils/verifier_traductions.py`.
langues.definir("fr")

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
# 1. Dossier surveillé
# ---------------------------------------------------------------------------

def essai_surveillance(base: Path) -> None:
    titre("Dossier surveillé : scrutation, stabilité, mémoire")

    dossier = base / "surveille"
    dossier.mkdir()
    memoire: dict = {}

    # Premier passage sur un dossier vide.
    p = surveillance.scruter(dossier, memoire, {})
    verifier(p["nouveaux"] == [] and p["probleme"] == "", "dossier vide, rien à prendre")

    # Un fichier apparaît : premier passage, il n'a pas encore de taille connue,
    # donc il n'est pas retenu. C'est exactement la garde anti-copie en cours.
    (dossier / "reunion.m4a").write_bytes(b"x" * 1000)
    p1 = surveillance.scruter(dossier, memoire, {})
    verifier(p1["nouveaux"] == [], "un fichier tout juste apparu n'est pas pris")

    # Deuxième passage, taille inchangée : il est stable, donc retenu.
    p2 = surveillance.scruter(dossier, memoire, p1["tailles"])
    verifier(
        [Path(c).name for c in p2["nouveaux"]] == ["reunion.m4a"],
        "un fichier stable est retenu au passage suivant",
        str(p2["nouveaux"]),
    )

    # Fichier en cours de copie : la taille bouge entre deux passages.
    grossissant = dossier / "copie-en-cours.mp3"
    grossissant.write_bytes(b"y" * 500)
    p3 = surveillance.scruter(dossier, memoire, p2["tailles"])
    grossissant.write_bytes(b"y" * 5000)
    p4 = surveillance.scruter(dossier, memoire, p3["tailles"])
    verifier(
        all(Path(c).name != "copie-en-cours.mp3" for c in p4["nouveaux"]),
        "un fichier dont la taille bouge n'est jamais pris",
        str(p4["nouveaux"]),
    )
    p5 = surveillance.scruter(dossier, memoire, p4["tailles"])
    verifier(
        any(Path(c).name == "copie-en-cours.mp3" for c in p5["nouveaux"]),
        "la copie terminée est prise au passage d'après",
        str(p5["nouveaux"]),
    )

    # Mémoire : un fichier déjà pris ne repart pas.
    for chemin in p2["nouveaux"] + p5["nouveaux"]:
        memoire[surveillance.empreinte(Path(chemin))] = 0
    p6 = surveillance.scruter(dossier, memoire, p5["tailles"])
    verifier(p6["nouveaux"] == [], "un fichier déjà traité n'est pas repris", str(p6["nouveaux"]))

    # Redémarrage simulé : mémoire relue, rien ne doit repartir.
    p7 = surveillance.scruter(dossier, dict(memoire), p6["tailles"])
    verifier(p7["nouveaux"] == [], "rien n'est retranscrit après un redémarrage")

    # Un fichier réenregistré sous le même nom est bien un fichier nouveau.
    import time as _time
    _time.sleep(1.1)                       # l'horodatage a une seconde de grain
    (dossier / "reunion.m4a").write_bytes(b"z" * 4321)
    p8 = surveillance.scruter(dossier, memoire, {})
    p9 = surveillance.scruter(dossier, memoire, p8["tailles"])
    verifier(
        any(Path(c).name == "reunion.m4a" for c in p9["nouveaux"]),
        "un enregistrement refait sous le même nom repart en transcription",
        str(p9["nouveaux"]),
    )

    # Formats non audio et sous-dossiers : ignorés.
    (dossier / "notes.txt").write_text("bonjour", encoding="utf-8")
    (dossier / "sous-dossier").mkdir()
    (dossier / "sous-dossier" / "cache.mp3").write_bytes(b"a" * 900)
    q1 = surveillance.scruter(dossier, memoire, {})
    q2 = surveillance.scruter(dossier, memoire, q1["tailles"])
    noms = [Path(c).name for c in q2["nouveaux"]]
    verifier("notes.txt" not in noms, "un fichier non audio est ignoré")
    verifier("cache.mp3" not in noms, "les sous-dossiers ne sont pas parcourus")

    # Dossier disparu : défaut annoncé, pas d'exception.
    absent = surveillance.scruter(base / "nulle-part", {}, {})
    verifier(
        absent["probleme"] != "" and absent["nouveaux"] == [],
        "un dossier introuvable se signale sans casser",
        str(absent),
    )
    verifier(
        surveillance.scruter("", {}, {})["probleme"] == "",
        "aucun dossier choisi, aucun défaut signalé",
    )

    # Le fichier vide n'est pas un enregistrement.
    (dossier / "vide.wav").write_bytes(b"")
    v1 = surveillance.scruter(dossier, memoire, {})
    v2 = surveillance.scruter(dossier, memoire, v1["tailles"])
    verifier(
        all(Path(c).name != "vide.wav" for c in v2["nouveaux"]),
        "un fichier de taille nulle est écarté",
    )


# ---------------------------------------------------------------------------
# 2. Comparaison de versions
# ---------------------------------------------------------------------------

def essai_versions() -> None:
    titre("Mise à jour : comparaison de versions")

    cas = [
        ("2.10.0", "2.9.0", 1, "2.10.0 est plus récent que 2.9.0"),
        ("2.9.0", "2.10.0", -1, "2.9.0 est plus ancien que 2.10.0"),
        ("2.2.0", "2.2.0", 0, "deux versions identiques"),
        ("v2.3.0", "2.2.9", 1, "le v du tag est ignoré"),
        ("3.0.0", "2.99.99", 1, "changement de version majeure"),
        ("2.2.1", "2.2.0", 1, "correctif plus récent"),
        ("2.2.0-beta.1", "2.2.0", -1, "une préversion précède la version finale"),
        ("2.2.0", "2.2.0-rc.2", 1, "la version finale suit sa préversion"),
        ("2.2.0-rc.2", "2.2.0-rc.10", -1, "préversions comparées en nombres"),
        ("2.3.2", "2.3.1", 1, "le correctif suivant est bien vu plus récent"),
        ("2.3.1", "2.3.2", -1, "et le précédent plus ancien"),
        ("2.3.10", "2.3.9", 1, "2.3.10 est plus récent que 2.3.9, pas l'inverse"),
        ("2.3.9", "2.3.10", -1, "2.3.9 est plus ancien que 2.3.10"),
        ("2.3.2", "2.3.2", 0, "égalité stricte sur la version du jour"),
        ("2.2", "2.2.0", 0, "un numéro court vaut le même complété de zéros"),
        ("2.2.0", "", 1, "une version absente en face ne bloque pas"),
    ]
    for gauche, droite, attendu, libelle in cas:
        obtenu = maj.comparer(gauche, droite)
        verifier(obtenu == attendu, f"{libelle} ({gauche} / {droite})", f"obtenu {obtenu}")

    # Lecture d'une réponse de l'API, sans réseau.
    publication = {
        "tag_name": "v2.3.0",
        "html_url": "https://github.com/exemple/scribouille/releases/tag/v2.3.0",
        "body": "Des nouveautés.",
    }
    lu = maj.analyser_release(publication, "2.2.0")
    verifier(lu["disponible"] and lu["version"] == "2.3.0", "une version plus récente est vue")
    verifier(not lu["reinstallation"], "sans marqueur, mise à jour par-dessus")

    publication["body"] = "Attention.\n\n[reinstallation-requise]\n\nSuite."
    verifier(
        maj.analyser_release(publication, "2.2.0")["reinstallation"],
        "le marqueur [reinstallation-requise] est reconnu",
    )
    verifier(
        maj.analyser_release({"tag_name": "v2.0.0", "body": ""}, "2.2.0")["disponible"] is False,
        "une version plus ancienne n'annonce rien",
    )
    verifier(
        maj.analyser_release({}, "2.2.0")["disponible"] is False,
        "une réponse vide n'annonce rien",
    )
    verifier(
        maj.url_api().startswith("https://api.github.com/repos/"),
        "l'adresse de l'API est déduite du dépôt",
        maj.url_api(),
    )


# ---------------------------------------------------------------------------
# 3. Motif de nommage
# ---------------------------------------------------------------------------

def essai_nommage() -> None:
    titre("Nom des fichiers produits")

    quand = datetime(2026, 8, 18, 14, 32, 5)
    source = Path(r"C:\Enregistrements\Réunion équipe.m4a")

    verifier(
        nommage.construire("", source, "large-v3", quand) == "2026-08-18-réunion-équipe",
        "motif vide : nommage historique inchangé",
        nommage.construire("", source, "large-v3", quand),
    )
    verifier(
        nommage.construire("{nom}", source, "", quand) == "réunion-équipe",
        "{nom} seul, accents conservés comme avant",
        nommage.construire("{nom}", source, "", quand),
    )
    verifier(
        nommage.construire("{date}-{heure}-{nom}", source, "", quand)
        == "2026-08-18-143205-réunion-équipe",
        "date et heure",
        nommage.construire("{date}-{heure}-{nom}", source, "", quand),
    )
    verifier(
        nommage.construire("{nom}-{modele}", source, "large-v3", quand)
        == "réunion-équipe-large-v3",
        "modèle repris dans le nom",
        nommage.construire("{nom}-{modele}", source, "large-v3", quand),
    )
    verifier(
        nommage.construire("CR {nom} du {date}", source, "", quand)
        == "CR réunion-équipe du 2026-08-18",
        "le texte de l'utilisateur garde sa casse",
        nommage.construire("CR {nom} du {date}", source, "", quand),
    )

    for interdit in '<>:"/\\|?*':
        message = nommage.valider(f"compte{interdit}rendu")
        verifier(bool(message), f"le caractère {interdit!r} est refusé")
    verifier(nommage.valider("") == "", "un motif vide est accepté, c'est le défaut")
    verifier(nommage.valider("{date}-{nom}") == "", "le motif par défaut est accepté")
    verifier(bool(nommage.valider("nul")), "un nom réservé de Windows est refusé")

    apercu_defaut = nommage.apercu("")
    verifier(
        apercu_defaut["ok"] and apercu_defaut["defaut"] and apercu_defaut["exemple"].endswith(".txt"),
        "aperçu du défaut",
        str(apercu_defaut),
    )
    apercu_fixe = nommage.apercu("transcription")
    verifier(
        apercu_fixe["ok"] and apercu_fixe["message"] == langues.t("nom.sans_variable"),
        "un motif sans variable est signalé sans être refusé",
        str(apercu_fixe),
    )
    verifier(
        nommage.apercu("a/b")["ok"] is False,
        "un séparateur de chemin est refusé dans l'aperçu",
    )
    verifier(
        len(nommage.construire("{nom}" * 40, source, "", quand)) <= nommage.LONGUEUR_MAX,
        "un motif démesuré est borné",
    )
    verifier(
        nommage.construire("{modele}", Path("son.wav"), "", quand) == "son",
        "un motif qui ne produirait rien retombe sur le nom du fichier",
        nommage.construire("{modele}", Path("son.wav"), "", quand),
    )

    # Non-régression : l'ancien code de app/sorties.py et le nouveau doivent
    # produire exactement le même nom quand aucun motif n'est réglé.
    from app import sorties

    for exemple in ("Réunion équipe.m4a", "notes_du_12 mars.mp3", "@@@.wav", "CR-final.m4a"):
        attendu = f"{datetime.now():%Y-%m-%d}-" + nommage.nettoyer_nom(Path(exemple).stem)
        verifier(
            sorties.nom_de_base(Path(exemple)) == attendu,
            f"nom historique préservé pour « {exemple} »",
            sorties.nom_de_base(Path(exemple)),
        )


# ---------------------------------------------------------------------------
# 4. Espace occupé
# ---------------------------------------------------------------------------

def essai_stockage(base: Path) -> None:
    titre("Espace utilisé")

    verifier(stockage.formater_octets(0) == "0 octet", "zéro octet",
             stockage.formater_octets(0))
    verifier(stockage.formater_octets(1536) == "1,5 Ko", "kilooctets",
             stockage.formater_octets(1536))
    verifier(stockage.formater_octets(3.1 * 1024 ** 3).endswith("Go"), "gigaoctets",
             stockage.formater_octets(3.1 * 1024 ** 3))

    arbre = base / "mesure"
    (arbre / "sous" / "encore").mkdir(parents=True)
    (arbre / "a.bin").write_bytes(b"0" * 1000)
    (arbre / "sous" / "b.bin").write_bytes(b"0" * 2000)
    (arbre / "sous" / "encore" / "c.bin").write_bytes(b"0" * 3000)
    (arbre / ".venv").mkdir()
    (arbre / ".venv" / "gros.bin").write_bytes(b"0" * 999000)

    octets, nombre = stockage.taille(arbre)
    verifier(octets == 1000 + 2000 + 3000 + 999000, "somme récursive complète", str(octets))
    verifier(nombre == 4, "nombre de fichiers", str(nombre))

    octets_hors_venv, _ = stockage.taille(arbre, exclus=stockage.EXCLUS_SOURCE)
    verifier(octets_hors_venv == 6000, "le .venv est exclu à la demande", str(octets_hors_venv))

    verifier(stockage.taille(base / "inexistant") == (0, 0), "un dossier absent vaut zéro")
    verifier(stockage.taille(arbre / "a.bin") == (1000, 1), "un fichier seul se mesure aussi")

    mesure = stockage.mesurer()
    cles = [p["cle"] for p in mesure["postes"]]
    verifier(cles == ["modeles", "donnees", "programme"], "trois postes annoncés", str(cles))
    verifier(
        all(p["chemin"] and p["taille"] for p in mesure["postes"]),
        "chaque poste porte un chemin et une taille lisible",
    )
    verifier(
        mesure["total"] == sum(p["octets"] for p in mesure["postes"]),
        "le total est la somme des postes",
    )
    verifier(bool(mesure["libre"]), "l'espace libre est renseigné", mesure["libre"])


# ---------------------------------------------------------------------------
# 5. Garde des 24 heures, et plomberie COM de la barre des tâches
# ---------------------------------------------------------------------------

def essai_cadence_maj() -> None:
    titre("Mise à jour : une vérification par jour au plus")

    fichier = maj._fichier_etat()
    existait = fichier.exists()
    sauvegarde = fichier.read_text(encoding="utf-8") if existait else ""
    try:
        fichier.unlink(missing_ok=True)
        verifier(maj.verification_due(), "sans état, la vérification est due")

        maj._ecrire_etat({"derniere": datetime.now().isoformat(timespec="seconds")})
        verifier(not maj.verification_due(), "juste après, elle ne l'est plus")

        hier = datetime.now() - timedelta(hours=25)
        maj._ecrire_etat({"derniere": hier.isoformat(timespec="seconds")})
        verifier(maj.verification_due(), "au-delà de 24 heures, elle l'est de nouveau")

        maj._ecrire_etat({"derniere": "n'importe quoi"})
        verifier(maj.verification_due(), "un état illisible ne bloque pas la vérification")

        essai_maj_indisponible()
        essai_maj_jalon(fichier)
    finally:
        if existait:
            fichier.write_text(sauvegarde, encoding="utf-8")
        else:
            fichier.unlink(missing_ok=True)


def essai_maj_indisponible() -> None:
    """
    Un dépôt privé répond 404 à l'API publique, un quota atteint répond 403.
    Ni l'un ni l'autre n'est un incident : le journal doit rester en INFO, et
    l'interface ne rien recevoir. Aucun appel réseau ici, l'interrogation est
    remplacée par l'exception qu'elle produirait.
    """
    import urllib.error

    from app import journal

    traces: dict[str, list[str]] = {"info": [], "attention": []}
    interrogation = maj._interroger
    ecrire_info, ecrire_attention = journal.info, journal.attention

    def echec(code: int):
        def lever(_url: str) -> dict:
            raise urllib.error.HTTPError(_url, code, "Not Found", {}, None)  # type: ignore[arg-type]
        return lever

    try:
        journal.info = lambda message, *args: traces["info"].append(str(message) % args if args else str(message))
        journal.attention = lambda message, *args: traces["attention"].append(str(message) % args if args else str(message))

        for code in (404, 403):
            traces["info"].clear()
            traces["attention"].clear()
            maj._interroger = echec(code)
            resultat = maj.verifier("2.0.0", forcer=True)
            verifier(not resultat.get("disponible"),
                     f"HTTP {code} : rien n'est proposé à l'utilisateur", str(resultat))
            verifier(not traces["attention"],
                     f"HTTP {code} : aucun avertissement dans le journal",
                     " | ".join(traces["attention"]))
            verifier(any(str(code) in ligne for ligne in traces["info"]),
                     f"HTTP {code} : une simple ligne d'information",
                     " | ".join(traces["info"]))

        traces["attention"].clear()
        maj._interroger = echec(500)
        maj.verifier("2.0.0", forcer=True)
        verifier(bool(traces["attention"]),
                 "une vraie panne de GitHub reste un avertissement")
    finally:
        maj._interroger = interrogation
        journal.info, journal.attention = ecrire_info, ecrire_attention


def essai_maj_jalon(fichier: Path) -> None:
    """
    Deux règles que la version 2.3.2 fixe, et qu'aucun appel réseau ne vient
    éprouver ici : l'interrogation est remplacée par ce qu'elle produirait.

    1. **Seul un succès pose le jalon des 24 heures.** Un 404, un poste hors
       ligne ou un pare-feu laissent la fenêtre du jour intacte. Sans cette
       règle, un unique essai malheureux, par exemple pendant la période où le
       dépôt était encore privé, condamnait le poste au silence à chaque
       lancement des 24 heures suivantes.
    2. **`forcer=True` ignore le cache**, sans quoi le bouton de la fenêtre
       d'aide répondrait « repassez demain » à un clic explicite.
    """
    import urllib.error

    from app import journal

    interrogation = maj._interroger
    ecrire_info, ecrire_attention = journal.info, journal.attention
    appels: list[str] = []

    publication = {
        "tag_name": "v9.9.9",
        "html_url": "https://exemple.invalide/releases/tag/v9.9.9",
        "body": "Sans marqueur.",
    }

    def repondre(_url: str) -> dict:
        appels.append(_url)
        return dict(publication)

    def lever(exception: Exception):
        def echouer(_url: str) -> dict:
            appels.append(_url)
            raise exception
        return echouer

    try:
        journal.info = lambda message, *args: None
        journal.attention = lambda message, *args: None

        # 1. Un échec ne consomme pas la fenêtre du jour.
        pannes = [
            (urllib.error.HTTPError(  # type: ignore[arg-type]
                "https://exemple.invalide", 404, "Not Found", {}, None),
             "un 404 ne pose pas le jalon des 24 heures"),
            (urllib.error.URLError("poste hors ligne"),
             "un poste hors ligne ne pose pas le jalon des 24 heures"),
            (TimeoutError("pare-feu"),
             "un délai dépassé ne pose pas le jalon des 24 heures"),
        ]
        for exception, libelle in pannes:
            fichier.unlink(missing_ok=True)
            maj._interroger = lever(exception)
            resultat = maj.verifier("2.0.0")
            verifier(not resultat.get("disponible"), f"{libelle} : rien n'est proposé")
            verifier("derniere" not in maj.lire_etat(), libelle, str(maj.lire_etat()))
            verifier(maj.verification_due(),
                     f"{libelle}, la vérification suivante reste due")

        # 2. Un succès, lui, le pose.
        fichier.unlink(missing_ok=True)
        maj._interroger = repondre
        resultat = maj.verifier("2.0.0")
        verifier(resultat.get("disponible") is True,
                 "une réponse valide annonce bien la version plus récente")
        verifier("derniere" in maj.lire_etat(),
                 "seul un succès pose le jalon des 24 heures")
        verifier(not maj.verification_due(),
                 "juste après un succès, la vérification n'est plus due")

        # 3. Le démarrage respecte le cache, le bouton l'ignore.
        appels.clear()
        passif = maj.verifier("2.0.0")
        verifier(passif.get("raison") == "verifiee-recemment",
                 "la vérification du démarrage respecte le cache de 24 heures", str(passif))
        verifier(not appels, "et n'émet aucun appel réseau", str(appels))

        appels.clear()
        force = maj.verifier("2.0.0", forcer=True)
        verifier(bool(appels), "forcer=True interroge malgré le cache")
        verifier(force.get("disponible") is True and force.get("version") == "9.9.9",
                 "forcer=True rend un résultat complet", str(force))

        # 4. La raison distingue « à jour » de « pas joignable » : la fenêtre
        #    d'aide s'en sert pour ne pas dire « à jour » à un poste hors ligne.
        a_jour = maj.verifier("9.9.9", forcer=True)
        verifier(a_jour.get("raison") == "a-jour" and not a_jour.get("disponible"),
                 "une version déjà à jour se distingue d'un échec", str(a_jour))
        maj._interroger = lever(urllib.error.URLError("hors ligne"))
        panne = maj.verifier("2.0.0", forcer=True)
        verifier(panne.get("raison") == "reseau", "un échec réseau se nomme", str(panne))
        maj._interroger = lever(urllib.error.HTTPError(  # type: ignore[arg-type]
            "https://exemple.invalide", 404, "Not Found", {}, None))
        prive = maj.verifier("2.0.0", forcer=True)
        verifier(prive.get("raison") == "indisponible",
                 "un dépôt injoignable se nomme autrement", str(prive))
    finally:
        maj._interroger = interrogation
        journal.info, journal.attention = ecrire_info, ecrire_attention


def essai_barre_taches() -> None:
    titre("Barre des tâches : plomberie COM en ctypes pur")

    from app import barre_taches

    if sys.platform != "win32":
        print("  (hors Windows, sans objet)")
        return

    objet = barre_taches._objet()
    verifier(objet is not None, "l'objet ITaskbarList3 se crée et s'initialise")

    # Sans fenêtre déclarée, tout doit rester inerte et silencieux.
    verifier(not barre_taches.disponible(), "sans fenêtre connue, le module est inerte")
    barre_taches.progression(50)
    barre_taches.erreur()
    barre_taches.effacer()
    verifier(True, "les appels sans fenêtre ne lèvent rien")

    verifier(
        barre_taches.definir_fenetre("Scribouille-fenetre-qui-n-existe-pas") == 0,
        "une fenêtre introuvable renvoie zéro sans erreur",
    )


# ---------------------------------------------------------------------------
# 7. Langue de l'interface
# ---------------------------------------------------------------------------

def essai_langues() -> None:
    titre("Langue de l'interface : détection, bascule, indépendance")

    from app import presets

    verifier(langues.normaliser("fr-FR") == "fr", "une locale complète est ramenée au code")
    verifier(langues.normaliser("en_US") == "en", "le tiret bas est accepté")
    verifier(langues.normaliser("de-DE") == "", "une langue non prise en charge est refusée")
    verifier(langues.normaliser(None) == "", "une valeur absente ne casse rien")
    verifier(langues.detecter_systeme() in langues.LANGUES,
             "la détection système rend toujours une langue connue",
             langues.detecter_systeme())
    verifier(langues.LANGUE_DEFAUT == "en",
             "hors francophonie, le repli documenté est l'anglais")

    try:
        langues.definir("fr")
        verifier(presets.nom_preset("qualite") == "Qualité maximale",
                 "les presets parlent français", presets.nom_preset("qualite"))
        verifier(stockage.formater_octets(1536) == "1,5 Ko",
                 "le séparateur décimal français s'applique")
        verifier(presets.formater_duree(3725).startswith("1 h"),
                 "les durées sont formatées", presets.formater_duree(3725))

        langues.definir("en")
        verifier(presets.nom_preset("qualite") == "Highest quality",
                 "la bascule change les textes produits par Python",
                 presets.nom_preset("qualite"))
        verifier(stockage.formater_octets(1536) == "1.5 KB",
                 "le séparateur décimal et les unités suivent la langue",
                 stockage.formater_octets(1536))
        verifier(langues.t("cle.qui.nexiste.pas") == "cle.qui.nexiste.pas",
                 "une clé absente se voit au lieu de planter")
        verifier(langues.tn("lect.remplacements", 1) == "1 replacement in the file.",
                 "le singulier est choisi", langues.tn("lect.remplacements", 1))
        verifier(langues.tn("lect.remplacements", 3) == "3 replacements in the file.",
                 "le pluriel est choisi", langues.tn("lect.remplacements", 3))
        verifier("{" not in langues.t("app.copie_ia", n=42),
                 "toutes les variables nommées sont substituées")
        verifier("{texte}" in langues.t("gabarit.defaut"),
                 "les accolades du gabarit ne sont pas consommées par la substitution")
    finally:
        langues.definir("fr")


# ---------------------------------------------------------------------------
# 8. Modèle laissé incomplet par un téléchargement interrompu
#
# Aucun modèle réel n'est téléchargé : on fabrique de fausses arborescences de
# cache huggingface dans un dossier temporaire, ce qui suffit à prouver la
# détection, la suppression ciblée, et le fait que le chargement bascule bien
# vers un nouveau téléchargement.
# ---------------------------------------------------------------------------

DEPOT_ABIME = "Systran/faster-whisper-large-v3"
DEPOT_SAIN = "Systran/faster-whisper-small"
DEPOT_TRONQUE = "Systran/faster-whisper-medium"
DEPOT_EN_COURS = "Systran/faster-whisper-base"


def _fabriquer_modele(racine: Path, depot: str, poids: int | None,
                      config: bool = True, en_cours: bool = False) -> Path:
    """
    Fabrique un dossier de cache huggingface. `poids` à None laisse le snapshot
    sans « model.bin », c'est exactement ce que laisse une coupure.
    """
    from app import moteur

    dossier = racine / (moteur.PREFIXE_CACHE + depot.replace("/", "--"))
    snapshot = dossier / "snapshots" / ("0" * 40)
    snapshot.mkdir(parents=True)
    (dossier / "refs").mkdir()
    (dossier / "refs" / "main").write_text("0" * 40, encoding="utf-8")
    if config:
        (snapshot / "config.json").write_text("{}", encoding="utf-8")
    if poids is not None:
        (snapshot / moteur.NOM_POIDS).write_bytes(b"0" * poids)
    if en_cours:
        (dossier / "blobs").mkdir(exist_ok=True)
        (dossier / "blobs" / ("a" * 16 + moteur.SUFFIXE_INCOMPLET)).write_bytes(b"0" * 128)
    return dossier


def essai_modele_incomplet(base: Path) -> None:
    titre("Modèle incomplet : détection, suppression ciblée, retéléchargement")

    from types import SimpleNamespace

    from app import chemins, moteur

    racine = base / "modeles-fictifs"
    racine.mkdir()

    complet = _fabriquer_modele(racine, DEPOT_SAIN, moteur.TAILLE_MINIMALE_POIDS + 1)
    abime = _fabriquer_modele(racine, DEPOT_ABIME, None)
    tronque = _fabriquer_modele(racine, DEPOT_TRONQUE, 4096)
    en_cours = _fabriquer_modele(racine, DEPOT_EN_COURS,
                                 moteur.TAILLE_MINIMALE_POIDS + 1, en_cours=True)
    voisin = racine / "mes-affaires"
    voisin.mkdir()
    (voisin / "note.txt").write_text("a garder", encoding="utf-8")

    # -- détection ---------------------------------------------------------
    etat = moteur.etat_modele(DEPOT_SAIN, racine)
    verifier(etat["etat"] == "complet", "un modèle entier est vu comme complet", str(etat))

    etat = moteur.etat_modele(DEPOT_ABIME, racine)
    verifier(etat["etat"] == "incomplet" and etat["reparable"],
             "un snapshot sans model.bin est vu comme incomplet et réparable", str(etat))
    verifier(moteur.NOM_POIDS in etat["motif"], "le motif nomme le fichier absent",
             etat["motif"])

    etat = moteur.etat_modele(DEPOT_TRONQUE, racine)
    verifier(etat["etat"] == "incomplet", "un model.bin tronqué est vu comme incomplet",
             str(etat))

    etat = moteur.etat_modele(DEPOT_EN_COURS, racine)
    verifier(etat["etat"] == "incomplet",
             "un fichier « .incomplete » suffit à déclasser le modèle", str(etat))

    etat = moteur.etat_modele("Systran/faster-whisper-tiny", racine)
    verifier(etat["etat"] == "absent", "un modèle jamais téléchargé reste « absent »",
             str(etat))

    # -- suppression, et rien d'autre --------------------------------------
    verifier(moteur.supprimer_modele(DEPOT_ABIME, racine), "le modèle incomplet est supprimé")
    verifier(not abime.exists(), "son dossier a bien disparu")
    verifier(complet.is_dir() and tronque.is_dir() and en_cours.is_dir(),
             "les autres modèles sont intacts")
    verifier(voisin.is_dir() and (voisin / "note.txt").exists(),
             "un dossier voisin étranger au cache n'est pas touché")
    verifier(len(list(racine.iterdir())) == 4, "un seul dossier en moins",
             str(sorted(p.name for p in racine.iterdir())))

    verifier(not moteur.supprimer_modele(DEPOT_ABIME, racine),
             "supprimer deux fois ne lève rien et ne prétend rien")
    verifier(not moteur.supprimer_modele("", racine),
             "un nom de modèle vide n'efface rien")
    verifier(racine.is_dir() and len(list(racine.iterdir())) == 4,
             "le dossier des modèles est toujours là")

    # -- après réparation, le chemin du téléchargement -----------------------
    verifier(moteur.etat_modele(DEPOT_ABIME, racine)["etat"] == "absent",
             "une fois réparé, le modèle est simplement « absent », donc à télécharger")

    # -- téléchargement mené par l'application ------------------------------
    #
    # Rien n'est jamais descendu ici : `_telecharger` et le test de connexion
    # sont remplacés, et l'on compte leurs appels. C'est ce comptage qui prouve
    # la promesse du hors-ligne, autant que le bon enchaînement des étapes.
    ancien = chemins.DOSSIER_MODELES
    ancien_telecharger = moteur._telecharger
    ancien_connexion = moteur.connexion_disponible
    ancienne_place = moteur.espace_libre_octets
    chemins.DOSSIER_MODELES = racine
    appels: list[str] = []
    messages: list[tuple[str, str]] = []
    reseau: list[str] = []

    def journal_ui(niveau: str, texte: str) -> None:
        messages.append((niveau, texte))

    def derniers_textes() -> str:
        return " | ".join(texte for _, texte in messages)

    try:
        moteur.connexion_disponible = lambda delai=4.0: (
            reseau.append("test") or True)
        # Place disponible fixée, sinon le résultat dépendrait du disque du poste
        # qui exécute le contrôle. Le cas du disque plein est traité plus bas.
        moteur.espace_libre_octets = lambda dossier: 50 * 1024 ** 3

        # -- un modèle complet ne touche à rien --------------------------
        reseau.clear()
        moteur._telecharger = lambda modele: reseau.append("telechargement")
        etat = moteur.assurer_modele_telecharge(DEPOT_SAIN, signaler=journal_ui)
        verifier(etat["etat"] == "complet" and not reseau,
                 "un modèle complet en local ne déclenche aucun appel réseau",
                 str(reseau))
        verifier(moteur.chemin_instanciation(DEPOT_SAIN).endswith("0" * 40),
                 "un modèle complet est instancié par son dossier, jamais par son nom",
                 moteur.chemin_instanciation(DEPOT_SAIN))
        verifier(moteur.chemin_instanciation("Systran/faster-whisper-tiny")
                 == "Systran/faster-whisper-tiny",
                 "un modèle absent reste désigné par son nom de dépôt")

        # -- le téléchargement rend un dossier sans model.bin -------------
        #
        # C'est le cas de production du 21 août : huggingface se replie en
        # silence sur le cache et rend un dossier partiel. Plus question
        # d'instancier là-dessus.
        messages.clear()
        moteur._telecharger = lambda modele: str(
            _fabriquer_modele(racine, DEPOT_ABIME, None))
        try:
            moteur.assurer_modele_telecharge("large-v3", signaler=journal_ui)
            verifier(False, "un téléchargement sans model.bin lève une erreur métier")
        except moteur.EchecTelechargement as exc:
            verifier(True, "un téléchargement sans model.bin lève une erreur métier")
            verifier("large-v3" in exc.message and "3,1 Go" in exc.message,
                     "le message nomme le modèle et son poids", exc.message)
            verifier("4,0 Go" in exc.message,
                     "le message chiffre la place nécessaire", exc.message)
            verifier("model.bin" not in exc.message and "Unable" not in exc.message,
                     "aucun jargon technique ne remonte à l'écran", exc.message)
        except Exception as exc:
            verifier(False, "un téléchargement sans model.bin lève une erreur métier",
                     f"{type(exc).__name__}: {exc}")
        verifier(any(niveau == "erreur" for niveau, _ in messages),
                 "l'échec est aussi porté au journal de l'interface", derniers_textes())
        verifier(abime.is_dir(),
                 "le dossier partiel est CONSERVÉ, la reprise doit rester possible")

        # -- espace disque insuffisant, détecté avant de télécharger -------
        messages.clear()
        reseau.clear()
        moteur.espace_libre_octets = lambda dossier: 900 * 1024 ** 2
        moteur._telecharger = lambda modele: reseau.append("telechargement")
        try:
            moteur.assurer_modele_telecharge("large-v3", signaler=journal_ui)
            verifier(False, "un disque trop plein lève une erreur métier")
        except moteur.EchecTelechargement as exc:
            verifier(True, "un disque trop plein lève une erreur métier")
            verifier("900 Mo" in exc.message and "4,0 Go" in exc.message,
                     "le message oppose la place restante à la place nécessaire",
                     exc.message)
        verifier(not reseau, "rien n'est téléchargé quand la place manque", str(reseau))
        moteur.espace_libre_octets = lambda dossier: 50 * 1024 ** 3

        # -- dépôt injoignable --------------------------------------------
        messages.clear()
        reseau.clear()
        moteur.connexion_disponible = lambda delai=4.0: False
        try:
            moteur.assurer_modele_telecharge("large-v3", signaler=journal_ui)
            verifier(False, "un dépôt injoignable lève une erreur métier")
        except moteur.EchecTelechargement as exc:
            verifier(True, "un dépôt injoignable lève une erreur métier")
            verifier("connexion" in exc.message.lower(),
                     "le message parle de la connexion Internet", exc.message)
        verifier(not reseau, "rien n'est téléchargé sans réseau", str(reseau))
        moteur.connexion_disponible = lambda delai=4.0: True

        # -- le chargement complète le modèle puis instancie ---------------
        messages.clear()

        def telecharger_pour_de_bon(modele: str) -> str:
            appels.append(modele)
            dossier = moteur.dossier_cache_modele(modele, racine)
            snapshot = dossier / "snapshots" / ("0" * 40)
            snapshot.mkdir(parents=True, exist_ok=True)
            (snapshot / "config.json").write_text("{}", encoding="utf-8")
            (snapshot / moteur.NOM_POIDS).write_bytes(
                b"0" * (moteur.TAILLE_MINIMALE_POIDS + 1))
            return str(snapshot)

        moteur._telecharger = telecharger_pour_de_bon
        instances: list[str] = []
        instance = moteur.MoteurTranscription(
            SimpleNamespace(peripherique="cpu", fils_calcul=4), forcer_processeur=True)
        instance._instancier = lambda modele: instances.append(modele) or "modele-simule"

        instance.charger(DEPOT_TRONQUE, journal_ui)
        verifier(appels == [DEPOT_TRONQUE], "le modèle tronqué est complété une seule fois",
                 str(appels))
        verifier(tronque.is_dir(),
                 "son dossier n'est PAS effacé : effacer, c'est perdre la reprise")
        verifier(instances == [DEPOT_TRONQUE], "le modèle est instancié une seule fois",
                 str(instances))
        verifier(any("incomplet" in texte for _, texte in messages),
                 "l'interface est prévenue que le modèle était incomplet",
                 derniers_textes())

        # -- filet de sécurité : des poids que CTranslate2 refuse ----------
        essais = {"n": 0}

        def instancier_capricieux(modele: str):
            essais["n"] += 1
            if essais["n"] == 1:
                raise RuntimeError(
                    f"Unable to open file 'model.bin' in model '{complet}'")
            return "modele-simule"

        appels.clear()
        instance.liberer()
        instance._instancier = instancier_capricieux
        instance.charger(DEPOT_SAIN, journal_ui)
        verifier(essais["n"] == 2, "un refus sur model.bin déclenche une seule reprise",
                 str(essais["n"]))
        verifier(appels == [DEPOT_SAIN],
                 "la reprise passe par un retéléchargement, une fois", str(appels))

        # Deuxième fichier de la même file, même modèle, même refus : la
        # réparation ne doit PAS recommencer. C'est ce qui bouclait au journal.
        essais["n"] = 0
        appels.clear()
        instance.liberer()
        instance._instancier = instancier_capricieux
        try:
            instance.charger(DEPOT_SAIN, journal_ui)
            verifier(False, "le refus remonte au lieu de relancer la réparation")
        except RuntimeError:
            verifier(True, "le refus remonte au lieu de relancer la réparation")
        verifier(essais["n"] == 1 and not appels,
                 "un seul essai, aucune réparation de plus dans la même file",
                 f"essais={essais['n']} appels={appels}")
    finally:
        chemins.DOSSIER_MODELES = ancien
        moteur._telecharger = ancien_telecharger
        moteur.connexion_disponible = ancien_connexion
        moteur.espace_libre_octets = ancienne_place
        chemins.confiner_cache_huggingface()

    verifier(moteur._poids_illisible(RuntimeError("Unable to open file 'model.bin'")),
             "l'erreur de faster-whisper est reconnue")
    verifier(not moteur._poids_illisible(OSError("disque plein")),
             "une erreur sans rapport ne déclenche pas de réparation")
    verifier(moteur._manque_de_place(OSError(28, "No space left on device")),
             "un disque plein est reconnu comme tel")
    verifier(not moteur._manque_de_place(OSError("Connection reset by peer")),
             "une coupure réseau n'est pas prise pour un disque plein")
    verifier(moteur.poids_attendu_octets("large-v3") == int(3.1 * 1024 ** 3),
             "le poids attendu de large-v3 est connu")
    verifier(moteur.poids_attendu_octets(presets.MODELE_TURBO) == int(1.6 * 1024 ** 3),
             "celui du modèle turbo aussi, le préréglage Rapide reste couvert")


def essai_amorce() -> None:
    """
    L'amorce du glossaire suit la langue PARLÉE, jamais celle de l'interface.

    C'est un prompt : le décodeur la lit comme un début de texte. Une phrase
    française en tête d'un enregistrement anglais pousse le modèle vers le
    français, ce qui est exactement l'inverse du service rendu.
    """
    titre("Amorce du glossaire, dans la langue parlée")

    glossaire = "Valenciennes\nCTranslate2\nScribouille"
    try:
        # Interface en anglais, enregistrement en français : c'est la langue
        # parlée qui décide, l'en-tête doit rester français.
        langues.definir("en")
        francais = vocabulaire.construire_amorce(glossaire, langue="fr")
        langues.definir("fr")
        anglais = vocabulaire.construire_amorce(glossaire, langue="en")
    finally:
        langues.definir("fr")

    verifier(francais["amorce"].startswith("Vocabulaire de cet enregistrement"),
             "langue parlée « fr » : en-tête français", francais["amorce"][:48])
    verifier(anglais["amorce"].startswith("Vocabulary for this recording"),
             "langue parlée « en » : en-tête anglais", anglais["amorce"][:48])
    verifier(vocabulaire.construire_amorce(glossaire, langue="de")["amorce"]
             .startswith("Vocabulary for this recording"),
             "toute autre langue parlée prend l'anglais")
    verifier(vocabulaire.construire_amorce(glossaire, langue="")["amorce"]
             .startswith("Vocabulary for this recording"),
             "détection automatique : anglais, on ne présume de rien")
    verifier("Valenciennes" in francais["amorce"] and "Valenciennes" in anglais["amorce"],
             "les termes du glossaire sont les mêmes des deux côtés")

    # Le budget se compte sur la forme réellement envoyée, en-tête compris.
    long_glossaire = "\n".join(f"Terminologie{n}" for n in range(400))
    tronquee = vocabulaire.construire_amorce(long_glossaire, langue="fr")
    verifier(tronquee["tronque"] is True, "un glossaire trop long est tronqué")
    verifier(tronquee["jetons"] < vocabulaire.LIMITE_JETONS_AMORCE,
             "le décompte reste sous la limite de 224 jetons", str(tronquee["jetons"]))
    verifier(tronquee["jetons"] == vocabulaire._compter_jetons(tronquee["amorce"]),
             "le décompte porte sur la chaîne réellement envoyée")


# ---------------------------------------------------------------------------
# 9. Compatibilité du renommage (2.4.0)
# ---------------------------------------------------------------------------

def essai_renommage(base: Path) -> None:
    """
    Ce que la 2.4.0 a laissé en place, exprès, en changeant de nom.

    Le fichier compagnon d'une transcription faite avant le renommage porte
    l'ancien marqueur de format. La vue de relecture doit continuer de l'ouvrir :
    sinon le changement de nom effacerait le surlignage de tout ce qui a déjà
    été transcrit. Le dossier de données, lui, ne bouge pas du tout.
    """
    titre("Compatibilité du renommage")

    bac = base / "renommage"
    bac.mkdir(parents=True, exist_ok=True)
    sortie = bac / "reunion.txt"
    sortie.write_text("Texte de la réunion.\n", encoding="utf-8")

    def poser(marqueur: str) -> None:
        compagnon.chemin_pour(sortie).write_text(json.dumps({
            "format": marqueur,
            "version": 1,
            "produit_par": "peu importe",
            "segments": [{"d": 0.0, "f": 1.5, "t": "Texte de la réunion."}],
        }, ensure_ascii=False), encoding="utf-8")

    poser(compagnon.FORMAT_HISTORIQUE)
    ancien = compagnon.lire(sortie)
    verifier(ancien is not None, "un compagnon écrit avant le renommage se relit")

    poser(compagnon.FORMAT)
    verifier(compagnon.lire(sortie) is not None, "un compagnon écrit après aussi")

    poser("autre-chose")
    verifier(compagnon.lire(sortie) is None, "un marqueur inconnu reste refusé")

    verifier(chemins.NOM_DOSSIER_UTILISATEUR == "WhiScribe",
             "le dossier de données garde son nom d'origine",
             chemins.NOM_DOSSIER_UTILISATEUR)
    verifier(chemins.RACINE.name == "WhiScribe" or not chemins.EST_GELE,
             "la racine des données suit ce nom dans la version installée")


# ---------------------------------------------------------------------------
# 10. Transfert des modèles : le backend « xet » est coupé
# ---------------------------------------------------------------------------

def essai_transfert_xet() -> None:
    """
    Le téléchargement des poids passe par le HTTPS ordinaire, jamais par « xet ».

    huggingface_hub lit `HF_HUB_DISABLE_XET` au moment où son module de
    constantes est chargé : la poser après coup ne servirait à rien. Elle est
    donc posée par `app/__init__.py`, et c'est cela qu'on vérifie ici, en
    regardant ce que la bibliothèque a réellement retenu.
    """
    titre("Transfert des modèles, backend « xet »")

    verifier(os.environ.get("HF_HUB_DISABLE_XET") == "1",
             "la variable est posée dès l'import du paquet",
             str(os.environ.get("HF_HUB_DISABLE_XET")))

    from huggingface_hub import constants

    verifier(constants.HF_HUB_DISABLE_XET is True,
             "huggingface_hub a bien retenu que xet est coupé",
             str(constants.HF_HUB_DISABLE_XET))
    from huggingface_hub.utils import _runtime

    verifier(_runtime.is_xet_available() is False,
             "le hub ne propose plus le transfert xet")

    # Un utilisateur qui pose la variable lui-même garde le dernier mot : c'est
    # un `setdefault`, pas une affectation. Vérifié dans un vrai processus fils,
    # le nôtre ayant déjà tout importé.
    environnement = dict(os.environ, HF_HUB_DISABLE_XET="0")
    sortie = subprocess.run(
        [sys.executable, "-c",
         "import app, os; print(os.environ['HF_HUB_DISABLE_XET'])"],
        cwd=str(RACINE), env=environnement, capture_output=True, text=True,
    )
    verifier(sortie.stdout.strip() == "0",
             "un choix explicite de l'utilisateur n'est pas écrasé",
             sortie.stdout.strip() or sortie.stderr.strip()[:80])


# ---------------------------------------------------------------------------
# 11. Recalibration à chaud des estimations de durée
# ---------------------------------------------------------------------------

def essai_calibration(base: Path) -> None:
    """
    Ce que la machine mesure d'elle-même remplace le facteur venu d'ailleurs.

    Tout se passe dans un dossier temporaire : la racine des données est
    déplacée le temps du contrôle, les mesures réelles du poste ne sont ni lues
    ni touchées.
    """
    titre("Recalibration à chaud des durées")

    bac = base / "calibration"
    bac.mkdir(parents=True, exist_ok=True)
    racine_reelle = chemins.RACINE
    chemins.RACINE = bac

    machine = materiel.Materiel(cpu_nom="Processeur d'essai", coeurs_logiques=16,
                                ram_go=32.0)
    autre_machine = materiel.Materiel(cpu_nom="Autre processeur", coeurs_logiques=4,
                                      ram_go=8.0)
    try:
        # -- repli : sans mesure, le facteur statique du preset ----------------
        statique = presets.facteur_temps_reel("qualite", machine)
        verifier(calibration.facteur_mesure("large-v3", "cpu", 8, machine) == 0.0,
                 "sans mesure, aucun facteur mesuré")
        verifier(statique > 0, "le facteur statique reste servi", str(statique))
        verifier(not calibration.fichier().exists(),
                 "aucun fichier écrit tant que rien n'a été mesuré")

        # -- une transcription réussie est retenue -----------------------------
        # 1 200 s d'audio en 2 484 s de calcul, soit le facteur 2,07 relevé le
        # 21 août 2026 sur le 7800X3D, là où le preset annonçait 1,35.
        lisse = calibration.enregistrer("large-v3", "cpu", 8, 1200.0, 2484.0, machine)
        verifier(abs(lisse - 2.07) < 0.001, "facteur mesuré à partir du temps réel",
                 str(lisse))
        verifier(calibration.fichier().exists(), "le fichier de mesures est écrit")
        verifier(abs(calibration.facteur_mesure("large-v3", "cpu", 8, machine) - 2.07) < 0.001,
                 "et relu tel quel au lancement suivant")

        mesure = presets.facteur_temps_reel("qualite", machine)
        verifier(abs(mesure - 2.07) < 0.001,
                 "l'estimation du preset suit la mesure, pas le chiffre d'origine",
                 f"{statique} puis {mesure}")
        verifier(presets.estimer_secondes(3600, "qualite", machine) > 3600 * 2,
                 "une heure d'audio est annoncée pour plus de deux heures de calcul")

        # -- ce qui distingue deux situations ----------------------------------
        verifier(calibration.facteur_mesure("large-v3", "cpu", 5, machine) == 0.0,
                 "une autre largeur de faisceau ne réutilise pas la mesure")
        verifier(calibration.facteur_mesure(presets.MODELE_TURBO, "cpu", 5, machine) == 0.0,
                 "un autre modèle non plus")
        verifier(calibration.facteur_mesure("large-v3", "cuda", 8, machine) == 0.0,
                 "un autre périphérique non plus")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 8, autre_machine) == 0.0,
                 "et un dossier de données recopié sur une autre machine repart à zéro")

        # -- lissage : la mesure fraîche pèse plus, la longue aussi -------------
        calibration.enregistrer("large-v3", "cpu", 8, 1200.0, 1200.0, machine)
        deux = calibration.facteur_mesure("large-v3", "cpu", 8, machine)
        verifier(1.0 < deux < 2.07,
                 "deux mesures donnent une valeur intermédiaire", str(deux))
        verifier(deux < (1.0 + 2.07) / 2,
                 "penchée vers la plus récente, pas une moyenne plate", str(deux))

        # Seules les cinq dernières comptent.
        for _ in range(6):
            calibration.enregistrer("large-v3", "cpu", 8, 600.0, 300.0, machine)
        donnees = calibration.charger(calibration.signature_machine(machine))
        historique = donnees["mesures"][calibration.cle_mesure("large-v3", "cpu", 8)]["historique"]
        verifier(len(historique) == calibration.MESURES_RETENUES,
                 "l'historique est borné aux cinq dernières mesures", str(len(historique)))
        verifier(abs(calibration.facteur_mesure("large-v3", "cpu", 8, machine) - 0.5) < 0.001,
                 "les vieilles mesures finissent par sortir")

        # -- mesures écartées ---------------------------------------------------
        calibration.oublier()
        verifier(calibration.enregistrer("large-v3", "cpu", 8, 30.0, 60.0, machine) == 0.0,
                 "un enregistrement trop court n'est pas mesuré")
        verifier(calibration.enregistrer("large-v3", "cpu", 8, 1200.0, 0.0, machine) == 0.0,
                 "un temps de calcul nul non plus")
        verifier(calibration.enregistrer("large-v3", "cpu", 8, 1200.0, 200000.0, machine) == 0.0,
                 "une valeur aberrante non plus")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 8, machine) == 0.0,
                 "aucune de ces trois n'a été retenue")

        # -- fichier abîmé : on repart des facteurs statiques --------------------
        calibration.fichier().write_text("{ceci n'est pas du JSON", encoding="utf-8")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 8, machine) == 0.0,
                 "un fichier de mesures illisible ne fait pas tomber l'application")
        verifier(presets.facteur_temps_reel("qualite", machine) == statique,
                 "et l'estimation revient au facteur statique")
    finally:
        chemins.RACINE = racine_reelle


def principal() -> int:
    print(f"Vérification des fonctions périphériques de Scribouille\n{'=' * 54}")
    with tempfile.TemporaryDirectory(prefix="scribouille-verif-") as brut:
        base = Path(brut)
        essai_surveillance(base)
        essai_versions()
        essai_nommage()
        essai_stockage(base)
        essai_cadence_maj()
        essai_barre_taches()
        essai_langues()
        essai_amorce()
        essai_modele_incomplet(base)
        essai_renommage(base)
        essai_transfert_xet()
        essai_calibration(base)

    print(f"\n{'=' * 54}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
