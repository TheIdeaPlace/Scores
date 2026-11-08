# Host side: reboot the VM (JAWS's 40-minute demo needs a restart of Windows) and start JAWS again.
$vt = 'C:\Users\kelly\GitHub\TheWorkBench\vmtest\vmtest.ps1'
function V { powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $vt @args }
Set-Location C:\Users\kelly\GitHub\Scores\.claude\worktrees\agent-a1350ad352800619c
V run "shutdown /r /t 2" -Elevated | Out-Null
Start-Sleep 75
for ($i = 0; $i -lt 20; $i++) {
    $r = V windows 2>&1 | Out-String
    if ($r -notmatch 'failed') { break }
    Start-Sleep 10
}
V run -ScriptFile C:\Users\kelly\scratch\jaws-stray\quiet-vm.ps1 2>&1 | Select-Object -Last 1
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\kelly\scratch\jaws-stray\restart-jaws.ps1
