#!/usr/bin/env python3
"""Strict end-to-end security validation for personal-task-station.

Validates:
1. Certificate chain integrity
2. HTTPS server startup and certificate presentation
3. Client rejects HTTP
4. Client verifies server certificate (no cert = fail, with cert = pass)
5. API key required over HTTPS
6. mTLS enforcement (optional)
7. Full data flow over secure channel
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).parent.parent.resolve()

def log(msg: str) -> None:
    print(f"[VALIDATE] {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}", file=sys.stderr)
    return False


def ok(msg: str) -> None:
    print(f"[OK] {msg}")
    return True


def generate_certs(output_dir: Path) -> dict[str, Path]:
    log("Generating fresh certificates...")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_certs.py"),
         "--output-dir", str(output_dir), "--hostname", "localhost"],
        capture_output=True, text=True, check=True,
    )
    print(result.stdout)
    return {
        "ca_cert": output_dir / "ca-cert.pem",
        "ca_key": output_dir / "ca-key.pem",
        "server_cert": output_dir / "server-cert.pem",
        "server_key": output_dir / "server-key.pem",
        "client_cert": output_dir / "client-cert.pem",
        "client_key": output_dir / "client-key.pem",
    }


def verify_cert_properties(paths: dict[str, Path]) -> bool:
    log("Verifying certificate properties...")
    all_ok = True

    # 1. Server cert has SAN with localhost and 127.0.0.1
    result = subprocess.run(
        ["openssl", "x509", "-in", str(paths["server_cert"]), "-noout", "-text"],
        capture_output=True, text=True, check=True,
    )
    server_text = result.stdout
    checks = [
        ("DNS:localhost" in server_text, "Server cert SAN contains DNS:localhost"),
        ("IP Address:127.0.0.1" in server_text, "Server cert SAN contains IP:127.0.0.1"),
        ("TLS Web Server Authentication" in server_text, "Server cert has ServerAuth EKU"),
        ("Issuer: C=CN, O=PersonalTaskStation, CN=PersonalTaskStation CA" in server_text,
         "Server cert is signed by PTS CA"),
    ]
    for cond, desc in checks:
        if cond:
            ok(desc)
        else:
            all_ok = fail(desc)

    # 2. Client cert has ClientAuth EKU
    result = subprocess.run(
        ["openssl", "x509", "-in", str(paths["client_cert"]), "-noout", "-text"],
        capture_output=True, text=True, check=True,
    )
    client_text = result.stdout
    if "TLS Web Client Authentication" in client_text:
        ok("Client cert has ClientAuth EKU")
    else:
        all_ok = fail("Client cert missing ClientAuth EKU")

    # 3. Chain verification
    for cert_name in ["server_cert", "client_cert"]:
        result = subprocess.run(
            ["openssl", "verify", "-CAfile", str(paths["ca_cert"]), str(paths[cert_name])],
            capture_output=True, text=True, check=True,
        )
        if "OK" in result.stdout:
            ok(f"{cert_name} chain verifies against CA")
        else:
            all_ok = fail(f"{cert_name} chain verification failed: {result.stdout}")

    return all_ok


def wait_for_server(port: int, timeout: float = 10.0, verify: str | bool = True, cert: tuple[str, str] | None = None) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            if cert:
                status, body, _ = _curl(f"https://127.0.0.1:{port}/health", Path(verify), Path(cert[0]), Path(cert[1]))
                if status == 200:
                    return True
            else:
                r = httpx.get(f"https://127.0.0.1:{port}/health", verify=verify, timeout=2.0)
                if r.status_code == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def start_server(env: dict[str, str], port: int) -> subprocess.Popen:
    log(f"Starting server on port {port}...")
    env_full = {**os.environ, **env}
    extra_args = []
    if env.get("PTS_SSL_CAFILE"):
        extra_args += ["--ssl-ca-certs", env["PTS_SSL_CAFILE"], "--ssl-cert-reqs", "2"]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "personal_task_station.server.app:app",
         "--host", "127.0.0.1",
         "--port", str(port),
         "--ssl-keyfile", env["PTS_SSL_KEYFILE"],
         "--ssl-certfile", env["PTS_SSL_CERTFILE"],
         *extra_args,
        ],
        cwd=str(REPO_ROOT),
        env=env_full,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def test_https_without_ca_fails(port: int) -> bool:
    log("Testing HTTPS without CA cert (should fail)...")
    try:
        httpx.get(f"https://127.0.0.1:{port}/health", timeout=5.0)
        return fail("Connection succeeded without CA cert — verification bypassed!")
    except httpx.ConnectError as exc:
        if "certificate verify failed" in str(exc) or "SSL" in str(exc):
            ok("HTTPS connection correctly rejected without CA cert")
            return True
        return fail(f"Unexpected connection error: {exc}")
    except Exception as exc:
        return fail(f"Unexpected error: {exc}")


def test_https_with_ca_no_api_key(port: int, ca_cert: Path) -> bool:
    log("Testing HTTPS with CA but no API key (should get 401)...")
    try:
        r = httpx.get(f"https://127.0.0.1:{port}/tasks", verify=str(ca_cert), timeout=5.0)
        if r.status_code == 401:
            ok("Protected endpoint returns 401 without API key")
            return True
        return fail(f"Expected 401, got {r.status_code}: {r.text}")
    except Exception as exc:
        return fail(f"Request failed: {exc}")


def test_https_with_ca_and_api_key(port: int, ca_cert: Path, api_key: str) -> bool:
    log("Testing HTTPS with CA + API key (should succeed)...")
    try:
        headers = {"X-API-Key": api_key}
        r = httpx.get(f"https://127.0.0.1:{port}/tasks", verify=str(ca_cert), headers=headers, timeout=5.0)
        if r.status_code == 200:
            ok("Authenticated HTTPS request succeeded")
            return True
        return fail(f"Expected 200, got {r.status_code}: {r.text}")
    except Exception as exc:
        return fail(f"Request failed: {exc}")


def test_https_wrong_api_key(port: int, ca_cert: Path) -> bool:
    log("Testing HTTPS with wrong API key (should get 401)...")
    try:
        headers = {"X-API-Key": "wrong-key"}
        r = httpx.get(f"https://127.0.0.1:{port}/tasks", verify=str(ca_cert), headers=headers, timeout=5.0)
        if r.status_code == 401:
            ok("Wrong API key correctly rejected with 401")
            return True
        return fail(f"Expected 401, got {r.status_code}: {r.text}")
    except Exception as exc:
        return fail(f"Request failed: {exc}")


def test_http_refused(port: int) -> bool:
    log("Testing HTTP connection (should be refused)...")
    try:
        httpx.get(f"http://127.0.0.1:{port}/health", timeout=5.0)
        return fail("HTTP connection succeeded — server should not listen on HTTP!")
    except (httpx.ConnectError, httpx.RemoteProtocolError):
        ok("HTTP connection correctly refused")
        return True
    except Exception as exc:
        return fail(f"Unexpected error: {exc}")


def test_full_crud_over_https(port: int, ca_cert: Path, api_key: str) -> bool:
    log("Testing full CRUD data flow over HTTPS...")
    all_ok = True
    base = f"https://127.0.0.1:{port}"
    headers = {"X-API-Key": api_key}
    verify = str(ca_cert)

    try:
        # Create
        r = httpx.post(f"{base}/tasks", headers=headers, verify=verify, timeout=5.0, json={
            "title": "Secure Task", "description": "Created over HTTPS", "task_date": "2026-04-23"
        })
        if r.status_code != 201:
            return fail(f"Create failed: {r.status_code} {r.text}")
        task = r.json()
        task_id = task["id"]
        ok(f"Created task {task_id} over HTTPS")

        # Read
        r = httpx.get(f"{base}/tasks/{task_id}", headers=headers, verify=verify, timeout=5.0)
        if r.status_code != 200 or r.json()["title"] != "Secure Task":
            all_ok = fail(f"Read failed: {r.status_code} {r.text}")
        else:
            ok("Read task over HTTPS")

        # Update
        r = httpx.patch(f"{base}/tasks/{task_id}", headers=headers, verify=verify, timeout=5.0, json={"title": "Updated Secure Task"})
        if r.status_code != 200:
            all_ok = fail(f"Update failed: {r.status_code} {r.text}")
        else:
            ok("Updated task over HTTPS")

        # Delete
        r = httpx.delete(f"{base}/tasks/{task_id}", headers=headers, verify=verify, timeout=5.0)
        if r.status_code != 204:
            all_ok = fail(f"Delete failed: {r.status_code} {r.text}")
        else:
            ok("Deleted task over HTTPS")

    except Exception as exc:
        return fail(f"CRUD flow failed: {exc}")

    return all_ok


def _curl(url: str, ca_cert: Path, client_cert: Path | None = None, client_key: Path | None = None) -> tuple[int, str, str]:
    cmd = ["curl", "-s", "-w", "\\n%{http_code}", "--cacert", str(ca_cert)]
    if client_cert and client_key:
        cmd += ["--cert", str(client_cert), "--key", str(client_key)]
    cmd += [url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    status_line = lines[-1] if lines else "0"
    body = "\\n".join(lines[:-1]) if len(lines) > 1 else ""
    return int(status_line), body, result.stderr


def test_mtls_rejects_client_without_cert(port: int, ca_cert: Path, api_key: str) -> bool:
    log("Testing mTLS: client without cert (should fail TLS handshake)...")
    status, body, stderr = _curl(f"https://127.0.0.1:{port}/health", ca_cert)
    # curl returncode 56 = CURLE_RECV_ERROR (server closed during TLS handshake)
    # or empty body with status 0
    if status == 0 and not body:
        ok("mTLS server correctly rejected client without certificate")
        return True
    return fail(f"Expected connection failure, got status={status} body={body}")


def test_mtls_accepts_client_with_cert(port: int, ca_cert: Path, client_cert: Path, client_key: Path, api_key: str) -> bool:
    log("Testing mTLS: client with cert (should succeed)...")
    status, body, stderr = _curl(
        f"https://127.0.0.1:{port}/health", ca_cert, client_cert, client_key
    )
    if status == 200 and '"status":"ok"' in body:
        ok("mTLS connection with client certificate succeeded")
        return True
    return fail(f"Expected 200, got status={status} body={body} stderr={stderr}")


def stop_server(proc: subprocess.Popen) -> None:
    log("Stopping server...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    log("=" * 60)
    log("STARTING STRICT END-TO-END SECURITY VALIDATION")
    log("=" * 60)

    results = []

    with tempfile.TemporaryDirectory() as tmpdir:
        cert_dir = Path(tmpdir)
        paths = generate_certs(cert_dir)
        api_key = "strict-validation-token-1234"

        # Phase 1: Certificate properties
        results.append(("Certificate chain + properties", verify_cert_properties(paths)))

        # Phase 2: HTTPS-only server (no mTLS)
        port = 18443
        env = {
            "PTS_API_KEY": api_key,
            "PTS_DATABASE_URL": f"sqlite:///{cert_dir}/test.db",
            "PTS_HOST": "127.0.0.1",
            "PTS_PORT": str(port),
            "PTS_SSL_CERTFILE": str(paths["server_cert"]),
            "PTS_SSL_KEYFILE": str(paths["server_key"]),
        }
        env_no_ca = {k: v for k, v in env.items() if k != "PTS_SSL_CAFILE"}
        proc = start_server(env_no_ca, port)
        try:
            if not wait_for_server(port, timeout=10.0, verify=str(paths["ca_cert"])):
                results.append(("Server startup", False))
                log("Server failed to start, aborting remaining tests.")
            else:
                ok("Server started and health check responded")
                results.append(("Server startup", True))
                results.append(("HTTP refused", test_http_refused(port)))
                results.append(("HTTPS without CA cert rejected", test_https_without_ca_fails(port)))
                results.append(("HTTPS + CA, no API key = 401", test_https_with_ca_no_api_key(port, paths["ca_cert"])))
                results.append(("HTTPS + CA + wrong API key = 401", test_https_wrong_api_key(port, paths["ca_cert"])))
                results.append(("HTTPS + CA + correct API key = 200", test_https_with_ca_and_api_key(port, paths["ca_cert"], api_key)))
                results.append(("Full CRUD over HTTPS", test_full_crud_over_https(port, paths["ca_cert"], api_key)))
        finally:
            stop_server(proc)

        # Phase 3: mTLS server
        port2 = 18444
        env_mtls = {
            **env,
            "PTS_PORT": str(port2),
            "PTS_SSL_CAFILE": str(paths["ca_cert"]),
        }
        proc2 = start_server(env_mtls, port2)
        try:
            if not wait_for_server(port2, timeout=10.0, verify=str(paths["ca_cert"]), cert=(str(paths["client_cert"]), str(paths["client_key"]))):
                results.append(("mTLS server startup", False))
                log("mTLS server failed to start, aborting mTLS tests.")
            else:
                ok("mTLS server started")
                results.append(("mTLS server startup", True))
                results.append(("mTLS rejects client without cert", test_mtls_rejects_client_without_cert(port2, paths["ca_cert"], api_key)))
                results.append(("mTLS accepts client with cert", test_mtls_accepts_client_with_cert(port2, paths["ca_cert"], paths["client_cert"], paths["client_key"], api_key)))
        finally:
            stop_server(proc2)

    # Phase 4: Full pytest suite
    log("Running full pytest suite...")
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    if pytest_result.returncode == 0:
        ok("Full pytest suite passed")
        results.append(("Pytest suite", True))
    else:
        fail("Pytest suite failed")
        print(pytest_result.stdout)
        print(pytest_result.stderr, file=sys.stderr)
        results.append(("Pytest suite", False))

    # Summary
    log("=" * 60)
    log("VALIDATION SUMMARY")
    log("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\nTotal: {passed}/{total} passed")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
