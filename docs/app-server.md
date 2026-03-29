# Persistent Agent Servers

## Problem

Even after the quick wins (direct dispatch, 👀 ACK), the webhook→agent
path still takes ~2-4 min, dominated by GHA scheduling (~30-120s) and
CLI installation (~30-60s). To get to <5s, the execution backend needs
to move off GHA onto persistent compute.

Several agent CLIs now offer persistent or programmatic modes that
eliminate cold-start entirely when run on always-ready compute.

## CLI Landscape

### Codex App Server

**Status:** Available now
**Docs:** https://developers.openai.com/codex/app-server

The Codex app server is a persistent JSON-RPC 2.0 process — the same
interface powering the VS Code extension. It supports stdio and
WebSocket transports.

Key properties:
- **Thread/Turn model** — create a thread, submit turns, stream events
- **Always-running** — no CLI cold-start, no `npm install`, no auth
  file setup per task
- **Built-in sandboxing** — configurable policies
  (`dangerFullAccess`, `readOnly`, `workspaceWrite`)
- **Persistent state** — threads serialize to JSONL on disk; threads
  can be resumed, compacted, or rolled back
- **WebSocket transport** — clients can connect remotely (experimental)

Task submission flow:
```jsonc
→ {"method": "thread/start", "params": {"workingDirectory": "/data/repos/6/nitrocop"}, "id": 1}
← {"result": {"threadId": "thread-abc"}}

→ {"method": "turn/start", "params": {
    "threadId": "thread-abc",
    "input": [{"type": "user", "text": "... task prompt ..."}],
    "model": "gpt-5.4",
    "reasoningEffort": "high",
    "sandboxPolicy": "dangerFullAccess"
  }, "id": 2}

← {"method": "item/started", "params": {...}}       // stream
← {"method": "item/completed", "params": {...}}      // stream
← {"method": "turn/completed", "params": {...}}      // done
```

### Claude Agent SDK

**Status:** Available now
**Docs:** https://platform.claude.com/docs/en/agent-sdk/overview
**Install:** `pip install claude-agent-sdk` / `npm install @anthropic-ai/claude-agent-sdk`

The Claude Agent SDK is a Python/TypeScript library that provides
programmatic access to the full Claude Code toolset.

Key properties:
- **`query()` function** — submit a prompt, get an async stream of
  messages with all built-in tools (Read, Edit, Bash, Glob, Grep, etc.)
- **Session resumption** — capture `session_id`, resume later with
  full context
- **Hooks** — `PreToolUse`, `PostToolUse`, `Stop`, etc.
- **Subagents** — spawn specialized agents for subtasks
- **MCP support** — connect to external tool servers
- **Permission modes** — control which tools are allowed

**Auth limitation:** The Agent SDK supports `ANTHROPIC_API_KEY`
(usage-based), Bedrock, Vertex, and Azure. It does **not** support
`CLAUDE_CODE_OAUTH_TOKEN` (bounded monthly pricing). Anthropic's
terms explicitly prohibit third-party developers from using claude.ai
login or rate limits via the SDK. This means the SDK can only be used
with per-token API billing, not the flat-rate OAuth plan that the bot
currently uses for the `claude-oauth-*` backends.

For the OAuth path, the only supported approach today is
`claude-code-action@v1` (GitHub Action) or the `claude` CLI with
`CLAUDE_CODE_OAUTH_TOKEN` set — both of which require either GHA or
direct CLI invocation rather than the SDK.

Task submission (API key auth only):
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Fix the bug in auth.py",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
        permission_mode="acceptEdits",
    ),
):
    if hasattr(message, "result"):
        print(message.result)
