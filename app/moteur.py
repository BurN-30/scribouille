"""
Moteur de transcription : faster-whisper (CTranslate2).

Choix d'architecture assumé pour la v1 : un seul moteur.
  - CPU partout en int8, c'est le meilleur rapport vitesse / mémoire / qualité ;
  - CUDA float16 uniquement si une carte NVIDIA répond.

Le modèle est chargé puis explicitement libéré : la diarisation ne démarre
jamais tant que le modèle de transcription occupe encore la mémoire. C'est ce
séquencement qui permet de faire tenir large-v3 plus pyannote dans 16 Go.

TÉLÉCHARGEMENT ET REPRISE
-------------------------
Les poids ne sont plus descendus par faster-whisper, mais par cet
module (`assurer_modele_telecharge`), pour trois raisons.

1. `huggingface_hub.snapshot_download` SE REPLIE EN SILENCE sur le cache quand
   le dépôt est injoignable : la panne réseau est avalée dans un `except`
   (`_snapshot_download.py`, lignes 264 à 290 de la version 1.27), puis le
   dossier déjà présent est rendu tel quel, poids manquants compris (lignes 301
   à 331). faster-whisper reçoit alors un chemin valide et CTranslate2 échoue à
   l'ouverture sur « Unable to open file 'model.bin' ». Le message parle d'un
   fichier, alors que la vraie cause est un téléchargement qui n'a pas abouti.
   On appelle donc le hub nous-mêmes et l'on RECONTRÔLE les poids après coup :
   sans « model.bin » de taille plausible, rien n'est instancié et l'incident
   est formulé en français.
2. La reprise est le comportement d'origine du hub depuis la 0.23 : chaque
   fichier est reçu sous un nom « .incomplete » puis renommé une fois complet.
   Encore faut-il ne pas effacer le dossier avant de retélécharger, ce que
   faisait la 2.3.1 : un échec à 80 % d'un fichier de 3 Go repartait de zéro.
   Un dossier incomplet est désormais COMPLÉTÉ, jamais vidé ; seule la panne
   inexpliquée (poids que faster-whisper refuse alors qu'ils paraissent sains)
   déclenche encore un effacement, une fois et une seule.
3. Un modèle déjà complet est instancié PAR SON DOSSIER (`chemin_instanciation`),
   ce qui fait prendre à faster-whisper la branche « dossier local » et ne
   produit aucun appel réseau. C'est la promesse du hors-ligne, tenue par
   construction et non par le repli d'une bibliothèque tierce.
"""

from __future__ import annotations

import gc
import os
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import audio as audio_module
from . import chemins, journal, langues, presets
from .journal import ErreurLisible
from .materiel import Materiel

# Repli de température : on part de 0 pour un décodage déterministe, et on ne
# remonte que si le décodage échoue sur un segment.
REPLI_TEMPERATURE = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass
class Mot:
    """
    Un mot et la probabilité que le modèle lui accorde.

    faster-whisper la fournit d'origine avec `word_timestamps=True`, sans
    surcoût notable. Elle sert à signaler dans la vue de lecture les passages
    entendus avec le moins de certitude, ceux qu'il vaut mieux réécouter.
    """

    texte: str
    debut: float
    fin: float
    probabilite: float


@dataclass
class Segment:
    debut: float
    fin: float
    texte: str
    locuteur: str = ""
    mots: list[Mot] = field(default_factory=list)


def identifiant_depot(modele: str) -> str:
    """Nom du dépôt Hugging Face correspondant à un nom court de modèle."""
    try:
        from faster_whisper.utils import _MODELS  # type: ignore

        return _MODELS.get(modele, modele)
    except Exception:
        return modele


# ---------------------------------------------------------------------------
# Intégrité d'un modèle déjà présent sur le disque
#
# Un téléchargement interrompu laisse le dossier du modèle en place, sans ses
# poids. huggingface_hub considère alors le dépôt comme « en cache » et
# faster-whisper échoue à l'ouverture avec un RuntimeError sur « model.bin ».
# L'utilisateur n'y peut rien depuis l'interface : c'est donc à l'application de
# reconnaître cet état et de le réparer elle-même.
#
# Deux formes de rangement coexistent selon la version de huggingface_hub et les
# privilèges du poste : les vrais fichiers sous « blobs/ » avec des liens
# symboliques dans « snapshots/<hash>/ », ou, sous Windows sans privilège, de
# vraies copies directement dans le snapshot. On ne regarde donc jamais la seule
# existence d'un chemin, toujours la taille du fichier réellement atteint, ce
# qui traverse le lien symbolique et démasque un lien mort.
# ---------------------------------------------------------------------------

#: Fichier de poids produit par CTranslate2, dans le snapshot du dépôt.
NOM_POIDS = "model.bin"

#: Fichiers que faster-whisper lit à côté des poids, et sans lesquels il refuse
#: de démarrer aussi sûrement que sans « model.bin ».
FICHIERS_ATTENDUS = ("config.json",)

