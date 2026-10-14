# Archive report: fv2-connector-broker

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-fv2-connector-broker/`)
- Completed: 2026-10-13
- Mode: hybrid (files + Engram `sdd/fv2-connector-broker/archive-report`)
- Summary: Connector broker: sealed credentials, OAuth+PKCE, MCP proxy with per-call authorization, SSRF-hardened egress guard, hidden routes and deploy smoke.
- Repo: control plane (.worktrees/web, branch feat/fv2-gap-g8-policy-key-rotation)
- Branches: feat/fv2-connector-broker-b1-core .. b6-hardening-smoke-docs
- Main commits: a519f4a, cd25dfd, abdf7ee, 6fb0cb3, a1ac460, c84948c, 8b3e2d4
- Tasks: 16/16 ticked
- Verification: No per-change verify-report.md. Latest verify covers it: forge-v2-program/verify-report.md (CP 5ad37f8 + reconciliation, PASS WITH WARNINGS, CRITICAL none). Tasks include ticked verification items.
- Exceptions: none

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| connector-egress | Created | +1 added, 0 modified, 0 removed |
| connector-oauth | Created | +2 added, 0 modified, 0 removed |
| connector-secrets | Created | +4 added, 0 modified, 0 removed |
| mcp-broker | Created | +3 added, 0 modified, 0 removed |
