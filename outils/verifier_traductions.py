"""
Contrôle des traductions : parité des clés, absence de français en dur, typographie.

L'internationalisation est un chantier mécanique dont le seul vrai danger est
l'oubli. Ce script est le filet. Il ne lance rien, ne touche à rien, et se
contente de lire les fichiers du dépôt.

Sept contrôles :

  1. PARITÉ PYTHON : `app/langues.py`, les clés du français et de l'anglais
     coïncident exactement.
  2. PARITÉ JAVASCRIPT : `web/langues.js`, même exigence.
  3. CLÉS PYTHON UTILISÉES : tout `langues.t("...")` littéral du code existe
     bien dans le catalogue.
  4. CLÉS JAVASCRIPT UTILISÉES : tout `t('...')` de `web/app.js` et tout
     `data-i18n` de `web/index.html` existe bien dans le catalogue.
  5. FRANÇAIS EN DUR : aucun caractère accenté ne subsiste dans les littéraux de
     `web/app.js` ni dans `web/index.html`, commentaires exclus. Le catalogue
     `web/langues.js` est le seul endroit où le français a le droit d'exister.
  6. TIRETS LONGS : aucun tiret cadratin ni demi-cadratin, dans aucune des deux
     langues, ni dans les fichiers d'interface.
  7. SUBSTITUTIONS : les variables `{nom}` d'une clé sont les mêmes dans les
     deux langues, sans quoi une phrase traduite perdrait une valeur.

    .venv\\Scripts\\python outils\\verifier_traductions.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import langues  # noqa: E402

_echecs: list[str] = []
_reussites = 0

#: Tirets interdits : cadratin, demi-cadratin, barre horizontale, tiret de
#: chiffre. La virgule ou les deux points font le travail, dans les deux langues.
TIRETS_INTERDITS = "—–―‒"

#: Préfixes de clés construites à l'exécution : elles ne peuvent pas être vues
#: par une lecture statique, et leur absence de la liste des clés citées est
#: normale.
PREFIXES_DYNAMIQUES = (
    "err.", "preset.", "modele.qualite.", "gpu.note.", "npu.note",
    "regle.etiquette.", "langue.", "ui.qualite.", "ui.langue.",
    "duree.", "duree_longue.", "unite.", "format.", "reglage.",
    "voc.section_apprises", "gabarit.defaut",
    "lect.remplacements.", "app.ajoutes.", "app.veille.ajoutes.",
    "ui.voc.termes.", "ui.voc.regles.", "ui.theme.", "ui.maj.",
    "ui.motif.", "app.motif.", "app.demarrer.ffmpeg_", "audio.ffmpeg.",
    "diar.indispo.", "stock.programme.detail_", "arch.chemin_",
    "lect.tronque", "lect.sans_compagnon",
)


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
# Lecture du catalogue JavaScript
#
# Pas d'interpréteur, pas de dépendance : le fichier a une forme stable, deux
# blocs de premier niveau « fr: { » et « en: { » fermés par « }, » en colonne 1.
# Une lecture par expression régulière suffit et reste vérifiable à l'œil.
# ---------------------------------------------------------------------------

_MOTIF_CLE_JS = re.compile(r"^\s{2}'([A-Za-z0-9_.]+)':", re.MULTILINE)


def bloc_langue_js(source: str, code: str) -> str:
    debut = source.find(f"\n{code}: {{")
    if debut < 0:
        return ""
    fin = source.find("\n},", debut)
    return source[debut:fin] if fin > debut else source[debut:]


def cles_js(source: str, code: str) -> set[str]:
    return set(_MOTIF_CLE_JS.findall(bloc_langue_js(source, code)))


def valeurs_js(source: str, code: str) -> str:
    """Le bloc brut d'une langue, pour les contrôles typographiques."""
    return bloc_langue_js(source, code)


# ---------------------------------------------------------------------------
# Retrait des commentaires
# ---------------------------------------------------------------------------

def sans_commentaires_js(source: str) -> str:
    sans_blocs = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"(?m)^\s*//.*$", " ", sans_blocs)


def sans_commentaires_html(source: str) -> str:
    return re.sub(r"<!--.*?-->", " ", source, flags=re.DOTALL)


def accents(texte: str) -> set[str]:
    """Caractères latins accentués présents dans le texte."""
    trouves = set()
    for caractere in texte:
        if not caractere.isalpha() or caractere.isascii():
            continue
        nom = unicodedata.name(caractere, "")
        if nom.startswith("LATIN "):
            trouves.add(caractere)
    return trouves


def lignes_avec(texte: str, caracteres: str, limite: int = 5) -> list[str]:
    resultat = []
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if any(c in ligne for c in caracteres):
            resultat.append(f"ligne {numero} : {ligne.strip()[:90]}")
            if len(resultat) >= limite:
                break
    return resultat


# ---------------------------------------------------------------------------
# 1 et 2. Parité des clés
# ---------------------------------------------------------------------------

