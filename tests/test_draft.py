import asyncio
import random

from champs.db import db
from champs.draft import (
    DraftPlayer,
    _best_team_assignment,
    _build_draft,
    _parse_draft_args,
    handle_draft,
)


def test_parse_draft_args_supports_explicit_and_opt_in_out() -> None:
    explicit, added, removed, wants_help = _parse_draft_args(
        ("Felix", "Wyn", "+Sean", "-Petez", "--help")
    )
    assert explicit == ["Felix", "Wyn"]
    assert added == ["Sean"]
    assert removed == ["Petez"]
    assert wants_help is True


def test_best_team_assignment_prefers_secondary_over_offrole() -> None:
    team = (
        DraftPlayer(name="TopMain", elo=1100, primary_role="TOP", secondary_role=None),
        DraftPlayer(name="TopJgl", elo=1100, primary_role="TOP", secondary_role="JUNGLE"),
        DraftPlayer(name="MidMain", elo=1100, primary_role="MID", secondary_role=None),
        DraftPlayer(name="BotMain", elo=1100, primary_role="BOT", secondary_role=None),
        DraftPlayer(name="SuppMain", elo=1100, primary_role="SUPP", secondary_role=None),
    )

    drafted = _best_team_assignment(team)
    role_by_player = {row.player.name: row.role for row in drafted.assignments}
    penalty_by_player = {row.player.name: row.penalty for row in drafted.assignments}

    assert role_by_player["TopMain"] == "TOP"
    assert role_by_player["TopJgl"] == "JUNGLE"
    assert penalty_by_player["TopMain"] == 0
    assert penalty_by_player["TopJgl"] == 20


def test_build_draft_balances_teams_and_assigns_unique_roles() -> None:
    players = [
        DraftPlayer(name="A", elo=1200, primary_role="TOP", secondary_role=None),
        DraftPlayer(name="B", elo=1180, primary_role="JUNGLE", secondary_role=None),
        DraftPlayer(name="C", elo=1160, primary_role="MID", secondary_role=None),
        DraftPlayer(name="D", elo=1140, primary_role="BOT", secondary_role=None),
        DraftPlayer(name="E", elo=1120, primary_role="SUPP", secondary_role=None),
        DraftPlayer(name="F", elo=1100, primary_role="TOP", secondary_role=None),
        DraftPlayer(name="G", elo=1080, primary_role="JUNGLE", secondary_role=None),
        DraftPlayer(name="H", elo=1060, primary_role="MID", secondary_role=None),
        DraftPlayer(name="I", elo=1040, primary_role="BOT", secondary_role=None),
        DraftPlayer(name="J", elo=1020, primary_role="SUPP", secondary_role=None),
    ]

    result = _build_draft(players)

    blue_roles = {row.role for row in result.blue.assignments}
    red_roles = {row.role for row in result.red.assignments}
    all_names = {row.player.name for row in result.blue.assignments} | {
        row.player.name for row in result.red.assignments
    }
    adjusted_gap = abs(result.blue.adjusted_total_elo - result.red.adjusted_total_elo)

    assert blue_roles == {"TOP", "JUNGLE", "MID", "BOT", "SUPP"}
    assert red_roles == {"TOP", "JUNGLE", "MID", "BOT", "SUPP"}
    assert len(all_names) == 10
    assert adjusted_gap <= 20


def test_build_draft_randomized_mode_is_seed_reproducible() -> None:
    players = [
        DraftPlayer(name="A", elo=1200, primary_role="TOP", secondary_role=None),
        DraftPlayer(name="B", elo=1180, primary_role="JUNGLE", secondary_role=None),
        DraftPlayer(name="C", elo=1160, primary_role="MID", secondary_role=None),
        DraftPlayer(name="D", elo=1140, primary_role="BOT", secondary_role=None),
        DraftPlayer(name="E", elo=1120, primary_role="SUPP", secondary_role=None),
        DraftPlayer(name="F", elo=1100, primary_role="TOP", secondary_role=None),
        DraftPlayer(name="G", elo=1080, primary_role="JUNGLE", secondary_role=None),
        DraftPlayer(name="H", elo=1060, primary_role="MID", secondary_role=None),
        DraftPlayer(name="I", elo=1040, primary_role="BOT", secondary_role=None),
        DraftPlayer(name="J", elo=1020, primary_role="SUPP", secondary_role=None),
    ]

    draft_one = _build_draft(players, randomize=True, rng=random.Random(42))
    draft_two = _build_draft(players, randomize=True, rng=random.Random(42))

    blue_one = tuple((row.role, row.player.name) for row in draft_one.blue.assignments)
    red_one = tuple((row.role, row.player.name) for row in draft_one.red.assignments)
    blue_two = tuple((row.role, row.player.name) for row in draft_two.blue.assignments)
    red_two = tuple((row.role, row.player.name) for row in draft_two.red.assignments)

    assert blue_one == blue_two
    assert red_one == red_two


