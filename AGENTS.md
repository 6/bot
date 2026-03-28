# 6/bot

Public control-plane repo for privileged AI-agent execution across `6/*` repositories.

This repo is intentionally small. It owns:
- secret-bearing agent execution
- source-repo allowlisting
- trusted-ref enforcement
- GitHub App token minting for source-repo access
- backend selection and secret injection
- generic privileged GitHub write operations for allowlisted repos
- remote artifact handoff back to the calling repo
- webhook ingress for comment-driven bot commands

This repo does **not** own target-repo orchestration. Each target repo decides:
- when to run an agent
- which refs are trusted
- what prompt to send
- what setup is needed before agent execution
- how to validate and land the result

## Mental Model

- `6/bot` is a **generic executor**, not a reusable workflow library for repo-specific CI.
- The Cloudflare Worker is the standard external ingress for command-driven bot requests.
- Inside `6/bot`, GitHub Actions still use `workflow_dispatch` as the internal handoff from the Worker into the executor workflows.
- `6/bot` checks that the source repo is explicitly allowlisted, then checks out the target repo at the requested SHA and either runs the selected backend or performs a generic write request with credentials that live only here.
- Target repos may expose an optional `.github/actions/bot-setup/action.yml` hook for language/toolchain setup. That hook runs inside the target repo checkout, so only allow trusted repos and trusted refs.
- The remote agent writes runtime artifacts and a patch. The calling repo downloads those artifacts and applies the patch locally.
- The remote repo-write path executes generic privileged side effects such as comments, label edits, and patch push/promotion on behalf of the target repo.

## Security Model

This repo is public by design, but it is meant to be tightly controlled:
- pull requests and issues should stay disabled
- `main` is the only branch intended for normal operation
- all model secrets stay in this repo, never in target repos
- the Cloudflare Worker validates webhook signatures and routes commands into `6/bot`
- the Worker holds GitHub App credentials and mints installation tokens per request
- target/source repos should not need a dispatch token in the webhook model
- only explicitly allowlisted source repos may dispatch work here
- only branch/tag refs are accepted; `refs/pull/*` is rejected
- the requested `target_sha` must still match the trusted ref contract for the requested operation

Important:
- allowlisting a repo means you trust its checked-out code to run under this control plane
- target repos must gate dispatch on their own side too; `6/bot` is a second line of defense, not the first

Trusted ref modes:
- remote agent execution may target a trusted branch/tag ref and run at the requested SHA
- remote repo-write requests default to `current_head` matching, so the target branch must still point at the expected SHA when the privileged write runs

## Repo Layout

- `.github/workflows/` — control-plane workflows
- `.github/actions/` — shared composite actions used by those workflows
- `config/` — editable control-plane configuration such as the source-repo allowlist
- `src/bot/` — Python helpers for backend resolution, runtime setup, leak scanning, and secret validation
- `tests/` — unit coverage for the control-plane helpers
- `worker/github-webhook/` — Cloudflare Worker ingress for GitHub App webhooks

## Required Repo Configuration

Repository variable:
- `GH_APP_ID`

Repository secrets:
- `GH_APP_PRIVATE_KEY`
- `MINIMAX_API_KEY`
- `CODEX_AUTH_JSON`
- `CLAUDE_CODE_OAUTH_TOKEN`

Optional secret:
- `ANTHROPIC_API_KEY`

Notes:
- `GH_APP_ID` is a variable, not a secret
- `GH_APP_PRIVATE_KEY` must remain a secret
- `CODEX_AUTH_JSON` is validated for JSON shape, required fields, `last_refresh`, and token expiry where detectable

## Current Workflows

### `remote-agent.yml`

Triggered by `workflow_dispatch` with inputs `request_id`, `source_repo`, and `payload` (JSON).

High-level flow:
1. Parse the JSON payload from the `payload` input.
2. Check the source repo against `config/allowlist.toml`.
3. Reject non-`6/*` repos, non-branch/tag refs, and PR refs.
4. Mint a read-only GitHub App token for the source repo.
5. Download the caller-provided input artifact.
6. Check out the source repo at `target_sha`.
7. Verify `target_sha` is contained in `target_ref`.
8. Optionally run the source repo’s `.github/actions/bot-setup/action.yml`.
9. Initialize the standard runtime layout.
10. Run the selected backend through `.github/actions/run-agent`.
11. Leak-scan runtime artifacts and upload the output artifact back to the caller.

### `remote-repo-write.yml`

Triggered by `workflow_dispatch` with inputs `request_id`, `source_repo`, and `payload` (JSON).

High-level flow:
1. Parse the JSON payload from the `payload` input.
2. Check the source repo against `config/allowlist.toml`.
3. Reject non-`6/*` repos, non-branch/tag refs, and PR refs.
4. Mint a GitHub App token for the source repo with the write permissions needed by the requested operations.
5. Download the caller-provided request artifact.
6. Check out the source repo at `target_sha`.
7. Verify the trusted ref contract for the request.
8. Execute the generic repo-write request.
9. Upload metadata back to the caller.

### `checks.yml`

Runs on `push` to `main` and `workflow_dispatch`.

Current checks:
- `uv sync --frozen --group dev`
- `uv run ruff check tests src .github`
- `uv run pytest -q`

### `secret-health.yml`

