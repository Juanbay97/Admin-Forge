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
from forge.invitation_delivery import DeliveryReceipt, LocalTestMailbox, onboarding_link

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
            receipt=mailbox.deliver(identifier,"Invitee@Example.com","<script>& Name",link)
            target=Path(owned).resolve()/f"{identifier}.eml"
            self.assertEqual(receipt,DeliveryReceipt('local_test_mailbox',f'<{identifier}@forge.local-test.invalid>'))
            self.assertTrue(target.is_file())  # the .eml is written exactly where it always was
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

    def test_company_code_is_a_query_hint_before_the_fragment_and_never_the_capability(self):
        identifier,token=uuid4(),secrets.token_urlsafe(32)
        link=onboarding_link("https://onboarding.example.com",identifier,token,company_code="acme")
        self.assertEqual(link,f"https://onboarding.example.com/onboarding?c=acme#invitation_id={identifier}&capability={token}")
        self.assertNotIn(token,link.split("#")[0])
        self.assertEqual(onboarding_link("https://onboarding.example.com",identifier,token,company_code="a-1"),
                         f"https://onboarding.example.com/onboarding?c=a-1#invitation_id={identifier}&capability={token}")

    def test_without_a_company_code_the_link_is_the_previous_form(self):
        identifier,token=uuid4(),secrets.token_urlsafe(32)
        self.assertEqual(onboarding_link("https://onboarding.example.com",identifier,token),
                         f"https://onboarding.example.com/onboarding#invitation_id={identifier}&capability={token}")
        self.assertEqual(onboarding_link("https://onboarding.example.com",identifier,token,company_code=None),
                         onboarding_link("https://onboarding.example.com",identifier,token))

    def test_a_malformed_company_code_is_refused(self):
        for code in ("","Acme","a b","-acme","acme&x=1","acme#frag","a"*64,"ac\nme",7):
            with self.subTest(code=code),self.assertRaises(ValueError):
                onboarding_link("https://onboarding.example.com",uuid4(),secrets.token_urlsafe(32),company_code=code)

    def test_every_adapter_reports_its_own_channel_through_the_coordinator(self):
        class Adapter:
            def __init__(self,channel):
                self.channel=channel
        for channel in ('smtp','local_test_mailbox'):
            with self.subTest(channel=channel):
                coordinator=DeliveryCoordinator(MagicMock(),Adapter(channel),origin='https://onboarding.example.com',
                                                encryption_key=Fernet.generate_key())
                self.assertEqual(coordinator.channel,channel)
        with TemporaryDirectory() as owned:
            mailbox=LocalTestMailbox(Path(owned),sender='forge@example.com')
            self.assertEqual(DeliveryCoordinator(MagicMock(),mailbox,origin='https://onboarding.example.com',
                                                 encryption_key=Fernet.generate_key()).channel,'local_test_mailbox')

    def test_an_adapter_that_does_not_name_a_valid_channel_is_never_reported(self):
        for adapter in (MagicMock(),type('NoChannel',(),{})(),type('Bad',(),{'channel':'Not A Channel'})()):
            coordinator=DeliveryCoordinator(MagicMock(),adapter,origin='https://onboarding.example.com',
                                            encryption_key=Fernet.generate_key())
            with self.subTest(adapter=type(adapter).__name__),self.assertRaises(ValueError):
                coordinator.channel

    def test_the_coordinator_ignores_whatever_receipt_an_adapter_returns(self):
        store=MagicMock()
        store.queue_invitation.return_value=True
        store.finish.return_value=True
        adapter=MagicMock()
        adapter.deliver.return_value=object()  # not a path, not a receipt: dispatch must not depend on it
        coordinator=DeliveryCoordinator(store,adapter,origin='https://onboarding.example.com',encryption_key=Fernet.generate_key())
        issued=IssuedInvitation(uuid4(),secrets.token_urlsafe(32),datetime.now(timezone.utc)+timedelta(hours=1))
        message=coordinator.queue_invitation(issued,InvitationRequest(uuid4(),uuid4(),uuid4(),'a@example.com','Name'))
        store.claim.return_value=store.queue_invitation.call_args.args[-1]
        self.assertEqual(coordinator.dispatch(message),DeliveryState.DELIVERED)