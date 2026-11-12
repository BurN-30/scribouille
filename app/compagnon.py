"""
Fichier compagnon d'une transcription : « nom-de-la-sortie.json ».

Le fichier texte est fait pour être lu par un humain, il ne peut pas porter la
confiance mot à mot sans devenir illisible. Ces données vivent donc à côté, dans
un petit fichier JSON de même nom, écrit en même temps que le `.txt`.

Il sert à la vue de lecture : rouvrir une transcription six mois plus tard et
retrouver les mots que le modèle a mal entendus, sans relancer le calcul.

Le compagnon est FACULTATIF. Une transcription produite par une version
antérieure, ou avec l'option coupée, s'ouvre normalement, simplement sans
surlignage : `app/lecture.py` se rabat alors sur le fichier texte.

--------------------------------------------------------------------------
Structure, version 1
--------------------------------------------------------------------------

    {
      "format": "scribouille-transcription",
      "version": 1,
      "produit_par": "Scribouille 2.1.0",
      "source": {
        "nom": "reunion.m4a",
        "chemin": "C:/.../reunion.m4a",
        "duree": 3612.4
      },
      "transcription": {
        "date": "2026-08-18T09:41:12",
        "modele": "large-v3",
        "langue": "fr",
        "temps_calcul": 4180.2,
        "nb_locuteurs": 3,
        "corrections_appliquees": 12
      },
      "seuils": {"faible": 0.6, "tres_faible": 0.35},
      "segments": [
        {
          "d": 0.0,                    début du segment, en secondes
          "f": 3.24,                   fin du segment
          "l": "Locuteur 1",           étiquette de locuteur, absente si aucune
          "t": "Bonjour à tous.",      texte du segment
          "m": [                       mots, absents si le moteur n'en a pas donné
            {"t": "Bonjour", "d": 0.12, "f": 0.58, "p": 0.98},
            ...                        p = probabilité du mot, de 0 à 1
          ]
        }
      ]
    }

Les clés des mots sont courtes à dessein : une heure de réunion représente
environ neuf mille mots, soit à peu près 400 Ko de compagnon avec ces clés,
contre plus du double avec des noms complets. Le reste du fichier, lu par des
humains, garde des noms explicites.

Toute lecture est défensive : un compagnon absent, tronqué, écrit par une
version plus récente ou simplement illisible n'est jamais une erreur, il est
ignoré et la vue de lecture se rabat sur le texte.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from . import VERSION, journal

FORMAT = "scribouille-transcription"

#: Marqueur écrit jusqu'à la version 2.3.3, sous l'ancien nom de l'application.
#: Il reste ACCEPTÉ en lecture : les compagnons déjà produits doivent continuer
#: de s'ouvrir dans la vue de relecture, le renommage ne regarde qu'eux.
FORMAT_HISTORIQUE = "whiscribe-transcription"

FORMATS_LUS = (FORMAT, FORMAT_HISTORIQUE)

VERSION_FORMAT = 1

#: Seuils de confiance retenus pour le surlignage.
#:
#: Mesurés sur du français de réunion, le même enregistrement passé dans deux
#: modèles (harnais `outils/verifier_chaine_lecture.py`) :
#:
#:              médiane   sous 0,50   sous 0,30
#:   tiny         0,91      11,5 %       3,1 %
#:   small        0,99       2,8 %       0,8 %
#:
#: Marquer sous 0,50 signale donc environ un mot sur dix avec le modèle le plus
#: faible, et un sur trente-cinq avec un modèle correct, qui est le cas d'usage
#: normal. C'est le bon compromis : assez pour attirer l'œil sur les passages à
#: réécouter, assez peu pour que la page ne soit pas bariolée. En dessous de
#: 0,30, le doute est sérieux et la marque plus nette.
#:
#: Ces valeurs sont écrites dans chaque compagnon : une transcription ancienne
#: garde les seuils avec lesquels elle a été relue la première fois.
SEUIL_FAIBLE = 0.50
SEUIL_TRES_FAIBLE = 0.30


def chemin_pour(chemin_sortie: str | Path) -> Path:
    """Compagnon d'un fichier de sortie : même nom, extension « .json »."""
    return Path(chemin_sortie).with_suffix(".json")


