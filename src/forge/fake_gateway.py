"""Fake OpenAI-compatible gateway for tests and local demos; never a real provider.

It proves the wire contract the strict adapters accept (models list and streamed
chat) and records Authorization headers so tests can prove key custody. It binds
to numeric loopback only, never echoes a bearer value, and proves nothing about
the real OmniRoute gateway's strictness.
"""
import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
from ipaddress import ip_address
import json
from pathlib import Path
import re
import sys
from threading import Event, Thread

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

MODELS = ('fake-fast', 'fake-slow', 'fake-error', 'fake-malformed', 'fake-nousage')
NO_USAGE_MODEL = 'fake-nousage'  # a gateway that ignores include_usage: the stream carries no usage chunk
REPLY = 'This is a fake gateway reply.'
DEFAULT_PORT = 3413
MAX_KEYS = 8
MAX_SLOW_DELAY = 5.0
MAX_MODEL_ID = 255
KEY_PATTERN = re.compile(r'[!-~]{1,4096}')


@dataclass(frozen=True, repr=False)
class FakeGatewayConfiguration:
    """Explicit trusted values; the accepted keys are never discovered."""
    keys: tuple[str, ...]
    host: str = '127.0.0.1'
    port: int = DEFAULT_PORT
    slow_delay_seconds: float = 0.5
    # Optional TLS (a throwaway certificate, see make_certificate): the deployment proof reaches the fake over https because the
    # production allow-list refuses plain http. ``any_interface`` (host 0.0.0.0) exists only for that container run and needs TLS.
    tls_cert: str | None = None
    tls_key: str | None = None
    any_interface: bool = False
    # Stream the extra fields OpenAI and OpenAI-compatible gateways send (usage null, obfuscation, fingerprint, nested usage details,
    # cost); the default stream stays the minimal contract.
    openai_realistic: bool = False

    def __post_init__(self):
        if type(self.openai_realistic) is not bool:
            raise ValueError('Invalid fake gateway mode.')
        if type(self.keys) is not tuple or not 1 <= len(self.keys) <= MAX_KEYS:
            raise ValueError('Invalid fake gateway keys.')
        if any(type(key) is not str or not KEY_PATTERN.fullmatch(key) for key in self.keys):
            raise ValueError('Invalid fake gateway keys.')
        if (self.tls_cert is None) != (self.tls_key is None) or type(self.any_interface) is not bool:
            raise ValueError('Invalid fake gateway TLS settings.')
        try:
            loopback = type(self.host) is str and ip_address(self.host).is_loopback
        except ValueError:
            loopback = False
        if self.any_interface:
            if self.host != '0.0.0.0' or self.tls_cert is None:
                raise ValueError('All interfaces are only for an explicit TLS container run.')
        elif not loopback:
            raise ValueError('The fake gateway binds to numeric loopback only.')
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError('Invalid fake gateway port.')
        if (type(self.slow_delay_seconds) not in (int, float)
                or not 0 <= self.slow_delay_seconds <= MAX_SLOW_DELAY):
            raise ValueError('Invalid fake gateway delay.')

    def __repr__(self):
        return 'FakeGatewayConfiguration(host=%r, port=%r)' % (self.host, self.port)


@dataclass(frozen=True, repr=False)
class GatewayRecord:
    method: str
    path: str
    model: str | None
    authorization: str | None

    def __repr__(self):
        return 'GatewayRecord(method=%r, path=%r)' % (self.method, self.path)

    def digest(self):
        return None if self.authorization is None else hashlib.sha256(self.authorization.encode()).hexdigest()


REALISTIC_EXTRAS = {'system_fingerprint': 'fp_fake0001', 'service_tier': 'default', 'obfuscation': 'fakeObf1'}


def _event(model: str, delta: dict, finish_reason=None, realistic=False) -> str:
    choice = {'index': 0, 'delta': delta, 'finish_reason': finish_reason}
    chunk = {'id': 'chatcmpl-fake', 'object': 'chat.completion.chunk', 'created': 0, 'model': model, 'choices': [choice]}
    if realistic:
        if delta.get('role') == 'assistant':
            delta = choice['delta'] = {**delta, 'refusal': None}
        choice['logprobs'] = None
        chunk.update(REALISTIC_EXTRAS, usage=None)
    return 'data: ' + json.dumps(chunk, separators=(',', ':')) + '\n\n'


def _usage_event(model: str, prompt_tokens: int, completion_tokens: int, realistic=False) -> str:
    usage = {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
             'total_tokens': prompt_tokens + completion_tokens}
    chunk = {'id': 'chatcmpl-fake', 'object': 'chat.completion.chunk', 'created': 0, 'model': model, 'choices': [],
             'usage': usage}
    if realistic:
        usage.update(prompt_tokens_details={'cached_tokens': 0, 'audio_tokens': 0},
                     completion_tokens_details={'reasoning_tokens': 0, 'audio_tokens': 0, 'accepted_prediction_tokens': 0,
                                                'rejected_prediction_tokens': 0},
                     cost=0.000042)
        chunk.update(REALISTIC_EXTRAS)
    return 'data: ' + json.dumps(chunk, separators=(',', ':')) + '\n\n'


