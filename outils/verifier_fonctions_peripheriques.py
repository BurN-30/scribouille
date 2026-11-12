"""
Vérification en ligne de commande des fonctions périphériques.

Vingt-six sujets, tous vérifiables sans ouvrir de fenêtre, sans transcrire quoi que
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
  12. les bornes de hauteur des fenêtres, qui ne s'expriment plus en unités
     `vh` : le grossissement de l'interface les multipliait, et le panneau
     d'aide sortait de l'écran.
  13. la reprise après coupure : le moteur ne repasse que la fin du signal,
     mais la séparation des locuteurs reçoit l'enregistrement entier ;
  14. la détection des cartes graphiques : écrans virtuels écartés, carte la
     mieux dotée en tête, mémoire réelle lue au lieu du plafond de WMI ;
  15. la sortie de pyannote.audio 4, un objet et non plus une annotation,
     dont les tours de parole se lisent bien ;
  16. le nombre de fils de calcul, un par cœur physique.
  17. la topologie des processeurs hybrides (cœurs performants, efficaces,
     basse consommation), lue dans un tampon fabriqué pour un Core Ultra 5 225U ;
  18. les estimations de durée sur un portable de 15 W et avec OpenVINO ;
  19. la sortie du bridage d'énergie de Windows (EcoQoS) pendant le calcul ;
  20. les fenêtres du moteur OpenVINO et leurs horodatages ;
  21. l'intégrité d'un modèle au format OpenVINO et la voie hors ligne ;
  22. le réglage de vitesse propre au poste, sa suspension après un plantage ;
  23. le banc d'essai : taux d'erreur, conseil, rapport sans nom ni chemin ;
  24. la commande d'installation d'OpenVINO, sans télémétrie, et hors ligne.
  25. la comparaison des moteurs sur un vrai enregistrement ;
  26. la campagne de mesure : taux d'erreur et intervalles, verdict, corpus
      (annotations, chevauchements, empreintes), rapport sans texte ni chemin,
      exemples anciens du glossaire, application du verdict, veille suspendue ;
  27. OpenVINO sur la puce graphique : faisceau non pris en charge (campagne,
      réglage du poste), garde-fou des répétitions à température, filet de la
      transcription (rejeu puis repli) sur un moteur simulé, réglage de
      comparaison des réunions ; épreuve d'endurance (taux, rapport sans texte).

Rien de ce que fait ce script ne touche à l'installation : tout se passe dans
un dossier temporaire, effacé à la fin.

    .venv\\Scripts\\python outils\\verifier_fonctions_peripheriques.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import json
import os
import re
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
        verifier(langues.tn("lect.remplacements", 1) == "1 place corrected.",
                 "le singulier est choisi", langues.tn("lect.remplacements", 1))
        verifier(langues.tn("lect.remplacements", 3) == "3 places corrected.",
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

    # Depuis la 3.0, le dossier de données est à notre nom ; l'ancien est repris
    # au premier lancement (vérifications dans outils/verifier_socle.py).
    verifier(chemins.NOM_DOSSIER_UTILISATEUR == "Scribouille" and chemins.NOM_DOSSIER_ANCIEN == "WhiScribe",
             "le dossier de données est à notre nom, l'ancien est connu pour être repris",
             chemins.NOM_DOSSIER_UTILISATEUR)
    verifier(chemins.RACINE.name == "Scribouille" or not chemins.EST_GELE,
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
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
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
        verifier(calibration.facteur_mesure("large-v3", "cpu", 5, machine) == 0.0,
                 "sans mesure, aucun facteur mesuré")
        verifier(statique > 0, "le facteur statique reste servi", str(statique))
        verifier(not calibration.fichier().exists(),
                 "aucun fichier écrit tant que rien n'a été mesuré")

        # -- confiance : une mesure courte ne déplace pas tout -------------------
        verifier(calibration.enregistrer("large-v3", "cpu", 5, 78.0, 156.0, machine) == 0.0,
                 "une transcription de 78 s n'est pas retenue (mise en route trop lourde)")
        un_a_un = presets.facteur_temps_reel("qualite", machine, lot=0)
        calibration.enregistrer("large-v3", "cpu", 5, 200.0, 2.07 * 200.0, machine)
        partiel = presets.facteur_temps_reel("qualite", machine, lot=0)
        verifier(un_a_un < partiel < un_a_un + (2.07 - un_a_un) * 0.3,
                 "une seule mesure de 3 min 20 rapproche l'annonce de la mesure, sans la remplacer",
                 f"{un_a_un} puis {partiel}")
        calibration.oublier()

        # Le reste de ce bloc éprouve la mesure elle-même : confiance pleine.
        pivot = calibration.PIVOT_CONFIANCE_S
        calibration.PIVOT_CONFIANCE_S = 0.0

        # -- une transcription réussie est retenue -----------------------------
        # 1 200 s d'audio en 2 484 s de calcul, soit le facteur 2,07 relevé le
        # 21 août 2026 sur le 7800X3D, là où le preset annonçait 1,35.
        lisse = calibration.enregistrer("large-v3", "cpu", 5, 1200.0, 2484.0, machine)
        verifier(abs(lisse - 2.07) < 0.001, "facteur mesuré à partir du temps réel",
                 str(lisse))
        verifier(calibration.fichier().exists(), "le fichier de mesures est écrit")
        verifier(abs(calibration.facteur_mesure("large-v3", "cpu", 5, machine) - 2.07) < 0.001,
                 "et relu tel quel au lancement suivant")

        mesure = presets.facteur_temps_reel("qualite", machine, lot=0)
        verifier(abs(mesure - 2.07) < 0.001,
                 "l'estimation du preset suit la mesure, pas le chiffre d'origine",
                 f"{statique} puis {mesure}")
        verifier(presets.estimer_secondes(3600, "qualite", machine, lot=0) > 3600 * 2,
                 "une heure d'audio est annoncée pour plus de deux heures de calcul")

        # -- le traitement par lots a sa propre mesure -------------------------
        verifier(presets.taille_lot("qualite", machine) == 8,
                 "32 Go de mémoire : le preset traite par lots de 8")
        verifier(presets.taille_lot("qualite", autre_machine) == 0,
                 "8 Go de mémoire : le preset reste passage par passage")
        verifier(presets.facteur_temps_reel("qualite", machine) == statique,
                 "une mesure sans lots ne sert pas d'estimation au traitement par lots")
        calibration.enregistrer("large-v3", "cpu", 5, 1200.0, 1620.0, machine, lot=8)
        verifier(abs(presets.facteur_temps_reel("qualite", machine) - 1.35) < 0.001,
                 "la mesure par lots sert l'estimation par lots")
        verifier(abs(calibration.facteur_mesure("large-v3", "cpu", 5, machine) - 2.07) < 0.001,
                 "sans toucher à celle du traitement un à un")

        # -- ce qui distingue deux situations ----------------------------------
        verifier(calibration.facteur_mesure("large-v3", "cpu", 8, machine) == 0.0,
                 "une autre largeur de faisceau ne réutilise pas la mesure")
        verifier(calibration.facteur_mesure(presets.MODELE_TURBO, "cpu", 5, machine) == 0.0,
                 "un autre modèle non plus")
        verifier(calibration.facteur_mesure("large-v3", "cuda", 5, machine) == 0.0,
                 "un autre périphérique non plus")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 5, autre_machine) == 0.0,
                 "et un dossier de données recopié sur une autre machine repart à zéro")

        # -- lissage : la mesure fraîche pèse plus, la longue aussi -------------
        calibration.enregistrer("large-v3", "cpu", 5, 1200.0, 1200.0, machine)
        deux = calibration.facteur_mesure("large-v3", "cpu", 5, machine)
        verifier(1.0 < deux < 2.07,
                 "deux mesures donnent une valeur intermédiaire", str(deux))
        verifier(deux < (1.0 + 2.07) / 2,
                 "penchée vers la plus récente, pas une moyenne plate", str(deux))

        # Seules les cinq dernières comptent.
        for _ in range(6):
            calibration.enregistrer("large-v3", "cpu", 5, 600.0, 300.0, machine)
        donnees = calibration.charger(calibration.signature_machine(machine))
        historique = donnees["mesures"][calibration.cle_mesure("large-v3", "cpu", 5)]["historique"]
        verifier(len(historique) == calibration.MESURES_RETENUES,
                 "l'historique est borné aux cinq dernières mesures", str(len(historique)))
        verifier(abs(calibration.facteur_mesure("large-v3", "cpu", 5, machine) - 0.5) < 0.001,
                 "les vieilles mesures finissent par sortir")

        # -- mesures écartées ---------------------------------------------------
        calibration.oublier()
        verifier(calibration.enregistrer("large-v3", "cpu", 5, 30.0, 60.0, machine) == 0.0,
                 "un enregistrement trop court n'est pas mesuré")
        verifier(calibration.enregistrer("large-v3", "cpu", 5, 1200.0, 0.0, machine) == 0.0,
                 "un temps de calcul nul non plus")
        verifier(calibration.enregistrer("large-v3", "cpu", 5, 1200.0, 200000.0, machine) == 0.0,
                 "une valeur aberrante non plus")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 5, machine) == 0.0,
                 "aucune de ces trois n'a été retenue")

        # -- fichier abîmé : on repart des facteurs statiques --------------------
        calibration.fichier().write_text("{ceci n'est pas du JSON", encoding="utf-8")
        verifier(calibration.facteur_mesure("large-v3", "cpu", 5, machine) == 0.0,
                 "un fichier de mesures illisible ne fait pas tomber l'application")
        verifier(presets.facteur_temps_reel("qualite", machine) == statique,
                 "et l'estimation revient au facteur statique")
    finally:
        chemins.RACINE = racine_reelle
        calibration.PIVOT_CONFIANCE_S = pivot


# ---------------------------------------------------------------------------
# 12. Mise en page des fenêtres, au grossissement près
# ---------------------------------------------------------------------------

def essai_bornes_fenetres() -> None:
    """
    Aucune fenêtre ne se borne en `vh`, et le script publie la taille réelle.

    Une lecture de fichiers, faute de navigateur : le grossissement passe par
    `zoom` sur le corps de page, et `zoom` multiplie aussi les unités `vh`. Une
    fenêtre bornée à 85vh dépassait donc par le bas dès que l'utilisateur
    grossissait l'interface. Le contrôle est statique, mais il attrape le retour
    d'un `vh` dans une règle de dimensionnement, qui est exactement la manière
    dont ce défaut reviendrait.
    """
    titre("Bornes des fenêtres, grossissement compris")

    styles = (RACINE / "web" / "styles.css").read_text(encoding="utf-8")
    script = (RACINE / "web" / "app.js").read_text(encoding="utf-8")

    # Les commentaires parlent de vh, c'est leur sujet : on ne lit que les règles.
    regles = re.sub(r"/\*.*?\*/", "", styles, flags=re.S)
    dimensions = [ligne.strip() for ligne in regles.splitlines()
                  if re.search(r"\b(height|width|max-height|max-width)\s*:", ligne)]
    en_vh = [ligne for ligne in dimensions if re.search(r"\d\s*v[hw]\b", ligne)]

    verifier(not en_vh, "aucune dimension exprimée en vh ou vw hors des variables",
             " | ".join(en_vh[:3]))
    verifier("--hauteur-fenetre: 100vh;" in styles and "--largeur-fenetre: 100vw;" in styles,
             "les variables gardent une valeur de repli juste au grossissement 1")
    verifier("height: var(--hauteur-fenetre)" in regles,
             "le voile et le corps de page suivent la fenêtre réelle")
    verifier("max-height: 100%;" in regles,
             "les fenêtres se bornent au voile, qui porte déjà la marge")
    verifier("--hauteur-fenetre" in script and "window.innerHeight" in script,
             "le script publie la hauteur réelle divisée par le grossissement")
    verifier("addEventListener('resize', mesurerFenetre)" in script,
             "et la remesure quand la fenêtre change de taille")


def essai_reprise_locuteurs(base: Path) -> None:
    """
    Une transcription reprise après coupure sépare les locuteurs sur TOUT l'audio.

    Le moteur ne reçoit que la fin du signal, à partir du dernier segment
    sauvegardé. La séparation des locuteurs, elle, doit recevoir le signal
    complet : ses tours de parole partent de zéro, comme les horodatages des
    segments auxquels ils sont attribués. Avant la correction, elle recevait le
    signal tronqué, et toutes les étiquettes étaient décalées de la position de
    reprise. Moteur, décodage et séparation sont simulés : rien n'est transcrit.
    """
    titre("Reprise après coupure et séparation des locuteurs")

    import numpy as np

    from app import diarisation, moteur, reprise, sorties, traitement
    from app import audio as audio_module

    frequence = audio_module.FREQUENCE
    duree, position = 20.0, 8.0
    vus: dict[str, float] = {}

    class MoteurSimule:
        tokeniseur = None

        def charger(self, modele, signaler=None):
            pass

        def liberer(self):
            pass

        def transcrire(self, signal, duree_totale, langue, reglages, amorce="",
                       progression=None, interrompu=None, decalage=0.0, sur_segment=None):
            vus["moteur"] = signal.size / frequence
            vus["decalage"] = decalage
            return [moteur.Segment(debut=decalage + 1.0, fin=decalage + 3.0, texte="suite")], {}

    def diariser_simule(signal, frequence_recue, **_options):
        vus["locuteurs"] = signal.size / frequence_recue
        return [{"debut": 0.0, "fin": duree, "locuteur": "Locuteur 1"}]

    originaux = {
        (audio_module, "decoder"): audio_module.decoder,
        (reprise, "lire_etat"): reprise.lire_etat,
        (reprise, "lire_segments"): reprise.lire_segments,
        (diarisation, "diariser"): diarisation.diariser,
        (diarisation, "disponible"): diarisation.disponible,
        (sorties, "ecrire_tout"): sorties.ecrire_tout,
        (traitement.calibration, "enregistrer"): traitement.calibration.enregistrer,
    }
    audio_module.decoder = lambda chemin, filtres_salle=False: np.zeros(
        int(duree * frequence), dtype=np.float32)
    reprise.lire_etat = lambda cle: {"ecoule": 5.0}
    reprise.lire_segments = lambda cle: [
        moteur.Segment(debut=0.0, fin=position, texte="début")]
    diarisation.diariser = diariser_simule
    # La séparation simulée vaut une séparation installée : sans cela, la file
    # ne la tente plus (elle sait qu'elle ne tournerait pas).
    diarisation.disponible = lambda: True
    sorties.ecrire_tout = lambda *a, **k: []
    traitement.calibration.enregistrer = lambda *a, **k: None
    try:
        source = base / "reprise-locuteurs.wav"
        source.write_bytes(b"\0")
        element = traitement.Element(identifiant="r1", chemin=str(source),
                                     nom=source.name, reprise="cle-simulee")
        file = traitement.FileTraitement(materiel.Materiel(coeurs_logiques=4))
        config = {"diarisation": True, "sauvegarde_progressive": False,
                  "utiliser_glossaire": False, "appliquer_corrections": False,
                  "dossier_sortie": str(base), "langue": "fr"}
        reglages = {"filtres_salle": False, "modele": "tiny", "preset": "rapide",
                    "beam_size": 5, "preset_nom": "Rapide"}
        file._traiter(element, config, reglages, MoteurSimule(), traitement.Rappels())
    finally:
        for (module, nom), valeur in originaux.items():
            setattr(module, nom, valeur)

    verifier(abs(vus.get("moteur", 0) - (duree - position)) < 0.01,
             "le moteur ne reçoit que la fin du signal", str(vus.get("moteur")))
    verifier(vus.get("decalage") == position,
             "les horodatages repris sont décalés de la position atteinte")
    verifier(abs(vus.get("locuteurs", 0) - duree) < 0.01,
             "la séparation des locuteurs reçoit l'enregistrement entier",
             str(vus.get("locuteurs")))
    verifier(element.etat == "termine", "le fichier repris va jusqu'au bout")


def essai_sortie_pyannote() -> None:
    """
    Les tours de parole se lisent aussi dans la sortie de pyannote.audio 4.

    La 4.x rend un `DiarizeOutput` au lieu d'une `Annotation` : sans adaptation,
    la séparation échouait toujours sur `itertracks` et la transcription sortait
    sans locuteurs. Les objets de pyannote sont imités, rien n'est installé.
    """
    titre("Sortie de pyannote.audio 3 et 4")

    from app import diarisation

    verifier(os.environ.get("PYANNOTE_METRICS_ENABLED") == "false",
             "la télémétrie de pyannote.audio 4 est coupée avant tout import")
    verifier(os.environ.get("HF_HUB_DISABLE_TELEMETRY") == "1",
             "celle de huggingface_hub aussi")

    class Periode:
        def __init__(self, debut, fin):
            self.start, self.end = debut, fin

    class Annotation:
        def __init__(self, *tours):
            self.tours = tours

        def itertracks(self, yield_label=False):
            for debut, fin, etiquette in self.tours:
                yield Periode(debut, fin), "_", etiquette

    class SortieV4:
        speaker_diarization = Annotation((0, 5, "A"), (4, 9, "B"))
        exclusive_speaker_diarization = Annotation((0, 4, "A"), (4, 9, "B"))

    verifier(diarisation.annotation_de(SortieV4()) is SortieV4.exclusive_speaker_diarization,
             "pyannote 4 : la version exclusive, sans chevauchement, est retenue")
    ancienne = Annotation((0, 3, "A"))
    verifier(diarisation.annotation_de(ancienne) is ancienne,
             "pyannote 3 : l'annotation rendue est lue telle quelle")

    originaux = (diarisation.indisponibilite, diarisation.jeton, diarisation._charger_pipeline)
    try:
        diarisation.indisponibilite = lambda: ""
        diarisation.jeton = lambda: "jeton-simule"
        diarisation._charger_pipeline = lambda cle, signaler: (lambda entree, **k: SortieV4())
        import numpy as np
        try:
            import torch  # noqa: F401
            tours = diarisation.diariser(np.zeros(16000, dtype=np.float32), 16000)
            verifier([t["fin"] for t in tours] == [4.0, 9.0] and len({t["locuteur"] for t in tours}) == 2,
                     "diariser() rend deux locuteurs depuis une sortie 4.x", str(tours))
        except ImportError:
            print("  --    diariser() de bout en bout : PyTorch absent, contrôle sauté")
    finally:
        diarisation.indisponibilite, diarisation.jeton, diarisation._charger_pipeline = originaux


def essai_fils_calcul() -> None:
    """Un fil de calcul par cœur physique, comme le recommande CTranslate2."""
    titre("Fils de calcul")
    cas = {(8, 16): 8, (4, 8): 4, (6, 6): 4, (0, 12): 10, (2, 2): 1}
    for (physiques, logiques), attendu in cas.items():
        obtenu = materiel.Materiel(coeurs_physiques=physiques,
                                   coeurs_logiques=logiques).fils_calcul
        verifier(obtenu == attendu,
                 f"{physiques} cœurs / {logiques} fils : {attendu} fils de calcul", str(obtenu))
    repere = materiel.Materiel(coeurs_physiques=6, coeurs_logiques=12, ram_go=32.0)
    verifier(presets._coefficient_machine(repere) == 1.0,
             "l'estimation de repli se cale toujours sur les fils logiques de la machine repère")


def essai_cartes_graphiques() -> None:
    """
    Les écrans virtuels ne passent pas pour des cartes, la vraie mémoire est lue.

    Sur un poste équipé d'un logiciel de bureau à distance, Windows déclare des
    adaptateurs virtuels AVANT la vraie carte, et le résumé du matériel affichait
    le premier. WMI plafonne en outre la mémoire à 4 Go. La réponse de
    PowerShell est simulée, le registre aussi : rien ne dépend du poste.
    """
    titre("Détection des cartes graphiques")

    reponse = json.dumps([
        {"Name": "Parsec Virtual Display Adapter", "AdapterCompatibility": "Parsec",
         "AdapterRAM": 0},
        {"Name": "AMD Radeon(TM) Graphics", "AdapterCompatibility": "Advanced Micro Devices",
         "AdapterRAM": 512 * 1024 * 1024},
        {"Name": "AMD Radeon RX 7900 XT", "AdapterCompatibility": "Advanced Micro Devices",
         "AdapterRAM": 4095 * 1024 * 1024},
        {"Name": "Microsoft Basic Display Adapter", "AdapterCompatibility": "Microsoft",
         "AdapterRAM": 0},
    ])

    class Resultat:
        stdout = reponse

    executer, registre = materiel.subprocess.run, materiel._memoires_registre
    plateforme = materiel.sys.platform
    try:
        materiel.subprocess.run = lambda *a, **k: Resultat()
        materiel.sys.platform = "win32"
        materiel._memoires_registre = lambda: {}
        sans_registre = materiel._cartes_graphiques()
        materiel._memoires_registre = lambda: {"AMD Radeon RX 7900 XT": 20464}
        avec_registre = materiel._cartes_graphiques()
    finally:
        materiel.subprocess.run, materiel._memoires_registre = executer, registre
        materiel.sys.platform = plateforme

    noms = [c.nom for c in avec_registre]
    verifier(noms == ["AMD Radeon RX 7900 XT", "AMD Radeon(TM) Graphics"],
             "adaptateurs virtuels écartés, carte la mieux dotée en tête", str(noms))
    verifier(avec_registre[0].memoire_mo == 20464,
             "la mémoire réelle vient du registre du pilote")
    plafonnee = next(c for c in sans_registre if c.nom == "AMD Radeon RX 7900 XT")
    verifier(plafonnee.memoire_mo == 0,
             "sans registre, la valeur plafonnée de WMI n'est pas affichée")


# ---------------------------------------------------------------------------
# 17 à 22. Poste de travail à processeur hybride, moteur OpenVINO, banc d'essai
# ---------------------------------------------------------------------------

def _tampon_topologie(coeurs: list[tuple[int, list[int]]], caches_l3: list[list[int]]) -> bytes:
    """Tampon de GetLogicalProcessorInformationEx fabriqué à la main."""
    import struct

    morceaux = []
    for classe, logiques in coeurs:
        masque = sum(1 << i for i in logiques)
        corps = struct.pack("<BBHH16sH", 1 if len(logiques) > 1 else 0, classe, 0, 0,
                            b"\0" * 16, 1) + struct.pack("<QH6s", masque, 0, b"\0" * 6)
        morceaux.append(struct.pack("<II", 0, 8 + len(corps)) + corps)
    for logiques in caches_l3:
        masque = sum(1 << i for i in logiques)
        corps = struct.pack("<BBHII18sH", 3, 12, 64, 12 << 20, 0, b"\0" * 18, 1) \
            + struct.pack("<QH6s", masque, 0, b"\0" * 6)
        morceaux.append(struct.pack("<II", 2, 8 + len(corps)) + corps)
    return b"".join(morceaux)


def essai_topologie() -> None:
    """
    Familles de cœurs lues comme Windows les décrit, et fils de calcul qui en
    découlent. Le Core Ultra 5 225U (2 performants avec hyperthreading, 8
    efficaces, 2 basse consommation hors du L3, 14 fils) est fabriqué de toutes
    pièces : aucun poste de test n'en a un.
    """
    titre("Processeur hybride : topologie et fils de calcul")

    coeurs_225u = [(1, [0, 1]), (1, [2, 3])] + [(0, [i]) for i in range(4, 12)] \
        + [(0, [12]), (0, [13])]
    topo = materiel.analyser_topologie(_tampon_topologie(coeurs_225u, [list(range(12))]))
    verifier((topo.performants, topo.efficaces, topo.basse_consommation, topo.hybride)
             == (2, 8, 2, True), "Core Ultra 5 225U : 2 performants, 8 efficaces, 2 basse consommation",
             str(topo))
    verifier(topo.logiques_principaux == list(range(12)),
             "les cœurs basse consommation sont écartés de l'affinité possible")
    machine = materiel.Materiel(cpu_nom="Intel(R) Core(TM) Ultra 5 225U", coeurs_physiques=12,
                                coeurs_logiques=14, topologie=topo, ram_go=32.0,
                                basse_consommation=materiel.est_basse_consommation(
                                    "Intel(R) Core(TM) Ultra 5 225U"))
    verifier(machine.fils_calcul == 10, "225U : un fil par cœur performant ou efficace (10)",
             str(machine.fils_calcul))
    machine.fils_imposes = 6
    verifier(machine.fils_calcul == 6 and machine.fils_automatiques == 10,
             "un réglage mesuré impose ses fils, le choix automatique reste lisible")
    machine.fils_imposes = 40
    verifier(machine.fils_calcul == 14, "un réglage imposé reste borné aux fils logiques")

    alder = [(1, [2 * i, 2 * i + 1]) for i in range(6)] + [(0, [i]) for i in range(12, 20)]
    topo_alder = materiel.analyser_topologie(_tampon_topologie(alder, [list(range(20))]))
    verifier((topo_alder.performants, topo_alder.efficaces, topo_alder.basse_consommation)
             == (6, 8, 0), "6 performants et 8 efficaces sans basse consommation (bureau)")
    verifier(materiel.Materiel(coeurs_physiques=14, coeurs_logiques=20,
                               topologie=topo_alder).fils_calcul == 14,
             "sans cœurs basse consommation, la règle d'un fil par cœur physique tient")

    lunar = [(1, [i]) for i in range(4)] + [(0, [i]) for i in range(4, 8)]
    topo_lunar = materiel.analyser_topologie(_tampon_topologie(lunar, [list(range(4))]))
    verifier((topo_lunar.performants, topo_lunar.efficaces, topo_lunar.basse_consommation)
             == (4, 4, 0), "deux familles dont une hors du L3 (Lunar Lake) : comptées efficaces")

    homogene = [(0, [2 * i, 2 * i + 1]) for i in range(8)]
    topo_h = materiel.analyser_topologie(_tampon_topologie(homogene, [list(range(16))]))
    verifier((topo_h.performants, topo_h.hybride) == (8, False),
             "processeur homogène 8 cœurs / 16 fils : ni hybride ni basse consommation")
    verifier(materiel.Materiel(coeurs_physiques=8, coeurs_logiques=16,
                               topologie=topo_h).fils_calcul == 8,
             "sur un processeur de bureau homogène, rien ne change (8 fils sur 8 cœurs)")
    verifier(materiel.analyser_topologie(b"\x00" * 5).performants == 0,
             "un tampon tronqué ne fait pas tomber la détection")

    reel = materiel._topologie()
    import psutil

    physiques = psutil.cpu_count(logical=False) or 0
    total = reel.performants + reel.efficaces + reel.basse_consommation
    verifier(sys.platform != "win32" or total == physiques,
             f"ce poste : {total} cœurs lus par Windows, {physiques} selon psutil")

    for nom, attendu in (("Intel(R) Core(TM) Ultra 5 225U", True), ("Intel(R) Core(TM) i7-1255U", True),
                         ("Intel(R) Core(TM) Ultra 7 258V", True), ("AMD Ryzen 5 7530U", True),
                         ("Intel(R) Core(TM) Ultra 7 155H", False),
                         ("AMD Ryzen 7 7800X3D 8-Core Processor", False)):
        verifier(materiel.est_basse_consommation(nom) == attendu,
                 f"« {nom} » " + ("est" if attendu else "n'est pas") + " un processeur basse consommation")


def essai_estimations_machine(base: Path) -> None:
    """Estimations honnêtes sur un portable de 15 W, conseil qui le dit."""
    titre("Estimations de durée selon la machine et le moteur")
    bac = base / "estimations"
    bac.mkdir(parents=True, exist_ok=True)
    racine_reelle = chemins.RACINE
    chemins.RACINE = bac
    pivot = calibration.PIVOT_CONFIANCE_S
    calibration.PIVOT_CONFIANCE_S = 0.0  # mesure tenue pour sûre dans ce bloc
    try:
        topo = materiel.Topologie(performants=2, efficaces=8, basse_consommation=2, hybride=True)
        portable = materiel.Materiel(cpu_nom="Intel(R) Core(TM) Ultra 5 225U", coeurs_physiques=12,
                                     coeurs_logiques=14, topologie=topo, ram_go=32.0,
                                     basse_consommation=True)
        bureau = materiel.Materiel(cpu_nom="Processeur de bureau", coeurs_physiques=8,
                                   coeurs_logiques=16, ram_go=32.0)
        rapide_portable = presets.facteur_temps_reel("rapide", portable)
        verifier(rapide_portable > 2.5 * presets.facteur_temps_reel("rapide", bureau),
                 "un processeur de 15 W est annoncé bien plus lent qu'un processeur de bureau",
                 str(rapide_portable))
        reco = presets.recommandation(portable)
        verifier(reco["preset_conseille"] == "rapide" and "1 h" in reco["phrase"],
                 "plus lent que le temps réel en Qualité : Rapide conseillé, chiffres à l'appui",
                 reco["phrase"])
        verifier(presets.recommandation(bureau)["preset_conseille"] == "qualite",
                 "sur un processeur de bureau, le conseil reste « Qualité maximale »")
        verifier(presets._coefficient_machine(materiel.Materiel(coeurs_physiques=6,
                                                                coeurs_logiques=12)) == 1.0,
                 "la machine repère garde son coefficient de 1")

        portable.moteur, portable.peripherique_openvino = "openvino", "GPU"
        verifier(portable.cle_calcul == "openvino-gpu", "clé de mesure propre à OpenVINO sur puce graphique")
        verifier(abs(presets.facteur_temps_reel("rapide", portable) - 0.12) < 1e-6,
                 "OpenVINO sur puce Intel : repli sur la mesure publiée (0,12 avec turbo)")
        verifier(presets.recommandation(portable)["preset_conseille"] == "qualite",
                 "avec la puce graphique, « Qualité maximale » redevient raisonnable")
        calibration.enregistrer(presets.MODELE_TURBO, "openvino-gpu", 1, 300.0, 30.0, portable)
        verifier(abs(presets.facteur_temps_reel("rapide", portable) - 0.1) < 1e-6,
                 "une mesure OpenVINO (glouton, sans lots) remplace le repli")
        verifier(calibration.enregistrer("large-v3", "cpu", 5, 40.0, 40.0, portable) == 0.0
                 and calibration.enregistrer("large-v3", "cpu", 5, 40.0, 40.0, portable,
                                             duree_minimale=20.0) > 0,
                 "un extrait du banc (40 s) n'entre que si on l'accepte explicitement")
    finally:
        chemins.RACINE = racine_reelle
        calibration.PIVOT_CONFIANCE_S = pivot


def essai_energie() -> None:
    """Le bridage d'énergie de Windows se lève le temps du calcul, puis se rend."""
    titre("Bridage d'énergie (EcoQoS)")
    from app import energie

    if sys.platform != "win32":
        print("  --    hors Windows, contrôle sauté")
        return
    with energie.pleine_vitesse() as pose:
        verifier(pose, "SetProcessInformation accepte la sortie de l'EcoQoS")
    verifier(energie.rendre_au_systeme(), "la main est rendue au système")


