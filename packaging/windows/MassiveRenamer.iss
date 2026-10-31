; Installer per Windows (Inno Setup 6), creato da build.py con la cartella dist\MassiveRenamer\.
;
; Si installa per il solo utente in %LOCALAPPDATA%\Programs\MassiveRenamer, senza permessi da
; amministratore: così l'aggiornamento automatico può sostituire i file. L'aggiornamento lancia questo
; installer con /VERYSILENT /LAUNCH: /LAUNCH riapre il programma alla fine.

#ifndef AppVersion
  #error "Manca /DAppVersion=X.Y.Z"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\MassiveRenamer"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif

[Setup]
AppId={{B926EB72-64E8-413F-B18F-F0E8DFC7EAA6}
AppName=MassiveRenamer
AppVersion={#AppVersion}
AppVerName=MassiveRenamer {#AppVersion}
AppPublisher=Giulio Banterla
AppPublisherURL=https://github.com/giuliobanterla/MassiveRenamer
AppSupportURL=https://github.com/giuliobanterla/MassiveRenamer/issues
AppUpdatesURL=https://github.com/giuliobanterla/MassiveRenamer/releases
AppCopyright=GPL-3.0
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\MassiveRenamer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\..\assets\icon\icon.ico
UninstallDisplayIcon={app}\MassiveRenamer.exe
UninstallDisplayName=MassiveRenamer
OutputDir={#OutputDir}
OutputBaseFilename=MassiveRenamer-setup
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
en.ContextMenu=Add «Rename with MassiveRenamer» to the right-click menu
it.ContextMenu=Aggiungi «Rinomina con MassiveRenamer» al menu del tasto destro
en.ContextLabel=Rename with MassiveRenamer
it.ContextLabel=Rinomina con MassiveRenamer

[Tasks]
Name: "contextmenu"; Description: "{cm:ContextMenu}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Le librerie della versione precedente: una nuova versione può non usarle più
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MassiveRenamer"; Filename: "{app}\MassiveRenamer.exe"
Name: "{autodesktop}\MassiveRenamer"; Filename: "{app}\MassiveRenamer.exe"; Tasks: desktopicon

[Registry]
; Stesse chiavi che scrive il programma (massiverenamer/integration.py), per file, cartelle e sfondo
Root: HKCU; Subkey: "Software\Classes\*\shell\MassiveRenamer"; ValueType: string; ValueData: "{cm:ContextLabel}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MassiveRenamer"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\MassiveRenamer.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MassiveRenamer"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\MassiveRenamer\command"; ValueType: string; ValueData: """{app}\MassiveRenamer.exe"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MassiveRenamer"; ValueType: string; ValueData: "{cm:ContextLabel}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MassiveRenamer"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\MassiveRenamer.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MassiveRenamer"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MassiveRenamer\command"; ValueType: string; ValueData: """{app}\MassiveRenamer.exe"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MassiveRenamer"; ValueType: string; ValueData: "{cm:ContextLabel}"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MassiveRenamer"; ValueType: string; ValueName: "Icon"; ValueData: """{app}\MassiveRenamer.exe"",0"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MassiveRenamer"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MassiveRenamer\command"; ValueType: string; ValueData: """{app}\MassiveRenamer.exe"" ""%V"""; Tasks: contextmenu
; Alla disinstallazione le voci vanno via anche se le ha aggiunte il programma dal suo menu
Root: HKCU; Subkey: "Software\Classes\*\shell\MassiveRenamer"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\MassiveRenamer"; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\Background\shell\MassiveRenamer"; Flags: dontcreatekey uninsdeletekey

[Run]
Filename: "{app}\MassiveRenamer.exe"; Description: "{cm:LaunchProgram,MassiveRenamer}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\MassiveRenamer.exe"; Flags: nowait; Check: LaunchRequested

[Code]
function LaunchRequested: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/LAUNCH') = 0 then
      Result := True;
end;
