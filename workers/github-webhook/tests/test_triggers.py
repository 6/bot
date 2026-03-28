from github_webhook.triggers import MentionTrigger, parse_owner_mention


def test_parse_owner_mention_uses_first_nonempty_line() -> None:
    result = parse_owner_mention(
        "\n\n@6 please retry with the smaller patch\nand keep the existing fixtures",
        owner_login="6",
    )

    assert result == MentionTrigger(
        login="6",
        prompt="please retry with the smaller patch\nand keep the existing fixtures",
    )


def test_parse_owner_mention_rejects_other_mentions() -> None:
    assert parse_owner_mention("@6[bot] please help", owner_login="6") is None
    assert parse_owner_mention("@other please help", owner_login="6") is None
