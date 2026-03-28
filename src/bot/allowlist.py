"""Editable control-plane allowlist for source repositories."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "allowlist.toml"


def load_allowlist(path: Path) -> list[str]:
    data = tomllib.loads(path.read_text())
    entries = data.get("allowed_repositories")
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise ValueError("allowed_repositories must be a list of strings")
    return entries


def is_allowed_repository(source_repo: str, path: Path | None = None) -> bool:
    config_path = default_config_path() if path is None else path
    return source_repo in load_allowlist(config_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config_path(),
        help="Path to the allowlist TOML file",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-repo", help="Fail if the source repo is not allowlisted")
    check.add_argument("source_repo")

    args = parser.parse_args()

    try:
        allowed = load_allowlist(args.config)
    except FileNotFoundError:
        print(f"Allowlist file not found: {args.config}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Invalid allowlist config: {exc}", file=sys.stderr)
        return 1

    if args.command == "check-repo":
        if args.source_repo not in allowed:
            print(
                f"Repository {args.source_repo} is not allowed to dispatch 6/bot",
                file=sys.stderr,
            )
            return 1
        print(args.source_repo)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
