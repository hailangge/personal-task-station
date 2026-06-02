from __future__ import annotations

import subprocess
import textwrap
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
        ROOT / "scripts/run-host-server.sh",
        ROOT / "scripts/smoke-test.sh",
        ROOT / "scripts/deploy-linux-server.sh",
        ROOT / "scripts/package-linux-client.sh",
    ]
    for script in scripts:
        assert script.exists()
        assert script.stat().st_mode & 0o111
        result = subprocess.run([str(script), "--dry-run"], cwd=ROOT, text=True, capture_output=True, check=True)
        assert "[dry-run]" in result.stdout


def test_operator_host_assets_are_present_and_safe():
    env_template = ROOT / ".env.example"
    host_script = ROOT / "scripts/run-host-server.sh"
    smoke_script = ROOT / "scripts/smoke-test.sh"
    systemd_service = ROOT / "deploy/systemd/personal-task-station.service"

    assert env_template.exists()
    env_text = env_template.read_text()
    assert "PTS_API_KEY=change-me" in env_text
    assert "PTS_HOST=127.0.0.1" in env_text
    assert "PTS_DATABASE_URL=sqlite:///" in env_text
    assert "PTS_SSL_CERTFILE" in env_text
    assert "PTS_SSL_CAFILE" in env_text

    host_text = host_script.read_text()
    assert "--dry-run" in host_text
    assert "if [[ ! -f \"$ENV_FILE\" ]]" in host_text
    assert "mkdir -p \"$PTS_DATA_DIR\"" in host_text
    assert "alembic upgrade head" in host_text
    assert "exec .venv/bin/pts-server" in host_text

    compose_deploy_text = (ROOT / "scripts/deploy-linux-server.sh").read_text()
    assert "source \"$ENV_FILE\"" in compose_deploy_text

    smoke_text = smoke_script.read_text()
    assert "GET /health" in smoke_text
    assert "GET /tasks" in smoke_text
    assert "POST /tasks" in smoke_text
    assert "DELETE /tasks/$task_id" in smoke_text

    service_text = systemd_service.read_text()
    assert "EnvironmentFile=%h/personal-task-station/.env.host" in service_text
    assert "ExecStart=%h/personal-task-station/.venv/bin/pts-server" in service_text
    assert "Restart=on-failure" in service_text

    gitignore = (ROOT / ".gitignore").read_text()
    assert ".env" in gitignore
    assert ".env.host" in gitignore


def test_deployment_docs_describe_access_and_smoke_paths():
    readme = (ROOT / "README.md").read_text()
    deployment = (ROOT / "DEPLOYMENT.md").read_text()

    combined = f"{readme}\n{deployment}"
    assert "scripts/run-host-server.sh --dry-run" in combined
    assert "scripts/smoke-test.sh" in combined
    assert "http://127.0.0.1:8000" in combined
    assert "http://<server-lan-ip>:8000" in combined
    assert "reverse proxy" in combined
    assert "Docker Compose" in combined
    assert "Allow HTTP for localhost/private LAN" in combined


def test_shell_scripts_pass_bash_syntax_check():
    scripts = [
        ROOT / "scripts/run-host-server.sh",
        ROOT / "scripts/smoke-test.sh",
        ROOT / "scripts/deploy-linux-server.sh",
        ROOT / "scripts/package-linux-client.sh",
    ]
    for script in scripts:
        subprocess.run(["bash", "-n", str(script)], cwd=ROOT, check=True)


def test_host_script_creates_env_provided_data_dir_before_migrations(tmp_path):
    temp_root = tmp_path / "repo"
    temp_scripts = temp_root / "scripts"
    temp_venv_bin = temp_root / ".venv/bin"
    temp_scripts.mkdir(parents=True)
    temp_venv_bin.mkdir(parents=True)

    script = temp_scripts / "run-host-server.sh"
    script.write_text((ROOT / "scripts/run-host-server.sh").read_text())
    script.chmod(0o755)

    env_file = tmp_path / "pts-se.env"
    data_dir = tmp_path / "pts-se-data"
    env_file.write_text(
        textwrap.dedent(
            f"""
            PTS_API_KEY=test-key
            PTS_DATA_DIR={data_dir}
            PTS_DATABASE_URL=sqlite:///{data_dir}/personal_task_station.sqlite3
            """
        ).strip()
        + "\n"
    )

    alembic = temp_venv_bin / "alembic"
    alembic.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "[[ -d \"$PTS_DATA_DIR\" ]]\n"
    )
    alembic.chmod(0o755)

    pts_server = temp_venv_bin / "pts-server"
    pts_server.write_text("#!/usr/bin/env bash\nset -euo pipefail\necho fake-server\n")
    pts_server.chmod(0o755)

    result = subprocess.run(
        [str(script), "--env-file", str(env_file), "--no-install"],
        cwd=temp_root,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )

    assert data_dir.is_dir()
    assert "fake-server" in result.stdout


def test_windows_packaging_script_documents_pyinstaller():
    script = ROOT / "scripts/package-windows-client.ps1"
    text = script.read_text()
    assert "PyInstaller" in text
    assert "pts-client.exe" in text
    assert "DryRun" in text
