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

from app import chemins, langues, lecture, sorties, vocabulaire  # noqa: E402
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


def texte_affiche(paragraphe: dict) -> str:
    """Ce que la vue affiche d'un paragraphe : chaque mot précédé de ce qui le précède."""
    return "".join(m.get("e", " " if i else "") + m["t"] for i, m in enumerate(paragraphe["mots"]))


def essai_vue_egale_fichier(base: Path) -> None:
    titre("La vue de relecture affiche et copie exactement le texte du fichier")
    dossier = base / "vue"
    dossier.mkdir()
    premier = segment(0.0, 5.0, jetons("C'est peut-être L'Amazon qui gagne, qu'est-ce que j'en sais ?"))
    # Mots que le moteur n'a pas détaillés (cas relevé avec OpenVINO) : le
    # texte du segment les porte, la liste des mots non.
    second = segment(5.5, 9.0, jetons("Et bien. Comment ça va aujourd'hui ?"))
    second.mots = [m for m in second.mots if m.texte not in ("Et", "Comment")]
    txt = ecrire(dossier, [premier, second])
    corps = lecture.separer_entete(txt.read_text(encoding="utf-8"))[1].strip()

    vue = lecture.charger(txt)
    affiche = "\n\n".join(texte_affiche(p) for p in vue["paragraphes"])
    verifier(all(texte_affiche(p) == p["texte"] for p in vue["paragraphes"]),
             "chaque paragraphe affiché est le texte de ses segments, caractère pour caractère",
             repr(affiche[:90]))
    verifier(affiche == corps, "le texte affiché est celui du fichier", f"{affiche!r} / {corps!r}")
    verifier(" '" not in affiche and " -" not in affiche,
             "aucune espace devant une apostrophe ou un trait d'union")
    verifier("Et bien. Comment" in affiche, "les mots sans détail du moteur restent affichés")
    verifier(vue.get("corps") == corps, "« Copier le texte » copie le corps du fichier")
    verifier(vue["statistiques"]["mots"] == len(premier.mots) + len(second.mots),
             "toutes les confiances restent comptées", str(vue["statistiques"]))

    retour = lecture.appliquer_correction(txt, "C'est peut-être", "C'était peut-être", ajouter_regle=False)
    verifier(retour.get("ok") is True, "une expression avec apostrophe et trait d'union se corrige",
             str(retour))
    apres = lecture.charger(txt)
    verifier("\n\n".join(texte_affiche(p) for p in apres["paragraphes"]) == apres["corps"],
             "après correction, la vue suit toujours le fichier")


def essai_casse_et_doublons(base: Path) -> None:
    titre("Corrections : la casse se corrige, une forme étendue ne se répète pas")
    regle = lambda s, c: vocabulaire.analyser_corrections(f"{s} => {c}")[0]  # noqa: E731
    verifier(vocabulaire.verifier_regle("gitlab", "GitLab") == "", "« gitlab » vers « GitLab » accepté")
    verifier(bool(vocabulaire.verifier_regle("api", "api")), "une forme strictement identique reste refusée")
    texte, n = vocabulaire.appliquer("le gitlab, le GitLab et le GITLAB", regle("gitlab", "GitLab"))
    verifier(texte == "le GitLab, le GitLab et le GitLab" and n == 2,
             "seules les formes à changer sont comptées", f"{texte!r}, {n}")
    phrase = "les réseaux sociaux, puis les réseaux"
    texte, n = vocabulaire.appliquer(phrase, regle("réseaux", "réseaux sociaux"))
    verifier(texte == "les réseaux sociaux, puis les réseaux sociaux" and n == 1,
             "aucun « réseaux sociaux sociaux »", f"{texte!r}, {n}")
    texte2, n2 = vocabulaire.appliquer(texte, regle("réseaux", "réseaux sociaux"))
    verifier(texte2 == texte and n2 == 0, "une seconde application ne change rien", f"{texte2!r}, {n2}")
    texte, n = vocabulaire.appliquer("chemin a", regle("a", r"b\1"))
    verifier(texte == r"chemin b\1", "une barre oblique inverse est prise à la lettre", texte)

    dossier = base / "casse"
    dossier.mkdir()
    txt = ecrire(dossier, [segment(0.0, 4.0, jetons("On pousse sur gitlab ce soir."))])
    retour = lecture.appliquer_correction(txt, "gitlab", "GitLab", ajouter_regle=False)
    verifier(retour.get("ok") is True and "sur GitLab ce soir" in txt.read_text(encoding="utf-8"),
             "la relecture corrige la casse dans le fichier", str(retour))


def essai_apercu_et_annulation(base: Path) -> None:
    titre("Corrections : aperçu des endroits touchés, annulation, règle sur demande")
    dossier = base / "apercu"
    dossier.mkdir()
    txt = ecrire(dossier, [
        segment(0.0, 4.0, jetons("Les réseaux sociaux, ça va.")),
        segment(4.5, 9.0, jetons("Mais les réseaux, je ne les comprends pas, les réseaux.")),
    ])
    avant = txt.read_text(encoding="utf-8")
    json_avant = (txt.with_suffix(".json")).read_text(encoding="utf-8")
    regles_avant = vocabulaire.lire_corrections()

    apercu = lecture.apercu_correction(txt, "réseaux", "réseaux sociaux")
    verifier(apercu.get("ok") is True and apercu.get("nombre") == 2,
             "l'aperçu compte les seuls endroits qui changeront", str(apercu))
    extraits = apercu.get("extraits") or []
    verifier(len(extraits) == 2 and all(x["forme"] == "réseaux" for x in extraits)
             and extraits[0]["avant"].endswith("Mais les ") and extraits[0]["apres"].startswith(", je"),
             "chaque endroit est montré avec son contexte", str(extraits[:1]))
    verifier(txt.read_text(encoding="utf-8") == avant, "l'aperçu n'écrit rien")
    absent = lecture.apercu_correction(txt, "GAFAM", "Gafam")
    verifier(absent.get("ok") is False and "retrouvé" in absent.get("message", ""),
             "une forme absente est dite avant d'appliquer")
    deja = lecture.apercu_correction(txt, "les", "Les")
    verifier(deja.get("ok") is True and deja.get("nombre") == 3,
             "seules les formes à changer apparaissent dans l'aperçu", str(deja.get("nombre")))
    deja = lecture.apercu_correction(txt, "mais", "Mais")
    verifier(deja.get("ok") is False and "déjà écrit" in deja.get("message", ""),
             "une forme déjà juste partout est dite comme telle", deja.get("message", ""))

    sans_regle = lecture.appliquer_correction.__defaults__
    verifier(sans_regle == (False,), "par défaut, la correction ne crée pas de règle globale",
             str(sans_regle))
    retour = lecture.appliquer_correction(txt, "réseaux", "réseaux sociaux", ajouter_regle=True)
    verifier(retour.get("ok") and retour.get("remplacements") == 2 and retour.get("regle_ajoutee"),
             "correction appliquée, règle ajoutée à la demande", str(retour))
    verifier(lecture.correction_annulable(txt), "la correction est annulable")
    annule = lecture.annuler_correction(txt)
    verifier(annule.get("ok") is True and annule.get("regle_retiree") is True,
             "annulation faite, règle retirée", str(annule))
    verifier(txt.read_text(encoding="utf-8") == avant
             and txt.with_suffix(".json").read_text(encoding="utf-8") == json_avant,
             "texte et compagnon reviennent à l'octet près")
    verifier(vocabulaire.lire_corrections().strip() == regles_avant.strip(),
             "les corrections reviennent à leur état d'avant")
    verifier(lecture.annuler_correction(txt).get("ok") is False, "rien à annuler une seconde fois")

    lecture.appliquer_correction(txt, "comprends", "comprenais")
    txt.write_text(txt.read_text(encoding="utf-8") + "ajout à la main\n", encoding="utf-8")
    verifier(lecture.annuler_correction(txt).get("ok") is False
             and "ajout à la main" in txt.read_text(encoding="utf-8"),
             "un fichier modifié depuis n'est pas écrasé par l'annulation")


