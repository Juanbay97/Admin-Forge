"""Idempotent schema migration runner for a deployment database: ``python -m forge.migrate``.

Raw reviewed SQL, applied in the canonical order (``MIGRATIONS`` then ``MVP_ADDITIONS``) by a
one-shot job that alone holds the database administrator credential; the runtime never does.

* One session advisory lock serializes runners; state is re-read after the lock is held.
* ``forge_ops.schema_migrations`` records ``(version, name, sha256, applied_at)``. It lives
  outside the ``forge`` schema on purpose: the catalog fingerprint covers every relation in
  ``forge``, so a bookkeeping table there would change every pinned checkpoint.
* The scripts own their ``BEGIN``/``COMMIT`` and ``SET LOCAL ROLE``, so the runner cannot wrap
  script and record in one transaction. Crash safety comes from the reviewed catalog
  fingerprints instead: before each script the schema must equal the checkpoint of the state
  before it; if it already equals the state after, the script committed and only the record
  is written. Anything else is ``SCHEMA_FINGERPRINT_MISMATCH``. Checkpoints exist from the
  sixth migration on; the first six are single-transaction scripts, so an interrupted fresh
  database fails loudly (a script re-run is refused by its own DDL) and is simply recreated.
* An existing ``forge`` schema without records is adopted only when its fingerprint is a known
  checkpoint; otherwise ``UNKNOWN_SCHEMA`` and nothing changes.
* Service-role LOGIN passwords come from secret files and are set on every run as SCRAM
  verifiers computed client-side, so neither the plaintext nor a log line ever carries it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg import errors, sql

from forge.account_readiness import catalog_fingerprint
from forge.dev_accounts import MIGRATIONS, ROOT
from forge.mvp_local import ConfigError, ROLES
from forge.mvp_profile import MVP_ADDITIONS, MVP_CHECKPOINTS
from forge.prod_config import load_prod_config, strip_libpq_environment

CANONICAL_ORDER = (*MIGRATIONS, *MVP_ADDITIONS)
BASE_COUNT = len(MIGRATIONS)  # checkpoints start after the base set: MVP_CHECKPOINTS[k] = state after BASE_COUNT + k
LOCK_KEY = 0x466F72676531  # "Forge1": one runner per database
LOCK_TIMEOUT = '120s'
_BOOKKEEPING = """
CREATE SCHEMA IF NOT EXISTS forge_ops;
CREATE TABLE IF NOT EXISTS forge_ops.schema_migrations(
 version integer PRIMARY KEY CHECK(version > 0),
 name text NOT NULL UNIQUE,
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 applied_at timestamptz NOT NULL DEFAULT clock_timestamp());
REVOKE ALL ON SCHEMA forge_ops FROM PUBLIC;
REVOKE ALL ON TABLE forge_ops.schema_migrations FROM PUBLIC;
"""


class MigrationError(Exception):
    """The message is always a finite code; ``migration`` names the file involved, never a value."""
    def __init__(self, code, migration=None):
        super().__init__(code)
        self.code, self.migration = code, migration


def file_hashes(directory, order):
    """sha256 of each file with LF line endings, so a Windows checkout and a Linux image agree."""
    hashes = {}
    for name in order:
        try:
            data = (Path(directory)/name).read_bytes()
        except OSError:
            raise MigrationError('MIGRATION_FILE_MISSING', name) from None
        hashes[name] = hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()
    return hashes


def verify_records(records, hashes, order):
    """Recorded rows must be an exact, unedited prefix of ``order``; returns how many are applied."""
    for position, (version, name, digest) in enumerate(records):
        if position >= len(order) or version != position + 1 or name != order[position]:
            raise MigrationError('MIGRATION_ORDER_MISMATCH', name)
        if digest != hashes[name]:
            raise MigrationError('MIGRATION_CHECKSUM_MISMATCH', name)
    return len(records)


def _read_records(connection):
    exists = connection.execute("SELECT to_regclass('forge_ops.schema_migrations') IS NOT NULL").fetchone()[0]
    if not exists:
        return []
    return connection.execute('SELECT version, name, sha256 FROM forge_ops.schema_migrations ORDER BY version').fetchall()


def _fingerprint(connection):
    with connection.cursor() as cursor:
        return catalog_fingerprint(cursor)


def _record(connection, entries):
    with connection.transaction():
        connection.execute(_BOOKKEEPING)
        for version, name, digest in entries:
            connection.execute('INSERT INTO forge_ops.schema_migrations(version, name, sha256) VALUES (%s, %s, %s)',
                               [version, name, digest])


def _adopt(connection, hashes, order, checkpoints):
    """A legacy database (installed by hand) joins the ledger only at a reviewed checkpoint."""
    known = checkpoints[:len(order) - BASE_COUNT + 1]
    actual = _fingerprint(connection)
    if actual not in known:
        raise MigrationError('UNKNOWN_SCHEMA')
    count = BASE_COUNT + known.index(actual)
    _record(connection, [(index + 1, order[index], hashes[order[index]]) for index in range(count)])
    return count


def _execute(connection, directory, name):
    try:
        connection.execute((Path(directory)/name).read_text('utf-8'))
    except psycopg.Error:
        try:
            connection.execute('ROLLBACK')  # a script that failed inside its own BEGIN leaves the session aborted
        except psycopg.Error:
            pass
        raise MigrationError('MIGRATION_FAILED', name) from None


def _converge(connection, directory, hashes, order, checkpoints):
    done = verify_records(_read_records(connection), hashes, order)
    if done == 0 and connection.execute("SELECT to_regnamespace('forge') IS NOT NULL").fetchone()[0]:
        done = _adopt(connection, hashes, order, checkpoints)
    applied = []
    for index in range(done, len(order)):
        name = order[index]
        if index >= BASE_COUNT:
            actual = _fingerprint(connection)
            before, after = checkpoints[index - BASE_COUNT], checkpoints[index - BASE_COUNT + 1]
            if actual == after:  # crash between the committed script and its record row
                _record(connection, [(index + 1, name, hashes[name])])
                continue
            if actual != before:
                raise MigrationError('SCHEMA_FINGERPRINT_MISMATCH', name)
        _execute(connection, directory, name)
        applied.append(name)
        if index + 1 >= BASE_COUNT and _fingerprint(connection) != checkpoints[index + 1 - BASE_COUNT]:
            raise MigrationError('SCHEMA_FINGERPRINT_MISMATCH', name)
        _record(connection, [(index + 1, name, hashes[name])])
    if len(order) >= BASE_COUNT and _fingerprint(connection) != checkpoints[len(order) - BASE_COUNT]:
        raise MigrationError('SCHEMA_FINGERPRINT_MISMATCH')  # also catches drift on a no-op rerun
    return applied


def _set_passwords(connection, passwords):
    if not passwords:
        return
    existing = {row[0] for row in connection.execute('SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)',
                                                      [list(passwords)])}
    if set(passwords) - existing:
        raise MigrationError('MIGRATION_ROLE_MISSING')
    for role, password in passwords.items():
        try:
            verifier = connection.pgconn.encrypt_password(password.encode('utf-8'), role.encode('ascii'),
                                                          b'scram-sha-256').decode('ascii')
            connection.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(verifier)))
        except psycopg.Error:
            raise MigrationError('ROLE_PASSWORD_FAILED') from None


def migrate(connection, directory, passwords, *, order=CANONICAL_ORDER, checkpoints=MVP_CHECKPOINTS):
    """Apply what is pending; returns the names of the scripts executed (a rerun returns ``[]``).

    ``connection`` must be an autocommit superuser connection. ``order`` and ``checkpoints`` are
    injectable only so tests can stop at an intermediate state.
    """
    if not connection.autocommit or set(passwords) - set(ROLES):
        raise ValueError('An autocommit connection and known service roles are required.')
    hashes = file_hashes(directory, order)
    connection.execute('SET statement_timeout = 0')  # the scripts bound themselves with SET LOCAL
    connection.execute(sql.SQL('SET lock_timeout = {}').format(sql.Literal(LOCK_TIMEOUT)))
    try:
        connection.execute('SELECT pg_advisory_lock(%s)', [LOCK_KEY])
    except errors.LockNotAvailable:
        raise MigrationError('MIGRATION_LOCK_TIMEOUT') from None
    try:
        applied = _converge(connection, directory, hashes, order, checkpoints)
        _set_passwords(connection, passwords)
        return applied
    finally:
        try:
            connection.execute('SELECT pg_advisory_unlock(%s)', [LOCK_KEY])
        except psycopg.Error:
            pass  # closing the session releases it anyway


def admin_settings(db):
    """Explicit libpq parameters for the one-shot administrator connection."""
    return dict(host=db.host, port=db.port, dbname=db.dbname, user=db.admin_user, password=db.admin_password,
                sslmode=db.sslmode, autocommit=True, connect_timeout=5, application_name='forge-migrate')


def run_migrations(config, directory, *, connect=psycopg.connect, run=migrate):
    if config.db.admin_password is None:
        raise ConfigError('CONFIG_INVALID:FORGE_DB_ADMIN_PASSWORD')
    try:
        connection = connect(**admin_settings(config.db))
    except psycopg.Error:
        raise MigrationError('DB_UNAVAILABLE') from None
    try:
        return run(connection, directory, config.roles)
    finally:
        connection.close()


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage()


def main(argv=None, *, environ=None, connect=psycopg.connect, run=migrate):
    emit = lambda document: print(json.dumps(document), flush=True)
    try:
        parser = _Parser(prog='forge.migrate', description='Apply the reviewed Forge schema migrations.')
        parser.add_argument('--migrations-dir', default=str(ROOT/'migrations'))
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except _Usage:
        emit({'status': 'failed', 'code': 'INVALID_ARGUMENTS'})
        return 2
    if environ is None:
        strip_libpq_environment(os.environ)
        environ = os.environ
    try:
        applied = run_migrations(load_prod_config(environ), arguments.migrations_dir, connect=connect, run=run)
    except MigrationError as error:
        emit({'status': 'failed', 'code': error.code, **({'migration': error.migration} if error.migration else {})})
        return 1
    except ConfigError as error:
        emit({'status': 'failed', 'code': str(error)})
        return 1
    except Exception:
        emit({'status': 'failed', 'code': 'MIGRATE_UNAVAILABLE'})
        return 1
    emit({'status': 'ok', 'applied': applied})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
