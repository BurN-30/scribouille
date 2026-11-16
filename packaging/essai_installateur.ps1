<#
.SYNOPSIS
  Essai réel du programme d'installation de Scribouille, sur un poste jetable.

.DESCRIPTION
  Installe, met à jour, lance et désinstalle pour de vrai. Écrit dans
  %LOCALAPPDATA%, dans le registre de l'utilisateur et de la machine, dans le
  menu Démarrer et sur le Bureau. Fait pour l'exécuteur Windows de GitHub
  (.github/workflows/essai-installateur.yml) : refuse de tourner ailleurs.

  Scénarios :
    neuve         installation neuve, vérification, vraie transcription courte
                  (modèle tiny, 75 Mo), désinstallation silencieuse, puis deux
                  désinstallations avec effacement demandé (par la ligne de
                  commande de l'application, puis par le repli du désinstalleur)
    depuis-2.3.3  WhiScribe 2.3.3 installée, données témoins, 3.0 par-dessus,
                  premier lancement, désinstallation
    depuis-2.4.0  même chose depuis Scribouille 2.4.0
    cohabitation  WhiScribe 2.3.3 installée pour tous les utilisateurs dans un
                  autre dossier, 3.0 installée pour l'utilisateur : rien de la
                  2.x ne doit changer, désinstallations comprises

  Chaque contrôle est écrit « OK » ou « ÉCHEC » ; un seul échec fait sortir
  avec le code 1. Inventaires (fichiers, registre, raccourcis) et journaux
  d'Inno Setup dans le dossier -Rapport.
#>
param(
    [Parameter(Mandatory)][ValidateSet('neuve', 'depuis-2.3.3', 'depuis-2.4.0', 'cohabitation')][string]$Scenario,
    [Parameter(Mandatory)][string]$Installateur,
    [Parameter(Mandatory)][string]$Portable,
    [string]$Rapport = (Join-Path (Get-Location) "essai-$Scenario"),
    [string]$Depot = 'BurN-30/scribouille'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 1

if ($env:GITHUB_ACTIONS -ne 'true') {
    throw "Cet essai installe et désinstalle pour de vrai : il ne tourne que sur un exécuteur GitHub."
}

$Installateur = (Resolve-Path $Installateur).Path
$Portable = (Resolve-Path $Portable).Path
New-Item -ItemType Directory -Force $Rapport | Out-Null
$Rapport = (Resolve-Path $Rapport).Path
$Racine = Split-Path -Parent $PSScriptRoot

$AppId = '{4E1B7C86-8F2A-4B5D-9C31-6D0A4F7E2B93}'
$CleDesinst = "Software\Microsoft\Windows\CurrentVersion\Uninstall\${AppId}_is1"
$Local = [Environment]::GetFolderPath('LocalApplicationData')
$Donnees = Join-Path $Local 'Scribouille'
$Ancien = Join-Path $Local 'WhiScribe'
$Travail = Join-Path $env:RUNNER_TEMP "essai-$Scenario"
New-Item -ItemType Directory -Force $Travail | Out-Null
$Version = ([regex]'Scribouille-Setup-(.+)\.exe$').Match((Split-Path -Leaf $Installateur)).Groups[1].Value

# ---------------------------------------------------------------------------
# Contrôles
# ---------------------------------------------------------------------------

$script:Echecs = [System.Collections.Generic.List[string]]::new()
$script:Bilan = [System.Collections.Generic.List[string]]::new()

function Etape([string]$Titre) {
    Write-Host ''
    Write-Host "=== $Titre ==="
    $script:Bilan.Add('')
    $script:Bilan.Add("== $Titre")
}

function Controle([string]$Nom, [bool]$Ok, [string]$Detail = '') {
    $etat = if ($Ok) { 'OK   ' } else { 'ÉCHEC' }
    $ligne = "$etat  $Nom" + $(if ($Detail) { " : $Detail" } else { '' })
    Write-Host $ligne
    $script:Bilan.Add($ligne)
    if (-not $Ok) {
        $script:Echecs.Add($Nom)
        Write-Host "::error::[$Scenario] $Nom$(if ($Detail) { " : $Detail" })"
    }
}

function Note([string]$Texte) {
    Write-Host "       $Texte"
    $script:Bilan.Add("       $Texte")
}

# ---------------------------------------------------------------------------
# Fenêtres de dialogue du désinstalleur : lues, puis répondues
# ---------------------------------------------------------------------------

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class Dialogues {
    delegate bool Rappel(IntPtr h, IntPtr l);
    [DllImport("user32.dll")] static extern bool EnumWindows(Rappel r, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetDlgItem(IntPtr h, int id);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, StringBuilder l);
    [DllImport("user32.dll")] static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);

    static string Texte(IntPtr h) {
        if (h == IntPtr.Zero) return "";
        var s = new StringBuilder(8192);
        SendMessage(h, 0x000D, (IntPtr)s.Capacity, s);   // WM_GETTEXT
        return s.ToString();
    }

    // Boîtes de message visibles des processus donnés : répond (Oui, sinon OK)
    // et rend le texte de chacune.
    public static List<string> Repondre(HashSet<uint> processus, bool oui) {
        var vues = new List<string>();
        var fenetres = new List<IntPtr>();
        EnumWindows((h, l) => {
            var c = new StringBuilder(64);
            GetClassName(h, c, c.Capacity);
            uint pid;
            GetWindowThreadProcessId(h, out pid);
            if (c.ToString() == "#32770" && IsWindowVisible(h) && processus.Contains(pid)) fenetres.Add(h);
            return true;
        }, IntPtr.Zero);
        foreach (var h in fenetres) {
            string texte = Texte(GetDlgItem(h, 0xFFFF));
            int[] ordre = oui ? new[] { 6, 1, 2 } : new[] { 7, 1, 2 };   // IDYES/IDNO, IDOK, IDCANCEL
            foreach (int id in ordre) {
                IntPtr bouton = GetDlgItem(h, id);
                if (bouton != IntPtr.Zero) {
                    PostMessage(h, 0x0111, (IntPtr)id, bouton);   // WM_COMMAND, BN_CLICKED
                    vues.Add("[" + Texte(h) + "] " + texte.Replace("\r", "").Replace("\n", " | ") + "  -> bouton " + id);
                    break;
                }
            }
        }
        return vues;
    }
}
'@

# ---------------------------------------------------------------------------
# Lecture de l'état du poste
# ---------------------------------------------------------------------------

function Vues {
    @(
        @{ Nom = 'HKCU'; Ruche = [Microsoft.Win32.RegistryHive]::CurrentUser; Vue = [Microsoft.Win32.RegistryView]::Default },
        @{ Nom = 'HKLM64'; Ruche = [Microsoft.Win32.RegistryHive]::LocalMachine; Vue = [Microsoft.Win32.RegistryView]::Registry64 },
        @{ Nom = 'HKLM32'; Ruche = [Microsoft.Win32.RegistryHive]::LocalMachine; Vue = [Microsoft.Win32.RegistryView]::Registry32 }
    )
}

# Clés de désinstallation de notre identifiant.
function Cles {
    $res = @()
    foreach ($v in Vues) {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($v.Ruche, $v.Vue)
        $k = $base.OpenSubKey($CleDesinst)
        if ($k) {
            $res += [pscustomobject]@{
                Ruche = $v.Nom; Version = [string]$k.GetValue('DisplayVersion'); Nom = [string]$k.GetValue('DisplayName')
                Dossier = [string]$k.GetValue('InstallLocation'); Desinstalleur = [string]$k.GetValue('UninstallString')
            }
            $k.Close()
        }
        $base.Close()
    }
    , $res
}

# Toutes les entrées de « Programmes installés » qui parlent de nous, quel que
# soit leur identifiant : une deuxième entrée serait un défaut.
function Entrees {
    $res = @()
    foreach ($v in Vues) {
        $base = [Microsoft.Win32.RegistryKey]::OpenBaseKey($v.Ruche, $v.Vue)
        $k = $base.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Uninstall')
        if ($k) {
            foreach ($nom in $k.GetSubKeyNames()) {
                $s = $k.OpenSubKey($nom)
                $affiche = [string]$s.GetValue('DisplayName')
                if ($affiche -match 'scribouille|whiscribe') {
                    $res += [pscustomobject]@{ Ruche = $v.Nom; Cle = $nom; Nom = $affiche; Version = [string]$s.GetValue('DisplayVersion') }
                }
                $s.Close()
            }
            $k.Close()
        }
        $base.Close()
    }
    , $res
}

# Autres clés à notre nom (l'application n'en écrit pas : on le vérifie).
function ClesLogiciel {
    $res = @()
    foreach ($chemin in 'HKCU:\Software', 'HKLM:\SOFTWARE', 'HKLM:\SOFTWARE\WOW6432Node') {
        Get-ChildItem $chemin -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match 'scribouille|whiscribe|burn-30' } |
            ForEach-Object { $res += $_.Name }
    }
    , $res
}

