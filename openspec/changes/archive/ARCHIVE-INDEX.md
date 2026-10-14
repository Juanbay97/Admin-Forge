# Archive index

Archived 2026-10-14 in order of delivery. Folder: `2026-10-14-<change>/`, each with an `archive-report.md`. Completed = date of the last commit. Control plane = `.worktrees/web` repo; client = nested `clients/openyak` repo. Specs were merged into `openspec/specs/` in this order, so later changes modify earlier ones.

## Changes

| # | Change | Completed | Summary | Main commits / branches |
|---|---|---|---|---|
| 1 | prometheon-forge-mvp | 2026-10-11 | Forge MVP local stack: admin web, fake gateway, gateway origin policy, identity discovery, member administration, managed client launch and rebrand. | c80e06b, 91d015f, a8202de, c66e965, d97707e, d121acd, 8a9110d, 4c8f585, 502fa70, 211735b, 0de35d8, f41e5da; feat/mvp-a0-docs .. feat/mvp-final-smoke; client feat/mvp-c1-remove-key-flow .. feat/mvp-c4-client-e2e |
| 2 | v1-multiuser | 2026-10-11 | Multi-user client: profile router, multi-org login and switching, scoped session revocation, multi-user smoke with clean-tree gate. | 0ac0b61, f1fa79f, 8f71005, 97e0e3a, cad51ba, 8c75d32, 295cdc5; feat/v1mu-cp1-pg-deflake, cp2-scoped-revocation, cp3-multiuser-smoke; client feat/mvp-v1-c1..c6 |
| 3 | v1-white-label | 2026-10-12 | Per-company white-label: branding validators, sanitized logos, branding migrations 0025/0026, public branding API, themed admin and client, company code. | 547e94d, 4aff692, 77d71c3, ed257fe, d7bbecb, bbb377d, 89ec6dd, 841f631, 28be856, fe9f129; feat/v1wl-w1a .. v3d; client feat/mvp-v1-wl-c1..c4c, g2 |
| 4 | fv2-prod-runtime | 2026-10-12 | Production runtime: env/secret-file config, checksummed migration runner, structured logging, serve_prod with health routes, gateway origin relaxed to canonical https (0027). | d57f662, 7286a1f, 4b926e9, 9c55f0a, 3faf0e4, bd66d33, 8367afa; feat/fv2-prod-runtime-s1-config .. s5-origin-config |
| 5 | fv2-deploy-compose | 2026-10-12 | Hardened image, Caddy TLS compose stack, secrets generator, local proof overlay, docker smoke, verified backups and data-only restore, runbook. | b79609e, acd40fb, 330e10a, f9d1aaf, 5c6f5af; feat/fv2-deploy-compose-s0 .. s4-backup-docs |
| 6 | fv2-smtp-delivery | 2026-10-12 | Generic SMTP adapter with verified TLS, real delivery channel reporting and receipts, relay wiring and Mailpit proof. | 0cef281, d3b07dc, 7525d5d, f5f1a87; feat/fv2-smtp-delivery-s1-adapter .. s3-deploy-proof |
| 7 | fv2-platform-core | 2026-10-12 | Platform scope: owner bootstrap CLI, TOTP, platform sessions, company lifecycle (create, suspend, reactivate, branding edit) and append-only platform audit. | 08fa715, 023eabf, e5c42cf, 3ec43e0, 1845873, 138941e, bf4491f, bf481dd, 4655a26; feat/fv2-platform-core-s1-scope .. s8-audit-smoke-docs |
| 8 | fv2-gateway-keys | 2026-10-12 | Platform gateway key pool with sealed keys, priority routing, failover, per-company model access, read-only company gateway. | 54c078c, c0fa75f, 5ce24ce, 8762d74, ca48c1c, 28573e6; feat/fv2-gateway-keys-s1-schema .. s5-admin-readonly |
| 9 | fv2-usage-metering | 2026-10-12 | Metered usage events and daily rollup, versioned model prices with cost snapshots, platform and company usage reports, deploy smoke proof. | 4db5bd2, c241ce6, 87d5588, d4e304e, 32063d1, 0772667, 63b3c97, 6e39ed6; feat/fv2-usage-metering-s1 .. s6b-smoke-docs |
| 10 | fv2-capability-governance | 2026-10-13 | Capability governance: catalog, layered resolver, company overrides, epochs, Ed25519 signed effective policy, invocation log, app manifest, seed sync. | d1ceb83, 3f17843, 19bb2f0, e88f7c3, 8d5cec5, 693f187, 0bc6a57, 051e15f, 02d038f; feat/fv2-capability-governance-s1-resolver .. s6b-ops-smoke-docs |
| 11 | fv2-connector-broker | 2026-10-13 | Connector broker: sealed credentials, OAuth+PKCE, MCP proxy with per-call authorization, SSRF-hardened egress guard, hidden routes and deploy smoke. | a519f4a, cd25dfd, abdf7ee, 6fb0cb3, a1ac460, c84948c, 8b3e2d4; feat/fv2-connector-broker-b1-core .. b6-hardening-smoke-docs |
| 12 | fv2-web-shell | 2026-10-12 | Admin web shell: semantic tokens, CSP/a11y gates, design-system kit, CSP-safe chart kit, role-aware routed shell, legacy pages ported. | 792403b, 13c8224, 76c5e6c, ad17932, ed7726d, b050247, cec8c7e, 28aae15, 887bd97; feat/fv2-web-shell-s1 .. s9-branding-closeout |
| 13 | fv2-web-platform-console | 2026-10-13 | Platform console: TOTP-gated console, overview, company list/detail/wizard/tabs, usage, key pool and prices, audit log, real-stack journey. | 8e463ec, 5490aeb, 943dab1, a10805a, e3445fe, 8b39a05, 61809f3, 92521a3, ab3f595; feat/fv2-web-platform-console-s1 .. s9-audit-sweep-docs |
| 14 | fv2-web-company-portal | 2026-10-13 | Company portal: hosting, branded join page, download page and installer manifest, member usage, company dashboard, real-stack journeys. | 6a1c665, f391e4c, 027ff35, 79d10a0, aa06289, 76ae8d9, 42ef2f3; feat/fv2-web-portal-s1-hosting .. s6-journeys-docs |
| 15 | fv2-gap-closure | 2026-10-13 | Gap closure: member usage route, platform members/overview reads, member department, invitation code/preview, edge link forwards, attestation ingest and effective level, policy key rotation. | a695b88, e0afa02, da1ec57, f259ecf, d18ef77, 19d9976, a0423d0, f4cc78b, 6b5e99d, 6625cef, 10b5509, 231e024, 4f065ed; feat/fv2-gap-s0-plan, g1a .. g8-policy-key-rotation |
| 16 | fv2c-desktop-owned-auth | 2026-10-12 | Desktop owned auth: Entra removal, owned login, sidecar runtime, per-company distribution config. | client 241adde, 0ab795c, f8485dd; CP tick 403da42, 7b90066; client branches fv2c-da-* (base feat/mvp-v1-wl-c4c-client-branding-e2e) |
| 17 | fv2c-sandbox-runner | 2026-10-13 | Sandbox tool runner with egress guard and attestation, real-container escape suite. | client 1f65297, b4d40e5, aa4cac9, 35cca6d, 19c589b, dcf9d09, f65e042, 00ef507, 70774df, a9c0269, 0ab64e8; client branches fv2c-sr-* |
| 18 | fv2c-capabilities-client | 2026-10-13 | Client capability policy client (signed policy pinning), connector secrets vault, capabilities UI, onboarding link, live attestation. | client 5b25df9, 154153e, e755a2c, 0216db3, 87f79b3, 4739317, 5392fb7, a6918dd, 9f52617, 1f65297; client branches fv2c-cc-* (e.g. fv2c-cc-i1-onboarding-link, i2-attestation-live, i3-container-shells) |
| 19 | fv2c-superapp-host | 2026-10-13 | Extension host: manifest validation, app catalog, stdio host and ExtensionHost/AppCatalog UI. | client 1936fa4, 57ed724, bdc777b, fdef3c9, 138033b; client branches fv2c-sa-* |

