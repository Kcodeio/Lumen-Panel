#!/usr/bin/env bash
#
# Lumen Panel - One-command installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Kcodeio/Lumen-Panel/main/install.sh | sudo bash
#   sudo bash install.sh
#   sudo bash install.sh --repair
#   sudo bash install.sh --uninstall
#
set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
LUMEN_VERSION="1.0.0"
LUMEN_REPO_URL="${LUMEN_REPO_URL:-https://github.com/Kcodeio/Lumen-Panel}"
LUMEN_INSTALL_DIR="/opt/lumen"
LUMEN_CONFIG_DIR="/etc/lumen"
LUMEN_LOG_DIR="/var/log/lumen"
LUMEN_DATA_DIR="/var/lib/lumen"
LUMEN_USER="lumen"
LUMEN_PORT_PANEL="8000"
LUMEN_PORT_AGENT="8081"
LUMEN_PORT_SETUP="8080"
LUMEN_GAME_PORT_START="25565"
LUMEN_GAME_PORT_END="25600"

LANG_CHOICE="en"
REPAIR_MODE=0
UNINSTALL_MODE=0
NONINTERACTIVE=0
SOURCE_DIR=""

# Color codes
C_RESET='\033[0m'
C_RED='\033[0;31m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_BLUE='\033[0;34m'
C_CYAN='\033[0;36m'
C_BOLD='\033[1m'

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info()  { echo -e "${C_BLUE}[INFO]${C_RESET}  $*"; }
log_ok()    { echo -e "${C_GREEN}[ OK ]${C_RESET}  $*"; }
log_warn()  { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
log_err()   { echo -e "${C_RED}[FAIL]${C_RESET}  $*" >&2; }
log_step()  { echo -e "\n${C_CYAN}${C_BOLD}>>> $*${C_RESET}"; }

trap 'log_err "Installation failed at line $LINENO. Check ${LUMEN_LOG_DIR}/install.log"' ERR

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------
declare -A T

load_translations() {
    local lang="$1"
    local i18n_file=""

    if [[ -n "$SOURCE_DIR" && -f "$SOURCE_DIR/installer/i18n/${lang}.sh" ]]; then
        i18n_file="$SOURCE_DIR/installer/i18n/${lang}.sh"
    elif [[ -f "./installer/i18n/${lang}.sh" ]]; then
        i18n_file="./installer/i18n/${lang}.sh"
    elif [[ -f "/tmp/lumen-installer/installer/i18n/${lang}.sh" ]]; then
        i18n_file="/tmp/lumen-installer/installer/i18n/${lang}.sh"
    fi

    if [[ -n "$i18n_file" ]]; then
        # shellcheck disable=SC1090
        source "$i18n_file"
    else
        # Inline fallback to English
        T[welcome]="Welcome to Lumen Panel installer"
        T[choose_language]="Choose your language"
        T[english]="English"
        T[turkish]="Türkçe"
        T[checking_root]="Checking root privileges"
        T[need_root]="This installer must be run as root (sudo)"
        T[checking_os]="Checking operating system"
        T[unsupported_os]="Unsupported operating system. Only Ubuntu/Debian are supported."
        T[checking_ports]="Checking required ports"
        T[port_in_use]="Port %s is already in use"
        T[installing_deps]="Installing system dependencies"
        T[installing_docker]="Installing Docker"
        T[docker_already]="Docker is already installed"
        T[creating_user]="Creating system user"
        T[setting_up_dirs]="Setting up directories"
        T[generating_keys]="Generating secure secrets"
        T[starting_setup]="Starting temporary setup web server"
        T[setup_url]="Open this URL in your browser to finish setup"
        T[waiting_setup]="Waiting for you to complete the setup form"
        T[setup_done]="Setup form completed"
        T[installing_panel]="Installing panel backend"
        T[installing_agent]="Installing node agent"
        T[creating_services]="Creating systemd services"
        T[starting_services]="Starting services"
        T[finalizing]="Finalizing installation"
        T[install_complete]="Installation complete!"
        T[panel_url]="Panel URL"
        T[admin_email]="Admin email"
        T[admin_password]="Admin password"
        T[repair_mode]="Repair mode enabled"
        T[uninstalling]="Uninstalling Lumen Panel"
        T[firewall_config]="Configuring firewall"
    fi
}

t() {
    local key="$1"; shift || true
    local val="${T[$key]:-$key}"
    if [[ $# -gt 0 ]]; then
        # shellcheck disable=SC2059
        printf "$val" "$@"
    else
        printf "%s" "$val"
    fi
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repair)         REPAIR_MODE=1 ;;
            --uninstall)      UNINSTALL_MODE=1 ;;
            --noninteractive) NONINTERACTIVE=1 ;;
            --lang=*)         LANG_CHOICE="${1#*=}" ;;
            --source=*)       SOURCE_DIR="${1#*=}" ;;
            --help|-h)
                cat <<EOF
