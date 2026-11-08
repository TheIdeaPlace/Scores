# Runs in the VM, elevated: silent install of JAWS from the web installer pushed to C:\vmtest\files.
$ErrorActionPreference = 'Stop'
$exe = Get-ChildItem C:\vmtest\files\J20*.exe | Where-Object { $_.Name -notmatch 'Offline' } | Select-Object -First 1
if (-not $exe) { throw 'No JAWS installer in C:\vmtest\files' }
$p = Start-Process $exe.FullName -ArgumentList '/Type silent' -Wait -PassThru
'installer exit {0} (0x{0:X8})' -f $p.ExitCode
Get-ChildItem 'C:\Program Files\Freedom Scientific\JAWS' -ErrorAction SilentlyContinue | ForEach-Object { "JAWS folder: $($_.FullName)" }
$log = Get-ChildItem "$env:TEMP\J20*\Setup_*.log", C:\Users\vmuser\AppData\Local\Temp\J20*\Setup_*.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($log) { Get-Content $log.FullName | Select-String 'e000|Exit code' | Select-Object -Last 8 | ForEach-Object Line }
