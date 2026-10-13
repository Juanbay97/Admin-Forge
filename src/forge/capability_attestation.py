"""Client attestation reports: what the device measured about its own isolation, as a strict allow-list.

The client's sandbox runner reports ``{level, suite_version, client_version, os_build, cases:[{id, passed}], at}`` (no path, no
environment, no user content). The control plane treats it as advisory telemetry (client-asserted): it validates the shape here
and again in the database, appends it to an append-only log and lets the effective policy use the latest one. Any key outside the
allow-list rejects the whole report; nothing is stored partially.
"""
import re
from uuid import UUID

from forge.capability_model import CapabilityInvalid
from forge.capability_policy import MAX_LEVEL
from forge.invitations import capability_digest

MAX_CASES = 64
_KEYS = {'level', 'suite_version', 'client_version', 'os_build', 'cases', 'at'}
_SUITE = re.compile(r'[A-Za-z0-9._-]{1,32}')
_CLIENT = re.compile(r'[A-Za-z0-9._+-]{1,32}')
_OS = re.compile(r'[A-Za-z0-9._ -]{1,64}')
_CASE = re.compile(r'[a-z0-9][a-z0-9_.-]{0,63}')
_AT = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z')


def _text(value, pattern):
    if type(value) is not str or not pattern.fullmatch(value):
        raise CapabilityInvalid()
    return value


def _case(item):
    if type(item) is not dict or set(item) != {'id', 'passed'} or type(item['passed']) is not bool:
        raise CapabilityInvalid()
    return {'id': _text(item['id'], _CASE), 'passed': item['passed']}


def _report(item):
    if type(item) is not dict or set(item) != _KEYS:
        raise CapabilityInvalid()
    level, cases = item['level'], item['cases']
    if type(level) is not int or not 0 <= level <= MAX_LEVEL or type(cases) is not list or len(cases) > MAX_CASES:
        raise CapabilityInvalid()
    return {'level': level, 'suite_version': _text(item['suite_version'], _SUITE), 'client_version': _text(item['client_version'], _CLIENT),
            'os_build': _text(item['os_build'], _OS), 'cases': [_case(case) for case in cases], 'at': _text(item['at'], _AT)}


class AttestationReports:
    def __init__(self, store):
        self._store = store

    def record(self, token, org, report):
        """True when the report was stored, False when it was a replay (same device time) or the daily bound was reached."""
        if type(org) is not UUID:
            raise CapabilityInvalid()
        return self._store.attest(capability_digest(token), org, _report(report)) is True
