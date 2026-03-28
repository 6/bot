from github_webhook.triggers import MentionTrigger, parse_bot_mention


def test_parse_bot_mention_uses_first_nonempty_line() -> None:
    result = parse_bot_mention(
        "\n\n@6 please retry with the smaller patch\nand keep the existing fixtures",
        bot_login="6",
    )

    assert result == MentionTrigger(
        login="6",
        prompt="please retry with the smaller patch\nand keep the existing fixtures",
    )


def test_parse_bot_mention_rejects_other_mentions() -> None:
    assert parse_bot_mention("@6[bot] please help", bot_login="6") is None
    assert parse_bot_mention("@other please help", bot_login="6") is None
