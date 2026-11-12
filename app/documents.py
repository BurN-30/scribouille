"""
Texte brut d'un document : transcription ou compte rendu.

Formats lus, sans dépendance : texte (.txt, .md), sous-titres (.srt, .vtt),
compagnon JSON de Scribouille, Word (.docx, lu dans son XML) et PDF texte
(flux décompressés, opérateurs de texte, tables ToUnicode). Un PDF scanné
(images) ne contient pas de texte : il est signalé, jamais deviné.

Les en-têtes d'export de Scribouille, les horodatages et les étiquettes de
locuteur (« Locuteur 1 : », « Marie : ») sont retirés : seuls les mots dits
comptent pour l'apprentissage et la mesure.
"""

from __future__ import annotations

import html
import json
import re
import zipfile
import zlib
from pathlib import Path

EXTENSIONS = (".txt", ".md", ".srt", ".vtt", ".json", ".docx", ".pdf")


class DocumentIllisible(Exception):
    def __init__(self, motif: str):
        super().__init__(motif)
        self.motif = motif


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------

def texte_docx(chemin: Path) -> str:
    try:
        with zipfile.ZipFile(chemin) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile, OSError) as exc:
        raise DocumentIllisible("docx_illisible") from exc
    xml = re.sub(r"<w:tab\b[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:(?:br|cr)\b[^>]*/>", "\n", xml)
    xml = re.sub(r"</w:p>", "\n", xml)
    morceaux = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|(\n)|(\t)", xml)
    texte = "".join(t or n or (" " if tab else "") for t, n, tab in morceaux)
    return html.unescape(texte)


# ---------------------------------------------------------------------------
# PDF texte (sous-ensemble suffisant pour les exports de traitements de texte)
# ---------------------------------------------------------------------------

_OBJET = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)


def _flux(corps: bytes) -> bytes | None:
    debut = corps.find(b"stream")
    if debut < 0:
        return None
    debut += 6
    if corps[debut:debut + 2] == b"\r\n":
        debut += 2
    elif corps[debut:debut + 1] in (b"\n", b"\r"):
        debut += 1
    fin = corps.rfind(b"endstream")
    brut = corps[debut:fin if fin > 0 else len(corps)]
    dico = corps[:corps.find(b"stream")]
    if b"/FlateDecode" in dico:
        try:
            return zlib.decompress(brut)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(brut)
            except zlib.error:
                return None
    if b"/Filter" in dico:
        return None
    return brut


def _cmap(donnees: bytes) -> dict[int, str]:
    table: dict[int, str] = {}

    def unicode_de(hexa: bytes) -> str:
        octets = bytes.fromhex(hexa.decode("ascii"))
        try:
            return octets.decode("utf-16-be")
        except UnicodeDecodeError:
            return ""

    for bloc in re.findall(rb"beginbfchar(.*?)endbfchar", donnees, re.S):
        for source, cible in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", bloc):
            table[int(source, 16)] = unicode_de(cible)
    for bloc in re.findall(rb"beginbfrange(.*?)endbfrange", donnees, re.S):
        for debut, fin, cible in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])", bloc):
            a, b = int(debut, 16), int(fin, 16)
            if cible.startswith(b"["):
                for k, element in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", cible)):
                    table[a + k] = unicode_de(element)
            else:
                base = bytes.fromhex(cible[1:-1].decode("ascii"))
                for k in range(0, min(b - a, 65535) + 1):
                    valeur = int.from_bytes(base, "big") + k
                    try:
                        table[a + k] = valeur.to_bytes(len(base), "big").decode("utf-16-be")
                    except (UnicodeDecodeError, OverflowError):
                        pass
    return table


def _chaine_litterale(donnees: bytes, i: int) -> tuple[bytes, int]:
    profondeur, sortie = 1, bytearray()
    i += 1
    while i < len(donnees) and profondeur:
        c = donnees[i]
        if c == 0x5C:  # barre oblique inverse
            suite = donnees[i + 1:i + 2]
            echappes = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
                        b"(": b"(", b")": b")", b"\\": b"\\"}
            if suite in echappes:
                sortie += echappes[suite]
                i += 2
                continue
            octal = re.match(rb"[0-7]{1,3}", donnees[i + 1:i + 4])
            if octal:
                sortie.append(int(octal.group(0), 8) & 0xFF)
                i += 1 + len(octal.group(0))
                continue
            i += 2
            continue
        if c == 0x28:
            profondeur += 1
        elif c == 0x29:
            profondeur -= 1
            if not profondeur:
                return bytes(sortie), i + 1
        sortie.append(c)
        i += 1
    return bytes(sortie), i


