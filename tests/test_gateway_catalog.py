import hashlib
import json
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uuid import uuid4

from forge.model_catalog import Verification
from forge.model_catalog_store import decode_catalog, encode_catalog


class UnknownCatalogTests(unittest.TestCase):
    def test_ids_only_discovery_roundtrips_without_capability_claims(self):
        org, binding = uuid4(), uuid4()
        capabilities = {key: None for key in (
            'input_modalities', 'output_modalities', 'tools', 'streaming',
            'max_context_tokens', 'max_output_tokens')}
        capabilities.update(capability_state='unknown', verification='unverified')
        document = {'schema_version': 2, 'organization_id': str(org),
                    'router_binding_id': str(binding), 'revision': 1, 'aliases': [
            {'name': 'assistant', 'routes': [{'organization_id': str(org),
                'router_binding_id': str(binding), 'route_id': str(uuid4()),
                'evidence_id': str(uuid4()), 'verification': 'unverified',
                'capabilities': capabilities}]}]}
        payload = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        checksum = hashlib.sha256(payload.encode()).hexdigest()
        snapshot = decode_catalog(payload, checksum)
        self.assertEqual(encode_catalog(snapshot), (payload, checksum))
        model = snapshot.public_projection()['models'][0]
        self.assertEqual(model, {'id': 'assistant', **capabilities})
        self.assertIs(snapshot.aliases[0].routes[0].verification, Verification.UNVERIFIED)


if __name__ == '__main__':
    unittest.main()

from dataclasses import replace
from unittest.mock import AsyncMock,MagicMock
from cryptography.fernet import Fernet
from forge.gateway_configuration import GatewayCipher,GatewayRecord,GatewayConflict,GatewayUnavailable,GATEWAY_ENDPOINT
from forge.gateway_catalog import GatewayCatalog,Discovery
from forge.model_catalog_store import CatalogStorageError

