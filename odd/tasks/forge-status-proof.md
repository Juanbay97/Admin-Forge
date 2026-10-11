# Forge local runtime status browser proof

## Outcome and scope

C10b proof only: demonstrate the actual read-only local /status surface and record
its limits against original PF03/PF12 client requirements. No production source,
tests, migrations, dependencies, real account configuration or deployment changes.
This task precedes fixture/evidence artifact writes. Parent owns browser automation
and supplies observations; no network-panel or screen-reader proof is inferred.

Baseline: 48c3e8eaf14fe22073775fd60d18c3f26f34df71.
Branch: feat/forge-tenant-storage. RDD remains OFF, disabled/unmanaged.
Existing local feature-branch-chain applies; no commit before parent validates proof.

## Checkpoints

- [x] P1: Read actual status assets/runtime and prepare this full task/mirror.
  Route: delegated direct; bounded fixture preparation and verification.
- [x] P2: Rerun existing 28 runtime and 18 API tests; report observed counts/times.
- [x] P3: Launch owned hidden actual unconfigured factory on loopback, starting
  with port 8765. Record PID and URL; never stop or inspect unrelated occupants.
- [x] P4: Launch isolated test fixture on another loopback port, initially 8766,
  serving exact actual status assets and delaying only /forge/v1/status.
  Local mode file selects normal, delay (2 seconds), timeout (6 seconds).
  No HTTP control endpoint, live identity, fake managed login/chat or source edits.
- [ ] P5: Parent browser observes actual status and click-triggered loading/timeout;
  record only received evidence with unavailable evidence explicitly bounded.
- [ ] P6: Stop exact owned PIDs on parent request, record cleanup, reconcile
  task/report/mirror, then wait for separate commit authorization.

P3/P4 keep owned processes alive only for parent observation. Start-Process must
use WindowStyle Hidden. If preferred port cannot bind, choose another local port;
do not inspect or terminate its occupant. Only loopback HTTP probes are permitted.

## Verification and expected observations

    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_runtime.py -v
    ./.venv/Scripts/python.exe -m unittest discover -s tests -p test_api.py -v
    git diff --check

Actual factory: existing venv python -m uvicorn forge.runtime:create_runtime_app
--factory --app-dir src --host 127.0.0.1 --port <owned-port> --no-access-log.
The unconfigured factory must not contact an identity provider or database.
The isolated fixture composes the same factory without configuration and wraps
only its status JSON request with a selected async delay. Asset bytes remain exact.
Production status.js aborts fetch after 4000ms and disables Refresh while pending.

Parent opens actual /status for read-only unconfigured labels, then isolated /status.
After initial render, write mode delay or timeout locally and click Refresh in the
supported browser. Observe pending/disabled state and eventual success or failure.
Normal mode restores immediate status. No real credentials or operator authority.

## Specification boundaries

PF03/PF12 Windows managed OpenYak login, bootstrap/profile and chat are not
implemented by this local status page. Read-only runtime diagnostics are available.
A next PF03 step should scope a real client, not unused additional backend plumbing.
Exact source/spec path references will be recorded after bounded readback.
Browser accessibility inspection is not live screen-reader certification.

## Allowed edit surfaces

- odd/tasks/forge-status-proof.md
- docs/changes/runtime-status-browser-proof.md
- README.md
- .local/runtime-test/c10b-*

Protect all production source, tests and migrations. No Gentle/CodeGraph retry,
dependency installation, ownership changes, public exposure, remote or deployment.
English artifacts use explicit UTF-8. RED is not applicable to passive proof/docs;
existing deterministic regressions and honest observed runtime evidence apply.
No browser automation from this worker; parent owns cua.

## Current evidence and next step

Launch-ready checkpoint. Existing 28 runtime tests passed in 11.780s;
18 API tests passed in 0.987s. Actual source uses /forge/v1/status and a
4000ms client abort timeout. A speculative docs/specs directory lookup was absent;
no files changed by that lookup. Full task mirror readback preceded fixture writes.
Mirror topic: odd/forge-status-proof/tasks. Parent browser evidence is pending. No screen-reader, network-panel, managed-login or chat claim.


## Owned live helpers and observed startup

Actual http://127.0.0.1:8765/status, PID 20036, started 2026-10-05T20:07:44Z.
Fixture http://127.0.0.1:8766/status, PID 23936, started 2026-10-05T20:07:54Z.
Both use hidden CREATE_NO_WINDOW child processes, explicit loopback bind, no access
logging and minimal child environment. No real config, identity or DB calls.
Local mode file .local/runtime-test/c10b-mode.txt is currently normal.
Write delay (2s) or timeout (6s) before clicking Refresh status on the fixture;
restore normal for recovery. Mode changes never affect the actual server.

Direct owned HTTP probes confirmed both actual JSON states and exact byte equality
for all three status assets. Server-response timings: 2.031s and 6.016s; no browser
rendering, network capture or screen-reader proof is claimed from those probes.
Startup/PID/asset/timing JSON and test logs are ignored c10b-* files.

Initial sandbox TestClient stalled and was interrupted. Initial actual launch
missed readiness; exact owned PID 24536 was stopped and absence confirmed before
narrow approved escalation launched the recorded replacements. Both completed
regression suites passed without skips. Deprecation warning is nonblocking.
No ownership, dependency, source, test or global configuration changes occurred.
Original external PF03/PF12 were read directly; report records unmet managed
Windows login/profile/chat/namespace and clean-PC requirements. No mock client.

Next: parent operates supported browser against the two URLs, reports observed
loading/timeout/recovery and any evidence limits, then requests exact-PID shutdown.
Do not commit until parent validates the browser evidence and authorizes delivery.

Owned-process readback requires the same narrow elevated context: sandboxed
Get-Process incorrectly reported the elevated helpers absent, while elevated
exact-PID readback and both loopback health probes confirmed them alive. Windows
venv redirectors also own child PIDs: actual 14356/22476 under 20036, fixture
24432/24392 under 23936. Retain these exact child IDs for complete owned cleanup;
never infer unrelated process ownership. Child records: c10b-owned-children.json.
