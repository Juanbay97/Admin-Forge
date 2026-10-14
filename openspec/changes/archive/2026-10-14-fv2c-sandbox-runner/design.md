# Design: fv2c-sandbox-runner

## Technical Approach
New package `backend/app/sandbox/` (portable policy logic + Windows-native adapters via `ctypes`, no new third-party deps). Existing tools call `runner.run(spec)` / `egress.fetch(...)`. Layers compose; each reports success so the attestation level is derived from what actually passed the suite, not from what was configured.

## Architecture Decisions

### Decision: AppContainer + Job Object + host-side egress, not Job Object alone
**Choice**: L3 = AppContainer (no network capability) + Job Object + jail + env scrub; network tools execute in the host through `EgressGuard`.
**Alternatives**: Job Object only (cannot restrict FS/network -> fails suite); Docker/WSL mandatory (not on every machine, heavy); server-only execution (contradicts decision).
**Rationale**: matches exploration finding; child never needs the network, which also avoids AppContainer loopback exemptions.

### Decision: bash/PowerShell opt-in via container runner; `code_execute` is the default-ON candidate
**Choice**: shell tools need a broad Windows runtime that AppContainer cannot readily provide; they run only with L4 (Docker/WSL, per company).
**Rationale**: honest security > feature breadth; user decision #2 pending confirmation (reported in summary).

### Decision: Runner level is measured, not declared
**Choice**: `attestation.py` runs the suite through the real runner; level = highest layer set whose cases all passed. `exec_allowed` reads signed cache.
**Alternatives**: static config flag.
**Rationale**: a missing OS feature or AV interference downgrades safely.

### Decision: Jail resolves via handle, not string
**Choice**: open with `CreateFileW` + `GetFinalPathNameByHandleW`, reject reparse points (`FILE_ATTRIBUTE_REPARSE_POINT`) on every component, compare final path to canonical root; portable fallback (`os.path.realpath` + component lstat) for tests on non-Windows.
**Rationale**: defeats junction/8.3/ADS/TOCTOU that pure string checks miss.

### Decision: Attestation is advisory to the CP
HMAC-protected cache (DPAPI key) prevents casual tampering locally; CP cannot verify a client-asserted claim -> telemetry + UX gate only.

## Data Flow
```
tool call -> capability gate (later) -> exec_allowed(policy)? -> RunSpec
  -> jail.validate(paths) -> env.scrub -> LocalSandboxRunner
       CreateAppContainerProfile -> ACL(workspace rw, runtime ro) -> CreateProcess(STARTUPINFOEX, SECURITY_CAPABILITIES)
       -> AssignProcessToJobObject(limits) -> pipes (capped) -> wait/timeout -> kill tree
web_fetch -> EgressGuard.resolve+pin+deny -> httpx(pinned IP) -> capped body
```

## File Changes
| File | Action | Description |
|------|--------|-------------|
| `backend/app/sandbox/runner.py` | Create | `ToolRunner` protocol, `RunSpec/RunResult`, `RemoteRunner` stub |
| `sandbox/jail.py`, `env.py` | Create | path jail, env allow-list |
| `sandbox/limits_win.py` | Create | Job Object wrapper (ctypes) |
| `sandbox/appcontainer_win.py` | Create | profile, ACL, spawn |
| `sandbox/egress.py`, `proxy.py` | Create | guard + loopback proxy |
| `sandbox/docker_runner.py` | Create | Docker/WSL runner |
| `sandbox/suite/` (`cases.py`, `harness.py`), `attestation.py` | Create | escape suite, levels, cache, report queue |
| `tool/builtin/code_execute.py`, `bash.py`, `web_fetch.py`, `web_search.py`, `tool/workspace.py` | Modify | route via runner/guard, fail-closed |
| `tests/test_sandbox_*.py` | Create | per layer + suite |
| `docs/sandbox.md` | Create | guarantees/non-guarantees |

## Interfaces / Contracts
```python
@dataclass(frozen=True)
class RunSpec: argv: tuple[str,...]; cwd: Path; env: Mapping[str,str]; wall_s: int; cpu_s: int; mem_mb: int; max_procs: int; max_out: int
class ToolRunner(Protocol): level: int; async def run(self, spec: RunSpec) -> RunResult: ...
def exec_allowed(policy: SandboxPolicy) -> Decision: ...
```
**CP contract assumptions (fv2-capability-governance, not final)**: effective policy provides `sandbox: {runner: "local"|"docker", egress_allow: [hosts], min_level: 3}`; `POST /forge/v1/client/attestation` (hidden, session-authenticated, via router relay) accepts the report JSON from the spec; both optional until the CP ships them.

## Testing Strategy (strict TDD)
| Layer | What | Approach |
|---|---|---|
| Unit (portable) | jail, env, egress deny ranges (table-driven incl. IPv6/mapped), attestation level math, cache HMAC | `cd tests; ..\backend\.venv\Scripts\python.exe -m unittest test_sandbox_jail test_sandbox_env test_sandbox_egress test_sandbox_attestation` |
| Windows-native | Job Object limits, AppContainer spawn, ACLs | same runner, `skipUnless(sys.platform=="win32")`; real processes, short limits |
| Escape suite | each adversarial case contained | `test_sandbox_escape_suite` against real runner; runtime self-test reuses `suite/cases.py` |
| Tools | no `exec(`, tools use runner/guard | `test_sandbox_tools_wiring` |
| Docker | container runner | `skipUnless(docker available)`; Docker 28.1.1 present here, WSL default distro is docker-desktop |

## Migration / Rollout
Dead code until S9; S9 keeps `tools=[]` in `forge_workspace` (capabilities-client turns tools on). First run triggers background self-test; failure leaves exec OFF.

## Open Questions
- Python runtime for the child inside AppContainer: bundled embeddable Python in installer resources (ACL read-only) vs the sidecar exe; resolve in S5 spike test-first.
- Whether `CreateAppContainerProfile` works under user's AV/Windows Home (self-test answers per machine).
