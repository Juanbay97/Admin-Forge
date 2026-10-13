"""The loopback OAuth 2.0 provider fixture (authorization code + PKCE, rotating refresh tokens, revocation); the implementation lives in
``forge.fake_connectors`` so the deploy smoke can run the same fixture in a container."""
from forge.fake_connectors import PROVIDER_CLIENT_ID, PROVIDER_CLIENT_SECRET, FakeOAuthProvider

__all__ = ('FakeOAuthProvider', 'PROVIDER_CLIENT_ID', 'PROVIDER_CLIENT_SECRET')