#: Taille en dessous de laquelle un « model.bin » est tenu pour tronqué. Le plus
#: petit modèle publié, « tiny », pèse déjà 75 Mo : 8 Mo laisse une marge large,
#: aucun poids réel ne passe en dessous, et un fichier amorcé puis coupé n'a
#: aucune raison de passer au-dessus par hasard.
TAILLE_MINIMALE_POIDS = 8 * 1024 * 1024

#: Modèles convertis au format d'OpenVINO (moteur Intel, en option). Leurs poids
#: sont répartis entre un encodeur, un décodeur et deux tokeniseurs compilés :
#: c'est la présence de ces fichiers, de taille plausible, qui dit le modèle
#: complet. Les dépôts viennent tous de l'organisation « OpenVINO » de Hugging
#: Face, qui les publie convertis et compressés en int8.
POIDS_OPENVINO = ("openvino_encoder_model.bin", "openvino_decoder_model.bin")
FICHIERS_OPENVINO = (
    "openvino_encoder_model.xml", "openvino_decoder_model.xml",
    "openvino_tokenizer.xml", "openvino_tokenizer.bin",
    "openvino_detokenizer.xml", "openvino_detokenizer.bin",
    "generation_config.json", "config.json", "preprocessor_config.json",
    "tokenizer.json",
)
MOTIFS_OPENVINO = ("*.json", "*.xml", "*.bin", "*.txt")


def est_modele_openvino(modele: str) -> bool:
    """Le modèle désigne-t-il un dépôt ou un dossier au format d'OpenVINO ?"""
    texte = str(modele or "")
    if texte.startswith("OpenVINO/"):
        return True
    dossier = Path(texte)
    return dossier.is_dir() and (dossier / "openvino_encoder_model.xml").is_file()


#: Préfixe des dossiers de cache de huggingface_hub. Sert aussi de garde-fou :
#: rien qui ne porte ce préfixe ne sera jamais supprimé.
PREFIXE_CACHE = "models--"

#: Suffixe posé par huggingface_hub sur un fichier en cours de réception.
SUFFIXE_INCOMPLET = ".incomplete"

#: Fichiers réclamés au dépôt. Même liste que `faster_whisper.utils.download_model`,
#: recopiée parce qu'elle y est une variable locale : c'est le prix à payer pour
#: appeler le hub nous-mêmes plutôt que de subir son repli silencieux.
MOTIFS_FICHIERS = (
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
)

#: Marge appliquée au poids annoncé du modèle pour juger l'espace disque. Le
#: fichier est écrit deux fois pendant sa réception (« .incomplete » puis blob),
#: et il faut de quoi respirer ensuite : 30 % de plus que le poids annoncé.
MARGE_DISQUE = 1.3

#: Poids retenu quand le modèle demandé n'est pas au catalogue. C'est celui du
#: plus lourd des modèles publiés : mieux vaut annoncer une exigence un peu haute
#: que laisser un disque se remplir à 99 % au milieu d'un téléchargement.
POIDS_INCONNU = int(3.1 * 1024 ** 3)


def _racine_modeles(racine: str | Path | None = None) -> Path:
    return Path(str(racine)) if racine else Path(chemins.DOSSIER_MODELES)


def dossier_cache_modele(modele: str, racine: str | Path | None = None) -> Path:
    """Dossier de cache attendu pour un modèle, « models--Systran--faster-whisper-large-v3 »."""
    depot = identifiant_depot(modele)
    return _racine_modeles(racine) / (PREFIXE_CACHE + depot.replace("/", "--"))


def _taille_reelle(chemin: Path) -> int | None:
    """Taille du fichier réellement atteint, None s'il manque ou si le lien est mort."""
    try:
        return chemin.stat().st_size
    except OSError:
        return None


def _fichiers_en_cours(dossier: Path) -> int:
    """Nombre de fichiers « .incomplete » laissés par un téléchargement coupé."""
    try:
        return sum(1 for f in dossier.rglob("*" + SUFFIXE_INCOMPLET))
    except OSError:
        return 0


def _analyser_snapshot(snapshot: Path, openvino: bool = False) -> tuple[str, str]:
    """(« complet » ou « incomplet », motif) pour un dossier contenant les poids."""
    if openvino:
        for nom in POIDS_OPENVINO:
            taille = _taille_reelle(snapshot / nom)
            if taille is None:
                return "incomplet", f"{nom} absent de « {snapshot.name} »"
            if taille < TAILLE_MINIMALE_POIDS:
                return "incomplet", f"{nom} tronqué, {taille} octets"
        manquants = [nom for nom in FICHIERS_OPENVINO if _taille_reelle(snapshot / nom) is None]
        if manquants:
            return "incomplet", "fichier(s) manquant(s) : " + ", ".join(manquants)
        return "complet", ""
    poids = snapshot / NOM_POIDS
    taille = _taille_reelle(poids)
    if taille is None:
        return "incomplet", f"{NOM_POIDS} absent de « {snapshot.name} »"
    if taille < TAILLE_MINIMALE_POIDS:
        return "incomplet", f"{NOM_POIDS} tronqué, {taille} octets"
    manquants = [nom for nom in FICHIERS_ATTENDUS if _taille_reelle(snapshot / nom) is None]
    if manquants:
        return "incomplet", "fichier(s) manquant(s) : " + ", ".join(manquants)
    return "complet", ""


