# Apply RankPilot DDL + seed to an existing PostgreSQL database (creates rp_* tables).
# Requires: psql on PATH (PostgreSQL client).
#
# Usage (PowerShell, from repo root or this folder):
#   $env:PGPASSWORD = 'YourPasswordHere'   # e.g. Baguvix1@
#   .\infra\sql\run_migrations.ps1 -Database rankpilot -User postgres
#
param(
    [string]$Database = "rankpilot",
    [string]$User = "postgres",
    [string]$Host = "localhost",
    [int]$Port = 5432
)

$ErrorActionPreference = "Stop"
if (-not $env:PGPASSWORD) {
    Write-Error "Set PGPASSWORD to your PostgreSQL password, then re-run."
}

$root = $PSScriptRoot
$files = @(
    "001_init_seo.sql",
    "002_extensions.sql",
    "003_seed_demo.sql",
    "004_client_password.sql",
    "005_login_username.sql",
    "006_drop_legacy_ai_overview.sql",
    "007_clear_placeholder_content_queue.sql"
)

foreach ($f in $files) {
    $path = Join-Path $root $f
    if (-not (Test-Path $path)) { Write-Error "Missing file: $path" }
    Write-Host ">> $f"
    & psql -h $Host -p $Port -U $User -d $Database -v ON_ERROR_STOP=1 -f $path
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "Done. RankPilot tables should exist on database '$Database'."
