# Archive report: fv2c-capabilities-client

- Archived: 2026-10-14 (to `openspec/changes/archive/2026-10-14-fv2c-capabilities-client/`)
- Completed: 2026-10-13
- Mode: hybrid (files + Engram `sdd/fv2c-capabilities-client/archive-report`)
- Summary: Client capability policy client (signed policy pinning), connector secrets vault, capabilities UI, onboarding link, live attestation.
- Repo: client repo clients/openyak (nested git repo)
- Branches: client branches fv2c-cc-* (e.g. fv2c-cc-i1-onboarding-link, i2-attestation-live, i3-container-shells)
- Main commits: client 5b25df9, 154153e, e755a2c, 0216db3, 87f79b3, 4739317, 5392fb7, a6918dd, 9f52617, 1f65297
- Tasks: 14/14 ticked
- Verification: No per-change verify-report.md. Evidence in forge-v2-program/verify-report.md (test_forge_capabilities_*, forge_vault, policy tests pass).
- Exceptions: Program verify flagged stale unticked boxes (0/12); reconciled from client git log afterwards (12/12, later 14/14 with I-slices). Capabilities panel runtime proof not independently re-run.

## Specs synced to openspec/specs/

| Capability | Action | Details |
|---|---|---|
| capabilities-ui | Created | +2 added, 0 modified, 0 removed |
| capability-policy-client | Created | +5 added, 0 modified, 0 removed |
| connector-secrets-client | Created | +3 added, 0 modified, 0 removed |