def essai_moteur_sans_confiance(base: Path) -> None:
    from app import adaptation, materiel

    titre("Moteur sans confiance par mot : la relecture et la proposition le disent")
    dossier = base / "openvino"
    dossier.mkdir()
    # Ce que rend OpenVINO : des mots horodatés, probabilité inconnue (-1).
    txt = ecrire(dossier, [segment(0.0, 4.0, jetons("Le moteur Intel ne note pas ses mots.", p=-1.0))])
    vue = lecture.charger(txt)
    stats = vue["statistiques"]
    verifier(vue["compagnon"] and stats["mots"] == 0 and stats["sans_confiance"] > 0,
             "aucune confiance connue, et les mots sans confiance sont comptés", str(stats))
    (dossier / "ct2").mkdir()
    normal = lecture.charger(ecrire(dossier / "ct2", [segment(0.0, 4.0, jetons("Mots notés."))]))
    verifier(normal["statistiques"]["sans_confiance"] == 0, "un moteur qui note ses mots n'est pas concerné")

    mat = materiel.detecter()
    profil = adaptation.Profil(processeur="essai", logiques=16, ram_go=32, openvino_installe=True)
    proposition = adaptation.proposer(mat, profil, etat_modele=lambda _d: "complet")
    verifier(proposition["moteur"] == "openvino"
             and any("ne donne pas la confiance" in n for n in proposition["notes"]),
             "proposer le moteur Intel dit ce que l'on perd", str(proposition["notes"]))
    profil = adaptation.Profil(processeur="essai", logiques=16, ram_go=32)
    proposition = adaptation.proposer(mat, profil, etat_modele=lambda _d: "complet")
    verifier(not any("ne donne pas la confiance" in n for n in proposition["notes"]),
             "le moteur habituel ne porte pas cette mention")


def essai_ecoute(base: Path) -> None:
    import urllib.error
    import urllib.request

    from app import ecoute

    titre("Écoute de la relecture : un seul fichier, servi en local, par plages")
    dossier = base / "ecoute"
    dossier.mkdir()
    audio = dossier / "réunion du lundi.wav"
    contenu = bytes(range(256)) * 40
    audio.write_bytes(contenu)
    autre = dossier / "autre.wav"
    autre.write_bytes(b"autre")

    serveur = ecoute.Ecoute()
    try:
        adresse = serveur.adresse_pour(audio)
        verifier(adresse.startswith("http://127.0.0.1:") and "file:" not in adresse
                 and "réunion" not in adresse,
                 "adresse http locale, sans chemin ni nom de fichier", adresse)

        def lire(url: str, plage: str = "") -> tuple[int, dict, bytes]:
            requete = urllib.request.Request(url, headers={"Range": plage} if plage else {})
            try:
                with urllib.request.urlopen(requete, timeout=10) as reponse:
                    return reponse.status, dict(reponse.headers), reponse.read()
            except urllib.error.HTTPError as exc:
                return exc.code, dict(exc.headers), b""

        statut, entetes, corps = lire(adresse)
        verifier(statut == 200 and corps == contenu and entetes.get("Content-Type") == "audio/wav"
                 and entetes.get("Accept-Ranges") == "bytes",
                 "le fichier entier, avec son type et l'annonce des plages", f"{statut} {entetes}")
        statut, entetes, corps = lire(adresse, "bytes=1000-1099")
        verifier(statut == 206 and corps == contenu[1000:1100]
                 and entetes.get("Content-Range") == f"bytes 1000-1099/{len(contenu)}",
                 "une plage pour se déplacer dans l'enregistrement", f"{statut} {entetes.get('Content-Range')}")
        statut, _, corps = lire(adresse, "bytes=-10")
        verifier(statut == 206 and corps == contenu[-10:], "la fin du fichier, pour la durée")
        statut, _, _ = lire(adresse, f"bytes={len(contenu) + 5}-")
        verifier(statut == 416, "une plage hors du fichier est refusée")
        racine = adresse.split("/son/")[0]
        refus = [lire(racine + chemin)[0] for chemin in (
            "/son/inconnu-inconnu-inconnu", "/son/../autre.wav", "/autre.wav",
            "/" + str(autre).replace("\\", "/"))]
        verifier(all(code == 404 for code in refus), "aucune autre adresse ne sert un fichier", str(refus))
        nouvelle = serveur.adresse_pour(autre)
        verifier(lire(adresse)[0] == 404 and lire(nouvelle)[2] == b"autre",
                 "ouvrir une autre transcription remplace le fichier servi")
    finally:
        serveur.arreter()


# ---------------------------------------------------------------------------
# Fichiers produits
# ---------------------------------------------------------------------------

def reunion_sans_locuteurs() -> list[Segment]:
    """Quatre minutes de parole d'une seule voix, avec des pauses franches."""
    phrases = [
        "On commence par le point sur le budget de l'année prochaine, qui reste serré.",
        "Les dépenses de formation ont augmenté, surtout pour les nouveaux arrivants.",
        "Il faudra en reparler avec la direction avant la fin du mois, c'est certain.",
        "Deuxième sujet, le déménagement du service, prévu pour le printemps.",
        "Les cartons arrivent la semaine du quinze, chacun prépare son bureau.",
        "Dernier point, les congés d'été : envoyez vos dates avant vendredi.",
    ]
    segments = []
    debut = 0.0
    for rang, phrase in enumerate(phrases):
        fin = debut + 6.0
        segments.append(segment(debut, fin, jetons(phrase)))
        # Pause franche après la troisième et la cinquième phrase.
        debut = fin + (3.0 if rang in (2, 4) else 0.4)
    return segments


def essai_fichiers_produits(base: Path) -> None:
    titre("Fichiers produits : paragraphes, en-tête, suffixe commun, historique")
    dossier = base / "produits"
    dossier.mkdir()
    segments = reunion_sans_locuteurs()
    formats = {"txt": True, "srt": True, "vtt": True, "horodatage": True}
    txt = ecrire(dossier, segments, formats)
    contenu = txt.read_text(encoding="utf-8")
    entete, corps = lecture.separer_entete(contenu)
    paragraphes = [p for p in corps.strip().split("\n\n") if p]
    verifier(len(paragraphes) == 3, "le texte est coupé en paragraphes aux pauses",
             f"{len(paragraphes)} paragraphe(s)")
    verifier(all(p.startswith("[00:") for p in paragraphes)
             and paragraphes[1].startswith("[00:00:21]"),
             "l'horodatage, demandé, marque chaque paragraphe", repr(paragraphes[1][:20]))
    ligne_source = next(ligne for ligne in entete.splitlines() if ligne.startswith("Source"))
    verifier(ligne_source.endswith(": reunion equipe.m4a") and str(base) not in entete,
             "l'en-tête donne le nom de l'enregistrement, pas son chemin", ligne_source)

    vue = lecture.charger(txt)
    verifier([p["texte"] for p in vue["paragraphes"]] == [p.split("] ", 1)[1] for p in paragraphes],
             "la vue coupe ses paragraphes exactement comme le fichier")

    second = ecrire(dossier, segments, formats)
    noms = sorted(f.name for f in (dossier / "sorties").iterdir())
    attendus = {second.stem + ext for ext in (".txt", ".json", ".srt", ".vtt")}
    verifier(second.stem.endswith("-2") and attendus <= set(noms),
             "la seconde transcription porte le même suffixe sur tous ses fichiers", str(noms))

    historique = sorties.historique(dossier / "sorties")
    verifier(len(historique) == 2 and all(len(h["formats"]) == 3 for h in historique),
             "l'historique compte des transcriptions, chacune avec ses formats",
             str([(h["nom"], [f["format"] for f in h["formats"]]) for h in historique]))
    for rang in range(45):
        (dossier / "sorties" / f"ancienne-{rang:02d}.txt").write_text("x", encoding="utf-8")
    verifier(len(sorties.historique(dossier / "sorties")) == 47, "plus de coupure à 40 fichiers")


# ---------------------------------------------------------------------------
# Conseil et annonces de durée
# ---------------------------------------------------------------------------

