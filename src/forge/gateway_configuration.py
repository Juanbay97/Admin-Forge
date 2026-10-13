"""Bound organization gateway credentials; no provider connection or key discovery."""
from dataclasses import dataclass,field
import json
import re
from typing import Protocol
from uuid import UUID,uuid4
from cryptography.fernet import Fernet
from forge.invitations import capability_digest
from forge.gateway_origins import DEFAULT_ENDPOINT,DEFAULT_POLICY,OriginPolicy

GATEWAY_ENDPOINT=DEFAULT_ENDPOINT
MAX_REVISION=2**63-3

class GatewayDenied(Exception):
    def __init__(self): super().__init__('Gateway configuration unavailable.')

class GatewayConflict(Exception):
    def __init__(self): super().__init__('Gateway configuration revision changed.')

class GatewayUnavailable(Exception):
    def __init__(self): super().__init__('Gateway configuration unavailable.')

@dataclass(frozen=True,repr=False)
class GatewayRecord:
    revision: int
    binding_id: UUID
    endpoint: str
    encrypted_key: str
    # Pool keys (sealed format v2) carry the key id and the revision of that key; legacy records carry neither.
    # ``revision`` stays the gateway/profile revision the catalogue binds to.
    key_id: UUID | None=None
    key_revision: int | None=None

@dataclass(frozen=True)
class GatewayStatus:
    status: str
    revision: int
    endpoint: str=GATEWAY_ENDPOINT
    # Informational (admin origin picker); never part of status identity.
    allowed_endpoints: tuple[str,...]=field(default=(),compare=False)

class GatewayStore(Protocol):
    def read(self,digest: str,organization_id: UUID) -> GatewayRecord | None: ...
    def save(self,digest: str,organization_id: UUID,expected_revision: int,
             binding_id: UUID,encrypted_key: str,endpoint: str=GATEWAY_ENDPOINT) -> GatewayRecord: ...

class GatewayKey(str):
    """Opened key text bound to the origin it was sealed for; equals the plain key.

    Only GatewayCipher.open_key creates it, after the allow-list check. Adapters
    read `endpoint` and re-check it; a plain `str` key means the fixed default origin.
    """
    def __new__(cls,value: str,endpoint: str):
        instance=super().__new__(cls,value)
        instance.endpoint=endpoint
        return instance

    def __repr__(self): return 'GatewayKey(<redacted>)'

