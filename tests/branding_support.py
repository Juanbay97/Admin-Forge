"""In-memory BrandingStore for API tests; the shared contract keeps it faithful to the database."""
from contextlib import contextmanager
import re
from threading import Lock
from uuid import uuid4

from forge.branding import ASSET_KINDS, DEFAULT, DEFAULT_INPUT, Branding, replace_code
from forge.branding_store import BrandingConflict, BrandingDenied, BrandingLimit, PublishedAsset

MAX_ASSETS = 24
_CODE = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
_SHA = re.compile(r'[0-9a-f]{64}')


class FakeBrandingStore:
    def __init__(self):
        self.lock = Lock()
        self.orgs, self.actors, self.calls = {}, {}, []

    # -- test setup -------------------------------------------------------------------------------
    def add_org(self, code, *, active=True):
        org = uuid4()
        self.orgs[org] = {'code': code, 'active': active, 'current': None, 'history': [], 'assets': {}}
        return org

    def add_actor(self, digest, org, role):
        self.actors.setdefault(digest, {})[org] = role

    # -- port -------------------------------------------------------------------------------------
    def _member(self, digest, org, *, admin):
        role = self.actors.get(digest, {}).get(org) if org in self.orgs else None
        if role is None or (admin and role != 'admin') or not self.orgs[org]['active']:
            raise BrandingDenied()
        return self.orgs[org]

    def read(self, digest, org):
        self.calls.append(('read', org))
        with self.lock:
            entry = self._member(digest, org, admin=False)
            return replace_code(entry['current'] or DEFAULT, entry['code'])

    def save(self, digest, org, expected, value, *, change='save'):
        self.calls.append((change, org))
        with self.lock:
            entry = self._member(digest, org, admin=True)
            revision = entry['current'].revision if entry['current'] else 0
            if expected != revision:
                raise BrandingConflict()
            if any(sha not in entry['assets'] for sha in value.assets.values()):
                raise ValueError('Invalid branding request.')
            entry['current'] = Branding(revision + 1, value.name, value.login_copy, value.primary, value.accent, value.tint,
                                        value.heading, value.body, {kind: value.assets[kind] for kind in ASSET_KINDS if kind in value.assets})
            entry['history'].append((change, entry['current']))
            return entry['current']

    def reset(self, digest, org, expected):
        return self.save(digest, org, expected, DEFAULT_INPUT, change='reset')

    def put_asset(self, digest, org, asset):
        self.calls.append(('put_asset', org))
        with self.lock:
            entry = self._member(digest, org, admin=True)
            if asset.sha256 in entry['assets']:
                return False
            if len(entry['assets']) >= MAX_ASSETS:
                raise BrandingLimit()
            entry['assets'][asset.sha256] = (asset.content_type, asset.data)
            return True

    def public(self, code):
        self.calls.append(('public', code))
        if type(code) is not str or not _CODE.fullmatch(code):
            return None
        with self.lock:
            for entry in self.orgs.values():
                if entry['code'] == code and entry['active']:
                    return entry['current'] or DEFAULT
        return None

    def asset(self, sha256):
        self.calls.append(('asset', sha256))
        if type(sha256) is not str or not _SHA.fullmatch(sha256):
            return None
        with self.lock:
            for entry in self.orgs.values():
                current = entry['current']
                if current is not None and sha256 in current.assets.values() and sha256 in entry['assets']:
                    return PublishedAsset(*entry['assets'][sha256])
        return None


class FakeHarness:
    """Two organizations (``org-a``, ``org-b``) with an administrator and, for A, a member each."""

    def __init__(self):
        self.store = FakeBrandingStore()
        self.code_a, self.code_b = 'org-a', 'org-b'
        self.org_a, self.org_b = self.store.add_org(self.code_a), self.store.add_org(self.code_b)
        self.admin_a, self.member_a, self.admin_b = 'a' * 64, 'b' * 64, 'c' * 64
        self.store.add_actor(self.admin_a, self.org_a, 'admin')
        self.store.add_actor(self.member_a, self.org_a, 'member')
        self.store.add_actor(self.admin_b, self.org_b, 'admin')

    def deactivate(self, code):
        for entry in self.store.orgs.values():
            if entry['code'] == code:
                entry['active'] = False


@contextmanager
def fake_harness():
    yield FakeHarness()
