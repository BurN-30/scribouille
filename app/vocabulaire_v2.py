"""
Vocabulaire, format 2 : un fichier unique, lisible et modifiable à la main.

Pourquoi un nouveau format
--------------------------
Le format 1 tient en deux listes : `vocabulaire.txt` (termes soufflés au
modèle) et `corrections.txt` (règles « forme erronée => forme correcte »). Il
ne sait pas dire à quelle sorte de mot on a affaire, combien de fois une
erreur a été vue, d'où vient une règle, si elle est validée, ni qu'une forme
fautive qui est aussi un mot courant ne doit être remplacée que dans un
contexte. Les outils reconnus séparent ces informations : la forme affichée et
sa prononciation (« DisplayAs » d'Amazon Transcribe), une pondération (le
« boost » de Google, le poids des listes de phrases d'Azure), les corrections
après coup (« custom spelling »). Le format 2 réunit tout cela dans un seul
fichier par portée (personnel, équipe, projet), fusionnables.

Syntaxe : un sous-ensemble strict de TOML 1.0, donc lisible par n'importe quel
outil TOML, mais lu ici par un petit analyseur maison (aucune dépendance, et
Python 3.9 n'a pas `tomllib`). Exemple, fictif :

    format = "scribouille-vocabulaire"
    version = 2
    nom = "Vocabulaire de l'équipe"
    portee = "equipe"          # personnel, equipe ou projet
    langue = "fr"

    [[terme]]
    forme = "Kubernetes"                       # forme correcte, telle qu'affichée
    categorie = "produit"                      # personne, societe, sigle, produit, metier, anglicisme, autre
    fautes = ["cubernetes", "qui bernetes"]    # ce que le modèle écrit à la place : toujours ramené
    prononciation = "kubeur nétisse"           # facultatif : aide au rapprochement phonétique
    poids = 3                                  # 1 à 5 : priorité dans l'amorce
    origine = "saisi"                          # saisi, correction, compte_rendu, apprentissage, glossaire_v1, corrections_v1, import
    etat = "actif"                             # actif, propose, refuse

    [[terme]]
    forme = "Martin Lebrun"
    categorie = "personne"
    fautes = [
      "martin le brun",
      { forme = "martin", voisins = ["monsieur", "lebrun"] },   # seulement près de ces mots
      { forme = "lebrin", vu = 4, reunions = 2 },               # vu 4 fois dans 2 réunions
    ]

Champs d'une faute, quand elle est écrite en table : `forme`, `voisins`
(portée : vide = toujours), `forcer` (vrai : remplacer même si c'est une suite
de mots courants, sans contexte ; c'est le cas des règles reprises du format 1,
écrites à la main), `vu` et `reunions` (comptes de l'apprentissage).

Champs facultatifs d'un terme : `amorce` (faux : ne jamais le souffler au
modèle, seulement corriger), `rapprochement` (faux : pas de rapprochement
phonétique, seulement les fautes listées), `vu`, `reunions`, `note`, `ajoute`.

Fusion : plusieurs fichiers, du moins prioritaire au plus prioritaire (équipe,
projet, puis personnel, qui a le dernier mot). Les fautes s'additionnent, les
autres champs du plus prioritaire l'emportent, un terme refusé l'est pour de
bon. Une même faute ramenée à deux formes différentes est un conflit : la
fusion garde la plus prioritaire et le signale.

Migration : le glossaire et les corrections du format 1 se convertissent sans
rien perdre (`depuis_v1`). Tant qu'ils ne sont pas convertis, ils restent lus
tels quels, comme une couche de plus (`effectif`).
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from . import chemins, journal, lexique

FORMAT = "scribouille-vocabulaire"
VERSION_FORMAT = 2
NOM_FICHIER = "vocabulaire.toml"
FICHIER_PERSONNEL = chemins.RACINE / NOM_FICHIER

CATEGORIES = ("personne", "societe", "sigle", "produit", "metier", "anglicisme", "autre")
ORIGINES = ("saisi", "correction", "compte_rendu", "apprentissage", "glossaire_v1",
            "corrections_v1", "import")
ETATS = ("actif", "propose", "refuse")
PORTEES = ("personnel", "equipe", "projet")
POIDS_MIN, POIDS_MAX = 1, 5


class ErreurFormat(ValueError):
    """Fichier de vocabulaire illisible : message en français, avec la ligne."""


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------

def cle(texte: str) -> str:
    """Clé de comparaison d'une forme : casse, accents composés et espaces ignorés."""
    return lexique.forme_comparable(texte)


@dataclass
class Faute:
    forme: str
    voisins: list[str] = field(default_factory=list)
    forcer: bool = False
    vu: int = 0
    reunions: int = 0

    @property
    def en_contexte(self) -> bool:
        return bool(self.voisins)

    def copie(self) -> "Faute":
        return Faute(self.forme, list(self.voisins), self.forcer, self.vu, self.reunions)


