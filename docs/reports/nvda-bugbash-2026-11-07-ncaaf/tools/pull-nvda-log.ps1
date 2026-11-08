# Copy NVDA's log out of the VM, for speech from a clip that was stopped before it saved its own.
# NVDA holds the log open, so it's copied inside the VM first.
param([Parameter(Mandatory)][string]$Destination)
Import-Module 'C:\Users\kelly\GitHub\TheWorkBench\audio-demo\tools\VmFiles.psm1' -Force
Invoke-InTestVM -Script @'
$src = [IO.File]::Open('C:\vmtest\rec\nvda.log', 'Open', 'Read', 'ReadWrite')
try { $dst = [IO.File]::Create('C:\vmtest\rec\nvda-copy.log'); $src.CopyTo($dst); $dst.Close() } finally { $src.Close() }
(Get-Item 'C:\vmtest\rec\nvda-copy.log').Length
'@
Copy-FromTestVM -Source 'C:\vmtest\rec\nvda-copy.log' -Destination $Destination
if (Test-Path $Destination) { "copied to $Destination" } else { "not copied" }