Runs:
- on schedule
- on manual dispatch
- when `.github/workflows/secret-health.yml` itself changes on `main`

It validates presence/shape of the repo credentials and should be the place to grow future provider-specific health probes.

### `webhook-command.yml`

Triggered by `workflow_dispatch` with inputs `request_id`, `source_repo`, and `payload` (JSON).

High-level flow:
1. Parse the JSON payload from the `payload` input.
2. Check the source repo against `config/allowlist.toml`.
3. Reject non-`6/*` repos.
4. Record the distilled webhook request in the job summary.
5. Upload the JSON payload as an artifact for follow-on routing/debugging.

This is the first landing point for the webhook ingress. It is intentionally generic and should stay free of target-repo business logic.

## Source Repo Allowlist

`config/allowlist.toml` is the control-plane allowlist.

Example:

```toml
allowed_repositories = [
  "owner/repo-a",
]
```

To add a new repo:
1. Add `owner/repo` to `config/allowlist.toml`.
2. Commit and push to `main`.
3. Make sure the GitHub App used by `6/bot` is installed on that repo with the minimum permissions needed by the workflows that repo will use.

## Supported Backends

Backends are defined in `src/bot/resolve_backend.py`.

Current backend names:
- `minimax`
- `claude-normal`
- `claude-hard`
- `claude-oauth-normal`
- `claude-oauth-hard`
- `codex-normal`
- `codex-hard`

The resolver is responsible for:
- mapping backend names to the CLI/action used
- exporting non-secret environment variables
- validating/masking the selected backend’s secret
- ensuring only the selected backend’s secret is used

## How A Target Repo Integrates

The target repo should keep its own orchestration and use `6/bot` only for privileged execution and publish steps.

Minimum integration pieces:

1. Install the GitHub App on the target repo.
2. Point GitHub App webhooks at the Cloudflare Worker route.
3. Make the target repo’s comments/commands and trust policy compatible with the Worker’s allowlist and command parser.
4. Keep repo-specific workflows responsible for prompt generation, verification, and any follow-on execution after `6/bot` runs.

If the target repo also wants `6/bot` to own privileged publish/mutation steps, add a second bridge for repo-write requests instead of doing those writes locally.

### Dispatch inputs

Both workflows accept three `workflow_dispatch` inputs:

| Input | Description |
|-------|-------------|
| `request_id` | Unique identifier for tracking (appears in run name) |
| `source_repo` | `owner/name` — must match the value inside `payload` |
| `payload` | JSON string containing the full request payload |

### Agent payload fields

The `payload` JSON for `remote-agent.yml` should contain:
- `request_id`
- `source_repo`
- `source_run_id`
- `input_artifact`
- `output_artifact`
- `target_sha`
- `target_ref`
- `backend`
- `base_sha`
- `workflow`
- optional `diff_paths`
- optional `setup_profile`
- optional `setup_config_json`

### Repo-write payload fields

The `payload` JSON for `remote-repo-write.yml` should contain:
- `request_id`
- `source_repo`
- `source_run_id`
- `input_artifact`
- `output_artifact`
- `target_sha`
- `target_ref`

The repo-write request artifact may contain operations such as:
- `comment_pr`
- `comment_issue`
- `edit_issue_labels`
- `push_patch`

## Optional Target-Repo Setup Hook

If a target repo defines:

`/.github/actions/bot-setup/action.yml`

then `6/bot` will call it before running the agent and pass:
- `setup_profile`
- `setup_config_json`

This is the intended place for target-repo-specific setup such as:
- installing a language toolchain
- restoring repo-specific dependencies
- exporting build flags

This hook should stay repo-local. Do not move language- or repo-specific setup into `6/bot`.

## Integration Guidance

When integrating a new repo:
- keep all model secrets in `6/bot`
- keep repo-specific prompts, setup, trust policy, and verification in the target repo
- keep repo-specific publish policy in the target repo, even if `6/bot` executes the final privileged mutation
- keep the webhook ingress centralized; do not add new direct-dispatch tokens to source repos
- gate dispatch on trusted refs before contacting `6/bot`
- avoid dispatching PR head refs from untrusted forks
- prefer slash-command or maintainer-only triggers over broad public comment triggers
- keep the target repo’s setup hook deterministic and non-interactive
- keep webhook signature validation in the Worker, not in GitHub Actions
- let the Worker dispatch only into generic `6/bot` entrypoints
- do not move repo-specific orchestration into the Worker

## Local Commands

```bash
uv sync --group dev
uv run ruff check tests src .github
uv run pytest -q
uv run python -m bot.secret_health --max-codex-age-days 7
uv run python -m bot.allowlist check-repo owner/repo-a
```

## Editing Rules

- keep `6/bot` generic; do not add target-repo-specific workflow semantics here
- repo-specific orchestration belongs in the source repo
- repo-specific language/toolchain setup belongs in the source repo’s optional `bot-setup` action
- update tests when changing allowlist, secret validation, backend resolution, or runtime contract
- treat changes to `remote-agent.yml`, `remote-repo-write.yml`, `run-agent/action.yml`, and privileged GitHub mutation helpers as security-sensitive

## When Updating The Contract

If you change:
- dispatch payload fields
- backend names or secret expectations
- output artifact contents
- required source-repo hooks

then update:
- this file
- tests in `tests/`
- at least one real source repo integration
