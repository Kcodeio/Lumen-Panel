#!/usr/bin/env bash
set -Eeuo pipefail

LUMEN_INSTALL_DIR="/opt/lumen"
LUMEN_CONFIG_DIR="/etc/lumen"
LUMEN_LOG_DIR="/var/log/lumen"
LUMEN_USER="lumen"

log() { echo -e "[INFO] $*"; }
err() { echo -e "[ERROR] $*" >&2; exit 1; }

require_root() {
if [[ $EUID -ne 0 ]]; then
err "Run with sudo"
fi
}

install_deps() {
log "Installing dependencies..."
apt update -y
apt install -y curl git python3 python3-venv python3-pip docker.io
systemctl enable --now docker
}

create_user() {
id "$LUMEN_USER" &>/dev/null || useradd -r -m -d "$LUMEN_INSTALL_DIR" "$LUMEN_USER"
usermod -aG docker "$LUMEN_USER"
}

fetch_sources() {
log "Cloning repo..."
rm -rf "$LUMEN_INSTALL_DIR"
git clone https://github.com/Kcodeio/Lumen-Panel "$LUMEN_INSTALL_DIR"
chown -R "$LUMEN_USER:$LUMEN_USER" "$LUMEN_INSTALL_DIR"
}

apply_fixes() {
log "Applying fixes..."

local file="$LUMEN_INSTALL_DIR/backend/app/api/servers.py"

if [[ -f "$file" ]]; then
if grep -q ')-> None:$' "$file"; then
sed -i 's|^) -> None:$|):|' "$file"
log "Fixed Python syntax bug in servers.py"
else
log "No syntax bug detected"
fi
else
log "servers.py not found, skipping fix"
fi
}

setup_env() {
mkdir -p "$LUMEN_CONFIG_DIR"
cat > "$LUMEN_CONFIG_DIR/panel.env" <<EOF
LUMEN_API_KEY=$(openssl rand -hex 32)
LUMEN_PORT=8000
EOF
}

setup_backend() {
log "Setting up backend..."
sudo -u "$LUMEN_USER" python3 -m venv "$LUMEN_INSTALL_DIR/backend/.venv"
sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/backend/.venv/bin/pip" install -r "$LUMEN_INSTALL_DIR/backend/requirements.txt"
}

create_service() {
cat > /etc/systemd/system/lumen.service <<EOF
[Unit]
Description=Lumen Panel
After=network.target

[Service]
User=$LUMEN_USER
WorkingDirectory=$LUMEN_INSTALL_DIR/backend
ExecStart=$LUMEN_INSTALL_DIR/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reexec
systemctl daemon-reload
systemctl enable --now lumen
}

main() {
require_root
install_deps
create_user
fetch_sources
apply_fixes   # 🔥 KRİTİK SATIR
setup_env
setup_backend
create_service

log "Done!"
log "Panel: http://SERVER_IP:8000"
}

main
