"""
Vérification de bout en bout de la chaîne de relecture.

La vue de lecture ne peut pas être cliquée par un script : ce contrôle vérifie
donc les DONNÉES qu'elle consomme, en passant par le vrai chemin de code, du
décodage au fichier compagnon.

Il transcrit un petit fichier audio avec un modèle léger, puis contrôle :

  1. le fichier texte et son compagnon JSON sont écrits côte à côte ;
  2. le compagnon est valide, versionné, et porte bien la confiance de chaque mot ;
  3. `app/lecture.py` reconstruit des paragraphes identiques au fichier texte ;
  4. le repli sans compagnon fonctionne, c'est le cas des transcriptions anciennes ;
  5. « Copier pour l'IA » produit le gabarit, les métadonnées et le texte ;
  6. une correction relue est écrite dans le texte, le compagnon et les règles ;
  7. la sauvegarde progressive est bien nettoyée après un succès ;
  8. une transcription interrompue se reprend, sans reperdre le temps écoulé.

Le glossaire, les corrections et le gabarit de l'utilisateur ne sont jamais
touchés : le contrôle travaille dans un dossier temporaire.

Usage, depuis la racine du projet :

    .venv\\Scripts\\python outils\\verifier_chaine_lecture.py --audio un.wav
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import chemins, compagnon, config as config_module  # noqa: E402
from app import gabarit, langues, lecture, materiel, reprise, traitement, vocabulaire  # noqa: E402

# Le contrôle compare des chaînes produites par l'application : la langue
# d'interface est fixée, sans quoi le résultat dépendrait de la langue de
# Windows sur le poste qui l'exécute. `config.charger()` repose la langue de la
# configuration à chaque appel, on l'enveloppe donc plutôt que de la subir. Le
# contenu anglais est vérifié à part, à l'étape 7.
_charger_reel = config_module.charger


def _charger_en_francais() -> dict:
    config = _charger_reel()
    config["langue_interface"] = "fr"
    langues.definir("fr")
    return config


config_module.charger = _charger_en_francais
langues.definir("fr")

_ANOMALIES: list[str] = []


def verifier(condition: bool, etiquette: str, detail: str = "") -> bool:
    if not condition:
        _ANOMALIES.append(etiquette)
    marque = "OK   " if condition else "ECHEC"
    print(f"  {marque}  {etiquette}" + (f" : {detail}" if detail else ""))
    return condition


def transcrire(audio: Path, dossier: Path, modele: str) -> list[dict]:
    mat = materiel.detecter()
    file = traitement.FileTraitement(mat)
    file.ajouter([str(audio)])
    config = config_module.charger()
    config.update({
        "dossier_sortie": str(dossier),
        "diarisation": False,
        "utiliser_glossaire": False,
        "appliquer_corrections": False,
        "mode_avance": True,
        "modele_avance": modele,
        "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
        "sauvegarde_progressive": True,
        "compagnon_confiance": True,
    })
    fini = threading.Event()
    produits: list[dict] = []
    rappels = traitement.Rappels(
        termine=lambda i, d: produits.extend(d.get("sorties") or []),
        file_terminee=lambda d: fini.set(),
    )
    depart = time.perf_counter()
    file.demarrer(config, rappels)
    fini.wait(timeout=3600)
    print(f"  Transcription faite en {time.perf_counter() - depart:.1f} s")
    return produits


def transcrire_puis_interrompre(audio: Path, dossier: Path, modele: str,
                                delai: float) -> None:
    """Lance une transcription et l'arrête en route, comme une fermeture brutale."""
    mat = materiel.detecter()
    file = traitement.FileTraitement(mat)
    file.ajouter([str(audio)])
    config = config_module.charger()
    config.update({
        "dossier_sortie": str(dossier), "diarisation": False,
        "utiliser_glossaire": False, "appliquer_corrections": False,
        "mode_avance": True, "modele_avance": modele,
        "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
        "sauvegarde_progressive": True, "compagnon_confiance": True,
    })
    fini = threading.Event()
    file.demarrer(config, traitement.Rappels(file_terminee=lambda d: fini.set()))
    threading.Timer(delai, file.arreter).start()
    fini.wait(timeout=3600)


