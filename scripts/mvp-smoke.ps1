# MVP acceptance smoke, loopback only, in real system Chrome:
#   1. builds the admin web and starts the owned local stack (PostgreSQL 17 in a disposable container,
#      two-organization seed, fake gateway on 3413, control plane + /admin on 3410);
#   2. admin flow (admin/e2e): sign in to /admin, invite a member, save the gateway key, publish the catalog;
#   3. starts the client through its single sanctioned launcher (production `next build` + `next start`,
#      UI 3411, workspace backend 3412) in a private data directory;
#   4. client flow (clients/openyak frontend e2e): the invited member activates the account in /onboarding,
#      signs in, sees only the published models, chats through client backend -> control plane -> fake gateway,
#      no gateway key or host reaches the browser, and an organization B member cannot enter or read it.
# Everything it starts is stopped and removed at the end (container, private workspace, client data directory).
# It only ever stops process trees it started itself (by PID); it never touches the retained demo ports or any other process.
[CmdletBinding()]
param(
    [int]$BuildTimeoutSeconds = 180,
    [int]$StackStartTimeoutSeconds = 240,
    [int]$ClientStartTimeoutSeconds = 1200,
    [int]$AdminTestTimeoutSeconds = 300,
    [int]$ClientTestTimeoutSeconds = 300,
    [int]$StopTimeoutSeconds = 90,
    [string]$ClientRoot = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$admin = Join-Path $root 'admin'
$python = Join-Path $root '.venv/Scripts/python.exe'
if ([string]::IsNullOrEmpty($ClientRoot)) { $ClientRoot = Join-Path $root '..\..\clients\openyak' }
$client = [IO.Path]::GetFullPath($ClientRoot)
$frontend = Join-Path $client 'frontend'
$mailboxInvitee = 'nina.newcomer@forge.local.test'   # invited through the admin web by admin/e2e/admin-flow.spec.ts
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'LOCAL_VENV_REQUIRED' }
if (-not (Test-Path -LiteralPath (Join-Path $admin 'node_modules') -PathType Container)) { throw 'ADMIN_DEPENDENCIES_REQUIRED: run npm ci in admin' }
if (-not (Test-Path -LiteralPath (Join-Path $client 'scripts/forge-managed.mjs') -PathType Leaf)) { throw 'CLIENT_CHECKOUT_REQUIRED: pass -ClientRoot' }
foreach ($required in @('frontend/node_modules', 'backend/.venv')) {
    if (-not (Test-Path -LiteralPath (Join-Path $client $required) -PathType Container)) { throw "CLIENT_DEPENDENCIES_REQUIRED: $required" }
}

function Stop-Tree([System.Diagnostics.Process]$Process) {
    if (-not $Process.HasExited) { & taskkill.exe /PID $Process.Id /T /F | Out-Null }
}

function Invoke-Bounded([string]$File, [string]$Arguments, [string]$WorkingDirectory, [int]$TimeoutSeconds) {
    $info = [Diagnostics.ProcessStartInfo]::new($File)
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.Arguments = $Arguments
    $process = [Diagnostics.Process]::Start($info)
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Tree $process
            throw "TIMEOUT: $([IO.Path]::GetFileName($File)) $Arguments exceeded $TimeoutSeconds s"
        }
        return $process.ExitCode
    } finally { $process.Dispose() }
}

# Reads one JSON line at a time until $Match returns a document, the stream ends or the deadline passes.
function Wait-Line($Reader, [scriptblock]$Match, [int]$TimeoutSeconds, [string]$What) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $line = $Reader.ReadLineAsync()
    while ($true) {
        if ([DateTime]::UtcNow -gt $deadline) { throw "TIMEOUT: $What did not become ready" }
        if (-not $line.IsCompleted) { Start-Sleep -Milliseconds 100; continue }
        $text = $line.GetAwaiter().GetResult()
        if ($null -eq $text) { throw "EXITED_BEFORE_READY: $What" }
        $document = $null
        try { $document = $text | ConvertFrom-Json } catch { }
        if ($null -ne $document -and (& $Match $document)) { return $document }
        $line = $Reader.ReadLineAsync()
    }
}