def essai_parite_python() -> None:
    titre("Parité des clés, côté Python (app/langues.py)")

    tables = {code: set(langues.TEXTES[code]) for code in langues.LANGUES}
    reference = tables["fr"]
    for code, cles in tables.items():
        if code == "fr":
            continue
        manquantes = sorted(reference - cles)
        en_trop = sorted(cles - reference)
        verifier(
            not manquantes,
            f"aucune clé du français absente de « {code} »",
            ", ".join(manquantes[:8]),
        )
        verifier(
            not en_trop,
            f"aucune clé de « {code} » absente du français",
            ", ".join(en_trop[:8]),
        )
    verifier(len(reference) > 150, "le catalogue Python est complet",
             f"{len(reference)} clés")
    print(f"         {len(reference)} clés par langue")


def essai_parite_js(source: str) -> None:
    titre("Parité des clés, côté JavaScript (web/langues.js)")

    tables = {code: cles_js(source, code) for code in ("fr", "en")}
    verifier(bool(tables["fr"]) and bool(tables["en"]),
             "les deux blocs de langue sont lisibles",
             f"fr={len(tables['fr'])}, en={len(tables['en'])}")
    manquantes = sorted(tables["fr"] - tables["en"])
    en_trop = sorted(tables["en"] - tables["fr"])
    verifier(not manquantes, "aucune clé du français absente de « en »",
             ", ".join(manquantes[:8]))
    verifier(not en_trop, "aucune clé de « en » absente du français",
             ", ".join(en_trop[:8]))
    print(f"         {len(tables['fr'])} clés par langue")


# ---------------------------------------------------------------------------
# 3 et 4. Les clés citées par le code existent
# ---------------------------------------------------------------------------

_MOTIF_APPEL_PY = re.compile(r"\blangues\.tn?\(\s*(['\"])([A-Za-z0-9_.]+)\1\s*[,)]")
_MOTIF_APPEL_JS = re.compile(r"(?<![\w.])tn?\(\s*(['\"])([A-Za-z0-9_.]+)\1\s*[,)]")
_MOTIF_I18N = re.compile(r'data-i18n(?:-html|-title|-aria|-placeholder)?="([A-Za-z0-9_.]+)"')


def essai_cles_citees_python() -> None:
    titre("Clés citées par le code Python")

    connues = set(langues.TEXTES["fr"])
    citees: dict[str, str] = {}
    for fichier in sorted(list((RACINE / "app").glob("*.py")) + [RACINE / "transcriber.pyw"]):
        if fichier.name == "langues.py":
            continue
        texte = fichier.read_text(encoding="utf-8")
        for _, cle in _MOTIF_APPEL_PY.findall(texte):
            citees.setdefault(cle, fichier.name)

    # `tn` cite une racine, les deux variantes doivent exister.
    inconnues = []
    for cle, origine in sorted(citees.items()):
        if cle in connues or {cle + ".un", cle + ".autres"} <= connues:
            continue
        inconnues.append(f"{cle} ({origine})")
    verifier(not inconnues, "toutes les clés citées existent dans le catalogue",
             ", ".join(inconnues[:6]))
    print(f"         {len(citees)} clés citées littéralement")


def essai_cles_citees_js(source_catalogue: str) -> None:
    titre("Clés citées par l'interface web")

    connues = cles_js(source_catalogue, "fr")

    app = sans_commentaires_js((RACINE / "web" / "app.js").read_text(encoding="utf-8"))
    citees = {cle for _, cle in _MOTIF_APPEL_JS.findall(app)}
    inconnues = sorted(
        cle for cle in citees
        if cle not in connues and not {cle + ".un", cle + ".autres"} <= connues
    )
    verifier(not inconnues, "app.js : toutes les clés citées existent",
             ", ".join(inconnues[:6]))

    html = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    posees = set(_MOTIF_I18N.findall(html))
    absentes = sorted(posees - connues)
    verifier(not absentes, "index.html : tous les data-i18n existent",
             ", ".join(absentes[:6]))
    print(f"         {len(citees)} clés dans app.js, {len(posees)} dans index.html")


# ---------------------------------------------------------------------------
# 5. Plus de français en dur dans l'interface
# ---------------------------------------------------------------------------

def essai_francais_en_dur() -> None:
    titre("Français en dur dans l'interface")

    app = (RACINE / "web" / "app.js").read_text(encoding="utf-8")
    code = sans_commentaires_js(app)
    restants = accents(code)
    verifier(
        not restants,
        "app.js : aucun littéral accentué hors commentaires",
        " ".join(sorted(restants)) + " ; " + " | ".join(lignes_avec(code, "".join(restants))),
    )

    html = (RACINE / "web" / "index.html").read_text(encoding="utf-8")
    corps = sans_commentaires_html(html)
    restants = accents(corps)
    verifier(
        not restants,
        "index.html : aucun texte accenté, tout passe par data-i18n",
        " ".join(sorted(restants)) + " ; " + " | ".join(lignes_avec(corps, "".join(restants))),
    )

    css = (RACINE / "web" / "styles.css").read_text(encoding="utf-8")
    contenus = re.findall(r"content\s*:\s*(['\"])(.*?)\1", css)
    avec_texte = [valeur for _, valeur in contenus if accents(valeur)]
    verifier(not avec_texte, "styles.css : aucun texte accenté en « content »",
             ", ".join(avec_texte[:5]))


