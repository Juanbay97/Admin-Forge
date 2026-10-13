"""The fake gateway can serve TLS with a throwaway self-signed certificate so the deployment proof can reach it over https
(the production allow-list refuses plain http). Test and dev only: it never binds beyond loopback unless asked to, explicitly."""
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import httpx
from cryptography import x509
from forge.fake_gateway import FakeGatewayConfiguration, main, make_certificate, serve

KEY = 'sk-fake-tls-0001'


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class CertificateTests(unittest.TestCase):
    def test_a_throwaway_certificate_names_exactly_the_requested_hosts_and_is_short_lived(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate, key = make_certificate(Path(directory), ('fake-gateway', '127.0.0.1'))
            parsed = x509.load_pem_x509_certificate(certificate.read_bytes())
            names = parsed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            self.assertEqual(sorted(names.get_values_for_type(x509.DNSName)), ['fake-gateway'])
            self.assertEqual([str(ip) for ip in names.get_values_for_type(x509.IPAddress)], ['127.0.0.1'])
            self.assertLessEqual((parsed.not_valid_after_utc - parsed.not_valid_before_utc).days, 3)
            self.assertEqual({path.name for path in Path(directory).iterdir()}, {'gateway.crt', 'gateway.key'})
            self.assertNotIn(b'PRIVATE KEY', certificate.read_bytes())
            self.assertIn(b'PRIVATE KEY', key.read_bytes())

    def test_invalid_names_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            for names in ((), ('bad name',), ('x' * 300,), ('ok', 5)):
                with self.subTest(names=names), self.assertRaises(ValueError):
                    make_certificate(Path(directory), names)


class ConfigurationTests(unittest.TestCase):
    def test_all_interfaces_are_only_for_an_explicit_tls_container_run(self):
        with self.assertRaises(ValueError):
            FakeGatewayConfiguration(keys=(KEY,), host='0.0.0.0')
        with self.assertRaises(ValueError):
            FakeGatewayConfiguration(keys=(KEY,), host='0.0.0.0', any_interface=True)  # plain http is never exposed
        with self.assertRaises(ValueError):
            FakeGatewayConfiguration(keys=(KEY,), host='127.0.0.1', any_interface=True)
        configuration = FakeGatewayConfiguration(keys=(KEY,), host='0.0.0.0', any_interface=True, tls_cert='c.crt', tls_key='c.key')
        self.assertEqual(configuration.host, '0.0.0.0')
        with self.assertRaises(ValueError):
            FakeGatewayConfiguration(keys=(KEY,), tls_cert='c.crt')  # a certificate needs its key


class ServeTlsTests(unittest.TestCase):
    def test_it_serves_https_to_a_client_that_trusts_the_certificate_and_refuses_everyone_else(self):
        with tempfile.TemporaryDirectory() as directory:
            certificate, key = make_certificate(Path(directory), ('127.0.0.1',))
            port, stopping, ready = free_port(), threading.Event(), threading.Event()
            configuration = FakeGatewayConfiguration(keys=(KEY,), port=port, tls_cert=str(certificate), tls_key=str(key))
            thread = threading.Thread(target=serve, args=(configuration,), kwargs={'stopping': stopping, 'announce': ready.set}, daemon=True)
            thread.start()
            try:
                self.assertTrue(ready.wait(10))
                url = 'https://127.0.0.1:%d/v1/models' % port
                deadline = time.monotonic() + 10
                while True:
                    try:
                        trusted = httpx.get(url, headers={'Authorization': 'Bearer ' + KEY}, verify=str(certificate), timeout=5)
                        break
                    except httpx.TransportError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.1)
                self.assertEqual((trusted.status_code, 'fake-fast' in trusted.text), (200, True))
                with self.assertRaises(httpx.ConnectError):
                    httpx.get(url, headers={'Authorization': 'Bearer ' + KEY}, timeout=5)  # the system trust store does not know it
                with self.assertRaises(httpx.TransportError):
                    httpx.get('http://127.0.0.1:%d/v1/models' % port, timeout=5)  # no plain http beside it
            finally:
                stopping.set()
                thread.join(10)


class CommandLineTests(unittest.TestCase):
    def test_make_cert_writes_the_files_and_prints_a_finite_status_without_the_key(self):
        import contextlib
        import io
        import json
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['--make-cert', directory, '--name', 'fake-gateway']), 0)
            self.assertTrue((Path(directory)/'gateway.crt').is_file() and (Path(directory)/'gateway.key').is_file())
        document = json.loads(output.getvalue().strip())
        self.assertEqual(document['status'], 'created')
        self.assertNotIn('PRIVATE', output.getvalue())


if __name__ == '__main__':
    unittest.main()
