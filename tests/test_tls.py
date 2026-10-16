from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from snapback.tls import ensure_certificate

OPENSSL = shutil.which("openssl")


@unittest.skipUnless(OPENSSL, "openssl is not installed")
class CertificateTests(unittest.TestCase):
    def test_writes_cert_once_and_reuses_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            cert, key = ensure_certificate(directory, ["snapback.local", "127.0.0.1"])
            ca = directory / "ca.pem"
            first = cert.read_bytes()
            ca_first = ca.read_bytes()
            self.assertTrue(key.is_file())
            subprocess.run(["openssl", "verify", "-CAfile", str(ca), str(cert)], check=True, capture_output=True)

            again, _ = ensure_certificate(directory, ["snapback.local", "127.0.0.1"])
            self.assertEqual(first, again.read_bytes())

            ensure_certificate(directory, ["snapback.local", "10.0.0.8"])
            self.assertEqual(ca_first, ca.read_bytes())
            self.assertNotEqual(first, cert.read_bytes())
            subprocess.run(["openssl", "verify", "-CAfile", str(ca), str(cert)], check=True, capture_output=True)
