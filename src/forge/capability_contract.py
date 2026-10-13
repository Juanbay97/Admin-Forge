"""The separately pinned ``forge.capability-policy.v1`` contract: document schema, canonicalization and signature test vectors.

``python -m forge.capability_contract --write`` regenerates ``contract/forge-capability-policy.v1.json`` and ``--check`` fails when the
committed file differs. The vectors are signed with a published TEST key (never a deployment key) so any client implementation can
prove its canonicalization and verification against them; they are built through the real resolver so they stay realistic. The
MVP contract pin (``contract/forge-mvp.contract.json``) is unaffected: this contract is a separate file and the routes are hidden.
"""
import hashlib
import json
from pathlib import Path
import sys

from forge.capability_policy import CatalogEntry, Layer, resolve
from forge.capability_signing import KEYS_SCHEMA, LIFETIME_SECONDS, SCHEMA, PolicySigner, canonical, timestamp

COMMITTED_PATH = Path(__file__).resolve().parents[2]/'contract'/'forge-capability-policy.v1.json'
TEST_SEED = hashlib.sha256(b'forge.capability-policy.v1 test vectors').digest()
OTHER_SEED = hashlib.sha256(b'forge.capability-policy.v1 foreign key').digest()
NOW = 1_800_000_000
ORG = '11111111-1111-4111-8111-111111111111'
PIN = hashlib.sha256(b'<!doctype html><title>hello</title>').hexdigest()


def _entries():
    return [CatalogEntry('app:acme.hello', 'app', '1.2.3', 'medium', False, 'off', 0, PIN, 'none', ('ui.title', 'storage.local'), ('ui.title',)),
            CatalogEntry('connector:github', 'connector', '1.0.0', 'medium', True, 'on', 0, None, 'server'),
            CatalogEntry('skill:pdf', 'skill', '1.0.0', 'low', True, 'on', 0, None, 'none'),
            CatalogEntry('tool:bash', 'tool', '1.0.0', 'high', False, 'on', 4, None, 'none'),
            CatalogEntry('tool:code_execute', 'tool', '1.0.0', 'high', False, 'on', 3, None, 'none')]


def _document(level, *, platform=None, company=None, org=None, platform_epoch=5, org_epoch=3, issued=NOW):
    items = resolve(_entries(), platform or {}, company or {}, org or {}, level)
    return {'schema': SCHEMA, 'org': ORG, 'platform_epoch': platform_epoch, 'org_epoch': org_epoch, 'issued_at': timestamp(issued),
            'expires_at': timestamp(issued + LIFETIME_SECONDS), 'reported_level': level, 'capabilities': [item.view() for item in items]}


def build():
    signer, other = PolicySigner(TEST_SEED), PolicySigner(OTHER_SEED)
    base = signer.sign(_document(2))
    locked = signer.sign(_document(4, platform={'skill:pdf': Layer(None, 'forced_off')}, org={'app:acme.hello': True}, org_epoch=4))
    tampered = {**base, 'capabilities': [{**item, 'enabled': True, 'state': 'on'} if item['id'] == 'code_execute' else item for item in base['capabilities']]}
    foreign = other.sign(_document(2))
    vectors = [
        ('base_set_at_level_2', 'The base skills and connectors are on; code_execute is blocked_attestation below level 3 and bash below level 4.', base, NOW, 'valid', None),
        ('locked_and_app_at_level_4', 'A force-off lock wins; an enabled app lists only granted permissions with its entry pin; every exec tool is on at level 4.', locked, NOW, 'valid', None),
        ('tampered_state', 'A client that flips code_execute to on after signing must fail verification.', tampered, NOW, 'bad_signature', None),
        ('unknown_key_id', 'A document signed by a key that is not in the published set.', foreign, NOW, 'unknown_key', None),
        ('expired_document', 'now is past expires_at.', base, NOW + LIFETIME_SECONDS + 1, 'expired', None),
        ('epoch_rollback', 'The client already saw platform_epoch 9: an older document is rejected.', base, NOW, 'rollback', [9, 0]),
    ]
    rendered = []
    for name, description, document, now, expect, minimum in vectors:
        item = {'name': name, 'description': description, 'document': document, 'canonical': canonical(document).decode('ascii'), 'now': now, 'expect': expect}
        if minimum:
            item['minimum_epochs'] = minimum
        rendered.append(item)
    return {
        'contract_version': SCHEMA,
        'note': 'Signature vectors made with the published TEST key below; never a deployment key. Ed25519 is deterministic, so the file is reproducible.',
        'schema': {
            'document': {'schema': 'string = "%s"' % SCHEMA, 'org': 'organization uuid', 'platform_epoch': 'integer >= 1, monotonic', 'org_epoch': 'integer >= 1, monotonic',
                         'issued_at': 'UTC, YYYY-MM-DDTHH:MM:SSZ', 'expires_at': 'issued_at + 24h', 'reported_level': 'integer 0..4 (attestation level the client reported; missing or invalid = 0)',
                         'capabilities': 'array of {id (bare slug), kind, state, enabled, reason?, min_sandbox_level, version, manifest_sha256, credential_locus, granted_permissions? (apps only)}',
                         'kid': 'key id = first 16 hex of sha256(raw public key)', 'sig': 'base64url (no padding) Ed25519 signature'},
            'states': ['on', 'off', 'forced_off', 'blocked_attestation'],
            'kinds': ['tool', 'skill', 'connector', 'plugin', 'app'],
            'canonicalization': 'json.dumps(document without sig, sort_keys=True, separators=(",", ":"), ensure_ascii=True)',
            'verification': 'known kid, then Ed25519 over the canonical bytes, then now < expires_at, then both epochs >= the highest seen',
            'attestation_levels': {'0': 'none', '1': 'workspace jail and environment scrub', '2': 'isolated process with limits', '3': 'level 2 plus egress guard and escape suite (code_execute)',
                                   '4': 'container runner (bash, powershell)'},
            'key_set_route': 'GET /forge/v1/capabilities/keys',
            'effective_route': 'GET /forge/v1/capabilities/effective?sandbox_level=N',
        },
        'key_set': {'schema': KEYS_SCHEMA, 'keys': signer.keyset()['keys']},
        'vectors': rendered,
    }


def render(document):
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + '\n'


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    document = build()
    if argv == ['--write']:
        COMMITTED_PATH.parent.mkdir(exist_ok=True)
        COMMITTED_PATH.write_text(render(document), 'utf-8', newline='\n')
        return 0
    if argv == ['--check']:
        return 0 if json.loads(COMMITTED_PATH.read_text('utf-8')) == document else 1
    print('usage: python -m forge.capability_contract (--write | --check)', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