def _mots_en_dict(segment) -> list[dict]:
    resultat: list[dict] = []
    for mot in getattr(segment, "mots", None) or []:
        texte = (getattr(mot, "texte", "") or "").strip()
        if not texte:
            continue
        resultat.append({
            "t": texte,
            "d": round(float(getattr(mot, "debut", 0.0) or 0.0), 2),
            "f": round(float(getattr(mot, "fin", 0.0) or 0.0), 2),
            "p": round(float(getattr(mot, "probabilite", 0.0) or 0.0), 3),
        })
    return resultat


# ---------------------------------------------------------------------------
# Les mots disent le texte
#
# Règle tenue partout où un compagnon s'écrit : les mots d'un segment (« m »),
# mis bout à bout, redonnent son texte (« t ») au caractère près, blancs mis à
# part, et aucun mot ne contient de blanc. C'est sur eux que reposent l'écoute
# mot à mot, les mots douteux et `scribouille lire` : un mot perdu, dupliqué
# ou amputé de sa ponctuation ferait dire au compagnon autre chose que le
# fichier. Le moteur ne la garantit pas (vocabulaire appliqué au texte seul,
# mots d'OpenVINO rangés par l'heure) : `aligner_mots` la rétablit.
# ---------------------------------------------------------------------------

def _sans_blancs(texte) -> str:
    return "".join(str(texte or "").split())


def mots_conformes(segment: dict) -> bool:
    """Les mots de ce segment redonnent-ils exactement son texte ?"""
    mots = segment.get("m") if isinstance(segment, dict) else None
    if not mots:
        return True
    if not isinstance(mots, list) or any(
            not isinstance(m, dict) or not str(m.get("t") or "") or _sans_blancs(m["t"]) != str(m["t"])
            for m in mots):
        return False
    return "".join(str(m["t"]) for m in mots) == _sans_blancs(segment.get("t"))


def ecart_mots(donnees: dict | None) -> str:
    """Premier segment dont les mots ne redonnent pas le texte, décrit ; chaîne vide sinon."""
    for rang, segment in enumerate((donnees or {}).get("segments") or []):
        if isinstance(segment, dict) and not mots_conformes(segment):
            mots = " ".join(str(m.get("t", "")) for m in segment.get("m") or [] if isinstance(m, dict))
            return f"mots du segment {rang + 1} : « {mots[:80]} » pour « {str(segment.get('t', ''))[:80]} »"
    return ""


def _chercher(texte: str, jeton: str, depart: int, portee: int = 200) -> int:
    """Le jeton dans le texte, à partir de `depart`, sans couper un mot ni sauter trop loin."""
    position = texte.find(jeton, depart)
    while 0 <= position <= depart + portee:
        avant = texte[position - 1] if position > 0 else ""
        apres = texte[position + len(jeton):position + len(jeton) + 1]
        if not (jeton[:1].isalnum() and avant.isalnum()) and not (jeton[-1:].isalnum() and apres.isalnum()):
            return position
        position = texte.find(jeton, position + 1)
    return -1


