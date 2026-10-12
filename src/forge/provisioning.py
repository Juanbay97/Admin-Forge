"""Trusted platform-operator provisioning: organizations, first admin, department, two-org seed.

Never reachable over HTTP. The operator connects through an explicit private file (numeric
loopback only, no environment discovery). Passwords and gateway keys are generated here,
handed once to a private credentials file inside the same transaction that creates the rows,
and never printed or logged. A rerun creates nothing and resets nothing.
"""
import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import secrets
import sys
from uuid import UUID, uuid4

from forge.accounts import ACCOUNT_ISSUER, PasswordHasher, canonical_email, display_name

SLUG = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')
OPERATOR_KEYS = {'host', 'port', 'dbname', 'user', 'password'}


@dataclass(frozen=True)
class OrganizationSpec:
    slug: str
    display_name: str
    department: str
    admin_email: str
    admin_name: str
    member_email: str | None = None
    member_name: str | None = None
    issue_gateway_key: bool = False
    # Accounts that are members of this organization and, through the same email, of others: only the first
    # organization creates the account (and its one credential); the others reuse it.
    shared_members: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if type(self.slug) is not str or not SLUG.fullmatch(self.slug):
            raise ValueError('Invalid slug.')
        for name in ('display_name', 'department', 'admin_name'):
            object.__setattr__(self, name, display_name(getattr(self, name)))
        object.__setattr__(self, 'admin_email', canonical_email(self.admin_email))
        if (self.member_email is None) != (self.member_name is None):
            raise ValueError('A member needs both an email and a name.')
        if self.member_email is not None:
            object.__setattr__(self, 'member_email', canonical_email(self.member_email))
            object.__setattr__(self, 'member_name', display_name(self.member_name))
            if self.member_email == self.admin_email:
                raise ValueError('The member must differ from the administrator.')
        shared = tuple((canonical_email(email), display_name(name)) for email, name in self.shared_members)
        taken = [email for email in (self.admin_email, self.member_email, *(email for email, _ in shared)) if email]
        if len(set(taken)) != len(taken):
            raise ValueError('Every member of an organization must be a different account.')
        object.__setattr__(self, 'shared_members', shared)


@dataclass(frozen=True)
class NewAccount:
    """A credential issued by this run; accounts that already existed never appear."""
    email: str
    name: str
    role: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class Provisioned:
    organization_id: UUID
    department_id: UUID
    slug: str
    accounts: tuple[NewAccount, ...]
    gateway_key: str | None = field(default=None, repr=False)


SEED = tuple(
    OrganizationSpec(slug='org-' + letter.lower(), display_name='Organization ' + letter, department=department,
                     admin_email='admin-%s@forge.local.test' % letter.lower(), admin_name='Admin ' + letter,
                     member_email='member-%s@forge.local.test' % letter.lower(), member_name='Member ' + letter,
                     issue_gateway_key=True)
    for letter, department in (('A', 'Operations'), ('B', 'Finance')))


# The same two organizations plus one account that belongs to both, for the multi-user local stack.
MULTIUSER_SEED = tuple(
    OrganizationSpec(**{**vars(spec), 'shared_members': (('shared@forge.local.test', 'Shared Member'),)})
    for spec in SEED)


def new_password():
    return secrets.token_urlsafe(24)


def _account(connection, spec_email, name, hasher):
    """Existing accounts are reused untouched; only a new account gets a password."""
    row = connection.execute('SELECT id FROM forge.owned_accounts WHERE canonical_email=%s', (spec_email,)).fetchone()
    if row is not None:
        return row[0], None
    identity, password = uuid4(), new_password()
    connection.execute("INSERT INTO forge.identities(id,provider,issuer,subject) VALUES(%s,'forge',%s,%s)",
                       (identity, ACCOUNT_ISSUER, str(identity)))
    connection.execute('INSERT INTO forge.owned_accounts(id,canonical_email,display_name,password_hash) '
                       'VALUES(%s,%s,%s,%s)', (identity, spec_email, name, hasher.hash(password)))
    return identity, password


def _member(connection, organization, department, email, name, role, hasher):
    identity, password = _account(connection, email, name, hasher)
    membership = uuid4()
    connection.execute("INSERT INTO forge.memberships(organization_id,id,identity_id,status) VALUES(%s,%s,%s,'active')",
                       (organization, membership, identity))
    connection.execute('INSERT INTO forge.membership_roles VALUES(%s,%s,%s)', (organization, membership, role))
    connection.execute('INSERT INTO forge.membership_departments VALUES(%s,%s,%s)', (organization, membership, department))
    return () if password is None else (NewAccount(email, name, role, password),)


