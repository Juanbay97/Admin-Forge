# Tasks: fv2c-sandbox-runner

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~7k |
| 400-line budget risk | High (budget in use: 800/slice) |
| Chained PRs recommended | Yes |
| Suggested split | 9 slices, one stack, SECOND in client queue |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units (branch prefix `fv2c-sr-`)

| Unit | Goal | Base | Est. lines |
|------|------|------|-----------|
| S1 | Runner port + types + `LocalSandboxRunner` L1 skeleton (subprocess, wall timeout) | last `fv2c-da-` slice (D8) | ~600 |
| S2 | Workspace jail (portable + Windows handle checks) | S1 | ~800 |
| S3 | Env scrub + output caps + tree kill + Job Object (`limits_win`) | S2 | ~800 |
| S4 | Egress guard (deny ranges, pinning, redirects, allow-list) + forward proxy | S3 | ~800 |
| S5 | AppContainer launcher + ACLs + runtime dir | S4 | ~800 |
| S6 | Escape suite cases + harness (against runner) | S5 | ~800 |
| S7 | Attestation levels, signed cache, report queue, `exec_allowed` | S6 | ~650 |
| S8 | Docker/WSL runner (optional) + suite in container | S7 | ~700 |
| S9 | Tool wiring: code_execute subprocess, web_fetch/search guard, workspace fail-closed, no `exec(` test, docs | S8 | ~800 |