def essai_une_seule_verite(base: Path) -> None:
    import copy

    from app import adaptation, calibration, diarisation, materiel, presets, rythme

    titre("Conseil et durées : une seule source, le rythme compté une fois")
    racine = chemins.RACINE
    # Racine temporaire : ni les mesures du poste, ni celles du banc des rythmes.
    chemins.RACINE = base / "racine"
    chemins.RACINE.mkdir()
    try:
        mat = materiel.Materiel(cpu_nom="Processeur d'essai", coeurs_physiques=8,
                                coeurs_logiques=16, ram_go=32.0)
        profil = adaptation.Profil(processeur="essai", logiques=16, ram_go=32, openvino_installe=True)
        proposition = adaptation.proposer(mat, profil, etat_modele=lambda _d: "complet")
        reco = presets.recommandation(mat, proposition)
        verifier(proposition["preset"] == "rapide" and reco["preset_conseille"] == "rapide"
                 and proposition["resume"] in reco["phrase"],
                 "la pastille et la fiche du matériel suivent la proposition", reco["phrase"])
        reco_seule = presets.recommandation(mat)
        verifier(reco_seule["preset_conseille"] == "qualite",
                 "sans proposition, la règle de repli décide seule (elle disait « Qualité », d'où la contradiction)")

        essai = copy.copy(mat)
        essai.moteur, essai.peripherique_openvino = "openvino", "CPU"
        verifier(proposition["une_heure"] == presets.pour_une_heure("rapide", essai, proposition["rythme"]),
                 "la proposition annonce ce qu'annonceront les cartes une fois appliquée",
                 proposition["une_heure"])
        for nom in rythme.RYTHMES:
            verifier(presets.pour_une_heure("qualite", mat, nom) == presets.formater_duree(
                presets.estimer_secondes(3600, "qualite", mat) * rythme.coefficient(nom, mat.cle_calcul)),
                f"carte et rythme « {nom} » : le même chiffre")
        reco_discret = presets.recommandation(mat, None, "discret")
        verifier(reco_discret["estimations"][0]["pour_une_heure"] == presets.pour_une_heure("qualite", mat, "discret"),
                 "la fiche du matériel tient compte du rythme choisi")

        verifier(diarisation.effective(True) == diarisation.disponible() and not diarisation.effective(False),
                 "la séparation des locuteurs ne compte que si elle est installée et demandée")
        if not diarisation.disponible():
            verifier(presets.estimer_annonce(600, "rapide", mat, "vitesse", diarisation.effective(True))
                     == presets.estimer_annonce(600, "rapide", mat, "vitesse", False),
                     "non installée, elle n'allonge pas l'estimation de la file")

        # Une transcription faite en « discret » (2,4 fois plus lente) : sa mesure
        # est rangée ramenée à la vitesse maximale, le rythme n'est compté qu'une fois.
        c_discret = rythme.coefficient("discret", "cpu")
        ralenti = rythme.coefficient_effectif({}, {"discret": 120.0}, "discret", "cpu")
        verifier(abs(ralenti - c_discret) < 1e-9, "tout le calcul en discret : coefficient du discret")
        moitie = rythme.coefficient_effectif({"vitesse": 10.0}, {"vitesse": 70.0, "discret": 60.0}, "discret", "cpu")
        verifier(abs(moitie - (1.0 + c_discret) / 2) < 1e-9, "moitié à pleine vitesse : moyenne pondérée")
        verifier(rythme.coefficient_effectif({}, {}, "equilibre", "cpu") == rythme.coefficient("equilibre", "cpu"),
                 "sans relevé : coefficient du rythme choisi")
        calibration.enregistrer("large-v3", "cpu", 5, 600.0, 600.0 / ralenti, mat, lot=8)
        verifier(abs(presets.estimer_annonce(600, "qualite", mat, "discret") - 600.0) < 1.0
                 and abs(presets.estimer_annonce(600, "qualite", mat, "vitesse") - 600.0 / c_discret) < 1.0,
                 "après une mesure en discret, l'annonce en discret retrouve la durée réelle",
                 f"{presets.estimer_annonce(600, 'qualite', mat, 'discret'):.0f} s")
    finally:
        chemins.RACINE = racine


# ---------------------------------------------------------------------------
# File d'attente
# ---------------------------------------------------------------------------

class _MoteurInerte:
    """Moteur de remplacement : la file n'en attend que la libération."""

    cle_calcul = "cpu"
    sur_puce = False

    def liberer(self) -> None:
        pass


class _MoteurFactice(_MoteurInerte):
    """Moteur qui « transcrit » en rendant des segments préparés, sans modèle."""

    tokeniseur = None

    def __init__(self, segments: list[Segment], pause: float = 0.0):
        self.segments = segments
        self.pause = pause

    def charger(self, modele: str, signaler) -> None:
        import time

        signaler("info", f"Chargement du modèle {modele}...")
        time.sleep(self.pause)

    def transcrire(self, signal, duree, langue, reglages, amorce="", progression=None,
                   interrompu=None, decalage=0.0, sur_segment=None):
        import time

        for rang, seg in enumerate(self.segments, start=1):
            time.sleep(self.pause)
            if sur_segment:
                sur_segment(seg)
            if progression:
                progression(rang / len(self.segments))
        return list(self.segments), {"duree": duree, "langue": langue,
                                     "peripherique": "cpu", "type_calcul": "int8"}


def file_factice(base: Path, nom: str, config_en_plus: dict, pause: float = 0.0):
    """
    Une vraie file sur un faux enregistrement : décodage et moteur remplacés,
    tout le reste (phases, progression, écriture, bilans) est le vrai chemin.
    Renvoie (bilan de la file, rappels reçus dans l'ordre, dossier de sortie).
    """
    import copy
    import threading
    import time

    import numpy as np

    from app import audio as audio_module, config as config_module, materiel, traitement

    dossier = base / nom
    dossier.mkdir()
    audio = dossier / "reunion.wav"
    audio.write_bytes(b"\0" * 64)
    segments = reunion_sans_locuteurs()
    duree = segments[-1].fin + 1.0
    file = traitement.FileTraitement(materiel.detecter())
    file.ajouter([str(audio)])
    config = copy.deepcopy(config_module.DEFAUTS)
    config.update({"dossier_sortie": str(dossier / "sorties"), "sauvegarde_progressive": False,
                   "utiliser_glossaire": False, "appliquer_corrections": False, **config_en_plus})
    recus: list[tuple] = []
    fini = threading.Event()
    bilan: dict = {}
    depart = time.monotonic()
    rappels = traitement.Rappels(
        etat=lambda i, e, m: recus.append(("etat", e, m, time.monotonic() - depart)),
        progression=lambda i, d: recus.append(("progression", dict(d), time.monotonic() - depart)),
        termine=lambda i, d: recus.append(("termine", dict(d))),
        journal_ui=lambda n, t: recus.append(("journal", n, t)),
        file_terminee=lambda d: (bilan.update(d), fini.set()),
    )
    fabriquer, decoder = traitement.fabriquer_moteur, audio_module.decoder
    traitement.fabriquer_moteur = lambda *_: _MoteurFactice(segments, pause)
    audio_module.decoder = lambda *_a, **_k: np.zeros(int(duree * audio_module.FREQUENCE), dtype=np.float32)
    try:
        file.demarrer(config, rappels)
        fini.wait(120)
    finally:
        traitement.fabriquer_moteur, audio_module.decoder = fabriquer, decoder
    return bilan, recus, dossier / "sorties"


def essai_voix_non_installees(base: Path) -> None:
    from app import diarisation

    titre("Séparation des voix cochée mais absente : dit avant, et dans l'état final")
    if diarisation.disponible():
        print("  (séparation des locuteurs installée sur ce poste : essai sans objet)")
        return
    racine = chemins.RACINE
    chemins.RACINE = base / "racine-voix"
    chemins.RACINE.mkdir()
    try:
        bilan, recus, sorties_dossier = file_factice(base, "voix", {"diarisation": True})
    finally:
        chemins.RACINE = racine
    termine = next((r[1] for r in recus if r[0] == "termine"), {})
    phases = [r[1] for r in recus if r[0] == "etat"]
    verifier(termine.get("ok") and termine.get("voix_non_separees") is True,
             "la ligne du fichier sait que les voix n'ont pas été séparées", str(termine))
    verifier(bilan.get("voix_non_separees") == 1, "le bilan de la file le compte", str(bilan))
    verifier("locuteurs" not in phases, "pas de phase « séparation » qui ne peut pas avoir lieu", str(phases))
    pourcents = [r[1]["pct"] for r in recus if r[0] == "progression"]
    verifier(max(x for x in pourcents if x < 100) == 99,
             "la barre ne plafonne pas à 85 % pour une séparation absente", str(pourcents))
    texte = next(sorties_dossier.glob("*.txt")).read_text(encoding="utf-8")
    verifier("n'est pas installée" in texte, "l'en-tête dit pourquoi, sans renvoyer au journal")