@dataclass
class Entree:
    forme: str
    categorie: str = "autre"
    fautes: list[Faute] = field(default_factory=list)
    prononciation: str = ""
    poids: int = 1
    origine: str = "saisi"
    etat: str = "actif"
    amorce: bool = True
    rapprochement: bool = True
    vu: int = 0
    reunions: int = 0
    note: str = ""
    ajoute: str = ""
    #: Fichier d'où vient l'entrée après fusion (jamais écrit).
    source: str = ""

    @property
    def cle(self) -> str:
        return cle(self.forme)

    @property
    def actif(self) -> bool:
        return self.etat == "actif"

    def faute(self, forme: str) -> Faute | None:
        k = cle(forme)
        return next((f for f in self.fautes if cle(f.forme) == k), None)

    def ajouter_faute(self, faute: Faute) -> None:
        existante = self.faute(faute.forme)
        if existante is None:
            self.fautes.append(faute.copie())
            return
        existante.vu = max(existante.vu, faute.vu)
        existante.reunions = max(existante.reunions, faute.reunions)
        existante.forcer = existante.forcer or faute.forcer
        if faute.voisins or existante.voisins:
            # Une faute « toujours » l'emporte sur une faute en contexte.
            if not faute.voisins or not existante.voisins:
                existante.voisins = []
            else:
                existante.voisins = list(dict.fromkeys(existante.voisins + faute.voisins))

    def copie(self) -> "Entree":
        return Entree(self.forme, self.categorie, [f.copie() for f in self.fautes], self.prononciation,
                      self.poids, self.origine, self.etat, self.amorce, self.rapprochement, self.vu,
                      self.reunions, self.note, self.ajoute, self.source)


@dataclass
class Vocabulaire:
    entrees: list[Entree] = field(default_factory=list)
    nom: str = ""
    portee: str = "personnel"
    langue: str = "fr"
    version: int = VERSION_FORMAT
    #: Conflits relevés à la fusion : (faute, forme gardée, forme écartée).
    conflits: list[tuple[str, str, str]] = field(default_factory=list)

    def actives(self) -> list[Entree]:
        return [e for e in self.entrees if e.actif]

    def par_etat(self, etat: str) -> list[Entree]:
        return [e for e in self.entrees if e.etat == etat]

    def chercher(self, forme: str, etat: str | None = "actif") -> Entree | None:
        k = cle(forme)
        return next((e for e in self.entrees if e.cle == k and (etat is None or e.etat == etat)), None)


# ---------------------------------------------------------------------------
# Lecture : sous-ensemble de TOML
# ---------------------------------------------------------------------------

