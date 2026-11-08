# Over PowerShell Direct: restart the shell hosts that show toasts, which can stop answering UI Automation.
Import-Module 'C:\Users\kelly\GitHub\TheWorkBench\audio-demo\tools\VmFiles.psm1' -Force
Invoke-InTestVM -Script @'
foreach ($name in 'ShellExperienceHost', 'StartMenuExperienceHost', 'SearchHost', 'Widgets', 'OneDrive', 'msedge') {
    Get-Process $name -ErrorAction SilentlyContinue | ForEach-Object { "stopping $($_.Name) $($_.Id) responding=$($_.Responding)"; Stop-Process -Id $_.Id -Force }
}
Get-Process | Where-Object { -not $_.Responding } | ForEach-Object { "not responding: $($_.Name) $($_.Id)" }
'@
