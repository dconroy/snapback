"""A self-signed certificate so the phone page can use the share sheet.

iOS only offers "Save Image" / "Save Video" (which add to Photos) from a secure
page. The certificate is generated on the Pi and is not trusted, so the phone
shows a warning the first time.
"""

from __future__ import annotations

import ipaddress
import socket
import subprocess
from pathlib import Path

HTTPS_PORT = 8443


def certificate_hosts() -> list[str]:
    hosts = ["snapback.local", "localhost", "127.0.0.1"]
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.168.1.1", 80))
        hosts.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return hosts


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def ensure_certificate(directory: Path, hosts: list[str]) -> tuple[Path, Path]:
    """Write cert.pem and key.pem, reusing them while the host list is unchanged."""
    directory.mkdir(parents=True, exist_ok=True)
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    stamp = directory / "hosts.txt"
    wanted = "\n".join(hosts) + "\n"
    if cert.exists() and key.exists() and stamp.is_file() and stamp.read_text() == wanted:
        return cert, key
    san = ",".join(f"IP:{host}" if _is_ip(host) else f"DNS:{host}" for host in hosts)
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "825",
            "-nodes", "-keyout", str(key), "-out", str(cert),
            "-subj", "/CN=snapback.local",
            "-addext", f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
    )
    stamp.write_text(wanted)
    return cert, key
