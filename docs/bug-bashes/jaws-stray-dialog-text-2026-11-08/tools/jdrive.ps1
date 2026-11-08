# Runs IN the VM, in the signed-in session, with JAWS running. Plays a steps file (k, t, w, n-less subset of
# the audio-demo format; x and e lines are skipped here) and records JAWS's exact speech after every key from
# its own speech history, through JAWS's COM API (FreedomSci.JawsApi): ClearSpeechHistory before the key,
# CopySpeechHistoryToClipboard after the waits that follow it. Also records the cable's audio.
#   powershell -STA -File jdrive.ps1 -Steps C:\vmtest\files\x.steps -Out C:\vmtest\rec\x.jaws.txt
param([Parameter(Mandatory)][string]$Steps, [Parameter(Mandatory)][string]$Out, [string]$Wav = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$j = New-Object -ComObject FreedomSci.JawsApi
$lines = Get-Content $Steps -Encoding UTF8
$log = New-Object System.Collections.Generic.List[string]
$rec = $null
if ($Wav) {
    $rec = Start-Process C:\vmtest\files\ffmpeg.exe -ArgumentList "-y -loglevel error -f dshow -i audio=`"CABLE Output (VB-Audio Virtual Cable)`" `"$Wav`"" -PassThru -WindowStyle Hidden -RedirectStandardInput C:\vmtest\rec\ffin.txt
}
$t0 = Get-Date
function Grab {
    [System.Windows.Forms.Clipboard]::Clear()
    $null = $j.RunScript('CopySpeechHistoryToClipboard')
    Start-Sleep -Milliseconds 700
    $s = [System.Windows.Forms.Clipboard]::GetText()
    $null = $j.RunScript('ClearSpeechHistory')
    Start-Sleep -Milliseconds 200
    $s
}
$pending = $null   # the step whose speech is being collected
function Flush {
    if ($null -eq $script:pending) { $null = $j.RunScript('ClearSpeechHistory'); return }
    $speech = Grab
    $script:log.Add($script:pending)
    foreach ($l in ($speech -split "`r?`n")) { if ($l.Trim()) { $script:log.Add("    said: $l") } }
    $script:pending = $null
}
$null = $j.RunScript('ClearSpeechHistory')
$n = 0
foreach ($raw in $lines) {
    $n++
    $line = $raw.TrimEnd()
    if (-not $line -or $line.StartsWith('#')) { continue }
    $op, $arg = $line -split ' ', 2
    switch ($op) {
        'w' { Start-Sleep -Milliseconds ([int]([double]$arg * 1000)) }
        'k' { Flush; $script:pending = ('[{0,6:N1}s] line {1}: key {2}' -f ((Get-Date) - $t0).TotalSeconds, $n, $arg); [System.Windows.Forms.SendKeys]::SendWait($arg) }
        't' { Flush; $script:pending = ('[{0,6:N1}s] line {1}: type {2}' -f ((Get-Date) - $t0).TotalSeconds, $n, $arg)
              foreach ($c in $arg.ToCharArray()) { $k = "$c"; if ('+^%~(){}[]'.Contains($k)) { $k = "{$k}" }; [System.Windows.Forms.SendKeys]::SendWait($k); Start-Sleep -Milliseconds 220 } }
        'j' { Flush; $script:pending = ('[{0,6:N1}s] line {1}: JAWS function {2}' -f ((Get-Date) - $t0).TotalSeconds, $n, $arg); $null = $j.RunFunction($arg) }
        's' { Flush; $script:pending = ('[{0,6:N1}s] line {1}: JAWS script {2}' -f ((Get-Date) - $t0).TotalSeconds, $n, $arg); $null = $j.RunScript($arg) }
        'e' { $log.Add("  expect: $arg") }
        'e!' { $log.Add("  expect not: $arg") }
        default { }
    }
}
Flush
if ($rec) { Stop-Process -Id $rec.Id -Force -ErrorAction SilentlyContinue }
$log | Set-Content -Path $Out -Encoding UTF8
"wrote $Out ($($log.Count) lines)"
