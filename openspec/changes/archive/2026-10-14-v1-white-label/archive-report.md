# Archive report: v1-white-label

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-v1-white-label/`)
- Completed: 2026-10-12
- Mode: hybrid (files + Engram `sdd/v1-white-label/archive-report`)
- Summary: Per-company white-label: branding validators, sanitized logos, branding migrations 0025/0026, public branding API, themed admin and client, company code.
- Repo: control plane + client repo clients/openyak (nested git repo)
- Branches: feat/v1wl-w1a .. v3d; client feat/mvp-v1-wl-c1..c4c, g2
- Main commits: 547e94d, 4aff692, 77d71c3, ed257fe, d7bbecb, bbb377d, 89ec6dd, 841f631, 28be856, fe9f129
- Tasks: 19/19 ticked
- Verification: verify-report.md present. Its verdict was FAIL (one test-only regression) -> PASS WITH WARNINGS once fixed.
- Exceptions: Verify C1 (test fixture regression, tests/mvp_support.py LOGIN_ROLES vs pre-0025 DB) was fixed in 9b5cdeb and recorded in tasks; the verify-report itself was not re-issued. Verify report counted 14/14 tasks; tasks.md now has 19/19 ticked (V1-V3 slices added afterwards).

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| admin-branding | Created | +2 added, 0 modified, 0 removed |
| client-branding | Created | +4 added, 0 modified, 0 removed |
| client-rebrand | Updated | +0 added, 1 modified, 0 removed |
| org-branding | Created | +5 added, 0 modified, 0 removed |