Lumen Panel installer v${LUMEN_VERSION}

Usage: sudo bash install.sh [options]

Options:
  --repair            Repair an existing installation
  --uninstall         Remove Lumen Panel from this system
  --noninteractive    Skip interactive prompts (use defaults)
  --lang=en|tr        Select interface language
  --source=DIR        Use local source directory instead of cloning
  --help              Show this help message
EOF
                exit 0
                ;;
            *)
                log_warn "Unknown argument: $1"
                ;;
        esac
        shift
    done
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
require_root() {
    log_step "$(t checking_root)"
    if [[ $EUID -ne 0 ]]; then
        log_err "$(t need_root)"
        exit 1
    fi
    log_ok "Running as root"
}

detect_os() {
    log_step "$(t checking_os)"
    if [[ ! -f /etc/os-release ]]; then
        log_err "$(t unsupported_os)"
        exit 1
    fi
    # shellcheck disable=SC1091
    source /etc/os-release
    case "$ID" in
        ubuntu|debian)
            log_ok "Detected: $PRETTY_NAME"
            ;;
        *)
            if [[ "${ID_LIKE:-}" == *"debian"* ]]; then
                log_ok "Detected Debian-like: $PRETTY_NAME"
            else
                log_err "$(t unsupported_os) (got: $ID)"
                exit 1
            fi
            ;;
    esac
}

check_ports() {
    log_step "$(t checking_ports)"
    local ports=("$LUMEN_PORT_SETUP" "$LUMEN_PORT_PANEL" "$LUMEN_PORT_AGENT")
    for p in "${ports[@]}"; do
        if ss -ltn "sport = :$p" 2>/dev/null | grep -q LISTEN; then
            if [[ $REPAIR_MODE -eq 1 ]]; then
                log_warn "Port $p in use (continuing in repair mode)"
            else
                log_err "$(t port_in_use "$p")"
                log_err "Free the port or use --repair to ignore"
                exit 1
            fi
        else
            log_ok "Port $p is free"
        fi
    done
}

detect_existing_install() {
    if [[ -d "$LUMEN_INSTALL_DIR" || -f "$LUMEN_CONFIG_DIR/panel.env" ]]; then
        if [[ $UNINSTALL_MODE -eq 1 ]]; then
            return 0
        fi
        if [[ $REPAIR_MODE -eq 0 ]]; then
            log_warn "Existing Lumen installation detected at $LUMEN_INSTALL_DIR"
            log_warn "Switching to REPAIR MODE automatically"
            REPAIR_MODE=1
        fi
        log_info "$(t repair_mode)"
    fi
}