def reprendre(audio: Path, dossier: Path, modele: str, cle: str) -> tuple[list[dict], float]:
    """Remet le fichier en file avec sa reprise, et le mène jusqu'au bout."""
    mat = materiel.detecter()
    file = traitement.FileTraitement(mat)
    file.ajouter_pour_reprise(str(audio), cle)
    config = config_module.charger()
    config.update({
        "dossier_sortie": str(dossier), "diarisation": False,
        "utiliser_glossaire": False, "appliquer_corrections": False,
        "mode_avance": True, "modele_avance": modele,
        "formats": {"txt": True, "srt": False, "vtt": False, "horodatage": False},
        "sauvegarde_progressive": True, "compagnon_confiance": True,
    })
    fini = threading.Event()
    produits: list[dict] = []
    file.demarrer(config, traitement.Rappels(
        termine=lambda i, d: produits.extend(d.get("sorties") or []),
        file_terminee=lambda d: fini.set(),
    ))
    depart = time.perf_counter()
    fini.wait(timeout=3600)
    return produits, time.perf_counter() - depart


def controler_reprise(audio: Path, bac: Path, modele: str) -> None:
    sortie = bac / "reprise"
    trouvee = None
    for delai in (7.0, 11.0, 15.0):
        transcrire_puis_interrompre(audio, sortie, modele, delai)
        candidates = [r for r in reprise.lister() if Path(r["chemin"]) == audio.resolve()
                      or Path(r["chemin"]) == audio]
        if candidates:
            trouvee = candidates[0]
            break
        print(f"         aucun segment sauvegardé en {delai:.0f} s, nouvel essai")

    if not verifier(trouvee is not None, "une reprise est proposée après l'interruption"):
        return
    print(f"         interrompue à {trouvee['position']:.1f} s d'audio, "
          f"{trouvee['nb_segments']} segments, {trouvee['ecoule']:.1f} s de calcul")
    verifier(trouvee["nb_segments"] > 0, "des segments ont été sauvegardés")
    verifier(trouvee["ecoule"] > 0, "le temps écoulé est mémorisé")

    produits, duree_reprise = reprendre(audio, sortie, modele, trouvee["cle"])
    verifier(bool(produits), "la reprise produit bien un fichier")
    if not produits:
        return
    txt = Path(produits[0]["chemin"])
    brut = json.loads(compagnon.chemin_pour(txt).read_text(encoding="utf-8"))
    verifier(len(brut["segments"]) > trouvee["nb_segments"],
             "le texte est complété, pas recommencé",
             f"{len(brut['segments'])} segments au total pour "
             f"{trouvee['nb_segments']} déjà transcrits")
    verifier(brut["segments"][0]["d"] < 1.0, "le début de l'enregistrement est conservé")
    verifier(brut["segments"][-1]["f"] > trouvee["position"], "la fin a bien été transcrite")
    temps = brut["transcription"]["temps_calcul"]
    verifier(temps > duree_reprise, "le temps déjà écoulé est conservé dans le compteur",
             f"{temps:.1f} s au total pour {duree_reprise:.1f} s de reprise seule")
    verifier(not [f for f in reprise.dossier().glob(trouvee["cle"] + "*")],
             "les fichiers de reprise sont effacés à la fin")


