"""
Glossaire de vocabulaire et table de corrections.

Deux leviers complémentaires contre les noms propres écorchés :

1. AMORCE (initial_prompt). La liste des termes de `vocabulaire.txt` est injectée
   au décodeur comme début de contexte. Whisper est alors biaisé vers ces
   orthographes. Limite dure : l'amorce ne peut pas dépasser la moitié de la
   fenêtre de contexte du modèle, soit 224 jetons. Au-delà, faster-whisper
   tronque par la fin, donc silencieusement. On tronque nous-mêmes, proprement,
   en gardant les termes du DÉBUT de la liste, et on le signale dans l'interface.
   L'amorce étant lue par le décodeur comme un début de texte, sa phrase
   d'introduction suit la LANGUE PARLÉE de l'enregistrement, jamais celle de
   l'interface : une phrase française biaiserait le modèle vers le français.

2. CORRECTIONS (`corrections.txt`). Table `forme_erronée => forme_correcte`
   appliquée au texte final, mot entier, insensible à la casse. Pour les
   massacres récurrents que l'amorce ne suffit pas à corriger.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import chemins, journal, langues

# Whisper réserve la moitié de ses 448 jetons de contexte à l'amorce.
LIMITE_JETONS_AMORCE = 224
# Marge pour la phrase d'introduction et le jeton de début de contexte.
MARGE_JETONS = 24
# Estimation utilisée quand aucun tokeniseur n'est disponible : le français et
# les noms propres tournent autour de 3 caractères par jeton, on reste prudent.
CARACTERES_PAR_JETON = 3.0

#: En-tête de l'amorce, dans la LANGUE PARLÉE de l'enregistrement.
#:
#: L'amorce est un prompt : le décodeur la lit comme un début de contexte, donc
#: une phrase française biaise le modèle vers le français. Elle doit suivre la
#: langue parlée choisie pour la transcription, réglage « langue », et non la
#: langue de l'interface. Toute langue autre que le français prend l'anglais,
#: qui est le repli du modèle comme celui de l'application.
ENTETES_AMORCE = {
    "fr": "Vocabulaire de cet enregistrement : ",
    "en": "Vocabulary for this recording: ",
}


def _langue_parlee_courante() -> str:
    """Langue parlée du réglage courant. Import tardif : `config` lit `langues`."""
    try:
        from . import config as config_module

        return str(config_module.charger().get("langue", "fr") or "")
    except Exception:  # pragma: no cover - un réglage illisible ne bloque pas
        return "fr"


def entete_amorce(langue: str | None = None) -> str:
    """
    En-tête de l'amorce pour une langue parlée donnée.

    `None` va chercher le réglage courant. Une langue vide, c'est-à-dire la
    détection automatique, prend l'anglais : on ne sait pas ce qui sera parlé,
    autant ne pas pousser le décodeur vers le français.
    """
    code = langue if langue is not None else _langue_parlee_courante()
    code = str(code or "").strip().lower()[:2]
    return ENTETES_AMORCE.get(code, ENTETES_AMORCE["en"])


# ---------------------------------------------------------------------------
# Glossaire
# ---------------------------------------------------------------------------

def lire_glossaire(fichier: Path | None = None) -> str:
    fichier = fichier or chemins.FICHIER_VOCABULAIRE
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        journal.attention("Lecture du glossaire impossible : %s", exc)
        return ""


def ecrire_glossaire(contenu: str, fichier: Path | None = None) -> None:
    fichier = fichier or chemins.FICHIER_VOCABULAIRE
    fichier.write_text(contenu.rstrip() + "\n", encoding="utf-8")


def termes(contenu: str | None = None) -> list[str]:
    """Un terme par ligne, lignes vides et commentaires « # » ignorés."""
    brut = contenu if contenu is not None else lire_glossaire()
    resultat: list[str] = []
    vus: set[str] = set()
    for ligne in brut.splitlines():
        terme = ligne.strip()
        if not terme or terme.startswith("#"):
            continue
        cle = terme.lower()
        if cle in vus:
            continue
        vus.add(cle)
        resultat.append(terme)
    return resultat


#: Termes que le glossaire livré par les versions 1.x à 2.3 contenait ACTIFS, à
#: titre d'exemple (noms fictifs, outils pris au hasard). Le fichier est recopié
#: une fois chez l'utilisateur et jamais écrasé : une installation ancienne les
#: a gardés, et ils partent en amorce dans chaque transcription. La 2.4.0 les a
#: mis en commentaire pour les nouvelles installations seulement.
EXEMPLES_ANCIENS = (
    "Jean Dupont", "Marie Lefèvre", "Karim Benali", "MonEntreprise",
    "Direction des systèmes d'information", "GitLab", "Kubernetes", "Active Directory",
    "PostgreSQL", "RGPD", "API", "SSO",
)
#: Règles actives du `corrections.txt` livré par les mêmes versions.
CORRECTIONS_ANCIENNES = (
    ("jean dupont", "Jean Dupont"), ("mon entreprise", "MonEntreprise"),
    ("guitte lab", "GitLab"), ("guite lab", "GitLab"), ("cubernetes", "Kubernetes"),
    ("poste grès", "PostgreSQL"), ("er gé pé dé", "RGPD"), ("a pé i", "API"),
)


