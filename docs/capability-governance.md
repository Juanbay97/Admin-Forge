# Capability governance

The control plane decides which tools, skills, connectors, plugins and apps each company's members may use, and hands every member's
device a **signed policy document** to enforce. Nothing here ships an app host or a sandbox runner: those live in the client.

## Who decides what

| Layer (highest wins) | Who writes it | Effect |
|---|---|---|
| Force-off lock (platform or per company) | platform owner | `forced_off`; a company administrator cannot change it (`409 LOCKED`) |
| Company administrator setting | company administrator | enable or disable one capability for the own company |
| Company override | platform owner | a default for one company |
| Platform default | platform owner | a default for every company |
| Catalog default | the seed / platform owner | what a new company gets with **zero rows** |

An id that is not in the catalog is `off`. A new company needs no rows: base skills and connectors are `on`, plugins and apps `off`, and
the execution tools are `on` only when the device proves it can contain them (below).

## Attestation levels (the client's scale, 0-4)

The device measures its own isolation and reports the level; the control plane **echoes it into the signed document and gates on it**.
`code_execute` needs **3**; `bash` and `powershell` need **4** because the client only runs shells in the container runner.

| Level | Meaning |
|---|---|
| 0 | none (also: no report, or a malformed one) |
| 1 | workspace jail and environment scrub |
| 2 | isolated process with limits (Job Object) |
| 3 | level 2 plus egress guard and a passing escape suite (AppContainer) |
| 4 | container runner (Docker) |

Below its minimum an enabled exec tool resolves `blocked_attestation`; no administrator setting can lift that. **The report is
client-reported and spoofable**: it is advisory telemetry for the server, and the local gate in the client is what really keeps
exec tools off.

### The attestation report (`POST /forge/v1/client/attestation`)

The device posts its self-test result after the sandbox suite runs (hidden route, member session, `?org=` when the session has several
companies): `{level 0..4, suite_version, client_version, os_build, cases:[{id, passed}] (at most 64), at}` and nothing else. Any other
field (a path, an environment value, a prompt) rejects the whole report with `422`; the answer is `202 {level, stored}`. Reports are kept
in an append-only, member-bound log (migration 0047: SELECT and INSERT only, no role can update or delete, no content column): who
(the member of the session, never the payload), which company, what was reported and when (`at` from the device, `recorded_at` from the
server). The same device time is a replay (`stored: false`) and at most 24 reports per member per day are kept. This log is the audit
trail of what each device claimed.

**Effective policy uses the latest attestation.** `GET /capabilities/effective` resolves with the *lower* of the level the request claims
(`?sandbox_level=`) and the member's newest attestation of the last 30 days: a claim can lower the level but never raise it above what the
device last attested; without a claim the attested level is used; without a recent attestation the claim is used as before (0 when there
is none). The signed document's `reported_level` is the level actually used. An attestation older than 30 days proves nothing about the
device now and is ignored.

## Routes

All routes are hidden from the published API contract (`include_in_schema=False`); the MVP contract pin is unchanged.

| Who | Route |
|---|---|
| Platform owner (MFA) | `GET /forge/v1/platform/capabilities`, `PUT .../capabilities/{id}` (`expected_revision` 0 creates), `PUT .../capabilities/{id}/policy`, `GET\|PUT .../companies/{org}/capabilities[/{id}]`, `GET .../capability-audit` |
| Company administrator | `GET /forge/v1/orgs/{org}/capabilities`, `PUT .../capabilities/{id}` with `{"enabled": true\|false\|null}`, `GET .../capability-audit` |
| Member | `GET /forge/v1/capabilities/effective?sandbox_level=N[&org=...]`, `POST /forge/v1/capabilities/audit`, `POST /forge/v1/client/attestation[?org=...]` |
| Anyone | `GET /forge/v1/capabilities/keys` (the public key set) |

Ids are `<kind>:<slug>` (`skill:pdf`, `tool:code_execute`, `app:acme.hello`). A company administrator who targets another company, a
member, and a missing company all get the same `404`.

## The signed document

`GET /forge/v1/capabilities/effective` returns `{schema, org, platform_epoch, org_epoch, issued_at, expires_at (24 h), reported_level,
capabilities[], kid, sig}`, signed with Ed25519 over canonical JSON. The client rejects a bad signature, an unknown `kid`, an expired
document and lower epochs than it has seen. Items use the bare slug as `id` plus `kind`, `state` (`on`, `off`, `forced_off`,
`blocked_attestation`), `enabled` and, when not on, `reason`; apps also carry `manifest_sha256` (the entry pin the client checks) and
only their **granted** permissions. The document, the canonicalization rule and signature test vectors are pinned in
[`contract/forge-capability-policy.v1.json`](../contract/forge-capability-policy.v1.json) (`python -m forge.capability_contract --check`).

Without a signing key the effective and keys routes answer `503`: nothing unsigned is ever served.

## Operating it

### Signing key

`scripts/deploy-secrets.(sh|ps1)` creates `policy_key` (32 random bytes: an Ed25519 seed). The control plane reads it from
`FORGE_POLICY_KEY_FILE` (compose already wires `/run/secrets/policy_key`); the local stack generates a throwaway one. **Back it up
offline.** Losing it means clients cannot verify new documents until a new key is published and trusted; rotating keeps the old
public key in the published set only when it is supplied as a retired key (not yet wired into the deployment configuration: rotate
by replacing the secret and re-trusting the new `kid`; key pinning at the client is still an open decision).

### Seeding the catalog

```
docker compose --profile tools run --rm --entrypoint python platform -m forge.capability_seed sync
```

Runs with the database administrator credential, in one transaction: it creates missing entries (25 skills, 46 connectors, 15 plugins,
the built-in tools and the governed groups), never overwrites what a platform owner changed, and a second run changes nothing. Add
`--update` to apply the seed's values over existing entries (revision bumps, audited with no actor).

### Audit

* **Changes**: every catalog, platform, company and administrator change appends who, what, which company, before and after and when,
  in the same transaction; rows are append-only for every role. A company administrator reads only the own company.
* **Invocations**: devices post batches of at most 100 `{event_id, capability_id, at, outcome, duration_ms, sandbox_level}`; any other
  field (arguments, output, a prompt) rejects the whole batch with `422`. Replays are deduplicated by `event_id`. No content is stored.

## Threat model in one paragraph

The attestation is reported by the device and can be forged by a modified client; governance still makes the *default* safe (exec
off without proof) and gives the platform an immediate kill switch (force-off, epoch bump). The database re-validates the session and the
role on every call, the policy document is signed so a proxy cannot flip a state, and the audit is append-only metadata with no content.
