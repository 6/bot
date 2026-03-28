from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandMatch:
    name: str
    args: str


def parse_command(body: str, allowed_commands: tuple[str, ...]) -> CommandMatch | None:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for command in sorted(allowed_commands, key=len, reverse=True):
            if stripped == command:
                return CommandMatch(name=command, args="")
            if stripped.startswith(f"{command} "):
                return CommandMatch(name=command, args=stripped[len(command) :].strip())
        return None
    return None
