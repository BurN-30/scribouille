"""
Témoin de la puce graphique (ou du NPU) : protège contre une ouverture qui fait
tomber le processus, sans prendre pour un plantage un arrêt venu de dehors.

Le fichier `openvino-chargement-en-cours.txt`, dans le dossier de données, sert
à deux choses :

  - **chargement en cours** : posé par le processus qui ouvre un modèle sur la
    puce (`moteur_openvino.MoteurOpenVINO.charger`), effacé dès que l'ouverture
    a réussi ou échoué proprement. Il dit QUI l'a posé (PID et heure de
    création du processus) et QUAND ;
  - **plantage constaté** : écrit par le superviseur (`app/superviseur.py`),
    qui voit son moteur mourir sur la puce avec un code de plantage
    (violation d'accès, arrêt du runtime C++...), ou bloqué. Seul ce verdict
    suspend la puce.

À la lecture, sans jamais rien écrire, le témoin vaut :

  « libre »       pas de témoin ;
  « en_cours »    le processus qui l'a posé vit encore : une ouverture se
                  fait en ce moment ailleurs (la fenêtre et une commande) ;
  « a_verifier »  l'ouverture n'a pas abouti mais rien ne dit que la puce a
                  planté : processus tué, console fermée, poste éteint, ou
                  témoin d'une version antérieure (3 octets, « GPU »). La
                  puce n'est PAS suspendue : la prochaine ouverture se fait,
                  dans le processus moteur (jetable : un plantage n'y coûte
                  ni la fenêtre ni la commande) et sous la garde du
                  superviseur, bornée dans le temps ; elle tranche ;
  « suspendue »   plantage constaté : le moteur habituel travaille, jusqu'à
                  ce que l'utilisateur lève la suspension (bouton de
                  l'interface, `scribouille materiel puce --lever`, nouveau
                  réglage accepté), ou que le pilote graphique, OpenVINO ou
                  Scribouille changent de version (nouvel essai, protégé).

Point d'essai : `SCRIBOUILLE_ESSAI_PUCE` simule l'échec de la puce dans
`MoteurOpenVINO.charger` (voir `essai_puce`), pour prouver le repli sur une
vraie machine. Sans la variable, rien ne change.
"""

from __future__ import annotations

import json
import os
import time

from . import chemins, journal

NOM_FICHIER = "openvino-chargement-en-cours.txt"
FORMAT = 2

#: Codes de sortie d'un arrêt venu de dehors, jamais tenus pour un plantage :
#: Ctrl+C, console fermée, fin de session (STATUS_CONTROL_C_EXIT) ; arrêt par
#: un autre programme qui choisit son code (psutil : 15 ; signal 9).
CODES_ARRET = (0xC000013A, 15, 9)
#: Codes d'un plantage : abort() du runtime C (3), exception C++ non
#: rattrapée (0xE06D7363), et toute erreur grave de Windows (0xC0000005
#: violation d'accès, 0xC0000409 arrêt rapide, 0xC0000374 tas abîmé...).
CODES_PLANTAGE = (3, 0xE06D7363, 0x80000003)

#: Valeurs de `SCRIBOUILLE_ESSAI_PUCE` comprises par `essai_puce`.
ESSAIS = ("erreur", "plantage", "blocage")


def fichier():
    return chemins.RACINE / NOM_FICHIER


# ---------------------------------------------------------------------------
# Écriture : seulement par qui ouvre la puce, ou par le superviseur
# ---------------------------------------------------------------------------

