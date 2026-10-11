"""Bound ciphertext and redacted status tests with labelled fixture keys only."""
from dataclasses import replace
from pathlib import Path
import secrets
import sys
import unittest
from uuid import uuid4
from cryptography.fernet import Fernet
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from forge.gateway_configuration import (GatewayCipher,GatewayConfiguration,GatewayRecord,
    GatewayStatus,GatewayConflict,GatewayUnavailable,GATEWAY_ENDPOINT)

KEY='fixture-only-new-exclusive-key'

class Store:
    def __init__(self): self.records={};self.digests=[]
    def read(self,digest,org):
        self.digests.append(digest);return self.records.get(org)
    def save(self,digest,org,expected,binding,encrypted):
        self.digests.append(digest)
        if self.records.get(org,GatewayStatus('NOT_CONFIGURED',0)).revision!=expected:
            raise GatewayConflict()
        value=GatewayRecord(expected+1,binding,GATEWAY_ENDPOINT,encrypted)
        self.records[org]=value;return value

class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.org=uuid4();self.token=secrets.token_urlsafe(32)
        self.key=Fernet.generate_key();self.cipher=GatewayCipher(self.key)
        self.store=Store();self.service=GatewayConfiguration(self.store,self.cipher)

    def test_saved_is_unverified_redacted_and_reopens(self):
        self.assertEqual(self.service.read(self.token,self.org).status,'NOT_CONFIGURED')
        result=self.service.save(self.token,self.org,0,KEY)
        self.assertEqual(result,GatewayStatus('SAVED_UNVERIFIED',1))
        self.assertNotIn(KEY,repr(result));self.assertNotIn(KEY,repr(self.store.records[self.org]))
        self.assertNotIn(KEY,self.store.records[self.org].encrypted_key)
        reopened=GatewayConfiguration(self.store,GatewayCipher(self.key))
        self.assertEqual(reopened.read(self.token,self.org),result)
        self.assertTrue(all(len(x)==64 and x!=self.token for x in self.store.digests))

    def test_stale_compare_and_swap_preserves_previous_record(self):
        self.service.save(self.token,self.org,0,KEY);old=self.store.records[self.org]
        with self.assertRaises(GatewayConflict):self.service.save(self.token,self.org,0,'different-fixture-key')
        self.assertEqual(self.store.records[self.org],old)
        self.assertEqual(self.service.save(self.token,self.org,1,KEY).revision,2)

    def test_wrong_key_and_ciphertext_binding_substitution_fail_closed(self):
        self.service.save(self.token,self.org,0,KEY);record=self.store.records[self.org]
        for mutated in (replace(record,revision=2),replace(record,binding_id=uuid4()),
                        replace(record,endpoint='https://untrusted.invalid'),replace(record,encrypted_key='x'*200)):
            with self.subTest(record=mutated),self.assertRaises(GatewayUnavailable):
                self.cipher.verify(self.org,mutated)
        with self.assertRaises(GatewayUnavailable):self.cipher.verify(uuid4(),record)
        with self.assertRaises(GatewayUnavailable):GatewayCipher(Fernet.generate_key()).verify(self.org,record)

    def test_plaintext_and_unicode_inputs_never_enter_store(self):
        for key in ('','fixture secret','x'*4097,'private\nkey','nonasciié',None):
            with self.subTest(key_type=type(key).__name__),self.assertRaises(ValueError) as caught:
                self.service.save(self.token,self.org,0,key)
            self.assertNotIn('private',str(caught.exception))
        self.assertEqual(self.store.records,{})

    def test_explicit_key_and_strict_revision_required(self):
        for value in (None,'notbytes',b'invalid'):
            with self.assertRaises(ValueError):GatewayCipher(value)
        for revision in (-1,True,1.1,2**63):
            with self.assertRaises(ValueError):self.service.save(self.token,self.org,revision,KEY)
        self.assertEqual(self.store.records,{})

    def test_ciphertext_is_randomized(self):
        binding=uuid4()
        self.assertNotEqual(self.cipher.seal(self.org,binding,1,KEY),self.cipher.seal(self.org,binding,1,KEY))
