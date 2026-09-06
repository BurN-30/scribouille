# Passer le dépôt en public : check-list

Dépôt : **`BurN-30/scribouille`**. Le nom du dépôt est `scribouille`, en minuscules, et il est
déjà écrit en dur dans `app/__init__.py` (`URL_PROJET`), dans `packaging/setup.iss` et dans
les deux README. Ne pas le renommer sans repasser sur ces quatre endroits, sinon la
vérification des mises à jour interroge une page qui n'existe plus.

---

## 1. Avant de basculer en public

- [ ] Relire `.gitignore` : `jeton_hf.txt`, `config.json`, `logs/`, `modeles/`, `reprises/`,
      `dist/`, `build/`, `.venv/`, `packaging/sortie/`. Vérifier avec
      `git ls-files | findstr /i "jeton config.json"` qu'aucun de ces fichiers n'est suivi.
- [ ] Vérifier l'historique, pas seulement l'état courant : `git log -p -- jeton_hf.txt` et
      `git log --diff-filter=A --name-only | findstr /i "jeton"`. Un secret déjà commité
      reste dans l'historique même si le fichier a été supprimé depuis.
- [ ] `vocabulaire.txt` et `corrections.txt` versionnés doivent contenir les **exemples
      génériques**, pas des noms de collègues, de clients ou de projets internes.
- [ ] Les captures d'écran ne doivent montrer aucun nom de fichier réel, aucun chemin
      utilisateur nominatif, aucun contenu de transcription réel. Prévoir un jeu
      d'enregistrements de démonstration.
- [ ] `LICENSE` présent, MIT, au nom de Nathan SACCOL.
- [ ] Une Release existe déjà, avec le `Scribouille-Setup-X.Y.Z.exe` en pièce jointe.

---

## 2. Description courte (champ « About »)

À coller telle quelle dans le champ **About** en haut à droite du dépôt. En anglais, avec
les mots que les gens tapent réellement dans la recherche GitHub.

```
Offline speech-to-text for Windows: private, on-device audio transcription and meeting
notes powered by Whisper. No account, no cloud.
```

Version courte, si le champ paraît trop chargé :

```
Private offline transcription for Windows. Whisper speech-to-text, on your machine, no cloud.
```

Dans le même panneau **About** :

- **Website** : laisser vide (pas de site), ou pointer la page Releases.
- [ ] Cocher **Releases** dans la colonne de droite (c'est ce que les visiteurs cherchent
      en premier).
- [ ] Décocher **Packages**, **Environments** et **Deployments**, inutiles ici.

---

## 3. Topics GitHub

Les topics sont le principal levier de trouvabilité interne à GitHub, avec le titre et la
description. Vingt maximum, en voici quinze utiles, du plus au moins évident :

```
whisper
speech-to-text
transcription
offline
privacy
windows
faster-whisper
meeting-notes
desktop-app
python
audio-to-text
local-first
stt
french
no-cloud
```

Quelques remarques :

- `whisper`, `speech-to-text` et `transcription` sont les trois requêtes réelles. Elles
  sont très concurrentielles, mais leur absence rend le dépôt introuvable.
- `offline`, `privacy`, `local-first` et `no-cloud` sont le vrai différenciateur : c'est
  par là qu'arrivent les gens qui refusent d'envoyer leur audio à un service.
- `french` mérite sa place : peu d'outils clé en main visent explicitement le français.
- Éviter les topics fourre-tout du type `ai`, `machine-learning`, `tool` : trop de bruit,
  aucun retour.

Le **titre du dépôt** compte aussi dans la recherche : `scribouille` seul ne dit rien, c'est
la description qui porte les mots-clés. D'où l'importance de l'étape 2.

---

## 4. Aperçu social (social preview)

L'image affichée quand le lien est partagé sur Slack, Teams, Mastodon, LinkedIn.

- **Dimensions** : 1280 x 640 px, ratio 2:1. GitHub recommande ce format et affiche en
  1280 x 640. Poids maximum 1 Mo, PNG ou JPG.
- **Contenu** : une capture de la fenêtre principale, thème sombre, légèrement recadrée,
  avec le nom **Scribouille** et une ligne de promesse. Marge de sécurité d'environ 60 px
  sur les bords, certains clients rognent.
- **Lisibilité** : le rendu est souvent affiché à 400 px de large, donc texte gros,
  pas plus de six ou sept mots.
- **Où** : Settings, section General, **Social preview**, bouton Edit.
- À faire pendant la séance de captures, en même temps que les images du README (voir les
  commentaires `<!-- capture 1 -->`, `<!-- capture 2 -->` et `<!-- gif -->` dans les README).

---