class GatewayCipher:
    """Caller supplies a SEPARATE deployment key, not invitation delivery material.

    Ciphertext contains exact record binding; substitution/revision/org drift fails.
    Caller owns key separation/rotation. No ambient environment or fallback key.
    """
    def __init__(self,key: bytes,*,policy: OriginPolicy=DEFAULT_POLICY):
        if type(key) is not bytes:
            raise ValueError('Explicit gateway encryption key required.')
        if type(policy) is not OriginPolicy:
            raise ValueError('Explicit gateway origin policy required.')
        self._policy=policy
        try: self._cipher=Fernet(key)
        except Exception: raise ValueError('Invalid gateway encryption key.') from None

    @property
    def policy(self) -> OriginPolicy:
        return self._policy

    @staticmethod
    def validate_key(key: str):
        if not isinstance(key,str) or not re.fullmatch(r'[!-~]{1,4096}',key):
            raise ValueError('Invalid gateway credential.')

    def seal(self,organization_id: UUID,binding_id: UUID,revision: int,key: str,endpoint: str=GATEWAY_ENDPOINT) -> str:
        self.validate_key(key)
        self._policy.require(endpoint)
        if type(organization_id) is not UUID or type(binding_id) is not UUID or type(revision) is not int or not 1<=revision<=MAX_REVISION+1:
            raise ValueError('Invalid gateway binding.')
        payload=json.dumps({'v':1,'organization':str(organization_id),'binding':str(binding_id),
            'revision':revision,'endpoint':endpoint,'key':key},sort_keys=True,separators=(',',':')).encode()
        return self._cipher.encrypt(payload).decode('ascii')

    def seal_pooled(self,key_id: UUID,revision: int,key: str,endpoint: str) -> str:
        """Format v2: the payload binds the key id, its revision and its origin, never an organization.

        The same key serves several companies, so the organization cannot be part of the binding; moving a
        sealed value to another key id, revision or origin makes it unreadable.
        """
        self.validate_key(key)
        self._policy.require(endpoint)
        if type(key_id) is not UUID or type(revision) is not int or not 1<=revision<=MAX_REVISION+1:
            raise ValueError('Invalid gateway binding.')
        payload=json.dumps({'v':2,'key_id':str(key_id),'revision':revision,'endpoint':endpoint,'key':key},
            sort_keys=True,separators=(',',':')).encode()
        return self._cipher.encrypt(payload).decode('ascii')

    def open_key(self,organization_id: UUID,record: GatewayRecord) -> GatewayKey:
        """Private server-side use only, after fresh administrator or restricted member-route authorization.

        Dispatches on the record: a pool key (``key_id`` set) opens as format v2, a legacy record as v1.
        """
        try:
            if type(record) is GatewayRecord and record.key_id is not None:
                return self._open_pooled(record)
            if (type(record) is not GatewayRecord or type(record.revision) is not int
                    or not 1<=record.revision<=MAX_REVISION+1 or type(record.binding_id) is not UUID
                    or not self._policy.permits(record.endpoint) or type(record.encrypted_key) is not str
                    or not 100<=len(record.encrypted_key)<=12288):
                raise ValueError()
            payload=json.loads(self._cipher.decrypt(record.encrypted_key.encode('ascii')))
            self.validate_key(payload['key'])
            if payload!={'v':1,'organization':str(organization_id),'binding':str(record.binding_id),
                    'revision':record.revision,'endpoint':record.endpoint,'key':payload['key']}:
                raise ValueError()
            return GatewayKey(payload['key'],record.endpoint)
        except Exception:
            raise GatewayUnavailable() from None

    def _open_pooled(self,record: GatewayRecord) -> GatewayKey:
        try:
            if (type(record.key_id) is not UUID or type(record.key_revision) is not int
                    or not 1<=record.key_revision<=MAX_REVISION+1 or type(record.revision) is not int
                    or not 1<=record.revision<=MAX_REVISION+1 or type(record.binding_id) is not UUID
                    or not self._policy.permits(record.endpoint) or type(record.encrypted_key) is not str
                    or not 100<=len(record.encrypted_key)<=12288):
                raise ValueError()
            payload=json.loads(self._cipher.decrypt(record.encrypted_key.encode('ascii')))
            self.validate_key(payload['key'])
            if payload!={'v':2,'key_id':str(record.key_id),'revision':record.key_revision,
                    'endpoint':record.endpoint,'key':payload['key']}:
                raise ValueError()
            return GatewayKey(payload['key'],record.endpoint)
        except Exception:
            raise GatewayUnavailable() from None

    def verify(self,organization_id: UUID,record: GatewayRecord) -> None:
        self.open_key(organization_id,record)

class GatewayConfiguration:
    def __init__(self,store: GatewayStore,cipher: GatewayCipher):
        self._store,self._cipher=store,cipher

    @property
    def allowed_endpoints(self) -> frozenset:
        return self._cipher.policy.allowed

    def read(self,token: str,organization_id: UUID) -> GatewayStatus:
        digest=capability_digest(token)
        if type(organization_id) is not UUID: raise ValueError('Invalid organization.')
        record=self._store.read(digest,organization_id)
        allowed=tuple(sorted(self.allowed_endpoints))
        if record is None: return GatewayStatus('NOT_CONFIGURED',0,GATEWAY_ENDPOINT,allowed)
        self._cipher.verify(organization_id,record)
        return GatewayStatus('SAVED_UNVERIFIED',record.revision,record.endpoint,allowed)

    def save(self,token: str,organization_id: UUID,expected_revision: int,key: str,endpoint: str|None=None) -> GatewayStatus:
        """A new write-only key is always required: the origin is bound into the ciphertext."""
        digest=capability_digest(token)
        if type(organization_id) is not UUID or type(expected_revision) is not int or not 0<=expected_revision<=MAX_REVISION:
            raise ValueError('Invalid gateway revision.')
        binding=uuid4()
        endpoint=GATEWAY_ENDPOINT if endpoint is None else endpoint
        encrypted=self._cipher.seal(organization_id,binding,expected_revision+1,key,endpoint)
        # The fixed default keeps the original store call shape (pre-0019 schemas).
        extra={} if endpoint==GATEWAY_ENDPOINT else {'endpoint':endpoint}
        record=self._store.save(digest,organization_id,expected_revision,binding,encrypted,**extra)
        self._cipher.verify(organization_id,record)
        if record.revision!=expected_revision+1 or record.binding_id!=binding or record.endpoint!=endpoint:
            raise GatewayUnavailable()
        return GatewayStatus('SAVED_UNVERIFIED',record.revision,record.endpoint,tuple(sorted(self.allowed_endpoints)))
