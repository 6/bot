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
cd workers/github-webhook
uv sync --group dev
```

For local development, put worker-only secrets in a gitignored `.dev.vars` file next to `wrangler.toml`.

Example:

```dotenv
GH_APP_ID=replace-me
GITHUB_WEBHOOK_SECRET=replace-me
GH_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
```

Useful commands:

```bash
uv run ruff check src tests
uv run pytest -q
uv run pywrangler dev
export CLOUDFLARE_WORKER_NAME=replace-me
uv run pywrangler deploy --name "$CLOUDFLARE_WORKER_NAME"
```

Or from the repo root with `mise` tasks:

```bash
mise run worker-webhook-sync
mise run worker-webhook-check
mise run worker-webhook-dev
export CLOUDFLARE_WORKER_NAME=replace-me
mise run worker-webhook-deploy
```

## Required Cloudflare Secrets

Set these in the Worker environment:
- `GH_APP_ID`
- `GH_APP_PRIVATE_KEY`
- `GITHUB_WEBHOOK_SECRET`

Notes:
- `GH_APP_ID` is the GitHub App identifier used to mint installation tokens.
- `GH_APP_PRIVATE_KEY` is the GitHub App private key used by the Worker to mint installation tokens.
- `GITHUB_WEBHOOK_SECRET` must match the webhook secret configured on the GitHub App.
- The Worker mints a GitHub App installation token per request and uses that token to trigger `workflow_dispatch` on `6/bot`.

For deployed environments, store these as Cloudflare Worker secrets, not in `wrangler.toml`.

Examples:

```bash
export CLOUDFLARE_WORKER_NAME=replace-me
npx wrangler secret put GH_APP_PRIVATE_KEY --name "$CLOUDFLARE_WORKER_NAME"
npx wrangler secret put GITHUB_WEBHOOK_SECRET --name "$CLOUDFLARE_WORKER_NAME"
```

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

## Deployment Notes

Authentication for deploys is separate from runtime secrets.

Use one of:
- `wrangler login` / `pywrangler deploy` for manual local deploys
- or `CLOUDFLARE_API_TOKEN` plus `CLOUDFLARE_ACCOUNT_ID` in CI for automated deploys

The checked-in Worker name is only a placeholder. Deploy the real public Worker name with:

```bash
export CLOUDFLARE_WORKER_NAME=replace-me
export GH_APP_ID=replace-me
uv run pywrangler deploy --name "$CLOUDFLARE_WORKER_NAME" --var "GH_APP_ID:$GH_APP_ID"
```

Recommended GitHub Actions secret:
- `CLOUDFLARE_WORKER_NAME`
- optional: `CLOUDFLARE_WORKERS_SUBDOMAIN` for masking the derived `workers.dev` URL in deploy logs

Recommended GitHub Actions variable:
- `GH_APP_ID`

This project is configured with:
- `workers_dev = true`
- `preview_urls = false`

That means:
- the Worker deploys to your account `workers.dev` subdomain
- the public script name comes from `--name` at deploy time, not from the checked-in placeholder
- preview URLs stay disabled

Terraform is not used for this `workers.dev` deployment path. If you later move to a custom domain or Cloudflare routes, add that infrastructure separately.
