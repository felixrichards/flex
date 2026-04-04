from datetime import timezone
import os

import manual_elo
from champs.db import db
from champs.db.models import MatchPlayerRecord, MatchRecord, PlayerRecord
from champs.payloads import Match
from sqlalchemy import select
from sqlalchemy.orm import Session


def _row(player: str) -> dict:
    return {"player": player, "champion": "Ezreal", "kda": "1/2/3"}


def _match_payload(date: str) -> dict:
    return {
        "win": [_row(f"w{i}") for i in range(5)],
        "lose": [_row(f"l{i}") for i in range(5)],
        "date": date,
    }


def _elo_match(win_names, lose_names) -> Match:
    return Match.model_validate(
        {
            "win": [{"player": name, "champion": "Ezreal", "kda": "1/1/1"} for name in win_names],
            "lose": [{"player": name, "champion": "Nami", "kda": "1/1/1"} for name in lose_names],
        }
    )


def test_load_matches_uses_date_for_timestamp() -> None:
    match = manual_elo._load_matches(_match_payload("05/04/2026"))[0]
    assert match.timestamp.tzinfo == timezone.utc
    assert match.timestamp.year == 2026
    assert match.timestamp.month == 4
    assert match.timestamp.day == 5
    assert match.timestamp.hour == 12


def test_insert_matches_sorts_by_timestamp(monkeypatch) -> None:
    early = manual_elo._load_matches(_match_payload("01/01/2024"))[0]
    late = manual_elo._load_matches(_match_payload("01/01/2025"))[0]
    call_order: list[object] = []

    def fake_insert_match(_db_path, match):
        call_order.append(match.timestamp)
        return True

    monkeypatch.setattr(manual_elo.db, "insert_match", fake_insert_match)
    inserted, skipped = manual_elo._insert_matches("/tmp/unused.db", [late, early])

    assert inserted == 2
    assert skipped == 0
    assert call_order == sorted(call_order)


def test_load_player_mappings_accepts_players_wrapper() -> None:
    payload = {
        "players": [
            {
                "username": "MaBalls",
                "name": "Felix",
                "primary_role": "JUNGLE",
                "secondary_role": "TOP",
            }
        ]
    }
    rows = manual_elo._load_player_mappings(payload)
    assert len(rows) == 1
    assert rows[0].username == "MaBalls"
    assert rows[0].name == "Felix"
    assert rows[0].primary_role == "JUNGLE"
    assert rows[0].secondary_role == "TOP"


def test_load_player_mappings_accepts_list_shape() -> None:
    payload = [
        {"username": "Wyn", "name": "Wyn", "primary_role": "BOT"},
        {"username": "Wyn", "name": "Sean"},
    ]
    rows = manual_elo._load_player_mappings(payload)
    assert len(rows) == 2
    assert rows[0].primary_role == "BOT"
    assert rows[1].secondary_role is None


