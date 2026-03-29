# Fast Webhook → Agent Execution

## Current State (after quick wins)

The Worker now dispatches directly to `repo-task.yml`, skipping the intermediate
`webhook-command.yml` hop. It also adds an immediate 👀 reaction on the
triggering comment/issue so the user gets sub-second visual feedback.

**Current latency chain:**

```
GitHub webhook → CF Worker (~300ms, posts 👀 reaction) → GHA queue (30-120s) → repo-task.yml (60-120s setup) → agent starts
```

**Estimated time to agent start: ~2-4 minutes** (down from 3-6 minutes).

The remaining latency is dominated by:
1. **GHA job scheduling** (30-120s) — cannot be reduced within GHA
2. **Repo checkout + token generation + routing** (~30-60s)
3. **CLI installation** (~30-60s) — not cached because Claude Code ships new versions daily and you always want the latest

## Platform Migration Options

To get near-instant agent start (<5s), the execution backend needs to move off
GHA for the webhook→agent path.

### Sprites (sprites.dev)

Persistent Firecracker microVMs with <1s cold start.

- **Latency:** <2s warm (persistent state means no setup)
- **Model:** Pre-create a Sprite per source repo with CLIs pre-installed and repos pre-cloned. Worker wakes the Sprite via REST API.
- **Persistence:** Full ext4 filesystem survives between runs — no re-install, no re-clone, just `git pull`.
- **Cost:** $0.07/CPU-hr active, ~$0.0007/GB-hr idle storage only.
- **Secrets:** Per-Sprite environment secrets. Worker passes ephemeral GitHub App tokens at invocation time.
- **Tradeoffs:** Newer platform (less ecosystem). Need to build status reporting, artifact handoff, and concurrency control.

### Modal (modal.com)

Serverless containers with warm pools and Python-native SDK.

- **Latency:** <3s warm pool, ~10s cold.
- **Model:** Define a Modal function/class. Keep 1-2 warm containers with CLIs pre-installed. Worker hits a Modal webhook endpoint.
- **Persistence:** No persistent filesystem (use Modal Volumes for repo cache). Warm pool compensates.
- **Cost:** ~$0.07/CPU-hr. Warm pool idle: ~$0.01/hr per container.
- **Secrets:** Native `modal.Secret` management.
- **Tradeoffs:** Most mature platform. Excellent Python SDK. GPU path available. Less stateful than Sprites — container images need rebuilding for CLI updates.

### Fly Machines (fly.io)

On-demand microVMs with persistent volumes and ~300ms resume.

- **Latency:** <2s resume from stopped, <300ms from suspended.
- **Model:** Create Fly Machines per source repo with persistent volumes. Auto-stop when idle, resume via HTTP proxy.
- **Persistence:** `/data` persistent volume keeps CLIs, repos, and state warm.
- **Cost:** $0.007/hr per shared CPU while running. Stopped machines: $0 compute, volume storage only (~$0.15/GB/mo).
- **Secrets:** Native per-app secrets via `fly secrets set`.
- **Tradeoffs:** More DevOps (Dockerfile, deploy pipeline). No warm pool abstraction — you manage the lifecycle. Cheapest idle cost.

### Self-Hosted GHA Runners

Keep GHA workflows, replace hosted runners with always-on self-hosted ones.

- **Latency:** <30s (no queue wait, still has workflow overhead).
- **Model:** Run `actions/runner` on EC2/Fly/etc. with CLIs pre-installed. Change `runs-on:` to target self-hosted runners.
- **Persistence:** Runner stays warm between jobs.
- **Cost:** EC2 instance cost (~$0.02-0.10/hr depending on size).
- **Secrets:** GHA secrets (unchanged).
- **Tradeoffs:** Minimal workflow changes, keeps native GHA integration. Can't get below ~30s due to GHA overhead. Must manage runner infra, updates, and security. Scaling requires runner pools.

## Comparison

| Platform | Agent start | Effort | Ongoing ops | Keeps GHA integration |
|----------|-------------|--------|-------------|----------------------|
| Sprites  | <2s         | Days   | Low         | No — must build      |
| Modal    | <3s         | Days   | Low         | No — must build      |
| Fly      | <2s         | Days   | Medium      | No — must build      |
| Self-hosted runners | <30s | Days | High     | Yes — native         |

## Agent Server Protocols

Some CLIs offer persistent/programmatic modes that eliminate process
cold-start on top of the platform-level gains above. See
[app-server.md](app-server.md) for details on the Codex App Server,
Claude Agent SDK, and the auth constraints (notably: the Agent SDK
does not support OAuth tokens / bounded monthly pricing).

## Recommendation

These two docs address different layers of the same problem:

- **This doc** (`fast-execution.md`) is the **platform** question —
  where does compute run? GHA is slow because of scheduling queues and
  ephemeral runners. Persistent compute (Sprites, Fly, Modal) gives
  <2s wake-up. This is the bigger win and is backend-agnostic.

- **[app-server.md](app-server.md)** is the **protocol** question —
  how do you talk to the agent once compute is ready? You can shell out
  to the CLI (`codex exec`, `claude -p`) or use a native protocol
  (Codex app server, Claude Agent SDK). This shaves another 1-3s and
  adds session resumption, but it's an optimization on top.

The practical sequence:

1. **Platform first.** Pick persistent compute (Fly or Sprites look
   strongest). Run raw CLIs. This alone gets from ~2-4 min to ~3-5s.
   Backend-agnostic, no auth changes.

2. **Codex app server second.** Once persistent compute exists,
   upgrading Codex to the app server protocol is a clear win — <1s
   task start, native sandboxing, session resumption. No auth
   constraint.

3. **Claude stays as CLI.** The OAuth pricing constraint means the
   Agent SDK isn't usable for the `claude-oauth-*` backends (see
   [app-server.md](app-server.md)). `claude -p` with
   `CLAUDE_CODE_OAUTH_TOKEN` on persistent compute is ~3-5s and
   preserves bounded monthly pricing. If Anthropic lifts the OAuth
   restriction on the SDK later, upgrade then.

**Bottom line:** platform migration is the 80/20 move. The app server
protocol is a nice-to-have for Codex, and blocked for Claude OAuth.

## Suggested Migration Path

1. **Prototype** one platform (Sprites or Modal) for a single source repo.
2. **Build the integration layer:** Worker → platform API, secret injection, status reporting back to GitHub (comments/checks), artifact capture (patch file, logs).
3. **Run in parallel** with GHA — the Worker can dispatch to both and use the faster result.
4. **Cut over** once the new backend is proven reliable.
5. **Keep GHA** as a fallback for the `remote-agent.yml` and `remote-repo-write.yml` paths, which are less latency-sensitive.

## What the Integration Layer Needs

Regardless of platform choice, moving off GHA means building:

- **Secret injection:** GitHub App token minting (already in the Worker), model API keys (store in platform's secret manager).
- **Status reporting:** Post GitHub comments/reactions at key lifecycle points (claimed, running, done, failed).
- **Artifact capture:** Upload patch file, agent logs, and result metadata somewhere retrievable (GH release asset, S3, or back as a GH comment).
- **Concurrency control:** One agent per source repo at a time (currently handled by GHA `concurrency` groups).
- **Trusted ref enforcement:** Verify the source repo checkout is at a trusted ref/SHA before running.
- **Leak scanning:** Run the same `guard_backend_secrets` scan on output before publishing.