## 5. Réglages du dépôt

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Visibilité | Public | |
| **Issues** | activées | seul canal de retour, et les gabarits sont déjà en place dans `.github/ISSUE_TEMPLATE/` |
| **Discussions** | optionnel | à activer seulement si le trafic le justifie. Tant qu'elles sont coupées, **retirer le lien Discussions de `.github/ISSUE_TEMPLATE/config.yml`**, sinon il renvoie une 404 |
| **Wiki** | désactivé | la documentation vit dans les README |
| **Projects** | désactivé | |
| **Sponsors** | désactivé | |
| Branche par défaut | `main` | |
| **Releases** épinglées dans About | oui | |
| Fusion des PR | Squash uniquement | historique lisible sur un projet à un mainteneur |
| **Suppression auto des branches** | activée | |
| Actions, permissions | lecture et écriture pour le workflow de release | il crée la Release et attache le setup |
| **Dependabot alerts** | activées | prévient sur les dépendances Python |
| **Secret scanning** | activé | gratuit sur les dépôts publics, filet pour le jeton Hugging Face |

Autres points :

- [ ] Vérifier que `.github/workflows/release.yml` ne contient aucune valeur interne
      (nom de machine, URL d'entreprise).
- [ ] Les gabarits d'issues n'apparaissent qu'une fois poussés sur la branche par défaut.
- [ ] Un `README.fr.md` n'est pas détecté automatiquement par GitHub : le lien de bascule
      en tête de chaque fichier est le seul mécanisme, il doit rester en première ligne.
- [ ] Après la bascule, ouvrir le dépôt en navigation privée et vérifier que le rendu du
      README, les badges et le lien de téléchargement de la Release fonctionnent.

---

## 6. Après la mise en public, les endroits où ce type d'outil se fait connaître

Sans forcer, une annonce sobre suffit. Par ordre de rapport signal sur bruit :

- Une issue ou une discussion chez les projets voisins **uniquement si elle apporte
  quelque chose** (par exemple la liste des intégrations communautaires de faster-whisper,
  qui accepte les ajouts).
- `r/selfhosted`, `r/DataHoarder`, `r/LocalLLaMA` : public exactement aligné sur le
  « local, sans cloud ». Poster le lien avec deux phrases et les limites, pas un pitch.
- Hacker News, en `Show HN`, une seule fois, en semaine, le matin heure US.
- Le fait d'être dans **winget** est en soi un canal de découverte, voir la section 7.

---

## 7. Publication sur winget : évaluation, sans engagement

**Ce qu'il faudrait faire.** Winget n'héberge rien. Publier revient à ouvrir une pull
request sur le dépôt `microsoft/winget-pkgs` avec un manifeste YAML de trois ou quatre
fichiers (version, installateur, locale par défaut), rangé dans
`manifests/b/BurN-30/Scribouille/X.Y.Z/`. Le manifeste pointe vers l'URL de téléchargement du
setup et porte son **empreinte SHA256**.

**Prérequis, honnêtement.**

| Point | État côté Scribouille |
|---|---|
| URL de release stable et versionnée | **OK**, la Release GitHub fournit une URL permanente par version |
| Installateur silencieux | **OK**, Inno Setup gère `/VERYSILENT` nativement, c'est un type d'installateur reconnu par winget |
| Signature de code | **pas exigée**, un installateur non signé est accepté |
| Empreinte SHA256 à jour | **contrainte réelle**, elle change à chaque version |
| Identifiant de paquet stable | à choisir une fois, `BurN-30.Scribouille` |
| Licence et URL de licence | **OK**, MIT |
| Politique de validation | le paquet doit s'installer et se désinstaller proprement en mode silencieux, sur une machine neuve |

**La friction.** Elle est à chaque release, pas à la première : nouvelle version, nouveau
manifeste, nouvelle empreinte, nouvelle PR, et une validation automatique qui peut demander
des allers-retours. `wingetcreate` (`winget install Microsoft.WingetCreate`) automatise la
majeure partie : `wingetcreate update BurN-30.Scribouille --version X.Y.Z --urls <url> --submit`
récupère le fichier, calcule l'empreinte, met à jour le manifeste et ouvre la PR. Il existe
aussi une action GitHub qui déclenche cela depuis le workflow de release, ce qui ramènerait
le coût à presque rien une fois réglée.

Deux frottements qui subsistent quoi qu'il arrive : SmartScreen continue d'avertir, winget
n'y change rien puisque le binaire reste non signé ; et une PR refusée ou en attente laisse
un décalage entre la version GitHub et la version winget, qu'il faut surveiller.

**Recommandation.** Faisable, sans certificat, et l'identifiant `BurN-30.Scribouille` mérite
d'être réservé un jour. Mais **attendre deux ou trois releases publiques stables** avant de
s'y mettre : tant que le rythme de version est rapide, chaque publication traîne une PR
externe derrière elle, et un paquet winget en retard d'une version donne une plus mauvaise
impression que pas de paquet du tout. À reprendre quand la version se stabilise, en
branchant `wingetcreate` directement dans le workflow de release.

*Aucun manifeste n'est écrit à ce stade, c'est volontaire.*
