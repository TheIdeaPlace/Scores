# Close Scores and put its settings back to a known state before each clip.
# Written without a byte-order mark: Set-Content -Encoding UTF8 adds one, json.load rejects it and the app silently uses defaults.
Get-Process Scores, Notepad, OneDrive, OneDriveSetup, msedge -ErrorAction SilentlyContinue | Stop-Process -Force
# Windows' own toasts (OneDrive backup, updates) take focus mid-clip. Turn them off for this user.
$push = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\PushNotifications'
if (-not (Test-Path $push)) { New-Item -Path $push | Out-Null }
Set-ItemProperty -Path $push -Name ToastEnabled -Value 0 -Type DWord
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name OneDrive -ErrorAction SilentlyContinue
# Dismiss any toast or system dialog already showing.
Add-Type -AssemblyName UIAutomationClient -ErrorAction SilentlyContinue
$root = [System.Windows.Automation.AutomationElement]::RootElement
foreach ($w in $root.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    $name = $w.Current.Name
    if ($name -like 'New notification*' -or $name -like "We've got an update*") {
        try { ($w.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)).Close(); "closed: $name" }
        catch {
            # A toast has no window pattern: its own Dismiss button does it.
            $btn = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
                (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, 'Dismiss')))
            if ($btn) { ($btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)).Invoke(); "dismissed: $name" } else { "couldn't close: $name" }
        }
    }
}
Start-Sleep 1
$dir = Join-Path $env:APPDATA 'Scores'
New-Item -ItemType Directory -Force $dir | Out-Null
[IO.File]::WriteAllText((Join-Path $dir 'settings.json'), '{"auto_check_updates": false, "default_view_mode": 0, "favorites": [], "sport_order": [], "sport_visibility": {}}')
