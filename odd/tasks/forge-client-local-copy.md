# Forge client local copy

## Authorized outcome

Create an independent local OpenYak repository for future Forge client work.
Source: C:/Users/JuanpabloBayona/Documents/Codex/2026-09-28/referenced-chatgpt-conversation-this-is-an/work/openyak.
Destination: N:/Proyects/forge/clients/openyak (verified absent before creation).
Pinned tag: v1.5.0-rc.3.
Commit: a9adf9fb6c47db995eec414602294f7d7d769408.
Tree: f1a7ea39e303ceeb8d021087342d6d1d612d0fc6.
Available source history is shallow: one commit, not full upstream history.

## Tasks

- [x] L1: Verify clean pinned source, provenance and isolation requirements.
  Route: delegated direct; local repository and backend isolation checks.
  Source has 1,401 tracked files, no gitlinks, symlinks or LFS pointer matches.
  Source and default template hooks contain no active hook files; effective
  hooksPath/template override and GIT_TEMPLATE_DIR are absent.
- [x] L2: Create the independent clone from the local source, remove its generated
  origin, create feat/forge-client-shell at the pinned commit and prove exact tree.
  Route: delegated direct; cross-repository copy and controlled metadata changes.
- [ ] L3: Verify bytes/history/isolation, add FORGE_DEVELOPMENT.md only, update
  this full mirror and hand off for independent parent verification.
  Route: delegated direct; hash comparison and multi-file provenance documentation.

## Scope and constraints

Allowed paths relative to N:/Proyects/forge:
- .git/info/exclude (append only /clients/openyak/, preserve existing bytes)
- clients/openyak/** (new clone, its Git metadata and FORGE_DEVELOPMENT.md only)
- .worktrees/tenant-storage/odd/tasks/forge-client-local-copy.md

No upstream tracked-code edits, overwrite, deletion, submodule or backend gitlink.
No manual directory/.git copy, real keys, settings, application data, dependency
install, build, server, run, branding changes or remote operation.
No staging or commits until parent independently checks the copy.
Private GitHub creation/publication is deferred until the end and separately authorized.
RDD remains disabled; no native review or ownership/configuration repair.

## Delivery and verification

Forecast: fewer than 200 authored lines; copied upstream history is not authored
patch volume. Accepted delivery strategy: local feature-branch-chain.
No runnable RED applies to an unchanged source copy. Use exact commit/tree,
tracked-byte, shallow-history and repository-isolation checks instead.
Tests/build/install/runtime proof are intentionally not applicable in this task.

Clone only from the authorized absolute local source using --no-local,
--no-hardlinks, --no-checkout and --branch v1.5.0-rc.3.
Stop for unexpected active hooks or templates, changed source or existing target.
Verify no remotes, object alternates, shared hardlinks or inherited active hooks.
Verify source status/HEAD/tree unchanged afterward; preserve backend status and
index except this new untracked task. Confirm licenses remain present.

Before any later run/install, isolate application ID, data, protocol and updater.
Retain signed-update verification. Windows dependency validation remains pending.
No app customization, build readiness or full upstream history is claimed.

## Current status

Provenance and hook checks passed. Source is clean and destination/task were absent.
Backend root has only the preexisting untracked .atl/skill-registry.md; the active
backend worktree's eight existing dirty entries are held in memory for comparison.
An initial read-only PowerShell invocation failed empty; corrected invocation passed.
Local copy and writer verification are complete; independent parent verification\nand authorization to stage/commit remain pending.
Full mirror: project forge, topic odd/forge-client-local-copy/tasks.

## Copy verification evidence

Destination branch: feat/forge-client-shell; HEAD/tag peel and tree match above.
The clone is shallow with one commit. All 1,401 tracked working-tree files are
byte-identical to the source; no Git-filter mismatch was observed.
All 26 license-named files, including the Apache 2.0 root LICENSE, are preserved.
No copied .env, node_modules, .venv or venv paths exist in the tracked copy.
Destination has three object-pack files, each single-link and distinct from
source object identities; no alternates, remotes, gitlinks or active hooks exist.
Source HEAD/tree/status remain unchanged and clean. Before provenance creation,
destination status was clean; afterward only FORGE_DEVELOPMENT.md is untracked.
Backend root status is exactly unchanged. Active worktree status differs only by
this untracked task. Backend index has no client entry, and the exclusion file
equals its original bytes followed by exactly /clients/openyak/ plus LF.
No staging or commits occurred.

Clone emitted a warning that annotated tag object ca688ab50daef5a23d12d9e82a60ec13593b43ab
is not a commit; its peeled commit and checked-out tree match the pinned source.
The sandbox denied the initial task write despite a path grant; narrow elevated
write succeeded. No permissions, hooks or Git ownership protections were weakened.
Effective Git user.name/user.email were unset; no identity was invented or changed.
L3 remains open only for the parent's independent copy check and delivery decision.
