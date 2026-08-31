; drawfeilin 安装包脚本（Inno Setup 6）
; 构建前先运行 build_exe.ps1 生成 dist\drawfeilin\，再执行本脚本。

#define MyAppName "drawfeilin 菲林自动绘制工具"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "drawfeilin"
#define MyAppExeName "drawfeilin.exe"
#define MyAppId "4B266371-64DC-4FDD-8685-E6BB36693812"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\drawfeilin
DefaultGroupName=drawfeilin
OutputDir=dist\installer
OutputBaseFilename=drawfeilin_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\drawfeilin.exe

[Languages]
Name: "chinesesimplified"; MessagesFile: "packaging\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\drawfeilin\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
