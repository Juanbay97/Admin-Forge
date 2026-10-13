"""Member department assignment, hidden from the contract (``include_in_schema=False``): ``PUT /forge/v1/orgs/{id}/members/{member}/department``.

The body is exactly ``{"department_id": <uuid>}`` and makes that the member's one department. Authority is the database function
(it re-validates the live session, the administrator of exactly that company, the member and an active department of that company),
so a member, another company's administrator, an unknown member or department and a stale session are the same 404.
"""
from uuid import UUID

from anyio.to_thread import run_sync
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from forge.capability_api import bearer_guard
from forge.directory import DirectoryDenied
from forge.platform_api import _UNAVAILABLE, _Refusal, _document, _envelope, _invalid

_NOT_FOUND = ('NOT_FOUND', 'The requested resource is unavailable.')


def member_view(item):
    return {'id': str(item.id), 'email': item.email, 'display_name': item.display_name, 'status': item.status, 'roles': list(item.roles),
            'departments': [{'id': str(entry.id), 'name': entry.name} for entry in item.departments]}


def mount_member_department(app: FastAPI, *, directory, sessions, readiness):
    def blocking(function, *arguments):
        return run_sync(lambda: function(*arguments), abandon_on_cancel=False)

    authenticate = bearer_guard(sessions, readiness, blocking)

    @app.put('/forge/v1/orgs/{organization_id}/members/{member_id}/department', include_in_schema=False)
    async def assign(organization_id: UUID, member_id: UUID, request: Request):
        try:
            token = await authenticate(request)
            document = await _document(request)
            if set(document) != {'department_id'} or type(document['department_id']) is not str:
                raise _invalid()
            try:
                department = UUID(document['department_id'])
            except ValueError:
                raise _invalid() from None
            return JSONResponse(member_view(await blocking(directory.assign_department, token, organization_id, member_id, department)))
        except _Refusal as refusal:
            return refusal.response
        except DirectoryDenied:
            return _envelope(404, *_NOT_FOUND)
        except ValueError:
            return _envelope(422, 'INVALID_REQUEST', 'The request is invalid.')
        except Exception:
            return _envelope(503, *_UNAVAILABLE)