def essai_retour_pendant_calcul(base: Path) -> None:
    from app import rythme

    titre("Pendant le calcul : phases nommées, temps qui avance, reste lissé")
    racine = chemins.RACINE
    chemins.RACINE = base / "racine-progression"
    chemins.RACINE.mkdir()
    try:
        _, recus, _ = file_factice(base, "progression", {"diarisation": False}, pause=0.05)
    finally:
        chemins.RACINE = racine
    progressions = [r[1] for r in recus if r[0] == "progression"]
    phases = [p["phase"] for p in progressions]
    verifier(phases[0] == langues.t("phase.chargement") and progressions[0].get("indetermine") is True,
             "le chargement du modèle est une phase à part, barre indéterminée", str(phases[:2]))
    verifier(phases[1] == langues.t("phase.transcription") and progressions[1]["pct"] == 0
             and progressions[1].get("restant_s"),
             "la transcription s'annonce dès le modèle chargé, avec un reste à faire", str(progressions[1]))
    verifier(phases[-2] == langues.t("etat.ecriture") and phases[-1] == langues.t("phase.termine"),
             "l'écriture des fichiers a sa phase, avant « Terminé »", str(phases[-3:]))
    pourcents = [p["pct"] for p in progressions]
    verifier(pourcents == sorted(pourcents), "une seule progression, qui ne recule jamais", str(pourcents))
    ecoules = [p.get("ecoule_s") for p in progressions]
    verifier(all(isinstance(e, float) for e in ecoules) and ecoules == sorted(ecoules),
             "chaque relevé donne le temps écoulé en secondes, pour l'horloge de l'interface")
    journal = [r[2] for r in recus if r[0] == "journal"]
    charge = next((i for i, t in enumerate(journal) if t.startswith("Modèle chargé")), -1)
    verifier(charge > 0 and journal[charge - 1].startswith("Chargement du modèle"),
             "le journal dit la fin du chargement : le pied de page ne reste pas figé dessus",
             str(journal[:4]))

    lisseur = rythme.LisseurRestant()
    premier = lisseur(600.0, 0.0)
    apres_saut = lisseur(150.0, 20.0)
    verifier(premier == 600.0 and 400.0 < apres_saut < 580.0,
             "un relevé plus rapide déplace la fin d'une fraction, sans saut", f"{apres_saut:.0f} s")
    stable = [lisseur(apres_saut - 10.0 * k, 20.0 + 10.0 * k) for k in range(1, 4)]
    verifier(all(abs(stable[k] - (apres_saut - 10.0 * (k + 1))) < 1.0 for k in range(3)),
             "une cadence régulière décompte normalement", str([round(s) for s in stable]))


def essai_file_apres_arret(base: Path) -> None:
    import copy
    import threading

    from app import config as config_module, materiel, moteur, traitement

    titre("Après « Arrêter » : reprendre, relancer, redéposer")
    dossier = base / "file"
    dossier.mkdir()
    un, deux = dossier / "un.wav", dossier / "deux.wav"
    for f in (un, deux):
        f.write_bytes(b"\0" * 64)

    file = traitement.FileTraitement(materiel.detecter())
    ajoutes = file.ajouter([str(un), str(deux)])
    verifier(len(ajoutes) == 2, "deux fichiers en file")

    # Le premier fichier est arrêté en route, comme par le bouton « Arrêter ».
    def traiter(element, *_):
        element.etat = "transcription"
        file.arreter()
        raise moteur.Interruption()

    file._traiter = traiter
    fabriquer = traitement.fabriquer_moteur
    traitement.fabriquer_moteur = lambda *_: _MoteurInerte()
    fini = threading.Event()
    bilan: dict = {}
    try:
        config = copy.deepcopy(config_module.DEFAUTS)
        file.demarrer(config, traitement.Rappels(
            file_terminee=lambda d: (bilan.update(d), fini.set())))
        fini.wait(60)
    finally:
        traitement.fabriquer_moteur = fabriquer
    etats = [e.etat for e in file.elements]
    verifier(etats == ["annule", "attente"],
             "le fichier arrêté est « arrêté », le suivant reste en attente", str(etats))

    remis = file.ajouter_pour_reprise(str(un), "cle-de-reprise")
    verifier(bool(remis) and remis["etat"] == "attente" and file.elements[0].reprise == "cle-de-reprise",
             "« Reprendre » remet en attente le fichier arrêté, avec sa reprise", str(remis))
    verifier(file.ajouter([str(un)]) == [] and file.derniers_doublons == 1,
             "un fichier déjà en attente n'est pas ajouté deux fois, et c'est compté")

    file.elements[1].etat = "annule"
    redepose = file.ajouter([str(deux)])
    verifier(len(redepose) == 1 and redepose[0]["id"] == ajoutes[1]["id"]
             and file.elements[1].etat == "attente",
             "redéposer un fichier annulé le remet en attente, sans doublon", str(redepose))
    file.elements[1].etat = "erreur"
    relance = file.relancer(ajoutes[1]["id"])
    verifier(bool(relance) and file.elements[1].etat == "attente", "« Relancer » depuis la ligne")
    file.elements[1].etat = "transcription"
    verifier(file.ajouter_pour_reprise(str(deux), "x") is None and file.relancer(ajoutes[1]["id"]) is None,
             "un fichier en cours de calcul n'est jamais remis en attente")
    verifier(len(file.elements) == 2, "toujours deux lignes, jamais de doublon")


# ---------------------------------------------------------------------------
# Accessibilité élémentaire de l'interface
# ---------------------------------------------------------------------------

def _contraste(couleur_a: str, couleur_b: str) -> float:
    def luminance(couleur: str) -> float:
        h = couleur.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        canaux = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    claire, sombre = sorted((luminance(couleur_a), luminance(couleur_b)), reverse=True)
    return (claire + 0.05) / (sombre + 0.05)


def essai_accessibilite() -> None:
    import re

    titre("Accessibilité : contraste, clavier, dialogues, annonces")
    css = (RACINE / "web" / "styles.css").read_text(encoding="utf-8")
    html = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    js = (RACINE / "web" / "app.js").read_text(encoding="utf-8")

    # Chaque bloc de thème qui définit le texte secondaire, avec ses fonds.
    ratios = []
    for bloc in css.split("}"):
        faible = re.search(r"--texte-faible:\s*(#[0-9a-fA-F]{3,6})", bloc)
        if not faible:
            continue
        for fond in ("--fond", "--carte", "--carte-creuse"):
            valeur = re.search(rf"{fond}:\s*(#[0-9a-fA-F]{{3,6}})", bloc)
            if valeur:
                ratios.append(round(_contraste(faible.group(1), valeur.group(1)), 2))
    verifier(len(ratios) == 12 and min(ratios) >= 4.5,
             "texte secondaire à 4,5:1 au moins sur tous les fonds, dans les deux thèmes", str(ratios))

    verifier('class="sortie"' not in js.replace('<button class="sortie"', ""),
             "les fichiers produits d'une ligne sont des boutons, atteignables au clavier")
    verifier(js.count("data-lire=") >= 2 and "ui.ligne.relire" in js,
             "chaque transcription, dans la file comme dans l'historique, a son bouton « Relire » en toutes lettres")
    verifier("setAttribute('role', 'dialog')" in js and "setAttribute('aria-modal', 'true')" in js
             and "aria-labelledby" in js, "chaque modale est un dialogue nommé par son titre")
    verifier("el.inert" in js and "pileFocus" in js,
             "l'arrière-plan d'une modale est inerte et le focus revient à son point de départ")
    verifier(re.search(r'id="etat-global"[^>]*role="status"[^>]*aria-live="polite"', html) is not None,
             "la ligne d'état (progression, bilans, erreurs) est annoncée aux lecteurs d'écran")
    verifier('role="progressbar"' in js and "aria-valuenow" in js,
             "la barre d'un fichier en cours est une barre de progression lisible")
    sans_nom = [b for b in re.findall(r'<button class="bouton-ligne"[^>]*>', js) if "aria-label" not in b]
    verifier(not sans_nom, "les boutons à icône des lignes ont un nom accessible", str(sans_nom))
    icones = re.findall(r'<button class="bouton-icone"[^>]*>', html)
    verifier(all("data-i18n-aria" in b or "data-fermer" in b for b in icones),
             "chaque bouton à icône de la page a un nom accessible",
             str([b for b in icones if "data-i18n-aria" not in b and "data-fermer" not in b]))
    verifier("function pieger" in js and "e.key === 'Tab'" in js,
             "Tab et Maj+Tab tournent dans la fenêtre du dessus")

    # Contrastes des couples texte et fond de la refonte, dans chaque thème.
    def couleurs(bloc: str) -> dict:
        return dict(re.findall(r"(--[a-z-]+):\s*(#[0-9a-fA-F]{3,6})", bloc))

    blocs = [couleurs(b) for b in css.split("}") if re.search(r"--texte-faible:\s*#", b)]
    couples = [("--texte-faible", "--carte-creuse"), ("--texte-doux", "--fond"), ("--ambre", "--ambre-fond"),
               ("--accent", "--accent-doux"), ("--accent-contraste", "--accent"), ("--vert", "--vert-fond"),
               ("--rouge", "--rouge-fond"), ("--texte", "--lu"), ("--texte", "--trouve")]
    faibles = []
    for numero, bloc in enumerate(blocs):
        for avant_plan, fond in couples:
            if avant_plan in bloc and fond in bloc:
                ratio = _contraste(bloc[avant_plan], bloc[fond])
                if ratio < 4.5:
                    faibles.append(f"thème {numero} {avant_plan}/{fond} {ratio:.2f}")
    verifier(len(blocs) == 4 and not faibles,
             "texte d'avertissement, d'accent, de succès, d'erreur et surlignages à 4,5:1 au moins, dans les deux thèmes",
             ", ".join(faibles))


