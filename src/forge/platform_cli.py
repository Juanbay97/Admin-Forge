"""Operator CLI for the platform owner: ``python -m forge.platform bootstrap-owner``.

Never reachable over HTTP and never prints or stores a password. It connects with the database administrator
credential (like ``forge.migrate``, from ``FORGE_DB_*`` and ``FORGE_DB_ADMIN_PASSWORD[_FILE]``) and, in ONE transaction,
creates the owner: an owned account with an unusable random password, a ``platform_owner`` role and NO membership, plus a
single-use set-password link (the account reset mechanism, stored as a digest only). The link goes to a private file
(exclusive create, mode 0600) before the transaction commits, so a link that cannot be stored aborts every row; it may
also be mailed (``--mailbox-dir`` for the local test mailbox, ``--smtp`` for the configured relay). A rerun, with any
address, creates nothing and writes nothing. The same entry point runs in the compose ``tools`` profile.
"""
import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlencode
from uuid import uuid4

from forge.accounts import ACCOUNT_ISSUER, PasswordHasher, canonical_email, display_name
from forge.gateway_origins import canonical_origin
from forge.invitation_delivery import LocalTestMailbox, trusted_origin
from forge.invitations import capability_digest
from forge.migrate import admin_settings
from forge.mvp_local import ConfigError, _fail
from forge.prod_config import _db
from forge.smtp_delivery import SmtpDelivery, load_smtp_settings

DEFAULT_TTL_HOURS = 24
MAX_TTL_HOURS = 168
MAILBOX_SENDER = 'forge@local.test'


class BootstrapRefused(Exception):
    """A finite refusal code; never a value from the database or the request."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BootstrapOutcome:
    created: bool
    link: str | None = field(default=None, repr=False)


def issue_link(origin, capability):
    """The capability stays in the fragment, so it never reaches a server log or a Referer header."""
    return trusted_origin(origin) + '/reset-password#' + urlencode({'capability': capability})


def write_private_file(path, text):
    """Exclusive create with mode 0600: an existing file is never overwritten (Windows ignores the mode bits)."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as output:
            output.write(text)
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise


def bootstrap_owner(connection, *, email, name, origin, ttl_seconds, write_link, hasher=None):
    """Create the owner and its one-time link, or do nothing when an owner already exists.

    ``connection`` must be an autocommit administrator connection (it creates rows the runtime roles cannot).
    ``write_link(link)`` runs before the commit; if it raises, nothing is created.
    """
    hasher = PasswordHasher() if hasher is None else hasher
    with connection.transaction():
        # Serialize concurrent bootstraps: the second one sees the first one's owner.
        connection.execute('SELECT pg_advisory_xact_lock(%s)', (0x466F726765504C54,))
        if connection.execute("SELECT 1 FROM forge.platform_roles WHERE role='platform_owner'").fetchone() is not None:
            return BootstrapOutcome(False)
        if connection.execute('SELECT 1 FROM forge.owned_accounts WHERE canonical_email=%s', (email,)).fetchone() is not None:
            raise BootstrapRefused('OWNER_ACCOUNT_EXISTS')
        account, capability = uuid4(), secrets.token_urlsafe(32)
        connection.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'forge',%s,%s)",
                           (account, ACCOUNT_ISSUER, str(account)))
        # A password nobody knows: the random value is hashed and dropped; only the reset link can set a real one.
        connection.execute('INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) VALUES(%s,%s,%s,%s)',
                           (account, email, name, hasher.hash(secrets.token_urlsafe(32))))
        connection.execute("INSERT INTO forge.platform_roles(account_id,role) VALUES(%s,'platform_owner')", (account,))
        connection.execute('INSERT INTO forge.account_password_resets(capability_hash,account_id,credential_revision,expires_at) '
                           "VALUES(%s,%s,1,clock_timestamp()+make_interval(secs=>%s))",
                           (capability_digest(capability), account, ttl_seconds))
        link = issue_link(origin, capability)
        write_link(link)
    return BootstrapOutcome(True, link)