# ---------------------------------------------------------------------------
# Language selection
# ---------------------------------------------------------------------------
prompt_language() {
    if [[ $NONINTERACTIVE -eq 1 ]]; then
        load_translations "$LANG_CHOICE"
        return
    fi
    echo
    echo -e "${C_BOLD}=========================================${C_RESET}"
    echo -e "${C_BOLD}        Lumen Panel Installer            ${C_RESET}"
    echo -e "${C_BOLD}=========================================${C_RESET}"
    echo
    echo "Select language / Dil seçin:"
    echo "  1) English"
    echo "  2) Türkçe"
    local choice
    read -r -p "[1-2] (default: 1): " choice </dev/tty || choice="1"
    case "$choice" in
        2) LANG_CHOICE="tr" ;;
        *) LANG_CHOICE="en" ;;
    esac
    load_translations "$LANG_CHOICE"
    log_ok "Language: $LANG_CHOICE"
}

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
install_dependencies() {
    log_step "$(t installing_deps)"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
        curl wget ca-certificates gnupg lsb-release \
        python3 python3-venv python3-pip \
        git ufw jq net-tools openssl \
        sqlite3 \
        software-properties-common \
        >/dev/null
    log_ok "System packages installed"
}

install_docker() {
    if command -v docker >/dev/null 2>&1; then
        log_ok "$(t docker_already)"
        return
    fi
    log_step "$(t installing_docker)"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/$(. /etc/os-release; echo "$ID")/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/$(. /etc/os-release; echo "$ID") \
$(. /etc/os-release; echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin >/dev/null
    systemctl enable --now docker
    log_ok "Docker installed"
}

configure_firewall() {
    log_step "$(t firewall_config)"
    if ! command -v ufw >/dev/null 2>&1; then
        log_warn "ufw not available, skipping firewall config"
        return
    fi
    ufw --force enable >/dev/null 2>&1 || true
    ufw allow 22/tcp >/dev/null
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw allow "$LUMEN_PORT_SETUP/tcp" >/dev/null
    ufw allow "$LUMEN_PORT_PANEL/tcp" >/dev/null
    ufw allow "${LUMEN_GAME_PORT_START}:${LUMEN_GAME_PORT_END}/tcp" >/dev/null
    ufw allow "${LUMEN_GAME_PORT_START}:${LUMEN_GAME_PORT_END}/udp" >/dev/null
    log_ok "Firewall rules applied"
}

# ---------------------------------------------------------------------------
# User & directories
# ---------------------------------------------------------------------------
create_user() {
    log_step "$(t creating_user)"
    if id "$LUMEN_USER" &>/dev/null; then
        log_ok "User $LUMEN_USER already exists"
    else
        useradd --system --home "$LUMEN_INSTALL_DIR" --shell /usr/sbin/nologin "$LUMEN_USER"
        log_ok "Created user $LUMEN_USER"
    fi
    if getent group docker >/dev/null; then
        usermod -aG docker "$LUMEN_USER"
        log_ok "Added $LUMEN_USER to docker group"
    fi
}

setup_directories() {
    log_step "$(t setting_up_dirs)"
    mkdir -p "$LUMEN_INSTALL_DIR" "$LUMEN_CONFIG_DIR" "$LUMEN_LOG_DIR" "$LUMEN_DATA_DIR"
    mkdir -p "$LUMEN_DATA_DIR/servers" "$LUMEN_DATA_DIR/db"
    chown -R "$LUMEN_USER:$LUMEN_USER" "$LUMEN_INSTALL_DIR" "$LUMEN_LOG_DIR" "$LUMEN_DATA_DIR"
    chown root:"$LUMEN_USER" "$LUMEN_CONFIG_DIR"
    # 0770 during install so the setup wizard (running as lumen) can create
    # admin.txt and rewrite env files. Tightened to 0750 in install_services()
    # once the wizard finishes.
    chmod 770 "$LUMEN_CONFIG_DIR"
    log_ok "Directories ready"
}

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
fetch_sources() {
    log_step "Fetching sources"
    if [[ -n "$SOURCE_DIR" && -d "$SOURCE_DIR" ]]; then
        log_info "Using local source: $SOURCE_DIR"
        cp -r "$SOURCE_DIR/." "$LUMEN_INSTALL_DIR/"
    elif [[ -d "/tmp/lumen-installer" ]]; then
        log_info "Using bundled source from /tmp/lumen-installer"
        cp -r /tmp/lumen-installer/. "$LUMEN_INSTALL_DIR/"
    else
        log_info "Cloning from $LUMEN_REPO_URL"
        # Mark as a safe directory so re-running as root after a previous install doesn't trip git
        git config --global --add safe.directory "$LUMEN_INSTALL_DIR" || true
        if [[ -d "$LUMEN_INSTALL_DIR/.git" ]]; then
            (cd "$LUMEN_INSTALL_DIR" && git pull --quiet)
        else
            # Make sure target dir is empty before cloning
            rm -rf "$LUMEN_INSTALL_DIR"
            git clone --quiet "$LUMEN_REPO_URL" "$LUMEN_INSTALL_DIR"
        fi
    fi
    chown -R "$LUMEN_USER:$LUMEN_USER" "$LUMEN_INSTALL_DIR"
    log_ok "Sources in place"
}

# ---------------------------------------------------------------------------
# Secrets and config
# ---------------------------------------------------------------------------
generate_secrets() {
    log_step "$(t generating_keys)"

    # In repair mode, keep existing secrets so existing JWTs/sessions stay valid
    if [[ $REPAIR_MODE -eq 1 && -f "$LUMEN_CONFIG_DIR/panel.env" ]]; then
        log_info "Keeping existing secrets (repair mode)"
        # Make writable for setup-UI again
        chown root:"$LUMEN_USER" "$LUMEN_CONFIG_DIR/panel.env" "$LUMEN_CONFIG_DIR/agent.env"
        chmod 660 "$LUMEN_CONFIG_DIR/panel.env" "$LUMEN_CONFIG_DIR/agent.env"
        # Make sure the dir is writable for the wizard during repair too
        chmod 770 "$LUMEN_CONFIG_DIR"
        log_ok "Existing secrets reused"
        return
    fi

    local jwt_secret api_key node_key
    jwt_secret=$(openssl rand -hex 48)
    api_key=$(openssl rand -hex 32)
    node_key=$(openssl rand -hex 32)
    cat > "$LUMEN_CONFIG_DIR/panel.env" <<EOF
# Auto-generated. Do NOT commit.
LUMEN_JWT_SECRET=${jwt_secret}
LUMEN_API_KEY=${api_key}
LUMEN_NODE_KEY=${node_key}
LUMEN_DATABASE_URL=sqlite:///${LUMEN_DATA_DIR}/db/panel.db
LUMEN_DATA_DIR=${LUMEN_DATA_DIR}
LUMEN_LOG_DIR=${LUMEN_LOG_DIR}
LUMEN_PORT=${LUMEN_PORT_PANEL}
LUMEN_AGENT_URL=http://127.0.0.1:${LUMEN_PORT_AGENT}
LUMEN_GAME_PORT_START=${LUMEN_GAME_PORT_START}
LUMEN_GAME_PORT_END=${LUMEN_GAME_PORT_END}
EOF
    cat > "$LUMEN_CONFIG_DIR/agent.env" <<EOF
LUMEN_NODE_KEY=${node_key}
LUMEN_AGENT_PORT=${LUMEN_PORT_AGENT}
LUMEN_PANEL_URL=http://127.0.0.1:${LUMEN_PORT_PANEL}
LUMEN_DATA_DIR=${LUMEN_DATA_DIR}
LUMEN_LOG_DIR=${LUMEN_LOG_DIR}
EOF
    # 0660 (rw for root + lumen group) so the setup wizard, which runs as
    # the lumen user, can rewrite this file with admin email/timezone/etc.
    # Permissions are tightened back to 0640 in install_services() once
    # the wizard has finished.
    chown root:"$LUMEN_USER" "$LUMEN_CONFIG_DIR/panel.env" "$LUMEN_CONFIG_DIR/agent.env"
    chmod 660 "$LUMEN_CONFIG_DIR/panel.env" "$LUMEN_CONFIG_DIR/agent.env"
    log_ok "Secrets generated"
}

# ---------------------------------------------------------------------------
# Auto IP/port allocation
# ---------------------------------------------------------------------------
detect_server_ip() {
    local ip
    ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [[ -z "$ip" ]]; then
        ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "127.0.0.1")
    fi
    echo "$ip"
}

