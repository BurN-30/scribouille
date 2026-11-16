"""
Contrôle des fiches « ce que ça change » (`app/description_reglage.py`).

La fiche d'un choix doit dire exactement ce que la transcription appliquera :
ce script la compare, cas par cas, à ce que pose la VRAIE
`traitement.FileTraitement.ouvrir_file` (moteur créé, modèle, faisceau, lots,
fils, propriétés d'OpenVINO, rythme, pauses), sur des postes simulés : bureau
AMD, Core Ultra 5 225U avec puce graphique Intel vue par OpenVINO, carte
NVIDIA, poste à 8 Go. Aucun modèle n'est chargé (les moteurs sont créés, pas
ouverts), rien du système n'est touché (leviers de priorité et veille
remplacés), OpenVINO est simulé quand il manque (service de GitHub).

Six contrôles :

  1. CHIFFRES : chaque mesure de justesse de la fiche figure dans le fichier
     d'où elle vient ; le corpus des réunions a bien la taille de son
     manifeste ; les autres constantes citées sont celles du code.
  2. FICHE CONTRE FILE : pour chaque poste, preset, rythme, adaptation et
     réglage du poste, la fiche et `ouvrir_file` disent la même chose ; la
     durée est celle des cartes ; les seuils de mémoire sont ceux de
     `rythme.garde_memoire`.
  3. HYPOTHÈSES : le réglage qu'écrirait « Appliquer » (proposition, banc,
     `reglages definir`) est celui que la fiche décrit.
  4. TEXTES : chaque section a des lignes, en français et en anglais, sans
     clé de traduction restée brute.
  5. LIGNE DE COMMANDE : `reglages decrire` (texte et `--json`) n'écrit rien,
     rend les mêmes lignes que la fonction, refuse une clé inconnue.
  6. PASSERELLE : `decrire_reglage` de la fenêtre rend la même fiche.

    python outils/verifier_fiches.py

Sort avec le code 0 si tout passe, 1 sinon.
"""

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
TEMPORAIRE = Path(tempfile.mkdtemp(prefix="scribouille-fiches-"))
for _nom in ("donnees", "maison", "localappdata", "appdata"):
    (TEMPORAIRE / _nom).mkdir()
os.environ["SCRIBOUILLE_DONNEES"] = str(TEMPORAIRE / "donnees")
os.environ["USERPROFILE"] = os.environ["HOME"] = str(TEMPORAIRE / "maison")
os.environ["LOCALAPPDATA"] = str(TEMPORAIRE / "localappdata")
os.environ["APPDATA"] = str(TEMPORAIRE / "appdata")
os.environ["SCRIBOUILLE_ESSAI_REGISTRE"] = "[]"
os.environ.pop("SCRIBOUILLE_MOTEUR_ESSAI", None)
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from app import (  # noqa: E402
    adaptation, calibration, config as config_module, description_reglage as fiche, energie, langues, materiel,
    moteur, moteur_openvino, presets, reglage_machine, rythme, temoin_puce, traitement)

langues.definir("fr")
# Aucun journal écrit par ce processus : le dossier des données ne doit changer
# que par ce que les commandes essayées y écriraient.
__import__("app.journal", fromlist=["sans_fichier"]).sans_fichier()
SANS_FENETRE = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

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


def _decimal(valeur: float) -> str:
    texte = f"{valeur:.2f}" if round(valeur, 1) != valeur else f"{valeur:.1f}"
    return texte.replace(".", ",")


# ---------------------------------------------------------------------------
# 1. Les chiffres viennent du dépôt
# ---------------------------------------------------------------------------