def _analyser_cache(dossier: Path, openvino: bool = False) -> tuple[str, str, Path | None, bool]:
    """
    (état, motif, instantané complet, réception en cours) pour un dossier de cache.

    L'instantané n'est renvoyé que s'il est utilisable : c'est lui qu'on passera
    à faster-whisper pour lui éviter tout appel réseau. « Réception en cours »
    signale des fichiers « .incomplete », donc un téléchargement à REPRENDRE et
    surtout pas un dossier à effacer.
    """
    en_cours = _fichiers_en_cours(dossier)
    if en_cours:
        return "incomplet", f"{en_cours} fichier(s) encore en cours de réception", None, True

    snapshots = dossier / "snapshots"
    try:
        candidats = sorted(d for d in snapshots.iterdir() if d.is_dir())
    except OSError:
        candidats = []
    if not candidats:
        return "incomplet", "aucun instantané téléchargé", None, False

    motifs: list[str] = []
    for snapshot in candidats:
        etat, motif = _analyser_snapshot(snapshot, openvino)
        if etat == "complet":
            return "complet", "", snapshot, False
        motifs.append(motif)
    return "incomplet", " ; ".join(motifs), None, False


def _snapshot_resolu(modele: str) -> Path | None:
    """Snapshot tel que faster-whisper le résoudrait, sans le moindre appel réseau."""
    try:
        from faster_whisper.utils import download_model

        return Path(download_model(
            modele, local_files_only=True, cache_dir=str(chemins.DOSSIER_MODELES)))
    except Exception:
        return None


def modele_supprimable(modele: str, racine: str | Path | None = None) -> bool:
    """
    L'application s'autorise-t-elle à effacer le dossier de ce modèle ?

    Oui uniquement pour un dossier de cache qu'elle a elle-même créé : le bon
    préfixe, enfant direct du dossier des modèles, et présent sur le disque.
    Jamais un dossier de modèle désigné à la main par l'utilisateur.
    """
    if Path(str(modele or "")).is_dir():
        return False
    dossier = dossier_cache_modele(modele, racine)
    if not dossier.is_dir():
        return False
    if not dossier.name.startswith(PREFIXE_CACHE) or len(dossier.name) <= len(PREFIXE_CACHE):
        return False
    try:
        return dossier.parent.resolve() == _racine_modeles(racine).resolve()
    except OSError:
        return False


def etat_modele(modele: str, racine: str | Path | None = None) -> dict:
    """
    État d'un modèle sur ce poste, avant tout chargement.

    Trois réponses possibles, et une seule demande une action :

      - « absent » : rien sur le disque, c'est le premier usage, déjà géré ;
      - « complet » : les poids sont là et utilisables, rien à faire ;
      - « incomplet » : le dossier existe mais les poids manquent ou sont
        tronqués, il faut l'effacer et retélécharger.

    `reparable` dit si l'application s'autorise à supprimer ce dossier : jamais
    un dossier de modèle désigné à la main par l'utilisateur, uniquement un
    dossier de cache qu'elle a elle-même créé sous le dossier des modèles.
    """
    openvino = est_modele_openvino(modele)
    fourni = Path(str(modele or ""))
    if fourni.is_dir():
        etat, motif = _analyser_snapshot(fourni, openvino)
        return {
            "etat": etat, "dossier": str(fourni), "motif": motif, "reparable": False,
            "snapshot": str(fourni) if etat == "complet" else "", "reception_en_cours": False,
        }

    dossier = dossier_cache_modele(modele, racine)
    if dossier.is_dir():
        etat, motif, snapshot, en_cours = _analyser_cache(dossier, openvino)
        return {
            "etat": etat,
            "dossier": str(dossier),
            "motif": motif,
            "reparable": etat == "incomplet" and modele_supprimable(modele, racine),
            "snapshot": str(snapshot) if snapshot else "",
            "reception_en_cours": en_cours,
        }

    # Le dossier n'est pas là où on l'attend : plutôt que de conclure trop vite
    # à l'absence, on laisse faster-whisper résoudre le cache à sa façon. Un
    # modèle bien présent ne doit jamais être annoncé comme à télécharger, un
    # poste hors ligne s'en trouverait bloqué pour rien.
    resolu = _snapshot_resolu(modele) if racine is None and not openvino else None
    if resolu is not None and resolu.is_dir():
        etat, motif = _analyser_snapshot(resolu)
        return {
            "etat": etat, "dossier": str(resolu), "motif": motif, "reparable": False,
            "snapshot": str(resolu) if etat == "complet" else "", "reception_en_cours": False,
        }

    return {
        "etat": "absent", "dossier": str(dossier), "motif": "", "reparable": False,
        "snapshot": "", "reception_en_cours": False,
    }


