#requires -Version 7.0
# Explicit retained local demo. Stop keeps all owned data; no delete/reset operation.
[CmdletBinding()]
param([switch]$Create,[switch]$Resume,[switch]$Stop,[switch]$UpgradeGateway,[string]$DemoDirectory)
$ErrorActionPreference = 'Stop'
if (([int]$Create.IsPresent + [int]$Resume.IsPresent + [int]$Stop.IsPresent + [int]$UpgradeGateway.IsPresent) -ne 1) { throw 'EXPLICIT_DURABLE_MODE_REQUIRED' }
if ($Create -and $DemoDirectory) { throw 'FRESH_DURABLE_DIRECTORY_REQUIRED' }
if (-not $Create -and -not $DemoDirectory) { throw 'EXPLICIT_DURABLE_DIRECTORY_REQUIRED' }
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'LOCAL_VENV_REQUIRED' }
$info = [Diagnostics.ProcessStartInfo]::new()
$info.FileName = $python
$info.WorkingDirectory = $root
$info.UseShellExecute = $false
$info.CreateNoWindow = $true
$info.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
$info.RedirectStandardInput = $true
$info.RedirectStandardOutput = $true
$info.RedirectStandardError = $true
$info.Environment.Clear()
foreach ($name in @('SystemRoot','WINDIR','COMSPEC','TEMP','TMP','PATH','PATHEXT')) {
    $value = [Environment]::GetEnvironmentVariable($name,'Process')
    if ($null -ne $value) { $info.Environment[$name] = $value }
}
$info.Environment['PYTHONPATH'] = Join-Path $root 'src'
$info.Environment['PYTHONNOUSERSITE'] = '1'
$info.Environment['PYTHONDONTWRITEBYTECODE'] = '1'
foreach ($argument in @('-B','-u','-m','forge.dev_accounts_persistent')) {
    $info.ArgumentList.Add($argument)
}
if ($Create) { $info.ArgumentList.Add('--create') }
elseif ($Resume) { $info.ArgumentList.Add('--resume') }
elseif ($UpgradeGateway) { $info.ArgumentList.Add('--upgrade-gateway') }
else { $info.ArgumentList.Add('--stop') }
if ($DemoDirectory) { $info.ArgumentList.Add('--demo-directory'); $info.ArgumentList.Add($DemoDirectory) }
if (-not $Stop -and -not $UpgradeGateway) { $info.ArgumentList.Add('--supervised') }
$process = [Diagnostics.Process]::new()
$process.StartInfo = $info
$started = $false
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
        if (-not $process.WaitForExit(40000)) {
            Write-Warning 'OWNED_CLEANUP_PENDING: use the reported private demo directory; no unrelated process was stopped.'
        }
    }
    $process.Dispose()
}
exit $result