def essai_chiffres() -> None:
    titre("1. Chiffres de la fiche : présents dans leur source")
    for m in fiche.MESURES:
        source = (RACINE / m.source).read_text(encoding="utf-8")
        for _langue, valeur in m.valeurs:
            verifier(_decimal(valeur) in source,
                     f"{m.corpus}, {m.moteur}, {moteur.nom_court(m.modele)}, faisceau {m.faisceau}"
                     f"{', lots' if m.lots else ''} : {_decimal(valeur)} % écrit dans {m.source}")
    from app import corpus_manifeste

    extraits = corpus_manifeste.MANIFESTE["extraits"]
    minutes = round(sum(float(e["fin"]) - float(e["debut"]) for e in extraits) / 60.0, 1)
    reunions = len({e["reunion"] for e in extraits})
    verifier((len(extraits), reunions, minutes) == (fiche.REUNIONS["extraits"], fiche.REUNIONS["reunions"],
                                                  fiche.REUNIONS["minutes"]),
             "corpus des réunions : extraits, réunions et minutes du manifeste",
             f"{len(extraits)}, {reunions}, {minutes}")
    journal = (RACINE / "CHANGELOG.md").read_text(encoding="utf-8")
    verifier("0,25 point en français et 0,37 en anglais" in journal,
             "valeur d'un mot d'écart : celle du journal des versions")
    verifier(f"{fiche.LIBRE_PUCE_225U_PCT} % du processeur" in (RACINE / "app" / "rythme.py").read_text(
        encoding="utf-8"), "processeur laissé libre sur la puce du 225U : celui de app/rythme.py")
    verifier("40 à 90 %" in journal and "sans changer un seul mot" in journal,
             "faisceau 8 par lots sans changer un mot : dit par le journal des versions")
    entete_ov = (RACINE / "app" / "moteur_openvino.py").read_text(encoding="utf-8")
    verifier("1,7 fois plus cher" in entete_ov, "faisceau d'OpenVINO 1,7 fois plus cher : dit par son en-tête")


# ---------------------------------------------------------------------------
# Postes simulés et OpenVINO simulé
# ---------------------------------------------------------------------------

def _tampon_topologie(coeurs: list[tuple[int, list[int]]], caches_l3: list[list[int]]) -> bytes:
    """Tampon de GetLogicalProcessorInformationEx fabriqué à la main (comme verifier_fonctions_peripheriques)."""
    import struct

    morceaux = []
    for classe, logiques in coeurs:
        masque = sum(1 << i for i in logiques)
        corps = struct.pack("<BBHH16sH", 1 if len(logiques) > 1 else 0, classe, 0, 0,
                            b"\0" * 16, 1) + struct.pack("<QH6s", masque, 0, b"\0" * 6)
        morceaux.append(struct.pack("<II", 0, 8 + len(corps)) + corps)
    for logiques in caches_l3:
        masque = sum(1 << i for i in logiques)
        corps = struct.pack("<BBHII18sH", 3, 12, 64, 12 << 20, 0, b"\0" * 18, 1) \
            + struct.pack("<QH6s", masque, 0, b"\0" * 6)
        morceaux.append(struct.pack("<II", 2, 8 + len(corps)) + corps)
    return b"".join(morceaux)


def poste_225u() -> materiel.Materiel:
    coeurs = [(1, [0, 1]), (1, [2, 3])] + [(0, [i]) for i in range(4, 12)] + [(0, [12]), (0, [13])]
    topo = materiel.analyser_topologie(_tampon_topologie(coeurs, [list(range(12))]))
    return materiel.Materiel(
        cpu_nom="Intel(R) Core(TM) Ultra 5 225U", coeurs_physiques=12, coeurs_logiques=14,
        topologie=topo, ram_go=32.0, basse_consommation=True, portable=True,
        gpus=[materiel.Gpu(nom="Intel(R) Graphics", vendeur="intel", pilote="32.0.101.8801")])


def poste_bureau() -> materiel.Materiel:
    return materiel.Materiel(cpu_nom="AMD Ryzen 7 7800X3D 8-Core Processor", coeurs_physiques=8,
                             coeurs_logiques=16, ram_go=47.0)


def poste_nvidia() -> materiel.Materiel:
    return materiel.Materiel(cpu_nom="Intel(R) Core(TM) i7-12700", coeurs_physiques=12, coeurs_logiques=20,
                             ram_go=32.0, a_nvidia=True, cuda_disponible=True,
                             gpus=[materiel.Gpu(nom="NVIDIA GeForce RTX 4060", vendeur="nvidia", accelere=True)])


def poste_8go() -> materiel.Materiel:
    return materiel.Materiel(cpu_nom="Intel(R) Core(TM) i5-8250U", coeurs_physiques=4, coeurs_logiques=8,
                             ram_go=8.0, basse_consommation=True)


class _Leviers:
    """Leviers du rythme qui notent au lieu de toucher au système."""

    def __init__(self):
        self.appels: list[tuple] = []

    def qos_seule(self, nom):
        self.appels.append(("qos", nom))

    def rendre_qos(self):
        pass

    def appliquer(self, b, avec_affinite):
        self.appels.append(("appliquer", b.priorite, b.qos, b.priorite_es, tuple(b.affinite) if avec_affinite else ()))

    def rendre(self):
        pass