def essai_openvino_decoupage() -> None:
    """Fenêtres sans silences, et temps ramenés à l'enregistrement d'origine."""
    titre("Moteur OpenVINO : fenêtres et horodatages")
    import numpy as np

    from app import moteur_openvino

    verifier(moteur_openvino.decouper(np.zeros(16000 * 20, dtype=np.float32)) == [],
             "un silence de 20 s ne produit aucune fenêtre (rien à inventer)")
    passages = [{"start": 16000 * 2, "end": 16000 * 5}, {"start": 16000 * 10, "end": 16000 * 12}]
    corr = moteur_openvino.Correspondance(passages)
    verifier(abs(corr.duree - 5.0) < 1e-6, "la fenêtre ne garde que la parole (3 s + 2 s)")
    verifier(abs(corr.origine(1.0) - 3.0) < 1e-6 and abs(corr.origine(3.5) - 10.5) < 1e-6,
             "un temps de la fenêtre retombe au bon endroit de l'enregistrement")
    verifier(abs(corr.origine(99.0) - 12.0) < 1e-6, "un temps hors fenêtre est borné à sa fin")
    verifier(moteur_openvino._taux_compression("bonjour " * 40) > moteur_openvino.SEUIL_COMPRESSION
             and moteur_openvino._taux_compression(
                 "Les plages sont nombreuses, car Auckland est à cheval sur deux ports.")
             < moteur_openvino.SEUIL_COMPRESSION,
             "une boucle de répétition est repérée, une phrase normale non")
    from app import moteur

    verifier(moteur.est_modele_openvino("OpenVINO/whisper-large-v3-int8-ov")
             and not moteur.est_modele_openvino("large-v3"), "dépôts OpenVINO reconnus")
    verifier(presets.depot_openvino(presets.MODELE_TURBO) == "OpenVINO/whisper-large-v3-turbo-int8-ov",
             "le modèle Rapide a son équivalent OpenVINO")


