from github_webhook.commands import CommandMatch, parse_command


def test_parse_command_uses_first_non_empty_line() -> None:
    result = parse_command("\n\n/6bot repair --fast\nignored", ("/6bot repair", "/6bot fix"))

    assert result == CommandMatch(name="/6bot repair", args="--fast")


def test_parse_command_rejects_unknown_command() -> None:
    assert parse_command("/otherbot repair", ("/6bot repair",)) is None
