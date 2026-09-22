# setup_firewall_permissions.ps1 — Registers on-demand highest-privilege scheduled tasks
# for KAVACH so standard non-admin Uvicorn processes can toggle Windows Defender Firewall.

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  KAVACH FIREWALL PERMISSION SETUP" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$helperPath = Join-Path $PSScriptRoot "firewall_helper.ps1"
if (-not (Test-Path $helperPath)) {
    Write-Host "[ERROR] Could not find firewall_helper.ps1 at $helperPath" -ForegroundColor Red
    exit 1
}

$taskLockdown = "KAVACH-Firewall-Lockdown"
$taskUnlock = "KAVACH-Firewall-Unlock"

$actionLockdown = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$helperPath`" -Action lockdown"
$actionUnlock = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$helperPath`" -Action unlock"

Write-Host "[INFO] Registering '$taskLockdown'..." -ForegroundColor Cyan
schtasks /create /tn "$taskLockdown" /tr "$actionLockdown" /sc ONCE /st 00:00 /rl HIGHEST /f

Write-Host "[INFO] Registering '$taskUnlock'..." -ForegroundColor Cyan
schtasks /create /tn "$taskUnlock" /tr "$actionUnlock" /sc ONCE /st 00:00 /rl HIGHEST /f

Write-Host "[OK] Permanent permission tasks registered successfully!" -ForegroundColor Green
Write-Host "     You can now launch the Uvicorn backend without Administrator elevation," -ForegroundColor Green
Write-Host "     and UI Lockdown toggles will execute silently with full firewall control." -ForegroundColor Green
