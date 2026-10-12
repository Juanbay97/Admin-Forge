# Tasks: Production Runtime

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2,700 (5 slices, 400–750 each) |
| 400-line budget risk | High (800-line/slice budget: Medium) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 → S4 → S5 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| S1 | ProdConfig + origin allow-list (~450) | PR 1 | base `feat/v1wl-v3d-openspec-artifacts` |
| S2 | Migration runner (~700) | PR 2 | base PR1; PG tests |
| S3 | `composition` extraction + host-set guard (~400) | PR 3 | behaviour-preserving |
| S4 | `serve_prod` + JSON logs + health CLI (~650) | PR 4 | needs S1,S3 |
| S5 | 0027 + F27 ripple (~500, conditional) | PR 5 | numbering gate |

## Phase 1: Config (S1)
- [x] 1.1 RED `tests/test_prod_config.py`: env/_FILE load, unknown key, bad origin, `FORGE_WORKERS!=1`, PG* stripped, repr hides secrets.
- [x] 1.2 GREEN `src/forge/prod_config.py`.
- [x] 1.3 RED/GREEN `policy_from_env` in `gateway_origins.py` (default `DEFAULT_ENDPOINT`; http refused) + extend `test_gateway_origins.py`.

## Phase 2: Runner (S2)
- [x] 2.1 RED `tests/test_postgres_migrate.py`: fresh, rerun no-op, checksum tamper, adopt known fingerprint, unknown schema, crash-between, concurrent, password rotation.
- [x] 2.2 GREEN `src/forge/migrate.py` (canonical order = `MIGRATIONS`+`MVP_ADDITIONS`; advisory lock; final fingerprint). Bookkeeping table is `forge_ops.schema_migrations`, not `forge.*`: the catalog fingerprint covers every relation in `forge`.
- [x] 2.3 Unit tests for CLI exit codes/JSON with fake connection.

## Phase 3: Composition (S3)
- [x] 3.1 Extract `src/forge/composition.py`; `mvp_local.compose` delegates; `tests/test_mvp_local.py` + PG mvp_local tests stay green (RED = new `test_composition.py`).
- [x] 3.2 RED/GREEN `apply_guard(hosts=)` in `admin_mount.py` + `test_admin_mount.py` cases.

## Phase 4: Serve (S4)
- [x] 4.1 RED `tests/test_logging_json.py` (fields, redaction, request-id).
- [x] 4.2 GREEN `logging_json.py`; silence uvicorn handlers, route to JSON.
- [ ] 4.3 RED `tests/test_serve_prod.py` (`/livez`, `/status` 503, foreign Host 403, healthcheck exit codes, port bind injected).
- [ ] 4.4 GREEN `serve_prod.py`; PG integration on harness; docstring explaining single worker.

## Phase 5: Origin DB pin (S5, conditional)
- [ ] 5.1 RED PG test: non-default https origin saved; path/userinfo rejected; upgrade F26→F27 equals fresh.
- [ ] 5.2 GREEN `migrations/0027_gateway_origin_config.sql`; ripple `mvp_profile.py` (F27, MVP_PROFILE), `mvp_readiness.py`, pinned tests.

## Phase 6: Verification
- [ ] 6.1 `python -m unittest discover -s tests -v`, `scripts/test-postgres.ps1`, `python -m compileall -q src tests`, `pip check`.
- [ ] 6.2 Local Docker proof is delivered by fv2-deploy-compose; here: `serve_prod migrate && serve` against harness PG17 container, `/status` ready, then container removed.
