"""Platform persistence: the PostgreSQL adapter for ``forge.platform``.

Every call is a SECURITY DEFINER function of migration 0028 and later, run on the dedicated
``forge_platform_service`` pool, which holds no table or sequence privilege. Callers pass the session *digest*, never
the capability. The pool's role is checked on every borrow; every failure is one of the finite platform codes.
"""
from contextlib import contextmanager
import math

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_store import _KEYS, _ROLE
from forge.branding_store import _branding
from forge.platform import (AuditEntry, Company, CompanyConflict, MfaChallenge, MfaEnrolled, MfaInvalid, MfaLocked, MfaRequired, MfaStatus,
                            PlatformDenied, PlatformError, PlatformIdentity, PlatformInvalid, PlatformNotFound, PlatformUnavailable,
                            RevisionConflict)

ROLE = 'forge_platform_service'
_MESSAGES = {'PLATFORM_DENIED': PlatformDenied, 'PLATFORM_INVALID': PlatformInvalid, 'MFA_REQUIRED': MfaRequired,
             'MFA_INVALID': MfaInvalid, 'MFA_LOCKED': MfaLocked, 'MFA_ENROLLED': MfaEnrolled, 'COMPANY_CONFLICT': CompanyConflict,
             'PLATFORM_NOT_FOUND': PlatformNotFound, 'REVISION_CONFLICT': RevisionConflict}


class PlatformConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid platform pool timeout.')
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise PlatformUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'%s'" % ROLE))
                    if cursor.fetchone() != (True,):
                        raise PlatformUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except PlatformError:
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message in _MESSAGES:
                    raise _MESSAGES[message]() from None
            raise PlatformUnavailable() from None


class PostgresPlatformStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = PlatformConnection(pool, acquisition_timeout=acquisition_timeout)

    def create_company(self, digest, ids, details, invitation_digest, lifetime):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_company_create(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (digest, ids['organization'], ids['department'], ids['invitation'], ids['membership'], details['slug'],
                            details['display_name'], details['department'], details['admin_email'], details['admin_name'],
                            invitation_digest, lifetime))
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise PlatformUnavailable()
            return row[0]

    def set_company_active(self, digest, organization_id, turn_on):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_company_set_active(%s,%s,%s)', (digest, organization_id, turn_on))
            return cursor.fetchone() == (True,)

    def company_branding(self, digest, organization_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_branding_read(%s,%s)', (digest, organization_id))
            row = cursor.fetchone()
            if row is None:
                raise PlatformUnavailable()
            return _branding(row)

    def save_company_branding(self, digest, organization_id, expected, change, value):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_branding_save(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           (digest, organization_id, expected, change, value.name, value.login_copy, value.primary, value.accent,
                            value.tint, value.heading, value.body, value.assets.get('logoLight'), value.assets.get('logoDark'),
                            value.assets.get('isotipo')))
            row = cursor.fetchone()
            if row is None:
                raise PlatformUnavailable()
            return _branding(row)

    def mfa_status(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_mfa_status(%s)', (digest,))
            return MfaStatus(*cursor.fetchone())

    def mfa_enroll(self, digest, sealed, hashes):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_mfa_enroll(%s,%s,%s)', (digest, sealed, list(hashes)))
            if cursor.fetchone() != (True,):
                raise PlatformUnavailable()

    def mfa_begin(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_mfa_begin(%s)', (digest,))
            return MfaChallenge(*cursor.fetchone())

    def mfa_confirm(self, digest, step):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_mfa_confirm(%s,%s)', (digest, step))
            if cursor.fetchone() != (True,):
                raise PlatformUnavailable()

    def mfa_recover(self, digest, code_hash):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.platform_mfa_recover(%s,%s)', (digest, code_hash))
            if cursor.fetchone() != (True,):
                raise PlatformUnavailable()

    def me(self, digest):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_me(%s)', (digest,))
            row = cursor.fetchone()
            if row is None:
                raise PlatformUnavailable()
            return PlatformIdentity(*row)

    def companies(self, digest, after, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_list(%s,%s,%s)', (digest, after, page))
            return [Company(*row) for row in cursor.fetchall()]

    def company(self, digest, organization_id):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_company_get(%s,%s)', (digest, organization_id))
            row = cursor.fetchone()
            return None if row is None else Company(*row)

    def audit(self, digest, before, page):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.platform_audit_page(%s,%s,%s)', (digest, before, page))
            return [AuditEntry(*row) for row in cursor.fetchall()]
