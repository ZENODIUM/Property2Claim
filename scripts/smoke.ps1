$ErrorActionPreference = "Stop"
$workspacePath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspacePath ".venv\Scripts\python.exe"
$backendPath = Join-Path $workspacePath "backend"
$frontendPath = Join-Path $workspacePath "frontend"
$nextPath = Join-Path $frontendPath "node_modules\next\dist\bin\next"
$backendOut = Join-Path $workspacePath ".smoke-backend.log"
$backendErr = Join-Path $workspacePath ".smoke-backend-error.log"
$frontendOut = Join-Path $workspacePath ".smoke-frontend.log"
$frontendErr = Join-Path $workspacePath ".smoke-frontend-error.log"

$backendProcess = Start-Process -FilePath $pythonPath -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010" -WorkingDirectory $backendPath -WindowStyle Hidden -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -PassThru
$frontendProcess = Start-Process -FilePath "node.exe" -ArgumentList $nextPath, "start", "-p", "3010" -WorkingDirectory $frontendPath -WindowStyle Hidden -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr -PassThru

try {
    $apiReady = $false
    $webReady = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8010/api/health" -TimeoutSec 2
            if ($health.status -eq "ok") { $apiReady = $true }
        } catch { }
        try {
            $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:3010" -TimeoutSec 2
            if ($page.StatusCode -eq 200) { $webReady = $true }
        } catch { }
        if ($apiReady -and $webReady) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $apiReady -or -not $webReady) {
        $backendLog = (Get-Content -Raw -ErrorAction SilentlyContinue $backendErr) + (Get-Content -Raw -ErrorAction SilentlyContinue $backendOut)
        $frontendLog = (Get-Content -Raw -ErrorAction SilentlyContinue $frontendErr) + (Get-Content -Raw -ErrorAction SilentlyContinue $frontendOut)
        throw "Smoke readiness failed: api=$apiReady frontend=$webReady backend=$backendLog frontend=$frontendLog"
    }
    $overview = Invoke-RestMethod -Uri "http://127.0.0.1:8010/api/overview" -TimeoutSec 5
    [ordered]@{
        api_status = $health.status
        frontend_status = $page.StatusCode
        companies = $overview.companies
        properties = $overview.properties
        open_claims = $overview.open_claims
        synthetic_only = $health.synthetic_only
    } | ConvertTo-Json -Compress
} finally {
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id -Force }
    if (-not $frontendProcess.HasExited) { Stop-Process -Id $frontendProcess.Id -Force }
}