class _Analyseur:
    """Analyseur d'un sous-ensemble de TOML : clés simples, chaînes, entiers,
    flottants, booléens, tableaux (sur plusieurs lignes), tables en ligne et
    en-têtes `[[terme]]`. Toute autre construction est refusée avec sa ligne."""

    def __init__(self, texte: str):
        self.t = texte.replace("\r\n", "\n")
        self.i = 0

    # -- outils
    def ligne(self) -> int:
        return self.t.count("\n", 0, self.i) + 1

    def erreur(self, message: str) -> ErreurFormat:
        return ErreurFormat(f"ligne {self.ligne()} : {message}")

    def blancs(self, sauts: bool = False) -> None:
        while self.i < len(self.t):
            c = self.t[self.i]
            if c in " \t" or (sauts and c == "\n"):
                self.i += 1
            elif c == "#":
                while self.i < len(self.t) and self.t[self.i] != "\n":
                    self.i += 1
            else:
                break

    def fin_de_ligne(self) -> None:
        self.blancs()
        if self.i < len(self.t) and self.t[self.i] != "\n":
            raise self.erreur("caractères en trop après la valeur")

    # -- document
    def document(self) -> dict:
        racine: dict = {}
        courante = racine
        while True:
            self.blancs(sauts=True)
            if self.i >= len(self.t):
                return racine
            if self.t.startswith("[[", self.i):
                fin = self.t.find("]]", self.i)
                if fin < 0:
                    raise self.erreur("en-tête « [[...]] » non fermé")
                nom = self.t[self.i + 2:fin].strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]+", nom):
                    raise self.erreur(f"en-tête de table invalide : {nom!r}")
                self.i = fin + 2
                self.fin_de_ligne()
                liste = racine.setdefault(nom, [])
                if not isinstance(liste, list):
                    raise self.erreur(f"« {nom} » est déjà une valeur simple")
                courante = {}
                liste.append(courante)
                continue
            if self.t[self.i] == "[":
                raise self.erreur("seules les tables « [[terme]] » sont permises")
            cle_lue = self.cle()
            self.blancs()
            if self.i >= len(self.t) or self.t[self.i] != "=":
                raise self.erreur(f"« = » attendu après « {cle_lue} »")
            self.i += 1
            self.blancs()
            valeur = self.valeur()
            if cle_lue in courante:
                raise self.erreur(f"clé « {cle_lue} » donnée deux fois")
            courante[cle_lue] = valeur
            self.fin_de_ligne()

    def cle(self) -> str:
        trouve = re.compile(r"[A-Za-z0-9_-]+").match(self.t, self.i)
        if trouve:
            self.i = trouve.end()
            return trouve.group(0)
        if self.i < len(self.t) and self.t[self.i] in "\"'":
            return self.chaine()
        raise self.erreur("nom de clé attendu")

    def valeur(self):
        if self.i >= len(self.t):
            raise self.erreur("valeur attendue")
        c = self.t[self.i]
        if c in "\"'":
            return self.chaine()
        if c == "[":
            return self.tableau()
        if c == "{":
            return self.table_en_ligne()
        for mot, valeur in (("true", True), ("false", False)):
            if self.t.startswith(mot, self.i):
                self.i += len(mot)
                return valeur
        trouve = re.compile(r"[+-]?\d[\d_]*(\.\d[\d_]*)?([eE][+-]?\d+)?").match(self.t, self.i)
        if trouve:
            self.i = trouve.end()
            texte = trouve.group(0).replace("_", "")
            return float(texte) if (trouve.group(1) or trouve.group(2)) else int(texte)
        raise self.erreur("valeur illisible (chaîne entre guillemets, nombre, true/false, [ ] ou { } attendus)")

    def chaine(self) -> str:
        guillemet = self.t[self.i]
        if self.t.startswith(guillemet * 3, self.i):
            raise self.erreur("les chaînes sur plusieurs lignes ne sont pas permises")
        self.i += 1
        morceaux: list[str] = []
        while True:
            if self.i >= len(self.t) or self.t[self.i] == "\n":
                raise self.erreur("chaîne non fermée")
            c = self.t[self.i]
            if c == guillemet:
                self.i += 1
                return "".join(morceaux)
            if c == "\\" and guillemet == '"':
                suite = self.t[self.i + 1:self.i + 2]
                simples = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
                if suite in simples:
                    morceaux.append(simples[suite])
                    self.i += 2
                    continue
                if suite in ("u", "U"):
                    longueur = 4 if suite == "u" else 8
                    code = self.t[self.i + 2:self.i + 2 + longueur]
                    if not re.fullmatch(r"[0-9A-Fa-f]+", code or "") or len(code) != longueur:
                        raise self.erreur("échappement \\u invalide")
                    morceaux.append(chr(int(code, 16)))
                    self.i += 2 + longueur
                    continue
                raise self.erreur(f"échappement inconnu : \\{suite}")
            morceaux.append(c)
            self.i += 1

    def tableau(self) -> list:
        self.i += 1
        elements = []
        while True:
            self.blancs(sauts=True)
            if self.i >= len(self.t):
                raise self.erreur("tableau non fermé")
            if self.t[self.i] == "]":
                self.i += 1
                return elements
            elements.append(self.valeur())
            self.blancs(sauts=True)
            if self.i < len(self.t) and self.t[self.i] == ",":
                self.i += 1
                continue
            self.blancs(sauts=True)
            if self.i < len(self.t) and self.t[self.i] == "]":
                self.i += 1
                return elements
            raise self.erreur("« , » ou « ] » attendu dans le tableau")

    def table_en_ligne(self) -> dict:
        self.i += 1
        table: dict = {}
        self.blancs()
        if self.i < len(self.t) and self.t[self.i] == "}":
            self.i += 1
            return table
        while True:
            self.blancs()
            cle_lue = self.cle()
            self.blancs()
            if self.i >= len(self.t) or self.t[self.i] != "=":
                raise self.erreur(f"« = » attendu après « {cle_lue} »")
            self.i += 1
            self.blancs()
            if cle_lue in table:
                raise self.erreur(f"clé « {cle_lue} » donnée deux fois")
            table[cle_lue] = self.valeur()
            self.blancs()
            if self.i < len(self.t) and self.t[self.i] == ",":
                self.i += 1
                continue
            if self.i < len(self.t) and self.t[self.i] == "}":
                self.i += 1
                return table
            raise self.erreur("« , » ou « } » attendu dans la table")


def analyser_toml(texte: str) -> dict:
    return _Analyseur(texte).document()


def _texte(valeur, defaut: str = "") -> str:
    return " ".join(str(valeur).split()) if isinstance(valeur, (str, int, float)) else defaut


