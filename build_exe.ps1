# drawfeilin build script: PyInstaller exe + Inno Setup installer
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# 1) Ensure PyInstaller
python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'pip install pyinstaller failed' }

# 2) Ensure runtime deps (3D 切片需要 trimesh，轮廓处理需要 shapely)
python -m pip install --upgrade trimesh shapely openpyxl
if ($LASTEXITCODE -ne 0) { throw 'pip install trimesh/shapely failed' }

# 3) PyInstaller build (onedir, windowed, README.md embedded)
python -m PyInstaller --noconfirm --clean --onedir --windowed --name drawfeilin --add-data "README.md;." --hidden-import trimesh --hidden-import trimesh.creation --hidden-import trimesh.intersections --hidden-import trimesh.path --hidden-import trimesh.path.exchange --hidden-import shapely --hidden-import shapely.geometry --hidden-import shapely.ops --hidden-import openpyxl drawfeilin_gui.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

# 4) Ship config.ini template next to the exe
$configDst = Join-Path $root 'dist\drawfeilin\config.ini'
Copy-Item -LiteralPath (Join-Path $root 'config.ini') -Destination $configDst -Force

# 5) Build installer with Inno Setup
$iscc = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw 'ISCC.exe not found. Install Inno Setup 6 first: winget install --id JRSoftware.InnoSetup'
}
& $iscc (Join-Path $root 'installer.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build failed' }

Write-Host ''
Write-Host 'Build finished:'
Write-Host '  App folder: dist\drawfeilin\'
Write-Host '  Installer:  dist\installer\drawfeilin_setup.exe'