def essai_modele_openvino_incomplet(base: Path) -> None:
    """Un dossier OpenVINO sans décodeur est incomplet, avec le décodeur il est complet."""
    titre("Moteur OpenVINO : intégrité d'un modèle")
    from app import moteur

    racine = base / "modeles-ov"
    depot = "OpenVINO/whisper-tiny-int8-ov"
    snapshot = racine / "models--OpenVINO--whisper-tiny-int8-ov" / "snapshots" / "abc"
    snapshot.mkdir(parents=True, exist_ok=True)
    for nom in moteur.FICHIERS_OPENVINO:
        (snapshot / nom).write_text("{}", encoding="utf-8")
    (snapshot / "openvino_encoder_model.bin").write_bytes(b"0" * (moteur.TAILLE_MINIMALE_POIDS + 1))
    etat = moteur.etat_modele(depot, racine)
    verifier(etat["etat"] == "incomplet" and "decoder" in etat["motif"],
             "décodeur absent : modèle incomplet, motif nommé", str(etat))
    (snapshot / "openvino_decoder_model.bin").write_bytes(b"0" * (moteur.TAILLE_MINIMALE_POIDS + 1))
    verifier(moteur.etat_modele(depot, racine)["etat"] == "complet", "tous les fichiers : complet")
    langues.definir("fr")
    phrase = moteur.voie_hors_ligne(depot)
    verifier("models--OpenVINO--whisper-tiny-int8-ov" in phrase and "huggingface.co/" + depot in phrase,
             "la voie hors ligne nomme le dossier à recopier et le dépôt d'origine")


def essai_reglage_machine(base: Path) -> None:
    """Réglage du banc : signé pour ce poste, ignoré ailleurs, suspendu après un plantage."""
    titre("Réglage de vitesse propre au poste")
    from app import moteur_openvino, reglage_machine

    racine_reelle = chemins.RACINE
    temoin_reel = moteur_openvino.TEMOIN_CHARGEMENT
    chemins.RACINE = base / "reglage"
    chemins.RACINE.mkdir(parents=True, exist_ok=True)
    moteur_openvino.TEMOIN_CHARGEMENT = chemins.RACINE / "temoin.txt"
    try:
        poste = materiel.Materiel(cpu_nom="Processeur d'essai", coeurs_physiques=8, coeurs_logiques=16)
        config: dict = {}
        reglage_machine.enregistrer(config, poste, {"moteur": "ctranslate2", "fils": 6, "lot": 4})
        verifier(poste.fils_calcul == 6 and reglage_machine.lot_impose(config, poste) == 4,
                 "fils et lots du banc appliqués sur ce poste")
        autre = materiel.Materiel(cpu_nom="Autre processeur", coeurs_physiques=8, coeurs_logiques=16)
        effet = reglage_machine.appliquer_au_materiel(config, autre)
        verifier(not effet and autre.fils_calcul == 8 and reglage_machine.lot_impose(config, autre) is None,
                 "recopié sur une autre machine, le réglage est ignoré")
        reglage_machine.oublier(config, poste)
        verifier(poste.fils_calcul == 8 and poste.moteur == "ctranslate2", "retour à l'automatique")

        installe, vus = moteur_openvino.installe, moteur_openvino.peripheriques_disponibles
        moteur_openvino.installe = lambda: True
        moteur_openvino.peripheriques_disponibles = lambda forcer=False: ["CPU", "GPU"]
        try:
            reglage_machine.enregistrer(config, poste, {"moteur": "openvino", "peripherique": "GPU"})
            verifier(poste.cle_calcul == "openvino-gpu", "OpenVINO sur puce graphique retenu")
            moteur_openvino.TEMOIN_CHARGEMENT.write_text("GPU", encoding="utf-8")
            effet = reglage_machine.appliquer_au_materiel(config, poste)
            verifier(effet.get("plantage") == "GPU" and poste.moteur == "ctranslate2",
                     "après un plantage au chargement, OpenVINO est suspendu au démarrage suivant")
            reglage_machine.enregistrer(config, poste, {"moteur": "openvino", "peripherique": "GPU"})
            verifier(not moteur_openvino.TEMOIN_CHARGEMENT.exists() and poste.moteur == "openvino",
                     "réappliquer le conseil lève la suspension")
            moteur_openvino.peripheriques_disponibles = lambda forcer=False: ["CPU"]
            effet = reglage_machine.appliquer_au_materiel(config, poste)
            verifier(effet.get("indisponible") and poste.moteur == "ctranslate2",
                     "périphérique disparu : le moteur habituel reprend la main")
        finally:
            moteur_openvino.installe, moteur_openvino.peripheriques_disponibles = installe, vus
    finally:
        chemins.RACINE = racine_reelle
        moteur_openvino.TEMOIN_CHARGEMENT = temoin_reel


def essai_banc() -> None:
    """Taux d'erreur, plan, conseil et rapport du banc, sans rien transcrire."""
    titre("Banc d'essai : mesure, conseil, rapport")
    from app import banc

    verifier(banc.taux_erreur_mots("Le chat dort.", "le chat dort") == 0.0
             and banc.taux_erreur_mots("un deux trois quatre", "un deux quatre") == 25.0,
             "taux d'erreur sur les mots, ponctuation et casse ignorées")
    verifier(banc.EXTRAIT.is_file() and banc.REFERENCE.is_file(),
             "l'extrait du banc et sa référence sont livrés avec l'application")

    topo = materiel.Topologie(performants=2, efficaces=8, basse_consommation=2, hybride=True,
                              logiques_principaux=list(range(12)))
    portable = materiel.Materiel(coeurs_physiques=12, coeurs_logiques=14, topologie=topo)
    verifier(banc.candidats_fils(portable) == [(10, False), (12, False), (14, False), (10, True)],
             "225U : 10, 12 et 14 fils, puis 10 fils cœurs basse consommation écartés",
             str(banc.candidats_fils(portable)))
    verifier(banc.candidats_fils(materiel.Materiel(coeurs_physiques=8, coeurs_logiques=16))
             == [(8, False), (16, False)], "processeur de bureau : 8 et 16 fils")

    def essai(etiquette, moteur_, facteur, wer, **k):
        e = banc.Essai(etiquette, moteur=moteur_, **k)
        e.resultat = {"etat": "ok", "facteur": facteur, "wer": wer, "duree_audio": 43.6,
                      "fils": k.get("fils", 0)}
        return e

    t = presets.MODELE_TURBO
    essais = [
        essai("a", "ctranslate2", 0.60, 9.5, modele=t, fils=10, lot=8),
        essai("b", "ctranslate2", 0.70, 9.5, modele=t, fils=12, lot=8),
        essai("c", "openvino", 0.10, 8.4, modele=t, peripherique="GPU", lot=0, faisceau=1),
        essai("d", "openvino", 0.05, 60.0, modele=t, peripherique="NPU", lot=0, faisceau=1),
        essai("e", "openvino", 0.30, 7.4, modele="large-v3", peripherique="GPU", lot=0, faisceau=1),
    ]
    conseil = banc.conseiller(portable, essais)
    verifier(conseil.get("moteur") == "openvino" and conseil.get("peripherique") == "GPU",
             "le plus rapide qui reste juste l'emporte (puce graphique)", str(conseil))
    verifier(conseil.get("fils") == 10 and conseil.get("lot") == 8,
             "un NPU rapide mais faux (60 % de WER) est écarté ; fils et lots du meilleur CTranslate2 gardés")
    verifier(conseil["facteurs"] == {"rapide": 0.10, "qualite": 0.30},
             "facteurs Rapide et Qualité du moteur retenu")
    essais[2].resultat = {"etat": "delai", "erreur": "plus de 420 s"}
    verifier(banc.conseiller(portable, essais).get("moteur") == "ctranslate2",
             "un périphérique bloqué n'est jamais conseillé")

    nom = os.environ.get("USERNAME") or "personne"
    texte = banc._masquer(f"utilisateur {nom}, dossier {Path.home()} et {chemins.RACINE}")
    verifier(nom not in texte and str(Path.home()) not in texte,
             "le rapport ne laisse passer ni nom d'utilisateur ni chemin", texte)
    rapport = banc.rediger(portable, essais, conseil, 300.0)
    verifier(str(Path.home()).lower() not in rapport.lower() and "Réglage conseillé" in rapport,
             "rapport rédigé sans chemin personnel")


def essai_extension_openvino() -> None:
    """Installation d'OpenVINO : sans dépendances (donc sans télémétrie), voie hors ligne."""
    titre("Extension OpenVINO : commande d'installation")
    from app import extensions

    arguments = extensions.arguments_pip(extensions.PAQUETS_OPENVINO, "", "", Path("cible"),
                                         sans_dependances=True)
    verifier("--no-deps" in arguments and not any("telemetry" in a for a in arguments),
             "trois roues sans dépendances : openvino-telemetry n'est pas posé")
    hors = extensions.arguments_pip(extensions.PAQUETS_OPENVINO, "https://pypi.org/simple", "",
                                    Path("cible"), sans_dependances=True, hors_ligne=Path("roues"))
    verifier("--no-index" in hors and "--find-links" in hors and "--index-url" not in hors,
             "voie hors ligne : aucun index consulté, seulement les roues déposées")
    verifier(extensions.options_reconnues(["--installer-openvino"]),
             "l'option d'installation est reconnue par le point d'entrée")


