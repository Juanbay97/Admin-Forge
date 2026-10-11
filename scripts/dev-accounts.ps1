#requires -Version 7.0
<# Disposable fixture only. Ctrl+C/parent exit requests exact owned cleanup.
   Credentials and .eml capabilities stay in the verified private session folder.
   Neither this wrapper nor the backend configures the native enterprise profile. #>
[CmdletBinding()]
param(
    [string]$RepositoryRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$FrontendOrigin = 'http://127.0.0.1:3319',
    [switch]$Stop,
    [string]$SessionDirectory
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if (-not (Test-Path -LiteralPath $RepositoryRoot -PathType Container) -or
    [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\','/') -ne $root.TrimEnd('\','/')) {
    throw 'INVALID_REPOSITORY'
}
if ($FrontendOrigin -cne 'http://127.0.0.1:3319') { throw 'INVALID_FRONTEND_ORIGIN' }
if ($Stop -and -not $SessionDirectory) { throw 'OWNED_SESSION_REQUIRED' }
if (-not $Stop -and $SessionDirectory) { throw 'EXISTING_SESSION_ADOPTION_FORBIDDEN' }
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
foreach ($argument in @('-B','-u','-m','forge.dev_accounts','--repository',$root,'--frontend-origin',$FrontendOrigin)) {
    $info.ArgumentList.Add($argument)
}
if ($Stop) {
    foreach ($argument in @('--stop','--session-directory',$SessionDirectory)) { $info.ArgumentList.Add($argument) }
} else { $info.ArgumentList.Add('--supervised') }
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
            Write-Warning 'OWNED_CLEANUP_PENDING: use the reported private session directory; no unrelated process was stopped.'
        }
    }
    $process.Dispose()
}
exit $result
