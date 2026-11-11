"""
Préparation du corpus de la campagne de mesure (outil de mainteneur).

Choisit une fois pour toutes les extraits de SUMM-RE ASRU que la campagne
transcrit (`app/campagne.py`), écrit leur liste figée dans
`app/corpus_manifeste.py` (octets dans les fichiers d'origine, empreintes), puis
fabrique le paquet prêt à l'emploi `corpus-campagne-vN.zip` (extraits mélangés
et références, sous CC BY-SA 4.0 comme leur source) que l'on dépose à côté du
programme portable. Le dépôt ne contient aucun extrait : seulement la liste.

Règle de choix, sans jugement humain sur le contenu : dans chacune des dix
réunions, deux fenêtres d'environ 66 s, l'une vers 30 % de la réunion, l'autre
vers 68 % (l'accueil et la conclusion sont évités), bornées sur un silence
d'au moins 0,6 s commun à tous les participants, avec au moins deux locuteurs
et 80 mots de référence.

    .venv\\Scripts\\python outils\\preparer_corpus_campagne.py --cache DOSSIER [--paquet SORTIE.zip]

`--cache` garde les morceaux téléchargés (environ 450 Mo) : une seconde
exécution ne retélécharge rien.
"""

from __future__ import annotations

import argparse
import json
import pprint
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

DEPOT_HF = "datasets-CNRS/summ-re-asru"
REVISION_HF = "de4e37a37f0052591049de6e5091144c0b9897be"
BASE_ORTOLANG = "https://repository.ortolang.fr/api/content/summ-re-asru/v2/SUMM-RE-sm"
BASE_HF = f"https://huggingface.co/datasets/{DEPOT_HF}/resolve/{REVISION_HF}"
CIBLES = (0.30, 0.68)
DUREE_VISEE, DUREE_MIN, DUREE_MAX = 66.0, 55.0, 80.0
SILENCE_MIN = 0.6
MANIFESTE = RACINE / "app" / "corpus_manifeste.py"

ENTETE_MANIFESTE = '''"""
Liste figée des extraits du corpus de la campagne (SUMM-RE ASRU, CC BY-SA 4.0).

Fichier produit par `outils/preparer_corpus_campagne.py`, à ne pas modifier à
la main. Il ne contient aucun extrait : des noms de pistes, des instants, des
positions d'octets dans les fichiers d'origine et des empreintes SHA-256.
"""

'''


def lire(url: str, debut: int | None = None, fin: int | None = None) -> tuple[bytes, str]:
    requete = urllib.request.Request(url, headers={"User-Agent": "Scribouille-preparation"})
    if debut is not None:
        requete.add_header("Range", f"bytes={debut}-{fin}")
    with urllib.request.urlopen(requete, timeout=120) as reponse:
        return reponse.read(), reponse.headers.get("Content-Range", "")


def en_cache(cache: Path, cle: str, url: str, debut=None, fin=None) -> bytes:
    fichier = cache / cle
    if fichier.is_file():
        return fichier.read_bytes()
    donnees, _ = lire(url, debut, fin)
    fichier.write_bytes(donnees)
    return donnees


def pistes_du_depot() -> dict[str, list[str]]:
    with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{DEPOT_HF}/revision/{REVISION_HF}",
                                timeout=60) as r:
        info = json.loads(r.read())
    reunions: dict[str, list[str]] = {}
    for s in info["siblings"]:
        nom = s["rfilename"]
        if nom.startswith("audio_anonymized/") and nom.endswith("_anon.wav"):
            piste = nom.split("/")[1][:-len("_anon.wav")]
            reunions.setdefault(piste.rsplit("_", 1)[0], []).append(piste)
    return {k: sorted(v) for k, v in sorted(reunions.items())}


def coupures(jetons_par_piste: dict, duree: float) -> list[float]:
    """Milieux des silences communs à tous les participants."""
    actifs = sorted((d, f) for jetons in jetons_par_piste.values() for d, f, j in jetons
                    if j.strip() not in ("#", ""))
    points, fin_courante = [], 0.0
    for d, f in actifs:
        if d - fin_courante >= SILENCE_MIN:
            points.append((fin_courante + d) / 2)
        fin_courante = max(fin_courante, f)
    return [p for p in points if 5.0 < p < duree - 5.0]


def choisir(jetons_par_piste: dict, duree: float) -> list[tuple[float, float]]:
    from app import corpus

    points = coupures(jetons_par_piste, duree)
    fenetres = []
    for cible in CIBLES:
        for debut in [p for p in points if p >= cible * duree]:
            fins = [p for p in points if DUREE_MIN <= p - debut <= DUREE_MAX]
            if not fins:
                continue
            fin = min(fins, key=lambda p: abs(p - debut - DUREE_VISEE))
            ref = corpus.construire_reference(jetons_par_piste, debut, fin)
            locuteurs = {m[3] for m in ref["mots"]}
            if len(ref["mots"]) >= 80 and len(locuteurs) >= 2:
                fenetres.append((round(debut, 3), round(fin, 3)))
                break
    return fenetres


