"""Per-member OAuth for remote connectors, held server-side: authorization code + PKCE (S256), a single-use state, sealed tokens and
single-flight refresh. The tokens never reach the member's device.

* ``start`` (member session, connector ``on`` by effective policy, a configured OAuth app) stores the hashed state and the *sealed* PKCE
  verifier and returns the authorize URL. The redirect URI is always ``<public origin>/forge/v1/connectors/oauth/callback`` from
  configuration, never from a request.
* ``complete`` (the callback, no session) consumes the state exactly once, exchanges the code through the egress guard, seals the token
  bundle bound to company, member, connector and revision, and stores it. Any bad, replayed or expired state is the same refusal.
* ``access_token`` returns a usable access token, refreshing when it is about to expire. Refresh is single-flight per grant (one lock
  per grant here, a revision compare-and-swap in the database); a refused refresh marks the grant ``reauth_required``.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from threading import Lock
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from forge.connector_cipher import Binding, ConnectorCipherError
from forge.connector_model import (BrokerConflict, BrokerDenied, BrokerDisabled, BrokerInvalid, BrokerNotConfigured, BrokerReauth,
                                   BrokerUpstream, ConnectorContext)
from forge.egress_guard import EgressDenied
from forge.invitations import capability_digest

CALLBACK_PATH = '/forge/v1/connectors/oauth/callback'
PLATFORM = UUID(int=0)  # the organization a platform-default credential is sealed for
STATE_BINDING_REVISION = 1
MAX_TOKEN_RESPONSE = 65536
STATE_TTL_SECONDS = 600
REFRESH_SKEW_SECONDS = 60


def _hash(state):
    return hashlib.sha256(state.encode('ascii')).hexdigest()


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')


def oauth_settings(attributes):
    """The connector's OAuth endpoints from its catalog attributes, or ``BrokerNotConfigured``."""
    config = attributes.get('oauth') if type(attributes) is dict else None
    if (type(config) is not dict or attributes.get('auth') != 'oauth' or attributes.get('transport') != 'mcp_http'
            or any(type(config.get(name)) is not str for name in ('authorize_url', 'token_url'))
            or type(config.get('scopes', [])) is not list or any(type(scope) is not str for scope in config.get('scopes', []))
            or config.get('token_auth', 'post') not in ('post', 'basic')):
        raise BrokerNotConfigured()
    return config


def credential_binding(context_scope, org, capability, revision):
    return Binding(PLATFORM if context_scope == 'platform' else org, 'org', '', capability, revision)


