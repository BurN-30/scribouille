; ===========================================================================
;  Scribouille, programme d'installation
;
;  Prend la sortie « onedir » de PyInstaller (dist\Scribouille) et produit un
;  fichier unique Scribouille-Setup-X.Y.Z.exe.
;
;  Partis pris :
;    - installation PAR UTILISATEUR, sans droits administrateur, dans
;      {localappdata}\Programs\Scribouille. C'est ce qui permet de poser
;      l'application sur un poste d'entreprise verrouillé ;
;    - les modèles de transcription, de 1,6 à 3,1 Go, ont leur propre page de
;      choix d'emplacement : on doit pouvoir les envoyer sur un autre disque ;
;    - rien n'est téléchargé pendant l'installation, sauf le runtime WebView2
;      de Microsoft s'il manque, et depuis le site de Microsoft uniquement ;
;    - une réinstallation par-dessus met à jour sans rien perdre : ni la
;      configuration, ni le glossaire, ni les corrections, ni les modèles.
;
;  Compilation :
;      iscc /DVersionApp=2.2.0 packaging\setup.iss
;
;  Le dossier « dist\Scribouille » doit exister au préalable.
; ===========================================================================

#ifndef VersionApp
  #define VersionApp "2.2.0"
#endif

#define NomApp        "Scribouille"
#define Editeur       "BurN-30"
#define UrlProjet     "https://github.com/BurN-30/scribouille"
#define ExeApp        "Scribouille.exe"
#define DossierSource "..\dist\Scribouille"

; Lien officiel et permanent de Microsoft vers le programme d'amorçage WebView2.
; Aucun binaire tiers n'est embarqué : c'est Microsoft qui sert le fichier.
#define UrlWebView2   "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

