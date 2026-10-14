# Archive report: fv2c-desktop-owned-auth

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-fv2c-desktop-owned-auth/`)
- Completed: 2026-10-12
- Mode: hybrid (files + Engram `sdd/fv2c-desktop-owned-auth/archive-report`)
- Summary: Desktop owned auth: Entra removal, owned login, sidecar runtime, per-company distribution config.
- Repo: client repo clients/openyak (nested git repo)
- Branches: client branches fv2c-da-* (base feat/mvp-v1-wl-c4c-client-branding-e2e)
- Main commits: client 241adde, 0ab795c, f8485dd; CP tick 403da42, 7b90066
- Tasks: 21/21 ticked
- Verification: No per-change verify-report.md. Evidence lives in forge-v2-program/verify-report.md (client node --test 111 pass, client py test_forge_* 629 OK, cargo test 48 passed).
- Exceptions: Verification evidence is in the program report, not a change-level report.

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| desktop-company-distribution | Created | +5 added, 0 modified, 0 removed |
| desktop-owned-login | Created | +4 added, 0 modified, 0 removed |
| desktop-sidecar-runtime | Created | +3 added, 0 modified, 0 removed |