@contextlib.contextmanager
def simulation(openvino: bool, temoin: dict | None = None):
    """OpenVINO installé avec CPU et GPU (ou absent), témoin de la puce choisi ; leviers et veille neutres."""
    sauve = (moteur_openvino.installe, moteur_openvino.peripheriques_disponibles, temoin_puce.etat,
             rythme.Leviers, energie.sans_veille, moteur.limiter_parallelisme, moteur_openvino.effacer_temoin)
    environnement = dict(os.environ)
    leviers = _Leviers()
    moteur_openvino.installe = lambda: openvino
    moteur_openvino.peripheriques_disponibles = lambda forcer=False: ["CPU", "GPU"] if openvino else []
    temoin_puce.etat = lambda: dict(temoin or {"etat": "libre"})
    rythme.Leviers = lambda: leviers
    energie.sans_veille = lambda: contextlib.nullcontext()
    moteur.limiter_parallelisme = lambda fils: None
    moteur_openvino.effacer_temoin = lambda: None
    try:
        yield leviers
    finally:
        (moteur_openvino.installe, moteur_openvino.peripheriques_disponibles, temoin_puce.etat,
         rythme.Leviers, energie.sans_veille, moteur.limiter_parallelisme, moteur_openvino.effacer_temoin) = sauve
        os.environ.clear()
        os.environ.update(environnement)


# ---------------------------------------------------------------------------
# 2. La fiche contre la vraie ouverture de la file
# ---------------------------------------------------------------------------

def reglage_de(mat: materiel.Materiel, nature: str) -> dict:
    signature = calibration.signature_machine(mat)
    return {
        "aucun": {},
        "ov_gpu": {"moteur": "openvino", "peripherique": "GPU", "signature": signature},
        "ov_cpu": {"moteur": "openvino", "peripherique": "CPU", "signature": signature},
        "ov_cpu_f5": {"moteur": "openvino", "peripherique": "CPU", "faisceau": 5, "signature": signature},
        "ct2_banc": {"moteur": "ctranslate2", "fils": 6, "lot": 4, "signature": signature},
        "ct2_f1": {"moteur": "ctranslate2", "faisceau": 1, "signature": signature},
    }[nature]