def essai_comparaison(base: Path) -> None:
    """Comparaison des moteurs : normalisation, alignement, référence, rapport sans texte."""
    titre("Comparaison des moteurs sur un vrai fichier")
    import random

    from app import banc, comparaison as c, materiel

    verifier([c.nombre_en_lettres(n) for n in (21, 71, 80, 91, 1990, 2022)] == [
        "vingt et un", "soixante et onze", "quatre vingt", "quatre vingt onze",
        "mille neuf cent quatre vingt dix", "deux mille vingt deux"],
        "nombres en lettres (21, 71, 80, 91, 1990, 2022)")
    verifier(c.ordinal_en_lettres(1) == "premier" and c.ordinal_en_lettres(3) == "troisième"
             and c.ordinal_en_lettres(9) == "neuvième", "ordinaux en lettres")
    verifier(c.normaliser("Euh, l'équipe livre le 3e lot à 14h30 : 25 % ; O.K. (rires)") == [
        "l", "équipe", "livre", "le", "troisième", "lot", "à", "quatorze", "heures", "trente",
        "vingt", "cinq", "pour", "cent", "ok"],
        "normalisation : élisions, ordinal, heure, pourcentage, ok, hésitation et annotation retirées")
    verifier(c.normaliser("deux mille vingt-deux") == c.normaliser("2022")
             and c.normaliser("p(eu)t-être") == c.normaliser("peut-être"),
             "« 2022 » et « deux mille vingt-deux » comptent pareil, élision notée dans le mot")

    hasard = random.Random(7)
    exact, couvert = True, True
    for _ in range(150):
        a = [hasard.choice("abcde") for _ in range(hasard.randint(1, 25))]
        b = [hasard.choice("abcde") for _ in range(hasard.randint(0, 25))]
        bilan = c.aligner(a, b)
        exact &= abs(bilan.taux("a") - banc.taux_erreur_mots(" ".join(a), " ".join(b))) < 0.01
        couvert &= ([o[1] for o in bilan.operations if o[0] != "ins"] == list(range(len(a)))
                    and [o[3] for o in bilan.operations if o[0] != "sup"] == list(range(len(b))))
    verifier(exact, "l'alignement donne le même WER que le banc (150 tirages)")
    verifier(couvert, "chaque mot des deux textes apparaît une fois dans l'alignement")
    ancien = c.CELLULES_MAX
    try:
        c.CELLULES_MAX = 50
        a = ("un deux trois quatre cinq six sept huit neuf dix " * 4).split()
        b = list(a)
        b[5], b[22] = "x", "y"
        del b[30]
        ancre = c.aligner(a, b)
    finally:
        c.CELLULES_MAX = ancien
    verifier(ancre.editions == 3, "alignement ancré des longs textes : mêmes trois écarts",
             str(ancre.editions))

    srt = base / "ref.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\nLocuteur 1 : Bonjour à tous\n\n"
                   "2\n00:00:04,000 --> 00:00:06,500\nMarie : on commence\n\n"
                   "3\n00:00:20,000 --> 00:00:22,000\nhors extrait\n", encoding="utf-8")
    ref = c.lire_reference(srt)
    verifier(ref.horodatee and [b[2] for b in ref.blocs][:2] == ["Bonjour à tous", "on commence"],
             "référence SRT : horodatages lus, noms de locuteurs retirés")
    texte, d, f, motif = c.reference_sur_extrait(ref, 0.0, 10.0, False)
    verifier(not motif and texte == "Bonjour à tous on commence" and d == 1.0 and f == 6.5,
             "seules les répliques comprises dans l'extrait sont gardées, fenêtre resserrée")
    txt = base / "export.txt"
    txt.write_text("=" * 68 + "\nTranscription : reunion.m4a\n" + "=" * 68 + "\nSource : x\n"
                   + "=" * 68 + "\n\n[00:00:01] Locuteur 1 : Bonjour à tous\n\n"
                   "[00:00:04] Locuteur 2 : on commence\nla suite\n", encoding="utf-8")
    ref_txt = c.lire_reference(txt)
    verifier(ref_txt.horodatee and len(ref_txt.blocs) == 2
             and ref_txt.blocs[1][2] == "on commence la suite" and ref_txt.blocs[0][1] == 4.0,
             "export texte de Scribouille : en-tête ignoré, horodatages et locuteurs compris")
    teams = base / "teams.txt"
    teams.write_text("Marie Durand   0:03\nBonjour à tous\n\nPaul Martin   1:02:05\nOn commence.\n",
                     encoding="utf-8")
    vtt = base / "teams.vtt"
    vtt.write_text("WEBVTT\n\nab12/3-0\n00:00:03.000 --> 00:00:05.500\n<v Marie Durand>Bonjour à tous</v>\n",
                   encoding="utf-8")
    ref_teams, ref_vtt = c.lire_reference(teams), c.lire_reference(vtt)
    verifier([b[0] for b in ref_teams.blocs] == [3.0, 3725.0]
             and c.normaliser(ref_teams.blocs[0][2]) == ["bonjour", "à", "tous"]
             and ref_vtt.blocs[0][:2] == (3.0, 5.5)
             and c.normaliser(ref_vtt.blocs[0][2]) == ["bonjour", "à", "tous"],
             "transcriptions de visioconférence : « Nom   0:03 » et WebVTT à balises <v>")
    brut = base / "brut.txt"
    brut.write_text("Bonjour à tous.\nOn commence.\n", encoding="utf-8")
    ref_brut = c.lire_reference(brut)
    verifier(c.reference_sur_extrait(ref_brut, 300.0, 900.0, False)[3] == "sans_horodatage"
             and c.reference_sur_extrait(ref_brut, 0.0, 60.0, True)[0] == "Bonjour à tous. On commence.",
             "texte brut : refusé sur un extrait, accepté sur le fichier entier")

    segments_a = [
        {"d": 0.0, "f": 3.0, "t": "Bonjour Bérénice, on lance le sprint",
         "m": [["Bonjour", 0.0, 0.5, 0.9], ["Bérénice,", 0.5, 1.0, 0.3], ["on", 1.0, 1.2, 0.9],
               ["lance", 1.2, 1.6, 0.9], ["le", 1.6, 1.8, 0.9], ["sprint", 1.8, 2.4, 0.4]]},
        {"d": 4.0, "f": 7.0, "t": "zygomatique pentagone hexagone octogone",
         "m": [["zygomatique", 4.0, 4.8, 0.9], ["pentagone", 4.8, 5.5, 0.9],
               ["hexagone", 5.5, 6.2, 0.9], ["octogone", 6.2, 7.0, 0.9]]},
    ]
    segments_b = [
        {"d": 0.0, "f": 3.0, "t": "Bonjour Bérénice, on lance le spring", "m": [
            ["Bonjour", 0.0, 0.5, -1], ["Bérénice,", 2.0, 2.4, -1], ["on", 1.0, 1.2, -1],
            ["lance", 1.2, 1.6, -1], ["le", 1.6, 1.8, -1], ["spring", 1.8, 2.4, -1]]},
    ]
    a, b = c.construire_texte(segments_a), c.construire_texte(segments_b)
    mesures = c.mesurer(a, b, ["sprint", "Bérénice"])
    r = mesures["repartition"]
    verifier(r["seulement_a"] == 1 and r["seulement_b"] == 0 and mesures["suppressions"] == 4,
             "un passage de quatre mots manquant chez OpenVINO est compté comme tel")
    verifier(mesures["ecarts_horodatage"] == 1, "un mot identique placé 1,5 s plus loin est relevé")
    verifier(mesures["incertains"] == 2 and mesures["incertains_divergents"] == 1,
             "mots incertains, et ceux qui tombent dans un passage divergent")
    verifier(mesures["glossaire"]["a"]["termes"] == 2 and mesures["glossaire"]["b"]["termes"] == 1
             and mesures["anglais_a"] == 1 and mesures["anglais_b"] == 0,
             "termes du glossaire et mots anglais comptés pour chaque moteur")
    corrige = c.construire_texte([{"d": 0.0, "f": 2.0, "t": "le Kubernetes tourne", "m": [
        ["le", 0.0, 0.3, 0.9], ["cube", 0.3, 0.8, 0.4], ["air", 0.8, 1.0, 0.4],
        ["net", 1.0, 1.2, 0.4], ["tourne", 1.2, 2.0, 0.9]]}])
    verifier(corrige.jetons[1].probabilite is None and corrige.jetons[2].debut == 1.2,
             "un mot réécrit par une correction perd sa probabilité, garde un horodatage voisin")

    mat = materiel.detecter()
    info = {"etat": "ok", "modele": "large-v3", "calcul_s": 10.0, "chargement_s": 1.0,
            "memoire_go": 2.0, "peripherique": "CPU", "faisceau": 1, "type_calcul": "int8"}
    phrase = c.normaliser("Bonjour Bérénice on lance le sprint zygomatique pentagone hexagone octogone")
    ref_infos = {"couverture_s": 7.0, "mots": 10, "format": "srt", "anglais": 1,
                 "a": c.mesurer_reference(phrase, a, 0.0, 7.0, ["sprint"]),
                 "b": c.mesurer_reference(phrase, b, 0.0, 7.0, ["sprint"])}
    rapport = c.rediger_rapport(mat, 7.0, 0.0, info, info, mesures, ref_infos,
                                {"langue": "fr", "preset": "qualite", "glossaire": True,
                                 "corrections": True})
    mots_du_texte = ("Bérénice", "zygomatique", "pentagone", "spring", "sprint", "Bonjour")
    verifier(not any(m.lower() in rapport.lower() for m in mots_du_texte),
             "le rapport de chiffres ne contient aucun mot de la transcription")
    verifier(str(Path.home()) not in rapport, "le rapport ne contient pas le dossier personnel")
    verifier(ref_infos["a"]["wer"] == 0.0 and ref_infos["b"]["wer"] == 50.0
             and ref_infos["b"]["glossaire_retrouves"] == 0 and ref_infos["a"]["glossaire_retrouves"] == 1,
             "taux d'erreur et termes du glossaire par rapport à la référence")
    piege = c.construire_texte([{"d": 0, "f": 1, "t": "a&b <i>x</i> \"y\"", "m": []}])
    page = c.rediger_page(base / "reunion.m4a", 0.0, piege, b,
                          {**c.mesurer(piege, b, []), "duree": 7.0}, None, "", None, info, info)
    verifier("<i>x</i>" not in page and "&lt;i&gt;" in page and "a&amp;b" in page,
             "la page échappe le texte transcrit")
    page3 = c.rediger_page(base / "reunion.m4a", 0.0, a, b, {**mesures, "duree": 7.0}, phrase, "",
                           {"a": {**ref_infos["a"], "rangs": list(range(len(a.jetons)))},
                            "b": {**ref_infos["b"], "rangs": list(range(len(b.jetons)))}}, info, info)
    verifier(page3.count("<th>") == 3 and "octogone" in page3,
             "avec une référence, la page montre trois colonnes")
    verifier(c.caler_sur_pauses(__import__("numpy").zeros(16000 * 10, dtype="float32"), False, False)
             == (0, 16000 * 10), "un extrait court n'est pas recadré")
    verifier(c.options_reconnues(["--comparer", "x.m4a"]) and c.lire_duree("00:05:00") == 300.0
             and c.lire_duree("600") == 600.0 and c.lire_duree("1:30") == 90.0,
             "options de la ligne de commande et durées « 00:05:00 », « 600 », « 1:30 »")


