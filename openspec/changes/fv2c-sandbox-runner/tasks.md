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
- [ ] 1.1 RED `test_sandbox_runner`: RunSpec validation, timeout -> `timed_out`, RemoteRunner raises NotImplemented
- [ ] 1.2 `sandbox/runner.py` + L1 runner; GREEN
- [ ] 1.3 RED `test_sandbox_jail`: `..`, absolute, junction (created with `mklink /J` in temp), symlink if permitted, 8.3, ADS, `\\?\`, device names, post-open recheck, no-workspace fails closed
- [ ] 1.4 `sandbox/jail.py`; GREEN

## Phase 2: Limits and egress (S3-S4)
- [ ] 2.1 RED `test_sandbox_env`: allow-list only; secrets absent
- [ ] 2.2 RED `test_sandbox_limits`: fork bomb contained (process cap), CPU/mem, huge output capped, tree kill, kill-on-close (Windows-only skips elsewhere)
- [ ] 2.3 `env.py`, `limits_win.py`
- [ ] 2.4 RED `test_sandbox_egress`: table of denied IPv4/IPv6/mapped/metadata, rebind pin, redirect hop, allow-list, size cap, proxy token
- [ ] 2.5 `egress.py`, `proxy.py`

## Phase 3: AppContainer + suite (S5-S6)
- [ ] 3.1 Spike test: spawn `python -c` in AppContainer with workspace ACL; decide runtime dir approach
- [ ] 3.2 RED `test_sandbox_appcontainer`: no network, no profile/registry writes, workspace rw only
- [ ] 3.3 `appcontainer_win.py`; GREEN
- [ ] 3.4 `suite/cases.py` + `harness.py`; `test_sandbox_escape_suite` covers all nine adversarial families

## Phase 4: Attestation + container (S7-S8)
- [ ] 4.1 RED `test_sandbox_attestation`: level math, HMAC cache tamper, 24h/OS-build invalidation, report schema without paths/env, bounded queue
- [ ] 4.2 `attestation.py`, `exec_allowed`
- [ ] 4.3 RED/GREEN `docker_runner` (skipUnless docker); `--network none`, ro root, caps drop, limits

## Phase 5: Wiring + docs (S9)
- [ ] 5.1 RED `test_sandbox_tools_wiring`: no `exec(`/`eval(` of user code; `web_fetch` blocks internal targets; file tools fail closed without workspace
- [ ] 5.2 Modify tools; keep `forge_workspace` `tools=[]` (assert unchanged)
- [ ] 5.3 `docs/sandbox.md` guarantees/non-guarantees; record suite run output

## Verification commands (record exact result per slice)
- py (from `clients/openyak/tests`): `..\backend\.venv\Scripts\python.exe -m unittest test_sandbox_runner test_sandbox_jail test_sandbox_env test_sandbox_limits test_sandbox_egress test_sandbox_appcontainer test_sandbox_escape_suite test_sandbox_attestation test_sandbox_tools_wiring -v`
- regression: existing `test_forge_*` router/launch modules
- Not agent-verifiable: other Windows builds, AV interference, WSL distro variety.
