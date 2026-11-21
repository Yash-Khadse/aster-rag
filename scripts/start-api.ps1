$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
uv run uvicorn rag_api.main:app --host 127.0.0.1 --port 8000 --reload
exit $LASTEXITCODE