def comparer(nom: str, mat: materiel.Materiel, conf: dict, leviers: _Leviers) -> list[str]:
    """Écarts entre la fiche et ce que pose `ouvrir_file` (liste vide : d'accord)."""
    p = fiche.plan(conf, mat)
    file = traitement.FileTraitement(copy.copy(mat))
    leviers.appels.clear()
    contexte = file.ouvrir_file(copy.deepcopy(conf))
    ecarts: list[str] = []
    try:
        reglages, instance, regulateur = contexte["reglages"], contexte["instance"], contexte["regulateur"]
        m = file.materiel

        def ecart(quoi, fiche_dit, file_pose):
            if fiche_dit != file_pose:
                ecarts.append(f"{quoi} : fiche {fiche_dit!r}, file {file_pose!r}")

        ecart("modèle", p["modele"], reglages["modele"])
        sur_ov = isinstance(instance, moteur_openvino.MoteurAvecRepli)
        if sur_ov and not (presets.depot_openvino(reglages["modele"]) or moteur.est_modele_openvino(reglages["modele"])):
            instance._actif = instance._ct2   # premier geste de `MoteurAvecRepli.charger`
        actif_ov = sur_ov and instance.sur_openvino
        ecart("moteur", p["moteur"], "openvino" if actif_ov else "ctranslate2")
        if actif_ov:
            ov = instance._ov
            ecart("périphérique", p["peripherique"], ov.peripherique_ov)
            ecart("faisceau", p["faisceau"], moteur_openvino.faisceau_effectif(
                ov.peripherique_ov, int(reglages.get("faisceau_openvino") or 1)))
            ecart("précision", p["precision"], ov.type_calcul)
            ecart("propriétés OpenVINO", p["rythme"]["proprietes_openvino"], dict(instance.proprietes))
            ecart("dépôt chargé", p["modele_calcule"], presets.depot_openvino(reglages["modele"]))
        else:
            ct2 = instance._ct2 if sur_ov else instance
            ecart("périphérique", p["peripherique"], ct2.peripherique)
            ecart("précision", p["precision"], ct2.type_calcul)
            ecart("faisceau", p["faisceau"], int(reglages.get("beam_size") or 5))
            ecart("lots", p["lots"], int(reglages.get("lot") or 0))
            ecart("fils", p["rythme"]["fils"], ct2.fils_effectifs)
        ecart("rythme", p["rythme"]["choisi"], regulateur.choisi)
        ecart("adaptation", p["rythme"]["auto"], regulateur.auto)
        ecart("vitesse sans réglage", p["rythme"]["leger"], regulateur.leger)
        ecart("lots au plus", p["rythme"]["lot_max"], regulateur.chargement.lot_max)
        # Pause quand le poste sert (le premier relevé d'activité a pu passer
        # en vitesse maximale sur un poste au repos) : rythme choisi posé.
        effectif, regulateur.effectif = regulateur.effectif, regulateur.choisi
        ecart("pause", p["rythme"]["pause"], regulateur.rapport_pause())
        regulateur.effectif = effectif
        attendu = (("qos", "haute"),) if p["rythme"]["leger"] else (
            ("appliquer", p["rythme"]["priorite"], p["rythme"]["qos"], p["rythme"]["priorite_es"],
             tuple(p["rythme"]["affinite"])),)
        ecart("leviers posés au départ", attendu, tuple(leviers.appels[:1]))
        # Durée : celle des cartes et du bandeau (même matériel, même rythme).
        if not conf.get("mode_avance"):
            ecart("durée", p["cout"]["pour_une_heure"], presets.pour_une_heure(conf.get("preset", "qualite"), m,
                                                                              regulateur.choisi))
        # Garde de la mémoire, comme `traiter_element` l'appelle.
        g = p["garde_memoire"]
        if regulateur.choisi != "vitesse":
            nom_moteur = "openvino" if m.moteur == "openvino" else "ctranslate2"
            lot = int(reglages.get("lot") or 0)
            leger = presets.MODELE_TURBO if not conf.get("mode_avance") else ""
            if g is None:
                ecarts.append("garde de la mémoire absente de la fiche")
            else:
                if g["lots_sous_go"]:
                    dessous = rythme.garde_memoire(regulateur.choisi, nom_moteur, reglages["modele"], lot,
                                                   g["lots_sous_go"] - 0.05, "")
                    dessus = rythme.garde_memoire(regulateur.choisi, nom_moteur, reglages["modele"], lot,
                                                  g["lots_sous_go"] + 0.05, "")
                    ecart("seuil des lots", ("lots", ""), (dessous[2], dessus[2]))
                if g["modele_sous_go"] and leger:
                    dessous = rythme.garde_memoire(regulateur.choisi, nom_moteur, reglages["modele"], 0,
                                                   g["modele_sous_go"] - 0.05, leger)
                    dessus = rythme.garde_memoire(regulateur.choisi, nom_moteur, reglages["modele"], 0,
                                                  g["modele_sous_go"] + 0.05, leger)
                    ecart("seuil du modèle", ("modele", ""), (dessous[2], dessus[2]))
        elif g is not None:
            ecarts.append("garde de la mémoire en vitesse maximale")
    finally:
        file.fermer_file(contexte, traitement.Rappels())
    return ecarts


