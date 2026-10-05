"""Offline genuine RSA authority; storage spy is not an authentication substitute."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
import unittest
from uuid import UUID, uuid4
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from forge.entra import EntraTokenValidator
from forge.administration import *
from test_entra import config, FakeFetcher, issuer, TENANT, OID, CLIENT, AUDIENCE, NOW

ORG = UUID(int=1)
MEMBER = UUID(int=21)
ACTOR = UUID(int=700)

class RecordingStore:
    def __init__(self): self.calls = []
    def _designate(self, operator, request, allowed_tenants):
        self.calls.append((operator, request, allowed_tenants))
        return DesignationResult(request.organization_id, request.membership_id,
                                 request.operation_id, uuid4(), request.expected_revision+1)

class AdministrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.fetcher = FakeFetcher(self.key)
        self.validator = EntraTokenValidator(config(),fetcher=self.fetcher,
            clock=lambda:NOW,monotonic_clock=lambda:100)
        self.operator = DeploymentOperator(issuer(),UUID(TENANT),UUID(OID),ACTOR)
        self.configuration = DesignationConfiguration((self.operator,),{ORG:frozenset({UUID(TENANT)})})
        self.store = RecordingStore()
        self.service = InitialAdministratorService(self.validator,self.store,self.configuration)
        self.request = DesignationRequest(ORG,MEMBER,uuid4(),1)
    def token(self, **changes):
        claims=dict(iss=issuer(),tid=TENANT,oid=OID,sub="operator-actual-sub",aud=AUDIENCE,
                    ver="2.0",azp=CLIENT,scp="forge.read",exp=NOW+60,nbf=NOW-5,iat=NOW-5)
        return jwt.encode(claims|changes,self.key,algorithm="RS256",headers={"kid":"key-1"})
    def test_valid_signed_operator_reaches_storage(self):
        try: result=self.service.designate(self.token(),self.request)
        except DesignationDenied: result=None
        self.assertIsNotNone(result)
        self.assertEqual(len(self.store.calls),1)
        self.assertEqual(self.store.calls[0][0].actor_id,ACTOR)

    def test_missing_or_empty_config_denies_without_storage(self):
        for cfg in (None,DesignationConfiguration((),{}),
                DesignationConfiguration((self.operator,),{})):
            with self.subTest(configuration=cfg):
                service=InitialAdministratorService(self.validator,self.store,cfg)
                with self.assertRaises(DesignationDenied):service.designate(self.token(),self.request)
        self.assertEqual(self.store.calls,[])

    def test_invalid_requests_deny_before_borrow(self):
        from dataclasses import replace
        for key,value in (("organization_id",str(ORG)),("membership_id",None),
                ("operation_id","missing"),("expected_revision",True),
                ("expected_revision",0),("expected_revision",-1),("expected_revision",1.0),
                ("expected_revision",float("nan")),("expected_revision",float("inf")),
                ("expected_revision",10**400),("expected_revision",2**63-1)):
            with self.subTest(key=key,value=value),self.assertRaises(DesignationDenied):
                self.service.designate(self.token(),replace(self.request,**{key:value}))
        with self.assertRaises(DesignationDenied):self.service.designate(self.token(),object())
        self.assertEqual(self.store.calls,[])

    def test_claimed_roles_email_and_tenant_admin_are_not_operator_authority(self):
        token=self.token(oid=str(UUID(int=900)),roles=["Global Administrator"],email="untrusted@example.invalid")
        with self.assertRaises(DesignationDenied):self.service.designate(token,self.request)
        self.assertEqual(self.store.calls,[])

    def test_operator_identity_uses_oid_not_sub(self):
        result=self.service.designate(self.token(sub="different-application-sub"),self.request)
        self.assertEqual(result.revision,2)
        self.assertEqual(self.store.calls[0][0].actor_id,ACTOR)

    def test_real_invalid_signature_and_claims_never_reach_storage(self):
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        original=self.key
        try:
            self.key=other
            invalid=self.token()
        finally:self.key=original
        tokens=[invalid,self.token(exp=NOW-90,nbf=NOW-200,iat=NOW-200),self.token(aud="https://graph.microsoft.com"),
                self.token(scp="",idtyp="app"),self.token(ver="1.0"),
                self.token(azp=str(UUID(int=901))),"not-a-token"]
        for token in tokens:
            with self.subTest(token_shape=token[:8]),self.assertRaises(DesignationDenied):
                self.service.designate(token,self.request)
        self.assertEqual(self.store.calls,[])

    def test_replay_is_freshly_authenticated_before_every_storage_call(self):
        self.service.designate(self.token(),self.request)
        self.service.designate(self.token(sub="another-valid-sub"),self.request)
        self.assertEqual(len(self.store.calls),2)
        with self.assertRaises(DesignationDenied):
            self.service.designate(self.token(exp=NOW-90,nbf=NOW-200,iat=NOW-200),self.request)
        self.assertEqual(len(self.store.calls),2)

    def test_revoked_deployment_operator_denies_replay_without_storage(self):
        self.service.designate(self.token(),self.request)
        revoked=InitialAdministratorService(self.validator,self.store,
            DesignationConfiguration((),self.configuration.organization_tenants))
        with self.assertRaises(DesignationDenied):revoked.designate(self.token(),self.request)
        self.assertEqual(len(self.store.calls),1)

    def test_missing_organization_tenant_map_denies_before_storage(self):
        from dataclasses import replace
        with self.assertRaises(DesignationDenied):
            self.service.designate(self.token(),replace(self.request,organization_id=UUID(int=2)))
        self.assertEqual(self.store.calls,[])

    def test_validator_outage_is_redacted_not_auth_denial(self):
        self.fetcher.error=RuntimeError("PRIVATE_TOKEN_NETWORK_EXCEPTION")
        with self.assertRaises(DesignationUnavailable) as error:
            self.service.designate(self.token(),self.request)
        self.assertEqual(str(error.exception),"Initial designation unavailable.")
        self.assertTrue(error.exception.__suppress_context__)
        self.assertEqual(self.store.calls,[])

    def test_configuration_is_copied_and_nested_collections_frozen(self):
        from dataclasses import FrozenInstanceError
        operators=[self.operator];tenants={UUID(TENANT)};mapping={ORG:tenants}
        cfg=DesignationConfiguration(operators,mapping)
        operators.clear();tenants.clear();mapping.clear()
        self.assertEqual(cfg.operators,(self.operator,))
        self.assertEqual(cfg.organization_tenants[ORG],frozenset({UUID(TENANT)}))
        with self.assertRaises(TypeError):cfg.organization_tenants[ORG]=frozenset()
        with self.assertRaises(FrozenInstanceError):cfg.operators=()

    def test_configuration_rejects_ambiguous_and_malformed_entries(self):
        from dataclasses import replace
        for operators,mapping in (
                ((self.operator,self.operator),{ORG:{UUID(TENANT)}}),
                ((replace(self.operator,issuer="https://other.invalid/"),),{ORG:{UUID(TENANT)}}),
                ((replace(self.operator,actor_id="caller-id"),),{ORG:{UUID(TENANT)}}),
                ((self.operator,),{str(ORG):{UUID(TENANT)}}),
                ((self.operator,),{ORG:set()}),
                ((self.operator,),{ORG:{"not-a-guid"}}),
                ("operator",{ORG:{UUID(TENANT)}}),
                ((self.operator,),[])):
            with self.subTest(operators=type(operators),mapping=type(mapping)),self.assertRaises(ValueError):
                DesignationConfiguration(operators,mapping)
        for operators,mapping in (([self.operator]*65,{}),
                ((),{UUID(int=n):{UUID(TENANT)} for n in range(257)}),
                ((),{ORG:{UUID(int=n) for n in range(65)}})):
            with self.assertRaises(ValueError):DesignationConfiguration(operators,mapping)

    def test_dataclass_or_fake_validator_cannot_supply_authority(self):
        from forge.entra import VerifiedPrincipal
        with self.assertRaises(ValueError):InitialAdministratorService(object(),self.store,self.configuration)
        with self.assertRaises(DesignationDenied):
            self.service.designate(VerifiedPrincipal("sub",TENANT,OID,issuer()),self.request)
        with self.assertRaises(TypeError):
            DesignationRequest(ORG,MEMBER,uuid4(),1,actor_id=ACTOR)
        self.assertEqual(self.store.calls,[])

    def test_store_failure_and_bad_result_are_redacted(self):
        from dataclasses import replace
        class Faulty:
            def _designate(inner,*args):raise RuntimeError("PRIVATE_TOKEN_DB_EXCEPTION")
        with self.assertRaises(DesignationUnavailable) as error:
            InitialAdministratorService(self.validator,Faulty(),self.configuration).designate(self.token(),self.request)
        self.assertNotIn("PRIVATE",str(error.exception))
        for value in (None,DesignationResult(ORG,MEMBER,self.request.operation_id,uuid4(),2.0),
                DesignationResult(UUID(int=99),MEMBER,self.request.operation_id,uuid4(),2)):
            class Bad:
                def _designate(inner,*args):return value
            with self.assertRaises(DesignationUnavailable):
                InitialAdministratorService(self.validator,Bad(),self.configuration).designate(self.token(),self.request)

    def test_result_is_frozen_and_publication_remains_pending(self):
        from dataclasses import FrozenInstanceError
        result=self.service.designate(self.token(),self.request)
        self.assertEqual(result.audit_publication,"pending")
        with self.assertRaises(FrozenInstanceError):result.revision=3
        self.assertNotIn(str(ACTOR),repr(self.operator))

    def test_maximum_expected_revision_does_not_overflow(self):
        from dataclasses import replace
        value=self.service.designate(self.token(),replace(self.request,expected_revision=2**63-2))
        self.assertEqual(value.revision,2**63-1)

if __name__=="__main__":unittest.main()