# ---------------------------------------------------------------------------
# Python virtualenvs
# ---------------------------------------------------------------------------
build_venvs() {
    log_step "Setting up Python environments"

    sudo -u "$LUMEN_USER" python3 -m venv "$LUMEN_INSTALL_DIR/backend/.venv"
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/backend/.venv/bin/pip" install --quiet --upgrade pip
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/backend/.venv/bin/pip" install --quiet \
        -r "$LUMEN_INSTALL_DIR/backend/requirements.txt"

    sudo -u "$LUMEN_USER" python3 -m venv "$LUMEN_INSTALL_DIR/agent/.venv"
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/agent/.venv/bin/pip" install --quiet --upgrade pip
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/agent/.venv/bin/pip" install --quiet \
        -r "$LUMEN_INSTALL_DIR/agent/requirements.txt"

    sudo -u "$LUMEN_USER" python3 -m venv "$LUMEN_INSTALL_DIR/setup-ui/.venv"
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/setup-ui/.venv/bin/pip" install --quiet --upgrade pip
    sudo -u "$LUMEN_USER" "$LUMEN_INSTALL_DIR/setup-ui/.venv/bin/pip" install --quiet \
        -r "$LUMEN_INSTALL_DIR/setup-ui/requirements.txt"

    log_ok "Python envs ready"
}