def _entier(valeur, defaut: int = 0) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def _faute_depuis(brut) -> Faute | None:
    if isinstance(brut, str):
        forme = _texte(brut)
        return Faute(forme) if forme else None
    if isinstance(brut, dict):
        forme = _texte(brut.get("forme", ""))
        if not forme:
            return None
        voisins = [_texte(v) for v in brut.get("voisins") or [] if _texte(v)]
        return Faute(forme, voisins, bool(brut.get("forcer", False)), max(0, _entier(brut.get("vu"))),
                     max(0, _entier(brut.get("reunions"))))
    return None


def depuis_donnees(donnees: dict, source: str = "") -> tuple[Vocabulaire, list[str]]:
    """Vocabulaire à partir d'un document analysé. Renvoie aussi les remarques
    de validation (valeurs inconnues ramenées au défaut, doublons...)."""
    remarques: list[str] = []
    if donnees.get("format", FORMAT) != FORMAT:
        raise ErreurFormat(f"ce n'est pas un vocabulaire de Scribouille (format « {donnees.get('format')} »)")
    version = _entier(donnees.get("version", VERSION_FORMAT), VERSION_FORMAT)
    if version > VERSION_FORMAT:
        raise ErreurFormat(f"version {version} plus récente que celle que sait lire cette application ({VERSION_FORMAT})")
    voc = Vocabulaire(nom=_texte(donnees.get("nom", "")), portee=_texte(donnees.get("portee", "personnel")),
                      langue=_texte(donnees.get("langue", "fr")) or "fr", version=VERSION_FORMAT)
    if voc.portee not in PORTEES:
        remarques.append(f"portée « {voc.portee} » inconnue, « personnel » retenu")
        voc.portee = "personnel"
    for rang, brut in enumerate(donnees.get("terme") or [], 1):
        if not isinstance(brut, dict):
            continue
        forme = _texte(brut.get("forme", ""))
        if not forme:
            remarques.append(f"terme {rang} sans « forme », ignoré")
            continue
        entree = Entree(forme=forme, source=source)
        categorie = _texte(brut.get("categorie", "autre")) or "autre"
        if categorie not in CATEGORIES:
            remarques.append(f"« {forme} » : catégorie « {categorie} » inconnue, « autre » retenu")
            categorie = "autre"
        entree.categorie = categorie
        for faute_brute in brut.get("fautes") or []:
            faute = _faute_depuis(faute_brute)
            if faute is None:
                continue
            if cle(faute.forme) == entree.cle:
                remarques.append(f"« {forme} » : faute identique à la forme correcte, ignorée")
                continue
            entree.ajouter_faute(faute)
        entree.prononciation = _texte(brut.get("prononciation", ""))
        entree.poids = min(POIDS_MAX, max(POIDS_MIN, _entier(brut.get("poids", 1), 1)))
        origine = _texte(brut.get("origine", "saisi")) or "saisi"
        if origine not in ORIGINES:
            remarques.append(f"« {forme} » : origine « {origine} » inconnue, « saisi » retenu")
            origine = "saisi"
        entree.origine = origine
        etat = _texte(brut.get("etat", "actif")) or "actif"
        if etat not in ETATS:
            remarques.append(f"« {forme} » : état « {etat} » inconnu, « propose » retenu")
            etat = "propose"
        entree.etat = etat
        entree.amorce = bool(brut.get("amorce", True))
        entree.rapprochement = bool(brut.get("rapprochement", True))
        entree.vu = max(0, _entier(brut.get("vu")))
        entree.reunions = max(0, _entier(brut.get("reunions")))
        entree.note = _texte(brut.get("note", ""))
        entree.ajoute = _texte(brut.get("ajoute", ""))
        voc.entrees.append(entree)
    # Doublons dans un même fichier : fusionnés, la dernière occurrence l'emporte.
    dedoublonne: dict[tuple[str, bool], Entree] = {}
    for entree in voc.entrees:
        k = (entree.cle, entree.etat == "propose")
        if k in dedoublonne:
            remarques.append(f"« {entree.forme} » présent deux fois, fusionné")
            _fusionner_dans(dedoublonne[k], entree)
        else:
            dedoublonne[k] = entree
    voc.entrees = list(dedoublonne.values())
    return voc, remarques


def lire_texte(texte: str, source: str = "") -> tuple[Vocabulaire, list[str]]:
    texte = texte.lstrip("\ufeff")
    if texte.lstrip().startswith("{"):
        # Import d'un export JSON (même modèle de données).
        try:
            donnees = json.loads(texte)
        except ValueError as exc:
            raise ErreurFormat(f"JSON illisible : {exc}") from exc
    else:
        donnees = analyser_toml(texte)
    return depuis_donnees(donnees, source)


def lire(chemin: Path | str) -> tuple[Vocabulaire, list[str]]:
    chemin = Path(chemin)
    try:
        texte = chemin.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ErreurFormat("le fichier n'est pas en UTF-8") from exc
    return lire_texte(texte, source=str(chemin))


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def _chaine(texte: str) -> str:
    echappe = (str(texte).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
               .replace("\t", "\\t").replace("\r", "\\r"))
    return f'"{echappe}"'