def essai_fiche_contre_file() -> None:
    titre("2. Fiche contre file : ce que dit la fiche est ce que pose ouvrir_file")
    postes = (("bureau AMD", poste_bureau, False, ("aucun", "ct2_banc", "ct2_f1")),
              ("Core Ultra 5 225U, OpenVINO", poste_225u, True, ("aucun", "ov_gpu", "ov_cpu", "ov_cpu_f5")),
              ("carte NVIDIA", poste_nvidia, False, ("aucun",)),
              ("8 Go de mémoire", poste_8go, False, ("aucun",)))
    total, desaccords = 0, []
    for nom, fabrique, ov, reglages in postes:
        with simulation(ov) as leviers:
            for nature in reglages:
                for cle_preset in presets.PRESETS:
                    for nom_rythme in ("", *rythme.RYTHMES):
                        for auto in (False, True):
                            for forcer in ((False, True) if nature.startswith("ov") else (False,)):
                                mat = fabrique()
                                conf = {**copy.deepcopy(config_module.DEFAUTS), "preset": cle_preset,
                                        "rythme": nom_rythme, "rythme_auto": auto,
                                        "mode_avance": forcer, "forcer_processeur": forcer,
                                        reglage_machine.CLE: reglage_de(mat, nature)}
                                ecarts = comparer(nom, mat, conf, leviers)
                                total += 1
                                if ecarts:
                                    desaccords.append(f"{nom}, {nature}, {cle_preset}, {nom_rythme or 'selon moteur'}"
                                                      f"{', auto' if auto else ''}{', forcé' if forcer else ''} : "
                                                      + " ; ".join(ecarts))
        verifier(not [d for d in desaccords if d.startswith(nom)], f"{nom} : fiche et file d'accord",
                 " | ".join(d for d in desaccords if d.startswith(nom))[:900])
    print(f"         {total} situations comparées")
    # Cas particuliers : modèle sans version OpenVINO, puce suspendue, mode avancé.
    with simulation(True) as leviers:
        mat = poste_225u()
        distil = "bofenghuang/whisper-large-v3-distil-fr-v0.2"
        conf = {**copy.deepcopy(config_module.DEFAUTS), "mode_avance": True, "modele_avance": distil,
                "rythme": "equilibre", reglage_machine.CLE: reglage_de(mat, "ov_gpu")}
        ecarts = comparer("distil", mat, conf, leviers)
        p = fiche.plan(conf, mat)
        verifier(not ecarts and p["sans_equivalent_openvino"] and p["moteur"] == "ctranslate2",
                 "modèle sans version OpenVINO sur la puce : la fiche dit CTranslate2, comme la file", "; ".join(ecarts))
        conf = {**copy.deepcopy(config_module.DEFAUTS), "mode_avance": True, "beam_size": 8, "preset": "qualite",
                reglage_machine.CLE: reglage_de(poste_bureau(), "aucun")}
        ecarts = comparer("faisceau 8", poste_bureau(), conf, leviers)
        verifier(not ecarts and fiche.plan(conf, poste_bureau())["faisceau"] == 8,
                 "mode avancé, faisceau 8 : la fiche dit 8, comme la file", "; ".join(ecarts))
    with simulation(True, {"etat": "suspendue", "peripherique": "GPU"}) as leviers:
        mat = poste_225u()
        conf = {**copy.deepcopy(config_module.DEFAUTS), reglage_machine.CLE: reglage_de(mat, "ov_gpu")}
        ecarts = comparer("suspendue", mat, conf, leviers)
        p = fiche.plan(conf, mat)
        verifier(not ecarts and p["moteur"] == "ctranslate2" and p["effet"].get("plantage") == "GPU"
                 and any(l["cle"] == "indisponible" for s in fiche.sections(p) for l in s["lignes"]),
                 "puce suspendue : CTranslate2, comme la file, et la fiche le dit", "; ".join(ecarts))
        p = fiche.plan(conf, mat, {"reglage": {"moteur": "openvino", "peripherique": "GPU"}, "leve_suspension": True})
        verifier(p["moteur"] == "openvino" and p["effet"].get("suspension_levee"),
                 "conseil d'OpenVINO appliqué : la suspension est levée, la fiche décrit la puce", str(p["effet"]))
    # La fiche ne touche ni à la configuration ni au matériel.
    with simulation(True):
        mat = poste_225u()
        conf = {**copy.deepcopy(config_module.DEFAUTS), reglage_machine.CLE: reglage_de(mat, "ov_gpu")}
        avant_conf, avant_mat = json.dumps(conf, sort_keys=True), (mat.moteur, mat.peripherique_openvino,
                                                                    mat.fils_imposes)
        fiche.decrire(conf, mat, {"preset": "rapide", "rythme": "discret", "rythme_auto": True,
                                  "reglage": {"moteur": "ctranslate2", "fils": 3}})
        verifier(json.dumps(conf, sort_keys=True) == avant_conf
                 and (mat.moteur, mat.peripherique_openvino, mat.fils_imposes) == avant_mat,
                 "décrire ne change ni la configuration ni le matériel")


# ---------------------------------------------------------------------------
# 3. Les hypothèses sont celles qu'« Appliquer » écrirait
# ---------------------------------------------------------------------------

def _sans_date(reglage: dict) -> dict:
    return {k: v for k, v in (reglage or {}).items() if k not in ("date", "source")}