[Setup]
; Identifiant figé : c'est lui qui fait qu'une nouvelle version se pose
; par-dessus l'ancienne au lieu de créer une deuxième entrée. Il n'a PAS suivi
; le renommage de la 2.4.0, et ne le suivra jamais : le changer donnerait une
; deuxième installation à côté de la première, et deux entrées dans la liste des
; programmes. Inno retient aussi le dossier d'installation par identifiant : un
; poste équipé depuis WhiScribe se met donc à jour dans son dossier d'origine,
; « Programs\WhiScribe », et seules les nouvelles installations vont dans
; « Programs\Scribouille ».
AppId={{4E1B7C86-8F2A-4B5D-9C31-6D0A4F7E2B93}
AppName={#NomApp}
AppVersion={#VersionApp}
AppVerName={#NomApp} {#VersionApp}
VersionInfoVersion={#VersionApp}
VersionInfoProductVersion={#VersionApp}
VersionInfoProductName={#NomApp}
VersionInfoDescription={#NomApp} Setup
VersionInfoCompany={#Editeur}
VersionInfoCopyright=Licence MIT, {#Editeur}
AppPublisher={#Editeur}
AppPublisherURL={#UrlProjet}
AppSupportURL={#UrlProjet}/issues
AppUpdatesURL={#UrlProjet}/releases
AppReadmeFile={app}\README.md

DefaultDirName={localappdata}\Programs\{#NomApp}
DefaultGroupName={#NomApp}
UninstallDisplayName={#NomApp}
UninstallDisplayIcon={app}\{#ExeApp}
LicenseFile=..\LICENSE

; Sans droits administrateur par défaut. Si l'utilisateur désigne malgré tout un
; emplacement système, Windows demandera l'élévation au lieu d'échouer.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Pages laissées visibles : l'utilisateur choisit son dossier et son groupe.
DisableDirPage=no
DisableProgramGroupPage=no
DisableWelcomePage=no
AllowNoIcons=yes

; Une instance ouverte pendant une mise à jour est fermée proprement, puis
; relancée, plutôt que de faire échouer la copie des fichiers.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=yes

Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

OutputDir=sortie
OutputBaseFilename={#NomApp}-Setup-{#VersionApp}
SetupIconFile=scribouille.ico
WizardStyle=modern
WizardSizePercent=110
; Aucune boîte de choix de langue : Inno retient tout seul la langue d'interface
; de Windows quand elle figure dans la liste ci-dessous. L'ANGLAIS EST LISTÉ EN
; PREMIER, il fait donc office de repli hors francophonie, exactement comme
; l'application elle-même (voir app/langues.py).
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[CustomMessages]
english.PageModelesTitre=Location of the transcription models
english.PageModelesDescription=Where should the speech recognition files be stored?
english.PageModelesTexte=The models are large and are downloaded once, the first time you use the application, not during this installation.%n%n    "Fast" preset: about 1.6 GB%n    "Highest quality" preset: about 3.1 GB%n%nIf your system drive is short on space, pick another drive. This location can be changed later, in the application settings, "Models" section.
english.PageModelesLibelle=Store the models in this folder:
english.TacheBureau=Create a &Desktop shortcut
english.LancerApp=Launch {#NomApp}
english.RaccourciCommentaire=Audio transcription, entirely on your own machine
english.WebView2Titre=Microsoft WebView2 component
english.WebView2Description=Downloading the display component from the Microsoft website
english.WebView2Manquant={#NomApp} displays its window through "Microsoft Edge WebView2 Runtime", which is not present on this machine.%n%nIt will be downloaded from the Microsoft website, then installed. Expect a few tens of megabytes.%n%nDo you want to continue?
english.WebView2Echec=The WebView2 component could not be installed automatically.%n%nThe installation of {#NomApp} will carry on, but the window will not open until that component is present. You can install it from:%n%n{#UrlWebView2}
english.EspaceInsuffisant=Only about %1 GB is free on this drive.%n%nThe highest quality model needs 3.1 GB on its own. Do you want to keep this location anyway?
english.DossierModelesRefuse=This folder could not be created, or is not writable.%n%nPlease choose another location.
english.DesinstallerModeles=Also delete the transcription models?%n%nThey take up %1 in:%n%2%n%nAnswer No to keep them: a reinstall will find them again and will have nothing to download.
english.DesinstallerDonnees=Also delete your personal {#NomApp} data?%n%nThis would permanently erase your glossary, your correction rules, your settings, the logs and the speaker separation components (%2), in:%n%1%n%nAnswer No to keep them.
english.EffacementComplet=Erase every file {#NomApp} wrote on this computer?%n%n%1%nYour transcriptions are NOT touched. Files that do not belong to {#NomApp} are left in place.%n%nAnswer No to keep everything: a reinstall will find your settings and models again.

french.PageModelesTitre=Emplacement des modèles de transcription
french.PageModelesDescription=Où faut-il ranger les fichiers de reconnaissance vocale ?
french.PageModelesTexte=Les modèles sont volumineux et se téléchargent une seule fois, au premier usage de l'application, pas pendant cette installation.%n%n    Preset « Rapide » : environ 1,6 Go%n    Preset « Qualité maximale » : environ 3,1 Go%n%nSi votre disque système est à l'étroit, choisissez un autre disque. Cet emplacement reste modifiable plus tard, dans les réglages de l'application, section « Modèles ».
french.PageModelesLibelle=Ranger les modèles dans ce dossier :
french.TacheBureau=Créer une icône sur le &Bureau
french.LancerApp=Lancer {#NomApp}
french.RaccourciCommentaire=Transcription audio, entièrement sur votre machine
french.WebView2Titre=Composant Microsoft WebView2
french.WebView2Description=Téléchargement du composant d'affichage depuis le site de Microsoft
french.WebView2Manquant=L'affichage de {#NomApp} s'appuie sur « Microsoft Edge WebView2 Runtime », qui n'est pas présent sur ce poste.%n%nIl va être téléchargé depuis le site de Microsoft, puis installé. Comptez quelques dizaines de mégaoctets.%n%nVoulez-vous continuer ?
french.WebView2Echec=Le composant WebView2 n'a pas pu être installé automatiquement.%n%nL'installation de {#NomApp} va se poursuivre, mais la fenêtre ne s'ouvrira pas tant que ce composant manquera. Vous pourrez le poser depuis :%n%n{#UrlWebView2}
french.EspaceInsuffisant=Il ne reste qu'environ %1 Go de libre sur ce disque.%n%nLe modèle de qualité maximale en demande 3,1 à lui seul. Voulez-vous quand même garder cet emplacement ?
french.DossierModelesRefuse=Ce dossier n'a pas pu être créé, ou n'est pas accessible en écriture.%n%nChoisissez un autre emplacement.
french.DesinstallerModeles=Supprimer aussi les modèles de transcription ?%n%nIls occupent %1 dans :%n%2%n%nRépondez Non pour les conserver : une réinstallation les retrouvera et n'aura rien à retélécharger.
french.DesinstallerDonnees=Supprimer aussi vos données personnelles de {#NomApp} ?%n%nCela effacerait définitivement votre glossaire, vos règles de correction, vos réglages, les journaux et les composants de séparation des locuteurs (%2), dans :%n%1%n%nRépondez Non pour les conserver.
french.EffacementComplet=Effacer tous les fichiers que {#NomApp} a écrits sur ce poste ?%n%n%1%nVos transcriptions ne sont PAS touchées. Les fichiers qui ne sont pas à {#NomApp} restent en place.%n%nRépondez Non pour tout garder : une réinstallation retrouvera vos réglages et vos modèles.

[Tasks]
; Décochée par défaut : on ne pose pas d'icône sur le bureau sans le demander.
Name: "desktopicon"; Description: "{cm:TacheBureau}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DossierSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#NomApp}"; Filename: "{app}\{#ExeApp}"; WorkingDir: "{app}"; Comment: "{cm:RaccourciCommentaire}"
Name: "{group}\{cm:UninstallProgram,{#NomApp}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#NomApp}"; Filename: "{app}\{#ExeApp}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#ExeApp}"; Description: "{cm:LancerApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Fichier écrit après l'installation, donc inconnu de la liste [Files].
Type: files; Name: "{app}\emplacement-modeles.txt"
Type: dirifempty; Name: "{app}"

[Code]
var
  PageModeles: TInputDirWizardPage;
  PageTelechargement: TDownloadWizardPage;
  { Vrai quand la question de l'effacement complet a été posée par la ligne
    de commande de l'application (désinstallation). }
  EffacementTraite: Boolean;

{ --------------------------------------------------------------------------
  Emplacements partagés avec l'application, voir app/chemins.py
  -------------------------------------------------------------------------- }

{ Le dossier de données est à notre nom depuis la 2.5, comme dans
  app/chemins.py. L'ancien, « WhiScribe », est repris par l'application à son
  premier lancement (app/migration.py) : un projet tiers homonyme range ses
  modèles dans le même dossier sous Windows, rien de lui n'est jamais touché. }
function DossierDonnees(): String;
begin
  Result := ExpandConstant('{localappdata}') + '\Scribouille';
end;

function AncienDossierDonnees(): String;
begin
  Result := ExpandConstant('{localappdata}') + '\WhiScribe';
end;

{ Un chemin noté dans l'ancien dossier est lu comme il sera après la reprise :
  « ...\WhiScribe\modeles » devient « ...\Scribouille\modeles ». }
function VersNouveauDossier(Chemin: String): String;
begin
  Result := Chemin;
  if Pos(Lowercase(AncienDossierDonnees() + '\'), Lowercase(Chemin + '\')) = 1 then
    Result := DossierDonnees() + Copy(Chemin, Length(AncienDossierDonnees()) + 1, Length(Chemin));
end;

function FichierChoixModeles(): String;
begin
  Result := DossierDonnees() + '\dossier-modeles.txt';
end;

function DossierModelesDefaut(): String;
begin
  Result := DossierDonnees() + '\modeles';
end;

{ Séparation des locuteurs installée depuis l'application (app/extensions.py).
  Elle pèse environ 2,5 Go et vit dans les données de l'utilisateur : elle entre
  donc dans le périmètre de la question « supprimer vos données », et son poids
  doit être annoncé, sans quoi la question porterait sur quelques kilooctets de
  glossaire alors qu'elle efface plusieurs gigaoctets. }
function DossierExtensions(): String;
begin
  Result := DossierDonnees() + '\extensions';
end;

function DossierCachePip(): String;
begin
  Result := DossierDonnees() + '\cache-pip';
end;

{ Emplacement effectif au moment où l'on parle : celui que l'application utilise
  réellement, éventuellement changé depuis l'installation précédente. }
function DossierModelesEffectif(): String;
var
  Lignes: TArrayOfString;
  Valeur, Fichier: String;
begin
  Result := DossierModelesDefaut();
  { Mise à jour depuis une 2.4 : le choix est encore dans l'ancien dossier. }
  Fichier := FichierChoixModeles();
  if not FileExists(Fichier) then
    Fichier := AncienDossierDonnees() + '\dossier-modeles.txt';
  if FileExists(Fichier) then
  begin
    if LoadStringsFromFile(Fichier, Lignes) and (GetArrayLength(Lignes) > 0) then
    begin
      Valeur := Trim(Lignes[0]);
      if Valeur <> '' then
        Result := VersNouveauDossier(Valeur);
    end;
  end;
end;

{ --------------------------------------------------------------------------
  Utilitaires
  -------------------------------------------------------------------------- }

{ Taille occupée par un dossier, récursivement. Sert à annoncer à la
  désinstallation ce que la suppression des modèles libérerait réellement. }
function TailleDossier(Dossier: String): Int64;
var
  Recherche: TFindRec;
begin
  Result := 0;
  if not DirExists(Dossier) then
    Exit;
  if FindFirst(Dossier + '\*', Recherche) then
  begin
    try
      repeat
        if (Recherche.Name <> '.') and (Recherche.Name <> '..') then
        begin
          if (Recherche.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := Result + TailleDossier(Dossier + '\' + Recherche.Name)
          else
            { Pas de décalage binaire : la multiplication est acceptée partout. }
            Result := Result + Int64(Recherche.SizeHigh) * 4294967296 + Int64(Recherche.SizeLow);
        end;
      until not FindNext(Recherche);
    finally
      FindClose(Recherche);
    end;
  end;
end;

function TailleLisible(Octets: Int64): String;
begin
  if Octets >= 1073741824 then
    Result := Format('%.1f Go', [Octets / 1073741824.0])
  else if Octets >= 1048576 then
    Result := Format('%.0f Mo', [Octets / 1048576.0])
  else
    { Toujours un flottant : Format n'accepte pas un Int64 sur « %d ». }
    Result := Format('%.0f Ko', [Octets / 1024.0]);
  StringChangeEx(Result, '.', ',', True);
end;

function EspaceLibreGo(Chemin: String): Extended;
var
  Racine: String;
  Libre, Total: Int64;
begin
  Result := 0;
  Racine := ExtractFileDrive(Chemin);
  if Racine = '' then
    Exit;
  if GetSpaceOnDisk64(Racine + '\', Libre, Total) then
    Result := Libre / 1073741824.0;
end;

{ Le runtime WebView2 s'annonce dans la base de registre, par machine ou par
  utilisateur. Une clé « pv » non vide et différente de 0.0.0.0 vaut présence. }
function VersionWebView2(Racine: Integer; Cle: String): String;
begin
  if not RegQueryStringValue(Racine, Cle, 'pv', Result) then
    Result := '';
end;

function WebView2Present(): Boolean;
{ PascalScript refuse un bloc const local a une fonction : variables assignees en tete. }
var
  CleClient, CleClient32: String;
  Version: String;
begin
  CleClient := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  CleClient32 := 'Software\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Version := VersionWebView2(HKEY_LOCAL_MACHINE, CleClient32);
  if Version = '' then
    Version := VersionWebView2(HKEY_LOCAL_MACHINE, CleClient);
  if Version = '' then
    Version := VersionWebView2(HKEY_CURRENT_USER, CleClient);
  Result := (Version <> '') and (Version <> '0.0.0.0');
end;

{ --------------------------------------------------------------------------
  Assistant
  -------------------------------------------------------------------------- }

function SurProgressionTelechargement(NomFichier, UrlFichier: String; Recus, Total: Int64): Boolean;
begin
  if Total > 0 then
    PageTelechargement.SetProgress(Recus, Total);
  Result := True;
end;

procedure InitializeWizard();
begin
  PageModeles := CreateInputDirPage(
    wpSelectDir,
    ExpandConstant('{cm:PageModelesTitre}'),
    ExpandConstant('{cm:PageModelesDescription}'),
    ExpandConstant('{cm:PageModelesTexte}'),
    False, '');
  PageModeles.Add(ExpandConstant('{cm:PageModelesLibelle}'));
  { Pré-rempli avec l'emplacement réellement utilisé : une mise à jour ne
    déplace rien tant que l'utilisateur ne touche pas au champ. }
  PageModeles.Values[0] := DossierModelesEffectif();

  PageTelechargement := CreateDownloadPage(
    ExpandConstant('{cm:WebView2Titre}'),
    ExpandConstant('{cm:WebView2Description}'),
    @SurProgressionTelechargement);
end;

function InstallerWebView2(): Boolean;
var
  Code: Integer;
begin
  Result := False;
  PageTelechargement.Clear;
  PageTelechargement.Add('{#UrlWebView2}', 'MicrosoftEdgeWebview2Setup.exe', '');
  PageTelechargement.Show;
  try
    try
      PageTelechargement.Download;
      { Installation par utilisateur, sans interface : cohérent avec le reste. }
      Result := Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'),
                     '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code)
                and (Code = 0);
    except
      Result := False;
    end;
  finally
    PageTelechargement.Hide;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Cible: String;
  Libre: Extended;
  Texte: String;
begin
  Result := True;

  if CurPageID = PageModeles.ID then
  begin
    Cible := Trim(PageModeles.Values[0]);
    if Cible = '' then
    begin
      PageModeles.Values[0] := DossierModelesDefaut();
      Cible := PageModeles.Values[0];
    end;
    if not ForceDirectories(Cible) then
    begin
      MsgBox(ExpandConstant('{cm:DossierModelesRefuse}'), mbError, MB_OK);
      Result := False;
      Exit;
    end;
    Libre := EspaceLibreGo(Cible);
    if (Libre > 0) and (Libre < 4.0) then
    begin
      Texte := Format('%.1f', [Libre]);
      StringChangeEx(Texte, '.', ',', True);
      Result := MsgBox(FmtMessage(ExpandConstant('{cm:EspaceInsuffisant}'), [Texte]),
                       mbConfirmation, MB_YESNO) = IDYES;
    end;
    Exit;
  end;

  if CurPageID = wpReady then
  begin
    if not WebView2Present() then
    begin
      if MsgBox(ExpandConstant('{cm:WebView2Manquant}'), mbConfirmation, MB_YESNO) = IDYES then
      begin
        if not InstallerWebView2() then
          MsgBox(ExpandConstant('{cm:WebView2Echec}'), mbInformation, MB_OK);
      end
      else
        MsgBox(ExpandConstant('{cm:WebView2Echec}'), mbInformation, MB_OK);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Cible: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  Cible := Trim(PageModeles.Values[0]);
  if Cible = '' then
    Cible := DossierModelesDefaut();
  ForceDirectories(Cible);
  ForceDirectories(DossierDonnees());

  { Deux traces du même choix, lues dans cet ordre par l'application :
    celle de l'espace utilisateur fait foi, celle du dossier de programme sert
    de secours si les données utilisateur sont effacées. }
  SaveStringToFile(FichierChoixModeles(), Cible + #13#10, False);
  SaveStringToFile(ExpandConstant('{app}\emplacement-modeles.txt'), Cible + #13#10, False);
end;

{ --------------------------------------------------------------------------
  Désinstallation : deux questions distinctes, aucune suppression silencieuse
  -------------------------------------------------------------------------- }

{ Efface les données personnelles de Scribouille, ENTRÉE PAR ENTRÉE : jamais
  un dossier entier à l'aveugle. Le dossier « WhiScribe » d'avant la 2.5 est
  partagé avec un projet tiers homonyme (ses modèles, « models ») : un
  DelTree du dossier les effaçait. Même liste que app/migration.py. Les modèles
  (« modeles ») ne partent que si l'utilisateur l'a demandé juste avant. }
procedure SupprimerEntrees(Base: String; PreserverModeles: Boolean);
begin
  if not DirExists(Base) then
    Exit;
  DeleteFile(Base + '\config.json');
  DeleteFile(Base + '\jeton_hf.txt');
  DeleteFile(Base + '\dossier-modeles.txt');
  DeleteFile(Base + '\vocabulaire.txt');
  DeleteFile(Base + '\corrections.txt');
  DeleteFile(Base + '\gabarit-ia.txt');
  DeleteFile(Base + '\calibration.json');
  DeleteFile(Base + '\maj-etat.json');
  DeleteFile(Base + '\surveillance-vus.json');
  DeleteFile(Base + '\vocabulaire.toml');
  DeleteFile(Base + '\materiel.json');
  DeleteFile(Base + '\openvino-chargement-en-cours.txt');
  DeleteFile(Base + '\migration-whiscribe.json');
  DelTree(Base + '\*-format1-sauvegarde.txt', False, True, False);
  DelTree(Base + '\vocabulaire-propositions-*', False, True, False);
  { Sauvegardes automatiques posées avant chaque import de données, sous le
    nom actuel et sous l'ancien (avant la 2.4.0). }
  DelTree(Base + '\scribouille-donnees-avant-import-*.zip', False, True, False);
  DelTree(Base + '\whiscribe-donnees-avant-import-*.zip', False, True, False);
  DelTree(Base + '\logs', True, True, True);
  DelTree(Base + '\reprises', True, True, True);
  { Séparation des locuteurs, moteur Intel et leurs caches : annoncés dans la
    question posée juste avant. }
  DelTree(Base + '\extensions', True, True, True);
  DelTree(Base + '\cache-pip', True, True, True);
  DelTree(Base + '\extensions-openvino', True, True, True);
  DelTree(Base + '\cache-openvino', True, True, True);
  DelTree(Base + '\paquets-hors-ligne', True, True, True);
  DelTree(Base + '\rapports-banc', True, True, True);
  DelTree(Base + '\comparaisons', True, True, True);
  DelTree(Base + '\campagnes', True, True, True);
  DelTree(Base + '\corpus-campagne', True, True, True);
  DelTree(Base + '\ancien-whiscribe', True, True, True);
  if not PreserverModeles then
    DelTree(Base + '\modeles', True, True, True);
  { Ne part que s'il est vide : ce qui n'est pas à nous y reste. }
  RemoveDir(Base);
end;

procedure SupprimerDonnees(PreserverModeles: Boolean);
begin
  SupprimerEntrees(DossierDonnees(), PreserverModeles);
  SupprimerEntrees(AncienDossierDonnees(), PreserverModeles);
end;

{ Effacement complet par la ligne de commande de l'application, AVANT que le
  programme ne soit retiré : elle seule tient l'inventaire de ce qu'elle a
  écrit (app/inventaire.py), modèles, caches, moteur Intel, journaux et ancien
  dossier compris, et elle ne touche ni aux transcriptions ni à ce qui n'est
  pas à elle. La liste et les tailles sont montrées avant. Renvoie True si la
  question a pu être posée (réponse Oui ou Non) ; False si la ligne de
  commande ne répond pas : l'ancien parcours en deux questions prend le relais. }
function EffacementParLigneDeCommande(): Boolean;
var
  Console, Resume, Liste: String;
  Lignes: TArrayOfString;
  I, Code: Integer;
begin
  Result := False;
  Console := ExpandConstant('{app}\scribouille.com');
  if not FileExists(Console) then
    Exit;
  Resume := AddBackslash(GetTempDir()) + 'scribouille-effacement.txt';
  DeleteFile(Resume);
  if not Exec(Console, 'effacer --complet --garder-programme --apercu --resume "' + Resume + '"',
              ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
    Exit;
  if (Code <> 0) or not LoadStringsFromFile(Resume, Lignes) then
    Exit;
  DeleteFile(Resume);
  Liste := '';
  for I := 0 to GetArrayLength(Lignes) - 1 do
    Liste := Liste + '    ' + Lignes[I] + #13#10;
  Result := True;
  if MsgBox(FmtMessage(ExpandConstant('{cm:EffacementComplet}'), [Liste]),
            mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    Exec(Console, 'effacer --complet --garder-programme --oui', ExpandConstant('{app}'),
         SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DossierModeles: String;
  Occupe: Int64;
  ModelesGardes: Boolean;
  ModelesDansLesDonnees: Boolean;
  PoidsExtensions: Int64;
begin
  { Une désinstallation silencieuse ne pose aucune question et ne détruit rien
    d'autre que le programme : c'est le comportement le moins surprenant. C'est
    aussi elle que lance l'effacement complet demandé depuis l'application. }
  if UninstallSilent then
    Exit;
  if CurUninstallStep = usUninstall then
  begin
    EffacementTraite := EffacementParLigneDeCommande();
    Exit;
  end;
  if CurUninstallStep <> usPostUninstall then
    Exit;
  if EffacementTraite then
    Exit;

  DossierModeles := DossierModelesEffectif();
  { Mise à jour jamais lancée : les modèles sont encore dans l'ancien dossier. }
  if (not DirExists(DossierModeles)) and DirExists(AncienDossierDonnees() + '\modeles')
     and (Lowercase(DossierModeles) = Lowercase(DossierModelesDefaut())) then
    DossierModeles := AncienDossierDonnees() + '\modeles';
  ModelesDansLesDonnees := (Pos(Lowercase(DossierDonnees()), Lowercase(DossierModeles)) = 1)
    or (Pos(Lowercase(AncienDossierDonnees()), Lowercase(DossierModeles)) = 1);
  ModelesGardes := True;

  Occupe := TailleDossier(DossierModeles);
  if Occupe > 0 then
  begin
    { Le crochet ne doit jamais ouvrir la ligne : Inno Setup y verrait un début de section, même dans [Code]. }
    if MsgBox(FmtMessage(ExpandConstant('{cm:DesinstallerModeles}'), [
                TailleLisible(Occupe), DossierModeles]),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(DossierModeles, True, True, True);
      ModelesGardes := False;
    end;
  end
  else
    ModelesGardes := False;

  if DirExists(DossierDonnees()) or DirExists(AncienDossierDonnees()) then
  begin
    PoidsExtensions := TailleDossier(DossierExtensions()) + TailleDossier(DossierCachePip())
      + TailleDossier(DossierDonnees() + '\extensions-openvino') + TailleDossier(DossierDonnees() + '\cache-openvino');
    if MsgBox(FmtMessage(ExpandConstant('{cm:DesinstallerDonnees}'), [
                DossierDonnees(), TailleLisible(PoidsExtensions)]),
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      SupprimerDonnees(ModelesGardes and ModelesDansLesDonnees);
  end;
end;
