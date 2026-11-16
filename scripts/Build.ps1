$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .venv/Scripts/python.exe scripts/build.py
if ($LASTEXITCODE -ne 0) { throw 'Build or release verification failed.' }
