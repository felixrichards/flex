import asyncio

from champs import match


class _FakeCtx:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_handle_match_addplayer_preserves_primary_secondary_order(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None, str | None]] = []

    def _fake_set_player_mapping(_db_path, username, name, primary_role=None, secondary_role=None):
        calls.append((username, name, primary_role, secondary_role))

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(match.db, "set_player_mapping", _fake_set_player_mapping)
    monkeypatch.setattr(match.asyncio, "to_thread", _fake_to_thread)

    ctx = _FakeCtx()
    asyncio.run(match._handle_match_addplayer(ctx, ["MaBalls", "Felix", "adc", "top"], "/tmp/test.db"))

    assert calls == [("MaBalls", "Felix", "adc", "top")]
    assert ctx.messages == ["Saved mapping: `MaBalls` -> `Felix` for roles `adc`/`top`"]
