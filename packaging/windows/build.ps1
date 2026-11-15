# Fabrique l'appli Windows : version portable (.zip) et installateur (.exe).
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1 -Version 1.0.0 -ToolsDir build\imobiledevice
#
# Prérequis : Python 3.10+, Inno Setup 6 (pour l'installateur), et les outils iPhone rassemblés par
# collect_imobiledevice.sh (sinon l'appli fonctionne sans la partie iPhone).
param(
    [string]$Version = "1.0.0",
    [string]$ToolsDir = ""
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "== Dépendances"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller pillow

Write-Host "== Icône"
python packaging\windows\make_icon.py build\app.ico

Write-Host "== PyInstaller"
python -m PyInstaller --noconfirm --clean --log-level WARN `
    --name SmartphoneBackup --windowed --icon build\app.ico `
    --distpath dist --workpath build\pyi --specpath build `
    --paths "$Root" `
    --add-data "$Root\smartphone_backup\icons;smartphone_backup\icons" `
    --exclude-module tkinter `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué" }

$App = "dist\SmartphoneBackup"
if ($ToolsDir) {
    Write-Host "== Outils iPhone"
    New-Item -ItemType Directory -Force "$App\tools" | Out-Null
    Copy-Item -Recurse -Force $ToolsDir "$App\tools\imobiledevice"
}
Copy-Item README.md "$App\LISEZMOI.md"

Write-Host "== Version portable"
$Zip = "dist\SmartphoneBackup-$Version-windows-portable.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path $App -DestinationPath $Zip

Write-Host "== Installateur"
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "${env:ProgramFiles}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) { Write-Warning "Inno Setup introuvable : installateur non fabriqué"; exit 0 }
& $Iscc "/DAppVersion=$Version" packaging\windows\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup a échoué" }
Get-ChildItem dist\*.zip, dist\*setup.exe | Format-Table Name, Length
