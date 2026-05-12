#!/usr/bin/env bash
# deploy.sh — Deploy ANPR Gate Control to the target VM
set -euo pipefail

TARGET="${1:-ced@192.168.10.10}"
APP_DIR="/home/ced/toctoc-app"
SERVICE="toctoc-anpr"

echo "=== ANPR Gate Control Deploy ==="
echo "Target: $TARGET"
echo "App dir: $APP_DIR"

# Build the package locally
echo "[1/6] Building package..."
cd "$(dirname "$0")/.."
pip install --upgrade pip
pip install build
python -m build --wheel 2>/dev/null

# Copy to target
echo "[2/6] Copying to target..."
scp dist/*.whl "$TARGET:/tmp/toctoc-$(date +%s).whl"

# Install on target
echo "[3/6] Installing on target..."
ssh "$TARGET" "pip install --force-reinstall /tmp/toctoc-*.whl"

# Deploy config
echo "[4/6] Deploying config..."
ssh "$TARGET" "mkdir -p $APP_DIR"
scp portier.yaml "$TARGET:$APP_DIR/" 2>/dev/null || true
scp -r anpr_gate/refs/ "$TARGET:$APP_DIR/" 2>/dev/null || true

# Install systemd service
echo "[5/6] Installing systemd service..."
scp deploy/toctoc.service "$TARGET:/tmp/"
ssh "$TARGET" "
  sudo cp /tmp/toctoc.service /etc/systemd/system/
  sudo sed -i 's|/home/ced/toctoc-improve|$APP_DIR|g' /etc/systemd/system/toctoc.service
  sudo systemctl daemon-reload
  sudo systemctl enable $SERVICE
  sudo systemctl restart $SERVICE
"

# Verify
echo "[6/6] Verifying..."
sleep 3
ssh "$TARGET" "systemctl status $SERVICE --no-pager"

echo ""
echo "=== Deploy complete ==="
echo "Logs: ssh $TARGET 'journalctl -u $SERVICE -f'"