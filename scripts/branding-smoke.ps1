# White-label acceptance smoke, loopback only, in real system Chrome, on the real stack:
#   1. builds the admin web and starts the owned local stack exactly as `mvp_local up` seeds it (PostgreSQL 17 in a
#      disposable container, two organizations each with its own branding, fake gateway on 3413, control plane + /admin
#      on 3410);
#   2. starts the client through its single sanctioned launcher (production `next build` + `next start`, UI 3411,
#      workspace backend 3412) in a private data directory;
#   3. client, seeded organizations (client playwright.forge-branding-orgs.config.ts): the two organizations look
#      different before sign-in, in the workspace and when one member of both switches; the content security policy
#      is sent and nothing violates it. Read-only: it must run before anything edits the seeded brands;
#   4. admin (admin/e2e/branding.spec.ts): both organizations are branded in /admin and an administrator re-brands,
#      resets and hits a stale revision against the real server, with no CSP violation;
#   5. client, administrator-set branding (client playwright.forge-branding.config.ts): the company-code gate, the
#      remembered brand, the offline cache and the switch of company, using branding saved through the real API;
#   6. neither repository may end the run with a tracked or untracked change it did not have at the start, and the
#      four MVP ports must be free again.
# Everything it starts is stopped and removed at the end (container, private workspace, client data directory).
# It only ever stops process trees it started itself (by PID); it never touches the retained demo ports or any other
# process. mvp-smoke.ps1 stays untouched; the process helpers below are a deliberate copy of its own.
[CmdletBinding()]
param(
    [int]$BuildTimeoutSeconds = 180,
    [int]$StackStartTimeoutSeconds = 240,
    [int]$ClientStartTimeoutSeconds = 1200,
    [int]$AdminTestTimeoutSeconds = 300,
    [int]$ClientTestTimeoutSeconds = 300,
    [int]$GateTestTimeoutSeconds = 600,
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
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'LOCAL_VENV_REQUIRED' }
if (-not (Test-Path -LiteralPath (Join-Path $admin 'node_modules') -PathType Container)) { throw 'ADMIN_DEPENDENCIES_REQUIRED: run npm ci in admin' }
if (-not (Test-Path -LiteralPath (Join-Path $client 'scripts/forge-managed.mjs') -PathType Leaf)) { throw 'CLIENT_CHECKOUT_REQUIRED: pass -ClientRoot' }
foreach ($required in @('frontend/node_modules', 'backend/.venv')) {
    if (-not (Test-Path -LiteralPath (Join-Path $client $required) -PathType Container)) { throw "CLIENT_DEPENDENCIES_REQUIRED: $required" }
}

# `git status --porcelain` lines of one repository: what a run must leave exactly as it found it.
function Get-TreeState([string]$Repository) {
    $lines = & git.exe -C $Repository status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "GIT_STATUS_FAILED: $Repository" }
    return @($lines | Where-Object { $_ })
}

# Names every file the run changed (modified, created or removed) in either repository.
function Get-TreeChanges($Before, $After) {
    $changes = @()
    foreach ($name in $Before.Keys) {
        foreach ($difference in @(Compare-Object -ReferenceObject $Before[$name] -DifferenceObject $After[$name])) {
            $changes += ('{0}: {1}' -f $name, ([string]$difference.InputObject).Trim())
        }
    }
    return $changes
}

