"""Company usage routes, hidden from the contract like the platform routes.

* ``GET /forge/v1/orgs/{id}/usage/members``: per-person usage of the own company, for its administrators.
* ``GET /forge/v1/orgs/{id}/usage/me``: the caller's own counters, for any active member of the company.

The authorization snapshot is only a fast deny (active membership and company, and the administrator role for the per-person
route); the database function re-validates the live session (and the administrator), so another company's person, a member
asking for the report, or a stale session is always the same not-found.
"""
from uuid import UUID

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.authorization import AuthorizationSnapshot
from forge.directory import DirectoryDenied
from forge.foundation import MembershipStatus
from forge.invitations import capability_digest
from forge.platform_api import _UNAVAILABLE, _Refusal, _envelope, _invalid
from forge.platform_usage_api import COUNTER_FIELDS, _counters, _window

_NOT_FOUND = ('NOT_FOUND', 'The requested resource is unavailable.')


def mount_company_usage(app: FastAPI, *, usage, sessions, authorization_reader, readiness):
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    async def authenticate(request):
        header = request.headers.getlist('authorization')
        scheme, separator, value = (header[0] if len(header) == 1 else '').partition(' ')
        unauthenticated = _Refusal(_envelope(401, 'UNAUTHENTICATED', 'A valid Forge bearer token is required.',
                                             headers={'WWW-Authenticate': 'Bearer'}))
        if scheme.lower() != 'bearer' or not separator or len(value) != 43 or any(c.isspace() for c in value):
            raise unauthenticated
        try:
            if readiness is None or not await blocking(readiness.check):
                raise _Refusal(_envelope(503, *_UNAVAILABLE))
            capability_digest(value)
            identity = await blocking(sessions.validate, value)
        except _Refusal:
            raise
        except ValueError:
            identity = None
        except Exception:
            raise _Refusal(_envelope(503, *_UNAVAILABLE)) from None
        if identity is None:
            raise unauthenticated
        return value, identity

    async def fast_deny(identity, organization_id, *, administrator):
        try:
            snapshot = await blocking(authorization_reader.read, identity, str(organization_id))
        except Exception:
            snapshot = None
        if (type(snapshot) is not AuthorizationSnapshot or snapshot.identity != identity
                or snapshot.organization_id != organization_id or (administrator and 'organization_admin' not in snapshot.roles)
                or snapshot.membership_status is not MembershipStatus.ACTIVE or not snapshot.organization_active):
            raise _Refusal(_envelope(404, *_NOT_FOUND))

    @app.get('/forge/v1/orgs/{organization_id}/usage/members', include_in_schema=False)
    async def members(organization_id: UUID, request: Request):
        try:
            token, identity = await authenticate(request)
            first, last, values = _window(request, {'after'})
            try:
                after = UUID(values['after']) if 'after' in values else None
            except ValueError:
                raise _invalid() from None
            page = int(values.get('page', 50))
            await fast_deny(identity, organization_id, administrator=True)
            found = await blocking(usage.members, token, organization_id, first, last, after, page)
            rows = [{'member_id': str(item.member_id), 'email': item.email, 'name': item.name, 'state': item.state,
                     **_counters(item.counters)} for item in found]
            return JSONResponse({'members': rows, 'next_after': rows[-1]['member_id'] if len(rows) == page else None})
        except _Refusal as refusal:
            return refusal.response
        except DirectoryDenied:
            return _envelope(404, *_NOT_FOUND)
        except ValueError:
            return _envelope(422, 'INVALID_REQUEST', 'The platform request is invalid.')
        except Exception:
            return _envelope(503, *_UNAVAILABLE)

    @app.get('/forge/v1/orgs/{organization_id}/usage/me', include_in_schema=False)
    async def mine(organization_id: UUID, request: Request):
        try:
            token, identity = await authenticate(request)
            first, last, values = _window(request, set())
            if 'page' in values:
                raise _invalid()
            await fast_deny(identity, organization_id, administrator=False)
            found = await blocking(usage.mine, token, organization_id, first, last)
            return JSONResponse(_counters(found))
        except _Refusal as refusal:
            return refusal.response
        except DirectoryDenied:
            return _envelope(404, *_NOT_FOUND)
        except ValueError:
            return _envelope(422, 'INVALID_REQUEST', 'The platform request is invalid.')
        except Exception:
            return _envelope(503, *_UNAVAILABLE)
