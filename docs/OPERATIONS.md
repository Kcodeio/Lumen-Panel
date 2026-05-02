# Lumen Panel — Operations Guide

This document covers day-to-day operation of an installed Lumen Panel.

## Service layout

| Service           | Unit name              | Port        | Bind        |
|-------------------|------------------------|-------------|-------------|
| Panel (FastAPI)   | `lumen-panel.service`  | 8000        | `0.0.0.0`   |
| Agent (FastAPI)   | `lumen-agent.service`  | 8081        | `127.0.0.1` |
| Game containers   | (Docker)               | 25565–25600 | `0.0.0.0`   |

The agent is intentionally bound to localhost only — the panel reaches it
through `http://127.0.0.1:8081` and authenticates with `X-Node-Key`.

## File layout

```
/opt/lumen/                 application code (read-only at runtime)
  backend/                  FastAPI panel
  agent/                    node agent
  setup-ui/                 (only present during install)
/etc/lumen/                 configuration
  panel.env                 panel environment file (mode 0640)
  agent.env                 agent environment file (mode 0640)
/var/lib/lumen/             persistent state
  lumen.db                  SQLite database
  servers/<id>/             per-server data volumes (mounted into containers)
/var/log/lumen/             log files
  panel.log
  agent.log
  install.log
```

All paths are owned `root:lumen` (group-readable for the `lumen` system user
that the services run as).

## Common tasks

### Check status

```bash
systemctl status lumen-panel lumen-agent
journalctl -u lumen-panel -f
journalctl -u lumen-agent -f
```

### Restart everything

```bash
sudo systemctl restart lumen-panel lumen-agent
```

### Rotate the JWT secret

Editing the secret invalidates all active sessions — users will have to
log in again.

```bash
sudo sed -i "s/^LUMEN_JWT_SECRET=.*/LUMEN_JWT_SECRET=$(openssl rand -hex 32)/" /etc/lumen/panel.env
sudo systemctl restart lumen-panel
```

### Rotate the node key

Both files must be updated together — the panel and agent compare these
with `hmac.compare_digest`.

```bash
NEW=$(openssl rand -hex 32)
sudo sed -i "s/^LUMEN_NODE_KEY=.*/LUMEN_NODE_KEY=$NEW/" /etc/lumen/panel.env
sudo sed -i "s/^LUMEN_NODE_KEY=.*/LUMEN_NODE_KEY=$NEW/" /etc/lumen/agent.env
sudo systemctl restart lumen-panel lumen-agent
```

### Backup

The only thing you really need to back up is `/var/lib/lumen/` and
`/etc/lumen/`. A simple cron-driven snapshot:

```bash
tar -czf "/backup/lumen-$(date +%F).tar.gz" /var/lib/lumen /etc/lumen
```

Restoring is the inverse — extract over the same paths and
`systemctl restart lumen-panel lumen-agent`.

### Reset the admin password

If you've locked yourself out:

```bash
sudo -u lumen /opt/lumen/backend/venv/bin/python - <<'PY'
from app.core.database import SessionLocal, init_db
from app.core.security import hash_password
from app.models.user import User
init_db()
db = SessionLocal()
u = db.query(User).filter(User.is_admin == True).first()
u.password_hash = hash_password("new-password-here")
db.commit()
print("Updated:", u.username)
PY
```

## Repair mode

If the install is broken (config drift, missing service file, etc.) re-run
the installer with `--repair`:

```bash
sudo bash install.sh --repair
```

Repair mode regenerates systemd units, re-installs Python venvs, and fixes
file permissions. It does **not** touch `/var/lib/lumen/lumen.db` or rotate
secrets.

## Uninstall

```bash
sudo bash install.sh --uninstall
```

This stops services, removes systemd units, and deletes `/opt/lumen`.
By default it preserves `/var/lib/lumen` and `/etc/lumen` — pass
`--purge` if you want those gone too.

## Container security model

Every game server runs in a container with the following hardening:

- Runs as UID/GID `1000:1000` — never root.
- `cap_drop: [ALL]` — no Linux capabilities.
- `security_opt: [no-new-privileges:true]`.
- `pids_limit: 512`.
- Memory and CPU limits enforced by Docker (`mem_limit`, `nano_cpus`).
- Restart policy `unless-stopped`.
- Labelled `com.lumen.managed=1` so unrelated containers are never touched.

The agent only acts on containers carrying that label; manual containers on
the same Docker host are left alone.