class CatalogServiceTests(unittest.TestCase):
    def setUp(self):
        self.org,self.binding=uuid4(),uuid4()
        self.cipher=GatewayCipher(Fernet.generate_key())
        self.record=GatewayRecord(1,self.binding,GATEWAY_ENDPOINT,self.cipher.seal(self.org,self.binding,1,'labelled-key'))
        self.store=MagicMock();self.adapter=MagicMock()
        self.store.gateway.return_value=self.record
        self.store.discovery.return_value=Discovery(self.record,('private/a','private/b'))
        self.store.publish.return_value=1
        self.store.ceiling.return_value=None
        self.adapter.discover.return_value=('private/a','private/b')
        self.adapter.discover_async=AsyncMock(return_value=('private/a','private/b'))
        self.service=GatewayCatalog(self.store,self.cipher,self.adapter)
        self.token='A'*43

    def test_refresh_revalidates_store_after_decryption_and_fetch(self):
        result=self.service.refresh(self.token,self.org)
        self.adapter.discover.assert_called_once_with('labelled-key')
        self.assertEqual(result['verification'],'unverified')
        self.store.save_discovery.assert_called_once()
        self.assertNotIn('labelled-key',str(result))

    def test_refresh_lists_only_the_discovered_models_inside_the_platform_ceiling_but_stores_the_whole_discovery(self):
        for ceiling,listed in ((None,['private/a','private/b']),(['private/b','not-discovered'],['private/b']),([],[])):
            with self.subTest(ceiling=ceiling):
                self.store.ceiling.return_value=ceiling;self.store.save_discovery.reset_mock()
                self.assertEqual(self.service.refresh(self.token,self.org)['model_ids'],listed)
                self.assertEqual(self.store.save_discovery.call_args.args[3],('private/a','private/b'))

    def test_the_asynchronous_refresh_applies_the_same_ceiling(self):
        import asyncio
        self.store.ceiling.return_value=['private/a']
        result=asyncio.run(self.service.refresh_async(self.token,self.org))
        self.assertEqual(result['model_ids'],['private/a'])
        self.assertEqual(self.store.save_discovery.call_args.args[3],('private/a','private/b'))

    def test_a_publication_the_database_refuses_for_the_ceiling_surfaces_as_its_own_error(self):
        from forge.gateway_configuration import GatewayOutsideCeiling
        self.store.publish.side_effect=GatewayOutsideCeiling()
        with self.assertRaises(GatewayOutsideCeiling):self.service.publish(self.token,self.org,uuid4(),0,1,{'a':'private/a'},'a')

    def test_wrong_cipher_binding_never_calls_network(self):
        self.store.gateway.return_value=replace(self.record,binding_id=uuid4())
        with self.assertRaises(GatewayUnavailable):self.service.refresh(self.token,self.org)
        self.adapter.discover.assert_not_called();self.store.save_discovery.assert_not_called()

    def test_only_trusted_discovered_ids_can_publish(self):
        for aliases,default in (({'a':'not-discovered'},'a'),({'BAD':'private/a'},'BAD'),({'a':'private/a'},'b')):
            with self.assertRaises(ValueError):self.service.publish(self.token,self.org,uuid4(),0,1,aliases,default)
        self.store.publish.assert_not_called()

    def test_gateway_revision_must_match_and_boolean_is_not_revision(self):
        with self.assertRaises(GatewayConflict):self.service.publish(self.token,self.org,uuid4(),0,2,{'a':'private/a'},'a')
        with self.assertRaises(ValueError):self.service.publish(self.token,self.org,uuid4(),True,1,{'a':'private/a'},'a')
        self.store.publish.assert_not_called()

    def test_stable_codec_and_replay_material_include_mapping_default_revision(self):
        operation=uuid4();mapping={'assistant':'private/a','fast':'private/b'}
        first=self.service.publish(self.token,self.org,operation,0,1,mapping,'assistant')
        args=self.store.publish.call_args.args
        self.assertEqual(first,{'revision':1,'default_model':'assistant','models':['assistant','fast']})
        self.service.publish(self.token,self.org,operation,0,1,dict(reversed(tuple(mapping.items()))),'assistant')
        self.assertEqual(self.store.publish.call_args.args,args)
        self.service.publish(self.token,self.org,operation,0,1,mapping,'fast')
        self.assertNotEqual(self.store.publish.call_args.args[-1],args[-1])
        snapshot=decode_catalog(args[-3],args[-2])
        self.assertEqual(snapshot.aliases[0].capabilities.public_projection()['capability_state'],'unknown')

    def test_member_read_only_returns_allowlisted_aliases(self):
        self.service.publish(self.token,self.org,uuid4(),0,1,{'assistant':'private/a'},'assistant')
        args=self.store.publish.call_args.args
        self.store.member_catalog.return_value=(*args[-3:-1],'assistant')
        result=self.service.read(self.token,self.org)
        for secret in ('private/a',str(self.binding),'route_id','evidence_id','labelled-key'):
            self.assertNotIn(secret,str(result))
        self.assertIsNone(result['models'][0]['streaming'])

    def test_unknown_codec_rejects_claims_and_known_only_v2(self):
        self.service.publish(self.token,self.org,uuid4(),0,1,{'assistant':'private/a'},'assistant')
        payload=self.store.publish.call_args.args[-3]
        for mutation in (lambda d:d['aliases'][0]['routes'][0]['capabilities'].update(tools=True),
                         lambda d:d['aliases'][0]['routes'][0].update(verification='verified'),
                         lambda d:d.update(schema_version=1)):
            document=json.loads(payload);mutation(document)
            changed=json.dumps(document,sort_keys=True,separators=(',',':'))
            with self.assertRaises(CatalogStorageError):decode_catalog(changed,hashlib.sha256(changed.encode()).hexdigest())


class AdminMetadataDomainTests(unittest.TestCase):
    def test_exact_authoritative_status_and_invalid_store_data(self):
        from forge.gateway_catalog import GatewayCatalog
        from forge.gateway_configuration import GatewayUnavailable
        store=MagicMock();service=GatewayCatalog(store,MagicMock(),MagicMock());org=uuid4();token='A'*43
        for row in ((0,None,'UNPUBLISHED'),(1,'assistant','CURRENT'),(9,'assistant','STALE_GATEWAY')):
            store.admin_status.return_value=row
            self.assertEqual(service.admin_status(token,org),dict(zip(('catalogue_revision','default_model','publication_state'),row)))
        for row in ((True,None,'UNPUBLISHED'),(0,'assistant','CURRENT'),(1,None,'CURRENT'),(0,None,'CURRENT'),(1,'private/route','CURRENT')):
            store.admin_status.return_value=row
            with self.assertRaises(GatewayUnavailable):service.admin_status(token,org)