# ---------------------------------------------------------------------------
# Setup wizard
# ---------------------------------------------------------------------------
run_setup_wizard() {
    # In repair mode, if setup already ran successfully, skip the wizard
    if [[ $REPAIR_MODE -eq 1 && -f "$LUMEN_DATA_DIR/.setup-complete" ]]; then
        log_step "$(t starting_setup)"
        log_ok "Setup already completed, skipping wizard"
        return
    fi

    log_step "$(t starting_setup)"
    local server_ip
    server_ip=$(detect_server_ip)

    export LUMEN_INSTALL_DIR LUMEN_CONFIG_DIR LUMEN_DATA_DIR LUMEN_LOG_DIR
    export LUMEN_PORT_SETUP LUMEN_DEFAULT_DOMAIN="$server_ip"

    local setup_log="$LUMEN_LOG_DIR/setup-wizard.log"
    : >"$setup_log"

    sudo -u "$LUMEN_USER" \
        env LUMEN_INSTALL_DIR="$LUMEN_INSTALL_DIR" \
            LUMEN_CONFIG_DIR="$LUMEN_CONFIG_DIR" \
            LUMEN_DATA_DIR="$LUMEN_DATA_DIR" \
            LUMEN_PORT_SETUP="$LUMEN_PORT_SETUP" \
            LUMEN_DEFAULT_DOMAIN="$server_ip" \
        "$LUMEN_INSTALL_DIR/setup-ui/.venv/bin/python" \
        "$LUMEN_INSTALL_DIR/setup-ui/server.py" \
        >>"$setup_log" 2>&1 &

    local setup_pid=$!

    local tries=0
    until curl -fsS "http://127.0.0.1:${LUMEN_PORT_SETUP}/health" >/dev/null 2>&1; do
        sleep 1
        tries=$((tries+1))
        if [[ $tries -ge 30 ]]; then
            log_err "Setup server failed to start. See $setup_log"
            exit 1
        fi
    done

    echo
    echo -e "${C_BOLD}${C_GREEN}========================================================${C_RESET}"
    echo -e "${C_BOLD}$(t setup_url):${C_RESET}"
    echo -e "    ${C_CYAN}http://${server_ip}:${LUMEN_PORT_SETUP}${C_RESET}"
    echo -e "    ${C_CYAN}http://127.0.0.1:${LUMEN_PORT_SETUP}${C_RESET}"
    echo -e "${C_BOLD}${C_GREEN}========================================================${C_RESET}"
    echo
    log_info "$(t waiting_setup)"

    local marker="$LUMEN_DATA_DIR/.setup-complete"
    while [[ ! -f "$marker" ]]; do
        if ! kill -0 "$setup_pid" 2>/dev/null; then
            log_err "Setup server died unexpectedly"
            tail -n 30 "$setup_log" >&2
            exit 1
        fi
        sleep 2
    done

    log_ok "$(t setup_done)"

    kill "$setup_pid" 2>/dev/null || true
    sleep 1
    kill -9 "$setup_pid" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# systemd services
# ---------------------------------------------------------------------------
install_services() {
    log_step "$(t creating_services)"

    cat > /etc/systemd/system/lumen-panel.service <<EOF
[Unit]
Description=Lumen Panel Backend
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${LUMEN_USER}
Group=${LUMEN_USER}
EnvironmentFile=${LUMEN_CONFIG_DIR}/panel.env
WorkingDirectory=${LUMEN_INSTALL_DIR}/backend
ExecStart=${LUMEN_INSTALL_DIR}/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${LUMEN_PORT_PANEL}
Restart=on-failure
RestartSec=5
StandardOutput=append:${LUMEN_LOG_DIR}/panel.log
StandardError=append:${LUMEN_LOG_DIR}/panel.log
NoNewPrivileges=yes
ProtectSystem=full
ProtectHome=yes

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/lumen-agent.service <<EOF
[Unit]
Description=Lumen Node Agent
After=network-online.target docker.service lumen-panel.service
Wants=network-online.target

[Service]
Type=simple
User=${LUMEN_USER}
Group=${LUMEN_USER}
SupplementaryGroups=docker
EnvironmentFile=${LUMEN_CONFIG_DIR}/agent.env
WorkingDirectory=${LUMEN_INSTALL_DIR}/agent
ExecStart=${LUMEN_INSTALL_DIR}/agent/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${LUMEN_PORT_AGENT}
Restart=on-failure
RestartSec=5
StandardOutput=append:${LUMEN_LOG_DIR}/agent.log
StandardError=append:${LUMEN_LOG_DIR}/agent.log
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload

    # Setup wizard is done — tighten permissions on all config files and the dir
    if [[ -f "$LUMEN_CONFIG_DIR/panel.env" ]]; then
        chmod 640 "$LUMEN_CONFIG_DIR/panel.env"
    fi
    if [[ -f "$LUMEN_CONFIG_DIR/agent.env" ]]; then
        chmod 640 "$LUMEN_CONFIG_DIR/agent.env"
    fi
    if [[ -f "$LUMEN_CONFIG_DIR/admin.txt" ]]; then
        chown root:"$LUMEN_USER" "$LUMEN_CONFIG_DIR/admin.txt"
        chmod 640 "$LUMEN_CONFIG_DIR/admin.txt"
    fi
    chmod 750 "$LUMEN_CONFIG_DIR"

    log_ok "Services installed"
}

start_services() {
    log_step "$(t starting_services)"
    systemctl enable --now lumen-panel.service
    sleep 3
    systemctl enable --now lumen-agent.service
    sleep 2

    if ! systemctl is-active --quiet lumen-panel.service; then
        log_err "lumen-panel failed to start"
        journalctl -u lumen-panel --no-pager -n 30 >&2 || true
        exit 1
    fi
    if ! systemctl is-active --quiet lumen-agent.service; then
        log_err "lumen-agent failed to start"
        journalctl -u lumen-agent --no-pager -n 30 >&2 || true
        exit 1
    fi
    log_ok "Services running"
}

# ---------------------------------------------------------------------------
# Default Minecraft seed
# ---------------------------------------------------------------------------
seed_default_server() {
    if [[ ! -f "$LUMEN_DATA_DIR/.create-default-mc" ]]; then
        return
    fi
    log_step "Creating default Minecraft server"
    local api_key
    api_key=$(grep '^LUMEN_API_KEY=' "$LUMEN_CONFIG_DIR/panel.env" | cut -d= -f2)
    sleep 5
    curl -fsS -X POST "http://127.0.0.1:${LUMEN_PORT_PANEL}/api/v1/servers" \
        -H "Content-Type: application/json" \
        -H "X-Api-Key: ${api_key}" \
        -d '{"name":"Default Minecraft","image":"itzg/minecraft-server","memory_mb":1024,"env":{"EULA":"TRUE","TYPE":"VANILLA"}}' \
        >/dev/null || log_warn "Default server creation skipped (panel not ready yet)"
    log_ok "Default Minecraft server created"
}

# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
print_summary() {
    local ip api_key
    ip=$(detect_server_ip)
    api_key=$(grep '^LUMEN_API_KEY=' "$LUMEN_CONFIG_DIR/panel.env" | cut -d= -f2)
    echo
    echo -e "${C_GREEN}${C_BOLD}========================================================${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}  $(t install_complete)${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}========================================================${C_RESET}"
    echo
    echo -e "  $(t panel_url):  ${C_CYAN}http://${ip}:${LUMEN_PORT_PANEL}${C_RESET}"
    echo -e "  Setup credentials: see ${C_CYAN}${LUMEN_CONFIG_DIR}/admin.txt${C_RESET}"
    echo -e "  API key:          ${C_YELLOW}${api_key}${C_RESET}"
    echo -e "  Logs:             ${LUMEN_LOG_DIR}"
    echo -e "  Game ports:       ${LUMEN_GAME_PORT_START}-${LUMEN_GAME_PORT_END}"
    echo
    echo -e "  Manage services:"
    echo -e "    systemctl status lumen-panel"
    echo -e "    systemctl status lumen-agent"
    echo
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
uninstall() {
    load_translations "$LANG_CHOICE"
    log_step "$(t uninstalling)"
    systemctl stop lumen-agent lumen-panel 2>/dev/null || true
    systemctl disable lumen-agent lumen-panel 2>/dev/null || true
    rm -f /etc/systemd/system/lumen-panel.service /etc/systemd/system/lumen-agent.service
    systemctl daemon-reload
    if command -v docker >/dev/null 2>&1; then
        docker ps -a --filter "label=com.lumen.managed=1" --format '{{.ID}}' \
            | xargs -r docker rm -f >/dev/null 2>&1 || true
    fi
    rm -rf "$LUMEN_INSTALL_DIR" "$LUMEN_CONFIG_DIR" "$LUMEN_DATA_DIR"
    if id "$LUMEN_USER" &>/dev/null; then
        userdel -r "$LUMEN_USER" 2>/dev/null || userdel "$LUMEN_USER" 2>/dev/null || true
    fi
    log_ok "Lumen Panel removed (logs preserved at $LUMEN_LOG_DIR)"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"
    mkdir -p "$LUMEN_LOG_DIR"
    exec > >(tee -a "$LUMEN_LOG_DIR/install.log") 2>&1

    if [[ $UNINSTALL_MODE -eq 1 ]]; then
        require_root
        uninstall
        exit 0
    fi

    prompt_language
    require_root
    detect_os
    detect_existing_install
    check_ports
    install_dependencies
    install_docker
    create_user
    setup_directories
    fetch_sources
    generate_secrets
    configure_firewall
    build_venvs
    run_setup_wizard
    install_services
    start_services
    seed_default_server
    print_summary
}

main "$@"