def aligner_mots(texte: str, mots: list, debut: float = 0.0, fin: float = 0.0, corrige: bool = False) -> list[dict]:
    """
    Mots d'un segment recalés sur son texte. Chaque mot du moteur retrouvé à
    sa place garde son heure et sa confiance ; un mot qui n'y est plus est
    retiré ; un morceau du texte que nul mot ne porte rejoint le mot auquel
    il est collé (ponctuation, suffixe), sinon devient un mot à lui, placé
    entre ses voisins, sans confiance (`p` -1) et marqué corrigé (`c`) quand
    le vocabulaire l'a écrit. Un mot qui contenait un blanc est coupé.
    """
    candidats: list[dict] = []
    for mot in mots or []:
        if not isinstance(mot, dict) or not str(mot.get("t") or "").strip():
            continue
        morceaux = str(mot["t"]).split()
        if len(morceaux) == 1:
            candidats.append({**mot, "t": morceaux[0]})
            continue
        d, f = float(mot.get("d", 0) or 0), float(mot.get("f", 0) or 0)
        total = sum(len(m) for m in morceaux)
        cumul = 0
        for morceau in morceaux:
            a = d + (f - d) * cumul / total
            cumul += len(morceau)
            candidats.append({**mot, "t": morceau, "d": round(a, 2), "f": round(d + (f - d) * cumul / total, 2)})
    places: list[list] = []   # [début, fin, mot]
    position = 0
    for mot in candidats:
        trouve = _chercher(texte, mot["t"], position)
        if trouve < 0:
            continue
        places.append([trouve, trouve + len(mot["t"]), mot])
        position = trouve + len(mot["t"])
    # Les morceaux du texte que nul mot ne porte, de gauche à droite.
    import re

    resultat: list[list] = []
    rang = 0
    couverts = [(a, b) for a, b, _ in places]

    def suivant_a_partir(n: int) -> int | None:
        return places[n][0] if n < len(places) else None

    morceaux_libres = []
    curseur = 0
    for a, b in couverts + [(len(texte), len(texte))]:
        if a > curseur:
            for trouve in re.finditer(r"\S+", texte[curseur:a]):
                morceaux_libres.append((curseur + trouve.start(), curseur + trouve.end()))
        curseur = max(curseur, b)
    libres = iter(morceaux_libres)
    prochain = next(libres, None)
    while rang < len(places) or prochain is not None:
        if prochain is not None and (rang >= len(places) or prochain[0] < places[rang][0]):
            a, b = prochain
            colle_avant = resultat and resultat[-1][1] == a
            colle_apres = rang < len(places) and places[rang][0] == b
            if colle_avant:
                resultat[-1][1] = b
                resultat[-1][2] = {**resultat[-1][2], "t": texte[resultat[-1][0]:b]}
            elif colle_apres:
                mot = places[rang][2]
                places[rang][0] = a
                places[rang][2] = {**mot, "t": texte[a:places[rang][1]]}
            else:
                avant = float(resultat[-1][2].get("f", debut) or debut) if resultat else float(debut or 0)
                apres = suivant_a_partir(rang)
                limite = float(places[rang][2].get("d", fin) or fin) if apres is not None else float(fin or avant)
                nouveau = {"t": texte[a:b], "d": round(avant, 2), "f": round(max(avant, limite), 2), "p": -1.0}
                if corrige:
                    nouveau["c"] = 1
                resultat.append([a, b, nouveau])
            prochain = next(libres, None)
            continue
        resultat.append(places[rang])
        rang += 1
    return [mot for _, _, mot in resultat]


def aligner_segments(donnees: dict | None) -> int:
    """Recale les mots de chaque segment qui ne redit pas son texte ; renvoie le nombre recalé."""
    if not donnees:
        return 0
    corriges = {
        int(r.get("s", -1)) for r in ((donnees.get("vocabulaire") or {}).get("remplacements") or [])
        if isinstance(r, dict) and not r.get("annule")
    }
    recales = 0
    for rang, segment in enumerate(donnees.get("segments") or []):
        if not isinstance(segment, dict) or mots_conformes(segment):
            continue
        mots = aligner_mots(str(segment.get("t") or ""), segment.get("m") or [], float(segment.get("d", 0) or 0),
                            float(segment.get("f", 0) or 0), corrige=rang in corriges)
        if mots:
            segment["m"] = mots
        else:
            segment.pop("m", None)
        recales += 1
    return recales


