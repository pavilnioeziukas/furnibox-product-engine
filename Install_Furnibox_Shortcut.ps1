$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectDir "Start_Furnibox_Product_Engine.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Furnibox Product Engine.lnk"

if (-not (Test-Path $Launcher)) {
    throw "Nerastas paleidimo failas: $Launcher"
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Launcher
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.Description = "Furnibox produktų ir BOM valdymo įrankis"

$PythonIcon = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
if (Test-Path $PythonIcon) {
    $Shortcut.IconLocation = "$PythonIcon,0"
}

$Shortcut.Save()
Write-Host "Darbalaukio nuoroda sukurta:" -ForegroundColor Green
Write-Host $ShortcutPath