function New-Child([string]$File, [string]$Arguments, [string]$WorkingDirectory, [bool]$CleanEnvironment) {
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $File
    $info.WorkingDirectory = $WorkingDirectory
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    if ($CleanEnvironment) {
        # OS plumbing by name only, never ambient credentials or PG* variables.
        $info.EnvironmentVariables.Clear()
        foreach ($name in @('SystemRoot', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATH', 'PATHEXT')) {
            $value = [Environment]::GetEnvironmentVariable($name, 'Process')
            if ($null -ne $value) { $info.EnvironmentVariables[$name] = $value }
        }
        $info.EnvironmentVariables['PYTHONPATH'] = Join-Path $root 'src'
        $info.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
        $info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
    }
    $info.Arguments = $Arguments
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    return $process
}

function Stop-Child([System.Diagnostics.Process]$Process, $Reader, [int]$TimeoutSeconds) {
    if ($Process.HasExited) { return $null }
    $Process.StandardInput.WriteLine('stop')
    $Process.StandardInput.Close()
    $stopped = $null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $line = $Reader.ReadLineAsync()
    while ($null -ne $line -and [DateTime]::UtcNow -lt $deadline) {
        if (-not $line.IsCompleted) { Start-Sleep -Milliseconds 100; continue }
        $text = $line.GetAwaiter().GetResult()
        if ($null -eq $text) { break }
        try { $document = $text | ConvertFrom-Json; if ($document.status -eq 'stopped') { $stopped = $document } } catch { }
        $line = $Reader.ReadLineAsync()
    }
    if (-not $Process.WaitForExit(5000)) {
        Stop-Tree $Process   # the exact process tree this script started, nothing else
        Write-Warning 'OWNED_CLEANUP_PENDING: a child had to be force-stopped by PID.'
    }
    return $stopped
}

# Docker Desktop (containerd store) can fail `image inspect` by digest until the image is used once; the owned
# stack requires that inspection to succeed. A throwaway --rm container warms it and never pulls anything.
$image = (Get-Content -LiteralPath (Join-Path $root 'scripts/postgres-image.txt') -Raw).Trim()
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& docker.exe run --rm --pull never --entrypoint postgres $image --version 2>&1 | Out-Null
$ErrorActionPreference = $previous

$npm = (Get-Command npm.cmd).Source
$npx = (Get-Command npx.cmd).Source
$node = (Get-Command node.exe).Source

Write-Output 'mvp-smoke: building the admin web'
if ((Invoke-Bounded $npm 'run build' $admin $BuildTimeoutSeconds) -ne 0) { throw 'ADMIN_BUILD_FAILED' }

$stack = New-Child $python '-B -u -m forge.mvp_local up --supervised --require-admin-build' $root $true
$stackStarted = $false
$clientProcess = $null
$clientStarted = $false
$clientData = Join-Path ([IO.Path]::GetTempPath()) ('forge-managed-client-' + [Guid]::NewGuid().ToString('N'))
$result = 1
$stackStopped = $null
try {
    $stackStarted = $stack.Start()
    $null = $stack.StandardError.ReadToEndAsync()   # diagnostics stay private; drained so the child never blocks
    $ready = Wait-Line $stack.StandardOutput { param($d) $d.status -eq 'ready' } $StackStartTimeoutSeconds 'the local stack'
    Write-Output "mvp-smoke: stack ready at $($ready.admin_url)"

    $env:FORGE_E2E_ADMIN_URL = $ready.control_plane_origin
    $env:FORGE_E2E_CREDENTIALS = $ready.credentials_file
    Write-Output 'mvp-smoke: admin flow (sign in, invite, gateway key, publish) in Chrome'
    $adminResult = Invoke-Bounded $npm 'run test:e2e' $admin $AdminTestTimeoutSeconds
    Remove-Item Env:FORGE_E2E_ADMIN_URL, Env:FORGE_E2E_CREDENTIALS -ErrorAction SilentlyContinue
    if ($adminResult -ne 0) { throw 'ADMIN_FLOW_FAILED' }

    Write-Output 'mvp-smoke: starting the managed client (production build; this takes a few minutes)'
    New-Item -ItemType Directory -Path $clientData | Out-Null
    $launcher = '"' + (Join-Path $client 'scripts/forge-managed.mjs') + '" --control-plane-origin ' + $ready.control_plane_origin +
        ' --data-dir "' + $clientData + '"'
    $clientProcess = New-Child $node $launcher $client $false
    $clientStarted = $clientProcess.Start()
    $null = $clientProcess.StandardError.ReadToEndAsync()
    $clientReady = Wait-Line $clientProcess.StandardOutput { param($d) $d.stage -eq 'ready' } $ClientStartTimeoutSeconds 'the managed client'
    Write-Output "mvp-smoke: client ready at $($clientReady.url)"

    $env:FORGE_E2E_CLIENT_URL = $ready.client_origin
    $env:FORGE_E2E_CONTROL_PLANE_ORIGIN = $ready.control_plane_origin
    $env:FORGE_E2E_CREDENTIALS = $ready.credentials_file
    $env:FORGE_E2E_MAILBOX = Join-Path $ready.workspace 'mailbox'
    $env:FORGE_E2E_INVITEE_EMAIL = $mailboxInvitee
    Write-Output 'mvp-smoke: client flow (onboarding, sign-in, streamed chat, isolation) in Chrome'
    $result = Invoke-Bounded $npx 'playwright test -c playwright.forge-managed-flow.config.ts' $frontend $ClientTestTimeoutSeconds
} finally {
    Remove-Item Env:FORGE_E2E_ADMIN_URL, Env:FORGE_E2E_CLIENT_URL, Env:FORGE_E2E_CONTROL_PLANE_ORIGIN, Env:FORGE_E2E_CREDENTIALS,
        Env:FORGE_E2E_MAILBOX, Env:FORGE_E2E_INVITEE_EMAIL -ErrorAction SilentlyContinue
    if ($clientStarted) { $null = Stop-Child $clientProcess $clientProcess.StandardOutput $StopTimeoutSeconds }
    if ($null -ne $clientProcess) { $clientProcess.Dispose() }
    if (Test-Path -LiteralPath $clientData) { Remove-Item -LiteralPath $clientData -Recurse -Force -ErrorAction SilentlyContinue }
    if ($stackStarted) { $stackStopped = Stop-Child $stack $stack.StandardOutput $StopTimeoutSeconds }
    $stack.Dispose()
}
if ($stackStarted -and ($null -eq $stackStopped -or -not $stackStopped.owned_container_absent -or -not $stackStopped.private_workspace_absent)) {
    Write-Warning 'mvp-smoke: clean stop of the owned stack was not confirmed'
    exit 1
}
Write-Output 'mvp-smoke: owned container, private workspace and client data directory removed'
if ($result -eq 0) { Write-Output 'mvp-smoke: PASS' } else { Write-Output 'mvp-smoke: FAIL' }
exit $result
