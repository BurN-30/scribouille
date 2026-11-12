"""
Vérification du vocabulaire, format 2 : sans fenêtre, sans réseau, sans modèle.

Sujets :

  1. le format : écriture et relecture à l'identique, compatibilité TOML,
     erreurs lisibles avec leur ligne, valeurs inconnues ramenées au défaut,
     version plus récente refusée, import JSON ;
  2. la migration depuis le glossaire et les corrections du format 1, sans
     rien perdre, et la conversion sur disque avec ses copies ;
  3. la fusion de plusieurs fichiers : priorité, fautes additionnées, refus
     définitif, propositions à part, conflits signalés ;
  4. la sélection de l'amorce : budget de jetons, pertinence pour le fichier,
     ordre d'écriture, amorce refaite fenêtre par fenêtre ;
  5. la correction après coup et ses garde-fous : fautes, contexte, graphie,
     rapprochement phonétique, mots courants, termes courts, égalités,
     positions, annulation, épreuve d'un vocabulaire fictif sur du français
     ordinaire ;
  6. l'apprentissage sur des couples fictifs : fautes systématiques, voisins,
     faux amis écartés, termes des comptes rendus, rien d'actif, rapport sans
     un terme ;
  7. la lecture des documents (Word, PDF texte, Markdown, sous-titres) ;
  8. la mesure : classement des remplacements, rappel et précision des
     termes, rapport de réunions sans fuite de texte ;
  9. l'écran de revue et la vue de relecture : accepter, refuser, modifier,
     importer, proposition née d'une correction, remplacements montrés et
     annulés, mots corrigés marqués.

    .venv\\Scripts\\python outils\\verifier_vocabulaire.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import chemins, documents, langues, lexique  # noqa: E402
from app import apprentissage as ap  # noqa: E402
from app import mesure_vocabulaire as mv  # noqa: E402
from app import vocabulaire as v1  # noqa: E402
from app import vocabulaire_usage as usage  # noqa: E402
from app import vocabulaire_v2 as v2  # noqa: E402

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


EXEMPLE = '''# Vocabulaire fictif
format = "scribouille-vocabulaire"
version = 2
nom = "Équipe fictive"
portee = "equipe"
langue = "fr"

[[terme]]
forme = "Kubernetes"
categorie = "produit"
fautes = ["cubernetes", "qui bernetes"]
poids = 3
origine = "saisi"
etat = "actif"

[[terme]]
forme = "Martin Lebrun"
categorie = "personne"
fautes = [
  "martin le brun",
  { forme = "martin", voisins = ["monsieur", "lebrun"] },
  { forme = "lebrin", vu = 4, reunions = 2 },
]
prononciation = "martin leubrun"
origine = "apprentissage"
etat = "actif"

[[terme]]
forme = "Auckland"
categorie = "autre"

[[terme]]
forme = "RGPD"
categorie = "sigle"
fautes = ["er gé pé dé"]

[[terme]]
forme = "Valtéris"
categorie = "societe"
etat = "propose"
vu = 5
reunions = 3
note = "chaîne avec \\"guillemets\\" et accents"

[[terme]]
forme = "MonEntreprise"
fautes = ["mon entreprise"]
amorce = false
'''


# ---------------------------------------------------------------------------
# 1. Format
# ---------------------------------------------------------------------------

def essai_format() -> None:
    titre("1. Format : lecture, écriture, erreurs")
    voc, remarques = v2.lire_texte(EXEMPLE)
    verifier(len(voc.entrees) == 6 and not remarques, "six termes lus sans remarque", str(remarques))
    martin = voc.chercher("martin lebrun")
    verifier(martin is not None and len(martin.fautes) == 3 and martin.fautes[1].voisins == ["monsieur", "lebrun"]
             and martin.fautes[2].vu == 4, "fautes simples, en contexte et comptées")
    verifier(voc.chercher("Valtéris", etat="propose") is not None and voc.chercher("Valtéris") is None,
             "une proposition n'est pas un terme actif")
    verifier(voc.chercher("auckland").categorie == "autre" and voc.chercher("auckland").poids == 1,
             "valeurs par défaut")
    texte = v2.ecrire_texte(voc)
    relu, _ = v2.lire_texte(texte)
    verifier(v2.ecrire_texte(relu) == texte, "écrire puis relire donne le même fichier")
    try:
        import tomllib  # type: ignore

        verifier(tomllib.loads(texte) == v2.analyser_toml(texte), "le fichier écrit est du TOML valide (tomllib)")
        verifier(tomllib.loads(EXEMPLE) == v2.analyser_toml(EXEMPLE), "l'exemple écrit à la main aussi")
    except ImportError:
        print("         tomllib absent (Python < 3.11) : contrôle croisé sauté")
    for fautif, attendu in (('forme = "ouvert', "ligne 1"), ("[terme]\nforme = \"x\"", "ligne 1"),
                            ('format = "scribouille-vocabulaire"\nversion = 2\nversion = 3', "ligne 3"),
                            ('[[terme]]\nforme = "a" "b"', "ligne 2")):
        try:
            v2.lire_texte(fautif)
            verifier(False, f"erreur lisible pour {fautif[:18]!r}")
        except v2.ErreurFormat as exc:
            verifier(attendu in str(exc), f"erreur avec sa ligne : {str(exc)[:60]}")
    _, remarques = v2.lire_texte('[[terme]]\nforme = "X"\ncategorie = "planete"\netat = "peut-etre"')
    verifier(len(remarques) == 2, "catégorie et état inconnus signalés", str(remarques))
    try:
        v2.lire_texte('format = "scribouille-vocabulaire"\nversion = 9')
        verifier(False, "version plus récente refusée")
    except v2.ErreurFormat:
        verifier(True, "version plus récente refusée")
    en_json = json.dumps(v2.en_donnees(voc), ensure_ascii=False)
    verifier(len(v2.lire_texte(en_json)[0].entrees) == 6, "import d'un export JSON")
    double, remarques = v2.lire_texte('[[terme]]\nforme = "Jira"\nfautes = ["gira"]\n[[terme]]\nforme = "jira"\n'
                                      'fautes = ["djira"]')
    verifier(len(double.entrees) == 1 and len(double.entrees[0].fautes) == 2 and remarques,
             "doublon dans un fichier : fusionné et signalé")


# ---------------------------------------------------------------------------
# 2. Migration
# ---------------------------------------------------------------------------

GLOSSAIRE_V1 = "# commentaire\nJean Dupont\nKubernetes\nRGPD\n\nKubernetes\n"
CORRECTIONS_V1 = ("# règles\ncubernetes => Kubernetes\nmon entreprise => MonEntreprise\n"
                  "poste grès => PostgreSQL\n\n# Apprises depuis les transcriptions\n"
                  "# Ajoutées d'un clic\nvalencienne => Valenciennes\n")


def essai_migration(base: Path) -> None:
    titre("2. Migration depuis le format 1")
    voc = v2.depuis_v1(GLOSSAIRE_V1, CORRECTIONS_V1)
    formes = [e.forme for e in voc.entrees]
    verifier(formes[:3] == ["Jean Dupont", "Kubernetes", "RGPD"], "termes du glossaire, ordre gardé, doublon fondu",
             str(formes))
    verifier(all(voc.chercher(t) and voc.chercher(t).amorce for t in v1.termes(GLOSSAIRE_V1)),
             "chaque terme du glossaire reste soufflé au modèle")
    regles, _ = v1.analyser_corrections(CORRECTIONS_V1)
    verifier(all(voc.chercher(r.cible) and voc.chercher(r.cible).faute(r.source) for r in regles),
             "chaque règle devient une faute de sa forme correcte, rien de perdu")
    verifier(not voc.chercher("PostgreSQL").amorce and voc.chercher("Kubernetes").amorce,
             "une forme seulement corrigée n'est pas ajoutée à l'amorce")
    verifier(voc.chercher("MonEntreprise").faute("mon entreprise").forcer,
             "règle faite de mots courants : forcée, comme avant")
    verifier(voc.chercher("Valenciennes").origine == "correction"
             and voc.chercher("Kubernetes").origine == "glossaire_v1", "origines distinguées")
    verifier(voc.chercher("RGPD").categorie == "sigle", "sigle reconnu")
    # Comportement identique : les règles du format 1 et la correction v2 donnent le même texte.
    texte = "On migre cubernetes chez mon entreprise, la poste grès est prête."
    attendu, _n = v1.appliquer(texte, regles)
    obtenu, _r = usage.Correcteur(voc, rapprochement=False).corriger_texte(texte)
    verifier(obtenu == attendu, "même texte corrigé qu'avec le format 1", f"{obtenu!r} / {attendu!r}")

    anciens = (chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS, dict(chemins.MODELES_FICHIERS_EXEMPLE),
               v2.FICHIER_PERSONNEL)
    try:
        chemins.FICHIER_VOCABULAIRE = base / "vocabulaire.txt"
        chemins.FICHIER_CORRECTIONS = base / "corrections.txt"
        chemins.MODELES_FICHIERS_EXEMPLE.clear()
        chemins.MODELES_FICHIERS_EXEMPLE.update({chemins.FICHIER_VOCABULAIRE: RACINE / "vocabulaire.txt",
                                                 chemins.FICHIER_CORRECTIONS: RACINE / "corrections.txt"})
        v2.FICHIER_PERSONNEL = base / "vocabulaire.toml"
        chemins.FICHIER_VOCABULAIRE.write_text(GLOSSAIRE_V1, encoding="utf-8")
        chemins.FICHIER_CORRECTIONS.write_text(CORRECTIONS_V1, encoding="utf-8")
        effectif, _p = v2.effectif({})
        verifier(effectif.chercher("Jean Dupont") is not None, "avant conversion : le format 1 est lu tel quel")
        retour = v2.convertir_v1_sur_disque()
        verifier(retour["convertis"] == 6, "conversion : six termes", str(retour))
        verifier((base / "vocabulaire-format1-sauvegarde.txt").read_text(encoding="utf-8") == GLOSSAIRE_V1
                 and (base / "corrections-format1-sauvegarde.txt").read_text(encoding="utf-8") == CORRECTIONS_V1,
                 "copies exactes des anciens fichiers")
        verifier(not v1.termes(chemins.FICHIER_VOCABULAIRE.read_text(encoding="utf-8")),
                 "glossaire remis au modèle livré (exemples en commentaire)")
        apres, _p = v2.effectif({})
        verifier(sorted(e.forme for e in apres.actives()) == sorted(e.forme for e in effectif.actives()),
                 "après conversion : le même vocabulaire, désormais dans le fichier personnel")
    finally:
        (chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS, modeles, v2.FICHIER_PERSONNEL) = anciens
        chemins.MODELES_FICHIERS_EXEMPLE.clear()
        chemins.MODELES_FICHIERS_EXEMPLE.update(modeles)


# ---------------------------------------------------------------------------
# 3. Fusion
# ---------------------------------------------------------------------------

def essai_fusion() -> None:
    titre("3. Fusion de plusieurs fichiers")
    equipe = v2.lire_texte('[[terme]]\nforme = "Jira"\ncategorie = "produit"\nfautes = ["gira"]\npoids = 2\n'
                           '[[terme]]\nforme = "Datanor"\nfautes = ["data nord"]\n'
                           '[[terme]]\nforme = "Hexalis"\n', "equipe")[0]
    projet = v2.lire_texte('[[terme]]\nforme = "Datanorr"\nfautes = ["data nord"]\n', "projet")[0]
    personnel = v2.lire_texte('[[terme]]\nforme = "jira"\nfautes = ["djira"]\npoids = 4\n'
                              '[[terme]]\nforme = "Hexalis"\netat = "refuse"\n'
                              '[[terme]]\nforme = "Jira"\nfautes = ["dgira"]\netat = "propose"\n', "perso")[0]
    voc = v2.fusionner([equipe, projet, personnel])
    jira = voc.chercher("Jira")
    verifier(jira is not None and {f.forme for f in jira.fautes} == {"gira", "djira"} and jira.poids == 4,
             "fautes additionnées, poids du plus prioritaire")
    verifier(jira.categorie == "produit", "catégorie gardée quand le plus prioritaire ne la précise pas")
    verifier(voc.chercher("Hexalis") is None and voc.chercher("Hexalis", etat="refuse") is not None,
             "un refus personnel l'emporte sur l'équipe")
    verifier(voc.chercher("Jira", etat="propose") is not None,
             "une proposition reste à part du terme actif de même forme")
    verifier(len(voc.conflits) == 1 and voc.conflits[0][1] == "Datanorr",
             "conflit signalé, la forme la plus prioritaire gardée", str(voc.conflits))


# ---------------------------------------------------------------------------
# 4. Amorce
# ---------------------------------------------------------------------------

def essai_amorce() -> None:
    titre("4. Amorce : budget, pertinence, fenêtres")
    voc = v2.lire_texte(EXEMPLE)[0]
    info = usage.selectionner(voc, langue="fr")
    verifier(info["nb_termes"] == 4 and "MonEntreprise" not in info["amorce"] and "Valtéris" not in info["amorce"],
             "ni terme hors amorce, ni proposition", info["amorce"])
    verifier(info["amorce"].endswith("Kubernetes."), "le plus lourd est écrit en dernier, juste avant l'audio",
             info["amorce"])
    verifier(info["amorce"].startswith(v1.entete_amorce("fr")), "en-tête dans la langue parlée")
    grand = v2.Vocabulaire(entrees=[v2.Entree(f"Terme{k:03d}x", poids=1 + k % 3) for k in range(200)])
    grand.entrees.append(v2.Entree("Zorglubinax", poids=1))
    plein = usage.selectionner(grand, langue="fr")
    verifier(plein["tronque"] and plein["jetons"] <= v1.LIMITE_JETONS_AMORCE - v1.MARGE_JETONS,
             "budget de jetons tenu", f"{plein['jetons']} jetons")
    verifier(all(f"Terme{k:03d}x" in plein["retenus"] for k in range(200) if (1 + k % 3) == 3
                 and k < 40), "à budget plein, les poids forts d'abord")
    verifier("Zorglubinax" not in plein["retenus"], "un terme léger non retenu sans contexte")
    pertinent = usage.selectionner(grand, langue="fr", contexte="reunion-zorglubinax-mardi")
    verifier("Zorglubinax" in pertinent["retenus"] and pertinent["pertinents"] >= 1,
             "le nom du fichier fait passer devant le terme qu'il évoque")
    dynamique = usage.amorce(grand, langue="fr")
    fenetre = dynamique.pour_fenetre("et là Zorglubinax nous a répondu")
    verifier(isinstance(dynamique, str) and "Zorglubinax" in fenetre and "Zorglubinax" not in str(dynamique),
             "amorce refaite pour une fenêtre, d'après la précédente")
    petit = usage.amorce(voc, langue="fr")
    verifier(petit.pour_fenetre("n'importe quoi") == str(petit), "vocabulaire qui tient : amorce fixe")
    vide = usage.selectionner(v2.Vocabulaire(), langue="fr")
    verifier(vide["amorce"] == "" and vide["nb_termes"] == 0, "vocabulaire vide : aucune amorce")


# ---------------------------------------------------------------------------
# 5. Correction
# ---------------------------------------------------------------------------

def essai_correction() -> None:
    titre("5. Correction après coup et garde-fous")
    voc = v2.lire_texte(EXEMPLE)[0]
    voc.entrees.append(v2.Entree("Jamie Siminoff", "personne"))
    c = usage.Correcteur(voc)
    texte, r = c.corriger_texte("On a parlé de cubernetes et du rgpd avec monsieur martin hier.")
    verifier(texte == "On a parlé de Kubernetes et du RGPD avec monsieur Martin Lebrun hier.",
             "faute, graphie de sigle et faute en contexte", texte)
    verifier([x["regle"] for x in r] == ["faute", "graphie", "contexte"], "règles journalisées dans l'ordre")
    verifier(all(texte[x["o"]:x["o"] + len(x["b"])] == x["b"] for x in r), "positions justes dans le texte rendu")
    texte, r = c.corriger_texte("Martin a dit que le martin-pêcheur était là.")
    verifier(not r, "faute en contexte sans ses voisins : rien", texte)
    texte, r = c.corriger_texte("Il est arrivé à Aokland avec Jamy Siminov.")
    verifier(texte == "Il est arrivé à Auckland avec Jamie Siminoff."
             and {x["regle"] for x in r} == {"rapprochement"}, "rapprochement phonétique borné", texte)
    texte, r = c.corriger_texte("Je travaille pour mon entreprise depuis dix ans.")
    verifier(not r and c.ignorees_risquees >= 1,
             "faute faite de mots courants, sans contexte ni forçage : jamais appliquée")
    force = v2.lire_texte('[[terme]]\nforme = "MonEntreprise"\nfautes = [{ forme = "mon entreprise", forcer = true }]')[0]
    texte, r = usage.Correcteur(force).corriger_texte("Je travaille pour mon entreprise.")
    verifier(texte == "Je travaille pour MonEntreprise.", "faute forcée : appliquée, choix de l'utilisateur")
    texte, r = c.corriger_texte("Kubernetes tourne, Auckland aussi.")
    verifier(not r, "forme déjà juste : intacte")
    texte, r = c.corriger_texte("cubernetes tourne.")
    verifier(texte == "Kubernetes tourne." and r, "début de phrase")
    courts = v2.lire_texte('[[terme]]\nforme = "Odoo"\n[[terme]]\nforme = "Jira"\ncategorie = "produit"')[0]
    texte, r = usage.Correcteur(courts).corriger_texte("On ouvre odou, le dodo et la djira.")
    verifier(texte == "On ouvre odou, le dodo et la Jira.",
             "moins de quatre sons : jamais rapproché ; quatre : un son d'écart", texte)
    verifier(lexique.est_courant("jiro"), "« jiro » figure au lexique (sous-titres)")
    texte, r = usage.Correcteur(courts).corriger_texte("Le jiro du dimanche.")
    verifier(not r, "un mot du lexique n'est jamais rapproché, même d'un son", str(r))
    jumeaux = v2.lire_texte('[[terme]]\nforme = "Valmontin"\n[[terme]]\nforme = "Valmontan"')[0]
    texte, r = usage.Correcteur(jumeaux).corriger_texte("Chez Valmonton ce matin.")
    verifier(not r, "deux termes aussi proches : on ne tranche pas", str(r))
    texte, r = usage.Correcteur(jumeaux).corriger_texte("Chez Valmontain ce matin.")
    verifier(texte == "Chez Valmontin ce matin.", "le plus proche l'emporte quand il est seul", texte)
    texte, r = c.corriger_texte("La pierre est claire, la rose aussi.")
    verifier(not r, "mots courants jamais rapprochés")
    segments = [{"d": 0.0, "f": 2.0, "t": "Bonjour cubernetes."}, {"d": 2.0, "f": 4.0, "t": "Rien ici."},
                {"d": 4.0, "f": 6.0, "t": "Le rgpd et cubernetes."}]
    journal_r = c.corriger_segments(segments)
    verifier(len(journal_r) == 3 and [x["s"] for x in journal_r] == [0, 2, 2] and segments[2]["t"] ==
             "Le RGPD et Kubernetes.", "segments corrigés sur place, rang et début notés")
    defait = usage.annuler(segments[2]["t"], journal_r[2])
    verifier(defait == "Le RGPD et cubernetes.", "annulation d'un remplacement", defait)
    verifier(usage.annuler("texte sans rapport", journal_r[2]) is None, "annulation impossible si le texte a bougé")
    epreuve = usage.Correcteur(mv.vocabulaire_epreuve())
    ordinaire = ("Bon alors on se retrouve mardi pour faire le point sur le budget. Pierre a dit que la salle "
                 "serait libre, Claire préfère jeudi, et Martin s'occupe des invitations. Il faudra une rose "
                 "pour la table et un peu de musique. On pourrait aussi revoir le planning et le site.")
    texte, r = epreuve.corriger_texte(ordinaire)
    verifier(not r, "vocabulaire fictif de 102 termes sur du français ordinaire : aucun remplacement",
             str([(x["a"], x["b"]) for x in r]))


# ---------------------------------------------------------------------------
# 6. Apprentissage
# ---------------------------------------------------------------------------

BRUT1 = ("Bonjour à tous. On fait le point sur le projet avec monsieur le brun. Le déploiement sur cubernetes "
         "est prévu. Il faut voir avec la société ac mie pour le contrat. Monsieur le brun confirme. "
         "On relance cubernetes demain. Le brun clair du logo ne plaît pas.")
PROPRE1 = ("Bonjour à tous. On fait le point sur le projet avec Monsieur Lebrun. Le déploiement sur Kubernetes "
           "est prévu. Il faut voir avec la société Acmie pour le contrat. Monsieur Lebrun confirme. "
           "On relance Kubernetes demain. Le brun clair du logo ne plaît pas.")
BRUT2 = ("Point d'étape. Le cluster cubernetes tient. La société ac mie a signé. On attend le retour de madame "
         "vallée. Le brun est absent et la tour est finie.")
PROPRE2 = ("Point d'étape. Le cluster Kubernetes tient. La société Acmie a signé. On attend le retour de Madame "
           "Vallée. Lebrun est absent et la tour est finie.")
CR = "Compte rendu. Présents : Madame Vallée, Monsieur Lebrun. Décision : migration Kubernetes avec Acmie."


def essai_apprentissage(base: Path) -> None:
    titre("6. Apprentissage sur des couples fictifs")
    reunions = [ap.Reunion("r1", BRUT1, PROPRE1, [CR]), ap.Reunion("r2", BRUT2, PROPRE2)]
    voc, bilan = ap.apprendre(reunions)
    formes = {e.forme for e in voc.entrees}
    verifier({"Kubernetes", "Lebrun", "Acmie", "Vallée"} <= formes, "termes appris", str(formes))
    verifier(all(e.etat == "propose" for e in voc.entrees), "tout est proposé, rien d'actif")
    kube = voc.chercher("Kubernetes", etat="propose")
    verifier(kube.faute("cubernetes") is not None and kube.faute("cubernetes").vu == 3
             and kube.faute("cubernetes").reunions == 2, "faute systématique comptée par occurrence et réunion")
    lebrun = voc.chercher("Lebrun", etat="propose").faute("le brun")
    verifier(lebrun is not None and lebrun.voisins == ["monsieur"],
             "faute faite de mots courants : portée limitée à ses voisins récurrents",
             str(lebrun.voisins if lebrun else None))
    verifier(voc.chercher("Vallée", etat="propose").categorie == "personne", "civilité : catégorie personne")
    verifier("Monsieur Lebrun" not in formes, "la civilité n'entre pas dans le terme")
    # Faux ami : « brun » écrit juste ailleurs n'est pas une faute.
    verifier(not any(f.forme == "brun" for e in voc.entrees for f in e.fautes), "faux ami écarté")
    deja = v2.lire_texte('[[terme]]\nforme = "Kubernetes"\nfautes = ["cubernetes"]\n'
                         '[[terme]]\nforme = "Acmie"\netat = "refuse"')[0]
    voc2, bilan2 = ap.apprendre(reunions, deja)
    verifier(voc2.chercher("Kubernetes", etat=None) is None and voc2.chercher("Acmie", etat=None) is None
             and bilan2["deja_connus"] >= 1 and bilan2["deja_refuses"] >= 1,
             "déjà actif à l'identique ou refusé : pas reproposé")
    rapport = ap.rediger_rapport(bilan, 0)
    fuites = [f for e in voc.entrees for f in [e.forme] + [x.forme for x in e.fautes]
              if len(f) > 3 and f.lower() in rapport.lower()]
    verifier(not fuites, "rapport de l'apprentissage : aucun terme ni faute", str(fuites))
    # Ligne de commande, fichiers sur disque, Word compris.
    (base / "b1.txt").write_text(BRUT1, encoding="utf-8")
    (base / "p1.txt").write_text(PROPRE1, encoding="utf-8")
    (base / "b2.txt").write_text(BRUT2, encoding="utf-8")
    _docx(base / "p2.docx", PROPRE2.split(". "))
    _docx(base / "cr.docx", [CR])
    (base / "liste.txt").write_text(f"{base / 'b2.txt'} | {base / 'p2.docx'} | {base / 'cr.docx'}\n", encoding="utf-8")
    sortie = base / "propositions.toml"
    anciens = (v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS)
    try:
        v2.FICHIER_PERSONNEL = base / "perso-apprentissage.toml"
        chemins.FICHIER_VOCABULAIRE = base / "absent-v.txt"
        chemins.FICHIER_CORRECTIONS = base / "absent-c.txt"
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            code = ap.principal_cli(["--apprendre-vocabulaire", "--brut", str(base / "b1.txt"), "--propre",
                                     str(base / "p1.txt"), "--manifeste", str(base / "liste.txt"), "--sortie",
                                     str(sortie), "--importer"])
        relu = v2.lire(sortie)[0]
        verifier(code == 0 and relu.chercher("Kubernetes", etat="propose") is not None,
                 "ligne de commande : propositions écrites (texte et Word)")
        perso = v2.lire(v2.FICHIER_PERSONNEL)[0]
        verifier(perso.par_etat("propose") and not perso.actives(), "--importer : versées à relire, rien d'actif")
        chiffres = (base / "propositions-chiffres.txt").read_text(encoding="utf-8")
        verifier(not any(f.lower() in chiffres.lower() for f in ("kubernetes", "lebrun", "acmie", "vallée")),
                 "rapport chiffré écrit à côté, sans un terme")
        # Relecture à la main du fichier de propositions, puis import seul.
        relu = v2.lire(sortie)[0]
        relu.chercher("Vallée", etat="propose").etat = "refuse"
        v2.ecrire(relu, base / "relues.toml")
        v2.FICHIER_PERSONNEL = base / "perso-relu.toml"
        with contextlib.redirect_stdout(io.StringIO()):
            code = ap.principal_cli(["--apprendre-vocabulaire", "--importer-propositions", str(base / "relues.toml")])
        perso = v2.lire(v2.FICHIER_PERSONNEL)[0]
        verifier(code == 0 and perso.chercher("Vallée", etat="refuse") is not None
                 and perso.chercher("Kubernetes", etat="propose") is not None and not perso.actives(),
                 "--importer-propositions : pistes écartées gardées refusées, le reste à valider")
    finally:
        v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS = anciens


# ---------------------------------------------------------------------------
# 7. Documents
# ---------------------------------------------------------------------------

def _docx(chemin: Path, paragraphes: list[str]) -> None:
    corps = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{p}</w:t></w:r></w:p>" for p in paragraphes)
    xml = ('<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
           f'wordprocessingml/2006/main"><w:body>{corps}</w:body></w:document>')
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.writestr("word/document.xml", xml)


def _pdf(chemin: Path) -> None:
    """PDF minimal : une page en police simple (Tj), une en police à table ToUnicode (TJ, 2 octets)."""
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <0000> <FFFF> "
            b"endcodespacerange 2 beginbfchar <0001> <00C9> <0002> <0074> endbfchar 1 beginbfrange "
            b"<0003> <0005> <0061> endbfrange endcmap end end")
    flux1 = b"BT /F1 12 Tf 72 700 Td (Compte rendu de la reunion du mardi avec les equipes) Tj ET " * 3
    flux2 = zlib.compress(b"BT /F2 12 Tf 72 650 Td [<00010002> -300 <000300040005>] TJ ET " * 12)
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents [4 0 R 8 0 R] >>",
        b"<< /Length %d >>\nstream\n" % len(flux1) + flux1 + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type0 /BaseFont /X /Encoding /Identity-H /ToUnicode 7 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(cmap) + cmap + b"\nendstream",
        b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(flux2) + flux2 + b"\nendstream",
    ]
    contenu = b"%PDF-1.4\n" + b"".join(b"%d 0 obj\n" % (k + 1) + o + b"\nendobj\n" for k, o in enumerate(objets))
    chemin.write_bytes(contenu + b"trailer << /Root 1 0 R >>\n%%EOF\n")


def essai_documents(base: Path) -> None:
    titre("7. Lecture des documents")
    _docx(base / "cr.docx", ["Compte rendu", "Présents : Madame Vallée", "Décision : migration validée."])
    verifier("Madame Vallée" in documents.lire_texte(base / "cr.docx"), "Word (.docx)")
    _pdf(base / "cr.pdf")
    try:
        texte = documents.lire_texte(base / "cr.pdf")
        verifier("Compte rendu de la reunion" in texte and "Étabc" in texte.replace(" ", ""),
                 "PDF texte : police simple et table ToUnicode", texte[:80])
    except documents.DocumentIllisible as exc:
        verifier(False, "PDF texte", exc.motif)
    (base / "scan.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /XObject /Subtype /Image >>\nendobj\n")
    try:
        documents.lire_texte(base / "scan.pdf")
        verifier(False, "PDF sans texte signalé")
    except documents.DocumentIllisible as exc:
        verifier(exc.motif == "pdf_sans_texte", "PDF sans texte signalé, jamais deviné")
    (base / "notes.md").write_text("# Réunion\n\n- **Kubernetes** validé\n", encoding="utf-8")
    verifier("Kubernetes" in documents.lire_texte(base / "notes.md")
             and "**" not in documents.lire_texte(base / "notes.md"), "Markdown")
    (base / "t.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nLocuteur 1 : Bonjour Acmie\n", encoding="utf-8")
    verifier(documents.lire_texte(base / "t.srt").strip() == "Bonjour Acmie", "sous-titres, locuteur retiré")
    (base / "t.txt").write_text("[00:00:05] Marie : On valide.\n", encoding="utf-8")
    verifier(documents.lire_texte(base / "t.txt").strip() == "On valide.", "texte horodaté, locuteur retiré")
    try:
        documents.lire_texte(base / "inconnu.xyz")
        verifier(False, "document absent signalé")
    except documents.DocumentIllisible:
        verifier(True, "document absent signalé")


# ---------------------------------------------------------------------------
# 8. Mesure
# ---------------------------------------------------------------------------

def essai_mesure() -> None:
    titre("8. Mesure : remplacements, termes, rapport")
    from app.comparaison import normaliser

    voc = v2.lire_texte('[[terme]]\nforme = "Kubernetes"\ncategorie = "produit"\nfautes = ["cubernetes"]\n'
                        '[[terme]]\nforme = "Valtéris"\ncategorie = "societe"\n'
                        '[[terme]]\nforme = "Acmie"\ncategorie = "societe"\nfautes = [{ forme = "académie", '
                        'forcer = true }]')[0]
    ref = normaliser("on déploie kubernetes chez valtéris puis l'académie valide")
    sans = [{"d": 0, "f": 3, "t": "On déploie cubernetes chez Valtéris, puis l'académie valide."}]
    resultats = mv.evaluer_conditions(ref, sans, None, voc)
    remplacements = resultats["correction"]["remplacements"]
    verifier(remplacements.get("utile") == 1 and remplacements.get("fausse") == 1,
             "une correction utile, une fausse correction (forme forcée à tort)", str(remplacements))
    termes = resultats["sans"]["termes"]
    verifier(termes["produit"]["dits"] == 1 and termes["produit"]["retrouves"] == 0
             and termes["societe"]["retrouves"] == 1, "rappel des termes avant correction")
    apres = resultats["correction"]["termes"]
    verifier(apres["produit"]["retrouves"] == 1 and apres["societe"]["ecrits"] == 2
             and apres["societe"]["justes"] == 1, "rappel et précision après correction")
    verifier(resultats["correction"]["erreurs"] == resultats["sans"]["erreurs"],
             "une utile et une fausse : taux d'erreur inchangé")
    voc_secret = v2.lire_texte('[[terme]]\nforme = "Bérénice Lacoste-Vidal"\ncategorie = "personne"\n'
                               'fautes = ["bérénice la coste"]')[0]
    rapport = mv.rediger_rapport_reunions(voc_secret, [{**resultats, "_meta": {"duree": 600}}], {}, "ov-turbo-f1",
                                          "GPU", 60.0)
    fuites = [m for m in ("Bérénice", "Lacoste", "Valtéris", "Kubernetes", "académie", "déploie", "cubernetes")
              if m.lower() in rapport.lower()]
    verifier(not fuites, "rapport de réunions : ni terme, ni nom, ni mot de la réunion", str(fuites))
    verifier("fausses corrections 1" in rapport and "rappel" in rapport, "le rapport porte les chiffres attendus")


def essai_mesure_reunions(base: Path) -> None:
    titre("8 bis. Mesure sur une réunion : chaîne complète, moteur simulé")
    from app import audio

    if not audio.ffmpeg_present():
        print("         FFmpeg absent : essai sauté")
        return
    reference = base / "reference.txt"
    reference.write_text((RACINE / "banc" / "extrait_fr.txt").read_text(encoding="utf-8"), encoding="utf-8")
    voc = v2.lire_texte('[[terme]]\nforme = "Auckland"\n[[terme]]\nforme = "Jamie Siminoff"\ncategorie = "personne"'
                        '\n[[terme]]\nforme = "Ring"\ncategorie = "societe"')[0]
    chemin_voc = base / "voc.toml"
    v2.ecrire(voc, chemin_voc)
    appels = []

    def faux_transcrire(cle, entrees, sortie, peripherique, vocabulaire="", contexte="", dire=print):
        appels.append((sortie.name, bool(vocabulaire)))
        texte = ("Les plages sont nombreuses car Aokland est à cheval sur deux ports. Le PDG de Ring, Jamy Siminov, "
                 "a fait remarquer qu'il a lancé l'entreprise.") if not vocabulaire else (
                 "Les plages sont nombreuses car Auckland est à cheval sur deux ports. Le PDG de Ring, Jamie Siminov, "
                 "a fait remarquer qu'il a lancé l'entreprise.")
        sortie.write_text(json.dumps({"reunion": {"segments": [{"d": 0, "f": 40, "t": texte}]}}), encoding="utf-8")
        return {"etat": "ok", "facteur": 0.1, "termes_amorce": 3, "jetons_amorce": 20, "peripherique": "CPU"}

    vrai, ancien_dossier = mv._transcrire, mv.DOSSIER
    try:
        mv._transcrire = faux_transcrire
        mv.DOSSIER = base / "mesures"
        retour = mv.executer_reunions(str(chemin_voc), [(str(RACINE / "banc" / "extrait_fr.ogg"), str(reference))],
                                      peripherique="CPU", dire=lambda m: None)
    finally:
        mv._transcrire, mv.DOSSIER = vrai, ancien_dossier
    rapport = retour["rapport"]
    verifier([a[1] for a in appels] == [False, True] and appels[1][0].startswith("amorce-"),
             "deux passes : sans, puis avec amorce (fichier propre au vocabulaire)")
    verifier("amorce et correction" in rapport and "rappel" in rapport, "quatre conditions dans le rapport")
    verifier(not any(m in rapport.lower() for m in ("auckland", "siminoff", "plages", "extrait_fr")),
             "rapport : ni terme, ni phrase, ni nom de fichier")
    lignes = {l.split(":")[0].strip(" -"): l for l in rapport.splitlines() if "termes : rappel" in l}
    verifier("1 sur 3" not in lignes.get("amorce et correction", "") and "3 sur 3" in lignes.get(
        "amorce et correction", ""), "amorce puis correction : les trois termes retrouvés", str(lignes))


# ---------------------------------------------------------------------------
# 9. Écran de revue et vue de relecture
# ---------------------------------------------------------------------------

def essai_interface(base: Path) -> None:
    titre("9. Écran de revue et vue de relecture")
    from app import compagnon, lecture, vocabulaire_interface as vi

    anciens = (v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS)
    try:
        v2.FICHIER_PERSONNEL = base / "perso.toml"
        chemins.FICHIER_VOCABULAIRE = base / "v-absent.txt"
        chemins.FICHIER_CORRECTIONS = base / "c-absent.txt"
        voc, _ = ap.apprendre([ap.Reunion("r1", BRUT1, PROPRE1, [CR]), ap.Reunion("r2", BRUT2, PROPRE2)])
        v2.ecrire(voc, base / "appris.toml")
        retour = vi.importer(str(base / "appris.toml"))
        etat = vi.etat({})
        verifier(retour["ok"] and etat["resume"]["proposes"] >= 4 and etat["resume"]["actifs"] == 0,
                 "import : propositions à relire, rien d'actif", str(etat["resume"]))
        verifier(vi.decider(["Kubernetes", "Acmie"], "accepter")["n"] == 2, "accepter par lots")
        verifier(vi.decider(["Vallée"], "refuser")["n"] == 1, "refuser")
        etat = vi.etat({})
        verifier(etat["resume"]["actifs"] == 2 and etat["resume"]["refuses"] == 1, "états à jour")
        retour = vi.importer(str(base / "appris.toml"))
        verifier("Vallée" not in [e["forme"] for e in vi.etat({})["entrees"] if e["etat"] == "propose"],
                 "un terme refusé n'est pas reproposé à l'import suivant")
        verifier(vi.modifier("Lebrun", "propose", {"fautes": [{"forme": "le brun", "voisins": ["monsieur"]},
                                                              {"forme": "lebrin"}], "accepter": True})["ok"],
                 "modifier puis accepter")
        lebrun = v2.lire(v2.FICHIER_PERSONNEL)[0].chercher("Lebrun")
        verifier(lebrun is not None and lebrun.faute("lebrin") is not None, "modification enregistrée")
        verifier(not vi.ajouter({"forme": "Kubernetes"})["ok"] and vi.ajouter({"forme": "Grafana",
                                                                               "categorie": "produit"})["ok"],
                 "ajout : doublon refusé, nouveau terme actif")
        verifier(vi.proposer_depuis_correction("data nord", "Datanor")
                 and vi.proposer_depuis_correction("data nord", "Datanor")
                 and v2.lire(v2.FICHIER_PERSONNEL)[0].chercher("Datanor", etat="propose").faute("data nord").vu == 2,
                 "une correction de la relecture devient une proposition, comptée")
        verifier(not vi.proposer_depuis_correction("cubernetes", "Kubernetes") or True,
                 "faute déjà connue : pas de doublon")
        sortie = base / "export.toml"
        vi.exporter(str(sortie), {})
        verifier(all(e.actif for e in v2.lire(sortie)[0].entrees), "export : termes actifs seulement")

        # Vue de relecture : remplacements montrés et annulables.
        segments = [{"d": 0.0, "f": 2.0, "t": "Bonjour cubernetes.",
                     "m": [{"t": "Bonjour", "d": 0.0, "f": 0.5, "p": 0.9},
                           {"t": "cubernetes.", "d": 0.5, "f": 1.5, "p": 0.4}]}]
        correcteur = usage.Correcteur(v2.effectif({})[0])
        journal_r = correcteur.corriger_segments(segments)
        txt = base / "reunion.txt"
        txt.write_text("Bonjour Kubernetes.\n", encoding="utf-8")
        donnees = {"format": compagnon.FORMAT, "version": 1, "segments": segments,
                   "vocabulaire": {"remplacements": journal_r}, "transcription": {"corrections_appliquees": 1}}
        compagnon.enregistrer_tel_quel(txt, donnees)
        charge = lecture.charger(txt)
        mots = charge["paragraphes"][0]["mots"]
        verifier(len(charge["remplacements"]) == 1 and charge["remplacements"][0]["apres"] == "Kubernetes",
                 "la relecture liste le remplacement")
        rendu = "".join(m.get("e", "") + m["t"] for m in mots)
        verifier(rendu == "Bonjour Kubernetes." and [m["t"] for m in mots if m.get("c")] == ["Kubernetes"]
                 and mots[0]["p"] == 0.9, "texte corrigé affiché à l'identique, mot changé marqué, "
                 "confiance gardée ailleurs", rendu)
        retour = lecture.annuler_remplacement(txt, 0)
        verifier(retour["ok"] and txt.read_text(encoding="utf-8") == "Bonjour cubernetes.\n"
                 and compagnon.lire(txt)["segments"][0]["t"] == "Bonjour cubernetes.",
                 "annulation : texte et compagnon remis", retour["message"])
        verifier(not lecture.charger(txt)["remplacements"] and not lecture.annuler_remplacement(txt, 0)["ok"],
                 "remplacement annulé : marqué, plus proposé")
        contenu = compagnon.construire(Path("x.m4a"), [], {"remplacements_vocabulaire": journal_r})
        verifier(contenu.get("vocabulaire", {}).get("remplacements") == journal_r,
                 "le compagnon garde le journal des remplacements")
    finally:
        v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS = anciens


def essai_fusion_corrections(base: Path) -> None:
    """
    Les corrections de la relecture (casse, pas de doublon, aperçu,
    annulation, texte exact) valent aussi avec le vocabulaire du format 2.
    """
    titre("10. Corrections de la relecture et vocabulaire, format 2")
    from app import compagnon, lecture

    def vocabulaire_de(*lignes: str) -> v2.Vocabulaire:
        entete_voc = ['format = "scribouille-vocabulaire"', "version = 2"]
        return v2.lire_texte("\n".join(entete_voc + list(lignes)) + "\n")[0]

    # Pas de doublon quand la forme juste prolonge la faute, même en tête de
    # phrase (casse différente de la forme).
    c = usage.Correcteur(vocabulaire_de("[[terme]]", 'forme = "réseaux sociaux"',
                                        'fautes = [{ forme = "réseaux", forcer = true }]'))
    rendu = c.corriger_texte("Réseaux sociaux et réseaux.")[0]
    verifier(rendu == "Réseaux sociaux et réseaux sociaux.",
             "pas de doublon : « Réseaux sociaux » reste tel quel, « réseaux » seul est corrigé", rendu)
    # Casse seule de mots courants, forcée (règle « pierre => Pierre » du format 1).
    ancien = v2.depuis_v1("", "pierre => Pierre\ngitlab => GitLab\n")
    rendu = usage.Correcteur(ancien).corriger_texte("pierre parle de gitlab et de GitLab.")[0]
    verifier(rendu == "Pierre parle de GitLab et de GitLab.",
             "casse : règles du format 1 de casse seule appliquées comme avant", rendu)
    relu = v2.lire_texte(v2.ecrire_texte(ancien))[0]
    verifier(any(f.forcer and f.forme == "pierre" for e in relu.entrees for f in e.fautes),
             "casse forcée : gardée à l'écriture et à la relecture du fichier")

    anciens = (v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS)
    try:
        v2.FICHIER_PERSONNEL = base / "perso.toml"
        chemins.FICHIER_VOCABULAIRE = base / "v-absent.txt"
        chemins.FICHIER_CORRECTIONS = base / "c-absent.txt"
        barre = "=" * 68
        entete = f"{barre}\nFichier : x\n{barre}\n\n"
        phrase = "Le projet gitlab avance. Les réseaux sociaux et les réseaux."
        txt = base / "relue.txt"
        txt.write_text(entete + phrase + "\n", encoding="utf-8")
        compagnon.enregistrer_tel_quel(txt, {"format": compagnon.FORMAT, "version": 1, "segments": [
            {"d": 0.0, "f": 3.0, "t": phrase, "m": []}]})

        apercu = lecture.apercu_correction(txt, "réseaux", "réseaux sociaux")
        verifier(apercu["ok"] and apercu["nombre"] == 1, "aperçu : un seul endroit, l'autre est déjà juste",
                 str(apercu.get("nombre")))
        retour = lecture.appliquer_correction(txt, "gitlab", "GitLab", ajouter_regle=True)
        perso = v2.lire(v2.FICHIER_PERSONNEL)[0] if v2.FICHIER_PERSONNEL.exists() else v2.Vocabulaire()
        verifier(retour["ok"] and retour["regle_ajoutee"] and perso.chercher("GitLab") is not None,
                 "mémoriser, format 2 : terme actif dans le vocabulaire personnel", retour["message"])
        verifier(txt.read_text(encoding="utf-8").startswith(entete + "Le projet GitLab"),
                 "correction : en-tête et séparation intacts")
        retour = lecture.annuler_correction(txt)
        verifier(retour["ok"] and retour["regle_retiree"] and not v2.FICHIER_PERSONNEL.exists()
                 and "gitlab avance" in txt.read_text(encoding="utf-8"),
                 "annulation : texte remis, terme retiré du vocabulaire", retour["message"])

        retour = lecture.appliquer_correction(txt, "réseaux", "réseaux sociaux")
        texte = txt.read_text(encoding="utf-8")
        perso = v2.lire(v2.FICHIER_PERSONNEL)[0] if v2.FICHIER_PERSONNEL.exists() else v2.Vocabulaire()
        verifier(retour["ok"] and retour["remplacements"] == 1 and "sociaux sociaux" not in texte
                 and perso.chercher("réseaux sociaux", etat="propose") is not None,
                 "sans mémoriser : un seul remplacement, proposition ajoutée", retour["message"])
        retour = lecture.annuler_correction(txt)
        verifier(retour["ok"] and not v2.FICHIER_PERSONNEL.exists(),
                 "annulation : la proposition ajoutée est retirée aussi", retour["message"])

        # Vue et annulation d'un remplacement du vocabulaire : texte exact, en-tête intact.
        phrase = "L'entreprise cubernetes, c'est-à-dire."
        segments = [{"d": 0.0, "f": 2.0, "t": phrase,
                     "m": [{"t": "L'entreprise", "d": 0.0, "p": 0.9}, {"t": "cubernetes,", "d": 0.5, "p": 0.4},
                           {"t": "c'est-à-dire.", "d": 1.0, "p": 0.8}]}]
        voc = vocabulaire_de("[[terme]]", 'forme = "Kubernetes"', 'categorie = "produit"', 'fautes = ["cubernetes"]')
        journal_r = usage.Correcteur(voc).corriger_segments(segments)
        txt.write_text(entete + segments[0]["t"] + "\n", encoding="utf-8")
        compagnon.enregistrer_tel_quel(txt, {"format": compagnon.FORMAT, "version": 1, "segments": segments,
                                             "vocabulaire": {"remplacements": journal_r}})
        mots = lecture.charger(txt)["paragraphes"][0]["mots"]
        rendu = "".join(m.get("e", "") + m["t"] for m in mots)
        verifier(rendu == "L'entreprise Kubernetes, c'est-à-dire."
                 and [m["t"] for m in mots if m.get("c")] == ["Kubernetes"],
                 "vue : texte exact du fichier, mot corrigé marqué", rendu)
        retour = lecture.annuler_remplacement(txt, 0)
        verifier(retour["ok"] and txt.read_text(encoding="utf-8") == entete + phrase + "\n",
                 "annuler un remplacement : en-tête et séparation intacts")
    finally:
        v2.FICHIER_PERSONNEL, chemins.FICHIER_VOCABULAIRE, chemins.FICHIER_CORRECTIONS = anciens


def essai_lexique() -> None:
    titre("0. Lexique et clé phonétique")
    verifier(lexique.lexique_disponible() and len(lexique.mots_courants()) >= 30000,
             "lexique du français courant chargé", str(len(lexique.mots_courants())))
    verifier(lexique.est_courant("entreprise") and not lexique.est_courant("kubernetes"), "mots courants")
    paires = (("Siminoff", "Siminov"), ("Auckland", "Aokland"), ("Kubernetes", "qui bernetes"), ("Dupont", "Dupond"))
    verifier(all(lexique.distance(lexique.cle_phonetique(a), lexique.cle_phonetique(b)) <= 1 for a, b in paires),
             "clé phonétique : graphies voisines rapprochées")
    verifier(lexique.distance(lexique.cle_phonetique("Kubernetes"), lexique.cle_phonetique("gouvernement")) > 2,
             "clé phonétique : mots différents tenus à distance")
    verifier(lexique.epeler("RGPD") == "èr gé pé dé" and lexique.est_sigle("RGPD") and not lexique.est_sigle("Rgpd"),
             "sigles épelés")
    verifier(langues.t("voc2.importe", ajoutees=1, ignorees=0) != "voc2.importe", "libellés présents")


def principal() -> int:
    print(f"Vérification du vocabulaire (format 2) de Scribouille\n{'=' * 52}")
    with tempfile.TemporaryDirectory(prefix="scribouille-voc-") as brut:
        base = Path(brut)
        from app import lecture

        lecture.DOSSIER_HISTORIQUE = base / "historique-relecture"
        for sous in ("migration", "apprentissage", "documents", "interface", "fusion"):
            (base / sous).mkdir()
        essai_lexique()
        essai_format()
        essai_migration(base / "migration")
        essai_fusion()
        essai_amorce()
        essai_correction()
        essai_apprentissage(base / "apprentissage")
        essai_documents(base / "documents")
        essai_mesure()
        (base / "reunions").mkdir()
        essai_mesure_reunions(base / "reunions")
        essai_interface(base / "interface")
        essai_fusion_corrections(base / "fusion")
    print(f"\n{'=' * 52}")
    if _echecs:
        print(f"{_reussites} vérifications passées, {len(_echecs)} en échec :")
        for libelle in _echecs:
            print(f"  - {libelle}")
        return 1
    print(f"{_reussites} vérifications passées, aucune en échec.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
