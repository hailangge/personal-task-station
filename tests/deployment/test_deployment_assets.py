from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_docker_assets_are_present_and_configurable():
    dockerfile = (ROOT / "Dockerfile").read_text()
    compose = (ROOT / "docker-compose.yml").read_text()
    entrypoint = ROOT / "scripts/docker-entrypoint.sh"

    assert "python:3.12-slim" in dockerfile
    assert "scripts/docker-entrypoint.sh" in dockerfile
    assert "PTS_DATABASE_URL" in compose
    assert "PTS_API_KEY" in compose
    assert "PTS_SSL_CERTFILE" in compose
    assert entrypoint.exists()
    assert entrypoint.stat().st_mode & 0o111


def test_packaging_scripts_support_dry_run():
    scripts = [
        ROOT / "scripts/deploy-linux-server.sh",
        ROOT / "scripts/package-linux-client.sh",
    ]
    for script in scripts:
        assert script.exists()
        assert script.stat().st_mode & 0o111
        result = subprocess.run([str(script), "--dry-run"], cwd=ROOT, text=True, capture_output=True, check=True)
        assert "[dry-run]" in result.stdout


def test_windows_packaging_script_documents_pyinstaller():
    script = ROOT / "scripts/package-windows-client.ps1"
    text = script.read_text()
    assert "PyInstaller" in text
    assert "pts-client.exe" in text
    assert "DryRun" in text
