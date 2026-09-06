"""
Scribouille : paquet applicatif.

Moteur unique : faster-whisper (CTranslate2), CPU int8 partout, CUDA float16
si une carte NVIDIA est detectee. Diarisation optionnelle via pyannote.audio,
sequencee apres la transcription pour limiter le pic memoire, et installable
depuis l'application elle-meme (voir app/extensions.py).
"""

VERSION = "2.4.0"

# Nom d'affichage. L'application s'est appelee WhiScribe jusqu'a la 2.3.3 : le
# nom collisionnait avec deux autres projets. Deux choses NE SUIVENT PAS le
# renommage, pour ne rien casser sur les postes deja equipes :
#   - le dossier de donnees %LOCALAPPDATA%\WhiScribe (voir app/chemins.py) ;
#   - l'identifiant Inno du programme d'installation (voir packaging/setup.iss),
#     qui est ce qui fait qu'une version se pose PAR-DESSUS l'ancienne.
NOM_APPLICATION = "Scribouille"

# Source unique de l'adresse du depot. A ajuster une seule fois ici si le nom du
# depot change : l'interface et la recette PyInstaller la relisent. Le script
# Inno Setup la porte de son cote, dans packaging/setup.iss.
URL_PROJET = "https://github.com/BurN-30/scribouille"
EDITEUR = "Nathan SACCOL"


# ---------------------------------------------------------------------------
# Transfert des modeles : HTTPS classique, jamais le backend « xet »
# ---------------------------------------------------------------------------
#
# huggingface_hub sait descendre les poids de deux facons : le HTTPS ordinaire,
# et un protocole maison, « xet », servi par une bibliotheque native separee
# (hf_xet) et par des hotes qui lui sont propres. Le 21 aout 2026, sur le reseau
# personnel de Nathan, ce second chemin rendait la main EN UNE SECONDE sans
# transferer un octet, alors que le meme fichier se telechargeait sans probleme
# depuis un navigateur : le hub n'a rien dit, l'application a cru tenir un
# modele, et le moteur a echoue plus loin sur un « model.bin » absent.
#
# On coupe donc xet, une bonne fois, AVANT que huggingface_hub ne soit importe :
# la bibliotheque lit cette variable au moment ou son module « constants » est
# charge, la poser ensuite n'aurait plus aucun effet. C'est la raison d'etre de
# ces lignes ici, dans le tout premier module du paquet, et pas ailleurs.
#
# `setdefault` et non une affectation : un utilisateur qui pose lui-meme la
# variable, dans un sens ou dans l'autre, garde le dernier mot.
import os as _os  # noqa: E402

_os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
del _os
