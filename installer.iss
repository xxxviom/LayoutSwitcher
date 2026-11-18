; Інсталятор для Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Спершу запустіть build.bat, щоб з'явився dist\LayoutSwitcher.exe
[Setup]
AppName=LayoutSwitcher
AppVersion=1.0
DefaultDirName={autopf}\LayoutSwitcher
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=LayoutSwitcher-Setup
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускати разом з Windows"

[Files]
Source: "dist\LayoutSwitcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "blacklist.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "words_*.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "dictionaries\*"; DestDir: "{app}\dictionaries"; Flags: onlyifdoesntexist skipifsourcedoesntexist recursesubdirs

[Icons]
Name: "{autoprograms}\LayoutSwitcher"; Filename: "{app}\LayoutSwitcher.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "LayoutSwitcher"; ValueData: """{app}\LayoutSwitcher.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\LayoutSwitcher.exe"; Description: "Запустити LayoutSwitcher"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM LayoutSwitcher.exe"; Flags: runhidden; RunOnceId: "KillLS"