def modele_deja_telecharge(modele: str) -> bool:
    """
    Le modèle est-il sur le disque ET utilisable ?

    Raccourci de lecture sur `etat_modele`, conservé parce qu'il se lit mieux
    là où seule la réponse binaire compte. Un modèle incomplet répond non : le
    donner pour présent laisserait croire qu'il est prêt à servir.
    """
    try:
        return etat_modele(modele)["etat"] == "complet"
    except Exception:
        return False


def _forcer_suppression(fonction, chemin, _infos) -> None:
    """Deuxième chance sur un fichier en lecture seule, fréquent dans un cache."""
    try:
        os.chmod(chemin, stat.S_IWRITE)
        fonction(chemin)
    except OSError:
        pass


def supprimer_modele(modele: str, racine: str | Path | None = None) -> bool:
    """
    Efface le dossier de cache d'un seul modèle, et rien d'autre.

    Trois gardes avant le moindre effacement : le dossier porte le préfixe des
    caches huggingface, il est un enfant direct du dossier des modèles, et il
    existe. Un chemin qui manque une seule de ces conditions n'est pas touché.
    """
    dossier = dossier_cache_modele(modele, racine)
    parent = _racine_modeles(racine)
    try:
        legitime = (
            dossier.name.startswith(PREFIXE_CACHE)
            and len(dossier.name) > len(PREFIXE_CACHE)
            and dossier.parent.resolve() == parent.resolve()
        )
    except OSError:
        legitime = False
    if not legitime:
        journal.attention("Suppression refusée, chemin inattendu : %s", dossier)
        return False
    if not dossier.is_dir():
        return False

    journal.info("Suppression du modèle incomplet : %s", dossier)
    try:
        shutil.rmtree(dossier, onerror=_forcer_suppression)
    except OSError as exc:
        journal.attention("Suppression de %s impossible : %s", dossier, exc)

    # Le verrou posé par huggingface_hub à côté ne gêne personne s'il subsiste,
    # mais autant ne rien laisser derrière soi.
    verrou = parent / ".locks" / dossier.name
    if verrou.is_dir():
        shutil.rmtree(verrou, ignore_errors=True)

    return not dossier.exists()


def reparer_modele(modele: str, etat: dict | None = None,
                   signaler: Callable[[str, str], None] | None = None) -> bool:
    """
    Efface un modèle pour que le téléchargement reparte de zéro.

    Dernier recours, appelé par le seul filet de sécurité : des poids que la
    vérification tient pour sains mais que CTranslate2 refuse d'ouvrir. Le cas
    ordinaire d'un dossier incomplet ne passe plus par ici, il est COMPLÉTÉ par
    `assurer_modele_telecharge`, ce qui préserve la reprise du téléchargement.
    Le retéléchargement lui-même suit immédiatement, côté appelant.
    """
    etat = etat or etat_modele(modele)
    journal.attention(
        "Modèle %s incomplet (%s), dossier %s",
        nom_court(modele), etat.get("motif") or "cause non identifiée", etat.get("dossier"),
    )
    supprime = supprimer_modele(modele)
    if signaler:
        if supprime:
            signaler("attention", langues.t(
                "moteur.modele_incomplet",
                modele=nom_court(modele), taille=taille_annoncee(modele)))
        else:
            signaler("attention", langues.t(
                "moteur.modele_incomplet_bloque",
                modele=nom_court(modele), dossier=etat.get("dossier", "")))
    return supprime


def _poids_illisible(exc: BaseException) -> bool:
    """L'exception de faster-whisper qui trahit des poids absents ou tronqués."""
    texte = f"{type(exc).__name__}: {exc}".lower()
    return NOM_POIDS in texte or "unable to open file" in texte


# ---------------------------------------------------------------------------
# Téléchargement des poids, mené par l'application
#
# Tout ce qui suit ne s'exécute QUE si le modèle demandé n'est pas déjà complet
# sur le disque. Un poste hors ligne dont le modèle est en place ne touche aucune
# de ces fonctions, pas même le test de connexion.
# ---------------------------------------------------------------------------

class EchecTelechargement(ErreurLisible):
    """
    Les poids n'ont pas pu être descendus, et l'on sait dire pourquoi.

    Sous-classe d'`ErreurLisible` : `journal.expliquer` la laisse passer telle
    quelle, l'utilisateur voit donc la phrase écrite ici et jamais un traceback.
    """