# ---------------------------------------------------------------------------
# 6. Tirets longs
# ---------------------------------------------------------------------------

def essai_tirets(source_catalogue: str) -> None:
    titre("Tirets longs, interdits dans les deux langues")

    for code in langues.LANGUES:
        fautifs = sorted(
            cle for cle, valeur in langues.TEXTES[code].items()
            if any(t in valeur for t in TIRETS_INTERDITS)
        )
        verifier(not fautifs, f"catalogue Python, langue « {code} »",
                 ", ".join(fautifs[:6]))

    for code in ("fr", "en"):
        bloc = valeurs_js(source_catalogue, code)
        verifier(
            not any(t in bloc for t in TIRETS_INTERDITS),
            f"catalogue JavaScript, langue « {code} »",
            " | ".join(lignes_avec(bloc, TIRETS_INTERDITS)),
        )

    for relatif in ("web/app.js", "web/index.html", "web/styles.css"):
        texte = (RACINE / relatif).read_text(encoding="utf-8")
        verifier(
            not any(t in texte for t in TIRETS_INTERDITS),
            f"{relatif}",
            " | ".join(lignes_avec(texte, TIRETS_INTERDITS)),
        )

    fautifs = []
    for fichier in sorted(list((RACINE / "app").glob("*.py")) + [RACINE / "transcriber.pyw"]):
        texte = fichier.read_text(encoding="utf-8")
        if any(tiret in texte for tiret in TIRETS_INTERDITS):
            fautifs.append(
                f"{fichier.name} ({lignes_avec(texte, TIRETS_INTERDITS, 1)[0]})")
    verifier(not fautifs, "aucun tiret long dans les sources Python",
             " | ".join(fautifs[:4]))


# ---------------------------------------------------------------------------
# 7. Variables de substitution
# ---------------------------------------------------------------------------

_MOTIF_VARIABLE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")

#: Le gabarit d'instructions parle de variables destinées à l'utilisateur, pas
#: à `t()` : elles n'ont aucune raison d'être identiques d'une langue à l'autre
#: dans leur ordre, et elles le sont de fait. On l'exclut du contrôle strict.
CLES_HORS_CONTROLE = {"gabarit.defaut"}


def essai_variables(source_catalogue: str) -> None:
    titre("Variables de substitution, identiques d'une langue à l'autre")

    divergences = []
    for cle, valeur_fr in langues.TEXTES["fr"].items():
        if cle in CLES_HORS_CONTROLE:
            continue
        for code in langues.LANGUES:
            if code == "fr":
                continue
            valeur = langues.TEXTES[code].get(cle, "")
            if set(_MOTIF_VARIABLE.findall(valeur_fr)) != set(_MOTIF_VARIABLE.findall(valeur)):
                divergences.append(f"{cle} ({code})")
    verifier(not divergences, "catalogue Python", ", ".join(divergences[:6]))

    lignes_fr = dict(_paires_js(source_catalogue, "fr"))
    lignes_en = dict(_paires_js(source_catalogue, "en"))
    divergences = [
        cle for cle, valeur in lignes_fr.items()
        if set(_MOTIF_VARIABLE.findall(valeur))
        != set(_MOTIF_VARIABLE.findall(lignes_en.get(cle, "")))
    ]
    verifier(not divergences, "catalogue JavaScript", ", ".join(divergences[:6]))


def _paires_js(source: str, code: str) -> list[tuple[str, str]]:
    """
    Couples (clé, valeur brute) d'un bloc de langue.

    La valeur s'étend de la clé jusqu'à la clé suivante : cela suffit pour
    compter des accolades, et cela encaisse les chaînes coupées sur plusieurs
    lignes par des concaténations.
    """
    bloc = bloc_langue_js(source, code)
    positions = [(m.group(1), m.start()) for m in _MOTIF_CLE_JS.finditer(bloc)]
    paires = []
    for index, (cle, debut) in enumerate(positions):
        fin = positions[index + 1][1] if index + 1 < len(positions) else len(bloc)
        paires.append((cle, bloc[debut:fin]))
    return paires


# ---------------------------------------------------------------------------

def principal() -> int:
    print(f"Vérification des traductions de Scribouille\n{'=' * 42}")
    catalogue = (RACINE / "web" / "langues.js").read_text(encoding="utf-8")

    essai_parite_python()
    essai_parite_js(catalogue)
    essai_cles_citees_python()
    essai_cles_citees_js(catalogue)
    essai_francais_en_dur()
    essai_tirets(catalogue)
    essai_variables(catalogue)

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