def _ecrire(contenu: dict) -> bool:
    cible = fichier()
    temporaire = cible.with_name(cible.name + f".{os.getpid()}.tmp")
    try:
        temporaire.write_text(json.dumps(contenu, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporaire, cible)
        return True
    except OSError as exc:
        journal.debug("Témoin de la puce graphique non écrit : %s", exc)
        try:
            temporaire.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _creation(pid: int) -> float:
    try:
        import psutil  # type: ignore

        return float(psutil.Process(int(pid)).create_time())
    except Exception:
        return 0.0


def _version() -> str:
    from . import VERSION

    return VERSION


def poser_chargement(peripherique: str) -> dict | None:
    """Ce processus ouvre un modèle sur `peripherique` : témoin posé, et renvoyé."""
    marque = {"format": FORMAT, "etape": "chargement", "peripherique": (peripherique or "GPU").upper(),
              "pid": os.getpid(), "cree": round(_creation(os.getpid()), 3), "pose": round(time.time(), 3),
              "parent": os.getppid() if hasattr(os, "getppid") else 0, "version": _version()}
    return marque if _ecrire(marque) else None


def lever_chargement(marque: dict | None) -> None:
    """Ouverture finie (réussie ou échouée proprement) : notre témoin s'en va, pas celui d'un autre."""
    if not marque:
        return
    brut = _lire_brut()
    if isinstance(brut, dict) and brut.get("etape") == "chargement" and brut.get("pid") == marque.get("pid") \
            and brut.get("pose") == marque.get("pose"):
        _effacer()


def lever_si_pid(pid: int | None) -> bool:
    """Le moteur `pid` a été arrêté exprès : son témoin de chargement n'est pas un plantage."""
    brut = _lire_brut()
    if pid and isinstance(brut, dict) and brut.get("etape") == "chargement" and brut.get("pid") == int(pid):
        _effacer()
        journal.info("Témoin de la puce graphique levé : moteur %s arrêté exprès pendant l'ouverture", pid)
        return True
    return False


def classer_code(code) -> str:
    """« plantage », « arret » (venu de dehors) ou « inconnu » (1 : arrêt forcé ou erreur Python)."""
    if code is None:
        return "inconnu"
    try:
        valeur = int(code) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return "inconnu"
    if valeur in CODES_ARRET:
        return "arret"
    if valeur in CODES_PLANTAGE or valeur >= 0xC0000000:
        return "plantage"
    return "inconnu"


def _pilote_graphique() -> str:
    """Version du pilote de la puce Intel, telle que la détection de fond l'a gardée."""
    try:
        from . import materiel

        lent = materiel.lire_cache() or {}
        for carte in lent.get("gpus") or []:
            if str(carte.get("vendeur") or "") == "intel":
                return str(carte.get("pilote") or "")
    except Exception:
        pass
    return ""


def _version_openvino() -> str:
    try:
        from . import materiel

        return str(((materiel.lire_cache() or {}).get("openvino") or {}).get("version") or "")
    except Exception:
        return ""


def noter_fin_moteur(peripherique: str, code, phase: str = "", cause: str = "") -> str:
    """
    Le superviseur a vu son moteur mourir sur la puce sans qu'on le demande.
    Un code de plantage (ou un blocage, `cause`) suspend la puce ; un arrêt
    venu de dehors ou un code ambigu ne la suspend pas (le témoin de
    chargement, s'il est resté, la fera vérifier à la prochaine ouverture).
    Renvoie le classement retenu.
    """
    classe = "plantage" if cause else classer_code(code)
    if classe != "plantage":
        journal.info("Moteur terminé sur %s (code %s, %s) : puce non suspendue", peripherique, code, classe)
        return classe
    _ecrire({"format": FORMAT, "etape": "plantage", "peripherique": (peripherique or "GPU").upper(),
             "code": None if code is None else int(code) & 0xFFFFFFFF, "phase": phase or "",
             "cause": cause or "plantage", "pose": round(time.time(), 3), "pid": os.getpid(),
             "version": _version(), "pilote": _pilote_graphique(), "openvino": _version_openvino()})
    journal.attention("Puce graphique suspendue : moteur tombé sur %s (code %s, %s, phase %s)",
                      peripherique, code, cause or "plantage", phase or "?")
    return classe


def lever(par: str = "") -> bool:
    """Suspension (ou témoin) levé à la demande de l'utilisateur. Vrai s'il y en avait un."""
    if not fichier().exists():
        return False
    etat_avant = etat()
    _effacer()
    journal.info("Témoin de la puce graphique levé (%s) : était %s", par or "demande", etat_avant.get("etat"))
    return True


def _effacer() -> None:
    try:
        fichier().unlink(missing_ok=True)
    except OSError as exc:
        journal.debug("Témoin de la puce graphique non effacé : %s", exc)


# ---------------------------------------------------------------------------
# Lecture : ne touche jamais au disque
# ---------------------------------------------------------------------------

def _lire_brut():
    """Le contenu du témoin : dict (format 2), texte (ancien format), ou None s'il n'y en a pas."""
    try:
        texte = fichier().read_text(encoding="utf-8", errors="replace").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return ""
    if texte.startswith("{"):
        try:
            donnees = json.loads(texte)
            if isinstance(donnees, dict):
                return donnees
        except ValueError:
            pass
    return texte


def _vivant(pid, cree) -> bool:
    """Le processus `pid` est-il celui qui a posé le témoin (même heure de création) ?"""
    try:
        import psutil  # type: ignore

        p = psutil.Process(int(pid))
        if p.status() == psutil.STATUS_ZOMBIE:
            return False
        return not cree or abs(float(p.create_time()) - float(cree)) < 1.0
    except Exception:
        return False


def _demarrage_systeme() -> float:
    try:
        import psutil  # type: ignore

        return float(psutil.boot_time())
    except Exception:
        return 0.0


def etat() -> dict:
    """
    {etat, peripherique, pose, origine, code, cause, phase, pid, vivant,
    detail} ; `etat` : libre, en_cours, a_verifier ou suspendue (voir en tête).
    Ne lit que le témoin et le cache du matériel : rien n'est écrit.
    """
    brut = _lire_brut()
    if brut is None:
        return {"etat": "libre"}
    if not isinstance(brut, dict):
        # Témoin d'une version antérieure (« GPU », 3 octets) : ni auteur ni
        # date. Rien ne dit que la puce a planté : on vérifie.
        try:
            pose = fichier().stat().st_mtime
        except OSError:
            pose = 0.0
        peripherique = str(brut or "").strip().upper()[:8] or "?"
        return {"etat": "a_verifier", "origine": "ancien_format", "peripherique": peripherique,
                "pose": round(pose, 3), "detail": "témoin sans auteur (version antérieure)"}
    peripherique = str(brut.get("peripherique") or "?").upper()
    base = {"peripherique": peripherique, "pose": brut.get("pose"), "pid": brut.get("pid"),
            "version": brut.get("version") or ""}
    if brut.get("etape") == "plantage":
        changes = []
        if brut.get("version") and brut.get("version") != _version():
            changes.append("Scribouille")
        pilote = _pilote_graphique()
        if brut.get("pilote") and pilote and pilote != brut.get("pilote"):
            changes.append("pilote graphique")
        openvino = _version_openvino()
        if brut.get("openvino") and openvino and openvino != brut.get("openvino"):
            changes.append("OpenVINO")
        commun = {**base, "code": brut.get("code"), "cause": brut.get("cause") or "plantage",
                  "phase": brut.get("phase") or ""}
        if changes:
            return {**commun, "etat": "a_verifier", "origine": "mise_a_jour",
                    "detail": "plantage constaté avant la mise à jour de : " + ", ".join(changes)}
        return {**commun, "etat": "suspendue", "origine": "plantage",
                "detail": f"{commun['cause']}, code {_code_lisible(commun['code'])}"}
    vivant = _vivant(brut.get("pid"), brut.get("cree"))
    if vivant:
        return {**base, "etat": "en_cours", "vivant": True, "origine": "chargement",
                "detail": f"ouverture en cours dans le processus {brut.get('pid')}"}
    eteint = bool(brut.get("pose")) and float(brut.get("pose") or 0) < _demarrage_systeme()
    return {**base, "etat": "a_verifier", "vivant": False, "origine": "extinction" if eteint else "coupure",
            "detail": ("poste éteint ou redémarré pendant l'ouverture" if eteint
                       else f"processus {brut.get('pid')} disparu pendant l'ouverture (arrêté, ou tombé)")}


def _code_lisible(code) -> str:
    if code is None:
        return "?"
    try:
        valeur = int(code)
    except (TypeError, ValueError):
        return str(code)
    return f"0x{valeur:08X}" if valeur > 0xFFFF else str(valeur)


def suspendue(peripherique: str = "") -> dict:
    """L'état du témoin s'il suspend `peripherique` (tous si vide), sinon un dict vide."""
    e = etat()
    if e.get("etat") != "suspendue":
        return {}
    vise = (peripherique or "").upper()
    if vise and e.get("peripherique") not in (vise, "?"):
        return {}
    return e


def resume(e: dict | None = None) -> str:
    """Une ligne en français pour la ligne de commande et le journal."""
    e = e if e is not None else etat()
    quand = ""
    if e.get("pose"):
        quand = time.strftime(" le %d/%m à %H:%M", time.localtime(float(e["pose"])))
    nom = e.get("etat")
    if nom == "libre":
        return "libre"
    if nom == "en_cours":
        return f"ouverture en cours sur {e.get('peripherique')} ({e.get('detail')})"
    if nom == "a_verifier":
        return (f"{e.get('peripherique')} à vérifier{quand} : {e.get('detail')} ; "
                "la prochaine ouverture se fait, protégée, et tranche")
    return (f"{e.get('peripherique')} suspendue{quand} : {e.get('detail')} ; "
            "« scribouille materiel puce --lever » pour réessayer")


# ---------------------------------------------------------------------------
# Point d'essai : simuler l'échec de la puce sur une vraie machine
# ---------------------------------------------------------------------------

def essai_puce() -> str:
    """Valeur de `SCRIBOUILLE_ESSAI_PUCE` si elle est reconnue, sinon vide (usage normal)."""
    valeur = os.environ.get("SCRIBOUILLE_ESSAI_PUCE", "").strip().lower()
    return valeur if valeur in ESSAIS else ""


def simuler_echec(peripherique: str) -> None:
    """
    Appelé par `MoteurOpenVINO.charger` sur la puce ou le NPU, après la pose
    du témoin et avant toute ouverture réelle. Sans la variable : rien.
      erreur    OpenVINO lève une erreur (repli propre sur le processeur) ;
      plantage  le processus tombe comme une violation d'accès (0xC0000005) :
                le superviseur suspend la puce et rejoue le fichier sans elle ;
      blocage   l'ouverture ne rend jamais la main (garde du superviseur).
    """
    essai = essai_puce()
    if not essai or (peripherique or "CPU").upper() == "CPU":
        return
    journal.attention("ESSAI (SCRIBOUILLE_ESSAI_PUCE=%s) : échec simulé de %s", essai, peripherique)
    if essai == "erreur":
        raise RuntimeError(f"échec simulé de {peripherique} (SCRIBOUILLE_ESSAI_PUCE=erreur)")
    if essai == "plantage":
        import logging

        logging.shutdown()
        os._exit(-1073741819)  # 0xC0000005, comme une violation d'accès du greffon GPU
    while True:
        time.sleep(3600)