def poids_attendu_octets(modele: str) -> int:
    """Poids annoncé du modèle, en octets. Sert à juger l'espace disque libre."""
    if modele in presets.POIDS_OPENVINO:
        return int(presets.POIDS_OPENVINO[modele])
    for avance in presets.MODELES_AVANCES:
        if modele in (avance["cle"], avance["nom"]):
            return int(avance["octets"])
    for p in presets.PRESETS.values():
        if p["modele"] == modele:
            return int(p["telechargement_go"] * 1024 ** 3)
    return POIDS_INCONNU


def espace_libre_octets(dossier: str | Path) -> int:
    """
    Espace libre sur le volume du dossier, -1 s'il est indéterminable.

    Le dossier des modèles peut ne pas encore exister : on remonte alors aux
    parents, le volume est le même.
    """
    cible = Path(str(dossier)).expanduser()
    for candidat in [cible, *cible.parents]:
        if candidat.exists():
            try:
                return shutil.disk_usage(str(candidat)).free
            except OSError:
                return -1
    return -1


def _manque_de_place(exc: BaseException) -> bool:
    """L'exception trahit-elle un disque plein plutôt qu'un incident réseau ?"""
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return True
    texte = f"{type(exc).__name__}: {exc}".lower()
    return any(motif in texte for motif in (
        "no space left", "espace insuffisant", "not enough space", "disk full",
    ))


def _echouer(signaler, titre: str, message: str, cause: BaseException | None = None):
    """Journalise, prévient l'interface, puis lève. Un seul endroit pour les trois."""
    journal.erreur("%s : %s", titre, message)
    if signaler:
        signaler("erreur", message)
    raise EchecTelechargement(titre, message, cause)


def _telecharger(modele: str) -> str:
    """
    Descend les poids depuis Hugging Face, sans repli et sans filet.

    Appel direct à `snapshot_download`, avec `local_files_only=False` : ce que la
    bibliothèque avale plus loin (voir l'en-tête du module), on le laisse ici
    remonter, pour pouvoir le nommer. La reprise d'un fichier coupé est acquise :
    `hf_hub_download` retrouve le « .incomplete » déjà sur le disque et repart de
    l'octet atteint. C'est aussi la raison pour laquelle on n'efface plus le
    dossier avant de retélécharger.
    """
    from huggingface_hub import snapshot_download

    depot = identifiant_depot(modele)
    chemins.confiner_cache_huggingface()
    journal.info("Téléchargement du modèle %s depuis le dépôt %s", nom_court(modele), depot)
    with journal.SortieMuette("téléchargement du modèle"):
        return snapshot_download(
            depot,
            cache_dir=str(chemins.DOSSIER_MODELES),
            allow_patterns=list(MOTIFS_OPENVINO if est_modele_openvino(modele)
                                else MOTIFS_FICHIERS),
            local_files_only=False,
        )


def assurer_modele_telecharge(modele: str, etat: dict | None = None,
                              signaler: Callable[[str, str], None] | None = None,
                              annoncer: bool = True) -> dict:
    """
    Garantit que les poids sont là AVANT toute instanciation.

    Renvoie l'état du modèle, forcément « complet ». Lève un `EchecTelechargement`
    dans tous les autres cas, avec la cause quand elle est identifiable : espace
    disque insuffisant, dépôt injoignable, ou téléchargement qui rend un dossier
    sans « model.bin ». Aucune boucle : un seul téléchargement par appel.

    `annoncer` à faux tait la phrase d'attente : le filet de sécurité vient de
    dire à l'utilisateur que le modèle est renouvelé, inutile de le répéter.
    """
    etat = etat or etat_modele(modele)
    if etat["etat"] == "complet":
        return etat

    # Dossier de modèle désigné à la main par l'utilisateur : il n'y a pas de
    # dépôt à interroger, on ne peut que dire ce qui manque.
    if Path(str(modele or "")).is_dir():
        _echouer(signaler, langues.t("err.modele.titre"), langues.t("err.modele.msg"))

    racine = Path(chemins.DOSSIER_MODELES)
    requis = int(poids_attendu_octets(modele) * MARGE_DISQUE)
    libre = espace_libre_octets(racine)
    if 0 <= libre < requis:
        _echouer(signaler, langues.t("err.disque.titre"), langues.t(
            "moteur.disque_insuffisant",
            modele=nom_court(modele), requis=langues.octets(requis),
            libre=langues.octets(libre), dossier=str(racine)))

    if signaler and annoncer:
        if etat["etat"] == "absent":
            signaler("attention", langues.t(
                "moteur.premier_usage", taille=taille_annoncee(modele)))
        elif etat.get("reception_en_cours"):
            signaler("attention", langues.t(
                "moteur.telechargement_reprend",
                modele=nom_court(modele), taille=taille_annoncee(modele)))
        else:
            signaler("attention", langues.t(
                "moteur.modele_incomplet",
                modele=nom_court(modele), taille=taille_annoncee(modele)))
    if etat["etat"] == "incomplet":
        journal.attention(
            "Modèle %s incomplet (%s), complété par téléchargement : %s",
            nom_court(modele), etat.get("motif") or "cause non identifiée",
            etat.get("dossier"))

    if not connexion_disponible():
        _echouer(signaler, langues.t("err.reseau.titre"), langues.t(
            "moteur.reseau_indisponible",
            modele=nom_court(modele), taille=taille_annoncee(modele))
            + " " + voie_hors_ligne(modele))

    try:
        _telecharger(modele)
    except Exception as exc:
        journal.exception(f"Téléchargement du modèle {modele} impossible", exc)
        if _manque_de_place(exc):
            _echouer(signaler, langues.t("err.disque.titre"), langues.t(
                "moteur.disque_insuffisant",
                modele=nom_court(modele), requis=langues.octets(requis),
                libre=langues.octets(max(0, espace_libre_octets(racine))),
                dossier=str(racine)), exc)
        _echouer(signaler, langues.t("moteur.telechargement_echoue.titre"), langues.t(
            "moteur.telechargement_echoue.msg",
            modele=nom_court(modele), taille=taille_annoncee(modele),
            requis=langues.octets(requis)) + " " + voie_hors_ligne(modele), exc)

    # Le hub a rendu la main sans se plaindre : cela ne prouve rien. Tant que
    # « model.bin » n'est pas là et de taille plausible, on n'instancie pas.
    apres = etat_modele(modele)
    if apres["etat"] != "complet":
        journal.attention(
            "Téléchargement terminé mais modèle toujours incomplet (%s)",
            apres.get("motif") or "cause non identifiée")
        _echouer(signaler, langues.t("moteur.telechargement_echoue.titre"), langues.t(
            "moteur.telechargement_echoue.msg",
            modele=nom_court(modele), taille=taille_annoncee(modele),
            requis=langues.octets(requis)) + " " + voie_hors_ligne(modele))
    journal.info("Modèle %s complet : %s", nom_court(modele), apres.get("snapshot"))
    return apres


