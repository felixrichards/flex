import asyncio

from champs import elo as elo_route
from champs import get as get_route
from champs import help as help_route
from champs import player as player_route


class _FakeCtx:
    def __init__(self) -> None:
        self.messages: list[tuple[str, object | None]] = []
        self.channel = type("Channel", (), {"id": 1})()

    async def send(self, message: str, file=None) -> None:
        self.messages.append((message, file))


def test_help_shows_clear_general_help() -> None:
    ctx = _FakeCtx()

    asyncio.run(help_route.handle_help(ctx, tuple()))

    text = ctx.messages[0][0]
    assert "`champshelp` usage:" in text
    assert "Commands:" in text
    assert "command" in text
    assert "subcommand" in text


def test_help_for_command_and_prefixed_command() -> None:
    ctx = _FakeCtx()

    asyncio.run(help_route.handle_help(ctx, ("get",)))
    asyncio.run(help_route.handle_help(ctx, ("champsfearless",)))

    assert ctx.messages[0][0].startswith("`champsget`")
    assert "`champsfearless` commands:" in ctx.messages[1][0]


def test_help_for_role_command() -> None:
    ctx = _FakeCtx()

    asyncio.run(help_route.handle_help(ctx, ("role",)))

    assert ctx.messages[0][0].startswith("`champsrole`")


def test_help_unknown_command() -> None:
    ctx = _FakeCtx()

    asyncio.run(help_route.handle_help(ctx, ("notacommand",)))

    assert "Unknown command `notacommand`" in ctx.messages[0][0]


def test_get_help_argument_shows_usage() -> None:
    ctx = _FakeCtx()

    asyncio.run(get_route.handle_get(ctx, ("help",)))

    assert ctx.messages[0][0].startswith("`champsget`")
    assert "If no number is given, 40 are returned." in ctx.messages[0][0]


def test_player_help_subcommand_shows_usage() -> None:
    ctx = _FakeCtx()

    asyncio.run(player_route.handle_player(ctx, ("help",), "/tmp/test.db"))

    assert "`champsplayer` commands:" in ctx.messages[0][0]


def test_elo_help_argument_shows_usage() -> None:
    ctx = _FakeCtx()

    asyncio.run(elo_route.handle_elo(ctx, ("help",), "/tmp/test.db"))

    assert "`champselo` usage:" in ctx.messages[0][0]