def essai_ecrans() -> None:
    """
    L'organisation de l'interface : l'écran principal sert les réunions, les
    outils du poste vivent dans Réglages, la relecture occupe tout l'écran.
    """
    import re

    titre("Écrans : réunions d'abord, réglages rangés, relecture plein cadre")
    html = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    js = "\n".join((RACINE / "web" / nom).read_text(encoding="utf-8") for nom in ("app.js", "relecture.js", "espace.js"))
    principal = re.search(r'<main[^>]*id="vue-principale".*?</main>', html, re.S).group(0)
    absents = [i for i in ("presets", "btn-lancer-banc", "materiel-detail", "btn-installer-openvino",
                           "comp-bloc", "opt-avance", "btn-reconnaitre", "bloc-proposition")
               if f'id="{i}"' in principal]
    verifier(not absents, "l'écran principal ne porte ni le banc, ni les moteurs, ni la fiche du poste", str(absents))
    verifier(principal.count("bascule") <= 2 and "segments-qualite" in principal and "segments-rythme" in principal,
             "au lancement : qualité, rythme, et les voix seulement si elles sont installées")
    verifier('id="vue-relecture"' in html and 'id="modale-lecture"' not in html,
             "la relecture est un écran entier, plus une fenêtre posée sur l'application")
    groupes = re.findall(r'data-i18n="ui\.reg\.groupe\.(\w+)"', html)
    verifier(groupes == ["courant", "avance", "mesures"],
             "Réglages : usage courant, puis avancé, puis mesures et diagnostic", str(groupes))
    for geste, preuve in (("lecture et pause à l'Espace", "touche === ' '"),
                          ("5 s en arrière ou en avant aux flèches", "deplacer(touche === 'ArrowLeft' ? -5 : 5)"),
                          ("recherche par Ctrl+F", "(touche === 'f' || touche === 'F')"),
                          ("point à vérifier suivant par N", "touche === 'n' || touche === 'N'"),
                          ("Entrée valide depuis toute la fenêtre de correction",
                           "$('#modale-correction').addEventListener('keydown'"),
                          ("après une correction, N repart du mot atteint", "retablirVise(repere)"),
                          ("vitesse aux touches directes , et ; (AZERTY)", "touche === ',' || touche === ';'"),
                          ("N puis Entrée corrige le mot atteint", "selectionnerMot(lect.vise)"),
                          ("un clic sur un bouton de lecture ne lui laisse pas Espace",
                           "$('.rl-outils').addEventListener('mousedown'"),
                          ("la position de relecture est gardée", "'memoriser_position'"),
                          ("clic sur un mot : l'écoute s'y place, sur ce mot", "placerA(lect.mots[i].d)"),
                          ("un double-clic qui sélectionne ne déplace pas l'écoute", "e.detail > 1")):
        verifier(preuve in js, f"relecture : {geste}")
    verifier("touche === ' ' && !cible.closest('button')" not in js,
             "relecture : Espace lit même après un clic sur un bouton")
    piege = re.search(r"function pieger.*?querySelectorAll\(\s*'([^']*)'", js, re.S)
    verifier(piege and "a[href]" in piege.group(1) and ", [href]" not in piege.group(1),
             "piège du focus : une icône (<use href>) ne compte pas parmi les éléments focalisables",
             piege.group(1) if piege else "")
    verifier("'occurrences_correction'" in js and "'corriger_occurrences'" in js and "data-rang" in js,
             "une correction vise les endroits cochés, pas tout le fichier d'office")
    verifier(html.count("doublure-passerelle.js") == 1 and "DOUBLURE_PASSERELLE" in js
             and js.count("DOUBLURE_PASSERELLE") == 1,
             "la doublure de la passerelle tient dans un fichier et une balise, retirables à la fusion")
    catalogue = (RACINE / "web" / "langues.js").read_text(encoding="utf-8")
    verifier("(s)" not in catalogue, "aucun accord en « (s) » dans les textes de l'interface")


def essai_relecture_ciblee(base: Path) -> None:
    """Corriger un seul endroit, renommer un locuteur, exporter : la vue reste le fichier."""
    from app import compagnon, relecture

    titre("Relecture : un seul endroit corrigé, locuteurs renommés, export")
    dossier = base / "ciblee"
    dossier.mkdir()
    txt = ecrire(dossier, [
        segment(0.0, 4.0, jetons("On ouvre gitlab ce matin."), "Locuteur 1"),
        segment(4.5, 9.0, jetons("Puis gitlab redémarre, et gitlab revient."), "Locuteur 2"),
        segment(9.5, 12.0, jetons("Bien, gitlab est stable."), "Locuteur 1"),
    ], details={"nb_locuteurs": 2})
    avant = txt.read_text(encoding="utf-8")
    json_avant = compagnon.chemin_pour(txt).read_text(encoding="utf-8")

    vue = relecture.occurrences(txt, "gitlab", "GitLab", avant="Puis ", apres=" redémarre")
    verifier(vue.get("ok") and vue["nombre"] == 4 and vue["choisie"] == 1,
             "l'aperçu liste les quatre endroits et retrouve celui de la sélection", str(vue)[:200])
    retour = relecture.corriger(txt, "gitlab", "GitLab", [vue["choisie"]])
    apres = txt.read_text(encoding="utf-8")
    verifier(retour.get("ok") and apres.count("GitLab") == 1 and "Puis GitLab redémarre" in apres,
             "seul l'endroit sélectionné change dans le fichier", str(retour))
    charge = lecture.charger(txt)
    affiche = "\n\n".join(texte_affiche(p) for p in charge["paragraphes"])
    verifier(all(texte_affiche(p) == p["texte"] for p in charge["paragraphes"])
             and "Puis GitLab redémarre, et gitlab revient." in affiche,
             "la vue, relue du compagnon, montre le même texte que le fichier")
    verifier(lecture.annuler_correction(txt).get("ok") and txt.read_text(encoding="utf-8") == avant
             and compagnon.chemin_pour(txt).read_text(encoding="utf-8") == json_avant,
             "Annuler remet le fichier et le compagnon à l'octet près")

    retour = relecture.corriger(txt, "gitlab", "GitLab", [0, 2])
    verifier(retour.get("ok") and txt.read_text(encoding="utf-8").count("GitLab") == 2,
             "deux endroits cochés, deux endroits corrigés", str(retour))
    lecture.annuler_correction(txt)
    retour = relecture.corriger(txt, "gitlab", "GitLab", "tous")
    verifier(retour.get("ok") and "gitlab" not in lecture.separer_entete(txt.read_text(encoding="utf-8"))[1],
             "« tout corriger » passe par la correction habituelle", str(retour))
    lecture.annuler_correction(txt)
    verifier(relecture.corriger(txt, "gitlab", "GitLab", []).get("code") == "aucun_endroit",
             "rien de coché : rien ne change, et l'interface le dit")

    retour = relecture.renommer_locuteur(txt, "Locuteur 1", "alice")
    renomme = txt.read_text(encoding="utf-8")
    donnees = compagnon.lire(txt)
    verifier(retour.get("ok") and retour["paragraphes"] == 2 and "Alice : On ouvre" in renomme
             and "Locuteur 1" not in renomme
             and sum(1 for s in donnees["segments"] if s.get("l") == "Alice") == 2,
             "un locuteur renommé l'est dans le fichier et le compagnon, majuscule comprise", str(retour))
    verifier(lecture.charger(txt)["paragraphes"][0]["locuteur"] == "Alice",
             "la relecture montre le nouveau nom")
    verifier(lecture.annuler_correction(txt).get("ok") and txt.read_text(encoding="utf-8") == avant,
             "le renommage s'annule comme une correction")
    verifier(relecture.renommer_locuteur(txt, "Locuteur 1", "1 : x").get("code") == "nom_invalide",
             "un nom qui ne se relirait pas depuis le fichier est refusé")

    retour = relecture.enregistrer_export(txt, ".md", "# Essai\n")
    verifier(retour.get("ok") and Path(retour["chemin"]).read_text(encoding="utf-8") == "# Essai\n"
             and Path(retour["chemin"]).parent == txt.parent,
             "l'export Markdown s'écrit à côté de la transcription", str(retour))
    second = relecture.enregistrer_export(txt, ".md", "# Autre\n")
    verifier(second.get("ok") and second["chemin"] != retour["chemin"], "un export n'en écrase jamais un autre")
    verifier(relecture.enregistrer_export(txt, ".txt", "x").get("code") == "format_refuse",
             "un export ne peut pas créer une seconde transcription .txt")