def essai_hypotheses() -> None:
    titre("3. Hypothèses : le réglage décrit est celui qu'« Appliquer » écrirait")
    with simulation(True):
        mat = poste_225u()
        base = {**copy.deepcopy(config_module.DEFAUTS),
                reglage_machine.CLE: {"moteur": "ctranslate2", "fils": 6, "lot": 4, "faisceau": 3,
                                      "signature": calibration.signature_machine(mat)}}
        for reglage in ({"moteur": "openvino", "peripherique": "GPU", "faisceau": 5},
                        {"moteur": "openvino", "peripherique": "CPU", "faisceau": 5, "fils": 4},
                        {"moteur": "ctranslate2", "fils": 8, "lot": 0}, {"moteur": "inconnu"}):
            ecrit = copy.deepcopy(base)
            reglage_machine.enregistrer(ecrit, copy.copy(mat), reglage)
            verifier(_sans_date(fiche.reglage_ecrit(mat, reglage)) == _sans_date(ecrit[reglage_machine.CLE]),
                     f"réglage {reglage} : écrit comme reglage_machine.enregistrer",
                     f"{fiche.reglage_ecrit(mat, reglage)} / {ecrit[reglage_machine.CLE]}")
        for proposition in adaptation.TABLE:
            p = {"moteur": proposition.moteur, "peripherique": proposition.peripherique, "preset": proposition.preset,
                 "faisceau": 0, "rythme": adaptation.rythme_propose({"moteur": proposition.moteur,
                                                                     "peripherique": proposition.peripherique})[0],
                 "rythme_auto": adaptation.rythme_propose({"moteur": proposition.moteur,
                                                           "peripherique": proposition.peripherique})[1]}
            for faisceau in (0, 5):
                p["faisceau"] = faisceau
                ecrit = copy.deepcopy(base)
                adaptation.appliquer(ecrit, copy.copy(mat), p)
                hyp = fiche.hypothese(base, mat, fiche.choix_proposition(base, mat, p))
                verifier(all(hyp.get(c) == ecrit.get(c) for c in ("preset", "rythme", "rythme_auto"))
                         and _sans_date(hyp[reglage_machine.CLE]) == _sans_date(ecrit[reglage_machine.CLE]),
                         f"proposition « {proposition.cle} », faisceau {faisceau} : comme adaptation.appliquer",
                         f"{hyp[reglage_machine.CLE]} / {ecrit[reglage_machine.CLE]}")


# ---------------------------------------------------------------------------
# 4. Les textes, dans les deux langues
# ---------------------------------------------------------------------------

def essai_textes() -> None:
    titre("4. Textes : toutes les sections remplies, en français et en anglais")
    cas = [("bureau", poste_bureau, False, "aucun"), ("225U puce", poste_225u, True, "ov_gpu"),
           ("225U processeur", poste_225u, True, "ov_cpu"), ("NVIDIA", poste_nvidia, False, "aucun"),
           ("8 Go", poste_8go, False, "aucun")]
    for langue in ("fr", "en"):
        langues.definir(langue)
        bruts, vides = [], []
        for nom, fabrique, ov, nature in cas:
            with simulation(ov):
                mat = fabrique()
                conf = {**copy.deepcopy(config_module.DEFAUTS), reglage_machine.CLE: reglage_de(mat, nature)}
                for sujet in ("actuel", "preset", "rythme", "auto", "proposition", "automatique", "forcer", "avance"):
                    for valeur in ({"preset": list(presets.PRESETS), "rythme": list(rythme.RYTHMES)}.get(sujet)
                                   or [None]):
                        choix, contexte, _ = fiche.choix_du_sujet(conf, mat, sujet, valeur)
                        f = fiche.decrire(conf, mat, choix)
                        textes = [f["titre"], f["verdict"], contexte, fiche.titre_sujet(sujet, valeur)]
                        for s in f["sections"]:
                            if not s["lignes"]:
                                vides.append(f"{nom}/{sujet}/{valeur}/{s['cle']}")
                            textes.append(s["titre"])
                            textes += [x for l in s["lignes"] for x in (l["libelle"], l["valeur"])]
                        bruts += [f"{nom}/{sujet}: {x}" for x in textes if "fiche." in x or "{" in x]
        verifier(not vides, f"{langue} : chaque section a ses lignes", ", ".join(vides[:5]))
        verifier(not bruts, f"{langue} : aucune clé ni variable restée brute", " | ".join(bruts[:4]))
    langues.definir("fr")
    with simulation(True):
        mat = poste_225u()
        conf = {**copy.deepcopy(config_module.DEFAUTS), reglage_machine.CLE: reglage_de(mat, "ov_gpu")}
        f = fiche.decrire(conf, mat, {"preset": "qualite", "rythme": "vitesse"})
        lignes = {l["cle"]: l["valeur"] for s in f["sections"] for l in s["lignes"]}
        verifier("glouton" in lignes["faisceau"] and "imposé" in lignes["faisceau"]
                 and "OpenVINO/whisper-large-v3-int8-ov" in lignes["modele"] and "92 %" in lignes["processeur"],
                 "225U, Qualité maximale sur la puce : large-v3 OpenVINO, glouton imposé, 92 % mesuré ailleurs",
                 str(lignes)[:400])
    bureau = poste_bureau()
    conf = copy.deepcopy(config_module.DEFAUTS)
    f = fiche.decrire(conf, bureau, {"preset": "qualite", "rythme": "vitesse"})
    lignes = {l["cle"]: l["valeur"] for s in f["sections"] for l in s["lignes"]}
    verifier("8 passages" in lignes["lots"] and lignes["faisceau"].startswith("5 ") and "int8" in lignes["precision"]
             and "35,1 %" in lignes["justesse_reunions"] and "33,1 %" in lignes["justesse_reunions"]
             and "estimation" in lignes["source"], "bureau, Qualité maximale : lots de 8, faisceau 5, int8, "
             "campagne des réunions avec OpenVINO turbo en regard, durée estimée", str(lignes)[:400])
    # Une mesure du poste change la source dite et la durée, comme sur les cartes.
    calibration.enregistrer("large-v3", "cpu", 5, 1800, 900, bureau, lot=8)
    f = fiche.decrire(conf, bureau, {"preset": "qualite", "rythme": "vitesse"})
    lignes = {l["cle"]: l["valeur"] for s in f["sections"] for l in s["lignes"]}
    verifier("mesurée sur ce poste (30 min" in lignes["source"]
             and f["cout"]["pour_une_heure"] == presets.pour_une_heure("qualite", bureau, "vitesse"),
             "mesure du poste : dite (minutes, poids), durée identique aux cartes", lignes["source"])
    calibration.oublier()


