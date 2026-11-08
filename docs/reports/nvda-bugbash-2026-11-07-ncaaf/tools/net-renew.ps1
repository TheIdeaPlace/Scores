# The VM's adapter sometimes comes up with a 169.254 address. Ask DHCP again until it has a real one.
for ($i = 1; $i -le 4; $i++) {
    ipconfig /release | Out-Null
    ipconfig /renew | Out-Null
    Start-Sleep 5
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias Ethernet -ErrorAction SilentlyContinue).IPAddress
    "try ${i}: $ip"
    if ($ip -and -not $ip.StartsWith('169.254')) { break }
    Get-NetAdapter | Restart-NetAdapter -Confirm:$false
    Start-Sleep 10
}
try { (Invoke-WebRequest https://site.api.espn.com/apis/site/v2/sports/football/college-football/news -UseBasicParsing -TimeoutSec 20).StatusCode } catch { "fail: $($_.Exception.Message)" }
