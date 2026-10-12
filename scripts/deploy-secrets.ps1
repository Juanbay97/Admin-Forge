<#
.SYNOPSIS
  Generate the deployment secrets once (PowerShell twin of deploy-secrets.sh).
.DESCRIPTION
  Idempotent: an existing file is never overwritten, because rotating a Fernet key would orphan stored data.
  Prints names only, never values.
#>
param([string]$Directory = (Join-Path $PSScriptRoot '..\deploy\secrets'))

$ErrorActionPreference = 'Stop'
$null = New-Item -ItemType Directory -Force -Path $Directory
$Directory = (Resolve-Path $Directory).Path
$random = [System.Security.Cryptography.RandomNumberGenerator]::Create()

function New-Bytes([int]$Count) {
    $buffer = New-Object byte[] $Count
    $random.GetBytes($buffer)
    return $buffer
}

function New-Password {
    $text = [Convert]::ToBase64String((New-Bytes 48)) -replace '[=+/]', ''
    return $text.Substring(0, 40)
}

# A Fernet key is 32 random bytes, urlsafe base64 (44 characters with padding).
function New-FernetKey {
    return ([Convert]::ToBase64String((New-Bytes 32))).Replace('+', '-').Replace('/', '_')
}

function Save-Secret([string]$Name, [scriptblock]$Generator) {
    $target = Join-Path $Directory $Name
    if (Test-Path -LiteralPath $target) {
        Write-Host "kept     $Name"
        return
    }
    $value = (& $Generator) + "`n"
    $stream = [System.IO.File]::Open($target, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try {
        $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes($value)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally {
        $stream.Dispose()
    }
    Write-Host "created  $Name"
}

foreach ($name in 'pg_superuser', 'role_forge_account_service', 'role_forge_enrollment', 'role_forge_runtime',
                  'role_forge_gateway_service', 'role_forge_branding_service', 'role_backup') {
    Save-Secret $name { New-Password }
}
Save-Secret 'delivery_key' { New-FernetKey }
Save-Secret 'gateway_key' { New-FernetKey }

Write-Host "secrets directory: $Directory"
Write-Host 'Back it up OFFLINE: losing delivery_key/gateway_key makes stored gateway keys and queued messages unrecoverable.'
