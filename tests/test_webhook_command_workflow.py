from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "webhook-command.yml"


def test_webhook_command_routes_issue_tasks_internally_and_prs_to_source_repo() -> None:
    content = WORKFLOW.read_text()

    assert "actions/workflows/repo-task.yml/dispatches" in content
    assert "if: steps.request.outputs.subject_kind == 'issue'" in content
    assert "if: steps.request.outputs.subject_kind == 'pull_request'" in content
    assert 'GH_TOKEN: ${{ github.token }}' in content
    assert "actions/create-github-app-token@v3" in content
    assert "permission-actions: write" in content
    assert 'actions/workflows/bot-command.yml/dispatches' in content
    assert '"ref": "main"' in content
    assert '"request_id": os.environ["REQUEST_ID"]' in content
    assert '"source_repo": os.environ["SOURCE_REPO"]' in content
    assert '"payload": os.environ["INPUT_PAYLOAD"]' in content
