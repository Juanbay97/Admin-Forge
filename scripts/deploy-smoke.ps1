# Deployment smoke: brings the REAL compose stack up on the local Docker daemon, asserts it, tears everything down.
#
#   1. generates throwaway secrets and an env file in $env:TEMP (nothing secret ever touches the repository);
#   2. `docker compose up --build --wait` with compose.dev.yml: Caddy internal CA, loopback-only random ports;
#   3. asserts health, applied migrations, TLS verified against Caddy's extracted root certificate, admin and
#      downloads through the proxy, default-deny API, refused Host, first-company provisioning, no secret in
#      `compose config`, non-root read-only control plane;
#      and meters real inference: the platform owner assigns gateway keys, a member chats through the control plane to a fake
#      gateway served over https with a throwaway certificate (the first key is rejected, so the request fails over), and the
#      usage appears in the platform reports and in the company administrator's per-person report;
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
    # Fake gateway over https: a throwaway certificate (the control plane trusts exactly this file) and the keys it accepts.
    $fakeGateway = Join-Path $work 'fake-gateway'
    $null = New-Item -ItemType Directory -Force -Path $fakeGateway
    & $python -c "import sys; sys.path.insert(0, r'$root/src'); from forge.fake_gateway import main; raise SystemExit(main(['--make-cert', r'$fakeGateway', '--name', 'fake-gateway']))" | Out-Null
    Assert-True ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath (Join-Path $fakeGateway 'gateway.crt'))) 'the fake gateway certificate was not generated'
    $fakeConnectors = Join-Path $work 'fake-connectors'
    $null = New-Item -ItemType Directory -Force -Path $fakeConnectors
    Set-Content -LiteralPath (Join-Path $fakeConnectors 'fixtures.json') -Encoding ascii -Value '{"oauth.fixture.test":{"connect_host":"fake-connectors","port":3414},"mcp.fixture.test":{"connect_host":"fake-connectors","port":3415}}'
    $goodKey, $badKey = 'smoke-key-good-0001', 'smoke-key-bad-0000'
    Set-Content -LiteralPath (Join-Path $fakeGateway 'keys.txt') -Value $goodKey -Encoding ascii
    @(
        'FORGE_DOMAIN=localhost', "FORGE_PORT_SUFFIX=:$httpsPort", 'FORGE_TLS=internal',
        "FORGE_HTTP_PORT=$httpPort", "FORGE_HTTPS_PORT=$httpsPort", "FORGE_MAILPIT_PORT=$mailpitPort", "FORGE_IMAGE=$image",
        'FORGE_SMTP_HOST=mailpit', 'FORGE_SMTP_FROM=forge@smoke.example.test', 'FORGE_SMTP_SECURITY=none', 'FORGE_SMTP_PORT=1025',
        ('FORGE_SECRETS_DIR=' + (& $forward (Join-Path $work 'secrets'))),
        ('FORGE_DOWNLOADS_DIR=' + (& $forward (Join-Path $work 'downloads'))),
        ('FORGE_CREDENTIALS_DIR=' + (& $forward (Join-Path $work 'credentials'))),
        ('FORGE_BACKUPS_DIR=' + (& $forward (Join-Path $work 'backups'))),
        ('FORGE_FAKE_GATEWAY_DIR=' + (& $forward $fakeGateway)), 'FORGE_GATEWAY_ORIGINS=https://fake-gateway:3413',
        ('FORGE_FAKE_CONNECTORS_DIR=' + (& $forward $fakeConnectors))
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
    foreach ($service in 'postgres', 'control-plane', 'caddy', 'fake-gateway', 'fake-connectors') {
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
        } elseif ($line -notmatch '-caddy-\d+ ') {  # (the fake gateway, like every other service, publishes nothing)
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

    # Metering: the owner assigns gateway keys to smoke-co, its administrator publishes a catalogue within the model ceiling,
    # a member chats (the first key is rejected by the fake gateway, so the request fails over to the second), and the usage
    # is visible to the owner (per company, per model, totals) and to the company administrator (per person) only.
    function Invoke-Send([string]$Method, [string]$Path, $Body, [string]$Token) {
        $arguments = @('-X', $Method, '-H', "Origin: $origin", '-H', "Authorization: Bearer $Token")
        $file = $null
        if ($null -ne $Body) {
            $file = Join-Path $work ('s-' + [Guid]::NewGuid().ToString('N'))
            Set-Content -LiteralPath $file -Value ($Body | ConvertTo-Json -Compress -Depth 6) -Encoding ascii
            $arguments += @('-H', 'Content-Type: application/json', '--data-binary', "@$file")
        }
        $reply = Invoke-Curl $Path -Arguments $arguments
        if ($file) { Remove-Item -LiteralPath $file -Force }
        return $reply
    }
    function Get-Rows([string]$Sql) { return (Invoke-Compose @('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'forge', '-tAc', $Sql)).Output.Trim() }
    $smokeOrg = $company.organization_id
    $gatewayOrigin = 'https://fake-gateway:3413'
    $secretValues = @($secretValues) + @($goodKey, $badKey)
    $good = Invoke-Send 'POST' '/forge/v1/platform/gateway-keys' @{ label = 'smoke-good'; origin = $gatewayOrigin; key = $goodKey } $ownerToken
    $bad = Invoke-Send 'POST' '/forge/v1/platform/gateway-keys' @{ label = 'smoke-bad'; origin = $gatewayOrigin; key = $badKey } $ownerToken
    Assert-True ($good.Status -eq 201 -and $bad.Status -eq 201) "the owner could not create the gateway keys ($($good.Status) $($bad.Status) $($good.Body))"
    Assert-True (-not $good.Body.Contains($goodKey) -and -not $bad.Body.Contains($badKey) -and ($good.Body | ConvertFrom-Json).hint -eq '0001') 'a key response carries key text or no hint'
    $goodId, $badId = ($good.Body | ConvertFrom-Json).id, ($bad.Body | ConvertFrom-Json).id
    $evil = Invoke-Send 'POST' '/forge/v1/platform/gateway-keys' @{ label = 'smoke-evil'; origin = 'https://evil.example.test'; key = 'x-evil-key-0000' } $ownerToken
    Assert-True ($evil.Status -eq 422) "a key for an origin outside the deployment allow-list was not refused ($($evil.Status))"
    $assigned = Invoke-Send 'PUT' "/forge/v1/platform/companies/$smokeOrg/gateway-keys" @{ keys = @(@{ key_id = $goodId; priority = 1; active = $true }) } $ownerToken
    Assert-True ($assigned.Status -eq 200) "the owner could not assign the key ($($assigned.Status) $($assigned.Body))"
    Assert-True ((Invoke-Send 'PUT' "/forge/v1/platform/companies/$smokeOrg/model-access" @{ models = @('fake-fast', 'fake-nousage') } $ownerToken).Status -eq 200) 'the owner could not set the model ceiling'
    Assert-True ((Invoke-Send 'POST' '/forge/v1/platform/prices' @{ upstream_id = 'fake-fast'; input_micros = 1000000; output_micros = 2000000 } $ownerToken).Status -eq 201) 'the owner could not set a price'
    Write-Pass 'the owner created two gateway keys (never echoed), refused a foreign origin, assigned one to the company, set its ceiling and a price'

    $smokeLogin = Invoke-Json '/forge/v1/accounts/login' @{ email = $administrator.email; password = $administrator.password }
    $smokeAdmin = ($smokeLogin.Body | ConvertFrom-Json).access_token
    $memberToken = ($newLogin.Body | ConvertFrom-Json).access_token
    $gatewayPath = "/forge/v1/orgs/$smokeOrg/gateway"
    $status = Invoke-Authenticated $gatewayPath $smokeAdmin
    $shown = $status.Body | ConvertFrom-Json
    Assert-True ($status.Status -eq 200 -and $shown.status -eq 'SAVED_UNVERIFIED' -and $shown.revision -eq 1 -and $shown.endpoint -eq '' -and @($shown.allowed_endpoints).Count -eq 0) "the administrator's gateway status is not status-only ($($status.Body))"
    $refusedWrite = Invoke-Send 'PUT' $gatewayPath @{ expected_revision = 0; api_key = 'admin-typed-key-0000' } $smokeAdmin
    Assert-True ($refusedWrite.Status -eq 403 -and $refusedWrite.Body -match 'GATEWAY_MANAGED_BY_PLATFORM' -and -not $refusedWrite.Body.Contains('admin-typed-key')) 'a company administrator could write the gateway key'
    $refresh = Invoke-Send 'POST' "$gatewayPath/catalogue/refresh" $null $smokeAdmin
    Assert-True ($refresh.Status -eq 200 -and $refresh.Body -match 'fake-fast') "the administrator could not refresh the models ($($refresh.Status) $($refresh.Body))"
    $publish = @{ operation_id = [Guid]::NewGuid().ToString(); expected_catalogue_revision = 0; expected_gateway_revision = 1
        aliases = @{ assistant = 'fake-fast'; quiet = 'fake-nousage' }; default_alias = 'assistant' }
    Assert-True ((Invoke-Send 'POST' "/forge/v1/orgs/$smokeOrg/models/publish" $publish $smokeAdmin).Status -eq 200) 'the administrator could not publish within the ceiling'
    $outside = @{ operation_id = [Guid]::NewGuid().ToString(); expected_catalogue_revision = 1; expected_gateway_revision = 1
        aliases = @{ assistant = 'fake-fast'; slow = 'fake-slow' }; default_alias = 'assistant' }
    Assert-True ((Invoke-Send 'POST' "/forge/v1/orgs/$smokeOrg/models/publish" $outside $smokeAdmin).Status -eq 404) 'a model outside the platform ceiling was published'
    Write-Pass 'the administrator sees status only (PUT is 403), refreshed the catalogue through the platform key and published within the ceiling (outside it is refused)'

    # Failover: the rejected key becomes the primary; rotation or reordering never stales the published catalogue.
    $reordered = Invoke-Send 'PUT' "/forge/v1/platform/companies/$smokeOrg/gateway-keys" @{ keys = @(@{ key_id = $badId; priority = 1; active = $true }, @{ key_id = $goodId; priority = 2; active = $true }) } $ownerToken
    Assert-True ($reordered.Status -eq 200 -and ($reordered.Body | ConvertFrom-Json).keys[0].label -eq 'smoke-bad') 'the owner could not make the rejected key the primary'
    $catalogStatus = (Invoke-Authenticated "$gatewayPath/catalogue/status" $smokeAdmin).Body | ConvertFrom-Json
    Assert-True ($catalogStatus.publication_state -eq 'CURRENT') 'reordering the keys staled the published catalogue'
    $chatPath = "/forge/v1/orgs/$smokeOrg/chat/completions"
    foreach ($alias in 'assistant', 'quiet') {
        $chat = Invoke-Send 'POST' $chatPath @{ model = $alias; messages = @(@{ role = 'user'; content = 'Hello' }); stream = $true } $memberToken
        Assert-True ($chat.Status -eq 200 -and $chat.Body -match 'data: \[DONE\]' -and $chat.Body -match '"content":"reply\."' -and $chat.Body -notmatch 'INFERENCE_UNAVAILABLE') "the member chat '$alias' did not stream through the failover ($($chat.Status) $($chat.Body))"
        Assert-True (-not $chat.Body.Contains($goodKey) -and -not $chat.Body.Contains($badKey)) 'a chat response carries a gateway key'
    }
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline -and (Get-Rows 'SELECT count(*) FROM forge.usage_events') -ne '2') { Start-Sleep -Milliseconds 500 }
    Assert-True ((Get-Rows 'SELECT count(*) FROM forge.usage_events') -eq '2') 'two chats did not record exactly two usage events (one per request, failover included)'
    Assert-True ((Get-Rows "SELECT count(*) FROM forge.usage_events e JOIN forge.gateway_keys k ON k.id = e.key_id WHERE k.label = 'smoke-good'") -eq '2') 'the usage events do not name the key that served after the failover'
    Assert-True ((Get-Rows "SELECT string_agg(usage_source || ':' || status, ',' ORDER BY usage_source) FROM forge.usage_events") -eq 'estimated:ok,gateway:ok') 'the gateway-reported and the estimated events are not both recorded'
    Write-Pass 'the member chat failed over from the rejected key, one event per request names the key that served; gateway usage and the estimate are both recorded'

    $today = [DateTime]::UtcNow.ToString('yyyy-MM-dd')
    $range = "from=$today&to=$today"
    $byCompany = (Invoke-Authenticated "/forge/v1/platform/usage/companies?$range" $ownerToken).Body | ConvertFrom-Json
    $row = @($byCompany.companies | Where-Object { $_.slug -eq 'smoke-co' })[0]
    Assert-True ($row.requests -eq 2 -and $row.cost_micros -eq 14 -and $row.unpriced_requests -eq 1 -and $row.estimated_requests -eq 1) "the platform per-company report is wrong ($($byCompany | ConvertTo-Json -Compress -Depth 4))"
    $byModel = (Invoke-Authenticated "/forge/v1/platform/usage/models?$range" $ownerToken).Body | ConvertFrom-Json
    Assert-True ((@($byModel.models | ForEach-Object { $_.upstream_id }) -join ',') -eq 'fake-fast,fake-nousage') 'the platform per-model report is wrong'
    $totals = (Invoke-Authenticated "/forge/v1/platform/usage/totals?$range" $ownerToken).Body | ConvertFrom-Json
    Assert-True ($totals.requests -eq 2 -and $totals.companies -eq 1) 'the platform totals are wrong'
    $people = Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/usage/members?$range" $smokeAdmin
    $person = ($people.Body | ConvertFrom-Json).members
    Assert-True ($people.Status -eq 200 -and @($person).Count -eq 1 -and $person[0].email -eq 'newhire@smoke.example.test' -and $person[0].requests -eq 2 -and $person[0].cost_micros -eq 14) "the company per-person report is wrong ($($people.Body))"
    Assert-True ((Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/usage/members?$range" $adminToken).Status -eq 404) 'another company administrator read this company usage'
    Assert-True ((Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/usage/members?$range" $memberToken).Status -eq 404) 'a plain member read the company usage'
    Assert-True ((Invoke-Authenticated "/forge/v1/platform/usage/totals?$range" $smokeAdmin).Status -eq 403) 'a company administrator read the platform usage'
    $trail = ((Invoke-Authenticated '/forge/v1/platform/audit' $ownerToken).Body | ConvertFrom-Json).entries | ForEach-Object { $_.action }
    Assert-True ((@($trail) -contains 'gateway_key.created') -and (@($trail) -contains 'company.gateway_assigned') -and (@($trail) -contains 'company.model_access_set') -and (@($trail) -contains 'model_price.set')) 'the key, assignment, ceiling and price changes are not audited'
    Write-Pass 'usage is visible per company, model and total to the owner and per person to the company administrator only; the changes are audited'

    # Governance: the catalog is seeded from the tools profile (the operator path), a member's signed policy verifies against the
    # published key set inside the control plane image, defaults and the attestation gate hold with zero company rows, the owner's
    # force-off lock beats the company administrator, every change is audited and the invocation log takes metadata only.
    function Invoke-ComposeStdin([string]$Stdin, [string[]]$Arguments) {
        $base = @('compose', '-p', $project, '--env-file', $envFile, '-f', (Join-Path $deploy 'compose.yml'), '-f', (Join-Path $deploy 'compose.dev.yml'))
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try { $output = ($Stdin | & docker @($base + $Arguments) 2>&1 | ForEach-Object { "$_" }) -join "`n" } finally { $ErrorActionPreference = $previous }
        return [pscustomobject]@{ Code = $LASTEXITCODE; Output = $output }
    }
    function Get-PolicyItems($Body) {
        $items = @{}
        foreach ($item in ($Body | ConvertFrom-Json).capabilities) { $items["$($item.kind):$($item.id)"] = $item }
        return $items
    }
    $seedArguments = @('run', '--rm', '-T', '--entrypoint', 'python', 'platform', '-m', 'forge.capability_seed', 'sync')
    $seeded = (Invoke-Compose $seedArguments -Global @('--profile', 'tools')).Output
    Assert-True ($seeded -match '"status": "synced"' -and $seeded -match '"created": (\d+)' -and [int]$Matches[1] -ge 100) "the catalog seed did not create the inventory ($seeded)"
    $seededAgain = (Invoke-Compose $seedArguments -Global @('--profile', 'tools')).Output
    Assert-True ($seededAgain -match '"created": 0' -and $seededAgain -match '"updated": 0') "a second seed run changes nothing, but it reported changes ($seededAgain)"
    Assert-True ([int](Get-Rows 'SELECT count(*) FROM forge.capability_catalog') -ge 100) 'the catalog holds fewer entries than the seed'
    Write-Pass 'governance: the catalog is seeded from the tools profile; a second seed run changes nothing'

    $keySet = Invoke-Curl '/forge/v1/capabilities/keys' -Arguments @('-H', "Origin: $origin")
    Assert-True ($keySet.Status -eq 200 -and $keySet.Body -match '"alg":"Ed25519"') "the public key set is not served ($($keySet.Status))"
    Assert-True ((Invoke-Curl '/forge/v1/capabilities/effective' -Arguments @('-H', "Origin: $origin")).Status -eq 401) 'the effective policy was served without a session'
    $verifyScript = "import json,sys,time;from forge.capability_signing import verify_document;d=json.load(sys.stdin);verify_document(d['doc'],d['keys'],now=time.time());print('verified',len(d['doc']['capabilities']))"
    $verify = { param($Document) Invoke-ComposeStdin ('{"doc":' + $Document + ',"keys":' + $keySet.Body + '}') @('exec', '-T', 'control-plane', 'python', '-c', $verifyScript) }
    $level2 = Invoke-Authenticated '/forge/v1/capabilities/effective?sandbox_level=2' $memberToken
    Assert-True ($level2.Status -eq 200) "the member could not read the effective policy ($($level2.Status) $($level2.Body))"
    $checked = & $verify $level2.Body
    Assert-True ($checked.Code -eq 0 -and $checked.Output -match 'verified \d+') "the signed policy does not verify against the published keys ($($checked.Output))"
    $forged = & $verify ($level2.Body -replace '"reported_level":2', '"reported_level":4')
    Assert-True ($forged.Code -ne 0 -and $forged.Output -match 'bad_signature') "a tampered policy was accepted ($($forged.Output))"
    $items2 = Get-PolicyItems $level2.Body
    Assert-True ($items2['skill:pdf'].state -eq 'on' -and $items2['connector:github'].state -eq 'on' -and $items2['plugin:bio-research'].state -eq 'off') 'the base skills and connectors are not on (or a plugin is) for a company with no policy rows'
    Assert-True ($items2['tool:code_execute'].state -eq 'blocked_attestation' -and $items2['tool:bash'].state -eq 'blocked_attestation' -and $items2['tool:browser'].state -eq 'off') 'the exec tools are not gated at level 2'
    $items3 = Get-PolicyItems (Invoke-Authenticated '/forge/v1/capabilities/effective?sandbox_level=3' $memberToken).Body
    Assert-True ($items3['tool:code_execute'].state -eq 'on' -and $items3['tool:bash'].state -eq 'blocked_attestation') 'level 3 does not open code_execute only'
    $items4 = Get-PolicyItems (Invoke-Authenticated '/forge/v1/capabilities/effective?sandbox_level=4' $memberToken).Body
    Assert-True ($items4['tool:bash'].state -eq 'on' -and $items4['tool:powershell'].state -eq 'on') 'level 4 does not open the shells'
    $items0 = Get-PolicyItems (Invoke-Authenticated '/forge/v1/capabilities/effective' $memberToken).Body
    Assert-True ($items0['tool:code_execute'].state -eq 'blocked_attestation') 'a missing level report was not treated as level 0'
    Write-Pass 'governance: the signed policy verifies inside the control plane image (a tampered copy fails); defaults and the attestation gate hold with no company rows'

    $epochBefore = ($level2.Body | ConvertFrom-Json).org_epoch
    $lock = Invoke-Send 'PUT' "/forge/v1/platform/companies/$smokeOrg/capabilities/connector:github" @{ state = $null; lock = 'forced_off' } $ownerToken
    Assert-True ($lock.Status -eq 200 -and ($lock.Body | ConvertFrom-Json).changed) "the owner could not force-off a connector for the company ($($lock.Status) $($lock.Body))"
    $locked = Invoke-Send 'PUT' "/forge/v1/orgs/$smokeOrg/capabilities/connector:github" @{ enabled = $true } $smokeAdmin
    Assert-True ($locked.Status -eq 409 -and $locked.Body -match 'LOCKED') "a force-off lock beats the company administrator, but the enable was not refused ($($locked.Status) $($locked.Body))"
    $disable = Invoke-Send 'PUT' "/forge/v1/orgs/$smokeOrg/capabilities/skill:pdf" @{ enabled = $false } $smokeAdmin
    Assert-True ($disable.Status -eq 200 -and ($disable.Body | ConvertFrom-Json).changed) 'the company administrator could not disable a skill'
    $afterDocument = (Invoke-Authenticated '/forge/v1/capabilities/effective?sandbox_level=2' $memberToken).Body
    $itemsAfter = Get-PolicyItems $afterDocument
    Assert-True ($itemsAfter['connector:github'].state -eq 'forced_off' -and $itemsAfter['connector:github'].reason -eq 'forced_off' -and $itemsAfter['skill:pdf'].state -eq 'off') 'the member policy does not show the lock and the administrator disable'
    Assert-True (($afterDocument | ConvertFrom-Json).org_epoch -eq $epochBefore + 2) 'the company epoch did not rise once per change'
    Assert-True ((& $verify $afterDocument).Code -eq 0) 'the updated policy does not verify'
    Assert-True ((Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/capabilities" $adminToken).Status -eq 404 -and (Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/capabilities" $memberToken).Status -eq 404) 'another company administrator or a plain member reached the company capability settings'
    $companyAudit = (Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/capability-audit" $smokeAdmin).Body | ConvertFrom-Json
    Assert-True ((@($companyAudit.entries | ForEach-Object { $_.action }) -join ',') -eq 'org.setting_set,company.policy_set') 'the company audit does not show the lock and the disable newest first'
    Assert-True ((Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/capability-audit" $adminToken).Status -eq 404) 'another company administrator read this company capability audit'
    Write-Pass 'governance: a force-off lock beats the company administrator, the member policy and epochs follow every change, and the change audit is scoped to the company'

    $eventId = [Guid]::NewGuid().ToString()
    $batch = @{ events = @(@{ event_id = $eventId; capability_id = 'tool:code_execute'; at = '2026-10-12T12:00:00Z'; outcome = 'ok'; duration_ms = 40; sandbox_level = 3 }) }
    $reported = Invoke-Send 'POST' '/forge/v1/capabilities/audit' $batch $memberToken
    Assert-True ($reported.Status -eq 202 -and ($reported.Body | ConvertFrom-Json).stored -eq 1) "the invocation batch was not stored ($($reported.Status) $($reported.Body))"
    Assert-True (($reported = Invoke-Send 'POST' '/forge/v1/capabilities/audit' $batch $memberToken).Status -eq 202 -and ($reported.Body | ConvertFrom-Json).stored -eq 0) 'a replayed event was stored twice'
    $content = @{ events = @(@{ event_id = [Guid]::NewGuid().ToString(); capability_id = 'tool:bash'; at = '2026-10-12T12:00:00Z'; outcome = 'ok'; duration_ms = 5; arguments = 'dir C:\' }) }
    Assert-True ((Invoke-Send 'POST' '/forge/v1/capabilities/audit' $content $memberToken).Status -eq 422) 'an invocation event with content was accepted'
    Assert-True ((Get-Rows 'SELECT count(*) FROM forge.tool_invocation_log') -eq '1') 'the invocation log does not hold exactly the one metadata row'
    Write-Pass 'governance: invocation metadata is stored once per event and content fields are refused'

    # Connector broker: a fixture OAuth provider and MCP server run beside the stack (compose.dev.yml, plain http, never published, reachable
    # by the control plane only through explicit egress fixtures). The owner registers the connector, the company administrator writes the
    # OAuth app write-only, the member connects through the public callback and calls tools through the proxy; the credential never reaches
    # the member, a force-off lock denies at once, and disconnecting stops brokering.
    $connectorEntry = @{ expected_revision = 0; entry = @{ version = '1.0.0'; risk = 'medium'; is_base = $true; default_state = 'on'; min_sandbox_level = 0; credential_locus = 'server'
        attributes = @{ name = 'Fixture'; category = 'dev-tools'; transport = 'mcp_http'; auth = 'oauth'; mcp_url = 'http://mcp.fixture.test/mcp'
            egress_hosts = @('oauth.fixture.test', 'mcp.fixture.test')
            oauth = @{ authorize_url = 'http://oauth.fixture.test/authorize'; token_url = 'http://oauth.fixture.test/token'; scopes = @('read', 'write'); revocation_url = 'http://oauth.fixture.test/revoke' } } } }
    Assert-True ((Invoke-Send 'PUT' '/forge/v1/platform/capabilities/connector:fixture' $connectorEntry $ownerToken).Status -eq 200) 'the owner could not register the fixture connector'
    $clientSecret = 'fixture-client-secret-0001'
    $secretValues = @($secretValues) + @($clientSecret)
    $credential = Invoke-Send 'PUT' '/forge/v1/connectors/connector:fixture/credential' @{ expected_revision = 0; kind = 'oauth_client'; client_id = 'fixture-client'; client_secret = $clientSecret } $smokeAdmin
    Assert-True ($credential.Status -eq 200 -and -not $credential.Body.Contains($clientSecret) -and ($credential.Body | ConvertFrom-Json).hint -eq '0001') "the OAuth app was not stored write-only ($($credential.Status) $($credential.Body))"
    Assert-True ((Invoke-Send 'PUT' '/forge/v1/connectors/connector:fixture/credential' @{ expected_revision = 0; kind = 'oauth_client'; client_id = 'x' } $memberToken).Status -eq 404) 'a plain member wrote a connector credential'
    $connectorStart = Invoke-Send 'POST' '/forge/v1/connectors/connector:fixture/oauth/start' $null $memberToken
    Assert-True ($connectorStart.Status -eq 200) "the member could not start the OAuth flow ($($connectorStart.Status) $($connectorStart.Body))"
    $authorizeUrl = ($connectorStart.Body | ConvertFrom-Json).authorize_url
    Assert-True ($authorizeUrl -like 'http://oauth.fixture.test/authorize?*' -and -not $authorizeUrl.Contains($clientSecret)) 'the authorize URL is not the connector endpoint or carries the client secret'
    $consentScript = "import sys,httpx;r=httpx.get('http://fake-connectors:3414/authorize?'+sys.argv[1],follow_redirects=False);print(r.status_code,r.headers.get('location',''))"
    $consent = (Invoke-Compose @('exec', '-T', 'control-plane', 'python', '-c', $consentScript, ([uri]$authorizeUrl).Query.TrimStart('?'))).Output.Trim()
    Assert-True ($consent -match '^302 (\S+)$') "the fixture provider did not redirect back ($consent)"
    $callback = [uri]$Matches[1]
    Assert-True ($callback.GetLeftPart([UriPartial]::Path) -eq "$origin/forge/v1/connectors/oauth/callback") "the redirect URI is not the configured public origin ($callback)"
    $connected = Invoke-Curl $callback.PathAndQuery
    Assert-True ($connected.Status -eq 200 -and $connected.Body -match 'Connected') "the public callback did not connect the member ($($connected.Status))"
    Assert-True ((Invoke-Curl $callback.PathAndQuery).Status -eq 400) 'a replayed OAuth callback was accepted'
    $listed = ((Invoke-Authenticated '/forge/v1/connectors' $memberToken).Body | ConvertFrom-Json).connectors | Where-Object { $_.id -eq 'connector:fixture' }
    Assert-True ($listed.status -eq 'connected' -and $listed.configured) 'the member status does not show the connector connected'
    Assert-True ((Get-Rows "SELECT count(*) FROM forge.connector_grants WHERE sealed LIKE '%at-%'") -eq '0') 'a grant holds plaintext token material'
    Write-Pass 'broker: the connector is connected through the public callback (state single-use, redirect URI from configuration, credential written write-only)'

    $mcp = '/forge/v1/mcp/connector:fixture'
    $initialize = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 1; method = 'initialize'; params = @{ protocolVersion = '2025-03-26' } } $memberToken
    Assert-True ($initialize.Status -eq 200 -and $initialize.Headers['mcp-session-id'] -eq 'fixture-session') "the broker did not relay initialize ($($initialize.Status) $($initialize.Body))"
    $echo = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 2; method = 'tools/call'; params = @{ name = 'echo'; arguments = @{ text = 'PRIVATE-SMOKE-TEXT' } } } $memberToken
    Assert-True ($echo.Status -eq 200 -and $echo.Body -match 'PRIVATE-SMOKE-TEXT') "the broker did not relay a tool call ($($echo.Status) $($echo.Body))"
    $echoHeaders = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 3; method = 'tools/call'; params = @{ name = 'headers'; arguments = @{} } } $memberToken
    Assert-True ($echoHeaders.Status -eq 200 -and $echoHeaders.Body.Contains('[redacted]') -and $echoHeaders.Body -notmatch 'at-[A-Za-z0-9_-]{20,}') 'a connector that echoes request headers handed the upstream credential back'
    Assert-True ($echoHeaders.Body -notmatch 'Bearer ') 'the echoed Authorization header was not scrubbed'
    foreach ($reply in $initialize, $echo, $echoHeaders, $connectorStart, $connected, $credential) { Assert-True (-not $reply.Body.Contains($clientSecret)) 'the OAuth client secret appeared in a response' }
    $blocked = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 4; method = 'sampling/createMessage'; params = @{} } $memberToken
    Assert-True ($blocked.Status -eq 403 -and $blocked.Body -match 'METHOD_NOT_ALLOWED') 'a server-to-client method was relayed'
    Write-Pass 'broker: the credential never reaches the member (header echo scrubbed, no secret in any response) and server-to-client methods are blocked'

    $lockFixture = Invoke-Send 'PUT' '/forge/v1/platform/capabilities/connector:fixture/policy' @{ state = $null; lock = 'forced_off' } $ownerToken
    Assert-True ($lockFixture.Status -eq 200) 'the owner could not force-off the connector'
    $denied = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 5; method = 'ping' } $memberToken
    Assert-True ($denied.Status -eq 403 -and $denied.Body -match 'CONNECTOR_DISABLED') "a force-off lock did not deny the broker at once ($($denied.Status) $($denied.Body))"
    Assert-True ((Invoke-Send 'PUT' '/forge/v1/platform/capabilities/connector:fixture/policy' @{ state = $null; lock = 'none' } $ownerToken).Status -eq 200) 'the owner could not lift the lock'
    Assert-True ((Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 6; method = 'ping' } $memberToken).Status -eq 200) 'lifting the lock did not restore the connector'
    Write-Pass 'broker: a force-off lock denies the next call at once and lifting it restores brokering'

    $metadata = Get-Rows "SELECT count(*) FROM forge.tool_invocation_log WHERE source = 'broker'"
    Assert-True ([int]$metadata -ge 4) "the broker logged $metadata metadata rows"
    Assert-True ((Get-Rows "SELECT count(*) FROM forge.tool_invocation_log WHERE source = 'broker' AND tool_name = 'echo'") -eq '1') 'the tool call was not logged by name'
    Assert-True ((Get-Rows "SELECT count(*) FROM forge.tool_invocation_log WHERE source = 'broker' AND method = 'sampling/createmessage'") -eq '0') 'a blocked method was logged as a call'
    $disconnect = Invoke-Send 'DELETE' '/forge/v1/connectors/connector:fixture/grant' $null $memberToken
    Assert-True ($disconnect.Status -eq 200 -and ($disconnect.Body | ConvertFrom-Json).disconnected) 'the member could not disconnect'
    $afterDisconnect = Invoke-Send 'POST' $mcp @{ jsonrpc = '2.0'; id = 7; method = 'ping' } $memberToken
    Assert-True ($afterDisconnect.Status -eq 409 -and $afterDisconnect.Body -match 'REAUTH_REQUIRED') 'a disconnected member could still use the connector'
    Assert-True ((Get-Rows 'SELECT count(*) FROM forge.connector_grants') -eq '0') 'disconnecting left the grant behind'
    $brokerAudit = ((Invoke-Authenticated "/forge/v1/orgs/$smokeOrg/capability-audit?page=20" $smokeAdmin).Body | ConvertFrom-Json).entries | ForEach-Object { $_.action }
    Assert-True ((@($brokerAudit) -contains 'connector.credential_set') -and (@($brokerAudit) -contains 'connector.connected') -and (@($brokerAudit) -contains 'connector.disconnected')) 'the credential, connection and disconnection are not audited'
    Write-Pass 'broker: disconnect destroys the grant and stops brokering; metadata (no content) and the change audit are recorded'

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
