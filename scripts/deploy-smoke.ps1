# Deployment smoke: brings the REAL compose stack up on the local Docker daemon, asserts it, tears everything down.
#
#   1. generates throwaway secrets and an env file in $env:TEMP (nothing secret ever touches the repository);
#   2. `docker compose up --build --wait` with compose.dev.yml: Caddy internal CA, loopback-only random ports;
#   3. asserts health, applied migrations, TLS verified against Caddy's extracted root certificate, admin and
#      downloads through the proxy, default-deny API, refused Host, first-company provisioning, no secret in
#      `compose config`, non-root read-only control plane;
#   4. proves a tampered migration is detected and blocks the control plane (separate throwaway project);
#   5. removes containers, volumes, networks, the image and the temp directory, and asserts nothing is left.
#
# Only resources prefixed `forge-smoke-` are created and removed. Ports are random free ones; 3319, 3320, 3331 and
# 3332 (retained demo ports) are never used. Exit code 0 only when every assertion passed.
[CmdletBinding()]
param(
    [int]$UpTimeoutSeconds = 300,
    [string]$Extra = ''
)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$deploy = Join-Path $root 'deploy'
$id = -join ((1..8) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
$project = 'forge-smoke-' + $id
$badProject = $project + '-bad'
$restoreProject = $project + '-restore'
$image = 'forge-smoke-image:' + $id
$work = Join-Path $env:TEMP $project
$reservedPorts = @(3319, 3320, 3331, 3332)
$envFile = Join-Path $work 'smoke.env'
$rootCert = Join-Path $work 'caddy-root.crt'
$failed = $false
$httpsPort = 0

function Write-Pass([string]$Message) { Write-Host "PASS $Message" }

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERT FAILED: $Message" }
}

function Invoke-Docker([string[]]$Arguments, [switch]$AllowFailure) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { $output = (& docker @Arguments 2>&1 | ForEach-Object { "$_" }) -join "`n" } finally { $ErrorActionPreference = $previous }
    $code = $LASTEXITCODE
    if ($code -ne 0 -and -not $AllowFailure) { throw "docker $($Arguments -join ' ') failed ($code): $output" }
    return [pscustomobject]@{ Code = $code; Output = $output }
}

function Invoke-Compose([string[]]$Arguments, [string]$Name = $project, [string[]]$Files = @(), [string[]]$Global = @(), [switch]$AllowFailure) {
    $base = @('compose', '-p', $Name, '--env-file', $envFile, '-f', (Join-Path $deploy 'compose.yml'), '-f', (Join-Path $deploy 'compose.dev.yml'))
    foreach ($file in $Files) { $base += @('-f', $file) }
    return Invoke-Docker ($base + $Global + $Arguments) -AllowFailure:$AllowFailure
}

function Get-FreePort {
    while ($true) {
        $port = Get-Random -Minimum 20000 -Maximum 40000
        if ($reservedPorts -contains $port) { continue }
        $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $port)
        try { $listener.Start(); $listener.Stop(); return $port } catch { }
    }
}

# GET/HEAD through Caddy. By default the certificate chain is verified against the extracted root (--cacert).
function Invoke-Curl([string]$Path, [string[]]$Arguments = @(), [switch]$Insecure) {
    $headerFile = Join-Path $work ('h-' + [Guid]::NewGuid().ToString('N'))
    $bodyFile = Join-Path $work ('b-' + [Guid]::NewGuid().ToString('N'))
    [string[]]$trust = if ($Insecure) { @('-k') } else { @('--cacert', $rootCert) }
    $status = & curl.exe -sS --max-time 20 --ssl-no-revoke @trust --resolve "localhost:${httpsPort}:127.0.0.1" `
        -o $bodyFile -D $headerFile -w '%{http_code}' @Arguments "https://localhost:${httpsPort}$Path"
    if ($LASTEXITCODE -ne 0) { throw "curl $Path failed ($LASTEXITCODE)" }
    $headers = @{}
    foreach ($line in (Get-Content -LiteralPath $headerFile)) {
        if ($line -match '^([^:]+):\s*(.*)$') { $headers[$Matches[1].ToLowerInvariant()] = $Matches[2].Trim() }
    }
    return [pscustomobject]@{ Status = [int]$status; Headers = $headers; Body = (Get-Content -LiteralPath $bodyFile -Raw) }
}

function Get-ProjectResources([string]$Name) {
    $label = "label=com.docker.compose.project=$Name"
    $containers = @((Invoke-Docker @('ps', '-a', '-q', '--filter', $label)).Output -split "`n" | Where-Object { $_.Trim() })
    $volumes = @((Invoke-Docker @('volume', 'ls', '-q', '--filter', $label)).Output -split "`n" | Where-Object { $_.Trim() })
    $networks = @((Invoke-Docker @('network', 'ls', '-q', '--filter', $label)).Output -split "`n" | Where-Object { $_.Trim() })
    return $containers + $volumes + $networks
}

