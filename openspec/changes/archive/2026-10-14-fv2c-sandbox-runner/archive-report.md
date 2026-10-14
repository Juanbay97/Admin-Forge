# Archive report: fv2c-sandbox-runner

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-fv2c-sandbox-runner/`)
- Completed: 2026-10-13
- Mode: hybrid (files + Engram `sdd/fv2c-sandbox-runner/archive-report`)
- Summary: Sandbox tool runner with egress guard and attestation, real-container escape suite.
- Repo: client repo clients/openyak (nested git repo)
- Branches: client branches fv2c-sr-*
- Main commits: client 1f65297, b4d40e5, aa4cac9, 35cca6d, 19c589b, dcf9d09, f65e042, 00ef507, 70774df, a9c0269, 0ab64e8
- Tasks: 24/24 ticked
- Verification: No per-change verify-report.md. Evidence in forge-v2-program/verify-report.md: escape suite 15/15 OK; docker_runner 13/14 (one flaky teardown race, passes alone).
- Exceptions: Verification evidence is in the program report. Known flaky test test_a_timeout_removes_the_container_and_reports_it (race, not a leak). Real-container tests are slow (~30 s each).

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| egress-guard | Created | +4 added, 0 modified, 0 removed |
| sandbox-attestation | Created | +5 added, 0 modified, 0 removed |
| tool-runner | Created | +7 added, 0 modified, 0 removed |