class _FakeCtx:
    def __init__(self, guild=None) -> None:
        self.guild = guild
        self.messages: list[str] = []

    async def send(self, message: str) -> None:
        self.messages.append(message)


def test_handle_draft_errors_when_mapping_missing(tmp_path) -> None:
    db_path = str(tmp_path / "draft_missing_mapping.db")
    db.init_db(db_path)
    ctx = _FakeCtx()

    asyncio.run(handle_draft(ctx, ("UnknownUser",), db_path))

    assert len(ctx.messages) == 1
    message = ctx.messages[0]
    assert "Unknown username -> name mappings" in message
    assert "champsmatch addplayer UnknownUser <name> <primary_role> <secondary_role>" in message
    assert "<league name (no tag)>" in message


def test_handle_draft_errors_when_roles_missing(tmp_path) -> None:
    db_path = str(tmp_path / "draft_missing_roles.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "Wyn", "Wyn")
    ctx = _FakeCtx()

    asyncio.run(handle_draft(ctx, ("Wyn",), db_path))

    assert len(ctx.messages) == 1
    message = ctx.messages[0]
    assert "Players missing primary and/or secondary role" in message
    assert "champsmatch addplayer Wyn Wyn <primary_role> <secondary_role>" in message


def test_handle_draft_uses_discord_id_mapping_for_voice_members(tmp_path) -> None:
    class _Member:
        def __init__(self, user_id: int, name: str) -> None:
            self.id = user_id
            self.bot = False
            self.display_name = name
            self.global_name = None
            self.name = name

    class _VoiceChannel:
        def __init__(self, channel_id: int, members) -> None:
            self.id = channel_id
            self.members = members

    class _Guild:
        def __init__(self, channels) -> None:
            self.voice_channels = channels
            self.afk_channel = None

    db_path = str(tmp_path / "draft_voice_discord_mapping.db")
    db.init_db(db_path)

    role_pairs = [
        ("TOP", "JUNGLE"),
        ("JUNGLE", "TOP"),
        ("MID", "BOT"),
        ("BOT", "SUPP"),
        ("SUPP", "MID"),
        ("TOP", "MID"),
        ("JUNGLE", "SUPP"),
        ("MID", "TOP"),
        ("BOT", "JUNGLE"),
        ("SUPP", "BOT"),
    ]
    for idx, (primary, secondary) in enumerate(role_pairs, start=1):
        league_username = f"League{idx}"
        actual_name = f"Player{idx}"
        db.set_player_mapping(db_path, league_username, actual_name, primary, secondary)
        db.set_discord_player_mapping(db_path, 1000 + idx, league_username)

    members = [_Member(1000 + i, f"DiscordAlias{i}") for i in range(1, 11)]
    guild = _Guild([_VoiceChannel(1, members)])
    ctx = _FakeCtx(guild=guild)

    asyncio.run(handle_draft(ctx, tuple(), db_path))

    assert len(ctx.messages) == 1
    assert "Blue Team" in ctx.messages[0]
    assert "Red Team" in ctx.messages[0]


def test_handle_draft_ignores_unlinked_voice_members(tmp_path) -> None:
    class _Member:
        def __init__(self, user_id: int, name: str) -> None:
            self.id = user_id
            self.bot = False
            self.display_name = name
            self.global_name = None
            self.name = name

    class _VoiceChannel:
        def __init__(self, channel_id: int, members) -> None:
            self.id = channel_id
            self.members = members

    class _Guild:
        def __init__(self, channels) -> None:
            self.voice_channels = channels
            self.afk_channel = None

    db_path = str(tmp_path / "draft_voice_unlinked_ignored.db")
    db.init_db(db_path)

    role_pairs = [
        ("TOP", "JUNGLE"),
        ("JUNGLE", "TOP"),
        ("MID", "BOT"),
        ("BOT", "SUPP"),
        ("SUPP", "MID"),
        ("TOP", "MID"),
        ("JUNGLE", "SUPP"),
        ("MID", "TOP"),
        ("BOT", "JUNGLE"),
        ("SUPP", "BOT"),
    ]
    for idx, (primary, secondary) in enumerate(role_pairs, start=1):
        league_username = f"League{idx}"
        actual_name = f"Player{idx}"
        db.set_player_mapping(db_path, league_username, actual_name, primary, secondary)
        db.set_discord_player_mapping(db_path, 2000 + idx, league_username)

    linked_members = [_Member(2000 + i, f"LinkedDiscord{i}") for i in range(1, 11)]
    unlinked_members = [_Member(9001, "RandomFriend"), _Member(9002, "AnotherGuest")]
    guild = _Guild([_VoiceChannel(1, linked_members + unlinked_members)])
    ctx = _FakeCtx(guild=guild)

    asyncio.run(handle_draft(ctx, tuple(), db_path))

    assert len(ctx.messages) == 1
    assert "Blue Team" in ctx.messages[0]
    assert "Red Team" in ctx.messages[0]
    assert "Unknown username -> name mappings" not in ctx.messages[0]
