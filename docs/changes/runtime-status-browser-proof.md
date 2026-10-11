# Reproduce the real local runtime status surface

## Current outcome

The actual unconfigured Forge runtime is running locally for parent-observed
browser proof. This is a read-only diagnostics surface, not a managed Windows
client or a login/chat demonstration. Browser observations are still pending.

- Actual runtime: http://127.0.0.1:8765/status; owned PID 20036.
- Isolated timing fixture: http://127.0.0.1:8766/status; owned PID 23936.
- Baseline: 48c3e8eaf14fe22073775fd60d18c3f26f34df71.
- No production source, test, migration or dependency edits.

Both helpers run hidden, bound exclusively to loopback, with access logging off.
Their child environments contain only required Windows/Python/temp values; no
real configuration or credential is supplied. PIDs are task-owned, not services
to keep running after this proof. Cleanup remains pending parent observation.

## Reproduce and distinguish the two servers

The actual server uses the unchanged factory:

    ./.venv/Scripts/python.exe -m uvicorn forge.runtime:create_runtime_app --factory --app-dir src --host 127.0.0.1 --port 8765 --no-access-log

The fixture at .local/runtime-test/c10b-fixture.py composes that same factory with
no configuration. One fixture-only async middleware delays /forge/v1/status;
all status assets and response semantics come from the actual application.
It exposes no mode-changing HTTP endpoint. It is not a production feature.

1. Open actual /status to inspect the genuine unconfigured state.
2. Open fixture /status and let its initial refresh complete.
3. Set .local/runtime-test/c10b-mode.txt to delay, then click Refresh status.
4. Capture the pending announcement/button state before the two-second response.
5. Set the file to timeout, click Refresh status, and wait beyond four seconds.
6. Restore normal and click Refresh status to observe recovery.

Write the selected mode locally with explicit UTF-8, never via the browser:

    [IO.File]::WriteAllText('N:/Proyects/forge/.worktrees/tenant-storage/.local/runtime-test/c10b-mode.txt', 'delay', [Text.UTF8Encoding]::new($false))

Allowed modes: normal (0s), delay (2s), timeout (6s). The actual production
status.js aborts its own fetch after 4000ms; the fixture does not synthesize its
error UI, change JavaScript or pretend to log a person in.
Changing the mode affects future status requests only. Keep the actual server
separate from fixture screenshots; clearly label artificial timing evidence.

The helper .local/runtime-test/c10b-launch.py records each exact owned PID and
command before checking readiness. It probes port availability by bind only;
it does not inspect or stop unrelated listeners. Preferred ports are 8765/8766,
with bounded alternate selection if occupied. Do not rerun the launcher while
these recorded servers are alive; keep their PID records for exact cleanup.

## Observed technical proof, not browser certification

- Existing runtime tests: 28 passed in 11.780s.
- Existing API tests: 18 passed in 0.987s.
- No skipped or failed tests in those completed runs.
- Both servers returned actual unconfigured status JSON.
- /status, /status.css and /status.js bytes matched source exactly on both servers.
- Server-side fixture timing measured delay=2.031s and timeout=6.016s.
- Mode was restored to normal after probes.

These HTTP probes prove serving and fixture timing, not browser rendering,
network-panel capture, keyboard completion or live screen-reader announcements.
Source contains role=status, aria-live=polite and a skip link; their presence is
not equivalent to accessibility certification. Parent owns supported cua evidence.

The first sandboxed TestClient run stalled and was interrupted; no pass is claimed.
A first sandboxed actual-server startup missed readiness; its exact recorded
PID 24536 was stopped and absence confirmed. Narrow approved escalation allowed
the two replacement owned servers and the completed test runs. No ownership,
dependency or global configuration change was used. Starlette's httpx TestClient
deprecation warning remains a nonblocking follow-up, not an upgrade authorization.

## Original-spec coverage and limits

Sources are the original external outputs/prometheon-forge/specs documents:
03-cliente-administrado.md (PF03, lines 5-27) and
12-validacion-roadmap.md (PF12, lines 27-28 and 44-46), read directly for this report.

| Requirement | What this proof establishes | Still missing |
|---|---|---|
| PF03 pinned OpenYak 1.5.0-rc.3 Windows managed client | Nothing about a client build; actual web diagnostics only | Scoped fork/client integration, packaging and version-pinned proof |
| Microsoft login, bootstrap, atomic profile, provider/MCP/skills, chat | Existing diagnostics clearly say no sign-in or access grant | End-to-end managed onboarding/profile/chat flow |
| Client signing_in/loading_profile/ready/degraded/suspended states | Only runtime fetch loading/failure can be observed here | Actual managed-client state machine |
| Organization/membership local namespaces | No client namespace behavior demonstrated | Independent local sessions/tokens/indexes/skills/preferences |
| PF12 CLI-01 clean-PC installation/login/use | Not exercised | Signed installer/clean-PC end-to-end proof without copied keys |
| PF12 CLI-02 local provider/policy mutation rejection | Not exercised by the status page | Actual managed-client local API enforcement |
| PF12 manual accessibility and recorded evidence | Reproducible timing fixture, exact build/PIDs/test results | Parent browser evidence and separate live screen-reader certification |

The next PF03 implementation should scope a real client-facing path against its
pinned source, rather than adding unused backend plumbing. This report neither
implements that client nor authorizes live staging credentials, paid inference,
public deployment, recovery/reassignment or other business-policy changes.

## Pending closure

Parent browser evidence, exact-owned-PID shutdown, final report reconciliation and
separate local commit authorization remain pending. RDD is OFF.
Task and recovery mirror: odd/tasks/forge-status-proof.md,
topic odd/forge-status-proof/tasks. Ignored c10b-* artifacts are not delivery files.

Owned-process readback requires the same narrow elevated context: sandboxed
Get-Process incorrectly reported the elevated helpers absent, while elevated
exact-PID readback and both loopback health probes confirmed them alive. Windows
venv redirectors also own child PIDs: actual 14356/22476 under 20036, fixture
24432/24392 under 23936. Retain these exact child IDs for complete owned cleanup;
never infer unrelated process ownership. Child records: c10b-owned-children.json.
