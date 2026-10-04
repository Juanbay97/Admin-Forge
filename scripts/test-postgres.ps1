# Own exactly one disposable local PostgreSQL container, including failure cleanup.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $PSScriptRoot
$Docker = 'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
$Python = Join-Path $Root '.venv/Scripts/python.exe'
$ImageFile = Join-Path $PSScriptRoot 'postgres-image.txt'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Create the worktree-local venv first.' }
if (-not (Test-Path -LiteralPath $ImageFile)) { throw 'Official PostgreSQL image digest pin is missing.' }
$Image = ([IO.File]::ReadAllText($ImageFile)).Trim()
if ($Image -notmatch '^postgres@sha256:[a-f0-9]{64}$') { throw 'Invalid official PostgreSQL digest pin.' }
$RunId = [Guid]::NewGuid().ToString('N')
$LocalRoot = Join-Path $Root '.local/postgres-test'
$Config = Join-Path $LocalRoot "docker-$RunId"
New-Item -ItemType Directory -Path $Config -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $Config 'config.json'), '{}', [Text.UTF8Encoding]::new($false))
$DockerOptions = @('--config', $Config, '--host', 'npipe:////./pipe/docker_engine')
$ContainerId = $null
$Result = 1
$Names = @('POSTGRES_PASSWORD', 'FORGE_PG_HARNESS', 'FORGE_PG_PORT', 'FORGE_PG_PASSWORD',
    'DOCKER_CONTEXT', 'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH', 'DOCKER_AUTH_CONFIG',
    'PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE', 'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER',
    'PGPASSWORD', 'PGOPTIONS', 'PGSSLMODE', 'PGTARGETSESSIONATTRS')
$Saved = @{}
foreach ($Name in $Names) { $Saved[$Name] = [Environment]::GetEnvironmentVariable($Name, 'Process') }
try {
    # Do not forward ambient Docker contexts/auth or libpq session settings.
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $null, 'Process') }
    # Inspect only the explicitly pinned public image, never containers or ambient contexts.
    & $Docker @DockerOptions image inspect $Image --format '{{.Id}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Pinned PostgreSQL image is unavailable. Resolve the authorized official image explicitly; normal tests never pull.' }
    $Bytes = New-Object byte[] 32
    $Rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $Rng.GetBytes($Bytes) } finally { $Rng.Dispose() }
    $Password = [Convert]::ToBase64String($Bytes)
    [Environment]::SetEnvironmentVariable('POSTGRES_PASSWORD', $Password, 'Process')
    # -e NAME passes process env without putting its value in command arguments.
    $Created = & $Docker @DockerOptions create --pull=never --name "forge-pg-test-$RunId" `
        --publish '127.0.0.1::5432' --env POSTGRES_PASSWORD --env POSTGRES_DB=forge_test `
        --tmpfs '/var/lib/postgresql/data:rw' $Image 2>$null
    if ($LASTEXITCODE -ne 0 -or "$Created" -notmatch '^[a-f0-9]{64}$') { throw 'Owned PostgreSQL container creation failed; no valid ID was returned.' }
    $ContainerId = "$Created".Trim()
    & $Docker @DockerOptions start $ContainerId *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Owned PostgreSQL container start failed.' }
    $MountsJson = & $Docker @DockerOptions container inspect $ContainerId --format '{{json .Mounts}}'
    if ($LASTEXITCODE -ne 0) { throw 'Owned container mount inspection failed.' }
    # Docker reports tmpfs separately in HostConfig; Mounts must have no volumes/binds.
    $TmpfsJson = & $Docker @DockerOptions container inspect $ContainerId --format '{{json .HostConfig.Tmpfs}}'
    if ($LASTEXITCODE -ne 0) { throw 'Owned container tmpfs inspection failed.' }
    $Tmpfs = ConvertFrom-Json -InputObject "$TmpfsJson"
    $TmpfsProperties = @($Tmpfs.PSObject.Properties)
    if ("$MountsJson".Trim() -ne '[]' -or $TmpfsProperties.Count -ne 1 -or
        $TmpfsProperties[0].Name -ne '/var/lib/postgresql/data' -or
        $TmpfsProperties[0].Value -ne 'rw') {
        throw 'Owned PostgreSQL must use only ephemeral data tmpfs, never host/persistent mounts.'
    }
    $Binding = & $Docker @DockerOptions port $ContainerId 5432/tcp
    if ($LASTEXITCODE -ne 0 -or "$Binding" -notmatch '^127\.0\.0\.1:(\d+)$') { throw 'Owned PostgreSQL container is not bound exclusively to localhost.' }
    [Environment]::SetEnvironmentVariable('FORGE_PG_HARNESS', 'owned-disposable-v1', 'Process')
    [Environment]::SetEnvironmentVariable('FORGE_PG_PORT', $Matches[1], 'Process')
    [Environment]::SetEnvironmentVariable('FORGE_PG_PASSWORD', $Password, 'Process')
    Push-Location $Root
    try {
        & $Python -m unittest discover -s tests -p test_postgres_*.py -v
        $Result = $LASTEXITCODE
    } finally { Pop-Location }
} finally {
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name, $Saved[$Name], 'Process') }
    if ($null -ne $ContainerId) {
        & $Docker @DockerOptions rm --force --volumes $ContainerId *> $null
        if ($LASTEXITCODE -ne 0) { throw 'Exact owned PostgreSQL container cleanup failed; preserve its ID for recovery.' }
        $PriorErrorAction = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $Docker @DockerOptions container inspect $ContainerId *> $null
            $StillExists = ($LASTEXITCODE -eq 0)
        } finally { $ErrorActionPreference = $PriorErrorAction }
        if ($StillExists) { throw 'Owned PostgreSQL container unexpectedly still exists.' }
        Write-Output 'Owned PostgreSQL container removed; exact-ID readback confirms absence.'
    }
    $ResolvedConfig = [IO.Path]::GetFullPath($Config)
    $ResolvedLocal = [IO.Path]::GetFullPath($LocalRoot).TrimEnd('\') + '\'
    if (-not $ResolvedConfig.StartsWith($ResolvedLocal, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing cleanup outside the intended ignored local directory.'
    }
    Remove-Item -LiteralPath $ResolvedConfig -Recurse -Force
}
exit $Result
