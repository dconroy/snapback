"""A local certificate authority so the phone can trust Snapback's secure page.

iOS only offers "Save Image" / "Save Video" from a secure page. Snapback creates
a CA on the Pi and a server certificate signed by it. Install ``ca.pem`` on the
phone once and enable full trust; the browser warning then goes away.
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


def _openssl(args: list[str]) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


def ensure_certificate(directory: Path, hosts: list[str]) -> tuple[Path, Path]:
    """Write a local CA plus a server certificate signed by it.

    The CA is created once. The server certificate is reused until the host list
    changes, and reissued from the same CA so the phone does not need a new profile.
    """
    directory.mkdir(parents=True, exist_ok=True)
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    ca = directory / "ca.pem"
    ca_key = directory / "ca.key"
    stamp = directory / "hosts.txt"
    wanted = "\n".join(hosts) + "\n"
    if all(path.exists() for path in (cert, key, ca, ca_key)) and stamp.is_file() and stamp.read_text() == wanted:
        return cert, key
    if not (ca.exists() and ca_key.exists()):
        _openssl([
            "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-days", "825", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca),
            "-subj", "/CN=Snapback Local CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        ])
    san = ",".join(f"IP:{host}" if _is_ip(host) else f"DNS:{host}" for host in hosts)
    csr = directory / "server.csr"
    ext = directory / "server.ext"
    ext.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName={san}\n"
    )
    _openssl([
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(csr),
        "-subj", "/CN=snapback.local",
    ])
    _openssl([
        "x509", "-req", "-in", str(csr),
        "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(cert), "-days", "825", "-sha256",
        "-extfile", str(ext),
    ])
    csr.unlink(missing_ok=True)
    ext.unlink(missing_ok=True)
    stamp.write_text(wanted)
    return cert, key
