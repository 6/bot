# GitHub Webhook Worker

Thin Cloudflare Worker front door for `6/bot`.

This worker is intentionally small:
- validate the GitHub webhook signature
- accept a small set of bot commands from allowlisted repositories
- apply simple repo/commenter policy
- trigger a `workflow_dispatch` run in `6/bot`

This worker does **not** run agents, poll long-running jobs, or do repo-specific business logic.

This is intended to be the standard external ingress for `6/bot`. `workflow_dispatch` remains the internal mechanism the Worker uses to start GitHub Actions workflows in the control-plane repo.

## Current Scope

Supported today:
- `POST /github/webhook`
- `GET /healthz`
- GitHub `ping`
- GitHub `issue_comment` on pull requests
- slash commands on the first non-empty line:
  - `/6bot repair`
  - `/6bot fix`

The worker currently dispatches to:
- `webhook-command.yml`

That workflow is just the first landing point inside `6/bot`. It records the request and keeps the control-plane boundary centralized.

## Local Setup

From the repo root:

```bash
mise install
cd worker/github-webhook
uv sync --group dev
```

Useful commands:

```bash
uv run ruff check src tests
uv run pytest -q
uv run pywrangler dev
uv run pywrangler deploy
```

Or from the repo root with `mise` tasks:

```bash
mise run worker-webhook-sync
mise run worker-webhook-check
mise run worker-webhook-dev
mise run worker-webhook-deploy
```

## Required Cloudflare Secrets

Set these in the Worker environment:
- `GITHUB_WEBHOOK_SECRET`
- `REMOTE_BOT_WORKFLOW_TOKEN`

Notes:
- `GITHUB_WEBHOOK_SECRET` must match the webhook secret configured on the GitHub App.
- `REMOTE_BOT_WORKFLOW_TOKEN` is the current bridge credential used by the Worker to trigger `workflow_dispatch` on `6/bot`.
- This token lives only in the Worker environment. Source repos should not need their own dispatch token in the webhook model.
- Long term, this token can be replaced by GitHub App installation-token minting inside the Worker if you want to remove it entirely.

## Non-Secret Configuration

The editable non-secret config lives in `wrangler.toml`:
- `BOT_CONTROL_REPO`
- `DISPATCH_WORKFLOW`
- `WORKFLOW_REF`
- `GITHUB_API_BASE`
- `ALLOWED_REPOSITORIES`
- `ALLOWED_ASSOCIATIONS`
- `ALLOWED_COMMANDS`

For now, the Worker allowlist should stay aligned with `config/allowlist.toml`.

## GitHub App Setup

Point the GitHub App webhook URL at this Worker route, for example:

`https://bot-webhook.example.com/github/webhook`

Configure the GitHub App to send at least:
- `Issue comment` events

`ping` events are accepted automatically and can be used to validate wiring.
