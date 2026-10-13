# Verify report: forge-v2 program (CP 5ad37f8, client 1f65297)

Verdict: PASS WITH WARNINGS. Mode: hybrid. Fast checks only; full smokes (mvp, branding, admin-e2e 26/26, deploy 34/0) were not re-run.

## Check results
| Check | Result |
|---|---|
| CP unittest discover (1670 tests) | 0 non-PG failures. 438 errors are all "Real PostgreSQL required" (PG-gated, not run here; covered by the earlier smokes). 11 skipped |
| `forge.contract --check`, `forge.capability_contract --check` | exit 0 / 0 |
| test_deploy_artifacts + test_deploy_proxmox_guide | 100 OK |
| admin `npm run test:unit` (includes the Playwright UI specs) / `tsc --noEmit` | 501 passed / exit 0 |
| client `node --test` (all 19 files) | 111 pass, 0 fail, 1 skipped |
| client py `test_forge_*` (backend .venv) | 629 OK, 2 skipped |
| client py `test_sandbox_*` | 10 of 12 files OK. `docker_runner` and `escape_suite` did not finish: real-Docker tests stalled past 70 s per file (at `test_runs_killed_early_leave_no_container_behind`). INCONCLUSIVE, not a proven failure |
| client frontend `test:unit` / tsc | 348 passed / exit 0 |
| cargo test (src-tauri) | 48 passed |

## (a) Unticked tasks
- fv2-gap-closure H4.2: BLOCKED. `forge-multiuser-flow` also fails at baseline 10b5509 ("Models unavailable"). It is a client-side diagnosis that is still open.
- fv2c-capabilities-client: 0/12 ticked. fv2c-superapp-host: 0/9 ticked.
  - Capabilities-client code and tests exist: `test_forge_capabilities_*`, `forge_vault` and the policy tests all pass. Its ticks are stale. Core tasks 5.x (route and panel) were not checked in detail.
  - superapp-host: `test_forge_extensions` and `test_forge_stdio_host` pass. The Playwright UI spec (2.3) and the ExtensionHost/AppCatalog UI (2.4) are not confirmed built.
- All other 14 changes are fully ticked.

## (b) Spec-to-evidence coverage
Sampled per change. Each has green unit tests, PG/e2e coverage through the earlier smokes, and contract vectors.
Gaps: the superapp-host UI, the capabilities panel, and the real-container sandbox suites without a runtime pass today.

## (c) Security
- Super-admin isolation: roles are NOBYPASSRLS. The only BYPASSRLS role is `backup_reader`: it is read-only, restricted to the backup job, and documented.
- CSP: the admin shell uses `default-src 'none'; script-src 'self'; style-src 'self'; frame-ancestors 'none'`. Brand assets get `sandbox`. The connector page allows inline style only.
- Present and test-covered: TOTP (`platform_totp`, mandatory enrolment, recovery codes), Fernet-sealed keys, signed policy with Ed25519 and rotation statements, client pinning, broker egress guard, sandbox escape suite.
- Not re-proven at runtime today: the live container sandbox (see above).

## Issues
CRITICAL: none.
WARNING:
1. Docker sandbox tests stalled. Re-run them on a quiet Docker host.
2. Stale tick boxes in fv2c-capabilities-client and fv2c-superapp-host.
3. H4.2 `forge-multiuser-flow` is unresolved. It is a client E2E that is red at baseline, and it is the only multi-org chat proof.
4. The repo has no git remote, and the work is on branch `feat/fv2-gap-g8-policy-key-rotation`. The guide's `git clone <repository-url>` needs the code pushed somewhere first.
5. The installer is unsigned (SmartScreen warns) and the installer build is manual. Optional NSIS rebuild not run.
SUGGESTION: add a CI job with PG for the 438 gated tests. Note the Playwright specs run inside `test:unit`, so that command is slow (~8 min).

## (d) Deployability
Verdict: YES, with one prerequisite. The guide covers Docker, DNS/ports, ACME Let's Encrypt, Resend STARTTLS/587, owner bootstrap and TOTP, the OmniRoute key in the console, the first company, installer publishing, client install via `forge-install.json`, and backup/upgrade. It is guarded by drift tests against deploy/, and deploy-smoke 34/0 passed.
Blockers:
- No pushed remote (see warning 4).
- Untested on a real public ACME run and on real Resend.
- The Windows client has to be built manually with the origin compiled in.
- The private-CA path for OmniRoute is documented, but only the public-cert path is plain.

## (e) Readiness (1-10)
| Area | Score |
|---|---|
| Deploy / runtime | 8 |
| Platform core / keys / metering | 8 |
| Governance / broker | 7 |
| Web console / portal | 8 |
| Client auth / branding | 7 |
| Sandbox / extensions | 5 (superapp-host UI unconfirmed, real-container tests stalled) |
| Multi-user E2E | 5 |
| Overall | 7 |
## Reconciliation (post-verify, same CP 5ad37f8 / client 1f65297)
- Ticks corrected from client `git log` and files at HEAD: fv2c-capabilities-client 12/12 (K1-K5d, I1-I5 recorded), fv2c-superapp-host 9/9, fv2-gap-closure H4.2 ticked. Warning 2 and the H4.2 part of warning 3 are closed. Every tick carries a commit hash.
- H4.2: `forge-multiuser-flow` passes after `231e024` (control plane) and `b45a076` (client); `mvp-smoke` multi-user 1/1 in three later runs.
- Docker sandbox on a quiet host (`backend\.venv\Scripts\python.exe -m unittest` from `tests/`): `test_sandbox_escape_suite` 15/15 OK in 197 s. `test_sandbox_docker_runner` 13/14 in 430 s, no stall. The one failure, `test_a_timeout_removes_the_container_and_reports_it`, listed `forge-sandbox-549274d7776f` right after the timeout while it was still being removed. Alone it passed in 4 s and the container was gone, so it is a flaky race and not a leak. No containers were left behind. Warning 1 is downgraded to a flaky-test note. The runner tests are slow (about 30 s per real container), which explains the earlier 70 s stall.
- Still open: no evidence for a runtime pass of the Playwright extension spec or the Tauri webview in this reconciliation (spec and UI files exist; not re-run here).