function Assert-Gone {
    foreach ($name in @($project, $badProject, $restoreProject)) {
        Assert-True (@(Get-ProjectResources $name).Count -eq 0) "compose project $name still owns containers, volumes or networks"
    }
    Assert-True ((Invoke-Docker @('image', 'inspect', $image) -AllowFailure).Code -ne 0) "image $image still exists"
    Assert-True (-not (Test-Path -LiteralPath $work)) "$work still exists"
}

try {
    foreach ($tool in @('docker', 'curl.exe')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "REQUIRED_TOOL_MISSING: $tool" }
    }
    $python = Join-Path $root '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { $python = 'python' }
    $null = New-Item -ItemType Directory -Force -Path $work, (Join-Path $work 'downloads'), (Join-Path $work 'credentials'), (Join-Path $work 'backups')
    $work = (Resolve-Path -LiteralPath $work).Path
    & (Join-Path $PSScriptRoot 'deploy-secrets.ps1') -Directory (Join-Path $work 'secrets') | Out-Null
    Set-Content -LiteralPath (Join-Path $work 'downloads/latest.json') -Value '{"version":"0.0.0-smoke"}' -Encoding ascii
    $httpPort, $httpsPort, $mailpitPort = (Get-FreePort), (Get-FreePort), (Get-FreePort)
    while ($httpsPort -eq $httpPort) { $httpsPort = Get-FreePort }
    while ($mailpitPort -eq $httpPort -or $mailpitPort -eq $httpsPort) { $mailpitPort = Get-FreePort }
    $forward = { param($path) $path.Replace('\', '/') }
    @(
        'FORGE_DOMAIN=localhost', "FORGE_PORT_SUFFIX=:$httpsPort", 'FORGE_TLS=internal',
        "FORGE_HTTP_PORT=$httpPort", "FORGE_HTTPS_PORT=$httpsPort", "FORGE_MAILPIT_PORT=$mailpitPort", "FORGE_IMAGE=$image",
        'FORGE_SMTP_HOST=mailpit', 'FORGE_SMTP_FROM=forge@smoke.example.test', 'FORGE_SMTP_SECURITY=none', 'FORGE_SMTP_PORT=1025',
        ('FORGE_SECRETS_DIR=' + (& $forward (Join-Path $work 'secrets'))),
        ('FORGE_DOWNLOADS_DIR=' + (& $forward (Join-Path $work 'downloads'))),
        ('FORGE_CREDENTIALS_DIR=' + (& $forward (Join-Path $work 'credentials'))),
        ('FORGE_BACKUPS_DIR=' + (& $forward (Join-Path $work 'backups')))
    ) | Set-Content -LiteralPath $envFile -Encoding ascii
    $secretValues = Get-ChildItem -LiteralPath (Join-Path $work 'secrets') -File | ForEach-Object { (Get-Content -LiteralPath $_.FullName -Raw) } | ForEach-Object { "$_".Trim() } | Where-Object { $_ }

    # compose config must render and never print a secret value.
    $rendered = (Invoke-Compose @('config')).Output
    foreach ($secret in $secretValues) { Assert-True (-not $rendered.Contains($secret)) 'compose config printed a secret value' }
    Assert-True ($rendered -match 'FORGE_PUBLIC_ORIGIN: https://localhost:' + $httpsPort) 'public origin does not follow FORGE_DOMAIN/FORGE_PORT_SUFFIX'
    Write-Pass 'compose config renders and leaks no secret'

    $started = Invoke-Compose @('up', '-d', '--build', '--wait', '--wait-timeout', "$UpTimeoutSeconds")
    $containers = @((Invoke-Compose @('ps', '-a', '--format', 'json')).Output -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json })
    $state = @{}
    foreach ($container in $containers) { $state[$container.Service] = $container }
    foreach ($service in 'postgres', 'control-plane', 'caddy') {
        Assert-True ($state[$service].State -eq 'running' -and $state[$service].Health -eq 'healthy') "$service is not running healthy"
    }
    Assert-True ($state['migrate'].State -eq 'exited' -and $state['migrate'].ExitCode -eq 0) 'migrate did not exit 0'
    Write-Pass 'services healthy and migrate exited 0'

    $expected = & $python -c "import sys; sys.path.insert(0, r'$root/src'); from forge.migrate import CANONICAL_ORDER; print(len(CANONICAL_ORDER))"
    $applied = (Invoke-Compose @('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'forge', '-tAc', 'SELECT count(*) FROM forge_ops.schema_migrations')).Output.Trim()
    Assert-True ($applied -eq "$expected") "forge_ops.schema_migrations has $applied rows, expected $expected"
    Write-Pass "migrations applied ($applied)"

    Assert-True ((Invoke-Compose @('exec', '-T', 'control-plane', 'python', '-m', 'forge.serve_prod', 'healthcheck') -AllowFailure).Code -eq 0) 'forge.serve_prod healthcheck failed'
    Assert-True ((Invoke-Docker @('run', '--rm', '--entrypoint', 'id', $image, '-u')).Output.Trim() -ne '0') 'the image runs as root'
    $controlPlaneId = (Invoke-Compose @('ps', '-q', 'control-plane')).Output.Trim()
    $hardening = (Invoke-Docker @('inspect', $controlPlaneId, '--format', '{{.HostConfig.ReadonlyRootfs}} {{.Config.User}} {{.HostConfig.CapDrop}}')).Output.Trim()
    Assert-True ($hardening -eq 'true 10001:10001 [ALL]') "control plane hardening is '$hardening'"
    $published = (Invoke-Docker @('ps', '--filter', "label=com.docker.compose.project=$project", '--format', '{{.Names}} {{.Ports}}')).Output
    foreach ($line in ($published -split "`n" | Where-Object { $_.Trim() })) {
        if ($line -match '-mailpit-\d+ ') {  # the dev-only mail catcher: its web UI and API on loopback, nothing else
            Assert-True ((@([regex]::Matches($line, '(\S+)->') | ForEach-Object { $_.Groups[1].Value } | Where-Object { $_ -notmatch '^127\.0\.0\.1:' })).Count -eq 0) "mailpit publishes beyond loopback: $line"
        } elseif ($line -notmatch '-caddy-\d+ ') {
            Assert-True ($line -notmatch '->') "a non-caddy service publishes a port: $line"
        }
    }
    Write-Pass 'control plane is non-root, read-only, capability-free; only caddy (and the dev mail catcher, loopback) publishes'

    Assert-True ((Invoke-Compose @('cp', 'caddy:/data/caddy/pki/authorities/local/root.crt', $rootCert)).Code -eq 0) 'cannot extract the Caddy root certificate'
    $status = Invoke-Curl '/status'
    Assert-True ($status.Status -eq 200 -and $status.Body -match '"status":\s*"ready"') "/status via caddy returned $($status.Status)"
    Assert-True ($status.Headers['strict-transport-security'] -like 'max-age=*' -and $status.Headers['x-content-type-options'] -eq 'nosniff') 'proxy security headers are missing'
    Write-Pass 'status ready through caddy (TLS verified against the extracted internal root)'

    $admin = Invoke-Curl '/admin/'
    Assert-True ($admin.Status -eq 200 -and $admin.Headers['content-type'] -like 'text/html*' -and $admin.Headers['content-security-policy']) '/admin/ is not served with the application CSP'
    Assert-True ((Invoke-Curl '/forge/v1/accounts/me').Status -eq 401) '/forge/v1/accounts/me is not default-deny'
    Write-Pass 'admin served with the application CSP; /forge/v1/accounts/me is 401'

    $refused = Invoke-Curl '/status' -Arguments @('-H', 'Host: evil.test') -Insecure
    Assert-True ($refused.Status -eq 421 -and $refused.Body -notmatch 'ready') "an unknown Host was not refused by the proxy ($($refused.Status))"
    $manifest = Invoke-Curl '/downloads/latest.json'
    Assert-True ($manifest.Status -eq 200 -and $manifest.Headers['cache-control'] -eq 'no-cache' -and $manifest.Body -match '0.0.0-smoke') 'latest.json is not served with no-cache'
    Assert-True ((Invoke-Curl '/downloads/').Status -eq 404) 'the downloads directory is listed'
    Write-Pass 'unknown Host refused; downloads served without listing and latest.json no-cache'

    $first = (Invoke-Compose @('run', '--rm', '-T', 'provision', 'org', '--slug', 'smoke-co', '--name', 'Smoke Company', '--department', 'Operations',
            '--admin-email', 'admin@smoke.example.test', '--admin-name', 'Smoke Admin') -Global @('--profile', 'tools')).Output
    Assert-True ($first -match '"status": "provisioned"' -and $first -match '"created": true') "first company was not provisioned: $first"
    $issued = @(Get-ChildItem -LiteralPath (Join-Path $work 'credentials') -File)
    Assert-True ($issued.Count -eq 1) 'exactly one credentials file must exist after the first run'
    $again = (Invoke-Compose @('run', '--rm', '-T', 'provision', 'org', '--slug', 'smoke-co', '--name', 'Smoke Company', '--department', 'Operations',
            '--admin-email', 'admin@smoke.example.test', '--admin-name', 'Smoke Admin') -Global @('--profile', 'tools')).Output
    Assert-True ($again -match '"created": false' -and @(Get-ChildItem -LiteralPath (Join-Path $work 'credentials') -File).Count -eq 1) 'a rerun created something'
    Write-Pass 'first company provisioned through the tools profile (rerun is a no-op)'

    # Invitation email: sign in as the new company's administrator, invite someone, read the message from Mailpit and
    # follow its link (the invited person sets a password and signs in).
    $mailpit = "http://127.0.0.1:$mailpitPort"
    $check = (Invoke-Compose @('exec', '-T', '-e', 'TO=check@smoke.example.test', 'control-plane', 'python', '-c',
            "import os, uuid; from forge.smtp_delivery import SmtpDelivery, load_smtp_settings; SmtpDelivery(load_smtp_settings(os.environ)).deliver(uuid.uuid4(), os.environ['TO'], 'Smoke test', os.environ['FORGE_PUBLIC_ORIGIN'] + '/onboarding#smtp-check'); print('sent')")).Output.Trim()
    Assert-True ($check -eq 'sent') "the SMTP check command did not print 'sent': $check"
    $credentials = Get-Content -LiteralPath $issued[0].FullName -Raw | ConvertFrom-Json
    $company = $credentials.organizations[0]
    $administrator = @($company.accounts | Where-Object { $_.role -eq 'organization_admin' })[0]
    $department = (Invoke-Compose @('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'forge', '-tAc', "SELECT id FROM forge.departments WHERE organization_id = '$($company.organization_id)'")).Output.Trim()
    $origin = "https://localhost:$httpsPort"
    function Invoke-Json([string]$Path, $Body, [string]$Token = '') {
        $file = Join-Path $work ('j-' + [Guid]::NewGuid().ToString('N'))
        Set-Content -LiteralPath $file -Value ($Body | ConvertTo-Json -Compress) -Encoding ascii
        $arguments = @('-X', 'POST', '-H', 'Content-Type: application/json', '-H', "Origin: $origin", '--data-binary', "@$file")
        if ($Token) { $arguments += @('-H', "Authorization: Bearer $Token") }
        $reply = Invoke-Curl $Path -Arguments $arguments
        Remove-Item -LiteralPath $file -Force
        return $reply
    }
    $login = Invoke-Json '/forge/v1/accounts/login' @{ email = $administrator.email; password = $administrator.password }
    Assert-True ($login.Status -eq 200) "the administrator could not sign in ($($login.Status))"
    $token = ($login.Body | ConvertFrom-Json).access_token
    $invited = Invoke-Json '/forge/v1/accounts/invitations' @{ organization_id = $company.organization_id; department_id = $department; email = 'newhire@smoke.example.test'; name = 'New Hire' } $token
    $invitation = $invited.Body | ConvertFrom-Json
    Assert-True ($invited.Status -eq 201 -and $invitation.delivery_state -eq 'delivered' -and $invitation.delivery_channel -eq 'smtp') "the invitation was not delivered over smtp ($($invited.Status) $($invited.Body))"
    $found = @((Invoke-RestMethod -Uri "$mailpit/api/v1/messages" -TimeoutSec 20).messages | Where-Object { @($_.To | ForEach-Object { $_.Address }) -contains 'newhire@smoke.example.test' })
    Assert-True ($found.Count -eq 1 -and $found[0].Subject -eq 'Your Forge invitation') 'Mailpit did not capture exactly one invitation for the invited person'
    $message = Invoke-RestMethod -Uri "$mailpit/api/v1/message/$($found[0].ID)" -TimeoutSec 20
    Assert-True ($message.From.Address -eq 'forge@smoke.example.test' -and $message.Text -match 'Hello New Hire') 'the captured message has the wrong sender or content'
    Assert-True ($message.Text -match '(https://localhost:\d+)/onboarding#invitation_id=([0-9a-f-]{36})&capability=([A-Za-z0-9_-]{43})') 'the message holds no onboarding link'
    Assert-True ($Matches[1] -eq $origin -and $Matches[2] -eq $invitation.invitation_id) 'the link does not use the public origin and the issued invitation'
    $capability = $Matches[3]
    Assert-True (-not $message.Text.Contains($administrator.password) -and -not $message.HTML.Contains($administrator.password)) 'the message carries a password'
    Write-Pass 'invitation email captured by Mailpit over smtp with the link on the public origin'

    $accepted = Invoke-Json '/forge/v1/accounts/invitations/accept' @{ invitation_id = $invitation.invitation_id; capability = $capability; password = 'a-long-new-hire-passphrase-1' }
    Assert-True ($accepted.Status -eq 201) "the emailed link did not activate the account ($($accepted.Status))"
    $newLogin = Invoke-Json '/forge/v1/accounts/login' @{ email = 'newhire@smoke.example.test'; password = 'a-long-new-hire-passphrase-1' }
    Assert-True ($newLogin.Status -eq 200) 'the invited person could not sign in after following the link'
    Write-Pass 'the emailed link activates the account and the invited person signs in'

    # Platform owner: bootstrap from the tools profile (the one-time link is mailed through Mailpit and also written to
    # a private file), set the password from the link once, enrol TOTP, create a company, follow the emailed first-admin
    # invitation, and prove suspension denies the company and reactivation restores it.
    function Get-Totp([string]$Secret, [int]$Offset = 0, [int64]$AtSeconds = 0) {
        $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
        $bits = -join ($Secret.ToUpperInvariant().TrimEnd('=').ToCharArray() | ForEach-Object { [Convert]::ToString($alphabet.IndexOf($_), 2).PadLeft(5, '0') })
        $key = [byte[]]@(for ($index = 0; $index + 8 -le $bits.Length; $index += 8) { [Convert]::ToByte($bits.Substring($index, 8), 2) })
        if ($AtSeconds -eq 0) { $AtSeconds = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }
        $counter = [int64]([Math]::Floor($AtSeconds / 30)) + $Offset
        $message = [BitConverter]::GetBytes($counter)
        [Array]::Reverse($message)
        $hash = [Security.Cryptography.HMACSHA1]::new($key).ComputeHash($message)
        $start = $hash[$hash.Length - 1] -band 0x0F
        # [byte] -shl stays a byte (255 -shl 8 is 0), so every term is widened to [int] first.
        $value = (([int]$hash[$start] -band 0x7F) -shl 24) -bor ([int]$hash[$start + 1] -shl 16) -bor ([int]$hash[$start + 2] -shl 8) -bor [int]$hash[$start + 3]
        return ($value % 1000000).ToString('000000')
    }
    function Get-Mail([string]$Address, [string]$Subject) {
        $listed = @((Invoke-RestMethod -Uri "$mailpit/api/v1/messages" -TimeoutSec 20).messages | Where-Object {
                @($_.To | ForEach-Object { $_.Address }) -contains $Address -and $_.Subject -eq $Subject })
        Assert-True ($listed.Count -eq 1) "Mailpit did not capture exactly one '$Subject' message for $Address"
        return Invoke-RestMethod -Uri "$mailpit/api/v1/message/$($listed[0].ID)" -TimeoutSec 20
    }
    function Invoke-Authenticated([string]$Path, [string]$Token) {
        return Invoke-Curl $Path -Arguments @('-H', "Authorization: Bearer $Token", '-H', "Origin: $origin")
    }
    $ownerAddress = 'owner@smoke.example.test'
    $bootstrap = (Invoke-Compose @('run', '--rm', '-T', 'platform', 'bootstrap-owner', '--email', $ownerAddress, '--name', 'Smoke Owner',
            '--link-file', '/credentials/owner-link.txt', '--smtp') -Global @('--profile', 'tools')).Output
    Assert-True ($bootstrap -match '"status": "created"' -and $bootstrap -match '"delivery": "delivered"') "the owner was not bootstrapped and mailed: $bootstrap"
    $linkFile = Join-Path (Join-Path $work 'credentials') 'owner-link.txt'
    Assert-True (Test-Path -LiteralPath $linkFile) 'the one-time link file was not written'
    $resetMail = Get-Mail $ownerAddress 'Reset your Forge password'
    Assert-True ($resetMail.Text -match '(https://localhost:\d+)/reset-password#capability=([A-Za-z0-9_-]{43})') 'the owner message holds no set-password link'
    Assert-True ($Matches[1] -eq $origin -and (Get-Content -LiteralPath $linkFile -Raw).Trim() -eq $Matches[0]) 'the mailed link differs from the private file or the public origin'
    $ownerCapability = $Matches[2]
    $ownerAgain = (Invoke-Compose @('run', '--rm', '-T', 'platform', 'bootstrap-owner', '--email', 'someone@smoke.example.test', '--name', 'Other',
            '--link-file', '/credentials/second-link.txt') -Global @('--profile', 'tools')).Output
    Assert-True ($ownerAgain -match '"status": "exists"' -and -not (Test-Path -LiteralPath (Join-Path (Join-Path $work 'credentials') 'second-link.txt'))) 'a rerun of the bootstrap was not a no-op'
    $ownerPassword = 'a-long-platform-owner-passphrase-1'
    Assert-True ((Invoke-Json '/forge/v1/accounts/password-reset/consume' @{ capability = $ownerCapability; password = $ownerPassword }).Status -eq 204) 'the set-password link did not work'
    Assert-True ((Invoke-Json '/forge/v1/accounts/password-reset/consume' @{ capability = $ownerCapability; password = 'another-platform-owner-passphrase-2' }).Status -eq 404) 'the owner link is single-use'
    $ownerLogin = Invoke-Json '/forge/v1/accounts/login' @{ email = $ownerAddress; password = $ownerPassword }
    Assert-True ($ownerLogin.Status -eq 200) 'the owner could not sign in after setting the password'
    $ownerToken = ($ownerLogin.Body | ConvertFrom-Json).access_token
    Assert-True ((Invoke-Authenticated '/forge/v1/platform/companies' $ownerToken).Status -eq 403) 'a password-only owner session reached the platform'
    $enrolment = (Invoke-Json '/forge/v1/platform/mfa/enroll' @{} $ownerToken)
    Assert-True ($enrolment.Status -eq 201) "TOTP enrolment failed ($($enrolment.Status))"
    $enrolled = $enrolment.Body | ConvertFrom-Json
    Assert-True (@($enrolled.recovery_codes).Count -eq 10) 'enrolment did not return ten recovery codes'
    $verified = Invoke-Json '/forge/v1/platform/login/mfa' @{ code = (Get-Totp $enrolled.secret) } $ownerToken
    Assert-True ($verified.Status -eq 200) "the TOTP code was not accepted ($($verified.Status) $($verified.Body))"
    Assert-True ((Invoke-Json '/forge/v1/platform/login/mfa' @{ code = (Get-Totp $enrolled.secret) } $ownerToken).Status -eq 403) 'a TOTP step was accepted twice'
    Write-Pass 'platform owner bootstrapped (link mailed, written once, rerun is a no-op), password set once, TOTP enrolled and verified'

    $created = Invoke-Json '/forge/v1/platform/companies' @{ slug = 'platform-co'; display_name = 'Platform Company'; department = 'Operations'
        admin_email = 'first.admin@smoke.example.test'; admin_name = 'First Admin' } $ownerToken
    $newCompany = $created.Body | ConvertFrom-Json
    Assert-True ($created.Status -eq 201 -and $newCompany.invitation.delivery_state -eq 'delivered' -and $newCompany.invitation.delivery_channel -eq 'smtp') "the company was not created with an emailed invitation ($($created.Status) $($created.Body))"
    Assert-True ((Invoke-Json '/forge/v1/platform/companies' @{ slug = 'platform-co'; display_name = 'Again'; department = 'Ops'
        admin_email = 'x@smoke.example.test'; admin_name = 'X' } $ownerToken).Status -eq 409) 'a taken company code was not a conflict'
    $adminMail = Get-Mail 'first.admin@smoke.example.test' 'Your Forge invitation'
    Assert-True ($adminMail.Text -match '(https://localhost:\d+)/onboarding\?c=platform-co#invitation_id=([0-9a-f-]{36})&capability=([A-Za-z0-9_-]{43})') 'the first-admin message holds no onboarding link with the company code'
    $firstInvitation = $Matches[2]
    $firstCapability = $Matches[3]
    Assert-True ($firstInvitation -eq $newCompany.invitation.id) 'the link does not carry the issued invitation'
    $firstPassword = 'a-long-first-admin-passphrase-1'
    Assert-True ((Invoke-Json '/forge/v1/accounts/invitations/accept' @{ invitation_id = $firstInvitation; capability = $firstCapability; password = $firstPassword }).Status -eq 201) 'the first admin could not accept the invitation'
    $adminLogin = Invoke-Json '/forge/v1/accounts/login' @{ email = 'first.admin@smoke.example.test'; password = $firstPassword }
    Assert-True ($adminLogin.Status -eq 200) 'the first admin could not sign in'
    $adminToken = ($adminLogin.Body | ConvertFrom-Json).access_token
    $membersPath = "/forge/v1/orgs/$($newCompany.id)/members"
    $members = Invoke-Authenticated $membersPath $adminToken
    Assert-True ($members.Status -eq 200 -and ($members.Body | ConvertFrom-Json).members[0].roles -contains 'organization_admin') 'the first admin does not see itself as organization_admin'
    Write-Pass 'company created by the owner; the emailed first-admin invitation was accepted and the admin runs the company'

    $suspend = Invoke-Json "/forge/v1/platform/companies/$($newCompany.id)/suspend" @{} $ownerToken
    Assert-True ($suspend.Status -eq 200 -and -not ($suspend.Body | ConvertFrom-Json).active) 'the company was not suspended'
    Assert-True (@(401, 403, 404) -contains (Invoke-Authenticated $membersPath $adminToken).Status) 'a suspended company still serves its administrator'
    $reactivate = Invoke-Json "/forge/v1/platform/companies/$($newCompany.id)/reactivate" @{} $ownerToken
    Assert-True ($reactivate.Status -eq 200 -and ($reactivate.Body | ConvertFrom-Json).active) 'the company was not reactivated'
    Assert-True ((Invoke-Authenticated $membersPath $adminToken).Status -eq 200) 'reactivation did not restore the administrator'
    $auditTrail = (Invoke-Authenticated '/forge/v1/platform/audit' $ownerToken).Body | ConvertFrom-Json
    Assert-True ((@($auditTrail.entries | ForEach-Object { $_.action }) -join ',') -eq 'company.reactivated,company.suspended,company.created,owner.mfa_enrolled') 'the audit log does not show the platform actions newest first'
    Write-Pass 'suspension denies the company and reactivation restores it; every platform action is audited'
    # Backups: a verified dump, retention, restore refusing a used database, and a round trip into a fresh volume.
    $backups = Join-Path $work 'backups'
    $backupScript = @('exec', '-T', 'backup', '/bin/sh', '/opt/forge/backup.sh')
    $null = Invoke-Compose ($backupScript + 'run-once')
    $dumps = @(Get-ChildItem -LiteralPath $backups -Filter 'forge-*.dump')
    Assert-True ($dumps.Count -eq 1 -and $dumps[0].Length -gt 0) 'run-once did not write exactly one non-empty dump'
    $listing = (Invoke-Compose @('exec', '-T', 'backup', 'pg_restore', '--list', "/backups/$($dumps[0].Name)")).Output
    Assert-True ($listing -match 'TABLE DATA forge organizations') 'pg_restore --list does not show the organizations data'
    Write-Pass 'backup dump is valid (pg_restore --list reads it)'

    foreach ($round in 1, 2) {
        Start-Sleep -Seconds 2
        $null = Invoke-Compose @('exec', '-T', '-e', 'FORGE_BACKUP_KEEP=2', 'backup', '/bin/sh', '/opt/forge/backup.sh', 'run-once')
    }
    $kept = @(Get-ChildItem -LiteralPath $backups -Filter 'forge-*.dump' | Sort-Object Name)
    Assert-True ($kept.Count -eq 2 -and $kept[0].Name -ne $dumps[0].Name) "retention left $($kept.Count) dumps (FORGE_BACKUP_KEEP=2)"
    Write-Pass 'retention keeps the newest 2'

    $newest = $kept[-1].Name
    $refusal = Invoke-Compose @('run', '--rm', '-T', 'restore', "/backups/$newest") -Global @('--profile', 'tools') -AllowFailure
    Assert-True ($refusal.Code -ne 0 -and $refusal.Output -match 'TARGET_NOT_EMPTY') 'restore.sh did not refuse a non-empty database'
    Write-Pass 'restore refuses a non-empty target'

    $sql = (Invoke-Compose @('exec', '-T', 'backup', 'pg_restore', '--file=-', "/backups/$newest")).Output
    foreach ($secret in $secretValues) { Assert-True (-not $sql.Contains($secret)) 'a dump contains a secret value' }
    Assert-True (@(Get-ChildItem -LiteralPath $backups -File | Where-Object { $_.Name -notmatch '^forge-\d{8}T\d{6}Z\.dump$' }).Count -eq 0) 'the backup directory holds unexpected files'
    Write-Pass 'dumps contain no secret value'

    # Round trip: a fresh stack (migrate builds the reviewed schema), then only the rows are restored into it.
    $null = Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '240', 'control-plane') -Name $restoreProject
    $null = Invoke-Compose @('stop', 'control-plane') -Name $restoreProject
    $restored = Invoke-Compose @('run', '--rm', '-T', 'restore', "/backups/$newest") -Name $restoreProject -Global @('--profile', 'tools')
    Assert-True ($restored.Output -match 'RESTORED') "restore.sh did not report success: $($restored.Output)"
    $second = Invoke-Compose @('run', '--rm', '-T', 'restore', "/backups/$newest") -Name $restoreProject -Global @('--profile', 'tools') -AllowFailure
    Assert-True ($second.Code -eq 3 -and $second.Output -match 'TARGET_NOT_EMPTY') 'a second restore was not refused'
    $noop = (Invoke-Compose @('run', '--rm', '-T', 'migrate', 'migrate', '--migrations-dir', '/app/migrations') -Name $restoreProject).Output
    Assert-True ($noop -match '"applied": \[\]') 'migrate was not a no-op after the restore'
    $null = Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '120', 'control-plane') -Name $restoreProject
    $slugs = (Invoke-Compose @('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'forge', '-tAc', 'SELECT slug FROM forge.organizations') -Name $restoreProject).Output
    Assert-True ($slugs -match 'smoke-co') 'the restored database lacks the provisioned company'
    Assert-True ((Invoke-Compose @('exec', '-T', 'control-plane', 'python', '-m', 'forge.serve_prod', 'healthcheck') -Name $restoreProject -AllowFailure).Code -eq 0) 'readiness does not attest after the restore'
    Write-Pass 'restore round trip into a fresh volume (migrate no-op, readiness attests)'    $null = Invoke-Compose @('down', '-v', '--remove-orphans') -Name $restoreProject -Global @('--profile', 'tools')

    # A tampered applied migration is detected by the one-shot job.
    $tampered = Join-Path $work 'tampered'
    Copy-Item -LiteralPath (Join-Path $root 'migrations') -Destination $tampered -Recurse
    $first = Get-ChildItem -LiteralPath $tampered -Filter '*.sql' | Sort-Object Name | Select-Object -First 1
    Add-Content -LiteralPath $first.FullName -Value "`n-- tampered"
    $override = Join-Path $work 'tamper.yml'
    $mount = (& $forward $tampered)
    Set-Content -LiteralPath $override -Encoding ascii -Value "services:`n  migrate:`n    volumes:`n      - ${mount}:/app/migrations:ro"
    $checksum = Invoke-Compose @('run', '--rm', '-T', 'migrate', 'migrate', '--migrations-dir', '/app/migrations') -Files @($override) -AllowFailure
    Assert-True ($checksum.Code -ne 0 -and $checksum.Output -match 'MIGRATION_CHECKSUM_MISMATCH') 'a tampered applied migration was not detected'

    # A failing migrate keeps the control plane from ever starting (fresh project, broken script).
    Add-Content -LiteralPath $first.FullName -Value 'SELECT definitely not valid sql ('
    $bad = Invoke-Compose @('up', '-d', '--wait', '--wait-timeout', '120', 'control-plane') -Name $badProject -Files @($override) -AllowFailure
    $badState = @((Invoke-Compose @('ps', '-a', '--format', 'json') -Name $badProject).Output -split "`n" | Where-Object { $_.Trim().StartsWith('{') } | ForEach-Object { $_ | ConvertFrom-Json })
    $badLogs = (Invoke-Compose @('logs', 'migrate') -Name $badProject -AllowFailure).Output
    Assert-True ($bad.Code -ne 0 -and $badLogs -match 'MIGRATION_FAILED') 'a failing migrate did not fail the stack'
    Assert-True (@($badState | Where-Object { $_.Service -eq 'control-plane' -and $_.State -eq 'running' }).Count -eq 0) 'the control plane started after a failed migrate'
    Write-Pass 'tampered migration blocks control plane'
} catch {
    $failed = $true
    Write-Host "FAIL $($_.Exception.Message)"
    # Service logs carry finite codes only (never a secret), so they are safe to show for diagnosis.
    foreach ($name in @($project, $restoreProject)) {
        if (Test-Path -LiteralPath $envFile) { Write-Host (Invoke-Compose @('logs', '--no-color', '--tail', '25', 'migrate', 'control-plane', 'postgres') -Name $name -AllowFailure).Output }
    }
} finally {
    foreach ($name in @($restoreProject, $badProject, $project)) {
        if (Test-Path -LiteralPath $envFile) { $null = Invoke-Compose @('down', '-v', '--remove-orphans') -Name $name -Global @('--profile', 'tools') -AllowFailure }
    }
    $null = Invoke-Docker @('rmi', '-f', $image) -AllowFailure
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }
    try { Assert-Gone; Write-Pass 'teardown left nothing' } catch { $failed = $true; Write-Host "FAIL $($_.Exception.Message)" }
}
if ($failed) { exit 1 }
exit 0
