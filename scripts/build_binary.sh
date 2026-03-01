#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_VENV="$PROJECT_DIR/.build-venv"
OUTPUT_DIR="$PROJECT_DIR/dist"
ARCH_INPUT="${1:-auto}"

detect_arch() {
  case "$(uname -m)" in
    x86_64) echo "amd64" ;;
    aarch64|arm64) echo "arm64" ;;
    *)
      echo "Unsupported architecture: $(uname -m)"
      exit 1
      ;;
  esac
}

HOST_ARCH="$(detect_arch)"

if [ "$ARCH_INPUT" = "auto" ]; then
  ARCH="$HOST_ARCH"
else
  ARCH="$ARCH_INPUT"
fi

if [ "$ARCH" != "amd64" ] && [ "$ARCH" != "arm64" ]; then
  echo "ARCH must be amd64 or arm64"
  exit 1
fi

if [ "$ARCH" != "$HOST_ARCH" ]; then
  echo "Cannot build real '$ARCH' binary on '$HOST_ARCH' host with PyInstaller."
  echo "Run this script on a native $ARCH machine (or matching container/runner)."
  exit 1
fi

ASSET_NAME="cfddns-linux-${ARCH}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required"
  exit 1
fi

python3 -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/pip" install --upgrade pip
"$BUILD_VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt" pyinstaller

"$BUILD_VENV/bin/pyinstaller" \
  --clean \
  --onefile \
  --name "$ASSET_NAME" \
  --collect-submodules gunicorn \
  --add-data "$PROJECT_DIR/templates:templates" \
  --add-data "$PROJECT_DIR/static:static" \
  "$PROJECT_DIR/serve.py"

echo "Binary created at: $OUTPUT_DIR/$ASSET_NAME"
