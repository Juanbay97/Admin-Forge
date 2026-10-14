# Tool Runner Specification

## Purpose
All tool execution goes through a `ToolRunner` interface so the same tools can run locally in a sandbox, in an optional container, or later on a server.

## Requirements

### Requirement: Runner interface

A `ToolRunner` MUST accept a `RunSpec` (argv, jailed cwd, env allow-list, limits, network mode `none`) and return a `RunResult` (exit code, truncated stdout/stderr, timed_out, killed_reason, runner level). Implementations: `LocalSandboxRunner`, `DockerRunner`; `RemoteRunner` is a typed stub raising `NotImplemented`.

#### Scenario: Selection
- GIVEN a company policy `runner=local|docker`
- WHEN a tool executes
- THEN the matching runner is used; if it is unavailable or below the required level the call fails closed with a clear error

### Requirement: Workspace jail

Every path handed to a tool MUST be canonicalised and MUST resolve inside the workspace root; `..`, absolute paths outside, symlinks, junctions and other reparse points, 8.3 short names, alternate data streams, UNC and device paths (`\\?\`, `\\.\`, `CON`) that escape MUST be rejected. Validation MUST also run after open to defeat check-then-use races.

#### Scenario: Traversal
- GIVEN workspace `W`
- WHEN a tool requests `W\..\..\Users\x\secret.txt`
- THEN the call is rejected before any file operation

#### Scenario: Junction escape
- GIVEN a junction `W\link` -> `C:\Users\x`
- WHEN a tool reads `W\link\secret.txt`
- THEN the call is rejected

#### Scenario: No workspace
- GIVEN no workspace is configured
- WHEN any file tool runs
- THEN it fails closed (replaces the current no-op `resolve_and_validate`)

### Requirement: Scrubbed environment

The child environment MUST be built from an allow-list (e.g. `PATH` limited to the sandbox runtime, `TEMP` inside workspace scratch, locale); all other variables, including tokens, `FORGE_*`, `PG*`, cloud credentials and the parent's `USERPROFILE/APPDATA`, MUST be absent.

#### Scenario: Env dump
- GIVEN the parent has `FORGE_SESSION_TOKEN=secret`
- WHEN the child runs `set` / `os.environ`
- THEN the secret and every non-allow-listed variable are absent

### Requirement: Resource limits

Local execution MUST apply a Job Object with kill-on-close, active-process limit, memory limit and CPU-time limit, plus wall-clock timeout, stdout/stderr byte caps and process-tree kill on timeout or parent exit.

#### Scenario: Fork bomb
- GIVEN a child that spawns processes unboundedly
- WHEN it exceeds the process limit
- THEN spawning is refused/terminated and the host remains responsive

#### Scenario: Long-running
- GIVEN a child that sleeps beyond the wall-clock limit
- WHEN the limit expires
- THEN the whole tree is killed and `timed_out=true`

#### Scenario: Large output
- GIVEN a child printing 1 GiB
- WHEN the cap is reached
- THEN output is truncated, the child is terminated, memory use stays bounded

### Requirement: AppContainer isolation

The default-ON local runner MUST launch children in an AppContainer with no network capabilities, write access only to the workspace (and scratch) via explicit ACLs, read-only access to the runtime directory, and no access to the user profile or registry hives outside the container.

#### Scenario: Profile and registry writes
- GIVEN a child attempts to write `%USERPROFILE%\x` or `HKCU\Software\x`
- WHEN executed
- THEN access is denied

### Requirement: Optional container runner

When enabled by company policy, a Docker/WSL runner MAY execute bash/PowerShell in a container with workspace bind-mount only, `--network none`, read-only root, dropped capabilities, and pids/memory/CPU limits; it MUST NOT be required.

#### Scenario: Docker absent
- GIVEN policy requests `docker` but Docker is not installed
- WHEN a tool executes
- THEN it fails closed; exec tools remain OFF

### Requirement: No in-process execution

`code_execute` MUST NOT use in-process `exec()`/`eval`; it MUST run in a runner subprocess.

#### Scenario: Static check
- GIVEN the tool package
- WHEN the test scans for `exec(`/`eval(` of user code
- THEN none exist
