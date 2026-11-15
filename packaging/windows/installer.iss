; Installateur Windows de Smartphone Backup (Inno Setup 6).
; Installation pour l'utilisateur courant, sans droits administrateur (au choix dans l'assistant).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C1E3F52-6B5A-4C1E-9E1F-3A7B2D9C4E11}
AppName=Smartphone Backup
AppVersion={#AppVersion}
AppPublisher=Smartphone Backup
DefaultDirName={autopf}\Smartphone Backup
DefaultGroupName=Smartphone Backup
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=SmartphoneBackup-{#AppVersion}-windows-setup
SetupIconFile=..\..\build\app.ico
UninstallDisplayIcon={app}\SmartphoneBackup.exe
UninstallDisplayName=Smartphone Backup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\SmartphoneBackup\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Smartphone Backup"; Filename: "{app}\SmartphoneBackup.exe"
Name: "{autodesktop}\Smartphone Backup"; Filename: "{app}\SmartphoneBackup.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SmartphoneBackup.exe"; Description: "{cm:LaunchProgram,Smartphone Backup}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; arrête le serveur adb téléchargé par l'appli, sinon ses fichiers resteraient verrouillés
Filename: "{localappdata}\SmartphoneBackup\platform-tools\adb.exe"; Parameters: "kill-server"; Flags: runhidden skipifdoesntexist; RunOnceId: "AdbKill"

[UninstallDelete]
; outils téléchargés par l'appli (adb) ; les sauvegardes ne sont jamais touchées
Type: filesandordirs; Name: "{localappdata}\SmartphoneBackup"
