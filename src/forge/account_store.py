"""Narrow external-pool enrollment transaction, not a runtime composition or login."""
from contextlib import contextmanager
import math
import re
from uuid import UUID, uuid4

from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.accounts import Enrollment, password_record
from forge.invitations import InvitationDenied, InvitationUnavailable, ExistingAccountAuthenticationRequired

_ROLE = """
SELECT current_user='forge_enrollment' AND session_user=current_user
 AND current_setting('row_security')='on' AND NOT r.rolsuper AND NOT r.rolbypassrls
 AND NOT r.rolcreatedb AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolinherit
 AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid OR roleid=r.oid)
 AND NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspowner=r.oid)
 AND NOT EXISTS(SELECT 1 FROM pg_class WHERE relowner=r.oid)
 AND current_setting('transaction_isolation')='read committed'
FROM pg_roles r WHERE rolname=current_user
"""
_KEYS = ('organization','provider','issuer','subject','enrollment_actor','enrollment_identity',
         'enrollment_member','enrollment_invite','enrollment_digest','enrollment_email',
         'account_digest','account_message')


class EnrollmentConnection:
    def __init__(self, pool, *, acquisition_timeout=1.0, role="forge_enrollment"):
        if (type(acquisition_timeout) not in (int,float) or not math.isfinite(acquisition_timeout)
                or not 0<acquisition_timeout<=30):
            raise ValueError("Invalid enrollment timeout.")
        if role not in ("forge_enrollment", "forge_account_service"):
            raise ValueError("Invalid account connection role.")
        self.role = role
        self.pool, self.timeout = pool, float(acquisition_timeout)

    @contextmanager
    def cursor(self):
        try:
            with self.pool.connection(timeout=self.timeout) as conn:
                if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                    raise InvitationUnavailable()
                with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE.replace("'forge_enrollment'", "'"+self.role+"'"))
                    if cursor.fetchone() != (True,):
                        raise InvitationUnavailable()
                    for key in _KEYS:
                        cursor.execute("SELECT set_config(%s,'',true)", ("forge."+key,))
                    yield cursor
        except (InvitationDenied, InvitationUnavailable):
            raise
        except Exception as exc:
            message = getattr(getattr(exc, "diag", None), "message_primary", None)
            if getattr(exc, "sqlstate", None) == "P0001":
                if message == "INVITATION_DENIED":
                    raise InvitationDenied() from None
                if message == "EXISTING_ACCOUNT_AUTH_REQUIRED":
                    raise ExistingAccountAuthenticationRequired() from None
            raise InvitationUnavailable() from None


class PostgresEnrollmentStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = EnrollmentConnection(pool, acquisition_timeout=acquisition_timeout)

    def accept(self, invitation_id: UUID, digest: str, encoded: str) -> Enrollment:
        if (type(invitation_id) is not UUID or type(digest) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("Invalid enrollment input.")
        password_record(encoded)  # Cost/version/length bounds before any SQL borrow.
        account_id = uuid4()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT * FROM forge.accept_account_invitation(%s,%s,%s,%s)",
                           (invitation_id, digest, account_id, encoded))
            row = cursor.fetchone()
            if row is None or len(row)!=4 or row[0]!=account_id or any(type(v) is not UUID for v in row):
                raise InvitationUnavailable()
            return Enrollment(*row)