# ---------------------------------------------------------------------------
# 5 et 6. Ligne de commande et passerelle
# ---------------------------------------------------------------------------

def _python() -> tuple[str, dict]:
    base = getattr(sys, "_base_executable", sys.executable) or sys.executable
    if os.path.normcase(os.path.abspath(base)) == os.path.normcase(os.path.abspath(sys.executable)):
        return sys.executable, {}
    return base, {"PYTHONPATH": os.pathsep.join(p for p in sys.path if p.lower().endswith("site-packages"))}


def _empreinte(dossier: Path) -> dict:
    return {str(c.relative_to(dossier)): hashlib.sha256(c.read_bytes()).hexdigest()
            for c in dossier.rglob("*") if c.is_file()}


def lancer(*arguments: str) -> tuple[int, str, str]:
    python, ajout = _python()
    p = subprocess.run([python, str(RACINE / "transcriber.pyw"), *arguments], capture_output=True, timeout=120,
                       cwd=str(TEMPORAIRE), env={**os.environ, **ajout, "PYTHONIOENCODING": "utf-8"},
                       creationflags=SANS_FENETRE)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def essai_ligne_de_commande() -> None:
    titre("5. Ligne de commande : reglages decrire")
    donnees = TEMPORAIRE / "donnees"
    (donnees / "config.json").write_text(json.dumps({"langue_interface": "fr", "preset": "rapide",
                                                     "rythme": "equilibre"}), encoding="utf-8")
    avant = _empreinte(donnees)
    code, sortie, erreur = lancer("reglages", "decrire", "--json")
    enveloppe = json.loads(sortie.strip().splitlines()[-1]) if sortie.strip() else {}
    f = (enveloppe.get("donnees") or {}).get("fiche") or {}
    verifier(code == 0 and f.get("preset") == "rapide" and f.get("rythme", {}).get("choisi") == "equilibre"
             and len(f.get("sections") or []) == 5, "reglages decrire --json : le réglage en service, cinq sections",
             f"code {code} {erreur[-300:]}")
    mat, _ = materiel.detecter_au_demarrage()
    attendu = fiche.decrire(config_module.charger(), mat, {})
    verifier(f.get("sections") == attendu["sections"],
             "reglages decrire : les mêmes lignes que la fonction de la fiche")
    code, texte, erreur = lancer("reglages", "decrire", "preset=qualite", "rythme=vitesse")
    verifier(code == 0 and "Ce qui calcule" in texte and "Modèle : large-v3" in texte
             and "Rythme : Vitesse maximale" in texte and "rien n'est enregistré" in texte,
             "reglages decrire preset=qualite rythme=vitesse : texte, hypothèse dite", texte[:300] + erreur[-200:])
    code, texte, _ = lancer("reglages", "decrire", "proposition")
    verifier(code == 0 and "Si le réglage proposé est appliqué" in texte, "reglages decrire proposition", texte[:200])
    code, _, erreur = lancer("reglages", "decrire", "zoom=2")
    verifier(code == 2 and "non décrite" in erreur, "clé inconnue : code 2 et message", erreur[-200:])
    code, _, erreur = lancer("reglages", "decrire", "banc")
    verifier(code == 2 and "banc" in erreur, "sans banc d'essai mené : code 2", erreur[-200:])
    code, _, erreur = lancer("reglages", "decrire", "rythme=vite")
    verifier(code == 2, "valeur refusée (rythme=vite) : code 2", erreur[-200:])
    apres = _empreinte(donnees)
    verifier(apres == avant, "reglages decrire n'a rien écrit dans le dossier des données",
             str(sorted(set(apres) ^ set(avant)) + [c for c in avant if c in apres and avant[c] != apres[c]]))
    from app import chemins

    verifier(chemins.commande_de_lecture(["reglages", "decrire", "preset=rapide"]),
             "reglages decrire est une commande de lecture (aucun journal)")
    code, texte, _ = lancer("reglages", "--aide")
    verifier(code == 0 and "decrire" in texte, "l'aide de reglages cite decrire")


