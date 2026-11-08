# Host side: one JAWS take of the harness with arguments <HArgs>, exact speech to <Name>.jaws.txt.
param([Parameter(Mandatory)][string]$Name, [string]$HArgs = '', [string]$Steps = 'harness')
$ErrorActionPreference = 'Continue'
$proj = 'C:\Users\kelly\OneDrive\testing\Scores\moreaudio\jaws-stray-dialog-text-2026-11-08'
$vt = 'C:\Users\kelly\GitHub\TheWorkBench\vmtest\vmtest.ps1'
function V { powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $vt @args }
Set-Location C:\Users\kelly\GitHub\Scores\.claude\worktrees\agent-a1350ad352800619c
V run "taskkill /f /im Harness.exe /im Scores.exe /im notepad.exe >nul 2>&1" | Out-Null
V push C:\Users\kelly\scratch\jaws-stray\jdrive.ps1 | Out-Null
V push "$proj\steps\$Steps.steps" | Out-Null
V launch notepad.exe | Out-Null
Start-Sleep 2
if ($HArgs) { V launch 'C:\vmtest\apps\Harness\Harness.exe' -Arguments $HArgs | Select-Object -First 1 }
else { V launch 'C:\vmtest\apps\Harness\Harness.exe' | Select-Object -First 1 }
Start-Sleep 4
V run "powershell -NoProfile -STA -ExecutionPolicy Bypass -File C:\vmtest\files\jdrive.ps1 -Steps C:\vmtest\files\$Steps.steps -Out C:\vmtest\rec\$Name.jaws.txt" -Timeout 600 | Select-Object -Last 1
Import-Module "C:\Users\kelly\GitHub\TheWorkBench\audio-demo\tools\VmFiles.psm1" -Force -DisableNameChecking
Copy-FromTestVM "C:\vmtest\rec\$Name.jaws.txt" "$proj\clips\$Name.jaws.txt"
Get-Content "$proj\clips\$Name.jaws.txt" -Encoding UTF8
