# Archive report: v1-multiuser

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-v1-multiuser/`)
- Completed: 2026-10-11
- Mode: hybrid (files + Engram `sdd/v1-multiuser/archive-report`)
- Summary: Multi-user client: profile router, multi-org login and switching, scoped session revocation, multi-user smoke with clean-tree gate.
- Repo: control plane + client repo clients/openyak (nested git repo)
- Branches: feat/v1mu-cp1-pg-deflake, cp2-scoped-revocation, cp3-multiuser-smoke; client feat/mvp-v1-c1..c6
- Main commits: 0ac0b61, f1fa79f, 8f71005, 97e0e3a, cad51ba, 8c75d32, 295cdc5
- Tasks: 17/17 ticked
- Verification: verify-report.md present: PASS WITH WARNINGS (mvp-smoke PASS 228 s, branding-smoke PASS).
- Exceptions: none

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| gateway-origin-policy | Updated | +0 added, 1 modified, 0 removed |
| managed-client-launch | Updated | +1 added, 1 modified, 0 removed |
| member-administration | Updated | +0 added, 1 modified, 0 removed |
| mvp-local-runtime | Updated | +1 added, 0 modified, 0 removed |
| profile-router | Created | +4 added, 0 modified, 0 removed |
