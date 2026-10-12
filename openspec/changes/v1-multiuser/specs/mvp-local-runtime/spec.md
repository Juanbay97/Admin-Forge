# Delta for MVP Local Runtime

## ADDED Requirements

### Requirement: Multi-user smoke and clean tree

`scripts/mvp-smoke.ps1` MUST run, in one client run, two members of one org and one member of another concurrently in separate browser contexts, and MUST fail if tracked files in either repo are modified by the run.

#### Scenario: Concurrent isolation
- GIVEN the seeded stack and one managed client
- WHEN three members chat concurrently
- THEN each sees only its own sessions and no cross-org data, and three profile directories exist

#### Scenario: Dirty tracked file
- GIVEN a build that rewrites a tracked file
- WHEN the smoke finishes
- THEN it reports failure naming the file

#### Scenario: Clean run
- GIVEN no tracked file changes
- WHEN the smoke finishes
- THEN `git status --porcelain` is empty in both repos and ports 3410-3413 are free