def nombre_exemples_anciens(liste: list[str]) -> int:
    """Combien des termes donnés sont des exemples livrés actifs par les anciennes versions."""
    anciens = {t.lower() for t in EXEMPLES_ANCIENS}
    return sum(1 for terme in liste if terme.lower() in anciens)


def glossaire_exemple_intact(contenu: str) -> bool:
    """Le glossaire est-il exactement celui des anciennes versions, jamais retouché ?"""
    return [t.lower() for t in termes(contenu)] == [t.lower() for t in EXEMPLES_ANCIENS]


def corrections_exemple_intactes(contenu: str) -> bool:
    regles, erreurs = analyser_corrections(contenu)
    return not erreurs and [(r.source.lower(), r.cible) for r in regles] == list(CORRECTIONS_ANCIENNES)


def retirer_exemples_anciens() -> list[str]:
    """
    Remplace le glossaire et la table de corrections d'une installation ancienne
    restés EXACTEMENT tels que livrés, exemples actifs compris, par les modèles
    actuels (mêmes exemples, en commentaire). Une copie de l'ancien fichier est
    gardée à côté. Un fichier retouché, ne serait-ce que d'un terme, n'est pas
    touché. Renvoie les noms des fichiers remplacés.

    Constaté sur un poste : les douze exemples fictifs partaient en amorce de
    chaque transcription, et la règle « mon entreprise => MonEntreprise »
    réécrivait une tournure française courante.
    """
    remplaces = []
    for cible, intact in ((chemins.FICHIER_VOCABULAIRE, glossaire_exemple_intact),
                          (chemins.FICHIER_CORRECTIONS, corrections_exemple_intactes)):
        source = chemins.MODELES_FICHIERS_EXEMPLE.get(cible)
        if source is None or cible == source or not cible.is_file() or not source.is_file():
            continue
        try:
            contenu = cible.read_text(encoding="utf-8-sig")
            if not intact(contenu):
                continue
            cible.with_name(cible.stem + "-exemples-anciens.txt").write_text(contenu, encoding="utf-8")
            cible.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            remplaces.append(cible.name)
            journal.info("%s : exemples livrés actifs remplacés par le modèle actuel", cible.name)
        except OSError as exc:
            journal.attention("Exemples anciens non retirés de %s : %s", cible.name, exc)
    return remplaces


def _compter_jetons(texte: str, tokeniseur=None) -> int:
    if tokeniseur is not None:
        try:
            return len(tokeniseur.encode(texte).ids)
        except Exception:
            try:
                return len(tokeniseur.encode(texte))
            except Exception:
                pass
    return int(len(texte) / CARACTERES_PAR_JETON) + 1


def construire_amorce(contenu: str | None = None, tokeniseur=None,
                      langue: str | None = None) -> dict:
    """
    Fabrique l'amorce à passer en `initial_prompt`.

    `langue` est la langue PARLÉE de l'enregistrement, pas celle de l'interface :
    elle décide de l'en-tête, et donc de la langue vers laquelle l'amorce biaise
    le décodeur. `None` reprend le réglage courant.

    Renvoie un dictionnaire : `amorce`, `nb_termes`, `nb_retenus`, `tronque`,
    `jetons`, `message`. La troncature garde l'ordre du fichier : les premiers
    termes sont les plus importants, c'est écrit dans l'en-tête de
    `vocabulaire.txt` et rappelé dans l'interface.

    Le budget de jetons est compté sur la forme réellement envoyée, en-tête
    compris : un en-tête plus court ne fait pas mentir le décompte affiché.
    """
    entete = entete_amorce(langue)
    liste = termes(contenu)
    if not liste:
        return {
            "amorce": "",
            "nb_termes": 0,
            "nb_retenus": 0,
            "tronque": False,
            "jetons": 0,
            "message": langues.t("voc.glossaire_vide"),
        }

    budget = LIMITE_JETONS_AMORCE - MARGE_JETONS
    retenus: list[str] = []
    for terme in liste:
        candidat = entete + ", ".join(retenus + [terme]) + "."
        if _compter_jetons(candidat, tokeniseur) > budget and retenus:
            break
        retenus.append(terme)
        if _compter_jetons(entete + ", ".join(retenus) + ".", tokeniseur) > budget:
            retenus.pop()
            break

    if not retenus:
        return {
            "amorce": "",
            "nb_termes": len(liste),
            "nb_retenus": 0,
            "tronque": True,
            "jetons": 0,
            "message": langues.t("voc.premier_trop_long"),
        }

    amorce = entete + ", ".join(retenus) + "."
    jetons = _compter_jetons(amorce, tokeniseur)
    tronque = len(retenus) < len(liste)

    if tronque:
        message = langues.t(
            "voc.amorce_tronquee", retenus=len(retenus), total=len(liste),
            jetons=jetons, limite=LIMITE_JETONS_AMORCE,
        )
    else:
        message = langues.t(
            "voc.amorce_ok", retenus=len(retenus), jetons=jetons,
            limite=LIMITE_JETONS_AMORCE,
        )

    return {
        "amorce": amorce,
        "nb_termes": len(liste),
        "nb_retenus": len(retenus),
        "tronque": tronque,
        "jetons": jetons,
        "message": message,
    }


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

