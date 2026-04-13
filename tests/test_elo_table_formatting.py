import asyncio

from champs import elo as elo_route
from champs.db.db import EloRow


class _FakeCtx:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_champselo_full_table_uses_short_headers_and_hides_elo(monkeypatch) -> None:
    rows = [
        EloRow(rank=1, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)

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
        EloRow(rank=1, player="Felix", cp=1010, elo=980, wins=10, losses=4, dodges=2, dodge_scale=1.2),
    ]

    monkeypatch.setattr(elo_route.db, "get_elo_rows", lambda *_args, **_kwargs: rows)

    ctx = _FakeCtx()
    asyncio.run(elo_route.handle_elo(ctx, ("Felix",), "/tmp/test.db"))

    text = ctx.messages[0]
    assert "Rank" in text
    assert "Player" in text
    assert "Wins" in text
    assert "Losses" in text
    assert "Dodges" in text
    assert "Scale" in text
    assert "ELO" not in text
