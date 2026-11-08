Get-Process Scores, notepad, msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
$dir = Join-Path $env:APPDATA 'Scores'
Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $dir | Out-Null
Set-Content -Path (Join-Path $dir 'settings.json') -Value '{"auto_check_updates": false}' -Encoding ASCII
'reset'
