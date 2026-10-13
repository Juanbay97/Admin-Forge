"""The capability catalog seed and its operator CLI: ``python -m forge.capability_seed sync [--update]``.

The seed is the OpenYak inventory (25 skills, 46 connectors, 15 plugins, the built-in tools and the governed capability groups) as
compact JSONL, one entry per line, sorted by id. ``sync`` runs with the database administrator credential (like
``forge.migrate`` and ``forge.platform``), never over HTTP, in ONE transaction:

* it CREATES entries that are missing (audited with a NULL actor: the trusted operator) and bumps the platform epoch once;
* it NEVER modifies an existing entry unless ``--update`` is given, so what a platform owner changed through the API survives a re-sync;
* a second run changes nothing: no revision, no epoch, no audit row.
"""
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from forge.capability_service import entry_document
from forge.migrate import admin_settings
from forge.mvp_local import ConfigError, _fail
from forge.prod_config import _db

SEED_PATH = Path(__file__).with_name('capability_seed.jsonl')
_LOCK = 0x466F726765434150  # "ForgeCAP": serializes concurrent syncs


@dataclass(frozen=True)
class SyncResult:
    created: int
    updated: int
    unchanged: int


def load_seed(path=None):
    """The validated entries (each as the catalog API would accept it, plus ``id``); any bad line refuses the whole file."""
    entries, seen = [], set()
    for number, line in enumerate(Path(path or SEED_PATH).read_text('utf-8').splitlines(), 1):
        try:
            raw = json.loads(line)
            identifier = raw.pop('id')
            document = entry_document(identifier, raw)
        except Exception:
            raise ValueError('Invalid capability seed line %d.' % number) from None
        if identifier in seen:
            raise ValueError('Invalid capability seed line %d.' % number)
        seen.add(identifier)
        entries.append({'id': identifier, **document})
    if not entries or [entry['id'] for entry in entries] != sorted(seen):
        raise ValueError('The capability seed must be non-empty and sorted by id.')
    return entries


_COLUMNS = ('version', 'risk', 'is_base', 'default_state', 'min_sandbox_level', 'manifest_sha256', 'credential_locus',
            'declared_permissions', 'granted_permissions', 'attributes')


def sync(connection, entries, *, update=False) -> SyncResult:
    """``connection`` must be an autocommit administrator connection. One transaction; a failure changes nothing."""
    created = updated = unchanged = 0
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (_LOCK,))
        for entry in entries:
            values = tuple(json.dumps(entry[name]) if name == 'attributes' else entry[name] for name in _COLUMNS)
            row = connection.execute('SELECT revision,version,risk,is_base,default_state,min_sandbox_level,manifest_sha256,credential_locus,'
                                     'declared_permissions,granted_permissions,attributes FROM forge.capability_catalog WHERE id=%s FOR UPDATE',
                                     (entry['id'],)).fetchone()
            if row is None:
                connection.execute('INSERT INTO forge.capability_catalog(id,kind,version,risk,is_base,default_state,min_sandbox_level,manifest_sha256,'
                                   'credential_locus,declared_permissions,granted_permissions,attributes) VALUES(%s,split_part(%s,%s,1),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                                   (entry['id'], entry['id'], ':', *values))
                connection.execute("INSERT INTO forge.capability_change_audit(scope,actor_id,action,target,after_state) VALUES('platform',NULL,'catalog.created',%s,'r1')",
                                   (entry['id'],))
                created += 1
            elif update and (*row[1:10], row[10]) != (*values[:9], entry['attributes']):
                connection.execute('UPDATE forge.capability_catalog SET version=%s,risk=%s,is_base=%s,default_state=%s,min_sandbox_level=%s,manifest_sha256=%s,'
                                   'credential_locus=%s,declared_permissions=%s,granted_permissions=%s,attributes=%s::jsonb,revision=revision+1,updated_at=clock_timestamp() WHERE id=%s',
                                   (*values, entry['id']))
                connection.execute("INSERT INTO forge.capability_change_audit(scope,actor_id,action,target,before_state,after_state) VALUES('platform',NULL,'catalog.updated',%s,%s,%s)",
                                   (entry['id'], 'r%d' % row[0], 'r%d' % (row[0] + 1)))
                updated += 1
            else:
                unchanged += 1
        if created or updated:
            connection.execute('UPDATE forge.capability_platform_epoch SET epoch=epoch+1 WHERE singleton')
    return SyncResult(created, updated, unchanged)


class _Refusal(Exception):
    def __init__(self, code, usage=False):
        super().__init__(code)
        self.code, self.usage = code, usage


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Refusal('INVALID_ARGUMENTS', usage=True)


def main(argv=None, *, environ=None, out=None, connect=None):
    out = sys.stdout if out is None else out
    emit = lambda document: print(json.dumps(document), file=out, flush=True)
    try:
        environ = dict(os.environ if environ is None else environ)
        if any(name.startswith('PG') for name in environ):
            raise _Refusal('ISOLATED_CHILD_ENVIRONMENT_REQUIRED')  # libpq would consult them even for explicit parameters
        parser = _Parser(prog='forge.capability_seed', description='Forge capability catalog seed; never reachable over HTTP.')
        commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
        commands.add_parser('sync').add_argument('--update', action='store_true')
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
        try:
            entries = load_seed()
        except (OSError, ValueError):
            raise _Refusal('SEED_INVALID') from None
        db = _db(environ)
        if db.admin_password is None:
            _fail('FORGE_DB_ADMIN_PASSWORD')
        if connect is None:
            import psycopg
            connect = psycopg.connect
        try:
            with connect(**{**admin_settings(db), 'application_name': 'forge-capability-seed'}, autocommit=True) as connection:
                result = sync(connection, entries, update=arguments.update)
        except Exception:
            raise _Refusal('SYNC_FAILED') from None
        emit({'status': 'synced', 'created': result.created, 'updated': result.updated, 'unchanged': result.unchanged})
        return 0
    except _Refusal as refusal:
        emit({'status': 'failed', 'code': refusal.code})
        return 2 if refusal.usage else 1
    except ConfigError as error:
        emit({'status': 'failed', 'code': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