## Phase 1: Foundation (S1-S2)
- [x] 1.1 RED `test_sandbox_runner`: RunSpec validation, timeout -> `timed_out`, RemoteRunner raises NotImplemented
- [x] 1.2 `sandbox/runner.py` + L1 runner; GREEN
- [x] 1.3 RED `test_sandbox_jail`: `..`, absolute, junction (created with `mklink /J` in temp), symlink if permitted, 8.3, ADS, `\\?\`, device names, post-open recheck, no-workspace fails closed
- [x] 1.4 `sandbox/jail.py`; GREEN

## Phase 2: Limits and egress (S3-S4)
- [x] 2.1 RED `test_sandbox_env`: allow-list only; secrets absent
- [x] 2.2 RED `test_sandbox_limits`: fork bomb contained (process cap), CPU/mem, huge output capped, tree kill, kill-on-close (Windows-only skips elsewhere)
- [x] 2.3 `env.py`, `limits_win.py`
- [x] 2.4 RED `test_sandbox_egress`: table of denied IPv4/IPv6/mapped/metadata, rebind pin, redirect hop, allow-list, size cap, proxy token
- [x] 2.5 `egress.py`, `proxy.py`

## Phase 3: AppContainer + suite (S5-S6)
- [x] 3.1 Spike test: spawn `python -c` in AppContainer with workspace ACL; decide runtime dir approach
- [x] 3.2 RED `test_sandbox_appcontainer`: no network, no profile/registry writes, workspace rw only
- [x] 3.3 `appcontainer_win.py`; GREEN
- [x] 3.4 `suite/cases.py` + `harness.py`; `test_sandbox_escape_suite` covers all nine adversarial families

## Phase 4: Attestation + container (S7-S8)
- [x] 4.1 RED `test_sandbox_attestation`: level math, HMAC cache tamper, 24h/OS-build invalidation, report schema without paths/env, bounded queue
- [x] 4.2 `attestation.py`, `exec_allowed`
- [x] 4.3 RED/GREEN `docker_runner` (skipUnless docker); `--network none`, ro root, caps drop, limits

## Phase 5: Wiring + docs (S9)
- [x] 5.1 RED `test_sandbox_tools_wiring`: no `exec(`/`eval(` of user code; `web_fetch` blocks internal targets; file tools fail closed without workspace
- [x] 5.2 Modify tools; keep `forge_workspace` `tools=[]` (assert unchanged)
- [x] 5.3 `docs/sandbox.md` guarantees/non-guarantees; record suite run output

Applied as slices `fv2c-sr-s1`..`fv2c-sr-s10` in `clients/openyak`. Tasks 1.1-5.3 done.

## Verification commands (record exact result per slice)
- py (from `clients/openyak/tests`): `..\backend\.venv\Scripts\python.exe -m unittest test_sandbox_runner test_sandbox_jail test_sandbox_env test_sandbox_limits test_sandbox_egress test_sandbox_appcontainer test_sandbox_escape_suite test_sandbox_attestation test_sandbox_tools_wiring -v`
- regression: existing `test_forge_*` router/launch modules
- Not agent-verifiable: other Windows builds, AV interference, WSL distro variety.

## Hardening

Batch applied in `clients/openyak` on top of `1f65297` (strict TDD, tip `b4d40e5`, local, no push). Goal: raise "Sandbox and extensions" to a sellable level by
attacking each isolation level with realistic techniques and fixing what gave way. Full threat model, per-level matrix and residual risks:
`clients/openyak/docs/sandbox.md`.

- [x] H1 Flaky `test_a_timeout_removes_the_container_and_reports_it` fixed in the product (`aa4cac9`). RED: the file failed on its own (baseline run) and a slow-removal
  `docker` shim (answers `rm -f` at once, removes 3 s later) failed deterministically. GREEN: the runner polls `docker ps -a` and re-issues `rm -f` until the
  container is gone (bounded, `ContainerNotRemoved` fails closed). Second defect found on the way: a flooding container hung `docker kill`/`rm -f` for over a
  minute (65.8 s RED) because the daemon waits for the client's full pipe; the client is now ended first. Docker file green 3/3 twice (124/142/121 s before the
  later slices, 223/166/148 s after them), no container left.
- [x] H2 Extensions in the real desktop runtime (`35cca6d`, `19c589b`). A Tauri window (Cargo example, Tauri 2.10.3, WebView2 155) serves a generated site through
  the Tauri protocol under the application's own `app.security`, mounts the real `AppCatalog`/`ExtensionHost`/prompt components and is driven over the WebView2
  DevTools port; 9 checks pass (hello renders in the script-only `srcdoc` frame; parent DOM, cookies, storage, popups, network blocked; loopback/IPC blocked from the
  frame; a granted native command works from the page and not from the frame; permission prompts allow/deny/no-flood; forged message and tampered entry refused).
  **Difference found and fixed:** Tauri added a sha256 to `script-src`, making the browser ignore `'unsafe-inline'`, so every extension's inline script was blocked in
  the desktop app (worked in Chrome). `dangerousDisableAssetCspModification: ["script-src","style-src"]` in `tauri.conf.json`; guarded by a node test. `AppCatalog` was
  unmounted: now the app launcher in `CapabilitiesScreen`; the capability panel is read-only. Chrome spec still 8/8.
- [x] H3 Sandbox gap review. Suite 1.1.0 (24 cases) adds: home secrets (SSH key, browser login store), outside writes through short names/streams/`\\?\`/`\\.\`/UNC/detours,
  IPv6 loopback, DNS rebinding, breakaway from the Job Object, child process reading the home, clipboard, window messages, Docker engine pipe, stderr flood, disk fill;
  `test_sandbox_attack_matrix` pins the result per level (L1/L2/L3/L4), `test_sandbox_cancel` proves no leftover process/container after cancel at every level,
  `test_sandbox_archives` covers zip-slip/tar/system tar/bombs. Level 3 contains everything; level 2 escapes files, home, loopback, Docker pipe (by design, exec requires 3).
  Real gaps fixed: one AppContainer shared by all workspaces (a run in B read A) -> one per workspace (`dcf9d09`); broad workspace (root/home/system/`.ssh`) refused
  (`workspace_rules`); no cap on bytes written to the workspace -> `disk_mb`/`disk_cap` (`f65e042`); `::/96` not denied by the egress guard (`00ef507`); archive member names
  (devices, streams, drive) and expanded size unchecked in the Ollama manager (`70774df`).
- [x] H4 Found while running the smoke: the suite prepared runners on the worker's event loop and each new workspace re-granted the Python directory (5 s, one ACL entry
  per workspace; 7 stale entries were found on the interpreter directory). Fixed: setup in a thread (`a9c0269`), runtime read granted once to ALL APPLICATION PACKAGES,
  entries detected by whole SID via `icacls /save` SDDL (`b4d40e5`).
- [x] H5 Docs (`0ab64e8`, `b4d40e5`): threat model, matrix, residual risks, WebView2 findings, hardening log in `clients/openyak/docs/sandbox.md`; `python -m app.sandbox.suite.report`
  prints the matrix.

Verification (Windows 10.0.26200, Docker 28.1.1): sandbox + stdio-host + capability modules 323 OK (4 skipped: symlink creation, 625 s); client py `test_forge_*` 629 OK (2 skipped, 315 s);
`node --test` 114 pass / 1 skipped; frontend unit 350 + managed 7 pass, `tsc --noEmit` clean; `cargo test` 48 pass; WebView2 spec 9/9; Chrome extension spec 8/8.
`scripts\mvp-smoke.ps1` (25 min bound): admin flow 9/9 and client flow 3/3 pass; the multi-user step fails (30 s waits for concurrent members' catalogue/chat) and **fails the same way on
the untouched baseline `1f65297`** (run during this batch), so it is pre-existing on this machine and not caused by this batch; both repositories and the four ports were left clean by every run.
Not agent-verifiable: other Windows builds, antivirus interference, a Docker daemon under different load, macOS/Linux.
Known pre-existing: `backend/tests/test_ollama` exec-bit test fails on Windows (POSIX permission semantics).
