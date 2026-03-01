#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${1:-all}"
CONTAINER_CLI="${CFDDNS_CONTAINER_CLI:-docker}"
PYTHON_IMAGE="${CFDDNS_PYTHON_IMAGE:-python:3.12-slim}"

if ! command -v "$CONTAINER_CLI" >/dev/null 2>&1; then
  echo "$CONTAINER_CLI is required but not installed"
  exit 1
fi

ensure_qemu() {
  if "$CONTAINER_CLI" run --rm --platform linux/arm64 "$PYTHON_IMAGE" python -V >/dev/null 2>&1; then
    return 0
  fi

  echo "Enabling binfmt/QEMU for cross-architecture emulation..."
  if ! "$CONTAINER_CLI" run --privileged --rm tonistiigi/binfmt --install all >/dev/null 2>&1; then
    echo "Could not auto-enable QEMU/binfmt."
    echo "Run manually: sudo $CONTAINER_CLI run --privileged --rm tonistiigi/binfmt --install all"
    exit 1
  fi
}

build_for_arch() {
  local arch="$1"
  local platform="linux/${arch}"
  local output_name="cfddns-linux-${arch}"

  echo "Building ${output_name} using ${platform}..."

  "$CONTAINER_CLI" run --rm \
    --platform "$platform" \
    --user "$(id -u):$(id -g)" \
    -v "$PROJECT_DIR:/workspace" \
    -w /workspace \
    "$PYTHON_IMAGE" \
    bash -lc "
      set -euo pipefail
      pip install --no-cache-dir -r requirements.txt pyinstaller
      pyinstaller --clean --onefile --name ${output_name} --collect-submodules gunicorn --add-data templates:templates --add-data static:static serve.py
    "

  if ! command -v file >/dev/null 2>&1; then
    echo "Built: dist/${output_name}"
    return 0
  fi

  file "${PROJECT_DIR}/dist/${output_name}" | cat
}

case "$TARGET" in
  amd64|arm64)
    ensure_qemu
    build_for_arch "$TARGET"
    ;;
  all)
    ensure_qemu
    build_for_arch amd64
    build_for_arch arm64
    ;;
  *)
    echo "Usage: ./scripts/build_binary_arm64.sh [all|amd64|arm64]"
    exit 1
    ;;
esac

echo "Done. Artifacts are in dist/."
