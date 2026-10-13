# Admin end-to-end: builds the admin web, starts the owned local stack (PostgreSQL 17 in a disposable
# container, two-organization seed, fake gateway on 3413, control plane + /admin on 3410), runs the real
# Playwright flow in system Chrome against it, then asks the stack to stop and confirms that the owned
# container and private workspace are gone. Loopback only; never touches 3319/3320/3331/3332 or any
# process it did not start. Every wait is bounded.
[CmdletBinding()]
param(
    [int]$BuildTimeoutSeconds = 180,
    [int]$StartTimeoutSeconds = 240,
    [int]$TestTimeoutSeconds = 1500,
    [int]$StopTimeoutSeconds = 90,
    # Optional Playwright file filter (e.g. "platform-"), so one area can be re-run against a fresh stack.
    [string]$Spec = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$admin = Join-Path $root 'admin'
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'LOCAL_VENV_REQUIRED' }
if (-not (Test-Path -LiteralPath (Join-Path $admin 'node_modules') -PathType Container)) { throw 'ADMIN_DEPENDENCIES_REQUIRED: run npm ci in admin' }

function Stop-Tree([System.Diagnostics.Process]$Process) {
    if (-not $Process.HasExited) { & taskkill.exe /PID $Process.Id /T /F | Out-Null }
}

function Invoke-Npm([string[]]$Arguments, [int]$TimeoutSeconds) {
    $info = [Diagnostics.ProcessStartInfo]::new((Get-Command npm.cmd).Source)
    $info.WorkingDirectory = $admin
    $info.UseShellExecute = $false
    $info.Arguments = $Arguments -join ' '
    $process = [Diagnostics.Process]::Start($info)
    try {
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Tree $process
            throw "TIMEOUT: npm $($info.Arguments) exceeded $TimeoutSeconds s"
        }
        return $process.ExitCode
    } finally { $process.Dispose() }
}

Write-Output 'admin-e2e: building the admin web'
if ((Invoke-Npm @('run', 'build') $BuildTimeoutSeconds) -ne 0) { throw 'ADMIN_BUILD_FAILED' }

# Same clean environment as scripts/mvp-local.ps1: OS plumbing by name only, no ambient credentials or PG* variables.
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName = $python
$info.WorkingDirectory = $root
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardInput = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$info.EnvironmentVariables.Clear()
foreach ($name in @('SystemRoot', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATH', 'PATHEXT')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ($null -ne $value) { $info.EnvironmentVariables[$name] = $value }
}
$info.EnvironmentVariables['PYTHONPATH'] = Join-Path $root 'src'
$info.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
$info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
$info.Arguments = '-B -u -m forge.mvp_local up --supervised --require-admin-build'
$stack = [Diagnostics.Process]::new()
$stack.StartInfo = $info
$started = $false
$result = 1
$stopped = $null
try {
    $started = $stack.Start()
    $null = $stack.StandardError.ReadToEndAsync()  # diagnostics stay private; drained so the child never blocks
    $line = $stack.StandardOutput.ReadLineAsync()
    $deadline = [DateTime]::UtcNow.AddSeconds($StartTimeoutSeconds)
    $ready = $null
    while ($null -eq $ready) {
        if ([DateTime]::UtcNow -gt $deadline) { throw 'TIMEOUT: the local stack did not become ready' }
        if (-not $line.IsCompleted) { Start-Sleep -Milliseconds 100; continue }
        $text = $line.GetAwaiter().GetResult()
        if ($null -eq $text) { throw 'STACK_EXITED_BEFORE_READY' }
        $document = $text | ConvertFrom-Json
        if ($document.status -eq 'ready') { $ready = $document }
        $line = $stack.StandardOutput.ReadLineAsync()
    }
    Write-Output "admin-e2e: stack ready at $($ready.admin_url) (admin build: $($ready.admin_build))"
    $env:FORGE_E2E_ADMIN_URL = $ready.control_plane_origin
    $env:FORGE_E2E_CREDENTIALS = $ready.credentials_file
    # The private workspace holds the owner set-password link, the local mailbox and (for the journeys) a small state file; it is
    # deleted with the stack.
    $env:FORGE_E2E_WORKSPACE = $ready.workspace
    $env:FORGE_E2E_OWNER_LINK = $ready.owner_link_file
    if (-not $env:FORGE_E2E_SHOTS) { $env:FORGE_E2E_SHOTS = Join-Path ([IO.Path]::GetTempPath()) 'opencode\forge-ui' }
    $npmArguments = @('run', 'test:e2e')
    if ($Spec) { $npmArguments += @('--', $Spec) }
    $result = Invoke-Npm $npmArguments $TestTimeoutSeconds
} finally {
    Remove-Item Env:FORGE_E2E_ADMIN_URL, Env:FORGE_E2E_CREDENTIALS, Env:FORGE_E2E_WORKSPACE, Env:FORGE_E2E_OWNER_LINK -ErrorAction SilentlyContinue
    if ($started -and -not $stack.HasExited) {
        $stack.StandardInput.WriteLine('stop')
        $stack.StandardInput.Close()
        $deadline = [DateTime]::UtcNow.AddSeconds($StopTimeoutSeconds)
        while ($null -ne $line -and [DateTime]::UtcNow -lt $deadline) {
            if (-not $line.IsCompleted) { Start-Sleep -Milliseconds 100; continue }
            $text = $line.GetAwaiter().GetResult()
            if ($null -eq $text) { break }
            $document = $text | ConvertFrom-Json
            if ($document.status -eq 'stopped') { $stopped = $document }
            $line = $stack.StandardOutput.ReadLineAsync()
        }
        if (-not $stack.WaitForExit(5000)) {
            Write-Warning 'OWNED_CLEANUP_PENDING: use the reported private workspace; no unrelated process was stopped.'
            $result = 1
        }
    }
    $stack.Dispose()
}
if ($started -and ($null -eq $stopped -or -not $stopped.owned_container_absent -or -not $stopped.private_workspace_absent)) {
    Write-Warning 'admin-e2e: clean stop was not confirmed'
    exit 1
}
Write-Output 'admin-e2e: owned container and private workspace removed'
exit $result