function Raccourcis {
    $shell = New-Object -ComObject WScript.Shell
    $res = @()
    foreach ($d in [Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('CommonPrograms'),
                   [Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('CommonDesktopDirectory')) {
        if (-not $d -or -not (Test-Path $d)) { continue }
        Get-ChildItem $d -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
            $cible = $shell.CreateShortcut($_.FullName).TargetPath
            if ($_.FullName -match 'scribouille|whiscribe' -or $cible -match 'scribouille|whiscribe') {
                $res += [pscustomobject]@{ Chemin = $_.FullName; Cible = $cible }
            }
        }
    }
    , $res
}

# Empreintes de tout ce qui est sous un dossier, en chemins relatifs.
function Empreintes([string]$Dossier) {
    $h = [ordered]@{}
    if (Test-Path $Dossier) {
        Get-ChildItem $Dossier -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
            $h[$_.FullName.Substring($Dossier.Length + 1)] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    }
    $h
}

function Inventaire([string]$Etiquette) {
    $etat = [ordered]@{
        etiquette  = $Etiquette
        cles       = Cles
        entrees    = Entrees
        logiciel   = ClesLogiciel
        raccourcis = Raccourcis
        donnees    = @(if (Test-Path $Donnees) { Get-ChildItem $Donnees -Recurse -Force | ForEach-Object { $_.FullName.Substring($Donnees.Length + 1) + $(if ($_.PSIsContainer) { '\' } else { " ($($_.Length))" }) } })
        whiscribe  = @(if (Test-Path $Ancien) { Get-ChildItem $Ancien -Recurse -Force | ForEach-Object { $_.FullName.Substring($Ancien.Length + 1) + $(if ($_.PSIsContainer) { '\' } else { " ($($_.Length))" }) } })
        programmes = @(foreach ($d in (Join-Path $Local 'Programs\Scribouille'), (Join-Path $Local 'Programs\WhiScribe'), 'C:\Program Files\WhiScribe') {
                if (Test-Path $d) { "$d : $((Get-ChildItem $d -Recurse -File -Force | Measure-Object).Count) fichiers" } })
    }
    $etat | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 (Join-Path $Rapport "inventaire-$Etiquette.json")
    $etat
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

function Attendre([System.Diagnostics.Process]$P, [int]$Secondes, [string]$Nom) {
    $null = $P.Handle
    if (-not $P.WaitForExit($Secondes * 1000)) {
        Stop-Process -Id $P.Id -Force -ErrorAction SilentlyContinue
        throw "$Nom : pas fini en $Secondes s, arrêté."
    }
    $P.ExitCode
}

function Installer([string]$Exe, [string]$Nom, [string[]]$Options = @()) {
    $journal = Join-Path $Rapport "inno-$Nom.log"
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', "/LOG=`"$journal`"") + $Options
    Write-Host "Installation : $(Split-Path -Leaf $Exe) $($arguments -join ' ')"
    $code = Attendre (Start-Process -FilePath $Exe -ArgumentList $arguments -PassThru) 900 "Installation $Nom"
    Controle "installation $Nom : code de retour 0" ($code -eq 0) "code $code"
}

function ProcessusDesinstalleur {
    # unins000.exe se recopie dans le dossier temporaire (« _iu14D2N.tmp ») et
    # c'est la copie qui désinstalle.
    @(Get-Process | Where-Object { $_.ProcessName -like '_iu*' -or $_.ProcessName -like '_un*' -or
                                   $_.ProcessName -like 'unins*' -or $_.ProcessName -like '*.tmp' })
}

# Désinstalleur Inno : il se recopie dans le dossier temporaire et la copie
# fait le travail ; on attend la copie. Interactif : chaque boîte de message
# est lue et reçoit « Oui » (ou OK).
function Desinstaller([string]$Nom, [switch]$Interactif) {
    $cle = (Cles) | Where-Object { $_.Version -eq $Version } | Select-Object -First 1
    if (-not $cle) { throw "Aucune clé de désinstallation de la $Version." }
    $exe = ($cle.Desinstalleur -replace '^"([^"]+)".*$', '$1')
    $journal = Join-Path $Rapport "inno-desinstallation-$Nom.log"
    $arguments = if ($Interactif) { @("/LOG=`"$journal`"") } else { @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$journal`"") }
    Write-Host "Désinstallation : $exe $($arguments -join ' ')"
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -PassThru
    $dialogues = [System.Collections.Generic.List[string]]::new()
    $limite = (Get-Date).AddMinutes(10)
    Start-Sleep -Milliseconds 500
    while ((Get-Date) -lt $limite) {
        $ids = [System.Collections.Generic.HashSet[uint32]]::new()
        foreach ($x in ProcessusDesinstalleur) { [void]$ids.Add([uint32]$x.Id) }
        if ($Interactif -and $ids.Count) {
            foreach ($d in [Dialogues]::Repondre($ids, $true)) { $dialogues.Add($d); Write-Host "  boîte : $d" }
        }
        if ($p.HasExited -and $ids.Count -eq 0) { break }
        Start-Sleep -Milliseconds 400
    }
    if ((ProcessusDesinstalleur).Count) {
        ProcessusDesinstalleur | Stop-Process -Force -ErrorAction SilentlyContinue
        throw "Désinstallation $Nom : pas finie en 10 min."
    }
    $dialogues | Out-File -Encoding utf8 (Join-Path $Rapport "dialogues-$Nom.txt")
    Controle "désinstallation $Nom : terminée" $true "$($dialogues.Count) boîte(s) de message"
    , $dialogues.ToArray()
}

# Ligne de commande de l'application installée. Sortie lue en UTF-8 dans un
# fichier, code de retour rendu ; --json rend l'objet.
function Commande([string]$Programme, [string[]]$Arguments, [int]$Secondes = 600) {
    $n = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $sortie = Join-Path $Travail "cli-$n.out"
    $erreurs = Join-Path $Travail "cli-$n.err"
    # Start-Process ne met pas de guillemets autour d'un argument qui a des espaces.
    $liste = @($Arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } })
    $p = Start-Process -FilePath (Join-Path $Programme 'scribouille.com') -ArgumentList $liste -PassThru -NoNewWindow `
        -RedirectStandardOutput $sortie -RedirectStandardError $erreurs -WorkingDirectory $Travail
    $null = $p.Handle   # sans quoi ExitCode peut rester vide
    $code = Attendre $p $Secondes "scribouille $($Arguments -join ' ')"
    $texte = Get-Content $sortie -Raw -Encoding utf8
    $err = Get-Content $erreurs -Raw -Encoding utf8
    Add-Content -Encoding utf8 (Join-Path $Rapport 'ligne-de-commande.txt') "`n> scribouille $($Arguments -join ' ')`n(code $code)`n$texte`n$err"
    $json = $null
    if ($Arguments -contains '--json' -and $texte) {
        $derniere = ($texte.Trim() -split "`n")[-1]
        try { $json = $derniere | ConvertFrom-Json } catch { $json = $null }
    }
    [pscustomobject]@{ Code = $code; Texte = $texte; Erreurs = $err; Json = $json }
}

function Telecharger([string]$Tag, [string]$Fichier) {
    $cible = Join-Path $Travail $Fichier
    if (-not (Test-Path $cible)) {
        $url = "https://github.com/$Depot/releases/download/$Tag/$Fichier"
        Write-Host "Téléchargement : $url"
        Invoke-WebRequest -Uri $url -OutFile $cible -UseBasicParsing
    }
    Note "$Fichier : $((Get-Item $cible).Length) octets, SHA-256 $((Get-FileHash $cible -Algorithm SHA256).Hash)"
    $cible
}

# Ce que le programme installé doit contenir : exactement le paquet portable,
# plus le désinstalleur et la note de l'emplacement des modèles. Un fichier de
# plus est un reste d'une version antérieure.
function ControleProgramme([string]$Dossier, [string]$Nom) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $attendus = @{}
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Portable)
    try {
        foreach ($e in $zip.Entries) {
            if ($e.FullName.EndsWith('/')) { continue }
            $attendus[($e.FullName -replace '^Scribouille/', '' -replace '/', '\').ToLowerInvariant()] = $e.Length
        }
    } finally { $zip.Dispose() }
    $presents = @{}
    Get-ChildItem $Dossier -Recurse -File -Force | ForEach-Object { $presents[$_.FullName.Substring($Dossier.Length + 1).ToLowerInvariant()] = $_.Length }
    $permis = 'unins000.exe', 'unins000.dat', 'emplacement-modeles.txt'
    $enTrop = @($presents.Keys | Where-Object { -not $attendus.ContainsKey($_) -and $permis -notcontains $_ } | Sort-Object)
    $manquants = @($attendus.Keys | Where-Object { -not $presents.ContainsKey($_) } | Sort-Object)
    $differents = @($attendus.Keys | Where-Object { $presents.ContainsKey($_) -and $presents[$_] -ne $attendus[$_] } | Sort-Object)
    Controle "$Nom : programme installé = paquet portable ($($attendus.Count) fichiers) + désinstalleur" `
        (($enTrop.Count + $manquants.Count + $differents.Count) -eq 0) `
        "en trop $($enTrop.Count) [$(($enTrop | Select-Object -First 8) -join ', ')], manquants $($manquants.Count) [$(($manquants | Select-Object -First 8) -join ', ')], tailles différentes $($differents.Count)"
    Controle "$Nom : désinstalleur présent" ($presents.ContainsKey('unins000.exe'))
    $taille = (Get-ChildItem $Dossier -Recurse -File -Force | Measure-Object Length -Sum).Sum
    Note "programme installé : $([math]::Round($taille / 1MB, 1)) Mo ($taille octets) dans $Dossier"
}

function ControleCleUnique([string]$Nom, [string]$Dossier) {
    $cles = Cles
    $entrees = Entrees
    Controle "$Nom : une seule clé de désinstallation, version $Version" (($cles.Count -eq 1) -and $cles[0].Version -eq $Version) `
        (($cles | ForEach-Object { "$($_.Ruche) $($_.Version) $($_.Dossier)" }) -join ' ; ')
    Controle "$Nom : une seule entrée dans les programmes installés" ($entrees.Count -eq 1) (($entrees | ForEach-Object { "$($_.Ruche) $($_.Cle) $($_.Nom) $($_.Version)" }) -join ' ; ')
    if ($Dossier) {
        Controle "$Nom : dossier d'installation $Dossier" ($cles.Count -ge 1 -and $cles[0].Dossier.TrimEnd('\') -ieq $Dossier.TrimEnd('\')) $cles[0].Dossier
    }
}

function ControleRaccourcis([string]$Nom, [string]$Dossier, [bool]$Bureau) {
    $r = Raccourcis
    $exe = Join-Path $Dossier 'Scribouille.exe'
    $appli = @($r | Where-Object { $_.Cible -ieq $exe })
    $menu = @($appli | Where-Object { $_.Chemin -like "$([Environment]::GetFolderPath('Programs'))*" })
    $surBureau = @($appli | Where-Object { $_.Chemin -like "$([Environment]::GetFolderPath('Desktop'))*" })
    $autres = @($r | Where-Object { $_.Cible -ine $exe -and $_.Cible -notmatch 'unins\d+\.exe$' })
    $desinst = @($r | Where-Object { $_.Cible -match 'unins\d+\.exe$' })
    Controle "$Nom : un raccourci de l'application dans le menu Démarrer" ($menu.Count -eq 1) (($menu | ForEach-Object Chemin) -join ' ; ')
    Controle "$Nom : un raccourci de désinstallation" ($desinst.Count -eq 1) (($desinst | ForEach-Object { "$($_.Chemin) -> $($_.Cible)" }) -join ' ; ')
    Controle "$Nom : raccourci sur le Bureau $(if ($Bureau) { 'présent' } else { 'absent' })" ($surBureau.Count -eq [int]$Bureau) (($surBureau | ForEach-Object Chemin) -join ' ; ')
    Controle "$Nom : aucun raccourci vers autre chose (ancien exécutable)" ($autres.Count -eq 0) (($autres | ForEach-Object { "$($_.Chemin) -> $($_.Cible)" }) -join ' ; ')
}

function ControleDesinstalle([string]$Nom, [string]$Dossier) {
    $cles = @((Cles) | Where-Object { $_.Version -eq $Version })
    Controle "$Nom : clé de désinstallation de la $Version retirée" ($cles.Count -eq 0)
    $restes = @(if (Test-Path $Dossier) { Get-ChildItem $Dossier -Recurse -Force | ForEach-Object FullName })
    Controle "$Nom : dossier du programme retiré" (-not (Test-Path $Dossier)) "$($restes.Count) reste(s) : $(($restes | Select-Object -First 5) -join ', ')"
    $r = @((Raccourcis) | Where-Object { $_.Cible -like "$Dossier*" })
    Controle "$Nom : raccourcis retirés" ($r.Count -eq 0) (($r | ForEach-Object Chemin) -join ' ; ')
    $logiciel = ClesLogiciel
    Controle "$Nom : aucune autre clé de registre à notre nom" ($logiciel.Count -eq 0) ($logiciel -join ' ; ')
}

# Données témoins d'une 2.x : réglages, glossaire, corrections, faux modèle,
# reprise, journal ; plus le dossier d'un logiciel homonyme, qui n'est pas à nous.
function PoserTemoins([string]$Base, [switch]$Avec24) {
    $f = @{
        'config.json'                                                                = "{`n  `"preset`": `"rapide`",`n  `"langue`": `"en`",`n  `"theme`": `"sombre`",`n  `"diarisation`": false`n}`n"
        'vocabulaire.txt'                                                            = "# Glossaire témoin`nKubernetes`nZéphyrin Lagadec`n"
        'corrections.txt'                                                            = "# Corrections témoins`nqui bernetes => Kubernetes`n"
        'gabarit-ia.txt'                                                             = "Gabarit témoin`n"
        'maj-etat.json'                                                              = "{`"derniere`": `"2026-11-01`"}`n"
        'modeles\models--Systran--faster-whisper-tiny\snapshots\temoin\model.bin'    = ('M' * 300000)
        'modeles\models--Systran--faster-whisper-tiny\snapshots\temoin\config.json'  = "{`"temoin`": true}`n"
        'reprises\0123456789abcdef.json'                                             = "{`"source`": `"temoin.wav`", `"segments`": 3}`n"
        'reprises\0123456789abcdef.jsonl'                                            = "{`"d`": 0, `"f`": 1, `"t`": `"un`"}`n{`"d`": 1, `"f`": 2, `"t`": `"deux`"}`n"
        'logs\whiscribe-2026-11-01.log'                                              = "journal témoin`n"
        'models\ggml-tiers.bin'                                                      = ('T' * 1000)
    }
    if ($Avec24) {
        $f['calibration.json'] = "{`"temoin`": 1}`n"
        $f['cache-openvino\1234567890.blob'] = ('B' * 5000)
    }
    foreach ($nom in $f.Keys) {
        $chemin = Join-Path $Base $nom
        New-Item -ItemType Directory -Force (Split-Path -Parent $chemin) | Out-Null
        [IO.File]::WriteAllText($chemin, $f[$nom], [Text.UTF8Encoding]::new($false))
    }
    Empreintes $Base
}

function DemarrerFenetre([string]$Dossier, [string]$DossierJournaux, [string]$Nom) {
    # Démarrage de la fenêtre : information seulement (l'exécuteur n'est pas
    # un poste de bureau ordinaire). Fermée proprement, sinon arrêtée.
    $debut = Get-Date
    $p = Start-Process -FilePath (Join-Path $Dossier 'Scribouille.exe') -PassThru
    $prete = $null
    for ($i = 0; $i -lt 90 -and -not $prete; $i++) {
        Start-Sleep -Seconds 1
        if ($p.HasExited) { break }
        $prete = Get-ChildItem $DossierJournaux -Filter *.log -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $debut } | Select-String -Pattern 'interface prête à ([\d.,]+) s' | Select-Object -First 1
    }
    $vivant = -not $p.HasExited
    if ($vivant) {
        [void]$p.CloseMainWindow()
        if (-not $p.WaitForExit(20000)) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    Get-Process -Name Scribouille, scribouille -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Note "$Nom, fenêtre (information) : $(if ($prete) { "interface prête ($($prete.Matches[0].Groups[1].Value) s)" } elseif ($vivant) { 'ouverte, sans « interface prête » au journal en 90 s' } else { "fermée seule, code $($p.ExitCode)" })"
}

function WebView2 {
    $cles = 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
            'HKCU:\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    foreach ($c in $cles) {
        $v = (Get-ItemProperty $c -ErrorAction SilentlyContinue).pv
        if ($v -and $v -ne '0.0.0.0') { return $v }
    }
    ''
}

# ---------------------------------------------------------------------------
# Préparation commune
# ---------------------------------------------------------------------------

Etape "Poste d'essai"
Note "Windows $([Environment]::OSVersion.Version), PowerShell $($PSVersionTable.PSVersion), installateur $(Split-Path -Leaf $Installateur) ($((Get-Item $Installateur).Length) octets)"
foreach ($d in $Donnees, $Ancien) { Controle "départ propre : $(Split-Path -Leaf $d) absent" (-not (Test-Path $d)) }
Controle "départ propre : aucune clé de désinstallation" ((Cles).Count -eq 0)
$wv = WebView2
if (-not $wv) {
    # Les programmes d'installation 2.x posent une question NON supprimable
    # quand WebView2 manque ; un poste Windows 10 ou 11 l'a d'office. On le
    # pose donc comme sur un poste ordinaire, depuis Microsoft.
    $amorce = Join-Path $Travail 'MicrosoftEdgeWebview2Setup.exe'
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $amorce -UseBasicParsing
    [void](Attendre (Start-Process $amorce -ArgumentList '/silent', '/install' -PassThru) 600 'WebView2')
    $wv = WebView2
    Note "WebView2 absent de l'exécuteur, posé depuis Microsoft : $wv"
} else {
    Note "WebView2 présent : $wv"
}
Controle 'WebView2 disponible (comme sur un poste Windows 10 ou 11)' ([bool]$wv)

$DossierNeuf = Join-Path $Local 'Programs\Scribouille'
$Audio = Join-Path $Racine 'banc\extrait_fr.ogg'
$Reference = Join-Path $Racine 'banc\extrait_fr.txt'

try {
    switch ($Scenario) {

        'neuve' {
            Etape 'Installation neuve'
            Installer $Installateur 'neuve'
            [void](Inventaire 'neuve-installee')
            ControleCleUnique 'neuve' $DossierNeuf
            ControleProgramme $DossierNeuf 'neuve'
            ControleRaccourcis 'neuve' $DossierNeuf $false
            Controle 'neuve : choix des modèles noté' ((Get-Content (Join-Path $Donnees 'dossier-modeles.txt') -Raw).Trim() -ieq (Join-Path $Donnees 'modeles'))
            Controle 'neuve : WhiScribe non créé' (-not (Test-Path $Ancien))

            Etape 'Vérification et diagnostic'
            $r = Commande $DossierNeuf @('--verifier')
            Controle 'scribouille --verifier : code 0' ($r.Code -eq 0) "code $($r.Code)"
            $r = Commande $DossierNeuf @('diagnostic', '--json')
            $d = $r.Json.donnees
            Controle 'diagnostic : code 0 ou 3 (modèle absent)' ($r.Code -in 0, 3) "code $($r.Code)"
            Controle "diagnostic : version $Version, mode installée" ($d.version -eq $Version -and $d.mode -eq 'installee') "$($d.version) / $($d.mode)"
            Controle 'diagnostic : données dans Scribouille' ($d.donnees -ieq $Donnees) $d.donnees

            Etape 'Vraie transcription courte (tiny, processeur)'
            $r = Commande $DossierNeuf @('reglages', 'definir', 'mode_avance=true', 'modele_avance=tiny', '--json')
            Controle 'réglages : modèle tiny en mode avancé' ($r.Code -eq 0) "code $($r.Code)"
            $sorties = Join-Path $Travail 'transcriptions'
            New-Item -ItemType Directory -Force $sorties | Out-Null
            $r = Commande $DossierNeuf @('transcrire', $Audio, '--moteur', 'ctranslate2', '--telecharger', '--sortie', $sorties, '--json') 900
            Controle 'transcrire : code 0' ($r.Code -eq 0) "code $($r.Code) $($r.Erreurs)"
            $txt = Get-ChildItem $sorties -Filter *.txt | Select-Object -First 1
            $compagnon = Get-ChildItem $sorties -Filter *.json | Select-Object -First 1
            Controle 'transcrire : .txt et .json écrits' ([bool]$txt -and [bool]$compagnon)
            if ($txt) {
                $obtenu = (Get-Content $txt.FullName -Raw -Encoding utf8).ToLowerInvariant()
                $mots = [regex]::Matches((Get-Content $Reference -Raw -Encoding utf8).ToLowerInvariant(), '\w+') | ForEach-Object Value
                $trouves = @($mots | Where-Object { $obtenu -match "\b$([regex]::Escape($_))\b" }).Count
                $part = [math]::Round($trouves / $mots.Count, 2)
                Controle 'transcrire : texte fidèle (au moins la moitié des mots de la référence)' ($part -ge 0.5) "$trouves sur $($mots.Count) ($part)"
            }
            DemarrerFenetre $DossierNeuf (Join-Path $Donnees 'logs') 'neuve'

            Etape 'Désinstallation silencieuse'
            $avant = Empreintes $Donnees
            [void](Desinstaller 'neuve-silencieuse')
            [void](Inventaire 'neuve-desinstallee')
            ControleDesinstalle 'neuve' $DossierNeuf
            $apres = Empreintes $Donnees
            Controle 'silencieuse : données de l''utilisateur laissées telles quelles' (($apres.Keys.Count -eq $avant.Keys.Count) -and -not @($avant.Keys | Where-Object { $apres[$_] -ne $avant[$_] }).Count) "$($avant.Keys.Count) fichiers avant, $($apres.Keys.Count) après"
            Controle 'silencieuse : transcriptions intactes' ((Get-ChildItem $sorties -File).Count -ge 2)

            Etape 'Désinstallation avec effacement complet (ligne de commande de l''application)'
            Installer $Installateur 'neuve-2'
            # Ce qui n'est pas à nous, dans les deux dossiers : jamais effacé.
            New-Item -ItemType Directory -Force (Join-Path $Ancien 'models') | Out-Null
            Set-Content (Join-Path $Ancien 'models\ggml-tiers.bin') 'tiers' -Encoding utf8
            Set-Content (Join-Path $Donnees 'note-personnelle.txt') 'pas a Scribouille' -Encoding utf8
            $dialogues = Desinstaller 'neuve-effacement' -Interactif
            [void](Inventaire 'neuve-effacement')
            ControleDesinstalle 'neuve-effacement' $DossierNeuf
            Controle 'effacement : la liste de ce qui part a été montrée' (@($dialogues | Where-Object { $_ -match 'Erase every file|Effacer tous les fichiers' }).Count -eq 1) (($dialogues) -join ' || ')
            $restes = @(if (Test-Path $Donnees) { Get-ChildItem $Donnees -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Donnees.Length + 1) } })
            Controle 'effacement : il ne reste dans Scribouille que ce qui n''est pas à nous' (($restes.Count -eq 1) -and $restes[0] -eq 'note-personnelle.txt') ($restes -join ', ')
            Controle 'effacement : modèle téléchargé effacé' (-not (Test-Path (Join-Path $Donnees 'modeles')))
            Controle 'effacement : dossier du logiciel homonyme intact' (Test-Path (Join-Path $Ancien 'models\ggml-tiers.bin'))
            Controle 'effacement : transcriptions intactes' ((Get-ChildItem $sorties -File).Count -ge 2)

            Etape 'Désinstallation avec effacement, repli du désinstalleur (ligne de commande absente)'
            Installer $Installateur 'neuve-3'
            $t = PoserTemoins $Ancien
            $r = Commande $DossierNeuf @('reglages', 'definir', 'langue=en', '--json')
            Controle 'premier lancement (reprise de WhiScribe) : code 0' ($r.Code -eq 0) "code $($r.Code)"
            Remove-Item (Join-Path $DossierNeuf 'scribouille.com') -Force
            $dialogues = Desinstaller 'neuve-repli' -Interactif
            [void](Inventaire 'neuve-repli')
            ControleDesinstalle 'neuve-repli' $DossierNeuf
            Controle 'repli : question des modèles puis des données posées' (@($dialogues | Where-Object { $_ -match 'transcription models|modèles de transcription' }).Count -eq 1 -and @($dialogues | Where-Object { $_ -match 'personal|personnelles' }).Count -eq 1) (($dialogues) -join ' || ')
            $restes = @(if (Test-Path $Donnees) { Get-ChildItem $Donnees -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Donnees.Length + 1) } })
            Controle 'repli : tailles dans les unités de la langue de l''assistant (Windows anglais : KB, MB, GB)' (-not @($dialogues | Where-Object { $_ -match '\d (Ko|Mo|Go)\b' }).Count) (($dialogues) -join ' || ')
            Controle 'repli : Scribouille vidé de ce qui est à nous' (($restes.Count -eq 1) -and $restes[0] -eq 'note-personnelle.txt') ($restes -join ', ')
            Controle 'repli : dossier du logiciel homonyme intact' (Test-Path (Join-Path $Ancien 'models\ggml-tiers.bin'))
        }

        { $_ -in 'depuis-2.3.3', 'depuis-2.4.0' } {
            $est24 = $Scenario -eq 'depuis-2.4.0'
            $ancienneVersion = if ($est24) { '2.4.0' } else { '2.3.3' }
            $fichier = if ($est24) { 'Scribouille-Setup-2.4.0.exe' } else { 'WhiScribe-Setup-2.3.3.exe' }
            $dossier = if ($est24) { Join-Path $Local 'Programs\Scribouille' } else { Join-Path $Local 'Programs\WhiScribe' }

            Etape "Installation de la $ancienneVersion publiée"
            $ancienInstallateur = Telecharger "v$ancienneVersion" $fichier
            Installer $ancienInstallateur $ancienneVersion @('/TASKS="desktopicon"')
            $cles = Cles
            Controle "$ancienneVersion installée (clé HKCU, version $ancienneVersion)" ($cles.Count -eq 1 -and $cles[0].Version -eq $ancienneVersion -and $cles[0].Ruche -eq 'HKCU') (($cles | ForEach-Object { "$($_.Ruche) $($_.Version)" }) -join ' ; ')
            [void](Inventaire "$ancienneVersion-installee")
            $temoins = PoserTemoins $Ancien -Avec24:$est24
            $choix = (Get-Content (Join-Path $Ancien 'dossier-modeles.txt') -Raw).Trim()
            Note "choix des modèles noté par la $ancienneVersion : $choix"
            $avantProgramme = @(Get-ChildItem $dossier -File | ForEach-Object Name)
            Note "racine du programme $ancienneVersion : $($avantProgramme -join ', ')"
            $poids = (Get-ChildItem $dossier -Recurse -File -Force | Measure-Object Length -Sum).Sum
            Note "programme $ancienneVersion installé : $([math]::Round($poids / 1MB, 1)) Mo ($poids octets)"

            Etape "Installation de la $Version par-dessus"
            Installer $Installateur 'mise-a-jour'
            [void](Inventaire 'mise-a-jour-installee')
            ControleCleUnique 'mise à jour' $dossier
            ControleProgramme $dossier 'mise à jour'
            ControleRaccourcis 'mise à jour' $dossier $true
            $avantLancement = Empreintes $Ancien
            Controle 'avant le premier lancement : WhiScribe intact' (-not @($temoins.Keys | Where-Object { $avantLancement[$_] -ne $temoins[$_] }).Count)
            Controle 'avant le premier lancement : rien posé dans Scribouille (la reprise fera tout)' (-not (Test-Path $Donnees)) $(if (Test-Path $Donnees) { (Get-ChildItem $Donnees -Recurse -Force | ForEach-Object Name) -join ', ' })

            Etape 'Premier lancement (ligne de commande)'
            $r = Commande $dossier @('reglages', 'definir', 'langue=en', '--json')
            Controle 'premier lancement : code 0' ($r.Code -eq 0) "code $($r.Code) $($r.Erreurs)"
            $apres = Empreintes $Donnees
            $perdus = @()
            foreach ($nom in $temoins.Keys) {
                if ($nom -like 'models\*') { continue }
                if ($nom -in 'config.json', 'dossier-modeles.txt') { continue }
                if ($apres[$nom] -ne $temoins[$nom]) { $perdus += $nom }
            }
            Controle 'données reprises dans Scribouille, à l''octet près (glossaire, corrections, modèle, reprise, journaux...)' ($perdus.Count -eq 0) "différents ou absents : $($perdus -join ', ')"
            $restesAncien = @(if (Test-Path $Ancien) { Get-ChildItem $Ancien -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($Ancien.Length + 1) } })
            Controle 'WhiScribe : ne garde que le dossier du logiciel homonyme' (($restesAncien.Count -eq 1) -and $restesAncien[0] -eq 'models\ggml-tiers.bin') ($restesAncien -join ', ')
            $journal = Get-Content (Join-Path $Donnees 'migration-whiscribe.json') -Raw -Encoding utf8 | ConvertFrom-Json
            Controle 'journal de la reprise : terminée, rien de resté' ($journal.etat -eq 'terminee' -and @($journal.restes).Count -eq 0) "état $($journal.etat)"
            Controle 'journal de la reprise : aucun doublon rangé à part' (@($journal.conflits).Count -eq 0) "conflits : $(@($journal.conflits) -join ', ')"
            $choixApres = (Get-Content (Join-Path $Donnees 'dossier-modeles.txt') -Raw).Trim()
            Controle 'choix des modèles : Scribouille\modeles' ($choixApres -ieq (Join-Path $Donnees 'modeles')) $choixApres
            foreach ($cle in @{ preset = 'rapide'; langue = 'en'; theme = 'sombre' }.GetEnumerator()) {
                $r = Commande $dossier @('reglages', 'lire', $cle.Key, '--json')
                Controle "réglage repris : $($cle.Key) = $($cle.Value)" ($r.Json.donnees.valeur -eq $cle.Value) "$($r.Json.donnees.valeur)"
            }
            $r = Commande $dossier @('diagnostic', '--json')
            $d = $r.Json.donnees
            Controle "diagnostic : version $Version, mode installée, données dans Scribouille" ($d.version -eq $Version -and $d.mode -eq 'installee' -and $d.donnees -ieq $Donnees) "$($d.version) / $($d.mode) / $($d.donnees)"
            Controle 'diagnostic : glossaire témoin lu (2 termes)' ($d.vocabulaire.nb_termes -eq 2) "$($d.vocabulaire.nb_termes)"
            Controle 'diagnostic : modèles dans Scribouille\modeles' ($d.modeles_dossier -ieq (Join-Path $Donnees 'modeles')) $d.modeles_dossier
            $r = Commande $dossier @('--verifier')
            Controle 'scribouille --verifier : code 0' ($r.Code -eq 0) "code $($r.Code)"
            DemarrerFenetre $dossier (Join-Path $Donnees 'logs') 'mise à jour'
            [void](Inventaire 'mise-a-jour-lancee')

            Etape 'Désinstallation silencieuse'
            $avant = Empreintes $Donnees
            [void](Desinstaller 'mise-a-jour')
            [void](Inventaire 'mise-a-jour-desinstallee')
            ControleDesinstalle 'mise à jour' $dossier
            $apres = Empreintes $Donnees
            Controle 'silencieuse : données de l''utilisateur laissées telles quelles' (-not @($avant.Keys | Where-Object { $apres[$_] -ne $avant[$_] }).Count) "$($avant.Keys.Count) fichiers avant, $($apres.Keys.Count) après"
            Controle 'silencieuse : dossier du logiciel homonyme intact' (Test-Path (Join-Path $Ancien 'models\ggml-tiers.bin'))
        }

        'cohabitation' {
            $dossier2x = 'C:\Program Files\WhiScribe'
            Etape 'WhiScribe 2.3.3 installée pour tous les utilisateurs, dans un autre dossier'
            $ancienInstallateur = Telecharger 'v2.3.3' 'WhiScribe-Setup-2.3.3.exe'
            Installer $ancienInstallateur '2.3.3-tous' @('/ALLUSERS', "/DIR=`"$dossier2x`"")
            $cles = Cles
            Controle '2.3.3 installée (clé HKLM)' ($cles.Count -eq 1 -and $cles[0].Ruche -like 'HKLM*' -and $cles[0].Version -eq '2.3.3') (($cles | ForEach-Object { "$($_.Ruche) $($_.Version) $($_.Dossier)" }) -join ' ; ')
            Controle 'aucun WhiScribe.exe dans Programs\WhiScribe (seule la clé la révèle)' (-not (Test-Path (Join-Path $Local 'Programs\WhiScribe\WhiScribe.exe')))
            $temoins = PoserTemoins $Ancien
            [void](Inventaire '2.3.3-installee')

            Etape "Installation de la $Version pour l'utilisateur"
            Installer $Installateur 'cohabitation' @('/CURRENTUSER')
            [void](Inventaire 'cohabitation-installee')
            $cles = Cles
            Controle 'deux installations, une par ruche (2.3.3 et 3.x)' ($cles.Count -eq 2 -and @($cles | Where-Object { $_.Ruche -eq 'HKCU' -and $_.Version -eq $Version }).Count -eq 1) (($cles | ForEach-Object { "$($_.Ruche) $($_.Version)" }) -join ' ; ')
            ControleProgramme $DossierNeuf 'cohabitation'
            Controle 'l''installation n''a pas créé Scribouille (la 2.x partage WhiScribe)' (-not (Test-Path $Donnees))
            $amorce = (Get-Content (Join-Path $DossierNeuf 'emplacement-modeles.txt') -Raw).Trim()
            Controle 'modèles notés à côté du programme : ceux de la 2.x' ($amorce -ieq (Join-Path $Ancien 'modeles')) $amorce
            $e = Empreintes $Ancien
            Controle 'WhiScribe intact après l''installation' (-not @($temoins.Keys | Where-Object { $e[$_] -ne $temoins[$_] }).Count)

            Etape 'Premier lancement : dossier partagé'
            $r = Commande $DossierNeuf @('reglages', 'definir', 'theme=clair', '--json')
            Controle 'premier lancement : code 0' ($r.Code -eq 0) "code $($r.Code) $($r.Erreurs)"
            $r = Commande $DossierNeuf @('diagnostic', '--json')
            $d = $r.Json.donnees
            Controle 'diagnostic : données gardées dans WhiScribe, partagées avec la 2.x' ($d.donnees -ieq $Ancien -and [bool]$d.donnees_partagees) "$($d.donnees) ; partagées avec : $($d.donnees_partagees)"
            Controle 'diagnostic : modèles de la 2.x' ($d.modeles_dossier -ieq (Join-Path $Ancien 'modeles')) $d.modeles_dossier
            Controle 'Scribouille toujours absent' (-not (Test-Path $Donnees))
            DemarrerFenetre $DossierNeuf (Join-Path $Ancien 'logs') 'cohabitation'
            $e = Empreintes $Ancien
            $changes = @($temoins.Keys | Where-Object { $e[$_] -ne $temoins[$_] })
            Controle 'rien de la 2.x n''a changé (réglages, glossaire, modèles, reprise, journaux)' ($changes.Count -eq 0) ($changes -join ', ')
            Note "ajouté par la 3.x dans WhiScribe : $((@($e.Keys | Where-Object { -not $temoins.Contains($_) })) -join ', ')"

            Etape 'Désinstallation de la 3.x avec effacement complet (ligne de commande)'
            $dialogues = Desinstaller 'cohabitation-effacement' -Interactif
            [void](Inventaire 'cohabitation-effacement')
            ControleDesinstalle 'cohabitation' $DossierNeuf
            $e = Empreintes $Ancien
            $changes = @($temoins.Keys | Where-Object { $e[$_] -ne $temoins[$_] })
            Controle 'effacement complet : rien de la 2.x touché' ($changes.Count -eq 0) ($changes -join ', ')
            Controle '2.3.3 toujours installée (clé et programme)' (@((Cles) | Where-Object { $_.Version -eq '2.3.3' }).Count -eq 1 -and (Test-Path (Join-Path $dossier2x 'WhiScribe.exe')))

            Etape 'Désinstallation de la 3.x, repli du désinstalleur (ligne de commande absente)'
            Installer $Installateur 'cohabitation-2' @('/CURRENTUSER')
            $r = Commande $DossierNeuf @('reglages', 'definir', 'theme=clair', '--json')
            Remove-Item (Join-Path $DossierNeuf 'scribouille.com') -Force
            $dialogues = Desinstaller 'cohabitation-repli' -Interactif
            [void](Inventaire 'cohabitation-repli')
            ControleDesinstalle 'cohabitation (repli)' $DossierNeuf
            Controle 'repli : aucune question sur les modèles ni les données de la 2.x' (@($dialogues | Where-Object { $_ -match 'transcription models|modèles de transcription|personal|personnelles' }).Count -eq 0) (($dialogues) -join ' || ')
            $e = Empreintes $Ancien
            $changes = @($temoins.Keys | Where-Object { $e[$_] -ne $temoins[$_] })
            Controle 'repli : rien de la 2.x touché' ($changes.Count -eq 0) ($changes -join ', ')
            Controle '2.3.3 toujours installée' (@((Cles) | Where-Object { $_.Version -eq '2.3.3' }).Count -eq 1 -and (Test-Path (Join-Path $dossier2x 'WhiScribe.exe')))
        }
    }
} catch {
    Controle "déroulement sans erreur" $false "$($_.Exception.Message) ($($_.InvocationInfo.ScriptLineNumber))"
}

$script:Bilan | Out-File -Encoding utf8 (Join-Path $Rapport 'bilan.txt')
Write-Host ''
if ($script:Echecs.Count) {
    Write-Host "Scénario $Scenario : $($script:Echecs.Count) échec(s)."
    exit 1
}
Write-Host "Scénario $Scenario : tout est conforme."
exit 0
