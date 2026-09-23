; Windows installer for the desktop app (Inno Setup 6).
;
;   iscc /DAppVersion=1.2.3 packaging\installer.iss
;
; Installs per user, so it needs no administrator rights -- common in offices
; where staff cannot elevate. The program goes under
; %LOCALAPPDATA%\Programs\Shabetz; the data lives separately in
; %LOCALAPPDATA%\Shabetz, which is why upgrading or uninstalling never touches
; anyone's schedule.

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

[Setup]
AppId={{6F3C9A52-2E1B-4F7D-9C8A-5B4E1D2F7A10}
AppName=Shabetz
AppVersion={#AppVersion}
AppPublisher=Shabetz
DefaultDirName={localappdata}\Programs\Shabetz
DefaultGroupName=Shabetz
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Shabetz-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\Shabetz.exe
UninstallDisplayName=Shabetz
; An upgrade must replace files the running app holds open.
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Shabetz\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Shabetz"; Filename: "{app}\Shabetz.exe"
Name: "{userdesktop}\Shabetz"; Filename: "{app}\Shabetz.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Shabetz.exe"; Description: "Start Shabetz now"; Flags: nowait postinstall skipifsilent
