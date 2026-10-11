"""Versioned control-plane contract, generated from the live app routes.

The committed ``contract/forge-mvp.contract.json`` is the reviewed pin. The hash is
taken over canonical JSON, never over file bytes, so line endings cannot change it.
The client commits a copy and fails closed when the served hash differs.
``python -m forge.contract --write`` regenerates the file after an intended change.
"""
import hashlib
import json
from pathlib import Path
import sys

CONTRACT_VERSION = 'forge-mvp/1'
COMMITTED_PATH = Path(__file__).resolve().parents[2]/'contract'/'forge-mvp.contract.json'
PREFIX = '/forge/v1/'
# Every code account_api can raise; test_contract compares this list with the source.
ERROR_CODES = ('AUTHENTICATION_TEMPORARILY_BLOCKED', 'DEPARTMENT_EXISTS', 'EXISTING_ACCOUNT_AUTH_REQUIRED',
               'INVALID_REQUEST', 'LAST_ADMIN', 'MEMBERSHIP_SUSPENDED', 'NOT_FOUND', 'REVISION_CONFLICT',
               'SERVICE_UNAVAILABLE', 'UNAUTHENTICATED')


def _deref(schema, components):
    while '$ref' in schema:
        schema = components[schema['$ref'].rsplit('/', 1)[1]]
    return schema


def _paths(schema, components, prefix=''):
    """Dotted key paths of the leaves; ``[]`` marks arrays and ``{}`` free-form maps."""
    schema = _deref(schema, components)
    found = set()
    for variant in (*schema.get('anyOf', ()), *schema.get('oneOf', ()), *schema.get('allOf', ())):
        found |= _paths(variant, components, prefix)
    if schema.get('type') == 'array':
        found |= _paths(schema['items'], components, prefix + '[]')
    if type(schema.get('additionalProperties')) is dict:
        found |= _paths(schema['additionalProperties'], components, prefix + '{}') or {prefix + '{}'}
    for name, child in schema.get('properties', {}).items():
        path = prefix + '.' + name if prefix else name
        found |= _paths(child, components, path) or {path}
    return found


def _body(content, components):
    keys = sorted(_paths(content.get('application/json', {}).get('schema', {}), components))
    # FastAPI always adds an empty JSON entry next to a declared stream; keys win, else media types.
    return keys or sorted(media for media in content if media != 'application/json')


def build(app):
    """The contract document for ``app``: routes under /forge/v1 with request/response key sets."""
    document = app.openapi()
    components = document.get('components', {}).get('schemas', {})
    routes = []
    for path, item in document['paths'].items():
        if not path.startswith(PREFIX):
            continue
        for method, operation in item.items():
            responses = operation.get('responses', {})
            routes.append({
                'method': method.upper(), 'path': path,
                'auth': 'bearer' if operation.get('security') else 'none',
                'request': _body(operation.get('requestBody', {}).get('content', {}), components),
                'responses': {status: _body(response.get('content', {}), components)
                              for status, response in responses.items() if status.startswith('2')},
                'errors': sorted(int(status) for status in responses if status[0] in '45'),
            })
    return {'contract_version': CONTRACT_VERSION, 'error_codes': sorted(ERROR_CODES),
            'error_envelope': sorted(_paths({'$ref': '#/components/schemas/ErrorEnvelope'}, components)),
            'routes': sorted(routes, key=lambda route: (route['path'], route['method']))}


def canonical_sha256(document):
    text = json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def render(document):
    """One route per line: reviewable diffs without a thousand-line file."""
    dump = lambda value: json.dumps(value, sort_keys=True, separators=(', ', ': '))
    lines = ['{'] + ['  %s: %s,' % (json.dumps(key), dump(document[key])) for key in sorted(document) if key != 'routes']
    lines += ['  "routes": [', ',\n'.join('    ' + dump(route) for route in document['routes']), '  ]', '}']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    from forge.account_api import create_account_app
    argv = sys.argv[1:] if argv is None else argv
    document = build(create_account_app())
    if argv == ['--write']:
        COMMITTED_PATH.parent.mkdir(exist_ok=True)
        COMMITTED_PATH.write_text(render(document), 'utf-8', newline='\n')
        return 0
    if argv == ['--check']:
        return 0 if json.loads(COMMITTED_PATH.read_text('utf-8')) == document else 1
    print('usage: python -m forge.contract (--write | --check)', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
