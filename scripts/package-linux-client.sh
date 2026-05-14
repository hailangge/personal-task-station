#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/package-linux-client.sh [--output-dir DIR] [--dry-run]

Creates a Linux desktop client distributable. If PyInstaller is available or can
be installed into a temporary venv, it builds a standalone executable; otherwise
it creates a source tarball with install/run instructions.
USAGE
}

OUTPUT_DIR="${PTS_PACKAGE_DIR:-dist/linux-client}"
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] would package Linux client into $OUTPUT_DIR"
  exit 0
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"
WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

python -m venv "$WORKDIR/venv"
"$WORKDIR/venv/bin/pip" install --upgrade pip >/dev/null
"$WORKDIR/venv/bin/pip" install -e ".[client]" pyinstaller >/dev/null

if "$WORKDIR/venv/bin/python" -m PyInstaller --name pts-client --onefile --windowed \
  --collect-all PySide6 \
  src/personal_task_station/client/main.py >/dev/null; then
  mkdir -p "$OUTPUT_DIR/bin"
  cp dist/pts-client "$OUTPUT_DIR/bin/pts-client"
  cat > "$OUTPUT_DIR/README.txt" <<README
Run ./bin/pts-client. Configure server URL, API key, and certificate paths in the Connection tab on first launch.
README
else
  echo "PyInstaller build failed; creating source tarball fallback." >&2
  tar --exclude='.git' --exclude='.venv' --exclude='dist' --exclude='build' -czf "$OUTPUT_DIR/personal-task-station-client-src.tar.gz" .
  cat > "$OUTPUT_DIR/README.txt" <<README
Install Python 3.12+, extract the tarball, then run:
python -m venv .venv
. .venv/bin/activate
pip install -e '.[client]'
pts-client
README
fi

echo "Linux client package written to $OUTPUT_DIR"
