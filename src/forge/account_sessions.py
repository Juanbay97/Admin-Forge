"""Opaque owned-account sessions over durable, externally supplied service ports."""
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
from typing import Protocol
from uuid import UUID
from forge.account_store import EnrollmentConnection
from forge.accounts import ACCOUNT_ISSUER, PasswordHasher, canonical_email, password_bytes, password_record
from forge.foundation import AuthenticatedIdentity
from forge.invitations import capability_digest, InvitationUnavailable


class SessionDenied(ValueError):

    def __init__(self):
        super().__init__("Account authentication unavailable.")


class LoginThrottled(SessionDenied):

    def __init__(self,retry_seconds: int):
        super().__init__()
        self.retry_seconds=max(1,min(900,retry_seconds))


@dataclass(frozen=True,repr=False)
class LoginAttempt:
    account_id: UUID | None
    encoded: str | None
    revision: int
    retry_seconds: int


@dataclass(frozen=True,repr=False)
class AccountSession:
    capability: str
    expires_at: datetime


@dataclass(frozen=True,repr=False)
class ResetIntent:
    capability: str
    account_id: UUID
    recipient: str
    name: str


class SessionStore(Protocol):

    def begin_login(self,email: str) -> LoginAttempt | None:
        ...

    def finish_login(self,attempt: LoginAttempt,digest: str) -> datetime | None:
        ...

    def validate(self,digest: str) -> UUID | None:
        ...

    def logout(self,digest: str) -> bool:
        ...

    def disable(self,digest: str) -> bool:
        ...

    def request_reset(self,email: str,digest: str) -> tuple[UUID,str,str] | None:
        ...

    def consume_reset(self,digest: str,encoded: str) -> bool:
        ...


class SessionService:

    def __init__(self,store: SessionStore,hasher: PasswordHasher | None=None):
        self.store,self.hasher=store,hasher or PasswordHasher()
        # A freshly generated non-account comparison record prevents a cheap
        # unknown-email path. It is not an identity, a fallback login or a fixture.
        self._dummy=self.hasher.hash(secrets.token_urlsafe(32))

    def login(self,email: str,password: str) -> AccountSession:
        try:
            email=canonical_email(email)
            password_bytes(password)
        except (ValueError,TypeError):
            raise SessionDenied() from None
        attempt=self.store.begin_login(email)
        if attempt is None:
            self.hasher.verify(password,self._dummy)
            raise SessionDenied()
        if type(attempt) is not LoginAttempt or type(attempt.revision) is not int or attempt.revision<1:
            raise InvitationUnavailable()
        if type(attempt.retry_seconds) is not int or not 0<=attempt.retry_seconds<=900:
            raise InvitationUnavailable()
        if attempt.retry_seconds:
            raise LoginThrottled(attempt.retry_seconds)
        if type(attempt.account_id) is not UUID:
            raise InvitationUnavailable()
        try:
            password_record(attempt.encoded)
        except (ValueError, TypeError):
            raise InvitationUnavailable() from None
        if not self.hasher.verify(password,attempt.encoded):
            raise SessionDenied()
        capability=secrets.token_urlsafe(32)
        expires=self.store.finish_login(attempt,capability_digest(capability))
        if expires is None:
            raise SessionDenied()
        if type(expires) is not datetime or expires.tzinfo is None or expires<=datetime.now(timezone.utc):
            raise InvitationUnavailable()
        return AccountSession(capability,expires)

    def validate(self,token: str) -> AuthenticatedIdentity | None:
        try:
            digest=capability_digest(token)
        except (ValueError,TypeError):
            return None
        account=self.store.validate(digest)
        if account is None:
            return None
        if type(account) is not UUID:
            raise InvitationUnavailable()
        return AuthenticatedIdentity('forge',ACCOUNT_ISSUER,str(account))

    def logout(self,token: str) -> bool:
        try:
            digest=capability_digest(token)
        except (ValueError,TypeError):
            return False
        return self.store.logout(digest)

    def disable(self,token: str) -> bool:
        try:
            digest=capability_digest(token)
        except (ValueError,TypeError):
            return False
        return self.store.disable(digest)

    def request_reset(self,email: str) -> ResetIntent | None:
        email=canonical_email(email)
        token=secrets.token_urlsafe(32)
        target=self.store.request_reset(email,capability_digest(token))
        if target is None:
            return None
        if len(target)!=3 or type(target[0]) is not UUID or canonical_email(target[1])!=target[1]:
            raise InvitationUnavailable()
        return ResetIntent(token,*target)

    def reset(self,token: str,password: str) -> bool:
        digest=capability_digest(token)
        encoded=self.hasher.hash(password)
        return self.store.consume_reset(digest,encoded)


class PostgresSessionStore:
    """Distinct function-only nonbypass pool; no ambient DSN or SET ROLE path."""

    def __init__(self,pool,*,acquisition_timeout=1.0):
        self.connection=EnrollmentConnection(pool,acquisition_timeout=acquisition_timeout,role='forge_account_service')

    def begin_login(self,email: str) -> LoginAttempt | None:
        if canonical_email(email)!=email:
            raise ValueError('Invalid account lookup.')
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.account_begin_login(%s)',(email,))
            row=cursor.fetchone()
            return None if row is None else LoginAttempt(*row)

    def finish_login(self,attempt: LoginAttempt,digest: str) -> datetime | None:
        if type(attempt) is not LoginAttempt:
            raise ValueError('Invalid login attempt.')
        password_record(attempt.encoded)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_finish_login(%s,%s,%s,%s)',(attempt.account_id,attempt.revision,attempt.encoded,digest))
            return cursor.fetchone()[0]

    def validate(self,digest: str) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_validate_session(%s)',(digest,))
            return cursor.fetchone()[0]

    def logout(self,digest: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_logout(%s)',(digest,))
            return cursor.fetchone()==(True,)

    def disable(self,digest: str) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_disable(%s)',(digest,))
            return cursor.fetchone()==(True,)

    def request_reset(self,email: str,digest: str):
        if canonical_email(email)!=email:
            raise ValueError('Invalid account lookup.')
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM forge.account_request_reset(%s,%s)',(email,digest))
            return cursor.fetchone()

    def consume_reset(self,digest: str,encoded: str) -> bool:
        password_record(encoded)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_consume_reset(%s,%s)',(digest,encoded))
            return cursor.fetchone()==(True,)
