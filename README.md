# Prometheon Forge

A generic organization-aware agent platform. This isolated repository starts
with executable domain contracts; it is not a deployed backend or client.

## Scope

The planned control plane uses Python/FastAPI and PostgreSQL. OpenYak and
OmniRoute remain read-only upstream references outside this repository.
No production deployment, credentials, providers, or remote services are changed.

## Delivery

See `docs/sprints.md` for the incremental plan and `docs/changes/foundation.md`
for the first bounded specification and its executable acceptance cases.


## Local checks

Requires Python 3.12 or newer; no third-party dependencies or installation needed.
Run from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
```

`forge.foundation.build_public_bootstrap` authorizes trusted adapter data and
returns an explicit public subset of PF-10. Add `src` to your Python import path
when integrating the module. Identity construction is not authentication: the
future adapter must validate tokens and load current membership/configuration.
HTTP authentication, effective capabilities, and PostgreSQL/RLS are not implemented
or proven by these domain tests. Internal configuration is never serialized.
