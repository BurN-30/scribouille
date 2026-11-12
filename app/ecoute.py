"""
Écoute de l'enregistrement d'origine pendant la relecture.

La page de l'application est servie en `http://127.0.0.1:<port>/` par
pywebview. Un lecteur audio de cette page qui pointe vers un `file:///...` est
refusé par le navigateur intégré (« Media load rejected by URL safety
check ») : l'écoute ne pouvait donc pas marcher, quelle que soit la version.

L'audio passe donc par un petit serveur local, lui aussi sur 127.0.0.1, qui ne
sert QU'UN fichier : celui de la transcription ouverte, sous une adresse au
jeton aléatoire. Ouvrir une autre transcription remplace ce fichier ; aucune
autre adresse ne répond, aucun chemin n'est interprété. Les requêtes par plage
(`Range`) sont prises en charge : c'est ce qui permet au lecteur de se placer
au début d'un paragraphe sans tout recharger.

Bibliothèque standard seulement : rien à installer, rien à embarquer.
"""

from __future__ import annotations

import mimetypes
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import journal

#: Types déclarés à la main : la table de Windows ne les connaît pas toujours,
#: et un type faux suffit à ce que le lecteur refuse le fichier.
TYPES_AUDIO = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".mp4": "video/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg",
    ".flac": "audio/flac", ".webm": "audio/webm", ".wma": "audio/x-ms-wma",
    ".mkv": "video/x-matroska", ".mov": "video/quicktime",
}

_TAILLE_BLOC = 64 * 1024
_MOTIF_CHEMIN = re.compile(r"^/son/([A-Za-z0-9_-]{16,64})(?:\.[A-Za-z0-9]{1,5})?$")
_MOTIF_PLAGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def plage(entete: str, taille: int) -> tuple[int, int] | None:
    """
    Plage demandée par un en-tête `Range`, bornes incluses, ou None si elle est
    illisible ou hors du fichier. Une seule plage : c'est ce que demande un
    lecteur audio.
    """
    trouve = _MOTIF_PLAGE.match((entete or "").strip())
    if not trouve or taille <= 0:
        return None
    debut, fin = trouve.groups()
    if not debut and not fin:
        return None
    if not debut:
        longueur = int(fin)
        if longueur <= 0:
            return None
        return max(0, taille - longueur), taille - 1
    debut_n = int(debut)
    fin_n = min(int(fin), taille - 1) if fin else taille - 1
    if debut_n >= taille or fin_n < debut_n:
        return None
    return debut_n, fin_n


class _Gestionnaire(BaseHTTPRequestHandler):
    serveur_ecoute: "Ecoute"

    def log_message(self, *_args) -> None:  # pas de bruit dans la console
        pass

    def do_HEAD(self) -> None:
        self._servir(corps=False)

    def do_GET(self) -> None:
        self._servir(corps=True)

    def _servir(self, corps: bool) -> None:
        trouve = _MOTIF_CHEMIN.match(self.path.split("?", 1)[0])
        fichier = self.serveur_ecoute.fichier_pour(trouve.group(1)) if trouve else None
        if fichier is None or not fichier.is_file():
            self.send_error(404)
            return
        taille = fichier.stat().st_size
        type_audio = (TYPES_AUDIO.get(fichier.suffix.lower())
                      or mimetypes.guess_type(fichier.name)[0] or "application/octet-stream")
        demande = self.headers.get("Range")
        if demande:
            bornes = plage(demande, taille)
            if bornes is None:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{taille}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            debut, fin = bornes
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        else:
            debut, fin = 0, taille - 1
            self.send_response(200)
        longueur = max(0, fin - debut + 1)
        self.send_header("Content-Type", type_audio)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(longueur))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not corps:
            return
        try:
            with fichier.open("rb") as flux:
                flux.seek(debut)
                reste = longueur
                while reste > 0:
                    bloc = flux.read(min(_TAILLE_BLOC, reste))
                    if not bloc:
                        break
                    self.wfile.write(bloc)
                    reste -= len(bloc)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Le lecteur abandonne une requête dès qu'il saute ailleurs : normal.
            pass


class Ecoute:
    """Serveur local d'un seul fichier audio, démarré au premier besoin."""

    def __init__(self):
        self._verrou = threading.Lock()
        self._serveur: ThreadingHTTPServer | None = None
        self._jeton = ""
        self._fichier: Path | None = None

    def fichier_pour(self, jeton: str) -> Path | None:
        with self._verrou:
            if self._jeton and secrets.compare_digest(jeton, self._jeton):
                return self._fichier
        return None

    def _demarrer(self) -> ThreadingHTTPServer:
        if self._serveur is None:
            gestionnaire = type("GestionnaireEcoute", (_Gestionnaire,), {"serveur_ecoute": self})
            self._serveur = ThreadingHTTPServer(("127.0.0.1", 0), gestionnaire)
            self._serveur.daemon_threads = True
            threading.Thread(target=self._serveur.serve_forever, daemon=True,
                             name="ecoute-audio").start()
            journal.info("Écoute de la relecture servie sur 127.0.0.1:%s", self._serveur.server_port)
        return self._serveur

    def adresse_pour(self, chemin: str | Path) -> str:
        """
        Adresse locale du fichier, qui devient le SEUL servi. Chaîne vide si le
        fichier n'existe pas ou si le serveur n'a pas pu démarrer.
        """
        fichier = Path(chemin or "")
        if not fichier.is_file():
            return ""
        try:
            serveur = self._demarrer()
        except OSError as exc:
            journal.attention("Écoute de la relecture impossible : %s", exc)
            return ""
        with self._verrou:
            if self._fichier is None or self._fichier != fichier.resolve():
                self._fichier = fichier.resolve()
                self._jeton = secrets.token_urlsafe(24)
            jeton = self._jeton
        # L'extension n'est qu'un indice pour le lecteur : seul le jeton compte.
        return f"http://127.0.0.1:{serveur.server_port}/son/{jeton}{fichier.suffix.lower()}"

    def oublier(self) -> None:
        with self._verrou:
            self._jeton, self._fichier = "", None

    def arreter(self) -> None:
        if self._serveur is not None:
            self._serveur.shutdown()
            self._serveur.server_close()
            self._serveur = None
