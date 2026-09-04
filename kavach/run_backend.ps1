# run_backend.ps1 — Automated host runner for KAVACH FastAPI Backend

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  KAVACH SOVEREIGN BACKEND RUNNER" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Administrator Elevation Pre-Check
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[WARNING] Not running as Administrator: /shield/firewall/toggle and Windows Firewall lockdown will fail." -ForegroundColor Yellow
    Write-Host "          (To enable hardware firewall lockdown, re-launch PowerShell with 'Run as Administrator')" -ForegroundColor DarkGray
} else {
    Write-Host "[OK] Running with elevated Administrator privileges." -ForegroundColor Green
}

# 2. Virtual Environment Activation
$venvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    Write-Host "[OK] Activated Python virtual environment." -ForegroundColor Green
} else {
    Write-Host "[WARN] .venv not found at $venvActivate; using system Python." -ForegroundColor Yellow
}

# 3. Check and Wait for Postgres Container Health
Write-Host "[INFO] Checking PostgreSQL status on localhost:5433..." -ForegroundColor Cyan
$maxAttempts = 30
$attempt = 0
$dbReady = $false

while (-not $dbReady -and $attempt -lt $maxAttempts) {
    $attempt++
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connectTask = $tcpClient.ConnectAsync("127.0.0.1", 5433)
        if ($connectTask.Wait(1000) -and $tcpClient.Connected) {
            $tcpClient.Close()
            $dbReady = $true
            break
        }
        $tcpClient.Close()
    } catch {
        # ignore connection error while polling
    }
    Write-Host "  Attempt $attempt/${maxAttempts}: Waiting for PostgreSQL container on port 5433..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 1
}

if (-not $dbReady) {
    Write-Host "[ERROR] PostgreSQL not reachable at 127.0.0.1:5433." -ForegroundColor Red
    Write-Host "        Please make sure Docker is running and execute: docker compose up -d postgres" -ForegroundColor Yellow
    exit 1
}
Write-Host "[OK] PostgreSQL is reachable and ready." -ForegroundColor Green

# 4. Run Alembic Database Migrations
Write-Host "[INFO] Applying database migrations (alembic upgrade head)..." -ForegroundColor Cyan
python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Alembic database migration failed." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "[OK] Database schema is up to date." -ForegroundColor Green

# 5. Launch FastAPI Backend Server
Write-Host "[INFO] Starting Uvicorn backend server on http://0.0.0.0:8000..." -ForegroundColor Cyan
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
