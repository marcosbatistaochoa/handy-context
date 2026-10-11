# Start the helper now and at every logon, with no console window.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command pythonw.exe).Source
$startup = [Environment]::GetFolderPath("Startup")
$lnkPath = Join-Path $startup "handy-context.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $pythonw
$lnk.Arguments = "-m handy_context"
$lnk.WorkingDirectory = $root
$lnk.Description = "Deep Context and dictionary for Handy dictation"
$lnk.Save()
Write-Output "Startup shortcut: $lnkPath"

# Restart it now.
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*handy_context*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process -FilePath $pythonw -ArgumentList "-m handy_context" -WorkingDirectory $root -WindowStyle Hidden
# A cold start can take longer than 2 s, so ask every half second for 20 s.
$deadline = (Get-Date).AddSeconds(20)
$started = Get-Date
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
        $secs = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
        Write-Output "Helper answers: $($r.Content) (after $secs s)"
        exit 0
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
Write-Output "Helper did not answer on 127.0.0.1:8765 within 20 s"
exit 1