def _texte_flux(contenu: bytes, cmaps: dict[bytes, dict[int, str]]) -> str:
    sortie: list[str] = []
    police: dict[int, str] | None = None
    largeur = 1
    pile: list = []
    i = 0
    while i < len(contenu):
        trouve = re.compile(rb"\s+").match(contenu, i)
        if trouve:
            i = trouve.end()
            continue
        c = contenu[i:i + 1]
        if c == b"(":
            valeur, i = _chaine_litterale(contenu, i)
            pile.append(valeur)
            continue
        if c == b"<" and contenu[i:i + 2] != b"<<":
            fin = contenu.find(b">", i)
            hexa = re.sub(rb"\s", b"", contenu[i + 1:fin])
            if len(hexa) % 2:
                hexa += b"0"
            try:
                pile.append(bytes.fromhex(hexa.decode("ascii")))
            except ValueError:
                pass
            i = fin + 1
            continue
        if c == b"[":
            pile.append("[")
            i += 1
            continue
        if c == b"]":
            elements = []
            while pile and pile[-1] != "[":
                elements.append(pile.pop())
            if pile:
                pile.pop()
            pile.append(list(reversed(elements)))
            i += 1
            continue
        trouve = re.compile(rb"/[^\s/\[\]()<>{}]+|-?\d*\.?\d+|[A-Za-z'\"*]+|<<|>>|.", re.S).match(contenu, i)
        if not trouve:
            break
        jeton = trouve.group(0)
        i = trouve.end()
        if jeton.startswith(b"/"):
            pile.append(jeton)
            continue
        if re.fullmatch(rb"-?\d*\.?\d+", jeton):
            pile.append(float(jeton))
            continue
        operateur = jeton

        def decoder(octets: bytes) -> str:
            if police:
                if largeur == 2:
                    return "".join(police.get(int.from_bytes(octets[k:k + 2], "big"), "")
                                   for k in range(0, len(octets) - 1, 2))
                return "".join(police.get(o, chr(o)) for o in octets)
            return octets.decode("latin-1")

        if operateur == b"Tf":
            nom = next((p for p in reversed(pile) if isinstance(p, bytes) and p.startswith(b"/")), b"")
            police = cmaps.get(nom[1:])
            largeur = 2 if police and max(police, default=0) > 255 else 1
            if police and nom[1:] in _LARGEURS:
                largeur = _LARGEURS[nom[1:]]
        elif operateur in (b"Tj", b"'", b'"'):
            if operateur != b"Tj":
                sortie.append("\n")
            chaine = next((p for p in reversed(pile) if isinstance(p, bytes) and not p.startswith(b"/")), b"")
            sortie.append(decoder(chaine))
        elif operateur == b"TJ":
            tableau = next((p for p in reversed(pile) if isinstance(p, list)), [])
            for element in tableau:
                if isinstance(element, bytes):
                    sortie.append(decoder(element))
                elif isinstance(element, float) and element < -200:
                    sortie.append(" ")
        elif operateur in (b"Td", b"TD", b"T*", b"Tm"):
            sortie.append("\n" if operateur != b"Tm" else " ")
        elif operateur == b"ET":
            sortie.append("\n")
        pile = []
    return "".join(sortie)


_LARGEURS: dict[bytes, int] = {}


def texte_pdf(chemin: Path) -> str:
    try:
        donnees = chemin.read_bytes()
    except OSError as exc:
        raise DocumentIllisible("pdf_illisible") from exc
    if not donnees.startswith(b"%PDF"):
        raise DocumentIllisible("pdf_illisible")
    objets = {int(m.group(1)): m.group(3) for m in _OBJET.finditer(donnees)}
    # Polices : nom de ressource -> table ToUnicode.
    cmaps: dict[bytes, dict[int, str]] = {}
    _LARGEURS.clear()
    for corps in objets.values():
        for nom, numero in re.findall(rb"/(F\w*|[A-Za-z]\w*)\s+(\d+)\s+0\s+R", corps):
            police = objets.get(int(numero), b"")
            if b"/Font" not in police:
                continue
            ref = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", police)
            if ref and int(ref.group(1)) in objets:
                flux = _flux(objets[int(ref.group(1))])
                if flux:
                    cmaps[nom] = _cmap(flux)
                    plage = re.search(rb"begincodespacerange\s*<([0-9A-Fa-f]+)>", flux)
                    _LARGEURS[nom] = len(plage.group(1)) // 2 if plage else 1
    pages: list[str] = []
    for corps in objets.values():
        if b"stream" not in corps or b"/Font" in corps[:200] or b"/Subtype /Image" in corps[:400] \
                or b"/Subtype/Image" in corps[:400]:
            continue
        flux = _flux(corps)
        if not flux or (b"Tj" not in flux and b"TJ" not in flux):
            continue
        pages.append(_texte_flux(flux, cmaps))
    texte = "\n".join(pages)
    if len(re.findall(r"\w+", texte)) < 20:
        raise DocumentIllisible("pdf_sans_texte")
    return texte


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def _nettoyer_lignes(texte: str) -> str:
    """Horodatages et étiquettes de locuteur retirés, ligne par ligne."""
    from .comparaison import _HORODATAGE_LIGNE, _NOM_PUIS_HEURE, _sans_locuteur

    lignes = []
    for ligne in texte.replace("\r\n", "\n").split("\n"):
        if not ligne.strip() or _NOM_PUIS_HEURE.match(ligne):
            lignes.append("")
            continue
        trouve = _HORODATAGE_LIGNE.match(ligne)
        if trouve and ":" in trouve.group(1):
            ligne = ligne[trouve.end():]
        lignes.append(_sans_locuteur(ligne))
    return "\n".join(lignes)


def lire_texte(chemin: str | Path) -> str:
    """Texte d'un document, prêt à aligner. Lève DocumentIllisible."""
    chemin = Path(chemin)
    extension = chemin.suffix.lower()
    if not chemin.is_file():
        raise DocumentIllisible("absent")
    if extension == ".docx":
        return _nettoyer_lignes(texte_docx(chemin))
    if extension == ".pdf":
        return _nettoyer_lignes(texte_pdf(chemin))
    if extension in (".json", ".srt", ".vtt", ".txt", ".md", ""):
        from .comparaison import lire_reference

        try:
            reference = lire_reference(chemin)
        except (OSError, ValueError) as exc:
            raise DocumentIllisible("illisible") from exc
        if extension == ".md":
            return "\n".join(re.sub(r"^[#>*\-\s]+|[*_`]+", " ", b[2]) for b in reference.blocs)
        return "\n".join(b[2] for b in reference.blocs)
    raise DocumentIllisible("format_inconnu")


def lire_json_segments(chemin: Path) -> list[dict]:
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    return [s for s in donnees.get("segments") or [] if isinstance(s, dict)]