def _liste(valeurs: list[str]) -> str:
    return "[" + ", ".join(_chaine(v) for v in valeurs) + "]"


def _faute_toml(faute: Faute) -> str:
    if not (faute.voisins or faute.forcer or faute.vu or faute.reunions):
        return _chaine(faute.forme)
    morceaux = [f"forme = {_chaine(faute.forme)}"]
    if faute.voisins:
        morceaux.append(f"voisins = {_liste(faute.voisins)}")
    if faute.forcer:
        morceaux.append("forcer = true")
    if faute.vu:
        morceaux.append(f"vu = {int(faute.vu)}")
    if faute.reunions:
        morceaux.append(f"reunions = {int(faute.reunions)}")
    return "{ " + ", ".join(morceaux) + " }"


ENTETE_FICHIER = """# Vocabulaire de Scribouille (format 2).
#
# Un bloc [[terme]] par mot à bien écrire. Seuls les termes à l'état « actif »
# servent ; les « propose » attendent une relecture dans l'application, les
# « refuse » ne sont plus jamais proposés. Le fichier se modifie à la main :
# l'application le relit à chaque transcription.
#
#   forme         : la forme correcte, telle qu'elle doit s'afficher
#   categorie     : personne, societe, sigle, produit, metier, anglicisme, autre
#   fautes        : ce que le modèle écrit à la place, toujours ramené à la forme ;
#                   { forme = "...", voisins = ["...", "..."] } : seulement près de ces mots
#   prononciation : facultatif, aide le rapprochement phonétique
#   poids         : 1 à 5, priorité dans l'amorce soufflée au modèle
#   origine       : saisi, correction, compte_rendu, apprentissage, glossaire_v1, corrections_v1, import
#   etat          : actif, propose, refuse
"""


def ecrire_texte(voc: Vocabulaire, entete: bool = True) -> str:
    lignes = [ENTETE_FICHIER] if entete else []
    lignes += [f"format = {_chaine(FORMAT)}", f"version = {VERSION_FORMAT}"]
    if voc.nom:
        lignes.append(f"nom = {_chaine(voc.nom)}")
    lignes.append(f"portee = {_chaine(voc.portee or 'personnel')}")
    lignes.append(f"langue = {_chaine(voc.langue or 'fr')}")
    for e in voc.entrees:
        lignes += ["", "[[terme]]", f"forme = {_chaine(e.forme)}", f"categorie = {_chaine(e.categorie)}"]
        if e.fautes:
            rendus = [_faute_toml(f) for f in e.fautes]
            une_ligne = "fautes = [" + ", ".join(rendus) + "]"
            if len(une_ligne) <= 100:
                lignes.append(une_ligne)
            else:
                lignes.append("fautes = [")
                lignes += [f"  {r}," for r in rendus]
                lignes.append("]")
        if e.prononciation:
            lignes.append(f"prononciation = {_chaine(e.prononciation)}")
        if e.poids != 1:
            lignes.append(f"poids = {int(e.poids)}")
        lignes.append(f"origine = {_chaine(e.origine)}")
        lignes.append(f"etat = {_chaine(e.etat)}")
        if not e.amorce:
            lignes.append("amorce = false")
        if not e.rapprochement:
            lignes.append("rapprochement = false")
        if e.vu:
            lignes.append(f"vu = {int(e.vu)}")
        if e.reunions:
            lignes.append(f"reunions = {int(e.reunions)}")
        if e.note:
            lignes.append(f"note = {_chaine(e.note)}")
        if e.ajoute:
            lignes.append(f"ajoute = {_chaine(e.ajoute)}")
    return "\n".join(lignes) + "\n"


def ecrire(voc: Vocabulaire, chemin: Path | str | None = None) -> Path:
    """Écrit d'un bloc (fichier provisoire puis renommé) : jamais de fichier à moitié écrit."""
    cible = Path(chemin) if chemin else FICHIER_PERSONNEL
    cible.parent.mkdir(parents=True, exist_ok=True)
    provisoire = cible.with_name(cible.name + ".tmp")
    provisoire.write_text(ecrire_texte(voc), encoding="utf-8")
    os.replace(provisoire, cible)
    return cible


