#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="cfddns"
APP_USER="cfddns"
APP_DIR="/opt/cfddns"
ENV_FILE="/etc/default/cfddns"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SYSTEM_CONFIG_DIR="/usr/share/cfddns"
KEEP_CONFIG="${KEEP_CONFIG:-1}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo ./scripts/uninstall.sh"
  exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
  systemctl disable --now "$SERVICE_NAME" || true
fi

rm -f "$SERVICE_FILE"
systemctl daemon-reload

rm -f "$ENV_FILE"
rm -rf "$APP_DIR"

if [ "$KEEP_CONFIG" = "0" ]; then
  rm -rf "$SYSTEM_CONFIG_DIR"
fi

if id "$APP_USER" >/dev/null 2>&1; then
  userdel "$APP_USER" || true
fi

echo "Uninstall complete."
if [ "$KEEP_CONFIG" = "1" ]; then
  echo "Config preserved at: $SYSTEM_CONFIG_DIR"
else
  echo "Config removed from: $SYSTEM_CONFIG_DIR"
fi
