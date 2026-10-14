# Design: Production Runtime

## Technical Approach
New prod modules beside the dev ones. Shared wiring moves to `forge.composition.build_app(...)`; `mvp_local.compose` calls it (dev behaviour byte-identical, protected by `tests/test_mvp_local.py`). `serve_prod` loads `ProdConfig`, opens the 5 restricted pools (explicit libpq kwargs, PG* env stripped like `mvp_local.main`), asserts `MvpReadiness`, then serves. Migrations are a separate one-shot command so the runtime never holds DDL credentials.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Profile split | New `prod_config`/`serve_prod`; `mvp_local` untouched | Parametrize `mvp_local` | Dev hard validations (loopback, dev policy) are safety features; loosening them risks the dev guard |
| Shared wiring | Extract `composition.build_app` | Copy `compose` | One wiring path; avoids drift when platform scope adds services |
| Config | Env + `_FILE` secrets | JSON config file | Docker secrets/compose native; no secret in image/repo |
| Migration state | `forge.schema_migrations` + sha256 + advisory lock | Alembic/Flyway | Raw reviewed SQL with `SET LOCAL ROLE`; an external tool adds deps and hides F-checkpoints |
| Crash safety | Pre-check catalog fingerprint vs checkpoint before apply | Wrap script+record in one tx | Scripts own `BEGIN/COMMIT`; cannot nest |
| Health | `/livez` + `/status`; `healthcheck` subcommand sends Host header | Exempt `/status` from host guard | Keeps guard uniform |
| Gateway origin | Env allow-list + 0027 relax CHECK | Keep pin | Domain spelling unconfirmed; DB pin would block any other origin |
| Workers | 1 uvicorn worker | N workers | Pools (2 conns/role), readiness cache and rate state are per-process; scale-out unverified |

## Data Flow
    env/_FILE ─► ProdConfig ─► migrate (superuser, one-shot) ─► DB @ F-latest
                    │
                    └► serve_prod ─► 5 role pools ─► MvpReadiness ─► uvicorn 0.0.0.0:3410
    request ─► host/origin guard ─► request-id+JSON log ─► routers

## File Changes

| File | Action | Description |
|---|---|---|
| `src/forge/prod_config.py` | Create | ProdConfig, `_FILE` loader, origin/host derivation |
| `src/forge/migrate.py` | Create | Runner + CLI |
| `src/forge/composition.py` | Create | `build_app` extracted from `mvp_local.compose` |
| `src/forge/serve_prod.py` | Create | CLI `migrate/serve/healthcheck`, uvicorn |
| `src/forge/logging_json.py` | Create | JSON formatter + request middleware |
| `src/forge/admin_mount.py` | Modify | `apply_guard(hosts=...)` |
| `src/forge/gateway_origins.py` | Modify | `policy_from_env` |
| `src/forge/mvp_local.py` | Modify | call `build_app` |
| `migrations/0027_gateway_origin_config.sql`, `mvp_profile.py`, `mvp_readiness.py` | Create/Modify | F27 |
| `tests/test_prod_config.py`, `test_migrate*.py`, `test_serve_prod.py`, `test_postgres_migrate.py` | Create | TDD |

## Interfaces / Contracts
```python
@dataclass(frozen=True)
class ProdConfig:
    public_origin: str; db: DbConfig; roles: dict  # repr=False
    delivery_key: bytes; gateway_key: bytes
    gateway_policy: OriginPolicy; admin_dir: str; port: int = 3410
def migrate(conn, migrations_dir, passwords) -> list[str]  # applied names
```
Exit codes: finite `{"status":"failed","code":...}` JSON like `mvp_local`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | config parsing, guard, log redaction | unittest, injected env |
| PG | runner fresh/rerun/tamper/adopt/crash/concurrent; 0027 fresh vs upgrade | `scripts/test-postgres.ps1` harness |
| Integration | serve_prod on harness DB, TestClient + real socket | existing `postgres_support` |
| Regression | full unittest + PG suites | before each slice |

## Migration / Rollout
0027 conditional on numbering with fv2-gateway-keys. Prod never calls `mvp_up.install_schema`.

## Open Questions
- [ ] Who owns 0027 (this change vs fv2-gateway-keys)?
- [ ] Per-migration checkpoints exist only for 0010+; 0001–0005 rely on single-transaction atomicity — acceptable?