class Correction:
    __slots__ = ("source", "cible", "motif")

    def __init__(self, source: str, cible: str):
        self.source = source
        self.cible = cible
        # Frontières de mot tolérantes aux accents et aux termes multi-mots :
        # on interdit simplement qu'un caractère de mot colle de part et d'autre.
        echappe = re.escape(source)
        echappe = re.sub(r"\\?\s+", r"\\s+", echappe)
        self.motif = re.compile(rf"(?<!\w){echappe}(?!\w)", re.IGNORECASE | re.UNICODE)


def lire_corrections(fichier: Path | None = None) -> str:
    fichier = fichier or chemins.FICHIER_CORRECTIONS
    try:
        return fichier.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        journal.attention("Lecture des corrections impossible : %s", exc)
        return ""


def ecrire_corrections(contenu: str, fichier: Path | None = None) -> None:
    fichier = fichier or chemins.FICHIER_CORRECTIONS
    fichier.write_text(contenu.rstrip() + "\n", encoding="utf-8")


def analyser_corrections(contenu: str | None = None) -> tuple[list[Correction], list[str]]:
    """Renvoie (règles valides, lignes en erreur formulées en français)."""
    brut = contenu if contenu is not None else lire_corrections()
    regles: list[Correction] = []
    erreurs: list[str] = []

    for numero, ligne in enumerate(brut.splitlines(), start=1):
        texte = ligne.strip()
        if not texte or texte.startswith("#"):
            continue
        if "=>" not in texte:
            erreurs.append(langues.t("voc.err.fleche", ligne=numero))
            continue
        source, _, cible = texte.partition("=>")
        source, cible = source.strip(), cible.strip()
        if not source:
            erreurs.append(langues.t("voc.err.source_vide", ligne=numero))
            continue
        if not cible:
            erreurs.append(langues.t("voc.err.cible_vide", ligne=numero))
            continue
        try:
            regles.append(Correction(source, cible))
        except re.error as exc:
            erreurs.append(langues.t("voc.err.illisible", ligne=numero, detail=exc))

    return regles, erreurs


def appliquer(texte: str, regles: list[Correction]) -> tuple[str, int]:
    """Applique les règles au texte, renvoie (texte corrigé, nombre de remplacements)."""
    if not regles or not texte:
        return texte, 0
    total = 0
    for regle in regles:
        texte, nombre = _remplacer(regle, texte)
        total += nombre
    return texte, total


def occurrences(regle: Correction, texte: str) -> list[re.Match]:
    """
    Les occurrences qu'une règle changerait réellement dans un texte.

    Deux garde-fous : une occurrence déjà écrite sous la forme corrigée n'est
    pas réécrite (« gitlab => GitLab » laisse « GitLab » tel quel), et quand la
    forme corrigée contient la forme entendue (« réseaux => réseaux sociaux »),
    une occurrence qui fait déjà partie de la forme corrigée n'est pas touchée :
    sans cela, chaque passage ajoutait un « sociaux » de plus.
    """
    proteges: list[tuple[int, int]] = []
    if regle.source.lower() in regle.cible.lower() and regle.source.lower() != regle.cible.lower():
        cible = re.sub(r"\\?\s+", r"\\s+", re.escape(regle.cible))
        motif_cible = re.compile(rf"(?<!\w){cible}(?!\w)", re.IGNORECASE | re.UNICODE)
        proteges = [trouve.span() for trouve in motif_cible.finditer(texte)]
    return [
        trouve for trouve in regle.motif.finditer(texte)
        if trouve.group(0) != regle.cible
        and not any(debut <= trouve.start() and trouve.end() <= fin for debut, fin in proteges)
    ]


