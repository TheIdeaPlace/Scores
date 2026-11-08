# Host side: one JAWS take with exact speech. Reset the app's settings, Notepad behind, launch build <Build>,
# then play steps <Steps> with jdrive.ps1 in the VM and bring back <Name>.jaws.txt.
param([Parameter(Mandatory)][string]$Steps, [Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string]$Build, [int]$Settle = 22)
$ErrorActionPreference = 'Continue'
$proj = 'C:\Users\kelly\OneDrive\testing\Scores\moreaudio\jaws-stray-dialog-text-2026-11-08'
$vt = 'C:\Users\kelly\GitHub\TheWorkBench\vmtest\vmtest.ps1'
function V { powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $vt @args }
Set-Location C:\Users\kelly\GitHub\Scores\.claude\worktrees\agent-a1350ad352800619c
New-Item -ItemType Directory -Force "$proj\clips" | Out-Null
V run -ScriptFile C:\Users\kelly\scratch\jaws-stray\reset.ps1 | Select-Object -Last 1
V push C:\Users\kelly\scratch\jaws-stray\jdrive.ps1 | Out-Null
V push "$proj\steps\$Steps.steps" | Out-Null
V launch notepad.exe | Out-Null
Start-Sleep 2
V launch "C:\vmtest\apps\$Build\Scores.exe" | Select-Object -First 1
Start-Sleep $Settle
V run "powershell -NoProfile -STA -ExecutionPolicy Bypass -File C:\vmtest\files\jdrive.ps1 -Steps C:\vmtest\files\$Steps.steps -Out C:\vmtest\rec\$Name.jaws.txt" -Timeout 880
Import-Module "C:\Users\kelly\GitHub\TheWorkBench\audio-demo\tools\VmFiles.psm1" -Force -DisableNameChecking
Copy-FromTestVM "C:\vmtest\rec\$Name.jaws.txt" "$proj\clips\$Name.jaws.txt"
Get-Content "$proj\clips\$Name.jaws.txt" -Encoding UTF8
