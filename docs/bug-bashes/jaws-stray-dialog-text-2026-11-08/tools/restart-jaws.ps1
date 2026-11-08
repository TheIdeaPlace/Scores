# Host side: restart JAWS in the VM (resets its 40-minute demo timer) and dismiss its start-up windows.
$vt = 'C:\Users\kelly\GitHub\TheWorkBench\vmtest\vmtest.ps1'
function V { powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $vt @args }
Set-Location C:\Users\kelly\GitHub\Scores\.claude\worktrees\agent-a1350ad352800619c
V run -ScriptFile C:\Users\kelly\scratch\jaws-stray\kill-jaws.ps1 -Elevated | Select-Object -Last 2
V launch 'C:\Program Files\Freedom Scientific\JAWS\2027\jfw.exe' 2>&1 | Out-Null
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep 5
    $w = V windows 2>&1 | Out-String
    if ($w -match 'JAWS Activation') { V invoke 'id:2' -Window 'JAWS Activation' -Elevated | Out-Null; continue }
    if ($w -match 'Account Sign In') { V close -Window 'Account Sign In' -Elevated | Out-Null; continue }
    if ($w -match 'Vispero Error Reporting') { V close -Window 'Vispero Error Reporting' -Elevated | Out-Null; continue }
    if ($w -match 'JAWS Professional' -and $i -ge 3) { break }
}
V windows