def voie_hors_ligne(modele: str) -> str:
    """
    Phrase qui explique comment poser le modèle sans réseau.

    Un poste d'entreprise peut filtrer Hugging Face pour de bon. Le dossier de
    cache d'un modèle est autonome : recopié tel quel depuis un poste qui l'a
    déjà téléchargé, il est reconnu sans le moindre appel réseau (voir
    `chemin_instanciation`).
    """
    return langues.t(
        "moteur.hors_ligne",
        dossier_cache=dossier_cache_modele(modele).name,
        dossier=str(chemins.DOSSIER_MODELES),
        depot=identifiant_depot(modele),
    )


def chemin_instanciation(modele: str) -> str:
    """
    Chemin réellement passé à faster-whisper.

    Un modèle complet est désigné par son DOSSIER : faster-whisper prend alors la
    branche « dossier local » et ne joint jamais le réseau. Désigné par son nom de
    dépôt, il passerait au contraire par `snapshot_download`, donc par une requête
    au hub à chaque chargement, hors ligne comprise.
    """
    try:
        etat = etat_modele(modele)
    except Exception:
        return modele
    if etat.get("etat") == "complet" and etat.get("snapshot"):
        return str(etat["snapshot"])
    return modele


class MoteurTranscription:
    """Enveloppe autour de WhisperModel, avec libération explicite."""

    def __init__(self, mat: Materiel, forcer_processeur: bool = False):
        self.materiel = mat
        self.forcer_processeur = forcer_processeur
        self._modele = None
        self._nom_modele = ""
        #: Modèles déjà effacés puis redescendus par le filet de sécurité. Une
        #: fois par modèle et par file de traitement, jamais deux : sans cette
        #: mémoire, chaque fichier de la file relançait la même réparation.
        self._reparations: set[str] = set()
        #: Fils de calcul imposés par le rythme (`app/rythme.py`), 0 : ceux
        #: du poste. Lus au chargement du modèle.
        self.fils = 0

    # -- cycle de vie ------------------------------------------------------

    @property
    def peripherique(self) -> str:
        if self.forcer_processeur:
            return "cpu"
        return self.materiel.peripherique

    @property
    def type_calcul(self) -> str:
        return "float16" if self.peripherique == "cuda" else "int8"

    @property
    def cle_calcul(self) -> str:
        """Situation de calcul pour les mesures de durée : « cpu » ou « cuda »."""
        return self.peripherique

    def charger(self, modele: str, signaler: Callable[[str, str], None] | None = None) -> None:
        if self._modele is not None and self._nom_modele == modele:
            return
        self.liberer()

        chemins.assurer_dossiers()

        # Les poids sont descendus et VÉRIFIÉS avant tout appel à faster-whisper.
        # Un téléchargement qui échoue s'arrête ici, sur une phrase en français :
        # sans cette garde, CTranslate2 lève un RuntimeError sur « model.bin » qui
        # ne dit rien de la vraie cause, et que l'utilisateur ne peut résoudre que
        # depuis un terminal.
        etat = assurer_modele_telecharge(modele, etat_modele(modele), signaler)

        journal.info(
            "Chargement du modèle %s (périphérique=%s, calcul=%s, fils=%s, état=%s)",
            modele, self.peripherique, self.type_calcul, self.fils_effectifs,
            etat["etat"],
        )
        if signaler:
            signaler("info", langues.t("moteur.chargement", modele=_nom_court(modele)))

        try:
            self._modele = self._instancier(modele)
        except Exception as exc:
            # Filet de sécurité : des poids que la vérification croit sains mais
            # que CTranslate2 refuse d'ouvrir. On efface et l'on redescend, une
            # fois par modèle et par file. Jamais de boucle.
            if (not _poids_illisible(exc) or not modele_supprimable(modele)
                    or modele in self._reparations):
                journal.exception(f"Chargement du modèle {modele} impossible", exc)
                raise
            self._reparations.add(modele)
            journal.attention("Poids illisibles au chargement, réparation puis nouvel essai")
            reparer_modele(modele, signaler=signaler)
            assurer_modele_telecharge(modele, None, signaler, annoncer=False)
            try:
                self._modele = self._instancier(modele)
            except Exception as second:
                journal.exception(f"Chargement du modèle {modele} impossible", second)
                raise
        self._nom_modele = modele

    def _instancier(self, modele: str):
        from faster_whisper import WhisperModel

        with journal.SortieMuette("chargement du modèle"):
            return WhisperModel(
                chemin_instanciation(modele),
                device=self.peripherique,
                compute_type=self.type_calcul,
                cpu_threads=self.fils_effectifs,
                num_workers=1,
                download_root=str(chemins.DOSSIER_MODELES),
            )

    @property
    def fils_effectifs(self) -> int:
        return int(self.fils) if self.fils and self.fils > 0 else self.materiel.fils_calcul

    def liberer(self) -> None:
        """Déréférence le modèle et rend la mémoire avant l'étape suivante."""
        if self._modele is None:
            return
        journal.info("Libération du modèle %s", self._nom_modele)
        self._modele = None
        self._nom_modele = ""
        gc.collect()

    @property
    def tokeniseur(self):
        return getattr(self._modele, "hf_tokenizer", None)

    # -- transcription -----------------------------------------------------

    def transcrire(
        self,
        signal: np.ndarray,
        duree_totale: float,
        langue: str,
        reglages: dict,
        amorce: str = "",
        progression: Callable[[float], None] | None = None,
        interrompu: Callable[[], bool] | None = None,
        decalage: float = 0.0,
        sur_segment: Callable[[Segment], None] | None = None,
    ) -> tuple[list[Segment], dict]:
        """
        Transcrit un signal déjà décodé.

        `decalage` déplace tous les horodatages : il vaut zéro en temps normal,
        et la position atteinte quand on reprend une transcription interrompue,
        où seule la fin du signal est repassée au modèle.

        `sur_segment` est appelé pour chaque segment dès qu'il sort du décodeur.
        C'est le point d'accroche de la sauvegarde progressive : le moteur
        produit déjà les segments un par un, rien n'est mis en tampon pour lui.
        """
        if self._modele is None:
            raise ErreurLisible(
                langues.t("moteur.non_charge.titre"),
                langues.t("moteur.non_charge.msg"),
            )

        beam = int(reglages.get("beam_size") or 5)
        options = dict(
            language=(langue or None) if langue != "auto" else None,
            task="transcribe",
            beam_size=beam,
            best_of=max(beam, int(reglages.get("best_of") or beam)),
            temperature=list(REPLI_TEMPERATURE),
            condition_on_previous_text=bool(reglages.get("condition_on_previous_text", True)),
            initial_prompt=amorce or None,
            vad_filter=bool(reglages.get("vad", True)),
            word_timestamps=True,
            no_speech_threshold=0.6,
            compression_ratio_threshold=2.4,
            hallucination_silence_threshold=2.0 if reglages.get("vad", True) else None,
        )
        if options["vad_filter"]:
            options["vad_parameters"] = {"min_silence_duration_ms": 500}

        # Traitement par lots : les passages de parole repérés par le VAD sont
        # décodés plusieurs à la fois. Chaque passage est alors transcrit sans le
        # texte du précédent (pas de condition_on_previous_text, pas de repli de
        # température ni de seuil de compression), ce qui supprime aussi les
        # boucles de répétition qui se propagent d'une fenêtre à l'autre. Le VAD
        # est obligatoire dans ce mode : sans lui, rien ne découpe le signal.
        lot = int(reglages.get("lot") or 0)
        par_lots = lot > 1 and options["vad_filter"]

        journal.info(
            "Transcription : langue=%s, beam=%s, VAD=%s, lots=%s, amorce=%s caractères",
            langue, beam, options["vad_filter"], lot if par_lots else "non", len(amorce),
        )

        with journal.SortieMuette("transcription"):
            if par_lots:
                from faster_whisper import BatchedInferencePipeline

                for inutile in ("condition_on_previous_text", "hallucination_silence_threshold"):
                    options.pop(inutile, None)
                options["temperature"] = 0.0
                # Horodatages internes conservés : sans eux, un segment couvre
                # tout un passage du VAD (jusqu'à 30 s), illisible en sous-titre.
                options["without_timestamps"] = False
                iterateur, info = BatchedInferencePipeline(model=self._modele).transcribe(
                    signal, batch_size=lot, **options)
            else:
                iterateur, info = self._modele.transcribe(signal, **options)

            # Rythme « je travaille en même temps » : une pause après chaque
            # morceau de calcul, à proportion de sa durée (voir app/rythme.py).
            frein = reglages.get("frein")
            if frein is not None:
                frein.depart()
            segments: list[Segment] = []
            for brut in iterateur:
                if interrompu is not None and interrompu():
                    journal.attention("Transcription interrompue à la demande de l'utilisateur")
                    raise Interruption()
                if frein is not None:
                    frein()
                texte = (brut.text or "").strip()
                if texte:
                    segment = Segment(
                        debut=brut.start + decalage,
                        fin=brut.end + decalage,
                        texte=texte,
                        mots=_mots_du_segment(brut, decalage),
                    )
                    segments.append(segment)
                    if sur_segment is not None:
                        sur_segment(segment)
                if progression and duree_totale > 0:
                    progression(min(0.99, (brut.end + decalage) / duree_totale))

        if progression:
            progression(1.0)

        details = {
            "langue": getattr(info, "language", langue),
            "probabilite_langue": round(float(getattr(info, "language_probability", 0) or 0), 3),
            "duree": float(getattr(info, "duration", duree_totale) or duree_totale),
            "modele": self._nom_modele,
            "peripherique": self.peripherique,
            "type_calcul": self.type_calcul,
        }
        journal.info(
            "Transcription terminée : %s segments, langue détectée %s",
            len(segments), details["langue"],
        )
        return segments, details


