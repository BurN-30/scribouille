"""
Le vocabulaire au travail : trois étages, mesurables séparément.

(a) AMORCE. Les termes sont soufflés au décodeur comme un texte précédent
    (`initial_prompt`). Les deux moteurs n'offrent rien d'autre : ni
    CTranslate2 (`Whisper.generate` : `suppress_tokens` seulement), ni OpenVINO
    GenAI 2026.4 (`initial_prompt` pour la première fenêtre d'un appel,
    `hotwords` pour toutes) n'ont de biais de vocabulaire par jeton. La place
    est bornée à 224 jetons (moitié du contexte de 448). Quand le vocabulaire
    déborde, on choisit : d'abord ce qui concerne CE fichier (nom du fichier,
    texte de la fenêtre précédente), puis le poids, puis l'usage observé. Les
    termes les plus importants sont placés en DERNIER : Whisper ne lit que la
    fin d'une amorce trop longue, et ce qui précède immédiatement l'audio pèse
    le plus (guide de prompting de Whisper, OpenAI).

    Répartition sur les fenêtres : l'application appelle OpenVINO une fois par
    fenêtre de 30 s, l'amorce peut donc changer d'une fenêtre à l'autre
    (`AmorceDynamique.pour_fenetre`). CTranslate2 la reçoit une fois (fenêtre
    par fenêtre) ou à chaque passage (par lots).

(b) CORRECTION APRÈS COUP, déterministe et journalisée. Dans l'ordre :
    fautes listées (toujours, ou seulement près de leurs voisins), graphie
    (« rgpd » vers « RGPD »), puis rapprochement phonétique borné. Garde-fous :
    une suite de mots courants n'est jamais remplacée sans contexte (sauf faute
    explicitement forcée), un terme de moins de quatre sons n'est jamais
    rapproché, une forme déjà juste ou appartenant à un autre terme n'est pas
    touchée, une égalité entre deux termes ne tranche rien. Chaque
    remplacement est noté (segment, position, avant, après, règle) pour être
    montré et annulé dans la vue de relecture.

(c) REMISE EN FORME PAR UN PETIT MODÈLE DE LANGUE : non codée ici, voir le
    rapport (étude, effort, risques).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import langues, lexique
from .vocabulaire_v2 import Entree, Faute, Vocabulaire, cle

# ---------------------------------------------------------------------------
# (a) Amorce
# ---------------------------------------------------------------------------


def _jetons(texte: str, tokeniseur=None) -> int:
    from .vocabulaire import _compter_jetons

    return _compter_jetons(texte, tokeniseur)


def _pertinence(entree: Entree, contexte_mots: set[str], contexte_cles: set[str]) -> int:
    """2 : le terme ou une de ses fautes est dans le contexte ; 1 : un son voisin ; 0 sinon."""
    if not contexte_mots:
        return 0
    formes = [entree.forme] + [f.forme for f in entree.fautes]
    for forme in formes:
        mots = lexique.mots_de(forme)
        significatifs = [m for m in mots if not lexique.est_courant(m) or len(mots) == 1]
        if significatifs and all(m in contexte_mots for m in significatifs):
            return 2
    k = lexique.cle_phonetique(entree.forme)
    return 1 if len(k) >= 5 and k in contexte_cles else 0


def _cles_contexte(mots: list[str]) -> set[str]:
    cles: set[str] = set()
    for n in (1, 2, 3):
        for i in range(len(mots) - n + 1):
            cles.add(lexique.cle_phonetique(" ".join(mots[i:i + n])))
    return cles


def selectionner(voc: Vocabulaire, tokeniseur=None, langue: str | None = None, contexte: str = "",
                 budget: int | None = None) -> dict:
    """
    Choisit les termes de l'amorce dans le budget de jetons.

    Ordre de choix : pertinence pour le fichier (contexte), poids, usage
    observé (vu), ordre du fichier. Ordre d'écriture : l'inverse, le plus
    important juste avant l'audio.
    """
    from .vocabulaire import LIMITE_JETONS_AMORCE, MARGE_JETONS, entete_amorce

    entete = entete_amorce(langue)
    budget = budget if budget is not None else LIMITE_JETONS_AMORCE - MARGE_JETONS
    candidats = [e for e in voc.actives() if e.amorce]
    if not candidats:
        return {"amorce": "", "nb_termes": 0, "nb_retenus": 0, "tronque": False, "jetons": 0,
                "retenus": [], "pertinents": 0, "message": langues.t("voc.glossaire_vide")}
    mots = lexique.mots_de(contexte)
    contexte_mots, contexte_cles = set(mots), _cles_contexte(mots) if mots else set()
    notes = []
    for rang, e in enumerate(candidats):
        pertinence = _pertinence(e, contexte_mots, contexte_cles)
        notes.append(((pertinence, e.poids, math.log1p(e.vu), -rang), e))
    notes.sort(key=lambda x: x[0], reverse=True)
    retenus: list[Entree] = []
    for _note, e in notes:
        essai = [x.forme for x in reversed(retenus + [e])]
        if _jetons(entete + ", ".join(essai) + ".", tokeniseur) > budget:
            continue
        retenus.append(e)
    formes = [e.forme for e in reversed(retenus)]
    amorce = entete + ", ".join(formes) + "." if formes else ""
    jetons = _jetons(amorce, tokeniseur) if amorce else 0
    tronque = len(retenus) < len(candidats)
    from .vocabulaire import LIMITE_JETONS_AMORCE as limite

    if not retenus:
        message = langues.t("voc.premier_trop_long")
    elif tronque:
        message = langues.t("voc.amorce_tronquee", retenus=len(retenus), total=len(candidats),
                            jetons=jetons, limite=limite)
    else:
        message = langues.t("voc.amorce_ok", retenus=len(retenus), jetons=jetons, limite=limite)
    return {"amorce": amorce, "nb_termes": len(candidats), "nb_retenus": len(retenus), "tronque": tronque,
            "jetons": jetons, "retenus": formes,
            "pertinents": sum(1 for (p, *_r), e in notes if p and e in retenus), "message": message}


class AmorceDynamique(str):
    """
    Une amorce qui reste une chaîne (le moteur qui l'ignore s'en sert telle
    quelle) et sait se refaire pour une fenêtre donnée, au vu du texte de la
    fenêtre précédente. Utile seulement quand le vocabulaire déborde du budget.
    """

    def __new__(cls, info: dict, voc: Vocabulaire, tokeniseur=None, langue: str | None = None,
                contexte: str = ""):
        objet = super().__new__(cls, info["amorce"])
        objet.info = info
        objet._voc = voc
        objet._tokeniseur = tokeniseur
        objet._langue = langue
        objet._contexte = contexte
        objet.changements = 0
        return objet

    @property
    def dynamique(self) -> bool:
        return bool(self.info.get("tronque"))

    def pour_fenetre(self, texte_precedent: str = "") -> str:
        if not self.dynamique or not texte_precedent:
            return str(self)
        info = selectionner(self._voc, self._tokeniseur, self._langue,
                            contexte=f"{self._contexte} {texte_precedent}")
        if info["amorce"] != str(self):
            self.changements += 1
        return info["amorce"]


def amorce(voc: Vocabulaire, tokeniseur=None, langue: str | None = None, contexte: str = "") -> AmorceDynamique:
    info = selectionner(voc, tokeniseur, langue, contexte)
    return AmorceDynamique(info, voc, tokeniseur, langue, contexte)


# ---------------------------------------------------------------------------
# (b) Correction après coup
# ---------------------------------------------------------------------------

#: Mots de part et d'autre où chercher les voisins d'une faute en contexte.
FENETRE_VOISINS = 6
#: Catégories ouvertes au rapprochement phonétique (les termes métier et les
#: anglicismes ressemblent trop souvent à des mots courants).
CATEGORIES_RAPPROCHEES = ("personne", "societe", "sigle", "produit", "autre")


@dataclass
class _Motif:
    entree: Entree
    mots: list[str]
    faute: Faute | None      # None : la forme elle-même (graphie)
    regle: str               # « faute », « contexte », « graphie »
    forcee: bool = False     # graphie appliquée même à des mots courants


@dataclass
class _Phonetique:
    entree: Entree
    cle: str
    nb_mots: int
    tolerance: int


class Correcteur:
    """Moteur de correction, préparé une fois pour un vocabulaire."""

    def __init__(self, voc: Vocabulaire, rapprochement: bool = True):
        self.motifs: list[_Motif] = []
        self.phonetiques: list[_Phonetique] = []
        self.formes_justes: set[tuple[str, ...]] = set()
        self.ignorees_risquees = 0
        for e in voc.actives():
            mots_forme = lexique.mots_de(e.forme)
            if not mots_forme:
                continue
            self.formes_justes.add(tuple(mots_forme))
            graphie_forcee = False
            for f in e.fautes:
                mots = lexique.mots_de(f.forme)
                if tuple(mots) == tuple(mots_forme):
                    # Même mots, autre casse, forcée : « pierre => Pierre » du
                    # format 1 s'appliquait partout, il s'applique toujours.
                    graphie_forcee = graphie_forcee or f.forcer
                    continue
                if not mots:
                    continue
                if not f.voisins and not f.forcer and lexique.tous_courants(mots):
                    # Garde-fou : une suite de mots courants n'est jamais
                    # remplacée sans contexte. La faute reste dans le fichier,
                    # l'application la signale « risquée ».
                    self.ignorees_risquees += 1
                    continue
                self.motifs.append(_Motif(e, mots, f, "contexte" if f.voisins else "faute"))
            # Graphie : même mots, autre casse ou accents (« rgpd », « kubernetes »).
            self.motifs.append(_Motif(e, mots_forme, None, "graphie", graphie_forcee))
            if rapprochement and e.rapprochement and e.categorie in CATEGORIES_RAPPROCHEES:
                sources = [e.forme] + ([e.prononciation] if e.prononciation else [])
                if lexique.est_sigle(e.forme):
                    sources.append(lexique.epeler(e.forme))
                for source in sources:
                    k = lexique.cle_phonetique(source)
                    tol = lexique.tolerance(k)
                    if tol >= 0:
                        self.phonetiques.append(_Phonetique(e, k, max(1, len(lexique.mots_de(source))), tol))
        # Les motifs les plus longs d'abord : « martin le brun » avant « martin ».
        self.motifs.sort(key=lambda m: len(m.mots), reverse=True)
        self._par_premier: dict[str, list[_Motif]] = {}
        for m in self.motifs:
            self._par_premier.setdefault(m.mots[0], []).append(m)

    # -- outils
    @staticmethod
    def _voisins_presents(mots: list[str], debut: int, fin: int, voisins: list[str]) -> bool:
        zone = set(mots[max(0, debut - FENETRE_VOISINS):debut]) | set(mots[fin:fin + FENETRE_VOISINS])
        for voisin in voisins:
            morceaux = lexique.mots_de(voisin)
            if morceaux and all(m in zone for m in morceaux):
                return True
        return False

    def _forme_affichee(self, entree: Entree, original: str, en_tete_de_phrase: bool) -> str:
        forme = entree.forme
        if en_tete_de_phrase and forme[:1].islower() and original[:1].isupper():
            return forme[:1].upper() + forme[1:]
        return forme

    # -- correction d'un texte
    def corriger_texte(self, texte: str) -> tuple[str, list[dict]]:
        """Corrige un texte (un segment). Renvoie le texte et les remplacements,
        positions comptées dans le texte RENDU, de gauche à droite."""
        jetons = lexique.decouper(texte)
        mots = [j[0] for j in jetons]
        if not mots:
            return texte, []
        trouves: list[tuple[int, int, Entree, str, int]] = []   # début, fin (mots), entrée, règle, distance
        occupe = [False] * len(mots)
        # Où la forme juste d'un terme est déjà écrite (à la casse près) : une
        # faute de CE terme qui la chevauche n'est pas appliquée. Sans cela,
        # « réseaux » ramené à « réseaux sociaux » ajoutait un « sociaux » de
        # plus à « Réseaux sociaux » en tête de phrase.
        formes_presentes: dict[str, list[tuple[int, int]]] = {}
        for motif in self.motifs:
            if motif.regle != "graphie":
                continue
            n = len(motif.mots)
            for k in range(len(mots) - n + 1):
                if mots[k:k + n] == motif.mots:
                    formes_presentes.setdefault(motif.entree.cle, []).append((k, k + n))
        # 1. Fautes listées et graphie.
        i = 0
        while i < len(mots):
            pris = False
            for motif in self._par_premier.get(mots[i], ()):
                n = len(motif.mots)
                if mots[i:i + n] != motif.mots or any(occupe[i:i + n]):
                    continue
                if motif.regle == "contexte" and not self._voisins_presents(mots, i, i + n, motif.faute.voisins):
                    continue
                if motif.regle != "graphie" and any(
                        a < i + n and i < b for a, b in formes_presentes.get(motif.entree.cle, ())):
                    continue
                if motif.regle == "graphie":
                    original = texte[jetons[i][1]:jetons[i + n - 1][2]]
                    if original == motif.entree.forme or lexique.sans_accents(original) == motif.entree.forme:
                        # Déjà juste : on réserve la place, rien à changer.
                        for k in range(i, i + n):
                            occupe[k] = True
                        pris = True
                        i += n
                        break
                    if not motif.forcee and lexique.tous_courants(motif.mots) \
                            and not lexique.est_sigle(motif.entree.forme) \
                            and not (motif.entree.categorie == "personne" and i > 0
                                     and mots[i - 1] in lexique.CIVILITES):
                        # « pierre » n'est pas toujours « Pierre » ; « madame
                        # vallée », si.
                        continue
                trouves.append((i, i + n, motif.entree, motif.regle, 0))
                for k in range(i, i + n):
                    occupe[k] = True
                pris = True
                i += n
                break
            if not pris:
                i += 1
        # 2. Rapprochement phonétique, sur ce qui reste.
        if self.phonetiques:
            trouves += self._rapprocher(mots, occupe)
        if not trouves:
            return texte, []
        trouves.sort(key=lambda t: t[0])
        morceaux: list[str] = []
        remplacements: list[dict] = []
        curseur = 0
        for debut, fin, entree, regle, dist in trouves:
            c1, c2 = jetons[debut][1], jetons[fin - 1][2]
            original = texte[c1:c2]
            en_tete = texte[:c1].rstrip()[-1:] in ("", ".", "!", "?", "…")
            nouveau = self._forme_affichee(entree, original, en_tete)
            if nouveau == original:
                continue
            morceaux.append(texte[curseur:c1])
            position = sum(len(m) for m in morceaux)
            morceaux.append(nouveau)
            curseur = c2
            remplacements.append({"o": position, "a": original, "b": nouveau, "terme": entree.forme,
                                  "categorie": entree.categorie, "regle": regle, "distance": dist})
        morceaux.append(texte[curseur:])
        return "".join(morceaux), remplacements

    def _index_phonetique(self) -> dict[int, dict[int, list[_Phonetique]]]:
        if getattr(self, "_index", None) is None:
            self._index: dict[int, dict[int, list[_Phonetique]]] = {}
            for p in self.phonetiques:
                self._index.setdefault(p.nb_mots, {}).setdefault(len(p.cle), []).append(p)
        return self._index

    def _rapprocher(self, mots: list[str], occupe: list[bool]) -> list[tuple[int, int, Entree, str, int]]:
        candidats: list[tuple] = []   # (distance, -longueur, début, fin, entrée)
        resultats = []
        index = self._index_phonetique()
        longueurs = sorted(index)
        for i in range(len(mots)):
            for longueur_terme in longueurs:
                for n in range(max(1, longueur_terme - 1), longueur_terme + 2):
                    j = i + n
                    if j > len(mots) or any(occupe[i:j]):
                        continue
                    morceau = mots[i:j]
                    if tuple(morceau) in self.formes_justes or any(m.isdigit() for m in morceau):
                        continue
                    if lexique.tous_courants(morceau):
                        continue
                    k = lexique.cle_phonetique(" ".join(morceau))
                    if len(k) < 4:
                        continue
                    meilleurs: list[tuple[int, Entree]] = []
                    par_taille = index[longueur_terme]
                    for taille in range(len(k) - 4, len(k) + 5):
                        for p in par_taille.get(taille, ()):
                            d = lexique.distance(k, p.cle, p.tolerance)
                            if d <= p.tolerance:
                                meilleurs.append((d, p.entree))
                    if not meilleurs:
                        continue
                    meilleurs.sort(key=lambda x: x[0])
                    d0 = meilleurs[0][0]
                    termes = {e.cle for d, e in meilleurs if d == d0}
                    if len(termes) > 1:
                        continue   # deux termes aussi proches : on ne tranche pas
                    entree = meilleurs[0][1]
                    if " ".join(morceau) == cle(entree.forme):
                        continue
                    candidats.append((d0, -(j - i), i, j, entree))
        # Les meilleurs d'abord, sans chevauchement.
        candidats.sort(key=lambda c: (c[0], c[1], c[2]))
        pris = list(occupe)
        for d, _l, i, j, entree in candidats:
            if any(pris[i:j]):
                continue
            for k in range(i, j):
                pris[k] = True
            resultats.append((i, j, entree, "rapprochement", d))
        return resultats

    def corriger_segments(self, segments) -> list[dict]:
        """Corrige des segments sur place (attribut `texte`, ou clé « t »).
        Renvoie le journal : un élément par remplacement, avec le rang du segment."""
        journal_remplacements: list[dict] = []
        for rang, segment in enumerate(segments):
            est_dict = isinstance(segment, dict)
            texte = segment.get("t", "") if est_dict else segment.texte
            nouveau, remplacements = self.corriger_texte(texte)
            if not remplacements:
                continue
            if est_dict:
                segment["t"] = nouveau
            else:
                segment.texte = nouveau
            debut = float(segment.get("d", 0) if est_dict else getattr(segment, "debut", 0.0))
            for r in remplacements:
                journal_remplacements.append({"s": rang, "d": round(debut, 2), **r})
        return journal_remplacements


def compter_par_regle(remplacements: list[dict]) -> dict[str, int]:
    comptes: dict[str, int] = {}
    for r in remplacements:
        comptes[r["regle"]] = comptes.get(r["regle"], 0) + 1
    return comptes


def annuler(texte: str, remplacement: dict) -> str | None:
    """Défait un remplacement dans le texte d'un segment, ou None s'il a bougé."""
    position, avant, apres = int(remplacement.get("o", -1)), remplacement.get("a", ""), remplacement.get("b", "")
    if position >= 0 and texte[position:position + len(apres)] == apres:
        return texte[:position] + avant + texte[position + len(apres):]
    trouve = texte.find(apres)
    if trouve < 0:
        return None
    return texte[:trouve] + avant + texte[trouve + len(apres):]