def essai_campagne(base: Path) -> None:
    """Campagne : taux d'erreur, intervalles, verdict, corpus, rapport sans texte, application."""
    titre("Campagne de mesure des réglages")
    import numpy as np

    from app import campagne as cp, config as config_module, corpus, energie, reglage_machine

    # Taux d'erreur contre une référence, chevauchements, insertions longues.
    reference = {"mots": [["bonjour", 0, 1, 0, False], ["tout", 1, 2, 0, False],
                          ["le", 2, 3, 0, True], ["monde", 3, 4, 0, True],
                          ["on", 4, 5, 1, True], ["commence", 5, 6, 1, False]]}
    segments = [{"d": 0.0, "f": 20.0, "t": "Bonjour tout le monde, alpha bravo charlie delta, on commence.",
                 "m": []},
                {"d": 20.0, "f": 22.0, "t": "voilà", "m": []}]
    m = cp.mesurer_extrait(reference, segments)
    verifier(m["mots_ref"] == 6 and m["sub"] == 0 and m["sup"] == 0 and m["ins"] == 5
             and m["insertions_longues"] == 1 and m["mots_insertions_longues"] == 4,
             "insertions comptées, quatre mots inventés d'affilée font une insertion longue")
    verifier(m["segments"] == 2 and m["segments_longs"] == 1, "un segment de plus de 15 s est relevé")
    manque = cp.mesurer_extrait(reference, [{"d": 0, "f": 3, "t": "bonjour tout commence", "m": []}])
    verifier(manque["chev_total"] == 3 and manque["chev_perdus"] == 3 and manque["hors_perdus"] == 0
             and manque["sup"] == 3, "mots perdus pendant un chevauchement, et seulement eux")
    avec_proba = cp.mesurer_extrait(reference, [{"d": 0, "f": 6, "t": "bonjour tout le monde on commande", "m": [
        ["bonjour", 0, 1, 0.9], ["tout", 1, 2, 0.9], ["le", 2, 3, 0.9], ["monde", 3, 4, 0.9],
        ["on", 4, 5, 0.9], ["commande", 5, 6, 0.3]]}])
    verifier(avec_proba["incertains"] == 1 and avec_proba["incertains_errones"] == 1
             and avec_proba["sub"] == 1, "un mot incertain qui est faux est compté comme tel")

    # Intervalles : rééchantillonnage des extraits, apparié entre réglages.
    erreurs, mots = [10, 12, 8, 11, 9] * 4, [100] * 20
    bas, haut = cp.intervalle(erreurs, mots)
    verifier(bas <= 10.0 <= haut and haut - bas < 3.0, "intervalle à 95 % autour du taux global",
             f"{bas}..{haut}")
    ecart, eb, eh = cp.ecart_apparie(erreurs, erreurs, mots)
    verifier(ecart == 0.0 and eb == 0.0 and eh == 0.0, "deux réglages identiques : écart nul, intervalle nul")
    ecart, eb, eh = cp.ecart_apparie([e + 3 for e in erreurs], erreurs, mots)
    verifier(ecart == 3.0 and eb > 0, "trois points de plus sur chaque extrait : écart significatif")

    # Verdict.
    ordre = [f"x{k}" for k in range(20)]

    def faux(erreurs_par_extrait: list[int]) -> dict:
        return {i: {"erreurs": e, "mots_ref": 100} for i, e in zip(ordre, erreurs_par_extrait)}

    rng = np.random.default_rng(3)
    base_err = [int(v) for v in rng.integers(15, 25, size=20)]
    par_extrait = {
        "ct2-v3-f5": faux(base_err),
        "ov-v3-f1": faux([e + (1 if k % 3 == 0 else 0) for k, e in enumerate(base_err)]),
        "ov-turbo-f1": faux([e + 4 for e in base_err]),
        "ct2-v3-f1": faux([max(0, e - 2) for e in base_err]),
    }
    resultats = {c: {"etat": "ok", "wer": 100.0 * sum(v["erreurs"] for v in d.values()) / 2000.0}
                 for c, d in par_extrait.items()}
    resultats["ct2-v3-f5"]["facteur"] = 0.9
    resultats["ov-v3-f1"]["facteur"] = 0.35
    resultats["ov-turbo-f1"]["facteur"] = 0.15
    resultats["ct2-v3-f1"]["facteur"] = 1.2
    d = cp.verdict(resultats, ordre, par_extrait)
    verifier(d["meilleur"] == "ct2-v3-f1" and not d["lignes"]["ct2-v3-f1"]["admissible"],
             "le plus juste, plus lent que la réunion, est écarté du choix")
    verifier(d["retenu"] == "ct2-v3-f5" and d["motif"] == "plus_juste_admissible",
             "aucun équivalent assez rapide : le plus juste des réglages admissibles",
             str(d.get("retenu")))
    resultats["ct2-v3-f1"]["facteur"] = 0.95
    par_extrait["ct2-v3-f1"] = faux(base_err)
    resultats["ct2-v3-f1"]["wer"] = resultats["ct2-v3-f5"]["wer"]
    d = cp.verdict(resultats, ordre, par_extrait)
    verifier(d["retenu"] == "ov-v3-f1" and d["lignes"]["ov-v3-f1"]["equivalent"]
             and not d["lignes"]["ov-turbo-f1"]["equivalent"],
             "moins d'un point d'écart : le plus rapide des équivalents ; quatre points : écarté",
             str(d.get("retenu")))
    verifier(cp.verdict({}, ordre, {}) == {}, "aucun réglage réussi : pas de verdict")

    # Corpus : annotations SPPAS, référence, chevauchements, en-tête WAV, mélange.
    verifier(corpus.nettoyer_jeton("p(eu)t-être") == "peut-être" and corpus.nettoyer_jeton("ex-") == ""
             and corpus.nettoyer_jeton("[sept,set]") == "sept" and corpus.nettoyer_jeton("SPEAKER_3") == ""
             and corpus.nettoyer_jeton("$Paris$") == "Paris" and corpus.nettoyer_jeton("@") == "",
             "annotations de la transcription manuelle retirées")
    pistes = {"a": [(0.0, 0.5, "#"), (0.5, 1.0, "bonjour"), (1.0, 1.5, "à"), (1.5, 2.0, "tous"),
                    (2.0, 3.0, "#"), (3.0, 3.5, "voilà")],
              "b": [(0.0, 1.2, "#"), (1.2, 1.6, "oui"), (1.6, 3.4, "#")]}
    ref = corpus.construire_reference(pistes, 0.0, 3.4)
    verifier([m[0] for m in ref["mots"]] == ["bonjour", "à", "tous", "oui"]
             and [m[4] for m in ref["mots"]] == [False, True, True, True],
             "référence rangée par prise de parole, chevauchements marqués, mot coupé au bord exclu")
    entete = b"RIFF" + (0).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little") + \
        (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (48000).to_bytes(4, "little") + \
        (96000).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little") + \
        b"data" + (0).to_bytes(4, "little")
    verifier(corpus.lire_entete(entete) == (1, 1, 48000, 16, 44), "en-tête WAV lu")
    fort, faible = np.ones(16000, dtype=np.float32) * 0.5, np.ones(16000, dtype=np.float32) * 0.01
    melange = corpus.melanger([fort, faible], [[(0.0, 1.0)], [(0.0, 1.0)]])
    verifier(melange.dtype == np.dtype("<i2") and int(np.max(np.abs(melange))) == int(0.9 * 32767),
             "pistes égalisées puis mélangées, crête à 0,9")
    from app.corpus_manifeste import MANIFESTE
    verifier(len(MANIFESTE["extraits"]) >= 15 and all(e["sha256_wav"] and e["sha256_ref"]
                                                      for e in MANIFESTE["extraits"])
             and 20 * 60 <= sum(e["fin"] - e["debut"] for e in MANIFESTE["extraits"]) <= 30 * 60,
             "manifeste du corpus : extraits figés et empreintes, 20 à 30 minutes")
    paquet = base / "paquet.zip"
    import zipfile
    with zipfile.ZipFile(paquet, "w") as z:
        z.writestr(MANIFESTE["extraits"][0]["id"] + ".wav", b"pas le bon contenu")
    dossier_corpus = base / "corpus"
    dossier_corpus.mkdir()
    poses = corpus._depuis_paquet(paquet, dossier_corpus)
    verifier(poses == 0 and not any(dossier_corpus.iterdir()),
             "un fichier du paquet à l'empreinte fausse est refusé")
    sources = corpus.SOURCES
    corpus.SOURCES = ("http://127.0.0.1:9",)
    try:
        corpus.telecharger("x", "0" * 64, 0, 10)
        refuse = False
    except corpus.ErreurCorpus as exc:
        refuse = exc.motif == "reseau"
    finally:
        corpus.SOURCES = sources
    verifier(refuse, "réseau refusé : erreur nommée, pas de traceback")

    # Rapport de chiffres : aucun mot du texte, aucun chemin.
    mat = materiel.detecter()
    secrets = ("zygomatique", "bérénice", "pentagone", "octogone")
    ref_secrete = {"mots": [[m, 0, 1, 0, False] for m in secrets]}
    seg_secret = [{"d": 0, "f": 1, "t": "Zygomatique Bérénice hexagone", "m": []}]
    mesure = cp.mesurer_extrait(ref_secrete, seg_secret)
    agregat = cp.agreger({"e1": mesure}, ["e1"])
    res = {"ov-v3-f1": {"etat": "ok", "facteur": 0.3, "chargement_s": 4, "memoire_go": 2.0,
                        "heure_debut": "2026-11-12 09:00", "heure_fin": "2026-11-12 09:10",
                        "peripherique": "GPU", "calcul_s": 3.0}}
    decision = cp.verdict({"ov-v3-f1": {**res["ov-v3-f1"], "wer": agregat["wer"]}}, ["e1"],
                          {"ov-v3-f1": {"e1": mesure}})
    rapport = cp.rediger_rapport(mat, {"extraits": 1, "reunions": 1, "duree_s": 60.0, "mots": 4,
                                       "chev": 0, "anglais": 0}, res, {"ov-v3-f1": agregat}, decision,
                                 {"ov-v3-f1": 5.0}, {}, {"termes": 12, "exemples": 12}, "GPU", 600.0)
    verifier(not any(s in rapport.lower() for s in secrets + ("hexagone",)),
             "le rapport de la campagne ne contient aucun mot de la référence ni du texte")
    verifier(str(Path.home()) not in rapport and "09:00" in rapport and "--campagne --appliquer" in rapport,
             "rapport sans chemin, avec l'heure de chaque réglage et la commande pour appliquer")
    verifier("12" in rapport and "exemple" in rapport.lower(),
             "le rapport dit combien de termes du glossaire sont des exemples d'origine, sans les citer")
    verifier(not any(t.lower() in rapport.lower() for t in vocabulaire.EXEMPLES_ANCIENS if len(t) > 3),
             "aucun terme du glossaire n'est cité")
    rapport_reunion = cp.rediger_rapport_reunion(
        mat, 600.0, res, {"ov-v3-f1": {"desaccord": 0.0, "mots": 3, "mots_ancre": 3, "en_plus": 0,
                                       "en_moins": 0}},
        "ov-v3-f1", "verdict", {"termes": 3, "exemples": 0}, {"ov-v3-f1": 1},
        {"ov-v3-f1": {"n": 1, "mediane": 1.0, "longs": 0}}, "GPU", 700.0)
    verifier(not any(s in rapport_reunion.lower() for s in secrets) and str(Path.home()) not in rapport_reunion,
             "le rapport d'une réunion réelle ne contient ni texte ni chemin")

    # Glossaire livré avec des exemples actifs par les anciennes versions.
    ancien = "# Glossaire\n\n" + "\n".join(vocabulaire.EXEMPLES_ANCIENS) + "\n"
    verifier(vocabulaire.glossaire_exemple_intact(ancien)
             and not vocabulaire.glossaire_exemple_intact(ancien + "Scribouille\n")
             and vocabulaire.nombre_exemples_anciens(vocabulaire.termes(ancien + "Scribouille\n")) == 12,
             "glossaire d'origine reconnu, un glossaire complété ne l'est plus")
    vocab_reel, corr_reel, modeles_reels = (chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS,
                                            dict(chemins.MODELES_FICHIERS_EXEMPLE))
    dossier_v = base / "vocab"
    dossier_v.mkdir()
    try:
        chemins.FICHIER_VOCABULAIRE = dossier_v / "vocabulaire.txt"
        chemins.FICHIER_CORRECTIONS = dossier_v / "corrections.txt"
        chemins.MODELES_FICHIERS_EXEMPLE.clear()
        chemins.MODELES_FICHIERS_EXEMPLE.update({
            chemins.FICHIER_VOCABULAIRE: RACINE / "vocabulaire.txt",
            chemins.FICHIER_CORRECTIONS: RACINE / "corrections.txt"})
        chemins.FICHIER_VOCABULAIRE.write_text(ancien, encoding="utf-8")
        corrections_anciennes = "\n".join(f"{a} => {b}" for a, b in vocabulaire.CORRECTIONS_ANCIENNES)
        chemins.FICHIER_CORRECTIONS.write_text(corrections_anciennes + "\nmaison => Maison\n", encoding="utf-8")
        remplaces = vocabulaire.retirer_exemples_anciens()
        verifier(remplaces == ["vocabulaire.txt"] and vocabulaire.termes(
            chemins.FICHIER_VOCABULAIRE.read_text(encoding="utf-8")) == []
                 and (dossier_v / "vocabulaire-exemples-anciens.txt").is_file()
                 and "maison => Maison" in chemins.FICHIER_CORRECTIONS.read_text(encoding="utf-8"),
                 "exemples d'origine remplacés (copie gardée), fichier retouché laissé tel quel")
    finally:
        chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS = vocab_reel, corr_reel
        chemins.MODELES_FICHIERS_EXEMPLE.clear()
        chemins.MODELES_FICHIERS_EXEMPLE.update(modeles_reels)

    # Application du verdict, signée pour le poste ; faisceau pris par la file.
    racine_reelle, config_reelle = chemins.RACINE, chemins.FICHIER_CONFIG
    chemins.RACINE = base / "appliquer"
    chemins.RACINE.mkdir()
    chemins.FICHIER_CONFIG = chemins.RACINE / "config.json"
    from app import moteur_openvino
    temoin_reel = moteur_openvino.TEMOIN_CHARGEMENT
    moteur_openvino.TEMOIN_CHARGEMENT = chemins.RACINE / "temoin.txt"
    enregistrer_reel = calibration.enregistrer
    calibration.enregistrer = lambda *a, **k: 0.0
    try:
        config_module.sauver({"preset": "qualite", "langue_interface": "fr"})
        cp.appliquer({"cle": "ct2-v3-f1", "moteur": "ctranslate2", "modele": "large-v3", "faisceau": 1,
                      "preset": "qualite", "peripherique": "cpu", "facteur": 0.6, "duree_audio": 1300.0,
                      "lot": 8})
        config = config_module.charger()
        verifier(config["reglage_machine"].get("faisceau") == 1
                 and config["reglage_machine"].get("source") == "campagne"
                 and reglage_machine.faisceau_impose(config, mat) == 1 and config["preset"] == "qualite",
                 "--appliquer écrit moteur, faisceau et preset, signés pour ce poste")
        verifier(reglage_machine.faisceau_impose({}, mat) is None,
                 "sans réglage, le faisceau reste celui du moteur")
    finally:
        chemins.RACINE, chemins.FICHIER_CONFIG = racine_reelle, config_reelle
        moteur_openvino.TEMOIN_CHARGEMENT = temoin_reel
        calibration.enregistrer = enregistrer_reel

    with energie.sans_veille() as pose:
        verifier(pose == (sys.platform == "win32"), "veille du système suspendue le temps du calcul")
    verifier(cp.options_reconnues(["--campagne"]) and cp.options_reconnues(["--campagne-essai", "{}"])
             and [r.cle for r in cp._choisir("ov-v3-f1,ct2-v3-f5")] == ["ov-v3-f1", "ct2-v3-f5"],
             "options de la ligne de commande et choix des réglages")
    try:
        cp._choisir("inconnu")
        refuse = False
    except Exception:
        refuse = True
    verifier(refuse, "un réglage inconnu est refusé avec un message")



def essai_campagne_candidats(base: Path) -> None:
    """Modèles candidats : sur demande seulement, hors verdict, interprète à part, poids absents."""
    titre("Campagne : modèles candidats")
    import os
    from app import campagne as cp

    verifier([r.cle for r in cp._choisir("")] == [r.cle for r in cp.CANDIDATS]
             and not any(r.candidat for r in cp.CANDIDATS),
             "sans --reglages, la campagne ne passe que les réglages de l'application")
    choisis = [r.cle for r in cp._choisir("candidats")]
    verifier(choisis == [r.cle for r in cp.MODELES_CANDIDATS] and all(cp.PAR_CLE[c].candidat for c in choisis),
             "« candidats » choisit tous les modèles candidats, et seulement eux")
    verifier([r.cle for r in cp._choisir("ov-turbo-f1,candidats,ov-turbo-f1")][:2]
             == ["ov-turbo-f1", cp.MODELES_CANDIDATS[0].cle],
             "réglages et groupe mêlés, sans doublon")
    verifier(len(cp._choisir("tous")) == len(cp.TOUS) == len(cp.PAR_CLE),
             "« tous » choisit le tout, chaque clé est unique")
    verifier(all(r.revision or r.converti for r in cp.MODELES_CANDIDATS),
             "chaque candidat téléchargé a sa révision figée")
    verifier("glouton" in cp.libelle(cp.PAR_CLE["onnx-parakeet3"])
             and "cohere" in cp.libelle(cp.PAR_CLE["hf-cohere"]),
             "libellé des moteurs de mesure")

    # Verdict : les candidats sont situés, jamais retenus.
    ordre = ["e1", "e2"]
    par = {c: {i: {"erreurs": e, "mots_ref": 100} for i in ordre}
           for c, e in (("ov-turbo-f1", 30), ("ct2-frd16-f5", 10))}
    application = [c for c in par if not cp.PAR_CLE[c].candidat]
    decision = cp.verdict({c: {"etat": "ok", "facteur": 0.1, "wer": par[c]["e1"]["erreurs"]} for c in application},
                          ordre, {c: par[c] for c in application})
    verifier(decision["retenu"] == "ov-turbo-f1" and "ct2-frd16-f5" not in decision["lignes"],
             "un candidat plus juste n'entre pas dans le verdict (rien ne peut l'appliquer)")

    # Poids absents : état « modele_absent », sans appel réseau.
    modeles_reels = cp.chemins.DOSSIER_MODELES
    cp.chemins.DOSSIER_MODELES = base / "candidats-vide"
    cp.chemins.DOSSIER_MODELES.mkdir()
    try:
        verifier(cp.chemin_poids(cp.PAR_CLE["ct2-frv3-f5"]) == "" and cp.chemin_poids(cp.PAR_CLE["ov-frd16-f1"]) == "",
                 "poids absents ou conversion pas faite : chemin vide")
    finally:
        cp.chemins.DOSSIER_MODELES = modeles_reels

    # Moteur de mesure sans interprète désigné : non lancé, dit pourquoi.
    lances: list[str] = []
    lancer_reel = cp.lancer_reglage
    cp.lancer_reglage = lambda parametres, *a, **k: lances.append(parametres) or {"cle": parametres["cle"], "etat": "ok"}
    ancien = os.environ.pop(cp.VARIABLE_PYTHON_CANDIDATS, None)
    try:
        resultats = cp._jouer([cp.PAR_CLE["onnx-parakeet3"]], [{"id": "e1", "wav": "e1.wav", "duree_s": 60.0}],
                              base / "candidats-jouer", "CPU", {"langue": "fr"}, lambda m: None, None)
        verifier(resultats["onnx-parakeet3"]["etat"] == "moteur_absent" and not lances,
                 "moteur de mesure sans interprète : non lancé, état « moteur_absent »")
        os.environ[cp.VARIABLE_PYTHON_CANDIDATS] = sys.executable
        cp._jouer([cp.PAR_CLE["onnx-parakeet3"]], [{"id": "e1", "wav": "e1.wav", "duree_s": 60.0}],
                  base / "candidats-jouer-2", "CPU", {"langue": "fr"}, lambda m: None, None)
        verifier(lances and lances[0].get("interprete") == sys.executable
                 and cp.commande_essai(lances[0])[0][0] == sys.executable,
                 "avec l'interprète désigné, le réglage tourne dans cet interprète")
    finally:
        cp.lancer_reglage = lancer_reel
        os.environ.pop(cp.VARIABLE_PYTHON_CANDIDATS, None)
        if ancien is not None:
            os.environ[cp.VARIABLE_PYTHON_CANDIDATS] = ancien


