# Proposal: fv2c-sandbox-runner

Repo: `clients/openyak` (CL). Position in client queue: **2nd**, stacked on the last slice of `fv2c-desktop-owned-auth` (single writer; no code dependency, ordering only). Program: forge-v2 change #13.

## Intent

The managed client is deliberately tool-less (`tools=[]`, forge_workspace.py:348) because upstream tools are unsafe: `code_execute` runs in-process `exec()` with full builtins (`tool/builtin/code_execute.py:169`), `bash` passes the full environment and validates only cwd (`bash.py:22,76`), `resolve_and_validate` is a no-op without a workspace (`tool/workspace.py`), `web_fetch` has no SSRF guard. Product vision v2: Forge must be a strong sandbox. Decision: tools run on the employee machine through a runner interface that can later execute server-side; exec tools become default-ON **only when an adversarial escape suite passes on that machine**.

## Scope

### In Scope
- `ToolRunner` port + `RunSpec/RunResult/Attestation` types; `LocalSandboxRunner` (Windows) now; `DockerRunner`/WSL (optional per company) in a late slice; `RemoteRunner` is an interface stub only.
- Layers: workspace jail (canonicalisation, `..`, junctions/symlinks/reparse points, 8.3 names, ADS, UNC/device paths); scrubbed env allow-list; AppContainer (low privilege, no network capability, ACL-granted workspace + read-only runtime) + Job Object (CPU/mem/process count/kill-on-close); host-side egress guard + local forward proxy (deny loopback, link-local/metadata 169.254.169.254, RFC1918, CGNAT, IPv6 equivalents, DNS-rebind pinned; per-policy allow-list); wall-clock timeouts, output caps, process-tree kill.
- Adversarial escape suite (unittest-driven and runnable at runtime as a self-test): `..`, junction/symlink escape, env dump, loopback/metadata fetch, fork bomb, long-running, huge output, registry/user-profile writes.
- Attestation levels reported to the control plane (contract item) and gating exec tools: default-ON only if suite passes on that machine.
- Re-point `code_execute` (subprocess in sandbox, no in-process exec), `bash`, `web_fetch`/`web_search` (host-side through egress guard) to the runner; exposure controlled by a capability flag consumed later by `fv2c-capabilities-client`.

### Out of Scope
- Policy/enable UI and effective-policy consumption (`fv2c-capabilities-client`).
- Server-side execution implementation (interface only).
- Browser/computer-use/channels/automations (stay off).
- Kernel-level guarantees: this is defence in depth on an unsigned user-space app, not a security boundary against a determined local admin.

## Capabilities

### New Capabilities
- `tool-runner`: runner port, local Windows sandbox runner (jail, env scrub, limits, AppContainer, Job Object), optional Docker/WSL runner, server-ready interface.
- `egress-guard`: host-side HTTP egress guard and local forward proxy with SSRF/metadata/private-range denial and per-policy allow-list.
- `sandbox-attestation`: escape suite, attestation levels, per-machine cache, report to CP, exec-tool gate.

### Modified Capabilities
- None in main specs (builtin tool behaviour is changed under `tool-runner`).

## Approach

Honest layering (from exploration #3371): a Job Object alone does NOT restrict filesystem or network, so default-ON requires AppContainer + Job + egress guard. Network tools run in the host process via `EgressGuard`, never inside the sandbox, so the sandbox child has no network at all (sidesteps AppContainer loopback restriction). bash/PowerShell are not AppContainer-friendly: they remain opt-in via Docker/WSL runner; only `code_execute` (python subprocess) can be default-ON after the suite passes. Build order: pure logic first (jail, env, egress policy: portable, fully unit-testable) then Windows-native layers (ctypes), then the suite, then wiring.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/app/sandbox/` | New | runner, jail, env, limits, appcontainer, egress, proxy, docker_runner, suite, attestation |
| `backend/app/tool/builtin/{code_execute,bash,web_fetch,web_search}.py`, `tool/workspace.py` | Modified | route through runner/guard; no in-process exec |
| `backend/app/forge_workspace.py` | Modified (small) | expose runner + attestation (tools stay `[]` until capabilities-client) |
| `tests/test_sandbox_*.py` | New | strict-TDD suites |
| `docs/` | New | sandbox guarantees and non-guarantees |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| AppContainer via ctypes (CreateAppContainerProfile, ACL, STARTUPINFOEX, SECURITY_CAPABILITIES) is intricate; python runtime must be readable by the container | High | dedicated slice; bundled read-only runtime dir with explicit ACL; suite proves behaviour; failure -> level downgrade -> tools OFF |
| Cannot verify on other Windows builds/AV products/Win Home variants | High | per-machine self-test is the gate; attestation records OS build |
| Attestation is client-asserted, not trustworthy to CP | Med | treated as telemetry/UX gate; documented; server execution is the real fix |
| Escape suite false confidence | Med | suite versioned; cases named after real techniques; new escapes add cases |
| DNS rebinding / TOCTOU in jail | Med | resolve-then-pin IP for connect; open handles by fd with re-validation after open |
| Docker/WSL present here (Docker 28.1.1; WSL default distro docker-desktop) but company machines vary | Med | optional; auto-detect; no hard dependency |

## Rollback Plan

Stacked PRs; wiring slice (S9) is the only one touching existing tool behaviour: revert S9 to return to tool-less state (`tools=[]` untouched until capabilities-client). New package is dead code until wired.

## Success Criteria

- [ ] Escape suite green at level >= L3 on the dev Windows machine; failures demonstrably downgrade the level and keep exec tools OFF.
- [ ] No in-process `exec()` remains; `code_execute` runs in sandboxed subprocess.
- [ ] `web_fetch` blocks loopback/metadata/private/rebind targets.
- [ ] Attestation JSON validates against a schema and is queued for CP.
