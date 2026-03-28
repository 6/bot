from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "repo-task.yml"


def test_repo_task_workflow_runs_repo_owned_planner_and_local_repo_write() -> None:
    content = WORKFLOW.read_text()

    assert 'name: Repo Task' in content
    assert 'python3 scripts/workflows/repo_task.py route' in content
    assert 'python3 scripts/workflows/repo_task.py prepare' in content
    assert 'python3 scripts/workflows/repo_task.py prepare-agent' in content
    assert 'python3 scripts/workflows/repo_task.py finalize' in content
    assert 'python3 scripts/workflows/repo_task.py cleanup' in content
    assert 'python3 scripts/workflows/agent_runtime.py "$WORKFLOW_NAME"' in content
    assert 'python -m bot.repo_write execute' in content
    assert 'uses: ./.bot/.github/actions/run-agent' in content
    assert 'actions/create-github-app-token@v3' in content