```

### Gemini CLI

**Status:** No server mode
**Docs:** https://github.com/google-gemini/gemini-cli

Gemini CLI supports non-interactive execution via `-p` flag and
`--output-format stream-json` for streaming JSONL events, but has no
persistent server or programmatic SDK. Each invocation is one-shot.
Could still benefit from persistent compute (skip install), but no
native session resumption.

### OpenCode

**Status:** No server mode
**Docs:** https://github.com/opencode-ai/opencode

Go-based TUI with `-p` flag for non-interactive mode. SQLite-backed
session persistence. No server mode, no programmatic API, no remote
invocation capability. Not a candidate for persistent server
deployment.

## How This Changes the Architecture

### Current (GHA-based)

```
Webhook → Worker → GHA queue (30-120s) → repo-task.yml (60-120s setup) → codex exec / claude -p → done
```

### Proposed (persistent compute)

```
Webhook → Worker → task-runner HTTP endpoint (~100ms) → Agent SDK query() / Codex app server turn → done
```

The task-runner is a small Python service on persistent compute (Fly,
Sprites, etc.) that:
1. Accepts task requests from the Worker via HTTP
2. Calls the Claude Agent SDK `query()` or connects to the local
   Codex app server
3. Streams progress, posts GitHub status updates
4. On completion: extracts patch, posts results to GitHub

### Nightly Update Pattern

```bash
# Claude Agent SDK
pip install --upgrade claude-agent-sdk

# Codex app server
npm install -g @openai/codex@latest
systemctl restart codex-app-server
```

Or: rebuild container image nightly, rolling deploy.

## Comparison

| | Codex App Server | Claude Agent SDK | Claude CLI | Gemini CLI | OpenCode |
|---|---|---|---|---|---|
| Persistent mode | JSON-RPC daemon | Python/TS library | No (one-shot) | No | No |
| Task start (warm) | <1s | <2s | ~3-5s (process spawn) | N/A | N/A |
| Session resume | Native | Native | `--resume` flag | No | No |
| Streaming | JSON-RPC notifications | Async iterator | `--output-format json` | JSONL (`stream-json`) | No |
| Sandboxing | Built-in policies | Permission modes | `--dangerously-skip-permissions` | No | No |
| Remote invocation | WebSocket | Library call | CLI only | CLI only | CLI only |
| OAuth token support | N/A | **No** (API key only) | **Yes** | N/A | N/A |
| Complexity | JSON-RPC protocol | Python async for | Shell exec | Shell exec | Shell exec |

**The OAuth constraint matters.** The bot's `claude-oauth-*` backends
use `CLAUDE_CODE_OAUTH_TOKEN` for bounded monthly pricing. The Agent
SDK can't use this token. On persistent compute, the options are:

1. **Claude CLI** (`claude -p`) with `CLAUDE_CODE_OAUTH_TOKEN` — works
   but is one-shot, no SDK niceties
2. **Claude Agent SDK** with `ANTHROPIC_API_KEY` — full SDK features
   but usage-based pricing
3. **`claude-code-action@v1`** on GHA — supports OAuth but requires GHA

## Suggested Phased Approach

1. **Phase 1 — Persistent compute with raw CLIs:**
   Pre-install Codex CLI and Claude CLI on Fly/Sprites. Use
   `codex exec` and `claude -p` (with `CLAUDE_CODE_OAUTH_TOKEN`)
   directly. Proves the infra, gets to ~3-5s. OAuth pricing preserved.

2. **Phase 2 — Codex app server:**
   Replace `codex exec` with the app server `turn/start` for <1s
   Codex task starts. Keep Claude on raw CLI (OAuth constraint).

3. **Phase 3 — Re-evaluate Claude path:**
   If Anthropic adds OAuth support to the Agent SDK, migrate.
   Otherwise, the raw `claude -p` CLI on persistent compute is
   already fast enough (~3-5s) and preserves bounded pricing.

4. **Phase 4 — Multi-backend task-runner:**
   Single HTTP service that accepts tasks and routes to the right
   backend (Codex server, Claude CLI, or raw CLI for others like
   Gemini). The Worker only needs to know one endpoint.
