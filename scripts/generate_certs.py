#!/usr/bin/env python3
"""Generate self-signed CA, server, and client certificates for HTTPS/mTLS."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _write_key(path: Path, key) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(path, 0o600)


def _write_cert(path: Path, cert) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(path, 0o644)


def _subject(common_name: str, org: str = "PersonalTaskStation") -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validity(days: int = 365):
    now = _now()
    return (now, now + timedelta(days=days))


def generate_ca(output_dir: Path, validity_days: int = 3650) -> tuple[Path, Path]:
    """Generate a self-signed CA certificate."""
    key = _rsa_key()
    not_before, not_after = _validity(validity_days)
    cert = (
        x509.CertificateBuilder()
        .subject_name(_subject("PersonalTaskStation CA"))
        .issuer_name(_subject("PersonalTaskStation CA"))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path = output_dir / "ca-key.pem"
    cert_path = output_dir / "ca-cert.pem"
    _write_key(key_path, key)
    _write_cert(cert_path, cert)
    return key_path, cert_path


def generate_server_cert(
    output_dir: Path,
    ca_key_path: Path,
    ca_cert_path: Path,
    hostname: str = "localhost",
    validity_days: int = 365,
) -> tuple[Path, Path]:
    """Generate a server certificate signed by the CA."""
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())

    key = _rsa_key()
    not_before, not_after = _validity(validity_days)

    san = x509.SubjectAlternativeName(
        [
            x509.DNSName(hostname),
            x509.DNSName(f"*.{hostname}"),
            x509.IPAddress(ip_address("127.0.0.1")),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(_subject(hostname))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(san, critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    key_path = output_dir / "server-key.pem"
    cert_path = output_dir / "server-cert.pem"
    _write_key(key_path, key)
    _write_cert(cert_path, cert)
    return key_path, cert_path


def generate_client_cert(
    output_dir: Path,
    ca_key_path: Path,
    ca_cert_path: Path,
    client_name: str = "pts-client",
    validity_days: int = 365,
) -> tuple[Path, Path]:
    """Generate a client certificate signed by the CA (for mTLS)."""
    ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())

    key = _rsa_key()
    not_before, not_after = _validity(validity_days)

    cert = (
        x509.CertificateBuilder()
        .subject_name(_subject(client_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    key_path = output_dir / "client-key.pem"
    cert_path = output_dir / "client-cert.pem"
    _write_key(key_path, key)
    _write_cert(cert_path, cert)
    return key_path, cert_path


def ip_address(addr: str):
    import ipaddress

    return ipaddress.ip_address(addr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate self-signed certificates for PTS HTTPS/mTLS")
    parser.add_argument("--output-dir", default="certs", help="Directory to write certificates (default: certs)")
    parser.add_argument("--hostname", default="localhost", help="Server hostname / SAN (default: localhost)")
    parser.add_argument("--client-name", default="pts-client", help="Client certificate CN (default: pts-client)")
    parser.add_argument("--validity-days", type=int, default=365, help="Certificate validity in days (default: 365)")
    parser.add_argument("--skip-client", action="store_true", help="Skip generating client certificate")
    args = parser.parse_args(argv)

    out = Path(args.output_dir).resolve()
    print(f"Generating certificates in: {out}")

    ca_key, ca_cert = generate_ca(out, validity_days=args.validity_days * 10)
    print(f"  CA key:     {ca_key}")
    print(f"  CA cert:    {ca_cert}")

    srv_key, srv_cert = generate_server_cert(
        out, ca_key, ca_cert, hostname=args.hostname, validity_days=args.validity_days
    )
    print(f"  Server key: {srv_key}")
    print(f"  Server cert: {srv_cert}")

    if not args.skip_client:
        cli_key, cli_cert = generate_client_cert(
            out, ca_key, ca_cert, client_name=args.client_name, validity_days=args.validity_days
        )
        print(f"  Client key: {cli_key}")
        print(f"  Client cert: {cli_cert}")

    print("\nDone. Keep ca-key.pem and server-key.pem secret.")
    print("Deploy ca-cert.pem to clients so they can verify the server.")
    if not args.skip_client:
        print("Deploy client-cert.pem + client-key.pem to authorized clients for mTLS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