def selectionner(cache: Path) -> dict:
    from app import corpus

    extraits, csv_empreintes = [], {}
    for reunion, pistes in pistes_du_depot().items():
        jetons, entetes = {}, {}
        for piste in pistes:
            brut_csv = en_cache(cache, f"{piste}.csv", f"{BASE_HF}/gold_transcriptions/csv/{piste}_anon.csv")
            csv_empreintes[piste] = corpus.empreinte(brut_csv)
            jetons[piste] = corpus.lire_jetons(brut_csv)
            entete, plage = lire(f"{BASE_HF}/audio_anonymized/{piste}_anon.wav", 0, 4095)
            taille = int(plage.rsplit("/", 1)[1])
            format_, canaux, frequence, bits, donnees = corpus.lire_entete(entete)
            assert canaux == 1, piste
            bloc = bits // 8
            entetes[piste] = (format_, frequence, bits, donnees, (taille - donnees) / (frequence * bloc))
        duree = min(e[4] for e in entetes.values())
        for rang, (debut, fin) in enumerate(choisir(jetons, duree), 1):
            entree = {"id": f"{reunion.split('_')[0]}-{rang}", "reunion": reunion,
                      "debut": debut, "fin": fin, "pistes": []}
            for piste in pistes:
                format_, frequence, bits, donnees, _ = entetes[piste]
                bloc = bits // 8
                octet_debut = donnees + int(debut * frequence) * bloc
                octet_fin = donnees + int(fin * frequence) * bloc - 1
                morceau = en_cache(cache, f"{piste}-{octet_debut}-{octet_fin}.pcm",
                                   f"{BASE_HF}/audio_anonymized/{piste}_anon.wav", octet_debut, octet_fin)
                entree["pistes"].append({"nom": piste, "format": format_, "bits": bits,
                                         "frequence": frequence, "octet_debut": octet_debut,
                                         "octet_fin": octet_fin, "sha256": corpus.empreinte(morceau)})
            extraits.append(entree)
            print(f"{entree['id']:8s} {debut:7.1f} -> {fin:7.1f} s, {len(pistes)} pistes", flush=True)
    return {"version": 1, "depot_hf": DEPOT_HF, "revision_hf": REVISION_HF,
            "base_ortolang": BASE_ORTOLANG, "csv": csv_empreintes, "extraits": extraits}


def ecrire_manifeste(manifeste: dict) -> None:
    MANIFESTE.write_text(ENTETE_MANIFESTE + "MANIFESTE = " + pprint.pformat(manifeste, width=100,
                                                                             sort_dicts=False) + "\n",
                         encoding="utf-8")


def construire(cache: Path, dossier: Path) -> None:
    """Prépare les extraits par le chemin de l'application, morceaux pris dans le cache."""
    import importlib

    from app import corpus

    importlib.reload(sys.modules["app.corpus_manifeste"])
    importlib.reload(corpus)
    index = {}
    for fichier in cache.iterdir():
        if fichier.suffix in (".csv", ".pcm"):
            index[corpus.empreinte(fichier.read_bytes())] = fichier

    def depuis_cache(relatif, sha256, debut=None, fin=None):
        if sha256 in index:
            return index[sha256].read_bytes()
        raise corpus.ErreurCorpus("cache", relatif)

    corpus.telecharger = depuis_cache
    corpus.preparer(dossier=dossier)


def main() -> int:
    analyseur = argparse.ArgumentParser()
    analyseur.add_argument("--cache", required=True)
    analyseur.add_argument("--paquet", default="")
    analyseur.add_argument("--garder-selection", action="store_true",
                           help="ne pas refaire le choix, seulement les empreintes et le paquet")
    args = analyseur.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    if not args.garder_selection:
        manifeste = selectionner(cache)
        for entree in manifeste["extraits"]:
            entree["sha256_wav"] = entree["sha256_ref"] = ""
        ecrire_manifeste(manifeste)
    import importlib

    from app import corpus_manifeste

    manifeste = importlib.reload(corpus_manifeste).MANIFESTE
    dossier = cache / "prepare"
    dossier.mkdir(exist_ok=True)
    construire(cache, dossier)
    from app import corpus

    for entree in manifeste["extraits"]:
        wav = dossier / f"{entree['id']}.wav"
        ref = dossier / f"{entree['id']}.ref.json"
        entree["sha256_wav"] = corpus.empreinte_fichier(wav)
        entree["sha256_ref"] = corpus.empreinte_fichier(ref)
    ecrire_manifeste(manifeste)
    duree = sum(e["fin"] - e["debut"] for e in manifeste["extraits"])
    octets = sum(p["octet_fin"] - p["octet_debut"] + 1 for e in manifeste["extraits"] for p in e["pistes"])
    print(f"{len(manifeste['extraits'])} extraits, {duree / 60:.1f} min, {octets / 1e6:.0f} Mo à télécharger")
    if args.paquet:
        importlib.reload(sys.modules["app.corpus_manifeste"])
        importlib.reload(corpus)
        corpus.fabriquer_paquet(Path(args.paquet), dossier)
        print("paquet :", args.paquet, corpus.empreinte_fichier(Path(args.paquet)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