def essai_campagne_limites(base: Path) -> None:
    """Faisceau sur la puce graphique non pris en charge, réglage de comparaison des réunions."""
    titre("Campagne : limites du périphérique, réglage de comparaison")
    from app import campagne as cp, config as config_module, moteur_openvino, reglage_machine

    lances: list[str] = []
    lancer_reel = cp.lancer_reglage

    def lancer_simule(parametres, inactivite_max, rappel=None, interrompu=None):
        lances.append(parametres["cle"])
        return {"cle": parametres["cle"], "etat": "ok", "peripherique": parametres["peripherique"]}

    cp.lancer_reglage = lancer_simule
    try:
        dossier = base / "campagne-limites"
        dits: list[str] = []
        resultats = cp._jouer(list(cp.CANDIDATS), [{"id": "e1", "wav": "e1.wav", "duree_s": 60.0}], dossier,
                              "GPU", {"langue": "fr"}, dits.append, None)
    finally:
        cp.lancer_reglage = lancer_reel
    hors = {c for c, r in resultats.items() if r["etat"] == cp.NON_PRIS_EN_CHARGE}
    verifier(hors == {"ov-v3-f5", "ov-turbo-f5"} and not hors & set(lances)
             and "ov-turbo-f1" in lances and "ct2-v3-f5" in lances,
             "faisceau 5 d'OpenVINO sur la puce graphique : non lancé, marqué non pris en charge")
    verifier(not any((dossier / "reglages" / f"{c}.json").exists() for c in hors),
             "rien n'est enregistré pour eux : une campagne sur processeur les mesurera")
    import copy

    mat = copy.deepcopy(materiel.detecter())
    rapport = cp.rediger_rapport_reunion(
        mat, 600.0, {"ov-v3-f5": resultats["ov-v3-f5"]}, {}, "", "premier",
        {"termes": 0, "exemples": 0}, {}, {}, "GPU", 10.0)
    verifier("non pris en charge" in rapport and "échec" not in rapport,
             "le rapport les dit non pris en charge, pas en échec")
    cpu = [r.cle for r in cp.CANDIDATS if cp.pris_en_charge(r, "CPU")]
    verifier(len(cpu) == len(cp.CANDIDATS), "sur le processeur, tous les réglages sont mesurés")

    # Réglage de comparaison d'une réunion.
    verifier(cp.choisir_ancre("ov-turbo-f1", ["ov-v3-f1", "ct2-v3-f5", "ov-turbo-f1"]) == ("ov-turbo-f1", "verdict"),
             "réunion : le réglage retenu par la campagne publique sert de comparaison")
    verifier(cp.choisir_ancre("ov-turbo-f1", ["ov-v3-f1", "ct2-v3-f5"]) == ("ct2-v3-f5", "verdict_echec"),
             "réglage retenu en échec sur la réunion : Qualité maximale, et le rapport dit pourquoi")
    verifier(cp.choisir_ancre("", ["ov-v3-f1", "ct2-v3-f5"]) == ("ct2-v3-f5", "qualite")
             and cp.choisir_ancre("", ["ov-v3-f1"]) == ("ov-v3-f1", "premier"),
             "sans verdict public : Qualité maximale, à défaut le premier réglage réussi")
    texte = langues.t("camp.reunion.ancre.verdict_echec", retenu="ov-turbo-f1")
    verifier("ov-turbo-f1" in texte and "pas de verdict" not in texte,
             "« pas de verdict public » n'est plus écrit quand le verdict existe")
    import inspect
    source = inspect.getsource(cp._executer_reunion)
    verifier(source.index("dernier_verdict()") < source.index("_jouer("),
             "le verdict public est lu au lancement de la réunion, avant les transcriptions")
    verifier("os.replace" in inspect.getsource(cp._executer),
             "le verdict public est écrit d'un bloc (fichier provisoire renommé)")

    # Réglage du poste : jamais de faisceau sur OpenVINO GPU, même écrit à la main.
    racine_reelle, config_reelle = chemins.RACINE, chemins.FICHIER_CONFIG
    chemins.RACINE = base / "faisceau-gpu"
    chemins.RACINE.mkdir()
    chemins.FICHIER_CONFIG = chemins.RACINE / "config.json"
    temoin_reel = moteur_openvino.TEMOIN_CHARGEMENT
    moteur_openvino.TEMOIN_CHARGEMENT = chemins.RACINE / "temoin.txt"
    installe, vus = moteur_openvino.installe, moteur_openvino.peripheriques_disponibles
    moteur_openvino.installe = lambda: True
    moteur_openvino.peripheriques_disponibles = lambda forcer=False: ["CPU", "GPU"]
    try:
        config = config_module.charger()
        propre = reglage_machine.enregistrer(config, mat, {"moteur": "openvino", "peripherique": "GPU",
                                                           "faisceau": 5})
        verifier(propre["faisceau"] == 1 and reglage_machine.faisceau_impose(config, mat) == 1,
                 "réglage OpenVINO GPU en faisceau 5 : enregistré et appliqué en faisceau 1")
        config[reglage_machine.CLE]["faisceau"] = 5
        verifier(reglage_machine.faisceau_impose(config, mat) == 1,
                 "faisceau 5 écrit à la main pour OpenVINO GPU : ramené à 1")
        reglage_machine.enregistrer(config, mat, {"moteur": "openvino", "peripherique": "CPU", "faisceau": 5})
        verifier(reglage_machine.faisceau_impose(config, mat) == 5,
                 "OpenVINO sur processeur garde son faisceau")
    finally:
        moteur_openvino.installe, moteur_openvino.peripheriques_disponibles = installe, vus
        chemins.RACINE, chemins.FICHIER_CONFIG = racine_reelle, config_reelle
        moteur_openvino.TEMOIN_CHARGEMENT = temoin_reel


# ---------------------------------------------------------------------------
# 27. OpenVINO : faisceau sur la puce graphique, garde-fou des répétitions,
#     filet (rejeu puis repli) sur un moteur simulé
# ---------------------------------------------------------------------------

_ERREUR_GPU = ("Exception from src\\core\\src\\runtime\\tensor.cpp:125: Exception from "
               "src\\inference\\dev_api\\openvino\\runtime\\iremote_tensor.hpp:32: Not Implemented")


def essai_openvino_faisceau() -> None:
    """Faisceau ramené à 1 sur GPU, garde-fou à température, reprise en échec sans perte."""
    titre("OpenVINO : faisceau et garde-fou des répétitions")
    from types import SimpleNamespace

    import numpy as np

    from app import moteur_openvino as mo

    verifier(not mo.faisceau_pris_en_charge("GPU", 5) and not mo.faisceau_pris_en_charge("NPU", 2)
             and mo.faisceau_pris_en_charge("GPU", 1) and mo.faisceau_pris_en_charge("CPU", 5)
             and mo.faisceau_effectif("gpu", 5) == 1 and mo.faisceau_effectif("CPU", 5) == 5,
             "faisceau : jamais plus de 1 sur la puce graphique ni le NPU, libre sur le processeur")

    class FauxPipeline:
        def __init__(self, textes, lever_si_faisceau=False):
            self.textes = list(textes)
            self.lever_si_faisceau = lever_si_faisceau
            self.configs: list[dict] = []

        def get_generation_config(self):
            return SimpleNamespace()

        def generate(self, _morceau, config, streamer=None):
            self.configs.append(dict(vars(config)))
            if self.lever_si_faisceau and config.num_beams > 1:
                # Ce que rend OpenVINO GenAI 2026.4 sur la puce graphique.
                raise RuntimeError(_ERREUR_GPU)
            texte = self.textes.pop(0)
            return SimpleNamespace(texts=[texte], words=[], languages=["<|fr|>"], perf_metrics=None,
                                   chunks=[SimpleNamespace(start_ts=0.0, end_ts=2.0, text=texte)])

    decouper_reel = mo.decouper
    mo.decouper = lambda signal: [[{"start": 0, "end": 32000}]]
    boucle, propre = "bonjour " * 40, "Bonjour à tous, on commence."
    mat = materiel.detecter()

    def moteur_sur(peripherique: str, pipeline) -> "mo.MoteurOpenVINO":
        instance = mo.MoteurOpenVINO(mat, peripherique)
        instance._pipeline, instance._mots, instance._nom_modele = pipeline, False, "turbo"
        return instance

    signal = np.zeros(32000, dtype=np.float32)
    try:
        tube = FauxPipeline([propre])
        segments, details = moteur_sur("GPU", tube).transcrire(signal, 2.0, "fr", {"faisceau_openvino": 5})
        verifier(tube.configs[0]["num_beams"] == 1 and details["faisceau"] == 1 and segments,
                 "faisceau de 5 demandé sur la puce graphique : décodage glouton, sans erreur")

        tube = FauxPipeline([boucle, propre], lever_si_faisceau=True)
        segments, details = moteur_sur("GPU", tube).transcrire(signal, 2.0, "fr", {"faisceau_openvino": 1})
        verifier(all(c["num_beams"] == 1 for c in tube.configs) and tube.configs[1].get("do_sample")
                 and tube.configs[1].get("temperature") == 0.2
                 and details["fenetres_repetitives"] == 1 and details["reprises"] == 1
                 and details["echecs_garde"] == 0 and segments[0].texte == propre,
                 "fenêtre qui boucle sur la puce graphique : refaite à température, jamais en faisceau")

        tube = FauxPipeline([boucle, propre])
        moteur_sur("CPU", tube).transcrire(signal, 2.0, "fr", {"faisceau_openvino": 1})
        verifier(tube.configs[1]["num_beams"] == 5 and not tube.configs[1].get("do_sample"),
                 "sur le processeur, le garde-fou garde son faisceau de 5")

        tube = FauxPipeline([boucle], lever_si_faisceau=True)
        segments, details = moteur_sur("GPU", tube).transcrire(
            signal, 2.0, "fr", {"faisceau_openvino": 1, "garde_repetition": "faisceau"})
        # Depuis la 3.0, la boucle restée est coupée en dernier recours (la
        # suite répétée gardée une fois) au lieu d'être gardée telle quelle.
        verifier(details["echecs_garde"] == 1 and "Not Implemented" in details["erreur_garde"]
                 and segments and segments[0].texte == "bonjour" and details["boucles_coupees"] == 1,
                 "ancien garde-fou forcé sur la puce graphique : l'erreur de la 2.4.0 est relevée, "
                 "la fenêtre est gardée, boucle coupée, au lieu de faire tomber la transcription")
    finally:
        mo.decouper = decouper_reel


def essai_filet_openvino() -> None:
    """Rejeu sur la puce graphique après un raté, repli sur CTranslate2 s'il se répète."""
    titre("OpenVINO : filet de la transcription (moteur simulé)")
    import numpy as np

    from app import moteur, moteur_openvino as mo
    from app.moteur import Segment

    class FauxMoteur:
        def __init__(self, nom: str, echecs_fenetres=(), echecs_ouverture: int = 0):
            self.nom, self.peripherique_ov = nom, "GPU"
            self.peripherique, self.type_calcul, self.tokeniseur = f"{nom}-x", "int8", None
            self.echecs_fenetres = list(echecs_fenetres)
            self.echecs_ouverture = echecs_ouverture
            self.ouvertures = self.liberations = 0
            self.departs: list[float] = []

        def charger(self, modele, signaler=None):
            self.ouvertures += 1
            if self.echecs_ouverture > 0:
                self.echecs_ouverture -= 1
                raise RuntimeError("compilation du modèle impossible")

        def liberer(self):
            self.liberations += 1

        def transcrire(self, signal, duree_totale, langue, reglages, amorce="", progression=None,
                       interrompu=None, decalage=0.0, sur_segment=None):
            self.departs.append(round(decalage, 3))
            sortis, duree, t = [], signal.size / 16000, 0.0
            while t < duree - 1e-6:
                debut = round(decalage + t, 3)
                if self.echecs_fenetres and abs(self.echecs_fenetres[0] - debut) < 1e-6:
                    self.echecs_fenetres.pop(0)
                    if self.nom == "stop":
                        raise moteur.Interruption()
                    raise RuntimeError(_ERREUR_GPU)
                segment = Segment(debut=debut, fin=min(debut + 10.0, decalage + duree),
                                  texte=f"{self.nom}", mots=[])
                sortis.append(segment)
                if sur_segment is not None:
                    sur_segment(segment)
                t += 10.0
            return sortis, {"moteur": self.nom}

    mat = materiel.detecter()
    pause = mo.MoteurAvecRepli.PAUSE_RECREATION_S
    mo.MoteurAvecRepli.PAUSE_RECREATION_S = 0.0
    signal = np.zeros(16000 * 60, dtype=np.float32)

    def monter(ov: FauxMoteur, ct2: FauxMoteur):
        filet = mo.MoteurAvecRepli(mat, "GPU")
        filet._ov, filet._ct2, filet._actif = ov, ct2, ov
        lignes: list[tuple[str, str]] = []
        filet.charger("turbo", lambda niveau, texte: lignes.append((niveau, texte)))
        return filet, lignes

    def jouer(filet):
        sauves: list = []
        segments, details = filet.transcrire(signal, 60.0, "fr", {}, sur_segment=sauves.append)
        return segments, details, sauves

    try:
        ov, ct2 = FauxMoteur("ov", echecs_fenetres=[20.0]), FauxMoteur("ct2")
        filet, lignes = monter(ov, ct2)
        segments, details, sauves = jouer(filet)
        verifier([s.debut for s in segments] == [0, 10, 20, 30, 40, 50] and segments == sauves
                 and all(s.texte == "ov" for s in segments),
                 "un raté : la fenêtre en cours est rejouée sur la puce graphique, rien n'est perdu ni doublé")
        verifier(ov.ouvertures == 2 and ov.liberations >= 1 and ov.departs == [0.0, 20.0]
                 and ct2.ouvertures == 0 and filet.sur_openvino and details["rejeux_openvino"] == 1,
                 "pipeline libéré puis recréé, CTranslate2 jamais sollicité")
        verifier([(i["phase"], i["issue"]) for i in filet.incidents] == [("transcription", "rejeu_reussi")]
                 and "Not Implemented" in filet.incidents[0]["erreur"],
                 "incident noté avec son erreur exacte, sans texte")
        verifier(any(n == "attention" and "reprise à" in t for n, t in lignes)
                 and not any("moteur habituel" in t for _n, t in lignes),
                 "une ligne sobre dans l'interface : modèle rouvert, reprise")

        ov, ct2 = FauxMoteur("ov", echecs_fenetres=[20.0, 20.0]), FauxMoteur("ct2")
        filet, lignes = monter(ov, ct2)
        segments, details, sauves = jouer(filet)
        verifier([s.debut for s in segments] == [0, 10, 20, 30, 40, 50] and segments == sauves
                 and [s.texte for s in segments] == ["ov", "ov", "ct2", "ct2", "ct2", "ct2"],
                 "deux ratés : repli sur CTranslate2 à la fin du dernier segment, rien de perdu")
        verifier(ov.ouvertures == 2 and ct2.ouvertures == 1 and ct2.departs == [20.0]
                 and not filet.sur_openvino and details.get("repli_ctranslate2"),
                 "un seul rejeu sur la puce graphique, puis CTranslate2")
        verifier([i["issue"] for i in filet.incidents] == ["rejeu", "repli"]
                 and any("moteur habituel" in t for _n, t in lignes),
                 "le repli est noté et dit dans l'interface")

        ov, ct2 = FauxMoteur("ov", echecs_ouverture=1), FauxMoteur("ct2")
        filet, lignes = monter(ov, ct2)
        verifier(filet.sur_openvino and ov.ouvertures == 2 and ct2.ouvertures == 0
                 and [(i["phase"], i["issue"]) for i in filet.incidents] == [("ouverture", "rejeu_reussi")],
                 "ouverture ratée une fois : pipeline recréé après une pause, la puce graphique reste")
        ov, ct2 = FauxMoteur("ov", echecs_ouverture=2), FauxMoteur("ct2")
        filet, lignes = monter(ov, ct2)
        verifier(not filet.sur_openvino and ct2.ouvertures == 1
                 and [i["issue"] for i in filet.incidents] == ["repli"],
                 "ouverture ratée deux fois : repli sur CTranslate2")

        ov, ct2 = FauxMoteur("stop", echecs_fenetres=[20.0]), FauxMoteur("ct2")
        filet, _lignes = monter(ov, ct2)
        try:
            jouer(filet)
            arretee = False
        except moteur.Interruption:
            arretee = True
        verifier(arretee and ov.ouvertures == 1 and not filet.incidents,
                 "une annulation n'est pas un raté : ni rejeu, ni repli")
    finally:
        mo.MoteurAvecRepli.PAUSE_RECREATION_S = pause



