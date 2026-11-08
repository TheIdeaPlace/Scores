# Runs in the VM, elevated: stop JAWS and its helpers, the error reporter, and the app.
Get-Process jfw, fsSynth*, fssm, FSReader, FSLauncher*, JAWS*, jhookldr, ErrorReporting*, Scores, notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process | Where-Object { $_.MainWindowTitle -match 'Vispero|JAWS' } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep 2
(Get-Process | Where-Object { $_.Path -like '*Freedom Scientific*' } | ForEach-Object Name) -join ', '
'stopped'
