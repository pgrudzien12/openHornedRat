; Inno Setup script for the Windows installer (epic #96, issue #97).
;
; PyInstaller freezes packaging/entrypoint.py into dist/ohr-engine/; this script
; wraps that onedir output. Per-user install, no admin required
; (PrivilegesRequired=lowest, install dir under the user's local app data, Start Menu shortcut
; under the user's own Start Menu, not the shared one).
;
; Build (after `pyinstaller packaging\windows\ohr-engine.spec --distpath dist --workpath build`):
;   ISCC packaging\windows\installer.iss
; Optionally override the version: ISCC /DMyAppVersion=1.2.3 packaging\windows\installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#define MyAppName "Open Horned Rat"
#define MyAppPublisher "openHornedRat project"
#define MyAppURL "https://github.com/pgrudzien12/openHornedRat"
#define MyAppExeName "ohr-engine.exe"
#define DistDir "..\..\dist\ohr-engine"

[Setup]
; Generated once for this app; do not reuse for unrelated installers.
AppId={{B36F9F2E-6E3C-4B7B-9C7B-6C9B4C6F0F8A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=ohr-engine-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The engine needs OpenGL 3.3 core; a fixed x64 build matches requirements-engine.txt's wheels.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Onedir build: the .exe plus its whole _internal/ tree (pygame-ce/zengl DLLs, the bundled
; scripts/ helper modules, and their third-party license notices as extracted below).
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "__pycache__\*,__pycache__"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: postinstall nowait skipifsilent unchecked