# ---------------------------------------------------------------------------
# Règle d'or sur une réunion longue : écran, fichier, compagnon, sous-titres
# ---------------------------------------------------------------------------

#: Paires de segments posées exprès : chaque correction ci-dessous chevauche
#: la frontière entre les deux.
_PAIRES = [
    ("Bon, alors,", "on commence le comité."),
    ("Alors du coup, pour moi,", "pour ma part, c'est clair."),
    ("On parle de la politique,", "d'emploi. On verra bien."),
    ("Le rôle de", "l'héros du film reste flou."),
    ("Bref, c'est", "peut-être vrai, ou pas."),
]
_FIN = "Merci à tous, à la semaine prochaine."

_PHRASES = [
    "On reprend le point sur le budget de l'année prochaine.",
    "Il faut qu'on en reparle avec la direction avant vendredi.",
    "Le serveur de test redémarre encore, c'est-à-dire trois fois par jour.",
    "J'ai vu l'équipe d'exploitation hier, elle est d'accord.",
    "Peut-être qu'on peut décaler la mise en production d'une semaine ?",
    "Aujourd'hui, le ticket est ouvert depuis vingt-deux jours.",
    "Qu'est-ce qu'on fait des anciens comptes, on les archive ?",
    "On garde l'ordinateur portable pour les astreintes.",
    "L'audit de sécurité arrive en mars, il faut s'y préparer.",
    "D'accord, je note : relance du fournisseur lundi matin.",
]


def reunion_longue(nb_mots: int = 15000) -> list[Segment]:
    """Une réunion de trois voix, environ quinze mille mots, avec les paires piégées dedans."""
    import random

    hasard = random.Random(7)
    segments: list[Segment] = []
    debut = 0.0
    mots = 0
    paires = list(_PAIRES)
    locuteur = "Locuteur 1"
    while mots < nb_mots:
        if hasard.random() < 0.08:
            locuteur = f"Locuteur {hasard.randint(1, 3)}"
        if paires and (not segments or hasard.random() < 0.004 * (len(segments) > 50)):
            textes = paires.pop(0)
        else:
            phrase = hasard.choice(_PHRASES).split()
            coupe = hasard.randint(3, max(3, len(phrase) - 2))
            textes = (" ".join(phrase[:coupe]), " ".join(phrase[coupe:]))
        for texte in textes:
            fin = debut + 0.45 * len(texte.split())
            segments.append(segment(debut, fin, jetons(texte, p=0.4 + 0.6 * hasard.random()), locuteur))
            mots += len(texte.split())
            debut = fin + (2.0 if hasard.random() < 0.05 else 0.3)
    for textes in paires:
        for texte in textes:
            fin = debut + 2.0
            segments.append(segment(debut, fin, jetons(texte), locuteur))
            debut = fin + 0.3
    segments.append(segment(debut, debut + 3.0, jetons(_FIN), locuteur))
    return segments


def egalite_ecran_fichier(txt: Path) -> str:
    """Écart entre ce que la vue affiche et le corps du fichier, ou chaîne vide."""
    import re

    vue = lecture.charger(txt)
    corps = lecture.separer_entete(txt.read_text(encoding="utf-8"))[1].strip()
    corps = re.sub(r"(?m)^\[\d\d:\d\d:\d\d\] ", "", corps)
    affiche = "\n\n".join((f"{p['locuteur']} : " if p.get("locuteur") else "") + texte_affiche(p)
                          for p in vue["paragraphes"])
    if affiche == corps:
        return ""
    i = next((n for n in range(min(len(affiche), len(corps))) if affiche[n] != corps[n]),
             min(len(affiche), len(corps)))
    return f"au caractère {i} : écran {affiche[max(0, i - 30):i + 30]!r}, fichier {corps[max(0, i - 30):i + 30]!r}"


def essai_reunion_longue(base: Path) -> None:
    from app import compagnon, relecture

    titre("Règle d'or : corrections à cheval sur deux segments, réunion de 15 000 mots")
    dossier = base / "longue"
    dossier.mkdir()
    segments = reunion_longue()
    txt = ecrire(dossier, segments, {"txt": True, "srt": True, "vtt": True},
                 details={"nb_locuteurs": 3, "duree": 6000.0})
    avant = {s: txt.with_suffix(s).read_text(encoding="utf-8") for s in (".txt", ".json", ".srt", ".vtt")}
    corps = lecture.separer_entete(avant[".txt"])[1]
    verifier(len(corps.split()) >= 15000 and egalite_ecran_fichier(txt) == "",
             "réunion longue : l'écran est le fichier à l'ouverture", f"{len(corps.split())} mots")

    controler = getattr(lecture, "controler", None)
    corrections = [
        ("Bon, alors, on commence", "Bon, on commence", "début du fichier, à cheval"),
        ("pour moi, pour ma part,", "pour ma part,", "à cheval sur deux segments"),
        ("politique, d'emploi.", "politique d'emploi", "à cheval, le point retiré"),
        ("de l'héros", "du héros", "à cheval, apostrophe"),
        ("c'est peut-être", "c'est sans doute", "à cheval, trait d'union"),
        ("à la semaine prochaine.", "à mardi.", "fin du fichier"),
    ]
    for source, cible, cas in corrections:
        vue = relecture.occurrences(txt, source, cible)
        retour = relecture.corriger(txt, source, cible, "tous") if vue.get("ok") else vue
        ecart = egalite_ecran_fichier(txt)
        verifier(retour.get("ok") is True and ecart == "", f"correction {cas} : l'écran suit le fichier",
                 ecart or str(retour)[:160])
        if controler:
            verifier(controler(txt) == "", f"correction {cas} : contrôle après écriture", controler(txt))
    texte = lecture.separer_entete(txt.read_text(encoding="utf-8"))[1]
    verifier(texte.startswith("Locuteur 1 : Bon, on commence le comité.") and texte.rstrip().endswith("à mardi.")
             and "pour moi, pour ma part" not in texte and "du héros" in texte,
             "les corrections à cheval sont dans le fichier, du premier au dernier mot")

    donnees = compagnon.lire(txt)
    situes = lecture.situer(lecture.separer_entete(txt.read_text(encoding="utf-8"))[1], donnees["segments"]) \
        if hasattr(lecture, "situer") else None
    verifier(situes is not None, "après les corrections à cheval, chaque segment reste situé dans le fichier")

    # Corrections ciblées après coup : c'est là que la relecture refusait tout.
    for n in range(4):
        vue = relecture.occurrences(txt, "budget", "Budget")
        retour = relecture.corriger(txt, "budget", "Budget", [n * 7]) if vue.get("ok") else vue
        verifier(retour.get("ok") is True and egalite_ecran_fichier(txt) == "",
                 f"correction ciblée {n + 1} après les corrections à cheval", str(retour)[:160])
    srt = txt.with_suffix(".srt").read_text(encoding="utf-8")
    verifier("pour moi, pour ma part" not in srt and "à mardi." in srt and "Budget" in srt,
             "les sous-titres suivent les corrections")
    verifier(lecture.charger(txt)["paragraphes"][0]["texte"].startswith("Bon, on commence"),
             "le premier paragraphe affiché porte la correction de début de fichier")

    # Une écriture qui romprait la règle est annulée et dite.
    if controler:
        original = lecture.situer
        try:
            lecture.situer = lambda corps, segs: None if "PIÈGE" in corps else original(corps, segs)
            retour = relecture.corriger(txt, "Budget", "PIÈGE", [0])
        finally:
            lecture.situer = original
        verifier(retour.get("ok") is False and retour.get("code") == "ecart"
                 and "PIÈGE" not in txt.read_text(encoding="utf-8") and controler(txt) == "",
                 "une écriture qui romprait l'égalité est refusée, les fichiers restent intacts", str(retour))


