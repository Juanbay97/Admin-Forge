"""Private delivery ports: the local-test mailbox (no network, no SMTP claim) and the shared message builder."""
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime
from datetime import datetime, timezone
from html import escape
import os
from pathlib import Path
import re
from typing import Protocol
from dataclasses import dataclass
from enum import Enum
import json
from cryptography.fernet import Fernet
from uuid import uuid4
from forge.account_store import EnrollmentConnection
from forge.invitations import InvitationUnavailable, IssuedInvitation, InvitationRequest
from forge.account_sessions import ResetIntent
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from forge.accounts import canonical_email, display_name
from forge.invitations import capability_digest


class MessageDelivery(Protocol):
    channel: str
    def deliver(self, message_id: UUID, recipient: str, name: str, link: str, *, purpose: str="invitation") -> "DeliveryReceipt":
        ...


def trusted_origin(value: str) -> str:
    """Fixed configuration only, never request Host or an unvalidated redirect."""
    if type(value) is not str or len(value)>300 or not value.isascii() or any(c.isspace() for c in value):
        raise ValueError("Invalid onboarding origin.")
    try:
        parsed=urlsplit(value)
        port=parsed.port
    except ValueError:
        raise ValueError("Invalid onboarding origin.") from None
    if (parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
            or parsed.netloc.endswith(':') or (port is not None and not 1<=port<=65535)
            or not re.fullmatch(r'[A-Za-z0-9.\[\]:-]+',parsed.netloc)):
        raise ValueError("Invalid onboarding origin.")
    if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError("Plain HTTP is only permitted for an explicitly configured loopback origin.")
    return value


COMPANY_CODE=re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
CHANNEL=re.compile(r'[a-z][a-z_]{0,31}')


def onboarding_link(origin: str, invitation_id: UUID, capability: str, company_code: str | None=None) -> str:
    """The capability stays in the fragment; the optional public company code is only a `c=` query hint before it."""
    origin=trusted_origin(origin)
    if type(invitation_id) is not UUID:
        raise ValueError("Invalid invitation identifier.")
    capability_digest(capability)
    if company_code is not None and (type(company_code) is not str or not COMPANY_CODE.fullmatch(company_code)):
        raise ValueError("Invalid company code.")
    hint='' if company_code is None else '?'+urlencode({'c':company_code})
    return origin+'/onboarding'+hint+'#'+urlencode({'invitation_id':str(invitation_id),'capability':capability})


@dataclass(frozen=True)
class DeliveryReceipt:
    """Opaque and non-secret: the channel that carried the message and a reference to it (its message id)."""
    channel: str
    reference: str


def build_message(sender: str, recipient: str, name: str, link: str, purpose: str, message_id: UUID,
                  *, domain: str='forge.local-test.invalid') -> EmailMessage:
    """The one message every delivery adapter sends: the recipient's name and the private link, nothing else."""
    if type(message_id) is not UUID:
        raise ValueError("Invalid local message identifier.")
    sender,recipient,name=canonical_email(sender),canonical_email(recipient),display_name(name)
    if purpose not in ('invitation','password_reset'):
        raise ValueError('Unsupported private message purpose.')
    if type(link) is not str or len(link)>1024 or any(ord(c)<32 for c in link):
        raise ValueError("Invalid private onboarding link.")
    parsed=urlsplit(link)
    trusted_origin(parsed.scheme+'://'+parsed.netloc)
    message=EmailMessage(policy=SMTP)
    message['From']=sender
    message['To']=recipient
    message['Subject']='Your Forge invitation' if purpose=='invitation' else 'Reset your Forge password'
    message['Date']=format_datetime(datetime.now(timezone.utc))
    message['Message-ID']=f'<{message_id}@{domain}>'
    message.set_content(f'Hello {name},\n\nSet your Forge password using this private link:\n{link}\n\nThis invitation expires and can be used only once.\n')
    message.add_alternative(f'<p>Hello {escape(name)},</p><p><a href="{escape(link,quote=True)}">Set your Forge password</a></p><p>This private invitation expires and can be used only once.</p>',subtype='html')
    return message


