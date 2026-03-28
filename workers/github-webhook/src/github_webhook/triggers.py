from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MentionTrigger:
    login: str
    prompt: str
def parse_bot_mention(body: str, *, bot_login: str) -> MentionTrigger | None:
    mention = f"@{bot_login}"
    lines = body.splitlines()

    first_nonempty_index: int | None = None
    for index, line in enumerate(lines):
        if line.strip():
            first_nonempty_index = index
            break

    if first_nonempty_index is None:
        return None

    first_line = lines[first_nonempty_index]
    match = re.match(
        rf"^\s*{re.escape(mention)}(?=$|[\s:,.!?-])(.*)$",
        first_line,
    )
    if match is None:
        return None

    prompt_lines: list[str] = []
    first_line_remainder = match.group(1).lstrip(" \t:,.!?-")
    if first_line_remainder:
        prompt_lines.append(first_line_remainder)
    prompt_lines.extend(lines[first_nonempty_index + 1 :])

    return MentionTrigger(
        login=bot_login,
        prompt="\n".join(prompt_lines).strip(),
    )
