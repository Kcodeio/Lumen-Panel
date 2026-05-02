# Lumen Panel

A self-hosted, single-machine game server management panel — like a much simpler Pterodactyl. Single-command install, runs on Ubuntu/Debian, manages Docker-based game servers from a web dashboard.

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Browser    │─────►│ Lumen Panel  │─────►│ Lumen Agent  │
│  (dashboard) │ HTTP │ (FastAPI)    │ HTTP │ (FastAPI)    │
└──────────────┘      │ :8000        │      │ :8081        │
                      └──────┬───────┘      └──────┬───────┘
                             │                      │
                             ▼                      ▼
                       ┌──────────┐          ┌────────────┐
                       │ SQLite   │          │ Docker     │
                       │ panel.db │          │ daemon     │
                       └──────────┘          └────────────┘
```

- **Installer** (`install.sh`) — bash script, one-shot install + repair + uninstall.
- **Setup UI** — temporary FastAPI on `:8080`, collects admin credentials, dies after submit.
- **Panel** — FastAPI on `:8000`, JWT + API key auth, REST + WebSocket logs, ships with a built-in single-page HTML dashboard.
- **Agent** — FastAPI on `:8081` (localhost only), wraps the Docker socket.
- **Servers** — each game server is one Docker container, non-root, capability-dropped, memory- and CPU-limited.

## Install

```bash
curl -fsSL https://github.com/Kcodeio/lumen-panel/install.sh | sudo bash
```

Or from a local checkout:

```bash
sudo bash install.sh --source=$(pwd)
```

The installer will:

1. Check you're on Ubuntu/Debian and running as root.
2. Check ports `80, 443, 8080, 8000, 8081` are free (or warn in repair mode).
3. Install Docker + Python + UFW.
4. Create `lumen` system user, lay down `/opt/lumen`, `/etc/lumen`, `/var/lib/lumen`, `/var/log/lumen`.
5. Generate JWT/API/Node secrets.
6. Spin up the setup wizard on `:8080`. Open the URL it prints.
7. After you submit the form, install systemd units and start `lumen-panel` + `lumen-agent`.
8. Optionally seed a default Minecraft server.

## Languages

The installer asks for English or Turkish. Translations live in `installer/i18n/{en,tr}.sh`.

## Repair mode

```bash
sudo bash install.sh --repair
```

Skips the "ports already in use" check and reuses an existing install dir.

## Uninstall

```bash
sudo bash install.sh --uninstall
```

Stops services, removes systemd units, deletes `/opt/lumen`, `/etc/lumen`, `/var/lib/lumen`, drops the `lumen` user, and force-removes any lumen-managed Docker containers. Logs in `/var/log/lumen` are preserved.

## Daily ops

```bash
systemctl status lumen-panel
systemctl status lumen-agent
journalctl -u lumen-panel -f
tail -f /var/log/lumen/panel.log
```

Admin credentials are saved at `/etc/lumen/admin.txt` (mode 0600).
The shared API key is in `/etc/lumen/panel.env` as `LUMEN_API_KEY`.

## API quickstart

```bash
# Login and get a JWT
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"…"}'

# Or use the static API key
curl -s http://localhost:8000/api/v1/servers \
  -H "X-Api-Key: $(grep LUMEN_API_KEY /etc/lumen/panel.env | cut -d= -f2)"

# Create a server
curl -s -X POST http://localhost:8000/api/v1/servers \
  -H "X-Api-Key: …" \
  -H 'Content-Type: application/json' \
  -d '{"name":"MC","image":"itzg/minecraft-server","memory_mb":1024,"env":{"EULA":"TRUE","TYPE":"PAPER"}}'
```

OpenAPI docs: `http://your-host:8000/docs`

## Security model

- **Panel ↔ Agent**: The agent listens only on `127.0.0.1` and requires `X-Node-Key` on every call. The key is generated at install time and shared via `/etc/lumen/{panel,agent}.env`.
- **User ↔ Panel**: JWT (HS256) for the dashboard, optional `X-Api-Key` for headless clients.
- **Containers**: dropped capabilities, `no-new-privileges`, non-root UID, mem/CPU/PID limits, port-mapped only into the configured game-port range.
- **Service hardening**: `NoNewPrivileges`, `ProtectSystem=full`, `ProtectHome=yes` on the systemd units.
- **Firewall**: UFW is enabled and only the necessary ports are opened.

## File layout

```
/opt/lumen/                 # source code + venvs
/etc/lumen/
  panel.env                 # backend secrets
  agent.env                 # agent secrets
  admin.txt                 # generated admin creds (0600)
/var/lib/lumen/
  db/panel.db               # SQLite
  servers/<uuid>/           # per-server data volume mount
/var/log/lumen/
  install.log
  panel.log
  agent.log
```
