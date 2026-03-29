from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "webhook-command.yml"


def test_webhook_command_routes_all_triggers_into_repo_task() -> None:
    content = WORKFLOW.read_text()

    assert "actions/workflows/repo-task.yml/dispatches" in content
    assert 'GH_TOKEN: ${{ github.token }}' in content
    assert "actions/create-github-app-token@v3" not in content
    assert 'actions/workflows/bot-command.yml/dispatches' not in content
    assert '"ref": "main"' in content
    assert '"request_id": os.environ["REQUEST_ID"]' in content
    assert '"source_repo": os.environ["SOURCE_REPO"]' in content
    assert '"payload": os.environ["INPUT_PAYLOAD"]' in content
