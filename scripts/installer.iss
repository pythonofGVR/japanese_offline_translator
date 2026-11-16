#define AppName "Japanese Offline Translator"
#define AppVersion "1.0.0"
[Setup]
AppId={{AF8905FA-6BE4-4646-8A40-93A452B12CC7}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\JapaneseTranslator
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=JapaneseTranslatorSetup
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
LicenseFile=..\LICENSES.md
[Files]
Source: "..\dist\JapaneseTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\日文离线翻译器"; Filename: "{app}\JapaneseTranslator.exe"
Name: "{autodesktop}\日文离线翻译器"; Filename: "{app}\JapaneseTranslator.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; Flags: unchecked
[Run]
Filename: "{app}\JapaneseTranslator.exe"; Description: "启动日文离线翻译器"; Flags: nowait postinstall skipifsilent
