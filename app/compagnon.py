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

    return {
        "format": FORMAT,
        "version": VERSION_FORMAT,
        "produit_par": f"Scribouille {VERSION}",
        "source": {
            "nom": source.name,
            "chemin": str(source),
            "duree": round(float(details.get("duree", 0) or 0), 2),
        },
        "transcription": {
            "date": datetime.now().isoformat(timespec="seconds"),
            "modele": details.get("modele_lisible", details.get("modele", "")),
            "langue": details.get("langue", ""),
            "temps_calcul": round(float(details.get("temps_calcul", 0) or 0), 1),
            "nb_locuteurs": int(details.get("nb_locuteurs", 0) or 0),
            "corrections_appliquees": int(details.get("corrections_appliquees", 0) or 0),
        },
        "seuils": {"faible": SEUIL_FAIBLE, "tres_faible": SEUIL_TRES_FAIBLE},
        "segments": liste,
    }


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
