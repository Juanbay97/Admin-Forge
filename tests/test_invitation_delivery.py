"""Private local delivery, not SMTP or a claim that an email was sent."""
from email import policy
from email.parser import BytesParser
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from unittest.mock import MagicMock
from cryptography.fernet import Fernet
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from forge.invitations import IssuedInvitation,InvitationRequest,InvitationUnavailable
from forge.invitation_delivery import DeliveryCoordinator,DeliveryState
from forge.account_sessions import ResetIntent
from forge.invitation_delivery import LocalTestMailbox, onboarding_link

class DeliveryTests(unittest.TestCase):
    def test_fragment_link_uses_only_explicit_trusted_origin(self):
        identifier=uuid4()
        token=secrets.token_urlsafe(32)
        link=onboarding_link("https://onboarding.example.com",identifier,token)
        self.assertEqual(link,f"https://onboarding.example.com/onboarding#invitation_id={identifier}&capability={token}")
        self.assertNotIn(token,link.split("#")[0])
    def test_bad_origin_fails_closed(self):
        for origin in ("https://evil.test/path","https://a@evil.test","https://evil.test?x=1", "https://evil.test#fragment", "http://not-local.test", "https://evil.test\nInjected: bad", "https://evil.test:bad"):
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                onboarding_link(origin,uuid4(),secrets.token_urlsafe(32))
    def test_owned_message_has_valid_headers_and_escaped_html(self):
        with TemporaryDirectory() as owned:
            mailbox=LocalTestMailbox(Path(owned),sender="forge@example.com")
            identifier=uuid4()
            link=onboarding_link("http://127.0.0.1:8000",uuid4(),secrets.token_urlsafe(32))
            target=mailbox.deliver(identifier,"Invitee@Example.com","<script>& Name",link)
            self.assertEqual(target,Path(owned).resolve()/f"{identifier}.eml")
            message=BytesParser(policy=policy.default).parsebytes(target.read_bytes())
            self.assertEqual(str(message['To']),"invitee@example.com")
            self.assertEqual(str(message['From']),"forge@example.com")
            self.assertIn(link,message.get_body(preferencelist=('plain',)).get_content())
            body=message.get_body(preferencelist=('html',)).get_content()
            self.assertNotIn("<script>",body)
            self.assertIn("&lt;script&gt;&amp; Name",body)
    def test_header_injection_and_filename_input_rejected(self):
        with TemporaryDirectory() as owned:
            mailbox=LocalTestMailbox(Path(owned),sender="forge@example.com")
            with self.assertRaises(ValueError):
                mailbox.deliver("../outside", "a@example.com","Name","https://example.com")
            with self.assertRaises(ValueError):
                mailbox.deliver(uuid4(),"a@example.com\nBcc: bad@example.com","Name","https://example.com")
            self.assertEqual(list(Path(owned).iterdir()),[])
    def test_existing_message_never_overwritten(self):
        with TemporaryDirectory() as owned:
            mailbox=LocalTestMailbox(Path(owned),sender="forge@example.com")
            identifier=uuid4()
            mailbox.deliver(identifier,"a@example.com","Name","https://example.com")
            original=(Path(owned)/f"{identifier}.eml").read_bytes()
            with self.assertRaises(FileExistsError):
                mailbox.deliver(identifier,"b@example.com","Other","https://example.com")
            self.assertEqual((Path(owned)/f"{identifier}.eml").read_bytes(),original)

    def test_encrypted_retry_payload_and_failure_state_without_diagnostics(self):
        store=MagicMock()
        store.queue_invitation.return_value=True
        store.finish.return_value=True
        adapter=MagicMock()
        key=Fernet.generate_key()
        coordinator=DeliveryCoordinator(store,adapter,origin='https://onboarding.example.com',encryption_key=key)
        token=secrets.token_urlsafe(32)
        issued=IssuedInvitation(uuid4(),token,datetime.now(timezone.utc)+timedelta(hours=1))
        request=InvitationRequest(uuid4(),uuid4(),uuid4(),'a@example.com','Name')
        message=coordinator.queue_invitation(issued,request)
        payload=store.queue_invitation.call_args.args[-1]
        self.assertNotIn(token,payload)
        self.assertNotIn('a@example.com',payload)
        self.assertIn(token,Fernet(key).decrypt(payload.encode()).decode())
        store.claim.return_value=payload
        adapter.deliver.side_effect=RuntimeError('PRIVATE-token-password-dsn')
        self.assertEqual(coordinator.dispatch(message),DeliveryState.FAILED)
        self.assertEqual(store.finish.call_args.args[-1],False)
        self.assertNotIn('PRIVATE',repr(store.finish.call_args))
        adapter.deliver.side_effect=None
        self.assertEqual(coordinator.dispatch(message),DeliveryState.DELIVERED)
        self.assertEqual(store.finish.call_args.args[-1],True)

    def test_unclaimed_or_tampered_payload_never_delivers(self):
        store=MagicMock()
        store.finish.return_value=True
        adapter=MagicMock()
        coordinator=DeliveryCoordinator(store,adapter,origin='https://onboarding.example.com',encryption_key=Fernet.generate_key())
        store.claim.return_value=None
        self.assertEqual(coordinator.dispatch(uuid4()),DeliveryState.PENDING)
        store.finish.assert_not_called()
        store.claim.return_value='x'*120
        self.assertEqual(coordinator.dispatch(uuid4()),DeliveryState.FAILED)
        adapter.deliver.assert_not_called()

    def test_reset_capability_is_private_and_explicit_key_is_required(self):
        store=MagicMock()
        store.queue_reset.return_value=True
        key=Fernet.generate_key()
        coordinator=DeliveryCoordinator(store,MagicMock(),origin='http://localhost:8000',encryption_key=key)
        token=secrets.token_urlsafe(32)
        coordinator.queue_reset(ResetIntent(token,uuid4(),'a@example.com','Name'))
        payload=store.queue_reset.call_args.args[-1]
        decoded=Fernet(key).decrypt(payload.encode()).decode()
        self.assertIn('/reset-password#capability='+token,decoded)
        self.assertNotIn(token,payload)
        for invalid in (None,b'invalid','text'):
            with self.assertRaises((ValueError,TypeError)):
                DeliveryCoordinator(store,MagicMock(),origin='https://example.com',encryption_key=invalid)
