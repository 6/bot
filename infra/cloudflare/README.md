# Cloudflare Wrapper

This directory is intentionally small.

The current split is:
- Worker code deploys with `pywrangler` from `worker/github-webhook/`
- Terraform manages the optional Cloudflare route that points traffic at that Worker

That keeps Worker iteration simple while still giving you a checked-in place for the surrounding Cloudflare configuration.

## Usage

1. Deploy the Worker code first:

```bash
mise install
cd worker/github-webhook
uv sync --group dev
uv run pywrangler deploy
```

2. Then apply the route:

```bash
cd infra/cloudflare
terraform init
terraform apply
```

## Variables

- `zone_id` — Cloudflare zone that should route to the Worker
- `workers_route_pattern` — URL pattern, for example `bot-webhook.example.com/*`
- `worker_script_name` — Worker script name, default `bot-github-webhook`