def _mots_du_segment(brut, decalage: float = 0.0) -> list[Mot]:
    """
    Extrait les mots et leur probabilité d'un segment de faster-whisper.

    Le décodeur les fournit déjà, `word_timestamps` étant activé pour attribuer
    les locuteurs. Un modèle ou une version qui ne les donnerait pas renvoie
    simplement une liste vide, et la vue de lecture s'en passe.
    """
    resultat: list[Mot] = []
    for mot in getattr(brut, "words", None) or []:
        texte = (getattr(mot, "word", "") or "").strip()
        if not texte:
            continue
        resultat.append(Mot(
            texte=texte,
            debut=float(getattr(mot, "start", 0.0) or 0.0) + decalage,
            fin=float(getattr(mot, "end", 0.0) or 0.0) + decalage,
            probabilite=float(getattr(mot, "probability", 0.0) or 0.0),
        ))
    return resultat


class Interruption(Exception):
    """Levée quand l'utilisateur demande l'arrêt de la file."""


def nom_court(modele: str) -> str:
    """« deepdml/faster-whisper-large-v3-turbo-ct2 » devient « large-v3-turbo »."""
    if "/" in modele:
        nom = modele.rsplit("/", 1)[1]
        if modele.startswith("OpenVINO/"):
            return nom.replace("whisper-", "").replace("-int8-ov", "") + " (OpenVINO)"
        return nom.replace("faster-whisper-", "").replace("-ct2", "")
    return modele


