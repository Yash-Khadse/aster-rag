$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 LTS or newer supported LTS.' }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv sync --frozen --extra evaluation
if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
Push-Location apps/web
try { npm ci; if ($LASTEXITCODE) { throw 'Frontend installation failed' } }
finally { Pop-Location }
Write-Host 'Next: ollama pull qwen2.5:3b; run scripts/start-api.ps1 and npm run dev in apps/web.'