## Program and exploration records (no spec merge)

- 2026-10-14-forge-roadmap-s4-s7: old exploration of the S4-S7 roadmap (base 48c3e8e), moved as-is.
- 2026-10-14-prometheon-forge-v1: v1 program exploration preceding v1-multiuser and v1-white-label.
- 2026-10-14-forge-v2-program: forge-v2 program exploration plus `verify-report.md` (CP 5ad37f8, client 1f65297, PASS WITH WARNINGS, CRITICAL none). It is the verification evidence for the fv2 and fv2c changes.

## Exceptions

- fv2-* and fv2c-* changes have no per-change verify-report.md; they rely on forge-v2-program/verify-report.md.
- v1-white-label: verify verdict FAIL (one test-only regression), fixed in 9b5cdeb; the report was not re-issued.
- fv2-gap-closure: no delta specs; its added behaviours are not reflected in `openspec/specs/`.
- fv2c-capabilities-client / fv2c-superapp-host: stale unticked boxes at program verify time, reconciled from client git history; runtime proof of the Playwright extension spec and Tauri webview not re-run.
- `forge-s3-member-lifecycle` was not part of this batch and remains in `openspec/changes/`.

## Capability specs

Totals: 57 capability specs under `openspec/specs/` (12 from mvp/v1, 33 from fv2, 12 from fv2c).