def principal() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--audio", required=True)
    analyseur.add_argument("--modele", default="tiny")
    arguments = analyseur.parse_args()

    audio = Path(arguments.audio)
    if not audio.is_file():
        print(f"Fichier introuvable : {audio}")
        return 1

    chemins.assurer_dossiers()

    with tempfile.TemporaryDirectory(prefix="scribouille-verif-") as temporaire:
        bac = Path(temporaire)
        # Les fichiers personnels sont mis de côté le temps du contrôle.
        chemins.FICHIER_CORRECTIONS = bac / "corrections.txt"
        chemins.FICHIER_GABARIT_IA = bac / "gabarit-ia.txt"

        sortie = bac / "sorties"
        print("\n[1] Transcription et écriture")
        produits = transcrire(audio, sortie, arguments.modele)
        verifier(bool(produits), "au moins un fichier produit")
        if not produits:
            return 1
        txt = Path(produits[0]["chemin"])
        json_compagnon = compagnon.chemin_pour(txt)
        verifier(txt.is_file(), "fichier texte écrit", txt.name)
        verifier(json_compagnon.is_file(), "compagnon écrit à côté", json_compagnon.name)
        verifier(
            not list(reprise.dossier().glob("*")) or all(
                not f.name.startswith(reprise.cle(audio, arguments.modele))
                for f in reprise.dossier().glob("*")
            ),
            "fichiers de reprise nettoyés après un succès",
        )

        print("\n[2] Contenu du compagnon")
        brut = json.loads(json_compagnon.read_text(encoding="utf-8"))
        verifier(brut.get("format") == compagnon.FORMAT, "champ format")
        verifier(brut.get("version") == compagnon.VERSION_FORMAT, "version du format",
                 str(brut.get("version")))
        verifier(bool(brut.get("segments")), "segments présents",
                 f"{len(brut.get('segments') or [])} segments")
        mots = [m for s in brut["segments"] for m in (s.get("m") or [])]
        verifier(len(mots) > 10, "mots avec confiance", f"{len(mots)} mots")
        verifier(all(0.0 <= m["p"] <= 1.0 for m in mots), "probabilités entre 0 et 1")
        verifier(all(m["d"] <= m["f"] + 0.001 for m in mots), "horodatages cohérents")
        taille_par_minute = json_compagnon.stat().st_size / max(1e-9, brut["source"]["duree"] / 60)
        print(f"         poids du compagnon : {json_compagnon.stat().st_size / 1024:.1f} Ko, "
              f"soit {taille_par_minute / 1024:.1f} Ko par minute d'audio")

        probabilites = sorted(m["p"] for m in mots)
        for seuil in (0.30, 0.35, 0.40, 0.50, 0.60, 0.70):
            part = sum(1 for p in probabilites if p < seuil) / len(probabilites) * 100
            print(f"         part des mots sous {seuil:.2f} : {part:5.1f} %")
        print(f"         médiane {statistics.median(probabilites):.3f}, "
              f"premier décile {probabilites[len(probabilites) // 10]:.3f}")

        print("\n[3] Données consommées par la vue de lecture")
        vue = lecture.charger(txt)
        verifier(vue.get("ok") is True, "transcription chargée")
        verifier(vue.get("compagnon") is True, "confiance disponible")
        verifier(bool(vue.get("paragraphes")), "paragraphes construits",
                 f"{len(vue['paragraphes'])} paragraphes")
        stats = vue["statistiques"]
        verifier(stats["mots"] == len(mots), "tous les mots sont présentés",
                 f"{stats['mots']} affichés pour {len(mots)} enregistrés")
        verifier(stats["signales"] <= stats["mots"], "mots signalés bornés",
                 f"{stats['signales']} signalés sous {vue['seuils']['faible']}")
        verifier(vue["seuils"]["faible"] == compagnon.SEUIL_FAIBLE, "seuil faible transmis")

        # Le texte reconstruit doit dire la même chose que le fichier écrit.
        corps_fichier = lecture.separer_entete(txt.read_text(encoding="utf-8"))[1]
        normaliser = lambda t: re.sub(r"[^\w]+", "", t, flags=re.UNICODE).lower()  # noqa: E731
        verifier(
            normaliser(lecture.texte_complet(vue["paragraphes"])) == normaliser(corps_fichier),
            "le texte affiché est celui du fichier",
        )
        verifier(vue["meta"]["source_presente"] is True, "fichier audio d'origine retrouvé")

        print("\n[4] Repli sans compagnon, comme une transcription ancienne")
        garde = json_compagnon.read_text(encoding="utf-8")
        json_compagnon.unlink()
        sans = lecture.charger(txt)
        verifier(sans.get("ok") is True, "chargement sans compagnon")
        verifier(sans.get("compagnon") is False, "surlignage désactivé")
        verifier(bool(sans.get("message")), "phrase d'explication affichée",
                 sans.get("message", "")[:60] + "...")
        verifier(bool(sans.get("paragraphes")), "texte tout de même découpé",
                 f"{len(sans['paragraphes'])} paragraphes")
        verifier(sans["statistiques"]["signales"] == 0, "aucun mot signalé sans confiance")
        json_compagnon.write_text(garde, encoding="utf-8")

        print("\n[5] Copier pour l'IA")
        copie = lecture.texte_pour_ia(txt)
        verifier(copie.get("ok") is True, "texte assemblé")
        contenu = copie.get("texte", "")
        verifier(chemins.FICHIER_GABARIT_IA.is_file(), "gabarit créé au premier usage")
        verifier("compte rendu" in contenu.lower(), "instructions présentes")
        verifier("{texte}" not in contenu and "{fichier}" not in contenu,
                 "toutes les variables sont remplacées")
        verifier(audio.name in contenu, "nom du fichier source rappelé")
        premier = vue["paragraphes"][0]["mots"][0]["t"]
        verifier(premier in contenu, "texte de la transcription inclus")
        verifier("#" not in contenu.splitlines()[0], "commentaires du gabarit retirés")

        print("\n[6] Correction apprise depuis la relecture")
        mot_cible = ""
        for paragraphe in vue["paragraphes"]:
            for mot in paragraphe["mots"]:
                propre = re.sub(r"[^\w'’-]", "", mot["t"])
                if len(propre) > 5:
                    mot_cible = propre
                    break
            if mot_cible:
                break
        verifier(bool(mot_cible), "un mot à corriger a été trouvé", mot_cible)
        remplacement = "MotCorrigéDeTest"
        retour = lecture.appliquer_correction(txt, mot_cible, remplacement, ajouter_regle=True)
        verifier(retour.get("ok") is True, "correction appliquée", retour.get("message", ""))
        verifier(retour.get("regle_ajoutee") is True, "règle mémorisée")
        texte_apres = txt.read_text(encoding="utf-8")
        entete_apres, corps_apres = lecture.separer_entete(texte_apres)
        verifier(remplacement in corps_apres, "corps du fichier corrigé")
        verifier(audio.name in entete_apres, "en-tête intact")
        apres = lecture.charger(txt)
        verifier(
            any(remplacement in m["t"] for p in apres["paragraphes"] for m in p["mots"]),
            "compagnon corrigé lui aussi",
        )
        regles_texte = chemins.FICHIER_CORRECTIONS.read_text(encoding="utf-8")
        verifier(vocabulaire.titre_section_apprises() in regles_texte, "section dédiée créée")
        verifier(f"{mot_cible} => {remplacement}" in regles_texte, "règle écrite proprement")
        doublon = vocabulaire.ajouter_correction_apprise(mot_cible, remplacement)
        verifier(doublon["ajoutee"] is False, "doublon refusé", doublon["message"])
        verifier(
            regles_texte.count(f"{mot_cible} => {remplacement}") == 1,
            "une seule occurrence de la règle",
        )
        conflit = vocabulaire.ajouter_correction_apprise(mot_cible, "AutreForme")
        verifier(conflit["ajoutee"] is False, "règle contradictoire refusée")
        refus = vocabulaire.verifier_regle("a => b", "x")
        verifier(bool(refus), "flèche interdite dans une règle")

        print("\n[7] Gabarit personnalisé, et langue du gabarit par défaut")
        gabarit.ecrire("# commentaire\nRésumé de {fichier} :\n\n{texte}")
        personnalise = lecture.texte_pour_ia(txt)["texte"]
        verifier(personnalise.startswith("Résumé de "), "gabarit modifié pris en compte")
        verifier("# commentaire" not in personnalise, "commentaire non copié")

        # Le gabarit par défaut suit la langue d'interface au moment de sa
        # création, et un fichier existant n'est jamais retraduit.
        chemins.FICHIER_GABARIT_IA.unlink(missing_ok=True)
        langues.definir("en")
        try:
            anglais = gabarit.lire()
            verifier("minutes of a meeting" in anglais.lower(),
                     "gabarit créé en anglais quand l'interface est en anglais")
            langues.definir("fr")
            verifier(gabarit.lire() == anglais,
                     "un gabarit déjà écrit n'est jamais retraduit")
        finally:
            langues.definir("fr")

        print("\n[8] Interruption puis reprise")
        controler_reprise(audio, bac, arguments.modele)

    print("")
    if _ANOMALIES:
        print(f"Bilan : {len(_ANOMALIES)} anomalie(s) : " + " ; ".join(_ANOMALIES))
        return 1
    print("Bilan : toute la chaîne de relecture est conforme.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