def essai_endurance(base: Path) -> None:
    """Épreuve d'endurance : plan, taux, diagnostic du 12/11, chute d'un processus, rapport sans texte."""
    titre("Épreuve d'endurance")
    import copy

    import numpy as np

    from app import campagne as cp, corpus, endurance as en, moteur

    # Plan : deux extraits de réunions différentes, environ 2 min, pression un passage sur deux.
    extraits = [{"id": f"r{k // 2}-{k % 2}", "wav": f"r{k}.wav", "reunion": f"r{k // 2}", "duree_s": 55.0 + k}
                for k in range(20)]
    plan = en.planifier(extraits, 30, pression=True)
    verifier(len(plan) == 30 and all(len(p["wavs"]) >= 2 for p in plan)
             and all(100.0 <= p["duree_s"] <= 180.0 for p in plan)
             and all(len({extraits[[e["wav"] for e in extraits].index(w)]["reunion"] for w in p["wavs"]})
                     == len(p["wavs"]) for p in plan),
             "30 passages d'environ 2 min, chacun fait de réunions différentes")
    verifier([p["mode"] for p in plan[:4]] == ["normal", "pression", "normal", "pression"]
             and all(p["mode"] == "normal" for p in en.planifier(extraits, 6, pression=False)),
             "pression mémoire un passage sur deux, seulement si elle est demandée")

    # Taux : borne haute de Wilson, panne avant et après rejeu.
    verifier(11.0 <= en.borne_haute(0, 30) <= 11.6 and en.borne_haute(0, 0) == 0.0
             and en.borne_haute(1, 30) > 100 / 30,
             "zéro panne sur 30 : taux réel sous 11 % environ (intervalle de Wilson)",
             str(en.borne_haute(0, 30)))
    lignes = [{"id": "a", "etat": "ok", "facteur": 0.1, "ouverture_s": 5, "libre_avant_ouverture_go": 9.0,
               "libre_avant_passage_go": 8.0},
              {"id": "b", "etat": "rejeu_reussi", "facteur": 0.2, "ouverture_s": 6,
               "libre_avant_ouverture_go": 4.0, "libre_avant_passage_go": 3.5},
              {"id": "c", "etat": "repli", "facteur": 0.6},
              {"id": "d", "etat": "plantage"},
              {"id": "e", "etat": "pression_ratee"}]
    b = en.bilan(lignes)
    verifier(b["n"] == 4 and b["avant"] == 3 and b["apres"] == 2 and b["rejeu_reussi"] == 1
             and b["pression_ratee"] == 1 and b["libre_ouv_min"] == 4.0 and b["facteur_med"] == 0.2,
             "panne avant rejeu, après rejeu, et pression ratée mise à part")

    # Diagnostic du 12/11 : réunion en échec retrouvée, journal lu sans en recopier une ligne.
    campagnes_reelles = cp.DOSSIER_CAMPAGNES
    cp.DOSSIER_CAMPAGNES = base / "endurance-campagnes"
    try:
        for nom, erreur in (("reunion-aaa", "RuntimeError: Exception from src\\core\\src\\runtime\\tensor.cpp:125:"
                                            "\nException from runtime/iremote_tensor.hpp:32:\nNot Implemented"),
                            ("reunion-bbb", "")):
            dossier = cp.DOSSIER_CAMPAGNES / nom / "reglages"
            dossier.mkdir(parents=True)
            (dossier / "ov-turbo-f1.json").write_text(json.dumps(
                {"etat": "erreur" if erreur else "ok", "erreur": erreur}), encoding="utf-8")
            np.save(cp.DOSSIER_CAMPAGNES / nom / "extrait.npy", np.zeros(160, dtype=np.float32))
        diag = en.diagnostics("ov-turbo-f1")
        verifier([(p["id"], p["garde"]) for p in diag] == [("r1-ancien", "faisceau"), ("r1-nouveau", "auto")]
                 and "reunion-aaa" in diag[0]["npy"],
                 "la réunion du 12/11 en échec est rejouée avec l'ancien puis le nouveau garde-fou")
    finally:
        cp.DOSSIER_CAMPAGNES = campagnes_reelles
    journaux = base / "endurance-logs"
    journaux.mkdir()
    (journaux / "2026-11-12_101500.log").write_text(
        "10:15:00  INFO  Chargement OpenVINO OpenVINO/whisper-large-v3-turbo-int8-ov sur GPU (x)\n"
        "10:15:09  INFO  Transcription OpenVINO : GPU, langue=fr, faisceau=1, 23 fenêtre(s), amorce=0 caractères\n"
        "10:16:10  WARNING  Fenêtre répétitive (taux 2.71), refaite avec un faisceau de 5\n"
        "10:16:11  ERROR  Campagne : réglage en échec\nTraceback (most recent call last):\n"
        '  File "app\\campagne.py", line 223, in executer_reglage\n'
        '  File "app\\moteur_openvino.py", line 414, in transcrire\n'
        "RuntimeError: Exception from src\\core\\src\\runtime\\tensor.cpp:125:\n"
        "Exception from runtime/iremote_tensor.hpp:32:\nNot Implemented\n", encoding="utf-8")
    (journaux / "2026-11-13_090000.log").write_text(
        "Reprise d'une fenêtre répétitive impossible\n  File \"app\\moteur_openvino.py\", line 430\n"
        "iremote_tensor.hpp:32 Not Implemented\n", encoding="utf-8")
    traces = en.lire_journaux(journaux)
    verifier(len(traces) == 1 and traces[0]["lignes"] == [414] and traces[0]["lieu"] == "garde_faisceau"
             and traces[0]["repetitive"] and traces[0]["ouvert"] and traces[0]["fenetres"] == 23,
             "journal du processus tombé : ligne de l'erreur, fenêtre qui bouclait juste avant ; "
             "les journaux de l'épreuve elle-même sont ignorés")

    # Un passage, avec un moteur simulé : classement, mémoire, pression ratée.
    class FauxFilet:
        def __init__(self, incidents, sur_openvino=True, lever=None):
            self.incidents, self.sur_openvino, self.lever = incidents, sur_openvino, lever
            self.liberations = 0

        def charger(self, modele, signaler=None):
            pass

        def transcrire(self, signal, duree, langue, reglages, amorce=""):
            if self.lever:
                raise self.lever
            return [object()], {"fenetres_repetitives": 1, "reprises": 2, "echecs_garde": 0}

        def liberer(self):
            self.liberations += 1

    fabriquer_reel, signal_reel, pression_reelle = en.fabriquer, en._signal, en._pression
    mat = copy.deepcopy(materiel.detecter())
    reglage = cp.PAR_CLE["ov-turbo-f1"]
    try:
        en._signal = lambda passage: np.zeros(16000 * 10, dtype=np.float32)
        cas = {
            "ok": FauxFilet([]),
            "rejeu_reussi": FauxFilet([{"phase": "transcription", "issue": "rejeu_reussi", "erreur": "E"}]),
            "repli": FauxFilet([{"phase": "transcription", "issue": "repli", "erreur": "E"}], sur_openvino=False),
            "erreur": FauxFilet([], lever=RuntimeError("panne")),
        }
        rendus = {}
        for attendu, faux in cas.items():
            en.fabriquer = lambda r, m, p, faux=faux: faux
            rendus[attendu] = en.jouer_passage({"id": "p01", "mode": "normal"}, reglage, mat, {}, "GPU", 4.0)
        verifier(all(rendus[e]["etat"] == e for e in cas) and all(f.liberations == 1 for f in cas.values()),
                 "passage classé réussi, réussi après rejeu, repli ou échec ; moteur toujours libéré")
        ok = rendus["ok"]
        verifier(ok["libre_avant_ouverture_go"] > 0 and ok["libre_avant_passage_go"] > 0
                 and ok["fenetres_repetitives"] == 1 and ok["reprises"] == 2 and "facteur" in ok,
                 "mémoire libre relevée avant l'ouverture et avant le passage")

        def pression_impossible(*_a):
            raise MemoryError("plus de mémoire")
        en._pression = pression_impossible
        en.fabriquer = lambda r, m, p: FauxFilet([])
        ratee = en.jouer_passage({"id": "p02", "mode": "pression"}, reglage, mat, {}, "GPU", 4.0)
        verifier(ratee["etat"] == "pression_ratee", "pression impossible : pas comptée comme une panne du moteur")
    finally:
        en.fabriquer, en._signal, en._pression = fabriquer_reel, signal_reel, pression_reelle

    # Orchestration : un processus qui tombe est noté, la file repart ; une relance reprend.
    reels = (en._lancer, en.DOSSIER, corpus.preparer, moteur.etat_modele, cp._peripherique_ov,
             cp.dernier_verdict, en.lire_journaux, en.diagnostics)
    en.DOSSIER = base / "endurance"
    corpus.preparer = lambda *a, **k: [corpus.Extrait(ident=e["id"], reunion=e["reunion"], duree=e["duree_s"],
                                                      wav=Path(e["wav"]), reference={}) for e in extraits]
    moteur.etat_modele = lambda depot: {"etat": "complet"}
    cp._peripherique_ov = lambda force="": "GPU"
    cp.dernier_verdict = lambda: {"cle": "ov-turbo-f1"}
    en.lire_journaux = lambda dossier=None: []
    en.diagnostics = lambda cle: []
    lancements: list[list[str]] = []

    def lancer_simule(fichier, recevoir, interrompu):
        restants = json.loads(Path(fichier).read_text(encoding="utf-8"))["passages"]
        lancements.append([p["id"] for p in restants])
        for p in restants:
            if p["id"] == "p03" and len(lancements) == 1:
                return "fin:3221225477", "p03"
            recevoir({"id": p["id"], "mode": p["mode"], "etat": "ok", "facteur": 0.12, "ouverture_s": 5.0,
                      "libre_avant_ouverture_go": 6.0, "libre_avant_passage_go": 5.5, "duree_s": 130.0,
                      "incidents": []})
        return "fin:0", ""

    en._lancer = lancer_simule
    try:
        resultat = en.executer(passages=6, pression=True)
        verifier(lancements == [["p01", "p02", "p03", "p04", "p05", "p06"], ["p04", "p05", "p06"]]
                 and resultat["complet"] and resultat["bilan"]["plantage"] == 1
                 and resultat["bilan"]["avant"] == 1 and resultat["bilan"]["n"] == 6,
                 "processus tombé : passage noté « processus tombé », la file repart au suivant")
        lancements.clear()
        resultat = en.executer(passages=6, pression=True)
        verifier(lancements == [] and resultat["complet"],
                 "relance : les passages déjà enregistrés ne sont pas refaits")
        rapport = resultat["rapport"]
        verifier("3221225477" in rapport and str(Path.home()) not in rapport and str(base) not in rapport,
                 "le rapport donne le code de sortie du processus tombé, sans chemin")
    finally:
        (en._lancer, en.DOSSIER, corpus.preparer, moteur.etat_modele, cp._peripherique_ov,
         cp.dernier_verdict, en.lire_journaux, en.diagnostics) = reels

    # Rapport : diagnostic concluant, aucun texte.
    diag_lignes = [
        {"id": "r1-ancien", "mode": "diagnostic", "etat": "ok", "fenetres_repetitives": 1, "echecs_garde": 1,
         "erreur_garde": "RuntimeError: ... iremote_tensor.hpp:32 Not Implemented", "facteur": 0.13,
         "incidents": []},
        {"id": "r1-nouveau", "mode": "diagnostic", "etat": "ok", "fenetres_repetitives": 1, "echecs_garde": 0,
         "facteur": 0.12, "incidents": []},
        {"id": "p01", "mode": "normal", "etat": "ok", "facteur": 0.12, "duree_s": 130.0, "incidents": []}]
    rapport = en.rediger_rapport(mat, "ov-turbo-f1", "GPU", diag_lignes,
                                 [{"date": "2026-11-12_1015", "lignes": [414], "lieu": "garde_faisceau",
                                   "repetitive": True, "ouvert": True, "faisceau": 1, "fenetres": 23}],
                                 False, 4.0, 60.0)
    verifier("cause confirmée" in rapport and "414" in rapport and "faisceau de 5" in rapport,
             "diagnostic : l'ancien garde-fou reproduit l'erreur, le nouveau la passe, cause confirmée")
    verifier(en.options_reconnues(["--endurance"]) and en.options_reconnues(["--endurance-essai", "x"]),
             "options de la ligne de commande")


def _poste_225u() -> materiel.Materiel:
    coeurs = [(1, [0, 1]), (1, [2, 3])] + [(0, [i]) for i in range(4, 12)] + [(0, [12]), (0, [13])]
    topo = materiel.analyser_topologie(_tampon_topologie(coeurs, [list(range(12))]))
    return materiel.Materiel(
        cpu_nom="Intel(R) Core(TM) Ultra 5 225U", coeurs_physiques=12, coeurs_logiques=14,
        topologie=topo, ram_go=32.0, basse_consommation=True, portable=True,
        gpus=[materiel.Gpu(nom="Intel(R) Graphics", vendeur="intel", pilote="32.0.101.8801")])


