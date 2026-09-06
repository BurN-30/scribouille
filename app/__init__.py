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