def essai_selection_exacte(base: Path) -> None:
    """La correction « ici » vise l'endroit sélectionné à l'écran, jamais un autre."""
    from app import relecture

    titre("Sélection : un morceau de mot ou une apostrophe ne corrige jamais ailleurs")
    dossier = base / "exacte"
    dossier.mkdir()
    txt = ecrire(dossier, [
        segment(0.0, 4.0, jetons("On garde l'ordinateur pour les astreintes.")),
        segment(4.5, 9.0, jetons("Mon ordi est en panne, tu t'appelles pas Paul ?")),
    ])
    vue = lecture.charger(txt)
    texte = vue["paragraphes"][0]["texte"]
    debut = texte.index("ordinateur")
    position = {"k": 0, "debut": debut, "fin": debut + 4}
    apercu = relecture.occurrences(txt, "ordi", "PC", texte[:debut], texte[debut + 4:], position)
    ici = next((x for x in apercu.get("extraits", []) if x["rang"] == apercu.get("choisie")), {})
    verifier(apercu.get("ok") and apercu["nombre"] == 2 and ici.get("apres", "").startswith("nateur"),
             "« ordi » pris dans « ordinateur » : l'endroit « ici » est celui de la sélection", str(apercu)[:220])
    retour = relecture.corriger(txt, "ordi", "PC", [apercu["choisie"]], position=position)
    corps = lecture.separer_entete(txt.read_text(encoding="utf-8"))[1]
    verifier(retour.get("ok") and "l'PCnateur" in corps and "Mon ordi est" in corps
             and egalite_ecran_fichier(txt) == "",
             "seul le mot sélectionné change, l'autre « ordi » reste tel quel", corps[:120])
    lecture.annuler_correction(txt)

    sans_position = relecture.occurrences(txt, "ordi", "PC", texte[:debut], texte[debut + 4:])
    verifier(sans_position.get("ok") and sans_position.get("choisie") == -1,
             "sans position, un endroit dont le contexte ne concorde pas n'est jamais « ici »",
             str(sans_position)[:200])

    second = lecture.charger(txt)["paragraphes"][0]["texte"]
    debut = second.index("'appelles")
    position = {"k": 0, "debut": debut, "fin": debut + len("'appelles pas")}
    apercu = relecture.occurrences(txt, "'appelles pas", "'appelais pas", position=position)
    retour = relecture.corriger(txt, "'appelles pas", "'appelais pas", [apercu.get("choisie", -1)],
                                position=position)
    verifier(retour.get("ok") and "tu t'appelais pas Paul" in txt.read_text(encoding="utf-8")
             and egalite_ecran_fichier(txt) == "",
             "une sélection qui commence à l'apostrophe se corrige à sa place", str(retour)[:200])
    perimee = relecture.occurrences(txt, "Mon", "Ton", position={"k": 0, "debut": 0, "fin": 9})
    verifier(perimee.get("ok") is True and perimee.get("choisie") == -1,
             "une position qui ne désigne plus la sélection est ignorée")


def essai_modifie_dehors(base: Path) -> None:
    """Un .txt retouché dans un éditeur : relu, dit, compagnon recalé, exports du même texte."""
    from app import compagnon, relecture

    titre("Fichier retouché hors de l'application : relu, dit, recalé")
    dossier = base / "dehors"
    dossier.mkdir()
    txt = ecrire(dossier, reunion_longue(3000), {"txt": True, "srt": True},
                 details={"nb_locuteurs": 3})
    empreinte_avant = lecture.empreinte(txt) if hasattr(lecture, "empreinte") else ""
    contenu = txt.read_text(encoding="utf-8")
    retouche = (contenu.replace("pour moi, pour ma part,", "pour ma part, franchement,", 1)
                .replace("l'héros du film", "le héros du film", 1)
                .replace("c'est clair.", "c'est clair.\n\nAjout : une phrase écrite à la main.", 1))
    txt.write_text(retouche, encoding="utf-8")

    vue = lecture.charger(txt)
    verifier(egalite_ecran_fichier(txt) == "", "l'écran montre le fichier retouché, mot pour mot",
             egalite_ecran_fichier(txt))
    verifier(bool(vue.get("message")) and "modifié hors de Scribouille" in vue["message"],
             "la retouche est dite à l'ouverture", vue.get("message", ""))
    verifier(vue.get("compagnon") is True and vue["statistiques"]["mots"] > 0,
             "la confiance des mots inchangés est gardée", str(vue["statistiques"]))
    ia = lecture.texte_pour_ia(txt)["texte"]
    verifier("pour ma part, franchement," in ia and "Ajout : une phrase écrite à la main." in ia,
             "« Copier pour l'IA » part du même texte que l'écran")
    verifier(vue.get("empreinte") and vue["empreinte"] != empreinte_avant,
             "l'empreinte du fichier change avec la retouche")

    lecture.charger(txt, persister=True) if "persister" in lecture.charger.__code__.co_varnames else None
    controler = getattr(lecture, "controler", lambda _t: "absent")
    verifier(controler(txt) == "" and lecture.charger(txt).get("message", "") == "",
             "le compagnon recalé est écrit une fois : le fichier se rouvre sans avis", controler(txt))
    retour = relecture.corriger(txt, "franchement", "vraiment", "tous")
    verifier(retour.get("ok") and egalite_ecran_fichier(txt) == "" and controler(txt) == "",
             "une correction après la retouche garde l'écran égal au fichier", str(retour)[:160])

    perimee = lecture.charger(txt)["empreinte"]
    txt.write_text(txt.read_text(encoding="utf-8").replace("vraiment", "sincèrement", 1), encoding="utf-8")
    refus = relecture.corriger(txt, "budget", "Budget", [0], empreinte=perimee)
    verifier(refus.get("ok") is False and refus.get("code") == "modifie_dehors"
             and "Budget" not in lecture.separer_entete(txt.read_text(encoding="utf-8"))[1],
             "une écriture lancée sur un fichier changé entre-temps est refusée, rien n'est écrit", str(refus))
    donnees = compagnon.lire(txt)
    verifier(donnees is not None, "le compagnon reste lisible après tout cela")


