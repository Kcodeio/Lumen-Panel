# Lumen Panel — HTTP API Reference

Base URL: `http://<panel-host>:8000/api/v1`

All endpoints except `/auth/login` and the agent-only routes require either:

- `Authorization: Bearer <jwt>` (from `POST /auth/login`), or
- `X-Api-Key: <key>` (per-user API key, generated in the dashboard).

Agent → panel routes additionally require `X-Node-Key`. They are not part
of the public API and shouldn't be called by clients.

## Auth

### `POST /auth/login`

Request:
```json
{ "username": "admin", "password": "..." }
```

Response:
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

Errors:
- `401` — wrong credentials.
- `429` — too many failed attempts (per-IP rate limit, 10/min).

### `GET /auth/me`

Returns the current user. Useful for verifying a token.

```json
{
  "id": 1,
  "username": "admin",
  "email": "admin@example.com",
  "is_admin": true,
  "created_at": "2026-05-02T10:00:00Z"
}
```

## Servers

### `GET /servers`

List servers visible to the current user. Admins see everything.

### `POST /servers`

Create a new server.

```json
{
  "name": "Survival",
  "image": "lumen/minecraft:latest",
  "memory_mb": 2048,
  "cpu_limit": 1.0,
  "env": { "EULA": "true", "MEMORY": "2G" }
}
```

A free port is allocated automatically from the configured range
(default `25565–25600`). Returns the created server with `port` set.

### `GET /servers/{id}`

Fetch one server.

### `PATCH /servers/{id}`

Update mutable fields. Only `name`, `memory_mb`, `cpu_limit`, and `env` can
be changed without recreating the container. Changing `image` requires
a stop → start cycle.

### `DELETE /servers/{id}`

Stop the container, remove it, and delete database state. The on-disk
data volume at `/var/lib/lumen/servers/<id>/` is preserved by default.
Add `?purge=true` to also delete the volume.

### `POST /servers/{id}/start`

Start (or create + start) the container. Idempotent.

### `POST /servers/{id}/stop`

Send SIGTERM, wait 30s, SIGKILL. Idempotent.

### `GET /servers/{id}/logs?tail=200`

Returns the last N lines of stdout/stderr from the container.

```json
{ "lines": [ "[INFO] Server started", "..." ] }
```

For live streaming, use the WebSocket below instead.

## WebSockets

### `WS /ws/servers/{id}/logs`

Streams container output line by line as JSON frames:

```json
{ "type": "log", "ts": "2026-05-02T10:00:00Z", "line": "..." }
{ "type": "status", "status": "running" }
{ "type": "error", "error": "container exited" }
```

Authentication: include `?token=<jwt>` in the URL since browsers cannot
attach `Authorization` headers to WebSockets.

## Errors

Errors use the FastAPI default shape:

```json
{ "detail": "Server not found" }
```

| Code | Meaning                                              |
|------|------------------------------------------------------|
| 400  | Validation error (bad payload, port range exhausted) |
| 401  | Missing or invalid credentials                       |
| 403  | Authenticated but not allowed                        |
| 404  | Resource doesn't exist                               |
| 409  | Conflict (e.g. server name already taken)            |
| 502  | Agent unreachable                                    |
| 503  | Docker unavailable on the agent host                 |
