# SSH Remote Guide (v3.0 HTTP Daemon Model)

> Updated for v3.0. The old "wait for MCP to auto-launch a browser" flow
> is gone — v3.0 uses a long-running daemon that you connect to with
> your local browser via SSH port forwarding.

## The shift in v3.0

In v2.x every `interactive_feedback` call tried to open a browser
window on the same host as the MCP server. On SSH Remote (VS Code
Remote / Cursor Remote / etc.) the remote host has no display, so that
failed with confusing errors.

v3.0 flips the model:

- You run **one daemon** on the remote host: `serve --http`;
- The daemon never opens a browser itself — it just listens;
- You connect to it from your **local** browser over an SSH-forwarded
  port (e.g. `http://localhost:8765/`);
- All AI agents (Cursor Chat etc.) send their MCP calls to the same
  daemon URL.

## 1. Start the daemon on the remote host

Pick one of two host bindings depending on how you want to forward:

### Option A — bind localhost, forward via SSH (recommended)

On the remote:

```bash
# Foreground; Ctrl+C to stop
uvx mcp-feedback-enhanced serve --http
# or
uv run python -m mcp_feedback_enhanced serve --http
```

This binds `127.0.0.1:8765` (loopback only, no exposure to the remote
network).

On your **local** machine, set up port forwarding (see §2).

### Option B — bind all interfaces (only if you control the network)

```bash
uvx mcp-feedback-enhanced serve --http --host 0.0.0.0 --port 8765
```

This listens on every interface. **Only safe if** the remote host is
behind a firewall and the port is not publicly reachable. No auth is
enforced by the daemon itself.

## 2. Port forwarding from your laptop

### VS Code Remote SSH

1. `Ctrl/Cmd+Shift+P` → `Forward a Port`;
2. Enter `8765`;
3. Open `http://localhost:8765/` in your local browser.

![Port Settings](../images/ssh-remote-port-setting.png)
![Connect URL](../images/ssh-remote-connect-url.png)

### Cursor Remote

1. Open the Ports panel (Command Palette → `Toggle Ports`);
2. Add forwarding rule for `8765`;
3. Open `http://localhost:8765/` locally.

### Plain SSH command line

```bash
ssh -L 8765:127.0.0.1:8765 user@remote-host
# then on your local browser: http://localhost:8765/
```

## 3. `mcp.json` on the Agent side

Your AI agent (Cursor IDE) runs **locally** and needs to reach the MCP
endpoint. With SSH forwarding this is straightforward:

```json
{
  "mcpServers": {
    "mcp-feedback-enhanced": {
      "url": "http://127.0.0.1:8765/mcp/",
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

The trailing `/` is required.

## 4. First-run smoke test

```bash
# On your local laptop, after SSH forwarding is up
curl http://localhost:8765/api/all-sessions
# → {"sessions":[]}
curl -s http://localhost:8765/ | head -n 5
# → HTML page
```

If both succeed, send a message from Cursor that triggers
`interactive_feedback`. A new card should appear in the sidebar of
`http://localhost:8765/`.

## 5. FAQ

**Q: Should I still set `MCP_WEB_HOST=0.0.0.0`?**
A: No. That env var was a v2.x workaround for "auto-launched browser
on remote cannot reach local". In v3.0 just pass `--host 0.0.0.0` to
`serve` if you actually need to bind all interfaces (Option B above).

**Q: The daemon says "address already in use".**
A: Another `mcp-feedback-enhanced` process or an unrelated service is
using 8765. Either stop it (`lsof -i :8765` → kill the PID), or pass
`--port 18765` and forward that port instead.

**Q: PID lock says daemon is already running but I can't find the
process.**
A: Stale lock. Delete the file and retry:

```bash
rm ~/.config/mcp-feedback-enhanced/daemon.pid
uvx mcp-feedback-enhanced serve --http
```

**Q: My agent keeps connecting to port 8765 on the laptop but the
daemon is on the server — nothing happens.**
A: SSH port forwarding is not actually active. Re-check §2, and verify
with `curl http://localhost:8765/api/all-sessions` from the laptop
before launching the AI call.

**Q: Can the daemon survive when I disconnect SSH?**
A: Not with plain `uvx ... serve --http` because `Ctrl+C` / SIGHUP on
disconnect kills the foreground process. Use `tmux` / `screen` / `nohup`
if you want it to persist across sessions:

```bash
tmux new -d -s mcp-feedback 'uvx mcp-feedback-enhanced serve --http'
```

v3.0 deliberately does not ship LaunchAgent / systemd templates
(design decision §7.14 in
[multi-session-http-redesign.md](../../architecture/multi-session-http-redesign.md)).

**Q: Can I share one daemon across multiple users on the same remote
box?**
A: Not recommended. The PID lock is per-user (`~/.config/...`), but
you'd share the session list across people — privacy hazard. Spin up
one daemon per user on different ports.

**Q: WebSocket shows "disconnected" in the browser console after a
Wi-Fi blip.**
A: The page auto-reconnects. If it doesn't, reload the tab — session
state is held server-side and comes back via `sessions_snapshot`.

---

**Related**:
- [Phase 2: HTTP Daemon Usage Guide](../../architecture/phase2-http-daemon-usage.md)
- [Phase 3: Multi-Session UI Usage Guide](../../architecture/phase3-multi-session-ui-usage.md)
- [Cache Management](../cache-management.md)
