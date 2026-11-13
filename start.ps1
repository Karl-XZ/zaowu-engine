$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runDir = Join-Path $PSScriptRoot '.run'
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
$pythonExe = Join-Path $PSScriptRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    python -m venv backend/.venv
    & $pythonExe -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Create .env from .env.example and configure providers first. Never share .env.'
}
$nodeExe = $null
$nodeCandidates = @(where.exe node 2>$null)
foreach ($candidate in $nodeCandidates) {
    $version = & $candidate --version 2>$null
    if ($LASTEXITCODE -eq 0 -and $version -match '^v\d+') { $nodeExe = $candidate; break }
}
if (-not $nodeExe) { throw 'A working Node.js installation is required.' }
if (-not (Test-Path -LiteralPath 'frontend/node_modules/vite/bin/vite.js')) {
    $npmCli = Join-Path (Split-Path $nodeExe) 'node_modules/npm/bin/npm-cli.js'
    Push-Location frontend
    try { & $nodeExe $npmCli ci --no-audit --no-fund } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
}
if (-not (Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue)) {
    $backendProcess = Start-Process -FilePath $pythonExe -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8010' -WorkingDirectory (Join-Path $PSScriptRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'backend.out.log') -RedirectStandardError (Join-Path $runDir 'backend.err.log') -PassThru
    $backendProcess.Id | Set-Content -LiteralPath (Join-Path $runDir 'backend.pid')
}
if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    $frontendProcess = Start-Process -FilePath $nodeExe -ArgumentList 'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173','--strictPort' -WorkingDirectory (Join-Path $PSScriptRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runDir 'frontend.out.log') -RedirectStandardError (Join-Path $runDir 'frontend.err.log') -PassThru
    $frontendProcess.Id | Set-Content -LiteralPath (Join-Path $runDir 'frontend.pid')
}
Write-Output 'Open http://127.0.0.1:5173/ . Logs are stored in .run/ .'