class LocalTestMailbox:
    """Write .eml messages in an explicitly supplied caller-owned private folder.

    The caller must restrict folder ACLs, especially on Windows: mode0600 alone
    cannot guarantee a private Windows ACL. Never use a public/static assets path.
    This output is local test delivery, not a claim of SMTP mail being sent.
    """
    channel='local_test_mailbox'

    def __init__(self, directory: Path, *, sender: str):
        if not isinstance(directory,Path) or directory.is_symlink() or not directory.is_dir():
            raise ValueError("A caller-owned private mailbox directory is required.")
        self.directory=directory.resolve(strict=True)
        self.sender=canonical_email(sender)

    def deliver(self, message_id: UUID, recipient: str, name: str, link: str, *, purpose: str="invitation") -> DeliveryReceipt:
        message=build_message(self.sender,recipient,name,link,purpose,message_id)
        target=self.directory/(str(message_id)+'.eml')
        if self.directory.is_symlink() or not self.directory.is_dir():
            raise ValueError("Local mailbox configuration changed.")
        descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            with os.fdopen(descriptor,'wb') as output:
                output.write(message.as_bytes())
                output.flush()
                os.fsync(output.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return DeliveryReceipt(self.channel,str(message['Message-ID']))


class DeliveryState(str, Enum):
    PENDING='pending'
    DELIVERED='delivered'
    FAILED='failed'


class DeliveryStore(Protocol):
    def queue_invitation(self,message: UUID,invitation: UUID,digest: str,payload: str) -> bool:
        ...
    def queue_reset(self,message: UUID,digest: str,payload: str) -> bool:
        ...
    def claim(self,message: UUID,lease: UUID) -> str | None:
        ...
    def finish(self,message: UUID,lease: UUID,delivered: bool) -> bool:
        ...


class DeliveryCoordinator:
    """Explicit encryption key and adapter, no ambient registry or SMTP fallback.

    A caller must retain this key separately from the database and configure a
    private mailbox folder. Encryption protects durable retry tokens; .eml files
    intentionally contain private links and must never be public/static assets.
    """
    def __init__(self,store: DeliveryStore,adapter: MessageDelivery,*,origin: str,encryption_key: bytes):
        if type(encryption_key) is not bytes:
            raise ValueError('Explicit Fernet key bytes are required.')
        self._cipher=Fernet(encryption_key)
        self.origin=trusted_origin(origin)
        self.store,self.adapter=store,adapter

    @property
    def channel(self) -> str:
        """The channel the adapter really uses, so the API never claims one it does not."""
        channel=getattr(self.adapter,'channel',None)
        if type(channel) is not str or not CHANNEL.fullmatch(channel):
            raise ValueError('The delivery adapter must name its channel.')
        return channel

    def _payload(self,purpose: str,recipient: str,name: str,link: str) -> str:
        document={'version':1,'purpose':purpose,'recipient':canonical_email(recipient),
                  'name':display_name(name),'link':link}
        data=json.dumps(document,separators=(',',':'),ensure_ascii=True).encode('utf-8')
        if len(data)>4096:
            raise ValueError('Private delivery payload exceeds its bound.')
        return self._cipher.encrypt(data).decode('ascii')

    def queue_invitation(self,issued: IssuedInvitation,request: InvitationRequest,company_code: str | None=None) -> UUID:
        message=uuid4()
        link=onboarding_link(self.origin,issued.invitation_id,issued.capability,company_code)
        payload=self._payload('invitation',request.email,request.name,link)
        if not self.store.queue_invitation(message,issued.invitation_id,capability_digest(issued.capability),payload):
            raise InvitationUnavailable()
        return message

    def queue_reset(self,intent: ResetIntent) -> UUID:
        message=uuid4()
        link=self.origin+'/reset-password#'+urlencode({'capability':intent.capability})
        payload=self._payload('password_reset',intent.recipient,intent.name,link)
        if not self.store.queue_reset(message,capability_digest(intent.capability),payload):
            raise InvitationUnavailable()
        return message

    def dispatch(self,message: UUID) -> DeliveryState:
        if type(message) is not UUID:
            raise ValueError('Invalid private message identifier.')
        lease=uuid4()
        payload=self.store.claim(message,lease)
        if payload is None:
            return DeliveryState.PENDING
        delivered=False
        try:
            if type(payload) is not str or not 100<=len(payload)<=16384:
                raise ValueError('Invalid private delivery payload.')
            data=self._cipher.decrypt(payload.encode('ascii'),ttl=604800)
            if len(data)>4096:
                raise ValueError('Private delivery payload exceeds its bound.')
            document=json.loads(data)
            if (type(document) is not dict or set(document)!={'version','purpose','recipient','name','link'}
                    or document['version']!=1 or document['purpose'] not in ('invitation','password_reset')):
                raise ValueError('Invalid private message version.')
            if not document['link'].startswith(self.origin+'/'):
                raise ValueError('Private message origin changed.')
            self.adapter.deliver(message,document['recipient'],document['name'],document['link'],purpose=document['purpose'])
            delivered=True
        except Exception:
            # Persist only a finite failure state; no diagnostic, recipient or link.
            delivered=False
        if not self.store.finish(message,lease,delivered):
            raise InvitationUnavailable()
        return DeliveryState.DELIVERED if delivered else DeliveryState.FAILED


class PostgresDeliveryStore:
    def __init__(self,pool,*,acquisition_timeout=1.0):
        self.connection=EnrollmentConnection(pool,acquisition_timeout=acquisition_timeout,role='forge_account_service')

    def queue_invitation(self,message,invitation,digest,payload):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_queue_message(%s,%s,%s,%s)',(message,invitation,digest,payload))
            return cursor.fetchone()==(True,)

    def queue_reset(self,message,digest,payload):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_queue_reset_message(%s,%s,%s)',(message,digest,payload))
            return cursor.fetchone()==(True,)

    def claim(self,message,lease):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_claim_message(%s,%s)',(message,lease))
            return cursor.fetchone()[0]

    def finish(self,message,lease,delivered):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT forge.account_finish_message(%s,%s,%s)',(message,lease,delivered))
            return cursor.fetchone()==(True,)