def en_donnees(voc: Vocabulaire) -> dict:
    """Même contenu en dictionnaire (export JSON, interface)."""
    return analyser_toml(ecrire_texte(voc, entete=False))


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def _fusionner_dans(cible: Entree, autre: Entree) -> None:
    """`autre`, plus prioritaire, complète et corrige `cible`."""
    for faute in autre.fautes:
        cible.ajouter_faute(faute)
    cible.forme = autre.forme
    if autre.categorie != "autre" or cible.categorie == "autre":
        cible.categorie = autre.categorie
    cible.prononciation = autre.prononciation or cible.prononciation
    cible.poids = autre.poids
    cible.amorce = autre.amorce
    cible.rapprochement = autre.rapprochement
    cible.vu = max(cible.vu, autre.vu)
    cible.reunions = max(cible.reunions, autre.reunions)
    cible.note = autre.note or cible.note
    cible.origine = autre.origine
    cible.source = autre.source or cible.source
    # Un refus est définitif ; sinon l'état du plus prioritaire.
    cible.etat = "refuse" if "refuse" in (cible.etat, autre.etat) else autre.etat


def fusionner(vocabulaires: list[Vocabulaire]) -> Vocabulaire:
    """Fusionne, du moins prioritaire au plus prioritaire. Les propositions
    restent à part des termes décidés (actifs ou refusés) de même forme."""
    resultat = Vocabulaire(nom="fusion", portee="personnel")
    index: dict[tuple[str, bool], Entree] = {}
    rang: dict[int, int] = {}
    for position, voc in enumerate(vocabulaires):
        for entree in voc.entrees:
            k = (entree.cle, entree.etat == "propose")
            if k in index:
                _fusionner_dans(index[k], entree)
            else:
                index[k] = entree.copie()
                resultat.entrees.append(index[k])
            rang[id(index[k])] = position
    # Une proposition déjà décidée ailleurs (acceptée telle quelle, ou refusée)
    # n'a plus lieu d'être.
    decides = {e.cle: e for e in resultat.entrees if e.etat != "propose"}
    garde = []
    for e in resultat.entrees:
        if e.etat == "propose" and e.cle in decides:
            decide = decides[e.cle]
            if decide.etat == "refuse":
                continue
            nouvelles = [f for f in e.fautes if decide.faute(f.forme) is None]
            if not nouvelles:
                continue
            e.fautes = nouvelles
        garde.append(e)
    resultat.entrees = garde
    # Conflits : une même faute active ramenée à deux formes différentes.
    vues: dict[str, Entree] = {}
    for e in sorted((e for e in resultat.entrees if e.actif), key=lambda e: rang.get(id(e), 0),
                    reverse=True):
        for f in list(e.fautes):
            k = cle(f.forme) + "|" + "|".join(sorted(cle(v) for v in f.voisins))
            if k in vues and vues[k].cle != e.cle:
                resultat.conflits.append((f.forme, vues[k].forme, e.forme))
                e.fautes.remove(f)
            else:
                vues[k] = e
    return resultat


# ---------------------------------------------------------------------------
# Migration depuis le format 1
# ---------------------------------------------------------------------------

def _categorie_devinee(forme: str) -> str:
    return "sigle" if lexique.est_sigle(forme) else "autre"


def depuis_v1(glossaire: str, corrections: str, source: str = "format 1") -> Vocabulaire:
    """
    Convertit le glossaire et les corrections du format 1, sans rien perdre.

    - Chaque terme du glossaire devient un terme actif, dans le même ordre (la
      sélection de l'amorce garde l'ordre à poids égal, comme le format 1).
    - Chaque règle « a => b » devient une faute de la forme « b ». Si « b »
      n'était pas au glossaire, le terme créé n'est PAS soufflé au modèle
      (`amorce = false`) : la conversion ne change pas ce qui était fait.
    - Une règle dont la forme fautive n'est faite que de mots courants
      (« mon entreprise ») était appliquée partout : elle le reste (`forcer`),
      et l'application le signale comme risquée.
    """
    from . import vocabulaire as v1

    voc = Vocabulaire(nom="Converti du format 1", portee="personnel")
    for terme in v1.termes(glossaire):
        if voc.chercher(terme) is None:
            voc.entrees.append(Entree(terme, _categorie_devinee(terme), origine="glossaire_v1", source=source))
    regles, _erreurs = v1.analyser_corrections(corrections)
    section = False
    titres = v1.titres_section_connus()
    apprises: set[str] = set()
    for ligne in corrections.splitlines():
        if ligne.strip() in titres:
            section = True
        elif section and "=>" in ligne and not ligne.strip().startswith("#"):
            apprises.add(cle(ligne.partition("=>")[0]))
    for regle in regles:
        entree = voc.chercher(regle.cible)
        if entree is None:
            origine = "correction" if cle(regle.source) in apprises else "corrections_v1"
            entree = Entree(regle.cible, _categorie_devinee(regle.cible), origine=origine, amorce=False,
                            source=source)
            voc.entrees.append(entree)
        courant = lexique.tous_courants(lexique.mots_de(regle.source))
        entree.ajouter_faute(Faute(regle.source, forcer=courant))
    return voc


def v1_a_du_contenu(glossaire: str, corrections: str) -> bool:
    from . import vocabulaire as v1

    return bool(v1.termes(glossaire) or v1.analyser_corrections(corrections)[0])


