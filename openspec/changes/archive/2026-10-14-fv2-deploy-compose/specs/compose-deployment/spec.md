# Compose Deployment Specification

## Purpose
A reproducible Docker Compose stack for an Ubuntu server and for local proof.

## Requirements

### Requirement: Service ordering and health
The stack MUST start `postgres`, run `migrate` to completion, then start `control-plane`, then `caddy`, each gated on health/completion. A failed `migrate` MUST prevent the control plane from starting.

#### Scenario: Healthy start
- GIVEN valid secrets and env
- WHEN `compose up -d --wait`
- THEN all long-running services are healthy and `migrate` exited 0

#### Scenario: Migration failure
- GIVEN a tampered applied migration
- WHEN the stack starts
- THEN `migrate` exits non-zero and `control-plane` never starts

### Requirement: Hardened runtime
The control-plane image MUST run as a non-root user with a read-only root filesystem, no added capabilities, and a single uvicorn worker. Images MUST be pinned by digest.

#### Scenario: Static policy
- GIVEN the Dockerfile and compose files
- WHEN the policy test runs
- THEN `USER` is non-root, `read_only: true`, `cap_drop: [ALL]` and every `image:` has a digest

### Requirement: Secrets and exposure
No secret MUST be committed, baked into an image layer, or printed by `compose config`; secrets MUST be Docker secrets (`*_FILE`). Only `caddy` MAY publish host ports; postgres and control-plane MUST NOT.

#### Scenario: Repo clean
- GIVEN generated `deploy/secrets/*`
- WHEN `git status` runs
- THEN secrets are ignored

#### Scenario: Port exposure
- GIVEN `docker compose config`
- WHEN ports are inspected
- THEN only caddy publishes

### Requirement: Domain configurability
The domain MUST come only from `FORGE_DOMAIN` (and `FORGE_PORT_SUFFIX`); no file other than `.env.example` MAY contain a concrete production domain.

#### Scenario: Other domain
- GIVEN `FORGE_DOMAIN=forge.example.test`
- WHEN the stack starts
- THEN Caddy, the Host guard and invitation origin all use it

### Requirement: Local proof and teardown
A smoke command MUST bring up the stack locally, assert health, applied migrations and admin reachability through Caddy, then remove containers and volumes.

#### Scenario: Smoke passes
- GIVEN Docker is available
- WHEN `scripts/deploy-smoke.ps1` runs
- THEN exit 0 and `docker ps -a` shows no project containers
