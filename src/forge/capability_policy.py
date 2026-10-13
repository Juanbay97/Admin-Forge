"""Capability governance: the catalog entry, the policy layers and the pure resolver. No I/O, no clock, no randomness.

The database stores *layers* (platform default, company override, organization-administrator setting); this module is the one
place that turns them into an effective state, so precedence is unit-testable and written once.

Precedence, highest first: (1) a force-off lock at platform or company-override level, (2) the organization administrator's
setting, (3) the company override, (4) the platform default, (5) the catalog default. An id that is not in the catalog is
``off``. The sandbox attestation gate then applies to anything that resolved ``on`` and has a minimum level: below the
reported level it is ``blocked_attestation``, and nothing an administrator writes can lift that.

Attestation scale (owned by the client, ``backend/app/sandbox/attestation.py``): 0 none, 1 workspace jail + environment scrub,
2 isolated process with limits (Job Object), 3 = 2 + egress guard + escape suite passed (AppContainer), 4 container runner.
``code_execute`` needs 3; the shells (``bash``, ``powershell``) run only in the container runner and need 4.
"""
from dataclasses import dataclass
import re
from typing import Literal, Mapping

State = Literal['on', 'off', 'forced_off', 'blocked_attestation']
KINDS = ('tool', 'skill', 'connector', 'plugin', 'app')
RISKS = ('low', 'medium', 'high')
LOCKS = ('none', 'forced_off')
LOCI = ('server', 'client', 'none')
MAX_LEVEL = 4
SLUG = r'[a-z0-9][a-z0-9._-]{0,127}'
ID = re.compile(r'\A(%s):(%s)\Z' % ('|'.join(KINDS), SLUG))
SHA256 = re.compile(r'\A[0-9a-f]{64}\Z')
PERMISSION = re.compile(r'\A[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*)*\Z')


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    kind: str
    version: str
    risk: str
    is_base: bool
    default_state: str
    min_sandbox_level: int
    manifest_sha256: str | None
    credential_locus: str = 'server'
    declared_permissions: tuple = ()
    granted_permissions: tuple = ()

    def __post_init__(self):
        match = ID.match(self.id) if type(self.id) is str else None
        if (match is None or match.group(1) != self.kind or self.risk not in RISKS or type(self.is_base) is not bool
                or self.default_state not in ('on', 'off') or type(self.min_sandbox_level) is not int
                or not 0 <= self.min_sandbox_level <= MAX_LEVEL or self.credential_locus not in LOCI
                or type(self.version) is not str or not 1 <= len(self.version) <= 64
                or (self.manifest_sha256 is not None and not SHA256.match(self.manifest_sha256))
                or any(type(name) is not str or not PERMISSION.match(name)
                       for name in (*self.declared_permissions, *self.granted_permissions))):
            raise ValueError('Invalid capability catalog entry.')

    @property
    def slug(self):
        return self.id.split(':', 1)[1]


@dataclass(frozen=True)
class Layer:
    """A platform default or a company override for one capability: an optional state and a lock."""
    state: str | None = None
    lock: str = 'none'

    def __post_init__(self):
        if self.state not in (None, 'on', 'off') or self.lock not in LOCKS:
            raise ValueError('Invalid policy layer.')


@dataclass(frozen=True)
class Effective:
    id: str
    kind: str
    state: str
    min_sandbox_level: int
    version: str
    manifest_sha256: str | None
    credential_locus: str
    granted_permissions: tuple | None

    @property
    def enabled(self):
        return self.state == 'on'

    def view(self):
        """The flat shape the signed document carries: the bare slug as ``id`` (the client's own naming), plus the verdict."""
        item = {'id': self.id.split(':', 1)[1], 'kind': self.kind, 'state': self.state, 'enabled': self.enabled,
                'min_sandbox_level': self.min_sandbox_level, 'version': self.version, 'manifest_sha256': self.manifest_sha256,
                'credential_locus': self.credential_locus}
        if self.state in ('forced_off', 'blocked_attestation'):
            item['reason'] = self.state
        if self.granted_permissions is not None:
            item['granted_permissions'] = list(self.granted_permissions)
        return item


def effective_level(reported) -> int:
    """The client-reported attestation level; anything missing or malformed is level 0 (the gate fails closed)."""
    return reported if type(reported) is int and 0 <= reported <= MAX_LEVEL else 0


def _state(entry, platform, company, org, level):
    above, below = platform.get(entry.id, Layer()), company.get(entry.id, Layer())
    if above.lock == 'forced_off' or below.lock == 'forced_off':
        return 'forced_off'
    chosen = None
    if entry.id in org:
        chosen = 'on' if org[entry.id] is True else 'off'
    for source in (below.state, above.state, entry.default_state):
        if chosen is None and source is not None:
            chosen = source
    if chosen == 'on' and entry.min_sandbox_level > level:
        return 'blocked_attestation'
    return chosen


def resolve_one(entry: CatalogEntry | None, platform: Mapping, company: Mapping, org: Mapping, level: int, *, identifier=None):
    """One capability. ``entry`` None is an unknown id: ``off``, never an error and never an inference from a layer."""
    if entry is None:
        kind = identifier.split(':', 1)[0]
        return Effective(identifier, kind, 'off', 0, '0', None, 'none', None)
    granted = None
    if entry.kind == 'app':
        declared = set(entry.declared_permissions)
        granted = tuple(sorted(name for name in entry.granted_permissions if name in declared))
    return Effective(entry.id, entry.kind, _state(entry, platform, company, org, level), entry.min_sandbox_level, entry.version,
                     entry.manifest_sha256, entry.credential_locus, granted)


def resolve(entries, platform: Mapping, company: Mapping, org: Mapping, reported_level) -> tuple:
    level = effective_level(reported_level)
    return tuple(resolve_one(entry, platform, company, org, level) for entry in entries)
