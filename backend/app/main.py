"""FastAPI application entrypoint for the Lumen Panel."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app import __version__
from app.api import api_router
from app.core.config import settings
from app.core.database import init_db


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_file = Path(settings.log_dir) / "panel.app.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("lumen.panel")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Lumen Panel %s starting", __version__)
    yield
    logger.info("Lumen Panel shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Lumen Panel",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": __version__})


# ---------------------------------------------------------------------------
# Built-in dashboard (single-file HTML/JS)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Lumen Panel</title>
<style>
  :root {
    --bg: #0b0d10;
    --panel: #14171c;
    --panel-2: #1b1f26;
    --line: #262b33;
    --text: #e7ecf2;
    --muted: #8b95a5;
    --accent: #f0b429;
    --accent-2: #65d6ad;
    --danger: #ff5d6c;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: radial-gradient(1200px 700px at 80% -10%, #1a1f28 0%, var(--bg) 60%);
    color: var(--text);
    font-family: ui-monospace, "JetBrains Mono", "Fira Code", Consolas, monospace;
    min-height: 100vh;
  }
  header {
    padding: 22px 32px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  header h1 {
    margin: 0;
    font-size: 18px;
    letter-spacing: 4px;
    text-transform: uppercase;
  }
  header h1 span { color: var(--accent); }
  main { padding: 32px; max-width: 1200px; margin: 0 auto; }

  .card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 4px;
    padding: 24px;
    margin-bottom: 24px;
  }
  .card h2 {
    margin: 0 0 16px;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--muted);
  }
  input, select, button {
    background: var(--panel-2);
    color: var(--text);
    border: 1px solid var(--line);
    padding: 10px 12px;
    font: inherit;
    border-radius: 3px;
  }
  input:focus, select:focus { outline: 1px solid var(--accent); }
  button {
    cursor: pointer;
    transition: background 0.15s;
  }
  button:hover { background: var(--line); }
  button.primary {
    background: var(--accent);
    color: #1a1300;
    border-color: var(--accent);
    font-weight: 600;
  }
  button.primary:hover { background: #ffc83a; }
  button.danger { color: var(--danger); border-color: var(--danger); }
  button.success { color: var(--accent-2); border-color: var(--accent-2); }

  .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
  .hidden { display: none !important; }

  table { width: 100%; border-collapse: collapse; }
  th, td {
    padding: 12px 8px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    font-size: 14px;
  }
  th { color: var(--muted); font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 1.5px; }

  .pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }
  .pill.running { background: rgba(101, 214, 173, 0.15); color: var(--accent-2); }
  .pill.stopped { background: rgba(139, 149, 165, 0.15); color: var(--muted); }
  .pill.error   { background: rgba(255, 93, 108, 0.15); color: var(--danger); }
  .pill.created, .pill.starting, .pill.stopping {
    background: rgba(240, 180, 41, 0.15); color: var(--accent);
  }

  pre.logs {
    background: #050608;
    color: #b8c2cc;
    padding: 14px;
    height: 320px;
    overflow: auto;
    font-size: 12px;
    border: 1px solid var(--line);
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
  }
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--panel);
    border-left: 4px solid var(--accent);
    padding: 12px 18px;
    border-radius: 3px;
    box-shadow: 0 6px 20px rgba(0,0,0,0.6);
    max-width: 360px;
    font-size: 13px;
  }
  .toast.error { border-left-color: var(--danger); }
  .toast.ok { border-left-color: var(--accent-2); }
  .muted { color: var(--muted); font-size: 12px; }
</style>
</head>
<body>

<header>
  <h1>LUMEN<span>·</span>PANEL</h1>
  <div id="userBox" class="muted"></div>
</header>

<main>

<!-- LOGIN -->
<section id="loginCard" class="card">
  <h2>Sign in</h2>
  <div class="row">
    <input id="loginEmail" type="email" placeholder="email@example.com" autocomplete="username" />
    <input id="loginPassword" type="password" placeholder="password" autocomplete="current-password" />
    <button class="primary" id="loginBtn">Sign in</button>
  </div>
</section>

<!-- DASHBOARD -->
<section id="dashboard" class="hidden">

  <div class="card">
    <h2>Create a server</h2>
    <div class="grid">
      <input id="csName" placeholder="Server name" />
      <input id="csImage" placeholder="docker image (e.g. itzg/minecraft-server)" />
      <input id="csMemory" type="number" placeholder="Memory MB" value="1024" />
      <input id="csEnv" placeholder='ENV (e.g. EULA=TRUE,TYPE=VANILLA)' />
    </div>
    <div class="row" style="margin-top:14px">
      <button class="primary" id="createBtn">Create server</button>
      <span class="muted">Comma-separated KEY=value pairs. Type valid Docker image names only.</span>
    </div>
  </div>

  <div class="card">
    <h2>Servers</h2>
    <table id="serverTable">
      <thead>
        <tr>
          <th>#</th><th>Name</th><th>Image</th><th>Port</th><th>Status</th><th>Actions</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="card hidden" id="logsCard">
    <h2>Logs <span class="muted" id="logsTitle"></span></h2>
    <pre class="logs" id="logsBox"></pre>
    <div class="row" style="margin-top:12px">
      <button id="closeLogs">Close</button>
    </div>
  </div>

</section>

<div id="toastSlot"></div>

<script>
const API = "/api/v1";
let token = localStorage.getItem("lumen_token") || null;
let currentUser = null;
let logsSocket = null;

function toast(msg, kind) {
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = msg;
  document.getElementById("toastSlot").appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

async function api(path, opts) {
  opts = opts || {};
  opts.headers = Object.assign({"Content-Type": "application/json"}, opts.headers || {});
  if (token) opts.headers["Authorization"] = "Bearer " + token;
  const res = await fetch(API + path, opts);
  if (res.status === 401) {
    logout();
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    let detail;
    try { detail = (await res.json()).detail; } catch { detail = res.statusText; }
    throw new Error(detail || ("HTTP " + res.status));
  }
  if (res.status === 204) return null;
  return res.json();
}

function logout() {
  token = null;
  currentUser = null;
  localStorage.removeItem("lumen_token");
  document.getElementById("loginCard").classList.remove("hidden");
  document.getElementById("dashboard").classList.add("hidden");
  document.getElementById("userBox").textContent = "";
}

async function loginFlow() {
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  if (!email || !password) { toast("Email and password required", "error"); return; }
  try {
    const data = await api("/auth/login", {method: "POST", body: JSON.stringify({email, password})});
    token = data.access_token;
    currentUser = data.user;
    localStorage.setItem("lumen_token", token);
    document.getElementById("loginCard").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");
    document.getElementById("userBox").textContent = currentUser.email + (currentUser.is_admin ? " · admin" : "");
    await refreshServers();
    toast("Welcome", "ok");
  } catch (e) {
    toast(e.message, "error");
  }
}

async function tryRestoreSession() {
  if (!token) return false;
  try {
    currentUser = await api("/auth/me");
    document.getElementById("loginCard").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");
    document.getElementById("userBox").textContent = currentUser.email + (currentUser.is_admin ? " · admin" : "");
    await refreshServers();
    return true;
  } catch {
    logout();
    return false;
  }
}

function parseEnv(raw) {
  const out = {};
  if (!raw) return out;
  raw.split(",").forEach(part => {
    const eq = part.indexOf("=");
    if (eq > 0) {
      const k = part.slice(0, eq).trim();
      const v = part.slice(eq + 1).trim();
      if (k) out[k] = v;
    }
  });
  return out;
}

async function createServer() {
  const name = document.getElementById("csName").value.trim();
  const image = document.getElementById("csImage").value.trim();
  const memory_mb = parseInt(document.getElementById("csMemory").value, 10) || 512;
  const env = parseEnv(document.getElementById("csEnv").value);
  if (!name || !image) { toast("Name and image required", "error"); return; }
  try {
    await api("/servers", {method: "POST", body: JSON.stringify({name, image, memory_mb, env})});
    toast("Server created", "ok");
    document.getElementById("csName").value = "";
    document.getElementById("csImage").value = "";
    document.getElementById("csEnv").value = "";
    await refreshServers();
  } catch (e) {
    toast(e.message, "error");
  }
}

async function refreshServers() {
  try {
    const list = await api("/servers");
    const tbody = document.querySelector("#serverTable tbody");
    tbody.innerHTML = "";
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted">No servers yet.</td></tr>';
      return;
    }
    list.forEach(s => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${s.id}</td>
        <td>${escapeHtml(s.name)}</td>
        <td><span class="muted">${escapeHtml(s.image)}</span></td>
        <td>${s.port}</td>
        <td><span class="pill ${s.status}">${s.status}</span></td>
        <td>
          <button class="success" data-act="start" data-id="${s.id}">▶ Start</button>
          <button class="danger" data-act="stop" data-id="${s.id}">■ Stop</button>
          <button data-act="logs" data-id="${s.id}" data-name="${escapeHtml(s.name)}">Logs</button>
          <button data-act="delete" data-id="${s.id}">Delete</button>
        </td>`;
      tbody.appendChild(tr);
    });
  } catch (e) {
    toast(e.message, "error");
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[c]));
}

async function handleTableClick(e) {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const id = btn.dataset.id;
  const act = btn.dataset.act;
  try {
    if (act === "start") {
      await api(`/servers/${id}/start`, {method: "POST"});
      toast("Started", "ok");
      refreshServers();
    } else if (act === "stop") {
      await api(`/servers/${id}/stop`, {method: "POST"});
      toast("Stopped", "ok");
      refreshServers();
    } else if (act === "delete") {
      if (!confirm("Delete this server?")) return;
      await api(`/servers/${id}`, {method: "DELETE"});
      toast("Deleted", "ok");
      refreshServers();
    } else if (act === "logs") {
      openLogs(id, btn.dataset.name);
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

function openLogs(id, name) {
  document.getElementById("logsCard").classList.remove("hidden");
  document.getElementById("logsTitle").textContent = "· " + name;
  const box = document.getElementById("logsBox");
  box.textContent = "";
  if (logsSocket) { try { logsSocket.close(); } catch {} }
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  logsSocket = new WebSocket(`${proto}//${location.host}/api/v1/ws/servers/${id}/logs?token=${encodeURIComponent(token)}`);
  logsSocket.onmessage = ev => {
    box.textContent += ev.data + "\\n";
    box.scrollTop = box.scrollHeight;
  };
  logsSocket.onerror = () => toast("Log stream error", "error");
  logsSocket.onclose = () => { /* ok */ };
}

document.getElementById("loginBtn").onclick = loginFlow;
document.getElementById("createBtn").onclick = createServer;
document.querySelector("#serverTable").addEventListener("click", handleTableClick);
document.getElementById("closeLogs").onclick = () => {
  document.getElementById("logsCard").classList.add("hidden");
  if (logsSocket) { try { logsSocket.close(); } catch {} }
};
document.getElementById("loginPassword").addEventListener("keydown", e => {
  if (e.key === "Enter") loginFlow();
});

tryRestoreSession();
setInterval(() => {
  if (token) refreshServers();
}, 15000);
</script>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)