def provision(connection, specs, deliver, *, hasher=None):
    """Create the missing organizations in ONE transaction; return only what this run created.

    ``deliver(results)`` runs before the commit, so credentials that cannot be stored
    safely abort every row instead of being lost.
    """
    hasher = PasswordHasher() if hasher is None else hasher
    created = []
    with connection.transaction():
        for spec in specs:
            organization, department = uuid4(), uuid4()
            inserted = connection.execute(
                'INSERT INTO forge.organizations VALUES(%s,%s,%s,true,1) ON CONFLICT (slug) DO NOTHING RETURNING id',
                (organization, spec.slug, spec.display_name)).fetchone()
            if inserted is None:
                continue
            connection.execute('INSERT INTO forge.configuration_revisions VALUES(%s,1)', (organization,))
            connection.execute('INSERT INTO forge.departments(organization_id,id,name) VALUES(%s,%s,%s)',
                               (organization, department, spec.department))
            accounts = _member(connection, organization, department, spec.admin_email, spec.admin_name,
                               'organization_admin', hasher)
            if spec.member_email is not None:
                accounts += _member(connection, organization, department, spec.member_email, spec.member_name,
                                    'member', hasher)
            for email, name in spec.shared_members:
                accounts += _member(connection, organization, department, email, name, 'member', hasher)
            key = 'fake-%s-%s' % (spec.slug, secrets.token_urlsafe(24)) if spec.issue_gateway_key else None
            created.append(Provisioned(organization, department, spec.slug, accounts, key))
        if created:
            deliver(tuple(created))
    return tuple(created)


def write_credentials(path, results):
    """Exclusive create: an existing file is never overwritten, so earlier secrets survive."""
    document = {'organizations': [{
        'slug': result.slug, 'organization_id': str(result.organization_id), 'gateway_key': result.gateway_key,
        'accounts': [{'email': a.email, 'role': a.role, 'password': a.password} for a in result.accounts],
    } for result in results]}
    with Path(path).open('x', encoding='utf-8') as output:
        json.dump(document, output, indent=2)
        output.write('\n')


class Refusal(Exception):
    """Carries only a finite, non-secret code."""


def _operator(path):
    try:
        values = json.loads(Path(path).read_text('utf-8'))
    except (OSError, ValueError):
        raise Refusal('OPERATOR_FILE_INVALID') from None
    if (type(values) is not dict or set(values) != OPERATOR_KEYS or values['host'] != '127.0.0.1'
            or type(values['port']) is not int or not 1 <= values['port'] <= 65535
            or any(type(values[key]) is not str or not values[key] for key in ('dbname', 'user', 'password'))):
        raise Refusal('OPERATOR_FILE_INVALID')
    return values


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refusal('INVALID_ARGUMENTS')


def _arguments(argv):
    parser = _Parser(prog='forge.provision', description='Trusted Forge provisioning; never production.')
    parser.add_argument('--operator-file', required=True)
    parser.add_argument('--credentials-file', required=True)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=_Parser)
    organization = commands.add_parser('org')
    for name in ('slug', 'name', 'department', 'admin-email', 'admin-name'):
        organization.add_argument('--' + name, required=True)
    commands.add_parser('seed')
    return parser.parse_args(argv)


def main(argv=None, *, out=None, environ=None, connect=None, provision_fn=provision):
    out = sys.stdout if out is None else out
    emit = lambda document: print(json.dumps(document), file=out, flush=True)
    try:
        if any(name.startswith('PG') for name in (os.environ if environ is None else environ)):
            raise Refusal('ISOLATED_CHILD_ENVIRONMENT_REQUIRED')
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        operator = _operator(arguments.operator_file)
        try:
            specs = SEED if arguments.command == 'seed' else (OrganizationSpec(
                slug=arguments.slug, display_name=arguments.name, department=arguments.department,
                admin_email=arguments.admin_email, admin_name=arguments.admin_name),)
        except ValueError:
            raise Refusal('INVALID_ORGANIZATION') from None
        if connect is None:
            import psycopg
            connect = psycopg.connect
        try:
            with connect(**operator, autocommit=True, connect_timeout=5) as connection:
                created = provision_fn(connection, specs,
                                       lambda results: write_credentials(arguments.credentials_file, results))
        except FileExistsError:
            raise Refusal('CREDENTIALS_FILE_EXISTS') from None
        except Exception:
            raise Refusal('PROVISIONING_FAILED') from None
        made = {result.slug for result in created}
        emit({'status': 'provisioned', 'credentials_file': arguments.credentials_file if made else None,
              'organizations': [{'slug': spec.slug, 'created': spec.slug in made} for spec in specs]})
        return 0
    except Refusal as refusal:
        emit({'status': 'failed', 'code': str(refusal)})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