def _prompt_tokens(messages) -> int:
    """Deterministic stand-in for tokenization: one token per four characters of text, rounded up."""
    return sum(-(-len(item['content']) // 4) for item in messages
               if type(item) is dict and type(item.get('content')) is str)


class FakeGateway:
    def __init__(self, configuration: FakeGatewayConfiguration, sleep):
        self.configuration = configuration
        self._sleep = sleep
        self._records: list[GatewayRecord] = []
        self.app = self._build()

    @property
    def records(self) -> tuple[GatewayRecord, ...]:
        return tuple(self._records)

    def reset(self):
        self._records.clear()

    def _authorized(self, request: Request) -> bool:
        header = request.headers.get('authorization')
        return header is not None and any(
            hmac.compare_digest(header.encode(), ('Bearer ' + key).encode())
            for key in self.configuration.keys)

    def _record(self, request: Request, model=None):
        self._records.append(GatewayRecord(request.method, request.url.path, model,
                                           request.headers.get('authorization')))

    async def _stream(self, model: str, prompt_tokens=None):
        """Role chunk, word deltas, a stop chunk, then ``[DONE]``; faults are model-id driven."""
        realistic = self.configuration.openai_realistic
        yield _event(model, {'role': 'assistant', 'content': ''}, realistic=realistic)
        words = REPLY.split(' ')
        for position, word in enumerate(words):
            if model == 'fake-slow':
                await self._sleep(self.configuration.slow_delay_seconds)
            delta = {'content': word if position == len(words) - 1 else word + ' '}
            if model == 'fake-malformed':
                delta['function_call'] = None
            yield _event(model, delta, realistic=realistic)
        yield _event(model, {}, 'stop', realistic=realistic)
        if prompt_tokens is not None and model != NO_USAGE_MODEL:
            yield _usage_event(model, prompt_tokens, len(words), realistic)
        yield 'data: [DONE]\n\n'

    def _build(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        def unauthorized():
            return JSONResponse({'error': {'message': 'Invalid credentials.', 'type': 'invalid_request_error'}},
                                status_code=401, headers={'WWW-Authenticate': 'Bearer'})

        @app.get('/v1/models')
        async def models(request: Request):
            self._record(request)
            if not self._authorized(request):
                return unauthorized()
            return {'object': 'list', 'data': [
                {'id': model, 'object': 'model', 'created': 0, 'owned_by': 'fake-gateway'}
                for model in sorted(MODELS)]}

        def failure(status, message, kind='invalid_request_error'):
            return JSONResponse({'error': {'message': message, 'type': kind}}, status_code=status)

        @app.post('/v1/chat/completions')
        async def completions(request: Request):
            if not self._authorized(request):
                self._record(request)
                return unauthorized()
            try:
                body = await request.json()
            except ValueError:
                body = None
            model = body.get('model') if type(body) is dict else None
            if type(model) is not str or not 1 <= len(model) <= MAX_MODEL_ID:
                model = None
            self._record(request, model)
            if model is None or type(body.get('messages')) is not list or not body['messages']:
                return failure(400, 'Invalid request.')
            if body.get('stream') is not True:
                return failure(400, 'Only streamed completions are supported.')
            if model not in MODELS:
                return failure(404, 'Unknown model.')
            if model == 'fake-error':
                return failure(500, 'Fake gateway failure.', 'server_error')
            # Like a real gateway, usage is sent only when the caller asked for it.
            wanted = body.get('stream_options') == {'include_usage': True}
            return StreamingResponse(self._stream(model, _prompt_tokens(body['messages']) if wanted else None),
                                     media_type='text/event-stream',
                                     headers={'Cache-Control': 'no-store'})

        @app.get('/__fake/requests')
        async def requests():
            return {'requests': [{'method': record.method, 'path': record.path, 'model': record.model,
                                  'authorization_sha256': record.digest()} for record in self._records]}

        @app.post('/__fake/reset')
        async def reset():
            self.reset()
            return Response(status_code=204)

        return app


def create_fake_gateway(configuration: FakeGatewayConfiguration, *, sleep=None) -> FakeGateway:
    """``sleep`` is an injectable coroutine function so tests never wait for real time."""
    if type(configuration) is not FakeGatewayConfiguration:
        raise TypeError('Explicit fake gateway configuration required.')
    return FakeGateway(configuration, asyncio.sleep if sleep is None else sleep)


class GatewayPortOccupied(RuntimeError):
    def __init__(self):
        super().__init__('PORT_OCCUPIED')


_HOST_NAME = re.compile(r'[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?')


def make_certificate(directory, names):
    """Write a self-signed throwaway certificate (and its key) for ``names`` into ``directory``: gateway.crt, gateway.key.

    Valid for two days and meant to be trusted explicitly (a private CA file), never installed anywhere. Returns both paths.
    """
    import datetime
    import os
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    if type(names) is not tuple or not 1 <= len(names) <= 8:
        raise ValueError('Invalid certificate names.')
    alternatives = []
    for name in names:
        if type(name) is not str:
            raise ValueError('Invalid certificate names.')
        try:
            alternatives.append(x509.IPAddress(ip_address(name)))
        except ValueError:
            if not _HOST_NAME.fullmatch(name):
                raise ValueError('Invalid certificate names.') from None
            alternatives.append(x509.DNSName(name))
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'forge fake gateway (throwaway)')])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
                   .not_valid_after(now + datetime.timedelta(days=2))
                   .add_extension(x509.SubjectAlternativeName(alternatives), critical=False)
                   .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                   .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=False, content_commitment=False,
                                                key_encipherment=False, data_encipherment=False, key_agreement=False,
                                                encipher_only=False, decipher_only=False), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
                   .sign(key, hashes.SHA256()))
    directory = Path(directory)
    certificate_path, key_path = directory/'gateway.crt', directory/'gateway.key'
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return certificate_path, key_path