def convertir_v1_sur_disque() -> dict:
    """
    Intègre le glossaire et les corrections du format 1 au fichier personnel,
    puis remet les deux fichiers au modèle livré (exemples en commentaire),
    avec une copie de l'ancien contenu à côté. Rien n'est perdu.
    """
    from . import vocabulaire as v1

    glossaire, corrections = v1.lire_glossaire(), v1.lire_corrections()
    if not v1_a_du_contenu(glossaire, corrections):
        return {"ok": True, "convertis": 0}
    ancien = depuis_v1(glossaire, corrections)
    personnel = charger_personnel()
    for entree in ancien.entrees:
        entree.source = ""
        existante = personnel.chercher(entree.forme, etat=None)
        if existante is not None and existante.etat != "propose":
            for f in entree.fautes:
                existante.ajouter_faute(f)
            existante.amorce = existante.amorce or entree.amorce
        else:
            personnel.entrees.append(entree)
    ecrire(personnel)
    for cible, contenu in ((chemins.FICHIER_VOCABULAIRE, glossaire), (chemins.FICHIER_CORRECTIONS, corrections)):
        modele = chemins.MODELES_FICHIERS_EXEMPLE.get(cible)
        try:
            cible.with_name(cible.stem + "-format1-sauvegarde.txt").write_text(contenu, encoding="utf-8")
            if modele is not None and modele.is_file() and modele != cible:
                cible.write_text(modele.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                cible.write_text("", encoding="utf-8")
        except OSError as exc:
            journal.attention("Format 1 non remis à zéro (%s) : %s", cible.name, exc)
    journal.info("Vocabulaire : %s termes du format 1 convertis", len(ancien.entrees))
    return {"ok": True, "convertis": len(ancien.entrees)}


# ---------------------------------------------------------------------------
# Vocabulaire effectif : format 1 + fichiers du format 2
# ---------------------------------------------------------------------------

def charger_personnel() -> Vocabulaire:
    if not FICHIER_PERSONNEL.is_file():
        return Vocabulaire(nom="Vocabulaire personnel", portee="personnel")
    try:
        return lire(FICHIER_PERSONNEL)[0]
    except (OSError, ErreurFormat) as exc:
        journal.attention("Vocabulaire personnel illisible : %s", exc)
        raise


def fichiers_partages(config: dict | None = None) -> list[Path]:
    if config is None:
        try:
            from . import config as config_module

            config = config_module.charger()
        except Exception:  # pragma: no cover
            config = {}
    return [Path(p) for p in (config.get("vocabulaires_partages") or []) if str(p).strip()]


def effectif(config: dict | None = None, avec_v1: bool = True) -> tuple[Vocabulaire, list[str]]:
    """
    Vocabulaire qui sert à la transcription : le format 1 encore en place
    (s'il n'a pas été converti), les fichiers partagés (équipe, projet, dans
    l'ordre de la configuration), puis le fichier personnel, qui a le dernier
    mot. Renvoie aussi les problèmes rencontrés (fichier illisible, conflit),
    en français, sans jamais lever : un vocabulaire cassé ne bloque pas une
    transcription.
    """
    from . import vocabulaire as v1

    couches: list[Vocabulaire] = []
    problemes: list[str] = []
    if avec_v1:
        glossaire, corrections = v1.lire_glossaire(), v1.lire_corrections()
        if v1_a_du_contenu(glossaire, corrections):
            couches.append(depuis_v1(glossaire, corrections))
    for chemin in fichiers_partages(config):
        try:
            couches.append(lire(chemin)[0])
        except (OSError, ErreurFormat) as exc:
            problemes.append(f"{chemin.name} : {exc}")
    if FICHIER_PERSONNEL.is_file():
        try:
            couches.append(lire(FICHIER_PERSONNEL)[0])
        except (OSError, ErreurFormat) as exc:
            problemes.append(f"{FICHIER_PERSONNEL.name} : {exc}")
    voc = fusionner(couches)
    for faute, gardee, ecartee in voc.conflits:
        problemes.append(f"conflit : « {faute} » ramené à « {gardee} » (et non « {ecartee} »)")
    return voc, problemes


# ---------------------------------------------------------------------------
# Revue des propositions
# ---------------------------------------------------------------------------

def aujourdhui() -> str:
    return date.today().isoformat()


def importer_propositions(voc: Vocabulaire, propositions: Vocabulaire) -> dict:
    """
    Verse des propositions (sortie de l'apprentissage, autre fichier) dans un
    vocabulaire, à l'état « propose ». Ce qui est déjà actif à l'identique, ou
    refusé, n'est pas reproposé. Rien ne devient actif ici.
    """
    ajoutees = ignorees = 0
    for entree in propositions.entrees:
        if entree.etat == "refuse":
            # Une piste écartée à la relecture du fichier reste écartée : elle
            # ne sera plus reproposée (sauf si le terme est déjà actif ici).
            if voc.chercher(entree.forme, etat=None) is None:
                refus = entree.copie()
                refus.source = ""
                voc.entrees.append(refus)
            continue
        decide = voc.chercher(entree.forme, etat="actif")
        refuse = voc.chercher(entree.forme, etat="refuse")
        if refuse is not None:
            ignorees += 1
            continue
        nouvelles = [f for f in entree.fautes if decide is None or decide.faute(f.forme) is None]
        if decide is not None and not nouvelles:
            ignorees += 1
            continue
        proposition = entree.copie()
        proposition.etat = "propose"
        proposition.fautes = [f.copie() for f in nouvelles] if decide is not None else proposition.fautes
        proposition.source = ""
        proposition.ajoute = proposition.ajoute or aujourdhui()
        existante = voc.chercher(entree.forme, etat="propose")
        if existante is not None:
            for f in proposition.fautes:
                existante.ajouter_faute(f)
            existante.vu = max(existante.vu, proposition.vu)
            existante.reunions = max(existante.reunions, proposition.reunions)
        else:
            voc.entrees.append(proposition)
        ajoutees += 1
    return {"ajoutees": ajoutees, "ignorees": ignorees}


def accepter(voc: Vocabulaire, forme: str, modification: dict | None = None) -> bool:
    """Une proposition devient active (fusionnée dans le terme actif s'il existe)."""
    proposition = voc.chercher(forme, etat="propose")
    if proposition is None:
        return False
    if modification:
        appliquer_modification(proposition, modification)
    actif = voc.chercher(proposition.forme, etat="actif")
    voc.entrees.remove(proposition)
    if actif is not None:
        for f in proposition.fautes:
            actif.ajouter_faute(f)
        actif.vu = max(actif.vu, proposition.vu)
        actif.reunions = max(actif.reunions, proposition.reunions)
    else:
        proposition.etat = "actif"
        voc.entrees.append(proposition)
    return True


def refuser(voc: Vocabulaire, forme: str) -> bool:
    """Une proposition refusée est gardée comme telle : elle ne revient plus."""
    proposition = voc.chercher(forme, etat="propose")
    if proposition is None:
        return False
    deja = voc.chercher(forme, etat="refuse")
    voc.entrees.remove(proposition)
    if deja is not None:
        for f in proposition.fautes:
            deja.ajouter_faute(f)
    elif voc.chercher(forme, etat="actif") is None:
        proposition.etat = "refuse"
        voc.entrees.append(proposition)
    return True


def appliquer_modification(entree: Entree, modification: dict) -> list[str]:
    """Modifie une entrée depuis l'interface. Renvoie les refus éventuels."""
    refus: list[str] = []
    if "forme" in modification:
        forme = _texte(modification["forme"])
        if forme:
            entree.forme = forme
        else:
            refus.append("forme vide")
    if "categorie" in modification:
        categorie = _texte(modification["categorie"])
        if categorie in CATEGORIES:
            entree.categorie = categorie
    if "fautes" in modification:
        fautes = []
        for brut in modification["fautes"] or []:
            faute = _faute_depuis(brut)
            if faute is not None and cle(faute.forme) != cle(entree.forme):
                fautes.append(faute)
        entree.fautes = []
        for f in fautes:
            entree.ajouter_faute(f)
    if "poids" in modification:
        entree.poids = min(POIDS_MAX, max(POIDS_MIN, _entier(modification["poids"], entree.poids)))
    if "prononciation" in modification:
        entree.prononciation = _texte(modification["prononciation"])
    if "amorce" in modification:
        entree.amorce = bool(modification["amorce"])
    if "note" in modification:
        entree.note = _texte(modification["note"])
    return refus


def faute_risquee(faute: Faute) -> bool:
    """Faute « toujours » faite de mots courants : remplacée partout seulement si forcée."""
    return not faute.voisins and lexique.tous_courants(lexique.mots_de(faute.forme))


def resume(voc: Vocabulaire) -> dict:
    """Comptes par état et par catégorie : jamais un terme."""
    par_categorie = {c: 0 for c in CATEGORIES}
    for e in voc.actives():
        par_categorie[e.categorie] = par_categorie.get(e.categorie, 0) + 1
    return {
        "actifs": len(voc.actives()), "proposes": len(voc.par_etat("propose")),
        "refuses": len(voc.par_etat("refuse")), "categories": par_categorie,
        "fautes": sum(len(e.fautes) for e in voc.actives()),
        "fautes_risquees": sum(1 for e in voc.actives() for f in e.fautes if faute_risquee(f) and not f.forcer),
        "conflits": len(voc.conflits),
    }


def normaliser_unicode(texte: str) -> str:
    return unicodedata.normalize("NFC", texte)
