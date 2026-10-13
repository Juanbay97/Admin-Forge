"""Capability governance persistence: the PostgreSQL adapter over the migration 0038/0039 functions.

Every call is a SECURITY DEFINER function run on the dedicated ``forge_capability_service`` pool, which holds no table privilege.
Callers pass the session *digest*, never the capability. The pool's role is checked on every borrow and every failure is one of
the finite errors of ``forge.capability_model`` (platform refusals keep the platform's own classes).
"""
from contextlib import contextmanager
import json
import math

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_store import _KEYS, _ROLE
from forge.capability_model import (AuditRecord, CapabilityConflict, CapabilityDenied, CapabilityError, CapabilityInvalid, CapabilityLocked,
                                    CapabilityNotFound, CapabilityUnavailable, CatalogRecord, CompanyPolicyRow, Snapshot)
from forge.capability_policy import CatalogEntry, Layer
from forge.platform import MfaRequired, PlatformDenied

ROLE = 'forge_capability_service'
_MESSAGES = {'CAP_DENIED': CapabilityDenied, 'CAP_INVALID': CapabilityInvalid, 'CAP_NOT_FOUND': CapabilityNotFound,
             'CAP_CONFLICT': CapabilityConflict, 'CAP_LOCKED': CapabilityLocked, 'PLATFORM_DENIED': PlatformDenied,
             'MFA_REQUIRED': MfaRequired}


class CapabilityConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid capability pool timeout.')
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise CapabilityUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'%s'" % ROLE))
                    if cursor.fetchone() != (True,):
                        raise CapabilityUnavailable()
                    for key in (*_KEYS, 'cap_platform'):
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except (CapabilityError, MfaRequired, PlatformDenied):
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message in _MESSAGES:
                    raise _MESSAGES[message]() from None
            raise CapabilityUnavailable() from None


_ENTRY = 'id,kind,version,risk,is_base,default_state,min_sandbox_level,manifest_sha256,credential_locus,declared_permissions,granted_permissions'


def _entry(row):
    try:
        return CatalogEntry(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], tuple(row[9]), tuple(row[10]))
    except ValueError:
        raise CapabilityUnavailable() from None  # a row the database holds but the domain refuses: fail closed


def _layer(state, lock):
    try:
        return Layer(state, lock)
    except ValueError:
        raise CapabilityUnavailable() from None


def _snapshot(rows):
    if not rows:
        # The function proved the session and the membership before it read any row, so no row means an empty catalog: a defined state
        # (nothing governed yet), at the default epochs because no catalog write has bumped either one.
        return Snapshot(1, 1, (), {}, {}, {})
    entries, platform, company, org = [], {}, {}, {}
    for row in rows:
        entry = _entry(row)
        entries.append(entry)
        platform[entry.id] = _layer(row[11], row[12])
        company[entry.id] = _layer(row[13], row[14])
        if row[15] is not None:
            org[entry.id] = row[15]
    return Snapshot(rows[0][16], rows[0][17], tuple(entries), platform, company, org)


class PostgresCapabilityStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = CapabilityConnection(pool, acquisition_timeout=acquisition_timeout)

    def _rows(self, query, values):
        with self.connection.cursor() as cursor:
            cursor.execute(query, values)
            return cursor.fetchall()

    def catalog(self, digest):
        return [CatalogRecord(_entry(row), row[11], _layer(row[12], row[13]))
                for row in self._rows('SELECT * FROM forge.cap_catalog_list(%s)', (digest,))]

    def put_entry(self, digest, identifier, expected, document):
        rows = self._rows('SELECT * FROM forge.cap_catalog_put(%s,%s,%s,%s::jsonb)', (digest, identifier, expected, json.dumps(document)))
        if len(rows) != 1:
            raise CapabilityUnavailable()
        return CatalogRecord(_entry(rows[0]), rows[0][11], Layer())

    def set_platform_policy(self, digest, identifier, state, lock):
        return self._rows('SELECT forge.cap_platform_policy_set(%s,%s,%s,%s)', (digest, identifier, state, lock))[0][0]

    def set_company_override(self, digest, org, identifier, state, lock):
        return self._rows('SELECT forge.cap_company_override_set(%s,%s,%s,%s,%s)', (digest, org, identifier, state, lock))[0][0]

    def company_policy(self, digest, org):
        return [CompanyPolicyRow(row[0], _layer(row[1], row[2]), row[3])
                for row in self._rows('SELECT * FROM forge.cap_company_policy_get(%s,%s)', (digest, org))]

    def set_org(self, digest, org, identifier, want):
        return self._rows('SELECT forge.cap_org_set(%s,%s,%s,%s)', (digest, org, identifier, want))[0][0]

    def snapshot(self, digest, org):
        return _snapshot(self._rows('SELECT * FROM forge.cap_read_layers(%s,%s)', (digest, org)))

    def admin_snapshot(self, digest, org):
        return _snapshot(self._rows('SELECT * FROM forge.cap_admin_layers(%s,%s)', (digest, org)))

    def org_audit(self, digest, org, before, page):
        return [AuditRecord(row[0], row[1], org, row[2], row[3], row[4], row[5], row[6], row[7])
                for row in self._rows('SELECT * FROM forge.cap_org_audit_page(%s,%s,%s,%s)', (digest, org, before, page))]

    def ingest(self, digest, org, events):
        return self._rows('SELECT forge.cap_invocation_ingest(%s,%s,%s::jsonb)', (digest, org, json.dumps(events)))[0][0]

    def attest(self, digest, org, report):
        return self._rows('SELECT forge.cap_attestation_ingest(%s,%s,%s::jsonb)', (digest, org, json.dumps(report)))[0][0] is True

    def attested_level(self, digest, org):
        """The member's latest attestation level for the company (None when there is none or it is older than 30 days)."""
        return self._rows('SELECT forge.cap_latest_attestation(%s,%s)', (digest, org))[0][0]

    def platform_audit(self, digest, before, page):
        return [AuditRecord(*row) for row in self._rows('SELECT * FROM forge.cap_platform_audit_page(%s,%s,%s)', (digest, before, page))]