# The four MVP ports (control plane, client UI, client backend, fake gateway) must be free once everything stopped.
function Get-OccupiedPorts([int[]]$Ports) {
    $occupied = @()
    foreach ($port in $Ports) {
        $listener = $null
        try {
            $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
            $listener.Start()
        } catch { $occupied += $port } finally { if ($null -ne $listener) { $listener.Stop() } }
    }
    return $occupied
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

$treeBefore = @{ 'control plane' = (Get-TreeState $root); 'client' = (Get-TreeState $client) }

$npm = (Get-Command npm.cmd).Source
$npx = (Get-Command npx.cmd).Source
$node = (Get-Command node.exe).Source

Write-Output 'branding-smoke: building the admin web'
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
    Write-Output "branding-smoke: stack ready at $($ready.admin_url)"

    Write-Output 'branding-smoke: starting the managed client (production build; this takes a few minutes)'
    New-Item -ItemType Directory -Path $clientData | Out-Null
    $launcher = '"' + (Join-Path $client 'scripts/forge-managed.mjs') + '" --control-plane-origin ' + $ready.control_plane_origin +
        ' --data-dir "' + $clientData + '"'
    $clientProcess = New-Child $node $launcher $client $false
    $clientStarted = $clientProcess.Start()
    $null = $clientProcess.StandardError.ReadToEndAsync()
    $clientReady = Wait-Line $clientProcess.StandardOutput { param($d) $d.stage -eq 'ready' } $ClientStartTimeoutSeconds 'the managed client'
    Write-Output "branding-smoke: client ready at $($clientReady.url)"

    $env:FORGE_E2E_CLIENT_URL = $ready.client_origin
    $env:FORGE_E2E_CONTROL_PLANE_ORIGIN = $ready.control_plane_origin
    $env:FORGE_E2E_CREDENTIALS = $ready.credentials_file
    $env:FORGE_E2E_CLIENT_DATA = $clientData
    Write-Output 'branding-smoke: client, two seeded organizations (gate, brand before and after sign-in, switching, CSP) in Chrome'
    $result = Invoke-Bounded $npx 'playwright test -c playwright.forge-branding-orgs.config.ts' $frontend $ClientTestTimeoutSeconds
    if ($result -eq 0) {
        $env:FORGE_E2E_ADMIN_URL = $ready.control_plane_origin
        Write-Output 'branding-smoke: admin branding (seed, edit, logo, reset, conflict, hostile input, CSP) in Chrome'
        $result = Invoke-Bounded $npx 'playwright test -c playwright.config.ts branding.spec.ts' $admin $AdminTestTimeoutSeconds
        Remove-Item Env:FORGE_E2E_ADMIN_URL -ErrorAction SilentlyContinue
    }
    if ($result -eq 0) {
        Write-Output 'branding-smoke: client, administrator-set branding (code gate, cache, offline, company switch) in Chrome'
        $result = Invoke-Bounded $npx 'playwright test -c playwright.forge-branding.config.ts' $frontend $GateTestTimeoutSeconds
    }
} finally {
    Remove-Item Env:FORGE_E2E_ADMIN_URL, Env:FORGE_E2E_CLIENT_URL, Env:FORGE_E2E_CONTROL_PLANE_ORIGIN, Env:FORGE_E2E_CREDENTIALS,
        Env:FORGE_E2E_CLIENT_DATA -ErrorAction SilentlyContinue
    if ($clientStarted) { $null = Stop-Child $clientProcess $clientProcess.StandardOutput $StopTimeoutSeconds }
    if ($null -ne $clientProcess) { $clientProcess.Dispose() }
    if (Test-Path -LiteralPath $clientData) { Remove-Item -LiteralPath $clientData -Recurse -Force -ErrorAction SilentlyContinue }
    if ($stackStarted) { $stackStopped = Stop-Child $stack $stack.StandardOutput $StopTimeoutSeconds }
    $stack.Dispose()
}
if ($stackStarted -and ($null -eq $stackStopped -or -not $stackStopped.owned_container_absent -or -not $stackStopped.private_workspace_absent)) {
    Write-Warning 'branding-smoke: clean stop of the owned stack was not confirmed'
    exit 1
}
Write-Output 'branding-smoke: owned container, private workspace and client data directory removed'
$treeAfter = @{ 'control plane' = (Get-TreeState $root); 'client' = (Get-TreeState $client) }
$dirty = @(Get-TreeChanges $treeBefore $treeAfter)
if ($dirty.Count -gt 0) {
    foreach ($line in $dirty) { Write-Warning "branding-smoke: TREE_DIRTY the run changed $line" }
    $result = 1
} else { Write-Output 'branding-smoke: both repositories are exactly as the run found them' }
$stillOpen = @()
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $stillOpen = @(Get-OccupiedPorts @(3410, 3411, 3412, 3413))
    if ($stillOpen.Count -eq 0) { break }
    Start-Sleep -Milliseconds 500
}
if ($stillOpen.Count -gt 0) {
    Write-Warning ('branding-smoke: PORTS_NOT_FREED ' + ($stillOpen -join ', '))
    $result = 1
} else { Write-Output 'branding-smoke: ports 3410-3413 are free' }
if ($result -eq 0) { Write-Output 'branding-smoke: PASS' } else { Write-Output 'branding-smoke: FAIL' }
exit $result