def read_keys(path):
    """One accepted key per line; blank lines ignored. Errors never echo file content."""
    try:
        keys = tuple(line.strip() for line in Path(path).read_text('utf-8').splitlines() if line.strip())
        FakeGatewayConfiguration(keys=keys)
    except (OSError, ValueError):
        raise ValueError('KEYS_FILE_INVALID') from None
    return keys


def serve(configuration: FakeGatewayConfiguration, *, stopping=None, announce=None, sleep=None):
    """Run the real HTTP server until ``stopping`` is set; the port is reserved before anything else."""
    from forge.mvp_local import ConfigError, reserve_loopback_port
    stopping = Event() if stopping is None else stopping
    try:
        if configuration.any_interface:
            from forge.serve_prod import reserve_port
            listener = reserve_port(configuration.host, configuration.port)
        else:
            listener = reserve_loopback_port(configuration.port)
    except ConfigError:
        raise GatewayPortOccupied() from None
    try:
        import uvicorn
        server = uvicorn.Server(uvicorn.Config(create_fake_gateway(configuration, sleep=sleep).app,
                                               host=configuration.host, port=configuration.port, access_log=False,
                                               log_config=None, timeout_graceful_shutdown=5,
                                               ssl_certfile=configuration.tls_cert, ssl_keyfile=configuration.tls_key))

        def watch():
            stopping.wait()
            server.should_exit = True
        Thread(target=watch, daemon=True).start()
        if announce is not None:
            announce()
        server.run(sockets=[listener])
    finally:
        stopping.set()
        listener.close()


class _Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage()


def main(argv=None, *, stopping=None):
    emit = lambda document: print(json.dumps(document), flush=True)
    try:
        parser = _Parser(prog='forge.fake_gateway', description='Fake OpenAI-compatible gateway; never a real provider.')
        parser.add_argument('--keys-file')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT)
        parser.add_argument('--tls-cert')
        parser.add_argument('--tls-key')
        parser.add_argument('--bind-all', action='store_true')
        parser.add_argument('--openai-realistic', action='store_true')
        parser.add_argument('--make-cert', metavar='DIRECTORY')
        parser.add_argument('--name', action='append')
        arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
        if (arguments.make_cert is None) == (arguments.keys_file is None):
            raise _Usage()
    except _Usage:
        emit({'status': 'failed', 'code': 'INVALID_ARGUMENTS'})
        return 2
    try:
        if arguments.make_cert is not None:
            certificate, _ = make_certificate(Path(arguments.make_cert), tuple(arguments.name or ()))
            emit({'status': 'created', 'certificate': str(certificate)})
            return 0
        from forge.mvp_local import FORBIDDEN_PORTS
        if arguments.port in FORBIDDEN_PORTS:
            raise ValueError('PORT_FORBIDDEN')
        options = {'tls_cert': arguments.tls_cert, 'tls_key': arguments.tls_key, 'openai_realistic': arguments.openai_realistic}
        if arguments.bind_all:
            options.update(host='0.0.0.0', any_interface=True)
        configuration = FakeGatewayConfiguration(keys=read_keys(arguments.keys_file), port=arguments.port, **options)
        scheme = 'https' if configuration.tls_cert else 'http'
        serve(configuration, stopping=stopping, announce=lambda: emit({
            'status': 'ready', 'origin': '%s://%s:%d' % (scheme, configuration.host, configuration.port)}))
        return 0
    except KeyboardInterrupt:
        return 0
    except GatewayPortOccupied:
        emit({'status': 'failed', 'code': 'PORT_OCCUPIED'})
    except ValueError as error:
        emit({'status': 'failed', 'code': str(error) if str(error) in ('KEYS_FILE_INVALID', 'PORT_FORBIDDEN')
              else 'INVALID_CONFIGURATION'})
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
