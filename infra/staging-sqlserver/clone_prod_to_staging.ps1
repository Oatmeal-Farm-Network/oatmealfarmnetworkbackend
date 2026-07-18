<#
.SYNOPSIS
  Clone the prod SQL Server database into the staging Cloud SQL instance.

.DESCRIPTION
  Step 2 of the staging DB setup (see docs/staging/STAGING_CLOUD_SQL_SETUP.md).
  Exports prod `Oatmealailivedb` to the transfer bucket as a .bak, then imports
  it into the staging instance (which creates the database).

  Prod data is pre-launch, so a full clone is acceptable. Re-run with -Refresh
  to drop the existing staging DB first (WIPES staging data).

  After this script, apply post_restore.sql to map the `oatmeal_app` login and
  grant write roles.

.EXAMPLE
  ./clone_prod_to_staging.ps1
  ./clone_prod_to_staging.ps1 -Refresh
#>
param(
    [switch]$Refresh
)

$ErrorActionPreference = "Stop"

$ProdProject     = "animated-flare-421518"
$ProdInstance    = "oatmealailive"
$StagingProject  = "oatmeal-farm-staging"
$StagingInstance = "oatmeal-staging-sqlserver"
$DbName          = "Oatmealailivedb"
$Bucket          = "oatmeal-farm-staging-sql-transfer"

$ts  = Get-Date -Format "yyyyMMdd-HHmmss"
$bak = "gs://$Bucket/$DbName-$ts.bak"

Write-Host ">> Exporting $DbName from prod to $bak" -ForegroundColor Cyan
gcloud sql export bak $ProdInstance $bak `
    --database=$DbName `
    --project=$ProdProject
if ($LASTEXITCODE -ne 0) { throw "Export failed (exit $LASTEXITCODE)" }

if ($Refresh) {
    Write-Host ">> -Refresh set: dropping existing staging DB $DbName" -ForegroundColor Yellow
    gcloud sql databases delete $DbName `
        --instance=$StagingInstance `
        --project=$StagingProject `
        --quiet
    # Ignore failure if the DB does not exist yet.
}

Write-Host ">> Importing into staging $StagingInstance (creates $DbName)" -ForegroundColor Cyan
gcloud sql import bak $StagingInstance $bak `
    --database=$DbName `
    --project=$StagingProject
if ($LASTEXITCODE -ne 0) {
    throw "Import failed (exit $LASTEXITCODE). If this is an edition-feature error, set database_version to SQLSERVER_2022_WEB in Terraform, re-apply, and re-run."
}

Write-Host ">> Clone complete. Next: apply post_restore.sql to grant write access to 'oatmeal_app'." -ForegroundColor Green
