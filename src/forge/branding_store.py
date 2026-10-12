"""Branding persistence: the store port, its failures, and the PostgreSQL adapter.

Every call is a SECURITY DEFINER function (0025). Member and administrator calls run on the existing
``forge_gateway_service`` pool and re-validate the live session in the database; public reads (company
code, asset bytes) run on the dedicated ``forge_branding_service`` pool, which holds no table grant.
Callers pass the session *digest*, never the capability. Failures are uniform and carry no detail.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import math
from typing import Protocol
from uuid import UUID

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_store import _KEYS, _ROLE
from forge.branding import ASSET_KINDS, DEFAULT, DEFAULT_INPUT, Branding, BrandingInput
from forge.branding_assets import Asset


class BrandingDenied(Exception):
    """Unknown, foreign, inactive or not an administrator: one outcome, never explained."""
    def __init__(self): super().__init__('Branding unavailable.')


class BrandingConflict(Exception):
    def __init__(self): super().__init__('Branding revision changed.')


class BrandingLimit(Exception):
    def __init__(self): super().__init__('Branding asset limit reached.')


class BrandingUnavailable(Exception):
    def __init__(self): super().__init__('Branding unavailable.')


@dataclass(frozen=True)
class PublishedAsset:
    content_type: str
    data: bytes


class BrandingStore(Protocol):
    def public(self, code: str) -> Branding | None: ...
    def asset(self, sha256: str) -> PublishedAsset | None: ...
    def read(self, digest: str, organization_id: UUID) -> Branding: ...
    def save(self, digest: str, organization_id: UUID, expected: int, value: BrandingInput) -> Branding: ...
    def reset(self, digest: str, organization_id: UUID, expected: int) -> Branding: ...
    def put_asset(self, digest: str, organization_id: UUID, asset: Asset) -> bool: ...


_MESSAGES = {'BRANDING_DENIED': BrandingDenied, 'DIRECTORY_DENIED': BrandingDenied,
             'BRANDING_CONFLICT': BrandingConflict, 'BRANDING_LIMIT': BrandingLimit}


class BrandingConnection:
    def __init__(self, pool, role, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid branding pool timeout.')
        if role not in ('forge_gateway_service', 'forge_branding_service'):
            raise ValueError('Invalid branding connection role.')
        self.pool, self.role, self.timeout = pool, role, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise BrandingUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'%s'" % self.role))
                    if cursor.fetchone() != (True,):
                        raise BrandingUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except (BrandingDenied, BrandingConflict, BrandingLimit, BrandingUnavailable, ValueError):
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message in _MESSAGES:
                    raise _MESSAGES[message]() from None
                if message == 'BRANDING_INVALID':
                    raise ValueError('Invalid branding request.') from None
            raise BrandingUnavailable() from None


def _branding(row):
    """Revision 0 (NULL fields) is the application default: the database stores only what was saved.

    The trailing columns are logo_light, logo_dark, isotipo: the order of ``ASSET_KINDS``."""
    revision, name, copy, primary, accent, tint, heading, body, *logos = row
    if revision == 0:
        return DEFAULT
    return Branding(revision, name, copy, primary, accent, tint, heading, body,
                    {kind: sha for kind, sha in zip(ASSET_KINDS, logos) if sha is not None})

_SAVE = 'SELECT * FROM forge.branding_save(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)'


class PostgresBrandingStore:
    def __init__(self, gateway_pool, public_pool, *, acquisition_timeout=1.0):
        self.members = BrandingConnection(gateway_pool, 'forge_gateway_service', acquisition_timeout=acquisition_timeout)
        self.public_pool = BrandingConnection(public_pool, 'forge_branding_service', acquisition_timeout=acquisition_timeout)

    def public(self, code):
        if type(code) is not str:
            return None
        with self.public_pool.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.branding_public_read(%s)', (code,))
            row = cursor.fetchone()
            return None if row is None else _branding(row)

    def asset(self, sha256):
        if type(sha256) is not str:
            return None
        with self.public_pool.cursor() as cursor:
            cursor.execute('SELECT content_type,body FROM forge.branding_asset_get(%s)', (sha256,))
            row = cursor.fetchone()
            return None if row is None else PublishedAsset(row[0], bytes(row[1]))

    def read(self, digest, organization_id):
        with self.members.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.branding_member_read(%s,%s)', (digest, organization_id))
            return _branding(cursor.fetchone())

    def _save(self, digest, organization_id, expected, change, value):
        with self.members.cursor() as cursor:
            cursor.execute(_SAVE, (digest, organization_id, expected, change, value.name, value.login_copy, value.primary,
                                   value.accent, value.tint, value.heading, value.body, value.assets.get('logoLight'),
                                   value.assets.get('logoDark'), value.assets.get('isotipo')))
            row = cursor.fetchone()
            if row is None:
                raise BrandingUnavailable()
            return _branding(row)

    def save(self, digest, organization_id, expected, value):
        return self._save(digest, organization_id, expected, 'save', value)

    def reset(self, digest, organization_id, expected):
        return self._save(digest, organization_id, expected, 'reset', DEFAULT_INPUT)

    def put_asset(self, digest, organization_id, asset):
        with self.members.cursor() as cursor:
            cursor.execute('SELECT forge.branding_asset_put(%s,%s,%s,%s,%s,%s,%s)',
                           (digest, organization_id, asset.sha256, asset.content_type, asset.width, asset.height, asset.data))
            return cursor.fetchone()[0] is True
