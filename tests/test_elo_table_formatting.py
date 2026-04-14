import asyncio
from types import SimpleNamespace

from champs import elo as elo_route
from champs.db.db import EloRow


class _FakeCtx:
    def __init__(self, author_id: int = 1) -> None:
        self.messages: list[str] = []
        self.author = SimpleNamespace(id=author_id)

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_champselo_full_table_uses_short_headers_and_hides_elo(monkeypatch) -> None:
    rows = [
        EloRow(rank=1, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2, private=False),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(elo_route.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: None)

    ctx = _FakeCtx()
    asyncio.run(elo_route.handle_elo(ctx, tuple(), "/tmp/test.db"))

    text = ctx.messages[0]
    assert "# P" in text
    assert "CP" in text
    assert " W " in text
    assert " L " in text
    assert " D" in text
    assert "ELO" not in text


def test_champselo_filtered_table_uses_standard_headers_and_hides_elo(monkeypatch) -> None:
    rows = [
        EloRow(rank=1, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2, private=False),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(elo_route.db, "resolve_player_identifier", lambda *_args, **_kwargs: "Felix")
    monkeypatch.setattr(elo_route.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: None)

    ctx = _FakeCtx()
    asyncio.run(elo_route.handle_elo(ctx, ("Felix",), "/tmp/test.db"))

    text = ctx.messages[0]
    assert "Rank" in text
    assert "Player" in text
    assert "Wins" in text
    assert "Losses" in text
    assert "Dodges" in text
    assert "scale" in text
    assert "ELO" not in text


def test_champselo_filtered_single_private_player_is_blocked(monkeypatch) -> None:
    rows = [
        EloRow(rank=0, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2, private=True),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(elo_route.db, "resolve_player_identifier", lambda *_args, **_kwargs: "Felix")
    monkeypatch.setattr(elo_route.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: "Wyn")
    monkeypatch.setattr(elo_route.db, "is_player_private", lambda *_args, **_kwargs: False)

    ctx = _FakeCtx(author_id=55)
    asyncio.run(elo_route.handle_elo(ctx, ("Felix",), "/tmp/test.db"))

    assert ctx.messages == ["That player's rank is private."]


def test_champselo_filtered_private_caller_is_blocked(monkeypatch) -> None:
    rows = [
        EloRow(rank=0, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2, private=True),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(elo_route.db, "resolve_player_identifier", lambda *_args, **_kwargs: "Felix")
    monkeypatch.setattr(elo_route.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: "Felix")
    monkeypatch.setattr(elo_route.db, "is_player_private", lambda *_args, **_kwargs: True)

    ctx = _FakeCtx(author_id=55)
    asyncio.run(elo_route.handle_elo(ctx, ("Felix",), "/tmp/test.db"))

    assert ctx.messages == ["Private players cannot use `champselo`."]


def test_champselo_public_table_blocked_for_private_caller(monkeypatch) -> None:
    rows = [
        EloRow(rank=1, player="Wyn", cp=1200, elo=1100, wins=12, losses=2, dodges=0, dodge_scale=1.0, private=False),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)
    monkeypatch.setattr(elo_route.db, "get_discord_linked_player_name", lambda *_args, **_kwargs: "Felix")
    monkeypatch.setattr(elo_route.db, "is_player_private", lambda *_args, **_kwargs: True)

    ctx = _FakeCtx(author_id=55)
    asyncio.run(elo_route.handle_elo(ctx, tuple(), "/tmp/test.db"))

    assert ctx.messages == ["Private players cannot use `champselo`."]