def essai_adaptation(base: Path) -> None:
    """Table de décision du choix automatique, sources mesurées, application."""
    titre("Choix automatique selon le poste : table de décision")
    from app import adaptation, moteur_openvino, reglage_machine

    P = adaptation.Profil
    travail = P(processeur="Core Ultra 5 225U", logiques=14, hybride=True, basse_consommation=True,
                ram_go=32, puce_intel=True, pilote_intel="32.0.101.8801", openvino_installe=True,
                openvino_puce=True, npu=True, portable=True)
    cas = [
        ("PC du travail, puce Intel vue par OpenVINO", travail, "puce_intel", "openvino", "GPU", "rapide"),
        ("même poste, OpenVINO pas installé", P(**{**travail.__dict__, "openvino_installe": False,
                                                   "openvino_puce": False}),
         "processeur_modeste", "ctranslate2", "", "rapide"),
        ("même poste, pilote graphique en panne", P(**{**travail.__dict__, "openvino_puce": False}),
         "puce_muette", "openvino", "CPU", "rapide"),
        ("bureau AMD et Radeon, sans OpenVINO", P(processeur="Ryzen 7 7800X3D", logiques=16, ram_go=47),
         "processeur_puissant", "ctranslate2", "", "qualite"),
        ("bureau AMD et Radeon, OpenVINO installé", P(logiques=16, ram_go=47, openvino_installe=True),
         "processeur_openvino", "openvino", "CPU", "rapide"),
        ("carte NVIDIA", P(logiques=16, ram_go=32, cuda=True, openvino_installe=True),
         "nvidia", "ctranslate2", "", "qualite"),
        ("8 Go de mémoire", P(logiques=16, ram_go=8, openvino_installe=False),
         "memoire_juste", "ctranslate2", "", "rapide"),
        ("processeur de 8 fils", P(logiques=8, ram_go=16), "processeur_modeste", "ctranslate2", "", "rapide"),
    ]
    for libelle, profil, cle, moteur_, peripherique, preset in cas:
        r = adaptation.regle(profil)
        verifier((r.cle, r.moteur, r.peripherique, r.preset) == (cle, moteur_, peripherique, preset),
                 f"table : {libelle} -> {cle}", str(r))
    verifier(adaptation.pilote_ancien("27.20.100.8935") and not adaptation.pilote_ancien("32.0.101.8801")
             and not adaptation.pilote_ancien("illisible"), "pilote Intel : minimum documenté d'OpenVINO")

    mat = _poste_225u()
    present = lambda depot: "complet"  # noqa: E731
    absent = lambda depot: "absent"  # noqa: E731
    p = adaptation.proposer(mat, travail, None, None, present)
    verifier(p["source"] == "table" and p["moteur"] == "openvino" and p["peripherique"] == "GPU"
             and not p["telechargement"] and p["rythme"] == "equilibre" and p["rythme_auto"],
             "proposition : table, puce Intel, rythme équilibré qui s'adapte", str(p))
    # La durée est celle annoncée sur ce poste, et aucune autre durée fixe ne
    # vient la contredire (l'ancienne raison disait « 7 minutes » à côté).
    verifier(p["une_heure"] in p["phrase"] and "Rapide" in p["phrase"] and "7 minutes" not in p["phrase"],
             "phrase claire avec la durée pour une heure", p["phrase"])
    p = adaptation.proposer(mat, travail, None, None, absent)
    verifier(p["telechargement"] and "téléchargés au premier lancement" in p["phrase"],
             "modèle absent : la taille est dite, rien n'est téléchargé", p["phrase"])
    verdict = {"moteur": "openvino", "peripherique": "GPU", "modele": "large-v3", "faisceau": 1,
               "preset": "qualite"}
    p = adaptation.proposer(mat, travail, verdict, None, present)
    verifier(p["source"] == "campagne" and p["preset"] == "qualite" and p["faisceau"] == 1,
             "le verdict d'une campagne passe devant la table")
    muette = P(**{**travail.__dict__, "openvino_puce": False})
    p = adaptation.proposer(mat, muette, verdict, None, present)
    verifier(p["source"] == "table" and p["peripherique"] == "CPU"
             and any("ne tient plus" in n for n in p["notes"]),
             "puce disparue : la campagne est écartée, et la proposition le dit", str(p["notes"]))
    p = adaptation.proposer(mat, P(**{**travail.__dict__, "openvino_installe": False, "openvino_puce": False}),
                            None, {"moteur": "openvino", "peripherique": "GPU"}, present)
    verifier(p["action"] == "installer_openvino" and any("90 Mo" in n for n in p["notes"])
             and p["moteur"] == "ctranslate2",
             "puce Intel sans moteur : jamais d'installation d'office, l'action est proposée à part")
    p = adaptation.proposer(mat, P(**{**travail.__dict__, "secteur": False}), None, None, present)
    verifier(any("batterie" in n for n in p["notes"]), "sur batterie : comportement dit")

    racine_reelle, temoin_reel = chemins.RACINE, moteur_openvino.TEMOIN_CHARGEMENT
    installe, vus = moteur_openvino.installe, moteur_openvino.peripheriques_disponibles
    chemins.RACINE = base / "adaptation"
    chemins.RACINE.mkdir(parents=True, exist_ok=True)
    moteur_openvino.TEMOIN_CHARGEMENT = chemins.RACINE / "temoin.txt"
    moteur_openvino.installe = lambda: True
    moteur_openvino.peripheriques_disponibles = lambda forcer=False: ["CPU", "GPU"]
    try:
        config = {"preset": "qualite", "rythme": "vitesse", "rythme_auto": False,
                  "reglage_machine": {}}
        p = adaptation.proposer(mat, travail, None, None, present)
        verifier(not adaptation.deja_en_place(p, config, mat), "avant application : rien n'a changé")
        adaptation.appliquer(config, mat, p)
        verifier(config["preset"] == "rapide" and config["rythme"] == "equilibre" and config["rythme_auto"]
                 and mat.cle_calcul == "openvino-gpu"
                 and reglage_machine.lire(config, mat).get("source") == "table",
                 "appliquer : preset, rythme et moteur écrits, signés pour ce poste")
        verifier(adaptation.deja_en_place(p, config, mat), "ensuite, la proposition est reconnue en place")
    finally:
        chemins.RACINE, moteur_openvino.TEMOIN_CHARGEMENT = racine_reelle, temoin_reel
        moteur_openvino.installe, moteur_openvino.peripheriques_disponibles = installe, vus
    verifier(adaptation.options_reconnues(["--reconnaitre"]), "option --reconnaitre")


class _FauxLeviers:
    def __init__(self):
        self.appels: list[tuple] = []

    def qos_seule(self, nom):
        self.appels.append(("qos", nom))

    def rendre_qos(self):
        self.appels.append(("rendre_qos",))

    def appliquer(self, b, avec_affinite):
        self.appels.append(("appliquer", b.rythme, b.priorite, b.qos, avec_affinite))

    def rendre(self):
        self.appels.append(("rendre",))


def essai_rythmes() -> None:
    """Bornes de chaque rythme, mémoire, bascule automatique sur activité simulée."""
    titre("Rythme « je travaille en même temps » : bornes et bascule")
    from app import banc_rythmes, rythme

    poste = _poste_225u()
    v, e, d = (rythme.bornes(n, poste) for n in rythme.RYTHMES)
    verifier((v.fils, v.lot_max, v.priorite, v.qos, v.affinite) == (10, None, "normale", "haute", ()),
             "vitesse maximale : comportement d'avant (10 fils, lots du preset, HighQoS)", str(v))
    verifier((e.fils, e.lot_max, e.priorite, e.qos) == (8, 4, "inferieure", "systeme")
             and e.ov_processeur == {"INFERENCE_NUM_THREADS": 8}
             and e.ov_puce.get("GPU_QUEUE_PRIORITY") == "LOW",
             "équilibré : 8 fils, lots de 4, priorité inférieure, file de la puce en priorité basse", str(e))
    verifier(d.fils == 5 and d.lot_max == 0 and d.priorite == "basse" and d.qos == "eco"
             and d.priorite_es == "basse" and list(d.affinite) == list(range(4, 12))
             and d.ov_processeur.get("SCHEDULING_CORE_TYPE") == "ECORE_ONLY"
             and d.ov_puce.get("GPU_QUEUE_THROTTLE") == "LOW",
             "discret (225U) : 5 fils sur les 8 cœurs efficaces, un à un, EcoQoS, puce bridée", str(d))
    bureau = materiel.Materiel(coeurs_physiques=8, coeurs_logiques=16)
    verifier([rythme.bornes(n, bureau).fils for n in rythme.RYTHMES] == [8, 6, 4]
             and rythme.bornes("discret", bureau).affinite == (),
             "bureau 8 cœurs : 8, 6 et 4 fils, sans affinité (processeur homogène)")
    mono = materiel.Materiel(coeurs_physiques=1, coeurs_logiques=1)
    verifier(all(rythme.bornes(n, mono).fils == 1 for n in rythme.RYTHMES), "jamais moins d'un fil")
    verifier(rythme.normaliser("inconnu") == "vitesse" and rythme.bornes("", bureau).rythme == "vitesse",
             "valeur inconnue : vitesse maximale, le défaut")
    auto = rythme.bornes_chargement("discret", True, poste)
    verifier(auto.fils == 10 and auto.lot_max is None and auto.ov_puce.get("GPU_QUEUE_PRIORITY") == "LOW"
             and "GPU_QUEUE_THROTTLE" not in auto.ov_puce,
             "adaptation automatique : fils et lots de la vitesse maximale au chargement")
    verifier(rythme.pause("discret", True, False) == 1.0 and rythme.pause("discret", False, False) == 0.0
             and rythme.pause("discret", False, True) == 0.5 and rythme.pause("vitesse", True, True) == 0.0,
             "pauses : sur la puce en discret, sur le processeur seulement en automatique")

    verifier(rythme.garde_memoire("vitesse", "ctranslate2", "large-v3", 8, 2.0, presets.MODELE_TURBO)
             == ("large-v3", 8, ""), "mémoire : la vitesse maximale ne change rien")
    verifier(rythme.garde_memoire("equilibre", "ctranslate2", "large-v3", 4, 6.0, presets.MODELE_TURBO)
             == ("large-v3", 0, "lots"), "6 Go libres : un passage à la fois")
    verifier(rythme.garde_memoire("discret", "ctranslate2", "large-v3", 0, 4.0, presets.MODELE_TURBO)
             == (presets.MODELE_TURBO, 0, "modele"), "4 Go libres : modèle plus léger, dit")
    verifier(rythme.garde_memoire("discret", "ctranslate2", "large-v3", 0, 4.0, "")[0] == "large-v3",
             "reprise ou mode avancé : le modèle n'est jamais changé")
    verifier(rythme.garde_memoire("discret", "openvino", "turbo", 0, 0.0, "")[2] == "",
             "mémoire illisible : rien ne change")

    R = rythme.Releve
    verifier(rythme.poste_occupe(R(inactivite_s=30))[1] == "clavier_souris"
             and rythme.poste_occupe(R(inactivite_s=600, charge_autres=35))[1] == "charge"
             and rythme.poste_occupe(R(inactivite_s=600, charge_autres=20), True)[0]
             and not rythme.poste_occupe(R(inactivite_s=600, charge_autres=20), False)[0]
             and rythme.poste_occupe(R(micro=True))[1] == "micro"
             and rythme.poste_occupe(R(plein_ecran=True))[1] == "plein_ecran"
             and rythme.poste_occupe(R(batterie=True))[1] == "batterie"
             and rythme.poste_occupe(R(inactivite_s=600, charge_autres=-1), True) == (True, "charge_inconnue")
             and not rythme.poste_occupe(R(inactivite_s=600, charge_autres=-1), False)[0],
             "poste occupé : clavier, charge des autres (avec hystérésis), micro, plein écran, batterie")

    horloge = [0.0]
    leviers = _FauxLeviers()
    releve = [R(inactivite_s=5)]
    reg = rythme.Regulateur(poste, "discret", True, capteur=lambda: releve[0], leviers=leviers,
                            horloge=lambda: horloge[0])
    reg.demarrer(suivre=False)
    verifier(reg.effectif == "discret" and leviers.appels[0][1] == "discret" and not leviers.appels[0][4],
             "départ, poste utilisé : discret, sans toucher à l'affinité (fils déjà fixés)")
    horloge[0] = 60.0
    releve[0] = R(inactivite_s=300, charge_autres=5)
    verifier(reg.evaluer() == "vitesse" and leviers.appels[-1][1:3] == ("vitesse", "normale"),
             "poste au repos depuis cinq minutes : pleine vitesse")
    horloge[0] = 100.0
    verifier(reg.evaluer(R(inactivite_s=300, charge_autres=40)) == "discret"
             and reg.raison == "charge", "un autre programme prend 40 % : discret")
    verifier(reg.evaluer(R(inactivite_s=300, charge_autres=20)) == "discret",
             "hystérésis : à 20 % on reste discret")
    horloge[0] = 130.0
    verifier(reg.evaluer(R(inactivite_s=300, charge_autres=8)) == "vitesse", "à 8 % : pleine vitesse")
    horloge[0] = 150.0
    verifier(reg.evaluer(R(inactivite_s=300, micro=True)) == "discret", "appel en cours : discret")
    horloge[0] = 160.0
    bilan = reg.arreter()
    verifier(bilan["bascules"] == 4 and abs(bilan["durees"]["vitesse"] - 60.0) < 1e-6
             and abs(bilan["durees"]["discret"] - 100.0) < 1e-6 and leviers.appels[-1] == ("rendre",),
             "bilan : 4 bascules, 60 s à pleine vitesse, 100 s discret, système rendu", str(bilan))

    leviers = _FauxLeviers()
    reg = rythme.Regulateur(poste, "vitesse", False, leviers=leviers)
    reg.demarrer(suivre=False)
    reg.arreter()
    verifier(leviers.appels == [("qos", "haute"), ("rendre_qos",)],
             "vitesse maximale sans adaptation : seulement le HighQoS d'avant", str(leviers.appels))
    leviers = _FauxLeviers()
    reg = rythme.Regulateur(poste, "discret", False, leviers=leviers)
    reg.sur_puce = lambda: True
    reg.demarrer(suivre=False)
    verifier(leviers.appels[0] == ("appliquer", "discret", "basse", "eco", True) and reg.rapport_pause() == 1.0,
             "discret sans adaptation : bornes complètes posées, affinité comprise, pause sur la puce")
    import time as _time
    debut = _time.monotonic()
    fait = reg.frein(0.05)
    verifier(abs(fait - 0.05) < 1e-9 and _time.monotonic() - debut >= 0.045,
             "frein : pause égale au calcul sur la puce en discret")
    verifier(reg.frein(10.0, interrompu=lambda: True) <= rythme.PAUSE_MAX_S
             and _time.monotonic() - debut < 1.0, "frein interrompu aussitôt par une annulation")
    reg.arreter()

    verifier(rythme.restant_s(600, 30, 0.05) == 570 and abs(rythme.restant_s(600, 100, 0.5) - 100) < 1e-6
             and abs(rythme.restant_s(600, 100, 0.2) - (0.5 * 500 + 0.5 * 400)) < 1e-6,
             "temps restant : estimation, puis cadence observée")
    verifier(rythme.coefficient("discret", "cpu", {"processeur": {"discret": 1.8}}) == 1.8
             and rythme.coefficient("discret", "openvino-gpu", {"processeur": {"discret": 1.8}}) == 2.4
             and rythme.coefficient("equilibre", "cpu", {"processeur": {"equilibre": 0.7}}) == 1.3
             and rythme.coefficient("vitesse", "cpu", {}) == 1.0,
             "coefficients de durée : mesure du banc, sinon repli prudent")

    verifier(banc_rythmes.libre_pct(8.0, 1.0, 16) == 50.0 and banc_rythmes.libre_pct(0, 0, 16) == 0.0,
             "banc des rythmes : processeur laissé libre")
    g = banc_rythmes.gene({"travail_median_ms": 3.0, "travail_p95_ms": 9.0, "reveil_p95_ms": 2.0},
                          {"travail_median_ms": 1.5, "travail_p95_ms": 3.0})
    verifier(g == {"median": 2.0, "p95": 3.0, "reveil_p95_ms": 2.0}, "gêne rapportée au repos", str(g))
    coef = banc_rythmes.coefficients([
        {"etat": "ok", "variante": "vitesse", "rythme": "vitesse", "facteur": 0.1},
        {"etat": "ok", "variante": "discret", "rythme": "discret", "facteur": 0.25},
        {"etat": "ok", "variante": "vitesse-passive", "rythme": "vitesse", "facteur": 0.2}])
    verifier(coef == {"discret": 2.5}, "coefficients : rythmes seuls, variantes écartées", str(coef))
    verifier(materiel.analyser_topologie(_tampon_topologie(
        [(1, [0, 1]), (1, [2, 3])] + [(0, [i]) for i in range(4, 12)] + [(0, [12]), (0, [13])],
        [list(range(12))])).logiques_performants == [0, 1, 2, 3],
        "topologie : processeurs logiques des cœurs performants à part")


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
        essai_bornes_fenetres()
        essai_reprise_locuteurs(base)
        essai_sortie_pyannote()
        essai_fils_calcul()
        essai_cartes_graphiques()
        essai_topologie()
        essai_estimations_machine(base)
        essai_energie()
        essai_openvino_decoupage()
        essai_modele_openvino_incomplet(base)
        essai_reglage_machine(base)
        essai_banc()
        essai_extension_openvino()
        essai_comparaison(base)
        essai_campagne(base)
        essai_campagne_limites(base)
        essai_campagne_candidats(base)
        essai_openvino_faisceau()
        essai_filet_openvino()
        essai_endurance(base)
        essai_adaptation(base)
        essai_rythmes()

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