_nom_court = nom_court  # compatibilité interne


def connexion_disponible(delai: float = 4.0) -> bool:
    """
    Teste si le dépôt de modèles est joignable, avant de lancer un téléchargement.

    Une simple ouverture de socket : pas de requête, rien d'envoyé. Cela évite de
    présenter un traceback réseau à quelqu'un dont le poste est simplement isolé.
    """
    import socket

    for hote in ("huggingface.co", "cdn-lfs.huggingface.co"):
        try:
            with socket.create_connection((hote, 443), timeout=delai):
                return True
        except OSError:
            continue
    return False


def taille_annoncee(modele: str) -> str:
    if modele in presets.POIDS_OPENVINO:
        return langues.octets(presets.POIDS_OPENVINO[modele])
    taille = presets.taille_modele_avance(modele)
    if taille:
        return taille
    for p in presets.PRESETS.values():
        if p["modele"] == modele:
            return langues.octets(p["telechargement_go"] * 1024 ** 3)
    return langues.t("moteur.taille_inconnue")


def limiter_parallelisme(fils: int) -> None:
    """Borne les bibliothèques de calcul pour que la machine reste utilisable."""
    valeur = str(max(1, fils))
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(variable, valeur)


def duree_et_signal(chemin: str, filtres_salle: bool) -> tuple[np.ndarray, float]:
    signal = audio_module.decoder(chemin, filtres_salle=filtres_salle)
    return signal, signal.size / audio_module.FREQUENCE
