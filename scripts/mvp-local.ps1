# Local MVP stack, loopback only: owned PostgreSQL 17 (tmpfs, removed on stop), two-organization seed,
# fake gateway on 3413 and control plane + /admin on 3410. Ctrl+C asks it to stop and remove what it owns.
# Never touches the legacy demo ports 3319/3320/3331/3332 or any process it did not start.
[CmdletBinding()]
param([switch]$RequireAdminBuild)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'LOCAL_VENV_REQUIRED' }
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName = $python
$info.WorkingDirectory = $root
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.RedirectStandardInput = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
# A clean environment: OS plumbing by name only, never ambient credentials or PG* variables.
$info.EnvironmentVariables.Clear()
foreach ($name in @('SystemRoot', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'PATH', 'PATHEXT')) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ($null -ne $value) { $info.EnvironmentVariables[$name] = $value }
}
$info.EnvironmentVariables['PYTHONPATH'] = Join-Path $root 'src'
$info.EnvironmentVariables['PYTHONNOUSERSITE'] = '1'
$info.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
$info.Arguments = '-B -u -m forge.mvp_local up --supervised' + $(if ($RequireAdminBuild) { ' --require-admin-build' } else { '' })
$process = [Diagnostics.Process]::new()
$process.StartInfo = $info
$started = $false
$result = 1
try {
    $started = $process.Start()
    $errors = $process.StandardError.ReadToEndAsync()
    $line = $process.StandardOutput.ReadLineAsync()
    while ($true) {
        if ($line.IsCompleted) {
            $text = $line.GetAwaiter().GetResult()
            if ($null -eq $text) { break }
            Write-Output $text
            $line = $process.StandardOutput.ReadLineAsync()
        }
        Start-Sleep -Milliseconds 100
    }
    $process.WaitForExit()
    # Child diagnostics are deliberately not echoed: private material stays private.
    $null = $errors.GetAwaiter().GetResult()
    $result = $process.ExitCode
} finally {
    if ($started -and -not $process.HasExited) {
        $process.StandardInput.WriteLine('stop')
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(60000)) {
            Write-Warning 'OWNED_CLEANUP_PENDING: use the reported private workspace; no unrelated process was stopped.'
        }
    }
    $process.Dispose()
}
exit $result
