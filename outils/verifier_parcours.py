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


# ---------------------------------------------------------------------------
# File d'attente
# ---------------------------------------------------------------------------

class _MoteurInerte:
    """Moteur de remplacement : la file n'en attend que la libération."""

    cle_calcul = "cpu"
    sur_puce = False

    def liberer(self) -> None:
        pass


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


def principal() -> int:
    print(f"Vérification du parcours de l'utilisateur\n{'=' * 42}")
    with tempfile.TemporaryDirectory(prefix="scribouille-parcours-") as brut:
        base = Path(brut)
        # Les règles apprises vont dans un fichier jetable, jamais dans celui
        # de l'utilisateur.
        chemins.FICHIER_CORRECTIONS = base / "corrections.txt"
        essai_entete_apres_correction(base)
        essai_vue_egale_fichier(base)
        essai_casse_et_doublons(base)
        essai_apercu_et_annulation(base)
        essai_file_apres_arret(base)

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