_PASSERELLE = r"""
import json, runpy, sys
sys.argv = [sys.argv[1]]
ns = runpy.run_path(sys.argv[0], run_name="essai-fiche")
p = ns["Passerelle"]()
retour = {}
for sujet, valeur in (("preset", "qualite"), ("preset", "rapide"), ("rythme", "discret"), ("auto", None),
                      ("actuel", None), ("proposition", None), ("forcer", None), ("avance", None),
                      ("automatique", None), ("banc", None), ("inconnu", None)):
    retour[f"{sujet}:{valeur}"] = p.decrire_reglage({"sujet": sujet, "valeur": valeur})
print(json.dumps(retour, ensure_ascii=False))
"""


def essai_passerelle() -> None:
    titre("6. Passerelle de la fenêtre : decrire_reglage")
    python, ajout = _python()
    p = subprocess.run([python, "-c", _PASSERELLE, str(RACINE / "transcriber.pyw")], capture_output=True,
                       timeout=120, cwd=str(TEMPORAIRE), env={**os.environ, **ajout, "PYTHONIOENCODING": "utf-8"},
                       creationflags=SANS_FENETRE)
    sortie = p.stdout.decode("utf-8", "replace").strip().splitlines()
    try:
        retour = json.loads(sortie[-1])
    except (IndexError, ValueError):
        verifier(False, "la passerelle répond", p.stderr.decode("utf-8", "replace")[-400:])
        return
    verifier(all(r.get("ok") and r.get("sections") and r.get("titre_fiche") for r in retour.values()),
             "chaque sujet a sa fiche (titre, contexte, sections)",
             str({k: r.get("message") for k, r in retour.items() if not r.get("ok")}))
    verifier([a["valeur"] for a in retour["preset:rapide"]["autres"]] == list(presets.PRESETS)
             and [a["sujet"] for a in retour["rythme:discret"]["autres"]] == ["rythme"] * 3 + ["auto"],
             "les autres choix du groupe sont proposés dans la fiche")
    verifier(retour["preset:rapide"]["modele"] == presets.MODELE_TURBO
             and retour["rythme:discret"]["rythme"]["choisi"] == "discret"
             and retour["auto:None"]["rythme"]["auto"] is True and retour["forcer:None"]["forcer_processeur"],
             "chaque fiche décrit bien son choix (preset, rythme, adaptation, processeur forcé)")
    mat, _ = materiel.detecter_au_demarrage()
    conf = config_module.charger()
    attendu = fiche.decrire(conf, mat, {"preset": "rapide"})
    verifier(retour["preset:rapide"]["sections"] == attendu["sections"],
             "la fenêtre et la fonction de la fiche disent les mêmes lignes")


def principal() -> int:
    print(f"Vérification des fiches « ce que ça change »\n{'=' * 44}")
    essai_chiffres()
    essai_fiche_contre_file()
    essai_hypotheses()
    essai_textes()
    essai_ligne_de_commande()
    essai_passerelle()
    print(f"\n{_reussites} contrôles réussis, {len(_echecs)} en échec.")
    for libelle in _echecs:
        print(f"  ECHEC : {libelle}")
    return 1 if _echecs else 0


if __name__ == "__main__":
    sys.exit(principal())