def essai_annulation_profonde(base: Path) -> None:
    """Annuler remonte cran par cran, survit à la fermeture, et l'original reste disponible."""
    import importlib

    from app import relecture

    titre("Annulation : plusieurs niveaux, gardés sur le disque, original conservé")
    dossier = base / "annulation"
    dossier.mkdir()
    txt = ecrire(dossier, reunion_sans_locuteurs(), {"txt": True, "srt": True})
    etats = [{s: txt.with_suffix(s).read_bytes() for s in (".txt", ".json", ".srt")}]
    for source, cible in (("budget", "Budget"), ("printemps", "Printemps"), ("vendredi", "Vendredi")):
        relecture.corriger(txt, source, cible, "tous")
        etats.append({s: txt.with_suffix(s).read_bytes() for s in (".txt", ".json", ".srt")})
    niveaux = getattr(lecture, "niveaux_annulables", lambda _t: 1)(txt)
    verifier(niveaux == 3, "trois corrections, trois niveaux d'annulation", str(niveaux))

    # Le module est rechargé : rien ne vient de la mémoire de la session.
    dossier_historique = lecture.DOSSIER_HISTORIQUE if hasattr(lecture, "DOSSIER_HISTORIQUE") else None
    importlib.reload(lecture)
    if dossier_historique is not None:
        lecture.DOSSIER_HISTORIQUE = dossier_historique
    for rang in (2, 1, 0):
        retour = lecture.annuler_correction(txt)
        actuel = {s: txt.with_suffix(s).read_bytes() for s in (".txt", ".json", ".srt")}
        verifier(retour.get("ok") is True and actuel == etats[rang],
                 f"annuler remonte d'un cran, à l'octet près (état {rang})", retour.get("message", ""))
    verifier(lecture.annuler_correction(txt).get("message") == langues.t("lect.annulation.aucune"),
             "au-delà : « Rien à annuler. »")

    relecture.corriger(txt, "budget", "BUDGET", "tous")
    relecture.corriger(txt, "congés", "vacances", "tous")
    revenir = getattr(lecture, "revenir_original", None)
    retour = revenir(txt) if revenir else {}
    verifier(retour.get("ok") is True and txt.read_bytes() == etats[0][".txt"]
             and txt.with_suffix(".json").read_bytes() == etats[0][".json"],
             "revenir au texte d'origine remet les fichiers d'avant toute modification", str(retour))
    verifier(lecture.annuler_correction(txt).get("ok") is True
             and "vacances" in txt.read_text(encoding="utf-8"),
             "revenir à l'original s'annule comme le reste")
    verifier(lecture.controler(txt) == "", "après tout cela, l'écran est toujours le fichier")


def essai_vocabulaire_sur_demande(base: Path) -> None:
    """Une correction ne nourrit le vocabulaire que si l'on coche « Mémoriser »."""
    from app import relecture, vocabulaire_v2

    titre("Vocabulaire : une correction n'apprend rien sans qu'on le demande")
    dossier = base / "sur-demande"
    dossier.mkdir()
    personnel = vocabulaire_v2.FICHIER_PERSONNEL
    vocabulaire_v2.FICHIER_PERSONNEL = dossier / "vocabulaire.toml"
    try:
        txt = ecrire(dossier, [segment(0.0, 4.0, jetons("On ouvre gitlab, puis le serveur jenkins."))])
        for source, cible in (("gitlab", "GitLab"), ("le serveur", "le serveur de test")):
            relecture.corriger(txt, source, cible, "tous")
        verifier(not vocabulaire_v2.FICHIER_PERSONNEL.exists(),
                 "deux corrections sans « Mémoriser » : aucune proposition déposée au vocabulaire")
        retour = relecture.corriger(txt, "jenkins", "Jenkins", "tous", ajouter_regle=True)
        verifier(retour.get("regle_ajoutee") is True,
                 "avec « Mémoriser », la correction est retenue pour les transcriptions suivantes",
                 str(retour)[:160])
        lecture.annuler_correction(txt)
    finally:
        vocabulaire_v2.FICHIER_PERSONNEL = personnel


def essai_position_relecture(base: Path) -> None:
    titre("Relecture : la position est retrouvée d'une ouverture à l'autre")
    (base / "position").mkdir()
    txt = ecrire(base / "position", [segment(0.0, 4.0, jetons("Une phrase pour se situer."))])
    memoriser = getattr(lecture, "memoriser_position", None)
    verifier(memoriser is not None and memoriser(txt, 754.36, 2400) is True
             and lecture.position(txt)["t"] == 754.4 and lecture.position(txt)["haut"] == 2400,
             "instant d'écoute et défilement gardés pour la prochaine ouverture")


def essai_passage_libre(base: Path) -> None:
    """Réécrire ou supprimer un passage : même règle d'égalité, même annulation."""
    titre("Passage réécrit ou supprimé : l'écran reste le fichier")
    dossier = base / "passage"
    dossier.mkdir()
    txt = ecrire(dossier, reunion_longue(2000), {"txt": True, "srt": True}, details={"nb_locuteurs": 3})
    editer = getattr(lecture, "editer_passage", None)
    if editer is None:
        verifier(False, "la relecture sait réécrire un passage")
        return
    avant = txt.read_bytes()
    vue = lecture.charger(txt)
    k = next(n for n, p in enumerate(vue["paragraphes"]) if "pour moi, pour ma part," in p["texte"])
    texte = vue["paragraphes"][k]["texte"]
    debut = texte.index("pour moi, pour ma part,")
    fin = debut + len("pour moi, pour ma part, c'est clair.")
    retour = editer(txt, k, debut, fin, texte[debut:fin], "  à mon avis, rien n'est clair  ")
    verifier(retour.get("ok") and "à mon avis, rien n'est clair" in txt.read_text(encoding="utf-8")
             and egalite_ecran_fichier(txt) == "" and lecture.controler(txt) == "",
             "une phrase réécrite à cheval sur deux segments : écran, fichier, compagnon égaux",
             str(retour)[:160])
    vue = lecture.charger(txt)
    long_texte = vue["paragraphes"][1]["texte"]
    retour = editer(txt, 1, 0, 120, long_texte[:120], "")
    verifier(retour.get("ok") and egalite_ecran_fichier(txt) == "" and lecture.controler(txt) == ""
             and lecture.charger(txt)["paragraphes"][1]["texte"] == long_texte[120:].strip(),
             "120 caractères supprimés d'un coup : pas de limite à 80, l'écran suit", str(retour)[:160])
    nb = len(vue["paragraphes"])
    entier = vue["paragraphes"][2]["texte"]
    retour = editer(txt, 2, 0, len(entier), entier, "")
    vue = lecture.charger(txt)
    verifier(retour.get("ok") and len(vue["paragraphes"]) == nb - 1 and egalite_ecran_fichier(txt) == ""
             and lecture.controler(txt) == "",
             "un paragraphe entier supprimé disparaît, avec son locuteur", str(retour)[:160])
    refus = editer(txt, 0, 0, 5, "pas ça", "x")
    verifier(refus.get("ok") is False and refus.get("code") == "introuvable",
             "un passage qui ne correspond plus à l'écran n'est pas écrit", str(refus))
    for _ in range(3):
        lecture.annuler_correction(txt)
    verifier(txt.read_bytes() == avant, "trois Ctrl+Z rendent le fichier d'origine à l'octet près")


def principal() -> int:
    print(f"Vérification du parcours de l'utilisateur\n{'=' * 42}")
    with tempfile.TemporaryDirectory(prefix="scribouille-parcours-") as brut:
        base = Path(brut)
        # Les règles apprises et les propositions du vocabulaire vont dans des
        # fichiers jetables, jamais dans ceux de l'utilisateur.
        from app import vocabulaire_v2

        chemins.FICHIER_CORRECTIONS = base / "corrections.txt"
        lecture.DOSSIER_HISTORIQUE = base / "historique-relecture"
        lecture.FICHIER_POSITIONS = base / "relecture-positions.json"
        vocabulaire_v2.FICHIER_PERSONNEL = base / "vocabulaire.toml"
        essai_entete_apres_correction(base)
        essai_vue_egale_fichier(base)
        essai_casse_et_doublons(base)
        essai_apercu_et_annulation(base)
        essai_moteur_sans_confiance(base)
        essai_ecoute(base)
        essai_fichiers_produits(base)
        essai_une_seule_verite(base)
        essai_voix_non_installees(base)
        essai_retour_pendant_calcul(base)
        essai_file_apres_arret(base)
        essai_relecture_ciblee(base)
        essai_reunion_longue(base)
        essai_selection_exacte(base)
        essai_modifie_dehors(base)
        essai_annulation_profonde(base)
        essai_vocabulaire_sur_demande(base)
        essai_passage_libre(base)
        essai_position_relecture(base)
        essai_accessibilite()
        essai_ecrans()

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
