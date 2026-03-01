#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cfddns"
APP_USER="cfddns"
APP_GROUP="cfddns"
APP_DIR="/opt/cfddns"
BINARY_PATH="$APP_DIR/cfddns"
SYSTEM_CONFIG_DIR="/usr/share/cfddns"
SYSTEM_CONFIG_FILE="$SYSTEM_CONFIG_DIR/config.json"
ENV_FILE="/etc/default/cfddns"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
RELEASES_PAGE_URL="https://github.com/SzponerZoli/cfddns/releases"
ASSET_PREFIX="cfddns-linux"
RELEASE_TAG="1.0"

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

usage() {
  echo "Usage: sudo ./scripts/install.sh"
}

extract_repo_slug() {
  local url="$1"
  url="${url#https://github.com/}"
  url="${url#http://github.com/}"
  url="${url#github.com/}"
  url="${url%%/releases*}"
  url="${url%%/}"
  printf '%s' "$url"
}

resolve_download_url() {
  local repo_slug="$1"
  local asset_name="$2"
  local release_tag="$3"
  local api_url
  local json_file
  local download_url

  if [ "$release_tag" = "latest" ]; then
    api_url="https://api.github.com/repos/${repo_slug}/releases/latest"
  else
    api_url="https://api.github.com/repos/${repo_slug}/releases/tags/${release_tag}"
  fi

  json_file="$(mktemp)"
  curl -fsSL "$api_url" -o "$json_file"

  download_url="$(python3 - "$json_file" "$asset_name" <<'PY'
import json
import sys

json_file = sys.argv[1]
asset_name = sys.argv[2]

with open(json_file, "r", encoding="utf-8") as fh:
    payload = json.load(fh)

for asset in payload.get("assets", []):
    if asset.get("name") == asset_name:
        print(asset.get("browser_download_url", ""))
        raise SystemExit(0)

print("")
PY
)"

  rm -f "$json_file"
  printf '%s' "$download_url"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root."
  usage
  exit 1
fi

if [ -z "$RELEASES_PAGE_URL" ] || printf '%s' "$RELEASES_PAGE_URL" | grep -q 'your-user/cfddns'; then
  echo "Please set RELEASES_PAGE_URL in scripts/install.sh to your real GitHub releases page."
  usage
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not installed."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not installed."
  exit 1
fi

REPO_SLUG="$(extract_repo_slug "$RELEASES_PAGE_URL")"
if ! printf '%s' "$REPO_SLUG" | grep -Eq '^[^/]+/[^/]+$'; then
  echo "Invalid GitHub releases page URL: $RELEASES_PAGE_URL"
  exit 1
fi

ARCH="$(detect_arch)"
ASSET_NAME="${ASSET_PREFIX}-${ARCH}"
DOWNLOAD_URL="$(resolve_download_url "$REPO_SLUG" "$ASSET_NAME" "$RELEASE_TAG")"
if [ -z "$DOWNLOAD_URL" ]; then
  echo "Could not find asset '$ASSET_NAME' in release '$RELEASE_TAG' for $REPO_SLUG"
  echo "Ensure your release includes architecture assets, e.g. ${ASSET_PREFIX}-amd64 and ${ASSET_PREFIX}-arm64"
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR"

curl -fL "$DOWNLOAD_URL" -o "$BINARY_PATH"
chmod 0755 "$BINARY_PATH"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

mkdir -p "$SYSTEM_CONFIG_DIR"
chown -R "$APP_USER:$APP_GROUP" "$SYSTEM_CONFIG_DIR"

if [ ! -f "$ENV_FILE" ]; then
  umask 077
  SECRET_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
  cat > "$ENV_FILE" <<EOF
CFDDNS_SECRET_KEY=$SECRET_KEY
CFDDNS_CONFIG_FILE=$SYSTEM_CONFIG_FILE
CFDDNS_HOST=0.0.0.0
CFDDNS_PORT=8080
EOF
  chmod 600 "$ENV_FILE"
fi

if ! grep -q '^CFDDNS_CONFIG_FILE=' "$ENV_FILE"; then
  echo "CFDDNS_CONFIG_FILE=$SYSTEM_CONFIG_FILE" >> "$ENV_FILE"
fi

if ! grep -q '^CFDDNS_HOST=' "$ENV_FILE"; then
  echo "CFDDNS_HOST=0.0.0.0" >> "$ENV_FILE"
fi

if ! grep -q '^CFDDNS_PORT=' "$ENV_FILE"; then
  echo "CFDDNS_PORT=8080" >> "$ENV_FILE"
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Cloudflare DDNS Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$BINARY_PATH
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl --no-pager status "$SERVICE_NAME" || true

echo

echo "Install complete."
echo "Service name: $SERVICE_NAME"
echo "Release source: $RELEASES_PAGE_URL"
echo "Asset: $ASSET_NAME"
echo "Port config: edit CFDDNS_PORT in $ENV_FILE"
echo "View logs: journalctl -u $SERVICE_NAME -f"
echo "Web UI: http://<server-ip>:<CFDDNS_PORT>"