class ConnectorOAuth:
    def __init__(self, store, cipher, client, *, public_origin, clock=time.time, state_ttl=STATE_TTL_SECONDS):
        origin = urlsplit(public_origin or '')
        if origin.scheme not in ('http', 'https') or not origin.hostname or origin.path not in ('', '/') or origin.query or origin.fragment:
            raise ValueError('A public origin is required for the OAuth callback.')
        self._store, self._cipher, self._client, self._clock, self._ttl = store, cipher, client, clock, state_ttl
        self.redirect_uri = '%s://%s%s' % (origin.scheme, origin.netloc, CALLBACK_PATH)
        self._locks, self._guard = {}, Lock()

    # -- helpers -------------------------------------------------------------------------------------------------------------
    def _client_app(self, org, capability, kind, scope, sealed, revision):
        if kind != 'oauth_client' or sealed is None:
            raise BrokerNotConfigured()
        try:
            app = self._cipher.open(credential_binding(scope, org, capability, revision), sealed)
        except ConnectorCipherError:
            raise BrokerNotConfigured() from None
        if not app.get('client_id'):
            raise BrokerNotConfigured()
        return app

    def _token_request(self, config, attributes, app, form):
        fields = dict(form)
        headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}
        if config.get('token_auth', 'post') == 'basic' and app.get('client_secret'):
            headers['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % (app['client_id'], app['client_secret'])).encode()).decode()
            fields['client_id'] = app['client_id']
        else:
            fields['client_id'] = app['client_id']
            if app.get('client_secret'):
                fields['client_secret'] = app['client_secret']
        try:
            upstream = self._client.request('POST', config['token_url'], attributes.get('egress_hosts', []), headers=headers, content=urlencode(fields).encode())
            status, body = upstream.status, upstream.read(MAX_TOKEN_RESPONSE)
        except EgressDenied:
            raise BrokerUpstream() from None
        try:
            document = json.loads(body)
        except ValueError:
            document = None
        return status, document if type(document) is dict else {}

    def _bundle(self, document, previous_refresh=None):
        access, kind = document.get('access_token'), str(document.get('token_type', 'Bearer')).lower()
        refresh = document.get('refresh_token', previous_refresh)
        lifetime = document.get('expires_in', 3600)
        if (type(access) is not str or not access or len(access) > 4096 or kind != 'bearer' or type(lifetime) is not int or not 1 <= lifetime <= 31536000
                or (refresh is not None and (type(refresh) is not str or not refresh or len(refresh) > 4096))):
            raise BrokerUpstream()
        bundle = {'access_token': access}
        if refresh:
            bundle['refresh_token'] = refresh
        return bundle, datetime.fromtimestamp(self._clock() + lifetime, timezone.utc)

    # -- start ---------------------------------------------------------------------------------------------------------------
    def start(self, token, org, connector_id):
        digest = capability_digest(token)
        context = self._store.context(digest, org, connector_id)
        if context.state != 'on':
            raise BrokerDisabled()
        if context.credential_locus != 'server':
            raise BrokerNotConfigured()
        config = oauth_settings(context.attributes)
        app = self._client_app(org, connector_id, context.credential_kind, context.credential_scope, context.credential_sealed, context.credential_revision)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        sealed = self._cipher.seal(Binding(org, 'user', str(context.membership_id), connector_id, STATE_BINDING_REVISION), {'verifier': verifier})
        self._store.oauth_start(digest, org, connector_id, _hash(state), sealed, self._ttl)
        query = {'response_type': 'code', 'client_id': app['client_id'], 'redirect_uri': self.redirect_uri, 'state': state,
                 'code_challenge': _challenge(verifier), 'code_challenge_method': 'S256'}
        if config.get('scopes'):
            query['scope'] = ' '.join(config['scopes'])
        return config['authorize_url'] + ('&' if '?' in config['authorize_url'] else '?') + urlencode(query)

    # -- callback ------------------------------------------------------------------------------------------------------------
    def complete(self, state, code):
        """The connector id of the grant that was stored. Every refusal is a typed error without detail."""
        if type(state) is not str or not 20 <= len(state) <= 128 or not state.isascii() or type(code) is not str or not 1 <= len(code) <= 2048:
            raise BrokerDenied()
        taken = self._store.oauth_take(_hash(state))  # consumes the state: a failed exchange burns it
        if taken.state != 'on':
            raise BrokerDisabled()
        config = oauth_settings(taken.attributes)
        app = self._client_app(taken.organization_id, taken.capability_id, taken.credential_kind, taken.credential_scope, taken.credential_sealed,
                               taken.credential_revision)
        try:
            verifier = self._cipher.open(Binding(taken.organization_id, 'user', str(taken.membership_id), taken.capability_id, STATE_BINDING_REVISION),
                                         taken.sealed_verifier)['verifier']
        except ConnectorCipherError:
            raise BrokerDenied() from None
        status, document = self._token_request(config, taken.attributes, app, {'grant_type': 'authorization_code', 'code': code,
                                                                                 'redirect_uri': self.redirect_uri, 'code_verifier': verifier})
        if status != 200:
            raise BrokerUpstream()
        bundle, expires = self._bundle(document)
        revision = taken.grant_revision + 1
        sealed = self._cipher.seal(Binding(taken.organization_id, 'user', str(taken.membership_id), taken.capability_id, revision), bundle)
        self._store.oauth_complete(_hash(state), taken.grant_revision, sealed, expires)
        return taken.capability_id

    def abort(self, state):
        """The provider reported an error (for example a refused consent): burn the state so the link cannot be reused."""
        if type(state) is str and 20 <= len(state) <= 128 and state.isascii():
            try:
                self._store.oauth_take(_hash(state))
            except BrokerDenied:
                pass

    # -- access token --------------------------------------------------------------------------------------------------------
    def _lock_for(self, key):
        with self._guard:
            return self._locks.setdefault(key, Lock())

    def _fresh(self, context):
        return context.access_expires_at is None or context.access_expires_at.timestamp() - REFRESH_SKEW_SECONDS > self._clock()

    def _open_grant(self, org, connector_id, context):
        try:
            return self._cipher.open(Binding(org, 'user', str(context.membership_id), connector_id, context.grant_revision), context.grant_sealed)
        except ConnectorCipherError:
            raise BrokerReauth() from None

    def access_token(self, token, org, connector_id, context: ConnectorContext) -> str:
        """The member's access token for this connector, refreshed single-flight when it is about to expire."""
        if context.grant_status != 'connected' or context.grant_sealed is None:
            raise BrokerReauth()
        bundle = self._open_grant(org, connector_id, context)
        if self._fresh(context):
            return bundle['access_token']
        digest = capability_digest(token)
        with self._lock_for((org, context.membership_id, connector_id)):
            current = self._store.context(digest, org, connector_id)  # another caller may have refreshed while we waited
            if current.state != 'on':
                raise BrokerDisabled()
            if current.grant_status != 'connected' or current.grant_sealed is None:
                raise BrokerReauth()
            bundle = self._open_grant(org, connector_id, current)
            if self._fresh(current):
                return bundle['access_token']
            return self._refresh(digest, org, connector_id, current, bundle)

    def _refresh(self, digest, org, connector_id, context, bundle):
        refresh = bundle.get('refresh_token')
        if not refresh:
            self._flag(digest, org, connector_id, context)
            raise BrokerReauth()
        config = oauth_settings(context.attributes)
        app = self._client_app(org, connector_id, context.credential_kind, context.credential_scope, context.credential_sealed, context.credential_revision)
        status, document = self._token_request(config, context.attributes, app, {'grant_type': 'refresh_token', 'refresh_token': refresh})
        if status in (400, 401) and document.get('error') in ('invalid_grant', 'invalid_token', 'unauthorized_client'):
            self._flag(digest, org, connector_id, context)
            raise BrokerReauth()
        if status != 200:
            raise BrokerUpstream()
        fresh, expires = self._bundle(document, previous_refresh=refresh)
        revision = context.grant_revision + 1
        sealed = self._cipher.seal(Binding(org, 'user', str(context.membership_id), connector_id, revision), fresh)
        try:
            self._store.grant_update(digest, org, connector_id, context.grant_revision, sealed, expires, 'connected')
        except BrokerConflict:
            # Another process won the compare-and-swap: its token is the one in the database now.
            winner = self._store.context(digest, org, connector_id)
            if winner.grant_status != 'connected' or winner.grant_sealed is None:
                raise BrokerReauth() from None
            return self._open_grant(org, connector_id, winner)['access_token']
        return fresh['access_token']

    def _flag(self, digest, org, connector_id, context):
        try:
            self._store.grant_update(digest, org, connector_id, context.grant_revision, None, None, 'reauth_required')
        except BrokerConflict:
            pass

    # -- disconnect ----------------------------------------------------------------------------------------------------------
    def disconnect(self, token, org, connector_id):
        """Destroy the member's grant and, when the connector declares a revocation endpoint, revoke the refresh token upstream (best effort)."""
        digest = capability_digest(token)
        removed = self._store.grant_delete(digest, org, connector_id)
        if removed is None:
            return False
        try:
            context = self._store.context(digest, org, connector_id)
            config = oauth_settings(context.attributes)
            url = config.get('revocation_url')
            if url:
                bundle = self._cipher.open(Binding(org, 'user', str(context.membership_id), connector_id, removed.revision), removed.sealed)
                app = self._client_app(org, connector_id, context.credential_kind, context.credential_scope, context.credential_sealed, context.credential_revision)
                self._token_request({**config, 'token_url': url}, context.attributes, app, {'token': bundle.get('refresh_token') or bundle['access_token']})
        except Exception:
            pass  # the grant is already destroyed; an upstream that cannot be reached must not undo that
        return True
