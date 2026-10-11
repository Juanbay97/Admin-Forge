"""Bound organization gateway credentials; no provider connection or key discovery."""
from dataclasses import dataclass
import json
import re
from typing import Protocol
from uuid import UUID,uuid4
from cryptography.fernet import Fernet
from forge.invitations import capability_digest

GATEWAY_ENDPOINT='https://ia.prometheonlab.com'
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

@dataclass(frozen=True)
class GatewayStatus:
    status: str
    revision: int
    endpoint: str=GATEWAY_ENDPOINT

class GatewayStore(Protocol):
    def read(self,digest: str,organization_id: UUID) -> GatewayRecord | None: ...
    def save(self,digest: str,organization_id: UUID,expected_revision: int,
             binding_id: UUID,encrypted_key: str) -> GatewayRecord: ...

class GatewayCipher:
    """Caller supplies a SEPARATE deployment key, not invitation delivery material.

    Ciphertext contains exact record binding; substitution/revision/org drift fails.
    Caller owns key separation/rotation. No ambient environment or fallback key.
    """
    def __init__(self,key: bytes):
        if type(key) is not bytes:
            raise ValueError('Explicit gateway encryption key required.')
        try: self._cipher=Fernet(key)
        except Exception: raise ValueError('Invalid gateway encryption key.') from None

    @staticmethod
    def validate_key(key: str):
        if type(key) is not str or not re.fullmatch(r'[!-~]{1,4096}',key):
            raise ValueError('Invalid gateway credential.')

    def seal(self,organization_id: UUID,binding_id: UUID,revision: int,key: str) -> str:
        self.validate_key(key)
        if type(organization_id) is not UUID or type(binding_id) is not UUID or type(revision) is not int or not 1<=revision<=MAX_REVISION+1:
            raise ValueError('Invalid gateway binding.')
        payload=json.dumps({'v':1,'organization':str(organization_id),'binding':str(binding_id),
            'revision':revision,'endpoint':GATEWAY_ENDPOINT,'key':key},sort_keys=True,separators=(',',':')).encode()
        return self._cipher.encrypt(payload).decode('ascii')

    def open_key(self,organization_id: UUID,record: GatewayRecord) -> str:
        """Private server-side use only, after fresh administrator or restricted member-route authorization."""
        try:
            if (type(record) is not GatewayRecord or type(record.revision) is not int
                    or not 1<=record.revision<=MAX_REVISION+1 or type(record.binding_id) is not UUID
                    or record.endpoint!=GATEWAY_ENDPOINT or type(record.encrypted_key) is not str
                    or not 100<=len(record.encrypted_key)<=12288):
                raise ValueError()
            payload=json.loads(self._cipher.decrypt(record.encrypted_key.encode('ascii')))
            self.validate_key(payload['key'])
            if payload!={'v':1,'organization':str(organization_id),'binding':str(record.binding_id),
                    'revision':record.revision,'endpoint':GATEWAY_ENDPOINT,'key':payload['key']}:
                raise ValueError()
            return payload["key"]
        except Exception:
            raise GatewayUnavailable() from None

    def verify(self,organization_id: UUID,record: GatewayRecord) -> None:
        self.open_key(organization_id,record)

class GatewayConfiguration:
    def __init__(self,store: GatewayStore,cipher: GatewayCipher):
        self._store,self._cipher=store,cipher

    def read(self,token: str,organization_id: UUID) -> GatewayStatus:
        digest=capability_digest(token)
        if type(organization_id) is not UUID: raise ValueError('Invalid organization.')
        record=self._store.read(digest,organization_id)
        if record is None: return GatewayStatus('NOT_CONFIGURED',0)
        self._cipher.verify(organization_id,record)
        return GatewayStatus('SAVED_UNVERIFIED',record.revision)

    def save(self,token: str,organization_id: UUID,expected_revision: int,key: str) -> GatewayStatus:
        digest=capability_digest(token)
        if type(organization_id) is not UUID or type(expected_revision) is not int or not 0<=expected_revision<=MAX_REVISION:
            raise ValueError('Invalid gateway revision.')
        binding=uuid4()
        encrypted=self._cipher.seal(organization_id,binding,expected_revision+1,key)
        record=self._store.save(digest,organization_id,expected_revision,binding,encrypted)
        self._cipher.verify(organization_id,record)
        if record.revision!=expected_revision+1 or record.binding_id!=binding:
            raise GatewayUnavailable()
        return GatewayStatus('SAVED_UNVERIFIED',record.revision)
