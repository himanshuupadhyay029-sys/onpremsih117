# firewall_helper.ps1 — Elevated helper for KAVACH Windows Defender Firewall manipulation.
param(
    [string]$Action = "lockdown",
    [string]$SubnetCidr = "",
    [string]$PriorInbound = "BlockInbound"
)

$RuleNameLocalhost = "KAVACH-Sovereignty-Lockdown-Allow-Localhost"
$RuleNameSubnet = "KAVACH-Sovereignty-Lockdown-Allow-Subnet"

# Auto-register scheduled tasks for silent subsequent runs if elevated
try {
    $scriptPath = $MyInvocation.MyCommand.Path
    $taskLockdown = "KAVACH-Firewall-Lockdown"
    $taskUnlock = "KAVACH-Firewall-Unlock"
    $actionLockdown = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Action lockdown"
    $actionUnlock = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`" -Action unlock"

    schtasks /query /tn "$taskLockdown" 2>$null
    if ($LASTEXITCODE -ne 0) {
        schtasks /create /tn "$taskLockdown" /tr "$actionLockdown" /sc ONCE /st 00:00 /rl HIGHEST /f 2>$null
    }
    schtasks /query /tn "$taskUnlock" 2>$null
    if ($LASTEXITCODE -ne 0) {
        schtasks /create /tn "$taskUnlock" /tr "$actionUnlock" /sc ONCE /st 00:00 /rl HIGHEST /f 2>$null
    }
} catch {
    # Non-fatal if registration fails
}

if ($Action -eq "lockdown") {
    # Detect local subnet if not provided
    if (-not $SubnetCidr) {
        $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" } | Select-Object -First 1).IPAddress
        if ($ip) {
            $parts = $ip.Split('.')
            $SubnetCidr = "$($parts[0]).$($parts[1]).$($parts[2]).0/24"
        } else {
            $SubnetCidr = "192.168.1.0/24"
        }
    }

    # Add localhost allow rule
    & netsh advfirewall firewall add rule name="$RuleNameLocalhost" dir=out action=allow remoteip=127.0.0.1 enable=yes
    # Add subnet allow rule
    & netsh advfirewall firewall add rule name="$RuleNameSubnet" dir=out action=allow remoteip="$SubnetCidr" enable=yes
    # Flip active profile outbound policy to Block
    & netsh advfirewall set currentprofile firewallpolicy "$PriorInbound,blockoutbound"

    Write-Host "[OK] Firewall lockdown enabled."
} elseif ($Action -eq "unlock") {
    # Restore outbound policy to Allow
    & netsh advfirewall set currentprofile firewallpolicy "BlockInbound,AllowOutbound"
    # Delete allow rules
    & netsh advfirewall firewall delete rule name="$RuleNameLocalhost"
    & netsh advfirewall firewall delete rule name="$RuleNameSubnet"

    Write-Host "[OK] Firewall lockdown unlocked."
} else {
    Write-Host "[WARN] Unknown action: $Action"
}
