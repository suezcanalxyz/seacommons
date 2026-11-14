"""Deterministic negative controls for the public PLAY smoke probe."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest

spec = importlib.util.spec_from_file_location("public_play_smoke", Path(__file__).resolve().parents[1] / "scripts" / "public_play_smoke.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublicPlaySmokeTests(unittest.TestCase):
    def test_refuses_http(self):
        with self.assertRaises(ValueError):
            module.probe("http://play.seacommons.org")

    def test_refuses_embedded_credentials(self):
        with self.assertRaises(ValueError):
            module.probe("https://user:secret@play.seacommons.org")

    def test_dns_failure_does_not_claim_site_down(self):
        with patch.object(module.socket, "getaddrinfo", side_effect=socket_error()):
            result = module.probe("https://play.seacommons.org")
        self.assertEqual(result["dns"], "failed")
        self.assertEqual(result["tls_http"], "unknown")
        self.assertEqual(result["error_type"], "gaierror")


def socket_error():
    import socket
    return socket.gaierror(-2, "Name or service not known")


if __name__ == "__main__":
    unittest.main()
