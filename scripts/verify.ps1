$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:DEEPEVAL_TELEMETRY_OPT_OUT = 'YES'
uv run --extra evaluation pytest tests -q
if ($LASTEXITCODE) { throw 'Python tests failed' }
Push-Location apps/web
try {
  foreach ($task in @('lint','typecheck','test','build')) { npm run $task; if ($LASTEXITCODE) { throw "Frontend $task failed" } }
} finally { Pop-Location }