def test_get_player_mapping_rows_groups_usernames_by_name_and_latest_roles(tmp_path) -> None:
    db_path = str(tmp_path / "manual_elo_player_mappings.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "AliasOne", "Felix", "MID", "BOT")
    db.set_player_mapping(db_path, "AliasTwo", "Felix")
    db.set_player_mapping(db_path, "AliasThree", "Felix", "TOP", "JUNGLE")
    db.set_discord_player_mapping(db_path, 111, "AliasOne")
    db.set_discord_player_mapping(db_path, 222, "AliasTwo")

    rows = manual_elo._get_player_mapping_rows(db_path)
    felix = [row for row in rows if row[0] == "Felix"]
    assert len(felix) == 1
    _, usernames, primary, secondary, discord_ids = felix[0]
    username_tokens = {token.strip() for token in usernames.split(",")}
    assert {"AliasOne", "AliasTwo", "AliasThree"}.issubset(username_tokens)
    assert primary == "TOP"
    assert secondary == "JUNGLE"
    discord_tokens = {token.strip() for token in discord_ids.split(",")}
    assert {"111", "222"}.issubset(discord_tokens)


def test_ensure_players_exist_adds_missing_and_skips_existing(tmp_path) -> None:
    db_path = str(tmp_path / "manual_elo_add_players.db")
    db.init_db(db_path)

    added_first = manual_elo._ensure_players_exist(db_path, ["Felix", "Wyn", "Felix"])
    assert added_first == 2

    engine = db._engine(db_path)
    with Session(engine) as session:
        names = set(session.scalars(select(PlayerRecord.name)).all())
    assert {"Felix", "Wyn"}.issubset(names)

    added_second = manual_elo._ensure_players_exist(db_path, ["Felix", "Jay"])
    assert added_second == 1

    with Session(engine) as session:
        final_names = set(session.scalars(select(PlayerRecord.name)).all())
    assert {"Felix", "Wyn", "Jay"}.issubset(final_names)


def test_should_print_ratings_only_for_rating_relevant_actions() -> None:
    class Args:
        def __init__(
            self,
            *,
            input_file=None,
            players_file=None,
            recalculate=False,
            reset_history=False,
            soft_reset=False,
            set_mapping=None,
            set_preferred_role=None,
            show_player_mappings=False,
        ) -> None:
            self.input_file = input_file
            self.players_file = players_file
            self.recalculate = recalculate
            self.reset_history = reset_history
            self.soft_reset = soft_reset
            self.set_mapping = set_mapping
            self.set_preferred_role = set_preferred_role
            self.show_player_mappings = show_player_mappings

    assert manual_elo._should_print_ratings(Args(show_player_mappings=True)) is False
    assert manual_elo._should_print_ratings(Args(players_file="players.json")) is True
    assert manual_elo._should_print_ratings(Args(recalculate=True)) is True
    assert manual_elo._should_print_ratings(Args(reset_history=True)) is True
    assert manual_elo._should_print_ratings(Args(soft_reset=True)) is True


def test_should_print_player_mappings_for_show_flag_or_players_file() -> None:
    class Args:
        def __init__(self, *, players_file=None, show_player_mappings=False) -> None:
            self.players_file = players_file
            self.show_player_mappings = show_player_mappings

    assert manual_elo._should_print_player_mappings(Args(players_file="players.json")) is True
    assert manual_elo._should_print_player_mappings(Args(show_player_mappings=True)) is True
    assert manual_elo._should_print_player_mappings(Args()) is False


def test_reset_history_and_ratings_clears_matches_and_resets_player_elo(tmp_path) -> None:
    db_path = str(tmp_path / "manual_elo_reset.db")
    db.init_db(db_path)

    db.set_player_mapping(db_path, "W1", "W1")
    db.set_player_mapping(db_path, "W2", "W2")
    db.set_player_mapping(db_path, "W3", "W3")
    db.set_player_mapping(db_path, "W4", "W4")
    db.set_player_mapping(db_path, "W5", "W5")
    db.set_player_mapping(db_path, "L1", "L1")
    db.set_player_mapping(db_path, "L2", "L2")
    db.set_player_mapping(db_path, "L3", "L3")
    db.set_player_mapping(db_path, "L4", "L4")
    db.set_player_mapping(db_path, "L5", "L5")

    match = _elo_match(["W1", "W2", "W3", "W4", "W5"], ["L1", "L2", "L3", "L4", "L5"])
    assert db.insert_match(db_path, match) is True

    deleted_matches, deleted_rows, reset_players = manual_elo._reset_history_and_ratings(db_path)
    assert deleted_matches == 1
    assert deleted_rows == 10
    assert reset_players >= 10

    engine = db._engine(db_path)
    with Session(engine) as session:
        assert len(session.scalars(select(MatchRecord)).all()) == 0
        assert len(session.scalars(select(MatchPlayerRecord)).all()) == 0
        players = session.scalars(select(PlayerRecord)).all()
    assert players
    assert all(int(player.rating) == db.INITIAL_RATING for player in players)


def test_backup_db_file_creates_timestamped_copy(tmp_path) -> None:
    db_path = str(tmp_path / "manual_elo_backup.db")
    db.init_db(db_path)
    assert os.path.exists(db_path)

    backup_path = manual_elo._backup_db_file(db_path)
    assert os.path.exists(backup_path)
    assert backup_path.startswith(db_path + ".backup-")


def test_soft_reset_ratings_compresses_towards_target(tmp_path) -> None:
    db_path = str(tmp_path / "manual_elo_soft_reset.db")
    db.init_db(db_path)

    manual_elo._ensure_players_exist(db_path, ["High", "Low", "Neutral"])
    engine = db._engine(db_path)
    with Session(engine) as session:
        high = session.get(PlayerRecord, "High")
        low = session.get(PlayerRecord, "Low")
        neutral = session.get(PlayerRecord, "Neutral")
        assert high is not None and low is not None and neutral is not None
        high.rating = 1100
        low.rating = 900
        neutral.rating = 1000
        session.commit()

    updated_players, total_delta = manual_elo._soft_reset_ratings(db_path, factor=0.2, target=1000)
    assert updated_players == 3
    assert total_delta == 160.0

    with Session(engine) as session:
        high = session.get(PlayerRecord, "High")
        low = session.get(PlayerRecord, "Low")
        neutral = session.get(PlayerRecord, "Neutral")
        assert high is not None and low is not None and neutral is not None
        assert int(high.rating) == 1020
        assert int(low.rating) == 980
        assert int(neutral.rating) == 1000
