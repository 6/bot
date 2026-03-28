from __future__ import annotations

import json
from urllib.parse import urlparse

from js import Object, Response, fetch as js_fetch
from pyodide.ffi import to_js as _py_to_js
from workers import WorkerEntrypoint

from github_webhook.config import DISPATCH_WORKFLOW, load_settings
from github_webhook.dispatch import build_workflow_dispatch_request
from github_webhook.github_app import build_installation_token_request
from github_webhook.github_signature import verify_signature
from github_webhook.intake import IgnoreWebhook, extract_dispatch_request


def _to_js(value: object):
    return _py_to_js(value, dict_converter=Object.fromEntries)


def _json_response(status: int, payload: dict[str, object]):
    return Response.new(
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        _to_js(
            {
                "status": status,
                "headers": {"content-type": "application/json; charset=utf-8"},
            }
        ),
    )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(str(request.url))

        if request.method == "GET" and url.path in {"/health", "/healthz"}:
            return _json_response(200, {"ok": True, "path": url.path})

        if url.path != "/github/webhook":
            return _json_response(404, {"error": "not_found"})

        if request.method != "POST":
            return _json_response(405, {"error": "method_not_allowed"})

        try:
            settings = load_settings(self.env)
        except ValueError as exc:
            return _json_response(500, {"error": "misconfigured_worker", "message": str(exc)})

        body = await request.text()
        signature = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(settings.webhook_secret, signature, body.encode("utf-8")):
            return _json_response(401, {"error": "invalid_signature"})

        event_name = request.headers.get("X-GitHub-Event") or ""
        delivery_id = request.headers.get("X-GitHub-Delivery")

        if event_name == "ping":
            return _json_response(200, {"ok": True, "event": "ping"})

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return _json_response(400, {"error": "invalid_json"})

        try:
            dispatch_request = extract_dispatch_request(
                event_name=event_name,
                delivery_id=delivery_id,
                payload=payload,
                settings=settings,
            )
        except IgnoreWebhook as exc:
            return _json_response(202, {"ignored": True, "reason": str(exc)})
        except ValueError as exc:
            return _json_response(400, {"error": "invalid_payload", "message": str(exc)})

        token_request = build_installation_token_request(
            settings,
            installation_id=dispatch_request.installation_id,
        )
        token_response = await js_fetch(
            token_request.url,
            _to_js(
                {
                    "method": "POST",
                    "headers": token_request.headers,
                    "body": token_request.body,
                }
            ),
        )
        token_body = await token_response.text()
        if not (200 <= int(token_response.status) < 300):
            return _json_response(
                502,
                {
                    "error": "installation_token_failed",
                    "status": int(token_response.status),
                    "body": str(token_body)[:500],
                },
            )
        try:
            installation_token = json.loads(str(token_body))["token"]
        except (json.JSONDecodeError, KeyError):
            return _json_response(502, {"error": "installation_token_invalid_response"})

        dispatch = build_workflow_dispatch_request(
            settings,
            dispatch_request,
            access_token=installation_token,
        )
        response = await js_fetch(
            dispatch.url,
            _to_js(
                {
                    "method": "POST",
                    "headers": dispatch.headers,
                    "body": dispatch.body,
                }
            ),
        )

        if 200 <= int(response.status) < 300:
            return _json_response(
                202,
                {
                    "ok": True,
                    "request_id": dispatch_request.request_id,
                    "workflow": DISPATCH_WORKFLOW,
                    "source_repo": dispatch_request.source_repo,
                },
            )

        response_text = await response.text()
        return _json_response(
            502,
            {
                "error": "workflow_dispatch_failed",
                "status": int(response.status),
                "body": str(response_text)[:500],
            },
        )