def _remplacer(regle: Correction, texte: str) -> tuple[str, int]:
    """Une règle sur un texte. Ne compte que les changements réels."""
    a_changer = occurrences(regle, texte)
    # Assemblage par tranches : la forme corrigée est prise à la lettre, une
    # barre oblique inverse n'y est jamais lue comme un renvoi de motif.
    morceaux: list[str] = []
    position = 0
    for trouve in a_changer:
        morceaux.append(texte[position:trouve.start()])
        morceaux.append(regle.cible)
        position = trouve.end()
    morceaux.append(texte[position:])
    return "".join(morceaux), len(a_changer)


# ---------------------------------------------------------------------------
# Corrections apprises depuis la vue de lecture
# ---------------------------------------------------------------------------

#: Titre de la section où sont rangées les règles ajoutées d'un clic depuis une
#: transcription. Les règles écrites à la main gardent leur place, en haut.
#:
#: Le titre est écrit dans la langue d'interface du moment, mais TOUTES les
#: langues connues sont reconnues à la relecture : un `corrections.txt` créé en
#: français ne se voit pas ajouter une seconde section quand l'interface passe
#: en anglais. Un fichier existant n'est jamais retraduit.


def titre_section_apprises() -> str:
    return langues.t("voc.section_apprises")


def titres_section_connus() -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        langues.TEXTES[code]["voc.section_apprises"] for code in langues.LANGUES
    ))

#: Une règle est faite pour un mot ou une courte expression, pas pour un
#: paragraphe entier : au-delà, on ne corrige plus, on réécrit.
LONGUEUR_MAX_REGLE = 80


def verifier_regle(source: str, cible: str) -> str:
    """Contrôle une règle avant écriture. Renvoie un refus en français, ou ''."""
    source = " ".join((source or "").split())
    cible = " ".join((cible or "").split())
    if not source:
        return langues.t("regle.selection_vide")
    if not cible:
        return langues.t("regle.cible_vide")
    # Une correction de casse (« gitlab » vers « GitLab ») est une vraie
    # correction : seule une forme strictement identique est refusée.
    if source == cible:
        return langues.t("regle.identique")
    for valeur, cle_etiquette in ((source, "regle.etiquette.source"),
                                  (cible, "regle.etiquette.cible")):
        if len(valeur) > LONGUEUR_MAX_REGLE:
            return langues.t(
                "regle.trop_longue",
                etiquette=langues.t(cle_etiquette), max=LONGUEUR_MAX_REGLE,
            )
        if "=>" in valeur:
            return langues.t("regle.fleche_interdite")
        if valeur.startswith("#"):
            return langues.t("regle.diese_interdit")
    return ""


def ajouter_correction_apprise(source: str, cible: str, fichier: Path | None = None) -> dict:
    """
    Ajoute une règle à `corrections.txt`, dans la section des règles apprises.

    Une règle dont la forme entendue est déjà couverte n'est pas ajoutée une
    seconde fois : le fichier doit rester lisible et modifiable à la main.
    """
    source = " ".join((source or "").split())
    cible = " ".join((cible or "").split())
    probleme = verifier_regle(source, cible)
    if probleme:
        return {"ajoutee": False, "message": probleme}

    contenu = lire_corrections(fichier)
    for ligne in contenu.splitlines():
        texte = ligne.strip()
        if not texte or texte.startswith("#") or "=>" not in texte:
            continue
        gauche, _, droite = texte.partition("=>")
        if " ".join(gauche.split()).lower() == source.lower():
            if " ".join(droite.split()).lower() == cible.lower():
                return {"ajoutee": False, "message": langues.t("regle.deja_enregistree")}
            return {
                "ajoutee": False,
                "message": langues.t(
                    "regle.conflit", source=source, cible=" ".join(droite.split())),
            }

    lignes = contenu.rstrip("\n").splitlines()
    connus = titres_section_connus()
    if not any(ligne.strip() in connus for ligne in lignes):
        if lignes:
            lignes.append("")
        lignes.append(titre_section_apprises())
        lignes.append(langues.t("voc.section_commentaire"))
    lignes.append(f"{source} => {cible}")

    ecrire_corrections("\n".join(lignes), fichier)
    journal.info("Correction apprise : « %s » vers « %s »", source, cible)
    return {
        "ajoutee": True,
        "message": langues.t("regle.ajoutee", source=source, cible=cible),
    }


def resume_glossaire(langue: str | None = None) -> dict:
    """État affiché dans le panneau de réglages, sans charger de modèle."""
    info = construire_amorce(langue=langue)
    regles, erreurs = analyser_corrections()
    info["nb_corrections"] = len(regles)
    info["erreurs_corrections"] = erreurs
    return info
