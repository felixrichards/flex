from sqlalchemy import select
from sqlalchemy.orm import Session

from champs.db import db
from champs.db.models import MatchPlayerRecord, MatchRecord, PlayerMappingRecord, PlayerRecord
from champs.payloads import Match


def _make_match(win_names, lose_names) -> Match:
    return Match.model_validate(
        {
            "win": [{"player": name, "champion": "Ezreal", "kda": "1/1/1"} for name in win_names],
            "lose": [{"player": name, "champion": "Nami", "kda": "1/1/1"} for name in lose_names],
            "date": None,
        }
    )


def _ratings(db_path: str) -> dict[str, int]:
    engine = db._engine(db_path)
    with Session(engine) as session:
        rows = session.scalars(select(PlayerRecord)).all()
        return {row.name: row.rating for row in rows}


def test_iterative_elo_and_duplicate_guard(tmp_path) -> None:
    db_path = str(tmp_path / "elo.db")
    db.init_db(db_path)

    winners = ["A", "B", "C", "D", "E"]
    losers = ["F", "G", "H", "I", "J"]

    match1 = _make_match(winners, losers)
    assert db.insert_match(db_path, match1) is True

    after_first = _ratings(db_path)
    assert after_first["A"] == 1016
    assert after_first["F"] == 984

    match2 = _make_match(winners, losers)
    assert db.insert_match(db_path, match2) is False

    match3 = _make_match(["A", "B", "C", "D", "X"], ["F", "G", "H", "I", "Y"])
    assert db.insert_match(db_path, match3) is True
    after_second = _ratings(db_path)
    assert after_second["A"] > after_first["A"]
    assert after_second["F"] < after_first["F"]
    assert "X" in after_second
    assert "Y" in after_second


def test_insert_match_rejects_missing_checksum(tmp_path) -> None:
    db_path = str(tmp_path / "elo_missing_checksum.db")
    db.init_db(db_path)
    match = _make_match(["A", "B", "C", "D", "E"], ["F", "G", "H", "I", "J"])
    checksumless = match.model_copy(update={"checksum": None})

    assert db.insert_match(db_path, checksumless) is False

    engine = db._engine(db_path)
    with Session(engine) as session:
        match_count = session.scalars(select(MatchRecord)).all()
    assert len(match_count) == 0


def test_match_rows_store_username_and_resolved_name(tmp_path) -> None:
    db_path = str(tmp_path / "elo_usernames.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "AlphaUser", "Alpha")
    db.set_player_mapping(db_path, "BravoUser", "Bravo")
    match = _make_match(
        ["AlphaUser", "BravoUser", "C", "D", "E"],
        ["F", "G", "H", "I", "J"],
    )
    assert db.insert_match(db_path, match) is True

    engine = db._engine(db_path)
    with Session(engine) as session:
        rows = session.scalars(select(MatchPlayerRecord)).all()
    by_username = {row.player_username: row.player_name for row in rows}
    assert by_username["AlphaUser"] == "Alpha"
    assert by_username["BravoUser"] == "Bravo"


def test_recalculate_refreshes_player_name_mappings(tmp_path) -> None:
    db_path = str(tmp_path / "elo_remap.db")
    db.init_db(db_path)
    db.set_player_mapping(db_path, "AliasUser", "OldName")
    match = _make_match(
        ["AliasUser", "B", "C", "D", "E"],
        ["F", "G", "H", "I", "J"],
    )
    assert db.insert_match(db_path, match) is True

    db.set_player_mapping(db_path, "AliasUser", "NewName")
    db.recalculate_all_ratings(db_path, refresh_mappings=True)

    engine = db._engine(db_path)
    with Session(engine) as session:
        mapped_rows = session.scalars(
            select(MatchPlayerRecord).where(MatchPlayerRecord.player_username == "AliasUser")
        ).all()
        players = {row.name: row.rating for row in session.scalars(select(PlayerRecord)).all()}
        mappings = {row.username: row.name for row in session.scalars(select(PlayerMappingRecord)).all()}

    assert mapped_rows
    assert all(row.player_name == "NewName" for row in mapped_rows)
    assert "NewName" in players
    assert mappings["AliasUser"] == "NewName"


def test_delete_match_removes_rows_and_rewinds_ratings(tmp_path) -> None:
    db_path = str(tmp_path / "elo_delete.db")
    db.init_db(db_path)

    first = _make_match(["A", "B", "C", "D", "E"], ["F", "G", "H", "I", "J"])
    second = _make_match(["A", "B", "C", "D", "X"], ["F", "G", "H", "I", "Y"])
    assert db.insert_match(db_path, first) is True
    ratings_after_first = _ratings(db_path)
    assert db.insert_match(db_path, second) is True
    ratings_after_second = _ratings(db_path)
    assert ratings_after_second["A"] > ratings_after_first["A"]

    assert db.delete_match(db_path, second.checksum or "") is True
    assert db.delete_match(db_path, second.checksum or "") is False

    engine = db._engine(db_path)
    with Session(engine) as session:
        checksums = set(session.scalars(select(MatchRecord.checksum)).all())
        players = set(session.scalars(select(PlayerRecord.name)).all())

    assert first.checksum in checksums
    assert second.checksum not in checksums
    assert "X" not in players
    assert "Y" not in players
    assert _ratings(db_path)["A"] == ratings_after_first["A"]


def test_recalculate_reassigns_to_existing_player_identity(tmp_path) -> None:
    db_path = str(tmp_path / "elo_existing_player_merge.db")
    db.init_db(db_path)

    base_match = _make_match(
        ["ExistingUser", "B", "C", "D", "E"],
        ["F", "G", "H", "I", "J"],
    )
    assert db.insert_match(db_path, base_match) is True

    db.set_player_mapping(db_path, "AltUser", "AltUser")
    alt_match = _make_match(
        ["AltUser", "B2", "C2", "D2", "E2"],
        ["F2", "G2", "H2", "I2", "J2"],
    )
    assert db.insert_match(db_path, alt_match) is True

    db.set_player_mapping(db_path, "AltUser", "ExistingUser")
    db.recalculate_all_ratings(db_path, refresh_mappings=True)

    engine = db._engine(db_path)
    with Session(engine) as session:
        players = {row.name: row.rating for row in session.scalars(select(PlayerRecord)).all()}
        alt_rows = session.scalars(
            select(MatchPlayerRecord).where(MatchPlayerRecord.player_username == "AltUser")
        ).all()

    assert alt_rows
    assert all(row.player_name == "ExistingUser" for row in alt_rows)
    assert "AltUser" not in players
    assert "ExistingUser" in players
