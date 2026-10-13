"""Connector broker persistence: the PostgreSQL adapter over the migration 0041 functions.

Every call is a SECURITY DEFINER function on the dedicated ``forge_broker_service`` pool, which holds no table privilege. Callers pass the
session *digest*, never the capability (the OAuth callback passes the hashed state). The pool's role is checked on every borrow and every
failure is a finite ``forge.connector_model`` error. Sealed values travel as opaque text; opening them is the cipher's job.
"""
from contextlib import contextmanager
import math

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.account_store import _KEYS, _ROLE
from forge.connector_model import (BrokerConflict, BrokerDenied, BrokerError, BrokerInvalid, BrokerLimit, BrokerNotFound, BrokerUnavailable,
                                   ConnectorContext, ConnectorStatus, CredentialInfo, CredentialStatus, RemovedGrant, TakenState, connector_state)
from forge.platform import MfaRequired, PlatformDenied

ROLE = 'forge_broker_service'
_MESSAGES = {'CAP_DENIED': BrokerDenied, 'BROKER_DENIED': BrokerDenied, 'BROKER_INVALID': BrokerInvalid, 'CAP_INVALID': BrokerInvalid,
             'BROKER_NOT_FOUND': BrokerNotFound, 'BROKER_CONFLICT': BrokerConflict, 'BROKER_LIMIT': BrokerLimit,
             'PLATFORM_DENIED': PlatformDenied, 'MFA_REQUIRED': MfaRequired}


class BrokerConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        if (type(acquisition_timeout) not in (int, float) or not math.isfinite(acquisition_timeout)
                or not 0 < acquisition_timeout <= 30):
            raise ValueError('Invalid broker pool timeout.')
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as connection:
                if not connection.autocommit or connection.info.transaction_status is not TransactionStatus.IDLE:
                    raise BrokerUnavailable()
                with connection.transaction(), connection.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'%s'" % ROLE))
                    if cursor.fetchone() != (True,):
                        raise BrokerUnavailable()
                    for key in (*_KEYS, 'cap_platform', 'broker_platform', 'broker_state'):
                        cursor.execute("SELECT set_config(%s,'',true)", ('forge.' + key,))
                    yield cursor
        except (BrokerError, MfaRequired, PlatformDenied):
            raise
        except Exception as error:
            if getattr(error, 'sqlstate', None) == 'P0001':
                message = getattr(getattr(error, 'diag', None), 'message_primary', None)
                if message in _MESSAGES:
                    raise _MESSAGES[message]() from None
            raise BrokerUnavailable() from None


class PostgresConnectorStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = BrokerConnection(pool, acquisition_timeout=acquisition_timeout)

    def _rows(self, query, values):
        with self.connection.cursor() as cursor:
            cursor.execute(query, values)
            return cursor.fetchall()

    def status(self, digest, org):
        return [ConnectorStatus(row[0], row[1], row[2], connector_state(row[0], row[3], row[4], row[5], row[6], row[7], row[8], row[9]),
                                row[10], row[11], row[12], row[13])
                for row in self._rows('SELECT * FROM forge.broker_status(%s,%s)', (digest, org))]

    def context(self, digest, org, capability_id):
        rows = self._rows('SELECT * FROM forge.broker_context(%s,%s,%s)', (digest, org, capability_id))
        if len(rows) != 1:
            raise BrokerUnavailable()
        row = rows[0]
        return ConnectorContext(row[0], row[1], row[2], connector_state(capability_id, row[3], row[4], row[5], row[6], row[7], row[8], row[9]),
                                row[10], row[11], row[12], row[13], row[14], row[15], row[16], row[17])

    def credential_save(self, digest, org, capability_id, kind, expected, sealed, hint):
        rows = self._rows('SELECT * FROM forge.broker_credential_save(%s,%s,%s,%s,%s,%s,%s)', (digest, org, capability_id, kind, expected, sealed, hint))
        if len(rows) != 1:
            raise BrokerUnavailable()
        return CredentialInfo(*rows[0])

    def credential_clear(self, digest, org, capability_id, expected):
        return self._rows('SELECT forge.broker_credential_clear(%s,%s,%s,%s)', (digest, org, capability_id, expected))[0][0]

    def credential_status(self, digest, org):
        return [CredentialStatus(*row) for row in self._rows('SELECT * FROM forge.broker_credential_status(%s,%s)', (digest, org))]

    def credential_revision(self, digest, org, capability_id):
        return self._rows('SELECT forge.broker_credential_revision(%s,%s,%s)', (digest, org, capability_id))[0][0]

    def platform_credential_save(self, digest, capability_id, kind, expected, sealed, hint):
        rows = self._rows('SELECT * FROM forge.broker_platform_credential_save(%s,%s,%s,%s,%s,%s)', (digest, capability_id, kind, expected, sealed, hint))
        if len(rows) != 1:
            raise BrokerUnavailable()
        return CredentialInfo(*rows[0])

    def platform_credential_revision(self, digest, capability_id):
        return self._rows('SELECT forge.broker_platform_credential_revision(%s,%s)', (digest, capability_id))[0][0]

    def oauth_start(self, digest, org, capability_id, hashed, sealed_verifier, ttl):
        self._rows('SELECT forge.broker_oauth_start(%s,%s,%s,%s,%s,%s)', (digest, org, capability_id, hashed, sealed_verifier, ttl))

    def oauth_take(self, hashed):
        rows = self._rows('SELECT * FROM forge.broker_oauth_take(%s)', (hashed,))
        if len(rows) != 1:
            raise BrokerDenied()
        return TakenState(*rows[0])

    def oauth_complete(self, hashed, expected, sealed, expires):
        return self._rows('SELECT forge.broker_oauth_complete(%s,%s,%s,%s)', (hashed, expected, sealed, expires))[0][0]

    def grant_update(self, digest, org, capability_id, expected, sealed, expires, status):
        return self._rows('SELECT forge.broker_grant_update(%s,%s,%s,%s,%s,%s,%s)', (digest, org, capability_id, expected, sealed, expires, status))[0][0]

    def grant_delete(self, digest, org, capability_id):
        rows = self._rows('SELECT * FROM forge.broker_grant_delete(%s,%s,%s)', (digest, org, capability_id))
        return RemovedGrant(*rows[0]) if rows else None

    def log_call(self, org, member, event, capability_id, outcome, took, method, tool, sent, received, status):
        return self._rows('SELECT forge.broker_log_call(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                          (org, member, event, capability_id, outcome, took, method, tool, sent, received, status))[0][0]
