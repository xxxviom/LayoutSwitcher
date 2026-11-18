; Інсталятор для Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Збирається командою: ISCC installer.iss  (спершу потрібні dist\LayoutSwitcher.exe, words_*.txt і dictionaries\,
; їх готують fetch_data.py і PyInstaller; усе це робить build.bat та GitHub Actions)
#ifndef AppVersion
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{685570FF-6467-4694-8532-DB1E7774C41B}
AppName=LayoutSwitcher
AppVersion={#AppVersion}
AppPublisher=xxxviom
AppPublisherURL=https://github.com/xxxviom/LayoutSwitcher
DefaultDirName={autopf}\LayoutSwitcher
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=dist
OutputBaseFilename=LayoutSwitcher-Setup
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\LayoutSwitcher.exe
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускати разом з Windows"

[Files]
Source: "dist\LayoutSwitcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "blacklist.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "THIRD_PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "words_*.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "dictionaries\*"; DestDir: "{app}\dictionaries"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{autoprograms}\LayoutSwitcher"; Filename: "{app}\LayoutSwitcher.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LayoutSwitcher"; ValueData: """{app}\LayoutSwitcher.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\LayoutSwitcher.exe"; Description: "Запустити LayoutSwitcher"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM LayoutSwitcher.exe"; Flags: runhidden; RunOnceId: "KillLS"
