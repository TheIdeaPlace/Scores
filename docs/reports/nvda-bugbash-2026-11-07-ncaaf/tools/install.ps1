# Install Scores 1.1.1 the way users get it, silently, then report where it went.
Get-Process OneDrive -ErrorAction SilentlyContinue | Stop-Process -Force
$p = Start-Process 'C:\vmtest\files\Scores-1.1.1-Setup.exe' -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOCANCEL' -PassThru -Wait
"setup exit: $($p.ExitCode)"
Get-Process Scores -ErrorAction SilentlyContinue | Stop-Process -Force
$exe = Join-Path $env:LOCALAPPDATA 'Programs\Scores\Scores.exe'
if (Test-Path $exe) { "installed: $exe $((Get-Item $exe).VersionInfo.ProductVersion)" } else { "not found at $exe" }