def build_delivery(arguments, environ):
    """The optional mail channel: the local test mailbox, the configured SMTP relay, or none."""
    if arguments.mailbox_dir is not None:
        return LocalTestMailbox(Path(arguments.mailbox_dir), sender=MAILBOX_SENDER)
    if arguments.smtp:
        return SmtpDelivery(load_smtp_settings(environ))
    return None


class _Refusal(Exception):
    def __init__(self, code, usage=False):
        super().__init__(code)
        self.code, self.usage = code, usage


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Refusal('INVALID_ARGUMENTS', usage=True)  # a malformed command line exits 2, a refused value exits 1


def _arguments(argv):
    parser = _Parser(prog='forge.platform', description='Forge platform operator tool; never reachable over HTTP.')
    commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
    owner = commands.add_parser('bootstrap-owner')
    owner.add_argument('--email', required=True)
    owner.add_argument('--name', required=True)
    owner.add_argument('--link-file', required=True)
    owner.add_argument('--ttl-hours', type=int, default=DEFAULT_TTL_HOURS)
    delivery = owner.add_mutually_exclusive_group()
    delivery.add_argument('--mailbox-dir')
    delivery.add_argument('--smtp', action='store_true')
    return parser.parse_args(argv)


def main(argv=None, *, environ=None, out=None, connect=None, bootstrap_fn=bootstrap_owner, delivery_factory=build_delivery):
    out = sys.stdout if out is None else out
    emit = lambda document: print(json.dumps(document), file=out, flush=True)
    try:
        environ = dict(os.environ if environ is None else environ)
        if any(name.startswith('PG') for name in environ):
            raise _Refusal('ISOLATED_CHILD_ENVIRONMENT_REQUIRED')  # libpq would consult them even for explicit parameters
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        if not 1 <= arguments.ttl_hours <= MAX_TTL_HOURS:
            raise _Refusal('INVALID_ARGUMENTS')
        try:
            email, name = canonical_email(arguments.email), display_name(arguments.name)
        except ValueError:
            raise _Refusal('INVALID_OWNER') from None
        try:
            origin = canonical_origin(environ.get('FORGE_PUBLIC_ORIGIN'))
        except ValueError:
            _fail('FORGE_PUBLIC_ORIGIN')
        db = _db(environ)
        if db.admin_password is None:
            _fail('FORGE_DB_ADMIN_PASSWORD')
        adapter = delivery_factory(arguments, environ)
        if connect is None:
            import psycopg
            connect = psycopg.connect
        try:
            with connect(**{**admin_settings(db), 'application_name': 'forge-platform'}) as connection:
                outcome = bootstrap_fn(connection, email=email, name=name, origin=origin,
                                       ttl_seconds=arguments.ttl_hours * 3600,
                                       write_link=lambda link: write_private_file(arguments.link_file, link + '\n'))
        except FileExistsError:
            raise _Refusal('LINK_FILE_EXISTS') from None
        except BootstrapRefused as refused:
            raise _Refusal(refused.code) from None
        except (ConfigError, _Refusal):
            raise
        except Exception:
            raise _Refusal('BOOTSTRAP_FAILED') from None
        if not outcome.created:
            emit({'status': 'exists'})
            return 0
        state = None
        if adapter is not None:
            try:
                adapter.deliver(uuid4(), email, name, outcome.link, purpose='password_reset')
                state = 'delivered'
            except Exception:
                state = 'failed'  # the link file still holds it; nothing from the exchange is reported
        emit({'status': 'created', 'link_file': arguments.link_file, 'delivery': state})
        return 0
    except _Refusal as refusal:
        emit({'status': 'failed', 'code': refusal.code})
        return 2 if refusal.usage else 1
    except ConfigError as error:
        emit({'status': 'failed', 'code': str(error)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