def construire(source: Path, segments, details: dict) -> dict:
    """Assemble le contenu du compagnon à partir des segments transcrits."""
    liste: list[dict] = []
    for segment in segments:
        entree: dict = {
            "d": round(float(segment.debut), 2),
            "f": round(float(segment.fin), 2),
            "t": segment.texte,
        }
        if getattr(segment, "locuteur", ""):
            entree["l"] = segment.locuteur
        mots = _mots_en_dict(segment)
        if mots:
            entree["m"] = mots
        liste.append(entree)

    contenu = {
        "format": FORMAT,
        "version": VERSION_FORMAT,
        "produit_par": f"Scribouille {VERSION}",
        "source": {
            "nom": source.name,
            "chemin": str(source),
            "duree": round(float(details.get("duree", 0) or 0), 2),
            # Date de l'enregistrement (fichier audio), pas de la transcription.
            **({"date": _date_fichier(source)} if _date_fichier(source) else {}),
        },
        "transcription": {
            "date": datetime.now().isoformat(timespec="seconds"),
            "modele": details.get("modele_lisible", details.get("modele", "")),
            # Détail technique que l'en-tête du .txt ne porte plus (3.0).
            "preset": details.get("preset_nom") or "",
            "calcul": f"{details.get('peripherique', 'cpu')} / {details.get('type_calcul', 'int8')}",
            "termes_amorce": int(details.get("termes_amorce", 0) or 0),
            "langue": details.get("langue", ""),
            "temps_calcul": round(float(details.get("temps_calcul", 0) or 0), 1),
            "nb_locuteurs": int(details.get("nb_locuteurs", 0) or 0),
            "corrections_appliquees": int(details.get("corrections_appliquees", 0) or 0),
        },
        "seuils": {"faible": SEUIL_FAIBLE, "tres_faible": SEUIL_TRES_FAIBLE},
        "segments": liste,
    }
    # Remplacements faits par le vocabulaire (étage b) : clé facultative, que
    # les versions antérieures ignorent. La vue de relecture les montre et
    # permet de les annuler un à un. « s » : rang du segment ; « o » : position
    # dans son texte ; « a » : avant ; « b » : après.
    remplacements = details.get("remplacements_vocabulaire") or []
    if remplacements:
        contenu["vocabulaire"] = {"remplacements": [dict(r) for r in remplacements]}
    # Les mots redisent le texte : vocabulaire appliqué, mots rangés par l'heure.
    aligner_segments(contenu)
    return contenu


def ecrire(chemin_sortie: str | Path, source: Path, segments, details: dict) -> Path | None:
    """
    Écrit le compagnon à côté du fichier de sortie.

    Un échec n'interrompt jamais rien : la transcription elle-même est écrite,
    le compagnon n'est qu'un confort de relecture.
    """
    cible = chemin_pour(chemin_sortie)
    try:
        cible.write_text(
            json.dumps(construire(source, segments, details), ensure_ascii=False),
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        journal.attention("Compagnon non écrit pour %s : %s", cible.name, exc)
        return None
    journal.info("Écrit : %s", cible)
    return cible


def lire(chemin_sortie: str | Path) -> dict | None:
    """Relit le compagnon d'un fichier de sortie, ou None s'il est inutilisable."""
    cible = chemin_pour(chemin_sortie)
    try:
        donnees = json.loads(cible.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        journal.attention("Compagnon illisible (%s) : %s", cible.name, exc)
        return None

    if not isinstance(donnees, dict) or donnees.get("format") not in FORMATS_LUS:
        return None
    version = donnees.get("version")
    if not isinstance(version, int) or version > VERSION_FORMAT:
        journal.attention(
            "Compagnon %s écrit dans un format plus récent (version %s), ignoré.",
            cible.name, version,
        )
        return None
    if not isinstance(donnees.get("segments"), list):
        return None
    return donnees


def enregistrer_tel_quel(chemin_sortie: str | Path, donnees: dict) -> bool:
    """Réécrit un compagnon déjà chargé, après une correction apprise."""
    cible = chemin_pour(chemin_sortie)
    try:
        cible.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
        return True
    except (OSError, TypeError, ValueError) as exc:
        journal.attention("Compagnon non réécrit (%s) : %s", cible.name, exc)
        return False


def _date_fichier(source: Path) -> str:
    """Date de modification du fichier audio, ISO, ou vide."""
    try:
        return datetime.fromtimestamp(Path(source).stat().st_mtime).isoformat(timespec="seconds")
    except (OSError, ValueError, TypeError):
        return ""


def source_rapide(compagnon_json: Path) -> dict:
    """
    Le bloc « source » d'un compagnon, lu dans ses premiers octets seulement
    (il est écrit en tête) : la liste des transcriptions n'a pas à charger les
    mots d'une réunion d'une heure pour connaître la date de l'enregistrement.
    """
    import re

    try:
        with Path(compagnon_json).open(encoding="utf-8", errors="replace") as flux:
            debut = flux.read(4000)
    except OSError:
        return {}
    trouve = re.search(r'"source"\s*:\s*(\{[^{}]*\})', debut)
    if not trouve:
        return {}
    try:
        bloc = json.loads(trouve.group(1))
    except ValueError:
        return {}
    return bloc if isinstance(bloc, dict) else {}
